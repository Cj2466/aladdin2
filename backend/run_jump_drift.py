"""One-off production runner for the jump-drift family.

Not part of the library — a script that calls the module's real entrypoint,
persists the rows, and dumps everything the run report needs as JSON so the
report is transcribed from measured numbers rather than retyped.
"""

import json
import logging
import sys
from dataclasses import asdict
from datetime import date

from app.db import SessionLocal
from app.services.research_lab.cross_sectional_jump_drift import (
    JUMP_DRIFT_SPECS,
    run_jump_drift_screening,
)
from app.services.research_lab.cross_sectional_persistence import (
    persist_cross_sectional_trial_results,
)
from app.services.research_lab.sp500_membership_history import MEMBERSHIP_DATA_START

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("run_jump_drift")

RUN_TAG = "jump_drift_2026-08-30"
OUT = "/tmp/jump_drift_run.json"

if __name__ == "__main__":
    start = MEMBERSHIP_DATA_START
    end = date(2026, 8, 29)
    log.info("start=%s end=%s specs=%d", start, end, len(JUMP_DRIFT_SPECS))

    summary = run_jump_drift_screening(start, end)
    log.info(
        "screening done: %d results, %d missing tickers, %d priced, %s..%s",
        len(summary.results),
        len(summary.missing_price_tickers),
        summary.n_priced_tickers,
        summary.first_date,
        summary.last_date,
    )

    payload = {
        "run_tag": RUN_TAG,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "universe_size": summary.universe_size,
        "n_priced_tickers": summary.n_priced_tickers,
        "first_date": str(summary.first_date),
        "last_date": str(summary.last_date),
        "missing_price_tickers": summary.missing_price_tickers,
        "results": [
            {
                "pattern_id": r.pattern_id,
                "sharpe_annualized": r.sharpe_annualized,
                "dsr": r.deflated_sharpe.dsr,
                "psr_vs_zero": r.deflated_sharpe.psr_vs_zero,
                "n_trials": r.deflated_sharpe.n_trials,
                "sigma_sr_annualized": r.deflated_sharpe.sigma_sr_annualized,
                "expected_max_sharpe_noise": (
                    r.deflated_sharpe.expected_max_sharpe_noise_annualized
                ),
                "dsr_floor_met": r.deflated_sharpe.dsr_floor_met,
                "interpretation": r.deflated_sharpe.interpretation,
                "n_formations": r.n_formations,
                "n_skipped_formations": r.n_skipped_formations,
                "avg_names_per_leg": r.avg_names_per_leg,
                "n_trading_days": r.n_trading_days,
                "total_cost_drag": r.total_cost_drag,
                "total_turnover": r.total_turnover,
                "edge_flat_fallback_notional": r.edge_flat_fallback_notional,
                "skewness": r.deflated_sharpe.skewness,
                "kurtosis": r.deflated_sharpe.kurtosis,
            }
            for r in summary.results
        ],
        "diagnostics": [asdict(d) for d in summary.diagnostics],
        "event_studies": [
            {
                "window": es.window,
                "z_crit": es.z_crit,
                "n_tickers_used": es.n_tickers_used,
                "n_bootstrap_draws": es.n_bootstrap_draws,
                "seed": es.seed,
                "verdict": es.verdict(),
                "cells": [asdict(c) for c in es.cells],
            }
            for es in summary.event_studies
        ],
    }
    with open(OUT, "w") as fh:
        json.dump(payload, fh, indent=2, default=str)
    log.info("wrote %s", OUT)

    if not summary.results:
        log.error("no replayable specs — nothing to persist")
        sys.exit(1)

    db = SessionLocal()
    try:
        n = persist_cross_sectional_trial_results(
            db, family_key="jump_drift", results=summary.results, run_tag=RUN_TAG
        )
        log.info("persisted %d rows to cross_sectional_trial_results", n)
    finally:
        db.close()
    log.info("DONE")
