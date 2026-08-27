from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import kurtosis as _kurtosis
from scipy.stats import norm
from scipy.stats import skew as _skew

from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR

# Bailey & Lopez de Prado, "The Sharpe Ratio Efficient Frontier" (2014).
# Every numeric claim below was independently verified this session via
# direct execution against this project's own venv, not taken on faith:
#
# - Normal-case reduction (skew=0, kurt=3) matches the classic Mertens
#   (2002) asymptotic form exactly: sr_hat=0.3, n=500 -> both give
#   0.9999999999722933.
# - The annualized-vs-daily unit-mixing bug is real, not theoretical:
#   feeding metrics.sharpe_ratio()'s ANNUALIZED output into this formula
#   with a daily observation count silently inflates confidence in
#   whichever direction the point estimate points (verified on identical
#   60-day synthetic data: correct daily-scale input gave an honest
#   PSR(0)~=0.53, the same data fed in annualized-scale gave a falsely
#   confident PSR(0)~=0.90). Both SR_hat AND sigma_SR must be de-annualized
#   (divided by sqrt(252)) before use here — sigma_SR is easy to miss since
#   SR0 is merely linear in it, but skipping that de-annualization
#   reintroduces the same bug by a different path.
# - SR0 (expected max Sharpe under N pure-noise trials) is degenerate at
#   N=1 (Phi^-1(0) = -infinity) and strictly increasing in N; verified at
#   sigma_sr=0.3: N=2->0.156, N=5->0.358, N=10->0.472, N=100->0.759,
#   N=1000->0.977.
# - The PSR variance term (1 - skew*sr + ((kurt-1)/4)*sr^2) can go
#   non-positive for real, not just pathological, input combinations
#   (verified: skew=3, kurt=1.5, sr=1 -> -1.875) and must be guarded
#   explicitly rather than fed into sqrt()/norm.cdf().

MIN_OBSERVATIONS_FOR_PSR = 2  # sqrt(n-1) undefined below this

# Below this many sibling trials, the sigma_SR estimate is too unstable to
# trust as a multiple-comparisons benchmark. Verified via repeated-sampling
# simulation: the coefficient of variation of the sigma_SR estimate itself
# is ~77%/54%/42%/38%/24%/16% at N=2/3/4/5/10/20 pure-noise trials — no
# sharp cutoff exists, but N=5 is roughly where the estimate stops being
# dominated by which 2-3 trials happened to land in the sample.
MIN_TRIALS_FOR_DSR = 5


@dataclass
class ReturnSeriesStats:
    n: int
    skewness: float
    kurtosis: float  # non-excess (Pearson) convention — normal distribution ~= 3


@dataclass
class DeflatedSharpeResult:
    sharpe_net_annualized: float
    sharpe_net_daily: float
    n_observations: int
    skewness: float
    kurtosis: float
    psr_vs_zero: float | None
    n_trials: int
    sigma_sr_annualized: float | None
    expected_max_sharpe_noise_annualized: float | None
    dsr: float | None
    dsr_floor_met: bool
    interpretation: str


def derive_returns_from_equity_curve(equity_values: Sequence[float]) -> pd.Series:
    """The walk-forward engine's own equity curve starts AFTER day one's
    return is applied (WalkForwardState.equity defaults to 1.0, and
    step_one_day computes new_equity = state.equity * (1 + net_return) —
    the pre-day-1 base of 1.0 is never itself stored as a day result).
    Naively diffing the stored curve alone silently drops observation 1
    and undercounts n by exactly one. Verified against a real 5-day
    replay: equity_curve=[0.99, 1.0098, 1.0098, 0.969408, 0.969408]
    against the authoritative net_return=[-0.01, 0.02, 0.0, -0.04, 0.0] —
    only prepending 1.0 before diffing reproduces it exactly."""
    series = pd.Series([1.0, *equity_values])
    return series.pct_change().dropna()


def compute_return_stats(returns: pd.Series) -> ReturnSeriesStats | None:
    if len(returns) < MIN_OBSERVATIONS_FOR_PSR:
        return None
    std = returns.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return None
    return ReturnSeriesStats(
        n=len(returns),
        skewness=float(_skew(returns, bias=True)),
        kurtosis=float(_kurtosis(returns, fisher=False, bias=True)),
    )


def probabilistic_sharpe_ratio(
    sr_hat: float, sr_benchmark: float, n_observations: int, skewness: float, kurtosis: float
) -> float | None:
    """Both sr_hat and sr_benchmark must be PER-PERIOD-scale (matching
    n_observations, a count of per-period returns) — see module docstring
    for why mixing an annualized Sharpe with a per-period n silently
    produces a falsely over/under-confident result.

    DELIBERATELY takes no periods_per_year: this function performs no
    annualization or de-annualization at all, so it is unit-agnostic and a
    periods_per_year argument here would be a no-op that invites callers to
    believe a conversion happened. The whole annualization contract lives in
    compute_deflated_sharpe, which is the only function in this module that
    crosses between annualized and per-period scale."""
    if n_observations < MIN_OBSERVATIONS_FOR_PSR:
        return None

    denom_sq = 1 - skewness * sr_hat + ((kurtosis - 1) / 4) * sr_hat**2
    if denom_sq <= 0 or not np.isfinite(denom_sq):
        return None

    z = (sr_hat - sr_benchmark) * np.sqrt(n_observations - 1) / np.sqrt(denom_sq)
    if not np.isfinite(z):
        return None
    return float(norm.cdf(z))


def expected_max_sharpe_under_noise(sigma_sr: float, n_trials: int) -> float | None:
    """SR0: the expected maximum Sharpe ratio you'd observe from the best
    of n_trials equally-skilled, zero-true-edge trials. Unit-agnostic —
    the caller must pass a PER-PERIOD-scale sigma_sr (see module docstring)
    and is responsible for annualizing the result back for display if
    needed. Takes no periods_per_year for exactly the reason
    probabilistic_sharpe_ratio does not: nothing here converts scales, and a
    parameter that does nothing is worse than no parameter.
    None below 2 trials (norm.ppf(1 - 1/1) = norm.ppf(0) = -inf, a real
    degeneracy, not an edge case to paper over) or for a negative/
    non-finite sigma_sr."""
    if n_trials < 2 or sigma_sr < 0 or not np.isfinite(sigma_sr):
        return None
    gamma = np.euler_gamma
    value = sigma_sr * (
        (1 - gamma) * norm.ppf(1 - 1 / n_trials) + gamma * norm.ppf(1 - 1 / (n_trials * np.e))
    )
    return float(value) if np.isfinite(value) else None


def _build_interpretation(
    n_trials: int,
    n_observations: int,
    psr_vs_zero: float | None,
    dsr: float | None,
    dsr_floor_met: bool,
    expected_max_sharpe_noise_annualized: float | None,
) -> str:
    if psr_vs_zero is None:
        return "Not enough out-of-sample return observations to compute PSR/DSR."
    if not dsr_floor_met or dsr is None or expected_max_sharpe_noise_annualized is None:
        return (
            f"Only {n_trials} similar trial(s) found (need >=5) — not enough to estimate the "
            f"multiple-comparisons benchmark. Showing PSR-vs-zero only: {psr_vs_zero:.0%} "
            "estimated probability this strategy's true Sharpe exceeds zero."
        )
    return (
        f"This is 1 of N={n_trials} similar configurations run against this ticker/strategy. "
        f"Adjusting for that search — and for this run's own sample size ({n_observations} days), "
        f"skew, and kurtosis — there is an estimated {dsr:.0%} probability that this strategy's "
        f"true long-run Sharpe ratio exceeds {expected_max_sharpe_noise_annualized:.2f}, the Sharpe "
        f"you'd expect from the best of {n_trials} equally-skilled, zero-edge trials by chance "
        f"alone. (Before accounting for the number of trials searched, PSR-vs-zero was "
        f"{psr_vs_zero:.0%}.) This is not a p-value or a guarantee — it is the model's best point "
        "estimate of the strategy's true statistical edge, not a certainty."
    )


def compute_deflated_sharpe(
    sharpe_net_annualized: float,
    returns: pd.Series,
    n_trials: int,
    sigma_sr_annualized: float | None,
    *,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
) -> DeflatedSharpeResult:
    """THE one place in this module that crosses between annualized and
    per-period scale, in all three directions: de-annualizing the point
    estimate, de-annualizing sigma_SR, and re-annualizing SR0 for display.

    periods_per_year must be the number of return observations a year of
    `returns` contains, and must match whatever was used to ANNUALIZE
    sharpe_net_annualized and sigma_sr_annualized in the first place
    (metrics.sharpe_ratio's own periods_per_year). Getting it wrong here
    compounds the same error twice, because sr_hat and sigma_SR are both
    divided by it: a crypto family whose Sharpe was correctly annualized at
    365 but de-annualized here at 252 would end up comparing a 365-scaled
    point estimate against a 252-scaled noise benchmark.

    Keyword-only and defaulted to TRADING_DAYS_PER_YEAR so every existing
    caller (equity, bond, FX, commodity) is byte-for-byte unaffected."""
    sr_hat_daily = sharpe_net_annualized / np.sqrt(periods_per_year)
    dsr_floor_met = n_trials >= MIN_TRIALS_FOR_DSR

    stats = compute_return_stats(returns)
    if stats is None:
        return DeflatedSharpeResult(
            sharpe_net_annualized=sharpe_net_annualized,
            sharpe_net_daily=sr_hat_daily,
            n_observations=len(returns),
            skewness=0.0,
            kurtosis=0.0,
            psr_vs_zero=None,
            n_trials=n_trials,
            sigma_sr_annualized=sigma_sr_annualized,
            expected_max_sharpe_noise_annualized=None,
            dsr=None,
            dsr_floor_met=dsr_floor_met,
            interpretation=_build_interpretation(n_trials, len(returns), None, None, dsr_floor_met, None),
        )

    psr_vs_zero = probabilistic_sharpe_ratio(sr_hat_daily, 0.0, stats.n, stats.skewness, stats.kurtosis)

    sr0_annualized: float | None = None
    dsr: float | None = None
    if dsr_floor_met and sigma_sr_annualized is not None:
        sigma_sr_daily = sigma_sr_annualized / np.sqrt(periods_per_year)
        sr0_daily = expected_max_sharpe_under_noise(sigma_sr_daily, n_trials)
        if sr0_daily is not None:
            sr0_annualized = sr0_daily * np.sqrt(periods_per_year)
            dsr = probabilistic_sharpe_ratio(sr_hat_daily, sr0_daily, stats.n, stats.skewness, stats.kurtosis)

    return DeflatedSharpeResult(
        sharpe_net_annualized=sharpe_net_annualized,
        sharpe_net_daily=sr_hat_daily,
        n_observations=stats.n,
        skewness=stats.skewness,
        kurtosis=stats.kurtosis,
        psr_vs_zero=psr_vs_zero,
        n_trials=n_trials,
        sigma_sr_annualized=sigma_sr_annualized,
        expected_max_sharpe_noise_annualized=sr0_annualized,
        dsr=dsr,
        dsr_floor_met=dsr_floor_met,
        interpretation=_build_interpretation(n_trials, stats.n, psr_vs_zero, dsr, dsr_floor_met, sr0_annualized),
    )
