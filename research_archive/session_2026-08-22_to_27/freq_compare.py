"""Performance-blind trade-frequency comparison: new 28-pattern low-frequency
family vs the committed 212-pattern intraday family, on the SAME 15-minute
bars. Positions are simulated from fire sequences alone (apply_pattern_signal_
rule semantics) — returns are never touched, so this cannot leak performance
into pattern selection.

Sample tickers: pre-specified rule, every 30th ticker of the alphabetically
sorted 284-ticker cache (no cherry-picking). The 212-family baseline uses the
last ~252 trading days of bars on the first/middle/last of those sample
tickers (fire_fns are expensive per-window calls; frequency-per-year is
scale-invariant to the sampled span).
"""

import glob
import os
import pickle
import sys
import time

import numpy as np

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a2520e5862565ddbf/backend")

import app.services.research_lab.intraday_patterns as ip
import app.services.research_lab.low_frequency_patterns as lf

CACHE = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/bars_cache"

all_tickers = sorted(
    os.path.basename(p).replace("_15Min.pkl", "") for p in glob.glob(f"{CACHE}/*_15Min.pkl")
)
sample = all_tickers[::30]
print(f"sample tickers ({len(sample)}): {sample}", flush=True)


def load(ticker):
    with open(f"{CACHE}/{ticker}_15Min.pkl", "rb") as f:
        return pickle.load(f)


# --- New family: exact simulated frequencies on the full history ----------
print("\n== NEW 28-pattern family (full history, all sample tickers) ==", flush=True)
new_rates = {}  # pattern_id -> list of per-ticker trades/yr
for ticker in sample:
    raw = lf.build_lowfreq_raw_data(load(ticker))
    for p in lf.LOW_FREQUENCY_PATTERN_FAMILY:
        new_rates.setdefault(p.pattern_id, []).append(lf.estimate_trades_per_ticker_year(raw, p))

new_means = {pid: float(np.mean(v)) for pid, v in new_rates.items()}
for pid, m in sorted(new_means.items(), key=lambda kv: -kv[1]):
    print(f"  {pid:45s} mean {m:6.1f}/yr  (min {min(new_rates[pid]):5.1f}, max {max(new_rates[pid]):5.1f})", flush=True)

# --- Old 212 family: simulated frequencies on last ~1y of bars, 3 tickers -
BASELINE_TICKERS = [sample[0], sample[len(sample) // 2], sample[-1]]
BARS_PER_YEAR = 26 * 252
print(f"\n== OLD 212-pattern family baseline (last ~1y of bars, {BASELINE_TICKERS}) ==", flush=True)

old_rates = {p.pattern_id: [] for p in ip.PATTERN_FAMILY}
for ticker in BASELINE_TICKERS:
    bars = load(ticker).iloc[-BARS_PER_YEAR:]
    raw = ip.build_pattern_raw_data(bars)
    n = len(raw)
    n_days = raw["trading_date"].nunique()
    years = n_days / 252.0
    fire_dirs = {p.pattern_id: np.zeros(n, dtype=np.int8) for p in ip.PATTERN_FAMILY}
    t0 = time.time()
    for t in range(ip.INTRADAY_FIT_WINDOW_BARS, n):
        window = raw.iloc[t - ip.INTRADAY_FIT_WINDOW_BARS : t]
        for p in ip.PATTERN_FAMILY:
            sig = p.fire_fn(window)
            if sig is not None:
                fire_dirs[p.pattern_id][t] = 1 if sig.direction == "long" else -1
    print(f"  {ticker}: fire pass {time.time()-t0:.0f}s over {n} bars / {n_days} days", flush=True)
    for pid, dirs in fire_dirs.items():
        old_rates[pid].append(lf.simulate_round_trips(dirs) / years)

old_means = {pid: float(np.mean(v)) for pid, v in old_rates.items()}

new_vals = np.array(list(new_means.values()))
old_vals = np.array(list(old_means.values()))
print("\n== SUMMARY ==", flush=True)
print(f"new family (n={len(new_vals)}): mean {new_vals.mean():.1f}, median {np.median(new_vals):.1f}, max {new_vals.max():.1f} trades/ticker-yr")
print(f"old family (n={len(old_vals)}): mean {old_vals.mean():.1f}, median {np.median(old_vals):.1f}, max {old_vals.max():.1f} trades/ticker-yr")
print(f"mean reduction factor: {old_vals.mean() / max(new_vals.mean(), 1e-9):.1f}x")
print(f"old-family patterns above 50/yr: {(old_vals > 50).sum()}/{len(old_vals)}; above 200/yr: {(old_vals > 200).sum()}")
print("old-family top 10 by frequency:")
for pid, m in sorted(old_means.items(), key=lambda kv: -kv[1])[:10]:
    print(f"  {pid:55s} {m:8.1f}/yr")
print("old-family bottom 5 by frequency:")
for pid, m in sorted(old_means.items(), key=lambda kv: kv[1])[:5]:
    print(f"  {pid:55s} {m:8.1f}/yr")

with open(os.path.join(os.path.dirname(__file__), "freq_compare_results.pkl"), "wb") as f:
    pickle.dump({"new": new_rates, "old": old_rates, "sample": sample, "baseline": BASELINE_TICKERS}, f)
print("\nsaved freq_compare_results.pkl", flush=True)
