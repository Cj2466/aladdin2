import numpy as np
import pandas as pd

from app.services.research_lab.regime_hmm import HMM_WINDOW_TRADING_DAYS, classify_regime_hmm


def _two_regime_price_series(
    n: int, seed: int, first_std: float, second_std: float, switch_at: int | None = None
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    if switch_at is None:
        switch_at = n // 2
    returns = np.concatenate([rng.normal(0, first_std, switch_at), rng.normal(0, second_std, n - switch_at)])
    log_price = np.cumsum(returns)
    return 100 * np.exp(log_price)


def test_classify_regime_hmm_labels_currently_high_vol_correctly():
    # Empirically verified 2026-08-25 across seeds 0-7 at n=HMM_WINDOW_TRADING_DAYS+1:
    # low-vol-then-high-vol always classifies the final day as high_vol.
    n = HMM_WINDOW_TRADING_DAYS + 1
    prices = pd.Series(_two_regime_price_series(n, seed=0, first_std=0.005, second_std=0.02))
    result = classify_regime_hmm(prices)
    assert result is not None
    assert result.label == "high_vol"
    assert result.confidence > 0.5
    assert result.expected_duration_days > 0


def test_classify_regime_hmm_labels_currently_low_vol_correctly():
    # Reversed: high-vol-then-low-vol — empirically verified across seeds 0-4
    # to always classify the final day as low_vol.
    n = HMM_WINDOW_TRADING_DAYS + 1
    prices = pd.Series(_two_regime_price_series(n, seed=0, first_std=0.02, second_std=0.005))
    result = classify_regime_hmm(prices)
    assert result is not None
    assert result.label == "low_vol"
    assert result.confidence > 0.5


def test_classify_regime_hmm_returns_none_below_window_floor():
    n = HMM_WINDOW_TRADING_DAYS  # one short of the required window + 1
    prices = pd.Series(np.linspace(100, 110, n))
    assert classify_regime_hmm(prices) is None


def test_classify_regime_hmm_returns_none_for_zero_variance():
    # Constant price -> zero-variance log returns -> a degenerate fit that
    # must be skipped, not raise.
    n = HMM_WINDOW_TRADING_DAYS + 1
    prices = pd.Series(np.full(n, 100.0))
    assert classify_regime_hmm(prices) is None


def test_classify_regime_hmm_handles_fit_failure_gracefully():
    # A pathological, near-degenerate but non-constant series should never
    # raise out of classify_regime_hmm — it must return None on any
    # fit/convergence failure instead of propagating a statsmodels exception.
    n = HMM_WINDOW_TRADING_DAYS + 1
    rng = np.random.default_rng(0)
    tiny_noise = rng.normal(0, 1e-12, n)
    prices = pd.Series(100.0 + np.cumsum(tiny_noise))
    result = classify_regime_hmm(prices)
    assert result is None or result.label in ("high_vol", "low_vol")
