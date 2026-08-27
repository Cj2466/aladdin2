"""DerSimonian-Laird vs Paule-Mandel: which recovers tau^2 better, and where?

DL is closed-form but is documented to be downward-biased when tau^2 is large
relative to the within-trial variances, and when the se_i are very unequal.
Test that claim directly rather than repeating it from memory.
"""

import numpy as np
from scipy.optimize import brentq

rng = np.random.default_rng(11)


def dl_tau2(theta, se):
    w = 1.0 / se**2
    mu = np.sum(w * theta) / np.sum(w)
    q = np.sum(w * (theta - mu) ** 2)
    df = len(theta) - 1
    c = np.sum(w) - np.sum(w**2) / np.sum(w)
    return max(0.0, (q - df) / c)


def pm_tau2(theta, se):
    k = len(theta)

    def f(t2):
        w = 1.0 / (t2 + se**2)
        mu = np.sum(w * theta) / np.sum(w)
        return np.sum(w * (theta - mu) ** 2) - (k - 1)

    if f(0.0) <= 0:
        return 0.0
    hi = 1.0
    for _ in range(200):
        if f(hi) < 0:
            break
        hi *= 2.0
    else:
        return hi
    return brentq(f, 0.0, hi, xtol=1e-12)


REPS = 4000
K = 60
print(f"k={K}, reps={REPS}")
for se_lo, se_hi, tag in [(0.35, 0.45, "near-homoskedastic se~U(.35,.45)"),
                          (0.10, 1.20, "STRONGLY heteroskedastic se~U(.10,1.20)")]:
    print(f"\n--- {tag} ---")
    print(f"{'true tau^2':>11} {'DL mean':>9} {'DL bias%':>9} {'PM mean':>9} {'PM bias%':>9}")
    for true_tau2 in [0.0, 0.01, 0.09, 0.25, 1.0, 4.0]:
        dl_v, pm_v = [], []
        for _ in range(REPS):
            se = rng.uniform(se_lo, se_hi, K)
            th = rng.normal(0.0, np.sqrt(true_tau2), K) + rng.normal(0, se)
            dl_v.append(dl_tau2(th, se))
            pm_v.append(pm_tau2(th, se))
        dl_m, pm_m = np.mean(dl_v), np.mean(pm_v)
        db = (dl_m - true_tau2) / true_tau2 * 100 if true_tau2 > 0 else float("nan")
        pb = (pm_m - true_tau2) / true_tau2 * 100 if true_tau2 > 0 else float("nan")
        print(f"{true_tau2:>11.3f} {dl_m:>9.4f} {db:>8.1f}% {pm_m:>9.4f} {pb:>8.1f}%")
