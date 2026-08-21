import pandas as pd
import pytest

from app.services.risk.returns import compute_daily_returns, compute_portfolio_returns


def test_compute_daily_returns_known_values():
    prices = pd.DataFrame({"AAA": [100.0, 110.0, 99.0]})
    returns = compute_daily_returns(prices)
    assert returns["AAA"].tolist() == pytest.approx([0.10, -0.10])


def test_compute_portfolio_returns_weighted_average():
    asset_returns = pd.DataFrame(
        {"AAA": [0.10, -0.10], "BBB": [0.02, 0.02]},
    )
    weights = {"AAA": 0.5, "BBB": 0.5}
    portfolio_returns = compute_portfolio_returns(asset_returns, weights)
    assert portfolio_returns.tolist() == pytest.approx([0.06, -0.04])
