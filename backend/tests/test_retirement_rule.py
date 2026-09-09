"""The forward-retirement rule: SPRT on standardized net daily returns with a
simulation-calibrated boundary; recommendation only."""

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.dormant_pool import BUCKET_HIGH, BUCKET_LOW
from app.services.research_lab.retirement_rule import (
    MIN_DAYS,
    S0_PROTECT,
    S1_HARM,
    SPRT_BOUNDARY,
    RetirementRuleError,
    evaluate,
    llr_increments,
    sprt_path,
)

PPY = 252.0


def _series(n, mean, seed, sd=0.01):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-02", periods=n, freq="B")
    return pd.Series(rng.standard_normal(n) * sd + mean, index=idx)


def test_increment_is_the_elementary_gaussian_llr_on_the_standardized_return():
    # Hand-built: three returns; day 1 has z=0 (no sd yet) so contributes -d*m, as the
    # gate script's llr_along does; day t uses the expanding sd (ddof=1)
    r = pd.Series([0.01, -0.02, 0.03])
    l = llr_increments(r)
    d = (S1_HARM - S0_PROTECT) / np.sqrt(PPY)
    m = (S1_HARM + S0_PROTECT) / (2 * np.sqrt(PPY))
    assert l[0] == pytest.approx(d * (0.0 - m))
    sd2 = np.std([0.01, -0.02], ddof=1)
    sd3 = np.std([0.01, -0.02, 0.03], ddof=1)
    assert l[1] == pytest.approx(d * (-0.02 / sd2 - m))
    assert l[2] == pytest.approx(d * (0.03 / sd3 - m))


def test_known_answer_a_strongly_negative_record_triggers_and_a_strongly_positive_one_never_does():
    # true Sharpe far below the harm level: Lambda drifts up by ~KL per day
    bad = _series(600, mean=-3.0 / np.sqrt(PPY) * 0.01, seed=1)
    good = _series(600, mean=+3.0 / np.sqrt(PPY) * 0.01, seed=2)
    a = evaluate(bad, BUCKET_LOW)
    assert a.triggered and a.first_trigger_day >= MIN_DAYS and a.statistic >= SPRT_BOUNDARY[BUCKET_LOW]
    g = evaluate(good, BUCKET_LOW)
    assert not g.triggered and g.statistic < 0


def test_expected_drift_matches_the_kl_arithmetic_in_the_preregistration():
    # Under truth s, E[l] per day ~ d*(s/sqrt(252) - m); over 100k days the mean is close
    rng = np.random.default_rng(3)
    for s in (-1.0, 0.5):
        r = pd.Series(rng.standard_normal(100_000) + s / np.sqrt(PPY))
        d = (S1_HARM - S0_PROTECT) / np.sqrt(PPY)
        m = (S1_HARM + S0_PROTECT) / (2 * np.sqrt(PPY))
        expected = d * (s / np.sqrt(PPY) - m)
        assert llr_increments(r).mean() == pytest.approx(expected, abs=2e-4)
    # and the two drifts are equal and opposite (the symmetric KL of the two simple hypotheses)
    assert abs(expected) == pytest.approx((S1_HARM - S0_PROTECT) ** 2 / (2 * PPY), rel=1e-9)


def test_below_the_floor_nothing_is_evaluated_and_the_path_is_a_cumsum():
    r = _series(MIN_DAYS - 1, 0.0, seed=4)
    a = evaluate(r, BUCKET_LOW)
    assert not a.triggered and a.statistic is None and "floor" in a.note
    assert np.allclose(sprt_path(r), np.cumsum(llr_increments(r)))


def test_high_bucket_has_no_calibrated_rule_and_says_so():
    a = evaluate(_series(400, -0.005, seed=5), BUCKET_HIGH)
    assert a.boundary is None and not a.triggered and "no calibrated rule" in a.note


def test_first_trigger_day_is_the_first_day_at_or_after_the_floor_where_lambda_crosses():
    r = _series(300, -0.004, seed=6)
    a = evaluate(r, BUCKET_LOW)
    path = sprt_path(r)
    if a.triggered:
        k = a.first_trigger_day
        assert path[k - 1] >= SPRT_BOUNDARY[BUCKET_LOW]
        assert np.all(path[MIN_DAYS - 1 : k - 1] < SPRT_BOUNDARY[BUCKET_LOW])
    else:
        assert np.all(path[MIN_DAYS - 1 :] < SPRT_BOUNDARY[BUCKET_LOW])


def test_unknown_bucket_raises():
    with pytest.raises(RetirementRuleError):
        evaluate(_series(100, 0.0, seed=7), "MEDIUM")


def test_the_boundary_is_the_one_the_gate_output_recorded():
    text = open("data/research_runs/retirement_rule_2026-09-09/retirement_rule_gates_output.txt").read()
    assert "boundaries LOW (phi_hat <= 0.10): S-A PSR floor: 0.0089, S-B SPRT: 3.7087" in text
    assert SPRT_BOUNDARY[BUCKET_LOW] == 3.7087
