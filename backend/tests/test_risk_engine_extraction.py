"""Proof that pulling compute_portfolio_risk_from_returns /
compute_portfolio_optimization_from_returns out of their price-fetching
wrappers is a lossless decomposition, not a rewrite.

The other half of that proof is that tests/test_risk_api.py and
tests/test_optimizer.py pass with zero edits after the refactor — including
test_infeasible_with_two_holdings_and_default_cap, which asserts (via a
prices_fn that raises) that the feasibility check still fires before any
price fetch, i.e. that it did NOT move into the shared core.
"""

import numpy as np
import pandas as pd
import pytest

from app.services.risk import returns as returns_svc
from app.services.risk.engine import compute_portfolio_risk, compute_portfolio_risk_from_returns
from app.services.risk.errors import InsufficientHistoryError
from app.services.risk.optimizer import (
    compute_portfolio_optimization,
    compute_portfolio_optimization_from_returns,
)

TICKERS = ["AAA", "BBB", "CCC"]
BENCHMARK = "BENCH"


def _frame(n_days: int = 300) -> pd.DataFrame:
    rng = np.random.default_rng(4242)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n_days)
    data = {
        t: 100.0 * np.cumprod(1 + rng.normal(0.0004, 0.011, n_days))
        for t in [*TICKERS, BENCHMARK]
    }
    return pd.DataFrame(data, index=dates)


def _prices_fn(frame: pd.DataFrame):
    def prices_fn(tickers, start, end):
        present = [t for t in tickers if t in frame.columns]
        return frame[present], [t for t in tickers if t not in frame.columns]

    return prices_fn


def test_risk_wrapper_and_core_produce_identical_output():
    frame = _frame()
    weights = {"AAA": 0.5, "BBB": 0.3, "CCC": 0.2}

    via_wrapper = compute_portfolio_risk(weights, BENCHMARK, 3, _prices_fn(frame))

    asset_returns = returns_svc.compute_daily_returns(frame[TICKERS])
    benchmark_returns = returns_svc.compute_daily_returns(frame[[BENCHMARK]])[BENCHMARK]
    via_core = compute_portfolio_risk_from_returns(
        asset_returns, weights, benchmark_returns, as_of=str(frame.index.max().date())
    )

    assert via_wrapper.model_dump() == via_core.model_dump()


def test_risk_core_appends_noisy_warning_after_a_threaded_in_warning():
    """The extraction threads `warnings` through rather than starting a
    fresh list, precisely so the wrapper's missing-data warning still lands
    before the noisy-estimate one."""
    frame = _frame(n_days=100)  # under NOISY_ESTIMATE_TRADING_DAYS
    asset_returns = returns_svc.compute_daily_returns(frame[TICKERS])
    benchmark_returns = returns_svc.compute_daily_returns(frame[[BENCHMARK]])[BENCHMARK]

    result = compute_portfolio_risk_from_returns(
        asset_returns,
        {"AAA": 0.5, "BBB": 0.3, "CCC": 0.2},
        benchmark_returns,
        as_of="2026-01-01",
        warnings=["No data returned for: ZZZ"],
    )
    assert result.warnings[0] == "No data returned for: ZZZ"
    assert "noisy" in result.warnings[1]


def test_risk_core_insufficient_history_label_is_customizable():
    frame = _frame(n_days=8)
    asset_returns = returns_svc.compute_daily_returns(frame[TICKERS])
    benchmark_returns = returns_svc.compute_daily_returns(frame[[BENCHMARK]])[BENCHMARK]

    with pytest.raises(InsufficientHistoryError) as excinfo:
        compute_portfolio_risk_from_returns(
            asset_returns,
            {"AAA": 0.5, "BBB": 0.3, "CCC": 0.2},
            benchmark_returns,
            as_of="2026-01-01",
            insufficient_history_label="selected strategies",
        )
    assert "selected strategies" in str(excinfo.value)
    # Default preserves the pre-extraction message at the 3 original call sites.
    assert "holdings" in str(InsufficientHistoryError(5))


def test_optimizer_wrapper_and_core_produce_identical_output():
    frame = _frame()
    weights = {"AAA": 0.5, "BBB": 0.3, "CCC": 0.2}

    via_wrapper = compute_portfolio_optimization(weights, 3, _prices_fn(frame), risk_free_rate=0.04)

    asset_returns = returns_svc.compute_daily_returns(frame[TICKERS]).dropna()
    via_core = compute_portfolio_optimization_from_returns(
        asset_returns, weights, 0.04, as_of=str(frame.index.max().date())
    )

    assert via_wrapper == via_core
