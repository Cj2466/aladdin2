import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import dependencies
from app.main import app
from app.services.risk.errors import InsufficientHistoryError, OptimizationInfeasibleError
from app.services.risk.optimizer import compute_portfolio_optimization


def _make_price_series(start_price: float, n_days: int, seed: int, loc: float, scale: float) -> np.ndarray:
    rng = np.random.default_rng(seed)
    daily_returns = rng.normal(loc=loc, scale=scale, size=n_days)
    return start_price * np.cumprod(1 + daily_returns)


def _synthetic_prices_fn(n_days: int = 100):
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n_days)
    data = {
        "DOM": _make_price_series(100.0, n_days, seed=10, loc=0.0025, scale=0.01),
        "MID": _make_price_series(100.0, n_days, seed=20, loc=0.0004, scale=0.01),
        "LOW": _make_price_series(100.0, n_days, seed=30, loc=-0.0005, scale=0.012),
    }
    frame = pd.DataFrame(data, index=dates)

    def prices_fn(tickers, start, end):
        present = [t for t in tickers if t in frame.columns]
        missing = [t for t in tickers if t not in frame.columns]
        return frame[present], missing

    return prices_fn


def test_optimized_weights_sum_to_one_and_respect_cap():
    weights = {"DOM": 1 / 3, "MID": 1 / 3, "LOW": 1 / 3}
    result = compute_portfolio_optimization(weights, 3, _synthetic_prices_fn(), risk_free_rate=0.04)

    total = sum(result.optimized_weights.values())
    assert total == pytest.approx(1.0, abs=1e-3)
    assert all(0.0 <= w <= 0.4 + 1e-6 for w in result.optimized_weights.values())


def test_optimizer_tilts_toward_dominant_sharpe_asset():
    weights = {"DOM": 1 / 3, "MID": 1 / 3, "LOW": 1 / 3}
    result = compute_portfolio_optimization(weights, 3, _synthetic_prices_fn(), risk_free_rate=0.04)

    # DOM has the highest drift and comparable volatility to the others, so
    # the optimizer should overweight it relative to equal-weighting, and
    # the optimized Sharpe should be at least as good as the naive baseline.
    assert result.optimized_weights["DOM"] > 1 / 3
    assert result.optimized.sharpe >= result.current.sharpe - 1e-9


def test_max_weight_cap_binds_for_extreme_dominance():
    n_days = 100
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n_days)
    data = {
        "DOM": _make_price_series(100.0, n_days, seed=1, loc=0.006, scale=0.005),
        "MID": _make_price_series(100.0, n_days, seed=2, loc=0.0001, scale=0.01),
        "LOW": _make_price_series(100.0, n_days, seed=3, loc=0.0001, scale=0.01),
    }
    frame = pd.DataFrame(data, index=dates)

    def prices_fn(tickers, start, end):
        present = [t for t in tickers if t in frame.columns]
        return frame[present], [t for t in tickers if t not in frame.columns]

    weights = {"DOM": 1 / 3, "MID": 1 / 3, "LOW": 1 / 3}
    result = compute_portfolio_optimization(weights, 3, prices_fn, risk_free_rate=0.04, max_weight=0.4)
    assert result.optimized_weights["DOM"] == pytest.approx(0.4, abs=0.01)


def test_infeasible_with_two_holdings_and_default_cap():
    def prices_fn(tickers, start, end):
        raise AssertionError("Feasibility pre-check must fail before any price fetch")

    with pytest.raises(OptimizationInfeasibleError):
        compute_portfolio_optimization({"A": 0.5, "B": 0.5}, 3, prices_fn, risk_free_rate=0.04)


def test_insufficient_history_raises():
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=5)

    def prices_fn(tickers, start, end):
        data = {t: np.linspace(100, 105, 5) for t in tickers}
        return pd.DataFrame(data, index=dates), []

    with pytest.raises(InsufficientHistoryError):
        compute_portfolio_optimization(
            {"A": 0.5, "B": 0.3, "C": 0.2}, 3, prices_fn, risk_free_rate=0.04
        )


@pytest.fixture
def client():
    return TestClient(app)


def _register(client, email="opt_user@example.com", password="supersecret123"):
    response = client.post("/api/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201
    return response.json()


def _sample_portfolio_payload(name="My portfolio"):
    return {
        "name": name,
        "holdings": [
            {"ticker": "AAPL", "weight": 0.5},
            {"ticker": "MSFT", "weight": 0.3},
            {"ticker": "GLD", "weight": 0.2},
        ],
    }


def test_optimize_stateless_endpoint(client, canned_prices, monkeypatch):
    def fake_get_price_history(tickers, start, end):
        present = [t for t in tickers if t in canned_prices.columns]
        missing = [t for t in tickers if t not in canned_prices.columns]
        return canned_prices[present], missing

    monkeypatch.setattr(dependencies.provider, "get_price_history", fake_get_price_history)

    response = client.post("/api/portfolios/optimize", json=_sample_portfolio_payload())
    assert response.status_code == 200
    body = response.json()
    total = sum(h["weight"] for h in body["optimized_weights"])
    assert total == pytest.approx(1.0, abs=1e-2)
    assert body["max_weight_cap"] == pytest.approx(0.4)
    assert body["risk_free_rate"] == pytest.approx(0.04)


def test_optimize_saved_portfolio_not_owned_is_404(client, canned_prices, monkeypatch):
    def fake_get_price_history(tickers, start, end):
        present = [t for t in tickers if t in canned_prices.columns]
        missing = [t for t in tickers if t not in canned_prices.columns]
        return canned_prices[present], missing

    monkeypatch.setattr(dependencies.provider, "get_price_history", fake_get_price_history)

    _register(client, email="owner_opt@example.com")
    create_response = client.post("/api/portfolios", json=_sample_portfolio_payload())
    portfolio_id = create_response.json()["id"]

    other_client = TestClient(app)
    _register(other_client, email="intruder_opt@example.com")
    response = other_client.get(f"/api/portfolios/{portfolio_id}/optimize")
    assert response.status_code == 404
