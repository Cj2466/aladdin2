#!/usr/bin/env python
"""Set 2 lockbox — the 212 Open Source Asset Pricing predictors, exactly as
LOCKBOX_PROTOCOL_OSAP.md declares (commit cd8d029). Run ONCE with --look.

--check-only: in-sample checks only (return units vs the doc's Return column;
sign orientation). Touches no sealed month.
--look:       the single look. Writes osap_lockbox_output.json and .txt.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
sys.path.insert(0, str(BACKEND))

from app.services.research_lab.deflated_sharpe import (
    probabilistic_sharpe_ratio,
)

MIN_SEALED_MONTHS = 36
COST_BPS_ONE_WAY = 5.0  # cross_sectional.DEFAULT_XS_COST_BPS


def load():
    ret = pd.read_csv(HERE / "osap/osap_ls_returns_wide.csv", parse_dates=["date"]).set_index("date")
    doc = pd.read_csv(HERE / "osap/osap_signal_doc.csv")
    doc = doc[doc["Cat.Signal"] == "Predictor"].set_index("Acronym")
    common = [c for c in ret.columns if c in doc.index]
    return ret[common], doc.loc[common]


def newey_west_t(x: np.ndarray, lags: int = 6) -> float:
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 3:
        return float("nan")
    m = x.mean()
    e = x - m
    s = (e * e).sum() / n
    for lag in range(1, lags + 1):
        w = 1 - lag / (lags + 1)
        s += 2 * w * (e[lag:] * e[:-lag]).sum() / n
    return float(m / np.sqrt(s / n))


def in_sample_checks(ret: pd.DataFrame, doc: pd.DataFrame) -> dict:
    out = {}
    for a in ret.columns:
        end = int(doc.loc[a, "SampleEndYear"])
        ins = ret.loc[ret.index.year <= end, a].dropna()
        out[a] = {
            "in_sample_months": len(ins),
            "in_sample_mean_pct_per_month": float(ins.mean()) if len(ins) else None,
            "doc_return": float(doc.loc[a, "Return"]) if pd.notna(doc.loc[a, "Return"]) else None,
            "sign_ok": bool(ins.mean() > 0) if len(ins) else None,
        }
    n_ok = sum(1 for v in out.values() if v["sign_ok"])
    ratio = [v["in_sample_mean_pct_per_month"] / v["doc_return"] for v in out.values()
             if v["doc_return"] and v["in_sample_mean_pct_per_month"] is not None and v["doc_return"] != 0]
    return {"predictors": len(out), "positive_in_sample_mean": n_ok,
            "median_ratio_insample_mean_to_doc_return": float(np.median(ratio)) if ratio else None,
            "detail": out}


def stats(series: pd.Series) -> dict:
    s = series.dropna()
    if len(s) < 12:
        return {"n_months": len(s)}
    r = s.values / 100.0  # percent -> decimal
    sharpe_m = float(r.mean() / r.std(ddof=1))
    ann = float(sharpe_m * np.sqrt(12))
    # per-period inputs, as the function's contract requires (monthly sr, n months, sample moments)
    psr = probabilistic_sharpe_ratio(sharpe_m, 0.0, len(r), float(sps.skew(r)), float(sps.kurtosis(r, fisher=False)))
    return {"n_months": len(s), "start": str(s.index.min())[:7], "end": str(s.index.max())[:7],
            "mean_pct_per_month": float(s.mean()), "sharpe_annualized": ann,
            "newey_west_t_6": newey_west_t(r), "psr_vs_0": psr}


def pooled(ret: pd.DataFrame, doc: pd.DataFrame, members: list[str], start_col: str, cost_mult: float) -> tuple[pd.Series, dict]:
    cols = []
    excluded = []
    per = {}
    for a in members:
        start_year = int(doc.loc[a, start_col]) + 1
        s = ret.loc[ret.index.year >= start_year, a].dropna()
        if len(s) < MIN_SEALED_MONTHS:
            excluded.append(a)
            continue
        p = doc.loc[a, "Portfolio Period"]
        p = 1.0 if pd.isna(p) or p <= 0 else float(p)
        haircut = cost_mult * 4 * COST_BPS_ONE_WAY / p / 100.0  # bps -> percent per month
        s = s - haircut
        cols.append(s.rename(a))
        per[a] = stats(s)
    panel = pd.concat(cols, axis=1)
    pool = panel.mean(axis=1)
    per_sh = [v["sharpe_annualized"] for v in per.values() if "sharpe_annualized" in v]
    return pool, {"members_in": len(cols), "excluded_lt_36_sealed_months": excluded,
                  "per_predictor_sealed_sharpe_median": float(np.median(per_sh)) if per_sh else None,
                  "per_predictor_share_positive": float(np.mean([x > 0 for x in per_sh])) if per_sh else None,
                  "per_predictor": per}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--look", action="store_true")
    a = ap.parse_args()
    ret, doc = load()
    checks = in_sample_checks(ret, doc)
    if a.check_only or not a.look:
        print(json.dumps({k: v for k, v in checks.items() if k != "detail"}, indent=1))
        (HERE / "osap_in_sample_checks.json").write_text(json.dumps(checks, indent=1))
        return 0
    if (HERE / "osap_lockbox_output.json").exists():
        print("REFUSING: the look has already been taken (osap_lockbox_output.json exists).")
        return 1
    clean = [x for x in ret.columns if doc.loc[x, "Predictability in OP"] in ("1_clear", "2_likely")
             and doc.loc[x, "Signal Rep Quality"] in ("1_good", "2_fair")]
    out = {"protocol": "LOCKBOX_PROTOCOL_OSAP.md @ cd8d029", "in_sample_checks": {k: v for k, v in checks.items() if k != "detail"},
           "pools": {}}
    lines = []
    for pool_name, members in (("P-all", list(ret.columns)), ("P-clean", clean)):
        for win_name, col in (("post_publication", "Year"), ("post_sample", "SampleEndYear")):
            for cost_name, mult in (("gross", 0.0), ("standard_haircut", 1.0), ("doubled_haircut", 2.0)):
                pool, meta = pooled(ret, doc, members, col, mult)
                st = stats(pool)
                # decay ratio vs in-sample of the same members (gross, same members)
                ins = []
                for m in members:
                    if m in meta["per_predictor"]:
                        end = int(doc.loc[m, "SampleEndYear"])
                        ins.append(ret.loc[ret.index.year <= end, m].dropna().rename(m))
                ins_pool = pd.concat(ins, axis=1).mean(axis=1) if ins else pd.Series(dtype=float)
                ins_st = stats(ins_pool)
                key = f"{pool_name}|{win_name}|{cost_name}"
                out["pools"][key] = {"stats": st, "in_sample_pool_stats": ins_st,
                                     "decay_ratio": (st.get("sharpe_annualized") / ins_st.get("sharpe_annualized")) if st.get("sharpe_annualized") is not None and ins_st.get("sharpe_annualized") else None,
                                     **{k: v for k, v in meta.items() if k != "per_predictor"}}
                lines.append(f"{key:45s} n={st.get('n_months')} SR={st.get('sharpe_annualized', float('nan')):.3f} NWt={st.get('newey_west_t_6', float('nan')):.2f} PSR={st.get('psr_vs_0')} members={meta['members_in']} med_pred_SR={meta['per_predictor_sealed_sharpe_median']:.3f} share>0={meta['per_predictor_share_positive']:.2f} decay={out['pools'][key]['decay_ratio']}")
                if pool_name == "P-clean" and win_name == "post_publication" and cost_name == "standard_haircut":
                    out["PRIMARY"] = key
                    out["PASS"] = bool(st.get("sharpe_annualized", 0) >= 0.50 and (st.get("psr_vs_0") or 0) >= 0.95)
    (HERE / "osap_lockbox_output.json").write_text(json.dumps(out, indent=1, default=str))
    (HERE / "osap_lockbox_output.txt").write_text("\n".join(lines) + f"\nPRIMARY={out['PRIMARY']} PASS={out['PASS']}\n")
    print("\n".join(lines)); print("PRIMARY", out["PRIMARY"], "PASS", out["PASS"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
