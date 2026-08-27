import numpy as np
import pandas as pd

# Corwin & Schultz (2012), "A Simple Way to Estimate Bid-Ask Spreads from
# Daily High and Low Prices," Journal of Finance 67(2), 719-760. A
# closed-form estimator of the effective bid-ask spread from OHLC alone --
# no tick/quote data needed. Rests on the observation that a day's High is
# (almost always) a buy-initiated trade and Low a sell-initiated trade, so
# the daily high-low range embeds both return variance and the spread;
# since variance scales with the length of the return interval but the
# spread component doesn't, comparing a single day's range to a two-day
# range identifies the two separately.
#
# THIS IS A MEMORY-RECONSTRUCTED IMPLEMENTATION of a public, well-known
# formula, not transcribed from the paper directly -- spot-check against
# the original paper or a reference implementation before relying on it
# for anything load-bearing. test_corwin_schultz_formula_lock pins the
# exact arithmetic so a future edit can be checked against a known-good
# computation, but that is a regression lock, not proof the formula
# matches the published derivation -- only
# test_synthetic_spread_recovery_is_monotonic_in_true_spread is real
# external validation, and it only checks rank order (exact-level recovery
# is documented in the literature to carry finite-sample bias, especially
# at low volatility).
#
# Built in response to this project's own repeated finding (Phase A/B
# intraday pattern mining, 420/420 patterns tried, zero with positive
# pooled Sharpe after cost): every backtest in this codebase currently
# assumes a FLAT cost in basis points, identical across every ticker and
# every day. This gives a per-ticker, per-day-varying cost proxy instead.
# NOT wired into any backtest yet -- replacing a flat cost assumption
# touches every family's realized Sharpe and is a decision to make
# explicitly, not fold in quietly alongside an unrelated change.

CS_CONST = 3 - 2 * np.sqrt(2)  # ~= 0.171573, from the paper's derivation
DEFAULT_WINDOW_DAYS = 21  # ~1 trading month, matching the paper's own monthly cadence


def _two_day_alpha(high: pd.Series, low: pd.Series) -> pd.Series:
    """One alpha per adjacent-day pair (t, t+1), indexed on day t. NaN
    wherever either day's H<=L (a non-positive or inverted range -- bad
    data, not a zero-spread day) so it drops out of a rolling mean via
    min_periods rather than silently contributing a wrong value."""
    if len(high) != len(low) or not high.index.equals(low.index):
        raise ValueError("high and low must share the same index")

    h = high.to_numpy(dtype=float)
    l = low.to_numpy(dtype=float)
    bad_day = (h <= 0) | (l <= 0) | (h <= l)  # h == l (zero range) excluded too, not just h < l

    with np.errstate(divide="ignore", invalid="ignore"):
        log_hl = np.log(h / l)
    log_hl = np.where(bad_day, np.nan, log_hl)

    beta = log_hl[:-1] ** 2 + log_hl[1:] ** 2

    h2 = np.maximum(h[:-1], h[1:])
    l2 = np.minimum(l[:-1], l[1:])
    with np.errstate(divide="ignore", invalid="ignore"):
        gamma = np.log(h2 / l2) ** 2

    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / CS_CONST - np.sqrt(gamma / CS_CONST)
    return pd.Series(alpha, index=high.index[:-1])


def estimate_corwin_schultz_spread(
    high: pd.Series, low: pd.Series, window_days: int = DEFAULT_WINDOW_DAYS
) -> pd.Series | None:
    """Rolling Corwin-Schultz effective-spread estimate, as a fraction of
    price (0.01 = 1%, i.e. ~100bps). `high`/`low` must share a DatetimeIndex
    with no gaps assumed -- a missing trading day just makes that pair span
    a longer real interval; the paper doesn't correct for this and neither
    does this implementation, acceptable at daily-bar granularity.

    Averages alpha (not the per-pair spread) over the window before
    converting to a spread and flooring at 0 -- flooring each two-day
    estimate individually before averaging is a known source of upward
    bias (negative-noise draws get truncated away while positive-noise
    draws survive), so this averages first and floors once.

    Returns None if there isn't enough history for even one full window."""
    if len(high) < window_days + 1:
        return None

    alpha = _two_day_alpha(high, low)
    alpha_avg = alpha.rolling(window_days, min_periods=window_days).mean()

    with np.errstate(over="ignore"):
        exp_alpha = np.exp(alpha_avg)
    spread = 2 * (exp_alpha - 1) / (1 + exp_alpha)
    return spread.clip(lower=0.0)
