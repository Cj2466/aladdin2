"""Tests for the Phase C structurally-low-frequency pattern family.

Synthetic-bar conventions: build_daily_frame/build_lowfreq_raw_data have no
minimum-bars-per-day requirement (no session phases in this family), so most
tests use compact 2-bars-per-day frames. The walk-forward tests must span
more than INTRADAY_FIT_WINDOW_BARS(=20) bars, i.e. >10 two-bar days."""

from datetime import date, timedelta
from functools import partial

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.intraday_patterns import (
    INTRADAY_COST_BPS,
    INTRADAY_FIT_WINDOW_BARS,
    PatternSpec,
)
from app.services.research_lab.low_frequency_patterns import (
    DAILY_SIGMA_LOOKBACK_DAYS,
    FAMILIES_WITHOUT_MAGNITUDE,
    HIGH252_LOOKBACK_DAYS,
    HIGH252_REFRACTORY_DAYS,
    LOW_FREQUENCY_PATTERN_FAMILY,
    MAX_FAMILY_SIZE,
    MAX_WEIGHT_MULTIPLE,
    LowFreqScreeningSummary,
    _fire_from_signal_column,
    _make_column_fit_fn,
    _third_friday,
    aggregate_ticker_outcomes,
    build_daily_frame,
    build_hold_and_magnitude_from_events,
    build_hold_from_events,
    build_lowfreq_raw_data,
    daily_returns_from_bar_equity,
    estimate_trades_per_ticker_year,
    magnitude_column_for,
    run_lowfreq_pattern_backtest,
    run_patterns_for_ticker,
    screen_lowfreq_pattern_universe,
    signal_column_for,
    simulate_round_trips,
)

NY = "America/New_York"


def make_bars(
    days: list[date],
    bars_per_day: int = 2,
    price_fn=None,
    volume_fn=None,
) -> pd.DataFrame:
    """Synthetic 15-minute-style OHLCV bars: `bars_per_day` bars per given
    trading day. price_fn(day_index, bar_index) -> (open, close);
    volume_fn(day_index) -> per-bar volume. Defaults: flat 100.0, volume
    1000."""
    rows = []
    index = []
    for d_i, d in enumerate(days):
        for b_i in range(bars_per_day):
            if price_fn is not None:
                bar_open, bar_close = price_fn(d_i, b_i)
            else:
                bar_open, bar_close = 100.0, 100.0
            volume = volume_fn(d_i) if volume_fn is not None else 1000.0
            rows.append(
                {
                    "open": bar_open,
                    "high": max(bar_open, bar_close),
                    "low": min(bar_open, bar_close),
                    "close": bar_close,
                    "volume": volume,
                }
            )
            index.append(
                pd.Timestamp(d) + pd.Timedelta(hours=9, minutes=30) + pd.Timedelta(minutes=15 * b_i)
            )
    df = pd.DataFrame(rows, index=pd.DatetimeIndex(index).tz_localize(NY))
    df.index.name = "timestamp"
    return df


def weekdays(start: date, n: int, skip: set[date] | None = None) -> list[date]:
    """The first n weekdays from `start`, optionally skipping given dates
    (simulated exchange holidays)."""
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5 and (skip is None or d not in skip):
            out.append(d)
        d += timedelta(days=1)
    return out


# --- Family invariants ----------------------------------------------------


def test_family_size_within_preregistered_ceiling():
    assert 20 <= len(LOW_FREQUENCY_PATTERN_FAMILY) <= MAX_FAMILY_SIZE
    assert len(LOW_FREQUENCY_PATTERN_FAMILY) == 28


def test_family_ids_unique_and_fully_cited():
    ids = [p.pattern_id for p in LOW_FREQUENCY_PATTERN_FAMILY]
    assert len(set(ids)) == len(ids)
    for spec in LOW_FREQUENCY_PATTERN_FAMILY:
        assert spec.citation.strip()
        assert spec.family.strip()


def test_every_pattern_gets_a_signal_column():
    days = weekdays(date(2024, 1, 1), 15)
    raw = build_lowfreq_raw_data(make_bars(days))
    for spec in LOW_FREQUENCY_PATTERN_FAMILY:
        column = signal_column_for(spec.pattern_id)
        assert column in raw.columns
        assert set(np.unique(raw[column])) <= {-1, 0, 1}


# --- build_hold_from_events ----------------------------------------------


def test_hold_placed_after_event_day():
    events = np.array([0, 0, 1, 0, 0, 0, 0], dtype=np.int8)
    hold = build_hold_from_events(events, hold_days=3)
    assert hold.tolist() == [0, 0, 0, 1, 1, 1, 0]


def test_later_event_overrides_overlap():
    events = np.array([0, 1, 0, -1, 0, 0, 0], dtype=np.int8)
    hold = build_hold_from_events(events, hold_days=3)
    # event at 1 sets days 2-4 to +1; event at 3 overrides days 4-6 to -1
    assert hold.tolist() == [0, 0, 1, 1, -1, -1, -1]


def test_refractory_suppresses_close_events():
    events = np.array([0, 1, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0], dtype=np.int8)
    hold = build_hold_from_events(events, hold_days=2, refractory_days=5)
    # event at 1 accepted (days 2-3); event at 3 suppressed (within 5 of 1);
    # event at 9 accepted (9 - 1 > 5) -> days 10-11
    assert hold.tolist() == [0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 1, 1]


def test_hold_truncates_at_series_end():
    events = np.array([0, 0, 0, 1], dtype=np.int8)
    hold = build_hold_from_events(events, hold_days=5)
    assert hold.tolist() == [0, 0, 0, 0]  # nothing left after the event day


# --- Magnitude-weighted sizing --------------------------------------------


def test_hold_from_events_is_a_thin_wrapper_over_magnitude_construction():
    # build_hold_from_events must stay byte-identical to before magnitude
    # weighting existed — proven structurally (it now delegates), re-proven
    # here against the original hand-checked fixtures.
    events = np.array([0, 1, 0, -1, 0, 0, 0], dtype=np.int8)
    hold = build_hold_from_events(events, hold_days=3)
    assert hold.tolist() == [0, 0, 1, 1, -1, -1, -1]


def test_hold_and_magnitude_carries_each_accepted_events_own_ratio():
    events = np.array([0, 1, 0, 0, 1, 0, 0, 0], dtype=np.int8)
    ratios = np.array([0.0, 2.0, 0.0, 0.0, 3.0, 0.0, 0.0, 0.0])
    hold, magnitude = build_hold_and_magnitude_from_events(events, ratios, hold_days=2, refractory_days=0)
    assert hold.tolist() == [0, 0, 1, 1, 0, 1, 1, 0]
    # off periods (hold==0) default to 1.0 — never read for P&L, but must
    # never silently look like a zero-weight bet.
    assert magnitude.tolist() == [1.0, 1.0, 2.0, 2.0, 1.0, 3.0, 3.0, 1.0]


def test_hold_and_magnitude_suppressed_event_never_contributes_its_ratio():
    events = np.array([0, 1, 0, 1, 0, 0, 0], dtype=np.int8)
    ratios = np.array([0.0, 2.0, 0.0, 5.0, 0.0, 0.0, 0.0])
    hold, magnitude = build_hold_and_magnitude_from_events(events, ratios, hold_days=3, refractory_days=5)
    assert hold.tolist() == [0, 0, 1, 1, 1, 0, 0]  # matches test_refractory_suppresses_close_events' shape
    assert magnitude.tolist() == [1.0, 1.0, 2.0, 2.0, 2.0, 1.0, 1.0]  # the suppressed 5.0 never appears


def test_families_without_magnitude_never_get_a_magnitude_column():
    days = weekdays(date(2024, 1, 1), 46)
    raw = build_lowfreq_raw_data(make_bars(days))
    for spec in LOW_FREQUENCY_PATTERN_FAMILY:
        has_column = magnitude_column_for(spec.pattern_id) in raw.columns
        if spec.family in FAMILIES_WITHOUT_MAGNITUDE:
            assert not has_column, spec.pattern_id
        else:
            assert has_column, spec.pattern_id


def test_extreme_move_magnitude_caps_at_max_weight_multiple_for_a_huge_move():
    n_days = DAILY_SIGMA_LOOKBACK_DAYS + 20
    event_day = DAILY_SIGMA_LOOKBACK_DAYS + 10
    bars = _alternating_then_event_bars(n_days, event_day, -0.10)  # a huge, many-sigma drop
    raw = build_lowfreq_raw_data(bars)
    days = sorted(raw["trading_date"].unique())
    mag = raw[magnitude_column_for("extreme_move_reversal_3s_2d")]

    event_bars = raw.index[raw["trading_date"] == days[event_day]]
    assert mag.loc[event_bars[-1]] == pytest.approx(MAX_WEIGHT_MULTIPLE)
    # held constant through the whole hold window
    hold_bars = raw.index[raw["trading_date"] == days[event_day + 1]]
    assert mag.loc[hold_bars[:-1]].tolist() == pytest.approx([MAX_WEIGHT_MULTIPLE] * len(hold_bars[:-1]))
    # back to flat once the hold ends
    after_bars = raw.index[raw["trading_date"] == days[event_day + 3]]
    assert mag.loc[after_bars].tolist() == pytest.approx([1.0] * len(after_bars))


def test_volume_shock_magnitude_is_exactly_one_at_the_threshold():
    n_days = 80
    event_day = 70

    def price_fn(d_i, b_i):
        level = 100.0 * (1.0 + (0.001 if d_i % 2 == 0 else -0.001))
        if d_i >= event_day:
            level = 108.0
        return level, level

    def volume_fn(d_i):
        return 5000.0 if d_i == event_day else 1000.0  # exactly 5x the (flat) prior median

    raw = build_lowfreq_raw_data(
        make_bars(weekdays(date(2021, 1, 4), n_days), price_fn=price_fn, volume_fn=volume_fn)
    )
    days = sorted(raw["trading_date"].unique())
    event_bars = raw.index[raw["trading_date"] == days[event_day]]
    mag = raw[magnitude_column_for("volume_shock_5x_confirmation")]
    assert mag.loc[event_bars[-1]] == pytest.approx(1.0)


def test_volume_shock_magnitude_scales_and_caps_above_the_threshold():
    n_days = 80
    event_day = 70

    def price_fn(d_i, b_i):
        level = 100.0 * (1.0 + (0.001 if d_i % 2 == 0 else -0.001))
        if d_i >= event_day:
            level = 108.0
        return level, level

    def volume_fn(d_i):
        return 50_000.0 if d_i == event_day else 1000.0  # 50x median, far past the 5x threshold

    raw = build_lowfreq_raw_data(
        make_bars(weekdays(date(2021, 1, 4), n_days), price_fn=price_fn, volume_fn=volume_fn)
    )
    days = sorted(raw["trading_date"].unique())
    event_bars = raw.index[raw["trading_date"] == days[event_day]]
    mag = raw[magnitude_column_for("volume_shock_5x_confirmation")]
    assert mag.loc[event_bars[-1]] == pytest.approx(MAX_WEIGHT_MULTIPLE)


def test_fit_fn_defaults_weight_magnitude_to_one_without_a_magnitude_column():
    fit_fn = _make_column_fit_fn("sig_x", None)
    window = pd.DataFrame({"sig_x": [0, 1]})
    fit = fit_fn(window)
    assert fit.params.get("weight_magnitude", 1.0) == 1.0


def test_fit_fn_reads_weight_magnitude_from_its_own_column():
    fit_fn = _make_column_fit_fn("sig_x", "mag_x")
    window = pd.DataFrame({"sig_x": [1, -1], "mag_x": [1.0, 2.5]})
    fit = fit_fn(window)
    assert fit.params["weight_magnitude"] == pytest.approx(2.5)


def test_magnitude_weighted_return_scales_realized_pnl():
    """The end-to-end integration proof: a 2.5x-magnitude-weighted hold
    realizes exactly 2.5x the flat-bet return (net of the SAME flat cost —
    see realize_lowfreq_return's disclosed cost-model asymmetry)."""
    n_days = 15
    gap_day = 12

    def price_fn(d_i, b_i):
        level = 110.0 if d_i >= gap_day else 100.0
        return level, level

    bars = make_bars(weekdays(date(2024, 1, 1), n_days), price_fn=price_fn)
    raw = build_lowfreq_raw_data(bars)

    pattern_id = "test_weighted_gap_hold"
    days = sorted(raw["trading_date"].unique())
    pos_for_bar = raw["trading_date"].map(lambda d: 1 if d == days[gap_day] else 0).to_numpy()
    signal = np.zeros(len(raw), dtype=np.int8)
    signal[:-1] = pos_for_bar[1:]
    raw[signal_column_for(pattern_id)] = signal
    magnitude = np.ones(len(raw), dtype=np.float64)
    magnitude[:-1] = np.where(pos_for_bar[1:] != 0, 2.5, 1.0)
    raw[magnitude_column_for(pattern_id)] = magnitude

    result = run_lowfreq_pattern_backtest(_spec_with_column(pattern_id), raw)
    daily_returns = daily_returns_from_bar_equity(result.day_results)
    cost = INTRADAY_COST_BPS / 10_000.0
    assert daily_returns.iloc[gap_day - 10] == pytest.approx(2.5 * 0.10 - cost, abs=1e-9)
    # exit-day cost is unaffected by magnitude (disclosed asymmetry).
    assert daily_returns.iloc[gap_day - 10 + 1] == pytest.approx(-cost, abs=1e-9)


# --- Calendar structure ---------------------------------------------------


def test_third_friday_known_examples():
    assert _third_friday(2024, 1) == date(2024, 1, 19)
    assert _third_friday(2024, 3) == date(2024, 3, 15)
    assert _third_friday(2021, 6) == date(2021, 6, 18)


def test_month_ordinals_and_preholiday_flags():
    holiday = date(2024, 1, 15)  # a Monday "holiday"
    days = weekdays(date(2024, 1, 1), 25, skip={holiday})
    daily = build_daily_frame(make_bars(days))

    assert daily.loc[date(2024, 1, 1), "month_ordinal"] == 1
    jan_days = [d for d in daily.index if d.month == 1]
    assert daily.loc[jan_days[-1], "month_reverse_ordinal"] == 1

    # Friday 2024-01-12 precedes the Monday holiday -> gap of 4 calendar days
    assert bool(daily.loc[date(2024, 1, 12), "is_preholiday"]) is True
    # A plain Friday->Monday weekend is NOT a pre-holiday
    assert bool(daily.loc[date(2024, 1, 5), "is_preholiday"]) is False
    # A plain mid-week day is not flagged
    assert bool(daily.loc[date(2024, 1, 3), "is_preholiday"]) is False
    # The final day in the data has no successor and is never flagged
    assert bool(daily.loc[daily.index[-1], "is_preholiday"]) is False


def test_opex_week_flags_and_holiday_shortened_expiry():
    # Third Friday of Jan 2024 is the 19th; week is Mon 15th - Fri 19th.
    days = weekdays(date(2024, 1, 1), 25)
    daily = build_daily_frame(make_bars(days))
    opex_days = [d for d in daily.index if daily.loc[d, "in_opex_week"]]
    assert opex_days == [date(2024, 1, d) for d in (15, 16, 17, 18, 19)]

    # If the expiration Friday itself is a holiday, the week still ends at
    # the last trading day <= that Friday (Thursday).
    days_gf = weekdays(date(2024, 1, 1), 25, skip={date(2024, 1, 19)})
    daily_gf = build_daily_frame(make_bars(days_gf))
    opex_days_gf = [d for d in daily_gf.index if daily_gf.loc[d, "in_opex_week"]]
    assert opex_days_gf == [date(2024, 1, d) for d in (15, 16, 17, 18)]


# --- Daily aggregation causality -----------------------------------------


def test_daily_frame_aggregates_and_sigma_is_prior_only():
    days = weekdays(date(2024, 1, 1), DAILY_SIGMA_LOOKBACK_DAYS + 10)

    def price_fn(d_i, b_i):
        # alternate small +/- moves so rolling std is positive
        base = 100.0 + (0.1 if d_i % 2 == 0 else -0.1)
        return base, base

    daily = build_daily_frame(make_bars(days, price_fn=price_fn))
    assert daily.loc[days[0], "day_open"] == pytest.approx(100.1)
    assert daily.loc[days[0], "day_volume"] == pytest.approx(2000.0)

    # sigma_prior on day d must equal the std of close_ret over the 60 days
    # ENDING d-1 — the event day's own return must not be included.
    d = days[DAILY_SIGMA_LOOKBACK_DAYS + 5]
    expected = daily["close_ret"].loc[: days[DAILY_SIGMA_LOOKBACK_DAYS + 4]].iloc[-DAILY_SIGMA_LOOKBACK_DAYS:].std(ddof=1)
    assert daily.loc[d, "sigma_prior"] == pytest.approx(float(expected))


def test_rsi_is_nan_for_a_dead_flat_series():
    days = weekdays(date(2024, 1, 1), 30)
    daily = build_daily_frame(make_bars(days))  # constant price
    assert daily["rsi"].isna().all()


# --- Signal columns fire where designed ----------------------------------


def _alternating_then_event_bars(n_days: int, event_day: int, event_return: float):
    def price_fn(d_i, b_i):
        if d_i < event_day:
            base = 100.0 * (1.0 + (0.001 if d_i % 2 == 0 else -0.001))
            return base, base
        if d_i == event_day:
            level = 100.0 * (1.0 + event_return)
            return level, level
        level = 100.0 * (1.0 + event_return)
        return level, level

    return make_bars(weekdays(date(2021, 1, 4), n_days), price_fn=price_fn)


def test_extreme_move_reversal_goes_long_after_a_multi_sigma_drop():
    n_days = DAILY_SIGMA_LOOKBACK_DAYS + 20
    event_day = DAILY_SIGMA_LOOKBACK_DAYS + 10
    bars = _alternating_then_event_bars(n_days, event_day, -0.10)
    raw = build_lowfreq_raw_data(bars)
    days = sorted(raw["trading_date"].unique())

    sig = raw[signal_column_for("extreme_move_reversal_3s_2d")]
    # signal turns long at the event day's LAST bar (position for the next
    # day's first bar), stays on through the 2-day hold, then flattens
    event_day_bars = raw.index[raw["trading_date"] == days[event_day]]
    assert sig.loc[event_day_bars[-1]] == 1
    hold_day_bars = raw.index[raw["trading_date"] == days[event_day + 1]]
    assert (sig.loc[hold_day_bars[:-1]] == 1).all()
    after_bars = raw.index[raw["trading_date"] == days[event_day + 3]]
    assert (sig.loc[after_bars] == 0).all()
    # continuation is the exact mirror
    sig_cont = raw[signal_column_for("extreme_move_continuation_3s_2d")]
    assert sig_cont.loc[event_day_bars[-1]] == -1
    # no firing anywhere before the event
    pre_bars = raw.index[raw["trading_date"] < days[event_day]]
    assert (sig.loc[pre_bars] == 0).all()


def test_gap_fade_fires_only_on_the_gap_day_and_exits_at_its_close():
    n_days = DAILY_SIGMA_LOOKBACK_DAYS + 20
    event_day = DAILY_SIGMA_LOOKBACK_DAYS + 10

    def price_fn(d_i, b_i):
        if d_i < event_day:
            base = 100.0 * (1.0 + (0.001 if d_i % 2 == 0 else -0.001))
            return base, base
        return 90.0, 90.0  # a huge overnight gap DOWN, flat intraday

    bars = make_bars(weekdays(date(2021, 1, 4), n_days), bars_per_day=4, price_fn=price_fn)
    raw = build_lowfreq_raw_data(bars)
    days = sorted(raw["trading_date"].unique())
    sig = raw[signal_column_for("gap_fade_2s")]

    event_bars = raw.index[raw["trading_date"] == days[event_day]]
    # long (fading the down-gap) on bars 1..last-1; flat again at the last bar
    assert (sig.loc[event_bars[:-1]] == 1).all()
    assert sig.loc[event_bars[-1]] == 0
    other_bars = raw.index[raw["trading_date"] != days[event_day]]
    assert (sig.loc[other_bars] == 0).all()
    # gap_follow is the mirror
    assert (raw.loc[event_bars[:-1], signal_column_for("gap_follow_2s")] == -1).all()


def test_turn_of_month_holds_the_designed_window():
    days = weekdays(date(2024, 1, 1), 46)  # spans Jan + Feb 2024
    raw = build_lowfreq_raw_data(make_bars(days))
    daily = build_daily_frame(make_bars(days))
    sig = raw[signal_column_for("turn_of_month_tom4_long")]

    held_days = sorted(
        {
            d
            for d in raw["trading_date"].unique()
            if (sig.loc[raw.index[raw["trading_date"] == d]] != 0).any()
        }
    )
    # position is held during: Jan 31 (day -1), Feb 1, 2, 5 (days +1..+3) —
    # the signal for a held day sits on the PRIOR day's last bar, so signal
    # activity also appears on Jan 30; the held-day set is what matters:
    in_window = [d for d in daily.index if daily.loc[d, "month_reverse_ordinal"] == 1 or daily.loc[d, "month_ordinal"] <= 3]
    # restrict to the fully-observed turn (Jan->Feb); January's own leading
    # days 1-3 are month_ordinal<=3 too (partial first month, disclosed)
    assert date(2024, 1, 31) in held_days
    assert date(2024, 2, 1) in held_days
    assert date(2024, 2, 5) in held_days
    assert date(2024, 2, 6) not in in_window


def test_preholiday_signal_held_exactly_on_the_preholiday_day():
    holiday = date(2024, 2, 19)  # Presidents' Day Monday
    days = weekdays(date(2024, 2, 1), 20, skip={holiday})
    raw = build_lowfreq_raw_data(make_bars(days))
    sig = raw[signal_column_for("preholiday_long")]
    preholiday_day = date(2024, 2, 16)  # the Friday before
    held_bars = raw.index[raw["trading_date"] == preholiday_day]
    assert (sig.loc[held_bars[:-1]] == 1).all()
    prior_day_bars = raw.index[raw["trading_date"] == date(2024, 2, 15)]
    assert sig.loc[prior_day_bars[-1]] == 1  # entry decided at prior close
    assert sig.loc[held_bars[-1]] == 0  # exit at the preholiday close


def test_high252_breakout_fires_once_then_respects_refractory():
    n_days = HIGH252_LOOKBACK_DAYS + 40
    breakout_day = HIGH252_LOOKBACK_DAYS + 10
    second_breakout = breakout_day + 5  # inside the 20-day refractory

    def price_fn(d_i, b_i):
        level = 100.0
        if d_i >= breakout_day:
            level = 110.0
        if d_i >= second_breakout:
            level = 120.0
        # tiny alternation so the series is not dead flat
        level *= 1.0 + (0.0001 if d_i % 2 == 0 else -0.0001)
        return level, level

    raw = build_lowfreq_raw_data(make_bars(weekdays(date(2021, 1, 4), n_days), price_fn=price_fn))
    days = sorted(raw["trading_date"].unique())
    sig = raw[signal_column_for("high252_breakout_continuation")]

    first_event_bars = raw.index[raw["trading_date"] == days[breakout_day]]
    assert sig.loc[first_event_bars[-1]] == 1
    # the second breakout is suppressed: after the first hold (10 days)
    # expires, and before the refractory (20 days) does, nothing re-fires
    gap_day = days[breakout_day + HIGH252_REFRACTORY_DAYS - 3]
    gap_bars = raw.index[raw["trading_date"] == gap_day]
    assert (sig.loc[gap_bars] == 0).all()


def test_volume_shock_direction_follows_the_days_return_sign():
    n_days = 80
    event_day = 70

    def price_fn(d_i, b_i):
        level = 100.0 * (1.0 + (0.001 if d_i % 2 == 0 else -0.001))
        if d_i >= event_day:
            level = 108.0
        return level, level

    def volume_fn(d_i):
        return 10_000.0 if d_i == event_day else 1000.0

    raw = build_lowfreq_raw_data(
        make_bars(weekdays(date(2021, 1, 4), n_days), price_fn=price_fn, volume_fn=volume_fn)
    )
    days = sorted(raw["trading_date"].unique())
    event_bars = raw.index[raw["trading_date"] == days[event_day]]
    # up-day on a 10x volume shock: confirmation goes long, climax reverses
    assert raw.loc[event_bars[-1], signal_column_for("volume_shock_5x_confirmation")] == 1
    assert raw.loc[event_bars[-1], signal_column_for("volume_shock_5x_climax_reversal")] == -1


def test_rsi_extreme_reversion_shorts_a_straight_up_march():
    def price_fn(d_i, b_i):
        return 100.0 * (1.01**d_i), 100.0 * (1.01**d_i)

    raw = build_lowfreq_raw_data(make_bars(weekdays(date(2021, 1, 4), 30), price_fn=price_fn))
    sig = raw[signal_column_for("rsi_daily_extreme_reversion")]
    assert (sig == -1).any()
    assert not (sig == 1).any()


# --- Price-causality: prefix invariance ----------------------------------


def test_signal_columns_are_prefix_invariant():
    """Mutating the FUTURE must not change past signals: building raw_data
    on a truncated copy reproduces the full build's signal columns on the
    shared prefix. Three comparison scopes, matching what each family may
    legitimately know in advance (calendar structure, never prices):
    price-driven patterns are exact up to the truncated frame's final bar
    (whose signal depends on whether a next trading day exists — calendar
    knowledge); preholiday additionally can't label the truncated final
    DAY (its successor gap is unobservable in the truncated data); and
    turn-of-month can't label the truncated final MONTH (the month's last
    trading day is calendar knowledge derived here from the data — a
    disclosed tail-of-sample artifact, see _add_calendar_columns)."""
    rng = np.random.default_rng(7)
    n_days = DAILY_SIGMA_LOOKBACK_DAYS + 30
    levels = 100.0 * np.cumprod(1.0 + rng.normal(0, 0.01, n_days))

    def price_fn(d_i, b_i):
        wiggle = 1.0 + (0.001 if b_i % 2 == 0 else -0.001)
        return levels[d_i] * wiggle, levels[d_i]

    bars = make_bars(weekdays(date(2021, 1, 4), n_days), bars_per_day=3, price_fn=price_fn)
    full = build_lowfreq_raw_data(bars)

    cut = len(bars) - 3 * 12  # truncate the last 12 days
    truncated = build_lowfreq_raw_data(bars.iloc[:cut])

    truncated_dates = truncated["trading_date"]
    last_day = truncated_dates.iloc[-1]
    before_last_day = int((truncated_dates < last_day).sum())
    last_month_start = date(last_day.year, last_day.month, 1)
    before_last_month = int((truncated_dates < last_month_start).sum())

    for spec in LOW_FREQUENCY_PATTERN_FAMILY:
        if spec.family == "turn_of_month":
            n_compare = before_last_month
        elif spec.family == "preholiday":
            n_compare = before_last_day
        else:
            n_compare = cut - 1
        column = signal_column_for(spec.pattern_id)
        pd.testing.assert_series_equal(
            full[column].iloc[:n_compare],
            truncated[column].iloc[:n_compare],
            check_names=False,
            obj=column,
        )


# --- Engine integration ---------------------------------------------------


def _spec_with_column(pattern_id: str) -> PatternSpec:
    return PatternSpec(
        pattern_id=pattern_id,
        family="test",
        citation="test",
        fire_fn=partial(_fire_from_signal_column, column=signal_column_for(pattern_id)),
    )


def test_multi_day_hold_captures_the_overnight_gap():
    """The close-to-close `ret` convention exists so a multi-day hold's
    overnight P&L is real: hold during day 12 only (entered at day 11's
    close), with a +10% overnight gap into day 12 and flat prices
    otherwise. The day-12 pooled return must be the gap minus one entry
    cost; day 13 carries only the exit cost."""
    n_days = 15
    gap_day = 12

    def price_fn(d_i, b_i):
        level = 110.0 if d_i >= gap_day else 100.0
        return level, level

    bars = make_bars(weekdays(date(2024, 1, 1), n_days), price_fn=price_fn)
    raw = build_lowfreq_raw_data(bars)

    pattern_id = "test_gap_hold"
    days = sorted(raw["trading_date"].unique())
    pos_for_bar = raw["trading_date"].map(lambda d: 1 if d == days[gap_day] else 0).to_numpy()
    signal = np.zeros(len(raw), dtype=np.int8)
    signal[:-1] = pos_for_bar[1:]
    raw[signal_column_for(pattern_id)] = signal

    result = run_lowfreq_pattern_backtest(_spec_with_column(pattern_id), raw)
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert not trade.still_open

    daily_returns = daily_returns_from_bar_equity(result.day_results)
    cost = INTRADAY_COST_BPS / 10_000.0
    # the walk-forward's out-of-sample span starts at bar 20 = synthetic day
    # 10, and daily_returns is positionally indexed (one entry per out-of-
    # sample trading day, in order) — the gap day (12) is its 3rd entry
    assert daily_returns.iloc[gap_day - 10] == pytest.approx(0.10 - cost, abs=1e-9)
    assert daily_returns.iloc[gap_day - 10 + 1] == pytest.approx(-cost, abs=1e-9)


def test_simulated_round_trips_match_engine_trade_count():
    rng = np.random.default_rng(3)
    n_days = 60
    levels = 100.0 * np.cumprod(1.0 + rng.normal(0, 0.01, n_days))

    def price_fn(d_i, b_i):
        return levels[d_i], levels[d_i] * (1.0 + 0.001 * (b_i % 2))

    bars = make_bars(weekdays(date(2024, 1, 1), n_days), price_fn=price_fn)
    raw = build_lowfreq_raw_data(bars)

    pattern_id = "test_sim_match"
    signal = np.zeros(len(raw), dtype=np.int8)
    # a few multi-bar holds, all safely after the fit window
    signal[30:36] = 1
    signal[50:53] = -1
    signal[70:80] = 1
    signal[90:91] = -1
    raw[signal_column_for(pattern_id)] = signal

    result = run_lowfreq_pattern_backtest(_spec_with_column(pattern_id), raw)
    assert simulate_round_trips(signal[INTRADAY_FIT_WINDOW_BARS - 1 :]) == len(result.trades)


def test_estimate_trades_per_ticker_year_counts_round_trips():
    days = weekdays(date(2024, 1, 1), 46)
    raw = build_lowfreq_raw_data(make_bars(days))
    tom_long = next(p for p in LOW_FREQUENCY_PATTERN_FAMILY if p.pattern_id == "turn_of_month_tom4_long")
    rate = estimate_trades_per_ticker_year(raw, tom_long)
    # 46 weekdays spanning one turn-of-month: roughly one round trip in
    # ~0.18 years -> on the order of 5-12 per year (January's partial
    # leading window merges into it at the series edge)
    assert rate > 0


# --- Pooled screening -----------------------------------------------------


def _screening_bars() -> pd.DataFrame:
    rng = np.random.default_rng(11)
    n_days = 70
    levels = 100.0 * np.cumprod(1.0 + rng.normal(0, 0.008, n_days))

    def price_fn(d_i, b_i):
        return levels[d_i] * (1.0 + 0.0005 * (b_i % 2)), levels[d_i]

    return make_bars(weekdays(date(2024, 1, 1), n_days), price_fn=price_fn)


def test_screening_counts_every_trial_and_reports_family_diagnostics():
    small_family = [
        p
        for p in LOW_FREQUENCY_PATTERN_FAMILY
        if p.pattern_id
        in ("turn_of_month_tom4_long", "turn_of_month_tom4_short", "opex_week_long", "opex_week_short", "preholiday_long")
    ]
    bars_by_ticker = {"AAA": _screening_bars(), "BBB": _screening_bars()}
    summary = screen_lowfreq_pattern_universe(bars_by_ticker, patterns=small_family)

    assert isinstance(summary, LowFreqScreeningSummary)
    assert summary.n_trials == len(small_family)
    assert summary.results  # calendar patterns always fire
    for result in summary.results:
        assert result.deflated_sharpe.n_trials == len(small_family)
        assert result.trades_per_ticker_year > 0
        assert result.n_tickers_in_basket == 2
    # >=2 pooled Sharpes -> the family diagnostics are measurable
    if len(summary.results) >= 2:
        assert summary.sigma_sr_annualized is not None
        assert summary.sr0_annualized is not None and summary.sr0_annualized > 0
    sharpes = [r.sharpe_annualized for r in summary.results]
    assert sharpes == sorted(sharpes, reverse=True)


def test_parallel_and_serial_screening_paths_agree():
    small_family = [
        p
        for p in LOW_FREQUENCY_PATTERN_FAMILY
        if p.pattern_id in ("turn_of_month_tom4_long", "opex_week_short")
    ]
    bars_by_ticker = {"AAA": _screening_bars(), "BBB": _screening_bars()}

    serial = screen_lowfreq_pattern_universe(bars_by_ticker, patterns=small_family)
    outcomes = {t: run_patterns_for_ticker(b, small_family) for t, b in bars_by_ticker.items()}
    parallel = aggregate_ticker_outcomes(outcomes, small_family)

    assert [r.pattern_id for r in serial.results] == [r.pattern_id for r in parallel.results]
    for a, b in zip(serial.results, parallel.results):
        assert a.sharpe_annualized == pytest.approx(b.sharpe_annualized)
        assert a.n_trades == b.n_trades
        assert a.hit_rate == b.hit_rate
    assert serial.sigma_sr_annualized == pytest.approx(parallel.sigma_sr_annualized)


def test_pattern_that_never_fires_is_skipped_but_still_a_trial():
    # dead-flat bars: no volatility-triggered pattern can fire; calendar
    # patterns still do
    family = [
        p
        for p in LOW_FREQUENCY_PATTERN_FAMILY
        if p.pattern_id in ("extreme_move_reversal_4s_5d", "turn_of_month_tom4_long", "opex_week_long", "preholiday_long", "opex_week_short")
    ]
    bars_by_ticker = {"AAA": _screening_bars()}
    summary = screen_lowfreq_pattern_universe(bars_by_ticker, patterns=family)
    assert summary.n_trials == 5
    result_ids = {r.pattern_id for r in summary.results}
    assert "extreme_move_reversal_4s_5d" not in result_ids  # never fired on this data
    for result in summary.results:
        assert result.deflated_sharpe.n_trials == 5  # trials never shrink
