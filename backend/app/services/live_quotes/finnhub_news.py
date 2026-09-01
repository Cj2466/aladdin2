"""Finnhub news client — company news and general market news.

Built for "Project 2" Phase 2.3 (assembling a bounded context bundle for the
Stage-B LLM call). It is deliberately built and verified in PHASE 2.2, one
phase before its first consumer exists, because of an explicit instruction in
the plan: a malformed news fetch silently fed to an LLM is how you get a
confidently-wrong judgment built on garbage input. Nothing in Phase 2.2 calls
this module in the scanner path — it is verified now precisely so that Phase
2.3 never has to trust it unverified.

ENDPOINTS — both verified LIVE 2026-09-01 against the real Finnhub API with a
real key, not recalled from documentation:

 * https://finnhub.io/api/v1/company-news?symbol=&from=&to=&token=
   Returns a bare JSON ARRAY (not an object with a data key). Fetched live for
   AAPL over a 5-day window: 69 items. Each item:
     {"category": "company", "datetime": 1788280806, "headline": str,
      "id": int, "image": str, "related": "AAPL", "source": "ChartMill",
      "summary": str, "url": str}
   `from`/`to` are required and are ISO dates (YYYY-MM-DD), NOT epochs.

 * https://finnhub.io/api/v1/news?category=general&token=
   Same item schema, 100 items live. `category` is the market feed selector;
   `related` is frequently an EMPTY STRING here (a general market story is
   attached to no ticker), which is why `related` is never used as a required
   field below.

THE ONE REAL SURPRISE, AND WHY IT IS HANDLED EXPLICITLY
============================================================================
An UNKNOWN SYMBOL IS NOT AN ERROR. Fetched live with symbol=ZZZZINVALID,
Finnhub answered HTTP 200 with an empty array `[]` — no error status, no error
body. This is the same convention finnhub_rest.fetch_quote_snapshot already
documents for /quote (HTTP 200 with all-zero fields for an unknown symbol),
so it is a house style of this vendor rather than a one-off.

The consequence matters more here than it does for a quote: "this ticker has
no news" and "this ticker does not exist" and "you typo'd the symbol" are all
the SAME response. So an empty list is returned as an empty list and is never
converted into an exception — but a caller must not read it as evidence that
nothing is happening. NewsFetchError is raised only for transport/status/shape
failures, which are genuinely different from "the vendor said nothing".

`datetime` IS A UNIX EPOCH IN SECONDS (observed 1788280806, an int), not an
ISO string. It is parsed to an aware UTC datetime here so no caller has to
rediscover the unit — getting this wrong silently mislabels every headline's
age, which for an event-driven system is the difference between "breaking" and
"last week".
"""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

FINNHUB_COMPANY_NEWS_URL = "https://finnhub.io/api/v1/company-news"
FINNHUB_MARKET_NEWS_URL = "https://finnhub.io/api/v1/news"

# Matches finnhub_rest.fetch_quote_snapshot's 10s. Finnhub is a low-latency
# commercial API; a news fetch that takes longer than this has failed in every
# way that matters to a 5-minute scan loop.
FINNHUB_NEWS_TIMEOUT_SECONDS = 10.0

# Bound what a single call can hand a caller. Live responses were 69 (company,
# 5 days) and 100 (general) items; a context bundle needs the newest handful,
# and an unbounded list is how an LLM prompt silently becomes enormous in a
# later phase. Applied AFTER sorting newest-first, so truncation drops the
# oldest rather than an arbitrary slice.
DEFAULT_MAX_ITEMS = 50


class NewsFetchError(RuntimeError):
    """A news fetch failed in a way the caller must not mistake for "no news".

    Deliberately NOT raised for an empty result: Finnhub answers an unknown
    symbol with HTTP 200 and `[]` (verified live — see the module docstring),
    so emptiness is a legitimate vendor answer and is returned as an empty
    list. This exception means the transport, the status, or the response
    SHAPE was wrong — i.e. the fetch produced no trustworthy answer at all.
    """


@dataclass(frozen=True)
class NewsItem:
    """One headline, with the vendor fields a later phase's context bundle
    actually needs. Deliberately drops `image` and `id`: neither informs a
    judgment, and both would just enlarge a prompt."""

    headline: str
    summary: str
    source: str
    url: str
    published_at: datetime
    category: str
    # The ticker Finnhub attached, or None. EMPTY STRING IS NORMALISED TO NONE
    # because the general feed sets it to "" constantly (observed live) and a
    # caller filtering on `related == some_ticker` must not be handed a
    # falsy-but-present value that reads as a real association.
    related: str | None


def _parse_item(raw: dict) -> NewsItem | None:
    """One vendor dict -> NewsItem, or None if it is unusable.

    A single malformed item is DROPPED rather than failing the whole fetch:
    one bad row in a 100-item feed should not blind the caller to the other
    99. A response that is not a list at all is a different matter and raises
    in the fetch functions below — that is a shape failure, not a bad row.

    Requires a real headline and a real timestamp. An item with neither is
    not a usable news item under any reading, and inventing a timestamp for it
    (say, "now") would misdate it as breaking news.
    """
    if not isinstance(raw, dict):
        return None

    headline = raw.get("headline")
    if not isinstance(headline, str) or not headline.strip():
        return None

    epoch = raw.get("datetime")
    # bool is a subclass of int in Python; a True here would become 1970.
    if isinstance(epoch, bool) or not isinstance(epoch, (int, float)) or epoch <= 0:
        return None
    try:
        published_at = datetime.fromtimestamp(float(epoch), tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None

    related = raw.get("related")
    related = related.strip() if isinstance(related, str) and related.strip() else None

    return NewsItem(
        headline=headline.strip(),
        summary=raw.get("summary") if isinstance(raw.get("summary"), str) else "",
        source=raw.get("source") if isinstance(raw.get("source"), str) else "",
        url=raw.get("url") if isinstance(raw.get("url"), str) else "",
        published_at=published_at,
        category=raw.get("category") if isinstance(raw.get("category"), str) else "",
        related=related,
    )


def _parse_payload(payload: object, *, context: str, max_items: int) -> list[NewsItem]:
    """Vendor payload -> newest-first, bounded list of NewsItem.

    The list-ness check is the shape guard the module docstring promises: both
    endpoints return a BARE ARRAY, so an object here means the vendor returned
    something structurally different from what was verified live (an error
    envelope, an HTML interstitial, a changed API) and must not be silently
    treated as "no news".
    """
    if not isinstance(payload, list):
        raise NewsFetchError(
            f"{context}: expected a JSON array, got {type(payload).__name__} — "
            "refusing to treat a malformed response as 'no news'"
        )

    items = [parsed for raw in payload if (parsed := _parse_item(raw)) is not None]
    n_dropped = len(payload) - len(items)
    if n_dropped:
        logger.warning("%s: dropped %d unparseable news item(s)", context, n_dropped)

    items.sort(key=lambda i: i.published_at, reverse=True)
    return items[:max_items]


def _get(client: httpx.Client, url: str, params: dict, *, context: str) -> object:
    try:
        response = client.get(url, params={**params, "token": settings.finnhub_api_key})
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        raise NewsFetchError(f"{context}: request failed: {exc}") from exc
    except ValueError as exc:
        # json() on a non-JSON body. Finnhub answers auth failures with a
        # plain-text body, so this is a real and reachable path.
        raise NewsFetchError(f"{context}: response was not valid JSON: {exc}") from exc


def fetch_company_news(
    symbol: str,
    from_date: date,
    to_date: date,
    *,
    max_items: int = DEFAULT_MAX_ITEMS,
    client: httpx.Client | None = None,
) -> list[NewsItem]:
    """Company news for one symbol over an inclusive [from_date, to_date]
    window, newest first.

    AN EMPTY LIST IS A LEGITIMATE ANSWER and means only "Finnhub returned no
    items" — it does NOT distinguish a quiet week from an unknown symbol, both
    of which are HTTP 200 + `[]` (verified live). Callers must not read
    emptiness as evidence about the world.

    `client` is injectable so tests drive scripted responses with no network,
    matching this project's scripted-fake-at-every-IO-boundary convention.
    """
    context = f"finnhub company-news {symbol}"
    params = {
        "symbol": symbol,
        # ISO dates, not epochs — this endpoint differs from the `datetime`
        # field it returns, which IS an epoch. Verified live.
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
    }
    if client is not None:
        return _parse_payload(_get(client, FINNHUB_COMPANY_NEWS_URL, params, context=context),
                              context=context, max_items=max_items)
    with httpx.Client(timeout=FINNHUB_NEWS_TIMEOUT_SECONDS) as owned:
        return _parse_payload(_get(owned, FINNHUB_COMPANY_NEWS_URL, params, context=context),
                              context=context, max_items=max_items)


def fetch_market_news(
    category: str = "general",
    *,
    max_items: int = DEFAULT_MAX_ITEMS,
    client: httpx.Client | None = None,
) -> list[NewsItem]:
    """General market news, newest first. `related` is usually None here — a
    macro story is attached to no ticker (verified live)."""
    context = f"finnhub news {category}"
    params = {"category": category}
    if client is not None:
        return _parse_payload(_get(client, FINNHUB_MARKET_NEWS_URL, params, context=context),
                              context=context, max_items=max_items)
    with httpx.Client(timeout=FINNHUB_NEWS_TIMEOUT_SECONDS) as owned:
        return _parse_payload(_get(owned, FINNHUB_MARKET_NEWS_URL, params, context=context),
                              context=context, max_items=max_items)
