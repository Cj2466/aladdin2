"""Corrected-cost re-audit, round_c — executes the frozen design in
data/research_runs/edge_cost_reaudit_corrected_PREREGISTRATION.txt (sha256
a17e993f647629236939d2af9886b9010f7d4a9a84609f3ea2bed843ae13c80b, frozen
2026-08-30 01:48 +0700, BEFORE this script first ran).

Same 30-definition ROUND_C_FAMILY, same point-in-time universe and window as
the 2026-08-28 re-audit (MEMBERSHIP_DATA_START 2015-01-07 -> 2026-08-26),
one shared data fetch, FIVE passes through the existing
screen_cross_sectional_universe mechanism (nothing reimplemented):

  RC-control     : flat_bps 5.0   (comparability anchor on this fetch)
  RC-low         : flat_bps 1.0
  RC-mid         : flat_bps 2.0
  RC-high        : flat_bps 3.5
  RC-edge-ranked : edge_spread with the EDGE half-spread frame rescaled by
                   ONE scalar so its pooled median charged cell equals 2.0bp
                   one-way (EDGE keeps only its relative ranking, per
                   spread_estimator.py's KNOWN LIMITATION block); NaN
                   fallback rate also 2.0bp.

Every one of the 30 specs of every pass is persisted (family_key "round_c",
run_tags below). Run from inside this worktree's backend/ so `app` and
./aladdin2.db resolve to THIS worktree.
"""

import json
import time
from dataclasses import asdict
from datetime import date, timedelta

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
from app.services.research_lab.edge_cost_reaudit_scenarios import (
    scale_half_spread_frame_to_median,
)
from app.services.research_lab.multi_signal_combination import PSR_SELECTION_THRESHOLD
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    get_universe_over,
)
from app.services.research_lab.spread_estimator import (
    COST_MODEL_WINDOW_DAYS,
    build_edge_half_spread_frame,
)

SCRATCH = (
    "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/"
    "be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
)
FAMILY_KEY = "round_c"
RUN_TAG_PREFIX = "edge_cost_reaudit_corrected_2026-08-30"

# Pinned to the archived original run's window, same as the 2026-08-28
# re-audit, so every comparison stays like-for-like.
START = MEMBERSHIP_DATA_START
END = date(2026, 8, 26)

# The frozen section 3 grid: (tag suffix, flat one-way bps). The edge_ranked
# pass is handled separately below because it swaps the cost MODEL, not just
# the rate.
FLAT_PASSES: list[tuple[str, float]] = [
    ("flat_control", 5.0),
    ("low_1bp", 1.0),
    ("mid_2bp", 2.0),
    ("high_3p5bp", 3.5),
]
EDGE_RANKED_SUFFIX = "edge_ranked_2bp"
EDGE_RANKED_TARGET_HALF_SPREAD = 0.0002  # 2.0bp one-way, unit fraction of price
EDGE_RANKED_FALLBACK_BPS = 2.0


def log(msg: str) -> None:
    print(f"[{time.strftime('%X')}] {msg}", flush=True)


def summarize(suffix: str, results) -> None:
    cleared = [
        r
        for r in results
        if r.deflated_sharpe.psr_vs_zero is not None
        and r.deflated_sharpe.psr_vs_zero >= PSR_SELECTION_THRESHOLD
    ]
    log(
        f"PASS {suffix}: {len(results)} specs, "
        f"{sum(1 for r in results if r.sharpe_annualized > 0)} positive Sharpe, "
        f"{len(cleared)} clear PSR >= {PSR_SELECTION_THRESHOLD}"
    )
    for r in sorted(results, key=lambda r: -r.sharpe_annualized)[:5]:
        log(
            f"  top: {r.pattern_id} sharpe={r.sharpe_annualized:.3f} "
            f"psr={r.deflated_sharpe.psr_vs_zero} dsr={r.deflated_sharpe.dsr}"
        )


def main() -> None:
    provider = YFinanceProvider()
    universe = get_universe_over(START, END)
    padded_start = START - timedelta(days=PRICE_HISTORY_PADDING_CALENDAR_DAYS)
    log(f"universe={len(universe)} tickers; fetching daily OHLCV {padded_start} -> {END}...")
    t0 = time.time()
    frames, missing = provider.get_daily_ohlcv(universe, padded_start, END)
    log(
        f"fetched in {time.time() - t0:.1f}s, close shape={frames['close'].shape}, "
        f"unresolved={len(missing)}"
    )

    from app.db import SessionLocal
    from app.services.research_lab.cross_sectional_persistence import (
        persist_cross_sectional_trial_results,
    )

    def persist(suffix: str, results) -> None:
        run_tag = f"{RUN_TAG_PREFIX}_{suffix}"
        with open(f"{SCRATCH}/round_c_corrected_{suffix}.json", "w") as f:
            json.dump(
                {"run_tag": run_tag, "n_trials": len(ROUND_C_FAMILY), "results": [asdict(r) for r in results]},
                f,
                indent=2,
                default=str,
            )
        db = SessionLocal()
        try:
            n = persist_cross_sectional_trial_results(db, FAMILY_KEY, results, run_tag=run_tag)
            log(f"PASS {suffix}: persisted {n} rows under run_tag={run_tag}")
        finally:
            db.close()

    data_flat = CrossSectionalData(
        close=frames["close"], open=frames["open"], volume=frames["volume"]
    )
    for suffix, cost_bps in FLAT_PASSES:
        config = CrossSectionalConfig(cost_bps=cost_bps)
        config.formation_start = START
        log(f"PASS {suffix}: flat_bps cost_bps={cost_bps}, {len(ROUND_C_FAMILY)} specs...")
        t0 = time.time()
        results = screen_cross_sectional_universe(data_flat, ROUND_C_FAMILY, config)
        log(f"PASS {suffix}: screen done in {time.time() - t0:.1f}s, {len(results)} usable replays")
        persist(suffix, results)
        summarize(suffix, results)

    log(f"building EDGE half-spread frame (window {COST_MODEL_WINDOW_DAYS}d)...")
    t0 = time.time()
    edge_frame = build_edge_half_spread_frame(
        frames["open"], frames["high"], frames["low"], frames["close"]
    )
    log(f"EDGE frame built in {time.time() - t0:.1f}s")
    scaled, scale, observed_median = scale_half_spread_frame_to_median(
        edge_frame, EDGE_RANKED_TARGET_HALF_SPREAD, START
    )
    log(
        f"edge_ranked calibration: observed pooled median {observed_median * 1e4:.2f}bp, "
        f"scale={scale:.5f}, target median {EDGE_RANKED_TARGET_HALF_SPREAD * 1e4:.1f}bp"
    )
    data_edge = CrossSectionalData(
        close=frames["close"], open=frames["open"], volume=frames["volume"], half_spread=scaled
    )
    config = CrossSectionalConfig(cost_model="edge_spread", cost_bps=EDGE_RANKED_FALLBACK_BPS)
    config.formation_start = START
    log(f"PASS {EDGE_RANKED_SUFFIX}: edge_spread on the rescaled frame, {len(ROUND_C_FAMILY)} specs...")
    t0 = time.time()
    results = screen_cross_sectional_universe(data_edge, ROUND_C_FAMILY, config)
    log(f"PASS {EDGE_RANKED_SUFFIX}: screen done in {time.time() - t0:.1f}s, {len(results)} usable replays")
    for r in results:
        fb = (r.edge_flat_fallback_notional / r.total_turnover) if r.total_turnover else 0.0
        if fb > 0.02:
            log(f"  note: {r.pattern_id} flat-fallback fraction {fb:.3f}")
    persist(EDGE_RANKED_SUFFIX, results)
    summarize(EDGE_RANKED_SUFFIX, results)
    log("ALL PASSES DONE")


if __name__ == "__main__":
    main()
