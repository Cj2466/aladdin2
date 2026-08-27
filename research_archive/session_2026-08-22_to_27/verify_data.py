import yfinance as yf, pandas as pd, numpy as np
from datetime import date
U=('SHY','IEI','IEF','TLH','TLT','TIP','LQD','HYG')
end=date(2026,8,27)
raw=yf.download(list(U),start=date(2007,1,1),end=end,auto_adjust=False,progress=False)
tr=raw['Adj Close'].dropna(axis=1,how='all').dropna(axis=0,how='all')
px=raw['Close'].reindex(index=tr.index,columns=tr.columns)
common=tr.dropna()
print("common clean rows:",len(common),"first",common.index[0].date(),"last",common.index[-1].date())
# auto_adjust=True equivalence
raw2=yf.download(list(U),start=date(2007,1,1),end=end,auto_adjust=True,progress=False)
c2=raw2['Close'].reindex(index=tr.index,columns=tr.columns)
print("max |AdjClose - auto_adjust=True Close| =", float(np.nanmax(np.abs(tr-c2))))
# CAGRs on both bases over common window
yrs=(common.index[-1]-common.index[0]).days/365.25
for t in U:
    a=common[t]; p=px[t].reindex(common.index)
    print(f"{t}: TR CAGR {((a.iloc[-1]/a.iloc[0])**(1/yrs)-1)*100:+.2f}%  PX CAGR {((p.iloc[-1]/p.iloc[0])**(1/yrs)-1)*100:+.2f}%")
r=common.pct_change().dropna()
print("corr(HYG,TLT) =", round(float(r['HYG'].corr(r['TLT'])),4))
print("ann vols:", {t: round(float(r[t].std()*np.sqrt(252)*100),2) for t in ('SHY','IEI','IEF','TLH','TLT')})
