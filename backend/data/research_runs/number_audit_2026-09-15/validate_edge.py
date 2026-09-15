"""Gold-standard validation of the EDGE spread estimator against synthetic data
with a KNOWN true spread (CLAUDE.md: never trust a published formula on real data
until it reproduces a known answer on simulated data).

Model (the one EDGE is derived under -- Ardia, Guidotti & Kroencke, JFE 2024):
  efficient log price   m_t  = m_{t-1} + sigma * z_t        (random walk)
  observed trade price  p_t  = m_t + (S/2) * q_t            q_t = +/-1 w.p. 1/2
Daily OPEN/HIGH/LOW/CLOSE are taken from the observed trade prices of that day.
True effective spread = S (in log units) -> report in basis points.
"""
import numpy as np, pandas as pd
from bidask import edge

rng = np.random.default_rng(20260915)

def simulate(true_spread_bp, n_days=500, trades_per_day=390, daily_vol_bp=150.0):
    S = true_spread_bp / 1e4
    sig = (daily_vol_bp / 1e4) / np.sqrt(trades_per_day)
    n = n_days * trades_per_day
    m = np.cumsum(rng.normal(0.0, sig, n))
    q = rng.choice([-1.0, 1.0], n)
    p = np.exp(m + (S / 2.0) * q)
    p = p.reshape(n_days, trades_per_day)
    return pd.DataFrame({
        "open":  p[:, 0],
        "high":  p.max(axis=1),
        "low":   p.min(axis=1),
        "close": p[:, -1],
    })

print(f"{'true bp':>9} | {'sign=False':>11} {'err':>8} | {'sign=True':>11} {'err':>8}")
print("-" * 58)
for true_bp in (1.0, 2.0, 5.0, 10.0, 25.0, 50.0, 100.0, 200.0, 500.0):
    outs = {}
    for sign in (False, True):
        ests = []
        for _ in range(12):
            df = simulate(true_bp)
            v = edge(df["open"], df["high"], df["low"], df["close"], sign=sign)
            ests.append(float(v) * 1e4)
        outs[sign] = float(np.nanmean(ests))
    a, b = outs[False], outs[True]
    print(f"{true_bp:9.1f} | {a:11.2f} {a-true_bp:+8.2f} | {b:11.2f} {b-true_bp:+8.2f}")

print()
print("=== ZERO-spread control: what does the estimator return when the truth is 0? ===")
for vol in (50.0, 150.0, 400.0):
    for sign in (False, True):
        ests = []
        for _ in range(12):
            df = simulate(0.0, daily_vol_bp=vol)
            ests.append(float(edge(df["open"], df["high"], df["low"], df["close"], sign=sign)) * 1e4)
        arr = np.array(ests, dtype=float)
        print(f"  daily vol {vol:5.0f}bp  sign={str(sign):5s}  mean {np.nanmean(arr):+8.2f} bp"
              f"   |mean| {np.nanmean(np.abs(arr)):7.2f} bp   sd {np.nanstd(arr):6.2f}")
