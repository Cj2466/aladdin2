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


# --- version 2 (adopted 2026-09-09): CUSUM at protect 1.0 -----------------------

from app.services.research_lab.retirement_rule import (  # noqa: E402
    CUSUM_BOUNDARY_V2,
    DEFAULT_BUCKET_WHEN_UNMEASURED,
    RULE_ID_V2,
    S0_PROTECT_V2,
    cusum_path,
    evaluate_cusum,
)


def test_cusum_known_answer_constant_increments():
    # constant +a increments accumulate linearly; constant -a stay at zero (Page's reset)
    import numpy as np
    from app.services.research_lab import retirement_rule as rr

    orig = rr.llr_increments
    try:
        rr.llr_increments = lambda *a, **k: np.full(10, 0.3)
        assert np.allclose(cusum_path(pd.Series(np.zeros(10))), 0.3 * np.arange(1, 11))
        rr.llr_increments = lambda *a, **k: np.full(10, -0.3)
        assert np.all(cusum_path(pd.Series(np.zeros(10))) == 0.0)
    finally:
        rr.llr_increments = orig


def test_v2_uses_protect_1_and_recommends_on_a_harmful_record_but_not_a_good_one():
    assert S0_PROTECT_V2 == 1.0
    bad = _series(700, mean=-3.0 / np.sqrt(PPY) * 0.01, seed=11)
    good = _series(700, mean=+3.0 / np.sqrt(PPY) * 0.01, seed=12)
    a = evaluate_cusum(bad, BUCKET_LOW)
    assert a.rule_id == RULE_ID_V2 and a.triggered and a.first_trigger_day >= MIN_DAYS
    assert a.boundary == CUSUM_BOUNDARY_V2[BUCKET_LOW]
    g = evaluate_cusum(good, BUCKET_LOW)
    assert not g.triggered and g.statistic < 0.5  # a good record keeps the CUSUM near its reset at zero


def test_v2_unmeasured_bucket_defaults_to_the_boundary_that_recommends_least():
    a = evaluate_cusum(_series(200, 0.0, seed=13), None)
    assert a.bucket == DEFAULT_BUCKET_WHEN_UNMEASURED == BUCKET_HIGH
    assert a.boundary == max(CUSUM_BOUNDARY_V2.values()) and "not measured" in a.note


def test_v2_boundaries_are_the_ones_the_gate_output_recorded_at_s0_1():
    text = open("data/research_runs/retirement_rule_2026-09-09/retirement_rule_gates_output.txt").read()
    assert "boundaries LOW (phi_hat <= 0.10): S-A PSR floor: 0.0240, S-B SPRT: 3.8842, S-C CUSUM: 5.8180" in text
    assert "boundaries HIGH (phi_hat > 0.10): S-A PSR floor: 0.0050, S-B SPRT: 5.6814, S-C CUSUM: 7.9806" in text
    assert CUSUM_BOUNDARY_V2 == {BUCKET_LOW: 5.8180, BUCKET_HIGH: 7.9806}


def test_advisory_bundle_carries_the_v2_recommendation_without_touching_status():
    from app.services.forward_validation_service import underperformance_advisory

    days = [{"net_return": float(x)} for x in _series(400, -0.006, seed=14)]
    adv = underperformance_advisory(days)
    assert adv.retirement_rule_id == RULE_ID_V2 and adv.retirement_bucket == BUCKET_HIGH
    assert adv.retirement_recommended is True and adv.retirement_first_trigger_day >= MIN_DAYS
    short = underperformance_advisory(days[:10])
    assert short.retirement_recommended is False and short.retirement_statistic is None
