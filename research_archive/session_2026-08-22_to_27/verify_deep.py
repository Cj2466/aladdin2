import warnings; warnings.filterwarnings("ignore")
import yfinance as yf, pandas as pd, numpy as np

VOL = ["^VIX","^VXN","^SKEW","^MOVE","^VVIX","^OVX","^GVZ"]
ETF = ["SPY","IEF","HYG","TLT","LQD"]

raw = yf.download(VOL, start="1990-01-01", end="2026-08-27", auto_adjust=True, progress=False)
vol = raw["Close"].dropna(axis=1, how="all")
raw2 = yf.download(ETF, start="1990-01-01", end="2026-08-27", auto_adjust=True, progress=False)
etf = raw2["Close"].dropna(axis=1, how="all")

print("=== VOL INDEX starts ===")
for t in VOL:
    s = vol[t].dropna(); print(f"  {t:7s} {s.index[0].date()} -> {s.index[-1].date()}  n={len(s)}")
print("=== ETF starts ===")
for t in ETF:
    s = etf[t].dropna(); print(f"  {t:7s} {s.index[0].date()} -> {s.index[-1].date()}  n={len(s)}")

core6 = ["^VIX","^VXN","^SKEW","^MOVE","^VVIX","^OVX"]
c6 = vol[core6].dropna(how="any")
print(f"\nCOMMON (6, ex-GVZ): {c6.index[0].date()} -> {c6.index[-1].date()} n={len(c6)}")
c7 = vol[VOL].dropna(how="any")
print(f"COMMON (7, inc-GVZ): {c7.index[0].date()} -> {c7.index[-1].date()} n={len(c7)}")

# first formation date = 252 trading days after the 6-index common start
print(f"252-td warmup from 6-index common start -> first formation ~ {c6.index[252].date()}")
print(f"252-td warmup from 7-index common start -> first formation ~ {c7.index[252].date()}")

# --- cross-index correlation of DAILY LOG CHANGES (scout claimed 0.34-0.42) ---
dl = np.log(vol[VOL]).diff().dropna(how="any")
print(f"\n=== corr of daily log changes, common window n={len(dl)} ({dl.index[0].date()}..{dl.index[-1].date()}) ===")
print(dl.corr().round(3).to_string())

# --- is MOVE/VIX just realized vol? scout claimed corr = -0.40 ---
spy_ret = np.log(etf["SPY"]).diff()
rv21 = spy_ret.rolling(21).std() * np.sqrt(252) * 100.0   # trailing realized vol, annualized %, VIX units
ratio = np.log(vol["^MOVE"] / vol["^VIX"])
j = pd.concat([ratio.rename("logMOVEVIX"), rv21.rename("rv21")], axis=1).dropna()
print(f"\ncorr(log(MOVE/VIX), trailing 21d realized SPY vol) = {j['logMOVEVIX'].corr(j['rv21']):+.3f}  n={len(j)}")
j2 = pd.concat([(vol["^MOVE"]/vol["^VIX"]).rename("r"), rv21.rename("rv")], axis=1).dropna()
print(f"corr(MOVE/VIX level,               same)             = {j2['r'].corr(j2['rv']):+.3f}  n={len(j2)}")
# VIX itself vs realized vol, for contrast
j3 = pd.concat([vol["^VIX"].rename("v"), rv21.rename("rv")], axis=1).dropna()
print(f"corr(VIX level,                    same)             = {j3['v'].corr(j3['rv']):+.3f}  n={len(j3)}  <- contrast")
