import warnings; warnings.filterwarnings("ignore")
import yfinance as yf, pandas as pd, numpy as np
G10 = ["EURUSD=X","GBPUSD=X","USDJPY=X","AUDUSD=X","USDCHF=X","USDCAD=X","NZDUSD=X","USDSEK=X","USDNOK=X"]
d = yf.download(G10, start="2005-01-01", end="2026-08-26", auto_adjust=False, progress=False, group_by="column")["Close"].dropna()
print("common panel:", d.index[0].date(), d.index[-1].date(), len(d), "cols", len(d.columns))
# express all as USD-per-FCU (invert USDXXX quotes) so a long = long foreign ccy
fcu = pd.DataFrame(index=d.index)
for p in G10:
    fcu[p] = d[p] if p.startswith(("EUR","GBP","AUD","NZD")) else 1.0/d[p]
r = np.log(fcu).diff().dropna()
# rank momentum turnover at several holds, top/bottom 3 of 9
for lb in [63,126,252]:
    for hold in [21,63,126]:
        sig = np.log(fcu).diff(lb)
        dates = r.index[::hold]
        w_prev=None; tos=[]
        for t in dates:
            s = sig.loc[t].dropna()
            if len(s)<6: continue
            rk = s.rank()
            w = pd.Series(0.0, index=s.index)
            k=3
            w[rk.nlargest(k).index]=1/(2*k); w[rk.nsmallest(k).index]=-1/(2*k)
            if w_prev is not None:
                tos.append(float((w-w_prev.reindex(w.index).fillna(0)).abs().sum()))
            w_prev=w
        avg_to=np.mean(tos); reb_per_yr=252/hold
        print(f"lb={lb:3d} hold={hold:3d}: avg_turnover/rebal={avg_to:.3f} rebals/yr={reb_per_yr:.1f} ann_gross_traded={avg_to*reb_per_yr:.2f}x")
# strategy vol at each hold (for cost-vs-Sharpe math)
print()
for hold in [21,63,126]:
    sig = np.log(fcu).diff(126)
    w_ts = pd.DataFrame(0.0,index=r.index,columns=fcu.columns)
    cur=None
    for i,t in enumerate(r.index):
        if i % hold==0:
            s=sig.loc[t].dropna()
            if len(s)>=6:
                rk=s.rank(); cur=pd.Series(0.0,index=fcu.columns)
                cur[rk.nlargest(3).index]=1/6; cur[rk.nsmallest(3).index]=-1/6
        if cur is not None: w_ts.loc[t]=cur
    pnl=(w_ts.shift(1)*r).sum(axis=1).dropna()
    print(f"hold={hold}: ann_vol_of_strategy={pnl.std()*np.sqrt(252):.4f}")
