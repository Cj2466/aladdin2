import warnings,json; warnings.filterwarnings("ignore")
import yfinance as yf, pandas as pd
DEAD=["LUNA1-USD","LUNC-USD","FTT-USD","UST-USD","CEL-USD","SRM-USD","WAVES-USD","ANC-USD"]
d=yf.download(DEAD,start="2019-01-01",end="2026-08-26",auto_adjust=False,progress=False)
cl=d["Close"] if "Close" in d else d
for t in DEAD:
    if t in cl:
        s=cl[t].dropna()
        print(f"{t:12s} n={len(s):5d} {s.index[0].date() if len(s) else '-'} -> {s.index[-1].date() if len(s) else '-'}")
    else: print(f"{t:12s} MISSING")
