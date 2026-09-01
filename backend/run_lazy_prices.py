"""One-off production runner for the Lazy Prices filing-language family.

Not part of the library — a script that calls the module's real entrypoint,
persists the rows, and dumps everything the run report needs as JSON so the
report is transcribed from measured numbers rather than retyped.

Set LAZY_PRICES_LIMIT_TICKERS to run a smaller smoke pass first (the full
universe walks ~10,000 real EDGAR documents and takes roughly an hour inside
the fair-access throttle); leave it unset for the production run.
"""

import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import date

from app.db import SessionLocal, engine
from app.services.research_lab.cross_sectional_lazy_prices import (
    LAZY_PRICES_FAMILY,
    LAZY_PRICES_FAMILY_NAME,
    LAZY_PRICES_N_TRIALS,
    run_lazy_prices_screening,
)
from app.services.research_lab.cross_sectional_persistence import (
    persist_cross_sectional_trial_results,
)
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    get_universe_over,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
log = logging.getLogger("run_lazy_prices")

RUN_TAG = "lazy_prices_2026-09-01"
OUT = "/tmp/lazy_prices_run.json"

if __name__ == "__main__":
    # The trial-results table must exist before a real run — this worktree
    # starts with no sqlite file at all, and a research result that cannot be
    # persisted is exactly the gap cross_sectional_persistence exists to close.
    import app.models  # noqa: F401 — registers every table on Base.metadata
    from app.db import Base

    Base.metadata.create_all(engine)

    start = MEMBERSHIP_DATA_START
    end = date(2026, 8, 31)

    universe = get_universe_over(start, end)
    limit = os.environ.get("LAZY_PRICES_LIMIT_TICKERS")
    if limit:
        universe = sorted(universe)[: int(limit)]
        log.warning("SMOKE RUN: limited to %d tickers — NOT a production result", len(universe))

    log.info(
        "start=%s end=%s universe=%d specs=%d",
        start,
        end,
        len(universe),
        len(LAZY_PRICES_FAMILY),
    )

    summary = run_lazy_prices_screening(start, end, tickers=universe)

    log.info(
        "screening done: %d results, %d priced tickers, %s..%s",
        len(summary.results),
        summary.n_priced_tickers,
        summary.first_date,
        summary.last_date,
    )
    for d in summary.dispersion:
        log.info(
            "dispersion %s/%s: n=%d tickers=%d mean=%.5f sd=%.5f p10=%.5f p50=%.5f p90=%.5f "
            "median_age=%.0fd",
            d.metric,
            d.scope,
            d.n_observations,
            d.n_tickers_with_signal,
            d.mean,
            d.std,
            d.p10,
            d.p50,
            d.p90,
            d.median_age_days,
        )

    payload = {
        "run_tag": RUN_TAG,
        "family_key": LAZY_PRICES_FAMILY_NAME,
        "n_trials_declared": LAZY_PRICES_N_TRIALS,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "smoke_limit": limit,
        "universe_size": summary.universe_size,
        "n_priced_tickers": summary.n_priced_tickers,
        "missing_price_tickers": summary.missing_price_tickers,
        "tickers_without_signal": summary.tickers_without_signal,
        "first_date": str(summary.first_date),
        "last_date": str(summary.last_date),
        "sample_disclosure": summary.sample_disclosure,
        "filing_report": asdict(summary.filing_report),
        "similarity_report": asdict(summary.similarity_report),
        "dispersion": [asdict(d) for d in summary.dispersion],
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
                "skewness": r.deflated_sharpe.skewness,
                "kurtosis": r.deflated_sharpe.kurtosis,
                "n_formations": r.n_formations,
                "n_skipped_formations": r.n_skipped_formations,
                "avg_names_per_leg": r.avg_names_per_leg,
                "n_trading_days": r.n_trading_days,
                "total_cost_drag": r.total_cost_drag,
                "total_financing_drag": r.total_financing_drag,
                "total_turnover": r.total_turnover,
                "edge_flat_fallback_notional": r.edge_flat_fallback_notional,
                "n_value_weighted_legs": r.n_value_weighted_legs,
                "n_value_weight_fallbacks": r.n_value_weight_fallbacks,
            }
            for r in summary.results
        ],
    }
    with open(OUT, "w") as fh:
        json.dump(payload, fh, indent=2, default=str)
    log.info("wrote %s", OUT)

    if not summary.results:
        log.error("no replayable specs — nothing to persist")
        sys.exit(1)

    if limit:
        log.warning("SMOKE RUN: not persisting to the trial-results table")
        sys.exit(0)

    db = SessionLocal()
    try:
        n = persist_cross_sectional_trial_results(
            db,
            family_key=LAZY_PRICES_FAMILY_NAME,
            results=summary.results,
            run_tag=RUN_TAG,
        )
        log.info("persisted %d rows to cross_sectional_trial_results", n)
    finally:
        db.close()
    log.info("DONE")
