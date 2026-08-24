from app.services.forward_validation_service import (
    UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS,
    UNDERPERFORMANCE_SHARPE_THRESHOLD,
    check_underperformance,
)


def _day_results(net_returns: list[float]) -> list[dict]:
    return [{"net_return": r} for r in net_returns]


def test_check_underperformance_false_below_lookback_floor():
    # Only 10 days of clearly bad returns — below the 60-day floor, so
    # there isn't enough data to judge yet.
    day_results = _day_results([-0.01] * 10)
    assert check_underperformance(day_results) is False


def test_check_underperformance_true_for_consistently_negative_trailing_window():
    day_results = _day_results([-0.005] * UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS)
    assert check_underperformance(day_results) is True


def test_check_underperformance_false_for_consistently_positive_trailing_window():
    day_results = _day_results([0.001] * UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS)
    assert check_underperformance(day_results) is False


def test_check_underperformance_uses_only_trailing_window_not_full_history():
    # A long bad stretch followed by a recent good stretch of exactly the
    # lookback length must NOT be flagged — an old bad period must not
    # mask, and a good period must not be masked by, the trailing window.
    bad = _day_results([-0.02] * 200)
    good = _day_results([0.002] * UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS)
    day_results = bad + good
    assert check_underperformance(day_results) is False


def test_check_underperformance_recent_bad_stretch_flagged_despite_old_good_history():
    # The inverse: a long good history followed by a recent bad trailing
    # window must be flagged — an old good stretch must not mask it.
    good = _day_results([0.002] * 200)
    bad = _day_results([-0.02] * UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS)
    day_results = good + bad
    assert check_underperformance(day_results) is True


def test_underperformance_sharpe_threshold_is_negative():
    assert UNDERPERFORMANCE_SHARPE_THRESHOLD < 0
