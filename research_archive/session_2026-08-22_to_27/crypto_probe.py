import warnings, json, sys
warnings.filterwarnings("ignore")
import yfinance as yf
import pandas as pd, numpy as np

TICKERS = ["BTC-USD","ETH-USD","XRP-USD","BNB-USD","SOL-USD","ADA-USD","DOGE-USD",
           "AVAX-USD","DOT-USD","LINK-USD","LTC-USD","BCH-USD","MATIC-USD","TRX-USD",
           "XLM-USD","ATOM-USD","ETC-USD","XMR-USD","UNI7083-USD","UNI-USD","NEAR-USD",
           "ALGO-USD","FIL-USD","AAVE-USD","APT21794-USD","ARB11841-USD","OP-USD",
           "USDT-USD","USDC-USD","SHIB-USD","HBAR-USD","VET-USD","ICP-USD","INJ-USD",
           "SUI20947-USD","TON11419-USD","IMX10603-USD","RNDR-USD","GRT6719-USD","MKR-USD"]

df = yf.download(TICKERS, start="2010-01-01", end="2026-08-26", interval="1d",
                 auto_adjust=False, progress=False, group_by="column", threads=True)
print("SHAPE", df.shape)
print("INDEX_TYPE", type(df.index), df.index.tz)
close = df["Close"]
vol = df["Volume"]
rows=[]
for t in TICKERS:
    if t not in close.columns:
        rows.append({"t":t,"status":"MISSING"}); continue
    s = close[t].dropna()
    if len(s)==0:
        rows.append({"t":t,"status":"EMPTY"}); continue
    v = vol[t].reindex(s.index)
    # first date with 60 consecutive non-nan and nonzero volume
    rows.append({
      "t":t,"status":"OK","first":str(s.index[0].date()),"last":str(s.index[-1].date()),
      "n":int(len(s)),
      "span_days":int((s.index[-1]-s.index[0]).days),
      "gaps": int((s.index.to_series().diff().dt.days.fillna(1)>1).sum()),
      "max_gap": int(s.index.to_series().diff().dt.days.max() if len(s)>1 else 0),
      "zero_vol_days": int((v.fillna(0)==0).sum()),
      "med_dollar_vol_1y": float(np.nanmedian((v*close[t]).dropna().tail(365))) if v.notna().sum()>0 else None,
      "dupe_close_runs": int((s.diff()==0).sum()),
    })
print(json.dumps(rows, indent=1))
