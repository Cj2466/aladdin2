from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from app.schemas.research_lab import PairsBacktestResponse
from app.services.research_lab import momentum, ou_pairs
from app.services.research_lab.backtest_result import (
    build_momentum_backtest_response,
    build_pairs_backtest_response,
    compute_momentum_backtest_input_hash,
    compute_pairs_backtest_input_hash,
)
from app.services.research_lab.engine import (
    ExperimentResult,
    StrategyFit,
    TargetLeg,
    WalkForwardConfig,
    WalkForwardState,
    apply_zscore_threshold_rule,
)
from app.services.research_lab.ou_pairs import PricesFn


@dataclass(frozen=True)
class StrategyAdapter:
    """Everything SweepRunner/ForwardValidationRunner need to process a row
    without hardcoding which strategy it belongs to — the only two call
    sites in the codebase that load rows generically (by status, not by
    strategy_name) and must behave differently per row. Every callable
    here uses the same uniform (ticker_a, ticker_b, ...) shape pairs
    already has natively; a single-asset strategy's adapter wraps its own
    clean singular-ticker functions to match, keeping that strategy's
    public API idiomatic and isolating all "make it look 2-ticker-shaped"
    plumbing to this one file."""

    strategy_name: str
    build_raw_data: Callable[[pd.DataFrame, str, str], pd.DataFrame]
    fit_fn: Callable[[pd.DataFrame], StrategyFit]
    return_fn: Callable[[pd.Series, StrategyFit], float]
    decide_position_fn: Callable[[float | None, bool, int, float, float], int]
    direction_labels: tuple[str, str]
    run_backtest: Callable[[str, str, int, PricesFn, WalkForwardConfig], ExperimentResult]
    compute_input_hash: Callable[..., str]
    build_response: Callable[..., PairsBacktestResponse]
    # ExecutionRunner is the third generic call site: it loads registrations
    # by status, not by strategy_name, and must turn each one's persisted
    # WalkForwardState into real dollar targets. Registered here rather than
    # special-cased in the runner — this seam is exactly what the adapter is
    # for.
    compute_target_legs: Callable[[WalkForwardState, str, str], list[TargetLeg]]


_registry: dict[str, StrategyAdapter] = {}


def register_strategy(adapter: StrategyAdapter) -> None:
    _registry[adapter.strategy_name] = adapter


def get_adapter(strategy_name: str) -> StrategyAdapter:
    try:
        return _registry[strategy_name]
    except KeyError:
        raise ValueError(f"Unknown strategy_name: {strategy_name!r}") from None


def _momentum_run_backtest(
    ticker_a: str, ticker_b: str, lookback_years: int, prices_fn: PricesFn, config: WalkForwardConfig
) -> ExperimentResult:
    del ticker_b  # always == ticker_a for a single-asset strategy row
    return momentum.run_momentum_backtest(ticker_a, lookback_years, prices_fn, config)


def _momentum_compute_input_hash(
    *, ticker_a: str, ticker_b: str, fit_window_days: int, entry_z: float, exit_z: float, cost_bps: float, lookback_years: int
) -> str:
    del ticker_b
    return compute_momentum_backtest_input_hash(
        ticker=ticker_a,
        fit_window_days=fit_window_days,
        entry_z=entry_z,
        exit_z=exit_z,
        cost_bps=cost_bps,
        lookback_years=lookback_years,
    )


def _momentum_build_response(
    result: ExperimentResult,
    *,
    ticker_a: str,
    ticker_b: str,
    fit_window_days: int,
    entry_z: float,
    exit_z: float,
    cost_bps: float,
    lookback_years: int,
    cached: bool,
    configurations_tested: int = 1,
) -> PairsBacktestResponse:
    del ticker_b
    return build_momentum_backtest_response(
        result,
        ticker=ticker_a,
        fit_window_days=fit_window_days,
        entry_z=entry_z,
        exit_z=exit_z,
        cost_bps=cost_bps,
        lookback_years=lookback_years,
        cached=cached,
        configurations_tested=configurations_tested,
    )


def _momentum_build_raw_data(prices: pd.DataFrame, ticker_a: str, ticker_b: str) -> pd.DataFrame:
    del ticker_b
    return momentum.build_momentum_raw_data(prices, ticker_a)


def _bootstrap() -> None:
    register_strategy(
        StrategyAdapter(
            strategy_name=ou_pairs.STRATEGY_NAME,
            build_raw_data=ou_pairs.build_pairs_raw_data,
            fit_fn=ou_pairs.fit_ou_pairs_window,
            return_fn=ou_pairs.realize_pairs_return,
            decide_position_fn=apply_zscore_threshold_rule,
            direction_labels=("long_spread", "short_spread"),
            run_backtest=ou_pairs.run_pairs_backtest,
            compute_input_hash=compute_pairs_backtest_input_hash,
            build_response=build_pairs_backtest_response,
            compute_target_legs=ou_pairs.compute_pairs_target_legs,
        )
    )
    register_strategy(
        StrategyAdapter(
            strategy_name=momentum.STRATEGY_NAME,
            build_raw_data=_momentum_build_raw_data,
            fit_fn=momentum.fit_momentum_window,
            return_fn=momentum.realize_momentum_return,
            decide_position_fn=momentum.apply_momentum_threshold_rule,
            direction_labels=("long", "short"),
            run_backtest=_momentum_run_backtest,
            compute_input_hash=_momentum_compute_input_hash,
            build_response=_momentum_build_response,
            compute_target_legs=momentum.compute_momentum_target_legs,
        )
    )


_bootstrap()
