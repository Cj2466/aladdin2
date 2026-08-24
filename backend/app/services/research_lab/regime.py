from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from scipy.stats import norm

# Lo-MacKinlay (1988) homoskedastic variance ratio test. Empirically checked
# 2026-08-24 against the real 108-ticker SCREENING_UNIVERSE (live yf.download)
# across windows 60/90/120/180/252 trading days and q in {2,5,10}: at p<=0.05
# the test passes only 2.8%-5.6% of the real universe — close to the ~5% a
# true random-walk null predicts, i.e. well-calibrated, NOT spuriously
# permissive like the other two screening gates (AR(1) pairs pre-filter:
# 99.3% spurious pass; momentum's own significance gate: 84.3% pass vs ~5%
# expected). That's the opposite failure mode: a hard filter or rank boost
# keyed to this bar would reject/ignore ~95% of an already-capped shortlist
# most runs. See screening.py's use of this module — shipped as a pure
# informational tag, never a filter or rank input.
#
# Mechanistic-distinctness check: feeding momentum's own trending fixture
# (_trend_price_series(91, drift=0.003, noise_std=0.0005, seed=42), which
# reliably trips momentum's OLS-on-price significance gate) through this
# test gives vr=0.860, z=-0.607, p=0.544 -> "indeterminate". VR is
# drift-invariant by construction (it demeans returns first) and responds
# only to serial correlation in returns, not to a price-level trend — a
# genuinely different statistical object from either existing screening gate.
VR_WINDOW_DAYS = 90  # a "current state" classifier wants a shorter, more responsive window than
# pairs' 252-day equilibrium fit; also requires zero change to screening_runner.py's existing
# MOMENTUM_SCREENING_LOOKBACK_CALENDAR_DAYS=180 fetch (confirmed: 108/108 tickers already resolve
# with 124 rows each over that window, comfortably above this test's 91-row floor).
VR_AGGREGATION_Q = 5  # ~1 trading week; q in {2,5,10} checked, no material change to the finding.


@dataclass
class RegimeClassification:
    regime: Literal["trending", "mean_reverting", "indeterminate"]
    vr_z_score: float
    vr_p_value: float


def compute_variance_ratio(log_returns: np.ndarray, q: int) -> tuple[float, float, float] | None:
    """Lo-MacKinlay (1988) VR(q) statistic on de-meaned log returns, using
    the paper's original homoskedastic asymptotic variance — matches this
    codebase's existing preference for plain closed-form fits (fit_ou_pairs_
    window, fit_momentum_window) over a heteroskedasticity-robust GMM
    variant. Returns None for T<=q or zero-variance (dead/halted ticker)."""
    t = len(log_returns)
    if t <= q:
        return None

    mu = log_returns.mean()
    sigma_a2 = np.sum((log_returns - mu) ** 2) / (t - 1)
    if sigma_a2 == 0:
        return None

    cum = np.concatenate([[0.0], np.cumsum(log_returns - mu)])
    m = t - q + 1
    sigma_c2 = np.sum((cum[q:] - cum[:-q]) ** 2) / (q * m * (1 - q / t))
    vr = sigma_c2 / sigma_a2

    phi_q = 2 * (2 * q - 1) * (q - 1) / (3 * q * t)
    z = (vr - 1) / np.sqrt(phi_q)
    p_value = 2 * (1 - norm.cdf(abs(z)))

    return float(vr), float(z), float(p_value)


def classify_regime(prices: pd.Series) -> RegimeClassification | None:
    """Takes one ticker's own already-dropna()'d price series (the same
    object screen_momentum_universe already holds as `series`). Returns
    None below VR_WINDOW_DAYS+1 rows (silent skip, same convention as
    momentum's own insufficient-history skip — a ticker can clear
    momentum's 90-row floor and still be 1 row short of this floor; that's
    fine, it just means no tag this run)."""
    window = prices.iloc[-(VR_WINDOW_DAYS + 1) :]
    if len(window) < VR_WINDOW_DAYS + 1:
        return None

    log_returns = np.diff(np.log(window.to_numpy()))
    result = compute_variance_ratio(log_returns, VR_AGGREGATION_Q)
    if result is None:
        return None
    vr, z, p_value = result

    regime: Literal["trending", "mean_reverting", "indeterminate"]
    if p_value <= 0.05 and vr > 1:
        regime = "trending"
    elif p_value <= 0.05 and vr < 1:
        regime = "mean_reverting"
    else:
        regime = "indeterminate"

    return RegimeClassification(regime=regime, vr_z_score=z, vr_p_value=p_value)
