#!/usr/bin/env python
"""Set 3 (PROTOCOL_SET3_BUILDABLE.md @ 2881420): per-predictor sealed statistics,
the buildable book, pairwise rho, and a ranking. Same sealed rules as
osap_lockbox.py (post-publication months, 20/P bps haircut, >=36 months, P-clean).
"""
from __future__ import annotations

import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from osap_lockbox import MIN_SEALED_MONTHS, load, stats

BUILDABLE = {"Accounting", "Price", "Trading", "13F", "Event"}
NOT_BUILDABLE = {"Analyst", "Options", "Other"}
COST_BPS_ONE_WAY = 5.0
MIN_RHO_OVERLAP = 120


def sealed_series(ret: pd.DataFrame, doc: pd.DataFrame, a: str) -> pd.Series | None:
    y0 = int(doc.loc[a, "Year"]) + 1
    s = ret.loc[ret.index.year >= y0, a].dropna()
    if len(s) < MIN_SEALED_MONTHS:
        return None
    p = doc.loc[a, "Portfolio Period"]
    p = 1.0 if pd.isna(p) or p <= 0 else float(p)
    return s - 4 * COST_BPS_ONE_WAY / p / 100.0


def main() -> int:
    ret, doc = load()
    clean = [x for x in ret.columns if doc.loc[x, "Predictability in OP"] in ("1_clear", "2_likely")
             and doc.loc[x, "Signal Rep Quality"] in ("1_good", "2_fair")]
    series = {a: s for a in clean if (s := sealed_series(ret, doc, a)) is not None}
    rows = []
    for a, s in series.items():
        st = stats(s)
        rows.append({"acronym": a, "cat_data": doc.loc[a, "Cat.Data"], "cat_economic": doc.loc[a, "Cat.Economic"],
                     "buildable": doc.loc[a, "Cat.Data"] in BUILDABLE, "pub_year": int(doc.loc[a, "Year"]),
                     "sample_end": int(doc.loc[a, "SampleEndYear"]), "portfolio_period_m": doc.loc[a, "Portfolio Period"],
                     "n_sealed_months": st["n_months"], "sealed_sharpe_after_haircut": st["sharpe_annualized"],
                     "nw_t": st["newey_west_t_6"], "authors": doc.loc[a, "Authors"], "long_description": str(doc.loc[a, "LongDescription"])[:120]})
    table = pd.DataFrame(rows).sort_values("sealed_sharpe_after_haircut", ascending=False)
    table.to_csv(HERE / "set3_per_predictor.csv", index=False)
    build = [a for a in series if doc.loc[a, "Cat.Data"] in BUILDABLE]
    nonb = [a for a in series if a not in build]
    pool_b = pd.concat([series[a].rename(a) for a in build], axis=1).mean(axis=1)
    pool_n = pd.concat([series[a].rename(a) for a in nonb], axis=1).mean(axis=1)
    rhos = []
    for a, b in combinations(build, 2):
        j = pd.concat([series[a], series[b]], axis=1, join="inner").dropna()
        if len(j) >= MIN_RHO_OVERLAP:
            rhos.append(float(j.iloc[:, 0].corr(j.iloc[:, 1])))
    jp = pd.concat([pool_b.rename("b"), pool_n.rename("n")], axis=1, join="inner").dropna()
    out = {"protocol": "PROTOCOL_SET3_BUILDABLE.md @ 2881420", "p_clean_sealed": len(series),
           "buildable_count": len(build), "not_buildable_count": len(nonb),
           "buildable_by_cat_data": {k: int(v) for k, v in table[table.buildable].cat_data.value_counts().items()},
           "buildable_book": stats(pool_b), "not_buildable_book": stats(pool_n),
           "rho_pairs": len(rhos), "rho_mean": float(np.mean(rhos)), "rho_abs_mean": float(np.mean(np.abs(rhos))),
           "rho_share_abs_ge_0.30": float(np.mean([abs(r) >= 0.30 for r in rhos])),
           "rho_buildable_vs_not_pools": float(jp.b.corr(jp.n)), "rho_pools_overlap_months": len(jp),
           "buildable_median_sealed_sharpe": float(table[table.buildable].sealed_sharpe_after_haircut.median()),
           "buildable_share_positive": float((table[table.buildable].sealed_sharpe_after_haircut > 0).mean()),
           "top15_buildable": table[table.buildable].head(15)[["acronym", "cat_data", "cat_economic", "pub_year", "n_sealed_months", "sealed_sharpe_after_haircut", "nw_t"]].to_dict("records")}
    (HERE / "set3_output.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if k != "top15_buildable"}, indent=1, default=str))
    print(table[table.buildable].head(15)[["acronym", "cat_data", "pub_year", "n_sealed_months", "sealed_sharpe_after_haircut", "nw_t"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
