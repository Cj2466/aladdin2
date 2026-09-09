"""Point-in-time store for SEC EDGAR XBRL company facts — the fundamentals
analogue of price_store.py, and built for the same reason.

WHY THIS EXISTS (the measured failure, 2026-09-09/10). Three Dormant-pool
families re-scored on frozen windows and did not reproduce: asset_growth
(+0.014), pead_ear (-0.016), dividend_payment_pressure (+0.049). The price
store was excluded as the cause by re-running them on the shared repaired
store. What the three have in common is that every one of their remaining
inputs is EDGAR-derived and MUTATES IN PLACE:

  * data/edgar_companyfacts/CIK##########.json is a MUTABLE cache. It is
    rewritten whenever a consumer with max_cache_age_days set asks for it,
    and since quality_cbop went live on 2026-09-08 its live panel (max age
    1 day) rewrites the same ~165 files every UTC day: 163 of 166 were
    rewritten on 2026-09-09. Each rewrite replaces the file in place, so
    what the document said on any earlier date is GONE.
  * company_tickers.json (the ticker -> CIK map) is rewritten the same way,
    and by SEC's own construction it maps only CURRENT tickers — so the
    universe a family resolves is itself a moving input.

The cost of that was demonstrated rather than argued: on 2026-09-10 an
attempt to attribute asset_growth's drift found NO recoverable copy of the
2026-09-04 cache anywhere on the machine (the three apparent "copies" in
worktrees and the session scratchpad all resolve, by inode, to the same live
files), so the question could not be answered at all. A store that had
existed on 09-04 would have answered it in seconds. That is the whole
argument for this module.

WHAT IS STORED, AND WHY IT IS SMALL. Not N dated copies of a 4 MB document.
Every fact SEC publishes already carries the two dates that matter — `filed`
(when the filing became public) and its accession `accn` (which filing it
came from) — so the document is a SET of immutable facts that only ever
grows. This module stores that set once per CIK, flattened, append-only,
gzipped, and rebuilds any dated view of the document on demand. Measured on
12 real documents from this project's own cache (2026-09-10): 66.4 MB of raw
JSON flattens to 60.6 MB and gzips to 3.4 MB — 5.2% of raw, projecting to
~47 MB for the whole 163-document universe against ~903 MB of raw copies.
A second snapshot costs only the facts that are genuinely new.

THE TWO DATES, AND WHY BOTH ARE KEPT. They answer different questions and
this module refuses to conflate them:

  * `filed` is SEC's own record of when a fact became public. It is the
    ECONOMIC point-in-time key, and it is what a backtest must filter on.
    document_as_of(cik, as_of=D) returns the document as SEC's API would
    have shown it on D.
  * `first_seen` is the date THIS STORE first observed the fact. It is the
    REPRODUCIBILITY key: a fact that SEC published on D but that the store
    did not fetch until D+5 (EDGAR's own processing lag is real) would
    silently change a rerun of a window ending on D+1. Passing
    knowledge_cutoff=K restricts the view to what the store knew on K, which
    reproduces the run made on K exactly.

Default behaviour uses `filed` alone, because that is the correct answer for
a backtest; `knowledge_cutoff` exists so that "why did this number move?"
has an answer instead of a shrug.

FIRST-WRITE-WINS, exactly as price_store section 4. A fact's identity is
(taxonomy, tag, unit, start, end, accn) — one filing cannot report two
different values for one tag and period, so anything arriving under an
identity already stored with a DIFFERENT value is either an SEC
re-processing or a bug, never an ordinary update. It is refused and recorded
on EdgarFactsStoreReport.revisions, where a human can look at it, rather than
overwriting history silently. A restatement is not a revision under this
rule: it arrives under a NEW accession with a later `filed`, so it is simply
a new fact, and extract_annual_tag_series' "earliest filed wins" continues to
prefer the originally-published figure.

WHAT SERVING DATED DOCUMENTS ALSO FIXES, measured rather than claimed.
edgar_xbrl_provider.extract_line_items runs _find_cross_filing_scale_conflicts
across the WHOLE document and drops every conflicted (tag, period), so a
filing made in 2026 can remove or re-resolve a period a 2015 backtest would
have seen — a look-ahead channel. Feeding it a document already truncated to
`filed <= as_of` closes it for free. Its size was MEASURED over all 163 cached
documents before any claim was made about it (2026-09-10):

  observations visible in the point-in-time view   15,851 (end-2018)
                                                   21,466 (end-2021)
                                                   26,951 (end-2024)
  dropped by the whole-document scan                    3 / 1 / 0
  resolved differently at the SAME filed date            2 / 0 / 0
  differing value that arrives with a LATER filed date  98 / 10 / 7

The first two rows are the contamination, and they are 0.03% of end-2018
observations and zero by end-2024 — real, worth closing, and NOT an
explanation for any of the three drifts. The third row is the consuming
family working CORRECTLY: a restated figure carries a later `filed` and
build_point_in_time_factor_frame delays it. Recording all three here so the
honest size of the effect survives, rather than the impression that a
look-ahead was found and heroically fixed.

WHAT THIS MODULE DOES NOT COVER, stated so it is not mistaken for done:
cross_sectional_pead's earnings dates come from SEC's SUBMISSIONS endpoint
and are fetched live on every run with no cache at all; the dividend
calendar's share counts come from sec_shares_outstanding_provider's own
mutable cache. Both are the same defect class and neither is served from
here yet.

ROUTED TO THE MAIN CHECKOUT, like the SQLite database and the price store.
A per-worktree fundamentals store would reproduce, one level up, the exact
defect that made backtests irreproducible across checkouts on 2026-09-09
(see price_store.py's SHARED_STORE_ROOT comment).
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from app.config import MAIN_CHECKOUT_BACKEND_DIR

logger = logging.getLogger(__name__)

# Bumped only when the on-disk row shape changes incompatibly; a new version
# is a new directory, so an old one stays readable next to it.
STORE_SCHEMA_VERSION = "v1"

SHARED_STORE_ROOT = MAIN_CHECKOUT_BACKEND_DIR / "data" / "edgar_facts_store"
DEFAULT_STORE_DIR = SHARED_STORE_ROOT / STORE_SCHEMA_VERSION

# Per-CIK file: gzipped JSON {"cik", "entity_name", "rows": [...]}.
STORE_FILE_SUFFIX = ".facts.json.gz"

# Ledger of WHICH DATES each CIK was fetched on. Separate from the rows for
# the same reason price_store keeps one: "have I asked about this CIK?" and
# "does it have facts?" are different questions, and a CIK with no XBRL facts
# at all (EdgarNotFoundError, a real answer) must not be re-asked forever.
COVERAGE_NAME = "_coverage.json"

# Dated snapshots of SEC's ticker -> CIK map, which is mutable and maps only
# CURRENT tickers (edgar_xbrl_provider's measured KNOWN LIMIT 1). One file per
# date it changed, so the universe a past run resolved can be rebuilt.
CIK_MAP_DIR_NAME = "cik_map"

# The fields of one stored fact, in the order they are written. Short keys are
# not an optimisation for its own sake: the flat table is ~91% of the raw
# document before compression and these names repeat once per fact, ~33,000
# times in an average document.
ROW_FIELDS = ("tx", "tag", "u", "s", "e", "v", "a", "f", "form", "fy", "fp", "frame", "seen")

# The identity of a fact: one filing (accn) reporting one tag, in one unit,
# for one period. See the module docstring's first-write-wins paragraph.
IDENTITY_FIELDS = ("tx", "tag", "u", "s", "e", "a")


def utc_today() -> date:
    """The date the store stamps `first_seen` with. UTC, never the process's
    local date — the same rule, and the same 2026-09-10 incident behind it,
    as price_store.utc_today."""
    return datetime.now(UTC).date()


def _parse_iso(value: str) -> date:
    return date.fromisoformat(value)


@dataclass
class EdgarFactsStoreReport:
    """What a store interaction actually did. Never printed, always
    returnable — so a caller can assert on it and an ingest script can
    summarise it.

    `revisions` is the load-bearing field, exactly as on PriceStoreReport:
    it is how a value that changed under an identity already stored becomes
    VISIBLE instead of silently discarded by first-write-wins. Each entry is
    (cik, tag, period end, accn, stored value, incoming value)."""

    ciks_requested: int = 0
    ciks_served_from_store: int = 0
    ciks_fetched: int = 0
    facts_written: int = 0
    facts_already_present: int = 0
    revisions: list[tuple[int, str, str, str, float, float]] = field(default_factory=list)
    missing: list[int] = field(default_factory=list)

    def describe(self) -> str:
        parts = [
            f"{self.ciks_served_from_store}/{self.ciks_requested} CIKs served from store",
            f"{self.ciks_fetched} fetched",
            f"{self.facts_written} facts written",
            f"{self.facts_already_present} already present",
        ]
        if self.revisions:
            parts.append(
                f"{len(self.revisions)} VALUE REVISIONS held back (see .revisions) — "
                "a stored fact's value changed under the same accession"
            )
        if self.missing:
            parts.append(f"{len(self.missing)} CIKs with no facts")
        return ", ".join(parts)


def _atomic_write_bytes(path: Path, payload: bytes) -> bool:
    """Publish a file so a concurrent reader sees the whole old one or the
    whole new one. Same contract, and the same measured torn-read reason, as
    EdgarXbrlProvider._write_cache_atomically: the two quality families'
    live panels walk these same CIKs concurrently on the first tick of each
    UTC day. Returns False when the filesystem refused the write, so a
    caller degrades instead of failing a research run."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
            os.replace(tmp_path, path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
    except OSError:
        logger.warning("EDGAR facts store: could not write %s; continuing without persisting", path)
        return False
    return True


def flatten_document(document: dict, *, first_seen: date) -> list[dict]:
    """Every fact in one companyfacts JSON as a flat row, in a deterministic
    order.

    Faithful to the source rather than to today's consumers: EVERY taxonomy
    (us-gaap, dei, ifrs-full, srt), every unit and every form is kept, not
    just the 10-K/USD subset cross_sectional_quality reads. A store that
    filtered to one family's needs would send the next family back to the
    network, which is how the mutable cache became the problem in the first
    place.

    Rows with no `filed` are DROPPED, with a reason: `filed` is the only key
    that makes a fact point-in-time, and a fact that cannot be dated cannot
    be served as of a date. Measured on this project's 163 cached documents
    (2026-09-10): every one of 1,502,729 annual-form entries carried one."""
    rows: list[dict] = []
    seen_iso = first_seen.isoformat()
    for taxonomy, tags in (document.get("facts") or {}).items():
        if not isinstance(tags, dict):
            continue
        for tag, node in tags.items():
            if not isinstance(node, dict):
                continue
            for unit, entries in (node.get("units") or {}).items():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    filed = entry.get("filed")
                    accn = entry.get("accn")
                    end = entry.get("end")
                    if not filed or not accn or not end:
                        continue
                    rows.append(
                        {
                            "tx": taxonomy,
                            "tag": tag,
                            "u": unit,
                            "s": entry.get("start"),
                            "e": end,
                            "v": entry.get("val"),
                            "a": accn,
                            "f": filed,
                            "form": entry.get("form"),
                            "fy": entry.get("fy"),
                            "fp": entry.get("fp"),
                            "frame": entry.get("frame"),
                            "seen": seen_iso,
                        }
                    )
    rows.sort(key=lambda r: (r["tx"], r["tag"], r["u"], r["s"] or "", r["e"], r["a"]))
    return rows


def rebuild_document(cik: int, entity_name: str, rows: Iterable[dict]) -> dict:
    """The inverse of flatten_document: a companyfacts-shaped dict that
    extract_line_items and every other existing reader accepts unchanged.

    The store's own bookkeeping column (`seen`) is NOT emitted — a caller
    reading a rebuilt document must not be able to tell it apart from one
    SEC served, or the store would quietly become a different input."""
    facts: dict[str, dict] = {}
    for row in rows:
        node = facts.setdefault(row["tx"], {}).setdefault(row["tag"], {"units": {}})
        entry: dict = {"end": row["e"], "val": row["v"], "accn": row["a"], "filed": row["f"]}
        if row.get("s") is not None:
            entry["start"] = row["s"]
        for key, column in (("fy", "fy"), ("fp", "fp"), ("form", "form"), ("frame", "frame")):
            if row.get(column) is not None:
                entry[key] = row[column]
        node["units"].setdefault(row["u"], []).append(entry)
    return {"cik": cik, "entityName": entity_name, "facts": facts}


class _Unset:
    """Sentinel distinguishing "caller passed nothing" from "caller passed
    None", which is a meaningful value here (None disables persistence).
    Same device, for the same reason, as price_store._UNSET."""


_UNSET = _Unset()


class EdgarFactsStore:
    """Append-only, first-write-wins storage for companyfacts, one file per
    CIK, routed to the main checkout (see the module docstring).

    `EdgarFactsStore()` opens the shared store; `EdgarFactsStore(None)`
    disables persistence entirely, so a test or a caller that deliberately
    wants no store can say so without a temp directory — the same escape
    hatch PriceStore(None) provides."""

    def __init__(self, store_dir: Path | str | None | _Unset = _UNSET) -> None:
        if isinstance(store_dir, _Unset):
            self.store_dir: Path | None = DEFAULT_STORE_DIR
        elif store_dir is None:
            self.store_dir = None
        else:
            self.store_dir = Path(store_dir)

    # --- paths ------------------------------------------------------------

    def _path(self, cik: int) -> Path | None:
        if self.store_dir is None:
            return None
        return self.store_dir / f"CIK{int(cik):010d}{STORE_FILE_SUFFIX}"

    def _coverage_path(self) -> Path | None:
        return None if self.store_dir is None else self.store_dir / COVERAGE_NAME

    # --- rows -------------------------------------------------------------

    def read_rows(self, cik: int) -> tuple[str, list[dict]]:
        """(entity name, rows) for one CIK; ("", []) when nothing is stored.
        Absent means empty, never an error — the contract read_ticker and
        load_filing_index both keep."""
        path = self._path(cik)
        if path is None or not path.exists():
            return "", []
        try:
            payload = json.loads(gzip.decompress(path.read_bytes()))
        except (OSError, EOFError, json.JSONDecodeError, gzip.BadGzipFile):
            logger.warning("EDGAR facts store: %s is unreadable; treating it as empty", path)
            return "", []
        return str(payload.get("entity_name") or ""), list(payload.get("rows") or [])

    def merge_document(
        self,
        cik: int,
        document: dict,
        report: EdgarFactsStoreReport,
        *,
        first_seen: date | None = None,
    ) -> int:
        """Add every fact of `document` that this store has not already
        stored, and return how many were new.

        FIRST-WRITE-WINS on (taxonomy, tag, unit, start, end, accn): a fact
        already stored is never replaced, and one whose value has CHANGED
        under that identity is recorded on report.revisions rather than
        applied. `first_seen` defaults to the UTC date and is stamped only
        on the genuinely new rows, so re-ingesting the same document twice
        is a no-op rather than a re-dating of history."""
        seen = utc_today() if first_seen is None else first_seen
        entity_name, existing = self.read_rows(cik)
        index = {tuple(row[k] for k in IDENTITY_FIELDS): row for row in existing}
        incoming = flatten_document(document, first_seen=seen)
        fresh: list[dict] = []
        for row in incoming:
            identity = tuple(row[k] for k in IDENTITY_FIELDS)
            stored = index.get(identity)
            if stored is None:
                fresh.append(row)
                index[identity] = row
                continue
            report.facts_already_present += 1
            if stored.get("v") != row.get("v"):
                report.revisions.append(
                    (
                        int(cik),
                        str(row["tag"]),
                        str(row["e"]),
                        str(row["a"]),
                        stored.get("v"),
                        row.get("v"),
                    )
                )
        if not fresh:
            return 0
        merged = existing + fresh
        merged.sort(key=lambda r: (r["tx"], r["tag"], r["u"], r["s"] or "", r["e"], r["a"]))
        name = str(document.get("entityName") or entity_name or "")
        if not self._write_rows(cik, name, merged):
            # No store directory, or the filesystem refused the write. Nothing
            # was persisted, so nothing may be REPORTED as written — a count a
            # caller could not read back would be the one lie this module
            # cannot afford.
            return 0
        report.facts_written += len(fresh)
        return len(fresh)

    def _write_rows(self, cik: int, entity_name: str, rows: list[dict]) -> bool:
        path = self._path(cik)
        if path is None:
            return False
        payload = json.dumps(
            {"cik": int(cik), "entity_name": entity_name, "schema": STORE_SCHEMA_VERSION, "rows": rows},
            separators=(",", ":"),
        ).encode("utf-8")
        return _atomic_write_bytes(path, gzip.compress(payload, 6))

    # --- the point-in-time read -------------------------------------------

    def document_as_of(
        self,
        cik: int,
        *,
        as_of: date | None = None,
        knowledge_cutoff: date | None = None,
    ) -> dict | None:
        """The companyfacts document as SEC would have shown it on `as_of`,
        or None when this CIK has nothing stored.

        `as_of` filters on SEC's own `filed` — the economic point-in-time
        question, and the one a backtest must ask. `knowledge_cutoff`
        additionally filters on when THIS STORE first saw each fact, which
        is the reproducibility question: it reconstructs what a run made on
        that date actually read, including the facts SEC had published but
        the store had not yet fetched. Passing neither returns everything
        stored, which is what a live consumer wants."""
        entity_name, rows = self.read_rows(cik)
        if not rows:
            return None
        kept = rows
        if as_of is not None:
            kept = [r for r in kept if _parse_iso(r["f"]) <= as_of]
        if knowledge_cutoff is not None:
            kept = [r for r in kept if _parse_iso(r["seen"]) <= knowledge_cutoff]
        return rebuild_document(int(cik), entity_name, kept)

    # --- coverage ledger --------------------------------------------------

    def read_coverage(self) -> dict[str, list[str]]:
        """CIK (as a string key, since JSON has no integer keys) -> the
        sorted dates this store fetched it on. A corrupt ledger is treated
        as empty: the worst cost of ignoring it is a redundant fetch."""
        path = self._coverage_path()
        if path is None or not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def record_fetch(self, cik: int, *, on: date | None = None) -> None:
        """Record that this CIK was asked about on `on` (default the UTC
        date), whether or not it yielded any facts — so a CIK SEC has no
        XBRL for is not re-asked on every run forever."""
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
        return _parse_iso(dates[-1]) if dates else None

    # --- the ticker -> CIK map, snapshotted by date ------------------------

    def record_cik_map(self, mapping: dict[str, int], *, on: date | None = None) -> Path | None:
        """Snapshot SEC's ticker -> CIK map for one date, but only when it
        DIFFERS from the newest snapshot already stored.

        The map is mutable and maps only CURRENT tickers, so it silently
        changes which companies a family resolves — a moving universe is a
        moving result, and no amount of price- or fact-level immutability
        fixes it. Skipping an unchanged map keeps the directory one file per
        real change rather than one per day."""
        if self.store_dir is None:
            return None
        directory = self.store_dir / CIK_MAP_DIR_NAME
        stamp = (utc_today() if on is None else on).isoformat()
        newest = self.latest_cik_map()
        if newest is not None and newest[1] == mapping:
            return None
        path = directory / f"{stamp}.json.gz"
        payload = json.dumps(mapping, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return path if _atomic_write_bytes(path, gzip.compress(payload, 6)) else None

    def cik_map_as_of(self, as_of: date) -> dict[str, int] | None:
        """The newest snapshot taken on or before `as_of`, or None when the
        store has none that old — never a later one, which would be exactly
        the look-ahead this directory exists to remove."""
        for stamp, mapping in self._cik_map_snapshots(newest_first=True):
            if stamp <= as_of:
                return mapping
        return None

    def latest_cik_map(self) -> tuple[date, dict[str, int]] | None:
        for stamp, mapping in self._cik_map_snapshots(newest_first=True):
            return stamp, mapping
        return None

    def _cik_map_snapshots(self, *, newest_first: bool = False):
        if self.store_dir is None:
            return
        directory = self.store_dir / CIK_MAP_DIR_NAME
        if not directory.exists():
            return
        paths = sorted(directory.glob("*.json.gz"), reverse=newest_first)
        for path in paths:
            try:
                stamp = _parse_iso(path.name.split(".")[0])
                yield stamp, json.loads(gzip.decompress(path.read_bytes()))
            except (ValueError, OSError, EOFError, json.JSONDecodeError, gzip.BadGzipFile):
                logger.warning("EDGAR facts store: unreadable CIK-map snapshot %s", path)
                continue


def store_manifest(store_dir: Path | str | None | _Unset = _UNSET) -> dict:
    """A summary of what one store holds — CIK count, fact count, the span of
    `filed` and `first_seen` dates, and the CIK-map snapshot dates.

    Written next to an ingest so the state of the store on a given day is
    committed evidence, the same role price_store's audit JSON plays."""
    store = EdgarFactsStore(store_dir)
    empty = {
        "store_dir": str(store.store_dir) if store.store_dir else None,
        "schema": STORE_SCHEMA_VERSION,
        "n_ciks": 0,
        "n_facts": 0,
        "filed_range": [None, None],
        "first_seen_range": [None, None],
        "cik_map_snapshots": [],
        "bytes_on_disk": 0,
    }
    if store.store_dir is None or not store.store_dir.exists():
        # Same key set whether or not the store exists yet — a caller writing
        # a manifest must not have to branch on it.
        return empty
    n_facts = 0
    filed_min = filed_max = seen_min = seen_max = None
    ciks: list[int] = []
    for path in sorted(store.store_dir.glob(f"CIK*{STORE_FILE_SUFFIX}")):
        cik = int(path.name[3 : 3 + 10])
        ciks.append(cik)
        _name, rows = store.read_rows(cik)
        n_facts += len(rows)
        for row in rows:
            filed, seen = row["f"], row["seen"]
            filed_min = filed if filed_min is None or filed < filed_min else filed_min
            filed_max = filed if filed_max is None or filed > filed_max else filed_max
            seen_min = seen if seen_min is None or seen < seen_min else seen_min
            seen_max = seen if seen_max is None or seen > seen_max else seen_max
    snapshots = [stamp.isoformat() for stamp, _ in store._cik_map_snapshots()]
    return {
        "store_dir": str(store.store_dir),
        "schema": STORE_SCHEMA_VERSION,
        "n_ciks": len(ciks),
        "n_facts": n_facts,
        "filed_range": [filed_min, filed_max],
        "first_seen_range": [seen_min, seen_max],
        "cik_map_snapshots": snapshots,
        "bytes_on_disk": sum(p.stat().st_size for p in store.store_dir.rglob("*") if p.is_file()),
    }
