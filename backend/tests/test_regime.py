import numpy as np
import pandas as pd

from app.services.research_lab.regime import (
    VR_AGGREGATION_Q,
    VR_WINDOW_DAYS,
    classify_regime,
    compute_variance_ratio,
)


def _ar1_return_price_series(n: int, phi: float, eps_std: float, seed: int) -> np.ndarray:
    """AR(1)-on-*returns* process — genuinely distinct from the i.i.d.-return
    drift-only fixtures used elsewhere (_trend_price_series/_flat_price_series):
    the variance ratio test is drift-invariant by construction (it demeans
    returns first) and only responds to serial correlation in returns."""
    rng = np.random.default_rng(seed)
    eps = rng.normal(0, eps_std, n)
    r = np.zeros(n)
    for t in range(1, n):
        r[t] = phi * r[t - 1] + eps[t]
    log_price = np.cumsum(r)
    return 100 * np.exp(log_price)


def _trend_price_series(n: int, drift: float, noise_std: float, seed: int) -> np.ndarray:
    # Same construction as test_momentum.py/test_screening.py's own verified fixture —
    # reused here specifically to prove VR tests a different statistical object.
    rng = np.random.default_rng(seed)
    log_price = np.cumsum(rng.normal(drift, noise_std, n))
    return 100 * np.exp(log_price)


# --- compute_variance_ratio --------------------------------------------------


def test_compute_variance_ratio_trending():
    prices = _ar1_return_price_series(91, phi=0.4, eps_std=0.01, seed=0)
    log_returns = np.diff(np.log(prices))
    vr, _z, p = compute_variance_ratio(log_returns, VR_AGGREGATION_Q)
    assert vr > 1
    assert p <= 0.05


def test_compute_variance_ratio_mean_reverting():
    prices = _ar1_return_price_series(91, phi=-0.4, eps_std=0.01, seed=2)
    log_returns = np.diff(np.log(prices))
    vr, _z, p = compute_variance_ratio(log_returns, VR_AGGREGATION_Q)
    assert vr < 1
    assert p <= 0.05


def test_compute_variance_ratio_random_walk_is_indeterminate():
    rng = np.random.default_rng(0)
    prices = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 91)))
    log_returns = np.diff(np.log(prices))
    _vr, _z, p = compute_variance_ratio(log_returns, VR_AGGREGATION_Q)
    assert p > 0.05


def test_compute_variance_ratio_returns_none_for_short_window():
    log_returns = np.array([0.01, -0.02, 0.005])
    assert compute_variance_ratio(log_returns, q=5) is None


def test_compute_variance_ratio_returns_none_for_zero_variance():
    log_returns = np.zeros(20)
    assert compute_variance_ratio(log_returns, q=5) is None


# --- classify_regime ----------------------------------------------------------


def test_classify_regime_labels_match_synthetic_fixtures():
    trending_prices = pd.Series(_ar1_return_price_series(91, phi=0.4, eps_std=0.01, seed=0))
    assert classify_regime(trending_prices).regime == "trending"

    mean_reverting_prices = pd.Series(_ar1_return_price_series(91, phi=-0.4, eps_std=0.01, seed=2))
    assert classify_regime(mean_reverting_prices).regime == "mean_reverting"

    rng = np.random.default_rng(0)
    random_walk_prices = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 91))))
    assert classify_regime(random_walk_prices).regime == "indeterminate"


def test_classify_regime_returns_none_below_window_plus_one_rows():
    short_prices = pd.Series(_ar1_return_price_series(VR_WINDOW_DAYS, phi=0.4, eps_std=0.01, seed=0))
    assert classify_regime(short_prices) is None


def test_classify_regime_mechanistically_distinct_from_momentum_trend():
    """Locks in the empirical cross-check as a permanent regression test:
    feeding momentum's own significance-gate-tripping trend fixture through
    VR must land 'indeterminate', proving VR responds to return serial
    correlation, not to a price-level trend."""
    prices = pd.Series(_trend_price_series(91, drift=0.003, noise_std=0.0005, seed=42))
    classification = classify_regime(prices)
    assert classification is not None
    assert classification.regime == "indeterminate"
