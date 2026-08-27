import sys, json, warnings, math
warnings.filterwarnings('ignore')
from datetime import date, timedelta
import yfinance as yf, pandas as pd, numpy as np
SP='/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/'
cand=json.load(open(SP+'cand.json'))
tick=sorted({c['ticker'] for c in cand})
print('unique tickers', len(tick), flush=True)
data={}
CH=30
for i in range(0,len(tick),CH):
    chunk=tick[i:i+CH]
    try:
        df=yf.download(chunk, start='2014-06-01', end='2026-08-25', auto_adjust=True, progress=False, threads=True, group_by='ticker')
    except Exception as e:
        print('chunk fail',i,e, flush=True); continue
    for t in chunk:
        try:
            s=df[t]['Close'].dropna() if len(chunk)>1 else df['Close'].dropna()
            if len(s)>0: data[t]=s
        except Exception: pass
    print('done', i+len(chunk), flush=True)
res=[]
for c in cand:
    t=c['ticker']; eff=pd.Timestamp(c['eff'])
    s=data.get(t)
    if s is None or len(s)==0:
        res.append({**c,'status':'no_data'}); continue
    idx=s.index.tz_localize(None) if s.index.tz is not None else s.index
    s=pd.Series(s.values, index=idx)
    pre=s[(idx>=eff-pd.Timedelta(days=90))&(idx<eff)]
    post=s[(idx>eff)&(idx<=eff+pd.Timedelta(days=200))]
    if len(pre)<40:
        res.append({**c,'status':'no_pre'}); continue
    if len(post)<120:
        res.append({**c,'status':'delisted_soon'}); continue
    # returns
    p0=float(s[idx<=eff].iloc[-1])
    def fwd(days):
        w=s[(idx>eff)&(idx<=eff+pd.Timedelta(days=days))]
        return float(w.iloc[-1]/p0-1) if len(w)>5 else None
    pre60=None
    w=s[(idx>=eff-pd.Timedelta(days=95))&(idx<=eff)]
    if len(w)>30: pre60=float(w.iloc[-1]/w.iloc[0]-1)
    res.append({**c,'status':'survivor','pre60':pre60,'r21':fwd(31),'r63':fwd(92),'r126':fwd(184)})
json.dump(res, open(SP+'surv.json','w'))
from collections import Counter
print(Counter(x['status'] for x in res))
