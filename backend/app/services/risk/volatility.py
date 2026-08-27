import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def annualized_volatility(
    portfolio_returns: pd.Series, *, periods_per_year: float = TRADING_DAYS_PER_YEAR
) -> float:
    """periods_per_year must match the series: ~252 for a daily exchange-
    traded series, 365 for a daily 24/7/365 crypto series. Keyword-only and
    defaulted so every existing caller (risk engine, optimizer, factor
    model) is byte-for-byte unaffected — it exists so an annualized RETURN
    and the annualized VOLATILITY reported beside it cannot be scaled by two
    different year lengths."""
    return float(portfolio_returns.std(ddof=1) * np.sqrt(periods_per_year))
