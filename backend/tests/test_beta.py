import pandas as pd
import pytest

from app.services.risk.beta import compute_beta


def test_beta_of_two_times_benchmark_is_two():
    benchmark = pd.Series([0.01, -0.02, 0.03, 0.01, -0.01, 0.02])
    portfolio = benchmark * 2
    assert compute_beta(portfolio, benchmark) == pytest.approx(2.0)


def test_beta_of_benchmark_against_itself_is_one():
    benchmark = pd.Series([0.01, -0.02, 0.03, 0.01, -0.01, 0.02])
    assert compute_beta(benchmark, benchmark) == pytest.approx(1.0)


def test_beta_zero_variance_benchmark_is_nan():
    benchmark = pd.Series([0.01, 0.01, 0.01, 0.01])
    portfolio = pd.Series([0.02, -0.01, 0.03, 0.00])
    result = compute_beta(portfolio, benchmark)
    assert result != result  # NaN != NaN
