import sys, json, pickle, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0,"/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import pandas as pd, numpy as np
from datetime import date
from app.services.research_lab.sp500_membership_history import get_universe_over, was_member
from app.services.research_lab.cross_sectional_ivol import (
    restrict_share_counts_to_price_lifecycle, implausible_market_cap_mask, build_point_in_time_market_cap)
SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
FLAGS = [r["ticker"] for r in json.load(open(f"{SP}/analysis_output.json"))["recycled_flags"]]
d = pickle.load(open(f"{SP}/d1_impact_data.pkl","rb"))
close, shares, splits = d["close"], d["shares"], d["splits"]
mcap_close = d["mcap_close"].reindex(index=close.index, columns=close.columns)
d1_uni=set(d["universe"]); priced=set(close.columns)
bb_uni=set(get_universe_over(date(2018,1,2), date(2026,8,27)))
mc,_ = build_point_in_time_market_cap(mcap_close, shares, splits)
_, dropped = restrict_share_counts_to_price_lifecycle(shares, close)
badmask = implausible_market_cap_mask(mc)
days = np.array([t.date() for t in close.index])

print(f"{'tick':6} {'D1uni':>6} {'BBuni':>6} {'priced':>7} {'shares':>7} {'elig_days':>10}  {'lifecycle_drop':>14} {'magnitude_cells':>15}")
for t in sorted(FLAGS):
    inp = t in priced; ish = t in shares
    if inp:
        fin = np.isfinite(close[t].to_numpy())
        mem = np.array([was_member(t, dd) for dd in days])
        n_el = int((fin & mem & (days>=date(2015,1,7))).sum())
    else: n_el = 0
    ld = dropped.get(t, 0)
    mg = int(badmask[t].sum()) if t in badmask.columns else 0
    print(f"{t:6} {str(t in d1_uni):>6} {str(t in bb_uni):>6} {str(inp):>7} {str(ish):>7} {n_el:10}  {ld:14} {mg:15}")

print("\n--- detail for any flagged ticker that was actually JOINED and ELIGIBLE ---")
for t in sorted(FLAGS):
    if t not in priced or t not in shares: continue
    fin = np.isfinite(close[t].to_numpy()); mem = np.array([was_member(t, dd) for dd in days])
    el = fin & mem & (days>=date(2015,1,7))
    if not el.any(): continue
    px = close[t].dropna(); s = shares[t]
    m = mc[t].where(pd.Series(el, index=close.index))
    print(f"  {t}: eligible {days[el][0]}..{days[el][-1]} ({int(el.sum())}d) | price {px.index[0].date()}..{px.index[-1].date()}"
          f" | shares {pd.Timestamp(s.index[0]).date()}..{pd.Timestamp(s.index[-1]).date()} ({len(s)} obs)"
          f" | implied cap on eligible days ${m.min()/1e9:.2f}B..${m.max()/1e9:.1f}B")
