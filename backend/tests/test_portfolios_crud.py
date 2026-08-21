import pytest
from fastapi.testclient import TestClient

from app import dependencies
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _register(client, email="user@example.com", password="supersecret123"):
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


def test_create_portfolio_requires_auth(client):
    response = client.post("/api/portfolios", json=_sample_portfolio_payload())
    assert response.status_code == 401


def test_create_and_get_portfolio(client):
    _register(client)
    create_response = client.post("/api/portfolios", json=_sample_portfolio_payload())
    assert create_response.status_code == 201
    body = create_response.json()
    assert body["name"] == "My portfolio"
    assert {h["ticker"] for h in body["holdings"]} == {"AAPL", "MSFT"}

    get_response = client.get(f"/api/portfolios/{body['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == body["id"]


def test_list_portfolios_only_returns_own(client):
    _register(client, email="owner@example.com")
    client.post("/api/portfolios", json=_sample_portfolio_payload("Owner's portfolio"))

    other_client = TestClient(app)
    _register(other_client, email="other@example.com")
    other_client.post("/api/portfolios", json=_sample_portfolio_payload("Other's portfolio"))

    response = client.get("/api/portfolios")
    assert response.status_code == 200
    names = [p["name"] for p in response.json()]
    assert names == ["Owner's portfolio"]


def test_get_portfolio_not_owned_is_404(client):
    _register(client, email="owner2@example.com")
    create_response = client.post("/api/portfolios", json=_sample_portfolio_payload())
    portfolio_id = create_response.json()["id"]

    other_client = TestClient(app)
    _register(other_client, email="intruder@example.com")
    response = other_client.get(f"/api/portfolios/{portfolio_id}")
    assert response.status_code == 404


def test_get_nonexistent_portfolio_is_404(client):
    _register(client)
    response = client.get("/api/portfolios/99999")
    assert response.status_code == 404


def test_update_portfolio_replaces_holdings(client):
    _register(client)
    create_response = client.post("/api/portfolios", json=_sample_portfolio_payload())
    portfolio_id = create_response.json()["id"]

    update_payload = {
        "name": "Renamed",
        "holdings": [{"ticker": "GLD", "weight": 1.0}],
    }
    response = client.put(f"/api/portfolios/{portfolio_id}", json=update_payload)
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed"
    assert [h["ticker"] for h in body["holdings"]] == ["GLD"]


def test_delete_portfolio(client):
    _register(client)
    create_response = client.post("/api/portfolios", json=_sample_portfolio_payload())
    portfolio_id = create_response.json()["id"]

    delete_response = client.delete(f"/api/portfolios/{portfolio_id}")
    assert delete_response.status_code == 204

    get_response = client.get(f"/api/portfolios/{portfolio_id}")
    assert get_response.status_code == 404


def test_analyze_saved_portfolio_caches_second_call(client, canned_prices, monkeypatch):
    fetch_calls = []

    def fake_get_price_history(tickers, start, end):
        fetch_calls.append(tuple(tickers))
        present = [t for t in tickers if t in canned_prices.columns]
        missing = [t for t in tickers if t not in canned_prices.columns]
        return canned_prices[present], missing

    monkeypatch.setattr(dependencies.provider, "get_price_history", fake_get_price_history)

    _register(client)
    create_response = client.post("/api/portfolios", json=_sample_portfolio_payload())
    portfolio_id = create_response.json()["id"]

    first = client.get(f"/api/portfolios/{portfolio_id}/analyze")
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["cached"] is False
    assert first_body["portfolio_id"] == portfolio_id

    second = client.get(f"/api/portfolios/{portfolio_id}/analyze")
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["cached"] is True
    # Numeric results are identical whether served fresh or from the
    # risk_results cache.
    assert second_body["volatility_annualized"] == pytest.approx(
        first_body["volatility_annualized"]
    )
    # Only the first call should have gone through compute_portfolio_risk
    # (which calls the price provider); the second is a pure cache hit.
    assert len(fetch_calls) == 1


def test_analyze_portfolio_not_owned_is_404(client, canned_prices, monkeypatch):
    def fake_get_price_history(tickers, start, end):
        present = [t for t in tickers if t in canned_prices.columns]
        missing = [t for t in tickers if t not in canned_prices.columns]
        return canned_prices[present], missing

    monkeypatch.setattr(dependencies.provider, "get_price_history", fake_get_price_history)

    _register(client, email="owner3@example.com")
    create_response = client.post("/api/portfolios", json=_sample_portfolio_payload())
    portfolio_id = create_response.json()["id"]

    other_client = TestClient(app)
    _register(other_client, email="intruder2@example.com")
    response = other_client.get(f"/api/portfolios/{portfolio_id}/analyze")
    assert response.status_code == 404
