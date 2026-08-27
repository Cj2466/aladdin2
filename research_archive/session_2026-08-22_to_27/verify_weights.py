import sys
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a327c9fd73bf9f348/backend")

import pandas as pd
import numpy as np
from app.services.research_lab.cross_sectional import (
    _apply_weight_cap,
    _resolve_leg_weights,
    MAX_WEIGHT_MULTIPLE,
)

print("MAX_WEIGHT_MULTIPLE =", MAX_WEIGHT_MULTIPLE)

print("\n=== Sum-to-1.0 check, various leg sizes/skews ===")
import random
random.seed(42)
worst_err = 0.0
for trial in range(2000):
    n = random.randint(2, 12)
    tickers = [f"T{i}" for i in range(n)]
    # random skew, including extreme outliers (to trigger the cap+redistribute loop)
    raw = {t: random.choice([
        random.uniform(1, 10),
        random.uniform(1000, 1_000_000),   # occasional mega-cap outlier
        random.uniform(0.0001, 0.01),
    ]) for t in tickers}
    weights = _apply_weight_cap(raw)
    s = sum(weights.values())
    worst_err = max(worst_err, abs(s - 1.0))
    if abs(s - 1.0) > 1e-9:
        print(f"TRIAL {trial} FAILED: sum={s}, raw={raw}")
        break
    # cap check (allow tiny fp slack)
    equal_share = 1.0 / n
    cap = MAX_WEIGHT_MULTIPLE * equal_share
    for t, w in weights.items():
        if w > cap + 1e-9:
            print(f"TRIAL {trial}: CAP VIOLATION t={t} w={w} cap={cap}")
else:
    print(f"All 2000 random trials: sum==1.0 (worst abs error {worst_err:.2e}), no cap violations.")

print("\n=== _resolve_leg_weights: value-weighting mega-cap outlier gets capped, sums to 1.0 ===")
tickers = ["MEGA", "B", "C", "D", "E"]
signal = pd.Series([5, 4, 3, 2, 1], index=tickers, dtype=float)  # arbitrary, unused when leg_weighting=value and caps usable
market_cap = pd.Series([1_000_000_000.0, 10_000.0, 10_000.0, 10_000.0, 10_000.0], index=tickers)
weights, fallback = _resolve_leg_weights(tickers, signal, higher_is_stronger=True, leg_weighting="value", market_cap=market_cap)
print("weights:", weights, "fallback:", fallback, "sum:", sum(weights.values()))
assert not fallback
assert abs(sum(weights.values()) - 1.0) < 1e-9
equal_share = 1/5
cap = MAX_WEIGHT_MULTIPLE * equal_share
assert weights["MEGA"] <= cap + 1e-9
print(f"MEGA capped at {weights['MEGA']:.4f} <= cap {cap:.4f}. Others got redistributed excess. Sum=1.0 confirmed.")

print("\n=== _resolve_leg_weights: whole-leg fallback when ONE member's market cap is missing ===")
market_cap_gap = pd.Series([1e9, 1e6, np.nan, 1e6, 1e6], index=tickers)
weights2, fallback2 = _resolve_leg_weights(tickers, signal, higher_is_stronger=True, leg_weighting="value", market_cap=market_cap_gap)
print("weights2:", weights2, "fallback2:", fallback2, "sum:", sum(weights2.values()))
assert fallback2 is True
assert abs(sum(weights2.values()) - 1.0) < 1e-9
print("Confirmed: single missing market cap -> WHOLE leg falls back to magnitude weighting (not partial). Sum still 1.0.")

print("\n=== _resolve_leg_weights: non-positive (zero/negative) market cap also triggers fallback ===")
market_cap_zero = pd.Series([1e9, 1e6, 0.0, 1e6, 1e6], index=tickers)
weights3, fallback3 = _resolve_leg_weights(tickers, signal, higher_is_stronger=True, leg_weighting="value", market_cap=market_cap_zero)
assert fallback3 is True
print("Confirmed: zero market cap -> fallback triggers. fallback3:", fallback3)

market_cap_neg = pd.Series([1e9, 1e6, -5.0, 1e6, 1e6], index=tickers)
weights4, fallback4 = _resolve_leg_weights(tickers, signal, higher_is_stronger=True, leg_weighting="value", market_cap=market_cap_neg)
assert fallback4 is True
print("Confirmed: negative market cap -> fallback triggers. fallback4:", fallback4)

print("\nALL WEIGHT-SUM / FALLBACK CHECKS PASSED.")
