"""Where is the detection boundary of a single-Gaussian-prior EB estimator?

SYNTHETIC. Establishes what this module can and cannot recover, so the honest
caveats in the final report are measured rather than asserted.
"""

import sys

import numpy as np

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-ae4c6e712670defb9/backend")

from app.services.research_lab.empirical_bayes_shrinkage import (  # noqa: E402
    TrialObservation,
    fit_empirical_bayes,
)

K = 212
SE = 0.40  # a well-measured trial (e.g. ~5y daily); keeps the arithmetic clean


def run(n_skilled, true_sharpe, seed, se=SE):
    rng = np.random.default_rng(seed)
    truth = np.zeros(K)
    truth[:n_skilled] = true_sharpe
    hat = truth + rng.normal(0, se, K)
    obs = [TrialObservation(f"p{i:03d}", float(hat[i]), se) for i in range(K)]
    res = fit_empirical_bayes(obs)
    skilled = [t for t in res.trials if int(t.trial_id[1:]) < n_skilled]
    top_n = sum(1 for t in skilled if t.rank_shrunk <= n_skilled)
    return res, np.mean([t.theta_shrunk for t in skilled]), top_n


print("=" * 100)
print("How many genuinely-skilled trials does a single-Gaussian prior need before it stops erasing them?")
print(f"(K={K} trials, se_i={SE} for all, skilled trials have true Sharpe = value shown)")
print("=" * 100)
print(f"{'n_skilled':>10} {'true SR':>8} {'t-stat':>7} | {'tau_hat':>8} {'Q p-value':>10} {'mean wt':>8} "
      f"| {'mean shrunk(skilled)':>20} {'recovered in top-n':>19}")
for n_skilled in [1, 3, 5, 10, 21, 42]:
    for true_sr in [0.6, 1.2, 2.0]:
        res, mean_sh, top_n = run(n_skilled, true_sr, seed=100 + n_skilled)
        print(f"{n_skilled:>10d} {true_sr:>8.1f} {true_sr/SE:>7.1f} | {res.tau_hat:>8.4f} "
              f"{res.heterogeneity_p_value:>10.4g} {res.mean_shrinkage_weight:>8.3f} "
              f"| {mean_sh:>20.4f} {f'{top_n}/{n_skilled}':>19}")
    print()

print("=" * 100)
print("SINGLE outlier, pushed to an extreme t-stat -- can ONE real edge ever survive a Gaussian prior?")
print("=" * 100)
print(f"{'true SR':>8} {'t-stat':>7} | {'tau_hat':>8} {'Q p':>9} {'wt':>6} | {'raw':>8} {'shrunk':>8} {'rank_raw':>9} {'rank_shrunk':>12}")
for true_sr in [1.2, 2.0, 4.0, 8.0, 16.0]:
    res, mean_sh, _ = run(1, true_sr, seed=7)
    t0 = [t for t in res.trials if t.trial_id == "p000"][0]
    print(f"{true_sr:>8.1f} {true_sr/SE:>7.1f} | {res.tau_hat:>8.4f} {res.heterogeneity_p_value:>9.3g} "
          f"{t0.shrinkage_weight:>6.3f} | {t0.theta_hat:>8.3f} {t0.theta_shrunk:>8.3f} "
          f"{t0.rank_raw:>9d} {t0.rank_shrunk:>12d}")
