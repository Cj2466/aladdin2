import asyncio
import json
import logging
import random

import websockets
from websockets.exceptions import ConnectionClosed

from app.config import settings
from app.services.live_quotes.manager import LiveQuoteManager

logger = logging.getLogger(__name__)

FINNHUB_WS_URL = "wss://ws.finnhub.io"
MAX_BACKOFF_SECONDS = 30


class FinnhubWebSocketClient:
    """Owns the single upstream connection to Finnhub. Reconnects with
    backoff on any drop and, on every (re)connect, resubscribes to whatever
    the manager currently says is wanted — re-derived from live state, not a
    separately tracked list, so a reconnect can never subscribe to something
    stale or miss something new."""

    def __init__(self, manager: LiveQuoteManager) -> None:
        self._manager = manager
        self._connection: websockets.ClientConnection | None = None
        manager.set_upstream_sender(self.send)

    async def send(self, message: dict) -> None:
        if self._connection is None:
            return  # not connected right now; next reconnect resubscribes from manager state
        try:
            await self._connection.send(json.dumps(message))
        except ConnectionClosed:
            pass  # the run loop's reconnect handles this

    async def run(self) -> None:
        if not settings.finnhub_api_key:
            logger.warning("FINNHUB_API_KEY not set; live quotes disabled.")
            return

        url = f"{FINNHUB_WS_URL}?token={settings.finnhub_api_key}"
        attempt = 0
        while True:
            try:
                async with websockets.connect(url) as connection:
                    self._connection = connection
                    attempt = 0
                    await self._resubscribe_all()
                    async for raw in connection:
                        await self._handle_message(raw)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Finnhub websocket error; reconnecting.")
            finally:
                self._connection = None

            attempt += 1
            delay = min(MAX_BACKOFF_SECONDS, 2 ** (attempt - 1)) + random.uniform(0, 1)
            await asyncio.sleep(delay)

    async def _resubscribe_all(self) -> None:
        for ticker in self._manager.currently_wanted_tickers():
            await self.send({"type": "subscribe", "symbol": ticker})

    async def _handle_message(self, raw: str | bytes) -> None:
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            return
        if message.get("type") != "trade":
            return
        for trade in message.get("data") or []:
            ticker = trade.get("s")
            price = trade.get("p")
            if ticker is None or price is None:
                continue
            await self._manager.on_upstream_trade(ticker, price, trade.get("t") or 0)
