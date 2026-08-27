import warnings; warnings.filterwarnings("ignore")
import yfinance as yf, pandas as pd

TICKERS = ["^VIX","^VIX3M","^VIX6M","^VXD","^VVIX","^SKEW","^MOVE","^OVX","^GVZ","^VIX9D","^VIX1D"]
print("=== individual yf.download, auto_adjust=True ===")
for t in TICKERS:
    try:
        raw = yf.download(t, start="1990-01-01", end="2026-08-27", auto_adjust=True, progress=False)
        if raw is None or raw.empty:
            print(f"{t:9s} EMPTY"); continue
        c = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
        s = c.iloc[:,0].dropna()
        print(f"{t:9s} first={s.index[0].date()} last={s.index[-1].date()} n={len(s)}")
    except Exception as e:
        print(f"{t:9s} ERROR {type(e).__name__}: {e}")

print("\n=== yf.Ticker().history(period='max') ===")
for t in TICKERS:
    try:
        h = yf.Ticker(t).history(period="max", auto_adjust=True)
        if h is None or h.empty:
            print(f"{t:9s} EMPTY"); continue
        s = h["Close"].dropna()
        print(f"{t:9s} first={s.index[0].date()} last={s.index[-1].date()} n={len(s)}")
    except Exception as e:
        print(f"{t:9s} ERROR {type(e).__name__}: {e}")
