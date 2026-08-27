import time
from datetime import date, timedelta

import yfinance as yf

TICKERS = ["AAPL", "MSFT"]

def try_fetch(interval, period=None, start=None, end=None, tickers=None):
    tickers = tickers or TICKERS
    t0 = time.time()
    try:
        df = yf.download(tickers, period=period, start=start, end=end, interval=interval,
                          auto_adjust=True, progress=False)
    except Exception as e:
        print(f"interval={interval} period={period} start={start} end={end}: EXCEPTION {e}")
        return
    dt = time.time() - t0
    if df is None or df.empty:
        print(f"interval={interval} period={period} start={start} end={end}: EMPTY ({dt:.1f}s)")
        return
    idx = df.index
    print(f"interval={interval} period={period} start={start} end={end}: "
          f"{len(df)} rows, span {idx.min()} -> {idx.max()} ({dt:.1f}s)")

print("=== max period per interval (single ticker AAPL) ===")
for interval in ["1m", "2m", "5m", "15m", "30m", "60m", "1h", "1d"]:
    try_fetch(interval, period="max", tickers=["AAPL"])

print()
print("=== explicit longer lookbacks for 5m (single ticker AAPL) ===")
today = date.today()
for days_back in [7, 30, 59, 60, 61, 90, 180, 365, 730]:
    start = today - timedelta(days=days_back)
    try_fetch("5m", start=start.isoformat(), end=today.isoformat(), tickers=["AAPL"])

print()
print("=== explicit longer lookbacks for 1m (single ticker AAPL) ===")
for days_back in [5, 7, 8, 10, 30]:
    start = today - timedelta(days=days_back)
    try_fetch("1m", start=start.isoformat(), end=today.isoformat(), tickers=["AAPL"])

print()
print("=== multi-ticker 5m fetch, 30 tickers, last 30 days ===")
tickers_30 = ["AAPL","MSFT","GOOGL","AMZN","NVDA","META","TSLA","JPM","V","UNH",
              "XOM","JNJ","WMT","PG","MA","HD","CVX","MRK","ABBV","KO",
              "PEP","BAC","AVGO","COST","MCD","CSCO","ADBE","CRM","TMO","ACN"]
start = today - timedelta(days=30)
try_fetch("5m", start=start.isoformat(), end=today.isoformat(), tickers=tickers_30)
