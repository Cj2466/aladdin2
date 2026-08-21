from datetime import date, timedelta

import pandas as pd
from sqlalchemy.orm import sessionmaker

from app.services.market_data.price_cache import get_price_history_cached


def _make_provider_returning(prices: pd.DataFrame):
    """A fake provider that, like a real one, only returns rows within the
    requested [start, end] window — records every call it receives so tests
    can assert on cache-hit vs. cache-miss behavior."""
    calls = []

    class FakeProvider:
        def get_price_history(self, tickers, start, end):
            calls.append((tuple(tickers), start, end))
            present = [t for t in tickers if t in prices.columns]
            missing = [t for t in tickers if t not in prices.columns]
            windowed = prices.loc[(prices.index.date >= start) & (prices.index.date <= end), present]
            return windowed, missing

    return FakeProvider(), calls


def _session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def test_cache_miss_then_hit_does_not_refetch(test_db_engine, canned_prices):
    provider, calls = _make_provider_returning(canned_prices)
    SessionLocal = _session_factory(test_db_engine)

    end = date.today()
    start = end - timedelta(days=365)

    with SessionLocal() as db:
        prices1, missing1 = get_price_history_cached(db, provider, ["AAPL", "MSFT"], start, end)
    assert not missing1
    assert len(calls) == 1

    with SessionLocal() as db:
        prices2, missing2 = get_price_history_cached(db, provider, ["AAPL", "MSFT"], start, end)
    assert not missing2
    # Second call should be served entirely from cache — no second fetch.
    assert len(calls) == 1

    pd.testing.assert_frame_equal(prices1.sort_index(axis=1), prices2.sort_index(axis=1))


def test_cache_refetches_when_range_extends_further_back(test_db_engine, canned_prices):
    provider, calls = _make_provider_returning(canned_prices)
    SessionLocal = _session_factory(test_db_engine)

    end = date.today()
    narrow_start = end - timedelta(days=30)
    wide_start = end - timedelta(days=365)

    with SessionLocal() as db:
        get_price_history_cached(db, provider, ["AAPL"], narrow_start, end)
    assert len(calls) == 1

    with SessionLocal() as db:
        prices, missing = get_price_history_cached(db, provider, ["AAPL"], wide_start, end)
    assert not missing
    # Cache didn't reach back far enough for the wider window -> must refetch.
    assert len(calls) == 2


def test_missing_ticker_propagates(test_db_engine, canned_prices):
    provider, _calls = _make_provider_returning(canned_prices)
    SessionLocal = _session_factory(test_db_engine)

    end = date.today()
    start = end - timedelta(days=30)

    with SessionLocal() as db:
        prices, missing = get_price_history_cached(db, provider, ["AAPL", "NOTREAL"], start, end)
    assert missing == ["NOTREAL"]
    assert "AAPL" in prices.columns


def _make_any_range_provider():
    """Unlike _make_provider_returning (backed by one fixed ~3yr frame),
    this can serve any requested [start, end] window — needed to simulate
    two genuinely disjoint historical fetches with a gap between them."""
    calls = []

    class FakeProvider:
        def get_price_history(self, tickers, start, end):
            calls.append((tuple(tickers), start, end))
            dates = pd.bdate_range(start=start, end=end)
            if len(dates) == 0:
                return pd.DataFrame(), list(tickers)
            data = {t: [100.0] * len(dates) for t in tickers}
            return pd.DataFrame(data, index=dates), []

    return FakeProvider(), calls


def test_gap_between_two_disjoint_cached_windows_is_not_treated_as_covered(test_db_engine):
    """Regression test: a ticker with two disjoint cached spans (e.g. a
    fixed 2008 scenario fetch and a separate 2023 fetch) has an all-time
    min/max that brackets everything in between — including a 2020 window
    that was never actually fetched. Bounds must be scoped to the requested
    window, not the ticker's all-time range, or this silently returns empty
    data instead of refetching."""
    provider, calls = _make_any_range_provider()
    SessionLocal = _session_factory(test_db_engine)

    window_a = (date(2007, 10, 9), date(2009, 3, 9))
    window_b = (date(2023, 1, 1), date(2023, 12, 31))
    gap_window = (date(2020, 2, 19), date(2020, 3, 23))  # entirely inside the 2009-2023 gap

    with SessionLocal() as db:
        get_price_history_cached(db, provider, ["AAPL"], *window_a)
    with SessionLocal() as db:
        get_price_history_cached(db, provider, ["AAPL"], *window_b)
    assert len(calls) == 2

    with SessionLocal() as db:
        prices, missing = get_price_history_cached(db, provider, ["AAPL"], *gap_window)

    assert len(calls) == 3  # must have refetched, not silently returned nothing
    assert not missing
    assert not prices.empty
    assert prices.index.min().date() >= gap_window[0]
    assert prices.index.max().date() <= gap_window[1]
