"""Run the EB shrinkage estimator against this project's REAL stored trials.

READ-ONLY: opens the SQLite file with mode=ro so a write is impossible at the
driver level, not merely by convention.
"""

import json
import sqlite3
import sys

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-ae4c6e712670defb9/backend")

from app.services.research_lab.empirical_bayes_shrinkage import (  # noqa: E402
    MIN_TRIALS_FOR_SHRINKAGE,
    fit_empirical_bayes,
    fit_empirical_bayes_by_group,
    trial_from_experiment_run,
)

DB = "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/aladdin2.db"
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
cur = con.cursor()

print("=" * 90)
print("SOURCE 1: experiment_runs  (the primary backtest-results table)")
print("=" * 90)
rows = cur.execute(
    "SELECT id, strategy_name, ticker_a, ticker_b, status, sharpe_net, num_trades, "
    "configurations_tested, results_json FROM experiment_runs"
).fetchall()
print(f"  total rows            : {len(rows)}")
ok = [r for r in rows if r["status"] == "ok"]
print(f"  rows with status='ok' : {len(ok)}")

observations = []
skipped = 0
for r in ok:
    obs = trial_from_experiment_run(
        r["id"], r["strategy_name"], r["ticker_a"], r["ticker_b"], r["results_json"]
    )
    if obs is None:
        skipped += 1
    else:
        observations.append(obs)
print(f"  usable (sharpe + se)  : {len(observations)}   (skipped {skipped} unusable)")

print()
print("=" * 90)
print("SOURCE 2: other tables that could conceivably hold trial-level results")
print("=" * 90)
for table, note in [
    ("cross_sectional_forward_validation_registrations", "cross-sectional family forward runs"),
    ("forward_validation_registrations", "pairs/momentum forward runs"),
    ("screening_candidates", "screening scores (no Sharpe, no n)"),
    ("screening_jobs", "screening job metadata"),
    ("sweep_jobs", "parameter-sweep parents of experiment_runs"),
    ("strategy_portfolio_allocations", "portfolio weights over experiment_runs"),
]:
    n = cur.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    print(f"  {table:<52s} {n:>5d}   ({note})")

print()
print("=" * 90)
print("SHRINKAGE RESULT")
print("=" * 90)
if len(observations) == 0:
    print("  NO TRIALS AVAILABLE. Nothing to shrink.")
    print(f"  (The estimator requires >= {MIN_TRIALS_FOR_SHRINKAGE} trials to estimate cross-trial dispersion.)")
else:
    pooled = fit_empirical_bayes(observations)
    print(f"  n_trials={pooled.n_trials}  mu_hat={pooled.mu_hat:.4f}  tau_hat={pooled.tau_hat:.4f}")
    print(f"  Q={pooled.q_statistic:.2f} df={pooled.q_df} p={pooled.heterogeneity_p_value:.4g} I^2={pooled.i_squared:.1%}")
    print(f"  mean shrinkage weight = {pooled.mean_shrinkage_weight:.3f}")
    print(f"\n  {pooled.interpretation}\n")
    print(f"  {'rank_s':>6} {'rank_raw':>8} {'shrunk':>9} {'raw':>9} {'se':>7} {'wt':>6} {'P(>0)':>7}  label")
    for t in sorted(pooled.trials, key=lambda x: x.rank_shrunk)[:25]:
        print(
            f"  {t.rank_shrunk:>6d} {t.rank_raw:>8d} {t.theta_shrunk:>9.4f} {t.theta_hat:>9.4f} "
            f"{t.se:>7.3f} {t.shrinkage_weight:>6.3f} {t.prob_positive:>7.1%}  {t.label}"
        )
    moved = sum(1 for t in pooled.trials if t.rank_raw != t.rank_shrunk)
    print(f"\n  trials whose rank changed under shrinkage: {moved}/{pooled.n_trials}")

    print("\n  --- per strategy_name group ---")
    for name, res in fit_empirical_bayes_by_group(observations).items():
        print(f"  {name:<20s} n={res.n_trials:<4d} floor_met={res.floor_met} tau_hat={res.tau_hat:.4f}")

con.close()
print("\n(read-only connection closed; no rows were modified)")
