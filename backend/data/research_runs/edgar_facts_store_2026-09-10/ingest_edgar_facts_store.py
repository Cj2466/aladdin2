"""Fill the point-in-time EDGAR fact store from the mutable companyfacts
cache, and write a dated manifest of what it holds.

    ./venv/bin/python data/research_runs/edgar_facts_store_2026-09-10/ingest_edgar_facts_store.py
    ./venv/bin/python data/research_runs/edgar_facts_store_2026-09-10/ingest_edgar_facts_store.py --manifest-only

Idempotent by construction: the store is append-only and first-write-wins, so
running this twice adds nothing the second time and re-dates nothing. Any
value that CHANGED under an accession already stored is refused and printed
(and written into the manifest) rather than applied — see
edgar_facts_store.EdgarFactsStoreReport.revisions.

WHAT `first_seen` MEANS ON THIS FIRST INGEST, said plainly so no later reader
mistakes it: every fact ingested here is stamped with TODAY, including facts
SEC published in 1994. It records when THIS STORE first saw them, not when
they became public — `filed` is that, and it is stored separately and
untouched. The consequence is that a knowledge_cutoff query for any date
before this ingest correctly returns nothing: the store's knowledge begins
now. That is also the honest answer to the question that motivated the store
— what the 2026-09-04 cache said is not recoverable, because no copy of it
was ever taken (checked 2026-09-10: the three apparent copies on this machine
all resolve to the same inode as the live files).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND))

from app.services.market_data.edgar_facts_store import (
    EdgarFactsStore,
    EdgarFactsStoreReport,
    store_manifest,
    utc_today,
)
from app.services.market_data.edgar_xbrl_provider import DEFAULT_CACHE_DIR

HERE = Path(__file__).resolve().parent
logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def ingest(store: EdgarFactsStore) -> tuple[EdgarFactsStoreReport, dict]:
    report = EdgarFactsStoreReport()
    cache = Path(DEFAULT_CACHE_DIR)
    documents = sorted(cache.glob("CIK*.json"))
    report.ciks_requested = len(documents)
    today = utc_today()
    per_cik: dict[str, int] = {}
    for i, path in enumerate(documents, start=1):
        try:
            doc = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  UNREADABLE {path.name}: {exc}")
            continue
        cik = int(doc.get("cik") or path.stem.removeprefix("CIK"))
        n_new = store.merge_document(cik, doc, report, first_seen=today)
        store.record_fetch(cik, on=today)
        report.ciks_fetched += 1
        if n_new:
            per_cik[str(cik)] = n_new
        if i % 25 == 0 or i == len(documents):
            print(f"  {i}/{len(documents)} documents, {report.facts_written:,} facts written", flush=True)
    return report, per_cik


def snapshot_cik_map(store: EdgarFactsStore) -> str | None:
    """Snapshot SEC's ticker -> CIK map from the same mutable cache. It maps
    CURRENT tickers only, so it silently changes which companies a family
    resolves — a moving universe is a moving result."""
    path = Path(DEFAULT_CACHE_DIR) / "company_tickers.json"
    if not path.exists():
        print("  no company_tickers.json in the cache; skipped")
        return None
    raw = json.loads(path.read_text())
    mapping = {row["ticker"]: int(row["cik_str"]) for row in raw.values()}
    written = store.record_cik_map(mapping, on=utc_today())
    print(f"  ticker->CIK map: {len(mapping)} tickers, "
          f"{'snapshot written ' + str(written.name) if written else 'unchanged, no new snapshot'}")
    return str(written) if written else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest-only", action="store_true",
                    help="write the manifest for the store as it already is; ingest nothing")
    args = ap.parse_args()

    store = EdgarFactsStore()
    now = datetime.now(UTC)
    print(f"store: {store.store_dir}")
    payload: dict = {"run_at": now.isoformat(timespec="minutes"), "source_cache": str(DEFAULT_CACHE_DIR)}

    if not args.manifest_only:
        report, per_cik = ingest(store)
        snapshot = snapshot_cik_map(store)
        print(f"  {report.describe()}")
        payload["ingest"] = {
            "summary": report.describe(),
            "ciks_requested": report.ciks_requested,
            "ciks_ingested": report.ciks_fetched,
            "facts_written": report.facts_written,
            "facts_already_present": report.facts_already_present,
            "revisions": [list(r) for r in report.revisions],
            "cik_map_snapshot": snapshot,
            "facts_written_per_cik": per_cik,
        }
        if report.revisions:
            print(f"  {len(report.revisions)} VALUE REVISIONS held back:")
            for row in report.revisions[:20]:
                print(f"    {row}")

    payload["manifest"] = store_manifest()
    payload["knowledge_begins"] = payload["manifest"].get("first_seen_range", [None])[0]
    out = HERE / f"edgar_facts_store_manifest_{now.strftime('%Y-%m-%dT%H%MZ')}.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"written {out.relative_to(_BACKEND)}")
    print(f"  {payload['manifest']['n_ciks']} CIKs, {payload['manifest']['n_facts']:,} facts, "
          f"{payload['manifest']['bytes_on_disk'] / 1e6:.1f} MB on disk")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
