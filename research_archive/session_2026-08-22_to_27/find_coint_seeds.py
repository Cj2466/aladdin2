import sys
sys.path.insert(0, ".")
import numpy as np
from statsmodels.tsa.stattools import coint

def cointegrated_pair(n, seed, phi=0.5, common_std=0.01, spread_std=0.005):
    rng = np.random.default_rng(seed)
    common = np.cumsum(rng.normal(0, common_std, n))
    spread = np.zeros(n)
    eps = rng.normal(0, spread_std, n)
    for t in range(1, n):
        spread[t] = phi * spread[t-1] + eps[t]
    log_a = common
    log_b = common + spread
    return 100*np.exp(log_a), 100*np.exp(log_b)

def spurious_pair(n, seed, common_std=0.01, idio_std=0.003):
    rng = np.random.default_rng(seed)
    common = np.cumsum(rng.normal(0, common_std, n))
    idio_a = np.cumsum(rng.normal(0, idio_std, n))
    idio_b = np.cumsum(rng.normal(0, idio_std, n))
    log_a = common + idio_a
    log_b = common + idio_b
    return 100*np.exp(log_a), 100*np.exp(log_b)

n = 550
print("=== cointegrated pair search ===")
for seed in range(20):
    a, b = cointegrated_pair(n, seed)
    log_a, log_b = np.log(a), np.log(b)
    corr = np.corrcoef(np.diff(log_a), np.diff(log_b))[0,1]
    stat, p, crit = coint(log_a, log_b)
    print(seed, "corr=", round(corr,3), "coint_p=", round(p,4), "PASS" if (corr>=0.6 and p<=0.05) else "")

print("=== spurious pair search ===")
for seed in range(20):
    a, b = spurious_pair(n, seed)
    log_a, log_b = np.log(a), np.log(b)
    corr = np.corrcoef(np.diff(log_a), np.diff(log_b))[0,1]
    stat, p, crit = coint(log_a, log_b)
    print(seed, "corr=", round(corr,3), "coint_p=", round(p,4), "SPURIOUS-CORR-BUT-NOT-COINT" if (corr>=0.6 and p>0.05) else "")
