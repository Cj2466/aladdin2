from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

import pandas as pd


class MarketDataError(Exception):
    """Raised when a market data provider fails to return usable price data."""


@dataclass
class TickerMetadataResult:
    sector: str | None
    industry: str | None
    asset_class: str | None
    currency: str | None


class MarketDataProvider(ABC):
    """A source of historical adjusted-close prices and ticker metadata.

    Kept as an abstract interface (rather than calling yfinance directly from
    the risk engine or router) so a fallback/alternate provider can be added
    later without touching risk math or route code.
    """

    @abstractmethod
    def get_price_history(
        self, tickers: list[str], start: date, end: date
    ) -> tuple[pd.DataFrame, list[str]]:
        """Return (prices, missing_tickers).

        prices: DataFrame indexed by date, one adjusted-close column per
        ticker that had usable data.
        missing_tickers: tickers requested but not present in the result.
        """
        raise NotImplementedError

    @abstractmethod
    def get_ticker_metadata(self, ticker: str) -> TickerMetadataResult | None:
        """Sector/industry/asset-class/currency for a single ticker, or None
        if no metadata is available (e.g. an invalid ticker)."""
        raise NotImplementedError
