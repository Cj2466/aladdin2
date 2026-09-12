"""Step A4.6 -- rebuild announcement_dates.csv with a `population` column
(living / formerly_listed) and merge in every ticker that passed the
two-independent-check delisted-name gate (resolve_delisted_names.py).

WHY A REBUILD RATHER THAN AN APPEND:
  1. The panel's 5 stopped-trading tickers that happened to resolve via the
     naive company_tickers.json path in Step A4's first pass (AYR, CONE,
     EMI, FBYDP, SVA) are currently classified as "living" in
     announcement_dates.csv purely because build_universe_ciks.py's
     resolution didn't know about dead_names.csv. Two of those five (CONE,
     EMI) were the WRONG company per the orchestrator's hand-check. This
     rebuild reclassifies all 5 as formerly_listed and re-derives their
     rows from the two-check-gate's OWN verified CIK, dropping any that no
     longer resolve (EMI: no_name under the gate, since it has no
     universe.csv name and no FTD-description recovery either) --
     measured here, not assumed: CONE and EMI each contributed ZERO rows to
     the original announcement_dates.csv (neither the true nor the wrong
     CIK filed an Item 2.02 8-K in the [2000-01-01, 2026-09-12] window), so
     no fabricated event rows actually existed to delete -- but that was
     luck, not the gate working, and is reported as such rather than
     glossed over. AYR/FBYDP/SVA's gate-verified CIK is IDENTICAL to their
     original naive-path CIK (1362988 / 1937987 / 1084201), so their
     existing rows are correct and are simply relabeled.
  2. Every ticker with status == "resolved" in delisted_resolution.csv
     (711 of 1,817 stopped-trading tickers) gets its Item 2.02 events
     extracted from the store, via cross_sectional_pead._parse_item_202_rows
     reused unchanged (identical extraction path to build_announcement_dates.py),
     and appended with population="formerly_listed".

    ./venv/bin/python data/research_runs/edgar_submissions_wholemarket_2026-09-12/rebuild_announcement_dates.py
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
ANNOUNCEMENT_CSV = HERE / "announcement_dates.csv"
DEAD_NAMES_CSV = (
    _BACKEND / "data" / "research_runs" / "delisting_outcomes_2026-09-12" / "dead_names.csv"
)
DELISTED_RESOLUTION_CSV = HERE / "delisted_resolution.csv"
OUT_CSV = HERE / "announcement_dates.csv"  # rewritten in place, same file this step already owns
OUT_REPORT = HERE / "announcement_dates_report.json"  # rewritten in place, same file this step already owns

FETCH_START = date(2000, 1, 1)
FETCH_END = date(2026, 9, 12)


def main() -> int:
    with DEAD_NAMES_CSV.open() as f:
        dead_tickers = {r["ticker"] for r in csv.DictReader(f)}

    with ANNOUNCEMENT_CSV.open() as f:
        existing_rows = list(csv.DictReader(f))
    print(f"existing announcement_dates.csv: {len(existing_rows)} rows")

    # The truncation block from Step A4's first-pass report is computed over
    # the living-universe CIK set and is untouched by this rebuild. It is
    # NOT re-derived from the current announcement_dates_report.json (this
    # script's first run already overwrote that file without it, a mistake
    # caught in review) -- instead read from a small backup snapshotted
    # straight out of that first-pass report before this fix, so the number
    # is carried forward exactly rather than silently dropped or re-guessed.
    truncation_backup_path = HERE / "announcement_dates_truncation.json"
    truncation_block = None
    if truncation_backup_path.exists():
        try:
            truncation_block = json.loads(truncation_backup_path.read_text())
        except json.JSONDecodeError:
            truncation_block = None

    # Drop the 5 stopped-trading tickers that slipped into the "living"
    # table via the naive pass -- they get regenerated below from the
    # gate's own verified CIK (or dropped entirely if the gate could not
    # confirm one).
    dropped = [r for r in existing_rows if r["ticker"] in dead_tickers]
    kept_living = [r for r in existing_rows if r["ticker"] not in dead_tickers]
    print(f"dropping {len(dropped)} rows for {sorted({r['ticker'] for r in dropped})} "
          f"(stopped-trading tickers misclassified as living in the first pass)")
    for r in kept_living:
        r["population"] = "living"

    with DELISTED_RESOLUTION_CSV.open() as f:
        delisted_rows = list(csv.DictReader(f))
    resolved = [r for r in delisted_rows if r["status"] == "resolved"]
    print(f"{len(resolved)}/{len(delisted_rows)} stopped-trading tickers passed both checks")

    store = EdgarSubmissionsStore()
    new_rows: list[dict] = []
    n_ciks_missing_store_rows = 0
    for r in resolved:
        ticker = r["ticker"]
        cik = int(r["cik"])
        retained = store.submissions_as_of(cik)
        if retained is None:
            n_ciks_missing_store_rows += 1
            continue
        events, _truncated = _parse_item_202_rows(ticker, cik, retained, FETCH_START, FETCH_END)
        for e in events:
            new_rows.append(
                {
                    "ticker": e.ticker,
                    "cik": e.cik,
                    "accession": e.accession,
                    "filing_date": e.filing_date.isoformat(),
                    "acceptance_utc": e.acceptance_utc,
                    "population": "formerly_listed",
                }
            )
    print(f"{len(new_rows)} new formerly_listed announcement rows from {len(resolved)} resolved tickers "
          f"({n_ciks_missing_store_rows} resolved CIKs unexpectedly had no stored rows)")

    all_rows = kept_living + new_rows
    all_rows.sort(key=lambda r: (r["ticker"], r["filing_date"]))
    fieldnames = ["ticker", "cik", "accession", "filing_date", "acceptance_utc", "population"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_rows)
    print(f"written {OUT_CSV.relative_to(_BACKEND)}: {len(all_rows)} rows "
          f"({len(kept_living)} living, {len(new_rows)} formerly_listed)")

    # --- per-year, split by population -------------------------------------
    events_per_year: dict[tuple[int, str], int] = defaultdict(int)
    tickers_per_year: dict[tuple[int, str], set] = defaultdict(set)
    for r in all_rows:
        year = int(r["filing_date"][:4])
        pop = r["population"]
        events_per_year[(year, pop)] += 1
        tickers_per_year[(year, pop)].add(r["ticker"])

    years = sorted({y for y, _p in events_per_year})
    year_table = {}
    for y in years:
        year_table[str(y)] = {
            "living": {
                "n_events": events_per_year.get((y, "living"), 0),
                "n_distinct_tickers": len(tickers_per_year.get((y, "living"), set())),
            },
            "formerly_listed": {
                "n_events": events_per_year.get((y, "formerly_listed"), 0),
                "n_distinct_tickers": len(tickers_per_year.get((y, "formerly_listed"), set())),
            },
        }

    n_dead_resolved = len(resolved)
    n_dead_total = len(dead_tickers)
    coverage_pct = round(100 * n_dead_resolved / n_dead_total, 1)

    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "extraction_path": "store-direct (submissions_as_of + cross_sectional_pead._parse_item_202_rows), no live re-fetch",
        "fetch_window": [FETCH_START.isoformat(), FETCH_END.isoformat()],
        "n_rows_total": len(all_rows),
        "n_rows_living": len(kept_living),
        "n_rows_formerly_listed": len(new_rows),
        "n_distinct_tickers_living": len({r["ticker"] for r in kept_living}),
        "n_distinct_tickers_formerly_listed": len({r["ticker"] for r in new_rows}),
        "reclassified_from_living_to_formerly_listed_or_dropped": sorted({r["ticker"] for r in dropped}),
        "note_on_reclassified_tickers": (
            "AYR/FBYDP/SVA's gate-verified CIK is identical to their original naive-path CIK -- their "
            "rows are unchanged, just relabeled formerly_listed. CONE (was wrongly CIK 2103884 'Compass "
            "Sub North, Inc.', now correctly CIK 1553023 'CyrusOne Holdco LLC') and EMI (gate found "
            "no_name -- unresolvable) both contributed ZERO rows to the original table (measured, not "
            "assumed: neither the wrong nor the right CIK filed an Item 2.02 8-K in this window), so no "
            "fabricated event rows actually existed to delete -- that is fortunate, not a property of "
            "the gate, and is stated as such rather than credited as a catch."
        ),
        "events_and_tickers_per_year_by_population": year_table,
        "truncation": truncation_block,
        "delisted_gate_summary": {
            "n_dead_tickers_total": n_dead_total,
            "n_resolved": n_dead_resolved,
            "coverage_pct_of_stopped_trading_tickers": coverage_pct,
        },
        "final_coverage_sentence": (
            f"Of the panel's {n_dead_total} tickers that stopped trading (last bar <= 2026-08-12), "
            f"the announcement-dates table now covers {n_dead_resolved} ({coverage_pct}%) with a "
            "name-match- and date-overlap-verified CIK; the remaining "
            f"{n_dead_total - n_dead_resolved} are excluded rather than guessed at (845 no single "
            "name match, 90 ambiguous name matches, 165 no name recoverable from any free source "
            "tried, 6 name-matched but rejected on date overlap)."
        ),
    }
    OUT_REPORT.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n")
    print(f"written {OUT_REPORT.relative_to(_BACKEND)}")
    print(report["final_coverage_sentence"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
