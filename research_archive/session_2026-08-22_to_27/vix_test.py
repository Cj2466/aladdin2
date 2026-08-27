import yfinance as yf, warnings, pandas as pd
warnings.filterwarnings('ignore')
syms=['^VIX','^VIX9D','^VIX3M','^VIX6M','^VVIX','^SKEW','^GVZ','^OVX','^VXN','^RVX','^VXTLT','^VXEEM','^VXAPL','^VXD','^MOVE','^VIX1D']
for s in syms:
    try:
        h=yf.Ticker(s).history(period='max',auto_adjust=False)
        if len(h)==0: print(f"{s:10} EMPTY"); continue
        print(f"{s:10} rows={len(h):6} start={h.index[0].date()} end={h.index[-1].date()} last={h['Close'].iloc[-1]:.2f} nan={h['Close'].isna().mean():.3f}")
    except Exception as e: print(f"{s:10} ERR {type(e).__name__}")
