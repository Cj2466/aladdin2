import warnings, json
warnings.filterwarnings("ignore")
import yfinance as yf, pandas as pd, numpy as np

PAIRS = ["EURUSD=X","GBPUSD=X","USDJPY=X","AUDUSD=X","USDCHF=X","USDCAD=X","NZDUSD=X",
         "EURJPY=X","EURGBP=X","EURCHF=X","GBPJPY=X","AUDJPY=X","AUDNZD=X","CADJPY=X",
         "USDSEK=X","USDNOK=X","USDMXN=X","USDZAR=X","USDTRY=X","USDSGD=X","USDHKD=X",
         "USDCNY=X","USDINR=X","USDBRL=X","USDPLN=X","EURSEK=X","EURNOK=X","NZDJPY=X",
         "CHFJPY=X","EURAUD=X","EURCAD=X","GBPCHF=X"]

df = yf.download(PAIRS, start="2003-01-01", end="2026-08-26", interval="1d",
                 auto_adjust=False, progress=False, threads=True, group_by="column")
close = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df
rows=[]
for p in PAIRS:
    if p not in close.columns:
        rows.append({"pair":p,"status":"MISSING"}); continue
    s = close[p].dropna()
    if len(s)==0:
        rows.append({"pair":p,"status":"EMPTY"}); continue
    r = np.log(s).diff().dropna()
    # gap analysis on business-day calendar
    idx = s.index
    bdays = pd.bdate_range(idx[0], idx[-1])
    cov = len(idx)/len(bdays)
    # repeated (stale) prints
    stale = float((r==0).mean())
    # extreme jumps > 5 sigma
    sd = r.std()
    jumps = int((r.abs() > 8*sd).sum())
    # max consecutive missing bdays
    present = pd.Series(1, index=idx).reindex(bdays).fillna(0)
    grp = (present!=present.shift()).cumsum()
    maxgap = int(present[present==0].groupby(grp).size().max()) if (present==0).any() else 0
    rows.append({"pair":p,"status":"OK","n":len(s),"start":str(idx[0].date()),"end":str(idx[-1].date()),
                 "bday_cov":round(cov,3),"stale_frac":round(stale,4),"ann_vol":round(float(sd*np.sqrt(252)),4),
                 "big_jumps_8sd":jumps,"max_gap_bdays":maxgap})
print(json.dumps(rows, indent=0))
