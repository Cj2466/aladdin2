import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.engine import DayResult, StrategyFit
from app.services.research_lab.intraday_patterns import (
    INTRADAY_FIT_WINDOW_BARS,
    MAX_WEIGHT_MULTIPLE,
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
    _make_fit_fn,
    _session_phase_for_day,
    _signal_weight_magnitude,
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


# --- _signal_weight_magnitude: magnitude-weighted sizing formula --------
# weight = clip(magnitude / strength_scale, -MAX_WEIGHT_MULTIPLE, +MAX_WEIGHT_MULTIPLE) * sign(direction)
# See intraday_patterns.py's own module-level note above PatternSpec for
# the full formula and per-family rationale this exercises.


def _spec(fire_fn=lambda w: None, strength_scale=None, strength_is_margin=False) -> PatternSpec:
    return PatternSpec(
        pattern_id="t", family="t", citation="t", fire_fn=fire_fn,
        strength_scale=strength_scale, strength_is_margin=strength_is_margin,
    )


def test_signal_weight_magnitude_no_scale_stays_flat_regardless_of_strength():
    """strength_scale=None (the default) means no natural threshold to normalize against — sizing stays flat, exactly the historical +-1 bet, no matter how large strength is."""
    spec = _spec(strength_scale=None)
    assert _signal_weight_magnitude(PatternSignal(direction="long", strength=999.0), spec) == pytest.approx(1.0)


def test_signal_weight_magnitude_raw_style_exactly_at_threshold_matches_flat_bet():
    """Raw-value-style family (strength_is_margin=False, e.g. VWAP): strength exactly equal to strength_scale is exactly the firing boundary -> ratio 1.0, the SAME magnitude as today's flat +-1 bet — this is what makes the scheme a refinement, not a new strategy."""
    spec = _spec(strength_scale=0.004)
    assert _signal_weight_magnitude(PatternSignal(direction="long", strength=0.004), spec) == pytest.approx(1.0)


def test_signal_weight_magnitude_raw_style_scales_linearly_above_threshold():
    spec = _spec(strength_scale=0.004)
    assert _signal_weight_magnitude(PatternSignal(direction="short", strength=0.008), spec) == pytest.approx(2.0)
    assert _signal_weight_magnitude(PatternSignal(direction="short", strength=0.006), spec) == pytest.approx(1.5)


def test_signal_weight_magnitude_caps_at_max_weight_multiple():
    spec = _spec(strength_scale=0.004)
    signal = PatternSignal(direction="long", strength=10.0)  # 2500x the threshold — must clip, not explode
    assert _signal_weight_magnitude(signal, spec) == pytest.approx(MAX_WEIGHT_MULTIPLE)


def test_signal_weight_magnitude_margin_style_exactly_at_threshold_matches_flat_bet():
    """Margin-style family (strength_is_margin=True, e.g. RSI overbought=70, strength_scale=70-50=20): strength==0 exactly at the firing boundary (rsi==overbought, the margin is zero) — reconstructing (strength + strength_scale) recovers the live distance from RSI's own neutral center (50), giving ratio 1.0 at the boundary just like the raw-value case."""
    spec = _spec(strength_scale=20.0, strength_is_margin=True)
    assert _signal_weight_magnitude(PatternSignal(direction="short", strength=0.0), spec) == pytest.approx(1.0)


def test_signal_weight_magnitude_margin_style_scales_above_threshold():
    """Same RSI(overbought=70) setup: rsi=90 -> strength=rsi-overbought=20 -> magnitude=20+20=40 -> ratio=40/20=2.0."""
    spec = _spec(strength_scale=20.0, strength_is_margin=True)
    assert _signal_weight_magnitude(PatternSignal(direction="short", strength=20.0), spec) == pytest.approx(2.0)


def test_signal_weight_magnitude_zero_scale_guards_against_division_by_zero():
    """ORB_1MIN_BUFFERS includes 0.0 (no minimum-excess requirement) — a zero (or negative) strength_scale must fall back to the flat historical bet, never divide by zero."""
    spec = _spec(strength_scale=0.0)
    assert _signal_weight_magnitude(PatternSignal(direction="long", strength=0.01), spec) == pytest.approx(1.0)


def test_signal_weight_magnitude_is_always_nonnegative_sign_carried_separately():
    """_signal_weight_magnitude only ever returns a magnitude — direction/sign is carried separately by PatternSignal.direction via _make_fit_fn's z_score (tested below), never by this function."""
    spec = _spec(strength_scale=0.004)
    long_weight = _signal_weight_magnitude(PatternSignal(direction="long", strength=0.008), spec)
    short_weight = _signal_weight_magnitude(PatternSignal(direction="short", strength=0.008), spec)
    assert long_weight == short_weight == pytest.approx(2.0)
    assert long_weight >= 0.0


# --- _make_fit_fn: weight_magnitude threading, direction sign unaffected ---


def test_make_fit_fn_carries_weight_magnitude_long():
    spec = _spec(fire_fn=lambda w: PatternSignal(direction="long", strength=0.008), strength_scale=0.004)
    fit = _make_fit_fn(spec)(pd.DataFrame({"x": [1]}))
    assert fit.is_valid is True
    assert fit.z_score == pytest.approx(1.0)  # a pure direction/sign carrier, unaffected by magnitude
    assert fit.params["weight_magnitude"] == pytest.approx(2.0)


def test_make_fit_fn_carries_weight_magnitude_short():
    spec = _spec(fire_fn=lambda w: PatternSignal(direction="short", strength=0.012), strength_scale=0.004)
    fit = _make_fit_fn(spec)(pd.DataFrame({"x": [1]}))
    assert fit.z_score == pytest.approx(-1.0)
    assert fit.params["weight_magnitude"] == pytest.approx(3.0)


def test_make_fit_fn_no_signal_is_invalid_with_empty_params():
    spec = _spec(fire_fn=lambda w: None, strength_scale=0.004)
    fit = _make_fit_fn(spec)(pd.DataFrame({"x": [1]}))
    assert fit.is_valid is False
    assert fit.z_score is None
    assert fit.params == {}


def test_make_fit_fn_empty_window_is_invalid_without_calling_fire_fn():
    calls = []
    spec = _spec(fire_fn=lambda w: calls.append(1) or PatternSignal(direction="long", strength=1.0))
    fit = _make_fit_fn(spec)(pd.DataFrame())
    assert fit.is_valid is False
    assert calls == []  # fire_fn never even called on an empty window


# --- Real PATTERN_FAMILY specs: strength_scale/strength_is_margin per family ---


def test_orb_continuation_specs_scale_to_own_breakout_threshold():
    from app.services.research_lab.intraday_patterns import ORB_BREAKOUT_THRESHOLDS

    specs = [p for p in PATTERN_FAMILY if p.family == "opening_range_breakout"]
    assert len(specs) == len(ORB_BREAKOUT_THRESHOLDS)
    for spec, threshold in zip(specs, ORB_BREAKOUT_THRESHOLDS):
        assert spec.strength_scale == pytest.approx(threshold)
        assert spec.strength_is_margin is False


def test_rsi_extreme_specs_scale_to_overbought_minus_neutral_center():
    specs = [p for p in PATTERN_FAMILY if p.family == "rsi_extreme_wilder1978"]
    assert specs
    for spec in specs:
        # pattern_id format: rsi_extreme_{period}_{overbought:.0f}_{oversold:.0f}_{phase}
        overbought = float(spec.pattern_id.split("_")[3])
        assert spec.strength_scale == pytest.approx(overbought - 50.0)
        assert spec.strength_is_margin is True


def test_bollinger_reversion_specs_scale_to_own_n_std():
    specs = [p for p in PATTERN_FAMILY if p.family == "bollinger_reversion"]
    assert specs
    for spec in specs:
        # pattern_id format: bollinger_reversion_{period}_{n_std:.1f}_{phase}
        n_std = float(spec.pattern_id.split("_")[3])
        assert spec.strength_scale == pytest.approx(n_std)
        assert spec.strength_is_margin is True


def test_candlestick_specs_trivial_scale_except_hammer_family():
    """Every candlestick shape but hammer_family fires at a fixed strength=1.0 (a shape match, no magnitude) — strength_scale=1.0 keeps sizing trivially flat. hammer_family's shadow-to-range ratio has no dimensionally-matched declared threshold, so it stays unweighted."""
    hammer_specs = [p for p in PATTERN_FAMILY if p.family == "candlestick" and p.pattern_id.startswith("hammer_family_")]
    other_specs = [p for p in PATTERN_FAMILY if p.family == "candlestick" and not p.pattern_id.startswith("hammer_family_")]
    assert hammer_specs and other_specs
    assert all(p.strength_scale is None for p in hammer_specs)
    assert all(p.strength_scale == pytest.approx(1.0) and not p.strength_is_margin for p in other_specs)


def test_families_with_no_natural_scale_stay_unweighted():
    """MA crossover (raw price-unit diff), MACD (same), and volume climax (return-magnitude strength vs. a volume-ratio filter) have no dimensionally-matched declared threshold to reuse — per the "don't invent a new constant" rule, they keep the historical flat +-1 bet."""
    for family in ("ma_crossover_brock1992", "macd_appel1979", "volume_price_divergence"):
        specs = [p for p in PATTERN_FAMILY if p.family == family] or [
            p for p in PATTERN_FAMILY_PHASE_B_15MIN if p.family == family
        ]
        assert specs, family
        assert all(p.strength_scale is None for p in specs)


# --- engine.py contract: weighting composes with the UNMODIFIED shared engine ---


def test_step_one_day_applies_weight_magnitude_from_fit_params_via_return_fn():
    """Regression guard on the exact mechanism this scheme relies on: engine.py itself is completely untouched (position stays a plain int +-1/0, still driving cost accounting) — a return_fn that reads fit.params can still scale the realized return by an arbitrary per-step magnitude. Proves the opt-in weighting composes correctly with engine.py's existing step_one_day/decide_position_fn contract, which pairs.py/momentum.py also share and which must NOT change."""
    from app.services.research_lab.engine import WalkForwardConfig, WalkForwardState, step_one_day

    window = pd.DataFrame({"x": [1, 2, 3]})
    day_row = pd.Series({"ret": 0.01}, name=pd.Timestamp("2024-01-02"))

    def fit_fn(w):
        return StrategyFit(is_valid=True, z_score=1.0, fit_quality=None, params={"weight_magnitude": 2.5})

    state = WalkForwardState()
    config = WalkForwardConfig(fit_window_days=1, entry_z=0.0, exit_z=0.0, cost_bps=0.0)
    _, day_result, _ = step_one_day(
        window, day_row, fit_fn, realize_pattern_return, state, config, decide_position_fn=apply_pattern_signal_rule
    )
    assert day_result.position == 1  # engine's own position: still a plain integer sign, untouched by weighting
    assert day_result.raw_return == pytest.approx(1 * 2.5 * 0.01)


# --- realize_pattern_return --------------------------------------------


def test_realize_pattern_return_uses_bar_own_ret():
    row = pd.Series({"ret": 0.0123})
    assert realize_pattern_return(row, fit=None) == pytest.approx(0.0123)  # no fit -> flat 1.0x, same as before this scheme existed


def test_realize_pattern_return_scales_by_weight_magnitude():
    row = pd.Series({"ret": 0.0123})
    fit = StrategyFit(is_valid=True, z_score=1.0, fit_quality=None, params={"weight_magnitude": 2.5})
    assert realize_pattern_return(row, fit) == pytest.approx(0.0123 * 2.5)


def test_realize_pattern_return_defaults_to_flat_when_params_key_missing():
    row = pd.Series({"ret": 0.0123})
    fit = StrategyFit(is_valid=True, z_score=1.0, fit_quality=None, params={})
    assert realize_pattern_return(row, fit) == pytest.approx(0.0123)


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


# ======================================================================
# Phase B: finer-granularity expansion
# ======================================================================

from app.services.research_lab.intraday_patterns import (
    FIT_WINDOW_BARS_1MIN,
    FIT_WINDOW_BARS_15MIN,
    PATTERN_FAMILY_PHASE_B_1MIN,
    PATTERN_FAMILY_PHASE_B_15MIN,
    PHASE_B_ADDITIONS_15MIN,
    PHASE_B_TOTAL_TRIALS,
    PHASE_B_UNIVERSE_1MIN,
    PHASE_B_UNIVERSE_15MIN,
    PHASE_B_UNIVERSE_LARGE_CAP,
    PHASE_B_UNIVERSE_MID_CAP,
    PHASE_B_UNIVERSE_SMALL_CAP,
    PatternScreenGroup,
    _fire_atr_expansion,
    _fire_cci_extreme,
    _fire_close_streak,
    _fire_gao_first_half_hour,
    _fire_gao_minute_momentum,
    _fire_keltner_reversion,
    _fire_macd_cross,
    _fire_mfi_extreme,
    _fire_obv_divergence,
    _fire_orb_range_break,
    _fire_pivot_reversion,
    _fire_prior_day_level_break,
    _fire_same_slot_persistence,
    _fire_session_bias,
    _fire_stochastic_extreme,
    _gate_to_minute_window,
    _minute_of_day,
    backtest_patterns_for_ticker,
    screen_pattern_groups,
)


def _ts_window(rows: list[dict], timestamps: list[str], trading_dates=None) -> pd.DataFrame:
    """Like _window but with a real tz-aware New York DatetimeIndex — the
    minute-gated Phase B patterns read timestamps off the index, exactly
    as build_pattern_raw_data's output carries them."""
    df = pd.DataFrame(rows)
    df.index = pd.DatetimeIndex([pd.Timestamp(t, tz="America/New_York") for t in timestamps])
    if trading_dates is None:
        trading_dates = [str(ts.date()) for ts in df.index]
    df["trading_date"] = trading_dates
    if "session_phase" not in df.columns:
        df["session_phase"] = None
    return df


# --- Keltner channel reversion (Family 12) ------------------------------


def _keltner_window(last_bar: dict) -> pd.DataFrame:
    rows = [_bar(100, 101, 99, 100) for _ in range(21)] + [last_bar]
    return _window(rows)


def test_keltner_fires_short_above_upper_band():
    signal = _fire_keltner_reversion(
        _keltner_window(_bar(100, 105.5, 100, 105)), period=20, atr_mult=2.0
    )
    assert signal is not None and signal.direction == "short"


def test_keltner_fires_long_below_lower_band():
    signal = _fire_keltner_reversion(
        _keltner_window(_bar(100, 100, 94.5, 95)), period=20, atr_mult=2.0
    )
    assert signal is not None and signal.direction == "long"


def test_keltner_silent_inside_band():
    signal = _fire_keltner_reversion(
        _keltner_window(_bar(100, 101, 99, 100)), period=20, atr_mult=2.0
    )
    assert signal is None


def test_keltner_silent_on_insufficient_data():
    rows = [_bar(100, 101, 99, 100) for _ in range(10)]
    assert _fire_keltner_reversion(_window(rows), period=20, atr_mult=2.0) is None


# --- Stochastic extremes (Family 13) ------------------------------------


def _stochastic_window(last_close: float) -> pd.DataFrame:
    rows = [_bar(100, 110, 90, 100) for _ in range(13)] + [_bar(100, 110, 90, last_close)]
    return _window(rows)


def test_stochastic_fires_short_when_overbought():
    signal = _fire_stochastic_extreme(_stochastic_window(109.0), period=14, overbought=80, oversold=20)
    assert signal is not None and signal.direction == "short"


def test_stochastic_fires_long_when_oversold():
    signal = _fire_stochastic_extreme(_stochastic_window(91.0), period=14, overbought=80, oversold=20)
    assert signal is not None and signal.direction == "long"


def test_stochastic_silent_mid_range():
    assert _fire_stochastic_extreme(_stochastic_window(100.0), period=14, overbought=80, oversold=20) is None


def test_stochastic_silent_on_insufficient_data():
    rows = [_bar(100, 110, 90, 100) for _ in range(5)]
    assert _fire_stochastic_extreme(_window(rows), period=14, overbought=80, oversold=20) is None


def test_stochastic_silent_on_flat_range():
    rows = [_bar(100, 100, 100, 100) for _ in range(14)]
    assert _fire_stochastic_extreme(_window(rows), period=14, overbought=80, oversold=20) is None


# --- CCI extremes (Family 14) -------------------------------------------


def _cci_window(last_typical: float) -> pd.DataFrame:
    rows = []
    for i in range(19):
        p = 101.0 if i % 2 == 0 else 99.0
        rows.append(_bar(p, p, p, p))
    rows.append(_bar(last_typical, last_typical, last_typical, last_typical))
    return _window(rows)


def test_cci_trend_reading_fires_with_extreme():
    signal = _fire_cci_extreme(_cci_window(115.0), period=20, level=100.0, reverse=False)
    assert signal is not None and signal.direction == "long"  # Lambert: trade WITH the up-cycle


def test_cci_reversion_reading_fades_extreme():
    signal = _fire_cci_extreme(_cci_window(115.0), period=20, level=100.0, reverse=True)
    assert signal is not None and signal.direction == "short"


def test_cci_negative_extreme_mirrors():
    signal = _fire_cci_extreme(_cci_window(85.0), period=20, level=100.0, reverse=False)
    assert signal is not None and signal.direction == "short"


def test_cci_silent_below_level():
    assert _fire_cci_extreme(_cci_window(100.4), period=20, level=100.0, reverse=False) is None


def test_cci_silent_on_insufficient_data():
    rows = [_bar(100, 100, 100, 100) for _ in range(5)]
    assert _fire_cci_extreme(_window(rows), period=20, level=100.0, reverse=False) is None


# --- MACD crossover (Family 15) -----------------------------------------


def test_macd_fires_long_on_bullish_cross():
    rows = [_bar(100, 100, 100, 100) for _ in range(30)] + [_bar(100, 105, 100, 105)]
    signal = _fire_macd_cross(_window(rows), fast=8, slow=17, signal=9)
    assert signal is not None and signal.direction == "long"


def test_macd_fires_short_on_bearish_cross():
    rows = [_bar(100, 100, 100, 100) for _ in range(30)] + [_bar(100, 100, 95, 95)]
    signal = _fire_macd_cross(_window(rows), fast=8, slow=17, signal=9)
    assert signal is not None and signal.direction == "short"


def test_macd_silent_without_a_fresh_cross():
    rows = [_bar(100, 100, 100, 100) for _ in range(31)]
    assert _fire_macd_cross(_window(rows), fast=8, slow=17, signal=9) is None


def test_macd_silent_on_insufficient_data():
    rows = [_bar(100, 100, 100, 100) for _ in range(10)]
    assert _fire_macd_cross(_window(rows), fast=8, slow=17, signal=9) is None


# --- MFI extremes (Family 16) -------------------------------------------


def test_mfi_fires_short_when_all_flow_positive():
    rows = [_bar(100 + i, 100 + i, 100 + i, 100 + i, volume=1000) for i in range(16)]
    signal = _fire_mfi_extreme(_window(rows), period=14, overbought=80, oversold=20)
    assert signal is not None and signal.direction == "short"


def test_mfi_fires_long_when_all_flow_negative():
    rows = [_bar(200 - i, 200 - i, 200 - i, 200 - i, volume=1000) for i in range(16)]
    signal = _fire_mfi_extreme(_window(rows), period=14, overbought=80, oversold=20)
    assert signal is not None and signal.direction == "long"


def test_mfi_silent_mid_range():
    rows = [_bar(100 + (1 if i % 2 else -1), 101, 99, 100 + (1 if i % 2 else -1)) for i in range(16)]
    assert _fire_mfi_extreme(_window(rows), period=14, overbought=80, oversold=20) is None


def test_mfi_silent_on_zero_volume():
    rows = [_bar(100 + i, 100 + i, 100 + i, 100 + i, volume=0) for i in range(16)]
    assert _fire_mfi_extreme(_window(rows), period=14, overbought=80, oversold=20) is None


# --- Session-phase bias (Family 17) -------------------------------------


def test_session_bias_returns_fixed_direction():
    window = _window([_bar(100, 101, 99, 100)])
    assert _fire_session_bias(window, direction="long").direction == "long"
    assert _fire_session_bias(window, direction="short").direction == "short"


# --- Prior-day-level breakout (Family 18) -------------------------------


def _two_day_window(day2_close: float) -> pd.DataFrame:
    day1 = [dict(_bar(100, 110, 90, 100), trading_date="2024-01-02") for _ in range(3)]
    day2 = [dict(_bar(100, day2_close + 1, day2_close - 1, day2_close), trading_date="2024-01-03")]
    return _window(day1 + day2)


def test_prior_day_break_continuation_long_above_prior_high():
    signal = _fire_prior_day_level_break(_two_day_window(111.0), reverse=False)
    assert signal is not None and signal.direction == "long"


def test_prior_day_break_fade_shorts_above_prior_high():
    signal = _fire_prior_day_level_break(_two_day_window(111.0), reverse=True)
    assert signal is not None and signal.direction == "short"


def test_prior_day_break_continuation_short_below_prior_low():
    signal = _fire_prior_day_level_break(_two_day_window(89.0), reverse=False)
    assert signal is not None and signal.direction == "short"


def test_prior_day_break_silent_inside_prior_range():
    assert _fire_prior_day_level_break(_two_day_window(100.0), reverse=False) is None


def test_prior_day_break_silent_without_prior_day():
    rows = [dict(_bar(100, 111, 99, 111), trading_date="2024-01-02")]
    assert _fire_prior_day_level_break(_window(rows), reverse=False) is None


# --- Pivot reversion (Family 19) ----------------------------------------
# Prior day H=110 L=90 C=100 -> PP=100, R1=110, S1=90, R2=120, S2=80.


def test_pivot_reversion_shorts_at_r1():
    signal = _fire_pivot_reversion(_two_day_window(111.0), level=1)
    assert signal is not None and signal.direction == "short"


def test_pivot_reversion_longs_at_s2():
    signal = _fire_pivot_reversion(_two_day_window(79.0), level=2)
    assert signal is not None and signal.direction == "long"


def test_pivot_reversion_silent_between_levels():
    assert _fire_pivot_reversion(_two_day_window(100.0), level=1) is None


def test_pivot_reversion_silent_without_prior_day():
    rows = [dict(_bar(100, 111, 99, 111), trading_date="2024-01-02")]
    assert _fire_pivot_reversion(_window(rows), level=1) is None


# --- ATR range expansion (Family 20) ------------------------------------


def _atr_window(last_bar: dict) -> pd.DataFrame:
    rows = [_bar(100, 101, 99, 100) for _ in range(16)] + [last_bar]
    return _window(rows)


def test_atr_expansion_continuation_follows_wide_up_bar():
    signal = _fire_atr_expansion(_atr_window(_bar(100, 106, 100, 105)), atr_mult=1.5, reverse=False)
    assert signal is not None and signal.direction == "long"


def test_atr_expansion_exhaustion_fades_wide_up_bar():
    signal = _fire_atr_expansion(_atr_window(_bar(100, 106, 100, 105)), atr_mult=1.5, reverse=True)
    assert signal is not None and signal.direction == "short"


def test_atr_expansion_silent_on_normal_range_bar():
    assert _fire_atr_expansion(_atr_window(_bar(100, 101, 99, 100.5)), atr_mult=1.5, reverse=False) is None


def test_atr_expansion_silent_on_insufficient_data():
    rows = [_bar(100, 101, 99, 100) for _ in range(5)]
    assert _fire_atr_expansion(_window(rows), atr_mult=1.5, reverse=False) is None


# --- Consecutive-close streaks (Family 21) ------------------------------


def test_streak_continuation_rides_up_streak():
    rows = [_bar(100 + i, 101 + i, 99 + i, 100 + i) for i in range(5)]
    signal = _fire_close_streak(_window(rows), streak_len=3, reverse=False)
    assert signal is not None and signal.direction == "long"


def test_streak_reversal_fades_up_streak():
    rows = [_bar(100 + i, 101 + i, 99 + i, 100 + i) for i in range(5)]
    signal = _fire_close_streak(_window(rows), streak_len=3, reverse=True)
    assert signal is not None and signal.direction == "short"


def test_streak_down_mirrors():
    rows = [_bar(200 - i, 201 - i, 199 - i, 200 - i) for i in range(5)]
    signal = _fire_close_streak(_window(rows), streak_len=3, reverse=True)
    assert signal is not None and signal.direction == "long"  # Lehmann: fade the down-streak


def test_streak_silent_on_mixed_closes():
    closes = [100, 101, 100, 101, 100]
    rows = [_bar(c, c + 1, c - 1, c) for c in closes]
    assert _fire_close_streak(_window(rows), streak_len=3, reverse=False) is None


def test_streak_silent_on_insufficient_data():
    rows = [_bar(100, 101, 99, 100) for _ in range(2)]
    assert _fire_close_streak(_window(rows), streak_len=3, reverse=False) is None


# --- OBV divergence (Family 22) -----------------------------------------


def _obv_divergence_window(up_volume: float, down_volume: float) -> pd.DataFrame:
    # Alternating +1.0 up-moves and -1.2 down-moves: price drifts DOWN
    # while OBV's direction is set entirely by which side carries volume.
    rows = []
    price = 100.0
    for i in range(14):
        if i % 2 == 0:
            new = price + 1.0
            rows.append(_bar(price, new, price, new, volume=up_volume))
        else:
            new = price - 1.2
            rows.append(_bar(price, price, new, new, volume=down_volume))
        price = new
    return _window(rows)


def test_obv_divergence_longs_when_obv_disagrees_upward():
    signal = _fire_obv_divergence(_obv_divergence_window(10_000, 100), lookback=10)
    assert signal is not None and signal.direction == "long"  # price fell, OBV rose -> follow OBV


def test_obv_divergence_silent_on_agreement():
    signal = _fire_obv_divergence(_obv_divergence_window(100, 10_000), lookback=10)
    assert signal is None  # price fell AND OBV fell -> no divergence


def test_obv_divergence_silent_on_insufficient_data():
    rows = [_bar(100, 101, 99, 100) for _ in range(5)]
    assert _fire_obv_divergence(_window(rows), lookback=10) is None


# --- Gao first-half-hour at 15-minute bars (Family 26) ------------------


def _gao_15min_day(first_two_bar_return: float) -> pd.DataFrame:
    open_price = 100.0
    mid = open_price * (1 + first_two_bar_return / 2)
    end = open_price * (1 + first_two_bar_return)
    rows = [
        dict(_bar(open_price, max(open_price, mid), min(open_price, mid), mid), trading_date="2024-01-03"),
        dict(_bar(mid, max(mid, end), min(mid, end), end), trading_date="2024-01-03"),
        dict(_bar(end, end + 1, end - 1, end), trading_date="2024-01-03"),
    ]
    return _window(rows)


def test_gao_first_half_hour_continuation_follows_opening_move():
    signal = _fire_gao_first_half_hour(_gao_15min_day(0.01), reverse=False, min_open_return=0.002)
    assert signal is not None and signal.direction == "long"


def test_gao_first_half_hour_reversal_fades_opening_move():
    signal = _fire_gao_first_half_hour(_gao_15min_day(0.01), reverse=True, min_open_return=0.002)
    assert signal is not None and signal.direction == "short"


def test_gao_first_half_hour_silent_below_threshold():
    assert _fire_gao_first_half_hour(_gao_15min_day(0.001), reverse=False, min_open_return=0.002) is None


def test_gao_first_half_hour_silent_without_two_open_bars():
    rows = [dict(_bar(100, 101, 99, 101), trading_date="2024-01-03")]
    assert _fire_gao_first_half_hour(_window(rows), reverse=False, min_open_return=0.002) is None


# --- Minute-of-day gating -----------------------------------------------


def test_minute_of_day_reads_ny_time():
    window = _ts_window([_bar(100, 101, 99, 100)], ["2024-01-03 09:30"])
    assert _minute_of_day(window) == 570


def test_gate_to_minute_window_blocks_outside_and_allows_inside():
    always = lambda window: PatternSignal(direction="long", strength=1.0)
    gated = _gate_to_minute_window(always, 600, 720)
    inside = _ts_window([_bar(100, 101, 99, 100)], ["2024-01-03 10:30"])
    before = _ts_window([_bar(100, 101, 99, 100)], ["2024-01-03 09:45"])
    at_end = _ts_window([_bar(100, 101, 99, 100)], ["2024-01-03 12:00"])
    assert gated(inside) is not None
    assert gated(before) is None
    assert gated(at_end) is None  # half-open window
    assert gated(inside.iloc[0:0]) is None  # empty window


# --- Gao literal first-half-hour from minute bars -----------------------


def _minute_day_window(n_open_bars: int = 30, open_return: float = 0.01, start="09:30"):
    times = pd.date_range(f"2024-01-03 {start}", periods=n_open_bars + 5, freq="1min")
    rows = []
    price = 100.0
    final = 100.0 * (1 + open_return)
    step = (final - price) / max(n_open_bars - 1, 1)
    for i in range(n_open_bars + 5):
        new = price + step if i < n_open_bars else price
        rows.append(_bar(price, max(price, new), min(price, new), new))
        price = new
    return _ts_window(rows, [str(t) for t in times])


def test_gao_minute_momentum_follows_first_half_hour():
    signal = _fire_gao_minute_momentum(_minute_day_window(), reverse=False, min_open_return=0.002)
    assert signal is not None and signal.direction == "long"


def test_gao_minute_momentum_reversal_flips():
    signal = _fire_gao_minute_momentum(_minute_day_window(), reverse=True, min_open_return=0.002)
    assert signal is not None and signal.direction == "short"


def test_gao_minute_momentum_silent_on_late_open():
    signal = _fire_gao_minute_momentum(
        _minute_day_window(start="09:40"), reverse=False, min_open_return=0.002
    )
    assert signal is None


def test_gao_minute_momentum_silent_on_incomplete_half_hour():
    signal = _fire_gao_minute_momentum(
        _minute_day_window(n_open_bars=10), reverse=False, min_open_return=0.002
    )
    assert signal is None


# --- Crabel N-minute opening-range breakout -----------------------------


def _orb_minute_window(last_close: float, range_minutes: int = 15, last_time="09:50"):
    times = [f"2024-01-03 09:{30 + i}" for i in range(range_minutes)] + [f"2024-01-03 {last_time}"]
    rows = [_bar(100, 101, 99, 100) for _ in range(range_minutes)] + [
        _bar(100, max(101.0, last_close), min(99.0, last_close), last_close)
    ]
    return _ts_window(rows, times)


def test_orb_range_break_longs_above_range_high():
    signal = _fire_orb_range_break(_orb_minute_window(101.5), range_minutes=15, buffer=0.0)
    assert signal is not None and signal.direction == "long"


def test_orb_range_break_shorts_below_range_low():
    signal = _fire_orb_range_break(_orb_minute_window(98.5), range_minutes=15, buffer=0.0)
    assert signal is not None and signal.direction == "short"


def test_orb_range_break_silent_inside_range():
    assert _fire_orb_range_break(_orb_minute_window(100.0), range_minutes=15, buffer=0.0) is None


def test_orb_range_break_buffer_requires_margin():
    # +0.5% above the range high clears buffer=0.0 but not buffer=0.1... (1%)
    assert _fire_orb_range_break(_orb_minute_window(101.5), range_minutes=15, buffer=0.01) is None


def test_orb_range_break_silent_while_range_still_forming():
    window = _orb_minute_window(101.5, last_time="09:40")
    assert _fire_orb_range_break(window, range_minutes=15, buffer=0.0) is None


# --- Heston/Korajczyk/Sadka same-slot persistence -----------------------


def _hks_window(slot_return: float, current_time="10:05"):
    # Prior day: a full 10:00-10:29 slot with the given return.
    prior_times = [f"2024-01-02 10:{i:02d}" for i in range(30)]
    rows = []
    price = 100.0
    final = 100.0 * (1 + slot_return)
    step = (final - price) / 29
    for _ in range(30):
        new = price + step
        rows.append(dict(_bar(price, max(price, new), min(price, new), new), trading_date="2024-01-02"))
        price = new
    rows.append(dict(_bar(100, 101, 99, 100), trading_date="2024-01-03"))
    return _ts_window(rows, prior_times + [f"2024-01-03 {current_time}"],
                      trading_dates=["2024-01-02"] * 30 + ["2024-01-03"])


def test_same_slot_persistence_follows_prior_day_slot():
    signal = _fire_same_slot_persistence(_hks_window(0.01), reverse=False, min_return=0.002)
    assert signal is not None and signal.direction == "long"


def test_same_slot_reversal_flips_prior_day_slot():
    signal = _fire_same_slot_persistence(_hks_window(0.01), reverse=True, min_return=0.002)
    assert signal is not None and signal.direction == "short"


def test_same_slot_silent_below_threshold():
    assert _fire_same_slot_persistence(_hks_window(0.001), reverse=False, min_return=0.002) is None


def test_same_slot_silent_in_different_slot():
    # Current bar at 11:05 -> slot 3; prior day only has slot-1 bars.
    assert _fire_same_slot_persistence(_hks_window(0.01, current_time="11:05"), reverse=False, min_return=0.002) is None


# --- Phase B family/universe invariants ---------------------------------


def test_phase_b_family_sizes_and_ceiling():
    # This round's explicit, pre-agreed ceiling: roughly 400-600 TOTAL
    # distinct definitions across both granularities (see the module
    # docstring for why the DSR correction bounds the family size).
    assert len(PHASE_B_ADDITIONS_15MIN) == 156
    assert len(PATTERN_FAMILY_PHASE_B_15MIN) == 212 + 156
    assert len(PATTERN_FAMILY_PHASE_B_1MIN) == 52
    assert PHASE_B_TOTAL_TRIALS == 368 + 52
    assert 400 <= PHASE_B_TOTAL_TRIALS <= 600


def test_phase_b_pattern_ids_globally_unique_and_cited():
    all_specs = PATTERN_FAMILY_PHASE_B_15MIN + PATTERN_FAMILY_PHASE_B_1MIN
    ids = [p.pattern_id for p in all_specs]
    assert len(ids) == len(set(ids))
    assert all(p.citation.strip() for p in all_specs)
    assert all(p.pattern_id.startswith("m1_") for p in PATTERN_FAMILY_PHASE_B_1MIN)


def test_keltner_specs_scale_to_own_atr_mult():
    specs = [p for p in PATTERN_FAMILY_PHASE_B_15MIN if p.family == "keltner_reversion"]
    assert specs
    for spec in specs:
        atr_mult = float(spec.pattern_id.split("_")[3])  # keltner_reversion_{period}_{atr_mult:.1f}_{phase}
        assert spec.strength_scale == pytest.approx(atr_mult)
        assert spec.strength_is_margin is True


def test_cci_specs_scale_to_own_level():
    specs = [p for p in PATTERN_FAMILY_PHASE_B_15MIN if p.family == "cci_lambert1980"]
    assert specs
    for spec in specs:
        level = float(spec.pattern_id.split("_")[2])  # cci_{trend|reversion}_{level:.0f}_{phase}
        assert spec.strength_scale == pytest.approx(level)
        assert spec.strength_is_margin is True


def test_atr_expansion_specs_scale_to_own_atr_mult_and_are_not_margin_style():
    """Unlike Keltner (a MARGIN past the band edge), ATR expansion's strength (last_tr/atr) is already the exact raw value compared against atr_mult at the firing boundary — no reconstruction needed."""
    import re

    specs = [p for p in PATTERN_FAMILY_PHASE_B_15MIN if p.family == "atr_range_expansion"]
    assert specs
    for spec in specs:
        # atr_expansion_{continuation|exhaustion}_{atr_mult:.1f}_{phase} — phase names can contain underscores (e.g. mid_morning), so anchor on the decimal-formatted float directly rather than splitting on "_".
        atr_mult = float(re.search(r"_(\d+\.\d+)_", spec.pattern_id).group(1))
        assert spec.strength_scale == pytest.approx(atr_mult)
        assert spec.strength_is_margin is False


def test_close_streak_specs_scale_to_own_streak_len_and_stay_flat():
    """strength=float(streak_len) always exactly equals this spec's own configured streak_len (a constant, not a per-bar magnitude) — strength_scale=streak_len makes the ratio trivially 1.0 always, i.e. sizing is unaffected in practice even though strength_scale is set."""
    import re

    specs = [p for p in PATTERN_FAMILY_PHASE_B_15MIN if p.family == "close_streak_lehmann1990"]
    assert specs
    for spec in specs:
        # streak_{continuation|reversal}_{streak_len}_{phase} — phase names can contain underscores, so anchor on the bare integer directly rather than splitting on "_".
        streak_len = float(re.search(r"_(\d+)_", spec.pattern_id).group(1))
        assert spec.strength_scale == pytest.approx(streak_len)
        signal = PatternSignal(direction="long", strength=streak_len)
        assert _signal_weight_magnitude(signal, spec) == pytest.approx(1.0)


def test_donchian_and_pivot_specs_have_no_configurable_magnitude_and_stay_unweighted():
    """Both fire at a zero-distance boundary crossing (a bool `reverse` / tier `level` selector, no separate magnitude constant) — no natural threshold to reuse, so sizing stays flat per the "don't invent a new constant" rule."""
    for family in ("prior_day_level_donchian1957", "pivot_reversion_person2004"):
        specs = [p for p in PATTERN_FAMILY_PHASE_B_15MIN if p.family == family]
        assert specs, family
        assert all(p.strength_scale is None for p in specs)


def test_m1_orb_range_break_buffer_zero_stays_unweighted_nonzero_scales():
    specs = {p.pattern_id: p for p in PATTERN_FAMILY_PHASE_B_1MIN if p.family == "opening_range_breakout"}
    zero_buffer = [p for pid, p in specs.items() if pid.endswith("_0.000")]
    nonzero_buffer = [p for pid, p in specs.items() if pid.endswith("_0.001")]
    assert zero_buffer and nonzero_buffer
    for spec in zero_buffer:
        assert spec.strength_scale == pytest.approx(0.0)
        # The strength_scale<=0 guard in _signal_weight_magnitude makes this behave as unweighted in practice.
        assert _signal_weight_magnitude(PatternSignal(direction="long", strength=0.05), spec) == pytest.approx(1.0)
    for spec in nonzero_buffer:
        assert spec.strength_scale == pytest.approx(0.001)


def test_phase_b_universe_structure():
    assert len(PHASE_B_UNIVERSE_LARGE_CAP) == 150
    assert len(PHASE_B_UNIVERSE_MID_CAP) == 90
    assert len(PHASE_B_UNIVERSE_SMALL_CAP) == 44
    assert len(PHASE_B_UNIVERSE_15MIN) == len(set(PHASE_B_UNIVERSE_15MIN)) == 284
    assert len(PHASE_B_UNIVERSE_1MIN) == len(set(PHASE_B_UNIVERSE_1MIN)) == 60
    assert set(PHASE_B_UNIVERSE_1MIN) <= set(PHASE_B_UNIVERSE_15MIN)
    # Buckets must not overlap.
    assert not (set(PHASE_B_UNIVERSE_LARGE_CAP) & set(PHASE_B_UNIVERSE_MID_CAP))
    assert not (set(PHASE_B_UNIVERSE_MID_CAP) & set(PHASE_B_UNIVERSE_SMALL_CAP))


def test_phase_b_fit_windows_cover_same_day_lookups():
    assert FIT_WINDOW_BARS_15MIN >= 2 * 26  # current day + prior day at 26 bars/day
    assert FIT_WINDOW_BARS_1MIN >= 390 + 30  # prior day's same half-hour slot at 390 bars/day


# --- backtest_patterns_for_ticker / screen_pattern_groups ---------------


def test_backtest_patterns_for_ticker_matches_direct_backtest():
    bars = _synthetic_ticker_bars(seed=21, n_days=60)
    pattern = PATTERN_FAMILY[0]
    stats = backtest_patterns_for_ticker(bars, [pattern])
    direct = run_pattern_backtest(pattern, build_pattern_raw_data(bars))
    expected_returns = daily_returns_from_bar_equity(direct.day_results)
    s = stats[pattern.pattern_id]
    assert s.n_trades == len(direct.trades)
    closed = [t for t in direct.trades if not t.still_open]
    assert s.n_closed_trades == len(closed)
    assert s.n_winning_trades == sum(1 for t in closed if t.trade_return > 0)
    assert s.fired == bool(direct.trades)
    pd.testing.assert_series_equal(s.daily_returns, expected_returns)


def test_backtest_patterns_for_ticker_empty_for_short_history():
    bars = _synthetic_ticker_bars(seed=22, n_days=2)  # 14 bars < 20-bar window
    assert backtest_patterns_for_ticker(bars, [PATTERN_FAMILY[0]]) == {}


def test_screen_pattern_groups_shares_n_trials_and_sigma_across_groups():
    always_long = PatternSpec(
        pattern_id="always_long_test",
        family="test",
        citation="synthetic test fixture",
        fire_fn=lambda window: PatternSignal(direction="long", strength=1.0),
    )
    always_short = PatternSpec(
        pattern_id="always_short_test",
        family="test",
        citation="synthetic test fixture",
        fire_fn=lambda window: PatternSignal(direction="short", strength=1.0),
    )
    bars_a = {"AAA": _synthetic_ticker_bars(seed=31, n_days=40)}
    bars_b = {"BBB": _synthetic_ticker_bars(seed=32, n_days=40)}
    groups = [
        PatternScreenGroup(
            timeframe="15m",
            patterns=[always_long],
            stats_by_ticker={t: backtest_patterns_for_ticker(b, [always_long]) for t, b in bars_a.items()},
        ),
        PatternScreenGroup(
            timeframe="1m",
            patterns=[always_short],
            stats_by_ticker={t: backtest_patterns_for_ticker(b, [always_short]) for t, b in bars_b.items()},
        ),
    ]
    results = screen_pattern_groups(groups, n_trials=420)
    assert len(results) == 2
    assert {r.timeframe for r in results} == {"15m", "1m"}
    for r in results:
        # The caller's PRE-DECLARED denominator, not the surviving count.
        assert r.deflated_sharpe.n_trials == 420
    # Two included patterns across groups -> one shared sigma estimate.
    sigmas = {r.deflated_sharpe.sigma_sr_annualized for r in results}
    assert len(sigmas) == 1 and None not in sigmas


def test_screen_pattern_universe_equivalent_to_single_group_screen():
    bars_by_ticker = {
        "AAA": _synthetic_ticker_bars(seed=41, n_days=50),
        "BBB": _synthetic_ticker_bars(seed=42, n_days=50),
    }
    family = PATTERN_FAMILY[:3]
    via_universe = screen_pattern_universe(bars_by_ticker, patterns=family)
    via_groups = screen_pattern_groups(
        [
            PatternScreenGroup(
                timeframe="60m",
                patterns=family,
                stats_by_ticker={
                    t: backtest_patterns_for_ticker(b, family) for t, b in bars_by_ticker.items()
                },
            )
        ],
        n_trials=len(family),
    )
    assert [(r.pattern_id, r.sharpe_annualized, r.n_trades) for r in via_universe] == [
        (r.pattern_id, r.sharpe_annualized, r.n_trades) for r in via_groups
    ]
