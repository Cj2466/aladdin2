#!/usr/bin/env python
"""PHASE 1 GATE for the bet-level test (design memo: option C in the
2026-09-09 discussion). Nothing in production depends on this file; it exists
to answer, on synthetic data with a KNOWN truth, the one question that decides
whether option C may be built at all:

    Under a NULL with clustered events and overlapping bets, does a bet-level
    PSR with a cluster/overlap-robust effective n keep its false-positive rate
    at or below nominal?  (If not, C is dead — no SE tuning until it passes.)

and two secondary questions:

    Does the power gain over the daily-Sharpe test match the sqrt(f) dilution
    argument for an event mechanism active a fraction f of days?
    For a CONTINUOUS monthly-rebalanced mechanism, is bet-level (monthly)
    neutral, better, or worse than daily?

THE SYNTHETIC WORLD (adversarial on purpose)
  * T trading days. A two-state Markov regime (quiet / crisis). Events arrive
    with daily hazard P_QUIET in quiet and P_CRISIS in crisis, so they CLUSTER.
  * Daily noise is N(0, SIGMA) in quiet and N(0, CRISIS_VOL_MULT*SIGMA) in
    crisis — clustered events are also the noisier ones.
  * Each event opens a window of H days; the strategy is long (position 1)
    on any day inside any window. Overlapping windows SHARE days, so bets are
    correlated exactly the way real overlapping holds are.
  * A bet = one event's window return (sum of the strategy's daily returns
    over that window). Under the null the per-active-day effect DELTA is 0.

THE STATISTICS COMPARED (all "vs zero", single pre-registered test, no SR0 —
the ladder's SR0 term is common to every statistic at a given N and sigma_SR,
so relative behaviour here transfers to DSR unchanged)
  A   daily PSR:      SR of the full daily series (idle days are zeros), n = T
  B   naive bet PSR:  SR of the bet series, n = number of bets, i.i.d. SE
  C   robust bet PSR: same SR, but n_eff = n / design_effect, where
                      design_effect = Var_HAC(mean) / (s^2 / n) from a
                      Newey-West HAC covariance (statsmodels, maxlags = H,
                      pre-declared from the mechanism's window — NOT tuned)
  C'  cluster bet PSR: n_eff from a cluster-robust covariance, clusters =
                      calendar month of the event (statsmodels cov_type
                      'cluster'); reported for comparison, C is the candidate

PSR itself is the project's deflated_sharpe.probabilistic_sharpe_ratio with
the series' own skew/kurtosis, called as-is. The HAC / cluster covariances are
statsmodels' — no sandwich formula is retyped here (CLAUDE.md).

Run from backend/:  python data/research_runs/bet_level_2026-09-09/bet_level_fp_gate.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND))

from app.services.research_lab.deflated_sharpe import (  # noqa: E402
    compute_return_stats,
    probabilistic_sharpe_ratio,
)

T = 2926
H = 10
P_QUIET = 0.01
P_CRISIS = 0.15
STAY_QUIET = 0.995
STAY_CRISIS = 0.98
SIGMA = 0.01
CRISIS_VOL_MULT = 2.0
THRESHOLD = 0.95
REPS = 2000
SEED = 20260909


def simulate(rng, delta_active_day: float):
    """One world. Returns daily strategy returns, list of (start, end) windows,
    and the regime path."""
    regime = np.empty(T, dtype=int)
    regime[0] = 0
    u = rng.random(T)
    for t in range(1, T):
        stay = STAY_QUIET if regime[t - 1] == 0 else STAY_CRISIS
        regime[t] = regime[t - 1] if u[t] < stay else 1 - regime[t - 1]
    hazard = np.where(regime == 0, P_QUIET, P_CRISIS)
    events = np.flatnonzero(rng.random(T) < hazard)
    vol = np.where(regime == 0, SIGMA, CRISIS_VOL_MULT * SIGMA)
    noise = rng.standard_normal(T) * vol
    active = np.zeros(T, dtype=bool)
    windows = []
    for e in events:
        end = min(T, e + H)
        active[e:end] = True
        windows.append((e, end))
    daily = np.where(active, delta_active_day + noise, 0.0)
    return daily, windows, regime


def psr_vs_zero(x: np.ndarray, n_override: float | None = None) -> float | None:
    s = pd.Series(x)
    stats = compute_return_stats(s)
    if stats is None:
        return None
    sr = float(s.mean() / s.std(ddof=1))
    n = stats.n if n_override is None else max(3, int(round(n_override)))
    return probabilistic_sharpe_ratio(sr, 0.0, n, stats.skewness, stats.kurtosis)


def design_effect(bets: np.ndarray, cov_type: str, **kw) -> float:
    """Var_robust(mean) / Var_iid(mean) for the bet series."""
    y = bets
    X = np.ones((len(y), 1))
    fit = sm.OLS(y, X).fit(cov_type=cov_type, cov_kwds=kw)
    var_robust = float(fit.cov_params()[0, 0])
    var_iid = float(np.var(y, ddof=1) / len(y))
    return var_robust / var_iid if var_iid > 0 else np.nan


def one_rep(rng, delta):
    daily, windows, _ = simulate(rng, delta)
    if len(windows) < 8:
        return None
    bets = np.array([daily[s:e].sum() for s, e in windows])
    months = np.array([s // 21 for s, _ in windows])
    out = {"n_bets": len(windows), "f_active": float((daily != 0).mean())}
    out["A"] = psr_vs_zero(daily)
    out["B"] = psr_vs_zero(bets)
    de_hac = design_effect(bets, "HAC", maxlags=H)
    de_cl = design_effect(bets, "cluster", groups=months)
    out["DE_hac"], out["DE_cluster"] = de_hac, de_cl
    out["C"] = psr_vs_zero(bets, n_override=len(bets) / de_hac) if np.isfinite(de_hac) and de_hac > 0 else None
    out["Cc"] = psr_vs_zero(bets, n_override=len(bets) / de_cl) if np.isfinite(de_cl) and de_cl > 0 else None
    return out


def run_block(label, delta, rng):
    rows = []
    for _ in range(REPS):
        r = one_rep(rng, delta)
        if r is not None:
            rows.append(r)
    df = pd.DataFrame(rows)
    rates = {k: float((df[k] >= THRESHOLD).mean()) for k in ("A", "B", "C", "Cc")}
    se = {k: float(np.sqrt(max(v * (1 - v), 1e-6) / len(df))) for k, v in rates.items()}
    print(f"\n== {label}: delta/active-day = {delta:.5f}, reps kept = {len(df)}, "
          f"mean bets = {df.n_bets.mean():.0f}, mean active fraction f = {df.f_active.mean():.3f}, "
          f"mean design effect HAC = {df.DE_hac.mean():.2f}, cluster = {df.DE_cluster.mean():.2f}")
    for k, name in (("A", "daily PSR"), ("B", "naive bet PSR"), ("C", "robust bet PSR (HAC)"), ("Cc", "robust bet PSR (cluster/month)")):
        print(f"   P(PSR >= {THRESHOLD}) {name:<32} = {rates[k]:.4f}  (MC se {se[k]:.4f})")
    return rates, se, df


def continuous_block(rng, true_annual_sharpe: float, reps: int = REPS):
    """A continuous monthly-rebalanced mechanism with i.i.d. daily noise:
    daily PSR vs monthly-bet PSR at the same truth. The Sharpe SE argument
    says these should be equal in expectation (sqrt(252/T) == sqrt(12/T/21))."""
    s_daily = true_annual_sharpe / np.sqrt(252)
    hits = {"daily": 0, "monthly": 0}
    for _ in range(reps):
        x = rng.standard_normal(T) * SIGMA + s_daily * SIGMA
        monthly = np.add.reduceat(x, np.arange(0, T, 21))
        pd_ = psr_vs_zero(x)
        pm = psr_vs_zero(monthly)
        hits["daily"] += int(pd_ is not None and pd_ >= THRESHOLD)
        hits["monthly"] += int(pm is not None and pm >= THRESHOLD)
    return {k: v / reps for k, v in hits.items()}


def main() -> int:
    t0 = time.time()
    rng = np.random.default_rng(SEED)
    print(f"T={T} days, H={H}, hazards quiet/crisis {P_QUIET}/{P_CRISIS}, crisis vol x{CRISIS_VOL_MULT}, reps={REPS}")

    null_rates, null_se, dnull = run_block("NULL (no effect)", 0.0, rng)
    gate_pass = null_rates["C"] <= (1 - THRESHOLD) + 2 * null_se["C"]
    print(f"\n   GATE 1 (robust bet PSR false-positive <= nominal {1-THRESHOLD:.2f} + 2se): "
          f"{'PASS' if gate_pass else 'FAIL'}  [{null_rates['C']:.4f} vs {(1-THRESHOLD) + 2*null_se['C']:.4f}]")
    print(f"   naive bet PSR inflation vs nominal: {null_rates['B'] / (1 - THRESHOLD):.1f}x")

    # Alternative: true per-active-day Sharpe s_active such that an ALWAYS-active
    # strategy would have annual Sharpe 1.0; the event strategy is active f of days.
    s_active = 1.0 / np.sqrt(252)
    delta = s_active * SIGMA  # quiet-regime units; crisis days are noisier, effect fixed
    alt_rates, alt_se, dalt = run_block("ALTERNATIVE (true active-day annual Sharpe 1.0, effect fixed)", delta, rng)
    f = dalt.f_active.mean()
    print(f"\n   sqrt(f) dilution prediction: daily test sees Sharpe x {np.sqrt(f):.2f}; "
          f"power daily = {alt_rates['A']:.3f} vs robust bet = {alt_rates['C']:.3f}")

    print("\n== CONTINUOUS monthly-rebalanced mechanism, i.i.d. daily noise (option C neutrality check)")
    for s in (0.5, 0.8):
        r = continuous_block(rng, s, reps=1000)
        print(f"   true annual Sharpe {s:.1f}: P(PSR>=0.95) daily = {r['daily']:.3f}, monthly bets = {r['monthly']:.3f}")

    print(f"\nelapsed {time.time() - t0:.0f}s")
    return 0 if gate_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
