"""EDGE-cost re-audit, job A: the SAME pre-declared 30-definition Round C
family (disposition_52wk_high + disposition_capital_gains_overhang +
overnight_intraday_tug_of_war, cross_sectional_patterns.ROUND_C_FAMILY),
over the SAME window as the archived original production run
(MEMBERSHIP_DATA_START 2015-01-07 -> 2026-08-26), run TWICE on ONE shared
data fetch:

  1. flat control — CrossSectionalConfig() defaults (cost_model="flat_bps",
     5bps one-way), i.e. the original run's exact configuration, to check
     replication against the archived round_c_final_report.txt and absorb
     any yfinance data drift since 2026-08-26.
  2. edge_spread  — cost_model="edge_spread": each ticker's traded notional
     charged its OWN trailing EDGE half-spread (window 63 =
     spread_estimator.COST_MODEL_WINDOW_DAYS), flat 5bps fallback for
     ticker/dates with no usable estimate, fallback notional counted.

PRE-DECLARED before seeing any result: same family list, same
screen_cross_sectional_universe machinery, same n_trials=30, window 63,
both runs persisted spec-by-spec (all 30, not a favorable subset).

KNOWN, PRE-VERIFIED estimator context (2026-08-28, before this run): EDGE
on daily OHLC carries a vol-scaled noise floor (~6-12bps half-spread at
zero TRUE spread on synthetic data, window 63) and estimates ~15-30bps
half-spreads on real mega-caps whose true effective spreads are ~1-3bps —
so for this liquid universe the edge model is STRICTLY HARSHER than flat
5bps, an upper-bound cost run. Declared before results existed.
"""
import json
import sys
import time
from dataclasses import asdict
from datetime import date, timedelta

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/edge-cost-model/backend")

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    screen_cross_sectional_universe,
)
from app.services.research_lab.cross_sectional_patterns import (
    PRICE_HISTORY_PADDING_CALENDAR_DAYS,
    ROUND_C_FAMILY,
)
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    get_universe_over,
)
from app.services.research_lab.spread_estimator import (
    COST_MODEL_WINDOW_DAYS,
    build_edge_half_spread_frame,
)

SCRATCH = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
OUT_JSON = f"{SCRATCH}/round_c_reaudit_results.json"
OUT_TXT = f"{SCRATCH}/round_c_reaudit_report.txt"

RUN_TAG_FLAT = "edge_cost_reaudit_2026-08-28_flat_control"
RUN_TAG_EDGE = "edge_cost_reaudit_2026-08-28_edge_spread"
FAMILY_KEY = "round_c"

# Pinned to the archived original run's exact window (round_c_final_report:
# "Window: 2015-01-07 -> 2026-08-26"), NOT date.today(), so the flat
# control is comparable to the archive as directly as yfinance allows.
START = MEMBERSHIP_DATA_START
END = date(2026, 8, 26)


def log(msg: str) -> None:
    print(f"[{time.strftime('%X')}] {msg}", flush=True)


def main() -> None:
    provider = YFinanceProvider()
    universe = get_universe_over(START, END)
    padded_start = START - timedelta(days=PRICE_HISTORY_PADDING_CALENDAR_DAYS)
    log(f"universe={len(universe)} tickers; fetching daily OHLCV {padded_start} -> {END}...")
    t0 = time.time()
    frames, missing = provider.get_daily_ohlcv(universe, padded_start, END)
    log(f"fetched in {time.time() - t0:.1f}s, close shape={frames['close'].shape}, unresolved={len(missing)}")

    log(f"building EDGE half-spread frame (window {COST_MODEL_WINDOW_DAYS}d)...")
    t0 = time.time()
    half_spread = build_edge_half_spread_frame(
        frames["open"], frames["high"], frames["low"], frames["close"],
        window_days=COST_MODEL_WINDOW_DAYS,
    )
    log(f"half-spread frame built in {time.time() - t0:.1f}s")

    # Spread sanity statistics, recorded BEFORE any screening result exists.
    med = half_spread.median() * 1e4
    med_clean = med.dropna()
    q = med_clean.quantile([0.05, 0.25, 0.50, 0.75, 0.95]).round(2).to_dict()
    named = {t: round(float(med[t]), 2) for t in ("AAPL", "MSFT", "JPM", "XOM", "NVDA") if t in med.index and med[t] == med[t]}
    nan_frac_after_warmup = float(half_spread.iloc[COST_MODEL_WINDOW_DAYS:].isna().mean().mean())
    log(f"per-ticker MEDIAN half-spread bps: quantiles={q}; named={named}; "
        f"overall NaN cell fraction after warmup={nan_frac_after_warmup:.3f}")

    data_flat = CrossSectionalData(close=frames["close"], open=frames["open"], volume=frames["volume"])
    data_edge = CrossSectionalData(
        close=frames["close"], open=frames["open"], volume=frames["volume"], half_spread=half_spread
    )

    config_flat = CrossSectionalConfig()
    config_flat.formation_start = START
    config_edge = CrossSectionalConfig(cost_model="edge_spread")
    config_edge.formation_start = START

    log("CONTROL run: flat_bps (original configuration), 30 specs...")
    t0 = time.time()
    results_flat = screen_cross_sectional_universe(data_flat, ROUND_C_FAMILY, config_flat)
    log(f"control screen done in {time.time() - t0:.1f}s, {len(results_flat)} usable replays")

    log("EDGE run: cost_model='edge_spread', same 30 specs, same data...")
    t0 = time.time()
    results_edge = screen_cross_sectional_universe(data_edge, ROUND_C_FAMILY, config_edge)
    log(f"edge screen done in {time.time() - t0:.1f}s, {len(results_edge)} usable replays")

    payload = {
        "window": f"{START} -> {END}",
        "n_trials": len(ROUND_C_FAMILY),
        "universe_size": len(universe),
        "unresolved_tickers": sorted(missing),
        "edge_window_days": COST_MODEL_WINDOW_DAYS,
        "median_half_spread_bps_quantiles": q,
        "median_half_spread_bps_named": named,
        "nan_cell_fraction_after_warmup": nan_frac_after_warmup,
        "flat_control": {"run_tag": RUN_TAG_FLAT, "results": [asdict(r) for r in results_flat]},
        "edge_spread": {"run_tag": RUN_TAG_EDGE, "results": [asdict(r) for r in results_edge]},
    }
    with open(OUT_JSON, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    log(f"wrote {OUT_JSON}")

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

    flat_by_id = {r.pattern_id: r for r in results_flat}
    edge_by_id = {r.pattern_id: r for r in results_edge}
    lines = [
        f"Round C EDGE-cost re-audit — window {START} -> {END}, n_trials=30 (both runs)",
        f"EDGE window: {COST_MODEL_WINDOW_DAYS}d; median half-spread bps quantiles {q}; named {named}",
        "",
        f"{'pattern_id':<32} {'flat_sharpe':>11} {'flat_dsr':>9} {'edge_sharpe':>11} {'edge_dsr':>9} {'edge_cost':>10} {'flat_cost':>10} {'fb_frac':>8}",
    ]
    for pid in sorted(flat_by_id, key=lambda p: -flat_by_id[p].sharpe_annualized):
        rf = flat_by_id[pid]
        re_ = edge_by_id.get(pid)
        fb = (re_.edge_flat_fallback_notional / re_.total_turnover) if re_ is not None and re_.total_turnover else 0.0
        lines.append(
            f"{pid:<32} {rf.sharpe_annualized:>11.3f} {rf.deflated_sharpe.dsr if rf.deflated_sharpe.dsr is not None else float('nan'):>9.3f} "
            f"{(re_.sharpe_annualized if re_ else float('nan')):>11.3f} "
            f"{(re_.deflated_sharpe.dsr if re_ and re_.deflated_sharpe.dsr is not None else float('nan')):>9.3f} "
            f"{(re_.total_cost_drag if re_ else float('nan')):>10.4f} {rf.total_cost_drag:>10.4f} {fb:>8.3f}"
        )
    report = "\n".join(lines)
    with open(OUT_TXT, "w") as f:
        f.write(report + "\n")
    print(report, flush=True)
    log("DONE")


if __name__ == "__main__":
    main()
