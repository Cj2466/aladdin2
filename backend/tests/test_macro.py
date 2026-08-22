from datetime import date, timedelta

import httpx
import pytest
from sqlalchemy.orm import sessionmaker

from app import dependencies
from app.config import settings
from app.models.macro_observation import MacroObservation
from app.services.macro_data.base import MacroDataError, MacroObservationResult
from app.services.macro_data.cache import get_cleveland_fed_nowcasts_cached, get_latest_macro_snapshot_cached
from app.services.macro_data.cleveland_fed_provider import ClevelandFedNowcastProvider
from app.services.macro_data.fred_provider import FredProvider
from app.services.macro_data.series import CLEVELAND_FED_SERIES, MACRO_SERIES
from app.time_utils import utcnow_naive


def _session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


class _FakeProvider:
    """Records every call it receives, like the FakeProvider in
    test_price_cache.py, so tests can assert on cache-hit vs. cache-miss."""

    def __init__(self, latest_by_series=None, fail_series=None):
        self.latest_by_series = latest_by_series or {}
        self.fail_series = fail_series or set()
        self.calls: list[tuple[str, str]] = []

    def get_latest_observations(self, series_id, fred_units, limit=5):
        self.calls.append(("latest", series_id))
        if series_id in self.fail_series:
            raise MacroDataError(f"boom: {series_id}")
        return self.latest_by_series.get(series_id, [])

    def get_observation_history(self, series_id, fred_units, start, end):
        self.calls.append(("history", series_id))
        if series_id in self.fail_series:
            raise MacroDataError(f"boom: {series_id}")
        return []


def _one_observation(value: float, as_of: date | None = None) -> list[MacroObservationResult]:
    return [MacroObservationResult(observation_date=as_of or date.today(), value=value)]


@pytest.fixture(autouse=True)
def no_real_cleveland_fed_calls(monkeypatch):
    """Every /api/macro/dashboard test now also touches the Cleveland Fed
    provider — default to a fake returning nothing (both nowcast series
    report "unavailable") so tests never make a real network call. Any
    test that wants specific Cleveland Fed values overrides this within
    its own body."""
    monkeypatch.setattr(dependencies.cleveland_fed_provider, "get_latest_nowcasts", lambda: {})


# --- Cache layer -------------------------------------------------------------


def test_all_series_ok_when_provider_returns_data(test_db_engine):
    latest = {d.series_id: _one_observation(1.23) for d in MACRO_SERIES}
    provider = _FakeProvider(latest_by_series=latest)
    SessionLocal = _session_factory(test_db_engine)

    with SessionLocal() as db:
        snapshots = get_latest_macro_snapshot_cached(db, provider)

    assert len(snapshots) == len(MACRO_SERIES)
    assert all(s.status == "ok" for s in snapshots)
    assert all(s.value == 1.23 for s in snapshots)


def test_second_call_within_ttl_does_not_refetch(test_db_engine):
    latest = {d.series_id: _one_observation(1.0) for d in MACRO_SERIES}
    provider = _FakeProvider(latest_by_series=latest)
    SessionLocal = _session_factory(test_db_engine)

    with SessionLocal() as db:
        get_latest_macro_snapshot_cached(db, provider)
    first_call_count = len(provider.calls)
    assert first_call_count == len(MACRO_SERIES)

    with SessionLocal() as db:
        get_latest_macro_snapshot_cached(db, provider)
    # Every series was just cached — well within every cadence tier's TTL —
    # so a second call must be served entirely from cache.
    assert len(provider.calls) == first_call_count


def test_stale_cache_served_when_refetch_fails(test_db_engine):
    failing_series = MACRO_SERIES[0].series_id
    SessionLocal = _session_factory(test_db_engine)

    # Seed a deliberately stale cached row (fetched_at far in the past, past
    # every cadence tier's TTL) directly, bypassing the cache function.
    with SessionLocal() as db:
        db.add(
            MacroObservation(
                series_id=failing_series,
                observation_date=date.today() - timedelta(days=30),
                value=5.0,
                fetched_at=utcnow_naive() - timedelta(days=30),
            )
        )
        db.commit()

    latest = {d.series_id: _one_observation(9.0) for d in MACRO_SERIES if d.series_id != failing_series}
    provider = _FakeProvider(latest_by_series=latest, fail_series={failing_series})

    with SessionLocal() as db:
        snapshots = get_latest_macro_snapshot_cached(db, provider)

    failing_snapshot = next(s for s in snapshots if s.series_id == failing_series)
    assert failing_snapshot.status == "ok"  # stale, but served — not blanked
    assert failing_snapshot.value == 5.0

    other_snapshots = [s for s in snapshots if s.series_id != failing_series]
    assert all(s.status == "ok" and s.value == 9.0 for s in other_snapshots)


class _FixedHistoryProvider:
    """Returns the same canned history for any series/date range —
    isolates get_series_value_near_date_cached's own nearest-match logic
    from the fetch/staleness plumbing already covered above."""

    def __init__(self, history: list[MacroObservationResult]):
        self.history = history

    def get_latest_observations(self, series_id, fred_units, limit=5):
        return []

    def get_observation_history(self, series_id, fred_units, start, end):
        return [o for o in self.history if start <= o.observation_date <= end]


def test_get_series_value_near_date_returns_nearest_within_tolerance(test_db_engine):
    from app.services.macro_data.cache import get_series_value_near_date_cached

    target = date(2024, 6, 15)
    history = [
        MacroObservationResult(observation_date=date(2024, 6, 10), value=1.0),
        MacroObservationResult(observation_date=date(2024, 6, 18), value=2.0),  # nearest to target
        MacroObservationResult(observation_date=date(2024, 6, 30), value=3.0),
    ]
    provider = _FixedHistoryProvider(history)
    SessionLocal = _session_factory(test_db_engine)

    with SessionLocal() as db:
        result = get_series_value_near_date_cached(db, provider, "T10Y2Y", target, tolerance_days=10)

    assert result is not None
    assert result.value == 2.0
    assert result.observation_date == date(2024, 6, 18)


def test_get_series_value_near_date_returns_none_outside_tolerance(test_db_engine):
    from app.services.macro_data.cache import get_series_value_near_date_cached

    target = date(2024, 6, 15)
    history = [MacroObservationResult(observation_date=date(2024, 1, 1), value=1.0)]
    provider = _FixedHistoryProvider(history)
    SessionLocal = _session_factory(test_db_engine)

    with SessionLocal() as db:
        result = get_series_value_near_date_cached(db, provider, "T10Y2Y", target, tolerance_days=10)

    assert result is None


def test_never_cached_and_fetch_fails_reports_unavailable(test_db_engine):
    failing_series = MACRO_SERIES[0].series_id
    latest = {d.series_id: _one_observation(9.0) for d in MACRO_SERIES if d.series_id != failing_series}
    provider = _FakeProvider(latest_by_series=latest, fail_series={failing_series})
    SessionLocal = _session_factory(test_db_engine)

    with SessionLocal() as db:
        snapshots = get_latest_macro_snapshot_cached(db, provider)

    failing_snapshot = next(s for s in snapshots if s.series_id == failing_series)
    assert failing_snapshot.status == "unavailable"
    assert failing_snapshot.value is None

    other_snapshots = [s for s in snapshots if s.series_id != failing_series]
    assert all(s.status == "ok" for s in other_snapshots)


# --- FredProvider (HTTP layer) ------------------------------------------------


class _FakeHttpResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_fred_provider_skips_missing_sentinel_values(monkeypatch):
    monkeypatch.setattr(settings, "fred_api_key", "test-key")

    def fake_get(self, url, params=None):
        return _FakeHttpResponse(
            {
                "observations": [
                    {"date": "2026-08-20", "value": "3.10"},
                    {"date": "2026-08-19", "value": "."},  # FRED's missing-data sentinel
                    {"date": "2026-08-18", "value": "3.05"},
                ]
            }
        )

    monkeypatch.setattr(httpx.Client, "get", fake_get)

    provider = FredProvider()
    results = provider.get_latest_observations("CPIAUCSL", "pc1", limit=5)

    assert len(results) == 2
    assert {r.observation_date.isoformat() for r in results} == {"2026-08-20", "2026-08-18"}


def test_fred_provider_raises_when_api_key_missing():
    original = settings.fred_api_key
    settings.fred_api_key = ""
    try:
        provider = FredProvider()
        with pytest.raises(MacroDataError):
            provider.get_latest_observations("CPIAUCSL", "pc1")
    finally:
        settings.fred_api_key = original


# --- ClevelandFedNowcastProvider (HTTP layer) ---------------------------------


def test_cleveland_fed_provider_extracts_latest_non_blank_value(monkeypatch):
    def fake_get(self, url):
        return _FakeHttpResponse(
            [
                {
                    "dataset": [
                        {
                            "seriesname": "CPI Inflation",
                            "data": [{"value": "2.90"}, {"value": ""}, {"value": "3.05"}],
                        },
                        {
                            "seriesname": "Core PCE Inflation",
                            "data": [{"value": ""}, {"value": ""}],  # nowcast cycle inactive
                        },
                    ]
                }
            ]
        )

    monkeypatch.setattr(httpx.Client, "get", fake_get)

    provider = ClevelandFedNowcastProvider()
    results = provider.get_latest_nowcasts()

    assert results.keys() == {"CLEVEFED_CPI_NOWCAST"}  # blank series never yields a result
    assert results["CLEVEFED_CPI_NOWCAST"].value == pytest.approx(3.05)  # last non-blank, not first


def test_cleveland_fed_provider_raises_on_malformed_payload(monkeypatch):
    def fake_get(self, url):
        return _FakeHttpResponse({"unexpected": "shape"})  # not a list with a "dataset" key

    monkeypatch.setattr(httpx.Client, "get", fake_get)

    provider = ClevelandFedNowcastProvider()
    with pytest.raises(MacroDataError):
        provider.get_latest_nowcasts()


# --- Cleveland Fed cache layer -------------------------------------------------


def test_cleveland_fed_nowcasts_never_cached_reports_unavailable(test_db_engine):
    class _EmptyProvider:
        def get_latest_nowcasts(self):
            return {}

    SessionLocal = _session_factory(test_db_engine)
    with SessionLocal() as db:
        snapshots = get_cleveland_fed_nowcasts_cached(db, _EmptyProvider())

    assert len(snapshots) == len(CLEVELAND_FED_SERIES)
    assert all(s.status == "unavailable" for s in snapshots)


def test_cleveland_fed_nowcasts_stale_serve_when_fetch_fails(test_db_engine):
    series_id = CLEVELAND_FED_SERIES[0].series_id
    SessionLocal = _session_factory(test_db_engine)

    with SessionLocal() as db:
        db.add(
            MacroObservation(
                series_id=series_id,
                observation_date=date.today() - timedelta(days=5),
                value=2.5,
                fetched_at=utcnow_naive() - timedelta(days=5),
            )
        )
        db.commit()

    class _FailingProvider:
        def get_latest_nowcasts(self):
            raise MacroDataError("boom")

    with SessionLocal() as db:
        snapshots = get_cleveland_fed_nowcasts_cached(db, _FailingProvider())

    stale = next(s for s in snapshots if s.series_id == series_id)
    assert stale.status == "ok"
    assert stale.value == 2.5


# --- Endpoint ------------------------------------------------------------------


def test_macro_dashboard_requires_auth(client):
    response = client.get("/api/macro/dashboard")
    assert response.status_code == 401


def test_macro_dashboard_returns_all_series_when_authenticated(client, register_and_verify, monkeypatch):
    register_and_verify(client)

    monkeypatch.setattr(
        dependencies.macro_provider,
        "get_latest_observations",
        lambda series_id, fred_units, limit=5: _one_observation(1.5),
    )
    monkeypatch.setattr(
        dependencies.macro_provider,
        "get_observation_history",
        lambda series_id, fred_units, start, end: _one_observation(1.5),
    )
    monkeypatch.setattr(
        dependencies.cleveland_fed_provider,
        "get_latest_nowcasts",
        lambda: {
            "CLEVEFED_CPI_NOWCAST": MacroObservationResult(observation_date=date.today(), value=2.5),
            "CLEVEFED_COREPCE_NOWCAST": MacroObservationResult(observation_date=date.today(), value=2.7),
        },
    )

    response = client.get("/api/macro/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert len(body["series"]) == len(MACRO_SERIES) + len(CLEVELAND_FED_SERIES)
    assert all(s["status"] == "ok" for s in body["series"])
    assert len(body["yield_curve"]) == 4


def test_debt_series_converted_from_millions_to_trillions(client, register_and_verify, monkeypatch):
    register_and_verify(client)

    def fake_latest(series_id, fred_units, limit=5):
        if series_id == "GFDEBTN":
            return _one_observation(35_000_000.0)  # FRED reports this in millions of USD
        return _one_observation(1.0)

    monkeypatch.setattr(dependencies.macro_provider, "get_latest_observations", fake_latest)
    monkeypatch.setattr(
        dependencies.macro_provider,
        "get_observation_history",
        lambda series_id, fred_units, start, end: _one_observation(1.0),
    )

    response = client.get("/api/macro/dashboard")
    body = response.json()
    debt = next(s for s in body["series"] if s["series_id"] == "GFDEBTN")
    assert debt["value"] == pytest.approx(35.0)


def test_macro_dashboard_degrades_gracefully_without_api_key(client, register_and_verify, monkeypatch):
    """A missing/bad FRED_API_KEY must never take down the whole endpoint —
    every series just reports unavailable."""
    register_and_verify(client)
    monkeypatch.setattr(settings, "fred_api_key", "")

    response = client.get("/api/macro/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert all(s["status"] == "unavailable" for s in body["series"])
