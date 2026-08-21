import pytest

from app.services.live_quotes.manager import LiveQuoteManager
from app.services.live_quotes.state import QuoteState


def make_quote(price=100.0, previous_close=99.0) -> QuoteState:
    return QuoteState(
        price=price,
        previous_close=previous_close,
        change_percent=(price - previous_close) / previous_close * 100,
        market_state="open",
        last_updated=1000.0,
    )


@pytest.fixture
def manager(monkeypatch):
    mgr = LiveQuoteManager()
    upstream_calls: list[dict] = []

    async def fake_upstream_send(message: dict) -> None:
        upstream_calls.append(message)

    mgr.set_upstream_sender(fake_upstream_send)
    mgr._upstream_calls = upstream_calls  # test-only attribute
    return mgr


def drain(queue) -> list[dict]:
    messages = []
    while not queue.empty():
        messages.append(queue.get_nowait())
    return messages


async def test_first_subscriber_activates_ticker_and_subscribes_upstream(manager, monkeypatch):
    monkeypatch.setattr(
        "app.services.live_quotes.manager.fetch_quote_snapshot",
        lambda ticker: _resolved(make_quote()),
    )
    client = object()
    queue = manager.register(client)

    await manager.subscribe(client, {"AAPL"})

    messages = drain(queue)
    assert len(messages) == 1
    assert messages[0]["type"] == "snapshot"
    assert messages[0]["ticker"] == "AAPL"
    assert manager._upstream_calls == [{"type": "subscribe", "symbol": "AAPL"}]


async def test_second_subscriber_uses_cache_no_refetch_no_resubscribe(manager, monkeypatch):
    fetch_calls = []

    async def fake_fetch(ticker):
        fetch_calls.append(ticker)
        return make_quote()

    monkeypatch.setattr("app.services.live_quotes.manager.fetch_quote_snapshot", fake_fetch)

    client_a = object()
    client_b = object()
    manager.register(client_a)
    queue_b = manager.register(client_b)

    await manager.subscribe(client_a, {"AAPL"})
    await manager.subscribe(client_b, {"AAPL"})

    assert fetch_calls == ["AAPL"]  # only fetched once
    assert manager._upstream_calls == [{"type": "subscribe", "symbol": "AAPL"}]  # only subscribed once
    messages = drain(queue_b)
    assert any(m["type"] == "snapshot" and m["ticker"] == "AAPL" for m in messages)


async def test_last_unsubscribe_sends_upstream_unsubscribe(manager, monkeypatch):
    monkeypatch.setattr(
        "app.services.live_quotes.manager.fetch_quote_snapshot",
        lambda ticker: _resolved(make_quote()),
    )
    client = object()
    manager.register(client)
    await manager.subscribe(client, {"AAPL"})

    await manager.subscribe(client, set())  # drop AAPL

    assert manager._upstream_calls[-1] == {"type": "unsubscribe", "symbol": "AAPL"}
    assert "AAPL" not in manager.subscribers
    assert "AAPL" not in manager.snapshot_cache


async def test_invalid_ticker_sends_error_and_never_subscribes_upstream(manager, monkeypatch):
    monkeypatch.setattr(
        "app.services.live_quotes.manager.fetch_quote_snapshot",
        lambda ticker: _resolved(None),
    )
    client = object()
    queue = manager.register(client)

    await manager.subscribe(client, {"ZZZZ"})

    messages = drain(queue)
    assert len(messages) == 1
    assert messages[0] == {
        "type": "error",
        "ticker": "ZZZZ",
        "code": "invalid_ticker",
        "message": "No quote data available for ZZZZ",
    }
    assert manager._upstream_calls == []
    assert "ZZZZ" not in manager.subscribers


async def test_on_upstream_trade_updates_cache_and_broadcasts_tick(manager, monkeypatch):
    monkeypatch.setattr(
        "app.services.live_quotes.manager.fetch_quote_snapshot",
        lambda ticker: _resolved(make_quote(price=100.0, previous_close=100.0)),
    )
    client = object()
    queue = manager.register(client)
    await manager.subscribe(client, {"AAPL"})
    drain(queue)  # discard the initial snapshot

    await manager.on_upstream_trade("AAPL", 105.0, 1234567890000)

    messages = drain(queue)
    assert len(messages) == 1
    assert messages[0]["type"] == "tick"
    assert messages[0]["price"] == 105.0
    assert messages[0]["change_percent"] == pytest.approx(5.0)


async def test_on_upstream_trade_ignores_untracked_ticker(manager):
    # No subscriber has ever activated MSFT — must be a silent no-op.
    await manager.on_upstream_trade("MSFT", 300.0, 1234567890000)
    assert "MSFT" not in manager.snapshot_cache


async def test_unsubscribe_all_cleans_up_client_state(manager, monkeypatch):
    monkeypatch.setattr(
        "app.services.live_quotes.manager.fetch_quote_snapshot",
        lambda ticker: _resolved(make_quote()),
    )
    client = object()
    manager.register(client)
    await manager.subscribe(client, {"AAPL", "MSFT"})

    await manager.unsubscribe_all(client)

    assert client not in manager.client_tickers
    assert client not in manager.client_queues
    assert "AAPL" not in manager.subscribers
    assert "MSFT" not in manager.subscribers
    assert {"type": "unsubscribe", "symbol": "AAPL"} in manager._upstream_calls
    assert {"type": "unsubscribe", "symbol": "MSFT"} in manager._upstream_calls


async def _resolved(value):
    return value
