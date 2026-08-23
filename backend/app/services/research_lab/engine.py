from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd


@dataclass
class WalkForwardConfig:
    fit_window_days: int
    entry_z: float
    exit_z: float
    cost_bps: float


@dataclass
class StrategyFit:
    is_valid: bool
    z_score: float | None
    fit_quality: Literal["weak", "moderate", "strong"] | None
    params: dict[str, float]  # opaque to the engine — whatever the strategy's return_fn needs


@dataclass
class DayResult:
    date: pd.Timestamp
    position: int
    z_score: float | None
    raw_return: float
    cost: float
    net_return: float
    equity: float


@dataclass
class Trade:
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp | None
    direction: Literal["long_spread", "short_spread"]
    holding_days: int
    trade_return: float
    still_open: bool


@dataclass
class ExperimentResult:
    status: Literal["ok", "not_mean_reverting", "insufficient_history"]
    n_trading_days: int
    n_out_of_sample_days: int
    day_results: list[DayResult] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)
    pct_days_mean_reverting: float = 0.0
    fit_quality_distribution: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def apply_zscore_threshold_rule(
    z_score: float | None, is_valid: bool, prev_position: int, entry_z: float, exit_z: float
) -> int:
    """Deterministic state machine: never jumps directly from +1 to -1 (or
    vice versa) in one step — always transits through flat first, which
    also keeps the transaction-cost accounting unambiguous (at most one
    "unit" of position change per day)."""
    if not is_valid or z_score is None:
        return 0  # never trust an untrustworthy fit — force flat regardless of prior position

    if prev_position == 0:
        if z_score <= -entry_z:
            return 1
        if z_score >= entry_z:
            return -1
        return 0
    if prev_position == 1:
        return 1 if z_score < -exit_z else 0
    if prev_position == -1:
        return -1 if z_score > exit_z else 0
    return 0


def run_walk_forward(
    raw_data: pd.DataFrame,
    config: WalkForwardConfig,
    fit_fn: Callable[[pd.DataFrame], StrategyFit],
    return_fn: Callable[[pd.Series, StrategyFit], float],
) -> ExperimentResult:
    """Strategy-agnostic walk-forward loop. For day t, fit_fn only ever sees
    raw_data[t-fit_window_days : t] — day t itself is structurally excluded
    from the window, which is what makes the day-t position decision
    incapable of seeing day t's own price move (proven by test_research_lab's
    look-ahead-bias test, not just asserted here).

    fit_fn and return_fn are strategy-specific; this function has no
    knowledge of what "log_a"/"hedge_ratio"/etc. mean — it only knows about
    StrategyFit's generic shape and integer positions in {-1, 0, +1}."""
    n = len(raw_data)
    day_results: list[DayResult] = []
    trades: list[Trade] = []

    position = 0
    equity = 1.0
    valid_count = 0
    fit_quality_counts = {"weak": 0, "moderate": 0, "strong": 0}

    trade_start_date: pd.Timestamp | None = None
    trade_start_index: int | None = None
    trade_direction: Literal["long_spread", "short_spread"] | None = None
    trade_equity = 1.0

    for t in range(config.fit_window_days, n):
        window = raw_data.iloc[t - config.fit_window_days : t]
        fit = fit_fn(window)

        new_position = apply_zscore_threshold_rule(
            fit.z_score, fit.is_valid, position, config.entry_z, config.exit_z
        )

        raw_return = 0.0
        if new_position != 0:
            raw_return = new_position * return_fn(raw_data.iloc[t], fit)

        cost = (config.cost_bps / 10_000.0) * abs(new_position - position)
        net_return = raw_return - cost
        equity *= 1.0 + net_return
        current_date = raw_data.index[t]

        # Trade bookkeeping — the no-direct-reversal invariant above means
        # "entering" and "exiting" are the only two transitions to track.
        if position == 0 and new_position != 0:
            trade_start_date = current_date
            trade_start_index = t
            trade_direction = "long_spread" if new_position == 1 else "short_spread"
            trade_equity = 1.0

        if trade_start_date is not None:
            trade_equity *= 1.0 + net_return

        if position != 0 and new_position == 0:
            assert trade_start_date is not None and trade_start_index is not None and trade_direction is not None
            trades.append(
                Trade(
                    entry_date=trade_start_date,
                    exit_date=current_date,
                    direction=trade_direction,
                    holding_days=t - trade_start_index,
                    trade_return=trade_equity - 1.0,
                    still_open=False,
                )
            )
            trade_start_date = None
            trade_start_index = None
            trade_direction = None

        day_results.append(
            DayResult(
                date=current_date,
                position=new_position,
                z_score=fit.z_score,
                raw_return=raw_return,
                cost=cost,
                net_return=net_return,
                equity=equity,
            )
        )

        if fit.is_valid:
            valid_count += 1
            if fit.fit_quality is not None:
                fit_quality_counts[fit.fit_quality] += 1

        position = new_position

    if trade_start_date is not None and trade_start_index is not None and trade_direction is not None:
        trades.append(
            Trade(
                entry_date=trade_start_date,
                exit_date=None,
                direction=trade_direction,
                holding_days=(n - 1) - trade_start_index,
                trade_return=trade_equity - 1.0,
                still_open=True,
            )
        )

    n_out_of_sample = n - config.fit_window_days
    pct_days_mean_reverting = valid_count / n_out_of_sample if n_out_of_sample > 0 else 0.0
    total_quality = sum(fit_quality_counts.values())
    fit_quality_distribution = {
        k: (v / total_quality if total_quality > 0 else 0.0) for k, v in fit_quality_counts.items()
    }

    return ExperimentResult(
        status="ok",
        n_trading_days=n,
        n_out_of_sample_days=n_out_of_sample,
        day_results=day_results,
        trades=trades,
        pct_days_mean_reverting=pct_days_mean_reverting,
        fit_quality_distribution=fit_quality_distribution,
        warnings=[],
    )
