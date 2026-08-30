"""Corrected-cost re-audit, phase_a_intraday_expanded — executes the frozen
design in data/research_runs/edge_cost_reaudit_corrected_PREREGISTRATION.txt
(sha256 a17e993f647629236939d2af9886b9010f7d4a9a84609f3ea2bed843ae13c80b,
frozen 2026-08-30 01:48 +0700, BEFORE this script first ran).

Same 212-definition PATTERN_FAMILY over the same 55-ticker
PATTERN_MINING_UNIVERSE, hourly bars, one shared fetch, FOUR passes through
the existing screen_pattern_universe mechanism (nothing reimplemented):

  PA-control : flat 5.0bp every ticker (comparability anchor on this fetch)
  PA-low     : large tier 0.75bp / mid-small tier  5.0bp, tick-floored
  PA-mid     : large tier 1.50bp / mid-small tier 10.0bp, tick-floored
  PA-high    : large tier 3.00bp / mid-small tier 20.0bp, tick-floored

Every measurable pattern of every pass is persisted (family_key
"phase_a_intraday_expanded", run_tags below). Run from inside this
worktree's backend/ so `app` and ./aladdin2.db resolve to THIS worktree.
"""

import json
import time
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.edge_cost_reaudit_scenarios import (
    tiered_cost_bps_by_ticker,
)
from app.services.research_lab.intraday_patterns import (
    INTRADAY_COST_BPS,
    PATTERN_FAMILY,
    PATTERN_MINING_UNIVERSE,
    PATTERN_MINING_UNIVERSE_LARGE_CAP,
    PATTERN_MINING_UNIVERSE_MID_SMALL_CAP,
    screen_pattern_universe,
)
from app.services.research_lab.multi_signal_combination import PSR_SELECTION_THRESHOLD

SCRATCH = (
    "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/"
    "be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
)
FAMILY_KEY = "phase_a_intraday_expanded"
RUN_TAG_PREFIX = "edge_cost_reaudit_corrected_2026-08-30"

# (tag suffix, large-cap one-way bps, mid/small one-way bps) — the frozen
# section 3 grid. None = the flat control (every ticker INTRADAY_COST_BPS).
PASSES: list[tuple[str, tuple[float, float] | None]] = [
    ("flat_control", None),
    ("low_tier", (0.75, 5.0)),
    ("mid_tier", (1.5, 10.0)),
    ("high_tier", (3.0, 20.0)),
]

# Same daily-OHLC span the 2026-08-28 re-audit used for its per-ticker
# derivation — here it only supplies each ticker's median close for the
# tick floor.
DAILY_LOOKBACK_CALENDAR_DAYS = 850


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
        raise SystemExit(f"missing hourly tickers: {missing}")

    end = datetime.now(tz=UTC).date()
    start = end - timedelta(days=DAILY_LOOKBACK_CALENDAR_DAYS)
    log(f"fetching daily OHLC {start} -> {end} for tick-floor median closes...")
    frames, daily_missing = provider.get_daily_ohlcv(list(PATTERN_MINING_UNIVERSE), start, end)
    if daily_missing:
        raise SystemExit(f"missing daily tickers for tick floors: {daily_missing}")
    median_close_by_ticker = {t: float(frames["close"][t].median()) for t in bars_by_ticker}
    log(
        "median closes (tick-floor input): "
        + ", ".join(f"{t}={median_close_by_ticker[t]:.0f}" for t in list(bars_by_ticker)[:8])
        + " ..."
    )

    from app.db import SessionLocal
    from app.services.research_lab.cross_sectional_persistence import (
        persist_cross_sectional_trial_results,
    )

    for suffix, rates in PASSES:
        run_tag = f"{RUN_TAG_PREFIX}_{suffix}"
        if rates is None:
            cost_bps_by_ticker = {t: float(INTRADAY_COST_BPS) for t in bars_by_ticker}
            log(f"PASS {suffix}: flat {INTRADAY_COST_BPS}bps everywhere")
        else:
            large_rate, mid_small_rate = rates
            cost_bps_by_ticker = tiered_cost_bps_by_ticker(
                list(bars_by_ticker),
                PATTERN_MINING_UNIVERSE_LARGE_CAP,
                PATTERN_MINING_UNIVERSE_MID_SMALL_CAP,
                large_rate,
                mid_small_rate,
                median_close_by_ticker,
            )
            floored = sorted(
                t
                for t, c in cost_bps_by_ticker.items()
                if c > (large_rate if t in set(PATTERN_MINING_UNIVERSE_LARGE_CAP) else mid_small_rate)
            )
            ordered = sorted(cost_bps_by_ticker.values())
            log(
                f"PASS {suffix}: large={large_rate}bp midsmall={mid_small_rate}bp; per-ticker "
                f"min={ordered[0]:.2f} median={ordered[len(ordered) // 2]:.2f} max={ordered[-1]:.2f}; "
                f"tick-floor bound for {len(floored)} tickers {floored}"
            )

        t0 = time.time()
        results = screen_pattern_universe(
            bars_by_ticker, patterns=PATTERN_FAMILY, cost_bps_by_ticker=cost_bps_by_ticker
        )
        log(f"PASS {suffix}: screen done in {(time.time() - t0) / 60:.1f} min, {len(results)} measurable")

        dump(
            f"{SCRATCH}/phase_a_corrected_{suffix}.json",
            {
                "run_tag": run_tag,
                "n_trials": len(PATTERN_FAMILY),
                "cost_bps_by_ticker": cost_bps_by_ticker,
                "results": [asdict(r) for r in results],
            },
        )

        db = SessionLocal()
        try:
            n = persist_cross_sectional_trial_results(db, FAMILY_KEY, results, run_tag=run_tag)
            log(f"PASS {suffix}: persisted {n} rows under run_tag={run_tag}")
        finally:
            db.close()

        positive = [r for r in results if r.sharpe_annualized > 0]
        cleared = [
            r
            for r in results
            if r.deflated_sharpe.psr_vs_zero is not None
            and r.deflated_sharpe.psr_vs_zero >= PSR_SELECTION_THRESHOLD
        ]
        log(
            f"PASS {suffix}: {len(results)} measurable, {len(positive)} positive raw Sharpe, "
            f"{len(cleared)} clear PSR >= {PSR_SELECTION_THRESHOLD}"
        )
        for r in results[:5]:
            log(
                f"  top: {r.pattern_id} [{r.family}] sharpe={r.sharpe_annualized:.3f} "
                f"psr={r.deflated_sharpe.psr_vs_zero} dsr={r.deflated_sharpe.dsr}"
            )
    log("ALL PASSES DONE")


if __name__ == "__main__":
    main()
