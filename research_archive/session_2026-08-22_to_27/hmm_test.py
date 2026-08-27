import sys, time, warnings
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import numpy as np
import pandas as pd
from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression
from app.services.research_lab import regime as vr_regime

warnings.filterwarnings("ignore")

prices = pd.read_pickle("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/prices_3y.pkl")
tickers = list(prices.columns)  # all ~168

WINDOW = 500

results = []
t0 = time.time()
n_converged = 0
n_failed = 0
for ticker in tickers:
    series = prices[ticker].dropna()
    if len(series) < WINDOW + 1:
        continue
    window = series.iloc[-WINDOW:]
    log_ret = np.diff(np.log(window.to_numpy())) * 100
    try:
        mod = MarkovRegression(log_ret, k_regimes=2, trend="c", switching_variance=True)
        res = mod.fit(disp=False, maxiter=200)
        n_converged += 1
    except Exception:
        n_failed += 1
        continue
    p = dict(zip(mod.param_names, res.params))
    mean0, mean1 = p["const[0]"], p["const[1]"]
    sigma0, sigma1 = np.sqrt(p["sigma2[0]"]), np.sqrt(p["sigma2[1]"])
    smoothed_last = res.smoothed_marginal_probabilities.iloc[-1].to_numpy() if hasattr(res.smoothed_marginal_probabilities, "iloc") else np.asarray(res.smoothed_marginal_probabilities)[-1]
    current_regime = int(np.argmax(smoothed_last))
    vr = vr_regime.classify_regime(series)
    results.append({
        "ticker": ticker, "mean0": float(mean0), "mean1": float(mean1),
        "sigma0": float(sigma0), "sigma1": float(sigma1),
        "current_regime": current_regime, "regime_prob": float(smoothed_last[current_regime]),
        "vr_tag": vr.regime if vr else None,
        "p00": float(p["p[0->0]"]), "p10": float(p["p[1->0]"]),
    })

elapsed = time.time() - t0
print(f"Converged: {n_converged}, failed: {n_failed}, total time: {elapsed:.1f}s ({elapsed/max(n_converged+n_failed,1):.3f}s/ticker)")
print()

n_hi_vol_now = 0
n_lo_vol_now = 0
persistences = []
for r in results:
    hi = 0 if r["sigma0"] > r["sigma1"] else 1
    cur_label = "HIGH-VOL" if r["current_regime"] == hi else "low-vol"
    if cur_label == "HIGH-VOL":
        n_hi_vol_now += 1
    else:
        n_lo_vol_now += 1
    # expected duration of currently-active regime = 1/(1-p_stay)
    p_stay = r["p00"] if r["current_regime"] == 0 else (1 - r["p10"])
    exp_duration = 1 / max(1e-6, 1 - p_stay)
    persistences.append(exp_duration)
    print(f"{r['ticker']:6s} mean=[{r['mean0']:+.3f},{r['mean1']:+.3f}] sigma=[{r['sigma0']:.2f},{r['sigma1']:.2f}] "
          f"current={cur_label} prob={r['regime_prob']:.2f} exp_dur={exp_duration:6.1f}d VR_tag={r['vr_tag']}")

print(f"\nCurrently HIGH-VOL: {n_hi_vol_now}, low-vol: {n_lo_vol_now}")
persist = np.array(persistences)
print(f"Expected regime duration (days): median={np.median(persist):.1f}, p10={np.percentile(persist,10):.1f}, p90={np.percentile(persist,90):.1f}")
n_low_confidence = sum(1 for r in results if r["regime_prob"] < 0.7)
print(f"Low-confidence classifications (smoothed prob < 0.7): {n_low_confidence}/{len(results)}")

# Cross-tab vs VR tag
from collections import Counter
crosstab = Counter()
for r in results:
    hi = 0 if r["sigma0"] > r["sigma1"] else 1
    cur_label = "HIGH-VOL" if r["current_regime"] == hi else "low-vol"
    crosstab[(cur_label, r["vr_tag"])] += 1
print("\nHMM current-vol-regime x VR classifier tag:")
for k, v in sorted(crosstab.items()):
    print(f"  {k}: {v}")
