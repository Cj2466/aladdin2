"""SEC EDGAR "Latest Filings" Atom feed client — real-time corporate-event
detection for "Project 2" Stage A.

Free, official, keyless, and auto-generated as filings are accepted. This is
the company-specific complement to gdelt_provider's world-news view.

CONVENTIONS ARE REUSED, NOT REINVENTED. The User-Agent, the request throttle
and the retry shape all come from market_data/edgar_xbrl_provider, which
established them against SEC's published fair-access policy (10 req/s ceiling,
declared user agent required). Importing them rather than restating them means
a future correction to SEC's policy is made in exactly one place, and it keeps
this project from presenting SEC with two different identities.

ENDPOINT — verified LIVE 2026-09-01 against the real feed, not from docs:
    https://www.sec.gov/cgi-bin/browse-edgar
        ?action=getcurrent&type=8-K&company=&dateb=&owner=include
        &count=100&output=atom

Real response: HTTP 200, Content-Type `application/atom+xml`, XML declared
`encoding="ISO-8859-1"` (NOT UTF-8 — httpx honours the XML declaration via the
charset, and ElementTree is fed BYTES below so it reads the declaration itself
rather than being handed an already-mis-decoded string). Root is
`<feed xmlns="http://www.w3.org/2005/Atom">`. One live `<entry>`, verbatim:

    <title>8-K - First Eagle Private Credit Fund (0001890107) (Filer)</title>
    <link rel="alternate" type="text/html"
          href="https://www.sec.gov/Archives/edgar/data/1890107/000119312526378072/
                0001193125-26-378072-index.htm"/>
    <summary type="html">
     &lt;b&gt;Filed:&lt;/b&gt; 2026-09-01 &lt;b&gt;AccNo:&lt;/b&gt; 0001193125-26-378072
     &lt;b&gt;Size:&lt;/b&gt; 219 KB
    &lt;br&gt;Item 8.01: Other Events
    &lt;br&gt;Item 9.01: Financial Statements and Exhibits
    </summary>
    <updated>2026-09-01T13:20:17-04:00</updated>
    <category scheme="https://www.sec.gov/" label="form type" term="8-K"/>
    <id>urn:tag:sec.gov,2008:accession-number=0001193125-26-378072</id>

THREE MEASURED SURPRISES, EACH OF WHICH CHANGED THE CODE BELOW
============================================================================
1. `type=` IS A PREFIX MATCH, NOT AN EXACT ONE. A live `type=8-K` request
   returned 100 entries of which one was form `8-K/A`. Worse, `type=SC 13`
   returned 3 entries and ALL of them were `SC 13E3` (going-private
   transactions) — a different form type entirely from the SC 13D/G ownership
   filings this scanner watches. A client that trusted its own query
   parameter would silently log SC 13E3 filings as 13D/G ownership events.
   So every entry is RE-FILTERED CLIENT-SIDE against the exact requested form
   term; the `term` attribute of <category> is the authoritative form type.

2. AN EMPTY FEED IS A NORMAL, VALID ANSWER. Live `type=SC 13D` and
   `type=SC 13G` both returned HTTP 200 with a ~500-byte feed containing ZERO
   entries and the title "Latest Filings - <ts> - No recent filings". The
   getcurrent feed is a short rolling window, and 13D/G filings are far rarer
   than 8-Ks, so "no entries" is the common case for them and is emphatically
   NOT an error. It must never be escalated, and it must never be recorded as
   a failure — doing either would corrupt the trigger-rate denominator that
   Phase 2.2 exists to measure.

3. THE FEED CARRIES NO TICKER. Entries identify a company by NAME and CIK
   only. Mapping to the point-in-time universe therefore has to go through
   CIK, which is why `universe_ciks` below is a CIK set and why the caller
   builds it by inverting edgar_xbrl_provider's existing ticker->CIK map
   rather than by inventing a second mapping.

The `(Filer)` / `(Subject)` role in the title is captured because it is
load-bearing for ownership filings: on an SC 13D the FILER is the accumulating
investor while the SUBJECT is the company whose stock is being accumulated —
and it is the subject that a market-moving read cares about. A live SC 13E3
entry confirmed the `(Subject)` role appears in exactly the same title
position: "SC 13E3 - Distribution Solutions Group, Inc. (0000703604) (Subject)".
"""

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from xml.etree import ElementTree

import httpx

from app.services.market_data.edgar_xbrl_provider import (
    EDGAR_MIN_SECONDS_BETWEEN_REQUESTS,
    EDGAR_RETRY_ATTEMPTS,
    EDGAR_RETRY_BASE_DELAY_SECONDS,
    build_edgar_user_agent,
)

logger = logging.getLogger(__name__)

EDGAR_BROWSE_URL = "https://www.sec.gov/cgi-bin/browse-edgar"

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

# SEC's getcurrent feed caps at 100 entries per request, and 100 is what a
# live request returned for 8-K. Asking for more does not yield more.
EDGAR_FEED_MAX_COUNT = 100

# "8-K - First Eagle Private Credit Fund (0001890107) (Filer)"
# Anchored at the END so a company name containing its own parentheses (real
# and common in EDGAR: "Acme Corp (Delaware)") cannot steal the CIK group —
# the CIK and role are always the LAST two parenthesised groups.
_ENTRY_TITLE_RE = re.compile(
    r"^(?P<form>.+?)\s+-\s+(?P<company>.+)\s+\((?P<cik>\d+)\)\s+\((?P<role>[^()]*)\)\s*$"
)

# "<b>Filed:</b> 2026-09-01 <b>AccNo:</b> 0001193125-26-378072" — ElementTree
# hands back the UNESCAPED text, so these match the real tags, not entities.
_FILED_RE = re.compile(r"Filed:\s*</b>\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE)
# "Item 8.01: Other Events"
_ITEM_RE = re.compile(r"Item\s+(\d+\.\d+)\s*:", re.IGNORECASE)


class EdgarFeedError(RuntimeError):
    """The feed could not be fetched or was not parseable Atom.

    NOT raised for an empty feed — see surprise 2 in the module docstring. An
    empty feed is a successful observation of "nothing filed recently", which
    the scanner must record as a real non-trigger rather than as an error.
    """


@dataclass(frozen=True)
class FilingEntry:
    """One accepted filing from the Latest Filings feed."""

    form_type: str
    company_name: str
    cik: int
    # "Filer", "Subject", "Reporting" — see the module docstring on why this
    # matters for ownership filings.
    role: str
    accession_number: str
    url: str
    # From <updated>: acceptance time, timezone-aware (the feed reports a real
    # offset, e.g. -04:00 for EDT). Kept aware so a naive-vs-aware comparison
    # can never silently shift a filing by four hours.
    updated_at: datetime | None
    filed_date: str | None
    # 8-K item numbers ("8.01", "9.01") parsed from the summary. Empty for
    # forms that carry no items (an SC 13D summary has none — verified live).
    item_numbers: tuple[str, ...]


def _text(element: ElementTree.Element | None) -> str:
    if element is None or element.text is None:
        return ""
    return element.text.strip()


def parse_filings_atom(raw: bytes) -> list[FilingEntry]:
    """Parse the Latest Filings Atom document into entries.

    Takes BYTES, not str, deliberately: the document declares
    `encoding="ISO-8859-1"` and ElementTree honours that declaration only when
    it is parsing bytes. Handing it an already-decoded string risks mojibake in
    company names carrying non-ASCII characters.

    An entry that does not parse is SKIPPED with a warning rather than failing
    the whole feed — one malformed title should not blind the scanner to the
    other 99 filings. A document that is not Atom at all raises.
    """
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise EdgarFeedError(f"feed was not parseable XML: {exc}") from exc

    if not root.tag.endswith("feed"):
        raise EdgarFeedError(f"expected an Atom <feed> root, got <{root.tag}>")

    entries: list[FilingEntry] = []
    for node in root.findall("atom:entry", ATOM_NS):
        title = _text(node.find("atom:title", ATOM_NS))
        match = _ENTRY_TITLE_RE.match(title)
        if match is None:
            logger.warning("EDGAR feed: unparseable entry title %r", title)
            continue

        # The <category term> is the AUTHORITATIVE form type; the title's own
        # prefix agrees with it on every entry observed live, but the category
        # is the structured field and is what the exact-match filter uses.
        category = node.find("atom:category", ATOM_NS)
        form_type = (
            category.get("term", "").strip()
            if category is not None
            else match.group("form").strip()
        )

        link = node.find("atom:link", ATOM_NS)
        url = link.get("href", "") if link is not None else ""

        raw_id = _text(node.find("atom:id", ATOM_NS))
        accession = raw_id.split("accession-number=")[-1] if "accession-number=" in raw_id else ""

        summary = _text(node.find("atom:summary", ATOM_NS))
        filed_match = _FILED_RE.search(summary)

        updated_raw = _text(node.find("atom:updated", ATOM_NS))
        updated_at: datetime | None = None
        if updated_raw:
            try:
                updated_at = datetime.fromisoformat(updated_raw)
            except ValueError:
                logger.warning("EDGAR feed: unparseable <updated> %r", updated_raw)

        entries.append(
            FilingEntry(
                form_type=form_type,
                company_name=match.group("company").strip(),
                cik=int(match.group("cik")),
                role=match.group("role").strip(),
                accession_number=accession,
                url=url,
                updated_at=updated_at,
                filed_date=filed_match.group(1) if filed_match else None,
                item_numbers=tuple(dict.fromkeys(_ITEM_RE.findall(summary))),
            )
        )
    return entries


class SecEdgarRssProvider:
    """Throttled, retrying client for the Latest Filings Atom feed.

    Mirrors EdgarXbrlProvider's construction exactly — same injectable
    `client`/`sleep`/`clock` so tests drive it with scripted responses and no
    real waiting, same throttle interval, same retry shape, same User-Agent
    builder. It deliberately does NOT cache: the entire value of this feed is
    that it is current, and a cached "latest filings" is a contradiction.
    """

    def __init__(
        self,
        user_agent: str | None = None,
        min_request_interval: float = EDGAR_MIN_SECONDS_BETWEEN_REQUESTS,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        client: httpx.Client | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.min_request_interval = min_request_interval
        self._sleep = sleep
        self._clock = clock
        self._last_request_at: float | None = None
        headers = {
            "User-Agent": user_agent if user_agent is not None else build_edgar_user_agent(),
            "Accept-Encoding": "gzip, deflate",
        }
        self._client = client if client is not None else httpx.Client(
            headers=headers, timeout=timeout, follow_redirects=True
        )

    def _throttle(self) -> None:
        if self._last_request_at is not None:
            elapsed = self._clock() - self._last_request_at
            remaining = self.min_request_interval - elapsed
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at = self._clock()

    def _get_bytes(self, params: dict) -> bytes:
        last_error: Exception | None = None
        for attempt in range(1, EDGAR_RETRY_ATTEMPTS + 1):
            self._throttle()
            try:
                response = self._client.get(EDGAR_BROWSE_URL, params=params)
                response.raise_for_status()
                return response.content
            except Exception as exc:  # noqa: BLE001 — transient 5xx/403/network; last attempt raises below
                last_error = exc
                if attempt < EDGAR_RETRY_ATTEMPTS:
                    self._sleep(EDGAR_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))
        raise EdgarFeedError(
            f"Latest Filings feed failed after {EDGAR_RETRY_ATTEMPTS} attempts"
        ) from last_error

    def fetch_latest_filings(
        self, form_type: str, *, count: int = EDGAR_FEED_MAX_COUNT
    ) -> list[FilingEntry]:
        """Recently-accepted filings for ONE form type, exact-matched.

        The `type` query parameter is a PREFIX match upstream (see surprise 1
        in the module docstring), so the returned list is filtered to entries
        whose authoritative `<category term>` equals `form_type` exactly. This
        is what stops an `SC 13D` watch from silently accumulating `SC 13E3`
        filings, and an `8-K` watch from absorbing `8-K/A` amendments unless
        those are watched in their own right.

        Returns [] when nothing recent was filed — a normal, verified state,
        not an error.
        """
        raw = self._get_bytes(
            {
                "action": "getcurrent",
                "type": form_type,
                "company": "",
                "dateb": "",
                "owner": "include",
                "count": str(count),
                "output": "atom",
            }
        )
        entries = parse_filings_atom(raw)
        exact = [e for e in entries if e.form_type == form_type]
        if len(exact) != len(entries):
            logger.info(
                "EDGAR feed %s: dropped %d prefix-matched entries of other form types",
                form_type,
                len(entries) - len(exact),
            )
        return exact
