"""Phase A: a bounded, individually-cited intraday pattern family, screened
against the existing walk-forward engine and DSR multiple-comparisons
correction — deliberately NOT an unconstrained/combinatorial pattern
generator. The whole point of keeping this family small (see PATTERN_FAMILY
below, currently 29 definitions, well under the ~100 ceiling) is that
compute_deflated_sharpe's n_trials correction was only empirically validated
for tens-to-hundreds of trials (see deflated_sharpe.py's own module
docstring); a naive "test every possible pattern definition at every bar"
search would either break that correction (if trials are counted honestly,
almost nothing would ever clear MIN_TRIALS_FOR_DSR's implied noise
benchmark) or invalidate it (if trials are undercounted). Every pattern here
traces to one of four cited, real sources.

Bars are hourly (60m, from YFinanceProvider.get_intraday_bars) — confirmed
the only intraday granularity yfinance gives enough free history for
(~2 years, see that method's own docstring); 5-minute-granularity work is
explicitly Phase B, against Alpaca instead.

Cadence design decision, stated explicitly: every pattern here is a FIXED,
naturally-short hold — a position opens on the bar right after the pattern's
own condition fires and is held only as long as that same condition keeps
re-firing in the same direction each subsequent bar (typically exactly 1
bar, since most session-phase buckets below are only 1-2 bars wide — see
apply_pattern_signal_rule). This is genuinely run through engine.py's
unmodified step_one_day/run_walk_forward directly against hourly-bar-indexed
raw_data (verified empirically, see test_intraday_patterns.py and this
module's live screening run) — NOT resampled to one row per day first. The
walk-forward's own per-BAR equity marks are then collapsed to one
end-of-trading-day equity mark per calendar date (daily_returns_from_bar_
equity) before computing Sharpe/DSR, so every downstream consumer
(metrics.sharpe_ratio, deflated_sharpe.compute_deflated_sharpe) keeps using
exactly the daily-cadence convention they were built and validated for
(TRADING_DAYS_PER_YEAR=252 annualization, n_observations as a trading-day
count) — see deflated_sharpe.py's own "annualized-vs-daily unit-mixing"
warning for why silently feeding it bar-frequency data instead would be
exactly the bug class that module already had to guard against once.
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Literal

import numpy as np
import pandas as pd

from app.services.research_lab.deflated_sharpe import (
    DeflatedSharpeResult,
    compute_deflated_sharpe,
    derive_returns_from_equity_curve,
)
from app.services.research_lab.engine import (
    DayResult,
    ExperimentResult,
    StrategyFit,
    Trade,
    WalkForwardConfig,
    run_walk_forward,
)
from app.services.research_lab.metrics import hit_rate, sharpe_ratio

SessionPhase = Literal["open", "mid_morning", "midday", "power_hour", "close"]
SESSION_PHASES: tuple[SessionPhase, ...] = ("open", "mid_morning", "midday", "power_hour", "close")

# A trading day needs at least this many bars for the 5-way session-phase
# split below to mean anything distinct (open/mid_morning/midday/power_hour/
# close each wants its own bar). Empirically, 493/500 real trading days over
# the AAPL/MSFT 60m/max window have exactly 7 bars; the remaining ~7 are
# early closes with 2-3 bars (see get_intraday_bars's own docstring) — those
# get session_phase=None throughout (an honest skip, not a guess at which
# bucket a 2-bar day's bars "really" belong to).
MIN_BARS_FOR_SESSION_PHASE = 5

# Bucketing thresholds on a bar's FRACTIONAL position within its trading day
# (0.0 = the day's first bar, 1.0 = its last) — an engineering judgment call
# to produce a sensible 5-way split of the empirically-dominant 7-bars/day
# structure (09:30/10:30/11:30/12:30/13:30/14:30/15:30 ET), not an
# independently-calibrated constant, same honesty register as this
# codebase's other disclosed judgment calls (e.g. Phase 3.6's
# UNDERPERFORMANCE_SHARPE_THRESHOLD). At 7 bars/day this yields open={bar 0},
# mid_morning={1,2}, midday={3,4}, power_hour={5}, close={bar 6} exactly.
MID_MORNING_FRAC_THRESHOLD = 0.35
POWER_HOUR_FRAC_THRESHOLD = 0.75

# Every pattern trade is a single-leg intraday bet with no hedge ratio —
# mirrors momentum.py's DEFAULT_COST_BPS=5.0 single-leg convention (half of
# pairs' two-leg 10bps), not independently recalibrated. Because
# apply_pattern_signal_rule always transits through flat before reversing
# (see its own docstring), a typical fire-then-flatten round trip charges
# this twice (once on entry, once on exit) — effectively ~10bps round-trip,
# still a conservative estimate for large-cap intraday liquidity.
INTRADAY_COST_BPS = 5.0

# Bars, not trading days, when passed to WalkForwardConfig against this
# module's hourly-bar-indexed raw_data (the field is named fit_window_days
# in engine.py because every OTHER caller uses daily bars — engine.py itself
# is unit-agnostic, it only ever slices positionally). Sized to comfortably
# contain a full current trading day (up to 7 bars) plus headroom, so
# patterns that need same-day context (the Gao/VWAP families below, which
# look back within window for the day's own "open" bucket bar) always find
# it regardless of where in a short holiday week the window starts.
INTRADAY_FIT_WINDOW_BARS = 20

# Reuses risk/engine.py's own MIN_OBS_FOR_ANY_ESTIMATE=20 floor-below-which-
# an-estimate-is-too-thin convention (not re-derived independently) — a
# pattern whose pooled daily-return series is shorter than this is dropped
# from the screening result entirely, not surfaced with a misleadingly
# precise Sharpe/DSR built on too little data.
MIN_POOLED_TRADING_DAYS = 20


@dataclass(frozen=True)
class PatternSignal:
    direction: Literal["long", "short"]
    strength: float  # magnitude of whatever moved the pattern to fire; only its sign (via `direction`) is used for position sizing in Phase A — kept for future refinement (e.g. confidence-weighted sizing), not read anywhere yet


@dataclass(frozen=True)
class PatternSpec:
    pattern_id: str
    family: str
    citation: str
    fire_fn: Callable[[pd.DataFrame], PatternSignal | None]  # already session-phase-gated


def _session_phase_for_day(n_bars: int) -> list[SessionPhase | None]:
    """Pure, testable: the session-phase label for each of a single
    trading day's n_bars, in order. Returns [None] * n_bars for a day too
    short to bucket meaningfully (see MIN_BARS_FOR_SESSION_PHASE)."""
    if n_bars < MIN_BARS_FOR_SESSION_PHASE:
        return [None] * n_bars
    phases: list[SessionPhase | None] = []
    for i in range(n_bars):
        if i == 0:
            phases.append("open")
        elif i == n_bars - 1:
            phases.append("close")
        else:
            frac = i / (n_bars - 1)
            if frac >= POWER_HOUR_FRAC_THRESHOLD:
                phases.append("power_hour")
            elif frac <= MID_MORNING_FRAC_THRESHOLD:
                phases.append("mid_morning")
            else:
                phases.append("midday")
    return phases


def build_pattern_raw_data(bars: pd.DataFrame) -> pd.DataFrame:
    """bars: one ticker's OHLCV frame as returned per-ticker by
    YFinanceProvider.get_intraday_bars (lowercase open/high/low/close/
    volume columns, tz-aware intraday DatetimeIndex). Adds the three
    columns every pattern fire_fn and run_walk_forward's return_fn need:
    trading_date (for same-day lookups), session_phase (see
    _session_phase_for_day), and ret — each bar's OWN open-to-close return,
    deliberately NOT close-to-close (which would silently pull in the
    overnight gap for a day's first bar, a move no single-bar-hold pattern
    here could ever actually trade since it only ever enters AT a bar's
    open)."""
    df = bars.sort_index().copy()
    df["trading_date"] = df.index.date
    df["ret"] = (df["close"] - df["open"]) / df["open"]

    phases: list[SessionPhase | None] = []
    for _trading_date, group in df.groupby("trading_date", sort=False):
        phases.extend(_session_phase_for_day(len(group)))
    df["session_phase"] = phases
    return df


def _gate_to_session_phase(
    fire_fn: Callable[[pd.DataFrame], PatternSignal | None], phase: SessionPhase
) -> Callable[[pd.DataFrame], PatternSignal | None]:
    """Restricts a pattern to fire only when the most recently OBSERVED bar
    (window.iloc[-1], i.e. one bar before the bar whose return will be
    realized) is itself in the given session-phase bucket — implements the
    plan's "bucketed by session-phase... rather than scanned at every
    individual bar position" requirement as a single shared wrapper rather
    than repeating the check inside every pattern below."""

    def gated(window: pd.DataFrame) -> PatternSignal | None:
        if window.empty or window.iloc[-1]["session_phase"] != phase:
            return None
        return fire_fn(window)

    return gated


# --- Family 1: Opening-range breakout continuation --------------------
# Crabel, "Day Trading with Short Term Price Patterns and Opening Range
# Breakout" (1990) — a strong directional move within the day's opening bar
# tends to continue, not revert, into the next bar.


def _fire_orb_continuation(window: pd.DataFrame, *, breakout_threshold: float) -> PatternSignal | None:
    bar = window.iloc[-1]
    bar_return = bar["ret"]
    if not np.isfinite(bar_return) or abs(bar_return) < breakout_threshold:
        return None
    return PatternSignal(direction="long" if bar_return > 0 else "short", strength=abs(bar_return))


# 0.1% / 0.2% / 0.3% of the opening bar's own open — three sensitivities of
# the same hypothesis, not three unrelated patterns.
ORB_BREAKOUT_THRESHOLDS = (0.001, 0.002, 0.003)


# --- Family 2: Intraday momentum by session-phase (Gao/Han/Xie/Yang) --
# Gao, Han, Xie & Yang, "Market Intraday Momentum" (Journal of Financial
# Economics, 2018): the first half-hour return predicts the last half-hour
# return, SAME direction. Adapted to hourly bars as open-bar-return ->
# close-bar-return. Already tested once this session on 5-minute data with a
# null result (p=0.505, n=2400) — re-tested here at hourly granularity, not
# assumed ruled out at a different sampling frequency. `reverse=True` tests
# the opposite-direction hypothesis as an honestly co-equal alternative
# (this project's own "test it, don't assume the sign" discipline), not a
# correction assumed to be right.


def _fire_intraday_momentum(
    window: pd.DataFrame, *, reverse: bool, min_open_return: float
) -> PatternSignal | None:
    bar = window.iloc[-1]
    trading_date = bar["trading_date"]
    day_rows = window[window["trading_date"] == trading_date]
    open_rows = day_rows[day_rows["session_phase"] == "open"]
    if open_rows.empty:
        return None
    open_bar = open_rows.iloc[0]
    open_return = open_bar["ret"]
    if not np.isfinite(open_return) or abs(open_return) < min_open_return:
        return None
    sign = -1.0 if reverse else 1.0
    predicted = open_return * sign
    return PatternSignal(direction="long" if predicted > 0 else "short", strength=abs(open_return))


# A small noise floor so the pattern isn't firing on economically
# meaningless near-zero opening moves — a judgment call, not empirically
# recalibrated against this project's own data.
GAO_MIN_OPEN_RETURN = 0.001


# --- Family 3: Anchored intraday VWAP-reversion ------------------------
# Standard intraday mean-reversion heuristic (e.g. Madhavan, "VWAP
# Strategies", Journal of Portfolio Management, 2002; widely used as a
# discretionary/systematic intraday signal in practice): price that has
# drifted far from the session's own running volume-weighted average price
# tends to revert toward it. VWAP computed only from bars already observed
# within the SAME trading day, up to and including the most recent bar — no
# lookahead.


def _fire_vwap_reversion(window: pd.DataFrame, *, deviation_threshold: float) -> PatternSignal | None:
    bar = window.iloc[-1]
    trading_date = bar["trading_date"]
    day_rows = window[window["trading_date"] == trading_date]
    total_volume = day_rows["volume"].sum()
    if day_rows.empty or total_volume == 0:
        return None
    typical_price = (day_rows["high"] + day_rows["low"] + day_rows["close"]) / 3.0
    vwap = float((typical_price * day_rows["volume"]).sum() / total_volume)
    if vwap == 0 or not np.isfinite(vwap):
        return None
    deviation = (bar["close"] - vwap) / vwap
    if abs(deviation) < deviation_threshold:
        return None
    # Price ABOVE VWAP is predicted to revert DOWN (short); below -> up (long).
    return PatternSignal(direction="short" if deviation > 0 else "long", strength=abs(deviation))


VWAP_DEVIATION_THRESHOLDS = (0.003, 0.006, 0.01)  # 0.3% / 0.6% / 1.0%
# VWAP-reversion needs a next bar within the SAME trading day to realize
# against — excludes "close" (no more bars left that day) and "open" (no
# meaningful VWAP yet with only one bar observed).
VWAP_REVERSION_PHASES: tuple[SessionPhase, ...] = ("mid_morning", "midday", "power_hour")


# --- Family 4: Classical multi-bar candlestick shapes -------------------
# Nison, "Japanese Candlestick Charting Techniques" (1991); Bulkowski,
# "Encyclopedia of Candlestick Charts" (2008) — three of the most widely
# cited multi-bar reversal shapes, evaluated at every session-phase bucket
# (not scanned at every bar position — see _gate_to_session_phase).

# A real body <=10% of the bar's own full high-low range — Nison's
# qualitative "open and close are virtually equal" definition, operational-
# ized as a numeric ratio; a judgment call, not independently recalibrated.
DOJI_BODY_TO_RANGE_MAX = 0.1


def _fire_engulfing(window: pd.DataFrame) -> PatternSignal | None:
    """A bar whose real body fully engulfs the prior bar's real body
    signals a potential reversal in the engulfing bar's own direction."""
    if len(window) < 2:
        return None
    prev, cur = window.iloc[-2], window.iloc[-1]
    prev_body_low, prev_body_high = sorted((prev["open"], prev["close"]))
    cur_body_low, cur_body_high = sorted((cur["open"], cur["close"]))
    if prev_body_high == prev_body_low:
        return None  # prior bar was itself a doji — no real body to engulf
    engulfs = cur_body_low <= prev_body_low and cur_body_high >= prev_body_high
    if not engulfs:
        return None
    cur_bullish = cur["close"] > cur["open"]
    return PatternSignal(direction="long" if cur_bullish else "short", strength=1.0)


def _fire_doji_reversal(window: pd.DataFrame) -> PatternSignal | None:
    """A doji (open ~= close) signals indecision, read as a potential
    reversal AGAINST the immediately preceding bar's own direction — the
    standard discretionary reading (a doji after an up move warns of a
    top, after a down move warns of a bottom)."""
    if len(window) < 2:
        return None
    prev, cur = window.iloc[-2], window.iloc[-1]
    bar_range = cur["high"] - cur["low"]
    if bar_range <= 0:
        return None
    body = abs(cur["close"] - cur["open"])
    if body / bar_range > DOJI_BODY_TO_RANGE_MAX:
        return None
    prev_direction = prev["close"] - prev["open"]
    if prev_direction == 0:
        return None
    return PatternSignal(direction="short" if prev_direction > 0 else "long", strength=1.0)


def _fire_three_bar_reversal(window: pd.DataFrame) -> PatternSignal | None:
    """Two consecutive bars moving in one direction followed by a third
    bar closing back beyond the FIRST bar's own open signals exhaustion
    and reversal."""
    if len(window) < 3:
        return None
    b1, b2, b3 = window.iloc[-3], window.iloc[-2], window.iloc[-1]
    down_down = b1["close"] < b1["open"] and b2["close"] < b2["open"] and b2["close"] < b1["close"]
    up_up = b1["close"] > b1["open"] and b2["close"] > b2["open"] and b2["close"] > b1["close"]
    if down_down and b3["close"] > b1["open"]:
        return PatternSignal(direction="long", strength=1.0)
    if up_up and b3["close"] < b1["open"]:
        return PatternSignal(direction="short", strength=1.0)
    return None


_CANDLESTICK_FIRE_FNS: dict[str, Callable[[pd.DataFrame], PatternSignal | None]] = {
    "engulfing": _fire_engulfing,
    "doji_reversal": _fire_doji_reversal,
    "three_bar_reversal": _fire_three_bar_reversal,
}


def _build_pattern_family() -> list[PatternSpec]:
    """Assembles the full, fixed pattern family — currently 29 definitions
    (3 ORB + 2 Gao/Han momentum + 9 VWAP-reversion + 15 candlestick),
    comfortably inside the plan's 20-100 ceiling. This list is the literal
    n_trials denominator screen_pattern_universe passes to
    compute_deflated_sharpe — see that function's own docstring for why."""
    specs: list[PatternSpec] = []

    orb_citation = "Crabel, 'Day Trading with Short Term Price Patterns and Opening Range Breakout' (1990)"
    for threshold in ORB_BREAKOUT_THRESHOLDS:
        specs.append(
            PatternSpec(
                pattern_id=f"orb_continuation_open_{threshold:.3f}",
                family="opening_range_breakout",
                citation=orb_citation,
                fire_fn=_gate_to_session_phase(
                    partial(_fire_orb_continuation, breakout_threshold=threshold), "open"
                ),
            )
        )

    gao_citation = "Gao, Han, Xie & Yang, 'Market Intraday Momentum' (Journal of Financial Economics, 2018)"
    for reverse in (False, True):
        specs.append(
            PatternSpec(
                pattern_id=f"intraday_momentum_{'reversal' if reverse else 'continuation'}_power_hour",
                family="intraday_momentum_gao2018",
                citation=gao_citation,
                fire_fn=_gate_to_session_phase(
                    partial(_fire_intraday_momentum, reverse=reverse, min_open_return=GAO_MIN_OPEN_RETURN),
                    "power_hour",
                ),
            )
        )

    vwap_citation = "Madhavan, 'VWAP Strategies' (Journal of Portfolio Management, 2002)"
    for phase in VWAP_REVERSION_PHASES:
        for threshold in VWAP_DEVIATION_THRESHOLDS:
            specs.append(
                PatternSpec(
                    pattern_id=f"vwap_reversion_{phase}_{threshold:.3f}",
                    family="vwap_reversion",
                    citation=vwap_citation,
                    fire_fn=_gate_to_session_phase(
                        partial(_fire_vwap_reversion, deviation_threshold=threshold), phase
                    ),
                )
            )

    candlestick_citation = (
        "Nison, 'Japanese Candlestick Charting Techniques' (1991); "
        "Bulkowski, 'Encyclopedia of Candlestick Charts' (2008)"
    )
    for shape_name, fire_fn in _CANDLESTICK_FIRE_FNS.items():
        for phase in SESSION_PHASES:
            specs.append(
                PatternSpec(
                    pattern_id=f"{shape_name}_{phase}",
                    family="candlestick",
                    citation=candlestick_citation,
                    fire_fn=_gate_to_session_phase(fire_fn, phase),
                )
            )

    return specs


PATTERN_FAMILY: list[PatternSpec] = _build_pattern_family()


def _make_fit_fn(fire_fn: Callable[[pd.DataFrame], PatternSignal | None]) -> Callable[[pd.DataFrame], StrategyFit]:
    """Adapts a pattern's fire_fn to engine.py's generic StrategyFit shape.
    z_score is used purely as a sign carrier (+1.0 long / -1.0 short) for
    apply_pattern_signal_rule below — patterns are fire-or-don't-fire, not
    continuous statistics, so no z-score magnitude is meaningful here."""

    def fit_fn(window: pd.DataFrame) -> StrategyFit:
        if window.empty:
            return StrategyFit(is_valid=False, z_score=None, fit_quality=None, params={})
        signal = fire_fn(window)
        if signal is None:
            return StrategyFit(is_valid=False, z_score=None, fit_quality=None, params={})
        z = 1.0 if signal.direction == "long" else -1.0
        return StrategyFit(is_valid=True, z_score=z, fit_quality=None, params={})

    return fit_fn


def apply_pattern_signal_rule(
    z_score: float | None, is_valid: bool, prev_position: int, entry_z: float, exit_z: float
) -> int:
    """Position tracks the freshly re-evaluated per-bar signal directly —
    no z-score band, since a pattern's z_score here is already a pure +1/-1
    direction carrier (see _make_fit_fn), not a magnitude to compare
    against a threshold. Matches this codebase's established never-direct-
    reversal invariant (apply_zscore_threshold_rule, momentum.py's
    apply_momentum_threshold_rule): a position always flattens for at
    least one step before flipping sign, keeping cost accounting
    unambiguous. In practice this means most trades last exactly 1 bar
    (most session-phase buckets below are only 1-2 bars wide, and a
    pattern's own condition rarely re-fires past that), occasionally
    2-3 for a bucket spanning multiple bars whose condition keeps holding
    — not an artificially fixed single-bar hold, an emergent one.

    entry_z/exit_z are accepted only to match step_one_day's Callable
    signature (each pattern's own fire/no-fire threshold is already baked
    into whether z_score is 0 vs +/-1, no separate band is needed here)."""
    del entry_z, exit_z
    if not is_valid or z_score is None or z_score == 0:
        return 0
    signal = 1 if z_score > 0 else -1
    if prev_position == 0 or prev_position == signal:
        return signal
    return 0  # signal reversed direction — flatten this step, re-enter (if it still holds) next


def realize_pattern_return(day_row: pd.Series, fit: StrategyFit) -> float:
    """Return per +1 (long) unit of position — single-leg intraday bet, no
    hedge ratio. Uses the bar's own open-to-close `ret` (see
    build_pattern_raw_data) — the return actually realizable by entering
    at this bar's open, exactly what a position opened on this step is
    assumed to do."""
    del fit  # unused — no fit params needed to size a single-leg bet
    return float(day_row["ret"])


def run_pattern_backtest(pattern: PatternSpec, raw_data: pd.DataFrame) -> ExperimentResult:
    """Runs the SAME engine.py walk-forward machinery (step_one_day via
    run_walk_forward, completely unmodified) directly against hourly-bar-
    indexed raw_data. Verified empirically, not just assumed from reading
    the source: engine.py's loop only ever does positional `.iloc` slicing
    and DayResult.date is typed pd.Timestamp (not datetime.date), so a
    tz-aware intraday DatetimeIndex round-trips through it exactly like a
    daily DatetimeIndex does — see test_intraday_patterns.py's
    test_run_pattern_backtest_accepts_hourly_indexed_raw_data and this
    module's real screening run against live yfinance hourly data."""
    config = WalkForwardConfig(
        fit_window_days=INTRADAY_FIT_WINDOW_BARS, entry_z=0.0, exit_z=0.0, cost_bps=INTRADAY_COST_BPS
    )
    return run_walk_forward(
        raw_data,
        config,
        _make_fit_fn(pattern.fire_fn),
        realize_pattern_return,
        decide_position_fn=apply_pattern_signal_rule,
        direction_labels=("long", "short"),
    )


def daily_returns_from_bar_equity(day_results: list[DayResult]) -> pd.Series:
    """Collapses the walk-forward's own per-BAR equity marks (one per
    hourly step — DayResult's field names are engine.py's daily-cadence
    convention, genuinely bar-granular here) down to one end-of-trading-
    day equity mark per calendar date, then reuses derive_returns_from_
    equity_curve (the SAME prepend-1.0-then-diff logic already validated
    for the daily case) to turn those into a genuine one-return-per-
    trading-day series. See this module's own docstring for why this
    matters: everything downstream must stay daily-cadence to safely
    reuse metrics.sharpe_ratio / deflated_sharpe.compute_deflated_sharpe
    unmodified."""
    if not day_results:
        return pd.Series(dtype=float)
    equity = pd.Series({d.date: d.equity for d in day_results})
    equity.index = pd.DatetimeIndex(equity.index)
    daily_equity = equity.groupby(equity.index.date).last().sort_index()
    return derive_returns_from_equity_curve(daily_equity.tolist())


@dataclass
class PatternScreeningResult:
    pattern_id: str
    family: str
    citation: str
    n_tickers_in_basket: int  # tickers with enough history to be included in the pooled series (most of the pilot universe, most patterns — see n_tickers_fired for how many actually traded)
    n_tickers_fired: int  # of those, how many had >=1 actual trade for this pattern (a flat 0%-return leg from a ticker the pattern never fired for still legitimately belongs in an equal-weighted basket, so this is a diagnostic, not a filter)
    n_trading_days: int  # length of the pooled daily-return series
    n_trades: int  # total bar-level trades across every ticker in the basket
    sharpe_annualized: float
    hit_rate: float | None
    deflated_sharpe: DeflatedSharpeResult


def screen_pattern_universe(
    bars_by_ticker: dict[str, pd.DataFrame], patterns: list[PatternSpec] | None = None
) -> list[PatternScreeningResult]:
    """For each pattern in the family, run run_pattern_backtest
    independently against every ticker's own hourly bars, then pool every
    contributing ticker's daily-return series into a single EQUAL-WEIGHTED
    basket return per pattern (row-wise mean across tickers, skipping any
    ticker with no observation that date) — one Sharpe per pattern, not
    one per (pattern, ticker).

    Trial-counting design decision, documented per the plan's explicit
    instruction that getting this right is the entire point of the
    exercise. Two framings were considered:

    (1) Per-pattern-per-ticker: a separate Sharpe for each (pattern,
    ticker) pair, still using n_trials=len(PATTERN_FAMILY) since that's
    how many trading rules were tried against any ONE ticker's data.
    Rejected: this only corrects for the pattern-search dimension WITHIN
    one ticker. The screening pass here also searches ACROSS the pilot
    universe for "which (pattern, ticker) combination looks best overall"
    — a second, uncorrected search dimension n_trials=29 would silently
    fail to account for, reintroducing exactly the kind of undisciplined
    multiple-comparisons risk this whole exercise exists to police.

    (2) Pooled across the pilot universe (used here): each pattern is
    applied uniformly, as a single equal-weighted basket, across every
    ticker in the pilot universe, producing ONE Sharpe per pattern. This
    correctly matches n_trials=len(PATTERN_FAMILY) to the one dimension
    actually being searched over (pattern definitions) — there is no
    second, silently-uncorrected "which ticker" search, because no
    per-ticker result is ever surfaced or cherry-picked. It's also a more
    realistic deployment framing: a pattern would be traded across a
    basket, not cherry-picked to whichever single ticker happened to look
    best in-sample. The honest tradeoff: pooling assumes large-cap
    intraday returns are independent enough across tickers for the
    pooled series' implied sample size to be meaningful — known to be
    imperfect (large-caps share market-wide moves, already disclosed in
    screening.py's MOMENTUM_SCREENING_METHODOLOGY_NOTE) but a materially
    smaller, already-disclosed bias than leaving a whole search dimension
    uncorrected.

    n_trials is therefore fixed at len(PATTERN_FAMILY) for every result
    (the family's pre-declared, literal size — not shrunk to "however many
    patterns happened to fire," which would itself be gameable by
    defining narrower patterns purely to shrink the denominator).
    sigma_sr is the std (ddof=1) across every OTHER pattern's own pooled
    Sharpe measured in this same screening run — the direct analogue of
    routers/research_lab.py's existing sibling_sharpes convention, with
    "same ticker/strategy, different config" replaced by "same pattern
    family, different pattern"."""
    family = patterns if patterns is not None else PATTERN_FAMILY
    n_trials = len(family)

    per_pattern_daily_returns: dict[str, pd.Series] = {}
    per_pattern_trades: dict[str, list[Trade]] = {}
    per_pattern_n_in_basket: dict[str, int] = {}
    per_pattern_n_fired: dict[str, int] = {}

    raw_data_by_ticker = {
        ticker: build_pattern_raw_data(bars) for ticker, bars in bars_by_ticker.items()
    }

    for pattern in family:
        ticker_daily_returns: dict[str, pd.Series] = {}
        trades: list[Trade] = []
        n_fired = 0
        for ticker, raw_data in raw_data_by_ticker.items():
            if len(raw_data) <= INTRADAY_FIT_WINDOW_BARS:
                continue
            result = run_pattern_backtest(pattern, raw_data)
            daily_returns = daily_returns_from_bar_equity(result.day_results)
            if not daily_returns.empty:
                ticker_daily_returns[ticker] = daily_returns
            if result.trades:
                n_fired += 1
            trades.extend(result.trades)

        if n_fired == 0:
            # Every ticker with enough history produces a daily-return
            # series regardless of whether this pattern ever actually
            # fired for it (a flat 0%-return day is still a valid walk-
            # forward day) — so ticker_daily_returns being non-empty does
            # NOT by itself mean the pattern found any real signal. Gate
            # on n_fired instead: a pattern that literally never fired
            # anywhere in the pilot universe is skipped entirely, not
            # reported as a misleading flat-zero "tested and neutral" row.
            continue

        pooled = pd.concat(ticker_daily_returns, axis=1).mean(axis=1, skipna=True).dropna()
        if len(pooled) < MIN_POOLED_TRADING_DAYS:
            continue

        per_pattern_daily_returns[pattern.pattern_id] = pooled
        per_pattern_trades[pattern.pattern_id] = trades
        per_pattern_n_in_basket[pattern.pattern_id] = len(ticker_daily_returns)
        per_pattern_n_fired[pattern.pattern_id] = n_fired

    sharpes = {pid: sharpe_ratio(returns) for pid, returns in per_pattern_daily_returns.items()}
    sigma_sr = float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None

    spec_by_id = {spec.pattern_id: spec for spec in family}
    results: list[PatternScreeningResult] = []
    for pattern_id, pooled in per_pattern_daily_returns.items():
        spec = spec_by_id[pattern_id]
        sharpe = sharpes[pattern_id]
        trades = per_pattern_trades[pattern_id]
        dsr = compute_deflated_sharpe(sharpe, pooled, n_trials, sigma_sr)
        results.append(
            PatternScreeningResult(
                pattern_id=pattern_id,
                family=spec.family,
                citation=spec.citation,
                n_tickers_in_basket=per_pattern_n_in_basket[pattern_id],
                n_tickers_fired=per_pattern_n_fired[pattern_id],
                n_trading_days=len(pooled),
                n_trades=len(trades),
                sharpe_annualized=sharpe,
                hit_rate=hit_rate(trades),
                deflated_sharpe=dsr,
            )
        )

    results.sort(key=lambda r: r.sharpe_annualized, reverse=True)
    return results
