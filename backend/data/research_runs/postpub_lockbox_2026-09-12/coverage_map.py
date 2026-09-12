#!/usr/bin/env python
"""Declared extension of PROTOCOL_SET3_BUILDABLE.md (@4c17e89): is the buildable
set many different bets, or one bet under many names?

Same sealed rules as osap_lockbox.py / set3_buildable.py: post-publication months,
20/P bps haircut, >=36 sealed months, P-clean membership. Descriptive only.
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
from osap_lockbox import load, stats
from set3_buildable import BUILDABLE, sealed_series

MIN_PER_CATEGORY = 3
MIN_OVERLAP = 120


def main() -> int:
    ret, doc = load()
    clean = [x for x in ret.columns if doc.loc[x, "Predictability in OP"] in ("1_clear", "2_likely")
             and doc.loc[x, "Signal Rep Quality"] in ("1_good", "2_fair")]
    series = {a: s for a in clean if (s := sealed_series(ret, doc, a)) is not None}
    build = {a: s for a, s in series.items() if doc.loc[a, "Cat.Data"] in BUILDABLE}
    cats: dict[str, list[str]] = {}
    for a in build:
        cats.setdefault(str(doc.loc[a, "Cat.Economic"]), []).append(a)
    pools = {}
    for cat, members in sorted(cats.items()):
        if len(members) < MIN_PER_CATEGORY:
            continue
        pool = pd.concat([build[m].rename(m) for m in members], axis=1).mean(axis=1)
        pools[cat] = pool
    rows = []
    for cat, pool in pools.items():
        st = stats(pool)
        rows.append({"category": cat, "members": len(cats[cat]), "n_months": st["n_months"],
                     "sharpe": st["sharpe_annualized"], "nw_t": st["newey_west_t_6"]})
    table = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    names = list(pools)
    corr = pd.DataFrame(index=names, columns=names, dtype=float)
    pairs = []
    for a, b in combinations(names, 2):
        j = pd.concat([pools[a], pools[b]], axis=1, join="inner").dropna()
        r = float(j.iloc[:, 0].corr(j.iloc[:, 1])) if len(j) >= MIN_OVERLAP else float("nan")
        corr.loc[a, b] = corr.loc[b, a] = r
        pairs.append(r)
    for a in names:
        corr.loc[a, a] = 1.0
    panel = pd.concat([pools[a].rename(a) for a in names], axis=1, join="inner").dropna()
    # Effective number of independent bets among the category pools: if the K pools
    # were uncorrelated and equally variable, an equal-weight average would have
    # variance avg_var / K, so M_eff = avg_var / var(equal-weight pool). K when
    # independent, 1 when perfectly correlated.
    cov = panel.cov().values
    weights = np.ones(len(names)) / len(names)
    var_pool = float(weights @ cov @ weights)
    avg_var = float(np.mean(np.diag(cov)))
    m_eff = avg_var / var_pool
    out = {"protocol": "PROTOCOL_SET3_BUILDABLE.md declared extension @4c17e89",
           "categories_with_pools": len(names), "min_members_per_category": MIN_PER_CATEGORY,
           "pool_table": table.to_dict("records"),
           "pairwise_rho_between_category_pools": {"n_pairs": int(np.sum(~np.isnan(pairs))),
                                                   "mean": float(np.nanmean(pairs)),
                                                   "abs_mean": float(np.nanmean(np.abs(pairs))),
                                                   "max": float(np.nanmax(pairs)), "min": float(np.nanmin(pairs)),
                                                   "share_abs_ge_0.30": float(np.nanmean(np.abs(pairs) >= 0.30))},
           "effective_number_of_independent_category_bets": m_eff,
           "common_months_used_for_matrix": len(panel)}
    corr.to_csv(HERE / "coverage_map_category_corr.csv")
    (HERE / "coverage_map_output.json").write_text(json.dumps(out, indent=1, default=str))
    print(table.to_string(index=False))
    print(json.dumps({k: v for k, v in out.items() if k != "pool_table"}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
