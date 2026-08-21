import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def annualized_volatility(portfolio_returns: pd.Series) -> float:
    return float(portfolio_returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
