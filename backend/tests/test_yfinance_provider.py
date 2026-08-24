from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.services.market_data.base import MarketDataError
from app.services.market_data.yfinance_provider import RETRY_ATTEMPTS, YFinanceProvider, _call_with_retry


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    """Retry backoff would otherwise add real multi-second delays to every
    test exercising the network-failure/retry paths below."""
    monkeypatch.setattr("app.services.market_data.yfinance_provider.time.sleep", lambda _seconds: None)


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


def test_get_price_history_retries_and_succeeds_on_third_attempt():
    good_frame = pd.DataFrame({"Close": [100.0, 101.0]}, index=pd.date_range("2024-01-02", periods=2))
    with patch("yfinance.download", side_effect=[ConnectionError("boom"), ConnectionError("boom"), good_frame]) as mock_download:
        prices, missing = YFinanceProvider().get_price_history(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))
    assert mock_download.call_count == 3
    assert missing == []
    assert not prices.empty


def test_get_price_history_raises_market_data_error_after_exhausting_all_attempts():
    with patch("yfinance.download", side_effect=ConnectionError("boom")) as mock_download:
        with pytest.raises(MarketDataError):
            YFinanceProvider().get_price_history(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))
    assert mock_download.call_count == RETRY_ATTEMPTS


def test_get_ticker_metadata_retries_and_succeeds():
    mock_ticker = MagicMock()
    mock_ticker.info = {"quoteType": "EQUITY", "sector": "Technology"}
    with patch("yfinance.Ticker", side_effect=[ConnectionError("boom"), ConnectionError("boom"), mock_ticker]):
        result = YFinanceProvider().get_ticker_metadata("AAPL")
    assert result is not None
    assert result.asset_class == "Equity"


def test_get_ticker_metadata_returns_none_after_exhausting_retries():
    with patch("yfinance.Ticker", side_effect=ConnectionError("boom")) as mock_ticker_cls:
        result = YFinanceProvider().get_ticker_metadata("AAPL")
    assert result is None
    assert mock_ticker_cls.call_count == RETRY_ATTEMPTS


def test_call_with_retry_backoff_is_exponential_with_jitter():
    delays = []
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("transient")
        return "ok"

    result = _call_with_retry(flaky, attempts=3, base_delay=1.0, sleep=delays.append)

    assert result == "ok"
    assert len(delays) == 2
    assert 1.0 <= delays[0] < 2.0  # base_delay * 2^0 + jitter[0,1)
    assert 2.0 <= delays[1] < 3.0  # base_delay * 2^1 + jitter[0,1)


def test_call_with_retry_reraises_after_exhausting_attempts():
    def always_fails():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        _call_with_retry(always_fails, attempts=3, base_delay=0.0, sleep=lambda _s: None)
