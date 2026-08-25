from collections.abc import Callable
from datetime import date, timedelta
from typing import Literal

import numpy as np
import pandas as pd
from scipy.stats import linregress

from app.services.research_lab.engine import (
    ExperimentResult,
    StrategyFit,
    WalkForwardConfig,
    run_walk_forward,
)
from app.services.research_lab.sp500_membership_history import build_membership_warnings
from app.services.risk.errors import MissingTickerDataError

STRATEGY_NAME = "ou_pairs_v1"

DEFAULT_FIT_WINDOW_DAYS = 252
DEFAULT_ENTRY_Z = 2.0
DEFAULT_EXIT_Z = 0.0
DEFAULT_COST_BPS = 10.0
DEFAULT_LOOKBACK_YEARS = 5

# Below this many out-of-sample trading days, a walk-forward result is too
# thin to mean anything — mirrors projection.py's MIN_HISTORY_FOR_BAND
# floor-below-which-refuse-to-project convention.
MIN_OUT_OF_SAMPLE_TRADING_DAYS = 60

# If a valid AR(1) fit (0 < b_coef < 1) essentially never occurs across the
# whole walk-forward run, the pair isn't behaving as mean-reverting over
# this window at all — report that honestly rather than showing an "ok"
# result built almost entirely from forced-flat days.
NOT_MEAN_REVERTING_THRESHOLD = 0.05

PricesFn = Callable[[list[str], date, date], tuple[pd.DataFrame, list[str]]]


def fit_ou_pairs_window(window: pd.DataFrame) -> StrategyFit:
    """One walk-forward step's fit: hedge ratio via OLS on log prices, then
    the OU process's exact discrete-time equivalent — an AR(1) fit on the
    resulting spread. `fit_quality` reflects AR(1) fit quality only; it is
    NOT a cointegration/unit-root test and does not by itself distinguish
    genuine mean-reversion from spurious regression (numerically verified
    this session: independent random walks pass the `0 < b_coef < 1` sanity
    check ~97-100% of the time with a spuriously "strong" score) — that's
    exactly why this result only matters in aggregate, out-of-sample, via
    run_walk_forward's realized Sharpe, not from any single window's fit."""
    log_a = window["log_a"].to_numpy()
    log_b = window["log_b"].to_numpy()

    if np.std(log_a) == 0 or np.std(log_b) == 0:
        return StrategyFit(is_valid=False, z_score=None, fit_quality=None, params={})

    slope, _intercept, _r, _p, _se = linregress(log_a, log_b)
    hedge_ratio = float(slope)
    spread = log_b - hedge_ratio * log_a

    if np.std(spread) == 0:
        return StrategyFit(is_valid=False, z_score=None, fit_quality=None, params={"hedge_ratio": hedge_ratio})

    b_coef, a_coef, r_value, p_value, _se2 = linregress(spread[:-1], spread[1:])
    r_squared = float(r_value**2)

    fit_quality: Literal["weak", "moderate", "strong"]
    if p_value > 0.05 or r_squared < 0.1:
        fit_quality = "weak"
    elif r_squared < 0.4:
        fit_quality = "moderate"
    else:
        fit_quality = "strong"

    if not (0 < b_coef < 1):
        return StrategyFit(
            is_valid=False, z_score=None, fit_quality=fit_quality, params={"hedge_ratio": hedge_ratio}
        )

    mu = a_coef / (1 - b_coef)
    residuals = spread[1:] - (a_coef + b_coef * spread[:-1])
    sigma_eps_sq = float(np.var(residuals, ddof=2))  # 2 estimated params (a_coef, b_coef)
    stationary_var = sigma_eps_sq / (1 - b_coef**2)

    if not np.isfinite(stationary_var) or stationary_var <= 0:
        return StrategyFit(
            is_valid=False, z_score=None, fit_quality=fit_quality, params={"hedge_ratio": hedge_ratio}
        )

    sigma_eq = float(np.sqrt(stationary_var))
    current_spread = float(spread[-1])
    z_score = (current_spread - mu) / sigma_eq

    return StrategyFit(
        is_valid=True,
        z_score=float(z_score),
        fit_quality=fit_quality,
        params={"hedge_ratio": hedge_ratio, "mu": float(mu)},
    )


def realize_pairs_return(row: pd.Series, fit: StrategyFit) -> float:
    """Return per +1 (long-spread) unit of position — the engine multiplies
    this by the actual signed position. Long spread = long $1 of B, short
    $hedge_ratio of A; gross capital deployed is the absolute dollar amount
    on each leg (1 + |hedge_ratio|), not (1 + hedge_ratio) — a negative
    hedge ratio (inversely-related tickers) would otherwise silently
    corrupt the normalization."""
    hedge_ratio = fit.params["hedge_ratio"]
    gross_notional = 1.0 + abs(hedge_ratio)
    return (row["ret_b"] - hedge_ratio * row["ret_a"]) / gross_notional


def build_pairs_raw_data(prices: pd.DataFrame, ticker_a: str, ticker_b: str) -> pd.DataFrame:
    """Shared by run_pairs_backtest and ForwardValidationRunner — guarantees
    both compute log_a/log_b/ret_a/ret_b identically, not two
    implementations that could quietly drift apart."""
    return pd.DataFrame(
        {
            "log_a": np.log(prices[ticker_a]),
            "log_b": np.log(prices[ticker_b]),
            "ret_a": prices[ticker_a].pct_change(),
            "ret_b": prices[ticker_b].pct_change(),
        }
    ).dropna()


def run_pairs_backtest(
    ticker_a: str,
    ticker_b: str,
    lookback_years: int,
    prices_fn: PricesFn,
    config: WalkForwardConfig,
) -> ExperimentResult:
    end = date.today()
    start = end - timedelta(days=round(lookback_years * 365.25))
    prices, _missing = prices_fn([ticker_a, ticker_b], start, end)

    missing_required = [t for t in (ticker_a, ticker_b) if t not in prices.columns]
    if missing_required:
        raise MissingTickerDataError(missing_required, label="pair")

    raw_data = build_pairs_raw_data(prices, ticker_a, ticker_b)

    # Point-in-time S&P 500 membership disclosure, per leg — a pair is only
    # as clean as its worse leg, so both are checked and each speaks for
    # itself. Same reasoning as run_momentum_backtest's identical call.
    replay_index = raw_data.index[config.fit_window_days :]
    membership_warnings = [
        *build_membership_warnings(ticker_a, replay_index),
        *build_membership_warnings(ticker_b, replay_index),
    ]

    n_out_of_sample = len(raw_data) - config.fit_window_days
    if n_out_of_sample < MIN_OUT_OF_SAMPLE_TRADING_DAYS:
        return ExperimentResult(
            status="insufficient_history",
            n_trading_days=len(raw_data),
            n_out_of_sample_days=max(0, n_out_of_sample),
            warnings=membership_warnings,
        )

    result = run_walk_forward(raw_data, config, fit_ou_pairs_window, realize_pairs_return)

    if result.pct_days_mean_reverting < NOT_MEAN_REVERTING_THRESHOLD:
        result.status = "not_mean_reverting"

    result.warnings.extend(membership_warnings)
    return result
