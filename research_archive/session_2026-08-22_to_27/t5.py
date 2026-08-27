import yfinance as yf, pandas as pd, time
tk="DFS SYMC TRIP GME KDP FTI ETFC STI CMA BWA SRCL HRB APC WLTW SNI CXO PX PEAK DO CERN AAL FLIR DISH XLNX ATVI TWTR FRC SIVB".split()
ok=fail=0; rows=[]
for s in tk:
    try:
        ed=yf.Ticker(s).get_earnings_dates(limit=100)
        n=0 if ed is None or ed.empty else int(ed['Reported EPS'].notna().sum())
        px=yf.download(s,start="2014-01-01",end="2026-08-01",auto_adjust=True,progress=False,threads=False)
        npx=0 if px.empty else len(px); last=None if px.empty else str(px.index.max())[:10]
        rows.append((s,n,npx,last)); ok+= (n>=8 and npx>200)
    except Exception as e: rows.append((s,-1,-1,repr(e)[:40]))
    time.sleep(0.3)
d=pd.DataFrame(rows,columns=['tic','n_earn','n_px','last_px'])
print(d.to_string()); print("\nUSABLE (>=8 qtrs earnings & >200 px days):",ok,"/",len(tk))
