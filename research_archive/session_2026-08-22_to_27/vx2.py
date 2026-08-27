import yfinance as yf, warnings, pandas as pd, numpy as np
warnings.filterwarnings('ignore')
print("--- VIX-futures ETFs / other vol products ---")
for s in ['VXX','VIXY','VXZ','SVXY','UVXY','^VIX3M','^VIF','^VXV']:
    try:
        h=yf.Ticker(s).history(period='max',auto_adjust=True)
        print(f"{s:8} rows={len(h):6}"+(f" {h.index[0].date()}..{h.index[-1].date()}" if len(h) else " EMPTY"))
    except Exception as e: print(f"{s:8} ERR")
print("\n--- Cross-asset IV complex: common sample + correlation of DAILY CHANGES ---")
syms=['^VIX','^VXN','^VXD','^MOVE','^GVZ','^OVX','^VVIX','^SKEW','^VIX9D','^VIX3M','^VIX6M']
d={}
for s in syms:
    h=yf.Ticker(s).history(period='max')['Close']
    h.index=h.index.tz_localize(None).normalize(); d[s]=h
df=pd.DataFrame(d).dropna()
print("common sample:",df.index[0].date(),"->",df.index[-1].date(),"rows",len(df))
ch=np.log(df[['^VIX','^VXN','^VXD','^MOVE','^GVZ','^OVX']]).diff().dropna()
print(ch.corr().round(2).to_string())
print("\nterm-structure ratio VIX9D/VIX3M stats:", (df['^VIX9D']/df['^VIX3M']).describe()[['mean','std','min','max']].round(3).to_dict())
print("MOVE/VIX ratio stats:", (df['^MOVE']/df['^VIX']).describe()[['mean','std','min','max']].round(2).to_dict())
