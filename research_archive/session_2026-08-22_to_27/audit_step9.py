import sys, pickle, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import pandas as pd, numpy as np
from datetime import date
from app.services.research_lab.sp500_membership_history import get_universe_over
from app.services.research_lab.cross_sectional_buyback import (
    build_point_in_time_share_counts, BUYBACK_FORMATION_START)
SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
d = pickle.load(open(f"{SP}/d1_impact_data.pkl","rb"))
close_d1, shares, splits = d["close"], d["shares"], d["splits"]

bb_universe = get_universe_over(date(2018,1,2), date(2026,8,27))
print("buyback universe:", len(bb_universe), "(production reported 691)")
print("not covered by the D1 fetch:", sorted(set(bb_universe) - set(d["universe"])))

# Reproduce buyback's own price panel from the D1 close (superset in time).
padded = date(2018,1,2) - pd.Timedelta(days=800)
cols = [t for t in close_d1.columns if t in set(bb_universe)]
close = close_d1.loc[close_d1.index >= pd.Timestamp(padded), cols].dropna(axis=1, how="all")
print("reconstructed buyback panel:", close.shape, " production reported panel_start 2015-10-26 ->", close.index[0].date())
print("priced tickers:", close.shape[1], "(production: 691-94 = 597)")

frame, unusable = build_point_in_time_share_counts(close, shares, splits)
frame.to_pickle(f"{SP}/audit_bb_shares.pkl"); close.to_pickle(f"{SP}/audit_bb_close.pkl")
print("unusable share history:", len(unusable))

print("\n=== BNY in the buyback share panel: the fabricated issuance ===")
b = frame["BNY"].dropna()
print("  panel coverage", b.index[0].date(), "..", b.index[-1].date())
for dt in ["2021-06-01","2021-07-24","2021-07-26","2021-09-01","2022-01-03","2022-06-01","2023-01-03"]:
    ts = frame.index[frame.index.searchsorted(pd.Timestamp(dt))]
    print(f"   {ts.date()}  shares={frame['BNY'].loc[ts]:,.0f}")
