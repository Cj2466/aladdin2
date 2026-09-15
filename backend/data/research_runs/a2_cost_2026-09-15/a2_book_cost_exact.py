"""A2 final: re-price the Set-2 book at the MEASURED cost, from the raw sealed
series -- no reconstruction from the published summary (my first attempt
recovered gross Sharpe 0.884 against the committed 0.785, because the haircut
is 20/P per predictor and P varies across members, so the pooled haircut is
NOT 20 bp/month).

Every number here is recomputed from osap_ls_returns_wide.csv with the same
independent loader used by the 2026-09-15 audit.
"""
import math, os, sys, json
from collections import defaultdict

AUDIT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "number_audit_2026-09-15")
sys.path.insert(0, os.path.abspath(AUDIT))
from audit_lockbox_numbers import (CLEAN_PRED, CLEAN_QUAL, END, MIN_SEALED,
                                   load_doc, load_returns, mean_sd)

HERE = os.path.dirname(os.path.abspath(__file__))


def build(meta, cols, months, data, cost_per_reformation_bp):
    """Pooled equal-weight series charging `cost_per_reformation_bp`/P per month.
    cost_per_reformation_bp = 0 gives the gross book."""
    start, per_month = {}, {}
    for j, acr in enumerate(cols):
        m = meta.get(acr)
        if not m: continue
        if m["Predictability in OP"].strip() not in CLEAN_PRED: continue
        if m["Signal Rep Quality"].strip() not in CLEAN_QUAL: continue
        try: yr = int(float(m["Year"]))
        except (ValueError, KeyError): continue
        start[j] = f"{yr + 1}-01"
        try:
            p = float(m["Portfolio Period"])
            if p <= 0 or math.isnan(p): p = 1.0
        except (ValueError, TypeError): p = 1.0
        per_month[j] = cost_per_reformation_bp / p / 100.0   # bp -> percent

    sealed = defaultdict(int)
    for i, mo in enumerate(months):
        if mo > END: continue
        for j in start:
            if mo >= start[j] and data[i][j] not in ("NA", ""): sealed[j] += 1
    elig = {j for j in start if sealed[j] >= MIN_SEALED}

    out = []
    for i, mo in enumerate(months):
        if mo > END: continue
        vals = [float(data[i][j]) - per_month[j] for j in elig
                if mo >= start[j] and data[i][j] not in ("NA", "")]
        if vals: out.append(sum(vals) / len(vals))
    mu, sd = mean_sd(out)
    return len(elig), len(out), mu, (mu / sd) * math.sqrt(12.0)


def main():
    meta = load_doc(); cols, months, data = load_returns()
    imp = json.load(open(os.path.join(HERE, "a2_book_cost_implication.json")))
    LOW = imp["one_reformation_bp"]["low_tick_floor"]
    HIGH = imp["one_reformation_bp"]["high_edge_floored"]
    DVW = 77.8   # dollar-volume-weighted HIGH, from a2_book_cost_implication

    print("re-priced from the raw sealed series (independent loader)\n")
    print(f"{'cost per reformation':>34s} {'members':>8s} {'months':>7s} "
          f"{'mean %/mo':>10s} {'Sharpe':>8s} {'verdict':>9s}")
    scen = [("0 bp (gross)", 0.0),
            ("20 bp - the protocol's assumption", 20.0),
            ("40 bp - the protocol's doubled arm", 40.0),
            (f"{LOW:.1f} bp - MEASURED low (tick floor)", LOW),
            (f"{DVW:.1f} bp - MEASURED, $vol-weighted", DVW),
            (f"{HIGH:.1f} bp - MEASURED high (EDGE)", HIGH)]
    res = []
    for label, c in scen:
        n_m, n, mu, sr = build(meta, cols, months, data, c)
        v = "PASS" if sr >= 0.50 else "FAIL"
        res.append({"label": label, "cost_bp": c, "members": n_m, "months": n,
                    "mean_pct_per_month": round(mu, 4), "sharpe": round(sr, 4), "verdict": v})
        print(f"{label:>34s} {n_m:8d} {n:7d} {mu:10.4f} {sr:8.3f} {v:>9s}")

    # exact break-even on the same series
    lo, hi = 0.0, 400.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        _, _, _, sr = build(meta, cols, months, data, mid)
        if sr >= 0.50: lo = mid
        else: hi = mid
    print(f"\nexact break-even: the book clears Sharpe 0.50 up to a cost of "
          f"{lo:.1f} bp per full reformation.")
    print(f"  measured range is {LOW:.0f} - {HIGH:.0f} bp "
          f"({DVW:.0f} bp dollar-volume-weighted).")

    json.dump({"scenarios": res, "breakeven_bp_per_reformation_for_sharpe_050": round(lo, 2),
               "measured_low_bp": LOW, "measured_high_bp": HIGH, "measured_dvw_bp": DVW},
              open(os.path.join(HERE, "a2_book_cost_exact.json"), "w"), indent=1)
    print("\nwrote a2_book_cost_exact.json")


if __name__ == "__main__":
    main()
