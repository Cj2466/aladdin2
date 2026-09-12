"""Step A4 correction sub-task -- PROBE (not build) whether a delisted ticker
in the whole-market price panel can be resolved to a CIK by any free route.

SEC's company_tickers.json (used by build_universe_ciks.py) only lists
companies with a CURRENT ticker: measured here, it resolves 5 of the panel's
1,817 delisted tickers (0.28%) -- confirmed below by cross-referencing
universe_ciks.csv (7,143 symbols resolved) against the panel's own
`status == inactive` column. Building the announcement-date table from that
mapping alone would silently make it survivor-only, which is exactly the
bias this whole step exists to remove. This script tests three candidate
free routes on a fixed 20-ticker sample of known-dead names before any full
run is attempted (per the orchestrator's correction -- probe, then report,
then wait for a go/no-go before spending hours on a full ingest).

    ./venv/bin/python data/research_runs/edgar_submissions_wholemarket_2026-09-12/probe_delisted_cik_resolution.py

Sample (20, deterministic): the 7 tickers named in the correction message
(ACIA, CLDR, FIT, ZNGA, AABA, ALOG, ARMO) plus the next 13 delisted,
not-SEC-resolved symbols in universe.csv sorted alphabetically by symbol
that were not already in that list of 7 (AACQU, ABDC, ACACU, ACAMU, ACBI,
ACC, ACGLP, ACKIT, ACKIU, ACLL, ACTCU, ACTDU, ACTTU).

Routes tested:
  (1) SEC browse-edgar company NAME search (getcompany&company=<name>),
      output=atom -- covers every CIK EVER registered, not just current
      tickers, keyed by company name substring match. Uses universe.csv's
      own `name` column (Alpaca's asset name), cleaned of share-class /
      security-type suffix noise ("Common Stock", "Class A", "Units", ...).
      Three of the 20 sample tickers (AABA, ALOG, ARMO) have an EMPTY name
      in universe.csv -- this route cannot even be attempted for them from
      data this project already holds, and that gap is reported as such,
      not papered over with an externally-recalled name.
  (2) EDGAR full text search (efts.sec.gov/LATEST/search-index?q=<ticker>)
      -- searches filing TEXT for the literal ticker string, 2001-present
      coverage only. A hit is a candidate CIK, not a resolution: the ticker
      string can appear in an unrelated filing (someone else's 8-K
      discussing the company, a index fund's holdings list, etc.), so this
      route's match is graded on whether the returned CIK's display name
      plausibly matches the company, not accepted blindly.
  (3) The submissions store's own rows for CIKs we already hold: do stored
      documents carry `tickers` or a former-name history that would help?
      Checked by inspecting a few stored payloads' `tickers` field, which
      the store type already exposes (see edgar_submissions_store.py
      rebuild_submissions / read_rows).

The quarterly full-index files (company.idx, one per quarter since 1993/1994)
are NOT fetched here -- estimating their cost analytically instead (see the
report's `full_index_cost_estimate`), because a name-substring match against
44+ quarters x thousands of companies each is a much larger free-text
matching problem than the other two routes and should only be built if (1)
and (2) together leave a large uncovered remainder.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

_BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND))

from app.services.market_data.edgar_submissions_store import EdgarSubmissionsStore
from app.services.research_lab.cross_sectional_pead import PEAD_SEC_USER_AGENT

HERE = Path(__file__).resolve().parent
UNIVERSE_CSV = _BACKEND / "data" / "research_runs" / "whole_market_panel_2026-09-12" / "universe.csv"
UNIVERSE_CIKS_CSV = HERE / "universe_ciks.csv"
OUT_REPORT = HERE / "delisted_cik_resolution_probe_report.json"

MIN_REQUEST_INTERVAL = 0.3  # more conservative than the 0.15s project default: the whole-market
# submissions ingest (ingest_wholemarket.py) is running concurrently in the background against the
# same SEC fair-access budget, so this probe halves its own rate rather than risk pushing the
# combined request rate over the published 10 req/s cap

GIVEN_SAMPLE = ["ACIA", "CLDR", "FIT", "ZNGA", "AABA", "ALOG", "ARMO"]

# Security-type / share-class suffix noise Alpaca appends to `name`; stripped
# before a company-name search so "Cloudera, Inc." rather than "Cloudera,
# Inc. Common Stock" is what gets searched. Order matters (longest/most
# specific first) -- this is pattern matching on Alpaca's OWN vocabulary,
# observed directly in universe.csv, not a general NLP cleaner.
_SUFFIX_PATTERNS = [
    # Preferred/debt instrument descriptions ("11% Series B Cumulative
    # Convertible Preferred Stock") -- added 2026-09-12 for the delisted-name
    # gate, whose dead-ticker population includes far more preferred/debt
    # securities than the original 20-ticker probe sample did. Stripping
    # from the first percentage sign onward removes the whole rate/series
    # clause in one shot, leaving just the issuer name.
    r",?\s*\d+(\.\d+)?%.*$",
    r",?\s*Class [A-Z] [Cc]ommon [Ss]tock.*$",
    r",?\s*Class [A-Z] [Oo]rdinary [Ss]hares.*$",
    r",?\s*[Cc]ommon [Ss]tock.*$",
    r",?\s*Ordinary Shares.*$",
    r",?\s*American Depositary Shares.*$",
    r",?\s*Depositary Shares.*$",
    r",?\s*Preferred Stock.*$",
    r",?\s*Subunits?$",
    r",?\s*Units?$",
    r",?\s*Warrants?$",
    r",?\s*Rights?$",
    r",?\s*Notes.*$",
    r",?\s*Debentures.*$",
]


# Corporate-suffix tokens that, left ON the query, were measured live
# 2026-09-12 to sometimes SUPPRESS an otherwise-good match (e.g. "Artius
# Acquisition Inc" -> 0 matches, "Artius Acquisition" -> 1; "American Campus
# Communities, Inc." -> 0, "American Campus Communities" -> 2). browse-edgar's
# company= search is evidently not a plain prefix match -- it behaves
# inconsistently with a trailing corporate-form word present ("Zynga Inc" DID
# match, "Artius Acquisition Inc" did NOT), so this is used only as a
# fallback query tried when the first (corp-suffix-retained) query returns
# zero matches, not as a replacement for it.
_CORP_SUFFIX_WORDS_RE = re.compile(
    r",?\s+(Inc|Incorporated|Corp|Corporation|Ltd|Limited|Co|LLC|L\.L\.C|LP|L\.P)\.?$",
    re.IGNORECASE,
)


def strip_corp_suffix(name: str) -> str:
    prev = None
    while prev != name:
        prev = name
        name = _CORP_SUFFIX_WORDS_RE.sub("", name).strip()
    return name


def clean_name(raw: str) -> str:
    name = raw.strip()
    for pat in _SUFFIX_PATTERNS:
        name = re.sub(pat, "", name, flags=re.IGNORECASE).strip()
    # browse-edgar's company= search appears to prefix-match against SEC's
    # own conformed name, which is written WITHOUT trailing punctuation
    # ("ZYNGA INC", not "ZYNGA INC."). Measured live 2026-09-12: "Zynga
    # Inc." (Alpaca's own name, period included) returns 0 matches; "Zynga
    # Inc" (period stripped) returns 1 -- exact hit. Same effect confirmed
    # for "Artius Acquisition Inc." (0 -> 1) and "American Campus
    # Communities, Inc." (0 -> 2). Stripping a trailing period is therefore
    # load-bearing for this route, not cosmetic.
    name = name.rstrip(".").strip()
    return name


def _get(url: str, *, timeout: int = 20) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": PEAD_SEC_USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b""


def route_browse_edgar_company_name(name: str) -> dict:
    """(1) https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=<name>&output=atom"""
    if not name:
        return {"attempted": False, "reason": "no name available in universe.csv"}
    url = (
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
        f"&company={urllib.parse.quote(name)}&output=atom&count=10"
    )
    status, body = _get(url)
    if status != 200 or not body:
        return {"attempted": True, "http_status": status, "n_matches": 0, "ciks": []}
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return {"attempted": True, "http_status": status, "n_matches": 0, "ciks": [], "parse_error": True}
    ns = {"a": "http://www.w3.org/2005/Atom"}
    matches = []
    # SEC serves either a single <company-info> (exact/unique match) or a
    # list of <entry> rows (ambiguous). Handle both shapes.
    single = root.find("a:company-info", ns)
    if single is not None:
        cik_el = single.find("a:cik", ns)
        name_el = single.find("a:conformed-name", ns)
        if cik_el is not None:
            matches.append({"cik": int(cik_el.text), "name": name_el.text if name_el is not None else ""})
    for entry in root.findall("a:entry", ns):
        content = entry.find("a:content", ns)
        if content is None:
            continue
        ci = content.find("a:company-info", ns)
        if ci is None:
            continue
        cik_el = ci.find("a:cik", ns)
        name_el = ci.find("a:conformed-name", ns)
        if cik_el is not None:
            matches.append({"cik": int(cik_el.text), "name": name_el.text if name_el is not None else ""})
    return {"attempted": True, "http_status": status, "n_matches": len(matches), "ciks": matches}


def route_full_text_search(ticker: str) -> dict:
    """(2) https://efts.sec.gov/LATEST/search-index?q=%22TICKER%22 -- filing
    TEXT search, 2001-present. Returns candidate CIKs graded, not accepted
    blindly (see module docstring)."""
    url = f"https://efts.sec.gov/LATEST/search-index?q=%22{urllib.parse.quote(ticker)}%22"
    status, body = _get(url)
    if status != 200 or not body:
        return {"attempted": True, "http_status": status, "n_hits": 0, "top_ciks": []}
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {"attempted": True, "http_status": status, "n_hits": 0, "top_ciks": [], "parse_error": True}
    hits = payload.get("hits", {}).get("hits", [])
    total = payload.get("hits", {}).get("total", {}).get("value", 0)
    top: dict[str, dict] = {}
    for h in hits:
        src = h.get("_source", {})
        ciks = src.get("ciks", [])
        names = src.get("display_names", [])
        # ciks[i] and display_names[i] are INDEX-ALIGNED (verified live
        # 2026-09-12 against a raw efts.sec.gov response for a multi-filer
        # hit) -- zipping them, rather than the earlier draft's "attach
        # every name in this hit to every cik in this hit", is load-bearing:
        # the earlier version cross-contaminated unrelated co-filers' names
        # onto the target CIK's entry.
        for cik, name in zip(ciks, names, strict=False):
            top.setdefault(cik, {"cik": cik, "display_names": set(), "n_hits": 0})
            top[cik]["display_names"].add(name)
            top[cik]["n_hits"] += 1
    top_list = sorted(top.values(), key=lambda r: -r["n_hits"])[:5]
    for r in top_list:
        r["display_names"] = sorted(r["display_names"])
    return {"attempted": True, "http_status": status, "n_hits_total": total, "top_ciks": top_list}


def route_store_ticker_history(sample: list[str]) -> dict:
    """(3) Do any submissions rows we already hold carry a delisted ticker in
    their `tickers` field (a former/secondary ticker on a CIK we already
    store)? Checked against the 6,038-CIK whole-market universe already
    ingested, not a full store scan (the store's own CIK files are keyed by
    CIK, not by ticker, so this is a linear scan -- cheap at 6,038 files)."""
    store = EdgarSubmissionsStore()
    hits: dict[str, list[int]] = {t: [] for t in sample}
    n_scanned = 0
    if store.store_dir is not None and store.store_dir.exists():
        with UNIVERSE_CIKS_CSV.open() as f:
            ciks = sorted({int(r["cik"]) for r in csv.DictReader(f)})
        for cik in ciks:
            _name, tickers, _rows = store.read_rows(cik)
            n_scanned += 1
            for t in tickers:
                if t in hits:
                    hits[t].append(cik)
    return {"n_ciks_scanned": n_scanned, "hits": {t: v for t, v in hits.items() if v}}


def build_sample() -> list[str]:
    with UNIVERSE_CSV.open() as f:
        rows = list(csv.DictReader(f))
    cands = sorted(
        (r["symbol"] for r in rows if r["status"] == "inactive" and r["in_sec_company_tickers"] == "False"),
    )
    extra = [s for s in cands if s not in GIVEN_SAMPLE][:13]
    return GIVEN_SAMPLE + extra


def main() -> int:
    with UNIVERSE_CSV.open() as f:
        rows = {r["symbol"]: r for r in csv.DictReader(f)}

    n_inactive = sum(1 for r in rows.values() if r["status"] == "inactive")
    n_inactive_resolved_by_company_tickers = sum(
        1 for r in rows.values() if r["status"] == "inactive" and r["in_sec_company_tickers"] == "True"
    )
    print(f"panel: {n_inactive} inactive/delisted symbols; "
          f"{n_inactive_resolved_by_company_tickers} of those already resolve via company_tickers.json")

    sample = build_sample()
    print(f"sample ({len(sample)}): {sample}")

    last_request = 0.0

    def throttle() -> None:
        nonlocal last_request
        elapsed = time.monotonic() - last_request
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        last_request = time.monotonic()

    per_ticker: dict[str, dict] = {}
    for t in sample:
        raw_name = rows.get(t, {}).get("name", "")
        cleaned = clean_name(raw_name)
        throttle()
        r1 = route_browse_edgar_company_name(cleaned)
        r1_fallback = None
        fallback_name = strip_corp_suffix(cleaned) if cleaned else ""
        if r1.get("attempted") and r1.get("n_matches") != 1 and fallback_name and fallback_name != cleaned:
            throttle()
            r1_fallback = route_browse_edgar_company_name(fallback_name)
        throttle()
        r2 = route_full_text_search(t)
        per_ticker[t] = {
            "raw_name": raw_name,
            "cleaned_name": cleaned,
            "browse_edgar_company_name": r1,
            "fallback_name_corp_suffix_stripped": fallback_name if r1_fallback else None,
            "browse_edgar_company_name_fallback": r1_fallback,
            "full_text_search": r2,
        }
        print(f"  {t}: name-search={r1.get('n_matches', 'n/a')} matches "
              f"(fallback={r1_fallback.get('n_matches') if r1_fallback else 'n/a'}), "
              f"full-text={r2.get('n_hits_total', 'n/a')} hits, "
              f"top={r2.get('top_ciks', [None])[:1]}")

    r3 = route_store_ticker_history(sample)
    print(f"route 3 (store ticker history): scanned {r3['n_ciks_scanned']} CIKs, hits={r3['hits']}")

    # Grading: route 1 counts as a resolved match only when it returned
    # EXACTLY ONE candidate CIK (an ambiguous multi-hit result is not a
    # resolution without a human/deterministic tiebreak this probe does not
    # attempt). Route 2 counts as a resolved match only when the top CIK's
    # hit count clearly dominates (>= 3x the second place, or it is the only
    # CIK returned) AND at least one display name is a plausible substring
    # match against the ticker's raw universe.csv name -- both checked by
    # hand below and recorded, not auto-accepted.
    def resolved_1to1(t: str) -> bool:
        r1 = per_ticker[t]["browse_edgar_company_name"]
        if r1.get("n_matches") == 1:
            return True
        fb = per_ticker[t]["browse_edgar_company_name_fallback"]
        return bool(fb and fb.get("n_matches") == 1)

    route1_resolved = sum(1 for t in sample if resolved_1to1(t))
    route1_resolved_without_fallback = sum(
        1 for t in sample if per_ticker[t]["browse_edgar_company_name"].get("n_matches") == 1
    )
    route1_attempted = sum(
        1 for t in sample if per_ticker[t]["browse_edgar_company_name"].get("attempted")
    )
    route1_no_name = sum(
        1 for t in sample if not per_ticker[t]["browse_edgar_company_name"].get("attempted", True)
    )
    route1_still_ambiguous_or_zero = [
        t for t in sample
        if per_ticker[t]["browse_edgar_company_name"].get("attempted") and not resolved_1to1(t)
    ]

    full_index_cost_estimate = {
        "endpoint": "https://www.sec.gov/Archives/edgar/full-index/<year>/QTR<n>/company.idx",
        "quarters_needed_for_full_history": "~132 (1993 Q1 .. 2026 Q3, one file per quarter)",
        "bytes_per_file_estimate": "several MB each (thousands of filer rows per quarter, not measured here)",
        "requests_for_full_history": 132,
        "note": (
            "Not fetched in this probe. Each file lists company NAME -> CIK for every filer active "
            "that quarter, so resolving a delisted ticker requires matching universe.csv's `name` "
            "against every quarter the company could plausibly have filed in (unknown a priori without "
            "the delisting date), i.e. an unbounded name-fuzzy-match problem across ~132 files rather "
            "than one lookup per ticker like routes (1) and (2). Only worth building if (1)+(2) leave a "
            "large uncovered remainder -- recommend measuring that first."
        ),
    }

    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "context": {
            "n_inactive_symbols_in_panel": n_inactive,
            "n_inactive_resolved_by_company_tickers_json": n_inactive_resolved_by_company_tickers,
            "company_tickers_json_delisted_coverage_pct": round(
                100 * n_inactive_resolved_by_company_tickers / n_inactive, 2
            ) if n_inactive else None,
        },
        "sample": sample,
        "per_ticker": per_ticker,
        "route_store_ticker_history": r3,
        "route1_summary": {
            "attempted": route1_attempted,
            "no_name_available": route1_no_name,
            "resolved_exactly_one_match_first_query_only": route1_resolved_without_fallback,
            "resolved_exactly_one_match_with_corp_suffix_fallback": route1_resolved,
            "resolution_rate_with_fallback": round(route1_resolved / route1_attempted, 3) if route1_attempted else None,
            "still_ambiguous_or_zero_after_fallback": route1_still_ambiguous_or_zero,
        },
        "full_index_cost_estimate": full_index_cost_estimate,
    }
    OUT_REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"written {OUT_REPORT.relative_to(_BACKEND)}")
    print(f"route1 (browse-edgar company name): {route1_resolved}/{route1_attempted} attempted resolved "
          f"1:1 with fallback ({route1_resolved_without_fallback} without it), "
          f"{route1_no_name} had no name to try")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
