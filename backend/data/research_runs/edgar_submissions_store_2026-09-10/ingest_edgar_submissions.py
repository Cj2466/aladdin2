"""Populate the point-in-time EDGAR submissions store for the PEAD screening
universe, and write a dated manifest of what it holds.

    ./venv/bin/python data/research_runs/edgar_submissions_store_2026-09-10/ingest_edgar_submissions.py
    ./venv/bin/python data/research_runs/edgar_submissions_store_2026-09-10/ingest_edgar_submissions.py --manifest-only

RUN IT EARLY AND RUN IT OFTEN, and the reason is not caching. SEC caps
https://data.sec.gov/submissions/CIK##########.json's `filings.recent` at
about 1,000 rows; older filings move into `filings.files` archives this
project does not fetch. For an active filer the covered window therefore
SLIDES FORWARD, and an 8-K visible today is simply absent from next year's
response. cross_sectional_pead's 2026-08-28 production run already measured
181 of 503 tickers truncated. Every day this store is not running is a day of
filings that can still be captured and, once gone from the endpoint, never
again. The store is append-only, so each run can only ever ADD.

Idempotent: re-running adds only genuinely new filing rows and re-dates
nothing. A row whose content changed under an accession already stored is
refused and reported (first-write-wins), never applied.

Rate-limited under SEC's published 10 req/s fair-access cap via
cross_sectional_pead's own constant, and sends the same declared user agent.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND))

from app.services.market_data.edgar_submissions_store import (
    EdgarSubmissionsStore,
    EdgarSubmissionsStoreReport,
    store_manifest,
    utc_today,
)
from app.services.research_lab.cross_sectional_pead import (
    PEAD_SEC_MIN_REQUEST_INTERVAL_SECONDS,
    PEAD_SEC_USER_AGENT,
    SEC_SUBMISSIONS_URL_TEMPLATE,
    _sec_get_json,
    load_cik_map,
)
from app.services.research_lab.ticker_universe import SCREENING_UNIVERSE

HERE = Path(__file__).resolve().parent
logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def ingest(store: EdgarSubmissionsStore) -> tuple[EdgarSubmissionsStoreReport, dict]:
    report = EdgarSubmissionsStoreReport()
    tickers = sorted(SCREENING_UNIVERSE)
    print(f"universe: {len(tickers)} tickers")
    cik_map = load_cik_map(PEAD_SEC_USER_AGENT)
    today = utc_today()
    outcome: dict = {"unresolved": [], "failed": [], "new_rows_per_ticker": {}, "earliest_filing": {}}
    last_request = 0.0
    for i, ticker in enumerate(tickers, start=1):
        cik = cik_map.get(ticker)
        if cik is None:
            outcome["unresolved"].append(ticker)
            continue
        elapsed = time.monotonic() - last_request
        if elapsed < PEAD_SEC_MIN_REQUEST_INTERVAL_SECONDS:
            time.sleep(PEAD_SEC_MIN_REQUEST_INTERVAL_SECONDS - elapsed)
        last_request = time.monotonic()
        try:
            document = _sec_get_json(SEC_SUBMISSIONS_URL_TEMPLATE.format(cik=cik), PEAD_SEC_USER_AGENT)
        except Exception as exc:  # noqa: BLE001 -- record and continue, never retry in a tight loop
            print(f"  FAILED {ticker} (CIK {cik}): {exc}")
            outcome["failed"].append(ticker)
            continue
        n_new = store.merge_submissions(cik, document, report, first_seen=today)
        store.record_fetch(cik, on=today)
        if n_new:
            outcome["new_rows_per_ticker"][ticker] = n_new
        earliest = store.earliest_filing_date(cik)
        if earliest is not None:
            outcome["earliest_filing"][ticker] = earliest.isoformat()
        if i % 50 == 0 or i == len(tickers):
            print(f"  {i}/{len(tickers)}, {report.rows_written:,} filing rows written", flush=True)
    return report, outcome


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest-only", action="store_true",
                    help="write the manifest for the store as it already is; fetch nothing")
    args = ap.parse_args()

    store = EdgarSubmissionsStore()
    now = datetime.now(UTC)
    print(f"store: {store.store_dir}")
    payload: dict = {"run_at": now.isoformat(timespec="minutes")}

    if not args.manifest_only:
        report, outcome = ingest(store)
        print(f"  {report.describe()}")
        payload["ingest"] = {
            "summary": report.describe(),
            "rows_written": report.rows_written,
            "rows_already_present": report.rows_already_present,
            "rows_unusable": report.rows_unusable,
            "ciks_ingested": report.ciks_ingested,
            "revisions": [list(r) for r in report.revisions],
            "unresolved_tickers": outcome["unresolved"],
            "failed_tickers": outcome["failed"],
            "new_rows_per_ticker": outcome["new_rows_per_ticker"],
            "earliest_filing_per_ticker": outcome["earliest_filing"],
        }
        if report.revisions:
            print(f"  {len(report.revisions)} FILING REVISIONS held back:")
            for row in report.revisions[:20]:
                print(f"    {row}")

    payload["manifest"] = store_manifest()
    out = HERE / f"edgar_submissions_manifest_{now.strftime('%Y-%m-%dT%H%MZ')}.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"written {out.relative_to(_BACKEND)}")
    m = payload["manifest"]
    print(f"  {m['n_ciks']} CIKs, {m['n_rows']:,} filing rows, {m['bytes_on_disk'] / 1e6:.1f} MB, "
          f"filing dates {m['filing_date_range'][0]} .. {m['filing_date_range'][1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
