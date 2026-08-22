from datetime import date

import pandas as pd
import pytest

from app import dependencies
from app.services.macro_data.base import MacroObservationResult
from app.services.risk.stress import SCENARIOS, compute_stress_impact


def test_actual_ticker_uses_realized_return():
    def prices_fn(tickers, start, end):
        index = pd.to_datetime([start, end])
        data = {}
        if "OLD" in tickers:
            data["OLD"] = [100.0, 80.0]  # -20%
        if "SPY" in tickers:
            data["SPY"] = [100.0, 90.0]  # -10%
        frame = pd.DataFrame(data, index=index)
        missing = [t for t in tickers if t not in frame.columns]
        return frame, missing

    results = compute_stress_impact({"OLD": 1.0}, "SPY", prices_fn)
    covid_result = next(r for r in results if r.scenario_id == "covid_2020")
    assert covid_result.has_estimated is False
    holding = covid_result.holdings[0]
    assert holding.basis == "actual"
    assert holding.return_pct == pytest.approx(-0.20)
    assert covid_result.benchmark_return == pytest.approx(-0.10)
    assert covid_result.portfolio_return == pytest.approx(-0.20)


def test_ticker_without_scenario_coverage_uses_estimated_beta():
    def prices_fn(tickers, start, end):
        # Beta-lookback calls request data reaching back only ~3 years from
        # today; every historical scenario window predates that.
        is_beta_lookback = start > date(2020, 1, 1)
        data = {}
        if is_beta_lookback:
            index = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
            if "SPY" in tickers:
                data["SPY"] = [100.0, 105.0, 99.75]  # returns: +5%, -5%
            if "NEW" in tickers:
                data["NEW"] = [100.0, 110.0, 99.0]  # returns: +10%, -10% -> beta 2.0
        else:
            index = pd.to_datetime([start, end])
            if "SPY" in tickers:
                data["SPY"] = [100.0, 90.0]  # -10%
            # NEW has no data at all in historical scenario windows.
        frame = pd.DataFrame(data, index=index)
        missing = [t for t in tickers if t not in frame.columns]
        return frame, missing

    results = compute_stress_impact({"NEW": 1.0}, "SPY", prices_fn)
    for scenario_result in results:
        assert scenario_result.has_estimated is True
        holding = scenario_result.holdings[0]
        assert holding.basis == "estimated"
        assert holding.return_pct == pytest.approx(2.0 * scenario_result.benchmark_return)


def test_all_scenarios_present():
    def prices_fn(tickers, start, end):
        return pd.DataFrame(), []

    results = compute_stress_impact({"X": 1.0}, "SPY", prices_fn)
    assert {r.scenario_id for r in results} == set(SCENARIOS.keys())


def test_portfolio_return_is_weighted_sum():
    def prices_fn(tickers, start, end):
        index = pd.to_datetime([start, end])
        data = {}
        if "A" in tickers:
            data["A"] = [100.0, 80.0]  # -20%
        if "B" in tickers:
            data["B"] = [100.0, 120.0]  # +20%
        if "SPY" in tickers:
            data["SPY"] = [100.0, 95.0]
        frame = pd.DataFrame(data, index=index)
        missing = [t for t in tickers if t not in frame.columns]
        return frame, missing

    results = compute_stress_impact({"A": 0.5, "B": 0.5}, "SPY", prices_fn)
    for scenario_result in results:
        assert scenario_result.portfolio_return == pytest.approx(0.0, abs=1e-9)


def test_stress_test_endpoint_includes_macro_context(client, register_and_verify, monkeypatch):
    register_and_verify(client, email="stress_macro@example.com")

    def fake_get_price_history(tickers, start, end):
        index = pd.to_datetime([start, end])
        data = {t: [100.0, 100.0] for t in tickers}
        return pd.DataFrame(data, index=index), []

    monkeypatch.setattr(dependencies.provider, "get_price_history", fake_get_price_history)

    # get_series_value_near_date_cached always routes through
    # get_observation_history (never get_latest_observations) — return a
    # value that depends on the requested window so "then" and "now" are
    # genuinely distinguishable, not coincidentally equal.
    def fake_get_observation_history(series_id, fred_units, start, end):
        value = 4.56 if start.year < 2024 else 1.23
        return [MacroObservationResult(observation_date=start, value=value)]

    monkeypatch.setattr(
        dependencies.macro_provider, "get_observation_history", fake_get_observation_history
    )

    response = client.post(
        "/api/portfolios/stress-test",
        json={"holdings": [{"ticker": "AAPL", "weight": 1.0}], "benchmark": "SPY"},
    )
    assert response.status_code == 200
    scenarios = response.json()["scenarios"]
    assert len(scenarios) == len(SCENARIOS)
    for scenario in scenarios:
        context = scenario["macro_context"]
        series_ids = {c["series_id"] for c in context}
        assert series_ids == {"T10Y2Y", "DFF"}
        for point in context:
            assert point["current_value"] == pytest.approx(1.23)
            assert point["start_value"] == pytest.approx(4.56)
