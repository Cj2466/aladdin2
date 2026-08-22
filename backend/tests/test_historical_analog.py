from datetime import date

import pandas as pd
import pytest

from app import dependencies
from app.services.historical_analog.episodes import (
    ThresholdEpisode,
    find_crossing_episodes,
)
from app.services.historical_analog.outcomes import compute_episode_outcomes
from app.services.macro_data.base import MacroObservationResult


def _obs(iso_date: str, value: float) -> MacroObservationResult:
    return MacroObservationResult(observation_date=date.fromisoformat(iso_date), value=value)


# --- find_crossing_episodes ----------------------------------------------------


def test_collapses_multi_day_inversion_into_one_episode():
    history = [
        _obs("2022-01-01", 0.5),
        _obs("2022-06-01", -0.1),  # inversion starts
        _obs("2022-07-01", -0.3),
        _obs("2022-08-01", -0.2),
        _obs("2022-09-01", 0.1),  # un-inverts
    ]
    episodes = find_crossing_episodes(history, lambda v: v < 0.0)

    assert len(episodes) == 1
    assert episodes[0].start_date == date(2022, 6, 1)
    assert episodes[0].end_date == date(2022, 8, 1)
    assert episodes[0].trading_days == 3


def test_already_crossed_at_history_start():
    history = [_obs("2000-01-01", -0.5), _obs("2000-02-01", -0.4), _obs("2000-03-01", 0.2)]
    episodes = find_crossing_episodes(history, lambda v: v < 0.0)

    assert len(episodes) == 1
    assert episodes[0].start_date == date(2000, 1, 1)
    assert episodes[0].end_date == date(2000, 2, 1)


def test_multiple_separate_episodes():
    history = [
        _obs("2000-01-01", -0.1),
        _obs("2000-02-01", 0.2),
        _obs("2010-01-01", -0.3),
        _obs("2010-02-01", 0.1),
        _obs("2020-01-01", -0.2),
    ]
    episodes = find_crossing_episodes(history, lambda v: v < 0.0)

    assert [e.start_date for e in episodes] == [date(2000, 1, 1), date(2010, 1, 1), date(2020, 1, 1)]
    # The episode still active at the last observation is still reported.
    assert episodes[-1].end_date == date(2020, 1, 1)


def test_no_episodes_when_never_crossed():
    history = [_obs("2000-01-01", 0.5), _obs("2000-02-01", 0.3)]
    assert find_crossing_episodes(history, lambda v: v < 0.0) == []


# --- compute_episode_outcomes ---------------------------------------------------


def _make_prices_fn(price_by_date: dict[str, float], ticker: str = "SPY"):
    def prices_fn(tickers, start, end):
        index = pd.to_datetime(list(price_by_date.keys()))
        frame = pd.DataFrame({ticker: list(price_by_date.values())}, index=index)
        frame = frame[(frame.index >= pd.Timestamp(start)) & (frame.index <= pd.Timestamp(end))]
        missing = [t for t in tickers if t != ticker]
        return frame, missing

    return prices_fn


def test_too_recent_horizon_is_flagged_not_silently_dropped():
    episode = ThresholdEpisode(start_date=date.today(), end_date=date.today(), trading_days=1)
    prices_fn = _make_prices_fn({str(date.today()): 100.0})

    outcomes = compute_episode_outcomes([episode], "SPY", prices_fn)

    assert len(outcomes) == 1
    for months in (6, 12, 18):
        value, status = outcomes[0].returns[months]
        assert value is None
        assert status == "too_recent"


def test_benchmark_unavailable_for_pre_inception_episode():
    # SPY has no price data at all in this window (simulates a pre-1993
    # inversion, before SPY existed).
    episode = ThresholdEpisode(start_date=date(1980, 1, 1), end_date=date(1980, 2, 1), trading_days=10)
    prices_fn = _make_prices_fn({})

    outcomes = compute_episode_outcomes([episode], "SPY", prices_fn)

    for months in (6, 12, 18):
        value, status = outcomes[0].returns[months]
        assert value is None
        assert status == "benchmark_unavailable"


def test_fetches_prices_once_not_once_per_episode():
    """Regression guard: computing outcomes for many episodes must issue a
    single prices_fn call spanning the whole range, not one call per
    episode (44 episodes over 50 years of real T10Y2Y history took 27s
    end-to-end before this was fixed, one separate cold-cache round-trip
    per episode)."""
    episodes = [
        ThresholdEpisode(start_date=date(2000, 1, 3), end_date=date(2000, 1, 3), trading_days=1),
        ThresholdEpisode(start_date=date(2010, 1, 4), end_date=date(2010, 1, 4), trading_days=1),
        ThresholdEpisode(start_date=date(2020, 1, 2), end_date=date(2020, 1, 2), trading_days=1),
    ]
    calls = []

    def prices_fn(tickers, start, end):
        calls.append((start, end))
        return pd.DataFrame(), list(tickers)

    compute_episode_outcomes(episodes, "SPY", prices_fn)

    assert len(calls) == 1


def test_ok_status_computes_real_forward_return():
    episode = ThresholdEpisode(start_date=date(2000, 1, 3), end_date=date(2000, 1, 3), trading_days=1)
    six_months_later = "2000-07-01"
    prices_fn = _make_prices_fn({"2000-01-03": 100.0, six_months_later: 110.0})

    outcomes = compute_episode_outcomes([episode], "SPY", prices_fn)

    value, status = outcomes[0].returns[6]
    assert status == "ok"
    assert value == pytest.approx(0.10, abs=1e-6)


# --- Router ----------------------------------------------------------------------


def test_historical_analog_rejects_unsupported_series(client, register_and_verify):
    register_and_verify(client, email="analog_bad_series@example.com")
    response = client.get("/api/macro/historical-analog", params={"series_id": "CPIAUCSL"})
    assert response.status_code == 400


def test_historical_analog_returns_episodes_and_caveat(client, register_and_verify, monkeypatch):
    register_and_verify(client, email="analog_ok@example.com")

    def fake_history(series_id, fred_units, start, end):
        return [
            MacroObservationResult(observation_date=date(2000, 1, 1), value=0.5),
            MacroObservationResult(observation_date=date(2000, 6, 1), value=-0.2),
            MacroObservationResult(observation_date=date(2000, 9, 1), value=0.3),
        ]

    monkeypatch.setattr(dependencies.macro_provider, "get_observation_history", fake_history)
    monkeypatch.setattr(
        dependencies.provider,
        "get_price_history",
        lambda tickers, start, end: (pd.DataFrame(), list(tickers)),  # no price data at all
    )

    response = client.get("/api/macro/historical-analog", params={"series_id": "T10Y2Y", "benchmark": "SPY"})
    assert response.status_code == 200
    body = response.json()
    assert body["episode_count"] == 1
    assert body["episodes"][0]["episode_start"] == "2000-06-01"
    assert "small sample" in body["caveat"]
    assert "not a prediction" in body["caveat"]
