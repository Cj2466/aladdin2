import sys, time
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint

from app.services.risk.correlation import correlation_matrix
from app.services.risk.returns import compute_daily_returns
from app.services.research_lab.screening import _pairs_from_correlation_matrix, MIN_SCREENING_CORRELATION
from app.services.research_lab import ou_pairs

prices = pd.read_pickle("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/prices_full503_760d.pkl")
print("Full universe shape:", prices.shape)

# Stage 1: EXISTING correlation prefilter, UNCHANGED (tail 253 days)
corr_window = prices.tail(ou_pairs.DEFAULT_FIT_WINDOW_DAYS + 1).dropna(axis=1, how="any")
print(f"Correlation window: {corr_window.shape[1]} tickers survive dropna (of {prices.shape[1]})")
returns = compute_daily_returns(corr_window)
corr = correlation_matrix(returns)
corr_pairs = _pairs_from_correlation_matrix(corr, MIN_SCREENING_CORRELATION, max_candidates=100_000)
print(f"Correlation-passing pairs (|corr|>=0.6) on FULL 503-universe: {len(corr_pairs)}")

# Stage 2: NEW cointegration filter over a LONGER 500-trading-day window
COINT_WINDOW = 500
coint_window = prices.tail(COINT_WINDOW)
t0 = time.time()
results = []
for p in corr_pairs:
    if p.ticker_a not in coint_window.columns or p.ticker_b not in coint_window.columns:
        continue
    a = coint_window[p.ticker_a].dropna()
    b = coint_window[p.ticker_b].dropna()
    common = a.index.intersection(b.index)
    if len(common) < COINT_WINDOW * 0.9:
        continue
    log_a = np.log(a.loc[common].to_numpy())
    log_b = np.log(b.loc[common].to_numpy())
    try:
        score, pvalue, crit = coint(log_a, log_b, trend="c", autolag="aic")
    except Exception:
        continue
    results.append((p.ticker_a, p.ticker_b, p.correlation, pvalue))
elapsed = time.time() - t0
print(f"Ran {len(results)} coint() tests in {elapsed:.1f}s")

pvals = np.array([r[3] for r in results])
for thresh in (0.05, 0.01):
    n_pass = int((pvals <= thresh).sum())
    print(f"  p<={thresh}: {n_pass}/{len(results)} ({100*n_pass/len(results):.2f}% of correlation-passing pairs; "
          f"{100*n_pass/(503*502/2):.3f}% of all {503*502//2} possible pairs)")

results.sort(key=lambda r: r[3])
print("Top 15 cointegrated pairs on the real full universe:")
for a,b,c,p in results[:15]:
    print(f"  {a}-{b}: corr={c:.3f} coint_p={p:.4f}")
