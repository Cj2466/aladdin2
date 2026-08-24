import numpy as np
import pandas as pd
from scipy.stats import norm

from app.services.research_lab.deflated_sharpe import (
    MIN_TRIALS_FOR_DSR,
    compute_deflated_sharpe,
    compute_return_stats,
    derive_returns_from_equity_curve,
    expected_max_sharpe_under_noise,
    probabilistic_sharpe_ratio,
)

# --- probabilistic_sharpe_ratio ----------------------------------------------


def test_psr_zero_effect_closed_form():
    # sr_hat == sr_benchmark -> numerator is 0 regardless of skew/kurtosis,
    # as long as denom_sq > 0 (verified denom_sq=1 here).
    assert probabilistic_sharpe_ratio(0.0, 0.0, n_observations=100, skewness=1.5, kurtosis=6.0) == 0.5


def test_psr_normal_case_reduction():
    # skew=0, kurt=3 must reduce exactly to the classic Mertens (2002) form.
    for sr_hat, n in [(0.3, 500), (-0.15, 60), (0.05, 750), (1.2, 30)]:
        actual = probabilistic_sharpe_ratio(sr_hat, 0.0, n, skewness=0.0, kurtosis=3.0)
        expected = float(norm.cdf(sr_hat * np.sqrt(n - 1) / np.sqrt(1 + sr_hat**2 / 2)))
        assert actual == expected


def test_psr_negative_variance_term_returns_none():
    # skew=3, kurt=1.5, sr=1 -> denom_sq = 1 - 3*1 + (0.5/4)*1 = -1.875
    assert probabilistic_sharpe_ratio(2.0, -1.0, n_observations=100, skewness=3.0, kurtosis=1.5) is None


def test_psr_returns_none_below_two_observations():
    assert probabilistic_sharpe_ratio(0.1, 0.0, n_observations=1, skewness=0.0, kurtosis=3.0) is None


# --- expected_max_sharpe_under_noise -----------------------------------------


def test_sr0_degenerate_at_one_trial():
    assert expected_max_sharpe_under_noise(1.0, n_trials=1) is None


def test_sr0_reference_value():
    # independently verified this session: sigma_sr=0.3, N=5 -> 0.357778
    value = expected_max_sharpe_under_noise(0.3, n_trials=5)
    assert value is not None
    assert abs(value - 0.357778) < 1e-3


def test_sr0_monotonic_in_n_trials():
    values = [expected_max_sharpe_under_noise(0.3, n) for n in [2, 5, 10, 20, 50, 100, 300, 500, 1000]]
    assert all(v is not None for v in values)
    assert values == sorted(values)
    assert len(set(values)) == len(values)  # strictly increasing, no ties


# --- compute_return_stats ----------------------------------------------------


def test_compute_return_stats_degenerate_std_returns_none():
    assert compute_return_stats(pd.Series([0.01] * 50)) is None


def test_compute_return_stats_below_floor_returns_none():
    assert compute_return_stats(pd.Series([0.01])) is None


# --- derive_returns_from_equity_curve ----------------------------------------


def test_derive_returns_from_equity_curve_matches_engine():
    # Exact 5-day step_one_day replay from this session's verification:
    # net_return=[-0.01, 0.02, 0.0, -0.04, 0.0] -> equity built up from 1.0.
    equity_values = [0.99, 1.0098, 1.0098, 0.969408, 0.969408]
    expected = [-0.01, 0.02, 0.0, -0.04, 0.0]
    derived = derive_returns_from_equity_curve(equity_values).to_numpy()
    assert np.allclose(derived, expected, atol=1e-9)
    assert len(derived) == len(equity_values)  # no off-by-one undercount


# --- compute_deflated_sharpe (orchestrator) ----------------------------------


def _synthetic_returns(n: int, seed: int) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(0.0005, 0.01, n))


def test_dsr_monotonic_in_n_trials():
    # sr_hat_daily=0.05, n=750, sigma_sr_annualized=0.35 — exact setup
    # independently verified this session (finding H).
    sharpe_net_annualized = 0.05 * np.sqrt(252)
    returns = _synthetic_returns(750, seed=1)

    dsr_values = []
    for n_trials in [5, 10, 20, 50, 100, 300]:  # >= MIN_TRIALS_FOR_DSR; below-floor behavior is its own test
        result = compute_deflated_sharpe(sharpe_net_annualized, returns, n_trials, sigma_sr_annualized=0.35)
        assert result.dsr is not None
        dsr_values.append(result.dsr)

    assert dsr_values == sorted(dsr_values, reverse=True)


def test_dsr_below_floor_still_computes_psr():
    returns = _synthetic_returns(100, seed=2)
    sharpe_net_annualized = 0.3
    result = compute_deflated_sharpe(sharpe_net_annualized, returns, n_trials=3, sigma_sr_annualized=0.4)
    assert result.dsr_floor_met is False
    assert result.dsr is None
    assert result.psr_vs_zero is not None
    assert "not enough" in result.interpretation.lower()


def test_dsr_floor_met_with_sufficient_trials():
    returns = _synthetic_returns(200, seed=3)
    sharpe_net_annualized = 0.5
    result = compute_deflated_sharpe(sharpe_net_annualized, returns, n_trials=MIN_TRIALS_FOR_DSR, sigma_sr_annualized=0.3)
    assert result.dsr_floor_met is True
    assert result.dsr is not None
    assert 0 <= result.dsr <= 1
    assert 0 <= result.psr_vs_zero <= 1


def test_dsr_none_sigma_sr_skips_deflation():
    returns = _synthetic_returns(100, seed=4)
    result = compute_deflated_sharpe(0.3, returns, n_trials=10, sigma_sr_annualized=None)
    assert result.dsr is None
    assert result.expected_max_sharpe_noise_annualized is None
    assert result.psr_vs_zero is not None


def test_dsr_insufficient_observations_returns_none_gracefully():
    result = compute_deflated_sharpe(0.3, pd.Series([0.01]), n_trials=10, sigma_sr_annualized=0.3)
    assert result.psr_vs_zero is None
    assert result.dsr is None
    assert "not enough" in result.interpretation.lower()
