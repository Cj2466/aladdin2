"""Builds the SEC EDGAR announcement-calendar cache the earnings-announcement
premium family runs on.

Calls the family module's OWN fetcher (fetch_announcement_calendar) rather
than a reimplementation, so the cache is exactly what the module would fetch
live. Checked in alongside the pre-registration and the run report so the
acquisition step is reproducible from the repo.

The cache itself is a REFETCHABLE VENDOR INPUT and is gitignored (the same
convention data/edgar_companyfacts/, data/insider_form4_trades.csv.gz and
data/binance_futures/ already follow); the RESULTS live in
cross_sectional_trial_results and in data/research_runs/.

Run from backend/ with ./venv/bin/python.
"""

import logging
import sys
import time
from datetime import date
from pathlib import Path

# WORKTREE BINDING GUARD -- load-bearing, not boilerplate. Running this file
# by path puts data/research_runs/ on sys.path[0], NOT backend/, and this
# worktree's venv is a SYMLINK to the main worktree's venv whose site-packages
# resolves `app` to the MAIN checkout. Without this, the fetch would silently
# run another checkout's code with no error at all.
_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND})."
    )

from app.services.research_lab.cross_sectional_earnings_premium import (
    EAP_EVENT_CACHE_PATH,
    fetch_announcement_calendar,
    save_calendar_cache,
)
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    get_universe_over,
    membership_coverage_end,
)

# Filings are fetched from well BEFORE the first formation: the predictor
# needs a full prior year of a firm's own filing calendar to place its next
# announcement, so a formation on 2016-01-04 reads filings back into 2014.
FETCH_START = date(2014, 6, 1)
FETCH_END = date(2026, 9, 1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("eap_calendar_fetch")


def main() -> int:
    started = time.time()
    # POINT-IN-TIME CANDIDATE POOL: every ticker that was an S&P 500 member on
    # ANY day of the membership-coverage window, not today's snapshot.
    pool = get_universe_over(MEMBERSHIP_DATA_START, membership_coverage_end())
    logger.info(
        "fetching EDGAR Item 2.02 calendar for %d point-in-time tickers, %s..%s",
        len(pool),
        FETCH_START,
        FETCH_END,
    )

    events, report = fetch_announcement_calendar(pool, FETCH_START, FETCH_END)
    elapsed = time.time() - started

    logger.info(
        "done in %.1f min: %d events; tickers requested=%d cik_resolved=%d fetched=%d failed=%d; "
        "chunks fetched=%d failed=%d; coverage_starts_late=%d",
        elapsed / 60,
        len(events),
        report.n_tickers_requested,
        report.n_tickers_cik_resolved,
        report.n_tickers_fetched,
        report.n_tickers_fetch_failed,
        report.n_chunks_fetched,
        report.n_chunks_failed,
        report.n_tickers_coverage_starts_late,
    )
    save_calendar_cache(events, report, FETCH_START, FETCH_END, EAP_EVENT_CACHE_PATH)
    logger.info("wrote cache to %s", EAP_EVENT_CACHE_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
