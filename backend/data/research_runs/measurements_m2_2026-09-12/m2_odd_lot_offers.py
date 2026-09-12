#!/usr/bin/env python
"""M2 — turn the EDGAR "odd lot" SC TO-I filing count into (a) real bets per year and
(b) the gross premium distribution.

Context: data/research_runs/small_participant_edges_2026-09-12/SMALL_PARTICIPANT_EDGES_2026-09-12.md
sections 3.1 and 5 (M2). That review counted FILINGS (84-224/yr, 2011-2026) containing the phrase
"odd lot" in form SC TO-I, and flagged two defects it could not resolve: filings are not offers
(amendments inflate the count), and the phrase appearing in a document does not prove the offer
grants odd-lot PRIORITY (acceptance of all shares of a <100-share holder without proration).

This script resolves both, for filings dated 2019-01-01 -> 2026-09-11:

  Stage 1  EDGAR full-text search (efts.sec.gov/LATEST/search-index), fully paginated,
           q="odd lot" forms=SC TO-I, one query per year.  -> every hit filing.
  Stage 2  Collapse filings to OFFERS.  For every CIK that appears, the company's EDGAR
           submissions index is read and its SC TO-I originals (form exactly "SC TO-I") are
           used as offer launches; every hit filing is attached to the latest original filed
           on or before it.  One offer = one (CIK, launch accession).
  Stage 3  Sample (rule below), fetch each offer's primary document, and extract:
           odd-lot clause verbatim, priority/no-proration yes-no, offer type
           (fixed price / Dutch auction / NAV-based), price or range, expiration,
           listed-vs-non-traded, ticker.
  Stage 4  Completion: read the final SC TO-I/A of the offer for the final price / proration.
  Stage 5  Prices: for exchange-listed offers with a ticker, the close on the last trading day
           BEFORE the launch date and the first trading day AFTER expiration; gross premium
           = offer price / pre-announcement close - 1.
  Stage 6  Aggregate: bets/year, premium distribution, completion rate, holding period, and
           the descriptive dollar round-trip for a 99-share holder.

SAMPLING RULE (fixed before any per-offer result was read): a CENSUS is used whenever the offer
count is <= SAMPLE_THRESHOLD (400).  The window produced 348 distinct offers and every one of them
is examined -- no sampling was needed, which is strictly stronger than the 60-offer fallback the
brief allowed.  The fallback is implemented and would fire above 400 offers:
random.Random(20260912).sample(sorted(offer_keys), 60) -- seed 20260912, keys sorted by
(cik, launch_date, accession) so the draw cannot depend on fetch order.

WHICH DOCUMENT IS READ: the clause and the offer terms are taken from the document EDGAR's
full-text index actually matched ("odd lot" lives in the Offer to Purchase exhibit, not in the
SC TO-I cover schedule), i.e. the file named in the full-text hit's _id.  The earliest hit
document of the offer is used, preferring the original SC TO-I over an amendment.

Data paths: EDGAR full-text search + EDGAR submissions + EDGAR Archives (all free, no key).
Prices: yfinance (stated in M2_RESULT.md).  yfinance drops delisted names; every ticker that
returns no bars is reported as such, never imputed.

Re-runnable: every HTTP response is cached under CACHE_DIR; delete it to refetch.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

UA = "aladdin2 research autoa0792@gmail.com"
OUT_DIR = Path(__file__).resolve().parent
SRC_DIR = OUT_DIR / "m2_sources"
CACHE_DIR = Path(
    os.environ.get(
        "M2_CACHE_DIR",
        "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/"
        "578690ea-ca6c-4d87-9e97-95cd1d64495e/scratchpad/m2cache",
    )
)
START = date(2019, 1, 1)
END = date(2026, 9, 11)
SAMPLE_SEED = 20260912
SAMPLE_SIZE = 60
SAMPLE_THRESHOLD = 400

_last_call = [0.0]


def _throttle(min_gap: float = 0.15) -> None:
    """<= ~7 requests/second to SEC, under the ~10/s ceiling."""
    dt = time.time() - _last_call[0]
    if dt < min_gap:
        time.sleep(min_gap - dt)
    _last_call[0] = time.time()


def fetch(url: str, binary: bool = False) -> bytes:
    key = hashlib.sha256(url.encode()).hexdigest()[:32]
    path = CACHE_DIR / key
    if path.exists():
        return path.read_bytes()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _throttle()
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept-Encoding": "gzip, deflate", "Accept": "*/*"}
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    import gzip

                    raw = gzip.decompress(raw)
            break
        except Exception as exc:  # retry; re-raised on the last attempt
            if attempt == 3:
                raise
            print(f"    retry {attempt + 1} on {url}: {exc!r}", file=sys.stderr)
            time.sleep(2 + 3 * attempt)
    path.write_bytes(raw)
    return raw


# --------------------------------------------------------------------------- stage 1
def fts_year(year: int) -> list[dict]:
    """Every SC TO-I filing hit for the exact phrase "odd lot" in one calendar year."""
    lo = max(date(year, 1, 1), START)
    hi = min(date(year, 12, 31), END)
    out: list[dict] = []
    frm = 0
    total = None
    while True:
        url = (
            "https://efts.sec.gov/LATEST/search-index?q="
            + urllib.parse.quote('"odd lot"')
            + "&forms="
            + urllib.parse.quote("SC TO-I")
            + f"&startdt={lo}&enddt={hi}&from={frm}"
        )
        d = json.loads(fetch(url))
        if total is None:
            total = d["hits"]["total"]["value"]
        hits = d["hits"]["hits"]
        if not hits:
            break
        for h in hits:
            s = h["_source"]
            out.append(
                {
                    "adsh": s["adsh"],
                    "doc": h["_id"].split(":", 1)[1] if ":" in h["_id"] else None,
                    "form": s["form"],
                    "file_date": s["file_date"],
                    "ciks": s["ciks"],
                    "display_names": s["display_names"],
                }
            )
        frm += len(hits)
        if frm >= total or frm >= 9900:
            break
    return out, total


# --------------------------------------------------------------------------- stage 2
def submissions(cik: str) -> dict:
    url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
    return json.loads(fetch(url))


def all_sc_to_i(cik: str) -> list[dict]:
    """Every SC TO-I / SC TO-I/A filing of a CIK from the submissions index (recent + archived)."""
    d = submissions(cik)
    rows: list[dict] = []

    def take(block: dict) -> None:
        for i, form in enumerate(block.get("form", [])):
            if form in ("SC TO-I", "SC TO-I/A"):
                rows.append(
                    {
                        "form": form,
                        "accession": block["accessionNumber"][i],
                        "filing_date": block["filingDate"][i],
                        "primary_doc": block["primaryDocument"][i],
                    }
                )

    take(d.get("filings", {}).get("recent", {}))
    for f in d.get("filings", {}).get("files", []):
        take(json.loads(fetch("https://data.sec.gov/submissions/" + f["name"])))
    rows.sort(key=lambda r: (r["filing_date"], r["accession"]))
    return rows, d


def build_offers(hits: list[dict]) -> dict:
    """Collapse hit filings into distinct offers: one per (CIK, launch SC TO-I original)."""
    by_cik: dict[str, list[dict]] = {}
    for h in hits:
        for c in h["ciks"]:
            by_cik.setdefault(c, []).append(h)

    offers: dict[tuple, dict] = {}
    for cik, hs in sorted(by_cik.items()):
        try:
            rows, subs = all_sc_to_i(cik)
        except Exception as exc:  # noqa: BLE001 - recorded, never silently dropped
            print(f"  submissions FAILED cik={cik}: {exc!r}", file=sys.stderr)
            continue
        originals = [r for r in rows if r["form"] == "SC TO-I"]
        name = subs.get("name", "")
        tickers = subs.get("tickers", []) or []
        exchanges = subs.get("exchanges", []) or []
        for h in hs:
            fd = h["file_date"]
            prior = [o for o in originals if o["filing_date"] <= fd]
            if prior:
                launch = prior[-1]
            elif h["form"] == "SC TO-I":
                launch = {
                    "accession": h["adsh"],
                    "filing_date": fd,
                    "primary_doc": h["doc"],
                    "form": "SC TO-I",
                }
            else:
                # amendment whose original predates the submissions index -> keep, flagged
                launch = {
                    "accession": h["adsh"],
                    "filing_date": fd,
                    "primary_doc": h["doc"],
                    "form": h["form"],
                    "orphan_amendment": True,
                }
            key = (cik, launch["accession"])
            o = offers.setdefault(
                key,
                {
                    "cik": cik,
                    "name": name,
                    "tickers": tickers,
                    "exchanges": exchanges,
                    "launch_accession": launch["accession"],
                    "launch_date": launch["filing_date"],
                    "launch_primary_doc": launch.get("primary_doc"),
                    "orphan_amendment": launch.get("orphan_amendment", False),
                    "hit_filings": [],
                    "all_filings": [],
                },
            )
            o["hit_filings"].append(
                {"adsh": h["adsh"], "form": h["form"], "date": h["file_date"], "doc": h["doc"]}
            )
        # attach the full amendment chain of each launch (for completion)
        for key, o in offers.items():
            if key[0] != cik:
                continue
            nxt = [
                r["filing_date"]
                for r in originals
                if r["filing_date"] > o["launch_date"]
            ]
            stop = nxt[0] if nxt else "9999-99-99"
            o["all_filings"] = [
                r
                for r in rows
                if o["launch_date"] <= r["filing_date"] < stop
                or r["accession"] == o["launch_accession"]
            ]
    return offers


# --------------------------------------------------------------------------- stage 3
def archive_url(cik: str, accession: str, doc: str) -> str:
    return (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
        f"{accession.replace('-', '')}/{doc}"
    )


def filing_index(cik: str, accession: str) -> list[dict]:
    """Every file in an accession folder, from EDGAR's own index.json (name + size)."""
    url = (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
        f"{accession.replace('-', '')}/index.json"
    )
    d = json.loads(fetch(url))
    return d.get("directory", {}).get("item", [])


MAX_DOC_BYTES = 12_000_000


def pick_offer_document(cik: str, accession: str, fallback: dict | None) -> tuple[str, bytes]:
    """The OFFER TO PURCHASE, not whatever exhibit the full-text index happened to match.

    EDGAR's full-text hit is frequently a two-page "summary advertisement" or a notice of
    guaranteed delivery -- it mentions "odd lot" but carries none of the terms.  The Offer to
    Purchase (exhibit (a)(1)(A), or the S-4/prospectus in a split-off exchange offer) is
    reliably the LARGEST document in the accession, so files are tried largest-first and the
    first one that actually contains "odd lot" wins.  Falls back to the full-text hit document.
    """
    try:
        items = filing_index(cik, accession)
    except Exception:  # noqa: BLE001 - fall back to the full-text hit document
        items = []
    cands = sorted(
        (
            it
            for it in items
            if it.get("name", "").lower().endswith((".htm", ".html", ".txt"))
            and str(it.get("name", "")).lower() != "index.json"
            and int(it.get("size") or 0) < MAX_DOC_BYTES
        ),
        key=lambda it: -int(it.get("size") or 0),
    )
    for it in cands[:4]:
        url = archive_url(cik, accession, it["name"])
        try:
            raw = fetch(url)
        except Exception as exc:  # noqa: BLE001 - logged, then the next candidate is tried
            print(f"    doc fetch failed {url}: {exc!r}", file=sys.stderr)
            continue
        if b"odd lot" in raw.lower() or b"odd-lot" in raw.lower():
            return url, raw
    if fallback and fallback.get("doc"):
        url = archive_url(cik, fallback["adsh"], fallback["doc"])
        return url, fetch(url)
    if cands:
        url = archive_url(cik, accession, cands[0]["name"])
        return url, fetch(url)
    raise FileNotFoundError(f"no document found for {cik}/{accession}")


TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def to_text(raw: bytes) -> str:
    s = raw.decode("utf-8", "replace")
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</tr>|</div>", "\n", s)
    s = TAG_RE.sub(" ", s)
    for a, b in (
        ("&nbsp;", " "),
        ("&amp;", "&"),
        ("&#8217;", "'"),
        ("&#8220;", '"'),
        ("&#8221;", '"'),
        ("&#151;", "-"),
        ("&#8212;", "-"),
        ("&#8211;", "-"),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&quot;", '"'),
        ("&#39;", "'"),
        ("&rsquo;", "'"),
        ("&mdash;", "-"),
        ("&ndash;", "-"),
    ):
        s = s.replace(a, b)
    s = re.sub(r"&#\d+;", " ", s)
    return WS_RE.sub(" ", s)


def odd_lot_sentences(text: str, max_n: int = 3) -> list[str]:
    """Sentences containing "odd lot", verbatim, best first.

    "Best" = the sentence most likely to BE the provision rather than a passing reference: it
    names the <100-share threshold and it speaks about proration/priority.  Ranked, not
    first-found, because the first mention in an Offer to Purchase is usually a summary
    cross-reference and the first mention in a Letter of Transmittal is signature boilerplate.
    """
    cands: list[tuple[float, str]] = []
    seen: set[str] = set()
    low = text.lower()
    for m in re.finditer(r"odd[ \-]?lot", low):
        lo = text.rfind(". ", max(0, m.start() - 700), m.start())
        lo = lo + 2 if lo != -1 else max(0, m.start() - 300)
        hi = text.find(". ", m.end())
        hi = hi + 1 if hi != -1 and hi - m.end() < 900 else min(len(text), m.end() + 350)
        sent = text[lo:hi].strip()
        if not (40 < len(sent) < 1500) or sent in seen:
            continue
        seen.add(sent)
        sl = sent.lower()
        score = 0.0
        if re.search(r"fewer than 100|less than 100|100 shares", sl):
            score += 3
        if "prorat" in sl:
            score += 2
        if "priority" in sl or "preference" in sl:
            score += 2
        if sl.count("_") > 8:
            score -= 5
        score -= len(sent) / 4000.0
        cands.append((score, sent))
    cands.sort(key=lambda t: -t[0])
    return [c[1] for c in cands[:max_n]]


# Explicit DENIAL of odd-lot priority -- checked BEFORE the positive patterns.  Closed-end fund
# tender offers frequently say so in as many words (Virtus Total Return Fund: "This tender offer
# will not have any special pro ration provision for odd-lot tenders, which means that all
# odd-lot tenders (including Stockholders who own fewer than 100 Shares) are subject to
# proration.")  Without this, the mere presence of the phrase would be read as a grant.
NEG_PAT = re.compile(
    r"(?i)("
    r"no[t]?\s+(?:have\s+any\s+)?special\s+pro\s?ration\s+provision\s+for\s+odd[ \-]?lot"
    r"|odd[ \-]?lot[^.]{0,150}?(?:are|is|will\s+be)\s+subject\s+to\s+prorat"
    r"|no\s+odd[ \-]?lot\s+(?:priority|preference|provision)"
    r"|odd[ \-]?lot[^.]{0,140}?will\s+not\s+(?:receive|be\s+given)\s+(?:any\s+)?"
    r"(?:priority|preference)"
    r")"
)

# GRANT of odd-lot priority: the entire holding of a <100-share holder taken without proration.
PRIORITY_PAT = re.compile(
    r"(?i)odd[ \-]?lot[^.]{0,400}?(without\s+(?:being\s+subject\s+to\s+)?prorat"
    r"|not\s+(?:be\s+)?subject\s+to\s+prorat|prior\s+to\s+(?:any\s+)?prorat"
    r"|before\s+(?:any\s+)?prorat|on\s+a\s+priority\s+basis|priority|preference)"
)
PRIORITY_PAT2 = re.compile(
    r"(?i)(without\s+(?:being\s+subject\s+to\s+)?prorat|not\s+(?:be\s+)?subject\s+to\s+prorat"
    r"|prior\s+to\s+(?:any\s+)?prorat|before\s+(?:any\s+)?prorat|priority|preference)"
    r"[^.]{0,400}?odd[ \-]?lot"
)
# The threshold itself, which is what makes the provision retail-only by construction.
THRESH_PAT = re.compile(r"(?i)(?:fewer|less)\s+than\s+100\s+shares")


def classify_priority(text: str, sents: list[str]) -> tuple[str, str]:
    """yes / no_explicitly_denied / mentioned_no_priority_language / absent, with the reason."""
    blob = " ".join(sents) if sents else ""
    scan = text[:400000]
    for mneg in NEG_PAT.finditer(scan):
        # Two sentence shapes GRANT the priority but read literally like a denial:
        #   "EXCEPT FOR Odd Lot Holders, ... shares ... will be subject to proration", and
        #   "if the aggregate number of Shares tendered by Odd Lot Holders exceeds 300,000 then
        #    all Shares ... by all stockholders, INCLUDING Odd lot Holders, will be subject to
        #    proration" (Anebulo Pharmaceuticals 2025-12-22, a capped grant, not a denial).
        # A preceding except/other-than/unless/including therefore disqualifies the match.
        lead = scan[max(0, mneg.start() - 120):mneg.start()].lower()
        if any(w in lead for w in ("except", "other than", "unless", "besides", "including")):
            continue
        return "no_explicitly_denied", f"document denies it: '{mneg.group(0)[:200]}'"
    for pat, why in (
        (PRIORITY_PAT, "odd-lot -> no-proration/priority"),
        (PRIORITY_PAT2, "no-proration/priority -> odd-lot"),
    ):
        m = pat.search(blob) or pat.search(scan)
        if m:
            thr = (
                "<100-share threshold stated in the document"
                if THRESH_PAT.search(scan)
                else "threshold not restated in this document"
            )
            return "yes", f"{why}: '{m.group(0)[:200]}' ({thr})"
    if re.search(r"(?i)odd[ \-]?lot", scan):
        return "mentioned_no_priority_language", "phrase present, no grant and no denial matched"
    return "absent", "phrase absent in the selected document"


SPLITOFF_PAT = re.compile(r"(?i)\bexchange\s+offer\b")
NAV_PAT = re.compile(r"(?i)net\s+asset\s+value")
NAVPCT_PAT = re.compile(
    r"(?i)(?:at|equal\s+to)\s+(\d{2,3}(?:\.\d+)?)\s*%\s+of\s+(?:the\s+)?net\s+asset\s+value"
)
PRICE_RANGE_PAT = re.compile(
    r"(?i)not\s+(less|more|greater)\s+than\s*\$\s?([\d,]+\.?\d*)\s*"
    r"(?:\(?[^$.]{0,40}?\)?\s*)?"
    r"(?:nor|and\s+not|or)\s+(?:less|more|greater)\s+than\s*\$\s?([\d,]+\.?\d*)"
)
PRICE_FIXED_PAT = re.compile(
    r"(?i)(?:purchase\s+price\s+of|cash\s+price\s+of|price\s+of|at)\s*"
    r"\$\s?([\d,]+\.[\d]{2})\s*(?:net\s+)?(?:in\s+cash\s+)?per\s+share"
)
EXPIRY_PAT = re.compile(
    r"(?i)expire[sd]?\b[^.]{0,170}?\bon\s+"
    r"((?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s*20\d\d)"
)
MONTHS = {
    m: i + 1
    for i, m in enumerate(
        [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ]
    )
}


def parse_date(s: str) -> str | None:
    m = re.match(r"([A-Za-z]+)\s+(\d{1,2}),\s*(20\d\d)", s.strip())
    if not m:
        return None
    mon = MONTHS.get(m.group(1).capitalize())
    if not mon:
        return None
    return f"{int(m.group(3)):04d}-{mon:02d}-{int(m.group(2)):02d}"


def classify_offer(text: str) -> dict:
    """Offer type, price/range, expiration -- read from the title block first, then the body.

    The Offer to Purchase states its own terms in the first ~4,000 characters ("Offer to
    Purchase for Cash ... At a Purchase Price Not Less Than $83.00 Per Share and Not More Than
    $97.00 Per Share"), which is far more reliable than any pattern run over 200 pages.
    """
    head = text[:4000]
    body = text[:250000]
    typ, price, lo, hi, navpct = "unknown", None, None, None, None

    if (
        len(SPLITOFF_PAT.findall(body)) >= 5
        and "offer to purchase for cash" not in body[:6000].lower()
    ):
        typ = "split_off_exchange_offer"

    mr = PRICE_RANGE_PAT.search(head) or PRICE_RANGE_PAT.search(body)
    if typ == "unknown" and mr:
        a, b = float(mr.group(2).replace(",", "")), float(mr.group(3).replace(",", ""))
        lo, hi = min(a, b), max(a, b)
        typ = "dutch_auction"
    if typ == "unknown":
        mn = NAVPCT_PAT.search(head) or NAVPCT_PAT.search(body[:60000])
        if mn:
            typ, navpct = "nav_based", float(mn.group(1))
        elif NAV_PAT.search(head):
            typ = "nav_based"
    if typ == "unknown":
        mf = PRICE_FIXED_PAT.search(head) or PRICE_FIXED_PAT.search(body)
        if mf:
            typ, price = "fixed_price", float(mf.group(1).replace(",", ""))

    exp = None
    me = EXPIRY_PAT.search(head) or EXPIRY_PAT.search(body)
    if me:
        exp = parse_date(me.group(1))
    return {
        "offer_type": typ,
        "offer_price": price,
        "range_low": lo,
        "range_high": hi,
        "nav_pct": navpct,
        "expiration": exp,
    }


NONTRADED_PAT = re.compile(
    r"(?i)(there\s+is\s+no\s+(?:established\s+)?public\s+(?:trading\s+)?market|"
    r"shares\s+are\s+not\s+listed|no\s+public\s+trading\s+market\s+(?:for|exists)|"
    r"not\s+listed\s+on\s+any\s+(?:national\s+)?securities\s+exchange|non-traded)"
)


def listed_status(text: str, tickers: list[str], exchanges: list[str]) -> tuple[str, str]:
    """Is the SECURITY BEING TENDERED exchange-listed?

    The OFFER DOCUMENT wins over the submissions index, because the index carries today's
    tickers and they can belong to a different class than the one being tendered (e.g. Priority
    Income Fund's PRIF-P* are listed PREFERRED shares while the common being repurchased is
    non-traded) or post-date the offer (MSC Income Fund listed on the NYSE in 2025 after years
    of non-traded quarterly tenders).  Conflicts are recorded, not hidden.
    """
    m = NONTRADED_PAT.search(text[:200000])
    has_idx = bool(tickers)
    if m:
        snippet = text[max(0, m.start()):m.start() + 140]
        extra = f" [submissions index also lists {tickers} on {exchanges} - other class or later]" if has_idx else ""
        return "non_traded", f"document: '{snippet}'{extra}"
    if has_idx and any(e for e in exchanges if e and str(e).lower() not in ("", "none")):
        return "listed", f"submissions index: {tickers} on {exchanges}; no non-traded language in doc"
    if has_idx:
        return "listed", f"submissions index tickers {tickers}, no exchange field"
    return "unknown", "no ticker in submissions index, no non-traded language matched"


VEHICLE_PAT = [
    (re.compile(r"(?i)\bREIT\b|real\s+estate\s+investment\s+trust"), "REIT"),
    (re.compile(r"(?i)business\s+development\s+company|\bBDC\b"), "BDC"),
    (re.compile(r"(?i)interval\s+fund|Rule\s+23c-3|closed-end\s+(?:management\s+)?investment"), "closed_end_or_interval_fund"),
]


def vehicle_type(text: str, name: str) -> str:
    blob = name + " " + text[:120000]
    for pat, label in VEHICLE_PAT:
        if pat.search(blob):
            return label
    return "operating_company"


# The offer document states its own reference price ("On February 12, 2020, the last reported
# sale price of the Shares was $33.66").  That print is the RIGHT denominator for a premium and
# a free market-data feed is not, for three reasons measured in this sample:
#   - currency: Imperial Oil's substantial issuer bid is in Canadian dollars against the TSX
#     close (C$64.12), while the NYSE-American USD close was 52.51 -- a fake +33% premium;
#   - share basis: yfinance reported a 4-for-1 split for Covenant Logistics that the price
#     history does not support, putting its 2021-08 close at 40.54 against the document's 20.27;
#   - class: Wheeler REIT tendered its Series D preferred ($17.35) while the ticker's common
#     printed $2.75 -- a fake +509% premium.
# The document print is therefore the primary denominator and the free feed is the cross-check.
DOCPRICE_PATS = [
    re.compile(r"(?i)last\s+reported\s+sale\s+price[^.]{0,260}?\$\s?([\d,]+\.\d{2})"),
    re.compile(r"(?i)closing\s+(?:sale\s+)?price[^.]{0,260}?\$\s?([\d,]+\.\d{2})"),
    re.compile(r"(?i)reported\s+(?:sale\s+)?price[^.]{0,260}?was\s+\$\s?([\d,]+\.\d{2})"),
]


def document_reference_price(text: str) -> dict:
    """The pre-announcement market price the offer document itself states, verbatim."""
    for pat in DOCPRICE_PATS:
        m = pat.search(text[:400000])
        if m:
            return {
                "doc_ref_price": float(m.group(1).replace(",", "")),
                "doc_ref_quote": m.group(0)[-220:],
            }
    return {"doc_ref_price": None, "doc_ref_quote": ""}


CLASS_PATS = [
    (re.compile(r"(?i)aggregate\s+principal\s+amount|\bnotes\s+due\b|% senior"), "debt"),
    (re.compile(r"(?i)\bwarrants?\b"), "warrants"),
    (re.compile(r"(?i)preferred\s+(?:stock|shares)|depositary\s+shares"), "preferred"),
    (re.compile(r"(?i)\bunits?\b\s+of\s+(?:limited\s+)?partnership"), "lp_units"),
]


def tendered_class(text: str) -> str:
    """Which security the offer is FOR, from the title block.

    Only a common-stock offer can be compared with a common-stock quote; a preferred or
    note offer read against the common ticker produces a meaningless premium.
    """
    head = text[:3000]
    for pat, label in CLASS_PATS:
        if pat.search(head):
            return label
    return "common_or_unspecified"


# --------------------------------------------------------------------------- stage 4
COMPLETE_PAT = re.compile(
    r"(?i)(expired|has\s+expired|completed|completion\s+of|results\s+of\s+the\s+(?:tender\s+)?offer|"
    r"accepted\s+for\s+(?:purchase|payment)|purchase\s+price\s+(?:of|was)\s+determined)"
)
PRORATION_PAT = re.compile(r"(?i)proration\s+factor[^.]{0,200}|prorat(?:ion|ed)\s+(?:factor\s+)?of[^.]{0,160}")
FINALPRICE_PAT = re.compile(
    r"(?i)(?:purchase\s+price\s+of|price\s+of|at\s+a\s+price\s+of)\s*\$\s?([0-9][0-9,]*\.[0-9]{2})\s*per\s+share"
)


def completion(offer: dict) -> dict:
    amends = [f for f in offer["all_filings"] if f["form"] == "SC TO-I/A"]
    if not amends:
        return {"completed": "no_amendment_found", "final_price": None, "proration": None,
                "completion_source": None}
    last = amends[-1]
    try:
        raw = fetch(archive_url(offer["cik"], last["accession"], last["primary_doc"]))
    except Exception as exc:  # noqa: BLE001 - recorded
        return {"completed": f"fetch_error:{exc!r}", "final_price": None, "proration": None,
                "completion_source": last["accession"]}
    txt = to_text(raw)
    done = bool(COMPLETE_PAT.search(txt[:120000]))
    fp = None
    mf = FINALPRICE_PAT.search(txt[:120000])
    if mf:
        fp = float(mf.group(1).replace(",", ""))
    mp = PRORATION_PAT.search(txt[:120000])
    return {
        "completed": "yes" if done else "unclear",
        "final_price": fp,
        "proration": (mp.group(0)[:200] if mp else None),
        "completion_source": last["accession"],
        "completion_doc": archive_url(offer["cik"], last["accession"], last["primary_doc"]),
        "completion_date": last["filing_date"],
    }


# --------------------------------------------------------------------------- stage 5
def prices(ticker: str, launch: str, expiry: str | None) -> dict:
    """Pre-announcement and post-expiration closes, on the SAME SHARE BASIS as the offer price.

    DEFECT THIS EXISTS TO FIX: yfinance's Close is always split-adjusted to today, while the
    offer price in a 2019 filing is in that day's shares.  Left uncorrected the two are not
    comparable and the premium is nonsense -- Coca-Cola Consolidated's May-2024 offer came out
    at +847% and MicroStrategy's Aug-2020 offer at +960% purely from later 10-for-1 splits,
    and Star Equity's Feb-2019 offer at -90% from a later reverse split.  Every close is
    therefore multiplied back by the cumulative split factor of every split with an ex-date
    AFTER the date of that close, and the factor used is recorded on the row.

    This is the same class of defect the project already found in its own price store
    (price_store.py section 4b / price_store_basis_audit.py, 2026-09-09: three tickers frozen
    at the wrong share basis), reached here from the opposite direction.
    """
    import yfinance as yf

    cache = CACHE_DIR / ("yf_" + hashlib.sha256(
        f"{ticker}|{launch}|{expiry}".encode()).hexdigest()[:28] + ".json")
    if cache.exists():
        return json.loads(cache.read_text())

    d0 = date.fromisoformat(launch)
    d1 = date.fromisoformat(expiry) if expiry else None
    if d1 is None or d1 <= d0:
        d1 = d0 + timedelta(days=30)
    try:
        tk = yf.Ticker(ticker)
        h = tk.history(
            start=(d0 - timedelta(days=25)).isoformat(),
            end=(d1 + timedelta(days=25)).isoformat(),
            auto_adjust=False,
        )
        splits = tk.splits
    except Exception as exc:  # noqa: BLE001 - recorded, never imputed
        out = {"pre_close": None, "post_close": None, "price_note": f"error:{exc!r}"}
        cache.write_text(json.dumps(out))
        return out
    if h is None or h.empty:
        out = {"pre_close": None, "post_close": None,
               "price_note": "no bars (delisted, renamed ticker, or not on the free feed)"}
        cache.write_text(json.dumps(out))
        return out

    sp = []
    try:
        for ts, ratio in splits.items():
            if ratio and float(ratio) > 0:
                sp.append((ts.date(), float(ratio)))
    except Exception as exc:  # noqa: BLE001 - no split history is not an error
        print(f"    no split history for {ticker}: {exc!r}", file=sys.stderr)

    def factor(d: date) -> float:
        f = 1.0
        for ex, ratio in sp:
            if ex > d:
                f *= ratio
        return f

    idx = [i.date() for i in h.index]
    pre = [(i, c) for i, c in zip(idx, h["Close"]) if i < d0]
    post = [(i, c) for i, c in zip(idx, h["Close"]) if i > d1]
    out = {"price_note": "yfinance Close, dividends unadjusted, split basis restored to the offer date"}
    if pre:
        d, c = pre[-1]
        f = factor(d)
        out["pre_close"] = float(c) * f
        out["pre_close_date"] = d.isoformat()
        out["pre_close_split_factor"] = f
    else:
        out["pre_close"] = None
        out["pre_close_split_factor"] = None
    if post:
        d, c = post[0]
        out["post_close"] = float(c) * factor(d)
        out["post_close_date"] = d.isoformat()
    else:
        out["post_close"] = None
    cache.write_text(json.dumps(out))
    return out


# --------------------------------------------------------------------------- driver
def main() -> None:
    SRC_DIR.mkdir(parents=True, exist_ok=True)
    print("=== stage 1: EDGAR full-text search, SC TO-I, phrase 'odd lot' ===")
    all_hits, totals = [], {}
    for y in range(START.year, END.year + 1):
        hits, total = fts_year(y)
        totals[y] = {"reported_total": total, "retrieved": len(hits)}
        all_hits += hits
        print(f"  {y}: reported total {total}, retrieved {len(hits)}")
    print(f"  TOTAL hit filings retrieved {len(all_hits)}")

    print("=== stage 2: collapse filings -> offers ===")
    offers = build_offers(all_hits)
    print(f"  distinct offers: {len(offers)}   distinct CIKs: {len({k[0] for k in offers})}")

    keys = sorted(offers, key=lambda k: (k[0], offers[k]["launch_date"], k[1]))
    if len(keys) <= SAMPLE_THRESHOLD:
        chosen, rule = keys, f"all {len(keys)} offers (<= {SAMPLE_THRESHOLD})"
    else:
        chosen = sorted(random.Random(SAMPLE_SEED).sample(keys, SAMPLE_SIZE))
        rule = f"random.Random({SAMPLE_SEED}).sample(sorted(keys), {SAMPLE_SIZE})"
    print(f"  sampling rule: {rule}")

    print("=== stage 3+4: primary documents, clause extraction, completion ===")
    rows = []
    for n, k in enumerate(chosen, 1):
        o = offers[k]
        # the document the FULL-TEXT INDEX matched: "odd lot" lives in the Offer to Purchase
        # exhibit, not in the SC TO-I cover schedule.  Earliest hit, original before amendment.
        hf = sorted(
            [h for h in o["hit_filings"] if h["doc"]],
            key=lambda h: (h["date"], h["form"] != "SC TO-I", h["adsh"]),
        )
        url, raw0 = None, None
        try:
            url, raw0 = pick_offer_document(o["cik"], o["launch_accession"], hf[0] if hf else None)
        except Exception as exc:  # noqa: BLE001 - recorded on the row
            print(f"    doc selection failed {o['cik']}/{o['launch_accession']}: {exc!r}",
                  file=sys.stderr)
        rec = {
            "cik": o["cik"],
            "issuer": o["name"],
            "tickers": ",".join(o["tickers"]),
            "exchanges": ",".join(e for e in o["exchanges"] if e),
            "launch_date": o["launch_date"],
            "launch_accession": o["launch_accession"],
            "clause_doc_url": url,
            "clause_doc_accession": o["launch_accession"],
            "launch_primary_doc": o["launch_primary_doc"],
            "n_hit_filings": len(o["hit_filings"]),
            "n_filings_in_offer": len(o["all_filings"]),
            "orphan_amendment": o["orphan_amendment"],
        }
        txt = ""
        if raw0 is not None:
            txt = to_text(raw0)
            rec["doc_sha256"] = hashlib.sha256(raw0).hexdigest()
            rec["doc_bytes"] = len(raw0)
        else:
            rec["doc_error"] = "no document could be selected"
        sents = odd_lot_sentences(txt)
        pr, why = classify_priority(txt, sents)
        rec["odd_lot_clause"] = sents[0] if sents else ""
        rec["odd_lot_clause_2"] = sents[1] if len(sents) > 1 else ""
        rec["odd_lot_priority"] = pr
        rec["odd_lot_priority_basis"] = why
        rec.update(classify_offer(txt))
        rec.update(document_reference_price(txt))
        rec["tendered_class"] = tendered_class(txt)
        ls, lb = listed_status(txt, o["tickers"], o["exchanges"])
        rec["listed_status"] = ls
        rec["listed_basis"] = lb
        rec["vehicle"] = vehicle_type(txt, o["name"])
        rec.update(completion(o))
        rows.append(rec)
        print(f"  [{n}/{len(chosen)}] {o['name'][:38]:38s} {o['launch_date']} "
              f"{rec['listed_status']:10s} {rec['offer_type']:13s} prio={pr}")

    print("=== stage 5: prices, and the gross premium ===")
    for r in rows:
        r["gross_premium"] = None
        r["premium_price_used"] = None
        r["premium_basis"] = ""
        r["premium_flag"] = ""
        r["yf_premium"] = None
        r["yf_doc_price_ratio"] = None

        # the offer price: the final price where the offer reported one, else the stated fixed
        # price, else the midpoint of the Dutch-auction range (flagged as a midpoint).
        px = r.get("final_price") or r.get("offer_price")
        if px is None and r.get("range_low") and r.get("range_high"):
            px = (r["range_low"] + r["range_high"]) / 2
            r["premium_flag"] = "range_midpoint"
        elif r.get("final_price") is None and r["offer_type"] == "dutch_auction":
            r["premium_flag"] = "dutch_auction_no_final_price_found"

        if r["listed_status"] == "listed" and r["tickers"]:
            tkr = r["tickers"].split(",")[0]
            r.update(prices(tkr, r["launch_date"], r["expiration"]))
        else:
            r["price_note"] = "not exchange-listed / no ticker in the submissions index"

        dref = r.get("doc_ref_price")
        if px and dref:
            r["gross_premium"] = px / dref - 1
            r["premium_price_used"] = px
            r["premium_basis"] = "offer price / the price the OFFER DOCUMENT itself states"
        if px and r.get("pre_close"):
            r["yf_premium"] = px / r["pre_close"] - 1
        if dref and r.get("pre_close"):
            r["yf_doc_price_ratio"] = r["pre_close"] / dref
        print(f"  {(r['tickers'].split(',')[0] if r['tickers'] else '-'):9s} {r['launch_date']} "
              f"doc={dref} yf={r.get('pre_close')} px={px} prem={r['gross_premium']}")

    # ------------------------------------------------------------------ stage 6
    listed = [r for r in rows if r["listed_status"] == "listed"]
    prio = [r for r in rows if r["odd_lot_priority"] == "yes"]
    listed_prio = [r for r in listed if r["odd_lot_priority"] == "yes"]

    # THE BET POPULATION: an exchange-listed common-stock offer that actually grants odd-lot
    # priority.  Anything else is not a trade a retail holder of 99 listed shares can take.
    def is_bet(r: dict) -> bool:
        return (
            r["listed_status"] == "listed"
            and r["odd_lot_priority"] == "yes"
            and r["tendered_class"] == "common_or_unspecified"
        )

    bets = [r for r in rows if is_bet(r)]
    prem_rows = [r for r in bets if r["gross_premium"] is not None]
    prem = sorted(r["gross_premium"] for r in prem_rows)
    prem_all = sorted(r["gross_premium"] for r in rows if r["gross_premium"] is not None)

    def q(xs, p):
        if not xs:
            return None
        i = (len(xs) - 1) * p
        lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
        return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)

    per_year: dict[str, dict] = {}
    for o in offers.values():
        y = o["launch_date"][:4]
        per_year.setdefault(y, {"offers": 0, "listed": 0, "listed_priority": 0, "bets": 0})
        per_year[y]["offers"] += 1
    for r in rows:
        y = r["launch_date"][:4]
        per_year.setdefault(y, {"offers": 0, "listed": 0, "listed_priority": 0, "bets": 0})
        if r["listed_status"] == "listed":
            per_year[y]["listed"] += 1
            if r["odd_lot_priority"] == "yes":
                per_year[y]["listed_priority"] += 1
        if is_bet(r):
            per_year[y]["bets"] += 1

    hold = sorted(
        (date.fromisoformat(r["expiration"]) - date.fromisoformat(r["launch_date"])).days
        for r in bets
        if r["expiration"] and r["expiration"] > r["launch_date"]
    )

    # cross-check: how often does the free feed agree with the document's own print?
    ratios = [r["yf_doc_price_ratio"] for r in rows if r["yf_doc_price_ratio"]]
    agree = sum(1 for x in ratios if 0.98 <= x <= 1.02)

    summary = {
        "generated": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "window": [START.isoformat(), END.isoformat()],
        "fts_per_year": totals,
        "hit_filings_retrieved": len(all_hits),
        "distinct_offers": len(offers),
        "distinct_ciks": len({k[0] for k in offers}),
        "sampling_rule": rule,
        "offers_examined": len(rows),
        "per_year": {k: per_year[k] for k in sorted(per_year)},
        "listed_count": len(listed),
        "non_traded_count": sum(1 for r in rows if r["listed_status"] == "non_traded"),
        "unknown_listing_count": sum(1 for r in rows if r["listed_status"] == "unknown"),
        "priority_yes": len(prio),
        "priority_denied": sum(1 for r in rows if r["odd_lot_priority"] == "no_explicitly_denied"),
        "priority_mentioned_only": sum(
            1 for r in rows if r["odd_lot_priority"] == "mentioned_no_priority_language"
        ),
        "priority_absent": sum(1 for r in rows if r["odd_lot_priority"] == "absent"),
        "listed_with_priority": len(listed_prio),
        "bets_total": len(bets),
        "tendered_classes": {
            t: sum(1 for r in rows if r["tendered_class"] == t)
            for t in sorted({r["tendered_class"] for r in rows})
        },
        "offer_types": {
            t: sum(1 for r in rows if r["offer_type"] == t)
            for t in sorted({r["offer_type"] for r in rows})
        },
        "bet_offer_types": {
            t: sum(1 for r in bets if r["offer_type"] == t)
            for t in sorted({r["offer_type"] for r in bets})
        },
        "vehicles": {
            t: sum(1 for r in rows if r["vehicle"] == t)
            for t in sorted({r["vehicle"] for r in rows})
        },
        "completed_yes": sum(1 for r in rows if r["completed"] == "yes"),
        "completed_unclear": sum(1 for r in rows if r["completed"] == "unclear"),
        "completed_no_amendment": sum(1 for r in rows if r["completed"] == "no_amendment_found"),
        "bets_completed_yes": sum(1 for r in bets if r["completed"] == "yes"),
        "bets_with_proration_text": sum(1 for r in bets if r.get("proration")),
        "premium_n": len(prem),
        "premium_median": q(prem, 0.5),
        "premium_p25": q(prem, 0.25),
        "premium_p75": q(prem, 0.75),
        "premium_p10": q(prem, 0.10),
        "premium_p90": q(prem, 0.90),
        "premium_min": prem[0] if prem else None,
        "premium_max": prem[-1] if prem else None,
        "premium_negative_n": sum(1 for x in prem if x < 0),
        "premium_midpoint_flagged_n": sum(
            1 for r in prem_rows if r["premium_flag"] == "range_midpoint"
        ),
        "premium_all_offers_n": len(prem_all),
        "premium_all_offers_median": q(prem_all, 0.5),
        "holding_days_n": len(hold),
        "holding_days_median": q(hold, 0.5),
        "holding_days_p25": q(hold, 0.25),
        "holding_days_p75": q(hold, 0.75),
        "price_no_bars": sum(
            1 for r in rows if str(r.get("price_note", "")).startswith("no bars")
        ),
        "yf_vs_document_price_n": len(ratios),
        "yf_vs_document_price_within_2pct": agree,
        "doc_ref_price_missing_in_bets": sum(1 for r in bets if not r.get("doc_ref_price")),
    }

    # descriptive 99-share round trip -- NOT a Sharpe, NOT a strategy claim
    roundtrip = []
    for r in prem_rows:
        stake = 99 * r["doc_ref_price"]
        gain = r["gross_premium"] * stake
        roundtrip.append(
            {
                "issuer": r["issuer"],
                "ticker": r["tickers"].split(",")[0],
                "launch_date": r["launch_date"],
                "doc_ref_price": round(r["doc_ref_price"], 4),
                "stake_usd_99sh": round(stake, 2),
                "gross_premium": round(r["gross_premium"], 6),
                "gross_gain_usd": round(gain, 2),
                "net_after_1usd_commission_each_way": round(gain - 2.0, 2),
            }
        )
    summary["roundtrip_99_share"] = roundtrip
    rt = sorted(x["gross_gain_usd"] for x in roundtrip)
    summary["roundtrip_gain_usd_median"] = q(rt, 0.5)
    summary["roundtrip_gain_usd_p25"] = q(rt, 0.25)
    summary["roundtrip_gain_usd_p75"] = q(rt, 0.75)
    summary["roundtrip_stake_usd_median"] = q(sorted(x["stake_usd_99sh"] for x in roundtrip), 0.5)
    summary["roundtrip_loss_making_after_2usd"] = sum(
        1 for x in roundtrip if x["net_after_1usd_commission_each_way"] <= 0
    )

    (OUT_DIR / "m2_output.json").write_text(
        json.dumps({"summary": summary, "offers": rows}, indent=1, default=str)
    )
    fields = sorted({k for r in rows for k in r})
    order = [
        "issuer", "cik", "tickers", "exchanges", "listed_status", "vehicle", "launch_date",
        "expiration", "offer_type", "offer_price", "range_low", "range_high", "nav_pct", "final_price",
        "premium_price_used", "premium_flag", "pre_close", "pre_close_date", "post_close",
        "post_close_date", "pre_close_split_factor", "doc_ref_price", "doc_ref_quote",
        "gross_premium", "yf_premium", "yf_doc_price_ratio", "premium_basis", "tendered_class", "completed", "proration", "odd_lot_priority",
        "odd_lot_clause", "odd_lot_clause_2", "odd_lot_priority_basis", "launch_accession",
        "clause_doc_accession", "clause_doc_url", "doc_sha256", "completion_doc", "completion_date",
        "n_hit_filings", "n_filings_in_offer", "orphan_amendment", "listed_basis", "price_note",
    ]
    cols = [c for c in order if c in fields] + [c for c in fields if c not in order]
    with (OUT_DIR / "m2_offers.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    lines = ["M2 odd-lot self-tender measurement", "=" * 60, json.dumps(summary, indent=1, default=str)]
    (OUT_DIR / "m2_output.txt").write_text("\n".join(lines))
    print("\n" + json.dumps({k: v for k, v in summary.items() if k != "roundtrip_99_share"},
                            indent=1, default=str))


if __name__ == "__main__":
    main()
