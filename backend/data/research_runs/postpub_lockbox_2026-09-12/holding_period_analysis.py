#!/usr/bin/env python
"""Does holding longer preserve more of the edge? (owner's question, 2026-09-13)

A descriptive cut of the ALREADY-COMPUTED sealed-window series (same rules as
PROTOCOL_SET3_BUILDABLE.md and its declared extension: post-publication months,
>=36 sealed months, P-clean membership). No new window, no selection, no verdict.

The number that decides a strategy's fate is EDGE PER TRADE vs COST PER TRADE.
For a predictor rebalanced every P months:
    gross edge per holding period = mean gross monthly return x P
    cost per round trip           = 4 legs x 5bp = 20bp = 0.20%  (this project's flat one-way rate)
    ratio                         = edge per trade / cost per trade
A ratio below 1 means costs eat the whole edge; the target discussed with the
owner is 3-5x. GROSS is used for the edge so the comparison is NOT circular --
the haircut itself is 20/P per month and would mechanically favour slow holders.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from osap_lockbox import MIN_SEALED_MONTHS, load, stats

COST_PER_ROUND_TRIP_PCT = 0.20  # 4 legs x 5bp


def main() -> int:
    ret, doc = load()
    clean = [x for x in ret.columns if doc.loc[x, "Predictability in OP"] in ("1_clear", "2_likely")
             and doc.loc[x, "Signal Rep Quality"] in ("1_good", "2_fair")]
    rows = []
    for a in clean:
        y0 = int(doc.loc[a, "Year"]) + 1
        s = ret.loc[ret.index.year >= y0, a].dropna()           # GROSS sealed months
        if len(s) < MIN_SEALED_MONTHS:
            continue
        p = doc.loc[a, "Portfolio Period"]
        p = 1.0 if pd.isna(p) or p <= 0 else float(p)
        st = stats(s)
        edge_per_trade = float(s.mean()) * p                     # percent per holding period
        rows.append({"acronym": a, "holding_months": p, "n_months": st["n_months"],
                     "gross_monthly_pct": float(s.mean()),
                     "gross_sharpe": st["sharpe_annualized"],
                     "edge_per_trade_pct": edge_per_trade,
                     "edge_over_cost": edge_per_trade / COST_PER_ROUND_TRIP_PCT,
                     "buildable": doc.loc[a, "Cat.Data"] in {"Accounting", "Price", "Trading", "13F", "Event"}})
    t = pd.DataFrame(rows)
    out = {"cost_per_round_trip_pct": COST_PER_ROUND_TRIP_PCT, "predictors": len(t), "by_holding_period": []}
    for p, g in t.groupby("holding_months"):
        out["by_holding_period"].append({
            "holding_months": p, "n_predictors": len(g),
            "median_gross_sharpe": float(g.gross_sharpe.median()),
            "median_edge_per_trade_pct": float(g.edge_per_trade_pct.median()),
            "median_edge_over_cost": float(g.edge_over_cost.median()),
            "share_edge_over_cost_ge_1": float((g.edge_over_cost >= 1).mean()),
            "share_edge_over_cost_ge_3": float((g.edge_over_cost >= 3).mean()),
            "share_gross_sharpe_positive": float((g.gross_sharpe > 0).mean()),
        })
    # equal-weight pooled book per holding bucket, gross
    for rec in out["by_holding_period"]:
        members = t[t.holding_months == rec["holding_months"]].acronym.tolist()
        cols = []
        for a in members:
            y0 = int(doc.loc[a, "Year"]) + 1
            cols.append(ret.loc[ret.index.year >= y0, a].dropna().rename(a))
        pool = pd.concat(cols, axis=1).mean(axis=1)
        rec["pooled_gross_sharpe"] = stats(pool)["sharpe_annualized"]
        rec["pooled_n_months"] = stats(pool)["n_months"]
        # net: the same 20/P bps-per-month haircut the lockbox used
        haircut = COST_PER_ROUND_TRIP_PCT / rec["holding_months"]
        rec["pooled_net_sharpe"] = stats(pool - haircut)["sharpe_annualized"]
        rec["haircut_pct_per_month"] = haircut
    t.sort_values("edge_over_cost", ascending=False).to_csv(HERE / "holding_period_per_predictor.csv", index=False)
    (HERE / "holding_period_output.json").write_text(json.dumps(out, indent=1, default=str))
    print(f"{'hold(m)':>8} {'n':>4} {'med gross SR':>13} {'edge/trade %':>13} {'edge/cost':>10} {'>=1x':>6} {'>=3x':>6} {'pooled gross':>13} {'pooled net':>11}")
    for r in out["by_holding_period"]:
        print(f"{r['holding_months']:8.0f} {r['n_predictors']:4d} {r['median_gross_sharpe']:13.3f} "
              f"{r['median_edge_per_trade_pct']:13.3f} {r['median_edge_over_cost']:10.2f} "
              f"{r['share_edge_over_cost_ge_1']*100:5.0f}% {r['share_edge_over_cost_ge_3']*100:5.0f}% "
              f"{r['pooled_gross_sharpe']:13.3f} {r['pooled_net_sharpe']:11.3f}")
    print(f"\nall predictors: median edge/cost {t.edge_over_cost.median():.2f}, "
          f"{(t.edge_over_cost>=1).mean()*100:.0f}% clear 1x, {(t.edge_over_cost>=3).mean()*100:.0f}% clear 3x")
    print("np check:", np.isfinite(t.edge_over_cost).all())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
