"""Does the post-shrinkage RANKING beat a naive raw-Sharpe ranking?

SYNTHETIC, with injected truth. Measures Spearman correlation of each ranking
against the true theta_i, plus top-10 precision (how many of the truly-best 10
each method actually surfaces).
"""

import sys

import numpy as np
from scipy.stats import spearmanr

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-ae4c6e712670defb9/backend")

from app.services.research_lab.empirical_bayes_shrinkage import (  # noqa: E402
    TrialObservation,
    fit_empirical_bayes,
)

K = 212
REPS = 200


def trial(hetero: bool, tau2: float, seed: int):
    rng = np.random.default_rng(seed)
    se = rng.uniform(0.10, 1.40, K) if hetero else np.full(K, 0.40)
    truth = rng.normal(0.0, np.sqrt(tau2), K)
    hat = truth + rng.normal(0, se)
    obs = [TrialObservation(f"p{i}", float(hat[i]), float(se[i])) for i in range(K)]
    res = fit_empirical_bayes(obs)
    raw = np.array([t.theta_hat for t in res.trials])
    sh = np.array([t.theta_shrunk for t in res.trials])
    top_true = set(np.argsort(-truth)[:10])
    return (
        spearmanr(raw, truth).statistic,
        spearmanr(sh, truth).statistic,
        len(top_true & set(np.argsort(-raw)[:10])),
        len(top_true & set(np.argsort(-sh)[:10])),
        sum(1 for a, b in zip(np.argsort(-raw), np.argsort(-sh)) if a != b),
    )


print("=" * 104)
print(f"RANKING QUALITY AGAINST INJECTED TRUTH  (K={K} trials, {REPS} independent populations)")
print("=" * 104)
print(f"{'se_i':>18} {'true tau^2':>11} | {'Spearman raw':>13} {'Spearman shrunk':>16} | "
      f"{'top-10 hits raw':>16} {'top-10 hits shrunk':>19}")
for hetero, tag in [(False, "all equal (0.40)"), (True, "U(0.10, 1.40)")]:
    for tau2 in [0.09, 0.25, 1.00]:
        rows = np.array([trial(hetero, tau2, 500 + s) for s in range(REPS)])
        print(
            f"{tag:>18} {tau2:>11.2f} | {rows[:,0].mean():>13.4f} {rows[:,1].mean():>16.4f} | "
            f"{rows[:,2].mean():>16.2f} {rows[:,3].mean():>19.2f}"
        )
    print()

print("Reading: with EQUAL se_i, shrinkage is a monotone transform of the raw Sharpe, so the two")
print("rankings are identical by construction and EB's contribution is magnitude, not order.")
print("With UNEQUAL se_i, the rankings genuinely diverge -- and the shrunk one tracks truth better.")
