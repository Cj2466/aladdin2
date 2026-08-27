"""Independent verification that the negative production result is REAL and
not an implementation artifact. Separates: costs, total-return construction,
carry-signal validity, and the spot-vs-total-return difference."""
import sys
from datetime import date

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_9fd00b72-30a-7/backend")

import numpy as np
import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalSpec,
    fixed_universe_membership,
    run_cross_sectional_backtest,
)
from app.services.research_lab.cross_sectional_fx import (
    FX_CURRENCIES,
    FX_FINANCING_BPS_PER_YEAR,
    FX_MIN_NAMES_PER_LEG,
    FX_RANK_FRACTION,
    FX_SPREAD_BPS_ONE_WAY,
    build_fx_price_panel,
    build_fx_total_return_panel,
    build_inverse_vol_basis,
    fetch_rate_differentials,
    signal_fx_carry,
)
from app.services.research_lab.metrics import sharpe_ratio

spot, flags, missing = build_fx_price_panel(YFinanceProvider(), date.today())
rates = fetch_rate_differentials()
tr, carry_end = build_fx_total_return_panel(spot, rates)
print(f"spot panel {spot.shape}  TR panel {tr.shape}  carry_end={carry_end.date()}")

# 1. Did the TR panel actually ADD carry? Compare cumulative TR vs spot.
print("\n=== 1. TOTAL-RETURN CONSTRUCTION: did carry actually get added? ===")
sp = spot.loc[tr.index]
for c in FX_CURRENCIES:
    spot_tot = sp[c].iloc[-1] / sp[c].iloc[0] - 1
    tr_tot = tr[c].iloc[-1] / tr[c].iloc[0] - 1
    mean_diff = rates[c].loc[rates.index <= carry_end].mean()
    print(f"  {c}: spot {spot_tot:+7.2%}   total-return {tr_tot:+7.2%}   "
          f"carry added {tr_tot-spot_tot:+7.2%}   mean rate diff {mean_diff:+.2f}%/yr")

# 2. Carry signal sanity: does it rank the known high-yielders high?
print("\n=== 2. CARRY SIGNAL SANITY at a few formation dates ===")
for probe in ("2010-06-01", "2015-06-01", "2020-06-01", "2025-06-01"):
    ts = pd.Timestamp(probe)
    view_rows = tr.loc[tr.index <= ts]
    if view_rows.empty:
        continue
    sig = signal_fx_carry(CrossSectionalData(close=view_rows.iloc[-300:]),
                          rate_differentials=rates, smoothing_months=1)
    ordered = sig.sort_values(ascending=False)
    print(f"  {probe}: LONG {list(ordered.index[:3])}  SHORT {list(ordered.index[-3:])}")

# 3. Cost decomposition: gross vs net Sharpe for the best carry spec.
print("\n=== 3. GROSS vs NET: how much of the result is cost? ===")
basis = build_inverse_vol_basis(tr)
data = CrossSectionalData(close=tr, leg_weight_basis=basis)

def run(cost_bps, fin_bps, hold=126, weighting="equal", smoothing=1):
    spec = CrossSectionalSpec(
        pattern_id="probe", family="fx_carry", citation="verify",
        signal_fn=lambda h: signal_fx_carry(h, rate_differentials=rates, smoothing_months=smoothing),
        lookback_days=1260, holding_days=hold, portfolio="long_short",
        rank_fraction=FX_RANK_FRACTION, leg_weighting=weighting,
    )
    cfg = CrossSectionalConfig(cost_bps=cost_bps, financing_bps_per_year=fin_bps,
                               min_names_per_leg=FX_MIN_NAMES_PER_LEG)
    return run_cross_sectional_backtest(data, spec, cfg, fixed_universe_membership(FX_CURRENCIES))

for label, cb, fb in [("GROSS (no costs at all)", 0.0, 0.0),
                      ("spread only", FX_SPREAD_BPS_ONE_WAY, 0.0),
                      ("financing only", 0.0, FX_FINANCING_BPS_PER_YEAR),
                      ("PRODUCTION (both)", FX_SPREAD_BPS_ONE_WAY, FX_FINANCING_BPS_PER_YEAR)]:
    res = run(cb, fb)
    ann = res.daily_returns.mean() * 252
    print(f"  {label:28}: Sharpe {sharpe_ratio(res.daily_returns):+.3f}   ann.return {ann:+.3%}")

# 4. Would carry look better on SPOT only (i.e. is the TR panel helping or hurting)?
print("\n=== 4. SPOT-ONLY vs TOTAL-RETURN carry (why TR matters) ===")
basis_spot = build_inverse_vol_basis(sp)
data_spot = CrossSectionalData(close=sp, leg_weight_basis=basis_spot)
spec = CrossSectionalSpec(
    pattern_id="probe", family="fx_carry", citation="verify",
    signal_fn=lambda h: signal_fx_carry(h, rate_differentials=rates, smoothing_months=1),
    lookback_days=1260, holding_days=126, portfolio="long_short",
    rank_fraction=FX_RANK_FRACTION, leg_weighting="equal",
)
cfg0 = CrossSectionalConfig(cost_bps=0.0, financing_bps_per_year=0.0,
                            min_names_per_leg=FX_MIN_NAMES_PER_LEG)
r_spot = run_cross_sectional_backtest(data_spot, spec, cfg0, fixed_universe_membership(FX_CURRENCIES))
r_tr = run_cross_sectional_backtest(data, spec, cfg0, fixed_universe_membership(FX_CURRENCIES))
print(f"  SPOT-only  gross Sharpe {sharpe_ratio(r_spot.daily_returns):+.3f}  "
      f"ann {r_spot.daily_returns.mean()*252:+.3%}")
print(f"  TOTAL-ret  gross Sharpe {sharpe_ratio(r_tr.daily_returns):+.3f}  "
      f"ann {r_tr.daily_returns.mean()*252:+.3%}")
print("  (the difference IS the carry the trade actually earns — omitting it")
print("   would have tested the Fama regression, not the carry trade)")

# 5. Sub-period stability of the best carry spec.
print("\n=== 5. SUB-PERIOD Sharpe of production carry (s1,h126,equal) ===")
res = run(FX_SPREAD_BPS_ONE_WAY, FX_FINANCING_BPS_PER_YEAR)
dr = res.daily_returns
for lo, hi in [("2011-01-01", "2015-01-01"), ("2015-01-01", "2019-01-01"),
               ("2019-01-01", "2023-01-01"), ("2023-01-01", "2026-12-31")]:
    seg = dr.loc[(dr.index >= lo) & (dr.index < hi)]
    if len(seg) > 60:
        print(f"  {lo[:4]}-{hi[:4]}: n={len(seg):5d}  Sharpe {sharpe_ratio(seg):+.3f}")

# 6. Was the scrub load-bearing for the RESULT (not just for vol)?
print("\n=== 6. Did the bad-print scrub change the answer? ===")
raw_spot_unscrubbed = spot.copy()
print(f"  (scrub removed {int(flags.to_numpy().sum())} cells; panel has {spot.notna().sum().sum()} valid)")
print("  Re-running production carry on an UNSCRUBBED panel:")
import app.services.research_lab.cross_sectional_fx as fx
raw_panel, _, _ = build_fx_price_panel(YFinanceProvider(), date.today())
# rebuild without scrub by re-deriving the panel pre-scrub
frames, _ = YFinanceProvider().get_daily_ohlcv([t for t, _ in fx.FX_PAIRS.values()],
                                               fx.FX_PRICE_HISTORY_START, date.today())
cols = {}
for cur, (tk, inv) in fx.FX_PAIRS.items():
    s = pd.to_numeric(frames["close"][tk], errors="coerce").where(lambda x: x > 0)
    cols[cur] = 1.0 / s if inv else s
unscrubbed = pd.DataFrame(cols).sort_index().dropna(how="any")
tr_un, _ = build_fx_total_return_panel(unscrubbed, rates)
data_un = CrossSectionalData(close=tr_un, leg_weight_basis=build_inverse_vol_basis(tr_un))
cfg = CrossSectionalConfig(cost_bps=FX_SPREAD_BPS_ONE_WAY,
                           financing_bps_per_year=FX_FINANCING_BPS_PER_YEAR,
                           min_names_per_leg=FX_MIN_NAMES_PER_LEG)
r_un = run_cross_sectional_backtest(data_un, spec, cfg, fixed_universe_membership(FX_CURRENCIES))
print(f"  UNSCRUBBED Sharpe {sharpe_ratio(r_un.daily_returns):+.3f}")
print(f"  SCRUBBED   Sharpe {sharpe_ratio(res.daily_returns):+.3f}")
