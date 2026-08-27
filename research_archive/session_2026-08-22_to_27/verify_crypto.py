"""Re-verify tonight's scout's crypto data claims against live yfinance."""
import sys
from datetime import date

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_897780eb-d4b-1/backend")

import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider

pd.set_option("display.width", 200)

p = YFinanceProvider()
END = date(2026, 8, 27)

# --- Claim 1: crypto trades 365/366 days a year, equities ~252 -------------
print("=== CLAIM 1: rows per calendar year, BTC-USD vs SPY ===")
frames, missing = p.get_daily_ohlcv(["BTC-USD", "SPY"], date(2018, 1, 1), END)
close = frames["close"]
for t in ["BTC-USD", "SPY"]:
    if t not in close.columns:
        print(f"  {t}: MISSING")
        continue
    s = close[t].dropna()
    by_year = s.groupby(s.index.year).size()
    print(f"  {t}: {dict(by_year)}")

# --- Claim 2: dead coins retained -----------------------------------------
print("\n=== CLAIM 2: dead coins still downloadable ===")
dead = ["LUNA1-USD", "UST-USD", "ANC-USD"]
frames_d, missing_d = p.get_daily_ohlcv(dead, date(2019, 1, 1), END)
cd = frames_d.get("close", pd.DataFrame())
for t in dead:
    if t not in cd.columns:
        print(f"  {t}: MISSING (missing_list={missing_d})")
        continue
    s = cd[t].dropna()
    if s.empty:
        print(f"  {t}: EMPTY")
        continue
    print(f"  {t}: {len(s)} rows, {s.index[0].date()} .. {s.index[-1].date()}, "
          f"first={s.iloc[0]:.4f} max={s.max():.4f} last={s.iloc[-1]:.6f}")

# --- Claim 3: known-bad tickers -------------------------------------------
print("\n=== CLAIM 3: known-bad / excluded tickers ===")
bad = ["SHIB-USD", "MATIC-USD", "RNDR-USD", "UNI-USD", "UNI7083-USD",
       "TON11419-USD", "USDT-USD", "USDC-USD", "POL-USD"]
frames_b, missing_b = p.get_daily_ohlcv(bad, date(2017, 1, 1), END)
cb = frames_b.get("close", pd.DataFrame())
vb = frames_b.get("volume", pd.DataFrame())
for t in bad:
    if t not in cb.columns:
        print(f"  {t}: MISSING")
        continue
    s = cb[t].dropna()
    if s.empty:
        print(f"  {t}: EMPTY")
        continue
    v = vb[t].dropna() if t in vb.columns else pd.Series(dtype=float)
    # staleness: fraction of days with exactly zero price change
    chg = s.pct_change(fill_method=None).dropna()
    stale = float((chg == 0.0).mean()) if len(chg) else float("nan")
    last90 = s.tail(90)
    print(f"  {t}: {len(s)} rows {s.index[0].date()}..{s.index[-1].date()} "
          f"stale_days={stale:.1%} medvol={v.median() if len(v) else float('nan'):.3g} "
          f"last_price={s.iloc[-1]:.6f} min={s.min():.3g}")
