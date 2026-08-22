from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.services.market_data.base import MarketDataError
from app.services.market_data.yfinance_provider import YFinanceProvider


def _mock_ticker_info(info: dict):
    mock_ticker = MagicMock()
    mock_ticker.info = info
    return patch("yfinance.Ticker", return_value=mock_ticker)


def test_equity_classified_as_equity():
    info = {"quoteType": "EQUITY", "sector": "Technology", "industry": "Consumer Electronics", "currency": "USD"}
    with _mock_ticker_info(info):
        result = YFinanceProvider().get_ticker_metadata("AAPL")
    assert result.asset_class == "Equity"
    assert result.sector == "Technology"


def test_plain_etf_stays_etf():
    info = {"quoteType": "ETF", "category": "Large Blend", "longName": "SPDR S&P 500 ETF Trust"}
    with _mock_ticker_info(info):
        result = YFinanceProvider().get_ticker_metadata("SPY")
    assert result.asset_class == "ETF"


def test_bond_etf_classified_via_category():
    info = {"quoteType": "ETF", "category": "Intermediate Core-Plus Bond", "longName": "iShares Core Total USD Bond Market ETF"}
    with _mock_ticker_info(info):
        result = YFinanceProvider().get_ticker_metadata("AGG")
    assert result.asset_class == "Bond"


def test_bond_etf_classified_via_name_when_category_missing():
    info = {"quoteType": "ETF", "category": None, "longName": "iShares 20+ Year Treasury Bond ETF"}
    with _mock_ticker_info(info):
        result = YFinanceProvider().get_ticker_metadata("TLT")
    assert result.asset_class == "Bond"


def test_crypto_classified_as_crypto():
    info = {"quoteType": "CRYPTOCURRENCY", "currency": "USD"}
    with _mock_ticker_info(info):
        result = YFinanceProvider().get_ticker_metadata("BTC-USD")
    assert result.asset_class == "Crypto"


def test_unmapped_quote_type_falls_back_to_other():
    info = {"quoteType": "FUTURE"}
    with _mock_ticker_info(info):
        result = YFinanceProvider().get_ticker_metadata("ES=F")
    assert result.asset_class == "Other"


def test_all_tickers_invalid_reports_missing_not_market_data_error():
    """Regression test: previously raised MarketDataError (a 502 at the API
    boundary) whenever every requested ticker came back empty — including
    the common case of a single nonexistent/mistyped ticker. That's not an
    upstream failure, it's the same "ticker doesn't exist" case a *partial*
    batch of invalid tickers already reports via the `missing` list
    (surfaced as a 422 MissingTickerDataError by the caller). Both cases
    must now behave identically."""
    with patch("yfinance.download", return_value=pd.DataFrame()):
        prices, missing = YFinanceProvider().get_price_history(
            ["ZZZQQXX"], date(2024, 1, 1), date(2024, 1, 31)
        )
    assert prices.empty
    assert missing == ["ZZZQQXX"]


def test_network_failure_still_raises_market_data_error():
    with patch("yfinance.download", side_effect=ConnectionError("boom")):
        with pytest.raises(MarketDataError):
            YFinanceProvider().get_price_history(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))
