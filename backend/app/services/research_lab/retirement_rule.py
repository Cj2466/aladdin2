"""THE FORWARD-RETIREMENT RULE (R-2026-09-09) — a sequential probability
ratio test on a registration's realized net daily returns, with a boundary
calibrated by simulation so that a genuinely good registration is almost
never recommended for retirement.

WHAT IT IS. For standardized daily net returns z_t = r_t / sigma_hat_t
(expanding-sample sd, ddof=1) the per-day log-likelihood ratio of "harm"
(true annualized Sharpe S1 = -1.0) against "protect" (S0 = +0.5) for a
Gaussian with common variance is

    l_t = d * (z_t - m),   d = (S1 - S0)/sqrt(252),   m = (S1 + S0)/(2*sqrt(252)),

the elementary identity log[phi(z; mu1)/phi(z; mu0)] = (mu1 - mu0)(z - (mu1 + mu0)/2)
for unit variance. The statistic is Lambda_t = sum_{i<=t} l_i, monitored
daily from MIN_DAYS on, and the rule RECOMMENDS retirement at the first day
Lambda_t >= B. B is NOT Wald's approximation: it is the simulated 0.95
quantile of max_t Lambda_t over a five-year horizon under the protect truth,
taken as the worst case over i.i.d. normal, Student-t(4) and AR(1) phi=0.10
daily returns (the LOW autocorrelation bucket, as in dormant_pool).

WHAT IT MEASURED (data/research_runs/retirement_rule_2026-09-09, run 2):
  R1  P(recommend within 5y | true 0.5) = 0.031 normal / 0.026 t4 / 0.051 AR(1) 0.1
  R2  P(recommend within 5y | true -1.0) = 0.82, median 2.25y, median drawdown
      at trigger 3.4 annual-vol units
  R3  an edge that is 1.0 for two years then -1.0: caught within 5y only 14.5%
      of the time (the whole-record statistic carries the good history) —
      THIS RULE IS NEARLY BLIND TO DECAY; the CUSUM alternative caught 49%
      but missed R2 by 0.006 and was not adopted, per the pre-declared rule.
  HIGH bucket (phi_hat > 0.10): NO statistic reached 80% power at -1.0
  within 5y, so there is no calibrated rule for HIGH-bucket registrations;
  evaluate() says so instead of pretending.

WHY IT IS SLOW, and why no rule can be faster (pre-registration section 1):
the evidence per year between two Sharpe levels is (S1 - S0)^2 / 2 nats, so
protecting 0.5 while catching -1.0 at alpha = 0.05 costs about
2 ln(20) / 1.5^2 = 2.7 years on average. Capital protection has to come from
sizing, not from detection speed. The owner may instead protect 1.0
(ALTERNATIVE_S0_1_0 below, informational): faster kills, but a true 0.5 is
then recommended for retirement 12% of the time within 5y.

WHAT IT DOES NOT DO. It never changes a status (CLAUDE.md rule 6): it
returns a recommendation. Mechanism evidence closes a registration
regardless of it. It is not wired into any runner or dashboard field yet —
the owner must first choose the protect level, because the boundary depends
on it (see the results memo).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.services.research_lab.dormant_pool import BUCKET_HIGH, BUCKET_LOW, assign_bucket
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR

RULE_ID = "R-2026-09-09"
S0_PROTECT = 0.5
S1_HARM = -1.0
ALPHA = 0.05
HORIZON_YEARS = 5
MIN_DAYS = 60  # forward_validation_service.UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS, unchanged
# Simulated 0.95 quantile of max_t Lambda_t under the protect truth over 5y,
# worst case over the LOW bucket's contract models (retirement_rule_gates_output.txt).
# HIGH: no statistic passed R2 — deliberately no boundary.
SPRT_BOUNDARY: dict[str, float | None] = {BUCKET_LOW: 3.7087, BUCKET_HIGH: None}
# Informational only, NOT adopted: what the same procedure gives at s0 = 1.0.
ALTERNATIVE_S0_1_0 = {
    "sprt": {BUCKET_LOW: 3.8842, BUCKET_HIGH: 5.6814},
    "cusum": {BUCKET_LOW: 5.8180, BUCKET_HIGH: 7.9806},
}


class RetirementRuleError(ValueError):
    """An input the rule cannot evaluate. Raised, never defaulted."""


@dataclass(frozen=True)
class RetirementAdvice:
    rule_id: str
    bucket: str
    n_days: int
    boundary: float | None
    statistic: float | None  # Lambda at the last day (None below MIN_DAYS)
    triggered: bool
    first_trigger_day: int | None  # 1-based index into the realized record
    note: str


def llr_increments(
    net_returns: pd.Series, s0: float = S0_PROTECT, s1: float = S1_HARM, periods_per_year: float = TRADING_DAYS_PER_YEAR
) -> np.ndarray:
    """l_t for every day, with the expanding-sample standardization declared
    in the pre-registration. Day 1 has no sample sd, so z_1 = 0 and it
    contributes the constant -d*m — identical to the gate script's
    llr_along, which is what the boundary was calibrated against."""
    r = np.asarray(pd.Series(net_returns, dtype=float).dropna().to_numpy(), dtype=float)
    if r.ndim != 1:
        raise RetirementRuleError("net_returns must be one-dimensional")
    n = len(r)
    if n == 0:
        return np.zeros(0)
    t = np.arange(1, n + 1, dtype=float)
    m1 = np.cumsum(r) / t
    m2 = np.cumsum(r**2) / t
    with np.errstate(divide="ignore", invalid="ignore"):
        sd = np.sqrt((m2 - m1**2) * t / (t - 1))
        z = r / sd
    z[0] = 0.0
    z = np.where(np.isfinite(z), z, 0.0)
    d = (s1 - s0) / np.sqrt(periods_per_year)
    m = (s1 + s0) / (2 * np.sqrt(periods_per_year))
    return d * (z - m)


def sprt_path(net_returns: pd.Series, **kwargs) -> np.ndarray:
    """Lambda_t = cumulative sum of the increments."""
    return np.cumsum(llr_increments(net_returns, **kwargs))


def evaluate(net_returns: pd.Series, bucket: str) -> RetirementAdvice:
    """The rule on one registration's realized net daily returns. `bucket`
    is the registration's autocorrelation bucket fixed at registration from
    its ORIGINAL window (dormant_pool.assign_bucket on the frozen spec's
    persisted series) — never re-chosen on the forward record."""
    if bucket not in SPRT_BOUNDARY:
        raise RetirementRuleError(f"unknown bucket {bucket!r}; expected one of {sorted(SPRT_BOUNDARY)}")
    boundary = SPRT_BOUNDARY[bucket]
    path = sprt_path(net_returns)
    n = len(path)
    if boundary is None:
        return RetirementAdvice(RULE_ID, bucket, n, None, float(path[-1]) if n else None, False, None,
                                "no calibrated rule for the HIGH bucket: no statistic reached 80% power at "
                                "true Sharpe -1.0 within 5y at the protect level (gates run 2); the advisory PSR "
                                "is all there is")
    if n < MIN_DAYS:
        return RetirementAdvice(RULE_ID, bucket, n, boundary, None, False, None,
                                f"below the {MIN_DAYS}-day floor: not evaluated")
    hits = np.flatnonzero(path[MIN_DAYS - 1 :] >= boundary)
    if hits.size:
        first = int(hits[0]) + MIN_DAYS
        return RetirementAdvice(RULE_ID, bucket, n, boundary, float(path[-1]), True, first,
                                f"retirement RECOMMENDED since day {first}: Lambda reached {boundary:.4f} "
                                f"(P(this | true Sharpe {S0_PROTECT}) <= {ALPHA} over {HORIZON_YEARS}y). "
                                "A recommendation, not a status change (CLAUDE.md rule 6).")
    return RetirementAdvice(RULE_ID, bucket, n, boundary, float(path[-1]), False, None,
                            f"not triggered: Lambda {path[-1]:+.3f} vs boundary {boundary:.4f}")


__all__ = [
    "ALPHA", "ALTERNATIVE_S0_1_0", "HORIZON_YEARS", "MIN_DAYS", "RULE_ID", "S0_PROTECT", "S1_HARM",
    "SPRT_BOUNDARY", "RetirementAdvice", "RetirementRuleError", "assign_bucket", "evaluate",
    "llr_increments", "sprt_path",
]
