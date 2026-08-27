import sys
from datetime import date, timedelta

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_ea27d8f0-500-1/backend")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.services.market_data.yfinance_provider import YFinanceProvider  # noqa: E402
from app.services.research_lab.sp500_membership_history import (  # noqa: E402
    _BASE_UNIVERSE,
    earliest_membership_date,
    vendored_events,
)

events = vendored_events()
base = set(_BASE_UNIVERSE)
first_removal = {}
for eff, added, removed in events:
    for t in removed:
        first_removal.setdefault(t, eff)
add_dates, rem_dates = {}, {}
for eff, added, removed in events:
    for t in added:
        add_dates.setdefault(t, []).append(eff)
    for t in removed:
        rem_dates.setdefault(t, []).append(eff)

LAG = 7
rename_dates = set()
for eff, added, removed in events:
    for s in added:
        em = earliest_membership_date(s)
        prior = first_removal.get(s)
        if em is not None and (eff - em).days > LAG and s not in base and not (prior and prior < eff):
            rename_dates.add(eff)
roundtrip = set()
for eff, added, removed in events:
    for r in removed:
        for s in added:
            for d2 in set(add_dates.get(r, [])) & set(rem_dates.get(s, [])):
                if d2 > eff:
                    roundtrip.add((r, eff))
                    roundtrip.add((s, d2))

all_removals = [(r, eff) for eff, a, rem in events for r in rem]
non_rename = [(r, d) for r, d in all_removals if d not in rename_dates and (r, d) not in roundtrip]
print("total removals            :", len(all_removals))
print("dates flagged as rename   :", len(rename_dates))
print("removals dropped by rename:", len(all_removals) - len(non_rename))
print("non-rename removals       :", len(non_rename))

tickers = sorted({r for r, _ in non_rename})
print("distinct tickers to fetch :", len(tickers))

prov = YFinanceProvider()
frames, missing = prov.get_daily_ohlcv(tickers, date(2014, 1, 1), date.today())
close = frames["close"]
vol = frames["volume"]
print("missing price data        :", len(missing))
print("close frame shape         :", close.shape, close.index[0].date(), close.index[-1].date())

spy_frames, spy_missing = prov.get_daily_ohlcv(["SPY"], date(2014, 1, 1), date.today())
spy = spy_frames["close"]["SPY"]
print("SPY rows                  :", len(spy))

idx = close.index
PRE_WINDOW, MIN_PRE = 21, 15
MAX_ENTRY_GAP_DAYS = 10

enterable, rejected = [], {}
for r, d in non_rename:
    if r not in close.columns:
        rejected.setdefault("no price data at all", []).append((r, d))
        continue
    ts = pd.Timestamp(d)
    pos_at = int(np.searchsorted(idx.values, ts.to_datetime64(), side="right")) - 1
    if pos_at < PRE_WINDOW:
        rejected.setdefault("removal before price history", []).append((r, d))
        continue
    entry_pos = pos_at + 1
    if entry_pos >= len(idx) - 1:
        rejected.setdefault("removal too recent for any hold", []).append((r, d))
        continue
    pre = close[r].iloc[pos_at - PRE_WINDOW + 1 : pos_at + 1]
    if int(pre.notna().sum()) < MIN_PRE:
        rejected.setdefault("no pre-removal prices (recycled/never traded)", []).append((r, d))
        continue
    if not np.isfinite(close[r].iloc[entry_pos]):
        rejected.setdefault("no price on entry day", []).append((r, d))
        continue
    if (idx[entry_pos].date() - d).days > MAX_ENTRY_GAP_DAYS:
        rejected.setdefault("entry day too far after effective date", []).append((r, d))
        continue
    enterable.append((r, d, entry_pos))

print()
print("ENTERABLE (quotable non-rename removals):", len(enterable))
for k, v in sorted(rejected.items(), key=lambda kv: -len(kv[1])):
    print(f"  rejected: {k:48s} {len(v):4d}  e.g. {v[:4]}")

# survival to a full post window
for hold in (63, 126, 252):
    full = 0
    for r, d, ep in enterable:
        end = ep + hold
        if end >= len(idx):
            continue
        seg = close[r].iloc[ep : end + 1]
        if int(seg.notna().sum()) >= int(0.9 * (hold + 1)):
            full += 1
    print(f"  survive a FULL {hold}-day post window: {full}")

# independent clusters: group event dates >= 7 days apart
dates = sorted({d for _, d, _ in enterable})
clusters, cur = [], [dates[0]]
for d in dates[1:]:
    if (d - cur[-1]).days >= 7:
        clusters.append(cur)
        cur = [d]
    else:
        cur.append(d)
clusters.append(cur)
print()
print("distinct event dates      :", len(dates))
print("independent clusters (>=7d):", len(clusters))
print("date range                :", dates[0], "..", dates[-1])

# liquidity: median dollar volume over the 63 trading days after entry
dv = []
for r, d, ep in enterable:
    end = min(ep + 63, len(idx) - 1)
    p = close[r].iloc[ep : end + 1]
    v = vol[r].iloc[ep : end + 1]
    m = (p * v).dropna()
    if len(m):
        dv.append(float(m.median()))
dv = np.array(dv)
print()
print("post-removal median $ volume/day across events: median ${:,.0f}".format(np.median(dv)))
print("  quartiles: 25% ${:,.0f}  75% ${:,.0f}  min ${:,.0f}".format(*np.percentile(dv, [25, 75]), dv.min()))
print("  events under $10M/day:", int((dv < 10e6).sum()), "of", len(dv))
