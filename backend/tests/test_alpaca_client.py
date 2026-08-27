"""Broker client: credentials, retry, URL selection, order formatting, and the
position sign convention.

Every response shape asserted here was captured from the REAL Alpaca paper
account this phase was verified against — in particular that every numeric
account field arrives as a string ("equity": "100000", not 100000).
"""

import httpx
import pytest

from app.config import settings
from app.services.execution import alpaca_client
from app.services.execution.alpaca_client import AlpacaError


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setattr(settings, "alpaca_api_key", "test-key")
    monkeypatch.setattr(settings, "alpaca_api_secret", "test-secret")
    monkeypatch.setattr(settings, "alpaca_paper_trading", True)
    monkeypatch.setattr(settings, "alpaca_live_trading_confirmed", False)


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.content = b"x" if payload is not None else b""
        self.text = str(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=self)  # type: ignore[arg-type]

    def json(self):
        return self._payload


def _patch_httpx(monkeypatch, script):
    """Replace httpx.Client with a scripted fake.

    The client opens a fresh httpx.Client per request, so `script` and `calls`
    are shared across every instance — which is what makes a retry sequence
    observable across attempts. Returns the shared call log.
    """
    script = list(script)
    calls: list[dict] = []

    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def request(self, method, url, headers=None, params=None, json=None):
            calls.append(
                {"method": method, "url": url, "headers": headers, "params": params, "json": json}
            )
            outcome = script.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    monkeypatch.setattr(httpx, "Client", lambda *_a, **_kw: _FakeClient())
    return calls


# --- credentials --------------------------------------------------------------


def test_missing_credentials_raise_before_any_network_call(monkeypatch):
    monkeypatch.setattr(settings, "alpaca_api_key", "")
    monkeypatch.setattr(settings, "alpaca_api_secret", "")

    def explode(*_a, **_kw):
        raise AssertionError("no network call must be attempted without credentials")

    monkeypatch.setattr(httpx, "Client", explode)

    with pytest.raises(AlpacaError, match="credentials"):
        alpaca_client.get_account()


def test_credentials_are_sent_as_alpaca_headers(monkeypatch, creds):
    calls = _patch_httpx(monkeypatch, [_FakeResponse({"equity": "1"})])
    alpaca_client.get_account()
    headers = calls[0]["headers"]
    assert headers["APCA-API-KEY-ID"] == "test-key"
    assert headers["APCA-API-SECRET-KEY"] == "test-secret"


# --- live/paper routing -------------------------------------------------------


def test_paper_is_the_default(monkeypatch, creds):
    assert alpaca_client.is_paper() is True
    assert alpaca_client.base_url() == alpaca_client.PAPER_BASE_URL


def test_turning_off_paper_alone_does_not_go_live(monkeypatch, creds):
    """One accidental env edit must never be enough. Both flags are required."""
    monkeypatch.setattr(settings, "alpaca_paper_trading", False)
    assert alpaca_client.is_paper() is True
    assert alpaca_client.base_url() == alpaca_client.PAPER_BASE_URL


def test_confirmation_flag_alone_does_not_go_live(monkeypatch, creds):
    monkeypatch.setattr(settings, "alpaca_live_trading_confirmed", True)
    assert alpaca_client.is_paper() is True


def test_both_flags_together_select_the_live_host(monkeypatch, creds):
    monkeypatch.setattr(settings, "alpaca_paper_trading", False)
    monkeypatch.setattr(settings, "alpaca_live_trading_confirmed", True)
    assert alpaca_client.is_paper() is False
    assert alpaca_client.base_url() == alpaca_client.LIVE_BASE_URL


# --- retry --------------------------------------------------------------------


def test_read_retries_then_succeeds(monkeypatch, creds):
    slept: list[float] = []
    calls = _patch_httpx(
        monkeypatch,
        [httpx.ConnectError("transient"), _FakeResponse({"is_open": True})],
    )
    clock = alpaca_client.get_clock(sleep=slept.append)
    assert clock == {"is_open": True}
    assert len(calls) == 2
    assert len(slept) == 1


def test_read_raises_after_exhausting_retries(monkeypatch, creds):
    slept: list[float] = []
    calls = _patch_httpx(
        monkeypatch, [httpx.ConnectError("down")] * alpaca_client.RETRY_ATTEMPTS
    )
    with pytest.raises(AlpacaError):
        alpaca_client.get_positions(sleep=slept.append)
    assert len(calls) == alpaca_client.RETRY_ATTEMPTS
    assert len(slept) == alpaca_client.RETRY_ATTEMPTS - 1


def test_order_submission_is_never_retried(monkeypatch, creds):
    """Re-POSTing an order is not free the way re-GETting a balance is."""
    slept: list[float] = []
    calls = _patch_httpx(monkeypatch, [httpx.ConnectError("down")])
    with pytest.raises(AlpacaError):
        alpaca_client.submit_notional_order(
            symbol="AAPL", notional=10.0, side="buy", client_order_id="x", sleep=slept.append
        )
    assert len(calls) == 1
    assert slept == []


# --- order formatting ---------------------------------------------------------


def test_notional_order_body_matches_alpacas_documented_constraints(monkeypatch, creds):
    calls = _patch_httpx(monkeypatch, [_FakeResponse({"id": "abc", "status": "accepted"})])
    alpaca_client.submit_notional_order(
        symbol="AAPL", notional=123.456, side="buy", client_order_id="cid-1"
    )
    body = calls[0]["json"]
    assert body == {
        "symbol": "AAPL",
        "notional": "123.46",  # two decimals; sub-cent notionals are rejected
        "side": "buy",
        "type": "market",  # notional orders are market/day only
        "time_in_force": "day",
        "client_order_id": "cid-1",
    }
    assert calls[0]["url"].endswith("/orders")


def test_qty_order_body_is_whole_shares(monkeypatch, creds):
    """The only route Alpaca offers for opening a SHORT. Verified live against
    the real paper account: a notional short sell answers
    422 {"code":42210000,"message":"fractional orders cannot be sold short"},
    while the same order as whole shares is accepted."""
    calls = _patch_httpx(monkeypatch, [_FakeResponse({"id": "abc"})])
    alpaca_client.submit_qty_order(
        symbol="MSFT", qty=3.0, side="sell", client_order_id="cid-2"
    )
    assert calls[0]["json"]["qty"] == "3"
    assert calls[0]["json"]["side"] == "sell"


def test_get_open_orders_filters_by_status_and_symbol(monkeypatch, creds):
    calls = _patch_httpx(monkeypatch, [_FakeResponse([])])
    alpaca_client.get_open_orders("AAPL")
    assert calls[0]["params"] == {"status": "open", "symbols": "AAPL"}


def test_cancel_all_orders_issues_a_delete(monkeypatch, creds):
    calls = _patch_httpx(monkeypatch, [_FakeResponse([{"id": "1"}])])
    assert alpaca_client.cancel_all_orders() == [{"id": "1"}]
    assert calls[0]["method"] == "DELETE"


def test_http_error_body_is_surfaced_in_the_exception(monkeypatch, creds):
    _patch_httpx(monkeypatch, [_FakeResponse({"message": "insufficient qty"}, status_code=403)])
    with pytest.raises(AlpacaError, match="403"):
        alpaca_client.submit_notional_order(
            symbol="AAPL", notional=1.0, side="sell", client_order_id="c"
        )


# --- parsing ------------------------------------------------------------------


def test_account_numbers_arrive_as_strings_and_are_parsed():
    """Captured verbatim from the real paper account."""
    account = {"equity": "100000", "last_equity": "100000", "cash": "100000"}
    assert alpaca_client.account_float(account, "equity") == 100000.0


def test_missing_account_field_raises_rather_than_defaulting_to_zero():
    with pytest.raises(AlpacaError):
        alpaca_client.account_float({"equity": "1"}, "last_equity")


def test_long_position_signs():
    position = {"symbol": "AAPL", "side": "long", "qty": "10", "market_value": "1500.5"}
    assert alpaca_client.position_signed_market_value(position) == pytest.approx(1500.5)
    assert alpaca_client.position_signed_qty(position) == pytest.approx(10.0)


def test_short_position_sign_is_taken_from_side_not_from_the_numeric_sign():
    """Alpaca's API reference documents `side` as a long/short enum and says
    nothing about the sign of the numeric fields. Real payloads DO carry
    negative qty/market_value for shorts — so both conventions are exercised
    here, and both must yield a negative signed exposure."""
    negative_convention = {"symbol": "SLM", "side": "short", "qty": "-2478", "market_value": "-22078.98"}
    positive_convention = {"symbol": "SLM", "side": "short", "qty": "2478", "market_value": "22078.98"}

    for position in (negative_convention, positive_convention):
        assert alpaca_client.position_signed_market_value(position) == pytest.approx(-22078.98)
        assert alpaca_client.position_signed_qty(position) == pytest.approx(-2478.0)


def test_intraday_pnl_is_none_when_absent_rather_than_zero():
    assert alpaca_client.position_intraday_pnl({"symbol": "A"}) is None
    assert alpaca_client.position_intraday_pnl({"unrealized_intraday_pl": "-12.5"}) == pytest.approx(-12.5)
