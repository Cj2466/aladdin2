"""SEC EDGAR FILING FULL-TEXT provider: the plain narrative text of a
company's periodic reports (10-K / 10-Q), keyed to the point-in-time date
each filing actually became public.

Built 2026-09-01 for the "Lazy Prices" cross-sectional family
(cross_sectional_lazy_prices.py). It is a genuinely NEW fetch path, not an
extension of edgar_xbrl_provider.py: that module reads STRUCTURED XBRL
FACTS (numeric line items from data.sec.gov/api/xbrl/companyfacts) and has
no access to narrative text at all. The one place it touches an archived
document (get_filing_header_sic) deliberately reads only the first 16KB
SGML header via an HTTP Range request and never the body. This module needs
the body — the actual English prose management wrote — so it fetches the
filing's PRIMARY DOCUMENT and converts it to text.

What IS reused from edgar_xbrl_provider, rather than reinvented: the
EdgarFetchError type, build_edgar_user_agent (SEC's declared-bot UA
convention and its SEC_EDGAR_CONTACT override), the throttle interval, and
the retry constants. The rate-limit and politeness posture is that module's,
unchanged.

============================================================================
ENDPOINTS — EVERY ONE VERIFIED LIVE 2026-09-01, NOT RECALLED FROM MEMORY
============================================================================
 * https://data.sec.gov/submissions/CIK##########.json — filings.recent as
   PARALLEL ARRAYS. Verified live against CIK0000320193 (Apple): the key set
   is accessionNumber / filingDate / reportDate / acceptanceDateTime / act /
   form / fileNumber / filmNumber / items / core_type / size / isXBRL /
   isInlineXBRL / isXBRLNumeric / primaryDocument / primaryDocDescription.
   A real 10-K row reads form='10-K', accessionNumber='0000320193-25-000079',
   filingDate='2025-10-31', reportDate='2025-09-27',
   acceptanceDateTime='2025-10-31T10:01:26.000Z',
   primaryDocument='aapl-20250927.htm'.
   `primaryDocument` is the field that makes this module possible: it names
   the ONE document in the submission that is the report itself, so the
   exhibits, XBRL instance files and images are never fetched.
   MEASURED, NOT ASSUMED: the `size` field is the size of the WHOLE
   submission, not of the primary document. Apple's FY2025 10-K row reads
   size=9,392,337 while its primary document is 1,522,000 bytes — a 6x
   difference. Never size-budget from that field.
 * https://data.sec.gov/submissions/{name}.json — the PAGINATED OLDER
   history named by filings.files[].name. Verified live for GE
   (CIK0000040545-submissions-001.json): it is a dict of the SAME parallel
   arrays, INCLUDING primaryDocument and acceptanceDateTime, carrying 10
   further 10-Ks back to 2008 that filings.recent does not hold.
   THIS MATTERS AND IS A DELIBERATE DEPARTURE from cross_sectional_pead.py,
   which fetches `recent` only and discloses the resulting truncation. A
   language-change family compares each filing to its OWN PREDECESSOR, so a
   truncated window does not merely shorten the sample — it destroys the
   FIRST usable observation of every firm whose predecessor fell off the
   edge. Paging costs 1-2 extra requests per company and is worth it here.
 * https://www.sec.gov/Archives/edgar/data/{cik}/{accession-no-dashes}/
   {primaryDocument} — the report document itself. Verified live for Apple,
   Coca-Cola, J&J, Boeing and GE.

TRANSFER COST, MEASURED LIVE 2026-09-01 over 43 real 10-Ks from 15 S&P 500
companies, because this was the open feasibility question and a guess would
have been worthless: mean 0.23s to fetch and 0.256 MB ON THE WIRE per
filing, against a mean 2.6 MB of raw HTML. The 10x gap is GZIP — this
module sends Accept-Encoding: gzip, deflate (as edgar_xbrl_provider does)
and SEC honors it on Archives documents. Apple's 1.52 MB FY2025 10-K
transfers as 0.11 MB. Without compression a full-universe run would move
tens of GB from a public service; with it, ~2.6 GB for 10,000 filings, at
under an hour of wall clock inside the throttle. The politeness posture is
still request-rate-based (SEC's own published cap is on requests/second),
but the bandwidth number is now measured rather than hoped for.

============================================================================
THE TEXT PIPELINE, AND THE ONE CONTAMINANT THAT MATTERS
============================================================================
Modern EDGAR filings are INLINE XBRL: the .htm document carries, inside
<ix:header> and <ix:hidden> blocks, a machine-readable dump of every tagged
fact plus the taxonomy URIs that name them. It is invisible in a browser and
enormous in the source.

MEASURED CONSEQUENCE (Apple FY2025 10-K, live 2026-09-01): stripping tags
WITHOUT removing those blocks first yields text that begins

    "aapl-20250927 false 2025 FY 0000320193 P1Y P1Y P1Y P1Y
     http://fasb.org/us-gaap/2025#LongTermDebtNoncurrent
     http://fasb.org/us-gaap/2025#LongTermDebtNoncurrent ..."

— 14,000 characters of duration codes and taxonomy URIs before a single word
of English. Removing the blocks first yields

    "UNITED STATES SECURITIES AND EXCHANGE COMMISSION Washington, D.C. 20549
     FORM 10-K (Mark One) ANNUAL REPORT PURSUANT TO SECTION 13 OR 15(d) ..."

This is not cosmetic. That block's content is a function of how many facts
the filer tagged that year, so it changes between consecutive filings for
reasons that have nothing to do with the language management wrote — exactly
the spurious "change" a Lazy Prices signal must not see. html_to_text
removes it first, always.

Numbers and dates are dropped at TOKENIZATION rather than here (see
cross_sectional_lazy_prices.tokenize): every filing's figures change every
period mechanically, and the hypothesis is about LANGUAGE.

============================================================================
POINT-IN-TIME AVAILABILITY — THE SAFETY-CRITICAL PART
============================================================================
A filing's text may be used ONLY from the date it actually became public.
availability_date() derives that from acceptanceDateTime (UTC -> US/Eastern
via zoneinfo), NEVER from reportDate:

    accepted before 16:00 ET on day D   -> available on D
    accepted at/after 16:00 ET on day D -> available on D+1
    no acceptance timestamp             -> filing_date + 1 (conservative)

reportDate (the fiscal period end) PRECEDES public availability by the
entire filing lag — 30 to 90 days. Apple's FY2025 10-K covers a year ending
2025-09-27 and was not public until 2025-10-31. Keying the signal to the
period end would let a backtest read, on 2025-09-27, language that did not
exist for another 34 days. That is the single largest look-ahead hazard in
this family and the reason availability_date takes a FilingRef and has no
code path that can reach report_date at all.
"""

import gzip
import html as html_module
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from app.services.market_data.edgar_xbrl_provider import (
    EDGAR_MIN_SECONDS_BETWEEN_REQUESTS,
    EDGAR_RETRY_ATTEMPTS,
    EDGAR_RETRY_BASE_DELAY_SECONDS,
    EdgarFetchError,
    build_edgar_user_agent,
)

logger = logging.getLogger(__name__)

EDGAR_SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
EDGAR_SUBMISSIONS_PAGE_URL_TEMPLATE = "https://data.sec.gov/submissions/{name}"
EDGAR_PRIMARY_DOC_URL_TEMPLATE = (
    "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{document}"
)
EDGAR_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# The periodic-report forms this module knows how to pair. Amendments
# (10-K/A, 10-Q/A) are deliberately EXCLUDED rather than mapped onto their
# base form: an amendment is usually a partial re-filing (often a single
# restated item or an exhibit), so its text is not comparable to a full
# annual report, and treating it as one would manufacture an enormous
# spurious "language change" for the firm that filed it.
PERIODIC_FORMS: tuple[str, ...] = ("10-K", "10-Q")

# Acceptance at/after this hour US/Eastern pushes availability to the next
# day. Same constant and same reasoning as cross_sectional_pead's
# PEAD_ANNOUNCEMENT_CUTOFF_HOUR_ET.
ACCEPTANCE_CUTOFF_HOUR_ET = 16
_EASTERN = ZoneInfo("America/New_York")

# Cache layout: data/edgar_filing_text/v1/CIK##########/{accession}.txt.gz,
# holding the EXTRACTED TEXT (not the raw HTML). Gzipped because the text is
# ~200KB per filing and a full-universe run holds ~10,000 of them.
# The "v1" segment versions the EXTRACTOR: html_to_text's output is what is
# stored, so changing that function invalidates every cached document and the
# directory must be bumped rather than silently serving text the current
# extractor would not produce.
CACHE_SCHEMA_VERSION = "v1"
DEFAULT_CACHE_DIR = (
    Path(__file__).resolve().parents[3] / "data" / "edgar_filing_text" / CACHE_SCHEMA_VERSION
)

# --- HTML -> text ----------------------------------------------------------

# Inline-XBRL machine metadata. Removed FIRST and unconditionally — see the
# module docstring's measured Apple example for why this is load-bearing and
# not cosmetic.
_IX_BLOCK = re.compile(r"(?is)<ix:(header|hidden)\b.*?</ix:\1\s*>")
_SCRIPT_STYLE = re.compile(r"(?is)<(script|style|noscript)\b.*?</\1\s*>")
_COMMENT = re.compile(r"(?s)<!--.*?-->")
# Block-level structure becomes a NEWLINE rather than a space. This is what
# makes line-anchored heading detection possible — see extract_section for
# the measured reason that matters.
_BLOCK_TAG = re.compile(
    r"(?is)</?(p|div|br|tr|table|h[1-6]|li|ul|ol|td|th|section|article)\b[^>]*>"
)
_TAG = re.compile(r"(?s)<[^>]+>")
_INLINE_SPACE = re.compile(r"[ \t\r\f\v]+")
_NEWLINE_RUN = re.compile(r"\n\s*")


def html_to_text(raw_html: str) -> str:
    """The filing's readable prose: inline-XBRL metadata blocks, comments,
    script/style and all markup removed, HTML entities decoded.

    BLOCK-LEVEL STRUCTURE IS PRESERVED AS NEWLINES, everything else collapses
    to single spaces. That one decision is load-bearing rather than cosmetic:
    a real Item heading occupies its own block element and therefore starts a
    line, while a cross-reference to the same item ("...as described in Item
    1A of this Annual Report...") sits mid-sentence. extract_section relies on
    exactly that distinction, and a version of this function that flattened
    everything to spaces made correct section extraction impossible — see
    that function's docstring for the measured failure.

    Tokenization treats newline as ordinary whitespace, so preserving it
    changes nothing about any similarity score computed over whole documents.

    Takes and returns plain strings so it is directly unit-testable against
    hand-built HTML fixtures with no network — the same contract
    edgar_xbrl_provider.extract_line_items and parse_filing_header_sic keep,
    and for the same reason."""
    text = _IX_BLOCK.sub(" ", raw_html)
    text = _COMMENT.sub(" ", text)
    text = _SCRIPT_STYLE.sub(" ", text)
    text = _BLOCK_TAG.sub("\n", text)
    text = _TAG.sub(" ", text)
    text = html_module.unescape(text)
    # A non-breaking space survives unescape as U+00A0; normalize it
    # explicitly so token and line boundaries are uniform.
    text = text.replace("\xa0", " ")
    text = _INLINE_SPACE.sub(" ", text)
    text = _NEWLINE_RUN.sub("\n", text)
    return text.strip()


# --- section extraction ----------------------------------------------------

# The two 10-K sections the Lazy Prices paper reports separately. Patterns
# tolerate a missing "Item N" prefix, and any punctuation/dash run between
# the item number and the heading words, because real filings vary on both.
#
# EVERY pattern is anchored to LINE START ((?m) plus ^). That anchor is the
# whole reason these work — see extract_section's docstring for the measured
# cross-reference failure it exists to reject. The item NUMBER is required
# (not optional): "Item 1A." before "Risk Factors" is what distinguishes the
# heading from the many places a filing says the words "risk factors" in a
# sentence.
_SECTION_PATTERNS: dict[str, tuple[str, str]] = {
    "risk_factors": (
        r"(?im)^\s*item\s*1a[\.\:\s\-–—]*risk\s+factors",
        (
            r"(?im)^\s*item\s*1b[\.\:\s\-–—]*unresolved"
            r"|^\s*item\s*2[\.\:\s\-–—]*propert"
        ),
    ),
    "mda": (
        r"(?im)^\s*item\s*7[\.\:\s\-–—]*management[’'ʼ]?s\s+discussion",
        (
            r"(?im)^\s*item\s*7a[\.\:\s\-–—]*quantitative"
            r"|^\s*item\s*8[\.\:\s\-–—]*financial\s+statements"
        ),
    ),
}

SECTION_NAMES: tuple[str, ...] = tuple(_SECTION_PATTERNS)

# A candidate span shorter than this is a table-of-contents artifact or a
# cross-reference, not a section body.
MIN_SECTION_CHARS = 1_000

# ...and one longer than this FRACTION of the whole document is a mis-parse,
# not a section. THIS GUARD IS THE RESULT OF A MEASURED SILENT FAILURE, not
# caution in the abstract. A "longest span between a start marker and a
# following end marker" rule, run live on 43 real 10-Ks (2026-09-01),
# reported 93% "coverage" for risk_factors — but GE's three filings returned
# spans of 436K/409K/387K characters against whole documents of 445K/456K/
# 445K, i.e. 87-98% of the filing, and Exxon's FY2023 returned 343K. Those
# are not sections; they are the whole document wearing a section's name,
# produced when an early stray "Risk Factors" cross-reference pairs with a
# late terminator. Unguarded they would have entered the panel as real
# section-level observations and quietly turned the section specs into
# duplicates of the whole-document specs.
MAX_SECTION_DOC_FRACTION = 0.5


def extract_section(text: str, section: str) -> str | None:
    """The body of one named 10-K section, or None when it cannot be located
    with confidence.

    THE HEADINGS MUST BE LINE-ANCHORED, AND THAT IS NOT A STYLE CHOICE. A
    first implementation matched the heading words anywhere in the flattened
    text and picked the longest plausible span. Run live on real filings
    (2026-09-01) it reported 89-100% "coverage" and every length looked
    reasonable (24-30% of the document) — but the CONTENT was wrong, which
    only a content check caught:
      * Apple's extracted "risk_factors" began mid-sentence at '." The
        Company assumes no obligation to revise or update any forward-looking
        statements...' — the forward-looking-statements disclaimer, reached
        through a CROSS-REFERENCE to risk factors rather than the Item 1A
        heading.
      * J&J's extracted "mda" ENDED inside Item 5, at '...symbol JNJ. As of
        February 4, 2026, there were 108,358 record holders of Common Stock'
        — a span running across entirely the wrong region of the filing.
    Plausible LENGTH masked wrong CONTENT, so neither size guard fired. The
    fix is structural: a real Item heading occupies its own block element and
    therefore starts a line (html_to_text preserves that), while a
    cross-reference sits mid-sentence. Re-measured with line anchoring, every
    extracted section opened with genuinely correct prose ("An investment in
    the Company's common stock or debt securities involves risks and
    uncertainties", "The following risk factors should be considered...") and
    section sizes became stable year-over-year for the same filer (Caterpillar
    risk factors: 53,582 then 53,565 characters). Measured coverage fell to
    78% (risk_factors) / 89% (MD&A). THAT TRADE IS THE POINT: correct text at
    78% is worth more than wrong text at 89%, and the lower number is the
    honest one.

    Returns the LONGEST candidate span that passes both sanity guards
    (MIN_SECTION_CHARS, MAX_SECTION_DOC_FRACTION), pairing each start with the
    FIRST terminator after it. First-terminator is what keeps a
    table-of-contents entry harmless: the TOC's "Item 1A" line is followed
    immediately by the TOC's own "Item 1B" line, a span of a few dozen
    characters that the min guard drops, rather than reaching the real body's
    terminator hundreds of thousands of characters later.

    None is a first-class answer meaning "this filing's section could not be
    located", and every caller must count it rather than silently treating the
    filing as having no section. Section headings are genuinely not
    standardized across filers (GE's integrated report matches neither
    pattern), so a measured, disclosed coverage rate below 100% is the honest
    outcome — not something to force upward with a looser pattern that would
    readmit the mis-parses above."""
    if section not in _SECTION_PATTERNS:
        raise ValueError(
            f"unknown section {section!r}; this module knows {sorted(_SECTION_PATTERNS)}"
        )
    start_pattern, end_pattern = _SECTION_PATTERNS[section]
    starts = [m.end() for m in re.finditer(start_pattern, text)]
    ends = [m.start() for m in re.finditer(end_pattern, text)]
    if not starts or not ends:
        return None

    max_chars = int(len(text) * MAX_SECTION_DOC_FRACTION)
    best: tuple[int, int, int] | None = None
    for start in starts:
        following = [e for e in ends if e > start]
        if not following:
            continue
        end = following[0]
        span = end - start
        if span < MIN_SECTION_CHARS or span > max_chars:
            continue
        if best is None or span > best[0]:
            best = (span, start, end)
    if best is None:
        return None
    return text[best[1] : best[2]]


# --- filing references -----------------------------------------------------


@dataclass(frozen=True)
class FilingRef:
    """One periodic report as listed by the submissions API.

    `acceptance_utc` is the raw acceptanceDateTime string ('' when the row
    carried none). `report_date` is the FISCAL PERIOD END and is carried for
    diagnostics and for same-period de-duplication ONLY — it must never
    reach a point-in-time visibility decision (see availability_date)."""

    cik: int
    accession: str
    form: str
    filing_date: date
    acceptance_utc: str
    report_date: date | None
    primary_document: str


def availability_date(filing: FilingRef) -> date:
    """The first calendar date this filing's text could have been used.

    Derived from acceptanceDateTime ONLY. There is deliberately no code path
    from this function to filing.report_date: the fiscal period end precedes
    public availability by the whole filing lag, and keying visibility to it
    is the look-ahead bug this family most has to avoid (module docstring,
    POINT-IN-TIME AVAILABILITY).

    A tz-NAIVE acceptance string is stamped UTC rather than passed to
    astimezone(), which would silently assume the HOST machine's timezone —
    the exact latent bug an adversarial pass found in
    cross_sectional_pead.announcement_day0 on 2026-08-28. A missing or
    unparseable timestamp falls back to filing_date + 1 day, which can only
    ever DELAY availability, never advance it."""
    if filing.acceptance_utc:
        try:
            accepted = datetime.fromisoformat(filing.acceptance_utc)
        except ValueError:
            return filing.filing_date + timedelta(days=1)
        if accepted.tzinfo is None:
            accepted = accepted.replace(tzinfo=UTC)
        eastern = accepted.astimezone(_EASTERN)
        if eastern.hour >= ACCEPTANCE_CUTOFF_HOUR_ET:
            return eastern.date() + timedelta(days=1)
        return eastern.date()
    return filing.filing_date + timedelta(days=1)


@dataclass
class FilingIndexReport:
    """What the filing-index pass actually covered. Every field here is a
    sample-construction fact the consuming family must report, not a log
    line — the same contract EdgarFetchReport keeps for PEAD."""

    n_tickers_requested: int = 0
    n_tickers_cik_resolved: int = 0
    n_tickers_indexed: int = 0
    n_older_pages_fetched: int = 0
    n_filings_listed: int = 0
    unresolved_tickers: list[str] = field(default_factory=list)
    failed_tickers: list[str] = field(default_factory=list)


def parse_filing_rows(
    cik: int, payload: dict, forms: tuple[str, ...] = PERIODIC_FORMS
) -> list[FilingRef]:
    """FilingRefs from ONE submissions payload — either the `filings.recent`
    sub-dict or a whole older page document, both of which are the same
    parallel-array shape (verified live, see module docstring).

    Rows missing a primaryDocument are skipped: without it there is no
    document to fetch. Form matching is EXACT against `forms`, so '10-K/A'
    never enters as '10-K' (see PERIODIC_FORMS for why amendments are out)."""
    recent = payload.get("filings", {}).get("recent") if "filings" in payload else payload
    if not isinstance(recent, dict):
        return []
    form_list = recent.get("form") or []
    accessions = recent.get("accessionNumber") or []
    filing_dates = recent.get("filingDate") or []
    acceptances = recent.get("acceptanceDateTime") or []
    report_dates = recent.get("reportDate") or []
    primaries = recent.get("primaryDocument") or []

    out: list[FilingRef] = []
    for i, form in enumerate(form_list):
        if form not in forms:
            continue
        if i >= len(accessions) or i >= len(filing_dates) or i >= len(primaries):
            continue
        primary = primaries[i]
        if not primary:
            continue
        raw_report = report_dates[i] if i < len(report_dates) else ""
        try:
            filed = date.fromisoformat(filing_dates[i])
        except (ValueError, TypeError):
            continue
        try:
            report = date.fromisoformat(raw_report) if raw_report else None
        except (ValueError, TypeError):
            report = None
        out.append(
            FilingRef(
                cik=cik,
                accession=accessions[i],
                form=form,
                filing_date=filed,
                acceptance_utc=(acceptances[i] or "") if i < len(acceptances) else "",
                report_date=report,
                primary_document=primary,
            )
        )
    return out


class EdgarFilingTextProvider:
    """Rate-limited, retrying, disk-caching fetcher for filing narrative text.

    Same injectable `sleep`/`clock`/`client` contract as EdgarXbrlProvider so
    tests can drive the throttle with no real waiting and no network."""

    def __init__(
        self,
        cache_dir: Path | str | None = DEFAULT_CACHE_DIR,
        user_agent: str | None = None,
        min_request_interval: float = EDGAR_MIN_SECONDS_BETWEEN_REQUESTS,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        client: httpx.Client | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.min_request_interval = min_request_interval
        self._sleep = sleep
        self._clock = clock
        self._last_request_at: float | None = None
        self.n_documents_fetched = 0
        self.n_documents_from_cache = 0
        headers = {
            "User-Agent": user_agent if user_agent is not None else build_edgar_user_agent(),
            # Measured 10x transfer reduction on real filings — see the module
            # docstring's TRANSFER COST block.
            "Accept-Encoding": "gzip, deflate",
        }
        self._client = (
            client
            if client is not None
            else httpx.Client(headers=headers, timeout=120.0, follow_redirects=True)
        )

    def _throttle(self) -> None:
        if self._last_request_at is not None:
            remaining = self.min_request_interval - (self._clock() - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at = self._clock()

    def _get(self, url: str, *, as_json: bool) -> dict | str:
        last_error: Exception | None = None
        for attempt in range(1, EDGAR_RETRY_ATTEMPTS + 1):
            self._throttle()
            try:
                resp = self._client.get(url)
                if resp.status_code == 404:
                    raise EdgarFetchError(f"404 for {url}")
                resp.raise_for_status()
                return resp.json() if as_json else resp.text
            except EdgarFetchError:
                raise
            except Exception as exc:  # noqa: BLE001 — transient 5xx/403/network; last attempt re-raises
                last_error = exc
                if attempt < EDGAR_RETRY_ATTEMPTS:
                    self._sleep(EDGAR_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))
        raise EdgarFetchError(
            f"failed after {EDGAR_RETRY_ATTEMPTS} attempts: {url}"
        ) from last_error

    def get_ticker_cik_map(self) -> dict[str, int]:
        """{ticker: CIK} from SEC's own mapping file (dash symbology for
        share classes, matching this project's own convention). Carries the
        SAME measured limit edgar_xbrl_provider documents: it maps CURRENT
        tickers only, so a departed index member resolves no CIK even though
        its filings still exist."""
        raw = self._get(EDGAR_COMPANY_TICKERS_URL, as_json=True)
        assert isinstance(raw, dict)
        return {row["ticker"]: int(row["cik_str"]) for row in raw.values()}

    def list_filings(
        self,
        cik: int,
        forms: tuple[str, ...] = PERIODIC_FORMS,
        *,
        include_older_pages: bool = True,
    ) -> tuple[list[FilingRef], int]:
        """(every periodic filing EDGAR lists for this company, older pages
        fetched) sorted by filing date.

        include_older_pages walks filings.files — the paginated pre-`recent`
        history — because a language-change family needs each filing's OWN
        PREDECESSOR and a truncated window destroys the first usable
        observation per firm, not merely some tail (module docstring)."""
        payload = self._get(EDGAR_SUBMISSIONS_URL_TEMPLATE.format(cik=cik), as_json=True)
        assert isinstance(payload, dict)
        filings = parse_filing_rows(cik, payload, forms)
        n_pages = 0
        if include_older_pages:
            for page in payload.get("filings", {}).get("files", []) or []:
                name = page.get("name")
                if not name:
                    continue
                try:
                    older = self._get(
                        EDGAR_SUBMISSIONS_PAGE_URL_TEMPLATE.format(name=name), as_json=True
                    )
                except EdgarFetchError as exc:
                    logger.warning("EDGAR older submissions page failed (%s): %s", name, exc)
                    continue
                assert isinstance(older, dict)
                n_pages += 1
                filings.extend(parse_filing_rows(cik, older, forms))
        seen: set[str] = set()
        unique: list[FilingRef] = []
        for filing in sorted(filings, key=lambda f: (f.filing_date, f.accession)):
            if filing.accession in seen:
                continue
            seen.add(filing.accession)
            unique.append(filing)
        return unique, n_pages

    def _cache_path(self, filing: FilingRef) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"CIK{filing.cik:010d}" / f"{filing.accession}.txt.gz"

    def get_filing_text(self, filing: FilingRef) -> str:
        """The filing's narrative text, disk-cached gzipped.

        An archived filing is IMMUTABLE — its accession number names a
        document that can never change — so unlike edgar_xbrl_provider's
        companyfacts cache this one needs no age bound: a refetch could only
        ever return the same bytes. What CAN change is html_to_text itself,
        which is why the cache directory carries CACHE_SCHEMA_VERSION."""
        cache_path = self._cache_path(filing)
        if cache_path is not None and cache_path.exists():
            try:
                with gzip.open(cache_path, "rt", encoding="utf-8") as handle:
                    self.n_documents_from_cache += 1
                    return handle.read()
            except (OSError, EOFError, gzip.BadGzipFile) as exc:
                # A truncated cache file (interrupted run) is refetched
                # rather than raising — the document is reproducible.
                logger.warning("unreadable filing-text cache %s: %s", cache_path, exc)

        url = EDGAR_PRIMARY_DOC_URL_TEMPLATE.format(
            cik=filing.cik,
            accession_nodash=filing.accession.replace("-", ""),
            document=filing.primary_document,
        )
        raw = self._get(url, as_json=False)
        assert isinstance(raw, str)
        text = html_to_text(raw)
        self.n_documents_fetched += 1
        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache_path.with_suffix(".tmp")
            try:
                with gzip.open(tmp, "wt", encoding="utf-8") as handle:
                    handle.write(text)
                tmp.replace(cache_path)
            except BaseException:
                tmp.unlink(missing_ok=True)
                raise
        return text

    def build_filing_index(
        self, tickers: list[str], forms: tuple[str, ...] = PERIODIC_FORMS
    ) -> tuple[dict[str, list[FilingRef]], FilingIndexReport]:
        """{ticker: its periodic filings} plus the coverage report. A ticker
        that resolves no CIK or whose submissions fetch fails is recorded on
        the report and skipped — both lists are part of the RESULT, never a
        log line, per this project's universe-accounting discipline."""
        report = FilingIndexReport(n_tickers_requested=len(tickers))
        cik_map = self.get_ticker_cik_map()
        index: dict[str, list[FilingRef]] = {}
        for ticker in tickers:
            cik = cik_map.get(ticker)
            if cik is None:
                report.unresolved_tickers.append(ticker)
                continue
            report.n_tickers_cik_resolved += 1
            try:
                filings, n_pages = self.list_filings(cik, forms)
            except EdgarFetchError as exc:
                logger.warning("EDGAR submissions fetch failed for %s: %s", ticker, exc)
                report.failed_tickers.append(ticker)
                continue
            report.n_tickers_indexed += 1
            report.n_older_pages_fetched += n_pages
            report.n_filings_listed += len(filings)
            index[ticker] = filings
        report.unresolved_tickers.sort()
        report.failed_tickers.sort()
        return index, report


def save_filing_index(
    index: dict[str, list[FilingRef]], report: FilingIndexReport, path: Path
) -> None:
    """Persist a filing index so a production run is replayable without
    re-walking EDGAR's submissions API (the same cache contract
    cross_sectional_pead.save_event_cache keeps for its 8-K events)."""
    payload = {
        "saved_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "report": {
            "n_tickers_requested": report.n_tickers_requested,
            "n_tickers_cik_resolved": report.n_tickers_cik_resolved,
            "n_tickers_indexed": report.n_tickers_indexed,
            "n_older_pages_fetched": report.n_older_pages_fetched,
            "n_filings_listed": report.n_filings_listed,
            "unresolved_tickers": report.unresolved_tickers,
            "failed_tickers": report.failed_tickers,
        },
        "filings": {
            ticker: [
                {
                    "cik": f.cik,
                    "accession": f.accession,
                    "form": f.form,
                    "filing_date": f.filing_date.isoformat(),
                    "acceptance_utc": f.acceptance_utc,
                    "report_date": f.report_date.isoformat() if f.report_date else "",
                    "primary_document": f.primary_document,
                }
                for f in filings
            ]
            for ticker, filings in index.items()
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def load_filing_index(path: Path) -> tuple[dict[str, list[FilingRef]], FilingIndexReport] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    r = payload["report"]
    report = FilingIndexReport(
        n_tickers_requested=r["n_tickers_requested"],
        n_tickers_cik_resolved=r["n_tickers_cik_resolved"],
        n_tickers_indexed=r["n_tickers_indexed"],
        n_older_pages_fetched=r["n_older_pages_fetched"],
        n_filings_listed=r["n_filings_listed"],
        unresolved_tickers=list(r["unresolved_tickers"]),
        failed_tickers=list(r["failed_tickers"]),
    )
    index = {
        ticker: [
            FilingRef(
                cik=int(row["cik"]),
                accession=row["accession"],
                form=row["form"],
                filing_date=date.fromisoformat(row["filing_date"]),
                acceptance_utc=row["acceptance_utc"],
                report_date=date.fromisoformat(row["report_date"]) if row["report_date"] else None,
                primary_document=row["primary_document"],
            )
            for row in rows
        ]
        for ticker, rows in payload["filings"].items()
    }
    return index, report
