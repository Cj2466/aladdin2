import sys
from datetime import date
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a327c9fd73bf9f348/backend")
import yfinance as yf
tests = ["BK","MMC","CTRA","HOLX","FI","SEE","WFC","K","DFS","JNPR","AAPL","MON"]
for t in tests:
    try:
        df = yf.download(t, start=date(2015,1,7), end=date(2026,8,26), auto_adjust=True, progress=False)
        n = 0 if df is None or df.empty else len(df.dropna(how="all"))
        print(f"{t}: rows={n}")
    except Exception as e:
        print(f"{t}: ERROR {type(e).__name__} {e}")
