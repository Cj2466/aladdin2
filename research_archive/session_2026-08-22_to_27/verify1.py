import yfinance as yf, pandas as pd, numpy as np
pd.set_option('display.width', 200)
SCRATCH = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
TK = ["^VIX","^SKEW","^MOVE","^VXD","^VIX3M","^OVX","^VVIX","^GVZ","^VIX6M","^VIX9D","^VIX1D","SPY","IEF","TLT","AGG"]
raw = yf.download(TK, start="1985-01-01", end="2026-08-27", auto_adjust=True, progress=False, group_by="column")
close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
print("=== per-ticker first/last/count ===")
for t in TK:
    if t not in close.columns:
        print(f"{t:9s} MISSING"); continue
    s = close[t].dropna()
    if s.empty:
        print(f"{t:9s} EMPTY"); continue
    print(f"{t:9s} {s.index[0].date()} -> {s.index[-1].date()}  n={len(s)}")
close.to_pickle(f"{SCRATCH}/close.pkl")
