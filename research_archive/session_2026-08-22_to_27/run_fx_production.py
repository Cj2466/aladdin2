"""REAL production screening of the FX cross-sectional family against live
yfinance + FRED data. Reports EVERY spec, not a cherry-picked subset."""
import sys
from datetime import date

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_9fd00b72-30a-7/backend")

import numpy as np
import pandas as pd

from app.services.research_lab.cross_sectional_fx import (
    FX_N_TRIALS,
    screen_fx_family,
)

TODAY = date.today()
print(f"=== FX CROSS-SECTIONAL PRODUCTION SCREENING — run {TODAY} ===\n")

summary = screen_fx_family(end=TODAY)

print("--- DISCLOSURE ---")
print(summary.text)
print()
if summary.warnings:
    print("--- WARNINGS ---")
    for w in summary.warnings:
        print(" *", w)
    print()

print("--- RUN FACTS ---")
print(f"pre-declared n_trials       : {summary.n_trials} (module constant FX_N_TRIALS={FX_N_TRIALS})")
print(f"panel                       : {summary.n_panel_rows} rows, {summary.panel_start} .. {summary.panel_end}")
print(f"carry data ends             : {summary.carry_data_end}")
print(f"carry publication lag       : {summary.carry_publication_lag_months} months")
print(f"leg size (tercile)          : {summary.leg_size}")
print(f"missing price data          : {summary.missing_price_data}")
print(f"bad prints scrubbed         : {summary.n_bad_prints_scrubbed}")
print(f"  by currency               : {summary.bad_prints_by_currency}")
print(f"specs surviving data floors : {len(summary.results)} of {summary.n_trials}")
print()

if not summary.results:
    print("NO RESULTS — nothing survived the data floors.")
    sys.exit(0)

rows = []
for r in summary.results:
    d = r.deflated_sharpe
    rows.append({
        "pattern_id": r.pattern_id,
        "family": r.family,
        "sharpe": r.sharpe_annualized,
        "n_days": r.n_trading_days,
        "n_form": r.n_formations,
        "n_skip": r.n_skipped_formations,
        "leg": r.avg_names_per_leg,
        "trade_cost": r.total_cost_drag,
        "fin_drag": r.total_financing_drag,
        "psr0": d.psr_vs_zero,
        "dsr": d.dsr,
        "dsr_ok": d.dsr_floor_met,
        "n_trials": d.n_trials,
        "fallbacks": f"{r.n_value_weight_fallbacks}/{r.n_value_weighted_legs}",
    })
df = pd.DataFrame(rows)

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 40)
pd.set_option("display.max_rows", 100)

print("--- EVERY SPEC, RANKED BY SHARPE (nothing omitted) ---")
show = df.copy()
show["sharpe"] = show["sharpe"].round(3)
show["leg"] = show["leg"].round(2)
show["trade_cost"] = show["trade_cost"].round(5)
show["fin_drag"] = show["fin_drag"].round(5)
show["psr0"] = show["psr0"].apply(lambda v: round(v, 4) if v is not None else None)
show["dsr"] = show["dsr"].apply(lambda v: round(v, 4) if v is not None else None)
print(show.to_string(index=False))
print()

print("--- SUMMARY STATISTICS ACROSS ALL 36 ---")
print(f"  best Sharpe   : {df['sharpe'].max():+.3f}  ({df.loc[df['sharpe'].idxmax(), 'pattern_id']})")
print(f"  worst Sharpe  : {df['sharpe'].min():+.3f}  ({df.loc[df['sharpe'].idxmin(), 'pattern_id']})")
print(f"  median Sharpe : {df['sharpe'].median():+.3f}")
print(f"  mean Sharpe   : {df['sharpe'].mean():+.3f}")
print(f"  std of Sharpes: {df['sharpe'].std(ddof=1):.3f}   <-- the DSR's sigma_sr input")
print(f"  # positive    : {(df['sharpe'] > 0).sum()} of {len(df)}")
print(f"  # DSR > 0.95  : {(df['dsr'].fillna(0) > 0.95).sum()}")
print(f"  # DSR > 0.99  : {(df['dsr'].fillna(0) > 0.99).sum()}")
print(f"  max DSR       : {df['dsr'].max():.4f}")
print()

print("--- BY SIGNAL FAMILY ---")
g = df.groupby("family")["sharpe"].agg(["count", "mean", "min", "max"]).round(3)
print(g.to_string())
print()

print("--- BY HOLD AND WEIGHTING ---")
df["hold"] = df["pattern_id"].str.extract(r"_h(\d+)_")[0].astype(int)
df["weighting"] = np.where(df["pattern_id"].str.endswith("inverse_vol"), "inverse_vol", "equal")
print(df.groupby("hold")["sharpe"].agg(["count", "mean", "min", "max"]).round(3).to_string())
print()
print(df.groupby("weighting")["sharpe"].agg(["count", "mean", "min", "max"]).round(3).to_string())
print()

print("--- COST DECOMPOSITION (is financing really dominant?) ---")
print(f"  mean total turnover cost over the replay : {df['trade_cost'].mean():.5f}")
print(f"  mean total financing drag over the replay: {df['fin_drag'].mean():.5f}")
print(f"  ratio financing/turnover                 : {df['fin_drag'].mean()/df['trade_cost'].mean():.2f}x")
for hold in sorted(df["hold"].unique()):
    sub = df[df["hold"] == hold]
    print(f"    hold={hold}: turnover={sub['trade_cost'].mean():.5f}  financing={sub['fin_drag'].mean():.5f}")
print()

df.to_csv("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/fx_production_results.csv", index=False)
print("full results saved to scratchpad/fx_production_results.csv")
