"""Production runner for the recovered Phase C low-frequency pattern family.

THIS IS A RE-MEASUREMENT OF AN ALREADY-CONCLUDED 2026-08-26 RESULT, NOT A
FRESH BACKTEST. The family was built, screened and closed as an honest
negative on an unmerged branch (worktree-agent-a2520e5862565ddbf, commits
f81a562 then 9d08106) that was never merged and whose trial rows were never
persisted. See data/research_runs/low_frequency_patterns_run_2026-09-06
.txt for the full recovery record and what can and cannot be claimed about
the comparison.

Calls the module's OWN entry points (run_patterns_for_ticker per ticker, then
aggregate_ticker_outcomes once) -- not a reimplementation -- then persists
every reportable pattern's pooled result to the shared
cross_sectional_trial_results table and writes the git-durable plain-text and
JSON run reports.

Checked into data/research_runs/ so the exact invocation that produced the
numbers is reproducible from the repo rather than living only in a scratchpad.
The 2026-08-26 original was NOT checked in (it lived in
research_archive/session_2026-08-22_to_27/run_lowfreq_screening.py pointing at
a scratchpad cache that no longer exists), which is a large part of why the
original numbers cannot be bit-reproduced.

Run from backend/ with
    python3 data/research_runs/run_low_frequency_patterns.py

Input: data/intraday_bars_15min/ (284 tickers of 15-minute Alpaca SIP bars,
rebuilt by data/research_runs/fetch_intraday_bars_15min.py). That cache is
gitignored vendor input; the RESULTS are the durable artifact.
"""

from __future__ import annotations

import json
import logging
import pickle
import sys
import time
from dataclasses import asdict
from multiprocessing import Pool
from pathlib import Path

# WORKTREE BINDING GUARD -- load-bearing, not boilerplate. Running this file by
# path puts data/research_runs/ on sys.path[0], NOT backend/, so without the
# lines below this runner can silently screen another checkout's code.
_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND}). The screen would have run against another checkout's code."
    )

from app.config import _main_checkout_backend_dir
from app.db import SessionLocal
from app.services.research_lab.cross_sectional_persistence import (
    describe_configured_database,
    persist_cross_sectional_trial_results,
    verify_persisted_trial_results,
)
from app.services.research_lab.low_frequency_patterns import (
    LOW_FREQUENCY_PATTERN_FAMILY,
    LOWFREQ_FAMILY,
    LOWFREQ_N_TRIALS,
    SCREENING_FLOOR,
    VALIDATED_EDGE_BAR,
    aggregate_ticker_outcomes,
    policy_d_denominators,
)
from app.services.research_lab.registration_scorecard import (
    policy_d_verdict,
)

RUN_TAG = "low_frequency_patterns_recovery_2026-09-06"
FAMILY_KEY = LOWFREQ_FAMILY
REPORT_PATH = "data/research_runs/low_frequency_patterns_run_2026-09-06.txt"
JSON_PATH = "data/research_runs/low_frequency_patterns_run_2026-09-06.json"

# The bar cache lives in the MAIN checkout (see fetch_intraday_bars_15min.py
# for why), so resolve it the same way rather than assuming this worktree.
CACHE = _main_checkout_backend_dir(_BACKEND) / "data" / "intraday_bars_15min"

# The 2026-08-26 run used 3 workers because ~10 of the machine's cores were
# busy with Phase B. Nothing else is running now, so this uses more -- a pure
# throughput choice with no effect on results (tickers are independent, and
# test_parallel_and_serial_screening_paths_agree pins that).
N_WORKERS = 10

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout
)
logger = logging.getLogger("low_frequency_patterns")


def _run_ticker(ticker: str):
    """One ticker's full family. Module-level (not a closure) because Pool
    pickles it."""
    import app.services.research_lab.low_frequency_patterns as lf

    with open(CACHE / f"{ticker}_15Min.pkl", "rb") as handle:
        bars = pickle.load(handle)
    started = time.time()
    return ticker, lf.run_patterns_for_ticker(bars), time.time() - started


def main() -> None:
    tickers = sorted(p.name.replace("_15Min.pkl", "") for p in CACHE.glob("*_15Min.pkl"))
    if not tickers:
        raise SystemExit(
            f"REFUSING TO RUN: no bars in {CACHE}. Rebuild it first with "
            "python3 data/research_runs/fetch_intraday_bars_15min.py"
        )
    logger.info("screening %d patterns x %d tickers from %s", len(LOW_FREQUENCY_PATTERN_FAMILY), len(tickers), CACHE)

    outcomes_by_ticker: dict[str, dict] = {}
    started = time.time()
    with Pool(N_WORKERS) as pool:
        for i, (ticker, outcomes, dt) in enumerate(pool.imap_unordered(_run_ticker, tickers), 1):
            outcomes_by_ticker[ticker] = outcomes
            if i % 20 == 0 or i == len(tickers):
                elapsed = time.time() - started
                logger.info(
                    "[%d/%d] %s (%.0fs) elapsed %.1fm ETA %.0fm",
                    i, len(tickers), ticker, dt, elapsed / 60, (len(tickers) - i) * elapsed / i / 60,
                )

    summary = aggregate_ticker_outcomes(outcomes_by_ticker)
    denominators = summary.denominators or policy_d_denominators()
    n_local = denominators[0]

    # ----- report -----------------------------------------------------------
    lines: list[str] = []
    add = lines.append
    add("PHASE C LOW-FREQUENCY PATTERN FAMILY -- RECOVERED RUN")
    add("=" * 78)
    add(f"run_tag         {RUN_TAG}")
    add(f"family_key      {FAMILY_KEY}")
    add(f"tickers         {len(tickers)}")
    add(f"n_trials        {summary.n_trials} (family's literal pre-declared size)")
    add(f"sigma_SR        {summary.sigma_sr_annualized}")
    add(f"SR0             {summary.sr0_annualized}")
    add(f"ladder          {denominators}")
    add("")
    add(
        f"{'pattern':45s} {'sharpe':>7s} {'DSR@' + str(n_local):>10s} "
        f"{'DSR@' + str(denominators[-1]):>11s} {'PSR0':>7s} {'trades':>7s} "
        f"{'t/tkr-yr':>8s} {'hit':>6s} {'presv':>6s}"
    )
    for r in summary.results:
        d = r.deflated_sharpe
        local = r.dsr_by_n.get(n_local)
        top = r.dsr_by_n.get(denominators[-1])
        add(
            f"{r.pattern_id:45s} {r.sharpe_annualized:7.2f} "
            f"{('n/a' if local is None else f'{local:.4f}'):>10s} "
            f"{('n/a' if top is None else f'{top:.4f}'):>11s} "
            f"{('n/a' if d.psr_vs_zero is None else f'{d.psr_vs_zero:.3f}'):>7s} "
            f"{r.n_trades:7d} {r.trades_per_ticker_year:8.1f} "
            f"{('n/a' if r.hit_rate is None else f'{r.hit_rate:.1%}'):>6s} "
            f"{r.preservation.get('preservation_score', float('nan')):6.3f}"
        )

    best = max(summary.results, key=lambda r: r.sharpe_annualized) if summary.results else None
    if best is not None:
        verdict = policy_d_verdict(
            dsr_by_n=best.dsr_by_n, threshold=VALIDATED_EDGE_BAR, n_local=n_local
        )
        verdict_floor = policy_d_verdict(
            dsr_by_n=best.dsr_by_n, threshold=SCREENING_FLOOR, n_local=n_local
        )
        add("")
        add(f"best spec           {best.pattern_id}")
        add(f"  sharpe            {best.sharpe_annualized:.4f}")
        add(f"  dsr_by_n          {best.dsr_by_n}")
        add(f"  verdict @{VALIDATED_EDGE_BAR}      {verdict}")
        add(f"  verdict @{SCREENING_FLOOR}      {verdict_floor}")
        add(f"  preservation      {best.preservation.get('preservation_score')}")
        add(f"  preservation_ns   {best.preservation.get('preservation_score_no_stab')}")

    missing = {p.pattern_id for p in LOW_FREQUENCY_PATTERN_FAMILY} - {
        r.pattern_id for r in summary.results
    }
    if missing:
        add("")
        add(f"no reportable result (never fired / too few pooled days): {sorted(missing)}")

    report = "\n".join(lines)
    print(report)
    (Path(_BACKEND) / REPORT_PATH).write_text(report + "\n")

    (Path(_BACKEND) / JSON_PATH).write_text(
        json.dumps(
            {
                "run_tag": RUN_TAG,
                "family_key": FAMILY_KEY,
                "n_tickers": len(tickers),
                "n_trials": summary.n_trials,
                "n_local": n_local,
                "denominators": denominators,
                "sigma_sr_annualized": summary.sigma_sr_annualized,
                "sr0_annualized": summary.sr0_annualized,
                "results": [asdict(r) for r in summary.results],
            },
            indent=2,
            default=str,
        )
        + "\n"
    )

    # ----- persist ----------------------------------------------------------
    if not summary.results:
        raise SystemExit(
            "REFUSING TO FINISH: no pattern produced a reportable pooled result, so there is "
            "nothing to persist and the report above describes nothing."
        )
    db = SessionLocal()
    try:
        written = persist_cross_sectional_trial_results(
            db, FAMILY_KEY, summary.results, run_tag=RUN_TAG
        )
        verify_persisted_trial_results(db, RUN_TAG, written, family_key=FAMILY_KEY)
        logger.info("persisted %d rows to %s", written, describe_configured_database())
    finally:
        db.close()

    logger.info(
        "n_trials stayed %d against a family of %d definitions", summary.n_trials, LOWFREQ_N_TRIALS
    )


if __name__ == "__main__":
    main()
