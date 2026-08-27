import warnings, json; warnings.filterwarnings("ignore")
import yfinance as yf, pandas as pd, numpy as np

CRYPTO=["BTC-USD","ETH-USD","XRP-USD","BNB-USD","SOL-USD","ADA-USD","DOGE-USD","AVAX-USD",
        "DOT-USD","LINK-USD","LTC-USD","BCH-USD","TRX-USD","XLM-USD","ATOM-USD","ETC-USD","XMR-USD","FIL-USD"]
EQ=["SPY","AAPL","MSFT","JPM","XOM","JNJ","WMT","PG"]

def vr(r,q):
    r=r.dropna().values; n=len(r)-(len(r)%q)
    r=r[:n]
    v1=r.var(ddof=1)
    agg=r.reshape(-1,q).sum(axis=1)
    vq=agg.var(ddof=1)/q
    # Lo-MacKinlay heteroskedasticity-robust z
    mu=r.mean(); m=n
    theta=0.0
    for j in range(1,q):
        num=((r[j:]-mu)**2*(r[:-j]-mu)**2).sum()
        den=(((r-mu)**2).sum())**2
        dj=m*num/den
        theta+=(2*(q-j)/q)**2*dj
    z=(vq/v1-1)/np.sqrt(theta) if theta>0 else np.nan
    return vq/v1, z

def corwin_schultz(h,l):
    # daily high/low -> effective spread, 2-day overlapping
    h=np.log(h); l=np.log(l)
    beta=((h-l)**2 + (h.shift(1)-l.shift(1))**2)
    h2=pd.concat([h,h.shift(1)],axis=1).max(axis=1); l2=pd.concat([l,l.shift(1)],axis=1).min(axis=1)
    gamma=(h2-l2)**2
    k=3-2*np.sqrt(2)
    alpha=(np.sqrt(2*beta)-np.sqrt(beta))/k - np.sqrt(gamma/k)
    s=2*(np.exp(alpha)-1)/(1+np.exp(alpha))
    return s.clip(lower=0)

out={}
for name,univ in [("crypto",CRYPTO),("equity",EQ)]:
    d=yf.download(univ,start="2021-01-01",end="2026-08-26",auto_adjust=False,progress=False)
    cl=d["Close"]; hi=d["High"]; lo=d["Low"]
    rows={}
    for t in univ:
        if t not in cl: continue
        r=np.log(cl[t]).diff().dropna()
        if len(r)<500: continue
        vr5,z5=vr(r,5); vr20,z20=vr(r,20)
        cs=corwin_schultz(hi[t],lo[t]).dropna()
        rows[t]={"ar1":round(float(r.autocorr(1)),4),
                 "VR5":round(float(vr5),3),"z5":round(float(z5),2),
                 "VR20":round(float(vr20),3),"z20":round(float(z20),2),
                 "ann_vol":round(float(r.std()*np.sqrt(365 if name=="crypto" else 252)),3),
                 "CS_spread_bps_med":round(float(np.nanmedian(cs.tail(365))*10000),1)}
    out[name]=rows
# cross-sectional dispersion + xs momentum autocorr proxy
d=yf.download(CRYPTO,start="2021-01-01",end="2026-08-26",auto_adjust=False,progress=False)["Close"]
r=np.log(d).diff()
out["xs_disp_crypto_daily_bps"]=round(float(r.std(axis=1).median()*10000),0)
de=yf.download(EQ,start="2021-01-01",end="2026-08-26",auto_adjust=False,progress=False)["Close"]
re_=np.log(de).diff()
out["xs_disp_equity_daily_bps"]=round(float(re_.std(axis=1).median()*10000),0)
# avg pairwise corr (crowding / how much is one factor)
out["crypto_avg_pairwise_corr"]=round(float(r.corr().values[np.triu_indices(len(r.columns),1)].mean()),3)
print(json.dumps(out,indent=1))
