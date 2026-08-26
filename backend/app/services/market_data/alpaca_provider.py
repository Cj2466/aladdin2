"""Read-only Alpaca HISTORICAL market-data client (Phase B pattern mining).

Scope, stated explicitly: this module talks to data.alpaca.markets only —
GET /v2/stocks/bars, nothing else. It deliberately contains NO order/
trading/execution capability (no POST /v2/orders, no account mutation of
any kind); the trading half of the original Phase 5 plan is a separate,
unbuilt module with its own safety architecture, and this file must never
grow into it by accident. Credentials come from Settings (pydantic-settings
reading .env), the same way finnhub_api_key/fred_api_key already do — never
hardcoded, never logged.

Why this exists (Phase B): yfinance's only intraday granularity with
enough free history to walk-forward against is hourly (~2 years, rolling —
see yfinance_provider.INTRADAY_ALLOWED_INTERVALS's comment). Alpaca's
historical bars endpoint provides minute-and-coarser bars back to at least
January 2021 (verified empirically with this exact account, real HTTP
calls, before this module was written), and returns full SIP
consolidated-tape data by default on this account (also verified
empirically: feed=iex gave AAPL 28,658 shares for one real minute in Jan
2021, feed=sip gave 3,806,856 for the same minute, and the unspecified
default matched sip exactly — this is NOT IEX-only data). feed="sip" is
passed explicitly anyway, below: if the account's data entitlement ever
changed, an explicit sip request fails loudly instead of silently
degrading to a thinner feed.

Not a MarketDataProvider subclass, deliberately: that ABC exists so a
fallback DAILY-close provider can be swapped in behind the risk engine
(get_price_history/get_ticker_metadata). This class has a genuinely
different shape — full OHLCV bars, dict-of-frames keyed by ticker, real
start/end windows at intraday granularity — exactly the "its own shape may
differ" case yfinance_provider.get_intraday_bars's own docstring already
anticipated for Phase B. Forcing the ABC onto it would mean implementing
two methods nothing calls.

Retry/backoff reuses yfinance_provider._call_with_retry (the codebase's
one retry precedent, per the Phase 5 plan's own "mirror it exactly"
instruction) — with a larger attempts/base_delay than yfinance's default,
sized for Alpaca's documented 200-requests/minute rate limit: yfinance's
3-attempts/~5s-total backoff cannot outlast a minute-window 429, while
5 attempts at base 2.0s (~30s+ of exponential backoff) usually can. In
practice serial paginated requests self-throttle well under 200/min, so
the 429 path is a safety net, not the expected path.
"""

import logging
from datetime import date
from datetime import time as dt_time

import httpx
import pandas as pd

from app.config import settings
from app.services.market_data.base import MarketDataError
from app.services.market_data.yfinance_provider import _call_with_retry

logger = logging.getLogger(__name__)


class AlpacaError(MarketDataError):
    """Alpaca-specific market-data failure. Subclasses MarketDataError so
    existing catch-sites treat it like any other provider failure; kept as
    its own class (matching the Phase 5 plan's AlpacaError convention) so
    Alpaca-specific handling stays possible without string-matching."""


ALPACA_DATA_BASE_URL = "https://data.alpaca.markets"

# The historical-bars timeframes this client supports. 1Min is the whole
# point of Phase B; the coarser steps let the same client serve the
# coarser-granularity screens (and daily bars for liquidity verification)
# without a second code path. Alpaca accepts other values (e.g. 3Min,
# 2Hour) — kept out until something needs them, same
# allowed-intervals-as-explicit-set convention as
# yfinance_provider.INTRADAY_ALLOWED_INTERVALS.
ALLOWED_TIMEFRAMES = {"1Min", "5Min", "15Min", "30Min", "1Hour", "1Day"}

# Alpaca's own documented per-response maximum. A multi-year multi-symbol
# request is ALWAYS larger than this — pagination via next_page_token is
# structural, not an edge case (verified empirically: one 10k-limit page
# of 1Min AAPL bars covers only ~25 trading days).
BARS_PAGE_LIMIT = 10_000

# Split-AND-dividend adjusted, matching the auto_adjust=True convention
# every yfinance fetch in this codebase already uses. Within-bar returns
# ((close-open)/open) are scale-invariant either way, but cross-bar
# lookbacks (RSI/MA/prior-day levels) would read an unadjusted split as a
# fake overnight crash.
DEFAULT_ADJUSTMENT = "all"
DEFAULT_FEED = "sip"

# Alpaca returns pre/post-market bars for intraday timeframes (04:00-20:00
# ET). Every downstream consumer (session-phase bucketing, session VWAP)
# assumes regular-trading-hours bars only, so RTH filtering defaults on.
# Bar timestamps are bar-START times: a regular-session bar starts at or
# after 09:30 and strictly before 16:00 ET.
REGULAR_SESSION_START = dt_time(9, 30)
REGULAR_SESSION_END = dt_time(16, 0)
MARKET_TZ = "America/New_York"

# See module docstring — sized for Alpaca's 200/min rate-limit window,
# unlike yfinance_provider's own 3/1.0 defaults.
ALPACA_RETRY_ATTEMPTS = 5
ALPACA_RETRY_BASE_DELAY_SECONDS = 2.0

# Chunk multi-symbol requests so URLs stay well-bounded and one bad chunk
# retries cheaply. Alpaca's endpoint accepts arbitrarily many symbols per
# request (pagination walks symbols alphabetically within the window).
SYMBOLS_PER_REQUEST = 100

REQUEST_TIMEOUT_SECONDS = 30.0

_OHLCV_KEY_TO_COLUMN = {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}


class AlpacaProvider:
    """Historical stock bars from Alpaca's data API. Read-only — see the
    module docstring for the explicit no-trading scope boundary."""

    def __init__(self, api_key: str | None = None, api_secret: str | None = None):
        self._api_key = api_key if api_key is not None else settings.alpaca_api_key
        self._api_secret = api_secret if api_secret is not None else settings.alpaca_api_secret

    def get_stock_bars(
        self,
        tickers: list[str],
        timeframe: str,
        start: date,
        end: date,
        *,
        regular_session_only: bool = True,
        feed: str = DEFAULT_FEED,
        adjustment: str = DEFAULT_ADJUSTMENT,
    ) -> tuple[dict[str, pd.DataFrame], list[str]]:
        """Full OHLCV bars for [start, end] (dates inclusive) at the given
        timeframe. Returns ({ticker: frame}, missing_tickers) — the same
        dict-of-frames shape as YFinanceProvider.get_intraday_bars (each
        frame: lowercase open/high/low/close/volume columns, tz-aware
        America/New_York DatetimeIndex, ascending), so downstream pattern
        code consumes either source unchanged. A requested ticker with no
        bars in the window (never listed, delisted, typo) lands in
        missing_tickers, mirroring the yfinance providers' missing-list
        convention rather than raising."""
        if not self._api_key or not self._api_secret:
            # Guard BEFORE any network call — mirrors the Phase 5 plan's
            # "missing credentials raise without any network call" test
            # requirement for its own client.
            raise AlpacaError(
                "Alpaca credentials are not configured (ALPACA_API_KEY / ALPACA_API_SECRET in .env)."
            )
        if timeframe not in ALLOWED_TIMEFRAMES:
            raise ValueError(
                f"Unsupported Alpaca timeframe {timeframe!r}; supported: {sorted(ALLOWED_TIMEFRAMES)}"
            )

        rows_by_ticker: dict[str, list[dict]] = {}
        try:
            with httpx.Client(
                base_url=ALPACA_DATA_BASE_URL,
                headers={
                    "APCA-API-KEY-ID": self._api_key,
                    "APCA-API-SECRET-KEY": self._api_secret,
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            ) as client:
                for chunk_start in range(0, len(tickers), SYMBOLS_PER_REQUEST):
                    chunk = tickers[chunk_start : chunk_start + SYMBOLS_PER_REQUEST]
                    self._fetch_chunk(
                        client, chunk, timeframe, start, end, feed, adjustment, rows_by_ticker
                    )
        except MarketDataError:
            raise
        except Exception as exc:
            raise AlpacaError(f"Failed to fetch Alpaca bars: {exc}") from exc

        bars_by_ticker: dict[str, pd.DataFrame] = {}
        for ticker, rows in rows_by_ticker.items():
            frame = self._rows_to_frame(rows)
            if regular_session_only and timeframe != "1Day":
                times = frame.index.time
                frame = frame[(times >= REGULAR_SESSION_START) & (times < REGULAR_SESSION_END)]
            if not frame.empty:
                bars_by_ticker[ticker] = frame

        missing = [t for t in tickers if t not in bars_by_ticker]
        return bars_by_ticker, missing

    def _fetch_chunk(
        self,
        client: httpx.Client,
        chunk: list[str],
        timeframe: str,
        start: date,
        end: date,
        feed: str,
        adjustment: str,
        rows_by_ticker: dict[str, list[dict]],
    ) -> None:
        """Walks EVERY page for one symbol chunk — Alpaca paginates large
        windows via next_page_token, and a single un-paginated request
        silently truncates to the first BARS_PAGE_LIMIT bars."""
        page_token: str | None = None
        while True:
            params: dict[str, str | int] = {
                "symbols": ",".join(chunk),
                "timeframe": timeframe,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": BARS_PAGE_LIMIT,
                "adjustment": adjustment,
                "feed": feed,
                "sort": "asc",
            }
            if page_token is not None:
                params["page_token"] = page_token

            def fetch_page(page_params: dict = params) -> dict:
                # Bound as a default (not a closure capture) so each loop
                # iteration's params are fixed at definition time.
                response = client.get("/v2/stocks/bars", params=page_params)
                response.raise_for_status()
                return response.json()

            payload = _call_with_retry(
                fetch_page,
                attempts=ALPACA_RETRY_ATTEMPTS,
                base_delay=ALPACA_RETRY_BASE_DELAY_SECONDS,
            )

            for symbol, bars in (payload.get("bars") or {}).items():
                rows_by_ticker.setdefault(symbol, []).extend(bars)

            page_token = payload.get("next_page_token")
            if not page_token:
                return

    @staticmethod
    def _rows_to_frame(rows: list[dict]) -> pd.DataFrame:
        frame = pd.DataFrame(rows)
        if frame.empty or "t" not in frame.columns:
            return pd.DataFrame()
        index = pd.to_datetime(frame["t"], utc=True).dt.tz_convert(MARKET_TZ)
        frame = frame.rename(columns=_OHLCV_KEY_TO_COLUMN)
        missing_fields = [c for c in _OHLCV_KEY_TO_COLUMN.values() if c not in frame.columns]
        if missing_fields:
            raise AlpacaError(f"Alpaca bar rows missing expected fields: {missing_fields}")
        frame = frame[list(_OHLCV_KEY_TO_COLUMN.values())].astype(float)
        frame.index = pd.DatetimeIndex(index, name="timestamp")
        return frame.sort_index()
