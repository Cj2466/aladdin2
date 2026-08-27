import json, warnings
warnings.filterwarnings('ignore')
import yfinance as yf, pandas as pd, numpy as np
SP='/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/'
sv=[x for x in json.load(open(SP+'surv.json')) if x['status']=='survivor']
tick=sorted({x['ticker'] for x in sv})
dv={}; cs={}
CH=30
store={}
for i in range(0,len(tick),CH):
    ch=tick[i:i+CH]
    df=yf.download(ch, start='2014-06-01', end='2026-08-25', auto_adjust=False, progress=False, group_by='ticker')
    for t in ch:
        try: store[t]=df[t][['High','Low','Close','Volume']].dropna()
        except Exception: pass
out=[]
for x in sv:
    t=x['ticker']; eff=pd.Timestamp(x['eff'])
    d=store.get(t)
    if d is None or len(d)==0: continue
    idx=d.index.tz_localize(None) if d.index.tz is not None else d.index
    d=d.set_index(idx)
    w=d[(d.index>eff)&(d.index<=eff+pd.Timedelta(days=95))]
    if len(w)<30: continue
    ddv=float((w['Close']*w['Volume']).median())
    # Corwin-Schultz 2-day high-low spread estimator
    hi=w['High'].values; lo=w['Low'].values
    b=(np.log(hi[1:]/lo[1:])**2+np.log(hi[:-1]/lo[:-1])**2)
    h2=np.maximum(hi[1:],hi[:-1]); l2=np.minimum(lo[1:],lo[:-1])
    g=np.log(h2/l2)**2
    k1=4*np.log(2); k2=np.sqrt(8/np.pi)
    a=(np.sqrt(2*b)-np.sqrt(b))/(3-2*np.sqrt(2))-np.sqrt(g/(3-2*np.sqrt(2)))
    s=2*(np.exp(a)-1)/(1+np.exp(a))
    s=s[np.isfinite(s)]; s=np.clip(s,0,None)
    out.append({'t':t,'ddv':ddv,'cs':float(np.median(s))})
dvv=np.array([o['ddv'] for o in out]); css=np.array([o['cs'] for o in out])
print('n with liquidity', len(out))
print('median daily $vol post-removal: $%.1fM  (p10 $%.1fM, p90 $%.1fM)'%(np.median(dvv)/1e6, np.percentile(dvv,10)/1e6, np.percentile(dvv,90)/1e6))
print('Corwin-Schultz median half-spread bps: median %.1f, p90 %.1f'%(np.median(css)*1e4/2, np.percentile(css,90)*1e4/2))
