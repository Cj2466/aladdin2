import yfinance as yf, pandas as pd, numpy as np, time
tk="AAPL MSFT JPM XOM PG KO WMT JNJ CVX MRK NKE ADBE CAT F LUV HON GS DE SO NUE".split()
prof=[]; drift=[]
for s in tk:
    try:
        ed=yf.Ticker(s).get_earnings_dates(limit=100); ed=ed[ed['Reported EPS'].notna()&ed['EPS Estimate'].notna()]
        px=yf.download(s,start="2004-01-01",end="2026-08-20",auto_adjust=True,progress=False,threads=False)
        if px.empty: continue
        if isinstance(px.columns,pd.MultiIndex): px.columns=px.columns.get_level_values(0)
        r=px['Close'].pct_change(); r.index=pd.to_datetime(r.index).tz_localize(None); sd=r.std()
        for ts,row in ed.iterrows():
            d=pd.Timestamp(ts); d=d.tz_convert('America/New_York') if d.tzinfo else d
            amc=d.hour>=16; day=(d.tz_localize(None) if d.tzinfo else d).normalize()
            i=r.index.searchsorted(day); e=i+1 if amc else i
            if e<5 or e>len(r)-45: continue
            w=r.iloc[e-3:e+6].values
            if len(w)==9 and not np.isnan(w).any(): prof.append(np.abs(w)/sd)
            # SUE via analyst surprise, drift t+1..t+40 (skip event day)
            su=row['Surprise(%)']
            if pd.notna(su):
                fwd=r.iloc[e+1:e+41]
                if fwd.notna().all(): drift.append((su,fwd.sum()))
    except Exception as ex: pass
    time.sleep(0.3)
P=np.array(prof); print("n events",len(P))
print("|r|/sd by day t-3..t+5:")
for k,v in zip(range(-3,6),P.mean(0)): print(f"  t{k:+d}: {v:.2f}")
D=pd.DataFrame(drift,columns=['sup','fwd40']); D=D[np.isfinite(D.sup)]
D['q']=pd.qcut(D.sup.rank(method='first'),5,labels=[1,2,3,4,5])
print("\nn drift obs",len(D))
print(D.groupby('q',observed=True).fwd40.agg(['mean','count']).assign(mean=lambda x:(x['mean']*100).round(2)))
print("Q5-Q1 spread (40d, %):",round((D[D.q==5].fwd40.mean()-D[D.q==1].fwd40.mean())*100,2))
