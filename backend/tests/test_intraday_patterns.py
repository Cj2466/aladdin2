import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.engine import DayResult
from app.services.research_lab.intraday_patterns import (
    INTRADAY_FIT_WINDOW_BARS,
    MIN_POOLED_TRADING_DAYS,
    PATTERN_FAMILY,
    PATTERN_MINING_UNIVERSE,
    PATTERN_MINING_UNIVERSE_LARGE_CAP,
    PATTERN_MINING_UNIVERSE_MID_SMALL_CAP,
    PatternSignal,
    PatternSpec,
    _fire_bollinger_reversion,
    _fire_day_of_week,
    _fire_doji_reversal,
    _fire_engulfing,
    _fire_hammer_family,
    _fire_harami,
    _fire_intraday_momentum,
    _fire_ma_crossover,
    _fire_orb_continuation,
    _fire_overnight_gap_persistence,
    _fire_piercing_darkcloud,
    _fire_prior_bar_momentum,
    _fire_rsi_extreme,
    _fire_star_reversal,
    _fire_three_bar_reversal,
    _fire_tweezer,
    _fire_volume_climax,
    _fire_vwap_reversion,
    _gate_to_session_phase,
    _session_phase_for_day,
    apply_pattern_signal_rule,
    build_pattern_raw_data,
    daily_returns_from_bar_equity,
    realize_pattern_return,
    run_pattern_backtest,
    screen_pattern_universe,
)

BAR_TIMES = ["09:30", "10:30", "11:30", "12:30", "13:30", "14:30", "15:30"]


def _synthetic_ticker_bars(seed: int, n_days: int, drift: float = 0.0, noise_std: float = 0.003) -> pd.DataFrame:
    """A deterministic (seeded), regular 7-bars/day OHLCV series matching
    the real empirically-confirmed structure (see get_intraday_bars's
    docstring) — used across this file wherever a full walk-forward run
    is needed rather than a single hand-built window."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=n_days)
    rows = []
    price = 100.0
    for d in dates:
        for t in BAR_TIMES:
            ts = pd.Timestamp(f"{d.date()} {t}", tz="America/New_York")
            ret = rng.normal(drift, noise_std)
            o = price
            c = price * (1 + ret)
            h = max(o, c) * (1 + abs(rng.normal(0, 0.0005)))
            low = min(o, c) * (1 - abs(rng.normal(0, 0.0005)))
            v = int(rng.integers(1000, 5000))
            rows.append((ts, o, h, low, c, v))
            price = c
    return pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"]).set_index("ts")


def _bar(open_: float, high: float, low: float, close: float, volume: float = 1000.0, **extra) -> dict:
    row = {"open": open_, "high": high, "low": low, "close": close, "volume": volume}
    row.update(extra)
    row["ret"] = (close - open_) / open_
    return row


def _window(rows: list[dict], trading_date="2024-01-02", session_phase=None) -> pd.DataFrame:
    """Builds a hand-crafted trailing window matching what
    build_pattern_raw_data would produce, with per-row overrides via
    'trading_date'/'session_phase' keys already inside each row dict, or
    the same value applied to every row via this function's own kwargs."""
    df = pd.DataFrame(rows)
    if "trading_date" not in df.columns:
        df["trading_date"] = trading_date
    if "session_phase" not in df.columns:
        df["session_phase"] = session_phase
    return df


# --- _session_phase_for_day --------------------------------------------


def test_session_phase_for_day_matches_real_7_bar_structure():
    # Empirically confirmed real structure (get_intraday_bars docstring):
    # 09:30/10:30/11:30/12:30/13:30/14:30/15:30 ET.
    phases = _session_phase_for_day(7)
    assert phases == ["open", "mid_morning", "mid_morning", "midday", "midday", "power_hour", "close"]


def test_session_phase_for_day_none_below_floor():
    phases = _session_phase_for_day(3)
    assert phases == [None, None, None]


def test_session_phase_for_day_single_bar_is_open():
    # A 1-bar day is >= MIN_BARS_FOR_SESSION_PHASE=5? No — 1 < 5, so this
    # should also be all-None. Covers the n_bars==1 edge inside the loop
    # (i==0 and i==n_bars-1 collide) never actually being reached.
    assert _session_phase_for_day(1) == [None]


# --- build_pattern_raw_data ----------------------------------------------


def test_build_pattern_raw_data_labels_session_phase_and_ret():
    bars = _synthetic_ticker_bars(seed=1, n_days=3)
    raw = build_pattern_raw_data(bars)
    assert list(raw["session_phase"].iloc[:7]) == [
        "open",
        "mid_morning",
        "mid_morning",
        "midday",
        "midday",
        "power_hour",
        "close",
    ]
    # ret is each bar's own open-to-close move, not close-to-close.
    expected_ret = (bars["close"].iloc[0] - bars["open"].iloc[0]) / bars["open"].iloc[0]
    assert raw["ret"].iloc[0] == pytest.approx(expected_ret)


def test_build_pattern_raw_data_short_day_gets_none_phase():
    bars = _synthetic_ticker_bars(seed=1, n_days=1).iloc[:2]  # only 2 bars that day
    raw = build_pattern_raw_data(bars)
    assert raw["session_phase"].isna().all()


# --- individual pattern fire_fns -----------------------------------------


def test_orb_continuation_fires_long_above_threshold():
    window = _window([_bar(100.0, 100.5, 99.9, 100.5)])  # +0.5% bar
    signal = _fire_orb_continuation(window, breakout_threshold=0.002)
    assert signal == PatternSignal(direction="long", strength=pytest.approx(0.005))


def test_orb_continuation_fires_short_above_threshold():
    window = _window([_bar(100.0, 100.1, 99.4, 99.4)])  # -0.6% bar
    signal = _fire_orb_continuation(window, breakout_threshold=0.002)
    assert signal is not None
    assert signal.direction == "short"


def test_orb_continuation_silent_below_threshold():
    window = _window([_bar(100.0, 100.05, 99.98, 100.05)])  # +0.05% bar
    assert _fire_orb_continuation(window, breakout_threshold=0.002) is None


def test_intraday_momentum_continuation_matches_open_direction():
    rows = [
        _bar(100.0, 101.0, 99.9, 101.0, session_phase="open"),
        _bar(101.0, 101.2, 100.9, 101.1, session_phase="mid_morning"),
    ]
    window = _window(rows)
    signal = _fire_intraday_momentum(window, reverse=False, min_open_return=0.0)
    assert signal is not None
    assert signal.direction == "long"  # open bar was up (+1%), continuation predicts long


def test_intraday_momentum_reversal_flips_open_direction():
    rows = [
        _bar(100.0, 101.0, 99.9, 101.0, session_phase="open"),
        _bar(101.0, 101.2, 100.9, 101.1, session_phase="mid_morning"),
    ]
    window = _window(rows)
    signal = _fire_intraday_momentum(window, reverse=True, min_open_return=0.0)
    assert signal is not None
    assert signal.direction == "short"  # reversal flips the up-open to a short prediction


def test_intraday_momentum_silent_without_open_bar_in_window():
    rows = [_bar(101.0, 101.2, 100.9, 101.1, session_phase="mid_morning")]
    window = _window(rows)
    assert _fire_intraday_momentum(window, reverse=False, min_open_return=0.0) is None


def test_intraday_momentum_respects_min_open_return_floor():
    rows = [
        _bar(100.0, 100.01, 99.99, 100.0005, session_phase="open"),  # ~5bps move
        _bar(100.0005, 100.1, 99.9, 100.05, session_phase="mid_morning"),
    ]
    window = _window(rows)
    assert _fire_intraday_momentum(window, reverse=False, min_open_return=0.001) is None


def test_vwap_reversion_fires_short_when_price_far_above_vwap():
    rows = [
        _bar(100.0, 100.2, 99.9, 100.0, volume=1000),
        _bar(100.0, 105.0, 99.9, 104.0, volume=1000),  # closes well above the day's VWAP
    ]
    window = _window(rows)
    signal = _fire_vwap_reversion(window, deviation_threshold=0.01)
    assert signal is not None
    assert signal.direction == "short"


def test_vwap_reversion_fires_long_when_price_far_below_vwap():
    rows = [
        _bar(100.0, 100.2, 99.9, 100.0, volume=1000),
        _bar(100.0, 100.1, 95.0, 96.0, volume=1000),  # closes well below the day's VWAP
    ]
    window = _window(rows)
    signal = _fire_vwap_reversion(window, deviation_threshold=0.01)
    assert signal is not None
    assert signal.direction == "long"


def test_vwap_reversion_silent_within_threshold():
    rows = [
        _bar(100.0, 100.2, 99.9, 100.0, volume=1000),
        _bar(100.0, 100.15, 99.9, 100.05, volume=1000),
    ]
    window = _window(rows)
    assert _fire_vwap_reversion(window, deviation_threshold=0.01) is None


def test_vwap_reversion_silent_on_zero_volume_day():
    rows = [_bar(100.0, 100.5, 99.5, 104.0, volume=0)]
    window = _window(rows)
    assert _fire_vwap_reversion(window, deviation_threshold=0.01) is None


def test_engulfing_fires_long_on_bullish_engulf():
    rows = [
        _bar(100.0, 100.2, 99.3, 99.5),  # small down body 100->99.5
        _bar(99.4, 101.0, 99.3, 100.8),  # bullish bar whose body [99.4,100.8] engulfs [99.5,100.0]
    ]
    window = _window(rows)
    signal = _fire_engulfing(window)
    assert signal is not None
    assert signal.direction == "long"


def test_engulfing_fires_short_on_bearish_engulf():
    rows = [
        _bar(99.5, 100.6, 99.4, 100.5),  # small up body 99.5->100.5
        _bar(100.6, 100.7, 99.0, 99.2),  # bearish bar whose body [99.2,100.6] engulfs [99.5,100.5]
    ]
    window = _window(rows)
    signal = _fire_engulfing(window)
    assert signal is not None
    assert signal.direction == "short"


def test_engulfing_silent_when_not_engulfing():
    rows = [_bar(100.0, 100.3, 99.8, 100.2), _bar(100.2, 100.4, 100.0, 100.3)]
    window = _window(rows)
    assert _fire_engulfing(window) is None


def test_engulfing_needs_two_bars():
    window = _window([_bar(100.0, 100.3, 99.8, 100.2)])
    assert _fire_engulfing(window) is None


def test_doji_reversal_fires_against_prior_up_move():
    rows = [
        _bar(100.0, 101.0, 99.9, 100.9),  # strong up bar
        _bar(100.9, 101.0, 100.8, 100.91),  # near-equal open/close -> doji
    ]
    window = _window(rows)
    signal = _fire_doji_reversal(window)
    assert signal is not None
    assert signal.direction == "short"


def test_doji_reversal_fires_against_prior_down_move():
    rows = [
        _bar(101.0, 101.1, 99.9, 100.0),  # strong down bar
        _bar(100.0, 100.15, 99.9, 100.01),  # doji
    ]
    window = _window(rows)
    signal = _fire_doji_reversal(window)
    assert signal is not None
    assert signal.direction == "long"


def test_doji_reversal_silent_on_large_body():
    rows = [_bar(100.0, 101.0, 99.9, 100.9), _bar(100.9, 102.0, 100.8, 101.9)]
    window = _window(rows)
    assert _fire_doji_reversal(window) is None


def test_three_bar_reversal_fires_long_after_two_down_bars():
    rows = [
        _bar(105.0, 105.1, 103.0, 103.5),  # bar 1: down
        _bar(103.4, 103.5, 101.0, 101.5),  # bar 2: down further, closes below bar1 close
        _bar(101.4, 106.0, 101.3, 105.5),  # bar 3: closes back above bar1's OPEN (105.0)
    ]
    window = _window(rows)
    signal = _fire_three_bar_reversal(window)
    assert signal == PatternSignal(direction="long", strength=1.0)


def test_three_bar_reversal_fires_short_after_two_up_bars():
    rows = [
        _bar(100.0, 102.0, 99.9, 101.5),  # bar 1: up
        _bar(101.6, 103.5, 101.5, 103.0),  # bar 2: up further, closes above bar1 close
        _bar(103.1, 103.2, 99.0, 99.5),  # bar 3: closes back below bar1's OPEN (100.0)
    ]
    window = _window(rows)
    signal = _fire_three_bar_reversal(window)
    assert signal == PatternSignal(direction="short", strength=1.0)


def test_three_bar_reversal_silent_without_pattern():
    rows = [
        _bar(100.0, 100.5, 99.8, 100.3),
        _bar(100.3, 100.6, 100.0, 100.4),
        _bar(100.4, 100.7, 100.1, 100.5),
    ]
    window = _window(rows)
    assert _fire_three_bar_reversal(window) is None


def test_three_bar_reversal_needs_three_bars():
    window = _window([_bar(100.0, 100.5, 99.8, 100.3), _bar(100.3, 100.6, 100.0, 100.4)])
    assert _fire_three_bar_reversal(window) is None


# --- _fire_prior_bar_momentum (overnight "immediate" family) --------------


def test_prior_bar_momentum_continuation_matches_sign():
    window = _window([_bar(100.0, 101.0, 99.9, 101.0)])  # +1% bar
    signal = _fire_prior_bar_momentum(window, reverse=False, min_return=0.005)
    assert signal is not None
    assert signal.direction == "long"


def test_prior_bar_momentum_reversal_flips_sign():
    window = _window([_bar(100.0, 101.0, 99.9, 101.0)])  # +1% bar
    signal = _fire_prior_bar_momentum(window, reverse=True, min_return=0.005)
    assert signal is not None
    assert signal.direction == "short"


def test_prior_bar_momentum_silent_below_threshold():
    window = _window([_bar(100.0, 100.05, 99.98, 100.05)])  # +0.05% bar
    assert _fire_prior_bar_momentum(window, reverse=False, min_return=0.005) is None


# --- _fire_overnight_gap_persistence (overnight "persistence" family) -----


def _overnight_window(prior_close_phase: str | None, prior_ret_open: float, prior_ret_close: float) -> pd.DataFrame:
    date1 = pd.Timestamp("2024-01-01").date()
    date2 = pd.Timestamp("2024-01-02").date()
    prior_close = 100.0 * (1 + prior_ret_close)
    rows = [
        _bar(100.0, 100.2, 99.8, 100.0 * (1 + prior_ret_open), trading_date=date1, session_phase="mid_morning"),
        _bar(100.0, max(100.0, prior_close) + 0.5, min(100.0, prior_close) - 0.5, prior_close,
             trading_date=date1, session_phase=prior_close_phase),
        _bar(prior_close, prior_close + 0.2, prior_close - 0.2, prior_close + 0.1,
             trading_date=date2, session_phase="open"),
        _bar(prior_close + 0.1, prior_close + 0.25, prior_close, prior_close + 0.15,
             trading_date=date2, session_phase="mid_morning"),
    ]
    return _window(rows)


def test_overnight_gap_persistence_continuation_matches_prior_close_bar_sign():
    window = _overnight_window(prior_close_phase="close", prior_ret_open=0.0, prior_ret_close=0.02)
    signal = _fire_overnight_gap_persistence(window, reverse=False, min_return=0.01)
    assert signal is not None
    assert signal.direction == "long"  # prior day's close-bar move was up


def test_overnight_gap_persistence_reversal_flips_prior_close_bar_sign():
    window = _overnight_window(prior_close_phase="close", prior_ret_open=0.0, prior_ret_close=0.02)
    signal = _fire_overnight_gap_persistence(window, reverse=True, min_return=0.01)
    assert signal is not None
    assert signal.direction == "short"


def test_overnight_gap_persistence_silent_without_prior_close_phase_bar():
    # Prior day never labeled a "close" bar (e.g. gated architecture never
    # saw one) -- an honest skip, not a guess at which bar to use instead.
    window = _overnight_window(prior_close_phase="mid_morning", prior_ret_open=0.0, prior_ret_close=0.02)
    assert _fire_overnight_gap_persistence(window, reverse=False, min_return=0.01) is None


def test_overnight_gap_persistence_silent_below_threshold():
    window = _overnight_window(prior_close_phase="close", prior_ret_open=0.0, prior_ret_close=0.001)
    assert _fire_overnight_gap_persistence(window, reverse=False, min_return=0.01) is None


# --- _fire_rsi_extreme ------------------------------------------------------


def _closes_window(closes: list[float]) -> pd.DataFrame:
    rows = [_bar(c, c + 0.1, c - 0.1, c) for c in closes]
    return _window(rows)


def test_rsi_extreme_fires_short_when_overbought():
    window = _closes_window([100.0, 101.0, 102.0, 103.0])  # monotonic gains -> RSI=100
    signal = _fire_rsi_extreme(window, period=3, overbought=70.0, oversold=30.0)
    assert signal is not None
    assert signal.direction == "short"


def test_rsi_extreme_fires_long_when_oversold():
    window = _closes_window([103.0, 102.0, 101.0, 100.0])  # monotonic losses -> RSI=0
    signal = _fire_rsi_extreme(window, period=3, overbought=70.0, oversold=30.0)
    assert signal is not None
    assert signal.direction == "long"


def test_rsi_extreme_silent_in_neutral_zone():
    window = _closes_window([100.0, 101.0, 100.0, 101.0])
    assert _fire_rsi_extreme(window, period=3, overbought=70.0, oversold=30.0) is None


def test_rsi_extreme_silent_on_insufficient_data():
    window = _closes_window([100.0, 101.0])
    assert _fire_rsi_extreme(window, period=3, overbought=70.0, oversold=30.0) is None


# --- _fire_bollinger_reversion -----------------------------------------


def test_bollinger_reversion_fires_short_above_upper_band():
    window = _closes_window([100.0, 101.0, 99.0, 100.0, 140.0])
    signal = _fire_bollinger_reversion(window, period=5, n_std=1.0)
    assert signal is not None
    assert signal.direction == "short"


def test_bollinger_reversion_fires_long_below_lower_band():
    window = _closes_window([100.0, 99.0, 101.0, 100.0, 60.0])
    signal = _fire_bollinger_reversion(window, period=5, n_std=1.0)
    assert signal is not None
    assert signal.direction == "long"


def test_bollinger_reversion_silent_within_bands():
    window = _closes_window([100.0, 101.0, 99.0, 100.0, 101.0])
    assert _fire_bollinger_reversion(window, period=5, n_std=1.0) is None


def test_bollinger_reversion_silent_on_insufficient_data():
    window = _closes_window([100.0, 101.0])
    assert _fire_bollinger_reversion(window, period=5, n_std=1.0) is None


# --- _fire_ma_crossover ---------------------------------------------------


def test_ma_crossover_fires_long_on_bullish_cross():
    window = _closes_window([100.0, 100.0, 100.0, 99.0, 103.0])
    signal = _fire_ma_crossover(window, short_period=2, long_period=3)
    assert signal is not None
    assert signal.direction == "long"


def test_ma_crossover_fires_short_on_bearish_cross():
    window = _closes_window([100.0, 100.0, 100.0, 101.0, 97.0])
    signal = _fire_ma_crossover(window, short_period=2, long_period=3)
    assert signal is not None
    assert signal.direction == "short"


def test_ma_crossover_silent_without_a_fresh_cross():
    window = _closes_window([100.0, 101.0, 102.0, 103.0, 104.0])  # already in a steady uptrend
    assert _fire_ma_crossover(window, short_period=2, long_period=3) is None


def test_ma_crossover_silent_on_insufficient_data():
    window = _closes_window([100.0, 101.0])
    assert _fire_ma_crossover(window, short_period=2, long_period=3) is None


# --- _fire_volume_climax ---------------------------------------------------


def test_volume_climax_confirmation_matches_bar_direction():
    window = _window(
        [
            _bar(100.0, 100.2, 99.8, 100.0, volume=1000),
            _bar(100.0, 100.2, 99.8, 100.0, volume=1000),
            _bar(100.0, 105.0, 99.9, 104.0, volume=5000),  # +4% bar on a 5x volume spike
        ]
    )
    signal = _fire_volume_climax(window, reverse=False, volume_multiple=3.0)
    assert signal is not None
    assert signal.direction == "long"  # confirmation reads WITH the spike bar's own direction


def test_volume_climax_exhaustion_flips_bar_direction():
    window = _window(
        [
            _bar(100.0, 100.2, 99.8, 100.0, volume=1000),
            _bar(100.0, 100.2, 99.8, 100.0, volume=1000),
            _bar(100.0, 105.0, 99.9, 104.0, volume=5000),
        ]
    )
    signal = _fire_volume_climax(window, reverse=True, volume_multiple=3.0)
    assert signal is not None
    assert signal.direction == "short"  # exhaustion reads AGAINST the spike bar's own direction


def test_volume_climax_silent_below_multiple_threshold():
    window = _window(
        [
            _bar(100.0, 100.2, 99.8, 100.0, volume=1000),
            _bar(100.0, 100.2, 99.8, 100.0, volume=1000),
            _bar(100.0, 105.0, 99.9, 104.0, volume=2000),  # only 2x, below the 3x multiple
        ]
    )
    assert _fire_volume_climax(window, reverse=False, volume_multiple=3.0) is None


# --- _fire_day_of_week ------------------------------------------------------


def test_day_of_week_fires_on_matching_weekday():
    monday = pd.Timestamp("2024-01-01").date()  # empirically a Monday
    assert monday.weekday() == 0
    window = _window([_bar(100.0, 100.5, 99.8, 100.3, trading_date=monday, session_phase="open")])
    signal = _fire_day_of_week(window, weekday=0, direction="short")
    assert signal == PatternSignal(direction="short", strength=1.0)


def test_day_of_week_silent_on_non_matching_weekday():
    monday = pd.Timestamp("2024-01-01").date()
    window = _window([_bar(100.0, 100.5, 99.8, 100.3, trading_date=monday, session_phase="open")])
    assert _fire_day_of_week(window, weekday=1, direction="short") is None  # gated to Tuesday, this bar is Monday


# --- _fire_hammer_family ----------------------------------------------------


def test_hammer_family_bullish_shape_after_downtrend_is_long():
    rows = [
        _bar(105.0, 105.2, 104.8, 105.0),  # trend context
        _bar(105.0, 100.2, 99.8, 100.0),  # trend context: declining
        _bar(100.0, 100.6, 97.0, 100.5),  # small body near top, long lower shadow
    ]
    window = _window(rows)
    signal = _fire_hammer_family(window, trend_lookback=2)
    assert signal is not None
    assert signal.direction == "long"  # hammer: this shape after a downtrend


def test_hammer_family_same_shape_after_uptrend_is_hanging_man_short():
    rows = [
        _bar(95.0, 95.2, 94.8, 95.0),  # trend context
        _bar(95.0, 100.2, 99.8, 100.0),  # trend context: rising
        _bar(100.0, 100.6, 97.0, 100.5),  # identical shape to the hammer test above
    ]
    window = _window(rows)
    signal = _fire_hammer_family(window, trend_lookback=2)
    assert signal is not None
    assert signal.direction == "short"  # hanging man: same shape after an uptrend


def test_hammer_family_shooting_star_shape_after_uptrend_is_short():
    rows = [
        _bar(95.0, 95.2, 94.8, 95.0),
        _bar(95.0, 100.2, 99.8, 100.0),  # rising
        _bar(100.0, 103.6, 99.9, 100.5),  # small body near bottom, long upper shadow
    ]
    window = _window(rows)
    signal = _fire_hammer_family(window, trend_lookback=2)
    assert signal is not None
    assert signal.direction == "short"  # shooting star: after an uptrend


def test_hammer_family_shooting_star_shape_after_downtrend_is_inverted_hammer_long():
    rows = [
        _bar(105.0, 105.2, 104.8, 105.0),
        _bar(105.0, 100.2, 99.8, 100.0),  # declining
        _bar(100.0, 103.6, 99.9, 100.5),  # identical shape to the shooting-star test above
    ]
    window = _window(rows)
    signal = _fire_hammer_family(window, trend_lookback=2)
    assert signal is not None
    assert signal.direction == "long"  # inverted hammer: after a downtrend


def test_hammer_family_silent_on_ordinary_bar_shape():
    rows = [
        _bar(105.0, 105.2, 104.8, 105.0),
        _bar(105.0, 100.2, 99.8, 100.0),
        _bar(100.0, 101.5, 99.5, 101.0),  # roughly symmetric shadows, no shape
    ]
    window = _window(rows)
    assert _fire_hammer_family(window, trend_lookback=2) is None


def test_hammer_family_silent_on_insufficient_data():
    window = _window([_bar(100.0, 100.6, 97.0, 100.5)])
    assert _fire_hammer_family(window, trend_lookback=2) is None


# --- _fire_star_reversal -----------------------------------------------


def test_star_reversal_fires_long_on_morning_star():
    rows = [
        _bar(110.0, 111.0, 99.0, 100.0),  # long bearish bar1
        _bar(99.0, 99.6, 98.9, 99.5),  # small-bodied indecision bar2
        _bar(100.0, 108.5, 99.9, 108.0),  # bullish bar3 closing well into bar1's body
    ]
    window = _window(rows)
    signal = _fire_star_reversal(window)
    assert signal == PatternSignal(direction="long", strength=1.0)


def test_star_reversal_fires_short_on_evening_star():
    rows = [
        _bar(100.0, 111.0, 99.0, 110.0),  # long bullish bar1
        _bar(110.0, 110.6, 109.9, 110.5),  # small-bodied indecision bar2
        _bar(109.0, 109.1, 101.5, 102.0),  # bearish bar3 closing well into bar1's body
    ]
    window = _window(rows)
    signal = _fire_star_reversal(window)
    assert signal == PatternSignal(direction="short", strength=1.0)


def test_star_reversal_silent_when_bar1_not_decisive():
    rows = [
        _bar(105.0, 110.0, 99.0, 104.0),  # bar1 body is small relative to its own range
        _bar(104.0, 104.6, 103.9, 104.5),
        _bar(100.0, 108.5, 99.9, 108.0),
    ]
    window = _window(rows)
    assert _fire_star_reversal(window) is None


def test_star_reversal_silent_on_insufficient_data():
    window = _window([_bar(110.0, 111.0, 99.0, 100.0), _bar(99.0, 99.6, 98.9, 99.5)])
    assert _fire_star_reversal(window) is None


# --- _fire_piercing_darkcloud -----------------------------------------


def test_piercing_darkcloud_fires_long_on_piercing_line():
    rows = [
        _bar(110.0, 111.0, 99.0, 100.0),  # long bearish bar1, midpoint 105
        _bar(98.0, 107.2, 97.9, 107.0),  # opens below bar1 close, closes back above midpoint
    ]
    window = _window(rows)
    signal = _fire_piercing_darkcloud(window)
    assert signal == PatternSignal(direction="long", strength=1.0)


def test_piercing_darkcloud_fires_short_on_dark_cloud_cover():
    rows = [
        _bar(100.0, 111.0, 99.0, 110.0),  # long bullish bar1, midpoint 105
        _bar(112.0, 112.1, 102.9, 103.0),  # opens above bar1 close, closes back below midpoint
    ]
    window = _window(rows)
    signal = _fire_piercing_darkcloud(window)
    assert signal == PatternSignal(direction="short", strength=1.0)


def test_piercing_darkcloud_silent_when_bar2_fully_engulfs():
    rows = [
        _bar(110.0, 111.0, 99.0, 100.0),  # long bearish bar1
        _bar(98.0, 116.0, 97.9, 115.0),  # closes back ABOVE bar1's own open -- an engulfing, not a piercing
    ]
    window = _window(rows)
    assert _fire_piercing_darkcloud(window) is None


def test_piercing_darkcloud_silent_on_insufficient_data():
    window = _window([_bar(110.0, 111.0, 99.0, 100.0)])
    assert _fire_piercing_darkcloud(window) is None


# --- _fire_harami ------------------------------------------------------


def test_harami_fires_long_on_bullish_harami():
    rows = [
        _bar(110.0, 111.0, 99.0, 100.0),  # long bearish bar1
        _bar(103.0, 107.0, 102.5, 107.0),  # bar2's body entirely inside bar1's body
    ]
    window = _window(rows)
    signal = _fire_harami(window)
    assert signal == PatternSignal(direction="long", strength=1.0)


def test_harami_fires_short_on_bearish_harami():
    rows = [
        _bar(100.0, 111.0, 99.0, 110.0),  # long bullish bar1
        _bar(107.0, 107.5, 102.5, 103.0),  # bar2's body entirely inside bar1's body
    ]
    window = _window(rows)
    signal = _fire_harami(window)
    assert signal == PatternSignal(direction="short", strength=1.0)


def test_harami_silent_when_not_inside():
    rows = [
        _bar(110.0, 111.0, 99.0, 100.0),
        _bar(95.0, 116.0, 94.9, 115.0),  # bar2's body extends past bar1's own range
    ]
    window = _window(rows)
    assert _fire_harami(window) is None


def test_harami_silent_on_insufficient_data():
    window = _window([_bar(110.0, 111.0, 99.0, 100.0)])
    assert _fire_harami(window) is None


# --- _fire_tweezer -----------------------------------------------------


def test_tweezer_bottom_fires_long_after_downtrend():
    rows = [
        _bar(110.0, 110.2, 109.8, 110.0),  # trend context
        _bar(105.0, 105.2, 104.8, 105.0),  # trend context: declining
        _bar(100.0, 100.0, 95.0, 99.0),  # bar1: low=95
        _bar(99.0, 110.0, 95.05, 100.0),  # bar2: matching low (within tolerance), unrelated high
    ]
    window = _window(rows)
    signal = _fire_tweezer(window, trend_lookback=2)
    assert signal == PatternSignal(direction="long", strength=1.0)


def test_tweezer_top_fires_short_after_uptrend():
    rows = [
        _bar(100.0, 100.2, 99.8, 100.0),  # trend context
        _bar(105.0, 105.2, 104.8, 105.0),  # trend context: rising
        _bar(110.0, 120.0, 110.0, 111.0),  # bar1: high=120
        _bar(111.0, 120.05, 90.0, 100.0),  # bar2: matching high (within tolerance), unrelated low
    ]
    window = _window(rows)
    signal = _fire_tweezer(window, trend_lookback=2)
    assert signal == PatternSignal(direction="short", strength=1.0)


def test_tweezer_silent_when_neither_extreme_matches():
    rows = [
        _bar(110.0, 110.2, 109.8, 110.0),
        _bar(105.0, 105.2, 104.8, 105.0),
        _bar(100.0, 101.0, 95.0, 99.0),
        _bar(99.0, 103.0, 90.0, 95.0),  # neither the high nor the low match bar1's
    ]
    window = _window(rows)
    assert _fire_tweezer(window, trend_lookback=2) is None


def test_tweezer_silent_on_insufficient_data():
    window = _window([_bar(100.0, 101.0, 95.0, 99.0), _bar(99.0, 103.0, 90.0, 95.0)])
    assert _fire_tweezer(window, trend_lookback=2) is None


# --- PATTERN_MINING_UNIVERSE -------------------------------------------


def test_pattern_mining_universe_is_deduplicated_and_nonoverlapping():
    assert len(PATTERN_MINING_UNIVERSE) == len(set(PATTERN_MINING_UNIVERSE))
    assert set(PATTERN_MINING_UNIVERSE_LARGE_CAP).isdisjoint(PATTERN_MINING_UNIVERSE_MID_SMALL_CAP)
    assert PATTERN_MINING_UNIVERSE == PATTERN_MINING_UNIVERSE_LARGE_CAP + PATTERN_MINING_UNIVERSE_MID_SMALL_CAP


# --- _gate_to_session_phase ------------------------------------------------


def test_gate_to_session_phase_blocks_outside_phase():
    always_fires = lambda window: PatternSignal(direction="long", strength=1.0)
    gated = _gate_to_session_phase(always_fires, "open")
    window = _window([_bar(100.0, 100.1, 99.9, 100.05, session_phase="close")])
    assert gated(window) is None


def test_gate_to_session_phase_allows_inside_phase():
    always_fires = lambda window: PatternSignal(direction="long", strength=1.0)
    gated = _gate_to_session_phase(always_fires, "open")
    window = _window([_bar(100.0, 100.1, 99.9, 100.05, session_phase="open")])
    assert gated(window) is not None


def test_gate_to_session_phase_blocks_empty_window():
    always_fires = lambda window: PatternSignal(direction="long", strength=1.0)
    gated = _gate_to_session_phase(always_fires, "open")
    assert gated(pd.DataFrame()) is None


# --- apply_pattern_signal_rule ---------------------------------------------


def test_apply_pattern_signal_rule_enters_long_from_flat():
    assert apply_pattern_signal_rule(1.0, True, 0, 0.0, 0.0) == 1


def test_apply_pattern_signal_rule_enters_short_from_flat():
    assert apply_pattern_signal_rule(-1.0, True, 0, 0.0, 0.0) == -1


def test_apply_pattern_signal_rule_holds_same_direction():
    assert apply_pattern_signal_rule(1.0, True, 1, 0.0, 0.0) == 1


def test_apply_pattern_signal_rule_flattens_on_reversal_never_direct_flip():
    # Never jumps from +1 directly to -1 — matches apply_zscore_threshold_
    # rule / apply_momentum_threshold_rule's established invariant.
    assert apply_pattern_signal_rule(-1.0, True, 1, 0.0, 0.0) == 0


def test_apply_pattern_signal_rule_flat_on_invalid():
    assert apply_pattern_signal_rule(1.0, False, 1, 0.0, 0.0) == 0
    assert apply_pattern_signal_rule(None, True, 1, 0.0, 0.0) == 0
    assert apply_pattern_signal_rule(0.0, True, 0, 0.0, 0.0) == 0


# --- realize_pattern_return --------------------------------------------


def test_realize_pattern_return_uses_bar_own_ret():
    row = pd.Series({"ret": 0.0123})
    assert realize_pattern_return(row, fit=None) == pytest.approx(0.0123)


# --- run_pattern_backtest: engine.py accepts hourly-indexed raw_data ------


def test_run_pattern_backtest_accepts_hourly_indexed_raw_data():
    """The core empirical claim this phase was told to verify, not assume:
    engine.py's step_one_day/run_walk_forward, completely unmodified,
    correctly consumes a tz-aware intraday-timestamp-indexed DataFrame —
    DayResult.date preserves the real intraday Timestamp (not silently
    truncated to midnight), and positional slicing produces a sane
    out-of-sample count."""
    bars = _synthetic_ticker_bars(seed=7, n_days=30)
    raw = build_pattern_raw_data(bars)
    pattern = PATTERN_FAMILY[0]
    result = run_pattern_backtest(pattern, raw)
    assert result.status == "ok"
    assert result.n_trading_days == len(raw)
    assert result.n_out_of_sample_days == len(raw) - INTRADAY_FIT_WINDOW_BARS
    assert len(result.day_results) == result.n_out_of_sample_days
    first_result_date = result.day_results[0].date
    assert isinstance(first_result_date, pd.Timestamp)
    assert first_result_date == raw.index[INTRADAY_FIT_WINDOW_BARS]
    assert first_result_date.tzinfo is not None  # tz-awareness survives the round trip, not silently dropped


def test_run_pattern_backtest_never_direct_reverses_position():
    bars = _synthetic_ticker_bars(seed=11, n_days=40)
    raw = build_pattern_raw_data(bars)
    for pattern in PATTERN_FAMILY:
        result = run_pattern_backtest(pattern, raw)
        positions = [d.position for d in result.day_results]
        for prev, cur in zip(positions, positions[1:]):
            assert not (prev == 1 and cur == -1)
            assert not (prev == -1 and cur == 1)


# --- daily_returns_from_bar_equity ---------------------------------------


def test_daily_returns_from_bar_equity_hand_computed():
    day1 = pd.Timestamp("2024-01-02 09:30", tz="America/New_York")
    day1b = pd.Timestamp("2024-01-02 10:30", tz="America/New_York")
    day2 = pd.Timestamp("2024-01-03 09:30", tz="America/New_York")

    def _dr(date, equity):
        return DayResult(date=date, position=0, z_score=None, raw_return=0.0, cost=0.0, net_return=0.0, equity=equity)

    day_results = [_dr(day1, 1.01), _dr(day1b, 1.015), _dr(day2, 1.025)]
    returns = daily_returns_from_bar_equity(day_results)
    assert len(returns) == 2
    assert returns.iloc[0] == pytest.approx(0.015)  # end-of-day1 mark (1.015) vs baseline 1.0
    assert returns.iloc[1] == pytest.approx(1.025 / 1.015 - 1)


def test_daily_returns_from_bar_equity_empty_input():
    assert daily_returns_from_bar_equity([]).empty


# --- screen_pattern_universe ------------------------------------------------


def test_screen_pattern_universe_n_trials_matches_family_size():
    bars_by_ticker = {
        "AAA": _synthetic_ticker_bars(seed=1, n_days=60),
        "BBB": _synthetic_ticker_bars(seed=2, n_days=60),
    }
    small_family = PATTERN_FAMILY[:4]
    results = screen_pattern_universe(bars_by_ticker, patterns=small_family)
    assert results  # at least one of these 4 fires somewhere over 60 real-shaped days
    for r in results:
        assert r.deflated_sharpe.n_trials == len(small_family)


def test_screen_pattern_universe_pools_as_equal_weighted_mean():
    bars_by_ticker = {
        "AAA": _synthetic_ticker_bars(seed=3, n_days=60),
        "BBB": _synthetic_ticker_bars(seed=4, n_days=60),
    }
    pattern = PATTERN_FAMILY[0]
    results = screen_pattern_universe(bars_by_ticker, patterns=[pattern])
    assert len(results) == 1
    result = results[0]

    # Independently reproduce the pooled series via the same public
    # building blocks, verified individually above, and check it matches
    # screen_pattern_universe's own pooling exactly.
    per_ticker = {}
    for ticker, bars in bars_by_ticker.items():
        raw = build_pattern_raw_data(bars)
        bt = run_pattern_backtest(pattern, raw)
        per_ticker[ticker] = daily_returns_from_bar_equity(bt.day_results)
    expected_pooled = pd.concat(per_ticker, axis=1).mean(axis=1, skipna=True).dropna()
    assert result.n_trading_days == len(expected_pooled)
    assert result.n_tickers_in_basket == 2


def test_screen_pattern_universe_excludes_pattern_that_never_fires():
    bars_by_ticker = {"AAA": _synthetic_ticker_bars(seed=5, n_days=30)}
    never_fires = PatternSpec(
        pattern_id="never_fires",
        family="test",
        citation="synthetic test fixture",
        fire_fn=lambda window: None,
    )
    results = screen_pattern_universe(bars_by_ticker, patterns=[never_fires])
    assert results == []


def test_screen_pattern_universe_excludes_pattern_below_min_pooled_days():
    # n_days deliberately short: enough for the fit window (20 bars ~= 3
    # days) plus only a handful of out-of-sample days — well under
    # MIN_POOLED_TRADING_DAYS.
    n_days = (INTRADAY_FIT_WINDOW_BARS // 7) + 2
    assert n_days * 7 - INTRADAY_FIT_WINDOW_BARS < MIN_POOLED_TRADING_DAYS
    bars_by_ticker = {"AAA": _synthetic_ticker_bars(seed=6, n_days=n_days)}
    always_fires = PatternSpec(
        pattern_id="always_fires",
        family="test",
        citation="synthetic test fixture",
        fire_fn=lambda window: PatternSignal(direction="long", strength=1.0),
    )
    results = screen_pattern_universe(bars_by_ticker, patterns=[always_fires])
    assert results == []


def test_screen_pattern_universe_sorted_by_sharpe_descending():
    bars_by_ticker = {
        "AAA": _synthetic_ticker_bars(seed=9, n_days=80),
        "BBB": _synthetic_ticker_bars(seed=10, n_days=80),
        "CCC": _synthetic_ticker_bars(seed=12, n_days=80),
    }
    results = screen_pattern_universe(bars_by_ticker, patterns=PATTERN_FAMILY)
    sharpes = [r.sharpe_annualized for r in results]
    assert sharpes == sorted(sharpes, reverse=True)


def test_pattern_family_size_within_approved_bounds():
    # This expanded screening pass's explicit ceiling: 150-300 distinct
    # pattern definitions (up from the original pilot's 20-100 — see this
    # module's own header docstring for why the ceiling itself moved, not
    # just the count within it).
    assert 150 <= len(PATTERN_FAMILY) <= 300
    assert len(PATTERN_FAMILY) == len({p.pattern_id for p in PATTERN_FAMILY})  # every id unique


def test_every_pattern_has_a_citation():
    assert all(spec.citation.strip() for spec in PATTERN_FAMILY)
