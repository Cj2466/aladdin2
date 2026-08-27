"""Candidate commodity ETF basket: common history, liquidity, empirical Corwin-Schultz spread."""
import warnings

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")
pd.set_option("display.width", 260)

# distinct exposures only (no GLD/IAU/SGOL duplicates)
UNIV = ["GLD", "SLV", "PPLT", "PALL", "CPER", "USO", "BNO", "UNG", "UGA",
        "CORN", "WEAT", "SOYB", "CANE", "DBA", "DBB", "DBE", "DBO", "DBC", "GSG", "USCI"]
raw = yf.download(UNIV, start="2005-01-01", end="2026-08-26", auto_adjust=False,
                  progress=False, threads=True)
hi, lo, cl, adj, vol = raw["High"], raw["Low"], raw["Close"], raw["Adj Close"], raw["Volume"]


def corwin_schultz(h, l):
    h, l = h.dropna(), l.dropna()
    idx = h.index.intersection(l.index)
    h, l = h.reindex(idx), l.reindex(idx)
    beta = (np.log(h / l) ** 2).rolling(2).sum()
    h2 = h.rolling(2).max()
    l2 = l.rolling(2).min()
    gamma = np.log(h2 / l2) ** 2
    k = 3 - 2 * np.sqrt(2)
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
    s = 2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))
    return s.clip(lower=0).dropna()


rows = []
for t in UNIV:
    a = adj[t].dropna()
    if len(a) < 100:
        continue
    v = vol[t].reindex(a.index)
    dv = (v * cl[t].reindex(a.index)).tail(750).median()
    s = corwin_schultz(hi[t], lo[t])
    rows.append({
        "ticker": t, "start": str(a.index[0].date()), "end": str(a.index[-1].date()),
        "yrs": round((a.index[-1] - a.index[0]).days / 365.25, 1),
        "adv_$M": round(float(dv) / 1e6, 2),
        "cs_spread_bp_med_5y": round(float(s.tail(1250).median()) * 1e4, 1),
        "cs_spread_bp_med_all": round(float(s.median()) * 1e4, 1),
        "ann_vol": round(float(np.log(a).diff().std() * np.sqrt(252)), 3),
    })
df = pd.DataFrame(rows).sort_values("start")
print(df.to_string())

for start in ["2007-01-08", "2010-06-10", "2011-11-16"]:
    sub = df[df["start"] <= start]
    print(f"\ncommon start {start}: n={len(sub)} -> {list(sub['ticker'])}")

print("\n=== pairwise corr of monthly returns, 2012+ (distinctness) ===")
m = adj.resample("ME").last().pct_change().loc["2012":]
core = [t for t in ["GLD", "SLV", "PPLT", "PALL", "CPER", "USO", "BNO", "UNG", "UGA",
                    "CORN", "WEAT", "SOYB", "CANE", "DBB", "DBA"] if t in m.columns]
c = m[core].corr()
print(c.round(2).to_string())
iu = np.triu_indices(len(core), 1)
print("median |corr|:", round(float(np.median(np.abs(c.values[iu]))), 3),
      " max:", round(float(np.max(c.values[iu])), 3))
