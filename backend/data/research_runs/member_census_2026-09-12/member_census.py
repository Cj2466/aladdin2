#!/usr/bin/env python
"""Day-1 member census (2026-09-12): how correlated are the 20 candidate BOOK
members (16 Dormant + 4 Active), and what does that imply for the pooled
Sharpe the BOOK could show?

Inputs, all already committed:
  * data/research_runs/dormant_pool_2026-09-09/dormant_pool_manifest.json  (16 frozen specs)
  * the four Active registrations' pattern ids, read from their registration modules
  * data/research_runs/global_effective_n_return_matrix_2026-09-05.csv.gz  (per-spec net daily
    returns captured by run_global_effective_n.py on 2026-09-05; PRE-DATES the 2026-09-09 price
    store repair, so three tickers' fabricated days are still inside the equity series)
  * captured_<family>_2026-09-05.csv for the two families built after that run (see
    capture_missing_two.py); if absent they are reported as missing, not invented.

Outputs (same folder): member_census_pairwise_rho.csv, member_census_summary.json.
Formula for the pooled Sharpe uses the BOOK pre-registration's own identity
Sharpe_pool ~= s * sqrt(M / (1 + (M-1) rho)) (book.py header, one common factor); it is an
approximation and is labelled as such in the output.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
sys.path.insert(0, str(BACKEND))

from app.services.research_lab.bab_forward_registration import (
    BAB_FAMILY_KEY,
    BAB_PATTERN_ID,
)
from app.services.research_lab.lazy_prices_forward_registration import (
    LAZY_PRICES_PATTERN_ID,
)
from app.services.research_lab.quality_forward_registration import (
    CBOP_PATTERN_ID,
)
from app.services.research_lab.short_interest_forward_registration import (
    SHORT_INTEREST_PATTERN_ID,
)

MIN_OVERLAP = 252  # one year of common days before a pairwise rho is reported


def main() -> int:
    manifest = json.loads((BACKEND / "data/research_runs/dormant_pool_2026-09-09/dormant_pool_manifest.json").read_text())
    members: list[tuple[str, str, str]] = [(e["family_key"], e["pattern_id"], "Dormant") for e in manifest["entries"]]
    members += [
        ("quality_cbop", CBOP_PATTERN_ID, "Active"),
        ("lazy_prices", LAZY_PRICES_PATTERN_ID, "Active"),
        ("short_interest", SHORT_INTEREST_PATTERN_ID, "Active"),
        (BAB_FAMILY_KEY, BAB_PATTERN_ID, "Active"),
    ]
    assert len(members) == 20, len(members)

    matrix = pd.read_csv(BACKEND / "data/research_runs/global_effective_n_return_matrix_2026-09-05.csv.gz", index_col=0, parse_dates=True)
    series: dict[str, pd.Series] = {}
    source: dict[str, str] = {}
    for fam, pid, _ in members:
        key = f"{fam}/{pid}"
        if pid in matrix.columns:
            series[key] = matrix[pid].dropna()
            source[key] = "global_effective_n_return_matrix_2026-09-05"
            continue
        cap = HERE / f"captured_{fam}_2026-09-05.csv"
        if cap.exists():
            df = pd.read_csv(cap, index_col=0, parse_dates=True)
            if pid in df.columns:
                series[key] = df[pid].dropna()
                source[key] = cap.name
                continue
        source[key] = "MISSING"

    keys = [f"{f}/{p}" for f, p, _ in members]
    have = [k for k in keys if k in series]
    rows = []
    for i, a in enumerate(have):
        for b in have[i + 1 :]:
            joined = pd.concat([series[a], series[b]], axis=1, join="inner").dropna()
            n = len(joined)
            rho = float(joined.iloc[:, 0].corr(joined.iloc[:, 1])) if n >= MIN_OVERLAP else float("nan")
            rows.append({"a": a, "b": b, "overlap_days": n, "rho": rho})
    pw = pd.DataFrame(rows)
    pw.to_csv(HERE / "member_census_pairwise_rho.csv", index=False)

    valid = pw.dropna(subset=["rho"])
    rho_mean = float(valid["rho"].mean())
    rho_abs_mean = float(valid["rho"].abs().mean())
    top = valid.reindex(valid["rho"].abs().sort_values(ascending=False).index).head(10)

    per_member = {}
    for k in have:
        s = series[k]
        ann = 252.0 if not k.startswith("crypto") else 365.0
        per_member[k] = {
            "n_days": len(s),
            "start": s.index.min().date().isoformat(),
            "end": s.index.max().date().isoformat(),
            "sharpe_full_series_annualized": float(s.mean() / s.std() * np.sqrt(ann)) if s.std() > 0 else None,
            "periods_per_year_assumed": ann,
        }

    m = len(have)
    def pooled(s: float, rho: float, mm: int) -> float:
        return s * np.sqrt(mm / (1.0 + (mm - 1) * rho))

    summary = {
        "members_total": 20,
        "members_with_series": m,
        "members_missing": [k for k in keys if k not in series],
        "series_source": source,
        "min_overlap_days_for_rho": MIN_OVERLAP,
        "pairs_total": len(pw),
        "pairs_with_rho": len(valid),
        "rho_mean": rho_mean,
        "rho_abs_mean": rho_abs_mean,
        "rho_max_abs_pair": top.iloc[0].to_dict() if len(top) else None,
        "top10_abs_rho_pairs": top.to_dict(orient="records"),
        "pooled_sharpe_approx_note": "s*sqrt(M/(1+(M-1)rho)) with rho = rho_mean; an approximation (single common factor), NOT a measurement of the BOOK",
        "pooled_sharpe_if_each_member_true_sharpe_0.3": {
            "M_available": pooled(0.3, max(rho_mean, 0.0), m),
            "M_20": pooled(0.3, max(rho_mean, 0.0), 20),
            "M_30": pooled(0.3, max(rho_mean, 0.0), 30),
        },
        "per_member": per_member,
    }
    (HERE / "member_census_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps({k: v for k, v in summary.items() if k not in ("per_member", "series_source", "top10_abs_rho_pairs")}, indent=2, default=str))
    print("top pairs:")
    print(top.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
