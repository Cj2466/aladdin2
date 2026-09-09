"""Point-in-time store for SEC EDGAR SUBMISSIONS (a company's filing index),
the sibling of edgar_facts_store.py — and it exists for a sharper reason than
reproducibility alone.

THE ENDPOINT LOSES DATA OVER TIME, and that is measured, not feared.
https://data.sec.gov/submissions/CIK##########.json returns the company's
filing index with the most recent filings in `filings.recent`; everything
older moves into separate `filings.files` archives that this project does not
fetch. `recent` is BOUNDED, so for an active filer the window it covers
SLIDES FORWARD as new filings arrive, and filings visible in an earlier fetch
are simply gone from a later one.

The bound, measured across all 503 tickers of the PEAD screening universe on
2026-09-09 rather than taken from memory: row counts run 29 .. 26,014 with a
median of 1,001; 435 of 503 sit between 995 and 1,010 rows; only 6 exceed
1,100, and 5 of those 6 (JPM 26,014, MS 19,798, GS 16,110, C 13,383, BAC
11,373 — all structured-note filers) bottom out at exactly one year of
history. That is consistent with `recent` holding the GREATER of about 1,000
filings or one year of them; the rule is inferred from this project's own
measurement and has not been verified against SEC's documentation, but the
consequence does not depend on the rule's exact form: JPM's earnings 8-Ks
older than one year are not in the endpoint today, and next month a further
month of them will be gone.

cross_sectional_pead measured exactly that on its 2026-08-28 production run:
of 503 tickers, **181 had truncated `recent` coverage** — their pre-2018-04-07
8-Ks were already unreachable. Every caller of fetch_item_202_events fetches
LIVE (no caller passes `events=`, and the event-cache file the module supports
has never existed on disk), so re-running the family on the SAME frozen window
months later necessarily scores a SMALLER sample: the earliest events have
fallen out of the endpoint. Refetching cannot recover them. That is a
mechanical source of drift no amount of care in the family can fix, and it is
consistent with the −0.016 pead_ear drift recorded in the Dormant pool
(consistent with, not proven to be the whole of — the loss is real either way).

An append-only store fixes it in the only direction available: **once a filing
row is stored it never leaves.** The truncation floor stops moving forward
from the day the store starts, and `submissions_as_of` serves the UNION of
everything ever seen, which is always a superset of what the endpoint would
return today.

SHAPE, AND WHY IT IS A DROP-IN. `submissions_as_of` rebuilds the exact nested
`{"cik", "entityName", "filings": {"recent": {<parallel arrays>}}}` shape SEC
serves, so cross_sectional_pead._parse_item_202_rows consumes it with no
change at all. A store that needed its consumer rewritten would be a second
implementation of the parse, which is how two paths silently diverge.

IDENTITY AND FIRST-WRITE-WINS, as price_store §4 and edgar_facts_store. A
filing is identified by its ACCESSION NUMBER, which is globally unique and
immutable. A row arriving under an accession already stored with different
content is an SEC re-processing or a bug, never an ordinary update: it is
refused and recorded on `EdgarSubmissionsStoreReport.revisions`.

THE TWO DATES, exactly as in edgar_facts_store: `filingDate` is SEC's own
publication date and the economic point-in-time key; `first_seen` is when this
store first saw the row and is the reproducibility key. Both are stored; only
`filingDate` is served back, because a consumer must not be able to tell a
stored document from one SEC returned.

ROUTED TO THE MAIN CHECKOUT, like the database, the price store and the fact
store — a per-worktree copy would fetch its own fresh (and therefore more
truncated) history, which is the defect this module exists to remove.
"""

from __future__ import annotations

import gzip
import json
import logging
from collections.abc import Iterable
from datetime import date
from pathlib import Path

from app.config import MAIN_CHECKOUT_BACKEND_DIR

# One atomic-write implementation and one clock for both EDGAR stores,
# deliberately imported rather than copied: two of either is how they drift.
from app.services.market_data.edgar_facts_store import _atomic_write_bytes, utc_today

logger = logging.getLogger(__name__)

STORE_SCHEMA_VERSION = "v1"

SHARED_STORE_ROOT = MAIN_CHECKOUT_BACKEND_DIR / "data" / "edgar_submissions_store"
DEFAULT_STORE_DIR = SHARED_STORE_ROOT / STORE_SCHEMA_VERSION

STORE_FILE_SUFFIX = ".submissions.json.gz"
COVERAGE_NAME = "_coverage.json"

# The parallel arrays SEC publishes under filings.recent, verified live
# 2026-08-28 (see cross_sectional_pead's endpoint block) and preserved in
# full rather than narrowed to the four fields pead reads today — a store
# shaped to one consumer sends the next consumer back to a network that has
# meanwhile dropped the rows.
RECENT_FIELDS = (
    "accessionNumber",
    "filingDate",
    "reportDate",
    "acceptanceDateTime",
    "act",
    "form",
    "fileNumber",
    "filmNumber",
    "items",
    "core_type",
    "size",
    "isXBRL",
    "isInlineXBRL",
    "primaryDocument",
    "primaryDocDescription",
)

# The identity of a filing. An accession number is globally unique and
# immutable — SEC assigns exactly one per submitted document.
IDENTITY_FIELD = "accessionNumber"

# Rows without these cannot be dated or identified, so they cannot be served
# point-in-time and are dropped on ingest.
REQUIRED_FIELDS = ("accessionNumber", "filingDate")


class EdgarSubmissionsStoreReport:
    """What one interaction did. Mirrors EdgarFactsStoreReport's contract:
    returnable, assertable, and with `revisions` as the load-bearing field —
    a filing whose content changed under an accession already stored is made
    VISIBLE rather than silently dropped by first-write-wins."""

    def __init__(self) -> None:
        self.ciks_ingested = 0
        self.rows_written = 0
        self.rows_already_present = 0
        self.rows_unusable = 0
        self.revisions: list[tuple[int, str, str, dict, dict]] = []

    def describe(self) -> str:
        parts = [
            f"{self.ciks_ingested} CIKs ingested",
            f"{self.rows_written} filing rows written",
            f"{self.rows_already_present} already present",
        ]
        if self.rows_unusable:
            parts.append(f"{self.rows_unusable} rows without an accession or filing date dropped")
        if self.revisions:
            parts.append(
                f"{len(self.revisions)} FILING REVISIONS held back (see .revisions) — "
                "a stored row's content changed under the same accession"
            )
        return ", ".join(parts)


def flatten_submissions(document: dict, *, first_seen: date) -> list[dict]:
    """Every row of `filings.recent` as a flat record, newest filing first.

    SEC serves the index as parallel arrays; a row is the i-th element of
    each. Arrays of differing length are tolerated (a short one yields None),
    because a store must not fail a research run over a vendor's ragged
    response — the same policy yfinance_provider keeps for a ragged batch."""
    recent = ((document.get("filings") or {}).get("recent")) or {}
    if not isinstance(recent, dict):
        return []
    lengths = [len(v) for v in recent.values() if isinstance(v, list)]
    if not lengths:
        return []
    seen_iso = first_seen.isoformat()
    rows: list[dict] = []
    for i in range(max(lengths)):
        row: dict = {}
        for field in RECENT_FIELDS:
            values = recent.get(field)
            row[field] = values[i] if isinstance(values, list) and i < len(values) else None
        if not all(row.get(f) for f in REQUIRED_FIELDS):
            continue
        row["seen"] = seen_iso
        rows.append(row)
    rows.sort(key=lambda r: (r["filingDate"], r["accessionNumber"]), reverse=True)
    return rows


def rebuild_submissions(cik: int, entity_name: str, tickers: list[str], rows: Iterable[dict]) -> dict:
    """The inverse of flatten_submissions: the nested shape SEC serves, which
    cross_sectional_pead._parse_item_202_rows consumes unchanged.

    The store's own `seen` column is not emitted — a consumer must not be
    able to tell a served document from SEC's own."""
    ordered = sorted(rows, key=lambda r: (r["filingDate"], r["accessionNumber"]), reverse=True)
    recent = {field: [row.get(field) for row in ordered] for field in RECENT_FIELDS}
    return {
        "cik": cik,
        "entityName": entity_name,
        "tickers": list(tickers),
        "filings": {"recent": recent, "files": []},
    }


class EdgarSubmissionsStore:
    """Append-only, first-write-wins storage for company filing indexes, one
    file per CIK, routed to the main checkout.

    `EdgarSubmissionsStore()` opens the shared store; passing None disables
    persistence, the same escape hatch PriceStore(None) and
    EdgarFactsStore(None) provide."""

    _UNSET = object()

    def __init__(self, store_dir: Path | str | None | object = _UNSET) -> None:
        if store_dir is EdgarSubmissionsStore._UNSET:
            self.store_dir: Path | None = DEFAULT_STORE_DIR
        elif store_dir is None:
            self.store_dir = None
        else:
            self.store_dir = Path(store_dir)  # type: ignore[arg-type]

    def _path(self, cik: int) -> Path | None:
        if self.store_dir is None:
            return None
        return self.store_dir / f"CIK{int(cik):010d}{STORE_FILE_SUFFIX}"

    def _coverage_path(self) -> Path | None:
        return None if self.store_dir is None else self.store_dir / COVERAGE_NAME

    def read_rows(self, cik: int) -> tuple[str, list[str], list[dict]]:
        """(entity name, tickers, rows) for one CIK; ("", [], []) when nothing
        is stored. Absent means empty, never an error."""
        path = self._path(cik)
        if path is None or not path.exists():
            return "", [], []
        try:
            payload = json.loads(gzip.decompress(path.read_bytes()))
        except (OSError, EOFError, json.JSONDecodeError, gzip.BadGzipFile):
            logger.warning("EDGAR submissions store: %s is unreadable; treating it as empty", path)
            return "", [], []
        return (
            str(payload.get("entity_name") or ""),
            list(payload.get("tickers") or []),
            list(payload.get("rows") or []),
        )

    def merge_submissions(
        self,
        cik: int,
        document: dict,
        report: EdgarSubmissionsStoreReport,
        *,
        first_seen: date | None = None,
    ) -> int:
        """Add every filing row not already stored; return how many were new.

        THIS IS THE WHOLE POINT: rows already stored are kept even after SEC
        drops them from `filings.recent`, so the union only ever grows. A row
        whose content changed under an accession already stored is refused and
        recorded on report.revisions."""
        seen = utc_today() if first_seen is None else first_seen
        entity_name, tickers, existing = self.read_rows(cik)
        index = {row[IDENTITY_FIELD]: row for row in existing}
        incoming = flatten_submissions(document, first_seen=seen)
        fresh: list[dict] = []
        for row in incoming:
            accession = row[IDENTITY_FIELD]
            stored = index.get(accession)
            if stored is None:
                fresh.append(row)
                index[accession] = row
                continue
            report.rows_already_present += 1
            changed = {
                f: (stored.get(f), row.get(f))
                for f in RECENT_FIELDS
                if stored.get(f) != row.get(f)
            }
            if changed:
                report.revisions.append(
                    (int(cik), accession, str(row.get("filingDate")),
                     {f: v[0] for f, v in changed.items()},
                     {f: v[1] for f, v in changed.items()})
                )
        report.ciks_ingested += 1
        if not fresh:
            return 0
        merged = existing + fresh
        merged.sort(key=lambda r: (r["filingDate"], r[IDENTITY_FIELD]), reverse=True)
        name = str(document.get("entityName") or entity_name or "")
        served_tickers = list(document.get("tickers") or tickers or [])
        if not self._write_rows(cik, name, served_tickers, merged):
            return 0
        report.rows_written += len(fresh)
        return len(fresh)

    def _write_rows(self, cik: int, entity_name: str, tickers: list[str], rows: list[dict]) -> bool:
        path = self._path(cik)
        if path is None:
            return False
        payload = json.dumps(
            {
                "cik": int(cik),
                "entity_name": entity_name,
                "tickers": tickers,
                "schema": STORE_SCHEMA_VERSION,
                "rows": rows,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        return _atomic_write_bytes(path, gzip.compress(payload, 6))

    def submissions_as_of(
        self,
        cik: int,
        *,
        as_of: date | None = None,
        knowledge_cutoff: date | None = None,
    ) -> dict | None:
        """The company's filing index as SEC would have shown it on `as_of` —
        except that it never loses a row the endpoint has since dropped, which
        is the reason this store exists. None when nothing is stored.

        `as_of` filters on SEC's `filingDate`; `knowledge_cutoff` additionally
        filters on when this store first saw the row, which reconstructs what
        a run made on that date actually read."""
        entity_name, tickers, rows = self.read_rows(cik)
        if not rows:
            return None
        kept = rows
        if as_of is not None:
            kept = [r for r in kept if date.fromisoformat(r["filingDate"]) <= as_of]
        if knowledge_cutoff is not None:
            kept = [r for r in kept if date.fromisoformat(r["seen"]) <= knowledge_cutoff]
        return rebuild_submissions(int(cik), entity_name, tickers, kept)

    def earliest_filing_date(self, cik: int) -> date | None:
        """The oldest filing this store retains for a CIK — the company's own
        coverage floor, which an append-only store can only move BACKWARD (by
        a lucky early fetch) and never forward, unlike the endpoint's."""
        _name, _tickers, rows = self.read_rows(cik)
        if not rows:
            return None
        return min(date.fromisoformat(r["filingDate"]) for r in rows)

    # --- coverage ledger --------------------------------------------------

    def read_coverage(self) -> dict[str, list[str]]:
        path = self._coverage_path()
        if path is None or not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def record_fetch(self, cik: int, *, on: date | None = None) -> None:
        """Record that this CIK was asked about on `on`, whether or not it
        yielded rows — so a CIK with no filings is not re-asked forever."""
        path = self._coverage_path()
        if path is None:
            return
        coverage = self.read_coverage()
        key = str(int(cik))
        stamp = (utc_today() if on is None else on).isoformat()
        dates = set(coverage.get(key, []))
        dates.add(stamp)
        coverage[key] = sorted(dates)
        _atomic_write_bytes(path, json.dumps(coverage, sort_keys=True).encode("utf-8"))

    def last_fetched(self, cik: int) -> date | None:
        dates = self.read_coverage().get(str(int(cik)))
        return date.fromisoformat(dates[-1]) if dates else None


def store_manifest(store_dir: Path | str | None | object = EdgarSubmissionsStore._UNSET) -> dict:
    """A summary of what one store holds, written next to an ingest so the
    state of the store on a given day is committed evidence."""
    store = EdgarSubmissionsStore(store_dir)
    empty = {
        "store_dir": str(store.store_dir) if store.store_dir else None,
        "schema": STORE_SCHEMA_VERSION,
        "n_ciks": 0,
        "n_rows": 0,
        "filing_date_range": [None, None],
        "first_seen_range": [None, None],
        "bytes_on_disk": 0,
    }
    if store.store_dir is None or not store.store_dir.exists():
        return empty
    n_rows = 0
    filed_min = filed_max = seen_min = seen_max = None
    n_ciks = 0
    for path in sorted(store.store_dir.glob(f"CIK*{STORE_FILE_SUFFIX}")):
        cik = int(path.name[3 : 3 + 10])
        n_ciks += 1
        _name, _tickers, rows = store.read_rows(cik)
        n_rows += len(rows)
        for row in rows:
            filed, seen = row["filingDate"], row["seen"]
            filed_min = filed if filed_min is None or filed < filed_min else filed_min
            filed_max = filed if filed_max is None or filed > filed_max else filed_max
            seen_min = seen if seen_min is None or seen < seen_min else seen_min
            seen_max = seen if seen_max is None or seen > seen_max else seen_max
    return {
        **empty,
        "n_ciks": n_ciks,
        "n_rows": n_rows,
        "filing_date_range": [filed_min, filed_max],
        "first_seen_range": [seen_min, seen_max],
        "bytes_on_disk": sum(p.stat().st_size for p in store.store_dir.rglob("*") if p.is_file()),
    }
