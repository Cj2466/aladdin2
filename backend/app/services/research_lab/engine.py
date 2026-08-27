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
    direction: Literal["long_spread", "short_spread", "long", "short"]
    holding_days: int
    trade_return: float
    still_open: bool


@dataclass
class OpenTrade:
    entry_date: pd.Timestamp
    direction: Literal["long_spread", "short_spread", "long", "short"]
    trade_equity: float
    days_held: int


@dataclass
class WalkForwardState:
    """Everything needed to resume the walk-forward loop one day later —
    JSON-serializable (via serialize_walk_forward_state) so a forward
    -validation registration can persist it between real-time ticks, not
    just carry it as loop-scoped locals within one in-memory backtest."""

    position: int = 0
    equity: float = 1.0
    valid_count: int = 0
    fit_quality_counts: dict[str, int] = field(default_factory=lambda: {"weak": 0, "moderate": 0, "strong": 0})
    open_trade: OpenTrade | None = None
    # The most recent fit's opaque params, carried forward so something
    # OUTSIDE the walk-forward loop can act on them. Nothing in the backtest
    # needs this (each step re-fits and hands `fit` straight to return_fn),
    # but live execution does: a pairs position's two legs can only be sized
    # from that day's hedge_ratio, which was previously computed fresh every
    # tick and discarded every tick — never persisted anywhere. Empty dict on
    # a state that predates this field (see deserialize_walk_forward_state),
    # which self-heals on the registration's next tick.
    last_fit_params: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class TargetLeg:
    """One ticker's share of a strategy instance's target exposure.

    `signed_weight` is a fraction of the capital allocated to that strategy:
    target_notional = signed_weight * allocated_capital. Positive is long,
    negative is short. Lives here, next to WalkForwardState, because both
    per-strategy compute_target_legs implementations read that state and
    neither strategy module imports the other."""

    ticker: str
    signed_weight: float


@dataclass
class ExperimentResult:
    status: Literal["ok", "not_mean_reverting", "insufficient_history", "not_trending"]
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


def step_one_day(
    window: pd.DataFrame,
    day_row: pd.Series,
    fit_fn: Callable[[pd.DataFrame], StrategyFit],
    return_fn: Callable[[pd.Series, StrategyFit], float],
    state: WalkForwardState,
    config: WalkForwardConfig,
    decide_position_fn: Callable[[float | None, bool, int, float, float], int] = apply_zscore_threshold_rule,
    direction_labels: tuple[str, str] = ("long_spread", "short_spread"),
) -> tuple[WalkForwardState, DayResult, Trade | None]:
    """One walk-forward step: fit on `window` (which must not include
    `day_row`'s own date), decide a position, realize `day_row`'s return.
    Returns a NEW state (never mutates the input) plus the day's result
    plus a closed Trade if (and only if) a position flattened this step.

    This is the exact mechanics both `run_walk_forward` (replaying history
    in one pass) and the forward-validation runner (one real day per tick,
    resumed from a persisted state) share — not two implementations that
    could drift apart.

    `decide_position_fn`/`direction_labels` default to the mean-reversion
    convention every existing caller relies on — a strategy with a
    different trading convention (e.g. momentum, which bets WITH a strong
    reading instead of against it) passes its own decision function and
    labels rather than this function ever guessing intent from the sign of
    z_score alone."""
    fit = fit_fn(window)
    new_position = decide_position_fn(fit.z_score, fit.is_valid, state.position, config.entry_z, config.exit_z)

    raw_return = 0.0
    if new_position != 0:
        raw_return = new_position * return_fn(day_row, fit)

    cost = (config.cost_bps / 10_000.0) * abs(new_position - state.position)
    net_return = raw_return - cost
    new_equity = state.equity * (1.0 + net_return)
    current_date = day_row.name

    # Trade bookkeeping — the no-direct-reversal invariant means "entering"
    # and "exiting" are the only two transitions to track. trade_equity and
    # days_held both accumulate for every day a trade is open, INCLUDING
    # the day it closes (that day's cost still belongs to the trade) —
    # holding_days then subtracts 1 at close/finalize time to exclude that
    # closing day from the count, matching this module's original
    # (already-shipped, already-tested) index-arithmetic convention exactly.
    open_trade = state.open_trade
    if state.position == 0 and new_position != 0:
        open_trade = OpenTrade(
            entry_date=current_date,
            direction=direction_labels[0] if new_position == 1 else direction_labels[1],
            trade_equity=1.0,
            days_held=0,
        )

    closed_trade: Trade | None = None
    if open_trade is not None:
        open_trade = OpenTrade(
            entry_date=open_trade.entry_date,
            direction=open_trade.direction,
            trade_equity=open_trade.trade_equity * (1.0 + net_return),
            days_held=open_trade.days_held + 1,
        )
        if state.position != 0 and new_position == 0:
            closed_trade = Trade(
                entry_date=open_trade.entry_date,
                exit_date=current_date,
                direction=open_trade.direction,
                holding_days=open_trade.days_held - 1,
                trade_return=open_trade.trade_equity - 1.0,
                still_open=False,
            )
            open_trade = None

    new_fit_quality_counts = dict(state.fit_quality_counts)
    if fit.is_valid and fit.fit_quality is not None:
        new_fit_quality_counts[fit.fit_quality] += 1

    new_state = WalkForwardState(
        position=new_position,
        equity=new_equity,
        valid_count=state.valid_count + (1 if fit.is_valid else 0),
        fit_quality_counts=new_fit_quality_counts,
        open_trade=open_trade,
        # Unconditionally, every step, INCLUDING invalid-fit steps:
        # fit_ou_pairs_window still returns a hedge_ratio on three of its four
        # invalid-return paths, and a state that goes flat on an invalid fit
        # still needs the ratio available the moment it re-enters.
        last_fit_params=dict(fit.params),
    )
    day_result = DayResult(
        date=current_date,
        position=new_position,
        z_score=fit.z_score,
        raw_return=raw_return,
        cost=cost,
        net_return=net_return,
        equity=new_equity,
    )
    return new_state, day_result, closed_trade


def finalize_open_trade(state: WalkForwardState, as_of_date: pd.Timestamp) -> Trade | None:
    """Batch-backtest-only: called once, after run_walk_forward's loop
    ends, to close any still-open position as still_open=True. The
    forward-validation runner NEVER calls this — an open forward position
    just stays represented in carry_state indefinitely, closed only when
    the strategy's own rule actually flattens it."""
    del as_of_date  # kept for interface clarity; the close date isn't itself recorded for a still-open trade
    if state.open_trade is None:
        return None
    return Trade(
        entry_date=state.open_trade.entry_date,
        exit_date=None,
        direction=state.open_trade.direction,
        holding_days=state.open_trade.days_held - 1,
        trade_return=state.open_trade.trade_equity - 1.0,
        still_open=True,
    )


def summarize_fit_stats(state: WalkForwardState, n_days: int) -> tuple[float, dict[str, float]]:
    """Extracted so the forward-validation endpoint can compute
    'pct_days_mean_reverting'/'fit_quality_distribution' from a persisted
    WalkForwardState without re-deriving the formula."""
    pct_days_mean_reverting = state.valid_count / n_days if n_days > 0 else 0.0
    total_quality = sum(state.fit_quality_counts.values())
    fit_quality_distribution = {
        k: (v / total_quality if total_quality > 0 else 0.0) for k, v in state.fit_quality_counts.items()
    }
    return pct_days_mean_reverting, fit_quality_distribution


def serialize_walk_forward_state(state: WalkForwardState) -> dict:
    return {
        "position": state.position,
        "equity": state.equity,
        "valid_count": state.valid_count,
        "fit_quality_counts": state.fit_quality_counts,
        "open_trade": (
            {
                "entry_date": state.open_trade.entry_date.strftime("%Y-%m-%d"),
                "direction": state.open_trade.direction,
                "trade_equity": state.open_trade.trade_equity,
                "days_held": state.open_trade.days_held,
            }
            if state.open_trade is not None
            else None
        ),
        "last_fit_params": state.last_fit_params,
    }


def deserialize_walk_forward_state(data: dict) -> WalkForwardState:
    open_trade = None
    raw_open_trade = data.get("open_trade")
    if raw_open_trade is not None:
        open_trade = OpenTrade(
            entry_date=pd.Timestamp(raw_open_trade["entry_date"]),
            direction=raw_open_trade["direction"],
            trade_equity=raw_open_trade["trade_equity"],
            days_held=raw_open_trade["days_held"],
        )
    return WalkForwardState(
        position=data["position"],
        equity=data["equity"],
        valid_count=data["valid_count"],
        fit_quality_counts=data["fit_quality_counts"],
        open_trade=open_trade,
        # .get(), not data["last_fit_params"] — every carry_state_json row
        # persisted before this field existed must still round-trip. Such a
        # state deserializes with an empty dict, which compute_pairs_target_legs
        # treats as "hedge ratio not known yet, stay flat", and the next tick
        # repopulates it. No migration: carry_state_json is an opaque Text
        # column, so this is purely a serialization-format change inside it.
        last_fit_params=data.get("last_fit_params", {}),
    )


def run_walk_forward(
    raw_data: pd.DataFrame,
    config: WalkForwardConfig,
    fit_fn: Callable[[pd.DataFrame], StrategyFit],
    return_fn: Callable[[pd.Series, StrategyFit], float],
    decide_position_fn: Callable[[float | None, bool, int, float, float], int] = apply_zscore_threshold_rule,
    direction_labels: tuple[str, str] = ("long_spread", "short_spread"),
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
    state = WalkForwardState()

    for t in range(config.fit_window_days, n):
        window = raw_data.iloc[t - config.fit_window_days : t]
        day_row = raw_data.iloc[t]
        state, day_result, closed_trade = step_one_day(
            window, day_row, fit_fn, return_fn, state, config, decide_position_fn, direction_labels
        )
        day_results.append(day_result)
        if closed_trade is not None:
            trades.append(closed_trade)

    if n > 0:
        final_trade = finalize_open_trade(state, raw_data.index[-1])
        if final_trade is not None:
            trades.append(final_trade)

    n_out_of_sample = n - config.fit_window_days
    pct_days_mean_reverting, fit_quality_distribution = summarize_fit_stats(state, n_out_of_sample)

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
