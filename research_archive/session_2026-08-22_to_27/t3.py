import yfinance as yf, pandas as pd, numpy as np, time
tk="AAPL MSFT JPM XOM PG KO WMT JNJ CVX MRK NKE ADBE CAT F LUV".split()
res=[]
for s in tk:
    try:
        ed=yf.Ticker(s).get_earnings_dates(limit=100)
        ed=ed[ed['Reported EPS'].notna()]
        px=yf.download(s,start="2005-01-01",end="2026-08-20",auto_adjust=True,progress=False,threads=False)
        if px.empty: continue
        if isinstance(px.columns,pd.MultiIndex): px.columns=px.columns.get_level_values(0)
        r=px['Close'].pct_change()
        r.index=pd.to_datetime(r.index).tz_localize(None)
        sd=r.std()
        # map each announcement to the first trading day the info is tradable
        recs=[]
        for ts in ed.index:
            d=pd.Timestamp(ts).tz_convert('America/New_York') if ts.tzinfo else pd.Timestamp(ts)
            naive=d.tz_localize(None) if d.tzinfo else d
            amc = d.hour>=16
            day=naive.normalize()
            idx=r.index.searchsorted(day)
            if idx>=len(r)-3: continue
            # event day = announcement day if BMO else next session
            e = idx+1 if amc else idx
            if e>=len(r)-2: continue
            recs.append((abs(r.iloc[e])/sd, abs(r.iloc[e-2])/sd, abs(r.iloc[e+2])/sd))
        if recs:
            a=np.array(recs)
            res.append((s,len(a),round(a[:,0].mean(),2),round(a[:,1].mean(),2),round(a[:,2].mean(),2)))
    except Exception as ex: print(s,"ERR",repr(ex)[:80])
    time.sleep(0.3)
df=pd.DataFrame(res,columns=['tic','n','|r|_event','|r|_t-2','|r|_t+2'])
print(df.to_string())
print("\nMEAN event-day |r| in sd:",round(df['|r|_event'].mean(),2)," t-2:",round(df['|r|_t-2'].mean(),2)," t+2:",round(df['|r|_t+2'].mean(),2))
