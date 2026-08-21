import time

import httpx

from app.config import settings
from app.services.live_quotes.market_hours import current_market_state
from app.services.live_quotes.state import QuoteState

FINNHUB_QUOTE_URL = "https://finnhub.io/api/v1/quote"


async def fetch_quote_snapshot(ticker: str) -> QuoteState | None:
    """One-shot REST snapshot, used to seed a ticker the instant it's first
    subscribed (before any trade ticks arrive over the websocket).

    Returns None if Finnhub has no data for this ticker. Finnhub's /quote
    signals "unknown symbol" with HTTP 200 and all-zero fields rather than
    an error status, so that's the check here rather than response.status_code.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            FINNHUB_QUOTE_URL,
            params={"symbol": ticker, "token": settings.finnhub_api_key},
        )
        response.raise_for_status()
        data = response.json()

    price = data.get("c") or 0.0
    previous_close = data.get("pc") or 0.0
    if price == 0.0 and previous_close == 0.0:
        return None

    change_percent = data.get("dp")
    if change_percent is None:
        change_percent = ((price - previous_close) / previous_close * 100) if previous_close else 0.0

    return QuoteState(
        price=price,
        previous_close=previous_close,
        change_percent=change_percent,
        market_state=current_market_state(),
        last_updated=time.time(),
    )
