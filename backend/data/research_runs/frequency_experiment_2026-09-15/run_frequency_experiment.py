"""Does trading more often reduce the chance of losing? (2026-09-15)

Predictions written first in PREDICTION_2026-09-15.md. Two arms:

  ARM 1 (simulation) -- isolates the causal question by holding the ANNUAL edge
  fixed and varying only how many trades it is split across. Splitting a fixed
  annual edge across N trades means each trade carries mu/N of the drift and
  sd/sqrt(N) of the risk, which preserves the annual Sharpe by construction.
  That is the whole point: if frequency mattered on its own, the loss
  probability would move anyway.

  ARM 2 (real data) -- the 195 sealed OSAP predictors, grouped by their own
  papers' rebalance cadence, at ZERO cost. Descriptive cut, no verdict.
"""
import math, os, sys
from collections import defaultdict
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "number_audit_2026-09-15")))
from audit_lockbox_numbers import (CLEAN_PRED, CLEAN_QUAL, END, MIN_SEALED,
                                   load_doc, load_returns)

rng = np.random.default_rng(20260915)
YEARS = 200_000


def arm1(annual_sharpe, annual_vol, cost_bp_per_trade, n_trades):
    """P(negative year) for a strategy with a FIXED annual edge split across n_trades."""
    mu_a = annual_sharpe * annual_vol
    mu_t = mu_a / n_trades
    sd_t = annual_vol / math.sqrt(n_trades)
    cost_t = cost_bp_per_trade / 1e4
    r = rng.normal(mu_t - cost_t, sd_t, size=(YEARS, n_trades))
    return float((r.sum(axis=1) < 0).mean())


def arm1_fresh_edge(sharpe_per_trade, annual_vol, cost_bp, n_trades):
    """The Medallion case, CORRECTED 2026-09-15.

    The first version of this function was wrong: it held the ANNUAL edge fixed
    (mu_t = s*vol/n with sd_t = vol/sqrt(n) gives annual Sharpe = s at every n),
    which is arm 1a again, and the printed annual Sharpe column of 0.60 at every
    frequency was the symptom. A FRESH edge per trade means the per-trade SHARPE
    is what stays constant, so mu_t = s * sd_t, giving annual Sharpe = s*sqrt(n).
    """
    sd_t = annual_vol / math.sqrt(n_trades)
    mu_t = sharpe_per_trade * sd_t                  # per-trade SHARPE held constant
    cost_t = cost_bp / 1e4
    r = rng.normal(mu_t - cost_t, sd_t, size=(YEARS, n_trades))
    net_annual_sharpe = (mu_t - cost_t) * n_trades / (sd_t * math.sqrt(n_trades))
    return float((r.sum(axis=1) < 0).mean()), net_annual_sharpe, mu_t * 1e4


def main():
    VOL = 0.15
    FREQ = [1, 4, 12, 52, 252, 1000]

    print("=" * 78)
    print("ARM 1a -- FIXED annual edge (Sharpe 0.60), ZERO cost. Tests P1.")
    print(f"{'trades/year':>12s} {'P(losing year)':>16s}")
    base = []
    for n in FREQ:
        p = arm1(0.60, VOL, 0.0, n)
        base.append(p)
        print(f"{n:12d} {p*100:15.2f}%")
    print(f"   spread across frequencies: {(max(base)-min(base))*100:.2f} percentage points")
    print(f"   theory says it should be:  0.00 (all equal to Phi(-0.60) = {100*0.5*(1+math.erf(-0.6/math.sqrt(2))):.2f}%)")

    print("=" * 78)
    print("ARM 1b -- same, but WITH a per-trade cost. Tests P2.")
    print(f"{'trades/year':>12s} {'0 bp':>9s} {'1 bp':>9s} {'5 bp':>9s} {'20 bp':>9s} {'50 bp':>9s}")
    for n in FREQ:
        row = [arm1(0.60, VOL, c, n) for c in (0.0, 1.0, 5.0, 20.0, 50.0)]
        print(f"{n:12d} " + " ".join(f"{p*100:8.2f}%" for p in row))

    print("=" * 78)
    print("ARM 1c -- the Medallion case: each trade carries a FRESH edge. Tests P3.")
    print("   per-trade SHARPE held at 0.05 (a tiny edge), so annual Sharpe = 0.05*sqrt(N)")
    print(f"{'trades/year':>12s} {'edge/trade':>11s} {'gross SR':>9s} {'P(lose)':>9s} "
          f"{'net SR @1bp':>12s} {'P(lose)':>9s} {'net SR @5bp':>12s} {'P(lose)':>9s}")
    for n in FREQ:
        p0, s0, edge_bp = arm1_fresh_edge(0.05, VOL, 0.0, n)
        p1, s1, _ = arm1_fresh_edge(0.05, VOL, 1.0, n)
        p5, s5, _ = arm1_fresh_edge(0.05, VOL, 5.0, n)
        print(f"{n:12d} {edge_bp:10.2f}b {s0:9.2f} {p0*100:8.1f}% "
              f"{s1:12.2f} {p1*100:8.1f}% {s5:12.2f} {p5*100:8.1f}%")
    print("   'edge/trade' is the gross expected gain per trade in bp. Compare it to the cost.")

    print("=" * 78)
    print("ARM 2 -- REAL DATA: the 195 sealed predictors, by their own rebalance cadence.")
    print("   Zero cost, non-overlapping calendar years, descriptive only. Tests P4.")
    meta = load_doc(); cols, months, data = load_returns()
    by_P = defaultdict(list)
    for j, acr in enumerate(cols):
        m = meta.get(acr)
        if not m: continue
        if m["Predictability in OP"].strip() not in CLEAN_PRED: continue
        if m["Signal Rep Quality"].strip() not in CLEAN_QUAL: continue
        try: yr = int(float(m["Year"]))
        except (ValueError, KeyError): continue
        start = f"{yr+1}-01"
        try:
            P = float(m["Portfolio Period"]); P = 1.0 if (P <= 0 or math.isnan(P)) else P
        except (ValueError, TypeError): P = 1.0
        series = [(mo, float(data[i][j])) for i, mo in enumerate(months)
                  if mo <= END and mo >= start and data[i][j] not in ("NA", "")]
        if len(series) < MIN_SEALED: continue
        years = defaultdict(list)
        for mo, v in series:
            years[mo[:4]].append(v)
        full = [y for y, v in years.items() if len(v) == 12]
        if len(full) < 5: continue
        losses = sum(1 for y in full if math.prod(1 + x/100 for x in years[y]) < 1.0)
        # same predictor, charged the project's 20/P bps per month haircut
        hair = 20.0 / P / 100.0
        losses_c = sum(1 for y in full
                       if math.prod(1 + (x - hair)/100 for x in years[y]) < 1.0)
        by_P[int(P)].append((losses / len(full), len(full), losses_c / len(full)))

    print(f"{'cadence':>18s} {'predictors':>11s} {'full years':>11s} "
          f"{'LOSING years, GROSS':>21s} {'LOSING years, w/ COST':>23s}")
    for P in sorted(by_P):
        v = by_P[P]
        shares = [x[0] for x in v]; shares_c = [x[2] for x in v]
        tot_years = sum(x[1] for x in v)
        lab = {1: "monthly", 3: "quarterly", 6: "semi-annual", 12: "annual", 36: "3-yearly"}.get(P, f"P={P}")
        print(f"{lab:>18s} {len(v):11d} {tot_years:11d} "
              f"{np.mean(shares)*100:20.1f}% {np.mean(shares_c)*100:22.1f}%")
    if 1 in by_P and 12 in by_P:
        a = np.mean([x[0] for x in by_P[1]]); b = np.mean([x[0] for x in by_P[12]])
        ac = np.mean([x[2] for x in by_P[1]]); bc = np.mean([x[2] for x in by_P[12]])
        print(f"\n   GROSS  : monthly {a*100:.1f}% vs annual {b*100:.1f}%  -> {(a-b)*100:+.1f} pp")
        print(f"   W/ COST: monthly {ac*100:.1f}% vs annual {bc*100:.1f}%  -> {(ac-bc)*100:+.1f} pp")
        print("   P4 said monthly would NOT be lower at zero cost. Negative = I am refuted.")


if __name__ == "__main__":
    main()
