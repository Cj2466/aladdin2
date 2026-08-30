"""Independent check of the 'negative over the common window' claim.

Regenerates the five raw candidate series, then does the date intersection
and the Sharpe arithmetic with plain pandas/numpy here — NOT through
build_returns_matrix — and checks:
  * each raw series' FULL-window Sharpe matches its persisted family row;
  * my own intersection has the same dates as the persisted matrix;
  * the in-window Sharpes match, and the sign flip is real;
  * there is no timezone / off-by-one in any index;
  * the sign flip is NOT produced by the alignment (also computed on a
    naive date-string intersection as a cross-check).
"""

import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from app.services.research_lab import multi_signal_combination as msc

MAIN_DATA = Path("/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/data")
PRIMARY = "multi_signal_recombination_2026-08-30"

FAMILY_TAG = {
    "crp_realized_21d_h63": ("correlation_risk_premium", "live_verification_2026-08-27"),
    "cbop_ls_h63": ("quality_cbop", "quality_build_2026-08-28"),
    "insider_opp_buy_h21_c2_equal": (
        "insider_opportunistic", "insider_form4_verified_2026-08-28"),
    "ofi_raw_h7": ("ofi_crypto", "ofi_crypto_verified_2026-08-29"),
    "lps_intraday_l252_h63": (
        "round_c", "edge_cost_reaudit_corrected_2026-08-30_mid_2bp"),
}


def sharpe(x, ppy=252):
    x = np.asarray(x, dtype=float)
    return float(np.mean(x) / np.std(x, ddof=1) * np.sqrt(ppy))


def main():
    c = sqlite3.connect("aladdin2.db")
    ref = json.loads(
        c.execute(
            "select full_result_json from cross_sectional_trial_results "
            "where run_tag=? and trial_id='rmt_denoised_hrp'", (PRIMARY,)
        ).fetchone()[0]
    )
    persisted_family = {}
    for label, (fam, tag) in FAMILY_TAG.items():
        row = c.execute(
            "select sharpe_annualized, n_observations, psr_vs_zero, dsr from "
            "cross_sectional_trial_results where family_key=? and run_tag=? "
            "and trial_id=?", (fam, tag, label)
        ).fetchone()
        persisted_family[label] = row
    c.close()

    print("=== regenerating raw series ===", flush=True)
    raw = msc.regenerate_candidate_series(
        edgar_cache_dir=MAIN_DATA / "edgar_companyfacts",
        insider_trades_cache=MAIN_DATA / "insider_form4_trades.csv.gz",
        binance_cache_dir=MAIN_DATA / "binance_futures",
    )

    print("\n=== 1. RAW SERIES: index hygiene + FULL-window Sharpe ===")
    for label, s in raw.items():
        idx = pd.DatetimeIndex(s.index)
        ppy = 365 if label in msc.NON_EQUITY_CALENDAR_SPECS else 252
        full = sharpe(s, ppy)
        p_sr, p_n, p_psr, p_dsr = persisted_family[label]
        print(f"  {label}")
        print(f"    tz={idx.tz}  monotonic={idx.is_monotonic_increasing}  "
              f"unique={idx.is_unique}  "
              f"normalized(midnight)={bool((idx.normalize() == idx).all())}")
        print(f"    span {idx.min().date()} .. {idx.max().date()}  n={len(s)} "
              f"(persisted n={p_n})")
        print(f"    FULL-window Sharpe (ppy={ppy}) {full:+.4f}  persisted "
              f"{p_sr:+.4f}  diff {full - p_sr:+.2e}   psr={p_psr:.4f} "
              f"dsr={p_dsr}")

    print("\n=== 2. MY OWN INTERSECTION (no build_returns_matrix) ===")
    equity = [k for k in raw if k not in msc.NON_EQUITY_CALENDAR_SPECS]
    common = None
    for k in equity:
        i = pd.DatetimeIndex(raw[k].index).normalize()
        common = i if common is None else common.intersection(i)
    ofi_idx = pd.DatetimeIndex(raw["ofi_raw_h7"].index).normalize()
    common = common[(common >= ofi_idx.min()) & (common <= ofi_idx.max())]
    print(f"  my intersection: n={len(common)} {common.min().date()} .. "
          f"{common.max().date()}")
    theirs = pd.DatetimeIndex(sorted(ref["candidate_daily_returns"]
                                     ["cbop_ls_h63"].keys()))
    print(f"  persisted matrix: n={len(theirs)} {theirs.min().date()} .. "
          f"{theirs.max().date()}")
    print(f"  identical date sets: {set(common) == set(theirs)}")

    print("\n=== 3. IN-WINDOW SHARPE, sliced by me, ppy=252 ===")
    print(f"  {'sleeve':<32} {'FULL':>9} {'IN-WINDOW':>10} {'persisted-in-w':>15}")
    for label in raw:
        s = raw[label].copy()
        s.index = pd.DatetimeIndex(s.index).normalize()
        if label in msc.NON_EQUITY_CALENDAR_SPECS:
            inw = msc.compound_onto_calendar(s, common)
            full_lbl = sharpe(s, 365)
        else:
            inw = s.reindex(common)
            full_lbl = sharpe(s, 252)
            assert not inw.isna().any(), f"{label}: NaN after reindex"
        mine = sharpe(inw, 252)
        theirs_sr = ref["single_candidate_sharpes"][label]
        flag = "  <-- SIGN FLIP" if (full_lbl > 0) != (mine > 0) else ""
        print(f"  {label:<32} {full_lbl:+9.4f} {mine:+10.4f} "
              f"{theirs_sr:+15.4f}{flag}   diff={mine - theirs_sr:+.2e}")

    print("\n=== 4. NAIVE date-STRING intersection cross-check (equity sleeves) ===")
    # completely different code path: string keys, no DatetimeIndex at all
    sets = []
    for k in equity:
        sets.append({str(pd.Timestamp(d).date()) for d in raw[k].index})
    common_str = sorted(set.intersection(*sets))
    lo = str(pd.Timestamp(raw["ofi_raw_h7"].index.min()).date())
    hi = str(pd.Timestamp(raw["ofi_raw_h7"].index.max()).date())
    common_str = [d for d in common_str if lo <= d <= hi]
    print(f"  n={len(common_str)} {common_str[0]} .. {common_str[-1]}")
    for label in equity:
        by_str = {str(pd.Timestamp(d).date()): float(v)
                  for d, v in raw[label].items()}
        vals = [by_str[d] for d in common_str]
        print(f"  {label:<32} in-window Sharpe {sharpe(vals):+.4f}")

    print("\n=== 5. WINDOW-BOUNDARY SANITY ===")
    for label in equity:
        idx = pd.DatetimeIndex(raw[label].index).normalize()
        after = idx[idx > common.max()]
        print(f"  {label:<32} dates after window end: {len(after)}"
              + (f"  (first {after[0].date()})" if len(after) else ""))
    print(f"  round_c panel last date = {pd.DatetimeIndex(raw['lps_intraday_l252_h63'].index).max().date()}"
          f"  (ROUND_C_REPRO_END pinned = {msc.ROUND_C_REPRO_END})")

    print("\n=== 6. RMT EIGENVALUES ON THE ALIGNED MATRIX ===")
    cand = pd.DataFrame(
        {k: pd.Series(v) for k, v in ref["candidate_daily_returns"].items()})
    cand.index = pd.to_datetime(cand.index)
    cand = cand.sort_index()
    corr = np.corrcoef(cand.to_numpy().T)
    ev = np.sort(np.linalg.eigvalsh(corr))[::-1]
    T, N = cand.shape
    q = T / N
    lam_plus = (1 + np.sqrt(1 / q)) ** 2
    print(f"  T={T} N={N} q={q:.2f} lambda_plus={lam_plus:.4f}")
    print(f"  eigenvalues: {np.round(ev, 4).tolist()}")
    print(f"  # above lambda_plus: {int((ev > lam_plus).sum())}")


if __name__ == "__main__":
    main()
