from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from app.services.risk import returns as returns_svc
from app.services.risk.engine import MIN_OBS_FOR_ANY_ESTIMATE
from app.services.risk.errors import (
    InsufficientHistoryError,
    MissingTickerDataError,
    OptimizationInfeasibleError,
)
from app.services.risk.volatility import TRADING_DAYS_PER_YEAR

PricesFn = Callable[[list[str], date, date], tuple[pd.DataFrame, list[str]]]

# Unconstrained mean-variance optimization is well known to produce
# degenerate corner solutions (100% into the single highest-Sharpe asset)
# under estimation error — a per-holding cap is standard practice, not an
# arbitrary limitation.
DEFAULT_MAX_WEIGHT = 0.4


@dataclass
class PortfolioStats:
    expected_return: float
    volatility: float
    sharpe: float


@dataclass
class OptimizationResult:
    as_of: str
    optimized_weights: dict[str, float]
    optimized: PortfolioStats
    current: PortfolioStats
    warnings: list[str]


def _portfolio_stats(
    w: np.ndarray, mean_returns: pd.Series, cov_matrix: pd.DataFrame, risk_free_rate: float
) -> PortfolioStats:
    expected_return = float(w @ mean_returns.values)
    volatility = float(np.sqrt(w @ cov_matrix.values @ w))
    sharpe = (expected_return - risk_free_rate) / volatility if volatility > 0 else 0.0
    return PortfolioStats(expected_return=expected_return, volatility=volatility, sharpe=sharpe)


def compute_portfolio_optimization_from_returns(
    asset_returns: pd.DataFrame,
    weights: dict[str, float],
    risk_free_rate: float,
    as_of: str,
    max_weight: float = DEFAULT_MAX_WEIGHT,
    warnings: list[str] | None = None,
    insufficient_history_label: str = "holdings",
) -> OptimizationResult:
    """The SLSQP max-Sharpe core, once a returns DataFrame exists —
    extracted verbatim out of compute_portfolio_optimization (below) so a
    second data source (research-lab strategy P&L series) reuses the exact
    same optimizer rather than a parallel copy.

    NOTE the `n * max_weight < 1.0` feasibility check deliberately does NOT
    live here — it stays in each wrapper, because it must fire before any
    price fetch (tests/test_optimizer.py's
    test_infeasible_with_two_holdings_and_default_cap asserts exactly that
    by raising AssertionError from its prices_fn)."""
    warnings = warnings if warnings is not None else []
    tickers = list(weights.keys())
    n = len(tickers)

    n_obs = len(asset_returns)
    if n_obs < MIN_OBS_FOR_ANY_ESTIMATE:
        raise InsufficientHistoryError(n_obs, label=insufficient_history_label)

    mean_returns = asset_returns.mean() * TRADING_DAYS_PER_YEAR
    cov_matrix = asset_returns.cov() * TRADING_DAYS_PER_YEAR

    def negative_sharpe(w: np.ndarray) -> float:
        return -_portfolio_stats(w, mean_returns, cov_matrix, risk_free_rate).sharpe

    x0 = np.full(n, 1.0 / n)
    bounds = [(0.0, max_weight)] * n
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

    result = minimize(negative_sharpe, x0, method="SLSQP", bounds=bounds, constraints=constraints)
    if not result.success:
        raise OptimizationInfeasibleError(f"Optimizer did not converge: {result.message}")

    optimized_w = np.clip(result.x, 0.0, max_weight)
    optimized_w = optimized_w / optimized_w.sum()
    optimized_w = np.round(optimized_w, 4)

    optimized_stats = _portfolio_stats(optimized_w, mean_returns, cov_matrix, risk_free_rate)
    current_w = np.array([weights[t] for t in tickers])
    current_stats = _portfolio_stats(current_w, mean_returns, cov_matrix, risk_free_rate)

    return OptimizationResult(
        as_of=as_of,
        optimized_weights=dict(zip(tickers, optimized_w.tolist())),
        optimized=optimized_stats,
        current=current_stats,
        warnings=warnings,
    )


def compute_portfolio_optimization(
    weights: dict[str, float],
    lookback_years: int,
    prices_fn: PricesFn,
    risk_free_rate: float,
    max_weight: float = DEFAULT_MAX_WEIGHT,
) -> OptimizationResult:
    """Long-only max-Sharpe mean-variance optimization. `weights`' keys
    define the investable universe; its values are the "current" allocation
    used for the before/after comparison in the response."""
    warnings: list[str] = []
    tickers = list(weights.keys())
    n = len(tickers)

    if n * max_weight < 1.0 - 1e-9:
        raise OptimizationInfeasibleError(
            f"Cannot allocate 100% weight with a per-holding cap of {max_weight:.0%} "
            f"across only {n} holdings — raise the cap or add holdings."
        )

    end = date.today()
    start = end - timedelta(days=int(lookback_years * 365.25))
    prices, missing = prices_fn(tickers, start, end)

    missing_required = [t for t in tickers if t not in prices.columns]
    if missing_required:
        raise MissingTickerDataError(missing_required)
    if missing:
        warnings.append(f"No data returned for: {', '.join(missing)}")

    asset_returns = returns_svc.compute_daily_returns(prices[tickers]).dropna()

    return compute_portfolio_optimization_from_returns(
        asset_returns,
        weights,
        risk_free_rate,
        as_of=str(prices.index.max().date()),
        max_weight=max_weight,
        warnings=warnings,
    )
