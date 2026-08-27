import sys
from datetime import date

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
rename_dates, why = set(), {}
for eff, added, removed in events:
    for s in added:
        em = earliest_membership_date(s)
        prior = first_removal.get(s)
        if em is not None and (eff - em).days > LAG and s not in base and not (prior and prior < eff):
            rename_dates.add(eff)
            why.setdefault(eff, []).append((s, em, removed))
roundtrip = set()
for eff, added, removed in events:
    for r in removed:
        for s in added:
            for d2 in set(add_dates.get(r, [])) & set(rem_dates.get(s, [])):
                if d2 > eff:
                    roundtrip.add((r, eff))
                    roundtrip.add((s, d2))

dropped = [(r, eff) for eff, a, rem in events for r in rem if eff in rename_dates or (r, eff) in roundtrip]
print("removals dropped by rename filter:", len(dropped))
for eff in sorted(why):
    print("  ", eff, "successor(s)", [(s, str(e)) for s, e, _ in why[eff]], "-> drops", why[eff][0][2])
print("  roundtrip drops:", sorted((t, str(d)) for t, d in roundtrip))

prov = YFinanceProvider()
tk = sorted({r for r, _ in dropped})
frames, missing = prov.get_daily_ohlcv(tk, date(2014, 1, 1), date.today())
close = frames["close"]
idx = close.index
survived = []
for r, d in dropped:
    if r not in close.columns:
        continue
    ts = pd.Timestamp(d)
    pos = int(np.searchsorted(idx.values, ts.to_datetime64(), side="right")) - 1
    if pos < 21 or pos + 1 >= len(idx) - 1:
        continue
    pre = close[r].iloc[pos - 20 : pos + 1]
    if int(pre.notna().sum()) < 15:
        continue
    if not np.isfinite(close[r].iloc[pos + 1]):
        continue
    survived.append((r, str(d)))
print()
print("of the", len(dropped), "rename-dropped removals,", len(survived), "would otherwise have been enterable:")
print("  ", survived)
