"""Re-price the sealed Set-2 series at the SOURCED micro-cap cost, by forced cadence.

Produces §4 of FINDING_2026-09-15.md. READ THAT FILE'S WARNING FIRST: forcing a
long cadence divides the COST while leaving the paper's own monthly-rebalanced
GROSS RETURN untouched, so every row below is an UPPER BOUND on what a slow book
could earn, not an estimate of one. Signal decay is given a value of exactly zero
here and has not been measured.

Cost source: Collver, "A characterization of market quality for small
capitalization US equities", US SEC Division of Trading and Markets, Sept 2014 --
median relative effective spread 0.922%-1.235% for sub-$100M caps, i.e. one-way
half-spreads 46.1-61.8 bp, i.e. 184.4-247.0 bp per full long-short reformation.
"""
import math, os, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "number_audit_2026-09-15")))
from audit_lockbox_numbers import (CLEAN_PRED, CLEAN_QUAL, END, MIN_SEALED,
                                   load_doc, load_returns, mean_sd)

LO, HI = 184.4, 247.0


def build(meta, cols, months, data, cost_bp, force_P=None):
    start, per_month = {}, {}
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
        if force_P is not None:
            p = float(force_P)
        else:
            try:
                p = float(m["Portfolio Period"])
                if p <= 0 or math.isnan(p):
                    p = 1.0
            except (ValueError, TypeError):
                p = 1.0
        per_month[j] = cost_bp / p / 100.0
    sealed = defaultdict(int)
    for i, mo in enumerate(months):
        if mo > END:
            continue
        for j in start:
            if mo >= start[j] and data[i][j] not in ("NA", ""):
                sealed[j] += 1
    elig = {j for j in start if sealed[j] >= MIN_SEALED}
    out = []
    for i, mo in enumerate(months):
        if mo > END:
            continue
        v = [float(data[i][j]) - per_month[j] for j in elig
             if mo >= start[j] and data[i][j] not in ("NA", "")]
        if v:
            out.append(sum(v) / len(v))
    mu, sd = mean_sd(out)
    return (mu / sd) * math.sqrt(12.0)


def main():
    meta = load_doc()
    cols, months, data = load_returns()
    print("UPPER BOUND ONLY -- signal decay is valued at zero here. See FINDING_2026-09-15.md §4.\n")
    print(f"{'forced cadence':>22s} {'cost/month (bp)':>18s} {'SR @184bp':>11s} {'SR @247bp':>11s} {'vs 0.50':>10s}")
    for label, P in (("each paper's own P", None), ("all monthly (P=1)", 1),
                     ("all quarterly (P=3)", 3), ("all annual (P=12)", 12),
                     ("all 2-yearly (P=24)", 24), ("all 3-yearly (P=36)", 36)):
        a = build(meta, cols, months, data, LO, P)
        b = build(meta, cols, months, data, HI, P)
        cm = f"{LO/(P or 1):.1f}-{HI/(P or 1):.1f}" if P else "varies"
        v = "PASS" if b >= 0.50 else ("split" if a >= 0.50 else "FAIL")
        print(f"{label:>22s} {cm:>18s} {a:11.3f} {b:11.3f} {v:>10s}")


if __name__ == "__main__":
    main()
