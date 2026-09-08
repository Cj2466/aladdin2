"""Per-fund, per-asset-category portfolio totals from N-PORT, for the
Frazzini-Lamont (2008) "Dumb Money" family.

WHY THIS EXISTS
===============
Frazzini & Lamont (JFE 88(2), 2008) p.302, Section 2.1, define their fund
universe verbatim as:

    "The universe of mutual funds we study includes all domestic equity funds
     that exist at any date between 1980 and 2003 for which quarterly total
     net assets (TNA) are available and for which we can match CRSP data with
     the common stock holdings data from Thomson Financial."

DOMESTIC EQUITY FUNDS. That restriction is load-bearing rather than cosmetic,
because of where the fund universe enters their construction. Their FLOW
(Eq. 8) is

    FLOW_jt = z_jt - zhat_jt

and the counterfactual half, zhat, is built from a pro-rata redistribution of
the AGGREGATE flows of the whole fund sector (Eq. 11):

    Fhat^i_s = (TNA^i_{t-k} / TNA^Agg_{t-k}) * F^Agg_s

so every non-equity fund left in the pool changes TNA^Agg and F^Agg, and hence
changes every equity fund's counterfactual TNA. The paper is explicit that the
flows it means are equity-sector reallocations — p.301: "By 'flows,' we mean
flows from one fund to another fund (not flows in and out of the entire mutual
fund sector)." Leaving bond, municipal, target-date and allocation funds in
the aggregate would silently redefine the estimand.

Non-equity funds do NOT contaminate the actual half z: a fund holding no
common stock contributes a zero term to the sum over funds. The contamination
is entirely via the aggregates. That is precisely why it cannot be ignored --
it is invisible in the per-stock inputs.

WHY A NEW FETCH RATHER THAN REUSING A CACHE
===========================================
N-PORT publishes NO fund-type field. Checked directly against the 2024q1 bulk
ZIP rather than assumed, all 32 members enumerated:
  * FUND_REPORTED_INFO.tsv (47 columns) carries assets, liabilities, credit
    spreads and the Item B.6 flow fields -- no category, no strategy, no type.
  * REGISTRANT.tsv carries CIK, name and postal address -- nothing typed.
  * MONTHLY_RETURN_CAT_INSTRUMENT.tsv is Item B.7 DERIVATIVE gains by contract
    category (Credit Contracts / Swap Category ...), not a portfolio
    composition, and is empty for a plain long-only equity fund.

The only published basis for the classification is ASSET_CAT on the holdings
rows themselves, in FUND_REPORTED_HOLDING.tsv. Both existing caches are
useless for it, and in the silent-wrong-answer way rather than the loud way:
data/nport_bulk was filtered at fetch time to S&P 500 CUSIPs and
data/nport_bulk_firesale to an S&P 500 + S&P 600 union, so an equity share
computed from either would be "fraction of net assets in THIS INDEX", not
"fraction in common equity", and would misclassify every genuine equity fund
holding mid-caps, foreign names or anything off-index. That is the same class
of trap recorded in fetch_nport_bulk_firesale.py's docstring.

WHAT IT WRITES, AND WHY IT STAYS SMALL
======================================
The holdings member is 157-425MB compressed per quarter, and this script
streams it WITHOUT a CUSIP filter -- every position row, all 27 quarters. It
never materialises those rows: they are folded on the fly into per-accession,
per-ASSET_CAT sums, so what lands on disk is one small gzipped CSV per quarter

    <quarter>_FUND_ASSET_CATEGORY.csv.gz
        ACCESSION_NUMBER, ASSET_CAT, VALUE_SUM, N_POSITIONS

of order 10^4-10^5 rows, a few hundred KB. Downstream, a fund's equity share
is VALUE_SUM(ASSET_CAT='EC') / sum(VALUE_SUM), and the family applies its own
pre-registered threshold to that -- this script commits to no threshold and
makes no classification. It records composition; the family decides.

Deliberately category-complete rather than equity-only: keeping every
ASSET_CAT means the denominator is real and a future family can re-derive a
different classification with no re-fetch.

RUNTIME AND RESUMABILITY
========================
This moves ~7GB over the wire. It is resumable at quarter granularity -- a
quarter whose CSV already exists is skipped with no HTTP request -- so it is
safe to interrupt and re-run. Rows whose field count disagrees with the header
are skipped rather than positionally guessed at, and the count of those is
reported per quarter; a CURRENCY_VALUE that will not parse is counted, never
silently read as zero.

Run from backend/ with
    ./venv/bin/python data/research_runs/fetch_nport_fund_asset_categories.py
"""

from __future__ import annotations

import csv
import gzip
import logging
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app  # noqa: E402

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND}). A worktree's venv symlinks to main's site-packages, so an unguarded run "
        f"can silently read and write main's tree instead of this one."
    )

from app.services.market_data.nport_provider import (  # noqa: E402
    TABLE_FUND_REPORTED_HOLDING,
    NportProvider,
    published_quarters,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("fetch_nport_fund_asset_categories")

CACHE_DIR = _BACKEND / "data" / "nport_fund_asset_categories"
COLUMNS = ("ACCESSION_NUMBER", "ASSET_CAT", "VALUE_SUM", "N_POSITIONS")


def _path(quarter: str) -> Path:
    return CACHE_DIR / f"{quarter}_FUND_ASSET_CATEGORY.csv.gz"


def aggregate_quarter(provider: NportProvider, quarter: str) -> tuple[int, dict[str, int]]:
    """Stream one quarter's holdings and fold them into per-(accession, category)
    totals. Returns the number of output rows and a dict of refusal counts."""
    stream = provider.stream_member_lines(quarter, TABLE_FUND_REPORTED_HOLDING)
    header = next(stream).rstrip("\r").split("\t")
    index = {name: position for position, name in enumerate(header)}
    for required in ("ACCESSION_NUMBER", "ASSET_CAT", "CURRENCY_VALUE"):
        if required not in index:
            raise SystemExit(
                f"{quarter}: column {required!r} absent from FUND_REPORTED_HOLDING. SEC changed "
                f"the layout; refusing to guess. Published header: {header}"
            )

    totals: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0])
    refused: dict[str, int] = defaultdict(int)
    n_rows = 0
    for line in stream:
        if not line.strip():
            continue
        parts = line.rstrip("\r").split("\t")
        if len(parts) != len(header):
            refused["field_count_mismatch"] += 1
            continue
        n_rows += 1
        raw = parts[index["CURRENCY_VALUE"]].strip()
        try:
            value = float(raw) if raw else 0.0
        except ValueError:
            refused["unparseable_currency_value"] += 1
            continue
        key = (parts[index["ACCESSION_NUMBER"]], parts[index["ASSET_CAT"]].strip())
        bucket = totals[key]
        bucket[0] += value
        bucket[1] += 1

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = _path(quarter).with_suffix(".part")
    with gzip.open(temporary, "wt", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for (accession, category), (value, count) in sorted(totals.items()):
            writer.writerow([accession, category, repr(value), count])
    temporary.rename(_path(quarter))
    logger.info("%s: %d position rows -> %d category rows", quarter, n_rows, len(totals))
    return len(totals), dict(refused)


def main() -> int:
    provider = NportProvider(cache_dir=None)  # nothing here belongs in the filtered caches
    quarters = published_quarters(date.today())  # noqa: DTZ011 — bounds which ZIPs exist
    logger.info("cache dir %s, %d published quarters", CACHE_DIR, len(quarters))

    failures = 0
    for quarter in quarters:
        if _path(quarter).exists() and _path(quarter).stat().st_size > 0:
            logger.info("%s already cached, skipping", quarter)
            continue
        started = time.time()
        try:
            n_out, refused = aggregate_quarter(provider, quarter)
        except Exception:
            logger.exception("%s FAILED", quarter)
            failures += 1
            continue
        logger.info(
            "%s done: %d rows, refused=%s (%.0fs)", quarter, n_out, refused or {}, time.time() - started
        )

    done = sorted(p.name.split("_")[0] for p in CACHE_DIR.glob("*_FUND_ASSET_CATEGORY.csv.gz"))
    logger.info("finished. cached quarters: %d/%d, failures: %d", len(done), len(quarters), failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
