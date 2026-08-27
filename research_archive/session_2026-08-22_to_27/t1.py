import yfinance as yf, pandas as pd
pd.set_option('display.width',200)
t = yf.Ticker("AAPL")
for name in ["earnings_dates","earnings_history","get_earnings_dates"]:
    try:
        obj = getattr(t,name)
        df = obj(limit=200) if callable(obj) else obj
        print("=== ",name, type(df))
        if hasattr(df,'shape'):
            print("shape",df.shape); print("cols",list(df.columns))
            print("index min/max", df.index.min(), df.index.max())
            print(df.head(3)); print(df.tail(3))
    except Exception as e:
        print("=== ",name,"ERR",repr(e)[:300])
