import pytest
from fastapi.testclient import TestClient

from app import dependencies
from app.main import app

client = TestClient(app)


def _patch_provider(monkeypatch, canned_prices):
    def fake_get_price_history(tickers, start, end):
        present = [t for t in tickers if t in canned_prices.columns]
        missing = [t for t in tickers if t not in canned_prices.columns]
        return canned_prices[present], missing

    monkeypatch.setattr(dependencies.provider, "get_price_history", fake_get_price_history)


def test_analyze_portfolio_returns_expected_shape(canned_prices, monkeypatch):
    _patch_provider(monkeypatch, canned_prices)

    payload = {
        "holdings": [
            {"ticker": "AAPL", "weight": 0.40},
            {"ticker": "MSFT", "weight": 0.35},
            {"ticker": "GLD", "weight": 0.25},
        ],
        "benchmark": "SPY",
        "lookback_years": 3,
    }
    response = client.post("/api/portfolios/analyze", json=payload)
    assert response.status_code == 200
    body = response.json()

    expected_keys = {
        "as_of",
        "volatility_annualized",
        "var_historical_95",
        "var_parametric_95",
        "cvar_95",
        "beta",
        "hhi",
        "avg_pairwise_correlation",
        "correlation_matrix",
        "warnings",
    }
    assert expected_keys.issubset(body.keys())
    assert body["volatility_annualized"] > 0
    assert body["var_historical_95"] < 0
    assert body["hhi"] == pytest.approx(0.40**2 + 0.35**2 + 0.25**2)

    corr = body["correlation_matrix"]
    for ticker in ["AAPL", "MSFT", "GLD"]:
        assert corr[ticker][ticker] == pytest.approx(1.0, abs=1e-3)


def test_analyze_portfolio_rejects_bad_weights():
    payload = {
        "holdings": [
            {"ticker": "AAPL", "weight": 0.5},
            {"ticker": "MSFT", "weight": 0.6},
        ],
    }
    response = client.post("/api/portfolios/analyze", json=payload)
    assert response.status_code == 422


def test_analyze_portfolio_rejects_unknown_ticker(canned_prices, monkeypatch):
    _patch_provider(monkeypatch, canned_prices)

    payload = {"holdings": [{"ticker": "NOTAREALTICKER", "weight": 1.0}]}
    response = client.post("/api/portfolios/analyze", json=payload)
    assert response.status_code == 422


def test_analyze_portfolio_rejects_duplicate_tickers():
    payload = {
        "holdings": [
            {"ticker": "AAPL", "weight": 0.5},
            {"ticker": "AAPL", "weight": 0.5},
        ],
    }
    response = client.post("/api/portfolios/analyze", json=payload)
    assert response.status_code == 422
