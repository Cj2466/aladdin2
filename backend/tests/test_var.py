import pandas as pd
import pytest
from scipy.stats import norm

from app.services.risk.var import conditional_var, historical_var, parametric_var


def test_historical_var_matches_numpy_percentile_directly():
    values = list(range(-10, 11))  # -10..10, 21 evenly spaced values
    returns = pd.Series([v / 100 for v in values])  # -0.10..0.10
    import numpy as np

    expected = np.percentile(returns, 5)
    assert historical_var(returns, confidence=0.95) == pytest.approx(expected)


def test_historical_var_is_negative_for_losses():
    returns = pd.Series([-0.05, -0.03, -0.01, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07])
    assert historical_var(returns, confidence=0.95) < 0


def test_parametric_var_known_formula():
    returns = pd.Series([0.01, -0.01, 0.02, -0.02, 0.005, -0.015, 0.03, -0.01])
    mean = returns.mean()
    std = returns.std(ddof=1)
    z = norm.ppf(0.05)
    expected = mean + z * std
    assert parametric_var(returns, confidence=0.95) == pytest.approx(expected)


def test_conditional_var_is_worse_than_or_equal_to_historical_var():
    returns = pd.Series(
        [-0.20, -0.15, -0.10, -0.05, -0.01, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07]
    )
    hvar = historical_var(returns, confidence=0.95)
    cvar = conditional_var(returns, confidence=0.95)
    # CVaR is the mean of the tail at-or-beyond VaR, so it must be <= VaR
    # (a more negative / equally negative number) when the tail isn't flat.
    assert cvar <= hvar


def test_conditional_var_known_tail_average():
    # Sorted ascending; 5th percentile of 20 evenly spaced values from
    # -0.10 to 0.09 falls at index ~0.95 (between -0.10 and -0.09).
    values = [(-10 + i) / 100 for i in range(20)]  # -0.10 .. 0.09
    returns = pd.Series(values)
    cutoff = historical_var(returns, confidence=0.95)
    expected_tail = [v for v in values if v <= cutoff]
    expected_mean = sum(expected_tail) / len(expected_tail)
    assert conditional_var(returns, confidence=0.95) == pytest.approx(expected_mean)
