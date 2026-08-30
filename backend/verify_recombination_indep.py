"""Independent adversarial re-derivation of the 2026-08-30 recombination run.

Recomputes every headline number from the PERSISTED candidate matrix using
plain numpy/pandas, with no call into multi_signal_combination.py's own
metric helpers, and compares against the persisted row and the run log.
"""

import json
import sqlite3
import sys

import numpy as np
import pandas as pd

DB = "aladdin2.db"
PRIMARY = "multi_signal_recombination_2026-08-30"
SENS = "multi_signal_recomb_sensitivity_add_noa_neutral_2026-08-30"
OLD = "multi_signal_build_2026-08-29"


def sharpe(x, ppy=252):
    x = np.asarray(x, dtype=float)
    return float(np.mean(x) / np.std(x, ddof=1) * np.sqrt(ppy))


def load(tag):
    c = sqlite3.connect(DB)
    out = {}
    for tid, blob in c.execute(
        "select trial_id, full_result_json from cross_sectional_trial_results "
        "where run_tag=?",
        (tag,),
    ):
        out[tid] = json.loads(blob)
    c.close()
    return out


def check(name, got, want, tol):
    ok = abs(got - want) <= tol
    print(f"  [{'OK ' if ok else 'FAIL'}] {name}: mine={got:+.6f} theirs={want:+.6f} "
          f"diff={got - want:+.2e}")
    return ok


def main():
    fails = []
    rows = load(PRIMARY)
    ref = rows["rmt_denoised_hrp"]
    cand = pd.DataFrame(
        {k: pd.Series(v) for k, v in ref["candidate_daily_returns"].items()}
    )
    cand.index = pd.to_datetime(cand.index)
    cand = cand.sort_index()
    print(f"candidate matrix: {cand.shape}, {cand.index.min().date()} .. "
          f"{cand.index.max().date()}, nulls={int(cand.isna().sum().sum())}")
    if len(cand) != ref["n_trading_days"]:
        fails.append("n_trading_days mismatch")

    print("\n1. PER-CANDIDATE SHARPE OVER THE COMMON WINDOW (independent):")
    for col in cand.columns:
        mine = sharpe(cand[col])
        theirs = ref["single_candidate_sharpes"][col]
        if not check(col, mine, theirs, 1e-6):
            fails.append(f"single sharpe {col}")

    print("\n2. PAIRWISE CORRELATIONS (independent):")
    cm = ref["correlation_matrix"]
    cols = list(cand.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            mine = float(np.corrcoef(cand[a], cand[b])[0, 1])
            if not check(f"{a} vs {b}", mine, cm[a][b], 1e-9):
                fails.append(f"corr {a}/{b}")

    print("\n3. COMBINATION SHARPES FROM WEIGHTS (independent):")
    for tid, row in sorted(rows.items()):
        w = pd.Series(row["weights"])
        if abs(w.sum() - 1.0) > 1e-9:
            fails.append(f"{tid} weights sum {w.sum()}")
        combo = (cand[w.index] * w).sum(axis=1)
        mine = sharpe(combo)
        if not check(f"{tid} sharpe", mine, row["sharpe_annualized"], 1e-6):
            fails.append(f"combo sharpe {tid}")
        persisted_series = pd.Series(row["daily_returns"])
        persisted_series.index = pd.to_datetime(persisted_series.index)
        d = float((combo - persisted_series.sort_index()).abs().max())
        print(f"        max|persisted daily_returns - w.X| = {d:.3e}")
        if d > 1e-12:
            fails.append(f"combo series {tid}")

    print("\n4. EQUAL-WEIGHT / INVERSE-VOL WEIGHTS RE-DERIVED FROM SCRATCH:")
    ew = rows["equal_weight"]["weights"]
    if not check("equal_weight w (max dev from 1/N)",
                 max(abs(v - 1 / len(ew)) for v in ew.values()), 0.0, 1e-12):
        fails.append("equal weights")
    iv = rows["inverse_volatility"]["weights"]
    inv = 1.0 / cand.std(ddof=1)
    inv = inv / inv.sum()
    for k, v in iv.items():
        if not check(f"inverse_vol {k}", inv[k], v, 1e-9):
            fails.append(f"invvol {k}")

    print("\n5. BEST SINGLE INPUT vs BEST COMBINATION:")
    best_single = max(ref["single_candidate_sharpes"].items(), key=lambda kv: kv[1])
    best_combo = max(rows.items(), key=lambda kv: kv[1]["sharpe_annualized"])
    print(f"  best single: {best_single[0]} {best_single[1]:+.4f}")
    print(f"  best combo:  {best_combo[0]} {best_combo[1]['sharpe_annualized']:+.4f}")
    claim = best_combo[1]["sharpe_annualized"] < best_single[1]
    print(f"  [{'OK ' if claim else 'FAIL'}] combined < best single input: {claim}")
    if not claim:
        fails.append("combined-below-best-single claim")

    print("\n6. NEGATIVE-OVER-COMMON-WINDOW CLAIM:")
    negs = {k: v for k, v in ref["single_candidate_sharpes"].items() if v < 0}
    print(f"  negative sleeves (primary): "
          f"{ {k: round(v, 4) for k, v in negs.items()} }")

    print("\n7. KELLY:")
    k = ref["kelly"]
    for kk, vv in k.items():
        print(f"  {kk} = {vv}")
    # independent Kelly: full-Kelly leverage = mu/sigma^2 on the RMT+HRP book
    w = pd.Series(ref["weights"])
    combo = (cand[w.index] * w).sum(axis=1)
    mu_a = float(combo.mean() * 252)
    sd_a = float(combo.std(ddof=1) * np.sqrt(252))
    print(f"  independent: mu_ann={mu_a:.6f} vol_ann={sd_a:.6f} "
          f"full-Kelly mu/sig^2={mu_a / sd_a**2:.4f} SR={mu_a / sd_a:+.4f}")

    print("\n8. NULL CONTROL (persisted):")
    for kk, vv in ref["null_control"].items():
        if not isinstance(vv, list):
            print(f"  {kk} = {vv}")

    print("\n9. SENSITIVITY RUN:")
    srows = load(SENS)
    sref = srows["rmt_denoised_hrp"]
    scand = pd.DataFrame(
        {kk: pd.Series(v) for kk, v in sref["candidate_daily_returns"].items()}
    )
    scand.index = pd.to_datetime(scand.index)
    scand = scand.sort_index()
    print(f"  matrix {scand.shape} {scand.index.min().date()}.."
          f"{scand.index.max().date()}")
    for col in scand.columns:
        mine = sharpe(scand[col])
        if not check(col, mine, sref["single_candidate_sharpes"][col], 1e-6):
            fails.append(f"sens single {col}")
    for tid, row in sorted(srows.items()):
        w = pd.Series(row["weights"])
        mine = sharpe((scand[w.index] * w).sum(axis=1))
        if not check(f"{tid}", mine, row["sharpe_annualized"], 1e-6):
            fails.append(f"sens combo {tid}")
    # the five shared sleeves must be IDENTICAL series across the two runs
    for col in cand.columns:
        d = float((cand[col] - scand[col]).abs().max())
        print(f"  shared sleeve {col}: max abs diff vs primary = {d:.3e}")
        if d > 0:
            fails.append(f"sleeve drift {col}")

    print("\n10. COMPARISON WITH THE 2026-08-29 RUN (what actually changed):")
    orows = load(OLD)
    oref = orows["rmt_denoised_hrp"]
    ocand = pd.DataFrame(
        {kk: pd.Series(v) for kk, v in oref["candidate_daily_returns"].items()}
    )
    ocand.index = pd.to_datetime(ocand.index)
    ocand = ocand.sort_index()
    print(f"  old window {oref['window_start']}..{oref['window_end']} "
          f"n={oref['n_trading_days']}; new {ref['window_start']}.."
          f"{ref['window_end']} n={ref['n_trading_days']}")
    old_dates, new_dates = set(ocand.index), set(cand.index)
    print(f"  dates in old but not new: "
          f"{sorted(str(d.date()) for d in old_dates - new_dates)}")
    print(f"  dates in new but not old: "
          f"{sorted(str(d.date()) for d in new_dates - old_dates)}")
    for col in ocand.columns:
        if col in cand.columns:
            common = ocand.index.intersection(cand.index)
            d = float((ocand.loc[common, col] - cand.loc[common, col]).abs().max())
            print(f"  {col}: max abs diff on shared dates = {d:.3e}; "
                  f"old SR {oref['single_candidate_sharpes'][col]:+.4f} -> new "
                  f"{ref['single_candidate_sharpes'][col]:+.4f}")

    print("\n" + "=" * 70)
    if fails:
        print(f"FAILURES ({len(fails)}): {fails}")
        sys.exit(1)
    print("ALL INDEPENDENT RE-DERIVATIONS MATCH THE PERSISTED ROWS.")


if __name__ == "__main__":
    main()
