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
for eff, a, rem in events:
    for t in rem:
        first_removal.setdefault(t, eff)
add_dates, rem_dates = {}, {}
for eff, a, rem in events:
    for t in a:
        add_dates.setdefault(t, []).append(eff)
    for t in rem:
        rem_dates.setdefault(t, []).append(eff)
rename_dates = set()
for eff, a, rem in events:
    for s in a:
        em = earliest_membership_date(s)
        prior = first_removal.get(s)
        if em is not None and (eff - em).days > 7 and s not in base and not (prior and prior < eff):
            rename_dates.add(eff)
roundtrip = set()
for eff, a, rem in events:
    for r in rem:
        for s in a:
            for d2 in set(add_dates.get(r, [])) & set(rem_dates.get(s, [])):
                if d2 > eff:
                    roundtrip.add((r, eff))
                    roundtrip.add((s, d2))
non_rename = [
    (r, eff) for eff, a, rem in events for r in rem if eff not in rename_dates and (r, eff) not in roundtrip
]

prov = YFinanceProvider()
frames, _ = prov.get_daily_ohlcv(sorted({r for r, _ in non_rename}), date(2014, 1, 1), date.today())
close, vol = frames["close"], frames["volume"]
idx = close.index

illiqs, advs = [], []
for r, d in non_rename:
    if r not in close.columns:
        continue
    pos = int(np.searchsorted(idx.values, pd.Timestamp(d).to_datetime64(), side="right")) - 1
    if pos < 21 or pos + 1 >= len(idx) - 1:
        continue
    if int(close[r].iloc[pos - 20 : pos + 1].notna().sum()) < 15 or not np.isfinite(close[r].iloc[pos + 1]):
        continue
    end = min(pos + 1 + 63, len(idx) - 1)
    p = close[r].iloc[pos + 1 : end + 1]
    v = vol[r].iloc[pos + 1 : end + 1]
    ret = p.pct_change(fill_method=None).abs()
    dollar = (p * v).replace(0.0, np.nan)
    ill = (ret / dollar).dropna()
    if len(ill) > 20:
        illiqs.append(float(ill.mean()))
        advs.append(float(dollar.median()))

illiqs, advs = np.array(illiqs), np.array(advs)
print("events measured:", len(illiqs))
print("median ADV $/day: {:,.0f}".format(np.median(advs)))
print("Amihud ILLIQ (mean |r| per $ traded), median: {:.3e}".format(np.median(illiqs)))
print()
print("Amihud-implied ONE-WAY price impact, by trade size as % of that name's median ADV")
print("(impact = 0.5 * ILLIQ * trade_dollars, Amihud 2002 daily price-response scaling)")
for frac in (0.01, 0.02, 0.05, 0.10, 0.20):
    imp = 0.5 * illiqs * (advs * frac)
    print(
        "  {:5.0%} of ADV -> median {:6.2f} bp   p75 {:6.2f} bp   p90 {:6.2f} bp".format(
            frac, np.median(imp) * 1e4, np.percentile(imp, 75) * 1e4, np.percentile(imp, 90) * 1e4
        )
    )
print()
for frac in (0.02, 0.05, 0.10):
    imp = 0.5 * illiqs * (advs * frac)
    rt = 2.0 * (np.median(imp) * 1e4 + 3.0)  # + 3bp assumed effective half-spread, round trip
    print("  round trip incl. 3bp half-spread @ {:4.0%} of ADV: {:5.1f} bp".format(frac, rt))
