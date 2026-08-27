import time, warnings, pandas as pd, yfinance as yf
warnings.filterwarnings('ignore')
OUT='/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/'
tk=['^VIX','^VXN','^SKEW','^MOVE','^VVIX','^OVX','^GVZ','SPY','IEF','HYG']
frames={}
for t in tk:
    for attempt in range(6):
        try:
            d=yf.download(t,start='2006-01-01',progress=False,auto_adjust=False,threads=False)
            if len(d)>100:
                c=d['Close']
                frames[t]=c.iloc[:,0] if hasattr(c,'columns') else c
                print(t,len(d),d.index[0].date(),flush=True); break
        except Exception as e: print(t,'err',str(e)[:50],flush=True)
        time.sleep(20)
    else: print(t,'FAILED',flush=True)
df=pd.DataFrame(frames)
df.to_pickle(OUT+'raw.pkl')
print('COLS',list(df.columns),len(df))
