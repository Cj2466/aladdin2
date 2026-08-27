import sys, time
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
from datetime import date, timedelta
import yfinance as yf
import pandas as pd
from app.services.research_lab.ticker_universe import SCREENING_UNIVERSE

end = date.today()
start = end - timedelta(days=760)
t0 = time.time()
raw = yf.download(SCREENING_UNIVERSE, start=start, end=end, auto_adjust=True, progress=False)
elapsed = time.time() - t0
close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
close = close.dropna(axis=1, how="all")
n_resolved = close.shape[1]
print(f"Full 503-universe @ 760 calendar days: fetched in {elapsed:.1f}s, resolved {n_resolved}/{len(SCREENING_UNIVERSE)}, {close.shape[0]} rows")

n_ge_500 = sum(1 for t in close.columns if close[t].dropna().shape[0] >= 500)
n_ge_520 = sum(1 for t in close.columns if close[t].dropna().shape[0] >= 520)
print(f"Tickers with >=500 trading-day rows (HMM window floor): {n_ge_500}/{n_resolved}")
print(f"Tickers with >=520 trading-day rows (HMM window + 20d buffer): {n_ge_520}/{n_resolved}")
print(f"Row-count distribution: min={close.count().min()}, median={close.count().median():.0f}, max={close.count().max()}")
