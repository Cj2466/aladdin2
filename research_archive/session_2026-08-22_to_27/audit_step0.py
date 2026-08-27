import sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
from datetime import date
import pandas as pd
import yfinance as yf

TICKERS = ["STI", "DFS", "CMA", "SRCL", "PARA", "AAPL"]
START, END = date(2013,12,3), date(2026,8,26)

print(f"{'tick':6} {'price_rows':>10} {'price_first':>12} {'price_last':>12} | {'shares_rows':>11} {'sh_first':>12} {'sh_last':>12} | {'earn_rows':>9}")
for t in TICKERS:
    tk = yf.Ticker(t)
    try:
        px = tk.history(start=START, end=END, auto_adjust=True)
    except Exception as e:
        px = pd.DataFrame()
    try:
        sh = tk.get_shares_full(start=START, end=END)
        sh = sh if sh is not None else pd.Series(dtype=float)
    except Exception as e:
        sh = pd.Series(dtype=float)
    try:
        eh = tk.earnings_history
        n_eh = 0 if eh is None else len(eh)
    except Exception:
        n_eh = -1
    pf = px.index[0].date() if len(px) else None
    pl = px.index[-1].date() if len(px) else None
    sf = pd.Timestamp(sh.index[0]).date() if len(sh) else None
    sl = pd.Timestamp(sh.index[-1]).date() if len(sh) else None
    print(f"{t:6} {len(px):10} {str(pf):>12} {str(pl):>12} | {len(sh):11} {str(sf):>12} {str(sl):>12} | {n_eh:9}")
