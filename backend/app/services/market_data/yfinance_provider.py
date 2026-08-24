import random
import time
from collections.abc import Callable
from datetime import date
from typing import TypeVar

import pandas as pd
import yfinance as yf

from app.services.market_data.base import MarketDataError, MarketDataProvider, TickerMetadataResult

T = TypeVar("T")

RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 1.0


def _call_with_retry(
    fn: Callable[[], T],
    *,
    attempts: int = RETRY_ATTEMPTS,
    base_delay: float = RETRY_BASE_DELAY_SECONDS,
    sleep: Callable[[float], None] | None = None,
) -> T:
    """Same exponential-backoff-with-jitter shape as
    FinnhubWebSocketClient.run's reconnect delay — the one existing
    retry precedent in this codebase. yfinance is an unofficial,
    scraping-based API with no retry logic of its own; a transient
    failure previously failed the whole caller immediately.

    `sleep` defaults to None (resolved to time.sleep on each call, not
    bound as a parameter default) so tests can monkeypatch this module's
    `time.sleep` and have it take effect — a bound default would capture
    the original function at import time, before any patch applies."""
    sleep_fn = sleep if sleep is not None else time.sleep
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception:
            if attempt == attempts:
                raise
            sleep_fn(base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1))
    raise AssertionError("unreachable")  # loop always returns or raises

# Individual/CUSIP-level bonds have no practical yfinance coverage, and
# options need a greeks/IV risk model this variance-based engine doesn't
# implement — both are deliberately left unmapped (fall through to "Other").
_QUOTE_TYPE_TO_ASSET_CLASS = {
    "EQUITY": "Equity",
    "ETF": "ETF",
    "MUTUALFUND": "Mutual Fund",
    "CRYPTOCURRENCY": "Crypto",
}

_BOND_KEYWORDS = ("bond", "fixed income", "fixed-income", "treasury")


def _is_bond_etf(info: dict) -> bool:
    # yfinance's `category` field is inconsistently populated across ETF
    # issuers, so fall back to the fund name as a second signal.
    haystack = " ".join(
        str(info.get(field) or "").lower() for field in ("category", "longName", "shortName")
    )
    return any(keyword in haystack for keyword in _BOND_KEYWORDS)


class YFinanceProvider(MarketDataProvider):
    """Fetches price history and ticker metadata from Yahoo Finance via the
    unofficial yfinance library. No caching in this class itself — the
    read-through caches in price_cache.py / metadata_cache.py sit in front
    of this same interface."""

    def get_price_history(
        self, tickers: list[str], start: date, end: date
    ) -> tuple[pd.DataFrame, list[str]]:
        try:
            raw = _call_with_retry(
                lambda: yf.download(
                    tickers,
                    start=start,
                    end=end,
                    auto_adjust=True,
                    progress=False,
                )
            )
        except Exception as exc:
            raise MarketDataError(f"Failed to fetch price data: {exc}") from exc

        if raw is None or raw.empty:
            # A genuine connectivity/upstream failure already raised above,
            # inside the try block — reaching here with an empty frame means
            # yfinance responded successfully but none of the requested
            # tickers resolved (typo, delisted, never listed). That's the
            # same "missing ticker" case the partial-invalid path below
            # already handles via the `missing` list, not a MarketDataError
            # — unify them rather than treating "0 of N tickers resolved"
            # as categorically different from "N-1 of N", which previously
            # surfaced as an inconsistent 502 instead of a 422.
            return pd.DataFrame(), list(tickers)

        if isinstance(raw.columns, pd.MultiIndex):
            if "Close" not in raw.columns.get_level_values(0):
                raise MarketDataError(f"Unexpected data shape for {tickers}")
            close = raw["Close"]
        else:
            # Some yfinance versions collapse to flat columns for a single ticker.
            if "Close" not in raw.columns:
                raise MarketDataError(f"Unexpected data shape for {tickers}")
            close = raw[["Close"]]
            close.columns = tickers

        # Drop any ticker column that came back entirely empty (bad/delisted
        # ticker, or a request yfinance silently failed on).
        close = close.dropna(axis=1, how="all")
        close = close.dropna(axis=0, how="all")

        if close.empty:
            # Same reasoning as above — every column was entirely NaN after
            # cleaning, i.e. every ticker is missing, not an upstream failure.
            return pd.DataFrame(), list(tickers)

        missing = [t for t in tickers if t not in close.columns]
        return close, missing

    def get_ticker_metadata(self, ticker: str) -> TickerMetadataResult | None:
        try:
            info = _call_with_retry(lambda: yf.Ticker(ticker).info)
        except Exception:
            return None

        if not info or info.get("quoteType") is None:
            return None

        quote_type = info.get("quoteType")
        asset_class = _QUOTE_TYPE_TO_ASSET_CLASS.get(quote_type, "Other")
        if quote_type == "ETF" and _is_bond_etf(info):
            asset_class = "Bond"

        return TickerMetadataResult(
            sector=info.get("sector"),
            industry=info.get("industry"),
            asset_class=asset_class,
            currency=info.get("currency"),
        )
