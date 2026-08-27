import warnings; warnings.filterwarnings("ignore")
import yfinance as yf, pandas as pd
# The 9 claimed known-recycled tickers: does any resolve a price?
T=["ARNC","DNB","DO","FI","LLL","MNK","MON","PX","WRK"]
px=yf.download(T,start="2018-01-02",end="2026-08-27",auto_adjust=False,progress=False)
close=px["Close"]
for t in T:
    s=close[t].dropna() if t in close.columns else pd.Series(dtype=float)
    print(f"{t:6s} n_price={len(s):5d} first={s.index[0].date() if len(s) else None} last={s.index[-1].date() if len(s) else None}")
# also raw (no dedup) share row counts for DFS/CMA/SRCL
print("--- raw share rows, no dedup ---")
for t in ["DFS","CMA","SRCL"]:
    sh=yf.Ticker(t).get_shares_full(start="2013-12-01",end="2026-08-27")
    print(t,"raw",len(sh) if sh is not None else 0,"dedup",len(sh[~sh.index.duplicated(keep='last')]) if sh is not None and len(sh) else 0)
