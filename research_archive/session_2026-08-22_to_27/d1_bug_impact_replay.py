"""STEP 2: did the market-cap bug actually change Build D1's already-reported
production numbers?

Replays the SAME real formations, on the SAME real data (fetched once by
d1_bug_impact_fetch.py), under three market-cap definitions:

  A shipped     : adj_close * raw_shares            <- the code that actually ran
  B split_fixed : adj_close * split_adjusted_shares <- isolates the split bug alone
  C fixed       : basis_close * split_adjusted_shares <- the new production path
                  (basis_close = split-adjusted, dividend-UNadjusted)

Part 1 diffs the resulting LEG WEIGHTS formation by formation.
Part 2 runs the full 21-spec screening under each and diffs the results.
"""
import json
import pickle
import sys
import time
import traceback
from datetime import date

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")

import numpy as np
import pandas as pd

BASE = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
LOG = f"{BASE}/d1_impact_replay.log"
OUT = f"{BASE}/d1_impact_replay.json"


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def main():
    from app.services.research_lab.cross_sectional import (
        CrossSectionalConfig,
        CrossSectionalData,
        _resolve_leg_weights,
        screen_cross_sectional_universe,
        select_leg_tickers,
    )
    from app.services.research_lab.cross_sectional_ivol import (
        ROUND_D1_FAMILY,
        build_point_in_time_market_cap,
    )
    from app.services.research_lab.sp500_membership_history import was_member

    with open(f"{BASE}/d1_impact_data.pkl", "rb") as f:
        d = pickle.load(f)

    start, end = d["start"], d["end"]
    close = d["close"]
    shares = d["shares"]
    splits = d["splits"]
    mcap_close = d["mcap_close"].reindex(index=close.index, columns=close.columns)

    log(f"close {close.shape}  shares {len(shares)}  splits {len(splits)}  "
        f"missing_price {len(d['missing_price'])}")

    caps = {}
    caps["A_shipped"], _ = build_point_in_time_market_cap(close, shares, {})
    caps["B_split_fixed"], _ = build_point_in_time_market_cap(close, shares, splits)
    caps["C_fixed"], _ = build_point_in_time_market_cap(mcap_close, shares, splits)
    log("built three market-cap frames")

    # How different are the market caps themselves, on days both are usable?
    both = caps["A_shipped"].notna() & caps["B_split_fixed"].notna()
    ratio_ab = (caps["B_split_fixed"] / caps["A_shipped"])[both]
    flat_ab = ratio_ab.to_numpy().ravel()
    flat_ab = flat_ab[np.isfinite(flat_ab)]
    ratio_ac = (caps["C_fixed"] / caps["A_shipped"])[both]
    flat_ac = ratio_ac.to_numpy().ravel()
    flat_ac = flat_ac[np.isfinite(flat_ac)]
    cap_summary = {
        "n_cells": int(flat_ab.size),
        "split_fix_changed_cells": int((np.abs(flat_ab - 1.0) > 1e-9).sum()),
        "split_fix_max_ratio": float(flat_ab.max()),
        "full_fix_min_ratio": float(flat_ac.min()),
        "full_fix_max_ratio": float(flat_ac.max()),
        "full_fix_median_ratio": float(np.median(flat_ac)),
    }
    log(f"market-cap cell diffs: {cap_summary}")

    # ---------------- Part 1: direct leg-weight diff -----------------------
    log("PART 1: replaying real formations and diffing leg weights ...")
    index = close.index
    n = len(index)
    weight_diff = {
        "legs_compared": 0,
        "legs_value_weighted_in_A": 0,
        "legs_value_weighted_in_C": 0,
        "legs_whose_weights_changed": 0,
        "max_abs_weight_change": 0.0,
        "sum_abs_weight_change": 0.0,
        "examples": [],
    }

    for spec in ROUND_D1_FAMILY:
        first_formation = max(spec.lookback_days, int(np.flatnonzero(index.date >= start)[0]))
        for i in range(first_formation, n - 1, spec.holding_days):
            formation_day = index[i].date()
            formation_close = close.iloc[i]
            eligible = [
                t for t in close.columns
                if was_member(t, formation_day) and np.isfinite(formation_close[t])
            ]
            if not eligible:
                continue
            row_start = max(0, i + 1 - spec.lookback_days)
            view = CrossSectionalData(close=close.iloc[row_start : i + 1].loc[:, eligible])
            signal = spec.signal_fn(view)
            top, bottom = select_leg_tickers(signal, spec.rank_fraction)
            n_ranked = int(signal.dropna().shape[0])
            if len(top) < 5 or 2 * len(top) > n_ranked:
                continue

            legs = [(top, True)]
            if spec.portfolio == "long_short":
                legs.append((bottom, False))

            for tickers, higher in legs:
                wa, fa = _resolve_leg_weights(
                    tickers, signal, higher_is_stronger=higher,
                    leg_weighting="value", market_cap=caps["A_shipped"].iloc[i],
                )
                wc, fc = _resolve_leg_weights(
                    tickers, signal, higher_is_stronger=higher,
                    leg_weighting="value", market_cap=caps["C_fixed"].iloc[i],
                )
                weight_diff["legs_compared"] += 1
                if not fa:
                    weight_diff["legs_value_weighted_in_A"] += 1
                if not fc:
                    weight_diff["legs_value_weighted_in_C"] += 1
                changed = False
                for t in tickers:
                    delta = abs(wa.get(t, 0.0) - wc.get(t, 0.0))
                    if delta > 1e-9:
                        changed = True
                        weight_diff["sum_abs_weight_change"] += delta
                        if delta > weight_diff["max_abs_weight_change"]:
                            weight_diff["max_abs_weight_change"] = delta
                        if len(weight_diff["examples"]) < 12 and delta > 0.01:
                            weight_diff["examples"].append({
                                "pattern": spec.pattern_id,
                                "formation": str(formation_day),
                                "ticker": t,
                                "weight_shipped": round(wa.get(t, 0.0), 6),
                                "weight_fixed": round(wc.get(t, 0.0), 6),
                            })
                if changed:
                    weight_diff["legs_whose_weights_changed"] += 1
        log(f"  ...{spec.pattern_id} done "
            f"({weight_diff['legs_compared']} legs so far, "
            f"{weight_diff['legs_whose_weights_changed']} changed)")

    log(f"PART 1 RESULT: {json.dumps({k: v for k, v in weight_diff.items() if k != 'examples'})}")

    # ---------------- Part 2: full screening, three ways -------------------
    screenings = {}
    for label in ("A_shipped", "B_split_fixed", "C_fixed"):
        log(f"PART 2: full 21-spec screening under {label} ...")
        config = CrossSectionalConfig()
        config.formation_start = start
        data = CrossSectionalData(close=close, market_cap=caps[label])
        t0 = time.time()
        results = screen_cross_sectional_universe(data, ROUND_D1_FAMILY, config)
        log(f"  {label}: {len(results)} results in {time.time()-t0:.1f}s")
        screenings[label] = [
            {
                "pattern_id": r.pattern_id,
                "sharpe_annualized": r.sharpe_annualized,
                "dsr": r.deflated_sharpe.dsr,
                "psr_vs_zero": r.deflated_sharpe.psr_vs_zero,
                "n_trials": r.deflated_sharpe.n_trials,
                "n_trading_days": r.n_trading_days,
                "n_formations": r.n_formations,
                "n_value_weighted_legs": r.n_value_weighted_legs,
                "n_value_weight_fallbacks": r.n_value_weight_fallbacks,
                "total_cost_drag": r.total_cost_drag,
                "avg_names_per_leg": r.avg_names_per_leg,
            }
            for r in results
        ]

    with open(OUT, "w") as f:
        json.dump(
            {
                "start": str(start), "end": str(end),
                "cap_summary": cap_summary,
                "weight_diff": weight_diff,
                "screenings": screenings,
                "n_priced": int(close.shape[1]),
                "missing_price": len(d["missing_price"]),
                "missing_shares": len(d["missing_shares"]),
                "n_tickers_with_splits": len(splits),
            },
            f, indent=2,
        )
    log(f"WROTE {OUT}")
    log("DONE")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("FATAL:\n" + traceback.format_exc())
        raise
