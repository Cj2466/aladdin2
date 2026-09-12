"""Step A4.5 -- resolve the panel's 1,817 STOPPED-TRADING tickers to CIKs
under a two-independent-check gate, per the orchestrator's GO decision.

WHY THE GATE IS MANDATORY, measured by the orchestrator, not assumed: of
the panel's 1,817 tickers whose last bar is <= 2026-08-12, only 5 resolve
via SEC's current-ticker company_tickers.json (AYR, CONE, EMI, FBYDP, SVA).
Hand-checking those 5 found **2 are the WRONG company** -- CONE now maps to
"Compass Sub North, Inc." (the real CyrusOne, acquired 2022, is a different,
defunct CIK) and EMI maps to "Encore Medical, Inc." (unrelated to whatever
EMI actually was). A ticker-string match is, for a dead name, MORE LIKELY
WRONG THAN RIGHT, and a wrong match silently attaches company A's earnings
dates to company B's -- and by extension, to whatever price series a family
reads under that ticker -- which is a fabricated-looking-plausible return,
exactly the failure mode this whole project exists to prevent.

THE TWO CHECKS, both required, matching the probe's own measured routes:

  1. NAME MATCH -- SEC browse-edgar company-name search (getcompany&company=
     <name>), reusing clean_name/strip_corp_suffix/route_browse_edgar_company_name
     from probe_delisted_cik_resolution.py UNCHANGED (imported, not copied).
     Rejected as ambiguous if 0 or >1 candidates survive the name+fallback
     query ladder measured in that probe (73% resolution rate on the
     20-ticker sample).

  2. DATE OVERLAP -- the candidate CIK's own filing history (fetched live,
     merged into the shared EdgarSubmissionsStore exactly like every other
     CIK this project stores) must overlap [first_bar, last_bar] from
     dead_names.csv. A CIK whose every filing is before first_bar or after
     last_bar cannot be the company that traded under this ticker during
     that window -- REJECTED regardless of how clean the name match looked
     (this is exactly the check that would have caught CONE/EMI, since
     "Compass Sub North" / "Encore Medical" almost certainly do not have a
     filing history overlapping the real CyrusOne's 2016-2022 trading run).

ALL 1,817 dead tickers go through this SAME gate uniformly -- including the
5 that a naive company_tickers.json match already resolved (2 of them
wrongly) and that are ALREADY IN announcement_dates.csv from Step A4's first
pass. This script's output supersedes those 5 rows: CONE and EMI's existing
(wrong) rows are identified for removal by the caller
(rebuild_announcement_dates.py), not silently left in place.

NAME SOURCE FOR THE "NO NAME" TICKERS (399 of 1,817 have no `name` in
universe.csv): probed first per instruction, not bulk-run blind. SEC's
Form 13F quarterly holdings (INFOTABLE.tsv's NAMEOFISSUER, keyed by CUSIP)
was the route named in the brief, but NO quarterly 13F archive is cached
locally (only 29 fails-to-deliver archives are) -- fetching one to test
(2018q3, 46.6MB) found it recovers a usable issuer name for every ticker
that has ANY cached CUSIP, but that CUSIP is the bottleneck, not the name
lookup. The already-cached FTD archives carry the SAME CUSIP plus their own
DESCRIPTION field (parsed here, not by the shared form13f_provider.py code,
since that module discards DESCRIPTION), which gives an equivalent name
proxy for FREE (no new fetch) with IDENTICAL coverage on the 20-ticker probe
sample (14/14 tickers that had a CUSIP recovered a name from BOTH routes).
This script therefore uses FTD DESCRIPTION as the name source for the
no-`name` cohort (234/399 = 58.6% recover this way; the other 165/399 have
no CUSIP in any cached FTD archive and stay unresolvable this round) --
cheaper and equally complete, not a deviation in kind from the requested
13F route, and the 13F quarter fetched to prove the equivalence is left
cached in data/form13f_raw/ for any future use.

    ./venv/bin/python data/research_runs/edgar_submissions_wholemarket_2026-09-12/resolve_delisted_names.py

Resumable the same way ingest_wholemarket.py is: a candidate CIK already
fetched today is not re-fetched (store.last_fetched). Progress logged every
100 tickers to resolve_delisted_progress.jsonl.
"""

from __future__ import annotations

import csv
import io
import json
import sys
import time
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND))
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from probe_delisted_cik_resolution import (
    clean_name,
    route_browse_edgar_company_name,
    strip_corp_suffix,
)

from app.services.market_data.edgar_submissions_store import (
    EdgarSubmissionsStore,
    EdgarSubmissionsStoreReport,
    utc_today,
)
from app.services.market_data.form13f_provider import (
    Form13FProvider,
    normalize_cusip,
    normalize_ticker,
)
from app.services.research_lab.cross_sectional_pead import (
    PEAD_SEC_USER_AGENT,
    SEC_SUBMISSIONS_URL_TEMPLATE,
    _sec_get_json,
)

UNIVERSE_CSV = _BACKEND / "data" / "research_runs" / "whole_market_panel_2026-09-12" / "universe.csv"
DEAD_NAMES_CSV = (
    _BACKEND / "data" / "research_runs" / "delisting_outcomes_2026-09-12" / "dead_names.csv"
)
OUT_CSV = HERE / "delisted_resolution.csv"
OUT_REPORT = HERE / "delisted_resolution_report.json"
PROGRESS_LOG = HERE / "resolve_delisted_progress.jsonl"

# Halved from the project default (0.15s) for the SAME reason
# probe_delisted_cik_resolution.py halves it: this script issues browse-edgar
# AND data.sec.gov requests, and no other process should be hammering SEC
# concurrently, but a conservative margin under the 10 req/s cap is cheap.
MIN_REQUEST_INTERVAL = 0.2
LOG_EVERY = 100


def load_ftd_name_map(tickers: set[str]) -> dict[str, str]:
    """ticker -> a DESCRIPTION string from SEC's own cached fails-to-deliver
    archives, for tickers with no name in universe.csv. Not part of
    form13f_provider.parse_ftd_archive (which drops DESCRIPTION), so parsed
    directly here -- reusing normalize_cusip/normalize_ticker from that
    module rather than re-deriving the normalisation rules."""
    provider = Form13FProvider()
    stamps = provider.available_ftd_stamps()
    out: dict[str, set[str]] = {}
    for stamp in stamps:
        zb = provider.get_ftd_archive(stamp)
        archive = zipfile.ZipFile(io.BytesIO(zb))
        for member in archive.namelist():
            if member.endswith("/"):
                continue
            text = archive.read(member).decode("utf-8", errors="replace")
            for line in text.split("\n")[1:]:
                parts = line.rstrip("\r").split("|")
                if len(parts) < 5:
                    continue
                symbol = normalize_ticker(parts[2])
                if symbol not in tickers:
                    continue
                cusip = normalize_cusip(parts[1])
                if cusip is None:
                    continue
                desc = parts[4].strip()
                if desc:
                    out.setdefault(symbol, set()).add(desc)
    # A ticker with >1 distinct description across archives (e.g. a security
    # renamed mid-history) uses the LONGEST description as the name query --
    # longer FTD descriptions are measured (see probe write-up) to be closer
    # to a full company name ("ALDER BIOPHARMACEUTICALS INC" vs a truncated
    # "ALDER BIOPHARMA"), which the browse-edgar route matches better.
    return {t: max(v, key=len) for t, v in out.items()}


def main() -> int:
    with UNIVERSE_CSV.open() as f:
        alpaca_name = {r["symbol"]: r["name"].strip() for r in csv.DictReader(f)}
    with DEAD_NAMES_CSV.open() as f:
        dead = {
            r["ticker"]: (date.fromisoformat(r["first_bar"]), date.fromisoformat(r["last_bar"]))
            for r in csv.DictReader(f)
        }
    tickers = sorted(dead)
    print(f"{len(tickers)} stopped-trading tickers to resolve")

    no_name_tickers = {t for t in tickers if not alpaca_name.get(t)}
    print(f"{len(no_name_tickers)} have no name in universe.csv; probing FTD description fallback")
    ftd_names = load_ftd_name_map(no_name_tickers)
    print(f"FTD description recovered a name for {len(ftd_names)}/{len(no_name_tickers)} of those")

    store = EdgarSubmissionsStore()
    store_report = EdgarSubmissionsStoreReport()
    today = utc_today()

    rows: list[dict] = []
    last_request = 0.0

    def throttle() -> None:
        nonlocal last_request
        elapsed = time.monotonic() - last_request
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        last_request = time.monotonic()

    def resolve_one(ticker: str) -> dict:
        first_bar, last_bar = dead[ticker]
        name = alpaca_name.get(ticker) or ftd_names.get(ticker) or ""
        name_source = "alpaca" if alpaca_name.get(ticker) else ("ftd_description" if ftd_names.get(ticker) else "")

        row: dict = {
            "ticker": ticker,
            "first_bar": first_bar.isoformat(),
            "last_bar": last_bar.isoformat(),
            "name_source": name_source,
            "raw_name": name,
        }

        if not name:
            row.update(status="no_name", cleaned_name="", query_used="", n_matches=None, cik=None)
            return row

        cleaned = clean_name(name)
        throttle()
        r1 = route_browse_edgar_company_name(cleaned)
        query_used = cleaned
        n_matches = r1.get("n_matches", 0)
        candidates = r1.get("ciks", [])
        if n_matches != 1:
            fallback_name = strip_corp_suffix(cleaned)
            if fallback_name and fallback_name != cleaned:
                throttle()
                r2 = route_browse_edgar_company_name(fallback_name)
                if r2.get("n_matches") == 1:
                    query_used = fallback_name
                    n_matches = 1
                    candidates = r2.get("ciks", [])

        row["cleaned_name"] = cleaned
        row["query_used"] = query_used
        row["n_matches"] = n_matches

        if n_matches == 0:
            row.update(status="rejected_by_name_zero", cik=None)
            return row
        if n_matches > 1:
            row.update(
                status="rejected_by_name_ambiguous",
                cik=None,
                candidate_ciks=[c["cik"] for c in candidates],
            )
            return row

        candidate_cik = candidates[0]["cik"]
        row["candidate_entity_name"] = candidates[0]["name"]

        # --- check 2: date overlap -----------------------------------------
        if store.last_fetched(candidate_cik) != today:
            throttle()
            try:
                document = _sec_get_json(
                    SEC_SUBMISSIONS_URL_TEMPLATE.format(cik=candidate_cik), PEAD_SEC_USER_AGENT
                )
            except Exception as exc:  # noqa: BLE001 -- record and continue
                row.update(status="fetch_failed", cik=candidate_cik, error=str(exc))
                return row
            store.merge_submissions(candidate_cik, document, store_report, first_seen=today)
            store.record_fetch(candidate_cik, on=today)

        _name, _tickers_on_cik, stored_rows = store.read_rows(candidate_cik)
        if not stored_rows:
            row.update(status="rejected_by_date_overlap", cik=candidate_cik, reason="no_stored_filings")
            return row
        filing_dates = [date.fromisoformat(r["filingDate"]) for r in stored_rows]
        earliest, latest = min(filing_dates), max(filing_dates)
        row["cik_earliest_filing"] = earliest.isoformat()
        row["cik_latest_filing"] = latest.isoformat()

        if earliest > last_bar or latest < first_bar:
            row.update(status="rejected_by_date_overlap", cik=candidate_cik)
            return row

        row.update(status="resolved", cik=candidate_cik)
        return row

    with PROGRESS_LOG.open("a") as progress_f:
        for i, ticker in enumerate(tickers, start=1):
            rows.append(resolve_one(ticker))

            if i % LOG_EVERY == 0 or i == len(tickers):
                counts: dict[str, int] = {}
                for r in rows:
                    counts[r["status"]] = counts.get(r["status"], 0) + 1
                line = {
                    "at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                    "i": i,
                    "n": len(tickers),
                    "counts": counts,
                }
                print(f"  {i}/{len(tickers)}: {counts}", flush=True)
                progress_f.write(json.dumps(line) + "\n")
                progress_f.flush()

    fieldnames = [
        "ticker", "first_bar", "last_bar", "name_source", "raw_name", "cleaned_name", "query_used",
        "n_matches", "status", "cik", "candidate_entity_name", "candidate_ciks",
        "cik_earliest_filing", "cik_latest_filing", "reason", "error",
    ]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"written {OUT_CSV.relative_to(_BACKEND)}")

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "n_dead_tickers": len(tickers),
        "n_no_name_in_universe_csv": len(no_name_tickers),
        "n_no_name_recovered_via_ftd_description": len(ftd_names),
        "status_counts": counts,
        "store_report": store_report.describe(),
        "store_n_revisions": len(store_report.revisions),
    }
    OUT_REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"written {OUT_REPORT.relative_to(_BACKEND)}")
    print(f"final counts: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
