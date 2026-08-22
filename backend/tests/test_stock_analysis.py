from datetime import date, timedelta

import httpx
import pytest
from sqlalchemy.orm import sessionmaker

from app import dependencies
from app.config import settings
from app.models.stock_fundamentals import StockFundamentals
from app.services.macro_data.base import MacroDataError, MacroObservationResult
from app.services.macro_data.series import STOCK_MACRO_CONTEXT_SERIES_IDS
from app.services.stock_analysis.cache import get_stock_fundamentals_cached
from app.services.stock_analysis.finnhub_fundamentals import (
    CompanyProfile,
    FinnhubFundamentalsClient,
    FinnhubFundamentalsError,
    FundamentalMetrics,
    RecommendationTrendPoint,
)
from app.time_utils import utcnow_naive


def _session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _profile(**overrides) -> CompanyProfile:
    defaults = {
        "company_name": "Apple Inc",
        "exchange": "NASDAQ NMS - GLOBAL MARKET",
        "country": "US",
        "currency": "USD",
        "ipo_date": "1980-12-12",
        "market_capitalization": 4_500_000.0,
        "share_outstanding": 14_687.36,
        "finnhub_industry": "Technology",
        "weburl": "https://www.apple.com/",
        "logo": "https://static2.finnhub.io/file/publicdatany/finnhubimage/stock_logo/AAPL.png",
    }
    defaults.update(overrides)
    return CompanyProfile(**defaults)


def _metrics(**overrides) -> FundamentalMetrics:
    defaults = {
        "week52_high": 344.57,
        "week52_low": 223.78,
        "beta": 1.08,
        "pe_ttm": 34.36,
        "eps_ttm": 8.72,
        "roe_ttm": 137.18,
        "roa_ttm": 34.55,
        "gross_margin_ttm": 48.65,
        "net_margin_ttm": 27.62,
        "current_ratio": 1.0,
        "quick_ratio": 0.93,
        "debt_to_equity": 0.78,
        "dividend_yield_ttm": 0.35,
        "avg_10day_volume": 42.25,
    }
    defaults.update(overrides)
    return FundamentalMetrics(**defaults)


class _FakeFinnhubClient:
    """Records every call, like _FakeProvider in test_macro.py — lets tests
    assert on cache-hit vs. cache-miss and on per-method failure isolation."""

    def __init__(self, profile=None, metrics=None, recommendation=None, peers=None, fail=None):
        self.profile = profile
        self.metrics = metrics
        self.recommendation = recommendation if recommendation is not None else []
        self.peers = peers if peers is not None else []
        self.fail = fail or set()
        self.calls: list[str] = []

    def get_profile(self, ticker):
        self.calls.append("profile")
        if "profile" in self.fail:
            raise FinnhubFundamentalsError("boom: profile")
        return self.profile

    def get_metrics(self, ticker):
        self.calls.append("metrics")
        if "metrics" in self.fail:
            raise FinnhubFundamentalsError("boom: metrics")
        return self.metrics

    def get_recommendation_trends(self, ticker):
        self.calls.append("recommendation")
        if "recommendation" in self.fail:
            raise FinnhubFundamentalsError("boom: recommendation")
        return self.recommendation

    def get_peers(self, ticker):
        self.calls.append("peers")
        if "peers" in self.fail:
            raise FinnhubFundamentalsError("boom: peers")
        return self.peers


# --- Cache layer -------------------------------------------------------------


def test_fresh_fetch_populates_cache_and_returns_result(test_db_engine):
    client = _FakeFinnhubClient(
        profile=_profile(),
        metrics=_metrics(),
        recommendation=[RecommendationTrendPoint("2026-08-01", 13, 24, 14, 3, 0)],
        peers=["MSFT"],
    )
    SessionLocal = _session_factory(test_db_engine)

    with SessionLocal() as db:
        result = get_stock_fundamentals_cached(db, client, "AAPL")

    assert result is not None
    assert result.company_name == "Apple Inc"
    assert result.pe_ttm == pytest.approx(34.36)
    assert result.peers == ["MSFT"]
    assert result.recommendation_trend == [RecommendationTrendPoint("2026-08-01", 13, 24, 14, 3, 0)]

    with SessionLocal() as db:
        assert db.get(StockFundamentals, "AAPL") is not None


def test_second_call_within_ttl_does_not_refetch(test_db_engine):
    client = _FakeFinnhubClient(profile=_profile(), metrics=_metrics())
    SessionLocal = _session_factory(test_db_engine)

    with SessionLocal() as db:
        get_stock_fundamentals_cached(db, client, "AAPL")
    first_call_count = len(client.calls)
    assert first_call_count == 4  # profile, metrics, recommendation, peers

    with SessionLocal() as db:
        get_stock_fundamentals_cached(db, client, "AAPL")
    assert len(client.calls) == first_call_count  # served entirely from cache


def test_stale_cache_served_when_profile_fetch_fails(test_db_engine):
    SessionLocal = _session_factory(test_db_engine)
    with SessionLocal() as db:
        db.add(
            StockFundamentals(
                ticker="AAPL",
                company_name="Apple Inc",
                pe_ttm=30.0,
                fetched_at=utcnow_naive() - timedelta(hours=48),
            )
        )
        db.commit()

    client = _FakeFinnhubClient(fail={"profile"})
    with SessionLocal() as db:
        result = get_stock_fundamentals_cached(db, client, "AAPL")

    assert result is not None
    assert result.company_name == "Apple Inc"
    assert result.pe_ttm == pytest.approx(30.0)


def test_unknown_ticker_returns_none_and_does_not_cache_a_row(test_db_engine):
    client = _FakeFinnhubClient(profile=None)
    SessionLocal = _session_factory(test_db_engine)

    with SessionLocal() as db:
        result = get_stock_fundamentals_cached(db, client, "ZZZZZZ")

    assert result is None
    with SessionLocal() as db:
        assert db.get(StockFundamentals, "ZZZZZZ") is None


def test_partial_failure_in_metrics_recommendation_or_peers_still_returns_profile(test_db_engine):
    client = _FakeFinnhubClient(profile=_profile(), fail={"metrics", "recommendation", "peers"})
    SessionLocal = _session_factory(test_db_engine)

    with SessionLocal() as db:
        result = get_stock_fundamentals_cached(db, client, "AAPL")

    assert result is not None
    assert result.company_name == "Apple Inc"  # profile data present
    assert result.pe_ttm is None  # metrics failed -> never defaulted, just None
    assert result.recommendation_trend == []
    assert result.peers == []


def test_refresh_preserves_prior_secondary_data_when_fetch_fails(test_db_engine):
    SessionLocal = _session_factory(test_db_engine)
    first_client = _FakeFinnhubClient(
        profile=_profile(), metrics=_metrics(), recommendation=[], peers=["MSFT", "DELL"]
    )
    with SessionLocal() as db:
        get_stock_fundamentals_cached(db, first_client, "AAPL")
        # Force staleness so the next call actually refetches.
        row = db.get(StockFundamentals, "AAPL")
        row.fetched_at = utcnow_naive() - timedelta(hours=48)
        db.commit()

    second_client = _FakeFinnhubClient(profile=_profile(company_name="Apple Inc (updated)"), fail={"peers"})
    with SessionLocal() as db:
        result = get_stock_fundamentals_cached(db, second_client, "AAPL")

    assert result.company_name == "Apple Inc (updated)"  # profile refreshed
    assert result.peers == ["MSFT", "DELL"]  # peers fetch failed -> prior value preserved, not wiped


def test_no_cache_and_total_fetch_failure_raises(test_db_engine):
    client = _FakeFinnhubClient(fail={"profile"})
    SessionLocal = _session_factory(test_db_engine)

    with SessionLocal() as db, pytest.raises(FinnhubFundamentalsError):
        get_stock_fundamentals_cached(db, client, "AAPL")


# --- FinnhubFundamentalsClient (HTTP layer) -----------------------------------


class _FakeHttpResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_get_profile_returns_none_for_empty_response(monkeypatch):
    monkeypatch.setattr(settings, "finnhub_api_key", "test-key")
    monkeypatch.setattr(httpx.Client, "get", lambda self, url, params=None: _FakeHttpResponse({}))

    client = FinnhubFundamentalsClient()
    assert client.get_profile("ZZZZZZ") is None


def test_get_metrics_maps_curated_fields_and_leaves_missing_ones_none(monkeypatch):
    monkeypatch.setattr(settings, "finnhub_api_key", "test-key")
    payload = {
        "metric": {
            "52WeekHigh": 344.57,
            "beta": 1.08,
            "peTTM": 34.36,
            "totalDebt/totalEquityQuarterly": 0.78,
            # eps/roe/margins/ratios deliberately omitted
        }
    }
    monkeypatch.setattr(httpx.Client, "get", lambda self, url, params=None: _FakeHttpResponse(payload))

    client = FinnhubFundamentalsClient()
    metrics = client.get_metrics("AAPL")

    assert metrics is not None
    assert metrics.week52_high == pytest.approx(344.57)
    assert metrics.pe_ttm == pytest.approx(34.36)
    assert metrics.debt_to_equity == pytest.approx(0.78)
    assert metrics.eps_ttm is None
    assert metrics.roe_ttm is None


def test_get_recommendation_trends_handles_empty_list(monkeypatch):
    monkeypatch.setattr(settings, "finnhub_api_key", "test-key")
    monkeypatch.setattr(httpx.Client, "get", lambda self, url, params=None: _FakeHttpResponse([]))

    client = FinnhubFundamentalsClient()
    assert client.get_recommendation_trends("AAPL") == []


def test_get_peers_excludes_self_ticker(monkeypatch):
    monkeypatch.setattr(settings, "finnhub_api_key", "test-key")
    monkeypatch.setattr(
        httpx.Client, "get", lambda self, url, params=None: _FakeHttpResponse(["AAPL", "MSFT", "DELL"])
    )

    client = FinnhubFundamentalsClient()
    assert client.get_peers("AAPL") == ["MSFT", "DELL"]


def test_client_raises_when_api_key_missing():
    original = settings.finnhub_api_key
    settings.finnhub_api_key = ""
    try:
        client = FinnhubFundamentalsClient()
        with pytest.raises(FinnhubFundamentalsError):
            client.get_profile("AAPL")
    finally:
        settings.finnhub_api_key = original


# --- Endpoint ------------------------------------------------------------------


def _patch_finnhub(monkeypatch, profile=None, metrics=None, recommendation=None, peers=None, fail=None):
    fake = _FakeFinnhubClient(profile=profile, metrics=metrics, recommendation=recommendation, peers=peers, fail=fail)
    monkeypatch.setattr(dependencies.finnhub_fundamentals_client, "get_profile", fake.get_profile)
    monkeypatch.setattr(dependencies.finnhub_fundamentals_client, "get_metrics", fake.get_metrics)
    monkeypatch.setattr(
        dependencies.finnhub_fundamentals_client, "get_recommendation_trends", fake.get_recommendation_trends
    )
    monkeypatch.setattr(dependencies.finnhub_fundamentals_client, "get_peers", fake.get_peers)
    return fake


def _patch_macro_ok(monkeypatch):
    monkeypatch.setattr(
        dependencies.macro_provider,
        "get_latest_observations",
        lambda series_id, fred_units, limit=5: [MacroObservationResult(observation_date=date.today(), value=1.5)],
    )


def test_stock_analysis_requires_auth(client):
    response = client.get("/api/stocks/AAPL/analysis")
    assert response.status_code == 401


def test_stock_analysis_returns_fundamentals_and_curated_macro_context(client, register_and_verify, monkeypatch):
    register_and_verify(client)
    _patch_finnhub(monkeypatch, profile=_profile(), metrics=_metrics(), peers=["MSFT"])
    _patch_macro_ok(monkeypatch)

    response = client.get("/api/stocks/AAPL/analysis")
    assert response.status_code == 200
    body = response.json()

    assert body["fundamentals"]["ticker"] == "AAPL"
    assert body["fundamentals"]["company_name"] == "Apple Inc"
    assert body["fundamentals"]["pe_ttm"] == pytest.approx(34.36)
    assert body["fundamentals"]["peers"] == ["MSFT"]
    assert {s["series_id"] for s in body["macro_context"]} == set(STOCK_MACRO_CONTEXT_SERIES_IDS)


def test_stock_analysis_unknown_ticker_returns_404(client, register_and_verify, monkeypatch):
    register_and_verify(client)
    _patch_finnhub(monkeypatch, profile=None)
    _patch_macro_ok(monkeypatch)

    response = client.get("/api/stocks/ZZZZZZ/analysis")
    assert response.status_code == 404


def test_stock_analysis_upstream_failure_with_no_cache_returns_502(client, register_and_verify, monkeypatch):
    register_and_verify(client)
    _patch_finnhub(monkeypatch, fail={"profile"})
    _patch_macro_ok(monkeypatch)

    response = client.get("/api/stocks/AAPL/analysis")
    assert response.status_code == 502


def test_stock_analysis_normalizes_ticker_case(client, register_and_verify, monkeypatch):
    register_and_verify(client)
    _patch_finnhub(monkeypatch, profile=_profile(), metrics=_metrics())
    _patch_macro_ok(monkeypatch)

    response = client.get("/api/stocks/aapl/analysis")
    assert response.status_code == 200
    assert response.json()["fundamentals"]["ticker"] == "AAPL"


def test_stock_analysis_degrades_gracefully_when_macro_provider_fails(client, register_and_verify, monkeypatch):
    register_and_verify(client)
    _patch_finnhub(monkeypatch, profile=_profile(), metrics=_metrics())

    def fail_latest(series_id, fred_units, limit=5):
        raise MacroDataError("boom")

    monkeypatch.setattr(dependencies.macro_provider, "get_latest_observations", fail_latest)

    response = client.get("/api/stocks/AAPL/analysis")
    assert response.status_code == 200
    body = response.json()
    assert body["fundamentals"]["company_name"] == "Apple Inc"  # fundamentals unaffected
    assert all(s["status"] == "unavailable" for s in body["macro_context"])
