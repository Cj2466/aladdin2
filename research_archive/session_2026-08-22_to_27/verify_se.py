"""Independently verify se(SR_hat) ~= sqrt((1 + SR^2/2)/n) by Monte Carlo.

Do NOT take the formula on faith (the Corwin-Schultz lesson). Generate iid
normal returns with a KNOWN true daily Sharpe, estimate SR many times, and
compare the empirical std of SR_hat against the analytic formula.
"""

import numpy as np

rng = np.random.default_rng(20260827)
REPS = 200_000

print(f"{'true_SR_d':>10} {'n':>6} {'emp_se':>10} {'analytic(n)':>12} {'ratio':>8} {'analytic(n-1)':>14} {'ratio':>8}")
for true_sr_daily in [0.0, 0.03, 0.06, 0.10, 0.20, 0.40]:
    for n in [60, 250, 750, 2500]:
        # returns ~ N(mu, sigma^2) with mu/sigma = true_sr_daily. sigma=0.01 wlog.
        sigma = 0.01
        mu = true_sr_daily * sigma
        x = rng.normal(mu, sigma, size=(REPS, n))
        m = x.mean(axis=1)
        s = x.std(axis=1, ddof=1)
        sr_hat = m / s
        emp_se = sr_hat.std(ddof=1)
        # Analytic evaluated at the TRUE Sharpe (the formula's population form)
        an_n = np.sqrt((1 + 0.5 * true_sr_daily**2) / n)
        an_nm1 = np.sqrt((1 + 0.5 * true_sr_daily**2) / (n - 1))
        print(
            f"{true_sr_daily:>10.2f} {n:>6d} {emp_se:>10.5f} {an_n:>12.5f} "
            f"{emp_se/an_n:>8.4f} {an_nm1:>14.5f} {emp_se/an_nm1:>8.4f}"
        )
