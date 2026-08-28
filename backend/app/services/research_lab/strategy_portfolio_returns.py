import json
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import (
    OPTIMIZATION_METHOD_HRP,
    OPTIMIZATION_METHOD_MEAN_VARIANCE,
    OPTIMIZATION_METHODS,
)
from app.models.experiment_run import ExperimentRun
from app.schemas.risk import PortfolioAnalyzeResponse
from app.services.market_data.base import MarketDataProvider
from app.services.market_data.price_cache import get_price_history_cached
from app.services.research_lab.deflated_sharpe import derive_returns_from_equity_curve
from app.services.risk import returns as returns_svc
from app.services.risk.engine import compute_portfolio_risk_from_returns
from app.services.risk.errors import (
    InsufficientHistoryError,
    MissingTickerDataError,
    OptimizationInfeasibleError,
    RiskComputationError,
)
from app.services.risk.hrp_optimizer import (
    compute_hrp_portfolio_optimization_from_returns,
)
from app.services.risk.optimizer import (
    DEFAULT_MAX_WEIGHT,
    OptimizationResult,
    compute_portfolio_optimization_from_returns,
)
from app.services.risk.volatility import TRADING_DAYS_PER_YEAR

# The label every error/warning from this module uses in place of the
# ticker-based feature's "holdings" — the assets here are backtested
# strategy instances, so "holdings" would be actively misleading.
STRATEGY_ASSET_LABEL = "selected strategies"


class MissingExperimentRunError(RiskComputationError):
    """A referenced experiment_run_id doesn't exist, or exists but has a
    non-"ok" status (so it has no usable equity curve). Raised lazily at
    analyze/optimize time rather than at CRUD time, mirroring the existing
    precedent that PortfolioCreate validates structure only (weight sum, no
    duplicates) and defers ticker-data-exists checks to /analyze."""

    def __init__(self, run_ids: list[int]) -> None:
        self.run_ids = run_ids
        super().__init__(
            "No usable backtest result for experiment run(s): "
            f"{', '.join(str(i) for i in sorted(run_ids))} — missing, or completed with a "
            'non-"ok" status.'
        )


def build_returns_frame(
    db: Session, run_ids: list[int]
) -> tuple[pd.DataFrame, dict[int, ExperimentRun]]:
    """Load each ExperimentRun's stored equity curve and turn the set into
    one date-indexed DataFrame of daily strategy returns, one column per
    run (column key = str(run_id)).

    Each column is derived via derive_returns_from_equity_curve, reused
    verbatim from the deflated-Sharpe work — it is the one function in this
    codebase that correctly reconstructs the walk-forward engine's
    observation 1 (the stored curve starts AFTER day one's return is
    applied; naively diffing it drops that observation and undercounts n by
    exactly one).

    The columns are INNER-joined on date, deliberately: a union/forward-fill
    join would let VaR and correlation be computed over dates where one
    leg's return is stale, silently misrepresenting exactly the tail
    co-movement this feature exists to measure. Measured on the real dev DB,
    the inner join costs almost nothing — a 4-strategy combo of real runs
    (pairs on PEP/KO, KO/PEP, AAPL/MSFT, GLD/SLV) retained 1002 overlapping
    trading days, 2022-08-24 -> 2026-08-21.

    Returns an EMPTY frame rather than raising on zero overlap — callers
    raise InsufficientHistoryError themselves, so nothing here touches
    .index on an empty frame."""
    if not run_ids:
        # An empty selection is "zero overlapping observations", not an
        # error to raise from here — the caller turns it into
        # InsufficientHistoryError, same as a genuine zero-overlap frame.
        return pd.DataFrame(), {}

    rows = db.execute(select(ExperimentRun).where(ExperimentRun.id.in_(run_ids))).scalars().all()
    by_id = {r.id: r for r in rows}

    unusable = [rid for rid in run_ids if rid not in by_id or by_id[rid].status != "ok"]
    if unusable:
        raise MissingExperimentRunError(unusable)

    series_by_key: dict[str, pd.Series] = {}
    for run_id in run_ids:
        payload = json.loads(by_id[run_id].results_json)
        points = payload.get("equity_curve") or []
        if not points:
            raise MissingExperimentRunError([run_id])
        index = pd.to_datetime([p["date"] for p in points])
        returns = derive_returns_from_equity_curve([p["equity"] for p in points])
        series_by_key[str(run_id)] = pd.Series(returns.to_numpy(), index=index)

    frame = pd.concat(series_by_key, axis=1, join="inner").dropna()
    return frame, by_id


def _as_of(frame: pd.DataFrame) -> str:
    return str(frame.index.max().date())


def compute_strategy_portfolio_risk(
    db: Session,
    provider: MarketDataProvider,
    allocations: dict[int, float],
    benchmark: str,
) -> PortfolioAnalyzeResponse:
    """Strategy-portfolio counterpart to risk/engine.py's
    compute_portfolio_risk: same math (literally the same
    compute_portfolio_risk_from_returns), different data source.

    The only network-touching part is the single benchmark ticker, fetched
    through the existing get_price_history_cached — no new fetch machinery,
    and no per-strategy fetch at all, since every strategy's realized
    returns are already sitting in its ExperimentRun.results_json."""
    run_ids = list(allocations.keys())
    frame, _runs = build_returns_frame(db, run_ids)
    if frame.empty:
        raise InsufficientHistoryError(0, label=STRATEGY_ASSET_LABEL)

    weights = {str(run_id): weight for run_id, weight in allocations.items()}

    # Fetch the benchmark over exactly the measured overlap window (plus a
    # small buffer for the pct_change row), not a fixed lookback_years —
    # the window here is fully determined by the selected runs' own stored
    # curves, so there is no lookback parameter to honor.
    start = frame.index.min().date() - timedelta(days=7)
    end = min(frame.index.max().date(), date.today())
    prices, _missing = get_price_history_cached(db, provider, [benchmark], start, end)
    if benchmark not in prices.columns:
        raise MissingTickerDataError([benchmark], is_benchmark=True)
    benchmark_returns = returns_svc.compute_daily_returns(prices[[benchmark]])[benchmark]

    return compute_portfolio_risk_from_returns(
        frame,
        weights,
        benchmark_returns,
        as_of=_as_of(frame),
        insufficient_history_label=STRATEGY_ASSET_LABEL,
    )


def compute_strategy_portfolio_optimization(
    db: Session,
    allocations: dict[int, float],
    risk_free_rate: float,
    max_weight: float = DEFAULT_MAX_WEIGHT,
    method: str = OPTIMIZATION_METHOD_MEAN_VARIANCE,
) -> tuple[OptimizationResult, float]:
    """Strategy-portfolio counterpart to risk/optimizer.py's
    compute_portfolio_optimization. Needs NO MarketDataProvider and makes
    no network call at all, unlike the ticker version — every input is
    already stored in results_json.

    Returns (result, measured_window_years) — the second value is the
    ACTUAL measured overlap window in years, which the response surfaces in
    place of the ticker version's echoed-back lookback_years request
    parameter (there isn't one here). That's strictly more honest: it
    reports the window the numbers were really computed over.

    `method` selects the allocator; it DEFAULTS to mean-variance, so every
    pre-existing caller is byte-for-byte unaffected. Both methods consume
    the identical returns frame from the identical build_returns_frame call
    below — the choice is only which allocator that one frame is handed to,
    never a second, differently-assembled dataset. That is what makes the
    two comparable at all.

    Under OPTIMIZATION_METHOD_HRP two things deliberately differ, both
    inherited from the algorithm rather than invented here (see
    hrp_optimizer.compute_hrp_portfolio_optimization_from_returns'
    docstring):

      - max_weight is not applied and the n*max_weight feasibility check
        does not fire. The cap exists to stop mean-variance corner
        solutions under estimation error; HRP cannot produce a corner
        solution (each weight is a product of alpha in [0, 1] splits), and
        no source applies a cap to HRP. Firing an "increase the cap or add
        strategies" error on a method that has no cap would be nonsense.
        Consequence worth stating plainly: HRP will optimize a 2-strategy
        portfolio that mean-variance refuses at the 0.4 cap.
      - expected returns do not enter the allocation, only the reported
        stats. HRP is a covariance-structure-only method."""
    if method not in OPTIMIZATION_METHODS:
        raise ValueError(
            f"unknown optimization method {method!r}; expected one of "
            f"{', '.join(OPTIMIZATION_METHODS)}"
        )

    run_ids = list(allocations.keys())
    n = len(run_ids)

    # Duplicated from the ticker wrapper on purpose, not hoisted into the
    # shared core: it must fire before any data assembly, exactly as
    # tests/test_optimizer.py::test_infeasible_with_two_holdings_and_default_cap
    # asserts for the ticker path. Skipped for HRP, which has no cap to be
    # infeasible against.
    if method == OPTIMIZATION_METHOD_MEAN_VARIANCE and n * max_weight < 1.0 - 1e-9:
        raise OptimizationInfeasibleError(
            f"Cannot allocate 100% weight with a per-strategy cap of {max_weight:.0%} "
            f"across only {n} strategies — raise the cap or add strategies."
        )

    frame, _runs = build_returns_frame(db, run_ids)
    if frame.empty:
        raise InsufficientHistoryError(0, label=STRATEGY_ASSET_LABEL)

    weights = {str(run_id): weight for run_id, weight in allocations.items()}
    if method == OPTIMIZATION_METHOD_HRP:
        try:
            result = compute_hrp_portfolio_optimization_from_returns(
                frame,
                weights,
                risk_free_rate,
                as_of=_as_of(frame),
                insufficient_history_label=STRATEGY_ASSET_LABEL,
            )
        except ValueError as exc:
            # hrp_optimizer REFUSES a degenerate covariance matrix (a
            # zero-variance column — a strategy whose stored equity curve
            # never moved — or a non-finite entry) rather than silently
            # patching it, and signals that with a plain ValueError.
            # Re-raised as OptimizationInfeasibleError so it lands in the
            # same RiskComputationError family every caller of this function
            # already handles: the runner falls back to equal weight, the
            # router returns 422. Without this, a single flat equity curve
            # would escape as an unhandled ValueError and cost a whole tick,
            # including its membership sync.
            raise OptimizationInfeasibleError(
                f"HRP cannot allocate over these strategies: {exc}"
            ) from exc
    else:
        result = compute_portfolio_optimization_from_returns(
            frame,
            weights,
            risk_free_rate,
            as_of=_as_of(frame),
            max_weight=max_weight,
            insufficient_history_label=STRATEGY_ASSET_LABEL,
        )
    return result, len(frame) / TRADING_DAYS_PER_YEAR
