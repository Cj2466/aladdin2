import numpy as np
import pandas as pd
from scipy.stats import norm


def historical_var(portfolio_returns: pd.Series, confidence: float = 0.95) -> float:
    """Empirical percentile of realized returns. Negative = a loss."""
    alpha = 1 - confidence
    return float(np.percentile(portfolio_returns, alpha * 100))


def parametric_var(portfolio_returns: pd.Series, confidence: float = 0.95) -> float:
    """Gaussian VaR: assumes normally distributed returns."""
    mean = portfolio_returns.mean()
    std = portfolio_returns.std(ddof=1)
    z = norm.ppf(1 - confidence)
    return float(mean + z * std)


def conditional_var(portfolio_returns: pd.Series, confidence: float = 0.95) -> float:
    """Expected Shortfall: mean of returns at or below the historical VaR cutoff.
    More robust than VaR alone (VaR ignores how bad the tail actually is)."""
    cutoff = historical_var(portfolio_returns, confidence)
    tail = portfolio_returns[portfolio_returns <= cutoff]
    if len(tail) == 0:
        return cutoff
    return float(tail.mean())
