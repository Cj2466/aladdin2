import sys
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
sys.path.insert(0, "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad")
import numpy as np
import pandas as pd
from scipy.stats import linregress
from statsmodels.tsa.stattools import adfuller, coint
from fracdiff_lib import frac_diff_ffd

prices = pd.read_pickle("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/prices_3y.pkl")

# Genuinely cointegrated pairs found earlier at the 750-day window
pairs = [("COF", "WFC"), ("EXR", "VMRK"), ("HBAN", "SYF"), ("CPT", "VMRK"), ("ITW", "PH")]

D_GRID = np.round(np.arange(0.0, 1.05, 0.05), 2)

for a_t, b_t in pairs:
    a = np.log(prices[a_t].dropna().to_numpy())
    b = np.log(prices[b_t].dropna().to_numpy())
    n = min(len(a), len(b))
    a, b = a[-n:], b[-n:]
    slope, intercept, r, p, se = linregress(a, b)
    spread = b - slope * a

    adf_stat, adf_p, *_ = adfuller(spread, autolag="aic")
    print(f"{a_t}-{b_t}: hedge_ratio={slope:.3f}, spread ADF p-value (NO differencing) = {adf_p:.4f}")

    # AR(1) coefficient of the raw spread -- its own persistence/memory
    b_coef, a_coef, r2, p2, se2 = linregress(spread[:-1], spread[1:])
    print(f"    spread AR(1) coefficient (memory/persistence) = {b_coef:.3f}  (this IS the mean-reversion edge)")

    # Minimum d needed for the spread itself
    d_star = None
    for d in D_GRID:
        fd = frac_diff_ffd(spread, d, threshold=1e-4)
        fd = fd[~np.isnan(fd)]
        if len(fd) < 30:
            continue
        stat, pv, *_ = adfuller(fd, autolag="aic")
        if pv <= 0.05:
            d_star = d
            break
    print(f"    minimum d for FFD-stationarity of the spread = {d_star}")
    print()
