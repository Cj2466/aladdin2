import pandas as pd
import pytest

from app.services.risk.correlation import correlation_matrix
from app.services.risk.diversification import (
    average_pairwise_correlation,
    herfindahl_index,
)


def test_hhi_equal_weighted_four_holdings():
    weights = {"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25}
    assert herfindahl_index(weights) == pytest.approx(4 * 0.25**2)  # 0.25


def test_hhi_fully_concentrated():
    weights = {"A": 1.0}
    assert herfindahl_index(weights) == pytest.approx(1.0)


def test_avg_pairwise_correlation_identical_series_is_one():
    returns = pd.DataFrame({"A": [0.01, -0.02, 0.03, 0.01], "B": [0.01, -0.02, 0.03, 0.01]})
    corr = correlation_matrix(returns)
    assert average_pairwise_correlation(corr) == pytest.approx(1.0)


def test_avg_pairwise_correlation_inverse_series_is_negative_one():
    a = [0.01, -0.02, 0.03, 0.01]
    returns = pd.DataFrame({"A": a, "B": [-x for x in a]})
    corr = correlation_matrix(returns)
    assert average_pairwise_correlation(corr) == pytest.approx(-1.0)


def test_avg_pairwise_correlation_single_holding_is_nan():
    returns = pd.DataFrame({"A": [0.01, -0.02, 0.03, 0.01]})
    corr = correlation_matrix(returns)
    result = average_pairwise_correlation(corr)
    assert result != result  # NaN != NaN
