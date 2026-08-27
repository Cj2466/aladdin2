import sys, datetime as dt, numpy as np, pandas as pd
sys.path.insert(0,"/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a327c9fd73bf9f348/backend")
from app.services.market_data.yfinance_provider import YFinanceProvider
T=["AAPL","MSFT","XOM","JPM","PG","KO","T","IBM","GE","CVX","WMT","HD","MRK","PFE","CSCO","ORCL","INTC","BA","CAT","DIS","ETSY","TSLA","AAL","APA","NCLH","FTNT","ANET","ODFL","TER","JKHY"]
p=YFinanceProvider()
idx=pd.bdate_range("2015-09-01","2026-08-26")
cols={}
for t in T:
    s,_=p.get_shares_outstanding([t],dt.date(2005,1,1),dt.date(2026,8,26))
    if t in s:
        u=s[t].index.union(idx).sort_values()
        cols[t]=s[t].reindex(u).ffill().reindex(idx)
df=pd.DataFrame(cols,index=idx)
print("tickers with data:",df.shape[1])
LAG=63  # 3-month reporting lag in business days
for d in ["2017-01-03","2017-06-01","2019-06-03","2022-06-01","2026-06-01"]:
    d=pd.Timestamp(d)
    if d not in df.index: d=df.index[df.index<=d][-1]
    lagged=df.loc[:d].iloc[:-LAG] if LAG else df.loc[:d]
    if len(lagged)<253: print(d.date(),"insufficient"); continue
    cur=lagged.iloc[-1]; prv=lagged.iloc[-253]
    sig=np.log(cur/prv)
    v=sig.dropna()
    print(f"{d.date()}: n_valid={len(v)}/{df.shape[1]}  mean={v.mean():+.4f} sd={v.std():.4f} "
          f"p10={v.quantile(.1):+.4f} p90={v.quantile(.9):+.4f} n_exact_zero={(v==0).sum()}")
    print("   most shrinking:", list(v.nsmallest(3).round(4).items()), " most diluting:", list(v.nlargest(3).round(4).items()))
