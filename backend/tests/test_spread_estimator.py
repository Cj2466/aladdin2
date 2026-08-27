import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.spread_estimator import (
    DEFAULT_WINDOW_DAYS,
    estimate_effective_spread,
)


def _dates(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq="B")


def _simulate_bid_ask_bounce_ohlc(
    n_days: int, true_spread_frac: float, ticks_per_day: int, seed: int
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Synthetic OHLC with a KNOWN, injected effective spread: an
    intraday-random-walk "true value" plus a bid-ask bounce of exactly
    true_spread_frac around it. This is the honest way to validate a
    third-party estimator's plumbing in this codebase: build a case where
    the right answer is known by construction, rather than trusting the
    package's own test suite alone."""
    rng = np.random.default_rng(seed)
    opens = np.empty(n_days)
    highs = np.empty(n_days)
    lows = np.empty(n_days)
    closes = np.empty(n_days)
    value = 100.0
    for day in range(n_days):
        intraday_moves = rng.normal(0, 0.0015, ticks_per_day)
        path = value * np.exp(np.cumsum(intraday_moves))
        side = rng.choice([-1.0, 1.0], ticks_per_day)
        observed = path * (1 + side * true_spread_frac / 2)
        opens[day] = observed[0]
        closes[day] = observed[-1]
        highs[day] = observed.max()
        lows[day] = observed.min()
        value = path[-1]
    idx = _dates(n_days)
    return (
        pd.Series(opens, index=idx),
        pd.Series(highs, index=idx),
        pd.Series(lows, index=idx),
        pd.Series(closes, index=idx),
    )


def test_insufficient_data_returns_none():
    idx = _dates(5)
    s = pd.Series([100.0] * 5, index=idx)
    assert estimate_effective_spread(s, s, s, s, window_days=21) is None


def test_mismatched_index_raises():
    idx = _dates(5)
    s = pd.Series([100.0] * 5, index=idx)
    s_shifted = pd.Series([100.0] * 5, index=idx + pd.Timedelta(days=1))
    with pytest.raises(ValueError):
        estimate_effective_spread(s, s, s, s_shifted, window_days=21)


def test_synthetic_spread_recovery_is_monotonic_across_regimes():
    """Real external validation, not self-consistency: averaged over 10
    seeds per level (single-seed estimates are noisy at window_days=21),
    recovered spread must increase monotonically with true spread. This
    is the check that would have caught the earlier Corwin-Schultz
    implementation's large downward bias at low spreads (it recovered a
    true 10bps as roughly -13bps -- not just biased, but non-monotonic
    against zero) before anything got wired into a backtest."""
    true_spreads_bps = [10, 50, 100, 300, 500]
    recovered = []
    for true_bps in true_spreads_bps:
        estimates = []
        for seed in range(10):
            o, h, l, c = _simulate_bid_ask_bounce_ohlc(
                300, true_bps / 10000, ticks_per_day=50, seed=seed
            )
            est = estimate_effective_spread(o, h, l, c, window_days=DEFAULT_WINDOW_DAYS)
            assert est is not None
            estimates.append(est.dropna().mean() * 10000)
        recovered.append(float(np.mean(estimates)))

    assert all(x > 0 for x in recovered), recovered
    assert recovered == sorted(recovered), (
        f"recovered spreads {recovered} are not monotonically increasing "
        f"with true spreads {true_spreads_bps}"
    )
    # At 50bps+ (the regime this module documents as trustworthy), demand
    # real accuracy, not just monotonicity.
    for true_bps, est_bps in zip(true_spreads_bps[1:], recovered[1:]):
        assert abs(est_bps - true_bps) / true_bps < 0.2, (
            f"true={true_bps}bps recovered {est_bps:.2f}bps, more than 20% "
            f"off in the regime this module claims is accurate"
        )


def test_returns_fraction_of_price_units():
    """A value of 0.01 must mean 1% (~100bps), per the package's own
    documented convention -- a unit-scale mixup here would silently
    corrupt every downstream cost calculation by 100x or 10000x."""
    o, h, l, c = _simulate_bid_ask_bounce_ohlc(80, 0.01, ticks_per_day=50, seed=1)
    est = estimate_effective_spread(o, h, l, c, window_days=21)
    assert est is not None
    mean_est = est.dropna().mean()
    assert 0.001 < mean_est < 0.05  # a 1% true spread should not read as ~1.0 or ~0.0001
