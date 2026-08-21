import pandas as pd


def compute_daily_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Simple (non-log) daily returns from adjusted close prices."""
    return prices.pct_change().dropna(how="all")


def compute_portfolio_returns(
    asset_returns: pd.DataFrame, weights: dict[str, float]
) -> pd.Series:
    """Portfolio daily returns using today's weights held constant across the
    lookback window (a simplification — does not model actual historical
    drift between rebalances)."""
    aligned = asset_returns[list(weights.keys())].dropna()
    weight_vector = pd.Series(weights)
    return aligned.dot(weight_vector)
