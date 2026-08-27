"""Build D1 REAL production screening re-run, THROUGH THE PRODUCTION ENTRY
POINT, with the market-cap fix in place.

Same parameters as the original reported run (start = MEMBERSHIP_DATA_START,
end = today, provider=None, config=None -> live YFinanceProvider and default
CrossSectionalConfig) so the numbers are directly comparable to the reported
table. This is the authoritative corrected result; the three-way replay in
d1_bug_impact_replay.py is what isolates WHY it differs.
"""
import json
import sys
import time
import traceback
from datetime import date

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")

BASE = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
OUT = f"{BASE}/d1_production_result_fixed.json"
LOG = f"{BASE}/d1_production_fixed.log"


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def main():
    from app.services.research_lab.cross_sectional_ivol import (
        ROUND_D1_FAMILY,
        run_round_d1_screening,
    )
    from app.services.research_lab.sp500_membership_history import MEMBERSHIP_DATA_START

    start = MEMBERSHIP_DATA_START
    end = date.today()
    log(f"start={start} end={end} family={len(ROUND_D1_FAMILY)} specs")

    t0 = time.time()
    results, missing_price, missing_shares = run_round_d1_screening(start, end)
    elapsed = time.time() - t0
    log(f"complete in {elapsed:.1f}s: {len(results)} results, "
        f"{len(missing_price)} missing-price, {len(missing_shares)} without shares")

    out = {
        "start": start.isoformat(), "end": end.isoformat(),
        "elapsed_seconds": elapsed, "family_size": len(ROUND_D1_FAMILY),
        "n_results": len(results),
        "missing_price_tickers": sorted(missing_price),
        "missing_shares_tickers": sorted(missing_shares),
        "results": [],
    }
    for r in results:
        ds = r.deflated_sharpe
        out["results"].append({
            "pattern_id": r.pattern_id,
            "n_formations": r.n_formations,
            "n_skipped_formations": r.n_skipped_formations,
            "avg_names_per_leg": r.avg_names_per_leg,
            "n_trading_days": r.n_trading_days,
            "sharpe_annualized": r.sharpe_annualized,
            "total_cost_drag": r.total_cost_drag,
            "n_value_weighted_legs": r.n_value_weighted_legs,
            "n_value_weight_fallbacks": r.n_value_weight_fallbacks,
            "dsr": ds.dsr,
            "psr_vs_zero": ds.psr_vs_zero,
            "n_trials": ds.n_trials,
            "dsr_floor_met": ds.dsr_floor_met,
            "interpretation": ds.interpretation,
        })

    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)
    log(f"WROTE {OUT}")
    log("DONE")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("FATAL:\n" + traceback.format_exc())
        raise
