"""Step A4.3 -- build the whole-market Item 2.02 (earnings release) 8-K
announcement-date table from the submissions store this run just extended
to 6,038 CIKs (universe_ciks.csv).

    ./venv/bin/python data/research_runs/edgar_submissions_wholemarket_2026-09-12/build_announcement_dates.py

WHICH EXTRACTION PATH THIS USES, AND WHY (the brief allowed either):
cross_sectional_pead.fetch_item_202_events(tickers, fetch_start, end) is the
project's existing extractor, but calling it here would re-issue one LIVE
SEC request per ticker (~7,143 tickers x 0.15s >= ~18 minutes) purely to
re-derive data this run's ingest_wholemarket.py already fetched and merged
into the SAME store minutes ago -- a second network pass over an endpoint
this project explicitly rate-limits out of respect for SEC's fair-access
policy, for zero new information. Instead this script reads the store
directly (EdgarSubmissionsStore.submissions_as_of, no live fetch) and
reuses cross_sectional_pead._parse_item_202_rows UNCHANGED to do the actual
extraction -- the same "8-K, item 2.02 present, filed in a chosen window"
rule, called with a window wide enough to cover everything the store holds
(2000-01-01 .. today) rather than re-implementing that parse. This is the
"store's own rows filtered to form 8-K carrying Item 2.02" alternative the
brief named explicitly, done by calling the project's own row-parser rather
than a second copy of its logic.

One CIK can carry multiple tickers (share classes / dual listings) --
universe_ciks.csv already collapsed the universe to (symbol, cik) pairs, so
this script fetches submissions_as_of ONCE per distinct CIK and reuses it
for every symbol sharing that CIK, then emits one announcement_dates.csv row
per (symbol, event) so a per-ticker family reader gets a ticker-keyed table.

Writes announcement_dates.csv (ticker, cik, accession, filing_date,
report_date, items) and announcement_dates_report.json (row counts,
per-year counts, distinct-ticker-per-year counts, truncation distribution).
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND))

from app.services.market_data.edgar_submissions_store import EdgarSubmissionsStore
from app.services.research_lab.cross_sectional_pead import _parse_item_202_rows

HERE = Path(__file__).resolve().parent
UNIVERSE_CIKS_CSV = HERE / "universe_ciks.csv"
OUT_CSV = HERE / "announcement_dates.csv"
OUT_REPORT = HERE / "announcement_dates_report.json"

# Wide enough to catch anything the store could plausibly hold (EDGAR
# full-text/XBRL history effectively starts ~1994; using 2000-01-01 as a
# round, clearly-before-everything floor) through today.
FETCH_START = date(2000, 1, 1)
FETCH_END = date(2026, 9, 12)

# The truncation question the brief asks: how many CIKs' earliest VISIBLE
# filing (in this store, today) is after this date -- i.e. their pre-2016
# history is already gone from the live endpoint and, for a CIK first
# fetched only now, was never captured by this store either.
TRUNCATION_FLOOR = date(2016, 1, 1)


def main() -> int:
    store = EdgarSubmissionsStore()
    by_cik: dict[int, list[str]] = defaultdict(list)
    with UNIVERSE_CIKS_CSV.open() as f:
        for row in csv.DictReader(f):
            by_cik[int(row["cik"])].append(row["symbol"])
    ciks = sorted(by_cik)
    print(f"{len(ciks)} distinct CIKs, {sum(len(v) for v in by_cik.values())} (symbol, cik) pairs")

    rows_out: list[dict] = []
    n_ciks_no_rows = 0
    earliest_filing_per_cik: dict[int, str] = {}

    for cik in ciks:
        retained = store.submissions_as_of(cik)
        if retained is None:
            n_ciks_no_rows += 1
            continue
        recent = retained.get("filings", {}).get("recent", {})
        filing_dates = recent.get("filingDate", [])
        if filing_dates:
            earliest_filing_per_cik[cik] = min(filing_dates)
        for symbol in by_cik[cik]:
            events, _truncated = _parse_item_202_rows(symbol, cik, retained, FETCH_START, FETCH_END)
            for e in events:
                rows_out.append(
                    {
                        "ticker": e.ticker,
                        "cik": e.cik,
                        "accession": e.accession,
                        "filing_date": e.filing_date.isoformat(),
                        "acceptance_utc": e.acceptance_utc,
                    }
                )

    rows_out.sort(key=lambda r: (r["ticker"], r["filing_date"]))
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "cik", "accession", "filing_date", "acceptance_utc"])
        w.writeheader()
        w.writerows(rows_out)
    print(f"written {OUT_CSV.relative_to(_BACKEND)}: {len(rows_out)} rows")

    # --- per-year counts ---------------------------------------------------
    events_per_year: dict[int, int] = defaultdict(int)
    tickers_per_year: dict[int, set] = defaultdict(set)
    for r in rows_out:
        year = int(r["filing_date"][:4])
        events_per_year[year] += 1
        tickers_per_year[year].add(r["ticker"])

    year_table = {
        str(y): {"n_events": events_per_year[y], "n_distinct_tickers": len(tickers_per_year[y])}
        for y in sorted(events_per_year)
    }

    # --- truncation distribution --------------------------------------------
    truncation_by_year: dict[int, int] = defaultdict(int)
    n_after_floor = 0
    for cik, earliest in earliest_filing_per_cik.items():
        y = int(earliest[:4])
        d = date.fromisoformat(earliest)
        if d > TRUNCATION_FLOOR:
            n_after_floor += 1
            truncation_by_year[y] += 1

    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "extraction_path": "store-direct (submissions_as_of + cross_sectional_pead._parse_item_202_rows), no live re-fetch",
        "fetch_window": [FETCH_START.isoformat(), FETCH_END.isoformat()],
        "n_ciks_total": len(ciks),
        "n_ciks_with_no_stored_rows": n_ciks_no_rows,
        "n_symbol_cik_pairs": sum(len(v) for v in by_cik.values()),
        "n_announcement_rows": len(rows_out),
        "n_distinct_tickers_with_any_event": len({r["ticker"] for r in rows_out}),
        "events_and_tickers_per_year": year_table,
        "truncation": {
            "floor_date": TRUNCATION_FLOOR.isoformat(),
            "n_ciks_with_earliest_filing_after_floor": n_after_floor,
            "n_ciks_with_earliest_filing_known": len(earliest_filing_per_cik),
            "pct_of_known_after_floor": round(100 * n_after_floor / len(earliest_filing_per_cik), 2)
            if earliest_filing_per_cik else None,
            "distribution_by_year_of_earliest_filing_after_floor": dict(sorted(truncation_by_year.items())),
        },
    }
    OUT_REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"written {OUT_REPORT.relative_to(_BACKEND)}")
    print(f"{len(rows_out)} announcement rows, {report['n_distinct_tickers_with_any_event']} distinct tickers")
    print(f"truncation: {n_after_floor}/{len(earliest_filing_per_cik)} CIKs' earliest stored filing is "
          f"after {TRUNCATION_FLOOR.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
