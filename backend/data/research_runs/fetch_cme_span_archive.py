"""Resume-safe bulk pull of CME's public SPAN settlement archive into
backend/data/futures_daily/cme_span/ (gitignored). Built 2026-09-07.

Usage (from backend/):
    python data/research_runs/fetch_cme_span_archive.py [--start YYYY-MM-DD] [--end YYYY-MM-DD]
                                                        [--newest-first] [--concurrency N]

One FTP GET per trading day (~10-13 MB zip), the 31-root FUT settlement
rows are extracted in memory and written as a ~40 KB daily CSV; the zip
is discarded. A day whose CSV exists is skipped, so the job can be killed
and restarted at any time. Progress is appended to
data/futures_daily/cme_span/fetch_log.txt so a later session can see
exactly what landed. Never touches www.cmegroup.com.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(f"REFUSING TO RUN: `app` resolved to {app.__file__}, not inside {_BACKEND}")

from app.services.market_data import cme_span_settlements as span

STORE = _BACKEND / "data" / "futures_daily" / "cme_span"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=span.SPAN_ARCHIVE_FIRST_DATE.isoformat())
    ap.add_argument("--end", default=span.SPAN_ARCHIVE_LAST_DATE.isoformat())
    ap.add_argument("--newest-first", action="store_true")
    ap.add_argument("--concurrency", type=int, default=span.FTP_MAX_CONCURRENCY)
    args = ap.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    days = [d.date() for d in pd.bdate_range(start, end)]
    if args.newest_first:
        days = days[::-1]
    STORE.mkdir(parents=True, exist_ok=True)
    log_path = STORE / "fetch_log.txt"
    from concurrent.futures import ThreadPoolExecutor

    def one(d: date) -> str:
        try:
            n = span.ingest_date(STORE, d)
            status = "absent" if n is None else f"rows={n}"
        except Exception as exc:  # noqa: BLE001 -- logged, job continues
            status = f"ERROR {type(exc).__name__}: {exc}"
        line = f"{datetime.now(UTC).isoformat(timespec='seconds')} {d.isoformat()} {status}"
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return line

    with ThreadPoolExecutor(max_workers=max(1, min(args.concurrency, span.FTP_MAX_CONCURRENCY))) as pool:
        for line in pool.map(one, days):
            print(line, flush=True)
    frame = span.load_daily(STORE)
    span.write_per_instrument(STORE, frame)
    span.write_manifest(STORE, frame, extra={"fetch_job": "fetch_cme_span_archive.py", "requested_range": [args.start, args.end]})
    print("ALL_DONE", len(frame), "rows", flush=True)


if __name__ == "__main__":
    main()
