"""Build D1 REAL production screening run.

Runs run_round_d1_screening against real yfinance data (no fake provider,
no synthetic data), start = MEMBERSHIP_DATA_START, end = today, matching
Round C's own convention. Writes a JSON result file so the calling process
can poll for completion without holding a live connection.
"""
import json
import sys
import time
import traceback
from datetime import date

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a327c9fd73bf9f348/backend")

OUT_PATH = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/d1_production_result.json"
PROGRESS_PATH = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/d1_production_progress.txt"


def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(PROGRESS_PATH, "a") as f:
        f.write(line + "\n")


def main() -> None:
    log("Starting Build D1 production screening run")
    from app.services.research_lab.cross_sectional_ivol import (
        ROUND_D1_FAMILY,
        run_round_d1_screening,
    )
    from app.services.research_lab.sp500_membership_history import (
        MEMBERSHIP_DATA_START,
        membership_coverage_end,
    )

    start = MEMBERSHIP_DATA_START
    end = date.today()
    log(f"start={start.isoformat()} end={end.isoformat()} "
        f"membership_coverage_end={membership_coverage_end().isoformat()}")
    log(f"Family size: {len(ROUND_D1_FAMILY)} specs")

    t0 = time.time()
    results, missing_price, missing_shares = run_round_d1_screening(start, end)
    elapsed = time.time() - t0
    log(f"Screening complete in {elapsed:.1f}s. "
        f"{len(results)} results, {len(missing_price)} missing-price tickers, "
        f"{len(missing_shares)} missing-shares tickers.")

    out = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "elapsed_seconds": elapsed,
        "family_size": len(ROUND_D1_FAMILY),
        "n_results": len(results),
        "missing_price_tickers": sorted(missing_price),
        "missing_shares_tickers": sorted(missing_shares),
        "results": [],
    }
    for r in results:
        ds = r.deflated_sharpe
        out["results"].append({
            "pattern_id": r.pattern_id,
            "family": r.family,
            "n_formations": r.n_formations,
            "n_skipped_formations": r.n_skipped_formations,
            "avg_names_per_leg": r.avg_names_per_leg,
            "n_trading_days": r.n_trading_days,
            "sharpe_annualized": r.sharpe_annualized,
            "total_cost_drag": r.total_cost_drag,
            "n_value_weighted_legs": r.n_value_weighted_legs,
            "n_value_weight_fallbacks": r.n_value_weight_fallbacks,
            "deflated_sharpe": {
                "sharpe_net_annualized": ds.sharpe_net_annualized,
                "sharpe_net_daily": ds.sharpe_net_daily,
                "n_observations": ds.n_observations,
                "skewness": ds.skewness,
                "kurtosis": ds.kurtosis,
                "psr_vs_zero": ds.psr_vs_zero,
                "n_trials": ds.n_trials,
                "sigma_sr_annualized": ds.sigma_sr_annualized,
                "expected_max_sharpe_noise_annualized": ds.expected_max_sharpe_noise_annualized,
                "dsr": ds.dsr,
                "dsr_floor_met": ds.dsr_floor_met,
                "interpretation": ds.interpretation,
            },
        })

    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2)
    log(f"Wrote results to {OUT_PATH}")
    log("DONE")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("FATAL ERROR:\n" + traceback.format_exc())
        with open(OUT_PATH, "w") as f:
            json.dump({"error": traceback.format_exc()}, f, indent=2)
        raise
