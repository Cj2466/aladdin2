"""C8: does the diversification arithmetic actually reconcile? (2026-09-15)

The conversational claim under audit was: "individual mechanism ~0.17 Sharpe, effective
independent bets 14.6, and 0.169 * sqrt(14.6) = 0.645 ~ the measured pooled 0.597, so the
formula and the measurement agree."

This checks it properly, on ONE identical sample, at the predictor level, with the same
loader used for C1 (independent of osap_lockbox.py).
"""
import math
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from audit_lockbox_numbers import (CLEAN_PRED, CLEAN_QUAL, END, MIN_SEALED,
                                   load_doc, load_returns, mean_sd, sharpe_annual)
from collections import defaultdict


def member_series(cols, months, data, meta):
    """Per-eligible-predictor sealed, haircut return series keyed by month."""
    start, hair = {}, {}
    for j, acr in enumerate(cols):
        m = meta.get(acr)
        if not m:
            continue
        if m["Predictability in OP"].strip() not in CLEAN_PRED:
            continue
        if m["Signal Rep Quality"].strip() not in CLEAN_QUAL:
            continue
        try:
            yr = int(float(m["Year"]))
        except (ValueError, KeyError):
            continue
        start[j] = f"{yr + 1}-01"
        try:
            p = float(m["Portfolio Period"])
            if p <= 0 or math.isnan(p):
                p = 1.0
        except (ValueError, TypeError):
            p = 1.0
        hair[j] = 20.0 / p / 100.0

    series = defaultdict(dict)
    for i, mo in enumerate(months):
        if mo > END:
            continue
        for j in start:
            if mo < start[j]:
                continue
            v = data[i][j]
            if v in ("NA", ""):
                continue
            series[j][mo] = float(v) - hair[j]
    return {j: s for j, s in series.items() if len(s) >= MIN_SEALED}, cols


def main():
    meta = load_doc()
    cols, months, data = load_returns()
    series, _ = member_series(cols, months, data, meta)
    print(f"eligible members: {len(series)}")

    # Common-month panel: months in which EVERY member is live.
    # (Membership grows over time, so this is the late window.)
    all_months = sorted({m for s in series.values() for m in s})
    common = [m for m in all_months if all(m in s for s in series.values())]
    print(f"months where ALL {len(series)} members are live: {len(common)}"
          f"  ({common[0]} -> {common[-1]})" if common else "no fully common month")

    # Use the widest window in which at least 150 members are live, to keep a real panel.
    live_count = {m: sum(1 for s in series.values() if m in s) for m in all_months}
    window = [m for m in all_months if live_count[m] >= 150]
    members = [j for j, s in series.items() if all(m in s for m in window)]
    print(f"\npanel used: {len(window)} months ({window[0]} -> {window[-1]}), "
          f"{len(members)} members present in every one")

    mat = [[series[j][m] for j in members] for m in window]  # months x members

    # per-member stats on THIS window
    per_mu, per_sd, per_sr = [], [], []
    for k in range(len(members)):
        col = [row[k] for row in mat]
        mu, sd = mean_sd(col)
        per_mu.append(mu)
        per_sd.append(sd)
        per_sr.append((mu / sd) * math.sqrt(12.0))
    per_sr_sorted = sorted(per_sr)
    med_sr = per_sr_sorted[len(per_sr_sorted) // 2]
    mean_sr = sum(per_sr) / len(per_sr)

    # equal-weight pool on the SAME window
    pool = [sum(row) / len(row) for row in mat]
    pool_mu, pool_sd = mean_sd(pool)
    pool_sr = sharpe_annual(pool)

    # variance-based effective bets, same window
    avg_var = sum(sd * sd for sd in per_sd) / len(per_sd)
    m_eff = avg_var / (pool_sd ** 2)

    # the ratio-of-averages Sharpe (the quantity the sqrt(M) formula actually scales)
    avg_mu = sum(per_mu) / len(per_mu)
    avg_sd_rms = math.sqrt(avg_var)
    ratio_of_avgs_sr = (avg_mu / avg_sd_rms) * math.sqrt(12.0)

    print("\n--- per-member (same window) ---")
    print(f"  median member Sharpe        : {med_sr:.4f}")
    print(f"  mean   member Sharpe        : {mean_sr:.4f}")
    print(f"  ratio-of-averages Sharpe    : {ratio_of_avgs_sr:.4f}   <- the right input to sqrt(M)")
    print("\n--- pooling ---")
    print(f"  effective independent bets  : {m_eff:.3f}")
    print(f"  MEASURED pooled Sharpe      : {pool_sr:.4f}")
    print("\n--- does sqrt(M) reconcile? ---")
    for label, s in (("median member", med_sr), ("mean member", mean_sr),
                     ("ratio-of-averages", ratio_of_avgs_sr)):
        pred = s * math.sqrt(m_eff)
        print(f"  {label:20s} {s:.4f} x sqrt({m_eff:.2f}) = {pred:.4f}   "
              f"vs measured {pool_sr:.4f}   ratio {pred / pool_sr:.3f}")
    print("\n  (only the ratio-of-averages line is the algebraic identity; the other two are"
          "\n   approximations that hold exactly ONLY when every member has the same variance.)")


if __name__ == "__main__":
    main()
