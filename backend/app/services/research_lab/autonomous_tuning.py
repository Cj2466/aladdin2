"""Per-candidate parameter tuning for the autonomous daily research loop.

Until this module existed, AutonomousResearchRunner backtested and
forward-validation-registered every top screening candidate with that
strategy's fixed DEFAULT_* constants — one-size-fits-all parameters
regardless of the individual ticker's or pair's own behavior. The
parameter-sweep machinery to do better already existed (sweep_service /
sweep_runner / the /api/research-lab/sweeps router) but was only ever
reachable by a human submitting a sweep through the UI.

This module is the seam between the two. It is deliberately a *service*
(pure-ish selection logic, independently testable) rather than more
methods on the runner, matching how screening.py/forward_validation_service.py
sit beside screening_runner.py/forward_validation_runner.py.

The load-bearing statistical decision: selecting "whichever combination
had the best raw Sharpe" out of a grid is itself a multiple-comparisons
problem — exactly the false-discovery risk deflated_sharpe.py (Phase 2.5)
exists to correct. Ranking by raw Sharpe here would silently reintroduce
it at the one point in the system that runs unattended every day. So the
grid is ranked by each combination's own deflated Sharpe ratio, computed
through compute_deflated_sharpe with the *same* sibling-trial semantics
routers/research_lab.py::get_experiment_run_detail already uses (n_trials
and sigma_SR derived from every stored ExperimentRun sharing this
strategy/ticker_a/ticker_b), not a parallel selection rule invented here.

Why DSR ranking is not just a monotone re-labelling of Sharpe ranking:
all combinations in one grid share the same n_trials and sigma_SR (they
are siblings of the same search), so SR0 is identical across them — but
each combination's own n_observations, skewness and kurtosis differ, and
those enter the PSR z-statistic. In particular a longer fit_window_days
consumes more of the series as burn-in and leaves *fewer* out-of-sample
observations, so a marginally-higher Sharpe measured over fewer days can
and does lose to a slightly lower Sharpe measured over more. That is the
honest correction, and it is precisely what raw-Sharpe ranking hides.

Measured, not assumed: this grid was run against 23 real candidates
(15 momentum tickers, 8 pairs) over real 5-year price history this
session. DSR ranking picked a *different* configuration than raw-Sharpe
ranking on 3 of them (13%) — a real but not overwhelming effect, stated
at the size actually observed rather than the size the correction's
reputation might imply. Both mechanisms showed up in those 3:
  - C/GS: raw Sharpe picks fit=504 (SR 1.276 over 749 out-of-sample
    days); DSR picks fit=252 (SR 1.204 over 1001 days) — 252 extra days
    of evidence outweigh 0.07 of Sharpe.
  - AAPL/MSFT: raw Sharpe picks fit=252 (SR 0.662, but skew 4.20 /
    kurtosis 55.4); DSR picks fit=504 (SR 0.568, skew 2.94 / kurtosis
    33.0) — the PSR variance term penalizes the fat-tailed series enough
    to flip the ranking despite it having both a higher Sharpe and more
    observations. So this is not merely "prefer more days"; it is the
    full non-normality correction.
The other 20 agreed, which is the expected and honest outcome: the
deflation is a correction to a selection rule, not a replacement for it.
Separately, 22 of the 23 tuned configurations differed from the
strategy's bare DEFAULT_* constants — the change this module makes to
daily behaviour is real and near-universal, not marginal.
"""

import logging
from dataclasses import dataclass
from typing import Literal

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.experiment_run import ExperimentRun
from app.models.forward_validation import ForwardValidationRegistration
from app.schemas.research_lab import PairsBacktestResponse
from app.schemas.sweep import SweepGridSpec
from app.services.market_data.base import MarketDataError, MarketDataProvider
from app.services.research_lab import momentum, ou_pairs
from app.services.research_lab.backtest_result import (
    run_and_store_momentum_backtest,
    run_and_store_pairs_backtest,
)
from app.services.research_lab.deflated_sharpe import (
    MIN_TRIALS_FOR_DSR,
    compute_deflated_sharpe,
    derive_returns_from_equity_curve,
)
from app.services.research_lab.sweep_service import expand_sweep_grid
from app.services.risk.errors import InsufficientHistoryError, MissingTickerDataError

logger = logging.getLogger(__name__)


# --- the grid -----------------------------------------------------------------
#
# Deliberately tiny next to MAX_SWEEP_COMBINATIONS=500 (what a human may
# explore by hand): 3 fit_window_days x 3 entry_z x 1 exit_z x 1 cost_bps
# = 9 combinations, 1.8% of the manual ceiling. Sizing reasoning, in the
# same daily-cost register as AUTO_BACKTEST_TOP_K's own comment:
#
# - Storage is the binding constraint, not compute. Measured directly
#   against this project's own dev DB this session: the 44 real
#   ExperimentRun rows average 98KB of results_json each (max 114KB) —
#   the stored equity curve dominates. Every grid combination that runs
#   becomes a permanent ExperimentRun row, so grid size multiplies the
#   ~1MB/day the autonomous loop already writes.
# - 9 combinations sits above MIN_TRIALS_FOR_DSR=5 with real headroom, so
#   a couple of combinations failing (a long fit window a young ticker
#   can't support, say) still leaves enough siblings for the DSR
#   benchmark to be estimable at all. A 6-combination grid would land
#   exactly on that floor with none to spare.
# - Only two axes are searched, and that is a statement about what may
#   honestly be optimized, not just a cost bound. cost_bps is an
#   assumption about the world (what trading actually costs), not a
#   strategy knob — "tuning" it downward would manufacture edge out of
#   nothing. lookback_years is likewise fixed at each strategy's
#   DEFAULT_LOOKBACK_YEARS: searching it would be choosing the historical
#   period that flatters the result, the single most classic form of the
#   backtest overfitting this whole project is built to resist. exit_z is
#   held at the strategy default purely to bound the grid.
# - fit_window_days values are ~0.5x/1x/2x each strategy's own default,
#   clamped into SweepGridSpec's own validated [60, 756] range (momentum's
#   0.5x would be 45, below that floor, so 60 is used). Each grid is
#   constructed as a real SweepGridSpec so those validators police these
#   constants too, and expanded through sweep_service.expand_sweep_grid
#   so the exit_z < entry_z invariant is enforced by the same one
#   implementation a manual sweep uses.
# - Every grid contains that strategy's own DEFAULT_* configuration, so
#   the defaults compete on exactly equal footing: tuning can only ever
#   pick something the deflated Sharpe ranked at or above the default.
AUTO_TUNING_GRIDS: dict[str, SweepGridSpec] = {
    momentum.STRATEGY_NAME: SweepGridSpec(
        fit_window_days=[60, momentum.DEFAULT_FIT_WINDOW_DAYS, 180],
        entry_z=[1.5, momentum.DEFAULT_ENTRY_Z, 2.5],
        exit_z=[momentum.DEFAULT_EXIT_Z],
        cost_bps=[momentum.DEFAULT_COST_BPS],
    ),
    ou_pairs.STRATEGY_NAME: SweepGridSpec(
        fit_window_days=[126, ou_pairs.DEFAULT_FIT_WINDOW_DAYS, 504],
        entry_z=[1.5, ou_pairs.DEFAULT_ENTRY_Z, 2.5],
        exit_z=[ou_pairs.DEFAULT_EXIT_Z],
        cost_bps=[ou_pairs.DEFAULT_COST_BPS],
    ),
}

# Hard per-job/day ceiling on how many *fresh* tunings may run, so the
# worst case is bounded rather than merely improbable. Candidates past it
# fall back to their strategy's defaults for that day and get tuned on a
# later day once they're still in the top-K (they almost always are — see
# the churn measurement below).
#
# Sized against real measured churn, not a guess. Replaying this project's
# own screening functions over the locally cached 515-ticker price history
# at several as-of offsets this session:
#   - momentum top-5 kept 4-5 of 5 members at offsets of 1/2/3/5/10/20
#     trading days -> ~1 new entrant per 20 trading days = 0.05/day.
#   - pairs top-5 kept 3 of 4-5 members between offsets 5 and 20 -> ~2 new
#     entrants per 15 trading days = 0.13/day.
# So the realistic cost is ~0.2 fresh tunings/day across both strategies
# (~18KB/day of new rows), and this cap of 2 per job leaves >10x headroom
# over that while capping the pathological "every top-5 slot churns every
# weekday" case at 9 x 2 x 2 strategies x ~90 weekdays ~= 3,200 rows
# ~= 320MB — which, added to the ~90MB the loop already writes over the
# same window, still fits inside Neon's free-tier 0.5GB ceiling (the same
# real dollar ceiling MAX_SWEEP_COMBINATIONS cites).
MAX_NEW_TUNINGS_PER_JOB = 2


@dataclass(frozen=True)
class StrategyConfig:
    """The 4 tunable walk-forward parameters — exactly the 4 that
    compute_forward_validation_config_hash folds into a registration's
    identity, and exactly the 4 axes SweepGridSpec exposes."""

    fit_window_days: int
    entry_z: float
    exit_z: float
    cost_bps: float


@dataclass(frozen=True)
class TuningOutcome:
    config: StrategyConfig
    source: Literal["tuned", "strategy_default", "existing_registration"]
    n_combinations_tested: int
    n_trials: int
    dsr: float | None
    sharpe_net: float | None
    note: str


def default_config(strategy_name: str) -> StrategyConfig:
    if strategy_name == momentum.STRATEGY_NAME:
        return StrategyConfig(
            fit_window_days=momentum.DEFAULT_FIT_WINDOW_DAYS,
            entry_z=momentum.DEFAULT_ENTRY_Z,
            exit_z=momentum.DEFAULT_EXIT_Z,
            cost_bps=momentum.DEFAULT_COST_BPS,
        )
    if strategy_name == ou_pairs.STRATEGY_NAME:
        return StrategyConfig(
            fit_window_days=ou_pairs.DEFAULT_FIT_WINDOW_DAYS,
            entry_z=ou_pairs.DEFAULT_ENTRY_Z,
            exit_z=ou_pairs.DEFAULT_EXIT_Z,
            cost_bps=ou_pairs.DEFAULT_COST_BPS,
        )
    raise ValueError(f"Unknown strategy_name: {strategy_name!r}")


def default_lookback_years(strategy_name: str) -> int:
    if strategy_name == momentum.STRATEGY_NAME:
        return momentum.DEFAULT_LOOKBACK_YEARS
    if strategy_name == ou_pairs.STRATEGY_NAME:
        return ou_pairs.DEFAULT_LOOKBACK_YEARS
    raise ValueError(f"Unknown strategy_name: {strategy_name!r}")


def build_tuning_grid(strategy_name: str) -> list[StrategyConfig]:
    """Expanded through sweep_service.expand_sweep_grid — the same one
    implementation (and the same exit_z < entry_z invariant) a manually
    submitted sweep goes through, not a second copy of it."""
    try:
        grid = AUTO_TUNING_GRIDS[strategy_name]
    except KeyError:
        raise ValueError(f"Unknown strategy_name: {strategy_name!r}") from None
    return [StrategyConfig(**combo) for combo in expand_sweep_grid(grid)]


def _run_one_combination(
    db: Session,
    provider: MarketDataProvider,
    *,
    strategy_name: str,
    ticker_a: str,
    ticker_b: str,
    config: StrategyConfig,
    lookback_years: int,
) -> PairsBacktestResponse | None:
    """One combination -> one real, stored, input_hash-deduped backtest,
    via the exact same run_and_store_* functions the runner already uses
    for its untuned backtest. Mirrors sweep_runner._process_combo's
    per-combination isolation: a combination that can't run (a fit window
    longer than this ticker's usable history, a provider failure that
    exhausted its retries) is logged and dropped, never allowed to take
    the rest of the grid down with it."""
    try:
        if strategy_name == momentum.STRATEGY_NAME:
            return run_and_store_momentum_backtest(
                db,
                provider,
                ticker=ticker_a,
                fit_window_days=config.fit_window_days,
                entry_z=config.entry_z,
                exit_z=config.exit_z,
                cost_bps=config.cost_bps,
                lookback_years=lookback_years,
            )
        return run_and_store_pairs_backtest(
            db,
            provider,
            ticker_a=ticker_a,
            ticker_b=ticker_b,
            fit_window_days=config.fit_window_days,
            entry_z=config.entry_z,
            exit_z=config.exit_z,
            cost_bps=config.cost_bps,
            lookback_years=lookback_years,
        )
    except (MarketDataError, MissingTickerDataError, InsufficientHistoryError):
        logger.warning(
            "Tuning combination failed for %s/%s (%s, fit=%s, entry_z=%s); dropping it from the grid.",
            ticker_a,
            ticker_b,
            strategy_name,
            config.fit_window_days,
            config.entry_z,
            exc_info=True,
        )
        return None


def sibling_trial_stats(
    db: Session, strategy_name: str, ticker_a: str, ticker_b: str
) -> tuple[int, float | None]:
    """(n_trials, sigma_SR_annualized) over every stored ExperimentRun for
    this exact strategy/ticker_a/ticker_b — lifted verbatim from
    routers/research_lab.py::get_experiment_run_detail so the tuning
    selection and the number the UI later shows for the winning run are
    computed from the same population, not two different notions of
    "how many trials was this one of". Because the grid's own runs are
    stored before this is called, they are counted here — as they should
    be: they *are* trials that were searched."""
    sibling_sharpes = (
        db.execute(
            select(ExperimentRun.sharpe_net).where(
                ExperimentRun.strategy_name == strategy_name,
                ExperimentRun.ticker_a == ticker_a,
                ExperimentRun.ticker_b == ticker_b,
                ExperimentRun.status == "ok",
                ExperimentRun.sharpe_net.is_not(None),
            )
        )
        .scalars()
        .all()
    )
    n_trials = len(sibling_sharpes)
    sigma_sr = float(np.std(sibling_sharpes, ddof=1)) if n_trials >= 2 else None
    return n_trials, sigma_sr


def select_tuned_config(
    db: Session,
    provider: MarketDataProvider,
    *,
    strategy_name: str,
    ticker_a: str,
    ticker_b: str,
) -> TuningOutcome:
    """Run the bounded grid for one candidate and return the combination
    with the highest deflated Sharpe ratio.

    Falls back to the strategy's own DEFAULT_* constants — a documented,
    expected outcome, not a failure state — whenever the search can't
    support an honest answer: too few combinations survived, fewer than
    MIN_TRIALS_FOR_DSR sibling trials exist, sigma_SR is unestimable, or
    no combination produced a finite DSR. Ranking by raw Sharpe in those
    cases would be strictly worse than not tuning at all, since it would
    hand back a search-selected maximum with no correction applied."""
    lookback_years = default_lookback_years(strategy_name)
    combos = build_tuning_grid(strategy_name)
    fallback = default_config(strategy_name)

    responses: list[tuple[StrategyConfig, PairsBacktestResponse]] = []
    for combo in combos:
        response = _run_one_combination(
            db,
            provider,
            strategy_name=strategy_name,
            ticker_a=ticker_a,
            ticker_b=ticker_b,
            config=combo,
            lookback_years=lookback_years,
        )
        if response is None or response.status != "ok" or response.sharpe_net is None:
            continue
        responses.append((combo, response))

    n_trials, sigma_sr = sibling_trial_stats(db, strategy_name, ticker_a, ticker_b)

    if not responses or n_trials < MIN_TRIALS_FOR_DSR or sigma_sr is None:
        return TuningOutcome(
            config=fallback,
            source="strategy_default",
            n_combinations_tested=len(responses),
            n_trials=n_trials,
            dsr=None,
            sharpe_net=None,
            note=(
                f"Tuning grid produced {len(responses)} usable configuration(s) and {n_trials} "
                f"sibling trial(s) (need >={MIN_TRIALS_FOR_DSR} with an estimable sigma_SR to deflate "
                "a search-selected maximum honestly). Falling back to the strategy's default "
                "configuration rather than selecting on uncorrected Sharpe."
            ),
        )

    best_config: StrategyConfig | None = None
    best_dsr: float | None = None
    best_sharpe: float | None = None
    for combo, response in responses:
        returns = derive_returns_from_equity_curve([p.equity for p in response.equity_curve])
        result = compute_deflated_sharpe(response.sharpe_net, returns, n_trials, sigma_sr)
        if result.dsr is None:
            continue
        if best_dsr is None or result.dsr > best_dsr:
            best_config, best_dsr, best_sharpe = combo, result.dsr, response.sharpe_net

    if best_config is None:
        return TuningOutcome(
            config=fallback,
            source="strategy_default",
            n_combinations_tested=len(responses),
            n_trials=n_trials,
            dsr=None,
            sharpe_net=None,
            note=(
                f"None of the {len(responses)} usable configuration(s) produced a finite deflated "
                "Sharpe ratio. Falling back to the strategy's default configuration."
            ),
        )

    return TuningOutcome(
        config=best_config,
        source="tuned",
        n_combinations_tested=len(responses),
        n_trials=n_trials,
        dsr=best_dsr,
        sharpe_net=best_sharpe,
        note=(
            f"Selected from {len(responses)} configuration(s) by deflated Sharpe ratio (not raw "
            f"Sharpe), deflated against N={n_trials} sibling trials on this strategy/ticker. "
            f"Winning configuration: fit_window_days={best_config.fit_window_days}, "
            f"entry_z={best_config.entry_z}, DSR={best_dsr:.3f}, raw Sharpe={best_sharpe:.3f}."
        ),
    )


def existing_registration_config(
    db: Session, *, user_id: int, strategy_name: str, ticker_a: str, ticker_b: str
) -> StrategyConfig | None:
    """The configuration this candidate is *already* being forward-validated
    under, if any. Ordered by id so the answer is the original registration
    and therefore deterministic across ticks."""
    row = (
        db.execute(
            select(ForwardValidationRegistration)
            .where(
                ForwardValidationRegistration.user_id == user_id,
                ForwardValidationRegistration.strategy_name == strategy_name,
                ForwardValidationRegistration.ticker_a == ticker_a,
                ForwardValidationRegistration.ticker_b == ticker_b,
            )
            .order_by(ForwardValidationRegistration.id)
        )
        .scalars()
        .first()
    )
    if row is None:
        return None
    return StrategyConfig(
        fit_window_days=row.fit_window_days,
        entry_z=row.entry_z,
        exit_z=row.exit_z,
        cost_bps=row.cost_bps,
    )


def resolve_candidate_config(
    db: Session,
    provider: MarketDataProvider,
    *,
    user_id: int,
    strategy_name: str,
    ticker_a: str,
    ticker_b: str,
    allow_tuning: bool = True,
) -> TuningOutcome:
    """The runner's single entry point: what configuration should this
    candidate be backtested and forward-validation-registered under today?

    Reuse-first, and that ordering is the load-bearing decision, not an
    optimization. A candidate already carrying a forward-validation
    registration keeps that registration's configuration verbatim; it is
    never re-tuned.

    Why re-tuning daily would be actively wrong: the top screening
    candidates barely churn (measured this session — momentum keeps 4-5 of
    its top 5 across 20 trading days), so the same ticker reappears almost
    every weekday. Re-running the grid on a rolling window would pick a
    slightly different "best" configuration on many of those days, and
    because compute_forward_validation_config_hash folds all 4 parameters
    into a registration's identity, each new winner would open a *brand
    new* registration at n_forward_trading_days=0. The old one would be
    abandoned mid-flight. Nothing would ever reach
    MIN_FORWARD_VALIDATION_TRADING_DAYS=126 — the single most load-bearing
    number in this project — no matter how many days passed. Tune once, at
    the moment a candidate first earns a registration; after that the
    registration's own configuration is its identity. This is the same
    "idempotent, never resets accumulated progress" principle
    register_or_get_forward_validation is already built around, applied
    one level up: idempotent in the *config*, not just in the row.

    A configuration that later proves bad is not stuck forever either —
    it gets caught by the existing underperformance rule
    (forward_validation_service.check_underperformance), and the runner's
    known-underperforming skip then frees the slot for the next-best
    candidate. That is the correct place for "this tuning was wrong" to be
    resolved: on 60 real forward days of evidence, not on a fresh
    in-sample re-search.

    This ordering also means the tuning grid never runs for a candidate
    that is about to be skipped as known-underperforming: such a candidate
    by definition already has a registration, so it takes the reuse path.
    """
    existing = existing_registration_config(
        db, user_id=user_id, strategy_name=strategy_name, ticker_a=ticker_a, ticker_b=ticker_b
    )
    if existing is not None:
        return TuningOutcome(
            config=existing,
            source="existing_registration",
            n_combinations_tested=0,
            n_trials=0,
            dsr=None,
            sharpe_net=None,
            note=(
                "Reusing the configuration this candidate is already being forward-validated "
                "under, so its accumulated out-of-sample day count keeps counting toward "
                "graduation instead of restarting at zero."
            ),
        )

    if not allow_tuning:
        return TuningOutcome(
            config=default_config(strategy_name),
            source="strategy_default",
            n_combinations_tested=0,
            n_trials=0,
            dsr=None,
            sharpe_net=None,
            note=(
                f"Per-job fresh-tuning budget (MAX_NEW_TUNINGS_PER_JOB={MAX_NEW_TUNINGS_PER_JOB}) "
                "already spent today; using the strategy's default configuration. This candidate "
                "is tuned on a later day if it stays in the top-K."
            ),
        )

    return select_tuned_config(
        db, provider, strategy_name=strategy_name, ticker_a=ticker_a, ticker_b=ticker_b
    )
