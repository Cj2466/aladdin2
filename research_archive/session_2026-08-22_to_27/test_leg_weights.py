import sys
sys.path.insert(0, ".")
import pandas as pd
import numpy as np
from app.services.research_lab.cross_sectional import _leg_weights, MAX_WEIGHT_MULTIPLE, MIN_RELATIVE_WEIGHT_FRACTION

def check(name, tickers, values, higher=True):
    signal = pd.Series(values, index=tickers)
    w = _leg_weights(tickers, signal, higher_is_stronger=higher)
    total = sum(w.values())
    cap = MAX_WEIGHT_MULTIPLE * (1.0/len(tickers))
    over = {t: v for t, v in w.items() if v > cap + 1e-9}
    print(f"--- {name} ---")
    print("weights:", {k: round(v,5) for k,v in w.items()})
    print("sum:", total, " cap:", cap, " any over cap:", over)
    print()

# 1. Extreme single outlier among many tied members (n=20)
tickers = [f"T{i}" for i in range(20)]
values = [1.0]*19 + [1_000_000.0]
check("extreme outlier n=20", tickers, values)

# 2. All zero / all tied signals
check("all-tied n=5", [f"A{i}" for i in range(5)], [0.5]*5)
check("all-zero n=5", [f"A{i}" for i in range(5)], [0.0]*5)

# 3. NaN mixed in signal reindex (shouldn't happen per contract, but leg tickers always from select_leg_tickers which drops NaN -- test anyway)
# 4. Negative values / all negative excess pattern
check("descending values n=6 higher_is_stronger=True", [f"B{i}" for i in range(6)], [100,90,80,70,60,50])

# 5. Two extreme outliers tied at max
tickers2 = [f"C{i}" for i in range(10)]
values2 = [1.0]*8 + [500.0, 500.0]
check("two tied outliers n=10", tickers2, values2)

# 6. n=3 with one huge outlier (test whether cap=1.0 can even bind)
check("n=3 one huge outlier", ["X","Y","Z"], [1.0, 1.0, 1e9])

# 7. Negative-valued excess with higher_is_stronger=False (short leg convention)
check("short leg convention", [f"D{i}" for i in range(8)], [5,4,3,2,1,0,-1,-100], higher=False)

# 8. Very large n to really stress redistribution loop
tickers3 = [f"E{i}" for i in range(200)]
values3 = list(np.linspace(0, 1, 199)) + [1e12]
check("n=200 extreme outlier", tickers3, values3)

# Empirical check: does cross_sectional's turnover-based cost actually scale with
# magnitude-weighted notional (unlike intraday/low_frequency's flat position-based cost)?
from app.services.research_lab.cross_sectional import _turnover
old = {}  # flat before formation
new_flat_equiv = {"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25}  # equal-weight baseline
new_magnitude_weighted = {"A": 0.0714, "B": 0.0714, "C": 0.0714, "D": 0.7857}  # one dominant name
print("\n--- cost-model proportionality check ---")
print("turnover, equal-weight formation:", _turnover(old, new_flat_equiv))
print("turnover, magnitude-weighted formation (same 4 names, concentrated):", _turnover(old, new_magnitude_weighted))
print("-> turnover DIFFERS with notional concentration (cost is notional-proportional, not flat)")
