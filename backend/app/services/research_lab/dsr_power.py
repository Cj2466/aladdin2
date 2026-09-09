"""Statistical power of the DSR gate: what size of TRUE edge the gate could
actually have detected, given a family's sample length and grid size.

WHY THIS MODULE EXISTS. Policy D (registration_scorecard.policy_d_verdict)
labels a family DEFINITE_NEGATIVE when its best DSR misses the declared bar
at the family's own N. That label reads as "the mechanism is not there", but
DSR < bar is also exactly what a REAL edge produces whenever the sample is too
short to resolve it: the criteria audit of 2026-09-09
(data/research_runs/criteria_audit_2026-09-09/CRITERIA_AUDIT_2026-09-09.md,
finding F1) measured that with ~11.6 years of daily data the 0.95 bar needs an
observed annualized Sharpe of roughly 0.65-1.2 for the equity families and
0.9-1.7 for the short-sample ones, so a true Sharpe-0.5 edge fails it most of
the time no matter how real it is. "Failed an underpowered test" and "shown to
be absent" are different findings, and this project's stated goal — many small,
honestly-verified micro-edges — is precisely the population an underpowered
test discards. A test that cannot see the effect it was built to look for has
not refuted it.

The remedy is standard experimental design, applied at PRE-REGISTRATION time:
state the effect size the source literature claims, compute the probability
this test would clear its own bar if that claim were exactly true (the power),
and if that probability is below POWER_FLOOR the test is declared underpowered
for the claim BEFORE any result exists. A failing result from an underpowered
test is then reported as UNDERPOWERED, not DEFINITE_NEGATIVE. This does NOT
lower the bar: nothing here changes what passes, and an UNDERPOWERED family
earns no forward slot by that label alone.

THE ARITHMETIC — nothing here is a new formula. The gate is
    DSR = PSR(SR_hat; SR0(N)) >= threshold,
which, because PSR is strictly increasing in SR_hat, is equivalent to
    SR_hat >= SR_req,
where SR_req is found by inverting deflated_sharpe.probabilistic_sharpe_ratio
numerically (bisection) against deflated_sharpe.expected_max_sharpe_under_noise.
Both functions are called as-is; no expression from either is retyped here.

Under an alternative "the true per-period Sharpe is s", the estimator SR_hat is
asymptotically normal with standard error
    sigma(s) = sqrt((1 - gamma3*s + ((gamma4 - 1)/4)*s^2) / (n - 1)),
which is, term for term, the variance expression
deflated_sharpe.probabilistic_sharpe_ratio already implements (Bailey & Lopez
de Prado, "The Sharpe Ratio Efficient Frontier", the source deflated_sharpe.py
cites; its normal-case reduction to Mertens (2002) / Lo (2002) is verified
numerically in that module's own header block). No equation number is quoted
here because none was re-checked against the paper for this module — the
expression is taken from the already-verified code, not from memory. PSR
evaluates it at SR_hat; power evaluates it at the hypothesised s. So
    power(s) = P(SR_hat >= SR_req | s) = 1 - Phi((SR_req - s) / sigma(s)).

VALIDATED AGAINST SYNTHETIC DATA WITH A KNOWN ANSWER, not trusted on sight:
tests/test_dsr_power.py simulates i.i.d. normal returns with a chosen true
Sharpe, runs them through the project's own PSR/SR0 functions, and checks the
empirical pass rate against power_to_pass(); the full-length validation is
data/research_runs/criteria_fix_2026-09-09/validate_dsr_power.py and its
committed output.

UNITS. Every public function here takes ANNUALIZED Sharpe values (true Sharpe,
sigma_sr, returned SR_req and min-detectable) plus periods_per_year, and
converts to per-period scale internally before touching PSR/SR0 — the same
contract as deflated_sharpe.compute_deflated_sharpe, and for the same reason
that module's docstring spells out (an annualized Sharpe fed to a per-period n
silently mis-states confidence). n_observations is the count of PER-PERIOD
returns the gate itself is computed on, so power mirrors the gate exactly.

SKEW/KURTOSIS. The default (skewness=0, kurtosis=3) is the normal case. A
caller with a family's measured moments may pass them; note that at
pre-registration time no realized moments exist yet, and the audit's F1
adversarial pass found the normal-case power to be, if anything, optimistic
for fat-tailed families (heavier tails widen sigma(s) and lower power), so a
pre-registration power computed at normal moments is an UPPER bound.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

from app.services.research_lab.deflated_sharpe import (
    MIN_TRIALS_FOR_DSR,
    expected_max_sharpe_under_noise,
    probabilistic_sharpe_ratio,
)
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR

# The 0.80 power convention attributed to Cohen (1988), "Statistical Power
# Analysis for the Behavioral Sciences" (2nd ed.): a test with less than an
# 80% chance of detecting the effect it was designed for is underpowered. A
# convention, not a derivation, and stated as such; the same number clinical
# trial design uses. The book was not re-opened for this module.
POWER_FLOOR = 0.80

# Bisection bounds for the annualized Sharpe search. 10 is far above any
# Sharpe this project has ever persisted (no family's best net Sharpe reaches
# 1.0 — criteria_audit_2026-09-09/family_power.csv); a required Sharpe above
# it means "not reachable" and is reported as None, never clipped.
_SHARPE_SEARCH_HI = 10.0
_BISECTION_ITERATIONS = 80

# Bisection bound for years-to-detect. A mechanism that needs more than this
# many years of daily data is, for this project's purposes, undetectable;
# returned as None so the caller cannot mistake a clipped bound for a number.
_MAX_YEARS_SEARCH = 500.0


class DsrPowerError(ValueError):
    """Inputs that cannot yield a power number. Raised, never papered over,
    because a silently-defaulted power would be exactly the false precision
    this module exists to remove."""


@dataclass(frozen=True)
class DsrPowerReport:
    """Everything a scorecard needs to say about the gate's sensitivity.

    All Sharpe fields are ANNUALIZED. `required_observed_sharpe` is what the
    best spec's realized Sharpe had to reach to clear `threshold` at
    `n_trials`; `power_at_claimed_sharpe` is the probability it would have,
    were the source's claim exactly true; `min_detectable_sharpe` is the
    smallest true Sharpe this test detects with probability POWER_FLOOR;
    `years_to_detect_claimed` is how many years of data at this
    periods_per_year the same grid would need to reach POWER_FLOOR at the
    claimed Sharpe (None when beyond _MAX_YEARS_SEARCH)."""

    threshold: float
    n_observations: int
    n_trials: int
    sigma_sr_annualized: float
    periods_per_year: float
    claimed_sharpe_annualized: float
    required_observed_sharpe: float
    power_at_claimed_sharpe: float
    min_detectable_sharpe: float | None
    years_to_detect_claimed: float | None
    underpowered: bool

    def summary(self) -> str:
        mds = "n/a" if self.min_detectable_sharpe is None else f"{self.min_detectable_sharpe:.2f}"
        yrs = "n/a" if self.years_to_detect_claimed is None else f"{self.years_to_detect_claimed:.0f}"
        return (
            f"bar {self.threshold:.2f} at N={self.n_trials}, n={self.n_observations} obs: needs observed "
            f"Sharpe >= {self.required_observed_sharpe:.2f}; power at claimed {self.claimed_sharpe_annualized:.2f} "
            f"= {self.power_at_claimed_sharpe:.2f} ({'UNDERPOWERED' if self.underpowered else 'adequately powered'} "
            f"vs floor {POWER_FLOOR:.2f}); min detectable Sharpe at {POWER_FLOOR:.0%} power = {mds}; "
            f"years of data to detect the claim = {yrs}"
        )


def _validate_common(
    *, n_observations: int, n_trials: int, sigma_sr_annualized: float, periods_per_year: float, threshold: float
) -> None:
    if not 0.0 < threshold < 1.0:
        raise DsrPowerError(f"threshold must be a probability strictly between 0 and 1, got {threshold}")
    if n_observations < 3:
        raise DsrPowerError(f"n_observations={n_observations}: the Sharpe standard error needs n-1 >= 2")
    if n_trials < MIN_TRIALS_FOR_DSR:
        raise DsrPowerError(
            f"n_trials={n_trials} is below deflated_sharpe.MIN_TRIALS_FOR_DSR={MIN_TRIALS_FOR_DSR}; the gate "
            "itself reports no DSR there, so there is no gate to compute the power of"
        )
    if not (np.isfinite(sigma_sr_annualized) and sigma_sr_annualized >= 0):
        raise DsrPowerError(f"sigma_sr_annualized must be a finite non-negative number, got {sigma_sr_annualized}")
    if not (np.isfinite(periods_per_year) and periods_per_year > 0):
        raise DsrPowerError(f"periods_per_year must be positive, got {periods_per_year}")


def _sharpe_standard_error(true_sharpe_per_period: float, n_observations: int, skewness: float, kurtosis: float) -> float:
    s = true_sharpe_per_period
    variance_numerator = 1 - skewness * s + ((kurtosis - 1) / 4) * s**2
    if variance_numerator <= 0 or not np.isfinite(variance_numerator):
        raise DsrPowerError(
            f"Sharpe variance term is non-positive at s={s:.4f}, skew={skewness}, kurt={kurtosis} "
            "(the same guard deflated_sharpe.probabilistic_sharpe_ratio applies)"
        )
    return float(np.sqrt(variance_numerator / (n_observations - 1)))


def required_observed_sharpe(
    *,
    threshold: float,
    n_observations: int,
    n_trials: int,
    sigma_sr_annualized: float,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float | None:
    """The smallest ANNUALIZED observed Sharpe at which the project's own DSR
    machinery reports DSR >= threshold at n_trials. Found by bisection on
    probabilistic_sharpe_ratio against expected_max_sharpe_under_noise —
    neither function's arithmetic is reproduced here. None if even
    _SHARPE_SEARCH_HI cannot clear the bar."""
    _validate_common(
        n_observations=n_observations,
        n_trials=n_trials,
        sigma_sr_annualized=sigma_sr_annualized,
        periods_per_year=periods_per_year,
        threshold=threshold,
    )
    scale = np.sqrt(periods_per_year)
    sr0_per_period = expected_max_sharpe_under_noise(sigma_sr_annualized / scale, n_trials)
    if sr0_per_period is None:
        raise DsrPowerError(f"expected_max_sharpe_under_noise returned None at n_trials={n_trials}")

    def clears(sr_annualized: float) -> bool:
        psr = probabilistic_sharpe_ratio(sr_annualized / scale, sr0_per_period, n_observations, skewness, kurtosis)
        return psr is not None and psr >= threshold

    if not clears(_SHARPE_SEARCH_HI):
        return None
    lo, hi = -_SHARPE_SEARCH_HI, _SHARPE_SEARCH_HI
    for _ in range(_BISECTION_ITERATIONS):
        mid = (lo + hi) / 2
        if clears(mid):
            hi = mid
        else:
            lo = mid
    return float(hi)


def power_to_pass(
    *,
    true_sharpe_annualized: float,
    threshold: float,
    n_observations: int,
    n_trials: int,
    sigma_sr_annualized: float,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """P(DSR >= threshold | the true annualized Sharpe is exactly
    true_sharpe_annualized), from the asymptotic normality of SR_hat with
    the standard error evaluated at the hypothesised Sharpe (module
    docstring). 0.0 when the bar is unreachable at any observed Sharpe."""
    required = required_observed_sharpe(
        threshold=threshold,
        n_observations=n_observations,
        n_trials=n_trials,
        sigma_sr_annualized=sigma_sr_annualized,
        periods_per_year=periods_per_year,
        skewness=skewness,
        kurtosis=kurtosis,
    )
    if required is None:
        return 0.0
    scale = np.sqrt(periods_per_year)
    s = true_sharpe_annualized / scale
    se = _sharpe_standard_error(s, n_observations, skewness, kurtosis)
    return float(1.0 - norm.cdf((required / scale - s) / se))


def min_detectable_sharpe(
    *,
    threshold: float,
    n_observations: int,
    n_trials: int,
    sigma_sr_annualized: float,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
    power_target: float = POWER_FLOOR,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float | None:
    """The smallest true ANNUALIZED Sharpe this gate detects with probability
    >= power_target. Bisection on power_to_pass, which is monotone increasing
    in the true Sharpe. None if no Sharpe up to _SHARPE_SEARCH_HI reaches
    the target."""
    if not 0.0 < power_target < 1.0:
        raise DsrPowerError(f"power_target must be strictly between 0 and 1, got {power_target}")

    def power(s: float) -> float:
        return power_to_pass(
            true_sharpe_annualized=s,
            threshold=threshold,
            n_observations=n_observations,
            n_trials=n_trials,
            sigma_sr_annualized=sigma_sr_annualized,
            periods_per_year=periods_per_year,
            skewness=skewness,
            kurtosis=kurtosis,
        )

    if power(_SHARPE_SEARCH_HI) < power_target:
        return None
    lo, hi = 0.0, _SHARPE_SEARCH_HI
    for _ in range(_BISECTION_ITERATIONS):
        mid = (lo + hi) / 2
        if power(mid) >= power_target:
            hi = mid
        else:
            lo = mid
    return float(hi)


def years_to_detect(
    *,
    true_sharpe_annualized: float,
    threshold: float,
    n_trials: int,
    sigma_sr_annualized: float,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
    power_target: float = POWER_FLOOR,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float | None:
    """Years of per-period data at which power_to_pass reaches power_target
    for the given true Sharpe, holding the grid (n_trials, sigma_sr) fixed.
    Bisection on the observation count, which power is monotone increasing
    in. None beyond _MAX_YEARS_SEARCH, and None for a non-positive true
    Sharpe (no amount of data detects an edge that is not there)."""
    if true_sharpe_annualized <= 0:
        return None
    if not 0.0 < power_target < 1.0:
        raise DsrPowerError(f"power_target must be strictly between 0 and 1, got {power_target}")

    def power_at_years(years: float) -> float:
        n_obs = max(3, round(years * periods_per_year))
        return power_to_pass(
            true_sharpe_annualized=true_sharpe_annualized,
            threshold=threshold,
            n_observations=n_obs,
            n_trials=n_trials,
            sigma_sr_annualized=sigma_sr_annualized,
            periods_per_year=periods_per_year,
            skewness=skewness,
            kurtosis=kurtosis,
        )

    if power_at_years(_MAX_YEARS_SEARCH) < power_target:
        return None
    lo, hi = 0.0, _MAX_YEARS_SEARCH
    for _ in range(_BISECTION_ITERATIONS):
        mid = (lo + hi) / 2
        if power_at_years(mid) >= power_target:
            hi = mid
        else:
            lo = mid
    return float(hi)


def dsr_power_report(
    *,
    claimed_sharpe_annualized: float,
    threshold: float,
    n_observations: int,
    n_trials: int,
    sigma_sr_annualized: float,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> DsrPowerReport:
    """The scorecard-facing bundle. `claimed_sharpe_annualized` is the effect
    size the pre-registration took from the source literature (net of this
    project's cost model where the paper reports gross); it must be written
    down BEFORE the family is run, or the power number is post hoc."""
    if not np.isfinite(claimed_sharpe_annualized):
        raise DsrPowerError(f"claimed_sharpe_annualized must be finite, got {claimed_sharpe_annualized}")
    common = {
        "threshold": threshold,
        "n_observations": n_observations,
        "n_trials": n_trials,
        "sigma_sr_annualized": sigma_sr_annualized,
        "periods_per_year": periods_per_year,
        "skewness": skewness,
        "kurtosis": kurtosis,
    }
    required = required_observed_sharpe(**common)
    if required is None:
        raise DsrPowerError(
            f"the {threshold:.2f} bar is unreachable at N={n_trials}, n={n_observations}, "
            f"sigma_sr={sigma_sr_annualized:.3f}: no observed Sharpe up to {_SHARPE_SEARCH_HI} clears it"
        )
    power = power_to_pass(true_sharpe_annualized=claimed_sharpe_annualized, **common)
    return DsrPowerReport(
        threshold=threshold,
        n_observations=n_observations,
        n_trials=n_trials,
        sigma_sr_annualized=sigma_sr_annualized,
        periods_per_year=periods_per_year,
        claimed_sharpe_annualized=claimed_sharpe_annualized,
        required_observed_sharpe=required,
        power_at_claimed_sharpe=power,
        min_detectable_sharpe=min_detectable_sharpe(**common),
        years_to_detect_claimed=years_to_detect(
            true_sharpe_annualized=claimed_sharpe_annualized,
            threshold=threshold,
            n_trials=n_trials,
            sigma_sr_annualized=sigma_sr_annualized,
            periods_per_year=periods_per_year,
            skewness=skewness,
            kurtosis=kurtosis,
        ),
        underpowered=power < POWER_FLOOR,
    )
