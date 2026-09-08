"""Populate an N-PORT bulk cache covering S&P 500 *and* S&P 600 CUSIPs, for
the Coval-Stafford fire-sale family.

WHY A SECOND CACHE RATHER THAN REUSING THE EXISTING ONE. data/nport_bulk was
built by the Lou/FIT family with a wanted-CUSIP set derived from the S&P 500
union ALONE — verified, not assumed: 2024q1_FUND_REPORTED_HOLDING.csv.gz holds
599 distinct ISSUER_CUSIPs. NportProvider caches the FILTERED extraction, so
the small-cap rows were discarded at fetch time and are simply gone
("CHANGING THE UNIVERSE MEANS RE-FETCHING", fetch_nport_bulk.py's own
docstring).

Pointing this family at the existing cache would be worse than merely
incomplete: the provider skips any quarter whose four tables are already
cached, so the S&P 600 arm would come back EMPTY while every log line said
"already cached". A silently small-cap-free result reported as a small-cap
result is exactly the failure mode this project's rules exist to prevent, so
the new cache gets its own directory and the old one is left untouched.

The fire-sale family's pre-registration names S&P 600 as the MORE FAITHFUL
universe (the paper's fire-sale stocks average ~2% of CRSP firms and are not
mega-caps), so this is not an optional extra arm that could be quietly dropped.

Resumable and safe to re-run: a quarter whose tables are already in THIS cache
is skipped without an HTTP request.

Run from backend/ with
    ./venv/bin/python data/research_runs/fetch_nport_bulk_firesale.py
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import date
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app  # noqa: E402

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND})."
    )

from app.services.market_data.nport_provider import (  # noqa: E402
    NportProvider,
    published_quarters,
)
from app.services.research_lab import small_cap_membership_history as smallcap  # noqa: E402
from app.services.research_lab import sp500_membership_history as large  # noqa: E402
from app.services.research_lab.cross_sectional_firesale_pressure import (  # noqa: E402
    FIRESALE_FORMATION_START,
)
from app.services.research_lab.cross_sectional_nport_flow import (  # noqa: E402
    load_cusip_ticker_map,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout
)
logger = logging.getLogger("fetch_nport_bulk_firesale")

# Deliberately NOT data/nport_bulk — see the module docstring.
CACHE_DIR = _BACKEND / "data" / "nport_bulk_firesale"

# A year of formation lookback plus a quarter of skip before the first
# formation date, matching the family's own history_start.
HISTORY_START = FIRESALE_FORMATION_START.replace(year=FIRESALE_FORMATION_START.year - 2)


def wanted_cusips() -> tuple[set[str], dict[str, int]]:
    end = date.today()  # noqa: DTZ011 — bounds which quarterly ZIPs exist yet
    stats: dict[str, int] = {}
    tickers: set[str] = set()
    for name, mod in (("sp500", large), ("sp600", smallcap)):
        names = mod.get_universe_over(max(mod.MEMBERSHIP_DATA_START, HISTORY_START), end)
        stats[f"{name}_tickers"] = len(names)
        tickers |= set(names)
    stats["union_tickers"] = len(tickers)

    cusip_map, empty_archives = load_cusip_ticker_map(sorted(tickers))
    stats["empty_ftd_archives"] = len(empty_archives)
    stats["unresolved_tickers"] = len(tickers - cusip_map.tickers())
    cusips = set(cusip_map.observations)
    stats["cusips"] = len(cusips)
    return cusips, stats


def main() -> int:
    end = date.today()  # noqa: DTZ011
    cusips, stats = wanted_cusips()
    logger.info("universe stats: %s", stats)
    if not cusips:
        logger.error("no CUSIPs resolved — fetch SEC fails-to-deliver archives first")
        return 1
    # Sanity floor: the S&P 500-only cache already carries ~600 CUSIPs, so a
    # union set that is not materially larger means the small-cap half failed
    # to resolve and this fetch would silently reproduce the existing cache.
    if len(cusips) < 900:
        logger.error(
            "refusing to fetch: only %d CUSIPs resolved, which is not materially more than "
            "the existing S&P 500-only cache's ~600 — the small-cap half did not resolve",
            len(cusips),
        )
        return 1

    provider = NportProvider(cache_dir=CACHE_DIR)
    already = set(provider.cached_quarters())
    logger.info("cache dir %s, already cached: %d quarters", CACHE_DIR, len(already))

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
    logger.info("done. cached quarters: %d", len(provider.cached_quarters()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
