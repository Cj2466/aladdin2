"""Independent verify: recompute financing from first principles, without
reusing any harness helper, and compare against the harness's own number."""
import sys
import numpy as np, pandas as pd
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig, CrossSectionalData, CrossSectionalSpec,
    run_cross_sectional_backtest, fixed_universe_membership,
)

ALWAYS = lambda t, d: True
idx = pd.bdate_range("2024-01-01", periods=16)
close = pd.DataFrame({t: 100.0*np.cumprod(np.full(16, 1.0+r))
                      for t, r in {"A": 0.01, "B": -0.01}.items()}, index=idx)
spec = CrossSectionalSpec(pattern_id="s", family="f", citation="c",
    signal_fn=lambda v: v.close.iloc[-1], lookback_days=10, holding_days=5,
    portfolio="long_short", rank_fraction=0.5)

RATE_BPS = 137.5   # deliberately not a round number
res = run_cross_sectional_backtest(CrossSectionalData(close=close), spec,
        CrossSectionalConfig(cost_bps=5.0, min_names_per_leg=1, financing_bps_per_year=RATE_BPS), ALWAYS)

# --- independent recomputation ---
GROSS = 2.0  # +1.0 A long, -1.0 B short
per_day = (RATE_BPS/10_000.0) * GROSS / 365.0
expected_daily, expected_total = {}, 0.0
for j in range(11, 16):
    d = (idx[j]-idx[j-1]).days
    expected_daily[idx[j]] = per_day*d
    expected_total += per_day*d

print("calendar-day gaps :", [(idx[j].day_name()[:3], (idx[j]-idx[j-1]).days) for j in range(11,16)])
print("independent total :", expected_total)
print("harness total     :", res.total_financing_cost)
print("MATCH total       :", abs(expected_total-res.total_financing_cost) < 1e-15)
print("closed form rate*gross*span/365:", (RATE_BPS/10_000.0)*GROSS*(idx[15]-idx[10]).days/365.0)

# per-day: net must equal gross_ret - cost - financing
zero = run_cross_sectional_backtest(CrossSectionalData(close=close), spec,
        CrossSectionalConfig(cost_bps=5.0, min_names_per_leg=1), ALWAYS)
ok = True
for j in range(11, 16):
    delta = zero.daily_returns.loc[idx[j]] - res.daily_returns.loc[idx[j]]
    if abs(delta - expected_daily[idx[j]]) > 1e-15:
        ok = False; print("  MISMATCH", idx[j].date(), delta, expected_daily[idx[j]])
print("MATCH per-day     :", ok, "(financing is the ONLY difference vs the 0.0 run)")

# --- fixed_universe_membership independent check ---
fx = ["EURUSD=X","GBPUSD=X","USDJPY=X","AUDUSD=X","USDCAD=X"]
m = fixed_universe_membership(fx)
import datetime, random
random.seed(0)
alldates = all(m(t, datetime.date(random.randint(1900,2100), random.randint(1,12), random.randint(1,28)))
               for t in fx for _ in range(200))
print("FX basket eligible on 1000 random dates 1900-2100:", alldates)
print("non-member rejected:", m("SPY", datetime.date(2024,1,1)) is False)
