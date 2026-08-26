"""Unit tests for the read-only Alpaca historical bars provider. Every
test mocks the HTTP layer (a fake httpx.Client) — no real authenticated
Alpaca call is ever made from the test suite, matching how
test_yfinance_provider.py mocks yf.download instead of hitting Yahoo."""

from datetime import date

import httpx
import pytest

from app.services.market_data.alpaca_provider import (
    ALPACA_RETRY_ATTEMPTS,
    AlpacaError,
    AlpacaProvider,
)


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    """Retry backoff otherwise adds real multi-second delays. The shared
    _call_with_retry resolves time.sleep from yfinance_provider's module
    at call time (see its own docstring), so that's the patch point."""
    monkeypatch.setattr(
        "app.services.market_data.yfinance_provider.time.sleep", lambda _seconds: None
    )


def _response(payload: dict) -> httpx.Response:
    return httpx.Response(200, json=payload, request=httpx.Request("GET", "https://test/v2/stocks/bars"))


def _bar(t: str, o=100.0, h=101.0, low=99.0, c=100.5, v=1000):
    return {"t": t, "o": o, "h": h, "l": low, "c": c, "v": v, "n": 10, "vw": 100.2}


class FakeClient:
    """Scripted stand-in for httpx.Client: returns queued payloads in
    order and records every (path, params) request for assertions."""

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.requests: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, path, params=None):
        self.requests.append({"path": path, "params": dict(params or {})})
        item = self.payloads.pop(0)
        if isinstance(item, Exception):
            raise item
        return _response(item)


def _patched_provider(monkeypatch, payloads) -> tuple[AlpacaProvider, FakeClient]:
    fake = FakeClient(payloads)
    monkeypatch.setattr(
        "app.services.market_data.alpaca_provider.httpx.Client", lambda **kwargs: fake
    )
    return AlpacaProvider(api_key="test-key", api_secret="test-secret"), fake


def test_missing_credentials_raise_without_any_network_call(monkeypatch):
    def explode(**kwargs):
        raise AssertionError("network client must never be constructed without credentials")

    monkeypatch.setattr("app.services.market_data.alpaca_provider.httpx.Client", explode)
    provider = AlpacaProvider(api_key="", api_secret="")
    with pytest.raises(AlpacaError):
        provider.get_stock_bars(["AAPL"], "1Min", date(2021, 1, 4), date(2021, 1, 5))


def test_unsupported_timeframe_rejected(monkeypatch):
    provider, _ = _patched_provider(monkeypatch, [])
    with pytest.raises(ValueError):
        provider.get_stock_bars(["AAPL"], "3Min", date(2021, 1, 4), date(2021, 1, 5))


def test_single_page_two_symbols_split_into_lowercase_ny_tz_frames(monkeypatch):
    payload = {
        "bars": {
            "AAPL": [_bar("2021-01-04T14:30:00Z", o=100, c=101), _bar("2021-01-04T14:31:00Z", o=101, c=102)],
            "MSFT": [_bar("2021-01-04T14:30:00Z", o=200, c=201)],
        },
        "next_page_token": None,
    }
    provider, _fake = _patched_provider(monkeypatch, [payload])
    bars, missing = provider.get_stock_bars(
        ["AAPL", "MSFT", "ZZZZ"], "1Min", date(2021, 1, 4), date(2021, 1, 5)
    )

    assert set(bars) == {"AAPL", "MSFT"}
    assert missing == ["ZZZZ"]
    aapl = bars["AAPL"]
    assert list(aapl.columns) == ["open", "high", "low", "close", "volume"]
    assert str(aapl.index.tz) == "America/New_York"
    # 14:30 UTC on a January (EST) date is 09:30 New York.
    assert aapl.index[0].hour == 9 and aapl.index[0].minute == 30
    assert aapl.index.is_monotonic_increasing
    assert float(aapl.iloc[0]["open"]) == 100.0


def test_request_params_carry_feed_adjustment_window_and_limit(monkeypatch):
    payload = {"bars": {"AAPL": [_bar("2021-01-04T14:30:00Z")]}, "next_page_token": None}
    provider, fake = _patched_provider(monkeypatch, [payload])
    provider.get_stock_bars(["AAPL"], "15Min", date(2021, 1, 4), date(2021, 2, 1))

    assert len(fake.requests) == 1
    params = fake.requests[0]["params"]
    assert fake.requests[0]["path"] == "/v2/stocks/bars"
    assert params["symbols"] == "AAPL"
    assert params["timeframe"] == "15Min"
    assert params["start"] == "2021-01-04"
    assert params["end"] == "2021-02-01"
    assert params["feed"] == "sip"
    assert params["adjustment"] == "all"
    assert params["limit"] == 10_000
    assert "page_token" not in params


def test_pagination_follows_next_page_token_until_exhausted(monkeypatch):
    page1 = {
        "bars": {"AAPL": [_bar("2021-01-04T14:30:00Z", c=101)]},
        "next_page_token": "TOKEN-1",
    }
    page2 = {
        "bars": {"AAPL": [_bar("2021-01-04T14:31:00Z", c=102)]},
        "next_page_token": "TOKEN-2",
    }
    page3 = {"bars": {"AAPL": [_bar("2021-01-04T14:32:00Z", c=103)]}, "next_page_token": None}
    provider, fake = _patched_provider(monkeypatch, [page1, page2, page3])
    bars, missing = provider.get_stock_bars(["AAPL"], "1Min", date(2021, 1, 4), date(2021, 1, 5))

    assert len(fake.requests) == 3
    assert "page_token" not in fake.requests[0]["params"]
    assert fake.requests[1]["params"]["page_token"] == "TOKEN-1"
    assert fake.requests[2]["params"]["page_token"] == "TOKEN-2"
    assert len(bars["AAPL"]) == 3
    assert missing == []


def test_regular_session_filter_drops_pre_and_post_market_bars(monkeypatch):
    payload = {
        "bars": {
            "AAPL": [
                _bar("2021-01-04T13:00:00Z"),  # 08:00 NY — premarket
                _bar("2021-01-04T14:30:00Z"),  # 09:30 NY — first regular bar
                _bar("2021-01-04T20:59:00Z"),  # 15:59 NY — last regular bar
                _bar("2021-01-04T21:00:00Z"),  # 16:00 NY — after-hours (bar START at close)
            ]
        },
        "next_page_token": None,
    }
    provider, _ = _patched_provider(monkeypatch, [payload])
    bars, _ = provider.get_stock_bars(["AAPL"], "1Min", date(2021, 1, 4), date(2021, 1, 5))
    times = [(ts.hour, ts.minute) for ts in bars["AAPL"].index]
    assert times == [(9, 30), (15, 59)]


def test_regular_session_filter_can_be_disabled(monkeypatch):
    payload = {
        "bars": {"AAPL": [_bar("2021-01-04T13:00:00Z"), _bar("2021-01-04T14:30:00Z")]},
        "next_page_token": None,
    }
    provider, _ = _patched_provider(monkeypatch, [payload])
    bars, _ = provider.get_stock_bars(
        ["AAPL"], "1Min", date(2021, 1, 4), date(2021, 1, 5), regular_session_only=False
    )
    assert len(bars["AAPL"]) == 2


def test_daily_timeframe_skips_session_filter(monkeypatch):
    # Daily bars are stamped at Alpaca's own daily convention (05:00 UTC =
    # midnight-ish NY) — nowhere near 09:30-16:00, and must NOT be dropped.
    payload = {"bars": {"AAPL": [_bar("2021-01-04T05:00:00Z")]}, "next_page_token": None}
    provider, _ = _patched_provider(monkeypatch, [payload])
    bars, _ = provider.get_stock_bars(["AAPL"], "1Day", date(2021, 1, 4), date(2021, 1, 5))
    assert len(bars["AAPL"]) == 1


def test_retry_then_succeed_returns_data(monkeypatch):
    payload = {"bars": {"AAPL": [_bar("2021-01-04T14:30:00Z")]}, "next_page_token": None}
    transient = httpx.ConnectError("boom", request=httpx.Request("GET", "https://test"))
    provider, fake = _patched_provider(monkeypatch, [transient, payload])
    bars, _ = provider.get_stock_bars(["AAPL"], "1Min", date(2021, 1, 4), date(2021, 1, 5))
    assert len(bars["AAPL"]) == 1
    assert len(fake.requests) == 2


def test_retry_exhausted_raises_alpaca_error(monkeypatch):
    failures = [
        httpx.ConnectError("boom", request=httpx.Request("GET", "https://test"))
        for _ in range(ALPACA_RETRY_ATTEMPTS)
    ]
    provider, fake = _patched_provider(monkeypatch, failures)
    with pytest.raises(AlpacaError):
        provider.get_stock_bars(["AAPL"], "1Min", date(2021, 1, 4), date(2021, 1, 5))
    assert len(fake.requests) == ALPACA_RETRY_ATTEMPTS


def test_http_error_status_raises_alpaca_error(monkeypatch):
    def error_response():
        return httpx.Response(
            403, json={"message": "forbidden"}, request=httpx.Request("GET", "https://test")
        )

    class ErrorClient(FakeClient):
        def get(self, path, params=None):
            self.requests.append({"path": path, "params": dict(params or {})})
            return error_response()

    fake = ErrorClient([])
    monkeypatch.setattr(
        "app.services.market_data.alpaca_provider.httpx.Client", lambda **kwargs: fake
    )
    provider = AlpacaProvider(api_key="test-key", api_secret="test-secret")
    with pytest.raises(AlpacaError):
        provider.get_stock_bars(["AAPL"], "1Min", date(2021, 1, 4), date(2021, 1, 5))


def test_symbols_chunked_across_requests(monkeypatch):
    monkeypatch.setattr("app.services.market_data.alpaca_provider.SYMBOLS_PER_REQUEST", 2)
    page_a = {"bars": {"AAA": [_bar("2021-01-04T14:30:00Z")]}, "next_page_token": None}
    page_b = {"bars": {"CCC": [_bar("2021-01-04T14:30:00Z")]}, "next_page_token": None}
    provider, fake = _patched_provider(monkeypatch, [page_a, page_b])
    bars, missing = provider.get_stock_bars(
        ["AAA", "BBB", "CCC"], "1Min", date(2021, 1, 4), date(2021, 1, 5)
    )
    assert len(fake.requests) == 2
    assert fake.requests[0]["params"]["symbols"] == "AAA,BBB"
    assert fake.requests[1]["params"]["symbols"] == "CCC"
    assert set(bars) == {"AAA", "CCC"}
    assert missing == ["BBB"]


def test_malformed_bar_rows_raise_alpaca_error(monkeypatch):
    payload = {
        "bars": {"AAPL": [{"t": "2021-01-04T14:30:00Z", "o": 1.0}]},  # missing h/l/c/v
        "next_page_token": None,
    }
    provider, _ = _patched_provider(monkeypatch, [payload])
    with pytest.raises(AlpacaError):
        provider.get_stock_bars(["AAPL"], "1Min", date(2021, 1, 4), date(2021, 1, 5))


def test_credentials_default_to_settings(monkeypatch):
    monkeypatch.setattr("app.services.market_data.alpaca_provider.settings.alpaca_api_key", "k")
    monkeypatch.setattr("app.services.market_data.alpaca_provider.settings.alpaca_api_secret", "s")
    provider = AlpacaProvider()
    assert provider._api_key == "k"
    assert provider._api_secret == "s"
