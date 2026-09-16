#!/usr/bin/env python
"""Test B reduction. WRITTEN AND COMMITTED BEFORE THE COLLECTION FINISHED, so the
reduction cannot be shaped to the answer. Governed by PROTOCOL_2026-09-16.md and
addenda 01-03.

Emits, in order: the gates (G1, G2), then Parts 1, 2, 3, then the decision rule
that section 7 returns. It does not decide anything the protocol did not already
decide; it reports which pre-declared branch the numbers land in.
"""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROWS = HERE / "collected_rows.jsonl"
OUT = HERE / "analysis_output.json"

BREAK_EVEN_BP = 30.6          # A2 RESULT_A2_2026-09-15.md, per full reformation
REFORM_MULT = 4.0             # A2 convention: both legs, in and out
PRIMARY = ["Q1 least liquid", "Q2", "Q3"]
ORDER = ["Q1 least liquid", "Q2", "Q3", "Q4", "Q5 most liquid"]
GATE_LO, GATE_HI = 0.05, 6.0  # ADDENDUM_03; ceiling fixed, floor widened there


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def load():
    rows = []
    for line in ROWS.open():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def by_bucket(rows, key):
    out = {}
    for b in ORDER:
        out[b] = med([r.get(key) for r in rows if r["bucket"] == b and not r.get("error")])
    return out


def part2_3(rows):
    """Resting-order fills and fill selection, Q1-Q3 (window A only).

    Buy arms: M fills at open ask; X limit at mid0 fills iff session min ask <= mid0;
    P limit at open bid fills iff session min ask <= open bid.
    Sell arms mirror it on max bid. P&L is measured to the session's last kept trade.
    An unfilled day holds nothing and contributes 0 to the unconditional mean - which
    is exactly why the conditional means are reported beside it.
    """
    res = {}
    for side in ("buy", "sell"):
        for arm in ("M", "X", "P"):
            pnl_all, pnl_fill, filled, unfilled_m, spread_saved = [], [], 0, [], []
            n = 0
            for r in rows:
                if r["bucket"] not in PRIMARY or r.get("error"):
                    continue
                ob, oa, c = r.get("open_bid"), r.get("open_ask"), r.get("close_price")
                mn, mx = r.get("A_min_ask"), r.get("A_max_bid")
                if None in (ob, oa, c, mn, mx) or oa <= 0 or ob <= 0 or c <= 0:
                    continue
                mid0 = (ob + oa) / 2.0
                n += 1
                if side == "buy":
                    px = {"M": oa, "X": mid0, "P": ob}[arm]
                    fill = True if arm == "M" else (mn <= px)
                    pnl = (c - px) / px * 10000.0
                    base = (c - oa) / oa * 10000.0
                else:
                    px = {"M": ob, "X": mid0, "P": oa}[arm]
                    fill = True if arm == "M" else (mx >= px)
                    pnl = (px - c) / px * 10000.0
                    base = (ob - c) / ob * 10000.0
                pnl_all.append(pnl if fill else 0.0)
                if fill:
                    pnl_fill.append(pnl)
                    filled += 1
                    spread_saved.append(abs(px - (oa if side == "buy" else ob)) / px * 10000.0)
                else:
                    unfilled_m.append(base)
            res[f"{side}_{arm}"] = {
                "n_ticker_days": n,
                "fill_rate": filled / n if n else None,
                "mean_pnl_bp_all_days": (sum(pnl_all) / len(pnl_all)) if pnl_all else None,
                "mean_pnl_bp_filled_days": (sum(pnl_fill) / len(pnl_fill)) if pnl_fill else None,
                "median_spread_saved_bp_when_filled": med(spread_saved),
                "mean_marketable_pnl_bp_on_UNFILLED_days": (
                    sum(unfilled_m) / len(unfilled_m)) if unfilled_m else None,
            }
    return res


def main() -> int:
    rows = load()
    ok = [r for r in rows if not r.get("error")]
    out = {
        "n_rows": len(rows), "n_errors": len(rows) - len(ok),
        "n_no_quote_state": sum(1 for r in rows if r.get("no_quote_state")),
        "n_truncated": sum(1 for r in rows if r.get("truncated")),
        "break_even_bp": BREAK_EVEN_BP,
    }

    # ---- Part 1 -------------------------------------------------------------
    B_q = by_bucket(ok, "B_quoted_half_bp")
    B_e2 = by_bucket(ok, "B_eff_half_bp_F2")
    B_e1 = by_bucket(ok, "B_eff_half_bp_F1")
    A_q = by_bucket(ok, "A_quoted_half_bp")
    A_e2 = by_bucket(ok, "A_eff_half_bp_F2")
    A_e1 = by_bucket(ok, "A_eff_half_bp_F1")
    out["part1_median_half_spread_bp"] = {
        b: {"B_quoted": B_q[b], "B_eff_F2": B_e2[b], "B_eff_F1": B_e1[b],
            "A_quoted": A_q[b], "A_eff_F2": A_e2[b], "A_eff_F1": A_e1[b]}
        for b in ORDER}
    out["part1_reformation_cost_bp"] = {
        b: {"from_B_eff_F2": (B_e2[b] * REFORM_MULT) if B_e2[b] is not None else None,
            "from_A_eff_F2": (A_e2[b] * REFORM_MULT) if A_e2[b] is not None else None}
        for b in ORDER}
    eq = [B_e2[b] for b in ORDER if B_e2[b] is not None]
    out["part1_equal_weight_all_buckets"] = {
        "median_eff_half_bp_F2": st.median(eq) if eq else None,
        "reformation_bp": (st.median(eq) * REFORM_MULT) if eq else None}

    # ---- Gates --------------------------------------------------------------
    g1 = {b: (None if (B_e2[b] is None or B_q[b] is None) else B_e2[b] <= B_q[b]) for b in ORDER}
    q5 = B_q["Q5 most liquid"]
    g2 = None if q5 is None else (GATE_LO <= q5 <= GATE_HI)
    out["gates"] = {"G1_effective_le_quoted_by_bucket": g1, "G1_pass": all(v for v in g1.values() if v is not None),
                    "G2_q5_quoted_half_bp": q5, "G2_band": [GATE_LO, GATE_HI], "G2_pass": g2}
    gate_pass = bool(out["gates"]["G1_pass"]) and bool(g2)
    out["gates"]["OVERALL_PASS"] = gate_pass

    if not gate_pass:
        out["verdict"] = "L0 PIPELINE FAILURE - no other number from this run is reported"
        OUT.write_text(json.dumps(out, indent=1))
        print(json.dumps({k: out[k] for k in ("gates", "verdict")}, indent=1))
        return 0

    # ---- Parts 2 and 3 ------------------------------------------------------
    out["part2_3"] = part2_3(ok)

    # ---- Section 7 ----------------------------------------------------------
    prim = [B_e2[b] for b in PRIMARY if B_e2[b] is not None]
    marketable = (st.median(prim) * REFORM_MULT) if prim else None
    out["primary_marketable_reformation_bp"] = marketable
    bx = out["part2_3"]["buy_X"]; bm = out["part2_3"]["buy_M"]
    net_adv = (None if (bx["mean_pnl_bp_all_days"] is None or bm["mean_pnl_bp_all_days"] is None)
               else bx["mean_pnl_bp_all_days"] - bm["mean_pnl_bp_all_days"])
    out["policy_X_net_advantage_bp_per_ticker_day_buy_side"] = net_adv
    if marketable is None:
        out["verdict"] = "L4 UNRESOLVED - primary cost not computable"
    elif marketable < BREAK_EVEN_BP:
        out["verdict"] = f"L1 - measured {marketable:.1f} bp < {BREAK_EVEN_BP} bp break-even; the Set-2 FAIL AS BUILT verdict must be revised"
    elif net_adv is not None and (marketable - 2 * net_adv) < BREAK_EVEN_BP:
        out["verdict"] = f"L2 - marketable {marketable:.1f} bp, passive execution closes the gap"
    else:
        out["verdict"] = f"L3 - marketable {marketable:.1f} bp >= {BREAK_EVEN_BP} bp and passive execution does not close it; the micro-cap route is closed on cost"
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
