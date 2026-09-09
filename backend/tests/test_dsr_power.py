"""dsr_power: the gate's sensitivity, validated against synthetic data with a
known true Sharpe (CLAUDE.md: never trust a formula on sight)."""

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.deflated_sharpe import (
    MIN_TRIALS_FOR_DSR,
    compute_return_stats,
    expected_max_sharpe_under_noise,
    probabilistic_sharpe_ratio,
)
from app.services.research_lab.dsr_power import (
    POWER_FLOOR,
    DsrPowerError,
    dsr_power_report,
    min_detectable_sharpe,
    power_to_pass,
    required_observed_sharpe,
    years_to_detect,
)

PPY = 252.0


def _empirical_pass_rate(rng, true_sharpe_ann, n_obs, n_trials, sigma_ann, threshold, reps):
    s = true_sharpe_ann / np.sqrt(PPY)
    sr0 = expected_max_sharpe_under_noise(sigma_ann / np.sqrt(PPY), n_trials)
    x = rng.standard_normal((reps, n_obs)) + s
    sr_hat = x.mean(axis=1) / x.std(axis=1, ddof=1)
    passes = 0
    for i in range(reps):
        stats = compute_return_stats(pd.Series(x[i]))
        psr = probabilistic_sharpe_ratio(sr_hat[i], sr0, n_obs, stats.skewness, stats.kurtosis)
        passes += int(psr is not None and psr >= threshold)
    return passes / reps


def test_required_sharpe_is_exactly_where_the_projects_own_dsr_crosses_the_bar():
    req = required_observed_sharpe(threshold=0.95, n_observations=2926, n_trials=12, sigma_sr_annualized=0.19)
    sr0 = expected_max_sharpe_under_noise(0.19 / np.sqrt(PPY), 12)
    just_below = probabilistic_sharpe_ratio((req - 1e-6) / np.sqrt(PPY), sr0, 2926, 0.0, 3.0)
    at = probabilistic_sharpe_ratio(req / np.sqrt(PPY), sr0, 2926, 0.0, 3.0)
    assert just_below < 0.95 <= at


@pytest.mark.parametrize(
    "true_sharpe, n_obs, n_trials, sigma, threshold",
    [(0.5, 600, 12, 0.19, 0.95), (1.0, 600, 12, 0.19, 0.95), (0.5, 600, 12, 0.19, 0.50), (0.0, 600, 12, 0.19, 0.95)],
)
def test_analytic_power_matches_monte_carlo_with_known_true_sharpe(true_sharpe, n_obs, n_trials, sigma, threshold):
    rng = np.random.default_rng(7)
    reps = 3000
    analytic = power_to_pass(
        true_sharpe_annualized=true_sharpe,
        threshold=threshold,
        n_observations=n_obs,
        n_trials=n_trials,
        sigma_sr_annualized=sigma,
    )
    empirical = _empirical_pass_rate(rng, true_sharpe, n_obs, n_trials, sigma, threshold, reps)
    se = np.sqrt(max(empirical * (1 - empirical), 1e-4) / reps)
    assert abs(empirical - analytic) < 3.5 * se + 0.005, (analytic, empirical, se)


def test_power_is_monotone_in_true_sharpe_and_in_sample_length():
    common = {"threshold": 0.95, "n_trials": 12, "sigma_sr_annualized": 0.19}
    p = [power_to_pass(true_sharpe_annualized=s, n_observations=2926, **common) for s in (0.2, 0.5, 0.8, 1.2)]
    assert p == sorted(p) and p[-1] > p[0]
    q = [power_to_pass(true_sharpe_annualized=0.5, n_observations=n, **common) for n in (500, 2926, 10_000)]
    assert q == sorted(q) and q[-1] > q[0]


def test_required_sharpe_rises_with_the_bar_and_with_the_denominator():
    common = {"n_observations": 2926, "sigma_sr_annualized": 0.19}
    assert required_observed_sharpe(threshold=0.95, n_trials=12, **common) > required_observed_sharpe(
        threshold=0.50, n_trials=12, **common
    )
    assert required_observed_sharpe(threshold=0.95, n_trials=1031, **common) > required_observed_sharpe(
        threshold=0.95, n_trials=12, **common
    )


def test_the_audit_headline_reproduces_a_true_half_sharpe_is_invisible_at_this_sample_length():
    # criteria_audit_2026-09-09 F1: at ~11.6y daily, N=12, the 0.95 bar needs
    # an OBSERVED Sharpe of ~0.80 — which is where a true 0.80 has only 50%
    # power. At the 80% floor the minimum detectable true Sharpe is ~1.05
    # (validate_dsr_power_output.txt: 1.047), and a true 0.5 has ~15% power.
    power = power_to_pass(true_sharpe_annualized=0.5, threshold=0.95, n_observations=2926, n_trials=12, sigma_sr_annualized=0.19)
    assert 0.10 < power < 0.20
    req = required_observed_sharpe(threshold=0.95, n_observations=2926, n_trials=12, sigma_sr_annualized=0.19)
    assert 0.75 < req < 0.85
    assert power_to_pass(true_sharpe_annualized=req, threshold=0.95, n_observations=2926, n_trials=12, sigma_sr_annualized=0.19) == pytest.approx(0.5, abs=0.01)
    mds = min_detectable_sharpe(threshold=0.95, n_observations=2926, n_trials=12, sigma_sr_annualized=0.19)
    assert 0.95 < mds < 1.15
    assert power_to_pass(true_sharpe_annualized=mds, threshold=0.95, n_observations=2926, n_trials=12, sigma_sr_annualized=0.19) == pytest.approx(POWER_FLOOR, abs=1e-6)


def test_years_to_detect_is_consistent_with_power_at_that_length():
    yrs = years_to_detect(true_sharpe_annualized=0.5, threshold=0.95, n_trials=12, sigma_sr_annualized=0.19)
    assert yrs is not None and yrs > 11.6  # more data than the families actually have
    n_obs = round(yrs * PPY)
    p = power_to_pass(true_sharpe_annualized=0.5, threshold=0.95, n_observations=n_obs, n_trials=12, sigma_sr_annualized=0.19)
    assert p == pytest.approx(POWER_FLOOR, abs=2e-3)
    assert years_to_detect(true_sharpe_annualized=0.0, threshold=0.95, n_trials=12, sigma_sr_annualized=0.19) is None


def test_report_flags_underpowered_only_below_the_floor():
    weak = dsr_power_report(claimed_sharpe_annualized=0.5, threshold=0.95, n_observations=2926, n_trials=12, sigma_sr_annualized=0.19)
    assert weak.underpowered and weak.power_at_claimed_sharpe < POWER_FLOOR
    strong = dsr_power_report(claimed_sharpe_annualized=1.5, threshold=0.95, n_observations=2926, n_trials=12, sigma_sr_annualized=0.19)
    assert not strong.underpowered and strong.power_at_claimed_sharpe >= POWER_FLOOR
    assert "UNDERPOWERED" in weak.summary() and "adequately powered" in strong.summary()


def test_refuses_inputs_the_gate_itself_cannot_score():
    with pytest.raises(DsrPowerError):
        required_observed_sharpe(threshold=0.95, n_observations=2926, n_trials=MIN_TRIALS_FOR_DSR - 1, sigma_sr_annualized=0.19)
    with pytest.raises(DsrPowerError):
        required_observed_sharpe(threshold=1.0, n_observations=2926, n_trials=12, sigma_sr_annualized=0.19)
    with pytest.raises(DsrPowerError):
        required_observed_sharpe(threshold=0.95, n_observations=2, n_trials=12, sigma_sr_annualized=0.19)


def test_fat_tails_lower_power_so_the_normal_case_is_an_upper_bound():
    normal = power_to_pass(true_sharpe_annualized=0.8, threshold=0.95, n_observations=2926, n_trials=12, sigma_sr_annualized=0.19)
    fat = power_to_pass(
        true_sharpe_annualized=0.8, threshold=0.95, n_observations=2926, n_trials=12, sigma_sr_annualized=0.19, kurtosis=9.0
    )
    assert fat < normal
