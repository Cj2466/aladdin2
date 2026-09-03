"""Tests for preservation_score.py.

Every expected value here is derived from the formula by hand (or from a
deliberately-constructed series with a known answer), never copied out of a
run of the code under test.
"""

import math

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.metrics import sharpe_ratio
from app.services.research_lab.preservation_score import (
    MDD_FLOOR,
    MIN_HALF_OBSERVATIONS,
    OOS_RETENTION,
    compute_preservation_metrics,
    equity_curve,
    split_half_sharpes,
    turnover_bucket,
)


def _series(values) -> pd.Series:
    idx = pd.bdate_range("2015-01-05", periods=len(values))
    return pd.Series(list(values), index=idx)


def _noisy(n, mean, sd, seed):
    rng = np.random.default_rng(seed)
    return _series(rng.normal(mean, sd, n))


def test_oos_retention_is_the_mclean_pontiff_post_publication_figure():
    """0.42 = 1 - 0.58. Pinned so a later edit cannot quietly move the
    literature anchor the module docstring justifies."""
    assert OOS_RETENTION == pytest.approx(1.0 - 0.58)


def test_equity_curve_compounds_rather_than_sums():
    curve = equity_curve(_series([0.1, 0.1]))
    assert curve.iloc[-1] == pytest.approx(1.21)  # 1.1 * 1.1, not 1.20


def test_max_drawdown_is_measured_on_the_compounded_path():
    # +50%, then -50%: peak 1.5, trough 0.75 -> drawdown exactly -50%.
    m = compute_preservation_metrics(_series([0.5, -0.5]), dsr=1.0)
    assert m.max_drawdown == pytest.approx(-0.5)


def test_split_half_sharpes_splits_by_position_and_gives_the_odd_day_to_the_second_half():
    n = 2 * MIN_HALF_OBSERVATIONS + 1
    values = [0.0] * n
    values[-1] = 1.0  # the single non-zero day lands in the second half
    s1, s2 = split_half_sharpes(_series(values))
    assert s1 == 0.0  # first half is all zeros -> zero std -> 0.0 by convention
    assert s2 > 0.0


def test_split_half_sharpes_refuses_a_sample_too_short_to_halve():
    short = _series([0.001] * (2 * MIN_HALF_OBSERVATIONS - 2))
    assert split_half_sharpes(short) == (None, None)


def test_split_half_sharpes_matches_sharpe_ratio_on_each_half():
    r = _noisy(600, 0.0004, 0.01, seed=7)
    s1, s2 = split_half_sharpes(r)
    assert s1 == pytest.approx(sharpe_ratio(r.iloc[:300]))
    assert s2 == pytest.approx(sharpe_ratio(r.iloc[300:]))


def test_risk_quality_is_the_signed_geometric_mean_of_sharpe_and_calmar():
    r = _noisy(1000, 0.0005, 0.01, seed=11)
    m = compute_preservation_metrics(r, dsr=1.0)
    assert m.risk_quality == pytest.approx(math.sqrt(abs(m.sharpe_full) * abs(m.calmar)))
    assert m.calmar == pytest.approx(m.annualized_return / abs(m.max_drawdown))


def test_a_losing_spec_keeps_a_negative_risk_quality_rather_than_folding_to_zero():
    m = compute_preservation_metrics(_noisy(1000, -0.0005, 0.01, seed=13), dsr=0.5)
    assert m.sharpe_full < 0
    assert m.risk_quality < 0
    assert m.preservation_score_no_stab < 0


def test_the_full_score_is_retention_times_credibility_times_rq_times_stability():
    r = _noisy(1200, 0.0004, 0.01, seed=17)
    m = compute_preservation_metrics(r, dsr=0.8)
    assert m.preservation_score_no_stab == pytest.approx(
        OOS_RETENTION * 0.8 * m.risk_quality
    )
    assert m.preservation_score == pytest.approx(m.preservation_score_no_stab * m.stability)


def test_stability_is_zero_when_one_half_lost_money():
    """All the edge in the first half, a losing second half -> stab == 0 and
    the full score is zeroed even though the full-sample Sharpe is positive."""
    n = 600
    rng = np.random.default_rng(23)
    first = rng.normal(0.0020, 0.005, n // 2)
    second = rng.normal(-0.0004, 0.005, n // 2)
    r = _series(np.concatenate([first, second]))
    m = compute_preservation_metrics(r, dsr=0.9)
    assert m.sharpe_full > 0
    assert m.sharpe_second_half < 0
    assert m.stability == 0.0
    assert m.preservation_score == 0.0
    assert m.preservation_score_no_stab > 0  # still visible in the variant


def test_stability_is_capped_at_one_so_an_improving_second_half_is_not_rewarded():
    n = 800
    rng = np.random.default_rng(29)
    first = rng.normal(0.0002, 0.005, n // 2)
    second = rng.normal(0.0020, 0.005, n // 2)
    m = compute_preservation_metrics(_series(np.concatenate([first, second])), dsr=1.0)
    assert m.sharpe_second_half > m.sharpe_first_half
    assert m.stability <= 1.0


def test_sharpe_decay_is_second_half_minus_first_half():
    r = _noisy(900, 0.0003, 0.01, seed=31)
    m = compute_preservation_metrics(r, dsr=0.5)
    assert m.sharpe_decay == pytest.approx(m.sharpe_second_half - m.sharpe_first_half)


def test_mdd_floor_is_applied_and_flagged_rather_than_silently_rescaling():
    """A strictly-monotone gaining series has ~zero drawdown; without the
    floor its Calmar would be unbounded."""
    r = _series([0.0001] * 600)
    m = compute_preservation_metrics(r, dsr=1.0)
    assert m.mdd_floor_hit is True
    assert m.calmar == pytest.approx(m.annualized_return / MDD_FLOOR)


def test_a_missing_dsr_scores_zero_credibility_not_full_credit():
    r = _noisy(800, 0.0005, 0.01, seed=37)
    m = compute_preservation_metrics(r, dsr=None)
    assert m.credibility == 0.0
    assert m.preservation_score == 0.0
    assert m.preservation_score_no_stab == 0.0


def test_credibility_is_clipped_into_the_unit_interval():
    r = _noisy(800, 0.0005, 0.01, seed=41)
    assert compute_preservation_metrics(r, dsr=1.7).credibility == 1.0
    assert compute_preservation_metrics(r, dsr=-0.3).credibility == 0.0


def test_a_sample_too_short_to_halve_gets_zero_stability_not_a_guessed_one():
    r = _noisy(2 * MIN_HALF_OBSERVATIONS - 4, 0.0005, 0.01, seed=43)
    m = compute_preservation_metrics(r, dsr=0.9)
    assert m.sharpe_first_half is None
    assert m.sharpe_decay is None
    assert m.stability == 0.0
    assert m.preservation_score == 0.0
    assert m.preservation_score_no_stab != 0.0


def test_crypto_periods_per_year_flows_through_to_every_annualized_term():
    r = _noisy(1000, 0.0005, 0.01, seed=47)
    eq = compute_preservation_metrics(r, dsr=1.0, periods_per_year=252)
    crypto = compute_preservation_metrics(r, dsr=1.0, periods_per_year=365)
    assert crypto.sharpe_full == pytest.approx(eq.sharpe_full * math.sqrt(365 / 252))
    assert crypto.annualized_return == pytest.approx(eq.annualized_return * 365 / 252)


def test_nan_days_are_dropped_rather_than_poisoning_the_whole_series():
    values = [0.001] * 500 + [float("nan")] + [0.001] * 500
    m = compute_preservation_metrics(_series(values), dsr=0.5)
    assert m.n_observations == 1000
    assert np.isfinite(m.sharpe_full)


def test_an_empty_series_raises_rather_than_returning_a_zero_score():
    with pytest.raises(ValueError):
        compute_preservation_metrics(pd.Series(dtype=float), dsr=0.5)


def test_turnover_bucket_boundary_is_inclusive_at_63_and_never_guesses():
    assert turnover_bucket(62) == "high_turnover"
    assert turnover_bucket(63) == "low_turnover"
    assert turnover_bucket(252) == "low_turnover"
    assert turnover_bucket(None) is None


def test_as_dict_round_trips_every_field():
    m = compute_preservation_metrics(_noisy(900, 0.0004, 0.01, seed=53), dsr=0.7)
    d = m.as_dict()
    assert d["preservation_score"] == m.preservation_score
    assert set(d) == {
        "n_observations",
        "periods_per_year",
        "sharpe_full",
        "annualized_return",
        "max_drawdown",
        "calmar",
        "mdd_floor_hit",
        "risk_quality",
        "sharpe_first_half",
        "sharpe_second_half",
        "sharpe_decay",
        "stability",
        "credibility",
        "preservation_score",
        "preservation_score_no_stab",
    }
