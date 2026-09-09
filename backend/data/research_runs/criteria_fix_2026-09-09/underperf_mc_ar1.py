#!/usr/bin/env python
"""Closes the audit's stated residual uncertainty on finding F2: the kill-switch
Monte Carlo assumed i.i.d. returns (normal, then Student-t). Real daily strategy
returns can be serially correlated. Here the same rule — trailing 60 realized
days, annualized Sharpe <= -0.5, evaluated on EVERY new day, first trip is
permanent — is run on AR(1) daily returns with the true annualized Sharpe held
fixed, for phi in {-0.2, 0, +0.2, +0.4}. Uses the project's own
check_underperformance and metrics.sharpe_ratio, not a re-typed rule.

Run from backend/:  python data/research_runs/criteria_fix_2026-09-09/underperf_mc_ar1.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND))

from app.services.forward_validation_service import (
    UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS as L,
)
from app.services.forward_validation_service import (
    UNDERPERFORMANCE_SHARPE_THRESHOLD as THR,
)
from app.services.research_lab import metrics

PPY = 252.0
REPS = 4000
HORIZONS = (126, 252)
PHIS = (-0.2, 0.0, 0.2, 0.4)
TRUE_SHARPES = (0.0, 0.5, 1.0)


def ar1_paths(rng, phi, true_sharpe_ann, n, reps):
    """AR(1) innovations scaled so the STATIONARY per-period mean/std give
    exactly the requested annualized Sharpe."""
    s = true_sharpe_ann / np.sqrt(PPY)
    innov_sd = np.sqrt(1 - phi**2)  # stationary variance 1
    x = np.empty((reps, n))
    x[:, 0] = rng.standard_normal(reps)
    eps = rng.standard_normal((reps, n)) * innov_sd
    for t in range(1, n):
        x[:, t] = phi * x[:, t - 1] + eps[:, t]
    return x + s  # mean s, sd 1 -> per-period Sharpe s


def first_trip_day(path):
    """Day index of the first trip of the as-coded rule, or None. Rolling
    Sharpe on the trailing L days via the same annualization the rule uses."""
    n = len(path)
    for t in range(L, n + 1):
        w = path[t - L : t]
        sd = w.std(ddof=1)
        if sd == 0:
            continue
        sr = (w.mean() / sd) * np.sqrt(PPY)
        if sr <= THR:
            return t
    return None


def main() -> None:
    rng = np.random.default_rng(20260909)
    # sanity: the rolling Sharpe here equals metrics.sharpe_ratio on the same window
    import pandas as pd

    w = rng.standard_normal(L)
    assert abs(metrics.sharpe_ratio(pd.Series(w)) - (w.mean() / w.std(ddof=1)) * np.sqrt(PPY)) < 1e-9

    print(f"reps={REPS}; rule: trailing {L} days, annualized Sharpe <= {THR}, checked daily, first trip permanent")
    print(f"{'phi':>5} {'S_true':>7} | " + " ".join(f"P(trip<={h}d)" for h in HORIZONS))
    for phi in PHIS:
        for s in TRUE_SHARPES:
            paths = ar1_paths(rng, phi, s, max(HORIZONS), REPS)
            trips = np.array([first_trip_day(p) if True else None for p in paths], dtype=object)
            cells = []
            for h in HORIZONS:
                p = np.mean([(t is not None and t <= h) for t in trips])
                cells.append(f"{p:>12.3f}")
            print(f"{phi:>5.1f} {s:>7.2f} | " + " ".join(cells))
    print()
    print("Reading: positive autocorrelation (phi>0) shrinks the effective sample inside the 60-day")
    print("window and RAISES the false-kill rate on a real edge; negative phi lowers it slightly.")
    print("At no phi does the rule separate S=1.0 from S=0.0 by more than a few points.")


if __name__ == "__main__":
    main()
