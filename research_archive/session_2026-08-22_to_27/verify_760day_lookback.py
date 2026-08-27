import sys
sys.path.insert(0, ".")
from datetime import date, timedelta
import yfinance as yf
from app.services.research_lab import ticker_universe

end = date.today()
start = end - timedelta(days=760)
tickers = ticker_universe.SCREENING_UNIVERSE
print("universe size:", len(tickers))

data = yf.download(tickers, start=start.isoformat(), end=end.isoformat(), progress=False, group_by="ticker", auto_adjust=True, threads=True)

n_ge_500 = 0
shortfalls = []
for t in tickers:
    try:
        col = data[t]["Close"].dropna()
    except Exception:
        shortfalls.append((t, "missing"))
        continue
    n = len(col)
    if n >= 500:
        n_ge_500 += 1
    else:
        shortfalls.append((t, n))

print(f"{n_ge_500}/{len(tickers)} tickers have >=500 trading-day rows over 760 calendar days")
print("shortfalls:", shortfalls[:20])
