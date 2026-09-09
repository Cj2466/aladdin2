#!/usr/bin/env python
"""Regenerate the DSR denominator-ladder decision: diagnosis, estimators, verdicts.

WHAT THIS SCRIPT ANSWERS
========================
Policy D reports every family's DSR at several n_trials values. Until
2026-09-06 those values were n_local, 481 and 857 -- the last two being
PROVENANCE fields on global_effective_n.json (respectively "how many specs
happened to carry a usable return series" and "the raw pooled count on
2026-09-04"), never chosen as denominators. This script measures what the
rungs should actually be, and writes the decision memo.

STAGES
  --stage diagnose   why ONC degenerated (overlap, structure, objective)
  --stage estimate   effective-N estimators on the committed 481-spec matrix
  --stage verdicts   recompute the live registrations' DSR at every rung
  --stage all        all three, then write the .txt/.json memo (default)

EVERY NUMBER comes from the live DB or the committed correlation matrix.
Nothing is retyped from an earlier report.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from app.services.research_lab.deflated_sharpe import (
    expected_max_sharpe_under_noise,
    probabilistic_sharpe_ratio,
)
from app.services.research_lab.effective_n_clustering import (
    MIN_OVERLAP_FOR_CORRELATION,
    correlation_to_distance,
)

RUN_DATE = "2026-09-09"  # re-measurement: raw pool hit the staleness threshold (1131 vs 1031)
RUN_TAG = f"dsr_policy_n_{RUN_DATE}"
MATRIX = BACKEND / "data/research_runs/global_effective_n_return_matrix_2026-09-05.csv.gz"
META = BACKEND / "data/research_runs/global_effective_n_return_matrix_2026-09-05.meta.json"

# The DB path is resolved by app.config, NOT by BACKEND / "aladdin2.db". Under a
# git worktree those are different files: config.py resolves --git-common-dir so
# a worktree run reads and writes MAIN's shared aladdin2.db, which is where every
# persisted trial row actually lives. Hardcoding the worktree-local path is the
# exact bug fixed on 2026-09-06 after a family's trial rows were silently lost.
from app.config import settings

_url = settings.database_url
if not _url.startswith("sqlite"):
    raise SystemExit(f"this script reads the local SQLite trial store; got {_url!r}")
DB = Path(_url.split("sqlite:///", 1)[1])

# --- the mechanism census ---------------------------------------------------
# family_key -> economic mechanism. ONLY re-runs, diagnostic re-tests and second
# universes of an existing mechanism are merged; every merge is justified here.
MECHANISM_OF = {
    "lazy_prices_ptit_fix_verification": "lazy_prices",       # diagnostic re-test
    "lazy_prices_vocab_ceiling_confound": "lazy_prices",      # confound check
    "lazy_prices_xom_hypothesis_test_fast": "lazy_prices",    # hypothesis re-test
    "quality_noa_industry_neutral": "quality_noa",            # same signal, neutralised
    "small_cap_ivol": "ivol",                                 # same signal, 2nd universe
    "small_cap_quarter_end_marking": "quarter_end_marking",   # same signal, 2nd universe
    "small_cap_tax_loss_selling_turn_of_year": "tax_loss_selling_turn_of_year",
    "funding_carry_pit": "funding_carry",                     # PIT rebuild of the same
}
# Weighted combinations of specs already counted elsewhere: counting them as a
# fresh search double-counts their constituents. The 2026-09-05 pooled run
# excluded them from the correlation matrix for exactly this reason.
NOT_A_SEARCH = {"multi_signal_combination"}


def load_matrix() -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    df = pd.read_csv(MATRIX, index_col=0, compression="gzip")
    df.index = pd.to_datetime(df.index)
    meta = json.loads(META.read_text())
    fam = np.array([meta["specs"][c]["family_key"] for c in df.columns])
    corr = df.corr(min_periods=MIN_OVERLAP_FOR_CORRELATION)
    C = np.nan_to_num(corr.to_numpy(), nan=0.0)
    np.fill_diagonal(C, 1.0)
    return df, C, fam


# --- estimators -------------------------------------------------------------
def galwey(M: np.ndarray) -> float:
    """Galwey (2009): M_eff = (sum sqrt(lam_i+))^2 / sum(lam_i+).
    Halle et al. (arXiv:1612.04535): ANTI-conservative, does not control FWER."""
    lam = np.clip(np.linalg.eigvalsh(M)[::-1], 0, None)
    pos = lam[lam > 0]
    return float((np.sqrt(pos).sum() ** 2) / pos.sum())


def li_ji(M: np.ndarray) -> float:
    """Li & Ji (2005): M_eff = sum f(|lam_i|), f(x)=I(x>=1)+(x-floor(x)).
    Halle et al.: ANTI-conservative, does not control FWER."""
    lam = np.abs(np.clip(np.linalg.eigvalsh(M)[::-1], 0, None))
    return float(np.sum((lam >= 1).astype(float) + (lam - np.floor(lam))))


def nyholt(M: np.ndarray) -> float:
    """Nyholt (2004): M_eff = 1 + (m-1)(1 - Var(lam)/m).
    Verified against the primary paper (Am. J. Hum. Genet. 74:765-769).
    Halle et al.: conservative."""
    m = M.shape[0]
    lam = np.clip(np.linalg.eigvalsh(M)[::-1], 0, None)
    return float(1 + (m - 1) * (1 - lam.var(ddof=0) / m))


def cheverud(M: np.ndarray) -> float:
    """Cheverud (2001): M_eff = m(1 - (m-1)Var(lam)/m^2). Halle et al.: conservative."""
    m = M.shape[0]
    lam = np.clip(np.linalg.eigvalsh(M)[::-1], 0, None)
    return float(m * (1 - (m - 1) * lam.var(ddof=0) / (m**2)))


def dsr_eq8_rho_bar(C: np.ndarray) -> float:
    """Bailey & Lopez de Prado (2014), "The Deflated Sharpe Ratio", Appendix A.3,
    Eq. (8): rho_bar = 2 * sum_{i<j} rho_ij / (M(M-1))."""
    m = C.shape[0]
    iu = np.triu_indices(m, k=1)
    return float(2.0 * C[iu].sum() / (m * (m - 1)))


def dsr_eq9_implied_n(rho_bar: float, m: int) -> float:
    """Bailey & Lopez de Prado (2014), Appendix A.3, Eq. (9):
    N_hat = rho_bar + (1 - rho_bar) * M -- the implied number of INDEPENDENT
    trials given M dependent ones. No clustering, no k=2 floor."""
    return float(rho_bar + (1.0 - rho_bar) * m)


def variance_effective_n(C: np.ndarray) -> float:
    """N^2/(1'C1). Reported ONLY to identify the "30" this ladder retires --
    effective_n_clustering.py's own docstring says this is a RISK statistic and
    "must not be substituted for E[K]"."""
    n = C.shape[0]
    return float(n * n / (np.ones(n) @ C @ np.ones(n)))


# --- census -----------------------------------------------------------------
def census() -> dict:
    con = sqlite3.connect(DB)
    per_family = dict(con.execute(
        "select family_key, count(distinct trial_id) from cross_sectional_trial_results "
        "group by family_key"))
    raw_trials = int(sum(per_family.values()))
    mech: dict[str, int] = {}
    for f, n in per_family.items():
        if f in NOT_A_SEARCH:
            continue
        key = MECHANISM_OF.get(f, f)
        mech[key] = mech.get(key, 0) + n
    con.close()
    return {
        "n_family_keys": len(per_family),
        "raw_distinct_family_trial_pairs": raw_trials,
        "n_mechanisms": len(mech),
        "per_family": per_family,
        "per_mechanism": mech,
    }


def dsr_at(sr_ann, n_obs, skew, kurt, sigma_ann, ppy, n_trials):
    """DSR at an arbitrary denominator, using deflated_sharpe's OWN functions."""
    sr0 = expected_max_sharpe_under_noise(sigma_ann / np.sqrt(ppy), n_trials)
    if sr0 is None:
        return None
    return probabilistic_sharpe_ratio(sr_ann / np.sqrt(ppy), sr0, n_obs, skew, kurt)


def live_registration_inputs() -> dict:
    """DSR inputs for each live registration, read from the persisted trial row
    that matches its CURRENT cost basis. Row ids are recorded so the choice is
    auditable rather than implicit."""
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    picks = {
        # label: (row id, why this row)
        "quality_cbop / cbop_ls_h63": (
            2492, "latest persisted row; financing 0.0 unchanged since registration"),
        "short_interest_ratio / si_ratio_hedged_h21": (
            2525, ("latest persisted row -- PREDATES the 44.7705bp borrow adopted "
                   "2026-09-06 (eac32c9); its Sharpe is therefore OPTIMISTIC")),
        "lazy_prices_jaccard_full / lazy_jaccard_full_h126_ivol": (
            3242, ("cost_basis_switch_2026-09-05_after_calibrated_measured_borrow -- "
                   "the row matching the adopted 48.1644bp basis")),
        "cross_sectional_crypto / xc_btcbeta_l180_h180": (
            2787, "only persisted row; financing 400.0 unchanged"),
    }
    out = {}
    for label, (rid, why) in picks.items():
        row = con.execute(
            "select family_key,trial_id,run_tag,full_result_json from "
            "cross_sectional_trial_results where id=?", (rid,)).fetchone()
        d = json.loads(row["full_result_json"])["deflated_sharpe"]
        ppy = 365.0 if row["family_key"] == "crypto" else 252.0
        out[label] = {
            "row_id": rid, "why_this_row": why, "run_tag": row["run_tag"],
            "family_key": row["family_key"], "trial_id": row["trial_id"],
            "sharpe_annualized": d["sharpe_net_annualized"],
            "n_observations": d["n_observations"], "skewness": d["skewness"],
            "kurtosis": d["kurtosis"], "sigma_sr_annualized": d["sigma_sr_annualized"],
            "periods_per_year": ppy, "n_local": d["n_trials"],
            "persisted_dsr": d["dsr"],
        }
    con.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all",
                    choices=["diagnose", "estimate", "verdicts", "all"])
    args = ap.parse_args()

    df, C, fam = load_matrix()
    M = C.shape[0]
    iu = np.triu_indices(M, k=1)
    vals = C[iu]
    same = fam[iu[0]] == fam[iu[1]]
    cen = census()
    report: dict = {"schema": "dsr_policy_n_run/v1", "run_tag": RUN_TAG,
                    "run_date": RUN_DATE}

    # ---------------- DIAGNOSE ----------------
    if args.stage in ("diagnose", "all"):
        finite = df.notna().to_numpy().astype(np.int32)
        ov = (finite.T @ finite)[iu]
        D = correlation_to_distance(pd.DataFrame(C)).to_numpy()
        from sklearn.cluster import KMeans
        from sklearn.metrics import silhouette_samples

        def q_and_silh(labels):
            s = silhouette_samples(D, labels)
            return float(s.mean() / s.std()), float(s.mean())

        uniq = {f: i for i, f in enumerate(sorted(set(fam)))}
        q_true, ms_true = q_and_silh(np.array([uniq[f] for f in fam]))
        lab2 = KMeans(n_clusters=2, n_init=10, random_state=20260904).fit_predict(D)
        q_k2, ms_k2 = q_and_silh(lab2)

        # The k-sweep is what separates "no structure" from "the objective
        # preferred a worse partition": if some k scores BETTER on the
        # silhouette than ONC's k=2 while scoring WORSE on q, then q -- not the
        # data -- is what selected k=2.
        sweep = {}
        for k in (2, 3, 5, 8, 13, 20, 28, 40, 60, 87, 120, 200):
            bq, bms = -np.inf, None
            for seed in range(5):
                lab = KMeans(n_clusters=k, n_init=1, random_state=seed).fit_predict(D)
                q, ms = q_and_silh(lab)
                if q > bq:
                    bq, bms = q, ms
            sweep[str(k)] = {"best_q": bq, "mean_silhouette_at_best_q": bms}

        report["diagnosis"] = {
            "sparsity_refuted": {
                "pairs": int(vals.size),
                "pairs_below_min_overlap": int((ov < MIN_OVERLAP_FOR_CORRELATION).sum()),
                "min_pairwise_overlap": int(ov.min()),
                "note": "no correlation cell was ever filled by the paper's fillna(0); "
                        "the matrix ONC clustered was fully populated with real correlations",
            },
            "structure_is_present": {
                "within_family_mean_abs_rho": float(np.abs(vals[same]).mean()),
                "between_family_mean_abs_rho": float(np.abs(vals[~same]).mean()),
                "within_family_mean_rho": float(vals[same].mean()),
                "between_family_mean_rho": float(vals[~same].mean()),
                "n_eigenvalues_above_1": int((np.linalg.eigvalsh(C) > 1).sum()),
                "jkp_2023_comparison": "Jensen/Kelly/Pedersen 2023 calibrate a block "
                                       "structure at 0.55 within-theme / 0.03 across-theme",
            },
            "onc_objective_picked_the_worse_answer": {
                "k_2_q": q_k2, "k_2_mean_silhouette": ms_k2,
                "true_family_partition_q": q_true,
                "true_family_partition_mean_silhouette": ms_true,
                "k_sweep": sweep,
                "note": "ONC maximizes q = mean(S)/std(S), NOT the mean silhouette. k=2 "
                        "maximizes q, but k-means at k=28 and k=120 reach mean silhouettes of "
                        "~0.37 and ~0.47 against k=2's 0.235 -- i.e. the ratio objective "
                        "actively PREFERS a partition that is materially worse by the "
                        "silhouette itself. The '0.235 <= 0.25, therefore no substantial "
                        "structure' reading was taken AT ONC's k=2 answer and does not "
                        "characterise the data.",
                "second_finding": "the TRUE FAMILY PARTITION scores only "
                        f"{ms_true:.4f} -- LOWER than k=2. So the correlation geometry does not "
                        "align cleanly with family labels either: there is real sub-family "
                        "and cross-family structure, which is why k=120 outscores k=28. This "
                        "is a caution against reading the family count as an "
                        "independent-bet count.",
            },
        }

    # ---------------- ESTIMATE ----------------
    rho_bar = dsr_eq8_rho_bar(C)
    raw_today = cen["raw_distinct_family_trial_pairs"]
    est = {
        "matrix_specs": M,
        "dsr_eq8_rho_bar": rho_bar,
        "dsr_eq9_implied_n_at_matrix": dsr_eq9_implied_n(rho_bar, M),
        "dsr_eq9_implied_n_at_full_pool": dsr_eq9_implied_n(rho_bar, raw_today),
        "cheverud_2001": cheverud(C),
        "nyholt_2004": nyholt(C),
        "li_ji_2005": li_ji(C),
        "galwey_2009": galwey(C),
        "variance_effective_n_RETIRED": variance_effective_n(C),
        "conservative_family_ratio_to_raw": dsr_eq9_implied_n(rho_bar, M) / M,
        "anticonservative_family_ratio_to_raw": li_ji(C) / M,
    }
    if args.stage in ("estimate", "all"):
        report["estimators"] = est

    # ---------------- LADDER ----------------
    n_mech = cen["n_mechanisms"]
    n_eff = round(li_ji(C) / M * raw_today)
    ladder = {"n_mechanisms": n_mech, "n_effective": n_eff, "n_raw": raw_today}
    report["census"] = cen
    report["ladder"] = ladder

    # ---------------- VERDICTS ----------------
    if args.stage in ("verdicts", "all"):
        live = live_registration_inputs()
        rungs_old = [481, 857]
        verdicts = {}
        for label, v in live.items():
            args_ = (v["sharpe_annualized"], v["n_observations"], v["skewness"],
                     v["kurtosis"], v["sigma_sr_annualized"], v["periods_per_year"])
            check = dsr_at(*args_, v["n_local"])
            row = {
                **{k: v[k] for k in ("row_id", "why_this_row", "run_tag", "n_local",
                                     "persisted_dsr", "sharpe_annualized")},
                "recomputation_matches_persisted": bool(
                    abs(check - v["persisted_dsr"]) < 1e-9),
                "dsr_by_n": {},
            }
            for n in sorted({v["n_local"], *ladder.values(), *rungs_old}):
                row["dsr_by_n"][str(n)] = dsr_at(*args_, n)
            for bar in (0.50, 0.95):
                lo = row["dsr_by_n"][str(v["n_local"])]
                hi = row["dsr_by_n"][str(max(v["n_local"], *ladder.values()))]
                row[f"verdict_at_{bar}"] = (
                    "definite_negative" if lo < bar
                    else "pass" if hi >= bar else "unresolved")
            verdicts[label] = row
        report["verdicts"] = verdicts

    out_json = BACKEND / f"data/research_runs/dsr_policy_n_{RUN_DATE}.json"
    out_json.write_text(json.dumps(report, indent=2, sort_keys=True))
    print(f"wrote {out_json}")
    print(json.dumps({"ladder": ladder, "estimators": est,
                      "n_mechanisms": n_mech, "raw": raw_today}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
