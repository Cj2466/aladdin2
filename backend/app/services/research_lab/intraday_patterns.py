"""Phase A: a bounded, individually-cited intraday pattern family, screened
against the existing walk-forward engine and DSR multiple-comparisons
correction — deliberately NOT an unconstrained/combinatorial pattern
generator. The whole point of keeping this family bounded (see
PATTERN_FAMILY below, currently 212 definitions, inside the 150-300 ceiling
this expanded screening pass was explicitly told to stay within) is that
compute_deflated_sharpe's n_trials correction was only empirically validated
for tens-to-hundreds of trials (see deflated_sharpe.py's own module
docstring); a naive "test every possible pattern definition at every bar"
search would either break that correction (if trials are counted honestly,
almost nothing would ever clear MIN_TRIALS_FOR_DSR's implied noise
benchmark) or invalidate it (if trials are undercounted).

This is an EXPANSION of the original 29-pattern pilot (still Phase A, same
hourly-bar/yfinance/engine.py machinery, not a new phase) — that first pass
came back honestly negative on both a 30-large-cap universe and a separate
17-verified-mid/small-cap universe (see PATTERN_MINING_UNIVERSE's own
docstring for the combined, re-verified universe used here). Rather than
stopping there, this pass broadens two dimensions at once, each bounded and
individually justified, not unconstrained: (1) more parameter variations
within the original four families (more ORB thresholds, more Gao/Han/Xie/
Yang phases and thresholds, more VWAP thresholds and a second price
convention, five more classical candlestick shapes), and (2) six entirely
new, separately-cited pattern families (RSI extremes, Bollinger Band
reversion, moving-average crossover, volume-price divergence, day-of-week
seasonality, and overnight close-to-open persistence) — see each family's
own citation comment below for its real, individual source. Every one of
these 212 definitions was planned BEFORE this screening run and is counted
in n_trials regardless of how it performs — see screen_pattern_universe's
own docstring, and this phase's task instructions, for why undercounting
trials (only counting the ones that "count," post hoc) would silently
reintroduce exactly the p-hacking risk this whole exercise exists to
police.

Result of the expanded live run (2026-08-25, all 212 patterns x all 55
tickers, run to completion with no early stopping): honestly negative
again. 204/212 patterns had a negative pooled raw Sharpe; the 8 positives
topped out at 0.79 annualized (volume_climax_4x_midday, 44 trades, 52.3%
hit rate) with a best deflated Sharpe of 1.1e-10 across the entire family
— nothing remotely clears the n_trials=212 correction. The negative is
robust to the sibling-sigma_SR caveat (deeply-negative cost-dominated
siblings inflate sigma_SR to ~2.9 annualized, making the SR0 noise
benchmark a severe 8.1): even with NO multiple-comparisons correction at
all, the best pattern's PSR-vs-zero was only 93.6%, far below what the
best of 212 pure-noise trials would be expected to show by chance. Same
cost-dominated-noise signature as the pilot, verified on this run's own
numbers: every day-of-week long/short pair sums to roughly the same
-1.0..-1.6 Sharpe (symmetric round-trip cost drag, no directional edge),
and Gao/Han momentum is deeply negative in BOTH directions at every
threshold and phase — impossible for a real signal, exactly what pure
transaction-cost bleed looks like.

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


# The widened screening universe for this expanded pass: the original
# 30-large-cap pilot universe, pooled with a 25-ticker mid/small-cap
# universe re-derived and re-verified fresh (NOT reused from the earlier
# session's 17-ticker diagnostic, which was never persisted anywhere in
# this codebase — re-verifying from scratch rather than trusting a stale,
# unrecorded list, per this phase's own empirical-first discipline).
#
# Large-cap 30 (informal sanity check only — every one of these is a
# well-known mega/large-cap by any reasonable definition; market caps
# empirically re-confirmed 2026-08-25 via live yfinance queries anyway,
# ranging from CRM's ~$170B up to NVDA's ~$5.1T):
PATTERN_MINING_UNIVERSE_LARGE_CAP: list[str] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "AVGO", "ORCL", "CRM", "TSLA",
    "HD", "MCD", "NKE", "SBUX", "COST", "WMT", "JPM", "V", "MA", "BAC",
    "GS", "UNH", "JNJ", "LLY", "ABBV", "CAT", "BA", "XOM", "CVX", "DIS",
]

# Mid/small-cap 25 — every ticker below was empirically verified live
# 2026-08-25 (via yf.Ticker(t).info) against three criteria before
# inclusion, not assumed from any external list: (1) market cap between
# $300M (below this is arguably micro-cap, too thin to trust the 5bps
# single-leg cost assumption INTRADAY_COST_BPS already uses) and $10B
# (above this drifts into large-cap territory, defeating the point of a
# separate mid/small-cap universe); (2) average dollar volume >= $5M/day
# (a reasonable-liquidity floor, also for the cost assumption to hold);
# (3) >= ~2 years of real 60m-interval bars available via
# YFinanceProvider.get_intraday_bars (empirically confirmed: every ticker
# below returned 3469-3473 bars, essentially the same ~2-year window as
# the large-cap set, zero missing).
#
# Candidates considered and explicitly EXCLUDED, for a disclosed reason
# rather than silently dropped: FIVE ($14.3B) and CHWY ($10.0B) exceeded
# the $10B ceiling; HAIN ($81M market cap, ~$1M/day dollar volume) fell
# below both floors; GES and LANC no longer resolve via yfinance at all
# (HTTP 404 "Quote not found" on both .info and a plain price-history
# download — consistent with both having been taken private/delisted
# since they were last tradeable, not a transient API hiccup).
PATTERN_MINING_UNIVERSE_MID_SMALL_CAP: list[str] = [
    "CROX", "SFM", "CAKE", "BJRI", "SHAK", "PLAY", "ANF", "URBN", "YETI", "FND",
    "BOOT", "OLLI", "PLNT", "WWW", "SIG", "BBWI", "ELF", "CELH", "BROS", "PZZA",
    "WEN", "JACK", "FRPT", "UNFI", "DIN",
]

PATTERN_MINING_UNIVERSE: list[str] = PATTERN_MINING_UNIVERSE_LARGE_CAP + PATTERN_MINING_UNIVERSE_MID_SMALL_CAP


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


# 0.05% through 0.5% of the opening bar's own open — eight sensitivities of
# the SAME hypothesis, not eight unrelated patterns (expanded from the
# original 3-threshold grid for broader coverage of the threshold space,
# per this phase's explicit "more parameter variations within the existing
# families" instruction).
ORB_BREAKOUT_THRESHOLDS = (0.0005, 0.001, 0.0015, 0.002, 0.0025, 0.003, 0.004, 0.005)


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


# Four sensitivities of the same "opening move predicts the day's later
# move" hypothesis (expanded from the original single 0.001 floor) — a
# small noise floor so the pattern isn't firing on economically meaningless
# near-zero opening moves at any threshold, a judgment call not empirically
# recalibrated against this project's own data.
GAO_OPEN_RETURN_THRESHOLDS = (0.0005, 0.001, 0.002, 0.003)

# The original pilot tested only "power_hour" (bar 5 of 7) as the paper's
# literal "last half-hour". Also testing "close" (bar 6, the day's actual
# final bar) is an honest broadening of which bar counts as "last" in an
# hourly-bar adaptation of a paper written for continuous intraday data —
# not cherry-picked after seeing which one looked better (both were added
# to the family before this screening run, per this phase's own no-early-
# stopping discipline).
GAO_MOMENTUM_PHASES: tuple[SessionPhase, ...] = ("power_hour", "close")


# --- Family 3: Anchored intraday VWAP-reversion ------------------------
# Standard intraday mean-reversion heuristic (e.g. Madhavan, "VWAP
# Strategies", Journal of Portfolio Management, 2002; widely used as a
# discretionary/systematic intraday signal in practice): price that has
# drifted far from the session's own running volume-weighted average price
# tends to revert toward it. VWAP computed only from bars already observed
# within the SAME trading day, up to and including the most recent bar — no
# lookahead.


def _fire_vwap_reversion(
    window: pd.DataFrame, *, deviation_threshold: float, price_convention: Literal["typical", "close"] = "typical"
) -> PatternSignal | None:
    """price_convention="typical" is Madhavan's own (H+L+C)/3 formula, the
    textbook VWAP definition. "close" (weighting each bar's own close by
    its volume instead) is also a standard, widely-used operationalization
    in practice when only close prices are available — a real, distinct
    parameter choice being tested honestly, not padding: both conventions
    can and do disagree materially within a session, especially on bars
    with large high-low ranges."""
    bar = window.iloc[-1]
    trading_date = bar["trading_date"]
    day_rows = window[window["trading_date"] == trading_date]
    total_volume = day_rows["volume"].sum()
    if day_rows.empty or total_volume == 0:
        return None
    if price_convention == "typical":
        price = (day_rows["high"] + day_rows["low"] + day_rows["close"]) / 3.0
    else:
        price = day_rows["close"]
    vwap = float((price * day_rows["volume"]).sum() / total_volume)
    if vwap == 0 or not np.isfinite(vwap):
        return None
    deviation = (bar["close"] - vwap) / vwap
    if abs(deviation) < deviation_threshold:
        return None
    # Price ABOVE VWAP is predicted to revert DOWN (short); below -> up (long).
    return PatternSignal(direction="short" if deviation > 0 else "long", strength=abs(deviation))


# Five sensitivities (expanded from the original 3-threshold grid) of the
# same reversion hypothesis.
VWAP_DEVIATION_THRESHOLDS = (0.002, 0.004, 0.006, 0.008, 0.012)
# VWAP-reversion needs a next bar within the SAME trading day to realize
# against — excludes "close" (no more bars left that day) and "open" (no
# meaningful VWAP yet with only one bar observed).
VWAP_REVERSION_PHASES: tuple[SessionPhase, ...] = ("mid_morning", "midday", "power_hour")
VWAP_PRICE_CONVENTIONS: tuple[Literal["typical", "close"], ...] = ("typical", "close")


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


# A real body must be at least this fraction of its own high-low range to
# count as a "long" bar for the shapes below that need one (star/piercing/
# harami all key off "bar1 was a decisive, not indecisive, move") — the
# complement of DOJI_BODY_TO_RANGE_MAX, same judgment-call register, not
# independently recalibrated against this project's own data.
LONG_BODY_TO_RANGE_MIN = 0.5

# Hammer/hanging-man/shooting-star/inverted-hammer (Nison ch. 6-7): a small
# real body with a shadow on ONE side at least this many times the body's
# own size, and little-to-no shadow on the other side.
HAMMER_SHADOW_TO_BODY_MIN = 2.0
# How many PRIOR bars (not counting the shape bar itself) define the
# "trend" context that disambiguates hammer-vs-hanging-man (same shape,
# opposite reading depending on whether it follows a down- or up-move) —
# a judgment call sized to fit comfortably inside the 20-bar walk-forward
# window alongside the shape's own bars, not empirically recalibrated.
TREND_CONTEXT_LOOKBACK = 3

# Two bars' highs (tweezer top) or lows (tweezer bottom) are treated as
# "matching" within this relative tolerance — Nison's qualitative "matching
# highs/lows" operationalized as a numeric band, a judgment call not
# independently recalibrated, same register as DOJI_BODY_TO_RANGE_MAX.
TWEEZER_MATCH_TOLERANCE = 0.001


def _fire_hammer_family(window: pd.DataFrame, *, trend_lookback: int = TREND_CONTEXT_LOOKBACK) -> PatternSignal | None:
    """Nison's four related single-bar shapes, all "small body, one long
    shadow": hammer (long LOWER shadow after a downtrend -> bullish),
    hanging man (identical shape after an UPTREND -> bearish), shooting
    star (long UPPER shadow after an uptrend -> bearish), inverted hammer
    (identical shape after a DOWNTREND -> bullish, Nison's own weaker/
    needs-confirmation variant, tested here on the same footing as the
    other three rather than assumed less reliable). One function handles
    all four since the shape-detection logic is identical; only the
    prior-trend context changes which historical name/reading applies."""
    if len(window) < trend_lookback + 1:
        return None
    cur = window.iloc[-1]
    body_low, body_high = sorted((cur["open"], cur["close"]))
    body = body_high - body_low
    full_range = cur["high"] - cur["low"]
    if full_range <= 0 or body <= 0:
        return None
    lower_shadow = body_low - cur["low"]
    upper_shadow = cur["high"] - body_high
    trend_rows = window.iloc[-(trend_lookback + 1) : -1]
    trend = trend_rows["close"].iloc[-1] - trend_rows["close"].iloc[0]
    if trend == 0:
        return None  # no clear prior direction to disambiguate the reading against

    if lower_shadow >= HAMMER_SHADOW_TO_BODY_MIN * body and upper_shadow <= body * 0.5:
        # hammer (downtrend context) or hanging man (uptrend context)
        return PatternSignal(direction="long" if trend < 0 else "short", strength=lower_shadow / full_range)
    if upper_shadow >= HAMMER_SHADOW_TO_BODY_MIN * body and lower_shadow <= body * 0.5:
        # inverted hammer (downtrend context) or shooting star (uptrend context)
        return PatternSignal(direction="long" if trend < 0 else "short", strength=upper_shadow / full_range)
    return None


def _fire_star_reversal(window: pd.DataFrame) -> PatternSignal | None:
    """Morning star (bullish) / evening star (bearish) — Nison ch. 8: a
    long decisive bar, then a small-bodied indecision bar, then a third
    bar closing back beyond the first bar's own midpoint in the opposite
    direction of the first bar."""
    if len(window) < 3:
        return None
    b1, b2, b3 = window.iloc[-3], window.iloc[-2], window.iloc[-1]
    b1_range = b1["high"] - b1["low"]
    if b1_range <= 0:
        return None
    b1_body = abs(b1["close"] - b1["open"])
    if b1_body / b1_range < LONG_BODY_TO_RANGE_MIN:
        return None
    b2_body = abs(b2["close"] - b2["open"])
    if b2_body >= b1_body * 0.5:
        return None  # middle bar wasn't decisively smaller — no indecision signature
    b1_mid = (b1["open"] + b1["close"]) / 2.0
    if b1["close"] < b1["open"] and b3["close"] > b1_mid and b3["close"] > b3["open"]:
        return PatternSignal(direction="long", strength=1.0)  # morning star
    if b1["close"] > b1["open"] and b3["close"] < b1_mid and b3["close"] < b3["open"]:
        return PatternSignal(direction="short", strength=1.0)  # evening star
    return None


def _fire_piercing_darkcloud(window: pd.DataFrame) -> PatternSignal | None:
    """Piercing line (bullish) / dark cloud cover (bearish) — Nison ch. 5:
    a long decisive bar followed by a bar that opens beyond the first
    bar's own close (a gap in the trend's direction) but then closes back
    past the first bar's own midpoint (not all the way through it — that
    would be an engulfing, already covered by Family 4)."""
    if len(window) < 2:
        return None
    b1, b2 = window.iloc[-2], window.iloc[-1]
    b1_range = b1["high"] - b1["low"]
    if b1_range <= 0:
        return None
    b1_body = abs(b1["close"] - b1["open"])
    if b1_body / b1_range < LONG_BODY_TO_RANGE_MIN:
        return None
    b1_mid = (b1["open"] + b1["close"]) / 2.0
    if b1["close"] < b1["open"] and b2["open"] < b1["close"] and b1_mid < b2["close"] < b1["open"]:
        return PatternSignal(direction="long", strength=1.0)  # piercing line
    if b1["close"] > b1["open"] and b2["open"] > b1["close"] and b1["open"] < b2["close"] < b1_mid:
        return PatternSignal(direction="short", strength=1.0)  # dark cloud cover
    return None


def _fire_harami(window: pd.DataFrame) -> PatternSignal | None:
    """Bullish/bearish harami ("inside bar") — Nison ch. 5: a long
    decisive bar followed by a bar whose entire real body sits INSIDE the
    first bar's own real body, reading as a sudden contraction in
    conviction and a potential reversal of the first bar's direction."""
    if len(window) < 2:
        return None
    b1, b2 = window.iloc[-2], window.iloc[-1]
    b1_lo, b1_hi = sorted((b1["open"], b1["close"]))
    b1_range = b1["high"] - b1["low"]
    if b1_range <= 0:
        return None
    b1_body = b1_hi - b1_lo
    if b1_body / b1_range < LONG_BODY_TO_RANGE_MIN:
        return None
    b2_lo, b2_hi = sorted((b2["open"], b2["close"]))
    inside = b2_lo >= b1_lo and b2_hi <= b1_hi and (b2_hi - b2_lo) < b1_body
    if not inside:
        return None
    if b1["close"] < b1["open"]:
        return PatternSignal(direction="long", strength=1.0)
    if b1["close"] > b1["open"]:
        return PatternSignal(direction="short", strength=1.0)
    return None


def _fire_tweezer(window: pd.DataFrame, *, trend_lookback: int = TREND_CONTEXT_LOOKBACK) -> PatternSignal | None:
    """Tweezer top (bearish) / tweezer bottom (bullish) — Bulkowski ch. on
    tweezers: two consecutive bars with matching highs (top, after an
    uptrend) or matching lows (bottom, after a downtrend), read as the
    second bar's failure to extend the first bar's own extreme."""
    if len(window) < trend_lookback + 2:
        return None
    b1, b2 = window.iloc[-2], window.iloc[-1]
    trend_rows = window.iloc[-(trend_lookback + 2) : -2]
    if len(trend_rows) < trend_lookback:
        return None
    trend = trend_rows["close"].iloc[-1] - trend_rows["close"].iloc[0]
    if trend == 0 or b1["low"] <= 0 or b1["high"] <= 0:
        return None
    low_diff = abs(b1["low"] - b2["low"]) / b1["low"]
    high_diff = abs(b1["high"] - b2["high"]) / b1["high"]
    if low_diff <= TWEEZER_MATCH_TOLERANCE and trend < 0:
        return PatternSignal(direction="long", strength=1.0)
    if high_diff <= TWEEZER_MATCH_TOLERANCE and trend > 0:
        return PatternSignal(direction="short", strength=1.0)
    return None


_CANDLESTICK_FIRE_FNS: dict[str, Callable[[pd.DataFrame], PatternSignal | None]] = {
    "engulfing": _fire_engulfing,
    "doji_reversal": _fire_doji_reversal,
    "three_bar_reversal": _fire_three_bar_reversal,
    "hammer_family": _fire_hammer_family,
    "star_reversal": _fire_star_reversal,
    "piercing_darkcloud": _fire_piercing_darkcloud,
    "harami": _fire_harami,
    "tweezer": _fire_tweezer,
}


# --- Family 5: RSI extremes (Wilder 1978) --------------------------------
# Wilder, J. Welles, "New Concepts in Technical Trading Systems" (1978) —
# the original source of the Relative Strength Index and its 70/30
# overbought/oversold reading: an RSI at or beyond the extreme predicts
# mean reversion. Computed on the window's own chronological close-price
# sequence (NOT reset per trading day, unlike VWAP) — this is how every
# real intraday RSI implementation actually works (RSI has no natural
# daily anchor the way a volume-weighted average does), a deliberate,
# disclosed difference from Family 3's session-anchoring, not an
# inconsistency. Gain/loss averaging uses a plain mean over the trailing
# `period` bars (Wilder's own original first-calculation step) rather than
# his subsequent exponential smoothing, which needs unbounded historical
# state this fixed INTRADAY_FIT_WINDOW_BARS-sized window doesn't carry — a
# disclosed simplification, not the full recursive formula.

RSI_PERIODS = (7, 14)
RSI_THRESHOLD_PAIRS: tuple[tuple[float, float], ...] = ((70.0, 30.0), (75.0, 25.0), (80.0, 20.0))


def _fire_rsi_extreme(window: pd.DataFrame, *, period: int, overbought: float, oversold: float) -> PatternSignal | None:
    closes = window["close"]
    if len(closes) < period + 1:
        return None
    deltas = closes.diff().dropna()
    if len(deltas) < period:
        return None
    recent = deltas.iloc[-period:]
    avg_gain = recent.clip(lower=0).mean()
    avg_loss = (-recent.clip(upper=0)).mean()
    if avg_loss == 0:
        rsi = 100.0
    else:
        rsi = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    if not np.isfinite(rsi):
        return None
    if rsi >= overbought:
        return PatternSignal(direction="short", strength=rsi - overbought)
    if rsi <= oversold:
        return PatternSignal(direction="long", strength=oversold - rsi)
    return None


# --- Family 6: Bollinger Band mean-reversion (Bollinger 2001) ------------
# Bollinger, John, "Bollinger on Bollinger Bands" (McGraw-Hill, 2001) —
# Bollinger's own published rule: a close outside the band (a rolling mean
# +/- N standard deviations of recent closes) predicts reversion back
# toward the mean. Same cross-day-boundary chronological-close-sequence
# convention as Family 5's RSI, for the same reason (no natural daily
# anchor).

BOLLINGER_PERIODS = (10, 14)
BOLLINGER_STD_MULTIPLES = (1.5, 2.0, 2.5)


def _fire_bollinger_reversion(window: pd.DataFrame, *, period: int, n_std: float) -> PatternSignal | None:
    closes = window["close"]
    if len(closes) < period:
        return None
    recent = closes.iloc[-period:]
    mean = recent.mean()
    std = recent.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return None
    last_close = closes.iloc[-1]
    upper = mean + n_std * std
    lower = mean - n_std * std
    if last_close > upper:
        return PatternSignal(direction="short", strength=(last_close - upper) / std)
    if last_close < lower:
        return PatternSignal(direction="long", strength=(lower - last_close) / std)
    return None


# --- Family 7: Moving-average crossover (Brock, Lakonishok & LeBaron) ---
# Brock, Lakonishok & LeBaron, "Simple Technical Trading Rules and the
# Stochastic Properties of Stock Returns" (Journal of Finance, 1992) — the
# definitive academic study of MA crossover trading rules (originally
# tested at daily frequency; adapted here to hourly bars, same discipline
# as Family 2's daily-paper-adapted-to-hourly-bars treatment). A short MA
# crossing above a long MA predicts continued upward momentum, and vice
# versa. NOT session-phase-gated, unlike every other family here — a
# crossover is a trend-following event with no inherent time-of-day
# structure, so gating it by session phase would just throw away most of
# its already-rare firings rather than testing a genuinely different
# hypothesis. long_period is capped at 19 so long_period+1 <=
# INTRADAY_FIT_WINDOW_BARS=20 — a crossover pair whose long leg doesn't
# fit inside the walk-forward window can never be evaluated at all.

MA_CROSSOVER_PAIRS: tuple[tuple[int, int], ...] = ((2, 5), (3, 8), (4, 10), (5, 13), (6, 15), (8, 19))


def _fire_ma_crossover(window: pd.DataFrame, *, short_period: int, long_period: int) -> PatternSignal | None:
    closes = window["close"]
    if len(closes) < long_period + 1:
        return None
    short_ma = closes.rolling(short_period).mean()
    long_ma = closes.rolling(long_period).mean()
    if short_ma.iloc[-2:].isna().any() or long_ma.iloc[-2:].isna().any():
        return None
    prev_diff = short_ma.iloc[-2] - long_ma.iloc[-2]
    cur_diff = short_ma.iloc[-1] - long_ma.iloc[-1]
    if prev_diff <= 0 and cur_diff > 0:
        return PatternSignal(direction="long", strength=abs(cur_diff))
    if prev_diff >= 0 and cur_diff < 0:
        return PatternSignal(direction="short", strength=abs(cur_diff))
    return None


# --- Family 8: Volume-price divergence (Wyckoff 1910; Granville 1963) ---
# Wyckoff, Richard D. (writing as "Rollo Tape"), "Studies in Tape Reading"
# (1910) — the original "volume climax" exhaustion-reversal reading: a
# sudden multiple-of-average volume spike marks the end of a move, not its
# continuation. Granville, Joseph E., "Granville's New Key to Stock Market
# Profits" (1963) — the origin of On-Balance-Volume and the competing
# "volume confirms price" reading, tested here as the honestly co-equal
# `reverse=False` alternative (this project's own established test-both-
# directions discipline, same as Family 2's reverse flag) rather than
# assuming the exhaustion reading is the right one.

VOLUME_CLIMAX_MULTIPLES = (2.0, 3.0, 4.0)


def _fire_volume_climax(window: pd.DataFrame, *, reverse: bool, volume_multiple: float) -> PatternSignal | None:
    if len(window) < 2:
        return None
    bar = window.iloc[-1]
    avg_volume = window.iloc[:-1]["volume"].mean()
    if avg_volume <= 0 or not np.isfinite(avg_volume):
        return None
    if bar["volume"] < volume_multiple * avg_volume:
        return None
    r = bar["ret"]
    if not np.isfinite(r) or r == 0:
        return None
    base_direction = 1.0 if r > 0 else -1.0
    sign = -1.0 if reverse else 1.0
    predicted = base_direction * sign
    return PatternSignal(direction="long" if predicted > 0 else "short", strength=abs(r))


# --- Family 9: Day-of-week seasonality (French 1980; Harris 1986) -------
# French, Kenneth R., "Stock Returns and the Weekend Effect" (Journal of
# Financial Economics, 1980) — the original "weekend effect" finding
# (Monday returns are, on average, historically negative while other
# weekdays are not). Harris, Lawrence, "A Transaction Data Study of Weekly
# and Intradaily Patterns in Stock Returns" (Journal of Financial
# Economics, 1986) — extends the weekday-return-pattern literature to
# intraday data specifically. Operationalized here as a fixed per-weekday
# directional bet, tested honestly at BOTH directions for EVERY weekday
# (not just "short Mondays, as French found") — this project's own
# test-both-directions/test-every-candidate discipline, not cherry-picking
# the one weekday/direction combination the literature already flagged.
# Fires on every bar of the matching weekday (not just its open), using
# window.iloc[-1]'s own trading_date directly — correct for 6 of every 7
# firings (same day as window's last bar); the 7th (window.iloc[-1] being
# a trading day's own "close" bar, i.e. the NEXT bar crosses into a new
# calendar day and typically a new weekday) is a small, disclosed, honest
# noise source, not a lookahead: no future information is used, the label
# is just occasionally one calendar day stale for that specific bar.

WEEKDAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday")


def _fire_day_of_week(window: pd.DataFrame, *, weekday: int, direction: Literal["long", "short"]) -> PatternSignal | None:
    bar = window.iloc[-1]
    if bar["trading_date"].weekday() != weekday:
        return None
    return PatternSignal(direction=direction, strength=1.0)


# --- Families 10-11: Overnight close-to-open persistence (Berkman et al.)
# Berkman, Koch, Tuttle & Zhang, "Paying Attention: Overnight Returns and
# the Persistence of Institutional Trading" (Journal of Financial and
# Quantitative Analysis, 2012) — overnight order-flow dynamics predict
# next-day intraday returns. The TRUE overnight gap (prior close vs. THIS
# day's own open) cannot be used as a predictor here without lookahead:
# fire_fn only ever sees `window` (bars up to and including t-1) and never
# day_row (bar t, whose own open price the "gap" would need) — see
# run_walk_forward's own docstring. Instead, the prior trading day's own
# FINAL bar's return (window.iloc[-1] when gated to "close", or a same-
# window lookback otherwise) is used as an observable, lookahead-safe
# proxy for the same overnight-positioning phenomenon Berkman et al.
# study — a disclosed methodology decision, not an attempt to test the
# literal paper's exact measure.
#
# Family 10 (immediate): fires on the transition FROM the prior day's own
# close bar, predicting the very next bar (day D's own open). Family 11
# (persistence): fires on LATER bars within day D (mid_morning/midday/
# power_hour), testing whether the same close-bar-return predictor keeps
# mattering several bars past the open, not just immediately after it —
# requires looking back within `window` for the most recent PRIOR
# trading day's own close-phase bar, since window.iloc[-1] is no longer
# that bar itself by the time we're several bars into day D.

OVERNIGHT_RETURN_THRESHOLDS = (0.001, 0.002, 0.004)
OVERNIGHT_PERSISTENCE_PHASES: tuple[SessionPhase, ...] = ("mid_morning", "midday", "power_hour")


def _fire_prior_bar_momentum(window: pd.DataFrame, *, reverse: bool, min_return: float) -> PatternSignal | None:
    """Generic 'the most recently observed bar's own return predicts the
    NEXT (unseen) bar's return, same or opposite direction' primitive.
    Structurally similar to Family 1's ORB-continuation (which also just
    reads window.iloc[-1]'s own ret) but a separate, distinctly-cited
    hypothesis (Berkman et al.'s overnight-persistence finding, not
    Crabel's opening-range one) — used here gated to the "close" phase, so
    window.iloc[-1] is the prior trading day's own final bar."""
    bar = window.iloc[-1]
    r = bar["ret"]
    if not np.isfinite(r) or abs(r) < min_return:
        return None
    sign = -1.0 if reverse else 1.0
    predicted = r * sign
    return PatternSignal(direction="long" if predicted > 0 else "short", strength=abs(r))


def _fire_overnight_gap_persistence(window: pd.DataFrame, *, reverse: bool, min_return: float) -> PatternSignal | None:
    bar = window.iloc[-1]
    current_date = bar["trading_date"]
    prior_rows = window[window["trading_date"] < current_date]
    if prior_rows.empty:
        return None
    prior_date = prior_rows["trading_date"].max()
    prior_close_rows = prior_rows[
        (prior_rows["trading_date"] == prior_date) & (prior_rows["session_phase"] == "close")
    ]
    if prior_close_rows.empty:
        return None
    close_ret = prior_close_rows.iloc[-1]["ret"]
    if not np.isfinite(close_ret) or abs(close_ret) < min_return:
        return None
    sign = -1.0 if reverse else 1.0
    predicted = close_ret * sign
    return PatternSignal(direction="long" if predicted > 0 else "short", strength=abs(close_ret))


def _build_pattern_family() -> list[PatternSpec]:
    """Assembles the full, fixed pattern family — see this module's own
    header docstring for the current total and its per-family breakdown.
    This list is the literal n_trials denominator screen_pattern_universe
    passes to compute_deflated_sharpe — see that function's own docstring
    for why."""
    specs: list[PatternSpec] = []

    orb_citation = "Crabel, 'Day Trading with Short Term Price Patterns and Opening Range Breakout' (1990)"
    for threshold in ORB_BREAKOUT_THRESHOLDS:
        specs.append(
            PatternSpec(
                pattern_id=f"orb_continuation_open_{threshold:.4f}",
                family="opening_range_breakout",
                citation=orb_citation,
                fire_fn=_gate_to_session_phase(
                    partial(_fire_orb_continuation, breakout_threshold=threshold), "open"
                ),
            )
        )

    gao_citation = "Gao, Han, Xie & Yang, 'Market Intraday Momentum' (Journal of Financial Economics, 2018)"
    for reverse in (False, True):
        for threshold in GAO_OPEN_RETURN_THRESHOLDS:
            for phase in GAO_MOMENTUM_PHASES:
                specs.append(
                    PatternSpec(
                        pattern_id=(
                            f"intraday_momentum_{'reversal' if reverse else 'continuation'}_{phase}_{threshold:.4f}"
                        ),
                        family="intraday_momentum_gao2018",
                        citation=gao_citation,
                        fire_fn=_gate_to_session_phase(
                            partial(_fire_intraday_momentum, reverse=reverse, min_open_return=threshold),
                            phase,
                        ),
                    )
                )

    vwap_citation = "Madhavan, 'VWAP Strategies' (Journal of Portfolio Management, 2002)"
    for phase in VWAP_REVERSION_PHASES:
        for threshold in VWAP_DEVIATION_THRESHOLDS:
            for price_convention in VWAP_PRICE_CONVENTIONS:
                specs.append(
                    PatternSpec(
                        pattern_id=f"vwap_reversion_{price_convention}_{phase}_{threshold:.3f}",
                        family="vwap_reversion",
                        citation=vwap_citation,
                        fire_fn=_gate_to_session_phase(
                            partial(
                                _fire_vwap_reversion,
                                deviation_threshold=threshold,
                                price_convention=price_convention,
                            ),
                            phase,
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

    rsi_citation = "Wilder, J. Welles, 'New Concepts in Technical Trading Systems' (1978)"
    for period in RSI_PERIODS:
        for overbought, oversold in RSI_THRESHOLD_PAIRS:
            for phase in SESSION_PHASES[1:]:  # excludes "open" — RSI needs prior bars, thinnest right at the open
                specs.append(
                    PatternSpec(
                        pattern_id=f"rsi_extreme_{period}_{overbought:.0f}_{oversold:.0f}_{phase}",
                        family="rsi_extreme_wilder1978",
                        citation=rsi_citation,
                        fire_fn=_gate_to_session_phase(
                            partial(_fire_rsi_extreme, period=period, overbought=overbought, oversold=oversold),
                            phase,
                        ),
                    )
                )

    bollinger_citation = "Bollinger, John, 'Bollinger on Bollinger Bands' (McGraw-Hill, 2001)"
    for period in BOLLINGER_PERIODS:
        for n_std in BOLLINGER_STD_MULTIPLES:
            for phase in SESSION_PHASES[1:]:
                specs.append(
                    PatternSpec(
                        pattern_id=f"bollinger_reversion_{period}_{n_std:.1f}_{phase}",
                        family="bollinger_reversion",
                        citation=bollinger_citation,
                        fire_fn=_gate_to_session_phase(
                            partial(_fire_bollinger_reversion, period=period, n_std=n_std), phase
                        ),
                    )
                )

    ma_citation = (
        "Brock, Lakonishok & LeBaron, 'Simple Technical Trading Rules and the Stochastic "
        "Properties of Stock Returns' (Journal of Finance, 1992)"
    )
    for short_period, long_period in MA_CROSSOVER_PAIRS:
        specs.append(
            PatternSpec(
                pattern_id=f"ma_crossover_{short_period}_{long_period}",
                family="ma_crossover_brock1992",
                citation=ma_citation,
                fire_fn=partial(_fire_ma_crossover, short_period=short_period, long_period=long_period),
            )
        )

    volume_citation = (
        "Wyckoff (as 'Rollo Tape'), 'Studies in Tape Reading' (1910); "
        "Granville, 'Granville's New Key to Stock Market Profits' (1963)"
    )
    for reverse in (False, True):
        for multiple in VOLUME_CLIMAX_MULTIPLES:
            for phase in SESSION_PHASES:
                specs.append(
                    PatternSpec(
                        pattern_id=(
                            f"volume_{'climax' if reverse else 'confirmation'}_{multiple:.0f}x_{phase}"
                        ),
                        family="volume_price_divergence",
                        citation=volume_citation,
                        fire_fn=_gate_to_session_phase(
                            partial(_fire_volume_climax, reverse=reverse, volume_multiple=multiple), phase
                        ),
                    )
                )

    seasonality_citation = (
        "French, 'Stock Returns and the Weekend Effect' (Journal of Financial Economics, 1980); "
        "Harris, 'A Transaction Data Study of Weekly and Intradaily Patterns in Stock Returns' "
        "(Journal of Financial Economics, 1986)"
    )
    for weekday, weekday_name in enumerate(WEEKDAY_NAMES):
        for direction in ("long", "short"):
            specs.append(
                PatternSpec(
                    pattern_id=f"day_of_week_{weekday_name}_{direction}",
                    family="day_of_week_seasonality",
                    citation=seasonality_citation,
                    fire_fn=partial(_fire_day_of_week, weekday=weekday, direction=direction),
                )
            )

    overnight_citation = (
        "Berkman, Koch, Tuttle & Zhang, 'Paying Attention: Overnight Returns and the "
        "Persistence of Institutional Trading' (Journal of Financial and Quantitative "
        "Analysis, 2012)"
    )
    for reverse in (False, True):
        for threshold in OVERNIGHT_RETURN_THRESHOLDS:
            specs.append(
                PatternSpec(
                    pattern_id=f"overnight_{'reversion' if reverse else 'continuation'}_immediate_{threshold:.3f}",
                    family="overnight_close_persistence_berkman2012",
                    citation=overnight_citation,
                    fire_fn=_gate_to_session_phase(
                        partial(_fire_prior_bar_momentum, reverse=reverse, min_return=threshold), "close"
                    ),
                )
            )
            for phase in OVERNIGHT_PERSISTENCE_PHASES:
                specs.append(
                    PatternSpec(
                        pattern_id=(
                            f"overnight_{'reversion' if reverse else 'continuation'}_persist_{phase}_{threshold:.3f}"
                        ),
                        family="overnight_close_persistence_berkman2012",
                        citation=overnight_citation,
                        fire_fn=_gate_to_session_phase(
                            partial(_fire_overnight_gap_persistence, reverse=reverse, min_return=threshold),
                            phase,
                        ),
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
