import pandas as pd
import pytest

from app.services.risk.correlation import correlation_matrix


def test_correlation_matrix_diagonal_is_one_and_symmetric():
    returns = pd.DataFrame(
        {
            "A": [0.01, -0.02, 0.03, 0.01, -0.01],
            "B": [0.02, -0.01, 0.01, 0.03, -0.02],
        }
    )
    corr = correlation_matrix(returns)
    assert corr.loc["A", "A"] == pytest.approx(1.0)
    assert corr.loc["B", "B"] == pytest.approx(1.0)
    assert corr.loc["A", "B"] == pytest.approx(corr.loc["B", "A"])
