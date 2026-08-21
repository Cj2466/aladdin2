import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import dependencies
from app.main import app
from app.services.alerts import checker as checker_module
from app.services.live_quotes.state import QuoteState


@pytest.fixture
def client():
    return TestClient(app)


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


def _register(client, email="alert_user@example.com", password="supersecret123"):
    response = client.post("/api/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201
    return response.json()


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


def test_create_alert_rule_requires_portfolio_ownership(client):
    _register(client, email="alert_owner@example.com")
    portfolio_id = client.post("/api/portfolios", json=_sample_portfolio_payload()).json()["id"]

    other_client = TestClient(app)
    _register(other_client, email="alert_intruder@example.com")
    response = other_client.post("/api/alerts/rules", json=_price_rule_payload(portfolio_id))
    assert response.status_code == 404


def test_create_and_list_alert_rules(client):
    _register(client, email="alert_list@example.com")
    portfolio_id = client.post("/api/portfolios", json=_sample_portfolio_payload()).json()["id"]

    response = client.post("/api/alerts/rules", json=_price_rule_payload(portfolio_id))
    assert response.status_code == 201
    rule_id = response.json()["id"]

    list_response = client.get("/api/alerts/rules")
    assert list_response.status_code == 200
    assert [r["id"] for r in list_response.json()] == [rule_id]


def test_list_alert_rules_only_returns_own(client):
    _register(client, email="alert_own1@example.com")
    portfolio_id = client.post("/api/portfolios", json=_sample_portfolio_payload()).json()["id"]
    client.post("/api/alerts/rules", json=_price_rule_payload(portfolio_id))

    other_client = TestClient(app)
    _register(other_client, email="alert_own2@example.com")
    response = other_client.get("/api/alerts/rules")
    assert response.status_code == 200
    assert response.json() == []


def test_delete_alert_rule_requires_ownership(client):
    _register(client, email="alert_del_owner@example.com")
    portfolio_id = client.post("/api/portfolios", json=_sample_portfolio_payload()).json()["id"]
    rule_id = client.post("/api/alerts/rules", json=_price_rule_payload(portfolio_id)).json()["id"]

    other_client = TestClient(app)
    _register(other_client, email="alert_del_intruder@example.com")
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


async def test_checker_fires_price_rule_and_respects_cooldown(client, fake_quote_snapshot):
    _register(client, email="alert_fire@example.com")
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


async def test_checker_does_not_fire_below_threshold(client, monkeypatch):
    async def fake_below_threshold(ticker):
        return QuoteState(
            price=100.0, previous_close=99.0, change_percent=1.0, market_state="open", last_updated=0.0
        )

    monkeypatch.setattr(checker_module, "fetch_quote_snapshot", fake_below_threshold)

    _register(client, email="alert_no_fire@example.com")
    portfolio_id = client.post("/api/portfolios", json=_sample_portfolio_payload()).json()["id"]
    client.post("/api/alerts/rules", json=_price_rule_payload(portfolio_id, threshold_pct=5.0))

    await checker_module.AlertChecker()._tick()

    assert client.get("/api/alerts").json() == []
    rules = client.get("/api/alerts/rules").json()
    assert rules[0]["last_checked_at"] is not None
    assert rules[0]["last_fired_at"] is None


async def test_risk_metric_rule_reuses_cached_risk_result(client, canned_prices, monkeypatch):
    fetch_calls = []

    def fake_get_price_history(tickers, start, end):
        fetch_calls.append(tuple(tickers))
        present = [t for t in tickers if t in canned_prices.columns]
        missing = [t for t in tickers if t not in canned_prices.columns]
        return canned_prices[present], missing

    monkeypatch.setattr(dependencies.provider, "get_price_history", fake_get_price_history)

    _register(client, email="alert_risk@example.com")
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
