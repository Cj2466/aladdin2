"""One-off DATA ACQUISITION for the dividend-month-premium family.

Fetches every cash-dividend EX-DATE and amount for the point-in-time S&P 500
candidate pool from yfinance and writes them to a local JSON cache, so the
screening run replays a FIXED input rather than re-hitting an unofficial,
non-reproducible scraping API on every invocation.

Computes NO return, NO position and NO P&L of any kind. It is the direct
analogue of fetch_eap_announcement_calendar.py and is run BEFORE the
pre-registration is finalized, for the same reason that family's EDGAR fetch
was: the design has to be able to see what data actually exists.

Run from backend/ with ./venv/bin/python.
"""

import json
import logging
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path

# WORKTREE BINDING GUARD -- load-bearing, not boilerplate. Running this file by
# path puts data/research_runs/ on sys.path[0], NOT backend/, and this
# worktree's venv is a SYMLINK to the main worktree's venv whose site-packages
# resolves `app` to the MAIN checkout. Without the two lines below, the fetch
# silently runs main's code instead of this branch's.
_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND})."
    )

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional_dividend_month import (
    DIVIDEND_CACHE_PATH,
)
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    get_universe_over,
    membership_coverage_end,
)

# Dividend history is loaded well before the first formation so a firm's own
# trailing payment calendar can warm up. See the pre-registration section 3.
FETCH_START = date(2012, 1, 3)
FETCH_END = date(2026, 9, 2)

# yfinance's own batching starts to time out well before 768 symbols in one
# call; measured live rather than assumed.
CHUNK_SIZE = 100

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("dividend_fetch")


def main() -> int:
    started = time.time()
    universe = get_universe_over(MEMBERSHIP_DATA_START, membership_coverage_end())
    logger.info("point-in-time candidate pool: %d tickers", len(universe))

    provider = YFinanceProvider()
    dividends: dict[str, list[tuple[str, float]]] = {}
    missing: list[str] = []
    n_priced = 0

    for i in range(0, len(universe), CHUNK_SIZE):
        chunk = universe[i : i + CHUNK_SIZE]
        logger.info("chunk %d..%d of %d", i, i + len(chunk), len(universe))
        by_ticker, close, chunk_missing = provider.get_dividend_history(
            chunk, FETCH_START, FETCH_END
        )
        missing.extend(chunk_missing)
        n_priced += len(close.columns) if not close.empty else 0
        for ticker, series in by_ticker.items():
            dividends[ticker] = [
                (ts.date().isoformat(), float(value)) for ts, value in series.items()
            ]

    n_events = sum(len(rows) for rows in dividends.values())
    payload = {
        "fetched_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "fetch_start": FETCH_START.isoformat(),
        "fetch_end": FETCH_END.isoformat(),
        "date_semantics": "EX-DIVIDEND date (NOT the payment date) -- see "
        "YFinanceProvider.get_dividend_history",
        "amount_semantics": "split-adjusted cash amount per share, same basis as Yahoo's Close",
        "n_tickers_requested": len(universe),
        "n_tickers_priced": n_priced,
        "n_tickers_with_dividends": len(dividends),
        "missing_price_data": sorted(missing),
        "dividends": dividends,
    }
    DIVIDEND_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DIVIDEND_CACHE_PATH.write_text(json.dumps(payload))
    logger.info(
        "wrote %s: %d tickers priced, %d with dividends, %d ex-dates, %d missing, %.1f min",
        DIVIDEND_CACHE_PATH,
        n_priced,
        len(dividends),
        n_events,
        len(missing),
        (time.time() - started) / 60,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
