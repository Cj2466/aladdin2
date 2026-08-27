import warnings; warnings.filterwarnings("ignore")
import yfinance as yf, pandas as pd, numpy as np

VOL = ["^VIX","^VXN","^SKEW","^MOVE","^VVIX","^OVX","^GVZ"]
ETF = ["SPY","IEF","HYG"]
vol = yf.download(VOL, start="2007-01-01", end="2026-08-27", auto_adjust=True, progress=False)["Close"]
etf = yf.download(ETF, start="2007-01-01", end="2026-08-27", auto_adjust=True, progress=False)["Close"]
etf = etf.dropna(how="any")
print("ETF calendar:", etf.index[0].date(), "->", etf.index[-1].date(), "n=", len(etf))

for t in VOL:
    s = vol[t].dropna()
    s = s[s.index >= etf.index[0]]
    on_etf_cal = s.index.intersection(etf.index)
    extra = s.index.difference(etf.index)
    # how many ETF trading days (after this index starts) have NO print for it
    etf_days = etf.index[etf.index >= s.index[0]]
    missing = etf_days.difference(s.index)
    print(f"{t:7s} start={s.index[0].date()} prints_on_etf_days={len(on_etf_cal)} "
          f"prints_NOT_on_etf_cal={len(extra)} etf_days_missing_this_index={len(missing)} "
          f"({100*len(missing)/max(len(etf_days),1):.2f}%)")

# max consecutive gap on the ETF calendar for each index (post-start)
print("\nmax consecutive ETF-day gap per index:")
for t in VOL:
    s = vol[t].dropna()
    etf_days = etf.index[etf.index >= s.index[0]]
    present = etf_days.isin(s.index)
    run = mx = 0
    for p in present:
        run = 0 if p else run + 1
        mx = max(mx, run)
    print(f"  {t:7s} {mx}")
