"""Phase C: a small, pre-specified, structurally LOW-FREQUENCY pattern
family (28 definitions, hard ceiling 40) screened against the existing
walk-forward engine and DSR multiple-comparisons correction.

Why this round exists, stated honestly: three prior rounds (29 patterns on
large-caps, 29 on mid/small-caps, 212 pooled — see intraday_patterns.py)
came back cleanly negative, and the much larger Phase B round exposed a
structural problem with that family design: mixing many high-frequency,
cost-dominated patterns into one family inflates the spread of results
across patterns (sigma_SR ~2.9 annualized measured directly on the 212
family's own run), which pushes deflated_sharpe.py's noise benchmark SR0 to
~8-9.5 annualized at n_trials~200-400 — a bar no real strategy could ever
clear (Medallion's own reported long-run Sharpe is ~2-3). A family like
that is structurally incapable of confirming OR denying an edge.

The fix, and this module's core design principle: every pattern here is
included because of a STRUCTURAL, A-PRIORI reason to expect low trading
frequency and therefore low transaction-cost drag — multi-sigma extreme
events instead of common 1-sigma crossings, monthly/holiday calendar
seasonality instead of every-bar reactions, multi-day holding periods
instead of same-session exits, and explicit refractory gates that hard-cap
firing at roughly once or twice a month per ticker. Patterns were chosen
from first principles and the cited literature BEFORE any backtest of this
family was run, and explicitly NOT by looking at per-pattern performance
from the 29/29/212/Phase-B rounds and keeping what scored well — that
would reintroduce exactly the data-snooping problem this redesign exists
to avoid. (The ONLY quantity measured before committing to the full run is
each pattern's trade FREQUENCY — a performance-blind diagnostic computed
from fire sequences alone, never from returns — to verify the design
actually achieved lower frequency; see estimate_trades_per_ticker_year.)

The cost-drag arithmetic that motivates the frequency ceiling: a round
trip costs ~2 x INTRADAY_COST_BPS = ~10bps. The prior families' 1-bar
holds firing up to every bar produced hundreds of round trips per
ticker-year (25-60%+ annual drag — guaranteed deeply-negative Sharpe for
any pattern without an enormous true edge, which is what inflated
sigma_SR). Every pattern below is designed for roughly <= 12-25 round
trips per ticker-year (~0.1-0.25% annual drag), mostly <= 12, so a
modest real edge would no longer be structurally invisible.

Bars are 15-minute OHLCV (multi-year Alpaca history; reused raw price
data carries no snooping risk — only pattern SELECTION does). The walk-
forward runs engine.py's unmodified run_walk_forward directly against
15-minute-bar-indexed raw_data, exactly like intraday_patterns.py does
against hourly bars, then collapses per-bar equity to one return per
trading day (daily_returns_from_bar_equity, reused as-is) before Sharpe/
DSR — keeping every downstream consumer on the daily-cadence convention
it was validated for.

Two deliberate, disclosed methodology differences from intraday_patterns:

(1) `ret` here is each bar's CLOSE-TO-CLOSE return (pct_change), not
open-to-close. intraday_patterns' open-to-close was correct for its 1-bar
holds (enter at a bar's open, exit at its close — the overnight gap was
untradeable). This family holds positions for MULTIPLE DAYS, so the
overnight moves while holding are real P&L that open-to-close would
silently discard (much of a multi-day reversal happens overnight). The
implied execution is entry/exit AT the signal bar's close — exactly the
convention momentum.py's daily walk-forward already uses (position decided
from the window through t-1 realizes day t's pct_change, i.e. entry at
t-1's close), not a new invention.

(2) Calendar structure (which day is a month's last trading day, exchange
holidays, option-expiration Fridays) is treated as KNOWN IN ADVANCE:
exchange calendars are published years ahead, so "enter at the close of
the month's second-to-last trading day" is a real, executable instruction,
not lookahead. All PRICE/VOLUME-derived quantities remain strictly causal
(each day's signal uses only bars up to that day's close; volatility
scaling uses only PRIOR days) — test_low_frequency_patterns.py's prefix-
invariance test verifies price-causality directly.

Every pattern's hold is expressed as a precomputed per-bar signal column
(sig_<pattern_id>: the desired position for the NEXT bar, in {-1,0,+1}),
so the walk-forward's fire function is a cheap column read and the hold
duration is explicit by construction rather than emergent. The engine's
own never-direct-reversal invariant (apply_pattern_signal_rule, reused
unmodified) still governs transitions.

The full family, its citations, and each pattern's structural frequency
argument (all real sources, same convention as intraday_patterns.py):

1. extreme_move (8): a one-day close-to-close move beyond +/-3 or 4 sigma
   (trailing 60-day daily volatility, measured through the PRIOR day so
   the event can't inflate its own denominator), held 2 or 5 days,
   reversal and continuation readings. Bremer & Sweeney, 'The Reversal of
   Large Stock-Price Decreases' (Journal of Finance, 1991); Atkins & Dyl,
   'Price Reversals, Bid-Ask Spreads, and Market Efficiency' (Journal of
   Financial and Quantitative Analysis, 1990) — Atkins & Dyl studied both
   large gainers AND losers, so the two-sided trigger is their design,
   not an extrapolation. Structurally rare: even with fat tails, |z|>=3
   one-day moves occur a handful of times per ticker-year, |z|>=4 about
   yearly.

2. gap (4): an overnight gap (today's open vs yesterday's close) beyond
   +/-2 or 3 sigma of trailing 60-day DAILY volatility, entered at the
   first 15-minute bar's close, exited at the same day's close — fade and
   follow readings. Grant, Wolf & Yu, 'Intraday price reversals in the US
   stock index futures market: A 15-year study' (Journal of Banking &
   Finance, 2005) — large-opening-gap reversal is their finding.
   Structurally rare: overnight variance is well below full-day variance,
   so a gap of >=2 full-day sigmas is a several-sigma overnight event.

3. turn_of_month (4): long/short held over the turn-of-month window,
   entered at the close of the month's second-to-last trading day; exits
   after the 3rd (tom4) or 9th (firsthalf) trading day of the new month.
   Ariel, 'A Monthly Effect in Stock Returns' (Journal of Financial
   Economics, 1987); Lakonishok & Smidt, 'Are Seasonal Anomalies Real? A
   Ninety-Year Perspective' (Review of Financial Studies, 1988).
   Exactly 12 round trips per year by construction.

4. preholiday (2): long/short the single trading day before an exchange
   holiday. Ariel, 'High Stock Returns before Holidays: Existence and
   Evidence on Possible Causes' (Journal of Finance, 1990). At most ~9
   round trips per year by construction (NYSE holiday count).

5. high252_breakout (2): the first daily close above the prior 252-day
   maximum close after a 20-trading-day refractory period with no such
   event, held 10 days, continuation (the documented direction) and
   reversal readings. George & Hwang, 'The 52-Week High and Momentum
   Investing' (Journal of Finance, 2004). Hard-capped at <=~12/year by
   the refractory gate; realistically far fewer.

6. opex_week (2): long/short held over the option-expiration week (the
   week containing the month's third Friday), entered at the prior
   trading day's close, exited at the expiration Friday's close. Stivers
   & Sun, 'Returns and Option Activity over the Option-Expiration Week
   for S&P 100 Stocks' (Journal of Banking & Finance, 2013). Exactly 12
   round trips per year by construction.

7. bollinger3s_daily (2): a DAILY close outside a 20-day, 3-STANDARD-
   DEVIATION Bollinger band (vs. the 1.5-2.5 sigma hourly variants the
   212-family tested — 3 sigma on daily closes is the structurally-rare
   version of the same published rule), held 5 days, 10-day refractory,
   reversion (Bollinger's reading) and continuation. Bollinger, John,
   'Bollinger on Bollinger Bands' (McGraw-Hill, 2001).

8. rsi_daily_extreme (2): DAILY 14-period RSI beyond 85/15 (Wilder's
   indicator at deep-extreme bounds chosen a priori for structural
   rarity — his classic 70/30 fires far too often for this family's
   frequency ceiling), held 5 days, 10-day refractory, reversion
   (Wilder's reading) and continuation. Wilder, J. Welles, 'New Concepts
   in Technical Trading Systems' (1978). Same plain-mean gain/loss
   averaging convention as intraday_patterns' RSI, disclosed there.

9. volume_shock_5x (2): daily volume >= 5x the trailing 60-day median
   (structurally rare — typically earnings/news days), direction from
   that day's own return sign, climax-reversal and confirmation readings,
   held 5 days, 10-day refractory. Wyckoff (as 'Rollo Tape'), 'Studies in
   Tape Reading' (1910); Granville, 'Granville's New Key to Stock Market
   Profits' (1963).

Where the literature documents one direction, the opposite reading is
tested as an honestly co-equal alternative (this project's established
test-both-directions discipline, exactly as intraday_patterns.py did with
its `reverse` flags), not as a correction assumed to be right.

n_trials is fixed at the family's literal size for every result — every
pattern above counts, no post-hoc exclusions, no early stopping. The
family's own measured sigma_SR and the resulting SR0 noise benchmark are
surfaced explicitly on the screening summary (LowFreqScreeningSummary) —
they are the key diagnostic this round exists to measure: a homogeneous
low-frequency family should produce a far smaller sigma_SR than the 212/
420 families' ~2.9, and therefore an SR0 a real strategy could actually
clear (or honestly fail to clear).

Result of the live screening run (2026-08-26, all 28 patterns x all 284
cached tickers, 15-minute bars 2021-01-04..2026-08-24, run to completion
with no early stopping; every number below is measured, none estimated):

- The frequency design held. Measured across the full run: mean 4.8 /
  median 2.7 / max 12.3 round trips per ticker-year. The committed
  212-pattern family, measured performance-blind on the SAME 15-minute
  bars (fire-sequence position simulation, no returns touched), runs at
  mean 142.9 / median 99.3 / max 1265.4 — a ~30x mean reduction, with
  147/212 of the old patterns above 50/year and every new pattern below
  12.5/year.
- The statistical fix this round existed to test WORKED: the family's
  measured sigma_SR is 0.456 annualized (vs ~2.9 on the 212 family),
  giving SR0 = 0.93 annualized at n_trials=28 (vs ~8.1-9.5 at
  n_trials=212-420) — for the first time in this program, a noise
  benchmark a real strategy could plausibly clear.
- Against that meaningful bar, the result is still a clean negative. All
  28 patterns fired and produced reportable pooled results (9 positive /
  19 negative Sharpe). The best, high252_breakout_continuation (+0.64
  annualized, 1.9 trades/ticker-year, 53.1% hit rate over 2,987 trades),
  reached PSR-vs-zero 93.4% but DSR only 0.249 — an estimated 25%
  probability its true Sharpe exceeds what the best of 28 zero-edge
  trials would show by luck. Nothing else exceeded DSR 0.25 either
  (next: turn_of_month_firsthalf_long 0.22, preholiday_long 0.16).
- An honest observation, explicitly NOT promoted to a finding: the
  literature's documented directions all landed on the positive side
  (high-252 continuation +0.64 vs its reversal mirror -0.89, turn-of-
  month long +0.61/+0.30 vs short -0.81/-0.59, preholiday long +0.55 vs
  short -1.39), a sign-consistency one would expect if the classic
  calendar/momentum anomalies retain a trace net of costs — but equally
  what long-only drift in a 2021-2026 sample produces, and none of it is
  separable from the best-of-28-noise benchmark at this sample size.

Unlike the 212/420 rounds, this negative is statistically meaningful
rather than structurally foreordained: the family was cheap enough to
trade that a modest real edge COULD have cleared its own noise bar, and
none did."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from functools import partial

import numpy as np
import pandas as pd

from app.services.research_lab.deflated_sharpe import (
    DeflatedSharpeResult,
    compute_deflated_sharpe,
    expected_max_sharpe_under_noise,
)
from app.services.research_lab.engine import (
    ExperimentResult,
    StrategyFit,
    WalkForwardConfig,
    run_walk_forward,
)
from app.services.research_lab.intraday_patterns import (
    INTRADAY_COST_BPS,
    INTRADAY_FIT_WINDOW_BARS,
    MIN_POOLED_TRADING_DAYS,
    PatternSignal,
    PatternSpec,
    apply_pattern_signal_rule,
    daily_returns_from_bar_equity,
)
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR, sharpe_ratio

# --- Structural-frequency design constants -------------------------------
# Every constant below was fixed BEFORE this family's first backtest run —
# they are the pre-registration. None was tuned against performance.

# Trailing window for the daily volatility that scales the extreme-move and
# gap triggers. Uses ONLY days strictly before the candidate event day
# (shifted by one), so an extreme day can never inflate its own sigma and
# thereby suppress its own trigger. Strict min_periods: no estimate until
# the window is full — early history simply can't fire, an honest warmup.
DAILY_SIGMA_LOOKBACK_DAYS = 60

# Multi-sigma one-day-move thresholds (family 1). 3 and 4 sigma — NOT the
# 1-2 sigma range where events are everyday occurrences; under a normal
# distribution |z|>=3 is ~0.3% of days (~0.7/yr) and even with real fat
# tails only a handful per year.
EXTREME_MOVE_Z_THRESHOLDS = (3.0, 4.0)
EXTREME_MOVE_HOLD_DAYS = (2, 5)  # Bremer & Sweeney find reversal over ~2 days; 5 tests a slower variant

# Overnight-gap thresholds in units of full-day sigma (family 2). Overnight
# variance is a fraction of full-day variance, so 2 full-day sigmas is
# already a rare overnight event; 3 is rarer still.
GAP_Z_THRESHOLDS = (2.0, 3.0)

# Turn-of-month exit ordinals (family 3): hold through the 3rd trading day
# of the new month (Lakonishok & Smidt's -1..+3 window) or the 9th
# (Ariel's first-half-of-month window). Entry is always the close of the
# month's second-to-last trading day, so day -1's return is captured.
TOM_EXIT_ORDINALS = {"tom4": 3, "firsthalf": 9}

# 52-week-high breakout (family 5).
HIGH252_LOOKBACK_DAYS = 252
HIGH252_REFRACTORY_DAYS = 20  # the explicit at-most-monthly structural gate
HIGH252_HOLD_DAYS = 10

# Daily Bollinger / RSI / volume-shock event families (7-9).
BOLLINGER_DAILY_PERIOD = 20
BOLLINGER_DAILY_N_STD = 3.0
RSI_DAILY_PERIOD = 14
RSI_DAILY_OVERBOUGHT = 85.0
RSI_DAILY_OVERSOLD = 15.0
VOLUME_SHOCK_MULTIPLE = 5.0
VOLUME_MEDIAN_LOOKBACK_DAYS = 60
EVENT_HOLD_DAYS = 5
EVENT_REFRACTORY_DAYS = 10

# Hard ceiling from this round's own pre-registration: the family may never
# exceed this many definitions, and n_trials always counts all of them.
MAX_FAMILY_SIZE = 40

# Cap on how many times a bare flat bet a single event's realized position
# can be sized at, once scaled by how far past its own family's declared
# threshold the triggering value actually was — see build_magnitude_ratio
# callables below. Same "engineering judgment call, disclosed not
# calibrated" register as cross_sectional.py's MAX_WEIGHT_MULTIPLE, and
# reused at the identical value for consistency across the project's
# pattern-mining harnesses, not independently tuned per module.
MAX_WEIGHT_MULTIPLE = 3.0

# Families with no natural continuous magnitude to scale by (a calendar
# window either applies or it doesn't; a 52-week breakout is a single
# binary event with no meaningful "how much of a breakout"): these stay
# permanently sized at a flat 1.0 ratio, a disclosed judgment call rather
# than inventing a post-hoc magnitude with no cited basis. Referenced by
# family name, not pattern_id, so it stays correct if a family's readings
# are renamed.
FAMILIES_WITHOUT_MAGNITUDE = frozenset({"turn_of_month", "preholiday", "opex_week", "high252_breakout"})


# --- Daily aggregation and calendar structure ----------------------------


def build_daily_frame(bars: pd.DataFrame) -> pd.DataFrame:
    """One row per trading day from a ticker's 15-minute OHLCV bars
    (lowercase open/high/low/close/volume, tz-aware intraday index).
    Every derived column is causal as of that day's CLOSE unless its name
    says otherwise (`*_prior` columns are causal as of that day's OPEN —
    they use only strictly-prior days)."""
    df = bars.sort_index()
    trading_date = pd.Series(df.index.date, index=df.index, name="trading_date")
    g = df.groupby(trading_date, sort=True)
    daily = pd.DataFrame(
        {
            "day_open": g["open"].first(),
            "day_close": g["close"].last(),
            "day_volume": g["volume"].sum(),
        }
    )
    daily["close_ret"] = daily["day_close"].pct_change()

    # Causal-as-of-open: computed from strictly-prior days only.
    daily["sigma_prior"] = (
        daily["close_ret"].rolling(DAILY_SIGMA_LOOKBACK_DAYS, min_periods=DAILY_SIGMA_LOOKBACK_DAYS).std(ddof=1).shift(1)
    )
    daily["high252_prior"] = (
        daily["day_close"].rolling(HIGH252_LOOKBACK_DAYS, min_periods=HIGH252_LOOKBACK_DAYS).max().shift(1)
    )
    daily["vol_median_prior"] = (
        daily["day_volume"].rolling(VOLUME_MEDIAN_LOOKBACK_DAYS, min_periods=VOLUME_MEDIAN_LOOKBACK_DAYS).median().shift(1)
    )

    with np.errstate(divide="ignore", invalid="ignore"):
        daily["ret_z"] = np.where(
            (daily["sigma_prior"] > 0) & np.isfinite(daily["sigma_prior"]),
            daily["close_ret"] / daily["sigma_prior"],
            np.nan,
        )
        gap_ret = daily["day_open"] / daily["day_close"].shift(1) - 1.0
        daily["gap_z"] = np.where(
            (daily["sigma_prior"] > 0) & np.isfinite(daily["sigma_prior"]),
            gap_ret / daily["sigma_prior"],
            np.nan,
        )

    # Daily Bollinger band (includes the current close in its window —
    # Bollinger's own standard construction; still uses only data <= d).
    mean = daily["day_close"].rolling(BOLLINGER_DAILY_PERIOD, min_periods=BOLLINGER_DAILY_PERIOD).mean()
    std = daily["day_close"].rolling(BOLLINGER_DAILY_PERIOD, min_periods=BOLLINGER_DAILY_PERIOD).std(ddof=1)
    daily["boll_upper"] = mean + BOLLINGER_DAILY_N_STD * std
    daily["boll_lower"] = mean - BOLLINGER_DAILY_N_STD * std
    daily["boll_mean"] = mean
    daily["boll_std"] = std

    # Daily RSI, plain-mean gain/loss averaging (intraday_patterns' own
    # disclosed convention for the same indicator).
    delta = daily["day_close"].diff()
    avg_gain = delta.clip(lower=0).rolling(RSI_DAILY_PERIOD, min_periods=RSI_DAILY_PERIOD).mean()
    avg_loss = (-delta.clip(upper=0)).rolling(RSI_DAILY_PERIOD, min_periods=RSI_DAILY_PERIOD).mean()
    # avg_loss can legitimately be exactly 0 (14 straight up-days) — RSI is
    # then 100 by definition, not a division error. But 14 straight FLAT
    # days (avg_gain == avg_loss == 0) is indeterminate, not overbought —
    # left NaN so a halted/stale series can never fire the extreme.
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_gain / avg_loss
        rsi = 100.0 - 100.0 / (1.0 + rs)
    daily["rsi"] = np.where(
        (avg_loss == 0) & avg_gain.notna(), np.where(avg_gain > 0, 100.0, np.nan), rsi
    )

    _add_calendar_columns(daily)
    return daily


def _third_friday(year: int, month: int) -> date:
    first_weekday = date(year, month, 1).weekday()  # Monday=0 .. Friday=4
    first_friday_day = 1 + (4 - first_weekday) % 7
    return date(year, month, first_friday_day + 14)


def _add_calendar_columns(daily: pd.DataFrame) -> None:
    """Adds month ordinals, pre-holiday flags, and option-expiration-week
    flags in place. Calendar structure is known in advance (exchange
    schedules are published years ahead) — see module docstring. Because
    the calendar is DERIVED from the data's own trading dates rather than
    an external schedule, the sample's first and last partial months carry
    a small disclosed artifact: month_reverse_ordinal labels the last
    OBSERVED day of the final partial month as "month end", and the final
    day can never be flagged pre-holiday (its successor is unobservable).
    This affects only the two boundary months of a multi-year sample."""
    dates = list(daily.index)
    month_keys = pd.Series([(d.year, d.month) for d in dates], index=daily.index)
    grouped = month_keys.groupby(month_keys)
    daily["month_ordinal"] = grouped.cumcount() + 1
    daily["month_reverse_ordinal"] = grouped.cumcount(ascending=False) + 1

    # Pre-holiday: the next trading day is further away than a plain
    # weekday (1 day) or plain weekend (3 days) would put it. The final
    # date in the data has no successor and is conservatively not flagged.
    preholiday = np.zeros(len(dates), dtype=bool)
    for i in range(len(dates) - 1):
        gap_days = (dates[i + 1] - dates[i]).days
        weekday = dates[i].weekday()
        preholiday[i] = (weekday <= 3 and gap_days >= 2) or (weekday == 4 and gap_days >= 4)
    daily["is_preholiday"] = preholiday

    # Option-expiration week: trading days from the Monday of the third-
    # Friday week through the expiration day (the last trading day <= the
    # third Friday — handles Good Friday expirations moving to Thursday).
    in_opex_week = np.zeros(len(dates), dtype=bool)
    date_index = {d: i for i, d in enumerate(dates)}
    for year, month in sorted(set(month_keys)):
        friday = _third_friday(year, month)
        monday = friday - timedelta(days=4)
        expiry_candidates = [d for d in dates if monday <= d <= friday]
        for d in expiry_candidates:
            in_opex_week[date_index[d]] = True
    daily["in_opex_week"] = in_opex_week


# --- Event -> daily hold construction ------------------------------------


def build_hold_and_magnitude_from_events(
    event_dir: np.ndarray, event_ratio: np.ndarray, hold_days: int, refractory_days: int = 0
) -> tuple[np.ndarray, np.ndarray]:
    """Same accept/refractory event-to-hold construction as
    build_hold_from_events, additionally carrying each ACCEPTED event's own
    magnitude ratio (see the per-family build_magnitude_ratio callables
    below — already clipped to [1.0, MAX_WEIGHT_MULTIPLE] by the caller,
    or a flat 1.0 for families with no natural magnitude) through that
    event's whole hold window — the position-SIZE analogue of the existing
    position-DIRECTION hold. build_hold_from_events is a thin wrapper over
    this with event_ratio fixed at all-ones, which guarantees its direction
    output stays byte-identical to before this function existed (not just
    similar by inspection)."""
    n = len(event_dir)
    hold = np.zeros(n, dtype=np.int8)
    magnitude_hold = np.ones(n, dtype=np.float64)
    last_accepted = -(10**9)
    for i in np.flatnonzero(event_dir):
        if i - last_accepted <= refractory_days:
            continue
        last_accepted = i
        hold[i + 1 : i + 1 + hold_days] = event_dir[i]
        magnitude_hold[i + 1 : i + 1 + hold_days] = event_ratio[i]
    return hold, magnitude_hold


def build_hold_from_events(event_dir: np.ndarray, hold_days: int, refractory_days: int = 0) -> np.ndarray:
    """Turns a per-day event series (+1/-1/0) into a per-day HOLD series:
    the position held DURING each day, entered at the prior day's close.
    An accepted event on day i sets days i+1 .. i+hold_days; a later
    accepted event overrides any overlap (most-recent-event-wins, a
    disclosed simplification). Events within `refractory_days` of the last
    ACCEPTED event are suppressed — the explicit structural frequency cap
    the module docstring describes."""
    hold, _ = build_hold_and_magnitude_from_events(
        event_dir, np.ones(len(event_dir), dtype=np.float64), hold_days, refractory_days
    )
    return hold


def _direction_from_z(z: pd.Series, threshold: float, *, reverse: bool) -> np.ndarray:
    """+1/-1/0 event direction from a signed z-score at +/-threshold.
    reverse=False bets WITH the move's sign; reverse=True against it."""
    values = z.to_numpy(dtype=float)
    direction = np.zeros(len(values), dtype=np.int8)
    with np.errstate(invalid="ignore"):
        fired = np.isfinite(values) & (np.abs(values) >= threshold)
    sign = np.sign(np.nan_to_num(values)).astype(np.int8)  # nan_to_num: NaN never casts to int8
    direction[fired] = sign[fired]
    return -direction if reverse else direction


# --- Per-bar signal columns ----------------------------------------------


def _daily_hold_to_bar_signal(daily_hold: pd.Series, bar_dates: np.ndarray) -> np.ndarray:
    """Maps a per-trading-day hold series onto per-bar SIGNAL values: the
    signal stored at bar j is the position desired for bar j+1 (what the
    walk-forward's fire function, reading the window's LAST bar, needs).
    Position during every bar of day D equals hold[D]; the signal is that
    per-bar position shifted back by one bar, so a day's last bar carries
    the NEXT day's hold (decidable then: holds for day D+1 are set by
    events through day D's close, and the trading calendar is known in
    advance). The final bar's signal is 0 — it is never read."""
    pos_for_bar = daily_hold.reindex(bar_dates).to_numpy()
    pos_for_bar = np.nan_to_num(pos_for_bar, nan=0.0).astype(np.int8)
    signal = np.empty_like(pos_for_bar)
    signal[:-1] = pos_for_bar[1:]
    signal[-1] = 0
    return signal


def _daily_hold_to_bar_magnitude(daily_magnitude: pd.Series, bar_dates: np.ndarray) -> np.ndarray:
    """The float64 magnitude-ratio analogue of _daily_hold_to_bar_signal —
    identical shift-by-one-bar mapping, so a magnitude column always lines
    up with its paired direction column bar-for-bar. The final bar and any
    day with no recorded magnitude default to 1.0 (a flat, unweighted bet)
    rather than 0.0 — a position sized at zero would silently vanish from
    realized P&L instead of just being un-magnitude-weighted."""
    mag_for_bar = daily_magnitude.reindex(bar_dates).to_numpy(dtype=np.float64)
    mag_for_bar = np.nan_to_num(mag_for_bar, nan=1.0)
    magnitude = np.empty_like(mag_for_bar)
    magnitude[:-1] = mag_for_bar[1:]
    magnitude[-1] = 1.0
    return magnitude


def _gap_bar_signal(
    daily: pd.DataFrame, bar_dates: np.ndarray, threshold: float, *, fade: bool
) -> np.ndarray:
    """Family 2 only: bar-level (not daily-hold) signal. On a gap-event
    day, the position is held during bars 2..last of that day — entry at
    the FIRST 15-minute bar's close (the gap is known at the open; the
    first bar is the entry vehicle), exit at the day's close. The signal
    (desired position for the NEXT bar) is therefore +/-1 on bars
    1..last-1 of the event day and 0 on its last bar. fade=True trades
    AGAINST the gap's direction (the Grant/Wolf/Yu reading); fade=False
    trades with it."""
    gap_dir = pd.Series(
        _direction_from_z(daily["gap_z"], threshold, reverse=fade),
        index=daily.index,
    )
    dir_for_bar = gap_dir.reindex(bar_dates).to_numpy()
    dir_for_bar = np.nan_to_num(dir_for_bar, nan=0.0).astype(np.int8)

    is_first_bar_of_day = np.empty(len(bar_dates), dtype=bool)
    is_first_bar_of_day[0] = True
    is_first_bar_of_day[1:] = bar_dates[1:] != bar_dates[:-1]
    pos_for_bar = np.where(is_first_bar_of_day, 0, dir_for_bar).astype(np.int8)

    signal = np.empty_like(pos_for_bar)
    signal[:-1] = pos_for_bar[1:]
    signal[-1] = 0
    return signal


def _gap_bar_magnitude(daily: pd.DataFrame, bar_dates: np.ndarray, threshold: float) -> np.ndarray:
    """Family 2's magnitude counterpart to _gap_bar_signal: the same
    bar-placement logic (held on bars 2..last of the gap-event day, flat on
    the first and last bars), carrying abs(gap_z)/threshold — clipped to
    [1.0, MAX_WEIGHT_MULTIPLE] — instead of a fixed direction. Computed
    before any fade/follow sign flip, since magnitude is direction-
    agnostic (see the extreme_move/bollinger/rsi/volume builders below for
    the same convention)."""
    gap_z = daily["gap_z"].to_numpy(dtype=float)
    with np.errstate(invalid="ignore"):
        fired = np.isfinite(gap_z) & (np.abs(gap_z) >= threshold)
    ratio = np.where(fired, np.clip(np.abs(gap_z) / threshold, 1.0, MAX_WEIGHT_MULTIPLE), 1.0)
    ratio_series = pd.Series(ratio, index=daily.index)
    ratio_for_bar = ratio_series.reindex(bar_dates).to_numpy(dtype=np.float64)
    ratio_for_bar = np.nan_to_num(ratio_for_bar, nan=1.0)

    is_first_bar_of_day = np.empty(len(bar_dates), dtype=bool)
    is_first_bar_of_day[0] = True
    is_first_bar_of_day[1:] = bar_dates[1:] != bar_dates[:-1]
    mag_for_bar = np.where(is_first_bar_of_day, 1.0, ratio_for_bar)

    magnitude = np.empty_like(mag_for_bar)
    magnitude[:-1] = mag_for_bar[1:]
    magnitude[-1] = 1.0
    return magnitude


@dataclass(frozen=True)
class _LowFreqPatternDef:
    """A pattern plus the recipes for its precomputed signal (direction)
    and magnitude-ratio (position size) columns. build_magnitude_ratio
    defaults to None for families with no natural continuous magnitude
    (see FAMILIES_WITHOUT_MAGNITUDE) — build_lowfreq_raw_data then never
    writes a mag_* column for that pattern, and _make_column_fit_fn's own
    default (flat ratio 1.0, today's behavior) applies."""

    spec: PatternSpec
    build_signal: Callable[[pd.DataFrame, np.ndarray], np.ndarray]  # (daily, bar_dates) -> per-bar signal
    build_magnitude_ratio: Callable[[pd.DataFrame, np.ndarray], np.ndarray] | None = None


def _fire_from_signal_column(window: pd.DataFrame, *, column: str) -> PatternSignal | None:
    if window.empty:
        return None
    value = window[column].iloc[-1]
    if value > 0:
        return PatternSignal(direction="long", strength=1.0)
    if value < 0:
        return PatternSignal(direction="short", strength=1.0)
    return None


def signal_column_for(pattern_id: str) -> str:
    return f"sig_{pattern_id}"


def magnitude_column_for(pattern_id: str) -> str:
    return f"mag_{pattern_id}"


def _make_spec(pattern_id: str, family: str, citation: str) -> PatternSpec:
    return PatternSpec(
        pattern_id=pattern_id,
        family=family,
        citation=citation,
        fire_fn=partial(_fire_from_signal_column, column=signal_column_for(pattern_id)),
    )


def _build_family() -> list[_LowFreqPatternDef]:
    defs: list[_LowFreqPatternDef] = []

    # -- 1. extreme_move ---------------------------------------------------
    extreme_citation = (
        "Bremer & Sweeney, 'The Reversal of Large Stock-Price Decreases' (Journal of Finance, 1991); "
        "Atkins & Dyl, 'Price Reversals, Bid-Ask Spreads, and Market Efficiency' "
        "(Journal of Financial and Quantitative Analysis, 1990)"
    )
    for z_threshold in EXTREME_MOVE_Z_THRESHOLDS:
        for hold_days in EXTREME_MOVE_HOLD_DAYS:
            for reading, reverse in (("reversal", True), ("continuation", False)):

                def _extreme_ratio(daily: pd.DataFrame, *, z_threshold: float) -> np.ndarray:
                    # Magnitude is direction-agnostic (computed before any
                    # reversal flip) — how far past the trigger the move
                    # was, not which way it was read.
                    z = daily["ret_z"].to_numpy(dtype=float)
                    with np.errstate(invalid="ignore"):
                        fired = np.isfinite(z) & (np.abs(z) >= z_threshold)
                    return np.where(fired, np.clip(np.abs(z) / z_threshold, 1.0, MAX_WEIGHT_MULTIPLE), 1.0)

                def build_extreme(
                    daily: pd.DataFrame,
                    bar_dates: np.ndarray,
                    *,
                    z_threshold: float = z_threshold,
                    hold_days: int = hold_days,
                    reverse: bool = reverse,
                ) -> np.ndarray:
                    events = _direction_from_z(daily["ret_z"], z_threshold, reverse=reverse)
                    hold, _ = build_hold_and_magnitude_from_events(
                        events, _extreme_ratio(daily, z_threshold=z_threshold), hold_days
                    )
                    return _daily_hold_to_bar_signal(pd.Series(hold, index=daily.index), bar_dates)

                def build_extreme_magnitude(
                    daily: pd.DataFrame,
                    bar_dates: np.ndarray,
                    *,
                    z_threshold: float = z_threshold,
                    hold_days: int = hold_days,
                    reverse: bool = reverse,
                ) -> np.ndarray:
                    events = _direction_from_z(daily["ret_z"], z_threshold, reverse=reverse)
                    _, magnitude_hold = build_hold_and_magnitude_from_events(
                        events, _extreme_ratio(daily, z_threshold=z_threshold), hold_days
                    )
                    return _daily_hold_to_bar_magnitude(pd.Series(magnitude_hold, index=daily.index), bar_dates)

                defs.append(
                    _LowFreqPatternDef(
                        spec=_make_spec(
                            f"extreme_move_{reading}_{z_threshold:.0f}s_{hold_days}d",
                            "extreme_move",
                            extreme_citation,
                        ),
                        build_signal=build_extreme,
                        build_magnitude_ratio=build_extreme_magnitude,
                    )
                )

    # -- 2. gap ------------------------------------------------------------
    gap_citation = (
        "Grant, Wolf & Yu, 'Intraday price reversals in the US stock index futures market: "
        "A 15-year study' (Journal of Banking & Finance, 2005)"
    )
    for z_threshold in GAP_Z_THRESHOLDS:
        for reading, fade in (("fade", True), ("follow", False)):

            def build_gap(
                daily: pd.DataFrame,
                bar_dates: np.ndarray,
                *,
                z_threshold: float = z_threshold,
                fade: bool = fade,
            ) -> np.ndarray:
                return _gap_bar_signal(daily, bar_dates, z_threshold, fade=fade)

            def build_gap_magnitude(
                daily: pd.DataFrame, bar_dates: np.ndarray, *, z_threshold: float = z_threshold
            ) -> np.ndarray:
                # Magnitude is direction-agnostic — fade vs follow doesn't
                # change how far past threshold the gap was.
                return _gap_bar_magnitude(daily, bar_dates, z_threshold)

            defs.append(
                _LowFreqPatternDef(
                    spec=_make_spec(f"gap_{reading}_{z_threshold:.0f}s", "gap", gap_citation),
                    build_signal=build_gap,
                    build_magnitude_ratio=build_gap_magnitude,
                )
            )

    # -- 3. turn_of_month --------------------------------------------------
    tom_citation = (
        "Ariel, 'A Monthly Effect in Stock Returns' (Journal of Financial Economics, 1987); "
        "Lakonishok & Smidt, 'Are Seasonal Anomalies Real? A Ninety-Year Perspective' "
        "(Review of Financial Studies, 1988)"
    )
    for window_name, exit_ordinal in TOM_EXIT_ORDINALS.items():
        for direction_name, direction in (("long", 1), ("short", -1)):

            def build_tom(
                daily: pd.DataFrame,
                bar_dates: np.ndarray,
                *,
                exit_ordinal: int = exit_ordinal,
                direction: int = direction,
            ) -> np.ndarray:
                in_window = (daily["month_reverse_ordinal"] == 1) | (daily["month_ordinal"] <= exit_ordinal)
                hold = pd.Series(np.where(in_window, direction, 0).astype(np.int8), index=daily.index)
                return _daily_hold_to_bar_signal(hold, bar_dates)

            defs.append(
                _LowFreqPatternDef(
                    spec=_make_spec(
                        f"turn_of_month_{window_name}_{direction_name}", "turn_of_month", tom_citation
                    ),
                    build_signal=build_tom,
                )
            )

    # -- 4. preholiday -----------------------------------------------------
    preholiday_citation = (
        "Ariel, 'High Stock Returns before Holidays: Existence and Evidence on Possible Causes' "
        "(Journal of Finance, 1990)"
    )
    for direction_name, direction in (("long", 1), ("short", -1)):

        def build_preholiday(
            daily: pd.DataFrame, bar_dates: np.ndarray, *, direction: int = direction
        ) -> np.ndarray:
            hold = pd.Series(
                np.where(daily["is_preholiday"], direction, 0).astype(np.int8), index=daily.index
            )
            return _daily_hold_to_bar_signal(hold, bar_dates)

        defs.append(
            _LowFreqPatternDef(
                spec=_make_spec(f"preholiday_{direction_name}", "preholiday", preholiday_citation),
                build_signal=build_preholiday,
            )
        )

    # -- 5. high252_breakout -----------------------------------------------
    high252_citation = "George & Hwang, 'The 52-Week High and Momentum Investing' (Journal of Finance, 2004)"
    for reading, direction in (("continuation", 1), ("reversal", -1)):

        def build_high252(
            daily: pd.DataFrame, bar_dates: np.ndarray, *, direction: int = direction
        ) -> np.ndarray:
            breakout = (
                np.isfinite(daily["high252_prior"].to_numpy(dtype=float))
                & (daily["day_close"].to_numpy() > daily["high252_prior"].to_numpy())
            )
            events = np.where(breakout, direction, 0).astype(np.int8)
            hold = build_hold_from_events(events, HIGH252_HOLD_DAYS, HIGH252_REFRACTORY_DAYS)
            return _daily_hold_to_bar_signal(pd.Series(hold, index=daily.index), bar_dates)

        defs.append(
            _LowFreqPatternDef(
                spec=_make_spec(f"high252_breakout_{reading}", "high252_breakout", high252_citation),
                build_signal=build_high252,
            )
        )

    # -- 6. opex_week --------------------------------------------------------
    opex_citation = (
        "Stivers & Sun, 'Returns and Option Activity over the Option-Expiration Week for "
        "S&P 100 Stocks' (Journal of Banking & Finance, 2013)"
    )
    for direction_name, direction in (("long", 1), ("short", -1)):

        def build_opex(
            daily: pd.DataFrame, bar_dates: np.ndarray, *, direction: int = direction
        ) -> np.ndarray:
            hold = pd.Series(
                np.where(daily["in_opex_week"], direction, 0).astype(np.int8), index=daily.index
            )
            return _daily_hold_to_bar_signal(hold, bar_dates)

        defs.append(
            _LowFreqPatternDef(
                spec=_make_spec(f"opex_week_{direction_name}", "opex_week", opex_citation),
                build_signal=build_opex,
            )
        )

    # -- 7. bollinger3s_daily ------------------------------------------------
    bollinger_citation = "Bollinger, John, 'Bollinger on Bollinger Bands' (McGraw-Hill, 2001)"
    for reading, reverse in (("reversion", True), ("continuation", False)):

        def _bollinger_events(daily: pd.DataFrame) -> np.ndarray:
            close = daily["day_close"].to_numpy(dtype=float)
            upper = daily["boll_upper"].to_numpy(dtype=float)
            lower = daily["boll_lower"].to_numpy(dtype=float)
            events = np.zeros(len(close), dtype=np.int8)
            with np.errstate(invalid="ignore"):
                events[np.isfinite(upper) & (close > upper)] = 1
                events[np.isfinite(lower) & (close < lower)] = -1
            return events

        def _bollinger_ratio(daily: pd.DataFrame) -> np.ndarray:
            # Distance from the band's own center in std units, direction-
            # agnostic — at the band edge this equals BOLLINGER_DAILY_N_STD
            # exactly, giving ratio 1.0 there (today's flat bet).
            close = daily["day_close"].to_numpy(dtype=float)
            mean = daily["boll_mean"].to_numpy(dtype=float)
            std = daily["boll_std"].to_numpy(dtype=float)
            with np.errstate(invalid="ignore", divide="ignore"):
                z_equiv = np.abs(close - mean) / std
                fired = np.isfinite(z_equiv) & (std > 0) & (z_equiv >= BOLLINGER_DAILY_N_STD)
                ratio = np.where(
                    fired, np.clip(z_equiv / BOLLINGER_DAILY_N_STD, 1.0, MAX_WEIGHT_MULTIPLE), 1.0
                )
            return np.nan_to_num(ratio, nan=1.0)

        def build_bollinger(
            daily: pd.DataFrame, bar_dates: np.ndarray, *, reverse: bool = reverse
        ) -> np.ndarray:
            events = _bollinger_events(daily)
            if reverse:
                events = -events
            hold, _ = build_hold_and_magnitude_from_events(
                events, _bollinger_ratio(daily), EVENT_HOLD_DAYS, EVENT_REFRACTORY_DAYS
            )
            return _daily_hold_to_bar_signal(pd.Series(hold, index=daily.index), bar_dates)

        def build_bollinger_magnitude(
            daily: pd.DataFrame, bar_dates: np.ndarray, *, reverse: bool = reverse
        ) -> np.ndarray:
            events = _bollinger_events(daily)
            if reverse:
                events = -events
            _, magnitude_hold = build_hold_and_magnitude_from_events(
                events, _bollinger_ratio(daily), EVENT_HOLD_DAYS, EVENT_REFRACTORY_DAYS
            )
            return _daily_hold_to_bar_magnitude(pd.Series(magnitude_hold, index=daily.index), bar_dates)

        defs.append(
            _LowFreqPatternDef(
                spec=_make_spec(f"bollinger3s_daily_{reading}", "bollinger3s_daily", bollinger_citation),
                build_signal=build_bollinger,
                build_magnitude_ratio=build_bollinger_magnitude,
            )
        )

    # -- 8. rsi_daily_extreme -------------------------------------------------
    rsi_citation = "Wilder, J. Welles, 'New Concepts in Technical Trading Systems' (1978)"
    for reading, reverse in (("reversion", True), ("continuation", False)):

        def _rsi_events(daily: pd.DataFrame) -> np.ndarray:
            rsi = daily["rsi"].to_numpy(dtype=float)
            events = np.zeros(len(rsi), dtype=np.int8)
            with np.errstate(invalid="ignore"):
                events[np.isfinite(rsi) & (rsi >= RSI_DAILY_OVERBOUGHT)] = 1
                events[np.isfinite(rsi) & (rsi <= RSI_DAILY_OVERSOLD)] = -1
            return events

        def _rsi_ratio(daily: pd.DataFrame) -> np.ndarray:
            # RSI's overbought/oversold bounds are symmetric around 50
            # (85/15 here) — distance from 50 is a direction-agnostic
            # magnitude that equals RSI_DAILY_OVERBOUGHT-50 exactly at
            # either boundary, giving ratio 1.0 there (today's flat bet).
            rsi = daily["rsi"].to_numpy(dtype=float)
            declared_threshold = RSI_DAILY_OVERBOUGHT - 50.0
            distance = np.abs(rsi - 50.0)
            with np.errstate(invalid="ignore"):
                fired = np.isfinite(distance) & (distance >= declared_threshold)
                ratio = np.where(
                    fired, np.clip(distance / declared_threshold, 1.0, MAX_WEIGHT_MULTIPLE), 1.0
                )
            return np.nan_to_num(ratio, nan=1.0)

        def build_rsi(
            daily: pd.DataFrame, bar_dates: np.ndarray, *, reverse: bool = reverse
        ) -> np.ndarray:
            events = _rsi_events(daily)
            if reverse:
                events = -events
            hold, _ = build_hold_and_magnitude_from_events(
                events, _rsi_ratio(daily), EVENT_HOLD_DAYS, EVENT_REFRACTORY_DAYS
            )
            return _daily_hold_to_bar_signal(pd.Series(hold, index=daily.index), bar_dates)

        def build_rsi_magnitude(
            daily: pd.DataFrame, bar_dates: np.ndarray, *, reverse: bool = reverse
        ) -> np.ndarray:
            events = _rsi_events(daily)
            if reverse:
                events = -events
            _, magnitude_hold = build_hold_and_magnitude_from_events(
                events, _rsi_ratio(daily), EVENT_HOLD_DAYS, EVENT_REFRACTORY_DAYS
            )
            return _daily_hold_to_bar_magnitude(pd.Series(magnitude_hold, index=daily.index), bar_dates)

        defs.append(
            _LowFreqPatternDef(
                spec=_make_spec(f"rsi_daily_extreme_{reading}", "rsi_daily_extreme", rsi_citation),
                build_signal=build_rsi,
                build_magnitude_ratio=build_rsi_magnitude,
            )
        )

    # -- 9. volume_shock_5x -----------------------------------------------------
    volume_citation = (
        "Wyckoff (as 'Rollo Tape'), 'Studies in Tape Reading' (1910); "
        "Granville, 'Granville's New Key to Stock Market Profits' (1963)"
    )
    for reading, reverse in (("climax_reversal", True), ("confirmation", False)):

        def _volume_shock(daily: pd.DataFrame) -> np.ndarray:
            volume = daily["day_volume"].to_numpy(dtype=float)
            median = daily["vol_median_prior"].to_numpy(dtype=float)
            with np.errstate(invalid="ignore"):
                return np.isfinite(median) & (median > 0) & (volume >= VOLUME_SHOCK_MULTIPLE * median)

        def _volume_events(daily: pd.DataFrame) -> np.ndarray:
            shock = _volume_shock(daily)
            ret = daily["close_ret"].to_numpy(dtype=float)
            return np.where(shock & np.isfinite(ret), np.sign(ret), 0).astype(np.int8)

        def _volume_ratio(daily: pd.DataFrame) -> np.ndarray:
            # volume/median is already a natural ratio to VOLUME_SHOCK_MULTIPLE
            # — at exactly the shock threshold, (5*median/median)/5 == 1.0
            # (today's flat bet).
            volume = daily["day_volume"].to_numpy(dtype=float)
            median = daily["vol_median_prior"].to_numpy(dtype=float)
            shock = _volume_shock(daily)
            with np.errstate(invalid="ignore", divide="ignore"):
                raw_multiple = volume / median
                ratio = np.where(
                    shock, np.clip(raw_multiple / VOLUME_SHOCK_MULTIPLE, 1.0, MAX_WEIGHT_MULTIPLE), 1.0
                )
            return np.nan_to_num(ratio, nan=1.0)

        def build_volume(
            daily: pd.DataFrame, bar_dates: np.ndarray, *, reverse: bool = reverse
        ) -> np.ndarray:
            events = _volume_events(daily)
            if reverse:
                events = -events
            hold, _ = build_hold_and_magnitude_from_events(
                events, _volume_ratio(daily), EVENT_HOLD_DAYS, EVENT_REFRACTORY_DAYS
            )
            return _daily_hold_to_bar_signal(pd.Series(hold, index=daily.index), bar_dates)

        def build_volume_magnitude(
            daily: pd.DataFrame, bar_dates: np.ndarray, *, reverse: bool = reverse
        ) -> np.ndarray:
            events = _volume_events(daily)
            if reverse:
                events = -events
            _, magnitude_hold = build_hold_and_magnitude_from_events(
                events, _volume_ratio(daily), EVENT_HOLD_DAYS, EVENT_REFRACTORY_DAYS
            )
            return _daily_hold_to_bar_magnitude(pd.Series(magnitude_hold, index=daily.index), bar_dates)

        defs.append(
            _LowFreqPatternDef(
                spec=_make_spec(f"volume_shock_5x_{reading}", "volume_shock_5x", volume_citation),
                build_signal=build_volume,
                build_magnitude_ratio=build_volume_magnitude,
            )
        )

    if len(defs) > MAX_FAMILY_SIZE:
        raise AssertionError(
            f"low-frequency family grew to {len(defs)} definitions — the pre-registered hard "
            f"ceiling is {MAX_FAMILY_SIZE}; shrink the family, never raise the ceiling post hoc"
        )
    return defs


_FAMILY_DEFS: list[_LowFreqPatternDef] = _build_family()
LOW_FREQUENCY_PATTERN_FAMILY: list[PatternSpec] = [d.spec for d in _FAMILY_DEFS]


def build_lowfreq_raw_data(bars: pd.DataFrame) -> pd.DataFrame:
    """The engine-facing per-bar frame: trading_date, ret (CLOSE-TO-CLOSE —
    see module docstring point (1) for why this differs from
    intraday_patterns' open-to-close), one precomputed sig_* column per
    pattern in the family, and — for the patterns with a natural
    continuous magnitude (see FAMILIES_WITHOUT_MAGNITUDE) — a paired mag_*
    column carrying that event's size-scaling ratio. The very first bar's
    ret is set to 0.0 (there is no prior close) — it sits inside the
    walk-forward's fit window and is never realized."""
    df = bars.sort_index().copy()
    df["trading_date"] = df.index.date
    df["ret"] = df["close"].pct_change().fillna(0.0)

    daily = build_daily_frame(bars)
    bar_dates = df["trading_date"].to_numpy()
    for pattern_def in _FAMILY_DEFS:
        df[signal_column_for(pattern_def.spec.pattern_id)] = pattern_def.build_signal(daily, bar_dates)
        if pattern_def.build_magnitude_ratio is not None:
            df[magnitude_column_for(pattern_def.spec.pattern_id)] = pattern_def.build_magnitude_ratio(
                daily, bar_dates
            )
    return df


def realize_lowfreq_return(day_row: pd.Series, fit: StrategyFit) -> float:
    """Return per +1 (long) unit of position — the bar's close-to-close
    `ret` (see build_lowfreq_raw_data), realizable by a position entered
    at the prior bar's close, which is exactly when this module's signal
    columns say to enter, scaled by the position's own magnitude-weighted
    size (fit.params["weight_magnitude"], defaulting to 1.0 — a flat bet,
    today's behavior — for patterns with no magnitude column at all).
    Direction is applied separately via engine.py's own position sign, so
    the full realized weight is direction * weight_magnitude * ret.

    Disclosed asymmetry: engine.py's own turnover cost is charged on
    |position CHANGE| in {-1,0,1} space, unaffected by weight_magnitude —
    a 3x-magnitude-weighted bet pays the exact same entry/exit cost as a
    flat 1x bet. This is generous relative to a real, notional-proportional
    cost model, but changing engine.py's cost mechanism itself would touch
    every strategy in this project (pairs, momentum), not just this
    module's sizing refinement — out of scope here, flagged not fixed."""
    return fit.params.get("weight_magnitude", 1.0) * float(day_row["ret"])


def run_lowfreq_pattern_backtest(pattern: PatternSpec, raw_data: pd.DataFrame) -> ExperimentResult:
    """Same unmodified engine.py walk-forward as intraday_patterns.py,
    against 15-minute-bar-indexed raw_data. Only the pattern's own signal
    (and, if present, magnitude) column and `ret` are passed — the engine
    slices its window every bar, so a narrow frame keeps that cheap."""
    config = WalkForwardConfig(
        fit_window_days=INTRADAY_FIT_WINDOW_BARS, entry_z=0.0, exit_z=0.0, cost_bps=INTRADAY_COST_BPS
    )
    column = signal_column_for(pattern.pattern_id)
    mag_column = magnitude_column_for(pattern.pattern_id)
    columns = ["ret", column] + ([mag_column] if mag_column in raw_data.columns else [])
    narrow = raw_data[columns]
    return run_walk_forward(
        narrow,
        config,
        _make_column_fit_fn(column, mag_column if mag_column in raw_data.columns else None),
        realize_lowfreq_return,
        decide_position_fn=apply_pattern_signal_rule,
        direction_labels=("long", "short"),
    )


def _make_column_fit_fn(column: str, mag_column: str | None = None) -> Callable[[pd.DataFrame], StrategyFit]:
    """The signal column already encodes fire/direction, so the fit is a
    single scalar read — the z_score is a pure +1/-1 sign carrier for
    apply_pattern_signal_rule, exactly intraday_patterns' convention.
    mag_column is optional: None (a pattern with no magnitude column, or a
    caller-built raw_data frame that never added one, e.g. this module's
    own synthetic test fixtures) reads as a flat weight_magnitude of 1.0 —
    today's unweighted bet, unchanged."""

    def fit_fn(window: pd.DataFrame) -> StrategyFit:
        if window.empty:
            return StrategyFit(is_valid=False, z_score=None, fit_quality=None, params={})
        value = window[column].iloc[-1]
        if value == 0:
            return StrategyFit(is_valid=False, z_score=None, fit_quality=None, params={})
        weight_magnitude = float(window[mag_column].iloc[-1]) if mag_column is not None else 1.0
        return StrategyFit(
            is_valid=True,
            z_score=float(np.sign(value)),
            fit_quality=None,
            params={"weight_magnitude": weight_magnitude},
        )

    return fit_fn


# --- Performance-blind frequency verification ----------------------------


def simulate_round_trips(signal: np.ndarray) -> int:
    """Replays apply_pattern_signal_rule's position semantics over a bare
    signal sequence and counts round trips (flat -> non-flat entries).
    Deliberately return-blind: positions depend only on the signal
    sequence, never on returns, so this can verify the family's frequency
    design BEFORE the full run without peeking at any performance."""
    position = 0
    entries = 0
    for value in signal:
        new_position = apply_pattern_signal_rule(
            float(np.sign(value)) if value != 0 else 0.0, bool(value != 0), position, 0.0, 0.0
        )
        if position == 0 and new_position != 0:
            entries += 1
        position = new_position
    return entries


def estimate_trades_per_ticker_year(raw_data: pd.DataFrame, pattern: PatternSpec) -> float:
    """Round trips per year for one ticker, from the precomputed signal
    column alone (see simulate_round_trips — performance-blind)."""
    signal = raw_data[signal_column_for(pattern.pattern_id)].to_numpy()
    n_days = raw_data["trading_date"].nunique()
    years = n_days / TRADING_DAYS_PER_YEAR
    if years == 0:
        return 0.0
    return simulate_round_trips(signal) / years


# --- Pooled screening -----------------------------------------------------


@dataclass
class TickerPatternOutcome:
    """One (pattern, ticker) walk-forward, reduced to what pooling needs —
    small enough to ship across process boundaries from parallel workers.
    closed_trade_returns carries only CLOSED trades' returns (hit-rate's
    own convention, see metrics.hit_rate); n_trades counts all trades
    including a still-open final one, matching intraday_patterns."""

    daily_returns: pd.Series
    n_trades: int
    fired: bool
    closed_trade_returns: list[float]


@dataclass
class LowFreqPatternResult:
    pattern_id: str
    family: str
    citation: str
    n_tickers_in_basket: int
    n_tickers_fired: int
    n_trading_days: int
    n_trades: int
    trades_per_ticker_year: float  # this round's core design claim, surfaced per pattern
    sharpe_annualized: float
    hit_rate: float | None
    deflated_sharpe: DeflatedSharpeResult


@dataclass
class LowFreqScreeningSummary:
    """The family-level diagnostics this round exists to measure, surfaced
    first-class instead of buried in per-pattern results: sigma_SR (the
    spread of pooled Sharpes across the family) and SR0 (the expected max
    Sharpe of n_trials pure-noise trials at that sigma_SR — the bar a real
    edge must clear). The 212/420-family failure mode was sigma_SR ~2.9 ->
    SR0 ~8-9.5; a structurally homogeneous low-frequency family should
    bring both down to where the test can actually discriminate."""

    n_trials: int
    sigma_sr_annualized: float | None
    sr0_annualized: float | None
    results: list[LowFreqPatternResult]


def run_patterns_for_ticker(
    bars: pd.DataFrame, patterns: list[PatternSpec] | None = None
) -> dict[str, TickerPatternOutcome]:
    """All patterns against one ticker's bars — the unit of work parallel
    runners fan out across tickers (raw_data is built once per ticker, the
    expensive part, then each pattern's walk-forward reuses it)."""
    family = patterns if patterns is not None else LOW_FREQUENCY_PATTERN_FAMILY
    raw_data = build_lowfreq_raw_data(bars)
    outcomes: dict[str, TickerPatternOutcome] = {}
    if len(raw_data) <= INTRADAY_FIT_WINDOW_BARS:
        return outcomes
    for pattern in family:
        result = run_lowfreq_pattern_backtest(pattern, raw_data)
        outcomes[pattern.pattern_id] = TickerPatternOutcome(
            daily_returns=daily_returns_from_bar_equity(result.day_results),
            n_trades=len(result.trades),
            fired=bool(result.trades),
            closed_trade_returns=[t.trade_return for t in result.trades if not t.still_open],
        )
    return outcomes


def aggregate_ticker_outcomes(
    outcomes_by_ticker: dict[str, dict[str, TickerPatternOutcome]],
    patterns: list[PatternSpec] | None = None,
) -> LowFreqScreeningSummary:
    """Pools per-ticker outcomes into one equal-weighted basket per pattern
    and applies the DSR correction at n_trials = the family's literal,
    pre-declared size — the same trial-counting reasoning documented at
    length in intraday_patterns.screen_pattern_universe (pooling removes
    the which-ticker search dimension; n_trials covers the only dimension
    actually searched, pattern definitions; the family size is never
    shrunk to "however many happened to fire"). sigma_SR is the ddof=1
    std across every pattern's own pooled Sharpe from this same run."""
    family = patterns if patterns is not None else LOW_FREQUENCY_PATTERN_FAMILY
    n_trials = len(family)

    per_pattern_daily_returns: dict[str, pd.Series] = {}
    per_pattern_n_trades: dict[str, int] = {}
    per_pattern_n_in_basket: dict[str, int] = {}
    per_pattern_n_fired: dict[str, int] = {}
    per_pattern_closed_returns: dict[str, list[float]] = {}

    for pattern in family:
        ticker_daily_returns: dict[str, pd.Series] = {}
        n_trades = 0
        n_fired = 0
        closed_returns: list[float] = []
        for ticker, outcomes in outcomes_by_ticker.items():
            outcome = outcomes.get(pattern.pattern_id)
            if outcome is None:
                continue
            if not outcome.daily_returns.empty:
                ticker_daily_returns[ticker] = outcome.daily_returns
            n_trades += outcome.n_trades
            closed_returns.extend(outcome.closed_trade_returns)
            if outcome.fired:
                n_fired += 1

        if n_fired == 0:
            # Same honest-skip convention as intraday_patterns: a pattern
            # that never fired anywhere produced no signal to evaluate —
            # skipped from results, still counted in n_trials.
            continue

        pooled = pd.concat(ticker_daily_returns, axis=1).mean(axis=1, skipna=True).dropna()
        if len(pooled) < MIN_POOLED_TRADING_DAYS:
            continue

        per_pattern_daily_returns[pattern.pattern_id] = pooled
        per_pattern_n_trades[pattern.pattern_id] = n_trades
        per_pattern_n_in_basket[pattern.pattern_id] = len(ticker_daily_returns)
        per_pattern_n_fired[pattern.pattern_id] = n_fired
        per_pattern_closed_returns[pattern.pattern_id] = closed_returns

    sharpes = {pid: sharpe_ratio(returns) for pid, returns in per_pattern_daily_returns.items()}
    sigma_sr = float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None

    sr0_annualized: float | None = None
    if sigma_sr is not None:
        sr0_daily = expected_max_sharpe_under_noise(sigma_sr / np.sqrt(TRADING_DAYS_PER_YEAR), n_trials)
        if sr0_daily is not None:
            sr0_annualized = sr0_daily * float(np.sqrt(TRADING_DAYS_PER_YEAR))

    spec_by_id = {spec.pattern_id: spec for spec in family}
    results: list[LowFreqPatternResult] = []
    for pattern_id, pooled in per_pattern_daily_returns.items():
        spec = spec_by_id[pattern_id]
        n_in_basket = per_pattern_n_in_basket[pattern_id]
        years = len(pooled) / TRADING_DAYS_PER_YEAR
        trades_per_ticker_year = (
            per_pattern_n_trades[pattern_id] / n_in_basket / years if n_in_basket > 0 and years > 0 else 0.0
        )
        closed_returns = per_pattern_closed_returns[pattern_id]
        results.append(
            LowFreqPatternResult(
                pattern_id=pattern_id,
                family=spec.family,
                citation=spec.citation,
                n_tickers_in_basket=n_in_basket,
                n_tickers_fired=per_pattern_n_fired[pattern_id],
                n_trading_days=len(pooled),
                n_trades=per_pattern_n_trades[pattern_id],
                trades_per_ticker_year=trades_per_ticker_year,
                sharpe_annualized=sharpes[pattern_id],
                hit_rate=(
                    sum(1 for r in closed_returns if r > 0) / len(closed_returns) if closed_returns else None
                ),
                deflated_sharpe=compute_deflated_sharpe(sharpes[pattern_id], pooled, n_trials, sigma_sr),
            )
        )

    results.sort(key=lambda r: r.sharpe_annualized, reverse=True)
    return LowFreqScreeningSummary(
        n_trials=n_trials,
        sigma_sr_annualized=sigma_sr,
        sr0_annualized=sr0_annualized,
        results=results,
    )


def screen_lowfreq_pattern_universe(
    bars_by_ticker: dict[str, pd.DataFrame], patterns: list[PatternSpec] | None = None
) -> LowFreqScreeningSummary:
    """Serial convenience wrapper: run every ticker, then aggregate. A
    parallel runner calls run_patterns_for_ticker per worker (tickers are
    independent) and aggregate_ticker_outcomes once — identical results
    either way."""
    family = patterns if patterns is not None else LOW_FREQUENCY_PATTERN_FAMILY
    outcomes_by_ticker = {
        ticker: run_patterns_for_ticker(bars, family) for ticker, bars in bars_by_ticker.items()
    }
    return aggregate_ticker_outcomes(outcomes_by_ticker, family)
