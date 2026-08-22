from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import dependencies
from app.main import app
from app.services.alerts import checker as checker_module
from app.services.live_quotes.state import QuoteState
from app.services.macro_data.base import MacroObservationResult


@pytest.fixture(autouse=True)
def patch_checker_session(test_db_engine, monkeypatch):
    """AlertChecker opens its own SessionLocal directly (it's not a FastAPI
    route, so the get_db dependency override doesn't reach it) — point that
    at the same per-test SQLite engine the TestClient uses, or the checker
    would silently operate on the real dev database."""
    testing_session_local = sessionmaker(bind=test_db_engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(checker_module, "SessionLocal", testing_session_local)


@pytest.fixture
def fake_quote_snapshot(monkeypatch):
    calls = []

    async def fake(ticker):
        calls.append(ticker)
        return QuoteState(
            price=100.0, previous_close=94.0, change_percent=6.0, market_state="open", last_updated=0.0
        )

    monkeypatch.setattr(checker_module, "fetch_quote_snapshot", fake)
    return calls


def _sample_portfolio_payload(name="My portfolio"):
    return {
        "name": name,
        "holdings": [
            {"ticker": "AAPL", "weight": 0.6},
            {"ticker": "MSFT", "weight": 0.4},
        ],
    }


def _price_rule_payload(portfolio_id, ticker="AAPL", threshold_pct=5.0, direction="up"):
    return {
        "portfolio_id": portfolio_id,
        "rule_type": "price_move",
        "ticker": ticker,
        "threshold_pct": threshold_pct,
        "direction": direction,
    }


def _macro_rule_payload(series_id="T10Y2Y", threshold_pct=0.0, direction="down"):
    return {
        "rule_type": "macro_threshold",
        "series_id": series_id,
        "threshold_pct": threshold_pct,
        "direction": direction,
    }


def _fake_macro_provider(monkeypatch, value):
    """Every series in MACRO_SERIES gets the same fake value — harmless,
    since a given test only ever asserts on the one series_id its rule
    targets, matching the simplification test_macro.py already uses."""

    def fake_latest(series_id, fred_units, limit=5):
        return [MacroObservationResult(observation_date=date.today(), value=value)]

    def fake_history(series_id, fred_units, start, end):
        return [MacroObservationResult(observation_date=date.today(), value=value)]

    monkeypatch.setattr(dependencies.macro_provider, "get_latest_observations", fake_latest)
    monkeypatch.setattr(dependencies.macro_provider, "get_observation_history", fake_history)


def test_create_alert_rule_requires_portfolio_ownership(client, register_and_verify):
    register_and_verify(client, email="alert_owner@example.com")
    portfolio_id = client.post("/api/portfolios", json=_sample_portfolio_payload()).json()["id"]

    other_client = TestClient(app)
    register_and_verify(other_client, email="alert_intruder@example.com")
    response = other_client.post("/api/alerts/rules", json=_price_rule_payload(portfolio_id))
    assert response.status_code == 404


def test_create_and_list_alert_rules(client, register_and_verify):
    register_and_verify(client, email="alert_list@example.com")
    portfolio_id = client.post("/api/portfolios", json=_sample_portfolio_payload()).json()["id"]

    response = client.post("/api/alerts/rules", json=_price_rule_payload(portfolio_id))
    assert response.status_code == 201
    rule_id = response.json()["id"]

    list_response = client.get("/api/alerts/rules")
    assert list_response.status_code == 200
    assert [r["id"] for r in list_response.json()] == [rule_id]


def test_list_alert_rules_only_returns_own(client, register_and_verify):
    register_and_verify(client, email="alert_own1@example.com")
    portfolio_id = client.post("/api/portfolios", json=_sample_portfolio_payload()).json()["id"]
    client.post("/api/alerts/rules", json=_price_rule_payload(portfolio_id))

    other_client = TestClient(app)
    register_and_verify(other_client, email="alert_own2@example.com")
    response = other_client.get("/api/alerts/rules")
    assert response.status_code == 200
    assert response.json() == []


def test_delete_alert_rule_requires_ownership(client, register_and_verify):
    register_and_verify(client, email="alert_del_owner@example.com")
    portfolio_id = client.post("/api/portfolios", json=_sample_portfolio_payload()).json()["id"]
    rule_id = client.post("/api/alerts/rules", json=_price_rule_payload(portfolio_id)).json()["id"]

    other_client = TestClient(app)
    register_and_verify(other_client, email="alert_del_intruder@example.com")
    assert other_client.delete(f"/api/alerts/rules/{rule_id}").status_code == 404
    assert client.delete(f"/api/alerts/rules/{rule_id}").status_code == 204


def test_price_move_rule_requires_ticker():
    from pydantic import ValidationError

    from app.schemas.alerts import AlertRuleCreate

    with pytest.raises(ValidationError):
        AlertRuleCreate(
            portfolio_id=1, rule_type="price_move", threshold_pct=5.0, direction="up"
        )


def test_risk_metric_rule_requires_allowed_metric():
    from pydantic import ValidationError

    from app.schemas.alerts import AlertRuleCreate

    with pytest.raises(ValidationError):
        AlertRuleCreate(
            portfolio_id=1,
            rule_type="risk_metric",
            metric="not_a_real_metric",
            threshold_pct=5.0,
            direction="up",
        )


def test_price_move_rule_requires_portfolio_id():
    from pydantic import ValidationError

    from app.schemas.alerts import AlertRuleCreate

    with pytest.raises(ValidationError):
        AlertRuleCreate(rule_type="price_move", ticker="AAPL", threshold_pct=5.0, direction="up")


def test_risk_metric_rule_rejects_zero_or_negative_threshold():
    from pydantic import ValidationError

    from app.schemas.alerts import AlertRuleCreate

    with pytest.raises(ValidationError):
        AlertRuleCreate(
            portfolio_id=1, rule_type="risk_metric", metric="beta", threshold_pct=0.0, direction="up"
        )


def test_macro_rule_requires_known_series_id():
    from pydantic import ValidationError

    from app.schemas.alerts import AlertRuleCreate

    with pytest.raises(ValidationError):
        AlertRuleCreate(
            rule_type="macro_threshold", series_id="NOT_A_REAL_SERIES", threshold_pct=0.0, direction="down"
        )


def test_macro_rule_allows_no_portfolio_and_negative_threshold():
    from app.schemas.alerts import AlertRuleCreate

    rule = AlertRuleCreate(
        rule_type="macro_threshold", series_id="T10Y2Y", threshold_pct=-0.5, direction="down"
    )
    assert rule.portfolio_id is None
    assert rule.threshold_pct == -0.5


def test_create_macro_alert_rule_without_portfolio(client, register_and_verify):
    register_and_verify(client, email="macro_alert_create@example.com")
    response = client.post("/api/alerts/rules", json=_macro_rule_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["portfolio_id"] is None
    assert body["series_id"] == "T10Y2Y"


def test_list_macro_series_returns_full_catalog(client, register_and_verify):
    register_and_verify(client, email="macro_series_list@example.com")
    response = client.get("/api/macro/series")
    assert response.status_code == 200
    body = response.json()
    assert len(body) > 0
    assert any(s["series_id"] == "T10Y2Y" for s in body)


def test_crosses_absolute_no_negation_for_down():
    # Pins the semantic difference from _crosses: a macro "down" threshold
    # is a plain level comparison, not a relative-move magnitude that gets
    # sign-flipped.
    assert checker_module.AlertChecker._crosses_absolute(-0.1, 0.0, "down") is True
    assert checker_module.AlertChecker._crosses_absolute(0.1, 0.0, "down") is False
    assert checker_module.AlertChecker._crosses_absolute(4.5, 4.0, "up") is True
    assert checker_module.AlertChecker._crosses_absolute(3.9, 4.0, "up") is False


async def test_checker_fires_price_rule_and_respects_cooldown(client, register_and_verify, fake_quote_snapshot):
    register_and_verify(client, email="alert_fire@example.com")
    portfolio_id = client.post("/api/portfolios", json=_sample_portfolio_payload()).json()["id"]
    rule_response = client.post("/api/alerts/rules", json=_price_rule_payload(portfolio_id))
    assert rule_response.status_code == 201

    checker = checker_module.AlertChecker()
    await checker._tick()

    events = client.get("/api/alerts").json()
    assert len(events) == 1
    # No RESEND_API_KEY configured in this environment -> graceful no-op,
    # confirmed explicitly rather than just "didn't crash".
    assert events[0]["email_sent"] is False

    rules = client.get("/api/alerts/rules").json()
    assert rules[0]["last_fired_at"] is not None
    assert rules[0]["last_checked_at"] is not None

    # Second tick within the cooldown window must not fire again.
    await checker._tick()
    assert len(client.get("/api/alerts").json()) == 1


async def test_checker_does_not_fire_below_threshold(client, register_and_verify, monkeypatch):
    async def fake_below_threshold(ticker):
        return QuoteState(
            price=100.0, previous_close=99.0, change_percent=1.0, market_state="open", last_updated=0.0
        )

    monkeypatch.setattr(checker_module, "fetch_quote_snapshot", fake_below_threshold)

    register_and_verify(client, email="alert_no_fire@example.com")
    portfolio_id = client.post("/api/portfolios", json=_sample_portfolio_payload()).json()["id"]
    client.post("/api/alerts/rules", json=_price_rule_payload(portfolio_id, threshold_pct=5.0))

    await checker_module.AlertChecker()._tick()

    assert client.get("/api/alerts").json() == []
    rules = client.get("/api/alerts/rules").json()
    assert rules[0]["last_checked_at"] is not None
    assert rules[0]["last_fired_at"] is None


async def test_risk_metric_rule_reuses_cached_risk_result(client, register_and_verify, canned_prices, monkeypatch):
    fetch_calls = []

    def fake_get_price_history(tickers, start, end):
        fetch_calls.append(tuple(tickers))
        present = [t for t in tickers if t in canned_prices.columns]
        missing = [t for t in tickers if t not in canned_prices.columns]
        return canned_prices[present], missing

    monkeypatch.setattr(dependencies.provider, "get_price_history", fake_get_price_history)

    register_and_verify(client, email="alert_risk@example.com")
    portfolio_id = client.post("/api/portfolios", json=_sample_portfolio_payload()).json()["id"]

    # Warm the risk_results cache via the normal analyze endpoint — same
    # fixed benchmark/lookback_years the checker uses for risk_metric rules.
    analyze_response = client.get(f"/api/portfolios/{portfolio_id}/analyze")
    assert analyze_response.status_code == 200
    assert len(fetch_calls) == 1

    rule_response = client.post(
        "/api/alerts/rules",
        json={
            "portfolio_id": portfolio_id,
            "rule_type": "risk_metric",
            "metric": "volatility_annualized",
            "threshold_pct": 1000.0,  # unreachable -> exercises the no-fire path
            "direction": "up",
        },
    )
    assert rule_response.status_code == 201

    await checker_module.AlertChecker()._tick()

    # The checker should have hit the risk_results cache row the analyze
    # call already wrote — no second provider fetch.
    assert len(fetch_calls) == 1
    rules = client.get("/api/alerts/rules").json()
    assert rules[0]["last_checked_at"] is not None
    assert client.get("/api/alerts").json() == []


async def test_checker_fires_macro_rule_and_respects_cooldown(client, register_and_verify, monkeypatch):
    _fake_macro_provider(monkeypatch, value=-0.25)  # an inverted yield curve
    register_and_verify(client, email="macro_alert_fire@example.com")
    rule_response = client.post("/api/alerts/rules", json=_macro_rule_payload())
    assert rule_response.status_code == 201

    checker = checker_module.AlertChecker()
    await checker._tick()

    events = client.get("/api/alerts").json()
    assert len(events) == 1
    assert events[0]["email_sent"] is False

    rules = client.get("/api/alerts/rules").json()
    assert rules[0]["last_fired_at"] is not None
    assert rules[0]["last_checked_at"] is not None

    # Second tick within the cooldown window must not fire again.
    await checker._tick()
    assert len(client.get("/api/alerts").json()) == 1


async def test_checker_does_not_fire_macro_rule_when_not_crossed(client, register_and_verify, monkeypatch):
    _fake_macro_provider(monkeypatch, value=0.5)  # not inverted
    register_and_verify(client, email="macro_alert_no_fire@example.com")
    client.post("/api/alerts/rules", json=_macro_rule_payload())

    await checker_module.AlertChecker()._tick()

    assert client.get("/api/alerts").json() == []
    rules = client.get("/api/alerts/rules").json()
    assert rules[0]["last_checked_at"] is not None
    assert rules[0]["last_fired_at"] is None
