"""Credit as a monthly de-risking filter (low turnover -> cost-safe).
Benchmarked against IDENTICALLY-SHAPED filters built from data every retail
quant already has (VIX, SPY 200d momentum). If credit doesn't beat those,
the 'multi-asset data advantage' is not real."""
import pandas as pd, numpy as np
P="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/close.pkl"
c=pd.read_pickle(P).sort_index(); r=np.log(c).diff()
d=pd.concat([r.HYG,r.IEF],axis=1).dropna()
b=d.HYG.rolling(252).cov(d.IEF)/d.IEF.rolling(252).var()
cx=(d.HYG-b.shift(1)*d.IEF).dropna()
spy=r.SPY; COST=0.0002
sig={ "CREDIT 21d exc>0" : cx.rolling(21).sum()>0,
      "CREDIT 63d exc>0" : cx.rolling(63).sum()>0,
      "VIX<median(252d)" : np.log(c["^VIX"])<np.log(c["^VIX"]).rolling(252).median(),
      "SPY>200d MA"      : c.SPY>c.SPY.rolling(200).mean(),
      "SPY 63d mom>0"    : spy.rolling(63).sum()>0 }
me=pd.Series(c.index,index=c.index).groupby([c.index.year,c.index.month]).transform("max")==c.index
for nm,s in sig.items():
    w=s.astype(float).where(me).ffill().shift(1)          # decide at month-end, hold 1m
    x=pd.concat([w.rename("w"),spy.rename("r")],axis=1).dropna()
    x=x.loc["2010-01-01":]
    to=x.w.diff().abs().fillna(0); net=x.w*x.r-to*COST
    dd=(net.cumsum()-net.cumsum().cummax()).min()
    print(f"{nm:20s} Sharpe={net.mean()/net.std()*np.sqrt(252):6.3f} "
          f"CAGR={net.mean()*252:6.3f} maxDD={dd:6.3f} inMkt={x.w.mean():4.2f} "
          f"trades/yr={to.sum()/(len(x)/252):4.1f}")
bh=spy.loc["2010-01-01":]
ddb=(bh.cumsum()-bh.cumsum().cummax()).min()
print(f"{'buy&hold SPY':20s} Sharpe={bh.mean()/bh.std()*np.sqrt(252):6.3f} "
      f"CAGR={bh.mean()*252:6.3f} maxDD={ddb:6.3f}")
