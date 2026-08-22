from datetime import date, timedelta

import numpy as np
import pytest

from app import dependencies
from app.services.macro_data.base import MacroObservationResult
from app.services.macro_data.projection import (
    MIN_HISTORY_FOR_BAND_TRADING_DAYS,
    PROJECTABLE_SERIES_IDS,
    compute_series_projection,
)


def _history(values: list[float], start: date | None = None) -> list[MacroObservationResult]:
    start = start or date(2000, 1, 1)
    return [
        MacroObservationResult(observation_date=start + timedelta(days=i), value=v)
        for i, v in enumerate(values)
    ]


def test_insufficient_history_below_floor():
    history = _history([1.0] * 10)
    result = compute_series_projection(history)

    assert result.status == "insufficient_history"
    assert result.point_estimate is None
    assert result.band_low is None


def test_flat_window_does_not_crash_and_reports_weak_trend():
    n = MIN_HISTORY_FOR_BAND_TRADING_DAYS + 50
    history = _history([2.5] * n)  # perfectly flat — linregress's degenerate case

    result = compute_series_projection(history)

    assert result.status == "ok"
    assert result.r_squared == pytest.approx(0.0)
    assert result.trend_strength == "weak"
    assert result.point_estimate == pytest.approx(2.5)


def test_band_low_always_less_than_band_high():
    rng = np.random.default_rng(42)
    n = MIN_HISTORY_FOR_BAND_TRADING_DAYS + 100
    values = list(4.0 + np.cumsum(rng.normal(0, 0.02, n)))
    history = _history(values)

    result = compute_series_projection(history)

    assert result.status == "ok"
    assert result.band_low < result.band_high
    assert result.band_low <= result.point_estimate or result.point_estimate_outside_historical_range
    assert result.band_high >= result.point_estimate or result.point_estimate_outside_historical_range


def test_strong_uptrend_yields_high_r_squared_and_strong_trend():
    n = MIN_HISTORY_FOR_BAND_TRADING_DAYS + 100
    # A clean, noise-free linear ramp — as strong a trend fit as possible.
    values = [1.0 + 0.001 * i for i in range(n)]
    history = _history(values)

    result = compute_series_projection(history)

    assert result.status == "ok"
    assert result.r_squared > 0.9
    assert result.trend_strength == "strong"
    assert result.point_estimate > result.last_value  # trend points upward


def test_all_projectable_series_reachable_via_endpoint(client, register_and_verify, monkeypatch):
    register_and_verify(client, email="projection_endpoint@example.com")

    n = MIN_HISTORY_FOR_BAND_TRADING_DAYS + 50

    def fake_history(series_id, fred_units, start, end):
        # get_macro_history_cached filters its final result to [start, end]
        # after upserting — the fake data must actually fall inside the
        # real requested window (relative to today), not a fixed past date.
        return _history([3.0 + 0.001 * i for i in range(n)], start=end - timedelta(days=n - 1))

    monkeypatch.setattr(dependencies.macro_provider, "get_observation_history", fake_history)

    response = client.get("/api/macro/projections")
    assert response.status_code == 200
    body = response.json()
    assert {p["series_id"] for p in body["projections"]} == set(PROJECTABLE_SERIES_IDS)
    assert "DFF" not in {p["series_id"] for p in body["projections"]}  # explicitly excluded
    assert body["methodology_note"]  # always present, never blank
    for projection in body["projections"]:
        assert projection["status"] == "ok"
        assert projection["band_low"] < projection["band_high"]
