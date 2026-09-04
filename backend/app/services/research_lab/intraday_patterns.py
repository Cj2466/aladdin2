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
from app.services.research_lab.global_effective_n import dsr_n_trials
from app.services.research_lab.engine import (
    DayResult,
    ExperimentResult,
    StrategyFit,
    WalkForwardConfig,
    run_walk_forward,
)
from app.services.research_lab.metrics import sharpe_ratio

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
    strength: float  # magnitude of whatever moved the pattern to fire — now read by _signal_weight_magnitude below to size the bet, not just to pick a direction (see that function's own docstring for the normalization)


# Magnitude-weighted position sizing (a fix, not a new strategy): every
# fire_fn above already computes `strength`, a genuine measure of how far
# past its own firing condition the pattern fired by — a VWAP deviation of
# 1.2% is a stronger reversion signal than one of 0.21%, an RSI of 95 is a
# stronger overbought reading than one of 71, yet before this change every
# firing pattern placed the exact same flat +-1 bet regardless. The fix,
# applied uniformly via PatternSpec.strength_scale/strength_is_margin and
# _signal_weight_magnitude below:
#
#     weight = clip(magnitude / strength_scale, -MAX_WEIGHT_MULTIPLE, +MAX_WEIGHT_MULTIPLE) * sign(direction)
#
# `strength_scale` is always reused from a threshold the pattern ALREADY
# declares for itself — never a newly-invented per-pattern constant (e.g.
# VWAP reversion's own deviation_threshold, Bollinger's own n_std, an RSI
# family's own overbought/oversold pair) — see each _build_*family
# function below for exactly which existing constant plays this role per
# pattern. `magnitude` is `strength` for a family whose strength is
# already the raw value compared against strength_scale at the firing
# boundary (e.g. VWAP: fires when abs(deviation) >= deviation_threshold,
# and strength IS abs(deviation) — ratio is exactly 1.0 at the boundary,
# by construction). For a family whose strength is instead already a
# MARGIN past its own level (strength_is_margin=True — e.g. RSI: fires at
# rsi>=overbought, strength=rsi-overbought, zero exactly at the boundary,
# not comparable to strength_scale directly), `magnitude` reconstructs the
# pattern's live raw distance from its own neutral center by adding
# strength_scale back (magnitude = strength + strength_scale) BEFORE
# dividing by strength_scale — this recovers the same "ratio == 1.0 at
# exactly the firing boundary" property algebraically for every margin
# family actually used here, because each one's threshold pair is
# symmetric around a fixed, well-known center (50 for a 0-100 oscillator:
# RSI/stochastic/MFI: strength_scale=overbought-50 and, by symmetry,
# =50-oversold too; 0 for Bollinger/Keltner/CCI, already centered by
# construction: strength_scale=n_std/atr_mult/level respectively) — see
# _signal_weight_magnitude's own docstring for the worked derivation.
# Several families have no natural, already-existing, dimensionally-
# matched threshold to reuse at all (MA crossover/MACD's raw price-unit
# diff; volume climax's return-magnitude strength vs. its volume-ratio
# filter; Donchian/pivot breaks with no magnitude constant, only a
# boolean/tier selector; the fixed-shape candlesticks/day-of-week/session-
# bias/OBV-divergence families, whose strength is a constant 1.0 with
# nothing to scale against anyway) — these keep strength_scale=None and
# stay at the historical flat +-1 bet, per the "do not invent a new
# per-pattern constant" instruction, rather than being forced through an
# ungrounded scale.
#
# MAX_WEIGHT_MULTIPLE=3.0 is the ONE constant shared by every pattern
# here (and, per this phase's task instructions, independently by
# low_frequency_patterns.py's and cross_sectional.py's own copies of this
# same scheme) — never tuned per pattern. Chosen, not fit to these
# results: a conventional soft-leverage guardrail (the same register as a
# vol-target cap or a Kelly-fraction cap in position-sizing practice) that
# still gives real separation between a just-past-threshold and a deeply
# extreme reading, without letting one outlier bar (a data glitch, a freak
# volume spike) blow a single trade up to an unbounded multiple of the
# historical flat +-1 bet. Nothing in this codebase's own results argues
# for a different single value, so it stays at the proposed 3.0.
MAX_WEIGHT_MULTIPLE = 3.0


@dataclass(frozen=True)
class PatternSpec:
    pattern_id: str
    family: str
    citation: str
    fire_fn: Callable[[pd.DataFrame], PatternSignal | None]  # already session-phase-gated
    # See the module-level position-sizing note above PatternSpec for the
    # full design. None (the default) means "no natural, already-existing
    # threshold to normalize strength against" — sizing stays flat +-1 for
    # that pattern, unchanged from before this scheme existed.
    strength_scale: float | None = None
    # True when `strength` is already a margin PAST the firing level
    # (strength==0 exactly at the boundary) rather than a raw value
    # directly comparable to strength_scale (ratio==1 exactly at the
    # boundary already, no reconstruction needed) — see the module-level
    # note above.
    strength_is_margin: bool = False


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
        # Column-then-scalar access instead of row-then-field: building the
        # full row Series crosses every column/block (~12us) while a single
        # column .iat is ~6us — and this check runs once per bar per gated
        # pattern, the single hottest line of the whole screen. Verified
        # value-equivalent on real bar data (including None phases).
        if window.empty or window["session_phase"].iat[-1] != phase:
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
    # Diff only the tail actually used: diffing all 480 bars of a Phase B
    # 1-minute window to keep the last `period` values is pure waste —
    # value-identical to the original full-window diff for NaN-free closes
    # (which both providers' dropna'd OHLCV frames guarantee); a NaN in
    # the tail now yields an honest None instead of silently reaching
    # further back, which is the more correct reading anyway.
    deltas = closes.iloc[-(period + 1) :].diff().dropna()
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
    # Only the last TWO points of each rolling mean are ever read — compute
    # exactly those four window means directly instead of a full rolling
    # series over the whole (up to 480-bar) window. Value-identical to
    # rolling(period).mean().iloc[-2:] by definition of a rolling mean.
    # The isna guard preserves the original's NaN behavior exactly: a NaN
    # close anywhere in the last long_period+1 positions (the union of all
    # four windows) made some rolling value NaN and returned None.
    if closes.iloc[-(long_period + 1) :].isna().any():
        return None
    prev_short = float(closes.iloc[-(short_period + 1) : -1].mean())
    cur_short = float(closes.iloc[-short_period:].mean())
    prev_long = float(closes.iloc[-(long_period + 1) : -1].mean())
    cur_long = float(closes.iloc[-long_period:].mean())
    prev_diff = prev_short - prev_long
    cur_diff = cur_short - cur_long
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
    # Column-then-slice: value-identical to window.iloc[:-1]["volume"] but
    # skips materializing an all-column row-slice frame first.
    avg_volume = window["volume"].iloc[:-1].mean()
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
                # strength=abs(bar_return), fires when abs(bar_return) >= breakout_threshold — raw value directly comparable to its own threshold, ratio==1.0 exactly at the boundary.
                strength_scale=threshold,
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
                        # strength=abs(open_return), fires when abs(open_return) >= min_open_return — raw value, ratio==1.0 at the boundary.
                        strength_scale=threshold,
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
                        # strength=abs(deviation), fires when abs(deviation) >= deviation_threshold — raw value, ratio==1.0 at the boundary.
                        strength_scale=threshold,
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
                    # Every shape but hammer_family fires with a fixed strength=1.0 (a pure shape match, no magnitude) — strength_scale=1.0 makes the ratio trivially 1.0 always, i.e. unchanged flat +-1 sizing. hammer_family's strength (shadow-to-range ratio) has no dimensionally-matched declared threshold to reuse, so it stays unweighted (strength_scale=None) per this scheme's "don't invent a new constant" rule.
                    strength_scale=None if shape_name == "hammer_family" else 1.0,
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
                        # strength=rsi-overbought (or oversold-rsi) is a MARGIN, zero at the boundary — reconstruct the live distance from RSI's own neutral center (50, a 0-100 oscillator) via strength_is_margin; RSI_THRESHOLD_PAIRS is always symmetric (overbought-50 == 50-oversold), so one scale serves both directions. See _signal_weight_magnitude's own docstring for the worked derivation.
                        strength_scale=overbought - 50.0,
                        strength_is_margin=True,
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
                        # strength=(close-band_edge)/std is a MARGIN, zero at the band edge, but already centered at a 0-std mean by construction — reconstructing with strength_is_margin recovers the live close-to-mean distance in std units, ratio==1.0 exactly at n_std standard deviations out (the band edge).
                        strength_scale=n_std,
                        strength_is_margin=True,
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
                    # strength is a fixed 1.0 (a calendar bet, no magnitude) — strength_scale=1.0 keeps the ratio trivially 1.0 always, unchanged flat +-1 sizing.
                    strength_scale=1.0,
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
                    # strength=abs(r), fires when abs(r) >= min_return — raw value, ratio==1.0 at the boundary.
                    strength_scale=threshold,
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
                        # strength=abs(close_ret), fires when abs(close_ret) >= min_return — raw value, ratio==1.0 at the boundary.
                        strength_scale=threshold,
                    )
                )

    return specs


PATTERN_FAMILY: list[PatternSpec] = _build_pattern_family()


# ======================================================================
# Phase B: finer-granularity expansion, against Alpaca bars
# ======================================================================
#
# Everything below extends the family for the Phase B screen (real Alpaca
# SIP bars: 15-minute granularity at 2021->2026 depth for the main group,
# true 1-minute granularity for a dedicated subfamily) while leaving the
# Phase A family and machinery above untouched. Every definition below was
# planned BEFORE the Phase B screening run and is counted in
# PHASE_B_TOTAL_TRIALS regardless of how it performs — same trial-counting
# discipline as Phase A, same reasons (see screen_pattern_universe's
# docstring). The two granularity groups are ONE search: a single n_trials
# denominator spanning both, and a single sigma_SR estimated across every
# pooled Sharpe from both groups (see screen_pattern_groups).

# Walk-forward fit window (in BARS) per Phase B granularity. 15-minute
# days have 26 bars, so same-day lookups (session VWAP, Gao's open-bucket
# bar, prior-day levels) need the window to span the whole current day
# PLUS the whole prior day — 60 bars ≈ 2.3 trading days does, with
# headroom for early closes. 1-minute days have 390 bars, and the
# Heston/Korajczyk/Sadka same-slot family below needs the SAME half-hour
# slot one full trading day back (up to 390+30 bars ago), so 480. These
# are deliberate per-granularity analogues of INTRADAY_FIT_WINDOW_BARS=20
# (Phase A's 7-bar-day sizing), not replacements for it.
FIT_WINDOW_BARS_15MIN = 60
FIT_WINDOW_BARS_1MIN = 480

# Minutes-since-midnight (America/New_York) session landmarks used by the
# minute-gated families below. 09:30 = 570, 10:00 = 600, 12:00 = 720,
# 15:29 = 929, 15:59 = 959, 16:00 = 960.
SESSION_OPEN_MINUTE = 570
SESSION_CLOSE_MINUTE = 960


def _minute_of_day(window: pd.DataFrame) -> int:
    """Minutes since midnight, America/New_York, of the most recently
    OBSERVED bar's start (window.iloc[-1]) — the tz-aware index is already
    New-York-local (both providers' convention)."""
    ts = window.index[-1]
    return ts.hour * 60 + ts.minute


def _gate_to_minute_window(
    fire_fn: Callable[[pd.DataFrame], PatternSignal | None], start_minute: int, end_minute: int
) -> Callable[[pd.DataFrame], PatternSignal | None]:
    """Minute-of-day analogue of _gate_to_session_phase, for 1-minute bars
    where fraction-of-day session phases are too coarse to express
    "the paper's literal first/last half-hour". Same convention: the gate
    applies to the most recently OBSERVED bar (one bar before the bar
    whose return is realized), half-open [start_minute, end_minute)."""

    def gated(window: pd.DataFrame) -> PatternSignal | None:
        if window.empty:
            return None
        minute = _minute_of_day(window)
        if minute < start_minute or minute >= end_minute:
            return None
        return fire_fn(window)

    return gated


# --- Family 12: Keltner channel reversion (Keltner 1960; Raschke) -------
# Keltner, Chester W., "How to Make Money in Commodities" (The Keltner
# Statistical Service, 1960) — the original price-channel band; the modern
# EMA-center/ATR-band form is Linda Bradford Raschke's (Raschke & Connors,
# "Street Smarts: High Probability Short-Term Trading Strategies", 1996).
# A close outside the band predicts reversion toward the center. ATR uses
# a plain mean of true ranges over the trailing period (Wilder's own
# first-calculation step) rather than his recursive smoothing — the same
# disclosed fixed-window simplification as Family 5's RSI.

KELTNER_PERIOD = 20
KELTNER_ATR_MULTIPLES = (1.5, 2.0, 2.5)


def _true_ranges(window: pd.DataFrame) -> pd.Series:
    prev_close = window["close"].shift(1)
    tr = pd.concat(
        [
            window["high"] - window["low"],
            (window["high"] - prev_close).abs(),
            (window["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.dropna()


def _fire_keltner_reversion(window: pd.DataFrame, *, period: int, atr_mult: float) -> PatternSignal | None:
    if len(window) < period + 2:
        return None
    center = float(window["close"].ewm(span=period, adjust=False).mean().iloc[-1])
    trs = _true_ranges(window)
    if len(trs) < period:
        return None
    atr = float(trs.iloc[-period:].mean())
    if atr <= 0 or not np.isfinite(atr) or not np.isfinite(center):
        return None
    last_close = float(window["close"].iloc[-1])
    upper = center + atr_mult * atr
    lower = center - atr_mult * atr
    if last_close > upper:
        return PatternSignal(direction="short", strength=(last_close - upper) / atr)
    if last_close < lower:
        return PatternSignal(direction="long", strength=(lower - last_close) / atr)
    return None


# --- Family 13: Stochastic oscillator extremes (Lane) -------------------
# Lane, George C., "Lane's Stochastics", Technical Analysis of Stocks &
# Commodities, Vol. 2 (1984) — the original %K overbought/oversold
# reading: raw %K at an extreme of its recent high-low range predicts
# reversion. Raw %K (no %D smoothing) — the simplest form of Lane's own
# statistic, a disclosed choice, not his full slow-stochastic recipe.

STOCHASTIC_PERIOD = 14
STOCHASTIC_THRESHOLD_PAIRS: tuple[tuple[float, float], ...] = ((80.0, 20.0), (90.0, 10.0))


def _fire_stochastic_extreme(
    window: pd.DataFrame, *, period: int, overbought: float, oversold: float
) -> PatternSignal | None:
    if len(window) < period:
        return None
    recent = window.iloc[-period:]
    highest = float(recent["high"].max())
    lowest = float(recent["low"].min())
    if highest <= lowest:
        return None
    k = 100.0 * (float(window["close"].iloc[-1]) - lowest) / (highest - lowest)
    if k >= overbought:
        return PatternSignal(direction="short", strength=k - overbought)
    if k <= oversold:
        return PatternSignal(direction="long", strength=oversold - k)
    return None


# --- Family 14: CCI extremes (Lambert 1980) -----------------------------
# Lambert, Donald R., "Commodity Channel Index: Tool for Trading Cyclic
# Trends", Commodities magazine (1980). Lambert's OWN reading is
# trend-following (CCI beyond +100 signals a tradeable up-cycle); the
# widely-used modern alternative fades the extreme as overbought/oversold.
# Both readings are tested as honestly co-equal (`reverse` flag), the same
# discipline as Families 2 and 8.

CCI_PERIOD = 20
CCI_LEVELS = (100.0, 200.0)


def _fire_cci_extreme(window: pd.DataFrame, *, period: int, level: float, reverse: bool) -> PatternSignal | None:
    if len(window) < period:
        return None
    typical = (window["high"] + window["low"] + window["close"]) / 3.0
    recent = typical.iloc[-period:]
    sma = float(recent.mean())
    mad = float((recent - sma).abs().mean())
    if mad <= 0 or not np.isfinite(mad):
        return None
    cci = (float(typical.iloc[-1]) - sma) / (0.015 * mad)
    if not np.isfinite(cci) or abs(cci) < level:
        return None
    base = 1.0 if cci > 0 else -1.0  # Lambert: trade WITH the cycle
    sign = -1.0 if reverse else 1.0
    predicted = base * sign
    return PatternSignal(direction="long" if predicted > 0 else "short", strength=abs(cci) - level)


# --- Family 15: MACD signal-line crossover (Appel 1979) -----------------
# Appel, Gerald, "The Moving Average Convergence-Divergence Trading
# Method" (Signalert, 1979) — MACD line crossing its own signal line
# predicts continuation in the cross's direction. EMAs are computed over
# the walk-forward window only (adjust=False), a disclosed fixed-window
# approximation of Appel's unbounded recursive EMAs — same register as the
# RSI/ATR simplifications above. Ungated by session phase, like Family 7:
# a crossover has no inherent time-of-day structure.

MACD_PARAMETER_SETS: tuple[tuple[int, int, int], ...] = ((12, 26, 9), (8, 17, 9))


def _fire_macd_cross(window: pd.DataFrame, *, fast: int, slow: int, signal: int) -> PatternSignal | None:
    if len(window) < slow + signal + 1:
        return None
    closes = window["close"]
    macd = closes.ewm(span=fast, adjust=False).mean() - closes.ewm(span=slow, adjust=False).mean()
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    prev_diff = float(macd.iloc[-2] - signal_line.iloc[-2])
    cur_diff = float(macd.iloc[-1] - signal_line.iloc[-1])
    if not (np.isfinite(prev_diff) and np.isfinite(cur_diff)):
        return None
    if prev_diff <= 0 and cur_diff > 0:
        return PatternSignal(direction="long", strength=abs(cur_diff))
    if prev_diff >= 0 and cur_diff < 0:
        return PatternSignal(direction="short", strength=abs(cur_diff))
    return None


# --- Family 16: Money Flow Index extremes (Quong & Soudack 1989) --------
# Quong, Gene & Soudack, Avrum, "Volume-Weighted RSI: Money Flow",
# Technical Analysis of Stocks & Commodities (March 1989) — RSI's
# overbought/oversold reading applied to volume-weighted money flow.

MFI_PERIOD = 14
MFI_THRESHOLD_PAIRS: tuple[tuple[float, float], ...] = ((80.0, 20.0), (90.0, 10.0))


def _fire_mfi_extreme(
    window: pd.DataFrame, *, period: int, overbought: float, oversold: float
) -> PatternSignal | None:
    if len(window) < period + 1:
        return None
    typical = (window["high"] + window["low"] + window["close"]) / 3.0
    money_flow = typical * window["volume"]
    direction = typical.diff()
    recent_flow = money_flow.iloc[-period:]
    recent_dir = direction.iloc[-period:]
    positive = float(recent_flow[recent_dir > 0].sum())
    negative = float(recent_flow[recent_dir < 0].sum())
    if positive + negative <= 0:
        return None
    mfi = 100.0 if negative == 0 else 100.0 - (100.0 / (1.0 + positive / negative))
    if not np.isfinite(mfi):
        return None
    if mfi >= overbought:
        return PatternSignal(direction="short", strength=mfi - overbought)
    if mfi <= oversold:
        return PatternSignal(direction="long", strength=oversold - mfi)
    return None


# --- Family 17: Intraday time-of-day seasonality (Wood/McInish/Ord) -----
# Wood, McInish & Ord, "An Investigation of Transactions Data for NYSE
# Stocks" (Journal of Finance, 1985) and Harris, "A Transaction Data
# Study of Weekly and Intradaily Patterns in Stock Returns" (JFE, 1986) —
# systematic time-of-day return structure (the U-shaped pattern: returns
# concentrate near the open and close). Operationalized exactly like
# Family 9's weekday bets: a fixed directional bet during each session
# phase, BOTH directions tested for EVERY phase, not just the literature's
# open/close-positive finding.


def _fire_session_bias(window: pd.DataFrame, *, direction: Literal["long", "short"]) -> PatternSignal | None:
    del window
    return PatternSignal(direction=direction, strength=1.0)


# --- Family 18: Prior-day-level breakout (Donchian channel) -------------
# Donchian, Richard D., "Trend-Following Methods in Commodity Price
# Analysis", Commodity Year Book (1957) — the original price-channel
# breakout rule: price exceeding the prior period's extreme signals
# continuation. Adapted intraday: a close beyond the PRIOR trading day's
# high/low. The fade reading (`reverse=True`) is tested as honestly
# co-equal, per house discipline.


def _fire_prior_day_level_break(window: pd.DataFrame, *, reverse: bool) -> PatternSignal | None:
    bar = window.iloc[-1]
    current_date = bar["trading_date"]
    prior_rows = window[window["trading_date"] < current_date]
    if prior_rows.empty:
        return None
    prior_date = prior_rows["trading_date"].max()
    prior_day = prior_rows[prior_rows["trading_date"] == prior_date]
    prior_high = float(prior_day["high"].max())
    prior_low = float(prior_day["low"].min())
    last_close = float(bar["close"])
    sign = -1.0 if reverse else 1.0
    if last_close > prior_high:
        predicted = 1.0 * sign
        strength = (last_close - prior_high) / prior_high
    elif last_close < prior_low:
        predicted = -1.0 * sign
        strength = (prior_low - last_close) / prior_low
    else:
        return None
    return PatternSignal(direction="long" if predicted > 0 else "short", strength=strength)


# --- Family 19: Floor-trader pivot reversion (Person 2004) --------------
# Person, John L., "A Complete Guide to Technical Trading Tactics: How to
# Profit Using Pivot Points, Candlesticks & Other Indicators" (Wiley,
# 2004) — the classical floor pivots: PP = (H+L+C)/3 of the prior day,
# R1 = 2*PP - L, S1 = 2*PP - H, R2 = PP + (H-L), S2 = PP - (H-L); price
# reaching a resistance/support level is read as extended and expected to
# revert.

PIVOT_LEVELS = (1, 2)  # R1/S1 vs R2/S2


def _fire_pivot_reversion(window: pd.DataFrame, *, level: int) -> PatternSignal | None:
    bar = window.iloc[-1]
    current_date = bar["trading_date"]
    prior_rows = window[window["trading_date"] < current_date]
    if prior_rows.empty:
        return None
    prior_date = prior_rows["trading_date"].max()
    prior_day = prior_rows[prior_rows["trading_date"] == prior_date]
    high = float(prior_day["high"].max())
    low = float(prior_day["low"].min())
    close = float(prior_day["close"].iloc[-1])
    pp = (high + low + close) / 3.0
    if level == 1:
        resistance, support = 2 * pp - low, 2 * pp - high
    else:
        resistance, support = pp + (high - low), pp - (high - low)
    last_close = float(bar["close"])
    if resistance <= support or resistance <= 0:
        return None
    if last_close >= resistance:
        return PatternSignal(direction="short", strength=(last_close - resistance) / resistance)
    if last_close <= support:
        return PatternSignal(direction="long", strength=(support - last_close) / max(support, 1e-12))
    return None


# --- Family 20: ATR range-expansion (Wilder 1978; Crabel 1990) ----------
# Wilder (1978) defines ATR; range-expansion trading — an unusually wide
# bar signaling follow-through — is Crabel (1990)'s stretch/expansion
# reading. The exhaustion reading (an unusually wide bar marking the END
# of the move) is tested as honestly co-equal via `reverse`, mirroring
# Family 8's climax-vs-confirmation treatment.

ATR_EXPANSION_PERIOD = 14
ATR_EXPANSION_MULTIPLES = (1.5, 2.5)


def _fire_atr_expansion(window: pd.DataFrame, *, atr_mult: float, reverse: bool) -> PatternSignal | None:
    if len(window) < ATR_EXPANSION_PERIOD + 2:
        return None
    trs = _true_ranges(window)
    if len(trs) < ATR_EXPANSION_PERIOD + 1:
        return None
    last_tr = float(trs.iloc[-1])
    atr = float(trs.iloc[-(ATR_EXPANSION_PERIOD + 1) : -1].mean())
    if atr <= 0 or not np.isfinite(atr) or last_tr < atr_mult * atr:
        return None
    r = window.iloc[-1]["ret"]
    if not np.isfinite(r) or r == 0:
        return None
    base = 1.0 if r > 0 else -1.0
    sign = -1.0 if reverse else 1.0
    predicted = base * sign
    return PatternSignal(direction="long" if predicted > 0 else "short", strength=last_tr / atr)


# --- Family 21: Consecutive-close streaks (Lehmann 1990) ----------------
# Lehmann, Bruce N., "Fads, Martingales, and Market Efficiency" (Quarterly
# Journal of Economics, 1990) — short-horizon return reversal: a run of
# same-direction moves predicts a bounce. The continuation reading
# (streaks persist — the short-horizon momentum framing of Jegadeesh &
# Titman, "Returns to Buying Winners and Selling Losers", Journal of
# Finance, 1993) is tested as honestly co-equal via `reverse`.

STREAK_LENGTHS = (3, 5)


def _fire_close_streak(window: pd.DataFrame, *, streak_len: int, reverse: bool) -> PatternSignal | None:
    closes = window["close"]
    if len(closes) < streak_len + 1:
        return None
    diffs = closes.diff().iloc[-streak_len:]
    if (diffs > 0).all():
        base = 1.0
    elif (diffs < 0).all():
        base = -1.0
    else:
        return None
    # reverse=True is Lehmann's reversal bet (fade the streak);
    # reverse=False is the continuation bet.
    sign = -1.0 if reverse else 1.0
    predicted = base * sign
    return PatternSignal(direction="long" if predicted > 0 else "short", strength=float(streak_len))


# --- Family 22: OBV divergence (Granville 1963) -------------------------
# Granville, Joseph E., "Granville's New Key to Stock Market Profits"
# (Prentice-Hall, 1963) — On-Balance-Volume leads price: when OBV's recent
# trend disagrees with price's, price is expected to follow OBV.

OBV_DIVERGENCE_LOOKBACKS = (10, 20)


def _fire_obv_divergence(window: pd.DataFrame, *, lookback: int) -> PatternSignal | None:
    if len(window) < lookback + 2:
        return None
    closes = window["close"]
    signs = np.sign(closes.diff().fillna(0.0))
    obv = (signs * window["volume"]).cumsum()
    obv_change = float(obv.iloc[-1] - obv.iloc[-1 - lookback])
    price_change = float(closes.iloc[-1] - closes.iloc[-1 - lookback])
    if obv_change == 0 or price_change == 0:
        return None
    if np.sign(obv_change) == np.sign(price_change):
        return None  # agreement — no divergence to trade
    return PatternSignal(direction="long" if obv_change > 0 else "short", strength=1.0)


# --- Family 23 parameters: RSI(2)-style extremes (Connors & Alvarez) ----
# Connors, Larry & Alvarez, Cesar, "Short Term Trading Strategies That
# Work" (TradingMarkets, 2008) — the RSI(2) strategy: an extremely short
# RSI lookback at extreme thresholds (95/5, 90/10). Reuses Family 5's
# _fire_rsi_extreme unchanged; only the parameterization is new, and only
# meaningful at intraday granularity this fine.
CONNORS_RSI_PERIODS = (2, 3)
CONNORS_RSI_THRESHOLD_PAIRS: tuple[tuple[float, float], ...] = ((95.0, 5.0), (90.0, 10.0))

# --- Family 24 parameters: Bollinger's own canonical 20-period ----------
# Bollinger (2001)'s canonical default is 20 bars — impossible inside
# Phase A's 20-bar window (period == window leaves no return step), now
# unlocked by the 60-bar Phase B window. Reuses _fire_bollinger_reversion.
BOLLINGER_CANONICAL_PERIOD = 20

# --- Family 25 parameters: longer MA-crossover pairs (Brock et al.) -----
# Brock, Lakonishok & LeBaron (1992) tested rules out to 1-200 at daily
# frequency; Phase A's 20-bar window capped the long leg at 19. The
# 60-bar window unlocks intraday analogues of their longer pairs.
MA_CROSSOVER_PAIRS_15MIN: tuple[tuple[int, int], ...] = ((5, 20), (8, 30), (10, 40), (12, 50))

# --- Family 26: Gao momentum from the TRUE first half-hour --------------
# Gao, Han, Xie & Yang (JFE 2018) define the predictor as the day's FIRST
# HALF-HOUR return. At 15-minute bars that is exactly the day's first TWO
# bars — materially closer to the paper than Phase A's one-hourly-bar
# "open bucket" adaptation, and only expressible at this granularity.
GAO_FIRST_HALF_HOUR_THRESHOLDS = (0.001, 0.002, 0.003)


def _fire_gao_first_half_hour(
    window: pd.DataFrame, *, reverse: bool, min_open_return: float, n_open_bars: int = 2
) -> PatternSignal | None:
    bar = window.iloc[-1]
    trading_date = bar["trading_date"]
    day_rows = window[window["trading_date"] == trading_date]
    if len(day_rows) < n_open_bars:
        return None
    first = day_rows.iloc[0]
    last_open_bar = day_rows.iloc[n_open_bars - 1]
    open_price = float(first["open"])
    if open_price <= 0:
        return None
    open_return = (float(last_open_bar["close"]) - open_price) / open_price
    if not np.isfinite(open_return) or abs(open_return) < min_open_return:
        return None
    sign = -1.0 if reverse else 1.0
    predicted = open_return * sign
    return PatternSignal(direction="long" if predicted > 0 else "short", strength=abs(open_return))


# The non-open session phases most Phase B additions are gated to — the
# same "needs prior bars, thinnest right at the open" reasoning as
# Family 5/6's SESSION_PHASES[1:].
PHASE_B_GATED_PHASES: tuple[SessionPhase, ...] = SESSION_PHASES[1:]


def _build_phase_b_15min_additions() -> list[PatternSpec]:
    """The 15-minute-native additions (run ALONGSIDE the base 212 at
    15-minute granularity). See each family's own citation comment."""
    specs: list[PatternSpec] = []

    keltner_citation = (
        "Keltner, 'How to Make Money in Commodities' (1960); Raschke & Connors, "
        "'Street Smarts: High Probability Short-Term Trading Strategies' (1996)"
    )
    for atr_mult in KELTNER_ATR_MULTIPLES:
        for phase in PHASE_B_GATED_PHASES:
            specs.append(
                PatternSpec(
                    pattern_id=f"keltner_reversion_{KELTNER_PERIOD}_{atr_mult:.1f}_{phase}",
                    family="keltner_reversion",
                    citation=keltner_citation,
                    fire_fn=_gate_to_session_phase(
                        partial(_fire_keltner_reversion, period=KELTNER_PERIOD, atr_mult=atr_mult), phase
                    ),
                    # strength=(close-band_edge)/atr is a MARGIN, zero at the band edge, already centered at a 0-ATR mean by construction — same reconstruction as Bollinger.
                    strength_scale=atr_mult,
                    strength_is_margin=True,
                )
            )

    stochastic_citation = "Lane, George C., 'Lane's Stochastics', Technical Analysis of Stocks & Commodities Vol. 2 (1984)"
    for overbought, oversold in STOCHASTIC_THRESHOLD_PAIRS:
        for phase in PHASE_B_GATED_PHASES:
            specs.append(
                PatternSpec(
                    pattern_id=f"stochastic_extreme_{STOCHASTIC_PERIOD}_{overbought:.0f}_{oversold:.0f}_{phase}",
                    family="stochastic_extreme_lane1984",
                    citation=stochastic_citation,
                    fire_fn=_gate_to_session_phase(
                        partial(
                            _fire_stochastic_extreme,
                            period=STOCHASTIC_PERIOD,
                            overbought=overbought,
                            oversold=oversold,
                        ),
                        phase,
                    ),
                    # strength=%K-overbought (or oversold-%K) is a MARGIN, zero at the boundary — %K is a 0-100 oscillator centered at 50, and STOCHASTIC_THRESHOLD_PAIRS is symmetric, so the same RSI-style reconstruction applies.
                    strength_scale=overbought - 50.0,
                    strength_is_margin=True,
                )
            )

    cci_citation = "Lambert, Donald R., 'Commodity Channel Index: Tool for Trading Cyclic Trends', Commodities (1980)"
    for reverse in (False, True):
        for level in CCI_LEVELS:
            for phase in PHASE_B_GATED_PHASES:
                specs.append(
                    PatternSpec(
                        pattern_id=f"cci_{'reversion' if reverse else 'trend'}_{level:.0f}_{phase}",
                        family="cci_lambert1980",
                        citation=cci_citation,
                        fire_fn=_gate_to_session_phase(
                            partial(_fire_cci_extreme, period=CCI_PERIOD, level=level, reverse=reverse),
                            phase,
                        ),
                        # strength=abs(cci)-level is a MARGIN, zero at the boundary, but CCI is already centered at 0 via its own abs() — reconstructing recovers abs(cci) directly, ratio==1.0 exactly at abs(cci)==level.
                        strength_scale=level,
                        strength_is_margin=True,
                    )
                )

    macd_citation = "Appel, Gerald, 'The Moving Average Convergence-Divergence Trading Method' (Signalert, 1979)"
    for fast, slow, signal in MACD_PARAMETER_SETS:
        specs.append(
            PatternSpec(
                pattern_id=f"macd_cross_{fast}_{slow}_{signal}",
                family="macd_appel1979",
                citation=macd_citation,
                fire_fn=partial(_fire_macd_cross, fast=fast, slow=slow, signal=signal),
            )
        )

    mfi_citation = "Quong & Soudack, 'Volume-Weighted RSI: Money Flow', Technical Analysis of Stocks & Commodities (1989)"
    for overbought, oversold in MFI_THRESHOLD_PAIRS:
        for phase in PHASE_B_GATED_PHASES:
            specs.append(
                PatternSpec(
                    pattern_id=f"mfi_extreme_{MFI_PERIOD}_{overbought:.0f}_{oversold:.0f}_{phase}",
                    family="mfi_quong_soudack1989",
                    citation=mfi_citation,
                    fire_fn=_gate_to_session_phase(
                        partial(
                            _fire_mfi_extreme, period=MFI_PERIOD, overbought=overbought, oversold=oversold
                        ),
                        phase,
                    ),
                    # strength=mfi-overbought (or oversold-mfi) is a MARGIN, zero at the boundary — MFI is a 0-100 oscillator centered at 50, and MFI_THRESHOLD_PAIRS is symmetric, so the same RSI-style reconstruction applies.
                    strength_scale=overbought - 50.0,
                    strength_is_margin=True,
                )
            )

    tod_citation = (
        "Wood, McInish & Ord, 'An Investigation of Transactions Data for NYSE Stocks' "
        "(Journal of Finance, 1985); Harris, 'A Transaction Data Study of Weekly and "
        "Intradaily Patterns in Stock Returns' (Journal of Financial Economics, 1986)"
    )
    for phase in SESSION_PHASES:
        for direction in ("long", "short"):
            specs.append(
                PatternSpec(
                    pattern_id=f"time_of_day_{phase}_{direction}",
                    family="time_of_day_seasonality",
                    citation=tod_citation,
                    fire_fn=_gate_to_session_phase(partial(_fire_session_bias, direction=direction), phase),
                    # strength is a fixed 1.0 — trivial ratio 1.0 always, unchanged flat +-1 sizing.
                    strength_scale=1.0,
                )
            )

    donchian_citation = "Donchian, 'Trend-Following Methods in Commodity Price Analysis', Commodity Year Book (1957)"
    for reverse in (False, True):
        for phase in PHASE_B_GATED_PHASES:
            specs.append(
                PatternSpec(
                    pattern_id=f"prior_day_break_{'fade' if reverse else 'continuation'}_{phase}",
                    family="prior_day_level_donchian1957",
                    citation=donchian_citation,
                    fire_fn=_gate_to_session_phase(
                        partial(_fire_prior_day_level_break, reverse=reverse), phase
                    ),
                )
            )

    pivot_citation = "Person, 'A Complete Guide to Technical Trading Tactics' (Wiley, 2004)"
    for level in PIVOT_LEVELS:
        for phase in PHASE_B_GATED_PHASES:
            specs.append(
                PatternSpec(
                    pattern_id=f"pivot_reversion_r{level}s{level}_{phase}",
                    family="pivot_reversion_person2004",
                    citation=pivot_citation,
                    fire_fn=_gate_to_session_phase(partial(_fire_pivot_reversion, level=level), phase),
                )
            )

    atr_citation = (
        "Wilder, 'New Concepts in Technical Trading Systems' (1978); Crabel, 'Day Trading "
        "with Short Term Price Patterns and Opening Range Breakout' (1990)"
    )
    for reverse in (False, True):
        for atr_mult in ATR_EXPANSION_MULTIPLES:
            for phase in PHASE_B_GATED_PHASES:
                specs.append(
                    PatternSpec(
                        pattern_id=(
                            f"atr_expansion_{'exhaustion' if reverse else 'continuation'}_{atr_mult:.1f}_{phase}"
                        ),
                        family="atr_range_expansion",
                        citation=atr_citation,
                        fire_fn=_gate_to_session_phase(
                            partial(_fire_atr_expansion, atr_mult=atr_mult, reverse=reverse), phase
                        ),
                        # strength=last_tr/atr, fires when last_tr/atr >= atr_mult — raw value directly comparable to atr_mult, ratio==1.0 at the boundary (no reconstruction needed, unlike Keltner: nothing was subtracted here).
                        strength_scale=atr_mult,
                    )
                )

    streak_citation = (
        "Lehmann, 'Fads, Martingales, and Market Efficiency' (Quarterly Journal of Economics, "
        "1990); Jegadeesh & Titman, 'Returns to Buying Winners and Selling Losers' (Journal of "
        "Finance, 1993)"
    )
    for reverse in (False, True):
        for streak_len in STREAK_LENGTHS:
            for phase in PHASE_B_GATED_PHASES:
                specs.append(
                    PatternSpec(
                        pattern_id=(
                            f"streak_{'reversal' if reverse else 'continuation'}_{streak_len}_{phase}"
                        ),
                        family="close_streak_lehmann1990",
                        citation=streak_citation,
                        fire_fn=_gate_to_session_phase(
                            partial(_fire_close_streak, streak_len=streak_len, reverse=reverse), phase
                        ),
                        # strength=float(streak_len) is always exactly this spec's own configured streak_len (a constant, not a per-bar magnitude) — strength_scale=streak_len makes the ratio trivially 1.0 always, unchanged flat +-1 sizing (there is no real magnitude here to size by).
                        strength_scale=float(streak_len),
                    )
                )

    obv_citation = "Granville, 'Granville's New Key to Stock Market Profits' (Prentice-Hall, 1963)"
    for lookback in OBV_DIVERGENCE_LOOKBACKS:
        for phase in PHASE_B_GATED_PHASES:
            specs.append(
                PatternSpec(
                    pattern_id=f"obv_divergence_{lookback}_{phase}",
                    family="obv_divergence_granville1963",
                    citation=obv_citation,
                    fire_fn=_gate_to_session_phase(partial(_fire_obv_divergence, lookback=lookback), phase),
                    # strength is a fixed 1.0 — trivial ratio 1.0 always, unchanged flat +-1 sizing.
                    strength_scale=1.0,
                )
            )

    connors_citation = "Connors & Alvarez, 'Short Term Trading Strategies That Work' (TradingMarkets, 2008)"
    for period in CONNORS_RSI_PERIODS:
        for overbought, oversold in CONNORS_RSI_THRESHOLD_PAIRS:
            for phase in PHASE_B_GATED_PHASES:
                specs.append(
                    PatternSpec(
                        pattern_id=f"connors_rsi_{period}_{overbought:.0f}_{oversold:.0f}_{phase}",
                        family="connors_rsi2008",
                        citation=connors_citation,
                        fire_fn=_gate_to_session_phase(
                            partial(_fire_rsi_extreme, period=period, overbought=overbought, oversold=oversold),
                            phase,
                        ),
                        # Reuses _fire_rsi_extreme — same MARGIN reconstruction as Family 5's RSI above (CONNORS_RSI_THRESHOLD_PAIRS is also symmetric around 50).
                        strength_scale=overbought - 50.0,
                        strength_is_margin=True,
                    )
                )

    bollinger_citation = "Bollinger, John, 'Bollinger on Bollinger Bands' (McGraw-Hill, 2001)"
    for n_std in BOLLINGER_STD_MULTIPLES:
        for phase in PHASE_B_GATED_PHASES:
            specs.append(
                PatternSpec(
                    pattern_id=f"bollinger_reversion_{BOLLINGER_CANONICAL_PERIOD}_{n_std:.1f}_{phase}",
                    family="bollinger_reversion",
                    citation=bollinger_citation,
                    fire_fn=_gate_to_session_phase(
                        partial(_fire_bollinger_reversion, period=BOLLINGER_CANONICAL_PERIOD, n_std=n_std),
                        phase,
                    ),
                    # Same MARGIN reconstruction as Family 6's Bollinger above.
                    strength_scale=n_std,
                    strength_is_margin=True,
                )
            )

    ma_citation = (
        "Brock, Lakonishok & LeBaron, 'Simple Technical Trading Rules and the Stochastic "
        "Properties of Stock Returns' (Journal of Finance, 1992)"
    )
    for short_period, long_period in MA_CROSSOVER_PAIRS_15MIN:
        specs.append(
            PatternSpec(
                pattern_id=f"ma_crossover_{short_period}_{long_period}",
                family="ma_crossover_brock1992",
                citation=ma_citation,
                fire_fn=partial(_fire_ma_crossover, short_period=short_period, long_period=long_period),
            )
        )

    gao_citation = "Gao, Han, Xie & Yang, 'Market Intraday Momentum' (Journal of Financial Economics, 2018)"
    for reverse in (False, True):
        for threshold in GAO_FIRST_HALF_HOUR_THRESHOLDS:
            for phase in GAO_MOMENTUM_PHASES:
                specs.append(
                    PatternSpec(
                        pattern_id=(
                            f"gao_first_half_hour_{'reversal' if reverse else 'continuation'}_{phase}_{threshold:.4f}"
                        ),
                        family="intraday_momentum_gao2018",
                        citation=gao_citation,
                        fire_fn=_gate_to_session_phase(
                            partial(_fire_gao_first_half_hour, reverse=reverse, min_open_return=threshold),
                            phase,
                        ),
                        # strength=abs(open_return), fires when abs(open_return) >= min_open_return — raw value, ratio==1.0 at the boundary.
                        strength_scale=threshold,
                    )
                )

    return specs


# --- 1-minute-native families -------------------------------------------
# These only make sense at true minute granularity: literal half-hour
# windows from minute bars, minute-scale indicator lookbacks, and Crabel's
# actual N-MINUTE opening ranges. Gating uses minute-of-day windows
# (_gate_to_minute_window), not fraction-of-day session phases — at 390
# bars/day the "open" phase is a single minute, far narrower than any of
# the cited papers' own definitions.

VWAP_1MIN_DEVIATION_THRESHOLDS = (0.001, 0.002, 0.003, 0.005)
# Morning (10:00-12:00) and afternoon (12:00-15:30) firing windows —
# after enough bars exist for a meaningful session VWAP, before the final
# half-hour (whose bars belong to the Gao family's window below).
VWAP_1MIN_WINDOWS: tuple[tuple[str, int, int], ...] = (("morning", 600, 720), ("afternoon", 720, 930))

GAO_1MIN_THRESHOLDS = (0.001, 0.0025, 0.004)
# The literal paper: first-half-hour return -> last-half-hour return.
# Observed-bar gate [15:29, 15:59) trades exactly the 15:30-16:00 bars.
GAO_1MIN_FIRST_HALF_HOUR_END = 600  # bars starting before 10:00
GAO_1MIN_FIRE_START = 929
GAO_1MIN_FIRE_END = 959

RSI_1MIN_PERIODS = (5, 14, 30)
RSI_1MIN_THRESHOLD_PAIRS: tuple[tuple[float, float], ...] = ((70.0, 30.0), (80.0, 20.0))
CONNORS_RSI_1MIN_THRESHOLD_PAIRS: tuple[tuple[float, float], ...] = ((95.0, 5.0), (90.0, 10.0))

BOLLINGER_1MIN_PERIODS = (20, 60)
BOLLINGER_1MIN_STD_MULTIPLES = (2.0, 2.5)

MA_CROSSOVER_PAIRS_1MIN: tuple[tuple[int, int], ...] = ((5, 20), (10, 50), (20, 100), (50, 200))

VOLUME_CLIMAX_1MIN_MULTIPLES = (5.0, 10.0)

ORB_1MIN_RANGE_MINUTES = (5, 15, 30)
ORB_1MIN_BUFFERS = (0.0, 0.001)
ORB_1MIN_FIRE_END = 720  # breakouts tradeable through noon

HKS_SLOT_MINUTES = 30
HKS_THRESHOLDS = (0.001, 0.002)


def _fire_gao_minute_momentum(window: pd.DataFrame, *, reverse: bool, min_open_return: float) -> PatternSignal | None:
    """Gao et al. (2018)'s literal predictor from minute bars: the current
    day's 09:30-10:00 return. The [15:29, 15:59) firing gate is applied by
    the caller via _gate_to_minute_window."""
    bar = window.iloc[-1]
    trading_date = bar["trading_date"]
    day_rows = window[window["trading_date"] == trading_date]
    if day_rows.empty:
        return None
    minutes = day_rows.index.hour * 60 + day_rows.index.minute
    first_half_hour = day_rows[minutes < GAO_1MIN_FIRST_HALF_HOUR_END]
    # Require a genuinely complete first half-hour (>=25 of 30 minutes,
    # starting at the true open) — an honest skip for late opens/halts.
    if len(first_half_hour) < 25 or (minutes.min() if len(minutes) else 9999) > SESSION_OPEN_MINUTE:
        return None
    open_price = float(first_half_hour.iloc[0]["open"])
    if open_price <= 0:
        return None
    open_return = (float(first_half_hour.iloc[-1]["close"]) - open_price) / open_price
    if not np.isfinite(open_return) or abs(open_return) < min_open_return:
        return None
    sign = -1.0 if reverse else 1.0
    predicted = open_return * sign
    return PatternSignal(direction="long" if predicted > 0 else "short", strength=abs(open_return))


def _fire_orb_range_break(window: pd.DataFrame, *, range_minutes: int, buffer: float) -> PatternSignal | None:
    """Crabel (1990)'s actual opening-range breakout: the high/low of the
    day's first N MINUTES defines the range; a later close beyond the
    range (plus an optional buffer) signals continuation in the breakout
    direction. Only expressible at minute granularity."""
    bar = window.iloc[-1]
    trading_date = bar["trading_date"]
    day_rows = window[window["trading_date"] == trading_date]
    if day_rows.empty:
        return None
    minutes = day_rows.index.hour * 60 + day_rows.index.minute
    range_end = SESSION_OPEN_MINUTE + range_minutes
    range_rows = day_rows[minutes < range_end]
    # The range must be complete (mostly-full bar coverage from the true
    # open) and the current bar must be past it.
    if len(range_rows) < int(range_minutes * 0.8) or (minutes.min() if len(minutes) else 9999) > SESSION_OPEN_MINUTE:
        return None
    if _minute_of_day(window) < range_end:
        return None
    range_high = float(range_rows["high"].max())
    range_low = float(range_rows["low"].min())
    last_close = float(bar["close"])
    if last_close > range_high * (1.0 + buffer):
        return PatternSignal(direction="long", strength=(last_close - range_high) / range_high)
    if last_close < range_low * (1.0 - buffer):
        return PatternSignal(direction="short", strength=(range_low - last_close) / range_low)
    return None


def _fire_same_slot_persistence(window: pd.DataFrame, *, reverse: bool, min_return: float) -> PatternSignal | None:
    """Heston, Korajczyk & Sadka, 'Intraday Patterns in the Cross-Section
    of Stock Returns' (Journal of Finance, 2010): returns earned in a
    given half-hour-of-day interval persist at daily lags — the PRIOR
    day's return in the SAME half-hour slot predicts this slot's return,
    same direction. `reverse` tests the opposite reading co-equally."""
    bar = window.iloc[-1]
    current_date = bar["trading_date"]
    minute = _minute_of_day(window)
    if minute < SESSION_OPEN_MINUTE or minute >= SESSION_CLOSE_MINUTE:
        return None
    slot = (minute - SESSION_OPEN_MINUTE) // HKS_SLOT_MINUTES
    prior_rows = window[window["trading_date"] < current_date]
    if prior_rows.empty:
        return None
    prior_date = prior_rows["trading_date"].max()
    prior_day = prior_rows[prior_rows["trading_date"] == prior_date]
    prior_minutes = prior_day.index.hour * 60 + prior_day.index.minute
    slot_mask = (prior_minutes - SESSION_OPEN_MINUTE) // HKS_SLOT_MINUTES == slot
    slot_rows = prior_day[slot_mask]
    if len(slot_rows) < int(HKS_SLOT_MINUTES * 0.8):
        return None
    open_price = float(slot_rows.iloc[0]["open"])
    if open_price <= 0:
        return None
    slot_return = (float(slot_rows.iloc[-1]["close"]) - open_price) / open_price
    if not np.isfinite(slot_return) or abs(slot_return) < min_return:
        return None
    sign = -1.0 if reverse else 1.0
    predicted = slot_return * sign
    return PatternSignal(direction="long" if predicted > 0 else "short", strength=abs(slot_return))


def _build_phase_b_1min_family() -> list[PatternSpec]:
    """The 1-minute-native subfamily. Every pattern_id carries an m1_
    prefix so ids stay globally unique across the whole Phase B search."""
    specs: list[PatternSpec] = []

    vwap_citation = "Madhavan, 'VWAP Strategies' (Journal of Portfolio Management, 2002)"
    for window_name, start_minute, end_minute in VWAP_1MIN_WINDOWS:
        for threshold in VWAP_1MIN_DEVIATION_THRESHOLDS:
            for price_convention in VWAP_PRICE_CONVENTIONS:
                specs.append(
                    PatternSpec(
                        pattern_id=f"m1_vwap_reversion_{price_convention}_{window_name}_{threshold:.3f}",
                        family="vwap_reversion",
                        citation=vwap_citation,
                        fire_fn=_gate_to_minute_window(
                            partial(
                                _fire_vwap_reversion,
                                deviation_threshold=threshold,
                                price_convention=price_convention,
                            ),
                            start_minute,
                            end_minute,
                        ),
                        # Same raw-value scaling as Family 3's VWAP above.
                        strength_scale=threshold,
                    )
                )

    gao_citation = "Gao, Han, Xie & Yang, 'Market Intraday Momentum' (Journal of Financial Economics, 2018)"
    for reverse in (False, True):
        for threshold in GAO_1MIN_THRESHOLDS:
            specs.append(
                PatternSpec(
                    pattern_id=(
                        f"m1_gao_half_hour_{'reversal' if reverse else 'continuation'}_{threshold:.4f}"
                    ),
                    family="intraday_momentum_gao2018",
                    citation=gao_citation,
                    fire_fn=_gate_to_minute_window(
                        partial(_fire_gao_minute_momentum, reverse=reverse, min_open_return=threshold),
                        GAO_1MIN_FIRE_START,
                        GAO_1MIN_FIRE_END,
                    ),
                    # strength=abs(open_return), fires when abs(open_return) >= min_open_return — raw value, ratio==1.0 at the boundary.
                    strength_scale=threshold,
                )
            )

    rsi_citation = "Wilder, J. Welles, 'New Concepts in Technical Trading Systems' (1978)"
    for period in RSI_1MIN_PERIODS:
        for overbought, oversold in RSI_1MIN_THRESHOLD_PAIRS:
            specs.append(
                PatternSpec(
                    pattern_id=f"m1_rsi_extreme_{period}_{overbought:.0f}_{oversold:.0f}",
                    family="rsi_extreme_wilder1978",
                    citation=rsi_citation,
                    fire_fn=partial(_fire_rsi_extreme, period=period, overbought=overbought, oversold=oversold),
                    # Same MARGIN reconstruction as Family 5's RSI above (RSI_1MIN_THRESHOLD_PAIRS is also symmetric around 50).
                    strength_scale=overbought - 50.0,
                    strength_is_margin=True,
                )
            )

    connors_citation = "Connors & Alvarez, 'Short Term Trading Strategies That Work' (TradingMarkets, 2008)"
    for overbought, oversold in CONNORS_RSI_1MIN_THRESHOLD_PAIRS:
        specs.append(
            PatternSpec(
                pattern_id=f"m1_connors_rsi_2_{overbought:.0f}_{oversold:.0f}",
                family="connors_rsi2008",
                citation=connors_citation,
                fire_fn=partial(_fire_rsi_extreme, period=2, overbought=overbought, oversold=oversold),
                # Same MARGIN reconstruction as Family 5's RSI above (CONNORS_RSI_1MIN_THRESHOLD_PAIRS is also symmetric around 50).
                strength_scale=overbought - 50.0,
                strength_is_margin=True,
            )
        )

    bollinger_citation = "Bollinger, John, 'Bollinger on Bollinger Bands' (McGraw-Hill, 2001)"
    for period in BOLLINGER_1MIN_PERIODS:
        for n_std in BOLLINGER_1MIN_STD_MULTIPLES:
            specs.append(
                PatternSpec(
                    pattern_id=f"m1_bollinger_reversion_{period}_{n_std:.1f}",
                    family="bollinger_reversion",
                    citation=bollinger_citation,
                    fire_fn=partial(_fire_bollinger_reversion, period=period, n_std=n_std),
                    # Same MARGIN reconstruction as Family 6's Bollinger above.
                    strength_scale=n_std,
                    strength_is_margin=True,
                )
            )

    ma_citation = (
        "Brock, Lakonishok & LeBaron, 'Simple Technical Trading Rules and the Stochastic "
        "Properties of Stock Returns' (Journal of Finance, 1992)"
    )
    for short_period, long_period in MA_CROSSOVER_PAIRS_1MIN:
        specs.append(
            PatternSpec(
                pattern_id=f"m1_ma_crossover_{short_period}_{long_period}",
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
        for multiple in VOLUME_CLIMAX_1MIN_MULTIPLES:
            specs.append(
                PatternSpec(
                    pattern_id=f"m1_volume_{'climax' if reverse else 'confirmation'}_{multiple:.0f}x",
                    family="volume_price_divergence",
                    citation=volume_citation,
                    fire_fn=partial(_fire_volume_climax, reverse=reverse, volume_multiple=multiple),
                )
            )

    orb_citation = "Crabel, 'Day Trading with Short Term Price Patterns and Opening Range Breakout' (1990)"
    for range_minutes in ORB_1MIN_RANGE_MINUTES:
        for buffer in ORB_1MIN_BUFFERS:
            specs.append(
                PatternSpec(
                    pattern_id=f"m1_orb_range_break_{range_minutes}min_{buffer:.3f}",
                    family="opening_range_breakout",
                    citation=orb_citation,
                    fire_fn=_gate_to_minute_window(
                        partial(_fire_orb_range_break, range_minutes=range_minutes, buffer=buffer),
                        SESSION_OPEN_MINUTE + range_minutes,
                        ORB_1MIN_FIRE_END,
                    ),
                    # strength=(close-range_edge)/range_edge, fires when that exceeds `buffer` — raw value, ratio==1.0 at the boundary. ORB_1MIN_BUFFERS includes 0.0 (no minimum-excess requirement at all); _signal_weight_magnitude's own strength_scale<=0 guard falls back to the flat +-1 bet for that case rather than dividing by zero.
                    strength_scale=buffer,
                )
            )

    hks_citation = (
        "Heston, Korajczyk & Sadka, 'Intraday Patterns in the Cross-Section of Stock "
        "Returns' (Journal of Finance, 2010)"
    )
    for reverse in (False, True):
        for threshold in HKS_THRESHOLDS:
            specs.append(
                PatternSpec(
                    pattern_id=(
                        f"m1_same_slot_{'reversal' if reverse else 'persistence'}_{threshold:.3f}"
                    ),
                    family="same_slot_persistence_hks2010",
                    citation=hks_citation,
                    fire_fn=partial(_fire_same_slot_persistence, reverse=reverse, min_return=threshold),
                    # strength=abs(slot_return), fires when abs(slot_return) >= min_return — raw value, ratio==1.0 at the boundary.
                    strength_scale=threshold,
                )
            )

    return specs


PHASE_B_ADDITIONS_15MIN: list[PatternSpec] = _build_phase_b_15min_additions()
PATTERN_FAMILY_PHASE_B_15MIN: list[PatternSpec] = PATTERN_FAMILY + PHASE_B_ADDITIONS_15MIN
PATTERN_FAMILY_PHASE_B_1MIN: list[PatternSpec] = _build_phase_b_1min_family()

# The single, pre-declared Phase B trial denominator: every definition
# tested at 15-minute granularity (the base 212 re-tested at the finer
# granularity — each a distinct trial from its hourly Phase A run — plus
# the 15-minute-native additions) AND every 1-minute-native definition.
# One search, one denominator, no exceptions.
PHASE_B_TOTAL_TRIALS = len(PATTERN_FAMILY_PHASE_B_15MIN) + len(PATTERN_FAMILY_PHASE_B_1MIN)

# Result of the completed Phase B live run (2026-08-26, all 420 included
# patterns run to completion, no early stopping, same discipline as Phase
# A's own result above): honestly negative, and more decisively so than
# Phase A. positive pooled Sharpe: 0 of 420 — not one definition, at any
# granularity, cleared even a raw-Sharpe-positive bar before any DSR
# correction is applied. The best-ranked pattern by raw Sharpe was still
# negative (day_of_week_monday_long, -0.033 annualized, psr0 46.9%, 284/284
# formations fired) and every deflated Sharpe in the family was 0.000e+00.
# Same cost-dominated-noise signature as both prior rounds: every
# day-of-week long/short pair lands in the same -0.03..-1.6 range
# regardless of direction, and the shortest-hold reversion/exhaustion
# patterns (Bollinger, CCI, ATR-expansion) cluster at the most negative end
# — exactly the reformation-cost drag this project's cross-sectional work
# later confirmed as a general pattern, not specific to intraday bars. Full
# ranked report: session record, 420/420 trials accounted for, zero
# omitted regardless of rank.


# --- Phase B universe ---------------------------------------------------
# Every ticker below was empirically verified live on 2026-08-26 (script:
# a real Alpaca daily-bars fetch 2021-01-04..2026-08-24, a real Alpaca
# 15-minute-bars probe over 2021-01-04..2021-01-15, and a live yfinance
# market-cap query per ticker — no name accepted from memory or from any
# list without passing all checks) against four criteria:
#   (1) full Alpaca history: first daily bar on/before 2021-01-08, >=97%
#       of the window's 1,416 trading days present;
#   (2) still active: last daily bar on/after 2026-08-14;
#   (3) liquidity: trailing-252-day average dollar volume >= $5M/day (the
#       floor INTRADAY_COST_BPS's 5bps single-leg assumption needs);
#   (4) real 15-minute bars available at the START of the window (>=200
#       of the ~260 expected bars over the first two weeks of 2021).
# Buckets by verified market cap: large >= $10B, mid $2-10B, small
# $300M-2B (same boundaries as the Phase A mid/small verification).
# WITHIN each verified bucket, selection was mechanical and pre-declared:
# rank by trailing-252-day dollar volume, take the top 150 large / top 90
# mid / all 44 passing small — a pure liquidity rule fixed before any
# backtest ran, so universe membership cannot encode return information.
# 59 candidates failed verification for disclosed reasons (post-2021
# IPOs like CAVA/RDDT/GEV, delisted/acquired names like GPS/FL/AZEK/RUTH,
# dollar volume below $5M like ZUMZ/LOCO, caps below $300M like
# NDLS/PLCE/RRGB) — recorded in the verification run's output, not
# silently dropped. Verified cap ranges: large $13.4B-$5.16T, mid
# $2.0B-$10.0B (min dollar vol $59M), small $320M-$2.0B (min $5.9M).
#
# Survivorship bias disclosure, same register as Phase A's: this universe
# is verified AS OF 2026-08-26 and applied backward over 2021-2026, so
# names that delisted mid-window can never appear — the already-logged
# "delisted-securities data vendor" decision is the eventual fix, not
# something this free-data phase can close.
PHASE_B_UNIVERSE_LARGE_CAP: list[str] = [
    "NVDA", "TSLA", "MU", "MSFT", "AAPL", "AMD", "AMZN", "META", "GOOGL", "AVGO",
    "INTC", "PLTR", "GOOG", "ORCL", "MRVL", "NFLX", "LLY", "LITE", "AMAT", "JPM",
    "UNH", "WDC", "WMT", "LRCX", "V", "XOM", "CRM", "QCOM", "BRK-B", "STX",
    "COST", "NOW", "CAT", "CSCO", "BAC", "GS", "JNJ", "IBM", "MA", "TXN",
    "KLAC", "DELL", "CVX", "PANW", "CRWD", "BA", "VRT", "GLW", "GE", "UBER",
    "C", "HD", "ADBE", "INTU", "COHR", "ABBV", "BKNG", "PG", "SMCI", "WFC",
    "ADI", "KO", "MRK", "ANET", "APH", "ACN", "PFE", "T", "VZ", "CVNA",
    "LIN", "PEP", "TMO", "MS", "TMUS", "ISRG", "DIS", "MCD", "NKE", "BSX",
    "ABT", "TER", "AXP", "SNPS", "RTX", "ETN", "NEM", "FCX", "SCHW", "PYPL",
    "CIEN", "PM", "DASH", "COF", "GILD", "AMGN", "NEE", "SPGI", "DDOG", "DHR",
    "CMCSA", "F", "MPWR", "COP", "UNP", "TJX", "SBUX", "VST", "NXPI", "LMT",
    "BLK", "DE", "ON", "HPE", "SLB", "MCHP", "MDT", "WDAY", "CDNS", "BX",
    "AZO", "MCK", "BMY", "SYK", "RCL", "CMG", "LOW", "TGT", "PGR", "VLO",
    "CVS", "SHW", "WELL", "VRTX", "ECHO", "CCL", "MRNA", "ADP", "CME", "FIX",
    "REGN", "UAL", "LULU", "PWR", "UPS", "GM", "CRH", "FTNT", "PH", "OXY",
]

PHASE_B_UNIVERSE_MID_CAP: list[str] = [
    "HIMS", "TTD", "NCLH", "CELH", "CAR", "RMBS", "SWKS", "ETSY", "PODD", "BLDR",
    "WING", "SFM", "ELF", "MOS", "SAIA", "VIAV", "AGX", "APTV", "ALK", "FND",
    "ANF", "PRIM", "M", "OLLI", "FORM", "PLNT", "CROX", "TAP", "SHAK", "AEO",
    "PBF", "ARE", "FNB", "URBN", "BRKR", "BOOT", "SM", "ESI", "DBX", "OSK",
    "PTCT", "BTU", "VLY", "PCTY", "WAL", "AOS", "EXP", "ALGM", "MTDR", "KEX",
    "LNTH", "CAKE", "TREX", "FRPT", "SITE", "GVA", "AGCO", "ITRI", "ONB", "CRUS",
    "KSS", "CALM", "SLAB", "MYRG", "TEX", "R", "PVH", "CMC", "MIDD", "SIG",
    "OLED", "IRTC", "QLYS", "PB", "TTC", "MUR", "ACLS", "ROAD", "SYNA", "HCC",
    "UCTT", "YETI", "APPF", "BOX", "TENB", "MSM", "BMI", "NOVT", "CBSH", "PLXS",
]

PHASE_B_UNIVERSE_SMALL_CAP: list[str] = [
    "JBLU", "BRBR", "WEN", "SRPT", "OLN", "HUN", "CPRI", "CBRL", "FLO", "PZZA",
    "BL", "EYE", "TDOC", "REAL", "PRGO", "SMPL", "PGNY", "QDEL", "GO", "WWW",
    "RVLV", "OMCL", "PLAY", "AZTA", "JJSF", "BJRI", "GBX", "KRUS", "RPD", "BLMN",
    "JACK", "EPAC", "OXM", "TNC", "DIN", "CTS", "NTGR", "AMPH", "HOPE", "WMK",
    "MRTN", "ARCO", "HTLD", "NGVC",
]

PHASE_B_UNIVERSE_15MIN: list[str] = (
    PHASE_B_UNIVERSE_LARGE_CAP + PHASE_B_UNIVERSE_MID_CAP + PHASE_B_UNIVERSE_SMALL_CAP
)

# The 1-minute basket: the SAME mechanical liquidity rule applied deeper
# — top 30 large / top 20 mid / top 10 small of the verified,
# liquidity-ranked buckets above. 1-minute bars cost ~10x the compute and
# ~10x the fetch of 15-minute bars per ticker-year, so this group buys its
# depth-per-ticker (every minute since 2023) by carrying fewer tickers —
# a pre-declared size/depth tradeoff, not a post-hoc selection.
PHASE_B_UNIVERSE_1MIN: list[str] = (
    PHASE_B_UNIVERSE_LARGE_CAP[:30] + PHASE_B_UNIVERSE_MID_CAP[:20] + PHASE_B_UNIVERSE_SMALL_CAP[:10]
)


def _signal_weight_magnitude(signal: PatternSignal, pattern: PatternSpec) -> float:
    """The magnitude side of position sizing — see the module-level note
    above PatternSpec for the full formula and per-family rationale.
    Direction/entry/exit TIMING (via z_score in _make_fit_fn below) is
    completely unaffected by this function; it only ever scales how big a
    +-1-direction bet is, never whether or when one is placed — that is
    what makes this a sizing refinement of the existing bet, not a new
    strategy.

    Worked derivation for strength_is_margin=True (the non-obvious case):
    take RSI, overbought=70. strength = rsi - 70 (Wilder's own margin past
    the level, zero exactly when rsi==70). RSI's neutral center is 50 by
    construction (a 0-100 oscillator) and this family's threshold pairs
    are always symmetric around it (70/30, 75/25, 80/20, ...), so
    strength_scale is set to overbought-50=20 at spec-build time. Then:

        magnitude = strength + strength_scale = (rsi - 70) + 20 = rsi - 50

    — exactly the live distance from RSI's own neutral center, with no new
    information invented. At rsi==70 (the firing boundary), magnitude=20,
    so magnitude/strength_scale == 20/20 == 1.0 — the same ratio the
    non-margin case gets "for free" (e.g. VWAP: strength IS abs(deviation),
    already directly comparable to deviation_threshold, so no
    reconstruction is needed there). Every strength_is_margin=True family
    actually used in this module (RSI/Connors-RSI, stochastic, MFI: all
    symmetric 0-100 oscillators around 50; Bollinger, Keltner: already
    centered at a 0-std/0-ATR mean by construction, strength_scale=n_std/
    atr_mult; CCI: already centered at 0 via its own abs(), strength_scale
    =level) satisfies this same algebraic identity — see each family's
    strength_scale assignment in the _build_*family functions below."""
    if pattern.strength_scale is None or pattern.strength_scale <= 0:
        return 1.0  # no natural scale to normalize against — flat +-1 bet, unchanged from before this scheme
    magnitude = signal.strength + pattern.strength_scale if pattern.strength_is_margin else signal.strength
    ratio = magnitude / pattern.strength_scale
    return float(np.clip(ratio, 0.0, MAX_WEIGHT_MULTIPLE))


def _make_fit_fn(pattern: PatternSpec) -> Callable[[pd.DataFrame], StrategyFit]:
    """Adapts a pattern's fire_fn to engine.py's generic StrategyFit shape.
    z_score is used purely as a sign carrier (+1.0 long / -1.0 short) for
    apply_pattern_signal_rule below — patterns are fire-or-don't-fire, not
    a continuous statistic to compare against an entry/exit band, so no
    z_score magnitude is meaningful here and entry_z/exit_z stay 0.0 (see
    run_pattern_backtest). The signal's actual MAGNITUDE is carried
    separately, through StrategyFit.params["weight_magnitude"] (opaque to
    engine.py by design — see StrategyFit's own field comment) — realize_
    pattern_return below reads it back out to scale the bet's size,
    leaving engine.py's own position bookkeeping (still int +-1/0, still
    driving cost accounting) completely untouched. This is what keeps the
    weighting scheme opt-in per-strategy rather than a change to engine.py
    shared with pairs/momentum, whose positions must stay integer +-1/0
    exactly as before."""

    def fit_fn(window: pd.DataFrame) -> StrategyFit:
        if window.empty:
            return StrategyFit(is_valid=False, z_score=None, fit_quality=None, params={})
        signal = pattern.fire_fn(window)
        if signal is None:
            return StrategyFit(is_valid=False, z_score=None, fit_quality=None, params={})
        z = 1.0 if signal.direction == "long" else -1.0
        weight_magnitude = _signal_weight_magnitude(signal, pattern)
        return StrategyFit(is_valid=True, z_score=z, fit_quality=None, params={"weight_magnitude": weight_magnitude})

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
    """Return per +1 (long) unit of DIRECTION — single-leg intraday bet, no
    hedge ratio. Uses the bar's own open-to-close `ret` (see
    build_pattern_raw_data) — the return actually realizable by entering
    at this bar's open, exactly what a position opened on this step is
    assumed to do — scaled by this step's magnitude-weighted bet size
    (fit.params["weight_magnitude"], set in _make_fit_fn; defaults to 1.0
    — today's flat bet — for any caller that never sets it, e.g. a
    synthetic PatternSpec built directly in a test with strength_scale
    left at its default None). engine.py's own `new_position * return_fn(
    ...)` (see step_one_day) then applies the +-1 DIRECTION on top of this
    already-magnitude-scaled return, so the final realized bet is
    direction * weight_magnitude * ret — never direction alone."""
    weight_magnitude = fit.params.get("weight_magnitude", 1.0) if fit is not None else 1.0
    return weight_magnitude * float(day_row["ret"])


def run_pattern_backtest(
    pattern: PatternSpec,
    raw_data: pd.DataFrame,
    fit_window_bars: int = INTRADAY_FIT_WINDOW_BARS,
    cost_bps: float = INTRADAY_COST_BPS,
) -> ExperimentResult:
    """Runs the SAME engine.py walk-forward machinery (step_one_day via
    run_walk_forward, completely unmodified) directly against hourly-bar-
    indexed raw_data. Verified empirically, not just assumed from reading
    the source: engine.py's loop only ever does positional `.iloc` slicing
    and DayResult.date is typed pd.Timestamp (not datetime.date), so a
    tz-aware intraday DatetimeIndex round-trips through it exactly like a
    daily DatetimeIndex does — see test_intraday_patterns.py's
    test_run_pattern_backtest_accepts_hourly_indexed_raw_data and this
    module's real screening run against live yfinance hourly data.

    fit_window_bars defaults to Phase A's hourly sizing; Phase B passes
    FIT_WINDOW_BARS_15MIN / FIT_WINDOW_BARS_1MIN (see those constants for
    the per-granularity sizing reasoning).

    cost_bps (added 2026-08-28) defaults to INTRADAY_COST_BPS — the flat
    5bps single-leg assumption every prior Phase A/B run used, so every
    existing caller is byte-for-byte unaffected. Passing a different value
    is how the EDGE-spread cost re-audit charges each ticker its OWN
    estimated half-spread instead of one flat number for the whole
    universe (see screen_pattern_universe's cost_bps_by_ticker): because
    every intraday backtest is single-ticker, a per-ticker rate threads
    through this one existing engine.py knob without touching engine.py's
    shared cost arithmetic at all. What this canNOT express is a cost that
    varies DAY BY DAY within one ticker's replay — engine.py charges one
    flat rate per unit of position change for the whole run — so the
    re-audit's per-ticker rate is a time-constant summary (its median
    trailing EDGE half-spread), a disclosed limitation of this wiring, not
    of the estimator."""
    config = WalkForwardConfig(
        fit_window_days=fit_window_bars, entry_z=0.0, exit_z=0.0, cost_bps=cost_bps
    )
    return run_walk_forward(
        raw_data,
        config,
        _make_fit_fn(pattern),
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
    timeframe: str = "60m"  # which bar granularity this pattern was screened at (Phase A's hourly default; Phase B stamps "15m"/"1m")


@dataclass
class TickerPatternStats:
    """One (ticker, pattern) backtest, reduced to exactly what pooling
    needs — small and picklable, so Phase B's long parallel screen can
    ship per-ticker results across process boundaries instead of holding
    hundreds of full ExperimentResults (whose per-BAR day_results lists
    dwarf everything else) in memory at once."""

    daily_returns: pd.Series
    n_trades: int  # all trades, including a final still-open one
    n_closed_trades: int
    n_winning_trades: int  # closed trades with trade_return > 0 (hit_rate's own definition)
    fired: bool


def backtest_patterns_for_ticker(
    bars: pd.DataFrame,
    patterns: list[PatternSpec],
    fit_window_bars: int = INTRADAY_FIT_WINDOW_BARS,
    cost_bps: float = INTRADAY_COST_BPS,
) -> dict[str, TickerPatternStats]:
    """Runs EVERY pattern in `patterns` against ONE ticker's bars — the
    per-ticker unit of work both screen_pattern_universe (in-process) and
    Phase B's parallel runner (one ticker per worker task) share, so the
    two paths cannot drift apart. Returns {} for a ticker whose history is
    too short to fit even one walk-forward window.

    cost_bps threads straight through to run_pattern_backtest (see its
    docstring): defaults to the flat INTRADAY_COST_BPS every prior run
    used, so existing callers are unaffected; the EDGE cost re-audit
    passes this ticker's own estimated half-spread instead."""
    if len(bars) <= fit_window_bars:
        return {}
    raw_data = build_pattern_raw_data(bars)
    stats: dict[str, TickerPatternStats] = {}
    for pattern in patterns:
        result = run_pattern_backtest(
            pattern, raw_data, fit_window_bars=fit_window_bars, cost_bps=cost_bps
        )
        daily_returns = daily_returns_from_bar_equity(result.day_results)
        closed = [t for t in result.trades if not t.still_open]
        stats[pattern.pattern_id] = TickerPatternStats(
            daily_returns=daily_returns,
            n_trades=len(result.trades),
            n_closed_trades=len(closed),
            n_winning_trades=sum(1 for t in closed if t.trade_return > 0),
            fired=bool(result.trades),
        )
    return stats


@dataclass
class PatternScreenGroup:
    """One granularity group of a screen: a pattern family evaluated over
    one basket of tickers at one bar granularity. Phase A screens are a
    single group; Phase B is two (15-minute and 1-minute) pooled into ONE
    corrected search by screen_pattern_groups."""

    timeframe: str
    patterns: list[PatternSpec]
    stats_by_ticker: dict[str, dict[str, TickerPatternStats]]


def screen_pattern_universe(
    bars_by_ticker: dict[str, pd.DataFrame],
    patterns: list[PatternSpec] | None = None,
    cost_bps_by_ticker: dict[str, float] | None = None,
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
    family, different pattern".

    cost_bps_by_ticker (added 2026-08-28, for the EDGE-spread cost
    re-audit): an explicit per-ticker one-way cost in bps, replacing the
    flat INTRADAY_COST_BPS for every backtest of that ticker. None (the
    default) charges the flat rate everywhere — byte-for-byte the only
    behavior that existed before, so every prior Phase A/B result is
    unaffected. When the dict IS supplied, it must cover EVERY ticker in
    bars_by_ticker: a missing entry raises rather than silently taking the
    flat rate, because the likeliest cause is a ticker-symbology mismatch
    between the bars fetch and the cost derivation, and a re-audit that
    silently charged half its universe the old flat cost would report
    itself as spread-priced while being nothing of the kind (the same
    loud-over-silent rule as cross_sectional.py's edge_spread checks). A
    caller with tickers that genuinely lack a spread estimate decides the
    fallback ITSELF, explicitly, by putting INTRADAY_COST_BPS in the dict
    for those tickers — an explicit, countable decision at the call site,
    not a hidden default here."""
    family = patterns if patterns is not None else PATTERN_FAMILY
    if cost_bps_by_ticker is not None:
        uncovered = sorted(set(bars_by_ticker) - set(cost_bps_by_ticker))
        if uncovered:
            raise ValueError(
                f"cost_bps_by_ticker is missing {len(uncovered)} ticker(s) present in "
                f"bars_by_ticker ({', '.join(uncovered[:10])}{'...' if len(uncovered) > 10 else ''}) — "
                "supply an explicit per-ticker cost (INTRADAY_COST_BPS for a deliberate flat "
                "fallback) rather than relying on a silent default; see this docstring."
            )
    stats_by_ticker = {
        ticker: backtest_patterns_for_ticker(
            bars,
            family,
            cost_bps=(
                cost_bps_by_ticker[ticker] if cost_bps_by_ticker is not None else INTRADAY_COST_BPS
            ),
        )
        for ticker, bars in bars_by_ticker.items()
    }
    return screen_pattern_groups(
        [PatternScreenGroup(timeframe="60m", patterns=family, stats_by_ticker=stats_by_ticker)],
        n_trials=len(family),
    )


def screen_pattern_groups(
    groups: list[PatternScreenGroup], n_trials: int
) -> list[PatternScreeningResult]:
    """The pooling/correction half of the screen, shared by Phase A's
    single-group path (screen_pattern_universe above) and Phase B's
    two-granularity search. Everything screen_pattern_universe's docstring
    says about pooling and trial counting applies unchanged; the two
    Phase-B-specific decisions are:

    - n_trials is the caller's PRE-DECLARED total across ALL groups
      (PHASE_B_TOTAL_TRIALS for Phase B — every definition at every
      granularity it was planned for), never derived from how many
      patterns happened to survive the fired/min-days gates: shrinking the
      denominator to the surviving subset would be exactly the
      trial-undercounting this whole exercise polices.

    - sigma_SR is the std (ddof=1) of pooled Sharpes across EVERY included
      pattern from EVERY group — the two granularities are one search, so
      they share one sibling-dispersion estimate, exactly as 212 patterns
      within one granularity did in the previous round.

    - POOLED DENOMINATOR (2026-09-04): the caller's pre-declared total is
      raised to the project-wide effectively-independent trial count when that
      is larger. This family's 212 definitions were never the whole search
      either; see global_effective_n.py."""
    n_trials = dsr_n_trials(n_trials)
    included: list[tuple[PatternScreenGroup, PatternSpec, pd.Series, int, int, int, int, int]] = []
    for group in groups:
        spec_by_id = {spec.pattern_id: spec for spec in group.patterns}
        for spec in group.patterns:
            ticker_daily_returns: dict[str, pd.Series] = {}
            n_fired = 0
            n_trades = 0
            n_closed = 0
            n_wins = 0
            for ticker, per_pattern in group.stats_by_ticker.items():
                stats = per_pattern.get(spec.pattern_id)
                if stats is None:
                    continue  # ticker had too little history for even one window
                if not stats.daily_returns.empty:
                    ticker_daily_returns[ticker] = stats.daily_returns
                if stats.fired:
                    n_fired += 1
                n_trades += stats.n_trades
                n_closed += stats.n_closed_trades
                n_wins += stats.n_winning_trades

            if n_fired == 0:
                # Every ticker with enough history produces a daily-return
                # series regardless of whether this pattern ever actually
                # fired for it (a flat 0%-return day is still a valid walk-
                # forward day) — so ticker_daily_returns being non-empty
                # does NOT by itself mean the pattern found any real
                # signal. Gate on n_fired instead: a pattern that literally
                # never fired anywhere in the universe is skipped entirely,
                # not reported as a misleading flat-zero "tested and
                # neutral" row.
                continue

            pooled = pd.concat(ticker_daily_returns, axis=1).mean(axis=1, skipna=True).dropna()
            if len(pooled) < MIN_POOLED_TRADING_DAYS:
                continue

            included.append(
                (group, spec_by_id[spec.pattern_id], pooled, len(ticker_daily_returns), n_fired, n_trades, n_closed, n_wins)
            )

    sharpes = [sharpe_ratio(pooled) for _, _, pooled, *_ in included]
    sigma_sr = float(np.std(sharpes, ddof=1)) if len(sharpes) >= 2 else None

    results: list[PatternScreeningResult] = []
    for (group, spec, pooled, n_in_basket, n_fired, n_trades, n_closed, n_wins), sharpe in zip(
        included, sharpes, strict=True
    ):
        dsr = compute_deflated_sharpe(sharpe, pooled, n_trials, sigma_sr)
        results.append(
            PatternScreeningResult(
                pattern_id=spec.pattern_id,
                family=spec.family,
                citation=spec.citation,
                n_tickers_in_basket=n_in_basket,
                n_tickers_fired=n_fired,
                n_trading_days=len(pooled),
                n_trades=n_trades,
                sharpe_annualized=sharpe,
                hit_rate=(n_wins / n_closed) if n_closed else None,
                deflated_sharpe=dsr,
                timeframe=group.timeframe,
            )
        )

    results.sort(key=lambda r: r.sharpe_annualized, reverse=True)
    return results
