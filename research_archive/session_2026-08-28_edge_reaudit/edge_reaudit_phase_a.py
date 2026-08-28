"""EDGE-cost re-audit, job B: the expanded Phase A intraday family (the
SAME pre-declared 212-definition PATTERN_FAMILY over the SAME 55-ticker
PATTERN_MINING_UNIVERSE, hourly bars), run TWICE on one shared bars fetch:

  1. flat control  — INTRADAY_COST_BPS (5bps one-way), the original cost
     model, to establish the like-for-like baseline on today's re-fetched
     bars (yfinance's 60m window slides daily, so the archived
     full_screen_results.json numbers are not byte-comparable; this
     control is).
  2. edge_spread   — per-ticker one-way cost = the ticker's MEDIAN
     trailing EDGE half-spread (window 63, spread_estimator.
     COST_MODEL_WINDOW_DAYS) from daily OHLC over the same ~2y span.
     Time-constant per ticker by the wiring's own disclosed limitation
     (engine.py charges one flat rate per run; see run_pattern_backtest's
     docstring).

PRE-DECLARED before seeing any result, per the project's standing
p-hacking discipline: same family, same universe, same
screen_pattern_universe / n_trials=len(PATTERN_FAMILY)=212 DSR machinery,
window 63 for the spread estimate, median as the per-ticker summary. Every
result is persisted (both runs, every spec), not just interesting ones.

KNOWN, PRE-VERIFIED estimator context (2026-08-28, before this run): EDGE
on daily OHLC has a vol-scaled noise floor (~6/9/12bps half-spread at
1/1.5/2% daily vol for a TRUE spread of zero, measured on synthetic data
at window 63), and on real mega-caps estimates ~15-30bps half-spreads
where true effective spreads are ~1-3bps. This makes the edge model
STRICTLY HARSHER than the flat 5bps for liquid names — an upper-bound
cost run, not a lower-bound one. Declared here so the interpretation
cannot be adjusted after the fact.
"""
import json
import sys
import time
from dataclasses import asdict
from datetime import date, timedelta

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/edge-cost-model/backend")

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.intraday_patterns import (
    INTRADAY_COST_BPS,
    PATTERN_FAMILY,
    PATTERN_MINING_UNIVERSE,
    screen_pattern_universe,
)
from app.services.research_lab.spread_estimator import (
    COST_MODEL_WINDOW_DAYS,
    build_edge_half_spread_frame,
)

SCRATCH = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
OUT_FLAT = f"{SCRATCH}/phase_a_reaudit_flat_control.json"
OUT_EDGE = f"{SCRATCH}/phase_a_reaudit_edge_spread.json"
OUT_COSTS = f"{SCRATCH}/phase_a_reaudit_per_ticker_costs.json"

RUN_TAG_FLAT = "edge_cost_reaudit_2026-08-28_flat_control"
RUN_TAG_EDGE = "edge_cost_reaudit_2026-08-28_edge_spread"
FAMILY_KEY = "phase_a_intraday_expanded"


def log(msg: str) -> None:
    print(f"[{time.strftime('%X')}] {msg}", flush=True)


def dump(path: str, payload: dict) -> None:
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    log(f"wrote {path}")


def main() -> None:
    provider = YFinanceProvider()

    log(f"fetching hourly bars for {len(PATTERN_MINING_UNIVERSE)} tickers...")
    t0 = time.time()
    bars_by_ticker, missing = provider.get_intraday_bars(PATTERN_MINING_UNIVERSE)
    log(f"hourly bars fetched in {time.time() - t0:.1f}s, resolved {len(bars_by_ticker)}, missing={missing}")
    if missing:
        # Same loud rule as the original run: the universe was pre-verified.
        raise SystemExit(f"missing hourly tickers: {missing}")

    # Daily OHLC over (a padding beyond) the same ~2y span the hourly bars
    # cover, for the per-ticker EDGE half-spread derivation.
    end = date.today()
    start = end - timedelta(days=850)
    log(f"fetching daily OHLC {start} -> {end} for the spread derivation...")
    frames, daily_missing = provider.get_daily_ohlcv(list(PATTERN_MINING_UNIVERSE), start, end)
    log(f"daily OHLC fetched, {frames['close'].shape}, missing={daily_missing}")

    half_spread = build_edge_half_spread_frame(
        frames["open"], frames["high"], frames["low"], frames["close"],
        window_days=COST_MODEL_WINDOW_DAYS,
    )
    median_half_bps = (half_spread.median() * 1e4).to_dict()

    # Explicit per-ticker cost dict covering EVERY hourly ticker, per
    # screen_pattern_universe's loud-contract: any ticker with no usable
    # EDGE estimate gets the flat INTRADAY_COST_BPS deliberately, and is
    # recorded here as a counted, named fallback.
    cost_bps_by_ticker: dict[str, float] = {}
    fallback_tickers: list[str] = []
    for t in bars_by_ticker:
        m = median_half_bps.get(t)
        if m is not None and m == m and m > 0:  # non-NaN, positive
            cost_bps_by_ticker[t] = float(m)
        else:
            cost_bps_by_ticker[t] = float(INTRADAY_COST_BPS)
            fallback_tickers.append(t)
    dump(OUT_COSTS, {
        "window_days": COST_MODEL_WINDOW_DAYS,
        "summary_statistic": "median of trailing EDGE half-spread, bps, one-way",
        "cost_bps_by_ticker": cost_bps_by_ticker,
        "flat_fallback_tickers": fallback_tickers,
        "flat_cost_bps": INTRADAY_COST_BPS,
    })
    ordered = sorted(cost_bps_by_ticker.values())
    log(f"per-ticker EDGE cost (bps): min={ordered[0]:.1f} p25={ordered[len(ordered)//4]:.1f} "
        f"median={ordered[len(ordered)//2]:.1f} p75={ordered[3*len(ordered)//4]:.1f} max={ordered[-1]:.1f}; "
        f"fallbacks={fallback_tickers}")

    log(f"CONTROL run: flat {INTRADAY_COST_BPS}bps, {len(PATTERN_FAMILY)} patterns x {len(bars_by_ticker)} tickers...")
    t0 = time.time()
    results_flat = screen_pattern_universe(bars_by_ticker, patterns=PATTERN_FAMILY)
    log(f"control screen done in {(time.time() - t0)/60:.1f} min, {len(results_flat)} measurable results")
    dump(OUT_FLAT, {
        "run_tag": RUN_TAG_FLAT, "n_trials": len(PATTERN_FAMILY),
        "cost_model": f"flat {INTRADAY_COST_BPS}bps",
        "results": [asdict(r) for r in results_flat],
    })

    log("EDGE run: per-ticker EDGE-derived costs, same family, same bars...")
    t0 = time.time()
    results_edge = screen_pattern_universe(
        bars_by_ticker, patterns=PATTERN_FAMILY, cost_bps_by_ticker=cost_bps_by_ticker
    )
    log(f"edge screen done in {(time.time() - t0)/60:.1f} min, {len(results_edge)} measurable results")
    dump(OUT_EDGE, {
        "run_tag": RUN_TAG_EDGE, "n_trials": len(PATTERN_FAMILY),
        "cost_model": f"per-ticker EDGE median half-spread (window {COST_MODEL_WINDOW_DAYS}d), flat fallback {INTRADAY_COST_BPS}bps",
        "results": [asdict(r) for r in results_edge],
    })

    # Persist BOTH runs, every spec, to the same table every family uses.
    from app.db import SessionLocal
    from app.services.research_lab.cross_sectional_persistence import (
        persist_cross_sectional_trial_results,
    )
    db = SessionLocal()
    try:
        n1 = persist_cross_sectional_trial_results(db, FAMILY_KEY, results_flat, run_tag=RUN_TAG_FLAT)
        n2 = persist_cross_sectional_trial_results(db, FAMILY_KEY, results_edge, run_tag=RUN_TAG_EDGE)
        log(f"persisted {n1} control rows + {n2} edge rows to cross_sectional_trial_results")
    finally:
        db.close()

    for label, results in (("FLAT CONTROL", results_flat), ("EDGE SPREAD", results_edge)):
        pos = [r for r in results if r.sharpe_annualized > 0]
        cleared = [r for r in results if r.deflated_sharpe.dsr is not None and r.deflated_sharpe.dsr > 0.5]
        log(f"{label}: {len(results)} measurable, {len(pos)} positive raw Sharpe, {len(cleared)} with DSR>0.5")
        for r in results[:5]:
            log(f"  top: {r.pattern_id} [{r.family}] sharpe={r.sharpe_annualized:.3f} dsr={r.deflated_sharpe.dsr}")
    log("DONE")


if __name__ == "__main__":
    main()
