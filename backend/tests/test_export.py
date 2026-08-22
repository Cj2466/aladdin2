from fastapi.testclient import TestClient

from app import dependencies
from app.main import app


def _sample_portfolio_payload(name="My portfolio"):
    return {
        "name": name,
        "holdings": [
            {"ticker": "AAPL", "weight": 0.6},
            {"ticker": "MSFT", "weight": 0.4},
        ],
    }


def _create_portfolio(client, register_and_verify, canned_prices, monkeypatch, email="export_user@example.com"):
    def fake_get_price_history(tickers, start, end):
        present = [t for t in tickers if t in canned_prices.columns]
        missing = [t for t in tickers if t not in canned_prices.columns]
        return canned_prices[present], missing

    monkeypatch.setattr(dependencies.provider, "get_price_history", fake_get_price_history)

    register_and_verify(client, email=email)
    create_response = client.post("/api/portfolios", json=_sample_portfolio_payload())
    return create_response.json()["id"]


def test_export_csv(client, register_and_verify, canned_prices, monkeypatch):
    portfolio_id = _create_portfolio(client, register_and_verify, canned_prices, monkeypatch)

    response = client.get(f"/api/portfolios/{portfolio_id}/export", params={"format": "csv"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    body = response.text
    assert "ticker,weight" in body
    assert "AAPL,0.6" in body
    assert "volatility_annualized" in body


def test_export_pdf(client, register_and_verify, canned_prices, monkeypatch):
    portfolio_id = _create_portfolio(client, register_and_verify, canned_prices, monkeypatch)

    response = client.get(f"/api/portfolios/{portfolio_id}/export", params={"format": "pdf"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")


def test_export_not_owned_is_404(client, register_and_verify, canned_prices, monkeypatch):
    portfolio_id = _create_portfolio(
        client, register_and_verify, canned_prices, monkeypatch, email="export_owner@example.com"
    )

    other_client = TestClient(app)
    register_and_verify(other_client, email="export_intruder@example.com")
    response = other_client.get(f"/api/portfolios/{portfolio_id}/export")
    assert response.status_code == 404


def test_export_invalid_format_is_422(client, register_and_verify, canned_prices, monkeypatch):
    portfolio_id = _create_portfolio(
        client, register_and_verify, canned_prices, monkeypatch, email="export_fmt@example.com"
    )

    response = client.get(f"/api/portfolios/{portfolio_id}/export", params={"format": "xlsx"})
    assert response.status_code == 422
