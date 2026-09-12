"""Step A4.2 -- extend the EDGAR submissions store from the 503-ticker PEAD
screening universe to the whole market the price panel covers (6,038
distinct CIKs from universe_ciks.csv, built by build_universe_ciks.py in
this same directory).

    ./venv/bin/python data/research_runs/edgar_submissions_wholemarket_2026-09-12/ingest_wholemarket.py
    ./venv/bin/python data/research_runs/edgar_submissions_wholemarket_2026-09-12/ingest_wholemarket.py --manifest-only

A THIN WRAPPER, deliberately: all storage semantics (append-only,
first-write-wins by accession, filingDate vs first_seen) live in
EdgarSubmissionsStore (app/services/market_data/edgar_submissions_store.py)
and are reused unmodified. The only thing this script adds over
edgar_submissions_store_2026-09-10/ingest_edgar_submissions.py is a larger
CIK list (whole market instead of the 503-ticker PEAD universe) and a
resumability layer keyed off the store's own coverage ledger, since a
6,038-CIK pass at SEC's declared rate cap runs on the order of an hour and
must survive a restart without re-fetching what is already fetched today.

Resumability: EdgarSubmissionsStore.record_fetch/.last_fetched already
persist a per-CIK "asked about on this UTC date" ledger (_coverage.json,
shared with every other consumer of this store). A CIK whose last_fetched()
== today is skipped on a restart -- not because the store cannot be
re-queried, but because a same-day re-fetch of an unchanged filing index
would burn SEC's rate budget for zero new rows (the store is append-only;
a same-day second fetch cannot find anything the first one didn't). This is
the identical semantics the store's docstring already documents for
record_fetch; this script only adds the "check before fetching" half.

Progress is logged every 200 CIKs to stdout AND appended as JSON lines to
ingest_progress.jsonl next to this script, so a killed run's last logged
line tells you exactly how far it got without waiting on stdout capture.
"""

from __future__ import annotations

import argparse
import csv
import json
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
)

HERE = Path(__file__).resolve().parent
UNIVERSE_CIKS_CSV = HERE / "universe_ciks.csv"
PROGRESS_LOG = HERE / "ingest_progress.jsonl"
LOG_EVERY = 200


def load_distinct_ciks() -> list[tuple[int, list[str]]]:
    """[(cik, [symbols sharing this cik])], sorted by cik, from
    universe_ciks.csv. Share classes/dual tickers collapse to one CIK, one
    fetch -- fetching the same CIK twice under two tickers would burn rate
    budget for a row this store already refuses as a duplicate."""
    by_cik: dict[int, list[str]] = {}
    with UNIVERSE_CIKS_CSV.open() as f:
        for row in csv.DictReader(f):
            by_cik.setdefault(int(row["cik"]), []).append(row["symbol"])
    return sorted(by_cik.items())


def ingest(store: EdgarSubmissionsStore, ciks: list[tuple[int, list[str]]]) -> dict:
    report = EdgarSubmissionsStoreReport()
    today = utc_today()
    outcome: dict = {
        "attempted": 0,
        "skipped_already_fetched_today": 0,
        "fetched_ok": 0,
        "failed": [],
        "new_rows_per_cik": {},
    }
    last_request = 0.0
    with PROGRESS_LOG.open("a") as progress_f:
        for i, (cik, symbols) in enumerate(ciks, start=1):
            if store.last_fetched(cik) == today:
                outcome["skipped_already_fetched_today"] += 1
                continue
            outcome["attempted"] += 1
            elapsed = time.monotonic() - last_request
            if elapsed < PEAD_SEC_MIN_REQUEST_INTERVAL_SECONDS:
                time.sleep(PEAD_SEC_MIN_REQUEST_INTERVAL_SECONDS - elapsed)
            last_request = time.monotonic()
            try:
                document = _sec_get_json(
                    SEC_SUBMISSIONS_URL_TEMPLATE.format(cik=cik), PEAD_SEC_USER_AGENT
                )
            except Exception as exc:  # noqa: BLE001 -- record and continue, never retry in a tight loop
                print(f"  FAILED CIK {cik} ({','.join(symbols)}): {exc}", flush=True)
                outcome["failed"].append({"cik": cik, "symbols": symbols, "error": str(exc)})
                continue
            outcome["fetched_ok"] += 1
            n_new = store.merge_submissions(cik, document, report, first_seen=today)
            store.record_fetch(cik, on=today)
            if n_new:
                outcome["new_rows_per_cik"][str(cik)] = n_new
            if i % LOG_EVERY == 0 or i == len(ciks):
                line = {
                    "at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                    "i": i,
                    "n_ciks": len(ciks),
                    "attempted": outcome["attempted"],
                    "fetched_ok": outcome["fetched_ok"],
                    "failed": len(outcome["failed"]),
                    "skipped_already_fetched_today": outcome["skipped_already_fetched_today"],
                    "rows_written_so_far": report.rows_written,
                }
                msg = (
                    f"  {i}/{len(ciks)}: attempted={outcome['attempted']} "
                    f"ok={outcome['fetched_ok']} failed={len(outcome['failed'])} "
                    f"skipped={outcome['skipped_already_fetched_today']} "
                    f"rows_written={report.rows_written:,}"
                )
                print(msg, flush=True)
                progress_f.write(json.dumps(line) + "\n")
                progress_f.flush()
    return {"report": report, "outcome": outcome}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest-only", action="store_true")
    args = ap.parse_args()

    store = EdgarSubmissionsStore()
    print(f"store: {store.store_dir}", flush=True)
    manifest_before = store_manifest()
    print(f"manifest BEFORE: {manifest_before['n_ciks']} CIKs, {manifest_before['n_rows']:,} rows", flush=True)

    payload: dict = {
        "run_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "manifest_before": manifest_before,
    }

    if not args.manifest_only:
        ciks = load_distinct_ciks()
        print(f"universe_ciks.csv: {len(ciks)} distinct CIKs to consider", flush=True)
        result = ingest(store, ciks)
        report, outcome = result["report"], result["outcome"]
        print(f"  {report.describe()}", flush=True)
        payload["ingest"] = {
            "n_ciks_total": len(ciks),
            "attempted": outcome["attempted"],
            "fetched_ok": outcome["fetched_ok"],
            "n_failed": len(outcome["failed"]),
            "skipped_already_fetched_today": outcome["skipped_already_fetched_today"],
            "rows_written": report.rows_written,
            "rows_already_present": report.rows_already_present,
            "rows_unusable": report.rows_unusable,
            "ciks_ingested": report.ciks_ingested,
            "n_revisions": len(report.revisions),
            "revisions": [list(r) for r in report.revisions],
            "failed": outcome["failed"],
        }
        if report.revisions:
            print(f"  {len(report.revisions)} FILING REVISIONS held back:", flush=True)
            for row in report.revisions[:20]:
                print(f"    {row}", flush=True)

    manifest_after = store_manifest()
    payload["manifest_after"] = manifest_after
    out = HERE / f"ingest_manifest_{datetime.now(UTC).strftime('%Y-%m-%dT%H%MZ')}.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"written {out.relative_to(_BACKEND)}", flush=True)
    print(
        f"manifest AFTER: {manifest_after['n_ciks']} CIKs, {manifest_after['n_rows']:,} rows, "
        f"{manifest_after['bytes_on_disk'] / 1e6:.1f} MB",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
