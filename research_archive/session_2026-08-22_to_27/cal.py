import warnings,json; warnings.filterwarnings("ignore")
import yfinance as yf, pandas as pd, numpy as np
# 1) does crypto index include weekends / all calendar days?
b=yf.download("BTC-USD",start="2024-01-01",end="2024-02-01",auto_adjust=True,progress=False)
idx=b.index
print("BTC Jan2024 rows:",len(idx),"expected cal days:31")
print("weekday counts:",pd.Series(idx.dayofweek).value_counts().sort_index().to_dict())
print("has Sat/Sun:",bool(set(idx.dayofweek)&{5,6}))
print("tz:",idx.tz,"dtype",idx.dtype)
# 2) mixed crypto+equity download -> union index NaN behaviour
m=yf.download(["BTC-USD","SPY"],start="2024-01-01",end="2024-02-01",auto_adjust=True,progress=False)["Close"]
print("\nMIXED rows:",len(m))
print("SPY NaN rows:",int(m["SPY"].isna().sum()),"BTC NaN rows:",int(m["BTC-USD"].isna().sum()))
print(m.head(8).to_string())
# 3) rows per year for a crypto ticker (365 vs 252)
f=yf.download("BTC-USD",start="2019-01-01",end="2026-01-01",auto_adjust=True,progress=False)
print("\nrows/yr BTC:",f.groupby(f.index.year).size().to_dict())
s=yf.download("SPY",start="2019-01-01",end="2026-01-01",auto_adjust=True,progress=False)
print("rows/yr SPY:",s.groupby(s.index.year).size().to_dict())
