"""Round C: a cross-sectional ranking / portfolio-formation backtest harness.

WHY THIS EXISTS (and why it is genuinely new capability rather than a
disguised reuse of engine.py): three prior honest pattern-mining rounds
(29 + 29 + 212 = 270 tested definitions, all single-ticker time-series,
see intraday_patterns.py) came back cleanly negative with a
cost-dominated-noise signature — symmetric losses on long/short pattern
pairs, both-direction momentum negative — consistent with too-frequent
trading eating the 10bps-per-round-trip cost assumption. The literature
review that motivated this round found that almost every robust,
well-replicated behavioral-finance anomaly (1) operates on multi-day-to-
multi-month holding periods, amortizing costs over far more return, and
(2) is CROSS-SECTIONAL: rank all stocks on a signal at a formation date,
go long the top decile and short the bottom decile, hold for a horizon,
reform. "One ticker's own history predicts that ticker's own next bar" —
the only shape engine.py/ou_pairs.py/momentum.py can express — is a
different (and, in 270 honest trials here, empirically empty) hypothesis
class. The ranking/formation step below is therefore new; what IS reused
is everything downstream that already works on a daily return series:
metrics.sharpe_ratio and deflated_sharpe.compute_deflated_sharpe, both
completely unmodified, exactly as intraday_patterns.py reused them.

POINT-IN-TIME UNIVERSE — the load-bearing correctness requirement of this
module. Survivorship bias is MORE severe for a cross-sectional decile
strategy than for the per-ticker screens built before it: a decile
portfolio formed from TODAY's index constituents silently excludes every
company that failed enough to leave the index, biasing the whole
strategy's return stream (especially the SHORT leg, which is precisely
where the failed names would have lived), not just which candidates got
surfaced. So eligibility here is decided per formation date by
sp500_membership_history.was_member — a ticker enters the ranked cross-
section on formation date d only if it was ACTUALLY an S&P 500 member on
d — never by ticker_universe.SCREENING_UNIVERSE (a snapshot of today)
applied retroactively. This is structural (the signal function is never
even shown an ineligible ticker's column), not a disclosed-after-the-fact
warning like build_membership_warnings — a deliberate strengthening for
the cross-sectional case, per the reasoning above.

What point-in-time membership CANNOT fix (carried over verbatim from
sp500_membership_history's KNOWN LIMITS, which every reader of results
from this module must internalize): ~48% of the members that left the
index in the trailing 5 years have NO yfinance price history at all —
the acquired/failed names whose absence flatters a backtest most. Those
tickers will be correctly ELIGIBLE at historical formation dates here,
but absent from the price data, so they simply never rank. The residual
bias is therefore still upward and is disclosed, not solved; actually
closing it needs a delisted-securities price vendor (Norgate, CRSP,
Sharadar) — already on the project's pending-paid-decisions list.

Recycled-ticker containment (the "silently wrong data" failure mode
sp500_membership_history documents — e.g. yfinance "FB" history restarts
2025-06-26 as a different company): a ticker's prices can only influence
this harness through (a) its signal at a formation date on which it was a
member, or (b) realization during a hold that began at such a formation.
Membership at formation gates (a) directly; (b) extends at most
holding_days past a formation, and every observed ticker recycling gap is
years, not months — so recycled data structurally cannot reach a
portfolio here. A removal DURING a hold keeps contributing until the hold
ends, which is correct (index removal is not a forced sale) and is
exactly the post-removal return window survivorship bias normally eats.

CONVENTIONS, each with its justification:
 * Formation at the close: the signal is computed from data up to and
   including formation date d's close, the position is assumed established
   at that same close, and returns realize from d+1 onward (close-to-
   close). This is the standard convention of the cited literature
   (George & Hwang 2004 and Grinblatt & Han 2005 both form at month-end
   using month-end prices) and is mildly optimistic about executing at the
   exact close print — disclosed, not hidden.
 * Equal-weighted legs, long-minus-short: daily portfolio return is the
   long leg's equal-weighted mean daily return minus the short leg's, the
   standard zero-investment academic convention — and the SAME
   self-financing dollar-neutral assumption metrics.sharpe_ratio already
   documents as its reason for not subtracting a risk-free rate, so that
   function is reused unmodified without silently violating its contract.
 * "Long-only" variants are implemented as long-top-decile MINUS the
   equal-weighted eligible universe ("long_universe_hedged"), not as a raw
   unhedged long: a raw long-only S&P-constituent decile's Sharpe is
   mostly the market's own Sharpe, which would (1) break
   metrics.sharpe_ratio's self-financing assumption above and (2) make
   sibling-Sharpe comparisons in the DSR's sigma_sr meaningless across a
   family mixing hedged and unhedged streams. Hedging with the universe
   isolates the cross-sectional selection effect, which is the hypothesis
   actually under test.
 * Equal weights are treated as re-set every day within a hold at zero
   cost (each day's leg return is that day's mean member return) — the
   standard academic equal-weighted portfolio return. The disclosed cost
   driver is formation-date turnover, priced exactly like engine.py's
   |position change| convention: cost_bps per unit of gross notional
   traded, one-way (see DEFAULT_XS_COST_BPS).
 * A ticker whose price disappears mid-hold (delisting, acquisition) drops
   out of its leg's mean from that day — economically, liquidation at the
   last available price with proceeds redistributed across the remaining
   names, the standard fallback absent true delisting returns (see the
   survivorship disclosure above for why the true returns are
   unavailable).
 * Non-overlapping holds: the whole portfolio reforms every holding_days
   trading days (formation cadence == holding period). The cited papers'
   headline results use Jegadeesh-Titman overlapping sub-portfolios, which
   smooth the return stream but change no expected return; the
   non-overlapping version is the simpler, noisier — i.e. conservative —
   estimator, and keeps turnover accounting unambiguous. Revisit only if a
   pattern's marginal DSR verdict plausibly hinges on formation-date
   noise.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd

from app.services.research_lab.deflated_sharpe import (
    DeflatedSharpeResult,
    compute_deflated_sharpe,
)
from app.services.research_lab.metrics import sharpe_ratio
from app.services.research_lab.sp500_membership_history import was_member

# One-way cost per unit of gross notional traded at a formation — mirrors
# momentum.py's DEFAULT_COST_BPS = 5.0 single-leg convention (itself half of
# pairs' two-leg 10bps), not independently recalibrated. A full long-short
# formation from flat trades gross notional 2.0 (buy 1.0 of longs, sell 1.0
# of shorts), so establishing the book costs ~10bps of equity, and each
# reformation costs 10bps times the fraction of the book actually replaced
# — far below the every-bar cost bleed the Round A/B post-mortem diagnosed,
# which is the entire economic thesis of this round.
DEFAULT_XS_COST_BPS = 5.0

# A leg with fewer names than this is a stock pick, not a decile portfolio —
# its "cross-sectional" return would be dominated by idiosyncratic single-
# name noise. 5 mirrors deflated_sharpe.MIN_TRIALS_FOR_DSR's
# smallest-sample-that-isn't-dominated-by-2-3-draws reasoning (verified
# there by simulation); an engineering judgment call at the same honesty
# register, not an independently calibrated constant.
DEFAULT_MIN_NAMES_PER_LEG = 5

# Same floor as momentum.py's MIN_OUT_OF_SAMPLE_TRADING_DAYS (itself
# mirroring ou_pairs.py) — below this many realized daily returns, a Sharpe
# is too thin to mean anything and the spec is dropped from screening
# results entirely rather than surfaced with misleading precision.
MIN_REPLAY_TRADING_DAYS = 60

MembershipFn = Callable[[str, date], bool]


@dataclass(frozen=True)
class CrossSectionalData:
    """Wide (dates x tickers) daily frames, all sharing close's exact index
    and columns (YFinanceProvider.get_daily_ohlcv guarantees the alignment;
    validate_cross_sectional_data re-checks it for hand-built data). open/
    volume are optional because only some signal families need them — the
    Lou/Polk/Skouras decomposition needs open, the Grinblatt/Han turnover
    proxy needs volume — and requiring all three everywhere would force
    every close-only test and caller to fabricate columns it never reads."""

    close: pd.DataFrame
    open: pd.DataFrame | None = None
    volume: pd.DataFrame | None = None


def validate_cross_sectional_data(data: CrossSectionalData) -> None:
    for name, frame in (("open", data.open), ("volume", data.volume)):
        if frame is None:
            continue
        if not frame.index.equals(data.close.index) or not frame.columns.equals(data.close.columns):
            raise ValueError(
                f"CrossSectionalData.{name} is not aligned with close "
                f"(index/columns must match exactly — see get_daily_ohlcv, which guarantees this)."
            )


# Receives a HISTORY VIEW: rows strictly up to and including the formation
# date, columns restricted to that formation date's eligible (point-in-time
# member) tickers. Returns one signal value per ticker; NaN means "this
# ticker has no valid signal today" (insufficient history, missing data)
# and excludes it from the ranking. The view construction in
# run_cross_sectional_backtest is what makes look-ahead structurally
# impossible — a signal function CANNOT read a future row, however buggy,
# because the row is not in the frame it is handed (the same structural
# guarantee engine.py's run_walk_forward makes by slicing the fit window
# before the day row, proven there by test_research_lab's look-ahead test
# and here by test_cross_sectional's).
SignalFn = Callable[[CrossSectionalData], pd.Series]


@dataclass(frozen=True)
class CrossSectionalSpec:
    pattern_id: str
    family: str
    citation: str
    signal_fn: SignalFn
    lookback_days: int  # trading rows of history the signal needs before its first formation
    holding_days: int  # trading days each formation is held; also the formation cadence (non-overlapping holds — see module docstring)
    portfolio: Literal["long_short", "long_universe_hedged"]
    rank_fraction: float  # 0.1 = deciles, 0.2 = quintiles
    requires_open: bool = False
    requires_volume: bool = False


@dataclass
class CrossSectionalConfig:
    cost_bps: float = DEFAULT_XS_COST_BPS
    min_names_per_leg: int = DEFAULT_MIN_NAMES_PER_LEG
    # Earliest calendar date a formation may occur on. The production entry
    # point sets this to the requested screening start so that price
    # history fetched EARLIER (purely to warm up long lookbacks) never
    # itself hosts a formation — and, critically, so no formation can land
    # before MEMBERSHIP_DATA_START, where was_member would silently answer
    # False for everyone (see sp500_membership_history.was_member's own
    # docstring on "no" vs "unknown").
    formation_start: date | None = None


@dataclass
class FormationRecord:
    """One formation date's full audit trail — what was eligible, what was
    held, what it cost. Kept per-formation (not just aggregated) because
    the point-in-time-correctness tests assert directly against these
    (e.g. TWTR must appear in no formation dated after its real 2022-11-01
    index removal), and because a surprising screening result should be
    auditable down to exactly which names drove it."""

    date: pd.Timestamp
    n_eligible: int
    long_tickers: list[str] = field(default_factory=list)
    short_tickers: list[str] = field(default_factory=list)
    turnover: float = 0.0  # sum of |weight change| across tickers, gross one-way notional traded
    skipped_reason: str | None = None


@dataclass
class CrossSectionalBacktestResult:
    status: Literal["ok", "insufficient_history", "no_valid_formations"]
    daily_returns: pd.Series  # net of costs, one observation per realized trading day
    formations: list[FormationRecord] = field(default_factory=list)
    total_cost: float = 0.0  # sum of all formation-turnover cost charges


def select_leg_tickers(signal: pd.Series, rank_fraction: float) -> tuple[list[str], list[str]]:
    """Ranks a cross-sectional signal and returns (top, bottom) leg ticker
    lists, each of size max(1, floor(n * rank_fraction)). Deterministic
    under ties: the signal is pre-sorted by ticker so the stable value sort
    breaks ties alphabetically — a re-run on identical data always forms
    the identical portfolio (screening results must be reproducible to be
    auditable). NaNs are dropped before ranking (a NaN signal means "no
    valid signal", per the SignalFn contract). The caller is responsible
    for rejecting cross-sections too small for the two legs to be disjoint
    (2 * leg size > n) — this function only ranks."""
    clean = signal.dropna()
    clean = clean[np.isfinite(clean)]
    n = len(clean)
    if n == 0:
        return [], []
    n_leg = max(1, int(n * rank_fraction))
    ordered = clean.sort_index().sort_values(ascending=False, kind="mergesort")
    top = list(ordered.index[:n_leg])
    bottom = list(ordered.index[-n_leg:])
    return top, bottom


def _target_weights(
    long_tickers: list[str], short_tickers: list[str], portfolio: str, eligible: list[str]
) -> dict[str, float]:
    """Net per-ticker weights for one formation: +1/n_long per long name,
    -1/n_short per short name (long_short), or -1/n_eligible per universe
    name (long_universe_hedged, where a long name's net weight is
    1/n_long - 1/n_eligible). Net (not per-leg) weights are what turnover
    must be measured on — a name staying long across a reformation trades
    nothing, whatever leg bookkeeping says."""
    weights: dict[str, float] = {}
    if long_tickers:
        w_long = 1.0 / len(long_tickers)
        for t in long_tickers:
            weights[t] = weights.get(t, 0.0) + w_long
    # A hedged portfolio shorts the universe only when it actually formed a
    # long leg — a skipped formation is FLAT, never a naked universe short.
    shorts = (eligible if long_tickers else []) if portfolio == "long_universe_hedged" else short_tickers
    if shorts:
        w_short = 1.0 / len(shorts)
        for t in shorts:
            weights[t] = weights.get(t, 0.0) - w_short
    return weights


def _turnover(old: dict[str, float], new: dict[str, float]) -> float:
    tickers = set(old) | set(new)
    return float(sum(abs(new.get(t, 0.0) - old.get(t, 0.0)) for t in tickers))


def _leg_mean_return(day_returns: pd.Series, tickers: list[str]) -> float:
    """Equal-weighted mean of the leg's member returns that day, skipping
    names with no return (delisted mid-hold — see module docstring's
    liquidate-at-last-price convention). A leg whose every name is missing
    contributes 0.0 — cash, not a fabricated number."""
    if not tickers:
        return 0.0
    vals = day_returns.reindex(tickers).dropna()
    if vals.empty:
        return 0.0
    return float(vals.mean())


def run_cross_sectional_backtest(
    data: CrossSectionalData,
    spec: CrossSectionalSpec,
    config: CrossSectionalConfig,
    membership_fn: MembershipFn | None = None,
) -> CrossSectionalBacktestResult:
    """One spec's full walk-forward replay: at each formation date (every
    holding_days trading days, starting once lookback_days of history
    exist and config.formation_start is reached), rank the point-in-time-
    eligible cross-section, form the legs, realize close-to-close returns
    until the next formation. See the module docstring for every
    convention used here and its justification.

    membership_fn defaults to sp500_membership_history.was_member — the
    production point-in-time gate. Tests inject their own to isolate
    mechanics from the vendored membership data, EXCEPT the point-in-time-
    correctness tests, which deliberately run the real was_member against
    real historical index events (TWTR's removal, PLTR's addition) to
    prove the composed system respects them."""
    validate_cross_sectional_data(data)
    if spec.requires_open and data.open is None:
        raise ValueError(f"{spec.pattern_id} requires daily Open data (CrossSectionalData.open is None).")
    if spec.requires_volume and data.volume is None:
        raise ValueError(f"{spec.pattern_id} requires daily Volume data (CrossSectionalData.volume is None).")

    is_member = membership_fn if membership_fn is not None else was_member
    index = data.close.index
    n = len(index)

    # fill_method=None: a mid-series NaN yields a NaN return (the ticker
    # drops out of its leg that day) rather than pandas' legacy forward-
    # fill, which would fabricate a 0% return for a halted/delisted name.
    daily_returns_all = data.close.pct_change(fill_method=None)

    first_formation = spec.lookback_days
    if config.formation_start is not None:
        eligible_positions = np.flatnonzero(index.date >= config.formation_start)  # type: ignore[attr-defined]
        if len(eligible_positions) == 0:
            return CrossSectionalBacktestResult(
                status="insufficient_history", daily_returns=pd.Series(dtype=float)
            )
        first_formation = max(first_formation, int(eligible_positions[0]))

    # Need at least one realization day after the first formation.
    if first_formation >= n - 1:
        return CrossSectionalBacktestResult(status="insufficient_history", daily_returns=pd.Series(dtype=float))

    formations: list[FormationRecord] = []
    return_dates: list[pd.Timestamp] = []
    net_returns: list[float] = []
    prev_weights: dict[str, float] = {}
    total_cost = 0.0
    any_formed = False

    for i in range(first_formation, n - 1, spec.holding_days):
        formation_ts = index[i]
        formation_day: date = formation_ts.date()

        # Point-in-time eligibility: an index member on the formation date,
        # with a price at that date's close (a member with no price today
        # cannot be ranked or traded). This is THE survivorship-bias gate —
        # see module docstring.
        formation_close = data.close.iloc[i]
        eligible = [
            t for t in data.close.columns if is_member(t, formation_day) and np.isfinite(formation_close[t])
        ]

        long_tickers: list[str] = []
        short_tickers: list[str] = []
        skipped_reason: str | None = None

        if eligible:
            # The history view: rows <= formation date, columns = eligible
            # only. Structural look-ahead impossibility — see SignalFn.
            # Rows are capped at the spec's own declared lookback_days —
            # the exact history the spec's contract says its signal reads —
            # rather than all history since inception: behaviorally
            # identical for any signal honoring its declaration, and it
            # caps the per-formation frame copy at lookback x universe
            # (~10MB at 567 rows x ~700 tickers) instead of growing with
            # every year of replay.
            row_start = max(0, i + 1 - spec.lookback_days)
            view = CrossSectionalData(
                close=data.close.iloc[row_start : i + 1].loc[:, eligible],
                open=data.open.iloc[row_start : i + 1].loc[:, eligible] if data.open is not None else None,
                volume=(
                    data.volume.iloc[row_start : i + 1].loc[:, eligible] if data.volume is not None else None
                ),
            )
            signal = spec.signal_fn(view)
            top, bottom = select_leg_tickers(signal, spec.rank_fraction)
            n_ranked = int(signal.dropna().shape[0])
            n_leg = len(top)
            if n_leg < config.min_names_per_leg:
                skipped_reason = (
                    f"only {n_ranked} ranked names -> leg of {n_leg} < min_names_per_leg="
                    f"{config.min_names_per_leg}"
                )
            elif 2 * n_leg > n_ranked:
                skipped_reason = f"legs would overlap ({n_ranked} ranked names for two legs of {n_leg})"
            else:
                long_tickers = top
                short_tickers = bottom if spec.portfolio == "long_short" else []
        else:
            skipped_reason = "no eligible tickers (point-in-time membership + price availability)"

        new_weights = _target_weights(long_tickers, short_tickers, spec.portfolio, eligible)
        turnover = _turnover(prev_weights, new_weights)
        cost = (config.cost_bps / 10_000.0) * turnover
        total_cost += cost
        prev_weights = new_weights
        if skipped_reason is None:
            any_formed = True

        formations.append(
            FormationRecord(
                date=formation_ts,
                n_eligible=len(eligible),
                long_tickers=long_tickers,
                short_tickers=(eligible if spec.portfolio == "long_universe_hedged" and long_tickers else short_tickers),
                turnover=turnover,
                skipped_reason=skipped_reason,
            )
        )

        hold_end = min(i + spec.holding_days, n - 1)
        for j in range(i + 1, hold_end + 1):
            day = daily_returns_all.iloc[j]
            long_ret = _leg_mean_return(day, long_tickers)
            short_ret = _leg_mean_return(day, formations[-1].short_tickers)
            gross = long_ret - short_ret
            # The formation's turnover cost lands on its first realization
            # day — the day the rebalance trades settle into the return
            # stream, mirroring engine.py charging |position change| on the
            # day the position changes.
            net = gross - (cost if j == i + 1 else 0.0)
            return_dates.append(index[j])
            net_returns.append(net)

    daily = pd.Series(net_returns, index=pd.DatetimeIndex(return_dates), dtype=float)
    status: Literal["ok", "insufficient_history", "no_valid_formations"] = (
        "ok" if any_formed else "no_valid_formations"
    )
    return CrossSectionalBacktestResult(
        status=status, daily_returns=daily, formations=formations, total_cost=total_cost
    )


@dataclass
class CrossSectionalScreeningResult:
    pattern_id: str
    family: str
    citation: str
    n_formations: int
    n_skipped_formations: int
    avg_names_per_leg: float
    n_trading_days: int  # length of the realized daily-return series
    sharpe_annualized: float
    total_cost_drag: float
    deflated_sharpe: DeflatedSharpeResult


def screen_cross_sectional_universe(
    data: CrossSectionalData,
    specs: list[CrossSectionalSpec],
    config: CrossSectionalConfig,
    membership_fn: MembershipFn | None = None,
) -> list[CrossSectionalScreeningResult]:
    """One Sharpe per spec across the whole cross-section, DSR-corrected
    for the family's pre-declared size. Trial counting follows
    intraday_patterns.screen_pattern_universe's pooled framing exactly,
    and for the same documented reason: each spec IS already a single
    portfolio across the whole universe (there is no per-ticker result to
    cherry-pick, so no silently-uncorrected "which ticker" search
    dimension exists), leaving "which pattern definition" as the one
    search dimension — so n_trials is fixed at len(specs), the family's
    literal pre-declared size, never shrunk to however many specs survived
    the data floors (which would be gameable by defining specs expected to
    fail). sigma_sr is the ddof=1 std of every sibling spec's own Sharpe
    from this same screening pass — the direct analogue of
    screen_pattern_universe's sibling convention, with "same family,
    different pattern" as the sibling relation."""
    n_trials = len(specs)

    replays: dict[str, CrossSectionalBacktestResult] = {}
    for spec in specs:
        result = run_cross_sectional_backtest(data, spec, config, membership_fn)
        if result.status != "ok":
            continue
        if len(result.daily_returns) < MIN_REPLAY_TRADING_DAYS:
            continue
        replays[spec.pattern_id] = result

    sharpes = {pid: sharpe_ratio(res.daily_returns) for pid, res in replays.items()}
    sigma_sr = float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None

    spec_by_id = {spec.pattern_id: spec for spec in specs}
    results: list[CrossSectionalScreeningResult] = []
    for pattern_id, replay in replays.items():
        spec = spec_by_id[pattern_id]
        formed = [f for f in replay.formations if f.skipped_reason is None]
        skipped = [f for f in replay.formations if f.skipped_reason is not None]
        avg_leg = float(np.mean([len(f.long_tickers) for f in formed])) if formed else 0.0
        dsr = compute_deflated_sharpe(sharpes[pattern_id], replay.daily_returns, n_trials, sigma_sr)
        results.append(
            CrossSectionalScreeningResult(
                pattern_id=pattern_id,
                family=spec.family,
                citation=spec.citation,
                n_formations=len(formed),
                n_skipped_formations=len(skipped),
                avg_names_per_leg=avg_leg,
                n_trading_days=len(replay.daily_returns),
                sharpe_annualized=sharpes[pattern_id],
                total_cost_drag=replay.total_cost,
                deflated_sharpe=dsr,
            )
        )

    results.sort(key=lambda r: r.sharpe_annualized, reverse=True)
    return results
