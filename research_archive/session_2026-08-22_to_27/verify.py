"""Independent verification of the production run:
(1) is 'zero mid-hold delistings' real or a bug?
(2) does a from-scratch event-study reproduce the replay's sign?
"""

import sys
from datetime import date, timedelta

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_ea27d8f0-500-1/backend")
import numpy as np  # noqa: E402

from app.services.market_data.yfinance_provider import YFinanceProvider  # noqa: E402
from app.services.research_lab.cross_sectional import _compute_delisting_positions  # noqa: E402
from app.services.research_lab.cross_sectional_index_removal import (  # noqa: E402
    REMOVAL_PRICE_HISTORY_PADDING_CALENDAR_DAYS,
    build_removal_event_book,
    list_index_removal_events,
)
from app.services.research_lab.sp500_membership_history import MEMBERSHIP_DATA_START  # noqa: E402

start, end = MEMBERSHIP_DATA_START, date.today()
events, _ = list_index_removal_events()
events = [e for e in events if start <= e.effective_date <= end]
prov = YFinanceProvider()
frames, missing = prov.get_daily_ohlcv(
    sorted({e.ticker for e in events}),
    start - timedelta(days=REMOVAL_PRICE_HISTORY_PADDING_CALENDAR_DAYS),
    end,
)
close = frames["close"]
spy = prov.get_daily_ohlcv(["SPY"], start - timedelta(days=REMOVAL_PRICE_HISTORY_PADDING_CALENDAR_DAYS), end)[0][
    "close"
]["SPY"]
entered, rejected = build_removal_event_book(close, events)
idx = close.index
n = len(idx)

print("=" * 70)
print("(1) DELISTING CHECK")
print("=" * 70)
positions = _compute_delisting_positions(close)
print(f"tickers in frame                       : {len(close.columns)}")
print(f"tickers whose prices END before the frame end: {len(positions)}")
entered_tk = {e.ticker for e in entered}
hit = {t: p for t, p in positions.items() if t in entered_tk}
print(f"...of which are ENTERED names          : {len(hit)}")
for t, p in sorted(hit.items(), key=lambda kv: kv[1]):
    print(f"    {t:6s} last price {idx[p - 1].date()}  (row {p})")
for hold in (63, 126, 252):
    fired = 0
    for e in entered:
        p = positions.get(e.ticker)
        if p is not None and e.entry_position < p <= min(e.entry_position + hold, n - 1):
            fired += 1
    print(f"  imputation would fire at hold={hold}: {fired} event(s)")

print()
print("=" * 70)
print("(2) INDEPENDENT EVENT STUDY -- buy-and-hold stock minus SPY, no costs")
print("=" * 70)
for hold in (63, 126, 252):
    ex = []
    for e in entered:
        a, b = e.entry_position, min(e.entry_position + hold, n - 1)
        if b <= a:
            continue
        s = close[e.ticker].iloc[a : b + 1].dropna()
        if len(s) < 2:
            continue
        stock = float(s.iloc[-1] / s.iloc[0] - 1.0)
        m = spy.iloc[a : b + 1].dropna()
        bench = float(m.iloc[-1] / m.iloc[0] - 1.0)
        ex.append(stock - bench)
    ex = np.array(ex)
    t = ex.mean() / (ex.std(ddof=1) / np.sqrt(len(ex)))
    print(
        f"hold={hold:3d}  n={len(ex):3d}  mean excess {ex.mean():+7.2%}  median {np.median(ex):+7.2%}  "
        f"t={t:+5.2f}  share positive {np.mean(ex > 0):5.1%}"
    )
