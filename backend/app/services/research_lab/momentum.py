from collections.abc import Callable
from datetime import date, timedelta

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

STRATEGY_NAME = "momentum_v1"

DEFAULT_FIT_WINDOW_DAYS = 90  # shorter than pairs' 252d — momentum decays faster than a slow equilibrium fit
DEFAULT_ENTRY_Z = 2.0
DEFAULT_EXIT_Z = 0.0
DEFAULT_COST_BPS = 5.0  # half of pairs' 10bps — one leg instead of two
DEFAULT_LOOKBACK_YEARS = 5

# Same reasoning as ou_pairs.py's own floor — below this many out-of-sample
# trading days, a walk-forward result is too thin to mean anything.
MIN_OUT_OF_SAMPLE_TRADING_DAYS = 60

# Reused from ou_pairs.py's NOT_MEAN_REVERTING_THRESHOLD, not independently
# recalibrated for momentum — see the manual real-ticker sanity check in
# the implementation plan before treating this as validated.
NOT_TRENDING_THRESHOLD = 0.05

PricesFn = Callable[[list[str], date, date], tuple[pd.DataFrame, list[str]]]


def fit_momentum_window(window: pd.DataFrame) -> StrategyFit:
    """One walk-forward step's fit: OLS regression of log price on a plain
    time index — the slope's t-statistic is the momentum signal, positive
    for an uptrend and negative for a downtrend with no sign negation
    anywhere (this is *why* regression-on-time is the right primitive over
    a manually-negated raw-return signal, which would need a fragile -1
    multiplier a future refactor could silently drop).

    `is_valid` is gated on statistical significance (p <= 0.05) rather
    than any structural condition — unlike the OU pairs fit, momentum has
    no "this doesn't make mathematical sense" case the way an AR(1)
    coefficient outside (0,1) is; any OLS slope is a coherent trend
    estimate. Gating on significance instead is what keeps the aggregate
    "was this actually trending" statistics non-vacuous, at the cost of
    momentum trading less often than pairs on typical daily-bar tickers
    (expected: daily single-stock trend is close to a random walk over
    most 60-90 day windows) — a deliberate honesty tradeoff, not a mirror
    of pairs' gate."""
    log_price = window["log_price"].to_numpy()

    if np.std(log_price) == 0:
        return StrategyFit(is_valid=False, z_score=None, fit_quality=None, params={})

    t = np.arange(len(log_price), dtype=float)
    slope, _intercept, r_value, p_value, std_err = linregress(t, log_price)
    r_squared = float(r_value**2)

    if std_err == 0 or not np.isfinite(std_err):
        return StrategyFit(is_valid=False, z_score=None, fit_quality=None, params={})

    t_stat = float(slope / std_err)

    fit_quality: str
    if p_value > 0.05 or r_squared < 0.1:
        fit_quality = "weak"
    elif r_squared < 0.4:
        fit_quality = "moderate"
    else:
        fit_quality = "strong"

    is_valid = bool(p_value <= 0.05)

    return StrategyFit(
        is_valid=is_valid,
        z_score=(t_stat if is_valid else None),
        fit_quality=fit_quality,  # type: ignore[arg-type]
        params={"slope": float(slope), "r_squared": r_squared, "t_stat": t_stat},
    )


def apply_momentum_threshold_rule(
    momentum_z: float | None, is_valid: bool, prev_position: int, entry_z: float, exit_z: float
) -> int:
    """Trend-following convention — the OPPOSITE mapping from
    apply_zscore_threshold_rule's mean-reversion convention: strongly
    POSITIVE momentum_z (confirmed uptrend) enters LONG; strongly NEGATIVE
    momentum_z (confirmed downtrend) enters SHORT. Every comparison
    direction here is deliberately flipped from the mean-reversion rule —
    never derive this by negating a mean-reversion decision, since a
    silently-backwards momentum strategy would trade against every trend
    and would pass any test that only checks "a position was taken.\""""
    if not is_valid or momentum_z is None:
        return 0

    if prev_position == 0:
        if momentum_z >= entry_z:
            return 1
        if momentum_z <= -entry_z:
            return -1
        return 0
    if prev_position == 1:
        return 1 if momentum_z > exit_z else 0
    if prev_position == -1:
        return -1 if momentum_z < -exit_z else 0
    return 0


def realize_momentum_return(row: pd.Series, fit: StrategyFit) -> float:
    """Return per +1 (long) unit of position — single asset, full
    notional, no hedge ratio needed."""
    del fit  # unused — momentum's position sizing needs no fit params, unlike pairs' hedge_ratio
    return float(row["ret"])


def build_momentum_raw_data(prices: pd.DataFrame, ticker: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "log_price": np.log(prices[ticker]),
            "ret": prices[ticker].pct_change(),
        }
    ).dropna()


def run_momentum_backtest(
    ticker: str,
    lookback_years: int,
    prices_fn: PricesFn,
    config: WalkForwardConfig,
) -> ExperimentResult:
    end = date.today()
    start = end - timedelta(days=round(lookback_years * 365.25))
    prices, _missing = prices_fn([ticker], start, end)

    if ticker not in prices.columns:
        raise MissingTickerDataError([ticker], label="ticker")

    raw_data = build_momentum_raw_data(prices, ticker)

    # Point-in-time S&P 500 membership disclosure. The candidate reaching
    # this function was drawn from ticker_universe.SCREENING_UNIVERSE — a
    # snapshot of TODAY's index — while this replay covers `lookback_years`
    # of history in which it may not have been a member at all. Scoped to
    # the out-of-sample slice run_walk_forward actually scores, not the
    # leading fit window. Discloses rather than clips; see
    # build_membership_warnings for why.
    membership_warnings = build_membership_warnings(ticker, raw_data.index[config.fit_window_days :])

    n_out_of_sample = len(raw_data) - config.fit_window_days
    if n_out_of_sample < MIN_OUT_OF_SAMPLE_TRADING_DAYS:
        return ExperimentResult(
            status="insufficient_history",
            n_trading_days=len(raw_data),
            n_out_of_sample_days=max(0, n_out_of_sample),
            warnings=membership_warnings,
        )

    result = run_walk_forward(
        raw_data,
        config,
        fit_momentum_window,
        realize_momentum_return,
        decide_position_fn=apply_momentum_threshold_rule,
        direction_labels=("long", "short"),
    )

    if result.pct_days_mean_reverting < NOT_TRENDING_THRESHOLD:
        result.status = "not_trending"

    result.warnings.extend(membership_warnings)
    return result
