import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.spread_estimator import (
    CS_CONST,
    _two_day_alpha,
    estimate_corwin_schultz_spread,
)


def _dates(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq="B")


def test_corwin_schultz_formula_lock():
    """Independently computed (not by calling the tested code) via the raw
    formula for H=[101,102], L=[99,98]: alpha ~= 0.0113977305, spread ~=
    0.0113976071. Locks in the exact arithmetic -- a future edit that
    silently swaps beta/gamma, flips a sign, or changes CS_CONST breaks
    this test even though it wouldn't break a synthetic-recovery test that
    only checks rank order."""
    high = pd.Series([101.0, 102.0], index=_dates(2))
    low = pd.Series([99.0, 98.0], index=_dates(2))

    alpha = _two_day_alpha(high, low)
    assert len(alpha) == 1
    assert alpha.iloc[0] == pytest.approx(0.011397730506157444, abs=1e-10)

    spread = estimate_corwin_schultz_spread(high, low, window_days=1)
    assert spread.iloc[0] == pytest.approx(0.011397607119481453, abs=1e-10)


def test_cs_const_matches_paper_derivation():
    assert CS_CONST == pytest.approx(3 - 2 * np.sqrt(2))
    assert CS_CONST == pytest.approx(0.17157287525, abs=1e-9)


def test_insufficient_data_returns_none():
    high = pd.Series([101.0] * 5, index=_dates(5))
    low = pd.Series([99.0] * 5, index=_dates(5))
    assert estimate_corwin_schultz_spread(high, low, window_days=21) is None


def test_zero_range_day_excluded_not_zeroed():
    """A halted/thinly-traded day (H==L) must drop out of the rolling mean
    via min_periods, not silently contribute alpha=0 (which would read as
    "zero spread that day" -- a data artifact, not a real observation)."""
    n = 10
    high = pd.Series([101.0] * n, index=_dates(n))
    low = pd.Series([99.0] * n, index=_dates(n))
    high.iloc[3] = 100.0
    low.iloc[3] = 100.0  # H == L on day 3 -> that day's pairs are NaN

    alpha = _two_day_alpha(high, low)
    assert np.isnan(alpha.iloc[2])  # pair (day2, day3)
    assert np.isnan(alpha.iloc[3])  # pair (day3, day4)
    assert not np.isnan(alpha.iloc[0])  # unaffected pairs stay real numbers


def test_mismatched_index_raises():
    high = pd.Series([101.0, 102.0], index=_dates(2))
    low = pd.Series([99.0, 98.0], index=_dates(2) + pd.Timedelta(days=1))
    with pytest.raises(ValueError):
        _two_day_alpha(high, low)


def _simulate_bid_ask_bounce_ohlc(
    n_days: int, true_spread_frac: float, ticks_per_day: int, seed: int
) -> tuple[pd.Series, pd.Series]:
    """Synthetic OHLC with a KNOWN, injected effective spread: an
    intraday-random-walk "true value" plus a bid-ask bounce of exactly
    true_spread_frac around it. High/Low are the max/min of the simulated
    transaction prices each day. This is the honest way to validate a
    memory-reconstructed formula without access to the original paper's
    numbers: build a case where the right answer is known by construction."""
    rng = np.random.default_rng(seed)
    highs = np.empty(n_days)
    lows = np.empty(n_days)
    value = 100.0
    for day in range(n_days):
        intraday_moves = rng.normal(0, 0.0015, ticks_per_day)
        path = value * np.exp(np.cumsum(intraday_moves))
        side = rng.choice([-1.0, 1.0], ticks_per_day)
        observed = path * (1 + side * true_spread_frac / 2)
        highs[day] = observed.max()
        lows[day] = observed.min()
        value = path[-1]
    idx = _dates(n_days)
    return pd.Series(highs, index=idx), pd.Series(lows, index=idx)


def test_synthetic_spread_recovery_is_monotonic_in_true_spread():
    """External validation, not a self-consistency check: simulate two
    series that are identical except for the injected true spread (0.3%
    vs 3.0%), and require the estimator to rank them correctly on average.
    Exact-level recovery is documented in the literature to carry
    finite-sample bias (especially at low volatility), so this checks rank
    order across several seeds rather than a point estimate."""
    tight_means = []
    wide_means = []
    for seed in range(8):
        h_tight, l_tight = _simulate_bid_ask_bounce_ohlc(120, 0.003, 50, seed)
        h_wide, l_wide = _simulate_bid_ask_bounce_ohlc(120, 0.03, 50, seed + 1000)

        s_tight = estimate_corwin_schultz_spread(h_tight, l_tight, window_days=21)
        s_wide = estimate_corwin_schultz_spread(h_wide, l_wide, window_days=21)

        tight_means.append(s_tight.dropna().mean())
        wide_means.append(s_wide.dropna().mean())

    tight_avg = float(np.mean(tight_means))
    wide_avg = float(np.mean(wide_means))
    assert wide_avg > tight_avg, (
        f"estimator failed to rank a 3.0% true spread above a 0.3% true "
        f"spread across 8 seeds: tight={tight_avg}, wide={wide_avg}"
    )


def test_negative_alpha_floors_spread_to_zero():
    """Pure-noise (effectively zero true spread) data routinely produces a
    negative raw alpha for individual day-pairs -- this is documented,
    expected behavior of the estimator, not a bug. Confirms the final
    spread series is never negative regardless of what the raw formula
    produces before flooring."""
    h, l = _simulate_bid_ask_bounce_ohlc(60, 0.0, 50, seed=7)
    spread = estimate_corwin_schultz_spread(h, l, window_days=21)
    assert (spread.dropna() >= 0.0).all()
