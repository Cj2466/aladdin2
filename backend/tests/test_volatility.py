import statistics

import numpy as np
import pandas as pd
import pytest

from app.services.risk.volatility import TRADING_DAYS_PER_YEAR, annualized_volatility


def test_zero_variance_returns_zero_volatility():
    returns = pd.Series([0.01, 0.01, 0.01, 0.01])
    assert annualized_volatility(returns) == pytest.approx(0.0)


def test_matches_independent_stdlib_calculation():
    values = [0.01, -0.01, 0.02, -0.02, 0.005]
    returns = pd.Series(values)
    expected = statistics.stdev(values) * (TRADING_DAYS_PER_YEAR**0.5)
    assert annualized_volatility(returns) == pytest.approx(expected)
