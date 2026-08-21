from datetime import date

import pandas as pd
import yfinance as yf

from app.services.market_data.base import MarketDataError, MarketDataProvider, TickerMetadataResult

_QUOTE_TYPE_TO_ASSET_CLASS = {
    "EQUITY": "Equity",
    "ETF": "ETF",
    "MUTUALFUND": "Mutual Fund",
    "CRYPTOCURRENCY": "Crypto",
}


class YFinanceProvider(MarketDataProvider):
    """Fetches price history and ticker metadata from Yahoo Finance via the
    unofficial yfinance library. No caching in this class itself — the
    read-through caches in price_cache.py / metadata_cache.py sit in front
    of this same interface."""

    def get_price_history(
        self, tickers: list[str], start: date, end: date
    ) -> tuple[pd.DataFrame, list[str]]:
        try:
            raw = yf.download(
                tickers,
                start=start,
                end=end,
                auto_adjust=True,
                progress=False,
            )
        except Exception as exc:
            raise MarketDataError(f"Failed to fetch price data: {exc}") from exc

        if raw is None or raw.empty:
            raise MarketDataError(f"No price data returned for {tickers}")

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
            raise MarketDataError(f"No usable price data for {tickers}")

        missing = [t for t in tickers if t not in close.columns]
        return close, missing

    def get_ticker_metadata(self, ticker: str) -> TickerMetadataResult | None:
        try:
            info = yf.Ticker(ticker).info
        except Exception:
            return None

        if not info or info.get("quoteType") is None:
            return None

        return TickerMetadataResult(
            sector=info.get("sector"),
            industry=info.get("industry"),
            asset_class=_QUOTE_TYPE_TO_ASSET_CLASS.get(info.get("quoteType"), "Other"),
            currency=info.get("currency"),
        )
