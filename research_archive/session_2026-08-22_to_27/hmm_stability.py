import sys, warnings
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import numpy as np
import pandas as pd
from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression

warnings.filterwarnings("ignore")

prices = pd.read_pickle("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/prices_3y.pkl")
tickers = list(prices.columns)[:25]

def classify(series, window_len, offset):
    end_idx = len(series) - offset
    window = series.iloc[end_idx - window_len: end_idx]
    log_ret = np.diff(np.log(window.to_numpy())) * 100
    try:
        mod = MarkovRegression(log_ret, k_regimes=2, trend="c", switching_variance=True)
        res = mod.fit(disp=False, maxiter=200)
    except Exception:
        return None
    p = dict(zip(mod.param_names, res.params))
    sigma0, sigma1 = np.sqrt(p["sigma2[0]"]), np.sqrt(p["sigma2[1]"])
    hi = 0 if sigma0 > sigma1 else 1
    smoothed_last = np.asarray(res.smoothed_marginal_probabilities)[-1] if not hasattr(res.smoothed_marginal_probabilities, "iloc") else res.smoothed_marginal_probabilities.iloc[-1].to_numpy()
    current = int(np.argmax(smoothed_last))
    return "HIGH" if current == hi else "low"

print("=== Stability across nearby windows (500-day, offset by a few days) ===")
n_flips = 0
n_checks = 0
for ticker in tickers:
    series = prices[ticker].dropna()
    if len(series) < 520:
        continue
    labels = [classify(series, 500, off) for off in (0, 3, 6, 10, 15, 20)]
    flips = sum(1 for i in range(1, len(labels)) if labels[i] != labels[i-1] and None not in (labels[i], labels[i-1]))
    n_flips += flips
    n_checks += len(labels) - 1
    print(f"{ticker:6s}: {labels}  (flips: {flips})")
print(f"\nTotal flip rate: {n_flips}/{n_checks} transitions ({100*n_flips/max(n_checks,1):.1f}%)")

print("\n=== Window-length sensitivity: 252d vs 500d classification agreement (offset=0) ===")
agree = 0
total = 0
for ticker in tickers:
    series = prices[ticker].dropna()
    if len(series) < 520:
        continue
    l252 = classify(series, 252, 0)
    l500 = classify(series, 500, 0)
    total += 1
    if l252 == l500:
        agree += 1
    print(f"{ticker:6s}: 252d={l252}  500d={l500}  {'MATCH' if l252==l500 else 'DIFFER'}")
print(f"\nAgreement: {agree}/{total} ({100*agree/max(total,1):.1f}%)")
