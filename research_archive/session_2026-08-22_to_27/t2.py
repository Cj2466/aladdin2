import yfinance as yf, pandas as pd, time, random
tk = "AAPL MSFT JPM XOM PG KO WMT JNJ CVX MRK PEP ABBV MCD CSCO ACN LIN TMO ADBE NKE DHR TXN NEE UPS RTX HON LOW UNP CAT GS BLK DE LMT ADP MMC CB SO DUK PSA AEP EXC F GM DAL LUV KHC HAS WHR MOS NUE X".split()
rows=[]
for s in tk:
    try:
        df = yf.Ticker(s).get_earnings_dates(limit=100)
        if df is None or df.empty: rows.append((s,0,None,None,None,None)); continue
        d = df[df['Reported EPS'].notna()]
        est_ok = d['EPS Estimate'].notna().mean() if len(d) else 0
        hrs = pd.Series(df.index).dt.hour.value_counts().to_dict()
        rows.append((s,len(d),str(d.index.min())[:10],str(d.index.max())[:10],round(est_ok,3),hrs))
    except Exception as e:
        rows.append((s,-1,repr(e)[:60],None,None,None))
    time.sleep(0.4)
r=pd.DataFrame(rows,columns=['tic','n_reported','first','last','est_cov','hours'])
print(r.to_string())
ok=r[r.n_reported>0]
print("\ntickers ok:",len(ok),"/",len(tk))
print("median n_reported:",ok.n_reported.median(),"min",ok.n_reported.min(),"max",ok.n_reported.max())
print("median first date:",ok['first'].median())
print("est coverage mean:",ok.est_cov.mean())
