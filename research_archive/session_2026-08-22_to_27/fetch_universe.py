"""Fetch the full point-in-time S&P 600 universe once and cache it, then
measure the real yfinance price-coverage gap (the survivorship disclosure)."""
import sys
import warnings
from datetime import date

warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_82071471-600-1/backend")

import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab import small_cap_membership_history as scm

SCRATCH = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
START = date(2020, 1, 1)
END = date.today()
PADDED = date(2017, 9, 1)  # covers Round C's 850-day and D1's 400-day lookback padding

universe = scm.get_universe_over(START, END)
print(f"point-in-time union universe 2020-01-01..today: {len(universe)} tickers", flush=True)

provider = YFinanceProvider()
frames, missing = provider.get_daily_ohlcv(universe, PADDED, END)
close = frames["close"]
print(f"resolved price data: {len(close.columns)} of {len(universe)}  "
      f"({len(close.columns) / len(universe) * 100:.1f}%)  missing={len(missing)}", flush=True)
print(f"panel: {close.shape[0]} rows {close.index[0].date()} .. {close.index[-1].date()}", flush=True)

for name, f in frames.items():
    f.to_pickle(f"{SCRATCH}/sp600_{name}.pkl")
pd.Series(missing).to_csv(f"{SCRATCH}/sp600_missing.csv", index=False, header=["ticker"])

# --- the survivorship disclosure -----------------------------------------
resolved = set(close.columns)
departed, current = [], []
for t in universe:
    spans = scm.get_membership_intervals(t)
    (current if spans and spans[-1][1] is None else departed).append(t)

print("\n--- SURVIVORSHIP GAP (the number that qualifies every result) ---")
for label, group in (("still members at coverage end", current), ("DEPARTED the index", departed)):
    hit = sum(1 for t in group if t in resolved)
    print(f"  {label}: {hit}/{len(group)} resolve prices ({hit / len(group) * 100:.1f}%) "
          f"-> {len(group) - hit} unpriceable")

# Departed names are also checked for the recycled-ticker hazard: price
# history that STARTS long after the ticker left the index is a different
# company, not the member.
recycled = []
for t in departed:
    if t not in resolved:
        continue
    spans = scm.get_membership_intervals(t)
    left = spans[-1][1]
    first_price = close[t].dropna()
    if first_price.empty:
        continue
    if first_price.index[0].date() > left:
        recycled.append((t, left, first_price.index[0].date()))
print(f"  recycled-ticker suspects (price history starts AFTER index exit): {len(recycled)}")
for t, left, first in recycled[:12]:
    print(f"     {t}: left {left}, yfinance history starts {first}")
