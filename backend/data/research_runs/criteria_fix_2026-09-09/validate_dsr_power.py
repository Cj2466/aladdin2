#!/usr/bin/env python
"""Validate dsr_power against synthetic data with a KNOWN true Sharpe.

For each (true Sharpe, n_obs, N, sigma_sr) case: simulate i.i.d. normal daily
returns with exactly that true per-period Sharpe, compute SR_hat and the
sample skew/kurtosis the project's own compute_return_stats would, feed them
through probabilistic_sharpe_ratio / expected_max_sharpe_under_noise exactly
as compute_deflated_sharpe does, and count how often DSR >= threshold. That
empirical rate must agree with dsr_power.power_to_pass to within Monte-Carlo
error. Run from backend/:  python data/research_runs/criteria_fix_2026-09-09/validate_dsr_power.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND))

import pandas as pd

from app.services.research_lab.deflated_sharpe import (
    compute_return_stats,
    expected_max_sharpe_under_noise,
    probabilistic_sharpe_ratio,
)
from app.services.research_lab.dsr_power import (
    min_detectable_sharpe,
    power_to_pass,
    required_observed_sharpe,
    years_to_detect,
)

PPY = 252.0
REPS = 20_000
CASES = [
    # (true annual Sharpe, n_obs, n_trials, sigma_sr_ann, threshold)
    (0.5, 2926, 12, 0.19, 0.95),
    (0.8, 2926, 12, 0.19, 0.95),
    (1.0, 2926, 12, 0.19, 0.95),
    (0.5, 2926, 12, 0.19, 0.50),
    (0.5, 1000, 24, 0.30, 0.95),
    (1.0, 1000, 24, 0.30, 0.95),
    (0.3, 2926, 1031, 0.19, 0.50),
    (0.0, 2926, 12, 0.19, 0.95),  # null: pass rate must be small
]


def empirical_pass_rate(rng, true_sharpe_ann, n_obs, n_trials, sigma_ann, threshold):
    s = true_sharpe_ann / np.sqrt(PPY)
    sr0 = expected_max_sharpe_under_noise(sigma_ann / np.sqrt(PPY), n_trials)
    x = rng.standard_normal((REPS, n_obs)) + s  # unit variance, mean s -> true per-period Sharpe s
    means = x.mean(axis=1)
    stds = x.std(axis=1, ddof=1)
    sr_hat = means / stds
    passes = 0
    # sample moments per replication, as compute_return_stats would produce
    for i in range(REPS):
        stats = compute_return_stats(pd.Series(x[i]))
        psr = probabilistic_sharpe_ratio(sr_hat[i], sr0, n_obs, stats.skewness, stats.kurtosis)
        if psr is not None and psr >= threshold:
            passes += 1
    return passes / REPS


def main() -> int:
    rng = np.random.default_rng(20260909)
    print(f"reps={REPS}, periods_per_year={PPY}")
    print(f"{'S_true':>7} {'n_obs':>6} {'N':>5} {'sig':>5} {'thr':>5} | {'SR_req':>7} {'analytic':>9} {'empirical':>9} {'MC se':>6} {'|z|':>5}")
    worst = 0.0
    for true_s, n_obs, n_tr, sig, thr in CASES:
        req = required_observed_sharpe(threshold=thr, n_observations=n_obs, n_trials=n_tr, sigma_sr_annualized=sig)
        analytic = power_to_pass(true_sharpe_annualized=true_s, threshold=thr, n_observations=n_obs, n_trials=n_tr, sigma_sr_annualized=sig)
        emp = empirical_pass_rate(rng, true_s, n_obs, n_tr, sig, thr)
        se = np.sqrt(max(emp * (1 - emp), 1e-6) / REPS)
        z = abs(emp - analytic) / se
        worst = max(worst, z)
        print(f"{true_s:>7.2f} {n_obs:>6d} {n_tr:>5d} {sig:>5.2f} {thr:>5.2f} | {req:>7.3f} {analytic:>9.4f} {emp:>9.4f} {se:>6.4f} {z:>5.2f}")
    print()
    mds = min_detectable_sharpe(threshold=0.95, n_observations=2926, n_trials=12, sigma_sr_annualized=0.19)
    yrs = years_to_detect(true_sharpe_annualized=0.5, threshold=0.95, n_trials=12, sigma_sr_annualized=0.19)
    print(f"min detectable Sharpe (80% power) at n=2926, N=12, sigma=0.19, bar 0.95: {mds:.3f}")
    print(f"years of daily data to detect true Sharpe 0.5 at 80% power, N=12, sigma=0.19, bar 0.95: {yrs:.1f}")
    print(f"worst |z| across cases: {worst:.2f}  (asymptotic-normal approximation; |z| < 3 expected at these n)")
    return 0 if worst < 3.5 else 1


if __name__ == "__main__":
    raise SystemExit(main())
