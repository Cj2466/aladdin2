"""One-off production runner for the macro/commodity exposure-beta family.

Not part of the library — a script that calls the module's real entrypoints
against REAL live data (yfinance for the 7 ETF proxies and the 503-name S&P
snapshot, FRED for the 6 macro series), persists the beta table, runs the
pre-registered out-of-sample forecast-quality test, and dumps everything the
run report needs as JSON so the report is transcribed from measured numbers
rather than retyped.

The pre-registration (data/research_runs/macro_beta_PREREGISTRATION.txt) was
committed BEFORE this script was ever run. Section 11 of it fixes the stopping
rule: this runs ONCE, and its numbers are the numbers.

Set MACRO_BETA_LIMIT_TICKERS to run a smaller smoke pass first; leave it unset
for the production run. A smoke pass deliberately does NOT persist and does NOT
produce a reportable verdict — a sub-universe cannot satisfy the pre-registered
minimum cross-section of 100 names.
"""

import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import date

from app.db import SessionLocal, engine
from app.services.macro_data.fred_provider import FredProvider
from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.macro_beta import (
    BONFERRONI_ALPHA,
    MACRO_DRIVERS,
    N_PRIMARY_TESTS,
    OOS_REQUIRED_ALIGNED_DAYS,
    evaluate_out_of_sample_forecast_quality,
    load_macro_beta_inputs,
    run_macro_beta_family,
)
from app.services.research_lab.ticker_universe import SCREENING_UNIVERSE

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
# Root at INFO also un-gates httpx's own INFO logger, whose format is
# 'HTTP Request: %s %s' with the FULL query string — and fred_provider passes
# api_key= as a query parameter. Without this line a run of this script prints
# FRED_API_KEY verbatim into the terminal and into any captured log. Confirmed
# by observation during the smoke run, not theorised. This is the same
# reasoning app/main.py applies when it raises the level on the `app` logger
# rather than on root; here the script genuinely wants root at INFO, so httpx
# is pushed back down individually instead.
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("run_macro_beta")

RUN_TAG = "macro_beta_2026-09-01"
OUT = "/tmp/macro_beta_run.json"

# Enough calendar history that every driver clears the 504 aligned trading days
# the out-of-sample split needs, INCLUDING credit_spread — FRED serves
# BAMLH0A0HYM2 over a rolling ~3-year window only (measured 2026-09-01,
# earliest observation 2023-09-01), so this is the binding constraint and the
# margin is deliberately generous rather than exactly 504.
TRADING_DAYS_TO_FETCH = 700

if __name__ == "__main__":
    # The table must exist before a real run — this worktree starts with no
    # sqlite file at all, and a research result that cannot be persisted is
    # exactly the gap this project's persistence convention exists to close.
    import app.models  # noqa: F401 — registers every table on Base.metadata
    from app.db import Base

    Base.metadata.create_all(engine)

    end = date(2026, 8, 31)
    universe = list(SCREENING_UNIVERSE)

    limit = os.environ.get("MACRO_BETA_LIMIT_TICKERS")
    if limit:
        universe = universe[: int(limit)]
        log.warning("SMOKE RUN: limited to %d tickers — NOT a production result", len(universe))

    log.info(
        "end=%s universe=%d drivers=%d fetching ~%d trading days",
        end, len(universe), len(MACRO_DRIVERS), TRADING_DAYS_TO_FETCH,
    )

    db = SessionLocal()
    try:
        # Fetched ONCE and shared by both entrypoints — the beta table uses the
        # trailing 252 days of this panel, the evaluation uses the trailing 504.
        inputs = load_macro_beta_inputs(
            db,
            YFinanceProvider(),
            FredProvider(),
            universe,
            end=end,
            trading_days_needed=TRADING_DAYS_TO_FETCH,
        )

        log.info(
            "panel: %d tickers resolved, %d missing, %d/%d drivers fetched",
            len(inputs.ticker_returns.columns),
            len(inputs.missing_tickers),
            len(inputs.driver_moves),
            len(MACRO_DRIVERS),
        )
        for driver_id, reason in inputs.failed_drivers.items():
            log.error("driver %s FAILED: %s", driver_id, reason)

        driver_coverage = {}
        for driver in MACRO_DRIVERS:
            moves = inputs.driver_moves.get(driver.driver_id)
            if moves is None or moves.empty:
                driver_coverage[driver.driver_id] = {"aligned_days": 0}
                continue
            aligned = inputs.ticker_returns.index.intersection(moves.index)
            driver_coverage[driver.driver_id] = {
                "aligned_days": len(aligned),
                "first": str(aligned.min().date()) if len(aligned) else None,
                "last": str(aligned.max().date()) if len(aligned) else None,
                "clears_oos_requirement": len(aligned) >= OOS_REQUIRED_ALIGNED_DAYS,
            }
            log.info(
                "driver %-20s aligned_days=%4d %s..%s",
                driver.driver_id,
                len(aligned),
                aligned.min().date() if len(aligned) else "-",
                aligned.max().date() if len(aligned) else "-",
            )

        # --- the out-of-sample test (does not touch the database) ------------
        log.info("running the pre-registered out-of-sample forecast-quality test...")
        evaluation = evaluate_out_of_sample_forecast_quality(inputs)

        for result in evaluation:
            log.info(
                "%-20s %-12s %-10s %s",
                result.driver, result.beta_variant, result.verdict, result.reason,
            )

        # --- the persisted lookup table --------------------------------------
        if limit:
            log.warning("SMOKE RUN: not persisting the beta table")
            summary = None
        else:
            summary = run_macro_beta_family(
                db, None, None, universe, end=end, inputs=inputs
            )
            log.info(
                "persisted %d rows across %d drivers, as_of=%s",
                summary.n_rows, summary.n_drivers_computed, summary.as_of_date,
            )

        payload = {
            "run_tag": RUN_TAG,
            "end": str(end),
            "n_universe_declared": len(universe),
            "n_tickers_resolved": len(inputs.ticker_returns.columns),
            "missing_tickers": inputs.missing_tickers,
            "failed_drivers": inputs.failed_drivers,
            "driver_coverage": driver_coverage,
            "n_primary_tests": N_PRIMARY_TESTS,
            "bonferroni_alpha": BONFERRONI_ALPHA,
            "beta_table": asdict(summary) if summary is not None else None,
            "evaluation": [asdict(r) for r in evaluation],
        }
        with open(OUT, "w") as fh:
            json.dump(payload, fh, indent=2, default=str)
        log.info("wrote %s", OUT)

        n_skill = sum(1 for r in evaluation if r.verdict == "skill")
        n_no_skill = sum(1 for r in evaluation if r.verdict == "no_skill")
        n_no_verdict = sum(1 for r in evaluation if r.verdict == "no_verdict")
        log.info(
            "VERDICT TALLY: %d skill / %d no_skill / %d no_verdict (of %d)",
            n_skill, n_no_skill, n_no_verdict, len(evaluation),
        )
        if summary is None and not limit:
            log.error("no beta table was written")
            sys.exit(1)
    finally:
        db.close()
    log.info("DONE")
