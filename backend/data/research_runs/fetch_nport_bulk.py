"""Populate the SEC Form N-PORT bulk cache the flow-induced-trading family
reads (data/nport_bulk/, gitignored — see backend/.gitignore).

WHY THIS IS A SEPARATE SCRIPT AND NOT A SIDE EFFECT OF THE FAMILY RUN. It
moves roughly 7GB across the wire to keep about 250MB of rows: every quarter's
FUND_REPORTED_HOLDING.tsv is 157-425MB compressed and must be streamed and
filtered in full to find the few hundred thousand rows belonging to this
project's universe. A research entry point that silently did that on first call
would be indistinguishable, to its caller, from one that read a warm cache.
run_nport_flow_screening therefore RAISES when the cache is empty and names
this script.

Resumable: a quarter whose four extracted tables are already cached is skipped
without a single HTTP request. Safe to re-run.

The wanted-CUSIP set is derived from this project's point-in-time S&P 500 union
universe via the same SEC fails-to-deliver CUSIP map cross_sectional_best_ideas
uses, so it matches exactly what the family will later ask for. CHANGING THE
UNIVERSE MEANS RE-FETCHING: the discarded rows are not kept.

Run from backend/ with ./venv/bin/python data/research_runs/fetch_nport_bulk.py
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import date
from pathlib import Path

# WORKTREE BINDING GUARD — load-bearing, not boilerplate. Running this file by
# path puts data/research_runs/ on sys.path[0], NOT backend/, and a worktree's
# venv is typically a SYMLINK to the main worktree's venv, whose site-packages
# resolves `app` to the MAIN worktree's backend/app.
_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND})."
    )

from app.services.market_data.nport_provider import (
    NportProvider,
    published_quarters,
)
from app.services.research_lab.cross_sectional_nport_flow import (
    NPORT_FLOW_FORMATION_START,
    load_cusip_ticker_map,
)
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    get_universe_over,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout
)
logger = logging.getLogger("fetch_nport_bulk")


def main() -> int:
    end = date.today()  # noqa: DTZ011 — bounds which quarterly ZIPs exist yet
    universe = get_universe_over(max(MEMBERSHIP_DATA_START, NPORT_FLOW_FORMATION_START), end)
    cusip_map, empty_archives = load_cusip_ticker_map(universe)
    cusips = set(cusip_map.observations)
    logger.info(
        "universe=%d tickers, cusips=%d, unresolved tickers=%d, empty FTD archives=%d",
        len(universe),
        len(cusips),
        len(set(universe) - cusip_map.tickers()),
        len(empty_archives),
    )
    if not cusips:
        logger.error("no CUSIPs resolved — fetch SEC fails-to-deliver archives first")
        return 1

    provider = NportProvider()
    already = set(provider.cached_quarters())
    quarters = published_quarters(end)
    for quarter in quarters:
        if quarter in already:
            logger.info("%s already cached, skipping", quarter)
            continue
        started = time.time()
        try:
            submissions = provider.submissions(quarter)
            fund_info = provider.fund_reported_info(quarter)
            returns = provider.monthly_total_returns(quarter)
            holdings = provider.holdings(quarter, cusips)
        except Exception:
            logger.exception("%s FAILED", quarter)
            continue
        logger.info(
            "%s: submissions=%d fund_info=%d returns=%d holdings=%d (%.0fs)",
            quarter,
            len(submissions),
            len(fund_info),
            len(returns),
            len(holdings),
            time.time() - started,
        )
    logger.info("cached quarters: %s", provider.cached_quarters())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
