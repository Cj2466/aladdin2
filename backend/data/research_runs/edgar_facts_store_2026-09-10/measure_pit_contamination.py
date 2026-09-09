"""The three measurements behind EDGAR_FACTS_STORE_2026-09-10.md, re-runnable.

    ./venv/bin/python data/research_runs/edgar_facts_store_2026-09-10/measure_pit_contamination.py

READ-ONLY. Writes its findings next to this script as
pit_contamination_<timestamp>.json so the numbers the memo quotes are committed
evidence rather than a transcript.

  (1) LATE FILINGS — how many annual-form facts in the cache were filed after a
      given date. Answers "could new filings alone have moved a frozen-window
      result?" Measured 2026-09-10 for 2026-09-04: 0 of 1,502,729, so no.

  (2) LOOK-AHEAD — extract_line_items runs _find_cross_filing_scale_conflicts
      over the WHOLE document and drops every conflicted (tag, period), so a
      filing made in 2026 can remove or re-resolve a period a 2015 backtest
      would have used. Compares extract_line_items(full document) against
      extract_line_items(document truncated to filed <= D) and classifies every
      difference, restricted to observations the point-in-time view says were
      visible on D. The classification matters more than the count: a differing
      value that arrives with a LATER filed date is the consuming family working
      CORRECTLY (build_point_in_time_factor_frame delays it), not contamination.

  (3) STORE FIDELITY — the store's served document must give extract_line_items
      exactly what the raw cache file gives it, or the store has quietly become
      a different input. Skipped when the store is empty.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND))

from app.services.market_data.edgar_facts_store import EdgarFactsStore
from app.services.market_data.edgar_xbrl_provider import (
    ANNUAL_FORMS,
    DEFAULT_CACHE_DIR,
    _parse_iso,
    extract_line_items,
)

HERE = Path(__file__).resolve().parent
AS_OFS = (date(2018, 12, 31), date(2021, 12, 31), date(2024, 12, 31))
LATE_FILING_CUTOFF = date(2026, 9, 4)  # the effective-N run the drifts are measured against


def truncate(document: dict, as_of: date) -> dict:
    """The document as SEC's API would have shown it on `as_of`."""
    out: dict[str, dict] = {}
    for taxonomy, tags in (document.get("facts") or {}).items():
        for tag, node in tags.items():
            units = {}
            for unit, entries in (node.get("units") or {}).items():
                kept = [e for e in entries if e.get("filed") and _parse_iso(e["filed"]) <= as_of]
                if kept:
                    units[unit] = kept
            if units:
                out.setdefault(taxonomy, {})[tag] = {**node, "units": units}
    return {"cik": document.get("cik"), "entityName": document.get("entityName"), "facts": out}


def main() -> int:
    documents = sorted(Path(DEFAULT_CACHE_DIR).glob("CIK*.json"))
    print(f"cache: {DEFAULT_CACHE_DIR} ({len(documents)} documents)")
    store = EdgarFactsStore()

    late = Counter()
    n_annual = 0
    contamination = {d: Counter() for d in AS_OFS}
    examples: dict[date, list] = {d: [] for d in AS_OFS}
    fidelity = Counter()
    mismatches: list = []

    for i, path in enumerate(documents, start=1):
        try:
            doc = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  UNREADABLE {path.name}: {exc}")
            continue
        cik = int(doc.get("cik") or path.stem.removeprefix("CIK"))

        # (1) late filings
        for tags in (doc.get("facts") or {}).values():
            for node in tags.values():
                for entries in (node.get("units") or {}).values():
                    for e in entries:
                        if e.get("form") not in ANNUAL_FORMS or not e.get("filed"):
                            continue
                        n_annual += 1
                        if _parse_iso(e["filed"]) > LATE_FILING_CUTOFF:
                            late[str(cik)] += 1

        # (2) look-ahead
        full = extract_line_items(doc)
        for as_of in AS_OFS:
            pit = extract_line_items(truncate(doc, as_of))
            counter = contamination[as_of]
            for item, resolved in pit.items.items():
                for end, r in resolved.items():
                    if r.filed > as_of:
                        continue
                    counter["visible_observations"] += 1
                    f = full.items.get(item, {}).get(end)
                    if f is None:
                        counter["dropped_by_the_whole_document_scan"] += 1
                    elif f.value != r.value:
                        if f.filed > as_of:
                            counter["value_arrives_with_a_later_filed_date"] += 1
                        elif f.filed == r.filed:
                            counter["resolved_differently_at_the_same_filed_date"] += 1
                            if len(examples[as_of]) < 10:
                                examples[as_of].append(
                                    [path.stem, item, str(end), r.tag, f.tag, r.value, f.value, str(r.filed)]
                                )
                        else:
                            counter["other_filed_date_difference"] += 1
                    elif f.tag != r.tag:
                        counter["same_value_different_tag"] += 1

        # (3) store fidelity
        served = store.document_as_of(cik)
        if served is not None:
            fidelity["documents_compared"] += 1
            served_x = extract_line_items(served)
            for item, resolved in full.items.items():
                if set(resolved) != set(served_x.items.get(item, {})):
                    fidelity["period_set_differs"] += 1
                    mismatches.append([path.stem, item, "periods differ"])
                    continue
                for end, r in resolved.items():
                    fidelity["observations_compared"] += 1
                    s = served_x.items[item][end]
                    if (r.value, r.filed, r.tag) != (s.value, s.filed, s.tag):
                        fidelity["MISMATCH"] += 1
                        if len(mismatches) < 10:
                            mismatches.append([path.stem, item, str(end), r.value, s.value])

        if i % 40 == 0 or i == len(documents):
            print(f"  {i}/{len(documents)}", flush=True)

    now = datetime.now(UTC)
    payload = {
        "run_at": now.isoformat(timespec="minutes"),
        "cache": str(DEFAULT_CACHE_DIR),
        "n_documents": len(documents),
        "late_filings": {
            "cutoff": LATE_FILING_CUTOFF.isoformat(),
            "annual_entries_scanned": n_annual,
            "n_documents_with_late_facts": len(late),
            "n_late_facts": sum(late.values()),
            "per_cik": dict(late.most_common(20)),
        },
        "look_ahead": {
            as_of.isoformat(): {
                **dict(counter),
                "examples_same_filed_date": examples[as_of],
            }
            for as_of, counter in contamination.items()
        },
        "store_fidelity": {**dict(fidelity), "mismatches": mismatches},
    }
    out = HERE / f"pit_contamination_{now.strftime('%Y-%m-%dT%H%MZ')}.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    print(f"\n(1) annual entries {n_annual:,}; filed after {LATE_FILING_CUTOFF}: {sum(late.values())}")
    for as_of, counter in contamination.items():
        visible = counter["visible_observations"] or 1
        print(
            f"(2) as of {as_of}: {counter['visible_observations']:,} visible | "
            f"dropped {counter['dropped_by_the_whole_document_scan']} | "
            f"same-filed-date re-resolution {counter['resolved_differently_at_the_same_filed_date']} "
            f"({100 * (counter['dropped_by_the_whole_document_scan'] + counter['resolved_differently_at_the_same_filed_date']) / visible:.3f}%) | "
            f"later-filed value {counter['value_arrives_with_a_later_filed_date']}"
        )
    print(
        f"(3) store: {fidelity['documents_compared']} documents, "
        f"{fidelity['observations_compared']:,} observations, {fidelity['MISMATCH']} mismatches"
    )
    print(f"written {out.relative_to(_BACKEND)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
