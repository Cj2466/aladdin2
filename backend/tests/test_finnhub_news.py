"""Unit tests for the Finnhub news client.

Every fixture below is a recorded-shape reproduction of what Finnhub's real
API returned when it was probed LIVE on 2026-09-01 with a real key (see
finnhub_news.py's docstring for the captured payloads). NO TEST HERE TOUCHES
THE NETWORK — an httpx.MockTransport serves every response, matching
test_edgar_filing_text_provider.py's convention.
"""

from datetime import UTC, date, datetime

import httpx
import pytest

from app.services.live_quotes.finnhub_news import (
    NewsFetchError,
    fetch_company_news,
    fetch_market_news,
)

# The exact item shape observed live (AAPL /company-news, 2026-09-01).
LIVE_COMPANY_ITEM = {
    "category": "company",
    "datetime": 1788280806,
    "headline": "These dow jones stocks are moving in today's session",
    "id": 141368965,
    "image": "https://www.chartmill.com/images/uploads/CM_Top_Movers.webp",
    "related": "AAPL",
    "source": "ChartMill",
    "summary": "Uncover the latest developments among dow jones stocks.",
    "url": "https://finnhub.io/api/news?id=c80d53f7cac54342",
}

# The exact item shape observed live (/news?category=general). Note `related`
# is an EMPTY STRING — a macro story attached to no ticker.
LIVE_GENERAL_ITEM = {
    "category": "top news",
    "datetime": 1788279553,
    "headline": "Jim Cramer says selling Amazon shares would be 'hysterical'",
    "id": 8431877,
    "image": "https://image.cnbcfm.com/api/v1/image/108356308.jpeg",
    "related": "",
    "source": "CNBC",
    "summary": 'The Investing Club holds its "Morning Meeting" every weekday.',
    "url": "https://www.cnbc.com/2026/09/01/cramer-amazon.html",
}


def _client(payload, status_code: int = 200, text: str | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if text is not None:
            return httpx.Response(status_code, text=text)
        return httpx.Response(status_code, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


# --- happy paths against the real observed shapes --------------------------


def test_company_news_parses_the_real_observed_item_shape():
    items = fetch_company_news(
        "AAPL", date(2026, 8, 27), date(2026, 9, 1), client=_client([LIVE_COMPANY_ITEM])
    )
    assert len(items) == 1
    item = items[0]
    assert item.headline == "These dow jones stocks are moving in today's session"
    assert item.source == "ChartMill"
    assert item.related == "AAPL"
    # datetime is a UNIX EPOCH IN SECONDS, not an ISO string — the single
    # easiest field in this API to misread.
    assert item.published_at == datetime.fromtimestamp(1788280806, tz=UTC)
    assert item.published_at.tzinfo is not None


def test_market_news_parses_and_normalises_empty_related_to_none():
    """A general story is attached to no ticker and Finnhub sends `related`
    as "". Handing a caller a falsy-but-present value would let a
    `related == ticker` filter read it as a real association."""
    items = fetch_market_news(client=_client([LIVE_GENERAL_ITEM]))
    assert len(items) == 1
    assert items[0].related is None


# --- THE surprise this vendor forces the caller to handle -------------------


def test_unknown_symbol_returns_empty_list_and_is_not_an_error():
    """Verified live: symbol=ZZZZINVALID answered HTTP 200 with `[]`, exactly
    as a genuinely quiet week would. Emptiness must therefore never be raised
    as an error — but it is also not evidence about the world, which is why
    the docstring says so and why this test pins the behaviour rather than the
    interpretation."""
    assert fetch_company_news(
        "ZZZZINVALID", date(2026, 8, 27), date(2026, 9, 1), client=_client([])
    ) == []


# --- shape guards: a malformed response must never read as "no news" -------


def test_a_json_object_instead_of_an_array_raises_rather_than_reading_as_no_news():
    """Both endpoints return a BARE ARRAY. An object means the API returned
    something structurally different from what was verified — an error
    envelope, or a changed API. Silently treating that as zero news is the
    exact failure the plan warns about: garbage input trusted downstream."""
    with pytest.raises(NewsFetchError, match="expected a JSON array"):
        fetch_market_news(client=_client({"error": "invalid api key"}))


def test_non_json_body_raises():
    with pytest.raises(NewsFetchError, match="not valid JSON"):
        fetch_market_news(client=_client(None, text="You don't have access to this resource."))


def test_http_error_status_raises():
    with pytest.raises(NewsFetchError, match="request failed"):
        fetch_market_news(client=_client(None, status_code=429, text="rate limit"))


# --- per-item robustness: one bad row must not blind the caller ------------


@pytest.mark.parametrize(
    "bad",
    [
        {"datetime": 1788280806},  # no headline
        {"headline": "  ", "datetime": 1788280806},  # blank headline
        {"headline": "x"},  # no timestamp
        {"headline": "x", "datetime": 0},  # non-positive epoch
        {"headline": "x", "datetime": "2026-09-01"},  # ISO string, not an epoch
        {"headline": "x", "datetime": True},  # bool is an int subclass -> 1970
        "not-a-dict",
    ],
)
def test_unusable_items_are_dropped_not_fatal(bad):
    items = fetch_market_news(client=_client([bad, LIVE_GENERAL_ITEM]))
    assert [i.headline for i in items] == [LIVE_GENERAL_ITEM["headline"]]


def test_items_come_back_newest_first_and_bounded():
    payload = [
        {**LIVE_GENERAL_ITEM, "headline": f"h{i}", "datetime": 1788000000 + i} for i in range(10)
    ]
    items = fetch_market_news(client=_client(payload), max_items=3)
    assert [i.headline for i in items] == ["h9", "h8", "h7"]


def test_company_news_sends_iso_dates_not_epochs():
    """The `from`/`to` PARAMS are ISO dates even though the `datetime` FIELD
    the API returns is an epoch — a genuine asymmetry in this endpoint."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=[])

    fetch_company_news(
        "AAPL",
        date(2026, 8, 27),
        date(2026, 9, 1),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert seen["from"] == "2026-08-27"
    assert seen["to"] == "2026-09-01"
    assert seen["symbol"] == "AAPL"
