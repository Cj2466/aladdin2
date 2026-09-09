import numpy as np
import pandas as pd
import pytest

from app.services.forward_validation_service import (
    MIN_FORWARD_DAYS_FOR_SHARPE,
    UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS,
    UNDERPERFORMANCE_SHARPE_THRESHOLD,
    check_underperformance,
    underperformance_advisory,
)
from app.services.research_lab.deflated_sharpe import (
    compute_return_stats,
    probabilistic_sharpe_ratio,
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


# --- the advisory (2026-09-09) -----------------------------------------------


def test_underperformance_advisory_carries_the_old_rules_verdict_unchanged():
    bad = _day_results([-0.005] * UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS)
    good = _day_results([0.001] * UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS)
    assert underperformance_advisory(bad).trailing_flag is check_underperformance(bad) is True
    assert underperformance_advisory(good).trailing_flag is check_underperformance(good) is False


def test_underperformance_advisory_below_the_floors_reports_nothing_it_cannot_support():
    a = underperformance_advisory(_day_results([-0.01] * (MIN_FORWARD_DAYS_FOR_SHARPE - 1)))
    assert a.n_realized_days == MIN_FORWARD_DAYS_FOR_SHARPE - 1
    assert a.trailing_flag is False
    assert a.trailing_sharpe_annualized is None
    assert a.whole_record_sharpe_annualized is None
    assert a.whole_record_psr_vs_zero is None


def test_whole_record_psr_is_computed_on_per_period_scale_against_zero():
    rng = np.random.default_rng(1)
    returns = list(rng.standard_normal(200) * 0.01 + 0.0005)
    a = underperformance_advisory(_day_results(returns))
    s = pd.Series(returns)
    stats = compute_return_stats(s)
    expected = probabilistic_sharpe_ratio(float(s.mean() / s.std(ddof=1)), 0.0, stats.n, stats.skewness, stats.kurtosis)
    assert a.whole_record_psr_vs_zero == expected
    assert 0.0 < a.whole_record_psr_vs_zero < 1.0
    # Feeding the ANNUALIZED Sharpe would be the unit-mixing bug deflated_sharpe's header warns about.
    assert a.whole_record_psr_vs_zero != probabilistic_sharpe_ratio(
        a.whole_record_sharpe_annualized, 0.0, stats.n, stats.skewness, stats.kurtosis
    )


def test_advisory_respects_the_familys_own_calendar():
    rng = np.random.default_rng(2)
    returns = list(rng.standard_normal(90) * 0.01 - 0.0004)
    equity = underperformance_advisory(_day_results(returns))
    crypto = underperformance_advisory(_day_results(returns), periods_per_year=365.0)
    assert crypto.trailing_sharpe_annualized == pytest.approx(
        equity.trailing_sharpe_annualized * (365.0 / 252.0) ** 0.5
    )
    # PSR is per-period and does not depend on the calendar at all.
    assert crypto.whole_record_psr_vs_zero == equity.whole_record_psr_vs_zero
