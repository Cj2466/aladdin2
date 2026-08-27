import sys
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import numpy as np
from statsmodels.tsa.stattools import coint
from app.services.research_lab.screening import MIN_SCREENING_CORRELATION

# More realistic spurious-pass control: two series sharing a common
# "market factor" random walk (so they correlate via shared beta, exactly
# like two real large-caps sharing market-wide beta) plus independent
# idiosyncratic random-walk noise on each leg -- NOT genuinely cointegrated
# (the spread between them is itself a random walk, since neither leg's
# idiosyncratic component is stationary or shared).
rng = np.random.default_rng(7)
n_days = 500
n_pairs = 400
corr_pass = 0
coint_pvals = []
for i in range(n_pairs):
    market = np.cumsum(rng.normal(0, 0.008, n_days))
    beta_a, beta_b = rng.uniform(0.7, 1.3), rng.uniform(0.7, 1.3)
    idio_a = np.cumsum(rng.normal(0, 0.006, n_days))
    idio_b = np.cumsum(rng.normal(0, 0.006, n_days))
    a = beta_a * market + idio_a + np.log(100)
    b = beta_b * market + idio_b + np.log(100)
    corr = np.corrcoef(np.diff(a), np.diff(b))[0, 1]
    if abs(corr) >= MIN_SCREENING_CORRELATION:
        corr_pass += 1
        score, pvalue, crit = coint(a, b, trend="c", autolag="aic")
        coint_pvals.append(pvalue)

print(f"Shared-market-factor synthetic pairs: {corr_pass}/{n_pairs} passed |corr|>=0.6 (realistic, market-beta-driven correlation)")
if coint_pvals:
    arr = np.array(coint_pvals)
    for thresh in (0.05, 0.01):
        n_pass = int((arr <= thresh).sum())
        print(f"  Of those, coint p<={thresh}: {n_pass}/{len(arr)} ({100*n_pass/len(arr):.1f}%) -- spurious-pass rate of the NEW gate")
