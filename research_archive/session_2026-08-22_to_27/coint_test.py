import sys, time
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint, adfuller

from app.services.risk.correlation import correlation_matrix
from app.services.risk.returns import compute_daily_returns
from app.services.research_lab.screening import _pairs_from_correlation_matrix, MIN_SCREENING_CORRELATION

prices = pd.read_pickle("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/prices_3y.pkl")
print("Full history shape:", prices.shape)

def run_at_window(trading_days, label):
    window = prices.tail(trading_days + 1).dropna(axis=1, how="any")
    print(f"\n=== Window: {label} ({trading_days} trading days) -> {window.shape[1]} tickers survive dropna ===")
    returns = compute_daily_returns(window)
    corr = correlation_matrix(returns)
    pairs = _pairs_from_correlation_matrix(corr, MIN_SCREENING_CORRELATION, max_candidates=100_000)
    print(f"Correlation-passing pairs (|corr|>=0.6): {len(pairs)}")

    t0 = time.time()
    results = []
    for p in pairs:
        a = np.log(window[p.ticker_a].to_numpy())
        b = np.log(window[p.ticker_b].to_numpy())
        score, pvalue, crit = coint(a, b, trend="c", autolag="aic")
        results.append((p.ticker_a, p.ticker_b, p.correlation, pvalue))
    elapsed = time.time() - t0
    print(f"Ran {len(results)} coint() tests in {elapsed:.1f}s ({elapsed/max(len(results),1)*1000:.1f}ms/pair)")

    if results:
        pvals = np.array([r[3] for r in results])
        for thresh in (0.05, 0.01):
            n_pass = int((pvals <= thresh).sum())
            print(f"  p<={thresh}: {n_pass}/{len(results)} ({100*n_pass/len(results):.1f}%)")
        # show a few of the strongest coint hits
        results.sort(key=lambda r: r[3])
        print("  Top 8 by p-value:")
        for a,b,c,p in results[:8]:
            print(f"    {a}-{b}: corr={c:.3f} coint_p={p:.4f}")
        print("  Bottom 8 (worst) by p-value:")
        for a,b,c,p in results[-8:]:
            print(f"    {a}-{b}: corr={c:.3f} coint_p={p:.4f}")
    return results

r1 = run_at_window(290, "current PAIRS_SCREENING_LOOKBACK_CALENDAR_DAYS=425 calendar days (~290 trading days)")
r2 = run_at_window(500, "~2 years (500 trading days)")
r3 = run_at_window(750, "full available ~3 years (750 trading days)")

# Control: random-walk synthetic pairs (independent GBM, no true relationship)
# to check false-positive/spurious-pass rate, same discipline already applied to AR(1) fit.
print("\n=== Control: independent random-walk pairs (spurious-pass check) ===")
rng = np.random.default_rng(42)
n_days = 290
n_synthetic_pairs = 300
spurious_pvals = []
spurious_corrs = []
for i in range(n_synthetic_pairs):
    a = np.cumsum(rng.normal(0, 0.01, n_days)) + np.log(100)
    b = np.cumsum(rng.normal(0, 0.01, n_days)) + np.log(100)
    corr = np.corrcoef(np.diff(a), np.diff(b))[0, 1]
    spurious_corrs.append(corr)
    if abs(corr) >= MIN_SCREENING_CORRELATION:
        score, pvalue, crit = coint(a, b, trend="c", autolag="aic")
        spurious_pvals.append(pvalue)
print(f"Of {n_synthetic_pairs} independent random-walk pairs, {len(spurious_pvals)} passed |corr|>=0.6 by chance")
if spurious_pvals:
    arr = np.array(spurious_pvals)
    for thresh in (0.05, 0.01):
        n_pass = int((arr <= thresh).sum())
        print(f"  Of those correlation-passing spurious pairs, coint p<={thresh}: {n_pass}/{len(arr)} ({100*n_pass/max(len(arr),1):.1f}%)")
