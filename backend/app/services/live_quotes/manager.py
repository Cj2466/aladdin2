import asyncio
import time
from collections.abc import Awaitable, Callable

from fastapi import WebSocket

from app.services.live_quotes.finnhub_rest import fetch_quote_snapshot
from app.services.live_quotes.market_hours import current_market_state
from app.services.live_quotes.state import QuoteState

UpstreamSender = Callable[[dict], Awaitable[None]]


class LiveQuoteManager:
    """Fans out a single upstream Finnhub connection to N downstream browser
    WebSocket clients, ref-counted per ticker so Finnhub only gets a
    subscribe while at least one connected client wants that ticker.

    All mutation here happens between awaits (no `await` inside a
    check-then-act span on the shared dicts below), which is what makes this
    safe without an explicit lock under asyncio's single-threaded cooperative
    scheduling — two coroutines can interleave only at an `await` point.
    """

    def __init__(self) -> None:
        self.subscribers: dict[str, set[WebSocket]] = {}
        self.client_tickers: dict[WebSocket, set[str]] = {}
        self.client_queues: dict[WebSocket, asyncio.Queue] = {}
        self.snapshot_cache: dict[str, QuoteState] = {}
        self._upstream_send: UpstreamSender | None = None

    def set_upstream_sender(self, sender: UpstreamSender) -> None:
        self._upstream_send = sender

    def currently_wanted_tickers(self) -> set[str]:
        return set(self.subscribers.keys())

    def register(self, client: WebSocket) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self.client_queues[client] = queue
        self.client_tickers[client] = set()
        return queue

    async def subscribe(self, client: WebSocket, tickers: set[str]) -> None:
        previous = self.client_tickers.get(client, set())
        added = tickers - previous
        removed = previous - tickers
        self.client_tickers[client] = tickers

        for ticker in removed:
            await self._release(ticker, client)

        for ticker in added:
            is_first_subscriber = ticker not in self.subscribers
            self.subscribers.setdefault(ticker, set()).add(client)
            if is_first_subscriber:
                await self._activate_ticker(ticker)
            else:
                await self._send_cached(client, ticker)

        # Re-send cached state for anything the client re-requested, so a
        # resubscribe (e.g. after the frontend reconnects) gets a fresh view.
        for ticker in tickers & previous:
            await self._send_cached(client, ticker)

    async def unsubscribe_all(self, client: WebSocket) -> None:
        tickers = self.client_tickers.pop(client, set())
        self.client_queues.pop(client, None)
        for ticker in list(tickers):
            await self._release(ticker, client, already_removed_from_client=True)

    async def on_upstream_trade(self, ticker: str, price: float, timestamp_ms: int) -> None:
        state = self.snapshot_cache.get(ticker)
        if state is None:
            return  # a trade for a ticker nobody local is tracking anymore; ignore
        previous_close = state.previous_close
        change_percent = ((price - previous_close) / previous_close * 100) if previous_close else 0.0
        self.snapshot_cache[ticker] = QuoteState(
            price=price,
            previous_close=previous_close,
            change_percent=change_percent,
            market_state=current_market_state(),
            last_updated=(timestamp_ms / 1000) if timestamp_ms else time.time(),
        )
        await self._broadcast(ticker, "tick")

    async def _release(self, ticker: str, client: WebSocket, *, already_removed_from_client: bool = False) -> None:
        if not already_removed_from_client:
            self.client_tickers.get(client, set()).discard(ticker)
        subs = self.subscribers.get(ticker)
        if not subs:
            return
        subs.discard(client)
        if not subs:
            del self.subscribers[ticker]
            self.snapshot_cache.pop(ticker, None)
            await self._upstream_send_safe({"type": "unsubscribe", "symbol": ticker})

    async def _activate_ticker(self, ticker: str) -> None:
        snapshot = await fetch_quote_snapshot(ticker)

        if ticker not in self.subscribers:
            return  # everyone interested already unsubscribed while this REST call was in flight

        if snapshot is None:
            for client in list(self.subscribers.get(ticker, set())):
                await self._send(client, {"type": "error", "ticker": ticker, "code": "invalid_ticker",
                                           "message": f"No quote data available for {ticker}"})
                self.client_tickers.get(client, set()).discard(ticker)
            self.subscribers.pop(ticker, None)
            return

        self.snapshot_cache[ticker] = snapshot
        await self._broadcast(ticker, "snapshot")
        await self._upstream_send_safe({"type": "subscribe", "symbol": ticker})

    async def _send_cached(self, client: WebSocket, ticker: str) -> None:
        state = self.snapshot_cache.get(ticker)
        if state is not None:
            await self._send(client, self._quote_message("snapshot", ticker, state))
        # else: activation is still in flight (or the ticker turned out invalid
        # and was already reported) — nothing to send yet.

    async def _broadcast(self, ticker: str, msg_type: str) -> None:
        state = self.snapshot_cache.get(ticker)
        if state is None:
            return
        message = self._quote_message(msg_type, ticker, state)
        for client in list(self.subscribers.get(ticker, set())):
            await self._send(client, message)

    async def _send(self, client: WebSocket, message: dict) -> None:
        queue = self.client_queues.get(client)
        if queue is not None:
            await queue.put(message)

    async def _upstream_send_safe(self, message: dict) -> None:
        if self._upstream_send is not None:
            await self._upstream_send(message)

    @staticmethod
    def _quote_message(msg_type: str, ticker: str, state: QuoteState) -> dict:
        return {
            "type": msg_type,
            "ticker": ticker,
            "price": state.price,
            "previous_close": state.previous_close,
            "change_percent": state.change_percent,
            "market_state": state.market_state,
            "last_updated": state.last_updated,
            "status": "ok",
        }


live_quote_manager = LiveQuoteManager()
