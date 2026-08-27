import warnings, json, os, pickle; warnings.filterwarnings("ignore")
import yfinance as yf, pandas as pd, numpy as np
SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/"
CRYPTO=["BTC-USD","ETH-USD","XRP-USD","BNB-USD","SOL-USD","ADA-USD","DOGE-USD","AVAX-USD",
        "DOT-USD","LINK-USD","LTC-USD","BCH-USD","TRX-USD","XLM-USD","ATOM-USD","ETC-USD","XMR-USD","FIL-USD"]
EQ=["SPY","AAPL","MSFT","JPM","XOM","JNJ","WMT","PG","KO","MRK"]
def get(u,tag):
    p=SP+tag+".pkl"
    if os.path.exists(p): return pickle.load(open(p,"rb"))
    d=yf.download(u,start="2021-01-01",end="2026-08-26",auto_adjust=False,progress=False)
    pickle.dump(d,open(p,"wb")); return d
def vr(r,q):
    r=np.asarray(r.dropna()); m=len(r)-(len(r)%q); r=r[:m]
    mu=r.mean(); v1=r.var(ddof=1); vq=r.reshape(-1,q).sum(axis=1).var(ddof=1)/q
    e2=(r-mu)**2; den=e2.sum()**2; th=0.0
    for j in range(1,q):
        th+=(2*(q-j)/q)**2*((e2[j:]*e2[:-j]).sum()/den)
    return vq/v1,(vq/v1-1)/np.sqrt(th)
res={}
for tag,u,ann in [("crypto",CRYPTO,365),("equity",EQ,252)]:
    d=get(u,tag); cl=d["Close"]; rows={}
    for t in u:
        if t not in cl: continue
        r=np.log(cl[t]).diff().dropna()
        if len(r)<500: continue
        a,az=vr(r,5); b,bz=vr(r,21)
        rows[t]=dict(n=len(r),ar1=round(float(r.autocorr(1)),3),VR5=round(float(a),3),z5=round(float(az),2),
                     VR21=round(float(b),3),z21=round(float(bz),2),ann_vol=round(float(r.std()*np.sqrt(ann)),2))
    res[tag]=rows
    v5=[x["VR5"] for x in rows.values()]; v21=[x["VR21"] for x in rows.values()]
    res[tag+"_MEAN"]=dict(VR5=round(float(np.mean(v5)),3),VR21=round(float(np.mean(v21)),3),
                          ar1=round(float(np.mean([x["ar1"] for x in rows.values()])),3))
print(json.dumps(res,indent=1))
