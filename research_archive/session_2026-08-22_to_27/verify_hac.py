import numpy as np
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant

# Fully independent re-implementation (not importing production code)
def indep_hac(y, lags=5):
    n = len(y)
    if n < 3 or np.std(y) == 0:
        return False
    X = add_constant(np.arange(n, dtype=float))
    try:
        res = OLS(y, X).fit().get_robustcov_results(cov_type="HAC", maxlags=lags)
        return bool(res.pvalues[1] <= 0.05)
    except Exception:
        return False

for lo, hi in [(0,500),(0,1000),(10000,10500),(50000,51000)]:
    hits = 0
    for s in range(lo, hi):
        rng = np.random.default_rng(s)
        y = np.cumsum(rng.normal(0, 0.01, 90))
        if indep_hac(y):
            hits += 1
    print(f"seeds {lo}-{hi}: {hits}/{hi-lo} = {hits/(hi-lo):.3%}")
