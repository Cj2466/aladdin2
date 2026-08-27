"""How unstable is tau^2_hat as a function of the number of sibling trials k?

Mirrors the simulation deflated_sharpe.py used to justify MIN_TRIALS_FOR_DSR:
repeated sampling, report the coefficient of variation of the estimate itself.
"""

import numpy as np
from scipy.optimize import brentq

rng = np.random.default_rng(7)


def dl_tau2(theta, se):
    w = 1.0 / se**2
    mu = np.sum(w * theta) / np.sum(w)
    q = np.sum(w * (theta - mu) ** 2)
    df = len(theta) - 1
    c = np.sum(w) - np.sum(w**2) / np.sum(w)
    return max(0.0, (q - df) / c), q, df


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


REPS = 3000
TRUE_TAU2 = 0.09  # tau = 0.3 annualized-Sharpe dispersion
MU = 0.0

print(f"true tau^2 = {TRUE_TAU2}, mu = {MU}, se_i ~ U(0.25, 0.55)")
print(f"{'k':>5} {'DL mean':>9} {'DL CV':>8} {'DL %at0':>9} {'PM mean':>9} {'PM CV':>8} {'PM %at0':>9}")
for k in [3, 5, 8, 10, 15, 20, 30, 50, 100, 200]:
    dl_vals, pm_vals = [], []
    for _ in range(REPS):
        se = rng.uniform(0.25, 0.55, k)
        theta_true = rng.normal(MU, np.sqrt(TRUE_TAU2), k)
        theta_hat = theta_true + rng.normal(0, se)
        dl_vals.append(dl_tau2(theta_hat, se)[0])
        pm_vals.append(pm_tau2(theta_hat, se))
    dl_vals = np.array(dl_vals)
    pm_vals = np.array(pm_vals)
    print(
        f"{k:>5d} {dl_vals.mean():>9.4f} {dl_vals.std()/max(dl_vals.mean(),1e-12):>8.2%} "
        f"{(dl_vals==0).mean():>9.1%} {pm_vals.mean():>9.4f} "
        f"{pm_vals.std()/max(pm_vals.mean(),1e-12):>8.2%} {(pm_vals==0).mean():>9.1%}"
    )
