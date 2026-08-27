import warnings; warnings.filterwarnings("ignore")
import time
import yfinance as yf, pandas as pd

CAND = ["^VIX3M","^VXV","^VIX6M","^VXMT","^VXD","^DJX","^VXN","^RVX","^VXEEM","^VXEFA","^VXTLT","^TYVIX","^EVZ","^VIX9D","^VIX1D"]
print("=== retry x2, period=10y and full ===")
for t in CAND:
    best = None
    for attempt in range(2):
        try:
            h = yf.Ticker(t).history(period="max", auto_adjust=True)
            if h is not None and not h.empty:
                s = h["Close"].dropna()
                if best is None or len(s) > best[2]:
                    best = (s.index[0].date(), s.index[-1].date(), len(s))
        except Exception as e:
            pass
        time.sleep(0.3)
    if best is None:
        print(f"{t:9s} EMPTY/UNRESOLVED")
    else:
        print(f"{t:9s} first={best[0]} last={best[1]} n={best[2]}")
