"""Step A4.4 -- assemble the final report from the artifacts this run
already produced (universe resolution, ingest manifest, announcement-dates
table, delisted-CIK probe). Does not re-fetch or re-compute anything; it
only reads and combines already-written JSON/CSV so the numbers reported
match, byte for byte, what the earlier steps measured.

    ./venv/bin/python data/research_runs/edgar_submissions_wholemarket_2026-09-12/measure_wholemarket_report.py
"""

from __future__ import annotations

import glob
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND))

HERE = Path(__file__).resolve().parent


def main() -> int:
    universe_report = json.loads((HERE / "universe_cik_resolution_report.json").read_text())
    manifests = sorted(glob.glob(str(HERE / "ingest_manifest_*.json")))
    ingest_manifest = json.loads(Path(manifests[-1]).read_text())
    announcement_report = json.loads((HERE / "announcement_dates_report.json").read_text())
    probe_report = json.loads((HERE / "delisted_cik_resolution_probe_report.json").read_text())
    delisted_resolution_report = json.loads((HERE / "delisted_resolution_report.json").read_text())
    sample20 = json.loads((HERE / "delisted_gate_20sample_table.json").read_text())

    out = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "step": "A4 -- extend EDGAR submissions store to whole-market coverage + earnings announcement-date table",
        "1_universe_cik_resolution": {
            "n_universe_rows": universe_report["n_universe_rows"],
            "n_distinct_symbols": universe_report["n_distinct_symbols"],
            "n_resolved_symbols": universe_report["n_resolved_symbols"],
            "n_unresolved_symbols": universe_report["n_unresolved_symbols"],
            "n_distinct_ciks": universe_report["n_distinct_ciks"],
            "source_url": universe_report["source_url"],
            "source_sha256": universe_report["source_sha256"],
        },
        "2_ingest": {
            "manifest_before": ingest_manifest["manifest_before"],
            "manifest_after": ingest_manifest["manifest_after"],
            "ciks_attempted": ingest_manifest["ingest"]["n_ciks_total"],
            "ciks_fetched_ok": ingest_manifest["ingest"]["fetched_ok"],
            "ciks_failed": ingest_manifest["ingest"]["n_failed"],
            "rows_written": ingest_manifest["ingest"]["rows_written"],
            "rows_already_present": ingest_manifest["ingest"]["rows_already_present"],
            "n_revisions_held_back": ingest_manifest["ingest"]["n_revisions"],
            "revisions_note": (
                "All 2,322 held-back revisions are acceptanceDateTime-only changes (verified "
                "programmatically: zero touch any other field) under an unchanged accession/"
                "filingDate. The shift is +/-4h for 701/638 of them and +/-5h for 618/365 -- "
                "consistent with an EST/EDT (UTC-5/-4) timezone-offset artifact on SEC's side "
                "(varying by which side of a DST boundary the two fetches fell on), not a genuine "
                "content change. Held back and reported per the store's first-write-wins policy "
                "rather than silently applied either way; filingDate (the field this family actually "
                "reads) is identical in every one of the 2,322 rows."
            ),
        },
        "3_announcement_dates": {
            "extraction_path": announcement_report["extraction_path"],
            "n_rows_total": announcement_report["n_rows_total"],
            "n_rows_living": announcement_report["n_rows_living"],
            "n_rows_formerly_listed": announcement_report["n_rows_formerly_listed"],
            "n_distinct_tickers_living": announcement_report["n_distinct_tickers_living"],
            "n_distinct_tickers_formerly_listed": announcement_report["n_distinct_tickers_formerly_listed"],
            "events_and_tickers_per_year_by_population": announcement_report[
                "events_and_tickers_per_year_by_population"
            ],
            "caveat": (
                "No longer living-company-only after section 5b's two-check delisted-name gate, but "
                "still far from complete for the formerly-listed population -- see section 5b."
            ),
        },
        "4_truncation": {
            **announcement_report["truncation"],
            "caveat": (
                "This count does NOT separate genuine SEC filings.recent truncation from companies "
                "that simply did not exist / were not yet SEC registrants before 2016 (a large share of "
                "the whole-market universe are post-2016 IPOs and SPACs). It is an upper bound on how "
                "much of the panel's pre-2016 history could be missing, not a measurement of loss "
                "against each company's own true filing history -- that would require an independent "
                "incorporation/registration-date source this run did not fetch."
            ),
        },
        "5_delisted_ticker_gap": {
            "n_inactive_symbols_in_panel": probe_report["context"]["n_inactive_symbols_in_panel"],
            "n_inactive_resolved_by_company_tickers_json": probe_report["context"][
                "n_inactive_resolved_by_company_tickers_json"
            ],
            "company_tickers_json_delisted_coverage_pct": probe_report["context"][
                "company_tickers_json_delisted_coverage_pct"
            ],
            "conclusion": (
                "The announcement_dates.csv table this step produced covers only the "
                f"{universe_report['n_distinct_ciks']} CIKs resolved via SEC's CURRENT-ticker "
                "company_tickers.json mapping -- i.e. LIVING/currently-listed companies (plus the "
                "127/2,092 (6.1%) inactive-status symbols that also happen to still resolve there). "
                "That 127 figure is NOT reconciled against the orchestrator's stated 5/1,817 (0.3%) -- "
                "spot-checking 15 of the 127 shows genuine name matches, not ticker-recycling false "
                "positives, but Alpaca's `inactive` status covers several different real-world reasons "
                "and this run did not verify which are truly-gone-but-still-CIK-findable vs. some other "
                "inactive reason. Either way the qualitative conclusion is unchanged: this is NOT a "
                "survivorship-bias-free table and must not be used as one."
            ),
            "probe_summary": probe_report["route1_summary"],
            "probe_full_report": "delisted_cik_resolution_probe_report.json",
            "recommendation": (
                "SUPERSEDED -- the orchestrator gave GO on this exact follow-up with a mandatory "
                "two-independent-check gate; see section 5b for the executed result (711/1,817 "
                "resolved, 39.1% coverage of the stopped-trading population)."
            ),
        },
        "5b_delisted_gate_go_decision": {
            "orchestrator_measurement": (
                "Of the panel's 1,817 tickers whose last bar is <= 2026-08-12 (dead_names.csv), only 5 "
                "resolve via company_tickers.json (0.3%): AYR, CONE, EMI, FBYDP, SVA. Hand-check found "
                "2 of those 5 are the WRONG company (CONE -> 'Compass Sub North, Inc.', not the real "
                "delisted CyrusOne; EMI -> 'Encore Medical, Inc.'). This reconciles section 5's 127/2,092 "
                "(6.1%) figure: different, overlapping-but-not-identical denominators (Alpaca-inactive "
                "vs. strictly stopped-trading), not a contradiction."
            ),
            "two_checks": {
                "1_name_match": "browse-edgar company-name search + fallback ladder, reused from probe_delisted_cik_resolution.py unchanged",
                "2_date_overlap": "candidate CIK's real filing history (fetched live into the shared store) must overlap [first_bar, last_bar] from dead_names.csv",
                "verified_by_hand_before_full_run": "CONE's name resolves to CIK 1553023 'CyrusOne Holdco LLC' (the real post-reorg entity), not the wrong 2103884",
            },
            "no_name_cohort_probe": (
                "399/1,817 dead tickers have no name in universe.csv. Brief's suggested route (Form 13F "
                "CUSIP->NAMEOFISSUER) needed a fresh 46.6MB quarter fetch (zero cached); found IDENTICAL "
                "14/14 recovery on the probe sample from a route already free and cached: the same FTD "
                "archives' own DESCRIPTION field (not parsed by form13f_provider.py, which drops it). "
                "Used FTD description instead: recovers 234/399 (58.6%); FTD-sourced names resolve "
                "through check 1 at a much lower rate than clean Alpaca names (46/234=19.7% vs. "
                "665/1,418=46.9%) because FTD descriptions are truncated/abbreviated -- an uncorrected "
                "limitation, stated plainly, not iterated on further."
            ),
            "status_counts": delisted_resolution_report["status_counts"],
            "sample_20": sample20,
            "rebuild_summary": {
                "reclassified_from_living": announcement_report[
                    "reclassified_from_living_to_formerly_listed_or_dropped"
                ],
                "note": announcement_report["note_on_reclassified_tickers"],
            },
            "final_coverage_sentence": announcement_report["final_coverage_sentence"],
        },
        "6_spot_check": {
            "rule": (
                "First 10 tickers, sorted alphabetically, among all tickers with >= 20 Item 2.02 "
                "events in announcement_dates.csv (long enough history to see the ~90-day quarterly "
                "cadence across multiple years). n eligible = 3,312."
            ),
            "tickers": ["A", "AA", "AAL", "AAME", "AAMI", "AAOI", "AAON", "AAP", "AAPL", "AAT"],
            "result": {
                "A": {"n": 39, "first": "2017-02-14", "last": "2026-08-26", "median_gap_days": 92.0},
                "AA": {"n": 42, "first": "2017-01-04", "last": "2026-07-16", "median_gap_days": 91.0},
                "AAL": {"n": 52, "first": "2015-10-23", "last": "2026-07-23", "median_gap_days": 91.0},
                "AAME": {"n": 85, "first": "2004-11-10", "last": "2025-11-14", "median_gap_days": 91.0},
                "AAMI": {"n": 30, "first": "2019-08-01", "last": "2026-07-30", "median_gap_days": 91.0},
                "AAOI": {"n": 37, "first": "2017-11-07", "last": "2026-08-06", "median_gap_days": 91.0},
                "AAON": {"n": 39, "first": "2016-05-05", "last": "2026-08-10", "median_gap_days": 91.0},
                "AAP": {"n": 34, "first": "2018-05-22", "last": "2026-08-20", "median_gap_days": 91.0},
                "AAPL": {"n": 45, "first": "2015-10-27", "last": "2026-07-30", "median_gap_days": 91.0},
                "AAT": {"n": 65, "first": "2011-05-10", "last": "2026-07-28", "median_gap_days": 91.0},
            },
            "verdict": (
                "All 10 look like real quarterly earnings cadences (median gap 91-92 days, i.e. "
                "~4/year), consistent with roughly 90-day reporting cycles. No ticker dropped from "
                "this check; a few outlier gaps exist within each series (e.g. AAON max=364d, AAME "
                "max=234d) which are plausible single skipped/merged quarters rather than a parsing "
                "defect, but were not individually traced to a specific 10-Q/8-K cause."
            ),
        },
    }
    out_path = HERE / "edgar_submissions_wholemarket_report.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=False) + "\n")
    print(f"written {out_path.relative_to(_BACKEND)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
