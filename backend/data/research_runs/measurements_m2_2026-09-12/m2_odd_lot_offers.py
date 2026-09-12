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
from datetime import date, datetime, timedelta
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
        except Exception as exc:  # noqa: BLE001 - network retry, failure is re-raised below
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


SENT_SPLIT = re.compile(r"(?<=[.;:])\s+(?=[A-Z(\"])")


def odd_lot_sentences(text: str, max_n: int = 4) -> list[str]:
    """Sentences containing 'odd lot' (case-insensitive), verbatim."""
    out = []
    low = text.lower()
    for m in re.finditer(r"odd[ \-]?lot", low):
        lo = text.rfind(". ", max(0, m.start() - 900), m.start())
        lo = lo + 2 if lo != -1 else max(0, m.start() - 400)
        hi = text.find(". ", m.end())
        hi = hi + 1 if hi != -1 and hi - m.end() < 900 else min(len(text), m.end() + 400)
        s = text[lo:hi].strip()
        if 40 < len(s) < 1400 and s not in out:
            out.append(s)
        if len(out) >= max_n:
            break
    return out


PRIORITY_PAT = re.compile(
    r"(?i)odd[ \-]?lot[^.]{0,400}?(without\s+proration|not\s+be\s+subject\s+to\s+proration|"
    r"prior\s+to\s+proration|before\s+any\s+proration|on\s+a\s+priority\s+basis|priority\s+over|"
    r"purchase[ds]?\s+(?:all|first)|accept(?:ed|s|ance)?\s+(?:of\s+)?all)"
)
PRIORITY_PAT2 = re.compile(
    r"(?i)(without\s+proration|not\s+subject\s+to\s+proration|prior\s+to\s+(?:any\s+)?proration|"
    r"before\s+(?:any\s+)?proration|priority)[^.]{0,400}?odd[ \-]?lot"
)


def classify_priority(sents: list[str]) -> tuple[str, str]:
    blob = " ".join(sents)
    if PRIORITY_PAT.search(blob) or PRIORITY_PAT2.search(blob):
        return "yes", "explicit no-proration / priority language next to 'odd lot'"
    if re.search(r"(?i)odd[ \-]?lot", blob):
        return "mentioned_no_priority_language", "phrase present, no priority clause matched"
    return "no", "phrase absent in extracted text"


DUTCH_PAT = re.compile(r"(?i)(modified\s+)?dutch\s+auction|price\s+range\s+of\s+not\s+(less|greater)")
NAV_PAT = re.compile(r"(?i)net\s+asset\s+value|%\s+of\s+(the\s+)?NAV|NAV\s+per\s+share")
PRICE_RANGE_PAT = re.compile(
    r"(?i)(?:not\s+(?:less|greater)\s+than|between)\s*\$\s?([0-9][0-9,]*\.?[0-9]*)\s*"
    r"(?:nor|and|to|or\s+more\s+than|and\s+not\s+(?:greater|more)\s+than)\s*\$\s?([0-9][0-9,]*\.?[0-9]*)"
)
PRICE_FIXED_PAT = re.compile(
    r"(?i)(?:purchase\s+price\s+of|price\s+of|at\s+a\s+price\s+of|cash\s+purchase\s+price\s+of)"
    r"\s*\$\s?([0-9][0-9,]*\.[0-9]{2})\s*(?:per\s+share|net\s+per\s+share|in\s+cash\s+per\s+share)"
)
EXPIRY_PAT = re.compile(
    r"(?i)(?:expire[sd]?|expiration\s+(?:date|time)[^.]{0,80}?)\s*(?:at|on|is)?[^.]{0,60}?"
    r"((?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s*20\d\d)"
)
MONTHS = {
    m: i + 1
    for i, m in enumerate(
        "January February March April May June July August September October November December".split()
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
    head = text[:200000]
    typ, price, lo, hi = "unknown", None, None, None
    mr = PRICE_RANGE_PAT.search(head)
    if DUTCH_PAT.search(head) and mr:
        typ = "dutch_auction"
        lo, hi = float(mr.group(1).replace(",", "")), float(mr.group(2).replace(",", ""))
    elif DUTCH_PAT.search(head):
        typ = "dutch_auction"
    mf = PRICE_FIXED_PAT.search(head)
    if typ == "unknown" and mf:
        typ, price = "fixed_price", float(mf.group(1).replace(",", ""))
    elif typ == "unknown" and NAV_PAT.search(head[:60000]):
        typ = "nav_based"
    if typ == "dutch_auction" and lo is None and mf:
        price = float(mf.group(1).replace(",", ""))
    if typ == "fixed_price" and NAV_PAT.search(head[:20000]) and price is None:
        typ = "nav_based"
    exp = None
    me = EXPIRY_PAT.search(head)
    if me:
        exp = parse_date(me.group(1))
    return {
        "offer_type": typ,
        "offer_price": price,
        "range_low": lo,
        "range_high": hi,
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
    if has_idx and any(e for e in exchanges if e and e.lower() not in ("", "none")):
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
    import yfinance as yf

    d0 = datetime.strptime(launch, "%Y-%m-%d").date()
    d1 = datetime.strptime(expiry, "%Y-%m-%d").date() if expiry else d0 + timedelta(days=30)
    try:
        h = yf.Ticker(ticker).history(
            start=(d0 - timedelta(days=20)).isoformat(),
            end=(d1 + timedelta(days=20)).isoformat(),
            auto_adjust=False,
        )
    except Exception as exc:  # noqa: BLE001 - recorded, never imputed
        return {"pre_close": None, "post_close": None, "price_note": f"error:{exc!r}"}
    if h is None or h.empty:
        return {"pre_close": None, "post_close": None, "price_note": "no bars (delisted or no feed)"}
    idx = [i.date() for i in h.index]
    pre = [(i, c) for i, c in zip(idx, h["Close"]) if i < d0]
    post = [(i, c) for i, c in zip(idx, h["Close"]) if i > d1]
    return {
        "pre_close": float(pre[-1][1]) if pre else None,
        "pre_close_date": pre[-1][0].isoformat() if pre else None,
        "post_close": float(post[0][1]) if post else None,
        "post_close_date": post[0][0].isoformat() if post else None,
        "price_note": "yfinance unadjusted close",
    }


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
        if hf:
            src = hf[0]
            url = archive_url(o["cik"], src["adsh"], src["doc"])
        else:
            src = {"adsh": o["launch_accession"], "doc": o["launch_primary_doc"]}
            url = archive_url(o["cik"], src["adsh"], src["doc"]) if src["doc"] else None
        rec = {
            "cik": o["cik"],
            "issuer": o["name"],
            "tickers": ",".join(o["tickers"]),
            "exchanges": ",".join(o["exchanges"]),
            "launch_date": o["launch_date"],
            "launch_accession": o["launch_accession"],
            "clause_doc_url": url,
            "clause_doc_accession": src["adsh"],
            "launch_primary_doc": o["launch_primary_doc"],
            "n_hit_filings": len(o["hit_filings"]),
            "n_filings_in_offer": len(o["all_filings"]),
            "orphan_amendment": o["orphan_amendment"],
        }
        txt = ""
        if url:
            try:
                raw = fetch(url)
                txt = to_text(raw)
                rec["doc_sha256"] = hashlib.sha256(raw).hexdigest()
                rec["doc_bytes"] = len(raw)
            except Exception as exc:  # noqa: BLE001 - recorded
                rec["doc_error"] = repr(exc)
        sents = odd_lot_sentences(txt)
        pr, why = classify_priority(sents)
        rec["odd_lot_clause"] = sents[0] if sents else ""
        rec["odd_lot_clause_2"] = sents[1] if len(sents) > 1 else ""
        rec["odd_lot_priority"] = pr
        rec["odd_lot_priority_basis"] = why
        rec.update(classify_offer(txt))
        ls, lb = listed_status(txt, o["tickers"], o["exchanges"])
        rec["listed_status"] = ls
        rec["listed_basis"] = lb
        rec["vehicle"] = vehicle_type(txt, o["name"])
        rec.update(completion(o))
        rows.append(rec)
        print(f"  [{n}/{len(chosen)}] {o['name'][:38]:38s} {o['launch_date']} "
              f"{rec['listed_status']:10s} {rec['offer_type']:13s} prio={pr}")

    print("=== stage 5: prices for listed issuers ===")
    for r in rows:
        r["gross_premium"] = None
        r["premium_price_used"] = None
        r["premium_flag"] = ""
        if r["listed_status"] != "listed" or not r["tickers"]:
            r["price_note"] = "not listed / no ticker"
            continue
        tkr = r["tickers"].split(",")[0]
        p = prices(tkr, r["launch_date"], r["expiration"])
        r.update(p)
        px = r.get("final_price") or r.get("offer_price")
        if px is None and r.get("range_low") and r.get("range_high"):
            px = (r["range_low"] + r["range_high"]) / 2
            r["premium_flag"] = "range_midpoint"
        elif r.get("final_price") is None and r["offer_type"] == "dutch_auction":
            r["premium_flag"] = "dutch_no_final_price"
        if px and p.get("pre_close"):
            r["gross_premium"] = px / p["pre_close"] - 1
            r["premium_price_used"] = px
        print(f"  {tkr:8s} {r['launch_date']} pre={p.get('pre_close')} "
              f"px={px} prem={r['gross_premium']}")

    # ------------------------------------------------------------------ stage 6
    listed = [r for r in rows if r["listed_status"] == "listed"]
    prio = [r for r in rows if r["odd_lot_priority"] == "yes"]
    listed_prio = [r for r in listed if r["odd_lot_priority"] == "yes"]
    prem = sorted(r["gross_premium"] for r in rows if r["gross_premium"] is not None)

    def q(xs, p):
        if not xs:
            return None
        i = (len(xs) - 1) * p
        lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
        return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)

    per_year: dict[str, dict] = {}
    for k, o in offers.items():
        y = o["launch_date"][:4]
        per_year.setdefault(y, {"offers": 0, "listed": 0, "listed_priority": 0})
        per_year[y]["offers"] += 1
    for r in rows:
        y = r["launch_date"][:4]
        per_year.setdefault(y, {"offers": 0, "listed": 0, "listed_priority": 0})
        if r["listed_status"] == "listed":
            per_year[y]["listed"] += 1
        if r["listed_status"] == "listed" and r["odd_lot_priority"] == "yes":
            per_year[y]["listed_priority"] += 1

    hold = [
        (datetime.strptime(r["expiration"], "%Y-%m-%d")
         - datetime.strptime(r["launch_date"], "%Y-%m-%d")).days
        for r in rows
        if r["expiration"] and r["expiration"] > r["launch_date"]
    ]
    hold.sort()

    summary = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "window": [START.isoformat(), END.isoformat()],
        "fts_per_year": totals,
        "hit_filings_retrieved": len(all_hits),
        "distinct_offers": len(offers),
        "distinct_ciks": len({k[0] for k in offers}),
        "sampling_rule": rule,
        "offers_examined": len(rows),
        "per_year": per_year,
        "listed_count": len(listed),
        "non_traded_count": sum(1 for r in rows if r["listed_status"] == "non_traded"),
        "unknown_listing_count": sum(1 for r in rows if r["listed_status"] == "unknown"),
        "priority_yes": len(prio),
        "priority_mentioned_only": sum(
            1 for r in rows if r["odd_lot_priority"] == "mentioned_no_priority_language"
        ),
        "priority_absent": sum(1 for r in rows if r["odd_lot_priority"] == "no"),
        "listed_with_priority": len(listed_prio),
        "offer_types": {
            t: sum(1 for r in rows if r["offer_type"] == t)
            for t in sorted({r["offer_type"] for r in rows})
        },
        "vehicles": {
            t: sum(1 for r in rows if r["vehicle"] == t)
            for t in sorted({r["vehicle"] for r in rows})
        },
        "completed_yes": sum(1 for r in rows if r["completed"] == "yes"),
        "completed_unclear": sum(1 for r in rows if r["completed"] == "unclear"),
        "completed_no_amendment": sum(1 for r in rows if r["completed"] == "no_amendment_found"),
        "premium_n": len(prem),
        "premium_median": q(prem, 0.5),
        "premium_p25": q(prem, 0.25),
        "premium_p75": q(prem, 0.75),
        "premium_min": prem[0] if prem else None,
        "premium_max": prem[-1] if prem else None,
        "holding_days_n": len(hold),
        "holding_days_median": q(hold, 0.5),
        "holding_days_p25": q(hold, 0.25),
        "holding_days_p75": q(hold, 0.75),
        "price_no_bars": sum(
            1 for r in rows if r.get("price_note", "").startswith("no bars")
        ),
    }

    # descriptive 99-share round trip -- NOT a Sharpe, NOT a strategy claim
    roundtrip = []
    for r in rows:
        if r["gross_premium"] is None or not r.get("pre_close"):
            continue
        stake = 99 * r["pre_close"]
        gain = r["gross_premium"] * stake
        roundtrip.append(
            {
                "issuer": r["issuer"],
                "ticker": r["tickers"].split(",")[0],
                "launch_date": r["launch_date"],
                "pre_close": round(r["pre_close"], 4),
                "stake_usd_99sh": round(stake, 2),
                "gross_premium": round(r["gross_premium"], 6),
                "gross_gain_usd": round(gain, 2),
                "net_after_1usd_commission_each_way": round(gain - 2.0, 2),
            }
        )
    summary["roundtrip_99_share"] = roundtrip

    (OUT_DIR / "m2_output.json").write_text(
        json.dumps({"summary": summary, "offers": rows}, indent=1, default=str)
    )
    fields = sorted({k for r in rows for k in r})
    order = [
        "issuer", "cik", "tickers", "exchanges", "listed_status", "vehicle", "launch_date",
        "expiration", "offer_type", "offer_price", "range_low", "range_high", "final_price",
        "premium_price_used", "premium_flag", "pre_close", "pre_close_date", "post_close",
        "post_close_date", "gross_premium", "completed", "proration", "odd_lot_priority",
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
