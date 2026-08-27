"""Economic test. Expanding-window OOS vol forecast -> vol-targeted SPY.
Marginal value of CREDIT = Sharpe(base+vix+cred) - Sharpe(base+vix).
Costs: 2bp round-trip on |turnover| (SPY: ~0.5-1bp spread, $0 commission). """
import pandas as pd, numpy as np, statsmodels.api as sm
P="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/close.pkl"
c=pd.read_pickle(P).sort_index(); r=np.log(c).diff()
d=pd.concat([r.HYG,r.IEF],axis=1).dropna()
b=d.HYG.rolling(252).cov(d.IEF)/d.IEF.rolling(252).var()
cred=(d.HYG-b.shift(1)*d.IEF).dropna().rolling(21).sum()
spy=r.SPY; rv=spy.rolling(21).std(); vix=np.log(c["^VIX"])
H=21; TGT=0.13/np.sqrt(252); COST=0.0002
y=spy.shift(-H).rolling(H).std()
X=pd.concat([y.rename("y"),rv.rename("base"),vix.rename("vix"),
             cred.rename("cred"),spy.rename("ret")],axis=1).dropna()
idx=X.index; start=1260   # 5y burn-in, strictly expanding
def overlay(cols,label):
    w=pd.Series(np.nan,index=idx)
    for i in range(start,len(idx),H):                 # rebalance every 21d
        tr=X.iloc[:i-H]                               # lag H: y unobservable
        m=sm.OLS(tr.y,sm.add_constant(tr[cols])).fit()
        f=float(m.predict(sm.add_constant(X[cols],has_constant='add').iloc[[i]]).iloc[0])
        f=max(f,0.002)
        w.iloc[i:i+H]=min(TGT/f,2.0)
    w=w.ffill()
    ret=(w.shift(1)*X.ret).dropna()
    to=w.diff().abs().fillna(0).reindex(ret.index).fillna(0)
    net=ret-to*COST
    sh=net.mean()/net.std()*np.sqrt(252)
    print(f"{label:22s} Sharpe={sh:6.3f}  vol={net.std()*np.sqrt(252):6.3f} "
          f" CAGR={net.mean()*252:6.3f}  avg_w={w.mean():5.2f} turn/yr={to.sum()/ (len(to)/252):5.2f}")
    return sh,net
print(f"n={len(idx)}  OOS from {idx[start].date()} to {idx[-1].date()}\n")
bh=X.ret.iloc[start:]; print(f"{'buy&hold SPY':22s} Sharpe={bh.mean()/bh.std()*np.sqrt(252):6.3f}")
s1,n1=overlay(["base","vix"],"VT: RV+VIX")
s2,n2=overlay(["base","vix","cred"],"VT: RV+VIX+CREDIT")
print(f"\nMARGINAL SHARPE FROM CREDIT = {s2-s1:+.4f}")
dif=(n2-n1).dropna()
print(f"diff-series t-stat = {dif.mean()/dif.std()*np.sqrt(len(dif)):+.3f}")
