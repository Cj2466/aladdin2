"""Verify FRED G10 3-month interbank panel access, REAL publication lag,
and the scout's 0.956 rank-correlation-at-6-months claim."""
import sys
from datetime import date

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_9fd00b72-30a-7/backend")

import numpy as np
import pandas as pd
from scipy import stats

from app.config import settings
from app.services.macro_data.fred_provider import FredProvider

print("FRED key configured:", bool(settings.fred_api_key), "len:", len(settings.fred_api_key))

CODES = {"EUR": "EZ", "GBP": "GB", "JPY": "JP", "AUD": "AU", "CHF": "CH",
         "CAD": "CA", "NZD": "NZ", "SEK": "SE", "NOK": "NO", "USD": "US"}

p = FredProvider()
series = {}
for ccy, cc in CODES.items():
    sid = f"IR3TIB01{cc}M156N"
    try:
        obs = p.get_observation_history(sid, "lin", date(2000, 1, 1), date(2026, 12, 31))
        s = pd.Series({o.observation_date: o.value for o in obs}).sort_index()
        series[ccy] = s
        print(f"{ccy} {sid:>18}: n={len(s):4d}  {s.index[0]} .. {s.index[-1]}  last={s.iloc[-1]:.4f}")
    except Exception as e:
        print(f"{ccy} {sid:>18}: FAILED {e}")

TODAY = date(2026, 8, 26)
print("\n=== REAL PUBLICATION LAG (today = %s) ===" % TODAY)
for ccy, s in series.items():
    last = s.index[-1]
    months = (TODAY.year - last.year) * 12 + (TODAY.month - last.month)
    print(f"  {ccy}: last observation {last}  -> {months} months stale")

print("\n=== Build the differential panel (foreign - USD), monthly ===")
df = pd.DataFrame({c: pd.Series({pd.Timestamp(k): v for k, v in s.items()}) for c, s in series.items()})
df = df.sort_index()
diff = df.drop(columns=["USD"]).sub(df["USD"], axis=0)
diff = diff.dropna(how="any")
print("differential panel:", diff.shape, diff.index[0].date(), "..", diff.index[-1].date())
print(diff.tail(3).round(3))

print("\n=== Cross-sectional rank correlation: diff_t vs diff_{t-k months} ===")
for k in (1, 3, 6, 7, 9, 12):
    cors = []
    for i in range(k, len(diff)):
        a = diff.iloc[i].values
        b = diff.iloc[i - k].values
        if np.all(np.isfinite(a)) and np.all(np.isfinite(b)):
            rho, _ = stats.spearmanr(a, b)
            if np.isfinite(rho):
                cors.append(rho)
    print(f"  lag {k:2d} months: mean cross-sectional Spearman = {np.mean(cors):.4f}  (n={len(cors)})")

print("\n=== Level check: is the differential economically meaningful? ===")
print(diff.describe().T[["mean", "std", "min", "max"]].round(3))
