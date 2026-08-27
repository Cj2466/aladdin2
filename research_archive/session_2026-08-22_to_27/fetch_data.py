import sys, time
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
from datetime import date, timedelta
import yfinance as yf
import pandas as pd

from app.services.research_lab.ticker_universe import SCREENING_UNIVERSE

# Sample: take every 3rd ticker from the real 503-universe -> ~168 tickers,
# spread across all sectors (matches the list's own sector-grouped ordering),
# not a cherry-picked subset.
sample = SCREENING_UNIVERSE[::3]
print(f"Sample size: {len(sample)}")

end = date.today()
start = end - timedelta(days=365 * 3 + 30)  # ~3 years, for coint window-length tests

t0 = time.time()
raw = yf.download(sample, start=start, end=end, auto_adjust=True, progress=False)
elapsed = time.time() - t0
close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
close = close.dropna(axis=1, how="all")
n_resolved = close.shape[1]
print(f"Fetched in {elapsed:.1f}s, resolved {n_resolved}/{len(sample)} tickers, {close.shape[0]} rows")

close.to_pickle("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/prices_3y.pkl")
print("Saved.")
