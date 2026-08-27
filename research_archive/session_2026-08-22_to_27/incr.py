import yfinance as yf, pandas as pd, numpy as np, warnings
warnings.filterwarnings('ignore')
def g(s,col='Close'):
    h=yf.Ticker(s).history(period='max',auto_adjust=True)[col]; h.index=h.index.tz_localize(None).normalize(); return h
d={s:g(s) for s in ['^VIX','^VIX9D','^VIX3M','^MOVE','^OVX','^GVZ','^VVIX','^SKEW']}
d['SPY']=g('SPY')
df=pd.DataFrame(d).dropna()
print("sample",df.index[0].date(),df.index[-1].date(),len(df))
H=21  # 21-trading-day hold, cost-justified
fwd=df.SPY.shift(-H)/df.SPY-1
# textbook signal: VIX term structure slope
ts=np.log(df['^VIX9D']/df['^VIX3M'])
# realized vol (the "dressed up" comparator)
rv=np.log(df.SPY).diff().rolling(21).std()*np.sqrt(252)
# variance risk premium (textbook)
vrp=df['^VIX']/100-rv
# cross-asset candidates
mv=np.log(df['^MOVE']/df['^VIX']); ov=np.log(df['^OVX']/df['^VIX']); gv=np.log(df['^GVZ']/df['^VIX'])
X=pd.DataFrame({'ts':ts,'vrp':vrp,'rv':rv,'move_vix':mv,'ovx_vix':ov,'gvz_vix':gv,'fwd':fwd}).dropna()
z=lambda s:(s-s.mean())/s.std()
print("\nunivariate corr with fwd %dd SPY ret (overlapping, indicative only):"%H)
for c in ['ts','vrp','rv','move_vix','ovx_vix','gvz_vix']:
    print(f"  {c:9} corr={X[c].corr(X.fwd):+.3f}")
import numpy.linalg as la
def reg(cols):
    A=np.column_stack([np.ones(len(X))]+[z(X[c]).values for c in cols]); y=X.fwd.values
    b=la.lstsq(A,y,rcond=None)[0]; r=y-A@b; r2=1-r.var()/y.var(); return b,r2
b1,r1=reg(['ts','vrp']); b2,r2_=reg(['ts','vrp','move_vix','ovx_vix'])
print(f"\nR2 textbook only (ts,vrp)          = {r1:.4f}")
print(f"R2 + cross-asset (move,ovx)        = {r2_:.4f}   delta={r2_-r1:+.4f}")
print("coefs cross-asset model:",dict(zip(['int','ts','vrp','move_vix','ovx_vix'],np.round(b2,4))))
print("\ncorr(move_vix, ts)=",round(X.move_vix.corr(X.ts),3)," corr(move_vix, rv)=",round(X.move_vix.corr(X.rv),3))
