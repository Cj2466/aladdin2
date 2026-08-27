"""Derive the S&P 600 plausibility band the SAME way the S&P 500 one was
derived: against the measured distribution of ELIGIBLE-cell market caps, then
name every ticker each candidate band would actually refuse.
"""
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
from app.services.research_lab.cross_sectional_ivol import (  # noqa: E402
    build_point_in_time_market_cap,
    implausible_market_cap_mask,
)

HERE = Path(__file__).parent
with (HERE / "sc600_fetch.pkl").open("rb") as fh:
    D = pickle.load(fh)
with (HERE / "audit_stage1.pkl").open("rb") as fh:
    S = pickle.load(fh)

pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_rows", 400)
elig = S["elig"]

# The band must be judged on the frame it will ACTUALLY mask in production:
# the market cap AFTER the time axis has already run (that is the wiring
# order in run_round_d1_screening).
mc = S["mcap_after_time"].where(elig)

for lo, hi in ((5e7, 1e11), (1e8, 1e11), (5e7, 5e10)):
    mask = implausible_market_cap_mask(mc, minimum_usd=lo, maximum_usd=hi)
    per = mask.sum(axis=0)
    per = per[per > 0].sort_values(ascending=False)
    print("=" * 78)
    print(f"BAND [{lo/1e9:.3f}bn, {hi/1e9:.0f}bn] -> {int(mask.to_numpy().sum())} cells "
          f"over {len(per)} tickers")
    for t, n in per.items():
        col = mc[t][mask[t]]
        print(f"   {t:6s} n={int(n):5d}  {col.min()/1e9:12.6f}bn..{col.max()/1e9:12.4f}bn  "
              f"dates {col.index[0].date()}..{col.index[-1].date()}")
    print()

# what the TOP of the distribution actually is, by ticker — is a $60bn
# reading a real S&P 600 member or a splice?
vals = mc.stack()
top = vals.sort_values(ascending=False).head(40)
print("TOP 40 eligible-cell market caps (post-time-axis):")
for (dt, t), v in top.items():
    print(f"   {t:6s} {dt.date()}  {v/1e9:10.3f}bn")
print()
bot = vals[vals > 0].sort_values().head(40)
print("BOTTOM 40 eligible-cell market caps (post-time-axis):")
for (dt, t), v in bot.items():
    print(f"   {t:6s} {dt.date()}  {v/1e9:14.8f}bn")
