#!/usr/bin/env python
"""One command to keep both of 2026-09-10's point-in-time EDGAR stores fresh.

    ./venv/bin/python data/research_runs/refresh_point_in_time_stores.py
    ./venv/bin/python data/research_runs/refresh_point_in_time_stores.py --dry-run

WHY THIS EXISTS
================
Two point-in-time stores were built the night of 2026-09-10, and both of
their own memos say the same thing in different words: they only do their
job if someone runs their ingest regularly.

* `edgar_facts_store_2026-09-10/EDGAR_FACTS_STORE_2026-09-10.md` closes a
  reproducibility gap (the mutable companyfacts cache gets rewritten in
  place every day quality_cbop's live panel reads it). Re-running the ingest
  captures the CURRENT state of that cache into the append-only store before
  the next overwrite erases the ability to answer "what did this document
  say on date D" for that day's snapshot.
* `edgar_submissions_store_2026-09-10/EDGAR_SUBMISSIONS_STORE_2026-09-10.md`
  closes a worse defect: SEC's `filings.recent` endpoint is BOUNDED (about
  1,000 rows or one year, whichever is greater) and an active filer's older
  8-Ks leave it PERMANENTLY -- 181 of 503 universe tickers were already
  truncated on 2026-08-28, and four more had lost early coverage by
  2026-09-09, twelve days later. "Run it regularly. Every day the store is
  not running is a day of filings that could still have been captured and,
  once they leave filings.recent, cannot be." (that memo, section 3). The
  store is append-only, so a re-run can only ever add rows, never lose them.

WHAT THIS SCRIPT DOES AND DOES NOT DO
=======================================
It runs the two existing, already-built, already-tested ingest scripts
(`edgar_facts_store_2026-09-10/ingest_edgar_facts_store.py` and
`edgar_submissions_store_2026-09-10/ingest_edgar_submissions.py`) in
sequence, as separate subprocesses using the same Python interpreter this
script was launched with, and reports a combined summary. It does NOT
reimplement either ingest, and it does NOT invent a scheduler -- no cron, no
launchd job, nothing that runs itself. A human (or an already-scheduled
process outside this script) is expected to run this command regularly, per
each memo's own recommendation.

BOTH SUB-INGESTS RUN EVEN IF THE FIRST ONE FAILS. A transient SEC fetch
failure in one store must not silently skip the other -- they are
independent stores on independent endpoints, and skipping the working one
because the other had a bad day would throw away real, otherwise-capturable
retention. The combined exit code is non-zero if EITHER sub-ingest failed
(non-zero return code), so an automated caller (or a human eyeballing this
command's exit status) still sees the failure.

--dry-run REPORTS ONLY. It imports each store module's own `store_manifest`
function directly (not the ingest scripts' `--manifest-only` flag, which
also writes a dated manifest file to disk as a side effect) and prints what
each store currently holds -- CIK/ticker count, row/fact count, date ranges,
bytes on disk. It makes NO network request and writes NO file. This is the
only mode this script was run in while building it: the live (fetching) path
hits SEC and was deliberately left unexercised here, per the task that
commissioned this script.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

FACTS_INGEST = BACKEND / "data" / "research_runs" / "edgar_facts_store_2026-09-10" / "ingest_edgar_facts_store.py"
SUBMISSIONS_INGEST = (
    BACKEND / "data" / "research_runs" / "edgar_submissions_store_2026-09-10" / "ingest_edgar_submissions.py"
)


def _print_facts_manifest() -> dict:
    from app.services.market_data.edgar_facts_store import (
        store_manifest as facts_store_manifest,
    )

    m = facts_store_manifest()
    print(f"edgar_facts_store: {m['store_dir']}")
    print(
        f"  {m['n_ciks']} CIKs, {m['n_facts']:,} facts, {m['bytes_on_disk'] / 1e6:.1f} MB on disk, "
        f"filed {m['filed_range'][0]} .. {m['filed_range'][1]}, "
        f"first_seen {m['first_seen_range'][0]} .. {m['first_seen_range'][1]}, "
        f"{len(m['cik_map_snapshots'])} ticker->CIK snapshot(s)"
    )
    return m


def _print_submissions_manifest() -> dict:
    from app.services.market_data.edgar_submissions_store import (
        store_manifest as submissions_store_manifest,
    )

    m = submissions_store_manifest()
    print(f"edgar_submissions_store: {m['store_dir']}")
    print(
        f"  {m['n_ciks']} CIKs, {m['n_rows']:,} filing rows, {m['bytes_on_disk'] / 1e6:.1f} MB on disk, "
        f"filingDate {m['filing_date_range'][0]} .. {m['filing_date_range'][1]}, "
        f"first_seen {m['first_seen_range'][0]} .. {m['first_seen_range'][1]}"
    )
    return m


def dry_run() -> int:
    print("--dry-run: reporting current store contents only. No network request, no file written.\n")
    facts = _print_facts_manifest()
    print()
    submissions = _print_submissions_manifest()
    print("\ncombined summary:")
    print(f"  edgar_facts_store:       {facts['n_ciks']} CIKs / {facts['n_facts']:,} facts")
    print(f"  edgar_submissions_store: {submissions['n_ciks']} CIKs / {submissions['n_rows']:,} filing rows")
    return 0


def _run_ingest(label: str, script: Path) -> int:
    print(f"\n{'=' * 70}\nrunning {label}: {script.relative_to(BACKEND)}\n{'=' * 70}")
    result = subprocess.run([sys.executable, str(script)], cwd=BACKEND, check=False)
    status = "OK" if result.returncode == 0 else f"FAILED (exit {result.returncode})"
    print(f"--- {label}: {status} ---")
    return result.returncode


def live_run() -> int:
    if not FACTS_INGEST.exists():
        raise SystemExit(f"missing ingest script: {FACTS_INGEST}")
    if not SUBMISSIONS_INGEST.exists():
        raise SystemExit(f"missing ingest script: {SUBMISSIONS_INGEST}")

    facts_rc = _run_ingest("edgar_facts_store ingest", FACTS_INGEST)
    submissions_rc = _run_ingest("edgar_submissions_store ingest", SUBMISSIONS_INGEST)

    print(f"\n{'=' * 70}\ncombined summary\n{'=' * 70}")
    print(f"  edgar_facts_store ingest:       {'OK' if facts_rc == 0 else f'FAILED (exit {facts_rc})'}")
    print(f"  edgar_submissions_store ingest: {'OK' if submissions_rc == 0 else f'FAILED (exit {submissions_rc})'}")

    if facts_rc != 0 or submissions_rc != 0:
        print("\nrefresh_point_in_time_stores: at least one sub-ingest failed; exiting non-zero.")
        return 1
    print("\nrefresh_point_in_time_stores: both stores refreshed successfully.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="report what each store currently holds via its own store_manifest(); fetch nothing, write nothing",
    )
    args = ap.parse_args()
    return dry_run() if args.dry_run else live_run()


if __name__ == "__main__":
    raise SystemExit(main())
