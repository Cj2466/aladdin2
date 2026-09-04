from datetime import date
from unittest.mock import MagicMock, patch

import numpy as np
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


# --- get_intraday_bars ------------------------------------------------------


def _multiindex_ohlcv_frame(tickers: list[str], n_bars: int = 14) -> pd.DataFrame:
    """Mocks yf.download's real MultiIndex(field, ticker) shape for
    interval="60m" — matches the actual live structure confirmed
    2026-08-25 (columns named ['Price','Ticker'], level 0 = field)."""
    index = pd.date_range("2024-01-02 09:30", periods=n_bars, freq="h", tz="America/New_York")
    fields = ["Close", "High", "Low", "Open", "Volume"]
    columns = pd.MultiIndex.from_product([fields, tickers], names=["Price", "Ticker"])
    data = {}
    for field in fields:
        for ticker in tickers:
            base = 100.0 + hash((field, ticker)) % 5
            data[(field, ticker)] = np.linspace(base, base + 1, n_bars)
    return pd.DataFrame(data, index=index, columns=columns)


def test_get_intraday_bars_happy_path_returns_lowercase_ohlcv_per_ticker():
    frame = _multiindex_ohlcv_frame(["AAPL", "MSFT"])
    with patch("yfinance.download", return_value=frame):
        bars_by_ticker, missing = YFinanceProvider().get_intraday_bars(["AAPL", "MSFT"])
    assert missing == []
    assert set(bars_by_ticker) == {"AAPL", "MSFT"}
    assert list(bars_by_ticker["AAPL"].columns) == ["open", "high", "low", "close", "volume"]
    assert isinstance(bars_by_ticker["AAPL"].index, pd.DatetimeIndex)
    assert bars_by_ticker["AAPL"].index.tz is not None


def test_get_intraday_bars_excludes_all_nan_ticker_as_missing():
    frame = _multiindex_ohlcv_frame(["AAPL", "BADTICKER"])
    for field in ["Close", "High", "Low", "Open", "Volume"]:
        frame[(field, "BADTICKER")] = np.nan
    with patch("yfinance.download", return_value=frame):
        bars_by_ticker, missing = YFinanceProvider().get_intraday_bars(["AAPL", "BADTICKER"])
    assert set(bars_by_ticker) == {"AAPL"}
    assert missing == ["BADTICKER"]


def test_get_intraday_bars_empty_response_reports_all_missing():
    with patch("yfinance.download", return_value=pd.DataFrame()):
        bars_by_ticker, missing = YFinanceProvider().get_intraday_bars(["ZZZQQXX"])
    assert bars_by_ticker == {}
    assert missing == ["ZZZQQXX"]


def test_get_intraday_bars_network_failure_raises_market_data_error():
    with patch("yfinance.download", side_effect=ConnectionError("boom")):
        with pytest.raises(MarketDataError):
            YFinanceProvider().get_intraday_bars(["AAPL"])


def test_get_intraday_bars_retries_and_succeeds_on_third_attempt():
    frame = _multiindex_ohlcv_frame(["AAPL"])
    with patch(
        "yfinance.download", side_effect=[ConnectionError("boom"), ConnectionError("boom"), frame]
    ) as mock_download:
        bars_by_ticker, missing = YFinanceProvider().get_intraday_bars(["AAPL"])
    assert mock_download.call_count == 3
    assert missing == []
    assert "AAPL" in bars_by_ticker


def test_get_intraday_bars_rejects_unsupported_interval_without_network_call():
    with patch("yfinance.download") as mock_download:
        with pytest.raises(ValueError):
            YFinanceProvider().get_intraday_bars(["AAPL"], interval="5m")
    mock_download.assert_not_called()


def test_get_intraday_bars_accepts_1h_alias():
    frame = _multiindex_ohlcv_frame(["AAPL"])
    with patch("yfinance.download", return_value=frame) as mock_download:
        bars_by_ticker, missing = YFinanceProvider().get_intraday_bars(["AAPL"], interval="1h")
    assert mock_download.call_args.kwargs["interval"] == "1h"
    assert "AAPL" in bars_by_ticker


def test_get_intraday_bars_always_requests_period_max():
    frame = _multiindex_ohlcv_frame(["AAPL"])
    with patch("yfinance.download", return_value=frame) as mock_download:
        YFinanceProvider().get_intraday_bars(["AAPL"])
    assert mock_download.call_args.kwargs["period"] == "max"


def test_get_intraday_bars_unexpected_shape_raises_market_data_error():
    bad_frame = pd.DataFrame({"Nonsense": [1, 2, 3]})
    with patch("yfinance.download", return_value=bad_frame):
        with pytest.raises(MarketDataError):
            YFinanceProvider().get_intraday_bars(["AAPL"])


# --- get_daily_ohlcv --------------------------------------------------------


def _daily_multiindex_frame(tickers: list[str], n_days: int = 10) -> pd.DataFrame:
    """Mocks yf.download's MultiIndex(field, ticker) shape for a daily
    interval — same structure as _multiindex_ohlcv_frame, daily index."""
    index = pd.bdate_range("2024-01-02", periods=n_days)
    fields = ["Close", "High", "Low", "Open", "Volume"]
    columns = pd.MultiIndex.from_product([fields, tickers], names=["Price", "Ticker"])
    data = {}
    for field in fields:
        for ticker in tickers:
            base = 100.0 + hash((field, ticker)) % 5
            data[(field, ticker)] = np.linspace(base, base + 1, n_days)
    return pd.DataFrame(data, index=index, columns=columns)


def test_get_daily_ohlcv_happy_path_returns_five_aligned_wide_frames():
    frame = _daily_multiindex_frame(["AAPL", "MSFT"])
    with patch("yfinance.download", return_value=frame):
        frames, missing = YFinanceProvider().get_daily_ohlcv(
            ["AAPL", "MSFT"], date(2024, 1, 1), date(2024, 1, 31)
        )
    assert missing == []
    assert set(frames) == {"open", "high", "low", "close", "volume"}
    for key in ("open", "high", "low", "volume"):
        assert frames[key].index.equals(frames["close"].index)
        assert frames[key].columns.equals(frames["close"].columns)
    assert set(frames["close"].columns) == {"AAPL", "MSFT"}


def test_get_daily_ohlcv_missing_defined_by_close_availability():
    frame = _daily_multiindex_frame(["AAPL", "BADTICKER"])
    for field in ["Close", "High", "Low", "Open", "Volume"]:
        frame[(field, "BADTICKER")] = np.nan
    with patch("yfinance.download", return_value=frame):
        frames, missing = YFinanceProvider().get_daily_ohlcv(
            ["AAPL", "BADTICKER"], date(2024, 1, 1), date(2024, 1, 31)
        )
    assert missing == ["BADTICKER"]
    assert list(frames["close"].columns) == ["AAPL"]


def test_get_daily_ohlcv_sparse_open_survives_as_nan_not_dropped():
    # A ticker with a full Close but a gappy Open must stay in the result
    # (Close availability defines the ticker set) with NaN opens the signal
    # fns' own min-observation gates then handle.
    frame = _daily_multiindex_frame(["AAPL", "MSFT"])
    frame.loc[frame.index[3:6], ("Open", "MSFT")] = np.nan
    with patch("yfinance.download", return_value=frame):
        frames, missing = YFinanceProvider().get_daily_ohlcv(
            ["AAPL", "MSFT"], date(2024, 1, 1), date(2024, 1, 31)
        )
    assert missing == []
    assert frames["open"]["MSFT"].isna().sum() == 3
    assert frames["close"]["MSFT"].notna().all()


def test_get_daily_ohlcv_empty_response_reports_all_missing():
    with patch("yfinance.download", return_value=pd.DataFrame()):
        frames, missing = YFinanceProvider().get_daily_ohlcv(
            ["ZZZQQXX"], date(2024, 1, 1), date(2024, 1, 31)
        )
    assert frames == {}
    assert missing == ["ZZZQQXX"]


def test_get_daily_ohlcv_network_failure_raises_market_data_error():
    with patch("yfinance.download", side_effect=ConnectionError("boom")):
        with pytest.raises(MarketDataError):
            YFinanceProvider().get_daily_ohlcv(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))


def test_get_daily_ohlcv_requests_raw_prices_and_actions_over_the_window():
    """The request shape INVERTED when the point-in-time price store landed,
    and that inversion is the whole fix rather than an incidental refactor:
    the provider now asks for the vendor's INPUTS (unadjusted prices plus the
    dividend and split series) and computes the adjusted panel itself, where
    it used to ask for the vendor's already-adjusted OUTPUT — a derived
    opinion Yahoo silently recomputes over time (see price_store.py section
    1). Open and Close still end up on one basis, which is what the old
    auto_adjust=True assertion was really protecting; that property is now
    pinned directly by
    test_price_store.py::test_ohlc_share_one_total_return_factor_...."""
    frame = _daily_multiindex_frame(["AAPL"])
    with patch("yfinance.download", return_value=frame) as mock_download:
        YFinanceProvider().get_daily_ohlcv(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))
    kwargs = mock_download.call_args.kwargs
    assert kwargs["auto_adjust"] is False
    assert kwargs["actions"] is True
    assert kwargs["start"] == date(2024, 1, 1)
    assert kwargs["end"] == date(2024, 1, 31)


def test_get_daily_ohlcv_replays_the_store_without_a_second_network_call():
    """The operational form of the reproducibility guarantee: once a fixed
    historical window is stored, re-requesting it makes NO network call, so
    it cannot pick up a revised price."""
    frame = _daily_multiindex_frame(["AAPL"])
    provider = YFinanceProvider()
    with patch("yfinance.download", return_value=frame) as mock_download:
        first, _ = provider.get_daily_ohlcv(["AAPL"], date(2024, 1, 1), date(2024, 1, 16))
        assert mock_download.call_count == 1
        second, _ = provider.get_daily_ohlcv(["AAPL"], date(2024, 1, 1), date(2024, 1, 16))
        assert mock_download.call_count == 1

    for field in ("open", "high", "low", "close", "volume"):
        pd.testing.assert_frame_equal(first[field], second[field])
    assert provider.last_store_report.tickers_fetched == 0


def test_a_revised_upstream_price_cannot_change_an_already_stored_window():
    """The end-to-end version of price_store's first-write-wins policy,
    through the public provider API: Yahoo returning DIFFERENT numbers for an
    identical historical window on a later call must not change what the
    window returns."""
    original = _daily_multiindex_frame(["AAPL"])
    provider = YFinanceProvider()
    with patch("yfinance.download", return_value=original):
        first, _ = provider.get_daily_ohlcv(["AAPL"], date(2024, 1, 1), date(2024, 1, 16))

    revised = original * 1.05
    # Widen the request so coverage misses and a refetch is genuinely made.
    with patch("yfinance.download", return_value=revised) as mock_download:
        second, _ = provider.get_daily_ohlcv(["AAPL"], date(2023, 12, 1), date(2024, 1, 16))
        assert mock_download.call_count == 1

    overlap = first["close"].index.intersection(second["close"].index)
    for field in ("open", "high", "low", "close", "volume"):
        pd.testing.assert_frame_equal(first[field].loc[overlap], second[field].loc[overlap])
    assert provider.last_store_report.revisions


def test_get_daily_ohlcv_unexpected_shape_raises_market_data_error():
    bad_frame = pd.DataFrame({"Nonsense": [1, 2, 3]})
    with patch("yfinance.download", return_value=bad_frame):
        with pytest.raises(MarketDataError):
            YFinanceProvider().get_daily_ohlcv(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))


# --- get_shares_outstanding (Build D1) --------------------------------------


def _mock_ticker_shares(shares_by_ticker: dict):
    """patch("yfinance.Ticker") with a per-ticker-symbol factory, mirroring
    get_shares_outstanding's own per-ticker yf.Ticker(t).get_shares_full(...)
    call shape (unlike yf.download, there is no batch form here — see that
    method's own docstring)."""

    def factory(ticker_symbol):
        mock_ticker = MagicMock()
        mock_ticker.get_shares_full.return_value = shares_by_ticker.get(ticker_symbol)
        return mock_ticker

    return patch("yfinance.Ticker", side_effect=factory)


def test_get_shares_outstanding_dedupes_keeping_last_and_strips_timezone():
    # Mirrors the real, live-confirmed yfinance quirk this method's own
    # docstring documents: get_shares_full can return an exact-duplicate
    # date with two different share counts (a preliminary vs. corrected
    # filing) — the corrected (LAST, after sorting) value must survive.
    idx = pd.DatetimeIndex(["2024-01-03", "2024-01-04", "2024-01-04"], tz="America/New_York")
    raw = pd.Series([1_000.0, 2_000.0, 2_500.0], index=idx)
    with _mock_ticker_shares({"AAPL": raw}):
        shares, missing = YFinanceProvider().get_shares_outstanding(
            ["AAPL"], date(2024, 1, 1), date(2024, 1, 10)
        )
    assert missing == []
    result = shares["AAPL"]
    assert result.index.tz is None  # stripped to match get_daily_ohlcv's tz-naive close index
    assert list(result.index.date) == [date(2024, 1, 3), date(2024, 1, 4)]
    assert result.iloc[0] == pytest.approx(1_000.0)
    assert result.iloc[1] == pytest.approx(2_500.0)  # the LAST of the duplicate pair, not the first


def test_get_shares_outstanding_none_result_is_reported_missing():
    # get_shares_full itself returns None (not raises) for an unresolvable
    # ticker — confirmed live 2026-08-26 for a nonexistent symbol.
    with _mock_ticker_shares({"BADTICKER": None}):
        shares, missing = YFinanceProvider().get_shares_outstanding(
            ["BADTICKER"], date(2024, 1, 1), date(2024, 2, 1)
        )
    assert shares == {}
    assert missing == ["BADTICKER"]


def test_get_shares_outstanding_empty_series_is_reported_missing():
    empty = pd.Series([], index=pd.DatetimeIndex([], tz="America/New_York"), dtype=float)
    with _mock_ticker_shares({"NEWIPO": empty}):
        shares, missing = YFinanceProvider().get_shares_outstanding(
            ["NEWIPO"], date(2024, 1, 1), date(2024, 2, 1)
        )
    assert shares == {}
    assert missing == ["NEWIPO"]


def test_get_shares_outstanding_retries_and_succeeds_on_third_attempt():
    good = pd.Series([1_000.0], index=pd.DatetimeIndex(["2024-01-03"], tz="America/New_York"))
    mock_ticker = MagicMock()
    mock_ticker.get_shares_full.side_effect = [ConnectionError("boom"), ConnectionError("boom"), good]
    with patch("yfinance.Ticker", return_value=mock_ticker):
        shares, missing = YFinanceProvider().get_shares_outstanding(
            ["AAPL"], date(2024, 1, 1), date(2024, 2, 1)
        )
    assert mock_ticker.get_shares_full.call_count == 3
    assert missing == []
    assert "AAPL" in shares


def test_get_shares_outstanding_one_ticker_exhausting_retries_does_not_fail_the_batch():
    good = pd.Series([1_000.0], index=pd.DatetimeIndex(["2024-01-03"], tz="America/New_York"))

    def factory(ticker_symbol):
        mock_ticker = MagicMock()
        if ticker_symbol == "BAD":
            mock_ticker.get_shares_full.side_effect = ConnectionError("boom")
        else:
            mock_ticker.get_shares_full.return_value = good
        return mock_ticker

    with patch("yfinance.Ticker", side_effect=factory):
        shares, missing = YFinanceProvider().get_shares_outstanding(
            ["AAPL", "BAD"], date(2024, 1, 1), date(2024, 2, 1)
        )
    assert set(shares) == {"AAPL"}
    assert missing == ["BAD"]


def test_get_shares_outstanding_requests_start_and_end_per_ticker():
    good = pd.Series([1_000.0], index=pd.DatetimeIndex(["2024-01-03"], tz="America/New_York"))
    mock_ticker = MagicMock()
    mock_ticker.get_shares_full.return_value = good
    with patch("yfinance.Ticker", return_value=mock_ticker):
        YFinanceProvider().get_shares_outstanding(["AAPL", "MSFT"], date(2024, 1, 1), date(2024, 2, 1))
    assert mock_ticker.get_shares_full.call_count == 2
    for call in mock_ticker.get_shares_full.call_args_list:
        assert call.kwargs["start"] == date(2024, 1, 1)
        assert call.kwargs["end"] == date(2024, 2, 1)


# --- get_market_cap_basis (Build D1 market-cap fix) --------------------------


def _market_cap_basis_frame(
    tickers: list[str], n_days: int = 10, splits: dict[str, dict[int, float]] | None = None
) -> pd.DataFrame:
    """Mocks yf.download(auto_adjust=False, actions=True)'s MultiIndex shape:
    a dividend-UNadjusted Close alongside a separate Adj Close, plus the
    Dividends/Stock Splits action columns."""
    index = pd.bdate_range("2024-01-02", periods=n_days)
    fields = ["Adj Close", "Close", "Dividends", "High", "Low", "Open", "Stock Splits", "Volume"]
    columns = pd.MultiIndex.from_product([fields, tickers], names=["Price", "Ticker"])
    data = {}
    for ticker in tickers:
        close = np.linspace(100.0, 110.0, n_days)
        data[("Close", ticker)] = close
        # Deliberately DIFFERENT from Close, as the real dividend-adjusted
        # series is — the whole reason this method exists.
        data[("Adj Close", ticker)] = close * 0.9
        for field in ("High", "Low", "Open", "Volume"):
            data[(field, ticker)] = close
        data[("Dividends", ticker)] = np.zeros(n_days)
        split_col = np.zeros(n_days)
        for offset, ratio in (splits or {}).get(ticker, {}).items():
            split_col[offset] = ratio
        data[("Stock Splits", ticker)] = split_col
    return pd.DataFrame(data, index=index, columns=columns)


def test_get_market_cap_basis_returns_the_dividend_unadjusted_close():
    frame = _market_cap_basis_frame(["AAPL", "MSFT"])
    with patch("yfinance.download", return_value=frame):
        close, _, missing = YFinanceProvider().get_market_cap_basis(
            ["AAPL", "MSFT"], date(2024, 1, 1), date(2024, 1, 31)
        )
    assert missing == []
    assert set(close.columns) == {"AAPL", "MSFT"}
    # Close, NOT Adj Close: multiplying a share count by a dividend-adjusted
    # price is not a market cap (see the method's own docstring).
    assert close["AAPL"].iloc[0] == pytest.approx(100.0)
    assert close["AAPL"].iloc[-1] == pytest.approx(110.0)


def test_get_market_cap_basis_requests_unadjusted_prices_with_actions():
    frame = _market_cap_basis_frame(["AAPL"])
    with patch("yfinance.download", return_value=frame) as mock_download:
        YFinanceProvider().get_market_cap_basis(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))
    kwargs = mock_download.call_args.kwargs
    # auto_adjust=True here would silently reintroduce the dividend half of
    # the market-cap bug; actions=False would drop the split ratios the
    # share-count restatement needs.
    assert kwargs["auto_adjust"] is False
    assert kwargs["actions"] is True
    assert kwargs["start"] == date(2024, 1, 1)
    assert kwargs["end"] == date(2024, 1, 31)


def test_get_market_cap_basis_extracts_dated_split_ratios():
    frame = _market_cap_basis_frame(["AAPL", "MSFT"], splits={"AAPL": {4: 4.0}})
    with patch("yfinance.download", return_value=frame):
        _, splits, _ = YFinanceProvider().get_market_cap_basis(
            ["AAPL", "MSFT"], date(2024, 1, 1), date(2024, 1, 31)
        )
    # A ticker with no split in the window is ABSENT, meaning "no splits" —
    # never a fabricated 1.0 row.
    assert set(splits) == {"AAPL"}
    assert list(splits["AAPL"]) == pytest.approx([4.0])
    assert splits["AAPL"].index[0] == pd.Timestamp("2024-01-08")
    assert splits["AAPL"].index.tz is None


def test_get_market_cap_basis_drops_zero_and_unit_split_rows():
    # yfinance writes 0.0 on every non-split day; a literal 1.0 ratio is a
    # no-op. Neither is a split event.
    frame = _market_cap_basis_frame(["AAPL"], splits={"AAPL": {3: 1.0}})
    with patch("yfinance.download", return_value=frame):
        _, splits, _ = YFinanceProvider().get_market_cap_basis(
            ["AAPL"], date(2024, 1, 1), date(2024, 1, 31)
        )
    assert splits == {}


def test_get_market_cap_basis_all_nan_ticker_reported_missing():
    frame = _market_cap_basis_frame(["AAPL", "BADTICKER"])
    for field in ["Adj Close", "Close", "High", "Low", "Open", "Volume"]:
        frame[(field, "BADTICKER")] = np.nan
    with patch("yfinance.download", return_value=frame):
        close, _, missing = YFinanceProvider().get_market_cap_basis(
            ["AAPL", "BADTICKER"], date(2024, 1, 1), date(2024, 1, 31)
        )
    assert missing == ["BADTICKER"]
    assert list(close.columns) == ["AAPL"]


def test_get_market_cap_basis_empty_response_reports_all_missing():
    with patch("yfinance.download", return_value=pd.DataFrame()):
        close, splits, missing = YFinanceProvider().get_market_cap_basis(
            ["ZZZQQXX"], date(2024, 1, 1), date(2024, 1, 31)
        )
    assert close.empty
    assert splits == {}
    assert missing == ["ZZZQQXX"]


def test_get_market_cap_basis_network_failure_raises_market_data_error():
    with patch("yfinance.download", side_effect=ConnectionError("boom")), pytest.raises(MarketDataError):
        YFinanceProvider().get_market_cap_basis(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))


def test_get_market_cap_basis_unexpected_shape_raises_market_data_error():
    bad = pd.DataFrame({"Nonsense": [1, 2, 3]})
    with patch("yfinance.download", return_value=bad), pytest.raises(MarketDataError):
        YFinanceProvider().get_market_cap_basis(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))


def test_get_market_cap_basis_handles_flat_single_ticker_columns():
    # Same defensive fallback get_price_history keeps for the yfinance
    # versions that collapse a length-1 request to flat columns.
    index = pd.bdate_range("2024-01-02", periods=5)
    flat = pd.DataFrame(
        {
            "Close": np.linspace(100.0, 104.0, 5),
            "Adj Close": np.linspace(90.0, 94.0, 5),
            "Stock Splits": [0.0, 0.0, 2.0, 0.0, 0.0],
        },
        index=index,
    )
    with patch("yfinance.download", return_value=flat):
        close, splits, missing = YFinanceProvider().get_market_cap_basis(
            ["AAPL"], date(2024, 1, 1), date(2024, 1, 31)
        )
    assert missing == []
    assert close["AAPL"].iloc[0] == pytest.approx(100.0)
    assert list(splits["AAPL"]) == pytest.approx([2.0])


# --- get_total_and_price_return_closes (bonds carry: both price bases) -------


def _both_bases_frame(
    tickers: list[str],
    n_days: int = 10,
    *,
    income_by_ticker: dict[str, float] | None = None,
    nan_close: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Mocks yf.download(auto_adjust=False, actions=True)'s MultiIndex shape.

    THE SOURCE OF THE TOTAL-RETURN BASIS CHANGED when the point-in-time price
    store landed, and this fixture changed with it for that reason rather
    than to keep old assertions green. It used to fabricate an `Adj Close`
    column unrelated to `Close`, because the provider simply forwarded
    whatever Yahoo put there. The provider now COMPUTES the total-return
    basis from `Close` plus the `Dividends` series (price_store.py section
    5), so a distribution is what the fixture must supply — and the wedge
    between the two returned frames is now caused by a modelled cash flow
    instead of being asserted into existence.

    `income_by_ticker` is a per-period distribution YIELD, paid on every day
    after the first, so the compounded wedge stays an exactly known number."""
    index = pd.bdate_range("2024-01-02", periods=n_days)
    fields = ["Close", "High", "Low", "Open", "Volume", "Dividends", "Stock Splits"]
    columns = pd.MultiIndex.from_product([fields, tickers], names=["Price", "Ticker"])
    income_by_ticker = income_by_ticker or {}
    data = {}
    for ticker in tickers:
        close = np.full(n_days, 100.0)
        yield_ = income_by_ticker.get(ticker, 0.05)
        dividends = np.full(n_days, 100.0 * yield_)
        dividends[0] = 0.0
        data[("Close", ticker)] = np.full(n_days, np.nan) if ticker in nan_close else close
        data[("Dividends", ticker)] = dividends
        data[("Stock Splits", ticker)] = np.zeros(n_days)
        for field in ("High", "Low", "Open", "Volume"):
            data[(field, ticker)] = close
    return pd.DataFrame(data, index=index, columns=columns)


def test_get_total_and_price_return_closes_returns_both_bases_aligned():
    frame = _both_bases_frame(["TLT", "LQD"], income_by_ticker={"TLT": 0.0, "LQD": 0.02})
    with patch("yfinance.download", return_value=frame):
        total_return, price_only, missing = YFinanceProvider().get_total_and_price_return_closes(
            ["TLT", "LQD"], date(2024, 1, 1), date(2024, 1, 31)
        )
    assert missing == []
    # Aligned exactly, which is what CrossSectionalData's own check demands.
    assert total_return.index.equals(price_only.index)
    assert total_return.columns.equals(price_only.columns)
    assert set(total_return.columns) == {"TLT", "LQD"}
    # price_only is Close: split-adjusted, dividend-UNadjusted, so a flat
    # price series stays flat however much is distributed out of it.
    assert price_only["LQD"].iloc[0] == pytest.approx(100.0)
    assert price_only["LQD"].iloc[-1] == pytest.approx(100.0)
    # total_return is a genuinely different series for a payer: both bases
    # meet at the window's base date (the last row), and every earlier date
    # is worth LESS on the total-return basis because holding it through the
    # window earned the distributions.
    assert total_return["LQD"].iloc[-1] == pytest.approx(price_only["LQD"].iloc[-1])
    assert total_return["LQD"].iloc[0] < price_only["LQD"].iloc[0]
    # TLT pays nothing in this fixture, so its two bases coincide throughout
    # — the control showing the wedge tracks income rather than being an
    # artifact of the computation.
    pd.testing.assert_series_equal(total_return["TLT"], price_only["TLT"])


def test_get_total_and_price_return_closes_recovers_the_income_wedge():
    """The reason the method exists: (TR_t/TR_0)/(PX_t/PX_0) - 1 is the
    distribution actually paid, an OBSERVED number. If the two frames were
    ever the same series this would be identically zero.

    Under the YAHOO convention a distribution of D against a previous close
    of P grows the total-return basis by P/(P-D) across its ex-date, so ten
    such days compound to (100/98)**10 for a 2% distribution."""
    frame = _both_bases_frame(["HYG"], n_days=11, income_by_ticker={"HYG": 0.02})
    with patch("yfinance.download", return_value=frame):
        total_return, price_only, _ = YFinanceProvider().get_total_and_price_return_closes(
            ["HYG"], date(2024, 1, 1), date(2024, 1, 31)
        )
    tr_growth = total_return["HYG"].iloc[-1] / total_return["HYG"].iloc[0]
    px_growth = price_only["HYG"].iloc[-1] / price_only["HYG"].iloc[0]
    assert tr_growth / px_growth - 1.0 == pytest.approx((100.0 / 98.0) ** 10 - 1.0)


def test_get_total_and_price_return_closes_requests_unadjusted_prices_and_actions():
    frame = _both_bases_frame(["TLT"])
    with patch("yfinance.download", return_value=frame) as mock_download:
        YFinanceProvider().get_total_and_price_return_closes(
            ["TLT"], date(2024, 1, 1), date(2024, 1, 31)
        )
    kwargs = mock_download.call_args.kwargs
    # auto_adjust=True would hand back Yahoo's already-adjusted series — the
    # derived, silently-revised opinion the price store exists to stop
    # depending on — and would carry no Dividends series to rebuild it from.
    assert kwargs["auto_adjust"] is False
    assert kwargs["actions"] is True
    assert kwargs["start"] == date(2024, 1, 1)
    assert kwargs["end"] == date(2024, 1, 31)


def test_get_total_and_price_return_closes_missing_defined_by_close_availability():
    """The ticker set is defined by CLOSE availability, matching
    get_daily_ohlcv's contract exactly. That is a change of WHICH field is
    primary (it used to be Yahoo's `Adj Close`) and a strict simplification:
    both returned bases are now functions of one stored close, so they can no
    longer disagree about which dates or tickers exist."""
    frame = _both_bases_frame(["TLT", "LQD"], nan_close=("LQD",))
    with patch("yfinance.download", return_value=frame):
        total_return, price_only, missing = YFinanceProvider().get_total_and_price_return_closes(
            ["TLT", "LQD"], date(2024, 1, 1), date(2024, 1, 31)
        )
    assert missing == ["LQD"]
    assert list(total_return.columns) == ["TLT"]
    assert list(price_only.columns) == ["TLT"]


def test_get_total_and_price_return_closes_bases_share_one_nan_pattern():
    """The alignment property that replaced "a sparse price-only survives as
    NaN": deriving both frames from one stored close makes them structurally
    incapable of disagreeing about coverage."""
    frame = _both_bases_frame(["TLT", "LQD"], income_by_ticker={"LQD": 0.01})
    with patch("yfinance.download", return_value=frame):
        total_return, price_only, missing = YFinanceProvider().get_total_and_price_return_closes(
            ["TLT", "LQD"], date(2024, 1, 1), date(2024, 1, 31)
        )
    assert missing == []
    assert total_return.isna().equals(price_only.isna())


def test_get_total_and_price_return_closes_empty_response_reports_all_missing():
    with patch("yfinance.download", return_value=pd.DataFrame()):
        total_return, price_only, missing = YFinanceProvider().get_total_and_price_return_closes(
            ["TLT", "LQD"], date(2024, 1, 1), date(2024, 1, 31)
        )
    assert total_return.empty and price_only.empty
    assert missing == ["TLT", "LQD"]


def test_get_total_and_price_return_closes_all_nan_response_reports_all_missing():
    frame = _both_bases_frame(["TLT", "LQD"], nan_close=("TLT", "LQD"))
    with patch("yfinance.download", return_value=frame):
        total_return, price_only, missing = YFinanceProvider().get_total_and_price_return_closes(
            ["TLT", "LQD"], date(2024, 1, 1), date(2024, 1, 31)
        )
    assert total_return.empty and price_only.empty
    assert missing == ["TLT", "LQD"]


def test_get_total_and_price_return_closes_network_failure_raises_market_data_error():
    with patch("yfinance.download", side_effect=Exception("boom")), pytest.raises(MarketDataError):
        YFinanceProvider().get_total_and_price_return_closes(
            ["TLT"], date(2024, 1, 1), date(2024, 1, 31)
        )


def test_get_total_and_price_return_closes_unexpected_shape_raises():
    """A response with no `Close` at all is the shape failure that matters
    now: `Close` is what every returned basis is computed from. (A missing
    `Adj Close` is no longer an error — nothing reads it.)"""
    nonsense = pd.DataFrame(
        {("Nonsense", "TLT"): np.linspace(100.0, 110.0, 5)},
        index=pd.bdate_range("2024-01-02", periods=5),
        columns=pd.MultiIndex.from_tuples([("Nonsense", "TLT")], names=["Price", "Ticker"]),
    )
    with patch("yfinance.download", return_value=nonsense), pytest.raises(MarketDataError):
        YFinanceProvider().get_total_and_price_return_closes(
            ["TLT"], date(2024, 1, 1), date(2024, 1, 31)
        )


def test_get_total_and_price_return_closes_handles_flat_single_ticker_columns():
    index = pd.bdate_range("2024-01-02", periods=6)
    close = np.full(6, 100.0)
    dividends = np.array([0.0, 0.0, 0.0, 1.0, 0.0, 0.0])
    flat = pd.DataFrame(
        {"Close": close, "Open": close, "Dividends": dividends, "Stock Splits": np.zeros(6)},
        index=index,
    )
    with patch("yfinance.download", return_value=flat):
        total_return, price_only, missing = YFinanceProvider().get_total_and_price_return_closes(
            ["TLT"], date(2024, 1, 1), date(2024, 1, 31)
        )
    assert missing == []
    assert list(total_return.columns) == ["TLT"]
    assert list(price_only.columns) == ["TLT"]
    assert price_only["TLT"].iloc[0] == pytest.approx(100.0)
    # One $1 distribution against a $100 close: the pre-ex-date total-return
    # basis sits 1% lower under the YAHOO convention, 100 * 99/100.
    assert total_return["TLT"].iloc[0] == pytest.approx(99.0)


def test_get_total_and_price_return_closes_retries_and_succeeds_on_third_attempt():
    frame = _both_bases_frame(["TLT"])
    with patch("yfinance.download", side_effect=[Exception("net"), Exception("net"), frame]):
        total_return, _, missing = YFinanceProvider().get_total_and_price_return_closes(
            ["TLT"], date(2024, 1, 1), date(2024, 1, 31)
        )
    assert missing == []
    assert not total_return.empty


# --- get_dividend_history (the dividend-month-premium family's input) ------
#
# Reuses _market_cap_basis_frame: both methods make the SAME
# yf.download(auto_adjust=False, actions=True) call and read different
# fields out of one response shape, so mocking that shape twice would be two
# fixtures that could silently drift apart.


def _dividend_frame(
    tickers: list[str], dividends: dict[str, dict[int, float]], n_days: int = 10
) -> pd.DataFrame:
    frame = _market_cap_basis_frame(tickers, n_days=n_days)
    for ticker, rows in dividends.items():
        column = np.zeros(n_days)
        for offset, amount in rows.items():
            column[offset] = amount
        frame[("Dividends", ticker)] = column
    return frame


def test_get_dividend_history_extracts_dated_cash_dividends():
    frame = _dividend_frame(["KO", "NVDA"], {"KO": {2: 0.46, 6: 0.46}})
    with patch("yfinance.download", return_value=frame):
        dividends, close, missing = YFinanceProvider().get_dividend_history(
            ["KO", "NVDA"], date(2024, 1, 1), date(2024, 1, 31)
        )
    assert missing == []
    # A ticker that paid nothing in the window is ABSENT, meaning "paid
    # nothing" — never a fabricated zero row. That distinction is what the
    # consuming family's payer/non-payer split rests on.
    assert set(dividends) == {"KO"}
    assert list(dividends["KO"]) == pytest.approx([0.46, 0.46])
    assert set(close.columns) == {"KO", "NVDA"}


def test_get_dividend_history_returns_the_split_adjusted_close_not_adj_close():
    """The amounts are split-adjusted, so the price they are divided by must
    be too. Adj Close is additionally dividend-back-adjusted, and pairing it
    with these amounts would overstate historical yields by a per-ticker
    factor — the exact bug get_market_cap_basis already documents."""
    frame = _dividend_frame(["KO"], {"KO": {1: 0.46}})
    with patch("yfinance.download", return_value=frame):
        _, close, _ = YFinanceProvider().get_dividend_history(
            ["KO"], date(2024, 1, 1), date(2024, 1, 31)
        )
    # The fixture sets Adj Close = Close * 0.9, so this pins WHICH one came back.
    assert close["KO"].iloc[0] == pytest.approx(100.0)


def test_get_dividend_history_requests_unadjusted_prices_with_actions():
    frame = _dividend_frame(["KO"], {"KO": {1: 0.46}})
    with patch("yfinance.download", return_value=frame) as mock_download:
        YFinanceProvider().get_dividend_history(["KO"], date(2024, 1, 1), date(2024, 1, 31))
    kwargs = mock_download.call_args.kwargs
    # actions=False would drop the Dividends column entirely; auto_adjust=True
    # would collapse Close into the dividend-adjusted series.
    assert kwargs["auto_adjust"] is False
    assert kwargs["actions"] is True


def test_get_dividend_history_ignores_zero_and_negative_action_rows():
    """yfinance fills the action columns with 0.0 on ordinary days, so a zero
    means "no distribution", never "unknown"."""
    frame = _dividend_frame(["KO"], {"KO": {3: 0.46}})
    frame[("Dividends", "KO")] = frame[("Dividends", "KO")].copy()
    frame.loc[frame.index[5], ("Dividends", "KO")] = -1.0
    with patch("yfinance.download", return_value=frame):
        dividends, _, _ = YFinanceProvider().get_dividend_history(
            ["KO"], date(2024, 1, 1), date(2024, 1, 31)
        )
    assert list(dividends["KO"]) == pytest.approx([0.46])


def test_get_dividend_history_normalizes_the_index_to_midnight():
    """Ex-dates are compared against a daily price index; a stray tz or
    intraday timestamp would make those comparisons silently miss."""
    frame = _dividend_frame(["KO"], {"KO": {2: 0.46}})
    with patch("yfinance.download", return_value=frame):
        dividends, _, _ = YFinanceProvider().get_dividend_history(
            ["KO"], date(2024, 1, 1), date(2024, 1, 31)
        )
    index = dividends["KO"].index
    assert index.tz is None
    assert (index == index.normalize()).all()


def test_get_dividend_history_empty_response_reports_all_missing():
    with patch("yfinance.download", return_value=pd.DataFrame()):
        dividends, close, missing = YFinanceProvider().get_dividend_history(
            ["KO", "NVDA"], date(2024, 1, 1), date(2024, 1, 31)
        )
    assert dividends == {}
    assert close.empty
    assert missing == ["KO", "NVDA"]


def test_get_dividend_history_network_failure_raises_market_data_error():
    with patch("yfinance.download", side_effect=Exception("boom")), patch("time.sleep"):
        with pytest.raises(MarketDataError, match="dividend history"):
            YFinanceProvider().get_dividend_history(
                ["KO"], date(2024, 1, 1), date(2024, 1, 31)
            )


def test_get_dividend_history_unexpected_shape_raises_market_data_error():
    frame = pd.DataFrame({"Open": [1.0, 2.0]}, index=pd.bdate_range("2024-01-02", periods=2))
    with patch("yfinance.download", return_value=frame):
        with pytest.raises(MarketDataError, match="dividend-history"):
            YFinanceProvider().get_dividend_history(
                ["KO"], date(2024, 1, 1), date(2024, 1, 31)
            )


def test_get_dividend_history_handles_flat_single_ticker_columns():
    index = pd.bdate_range("2024-01-02", periods=6)
    close = np.linspace(100.0, 105.0, 6)
    dividends_column = np.zeros(6)
    dividends_column[2] = 0.46
    flat = pd.DataFrame(
        {"Adj Close": close * 0.9, "Close": close, "Dividends": dividends_column},
        index=index,
    )
    with patch("yfinance.download", return_value=flat):
        dividends, close_frame, missing = YFinanceProvider().get_dividend_history(
            ["KO"], date(2024, 1, 1), date(2024, 1, 31)
        )
    assert missing == []
    assert list(close_frame.columns) == ["KO"]
    assert list(dividends["KO"]) == pytest.approx([0.46])
