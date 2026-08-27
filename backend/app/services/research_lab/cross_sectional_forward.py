"""Ticking a CROSS-SECTIONAL strategy one real trading day forward.

WHAT THIS IS AND WHY IT IS SEPARATE FROM engine.py. engine.py's
step_one_day advances a strategy that decides a position in {-1, 0, +1}
EVERY day from a fit over a trailing window — the shape ou_pairs and
momentum have, and the only shape the existing ForwardValidationRunner can
tick. A cross-sectional strategy has a structurally different shape:

  * It holds a PORTFOLIO (a dict of signed per-ticker weights), not a
    scalar position.
  * It only reforms every spec.holding_days rows. On the ~179 days out of
    180 that are NOT a formation date, the correct behavior is to hold the
    existing book and realize its real P&L — the signal is not consulted at
    all, and re-deciding daily would be a different (and much more
    expensive) strategy than the one that was backtested.
  * Its costs come in two structurally different components that the pairs
    engine has no concept of: a TURNOVER charge paid once per formation,
    and a TIME-based financing charge accrued per calendar day held (see
    cross_sectional.py's two-cost CONVENTIONS bullet).

So this module is to cross_sectional.py what step_one_day is to
run_walk_forward: the same mechanics, resumable one real day at a time from
a persisted state, rather than replayed in one in-memory pass.

THE ANTI-DRIFT RULE, which is the whole reason this file is as short as it
is. Every piece of arithmetic below that decides WHAT IS HELD or WHAT IT
EARNED is a call into cross_sectional.py's own functions:

  * cross_sectional.form_portfolio  — point-in-time eligibility, the
    history view, the signal, ranking, leg weighting (including the
    inverse-vol/value fallbacks), net target weights, turnover, and the
    turnover cost.
  * cross_sectional.realize_formation_day — the long-minus-short weighted
    daily return, including the drop-and-renormalize treatment of a name
    that stops printing mid-hold.
  * cross_sectional.FINANCING_DAYS_PER_YEAR — the calendar-day financing
    accrual base.

Those are the SAME functions run_cross_sectional_backtest's _replay_sleeve
calls (they were extracted FROM it, not written alongside it). A forward
validation whose daily P&L came from a second implementation of the
harness's math would not be validating the backtested strategy; it would be
validating a lookalike. This module therefore contains no leg construction,
no weighting, no ranking and no cost formula of its own — only the
bookkeeping that turns "replay a whole history" into "resume where the last
real day left off".

NO LOOK-AHEAD, STRUCTURALLY. A tick that steps onto row p calls
form_portfolio(..., position=p), which slices the panel to rows
[p - lookback + 1, p] before the signal function ever sees it. Rows after p
are not in the frame handed to the signal, exactly as in the batch replay.
On a live tick p is the panel's last row — today — so there is no future
data anywhere in the process to leak in the first place.

WHAT IS DELIBERATELY NOT SUPPORTED, refused loudly at registration time
rather than silently approximated (see validate_spec_is_forward_tickable):

  * spec.cohort_formation_days (overlapping Jegadeesh-Titman sleeves). The
    batch harness runs holding_days // cohort_formation_days independent
    staggered sleeves and blends them. Ticking that forward means carrying
    several concurrent books, each with its own formation clock and its own
    share of the financing base. That is buildable, but no family in this
    project sets the field (the Crypto family explicitly refuses it), so
    building it now would be untested speculative machinery in a path whose
    single correctness bar is that it must not quietly differ from the
    backtest.
  * config.impute_delisting_returns. The imputation fires on the day a
    ticker's price stops appearing ANYWHERE LATER in the loaded frame
    (_compute_delisting_positions) — a judgment that requires seeing the
    future of the series. Live, the last row is always the frame's end, so
    "permanently gone" is not knowable today and the flag could only ever
    be approximated. Forward ticking therefore always uses the harness's
    DEFAULT convention (drop the name, renormalize the survivors — i.e.
    liquidate at the last real price), and a family that opted into
    imputation is refused rather than ticked under a different convention
    than it was backtested with.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from app.services.research_lab.cross_sectional import (
    FINANCING_DAYS_PER_YEAR,
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalSpec,
    MembershipFn,
    form_portfolio,
    realize_formation_day,
)

# How many unprocessed panel rows one call to advance_forward_validation may
# catch up on. A tick that finds several new rows (the runner was down, or a
# 24/7 crypto panel published rows while the process was restarting) must
# realize EVERY one of them: skipping straight to the newest row would drop
# the intervening days' real returns from the track record while still
# counting the price move across them, which would corrupt exactly the
# quantity this whole mechanism exists to measure honestly.
#
# Bounded anyway so one tick can never turn into an unbounded replay of
# years of history — successive ticks continue where this one stopped, and
# at the runner's 30-minute cadence a bounded catch-up drains a long outage
# within hours. 90 rows is a calendar quarter of a 24/7 panel.
MAX_CATCHUP_ROWS_PER_TICK = 90


class ForwardTickNotSupportedError(ValueError):
    """A spec or config whose backtested behavior this forward ticker cannot
    reproduce exactly (see the module docstring's "deliberately not
    supported" section). Raised at REGISTRATION time, never mid-tick, so an
    unsupported configuration can never start a 126-day clock it would
    silently be running under different rules than its own backtest."""


@dataclass
class CrossSectionalForwardState:
    """Everything needed to resume a cross-sectional replay one real day
    later — JSON-serializable, the same contract engine.WalkForwardState
    keeps for the pairs/momentum path.

    rows_since_formation is the load-bearing field and its None is
    meaningful: None means NO BOOK HAS EVER BEEN FORMED (the registration
    exists but its first formation has not happened yet), while 0 means a
    book was formed on the most recently processed row and nothing has been
    realized against it yet. The two are different — the first says "do not
    realize anything today", the second says "realize today and charge this
    book's turnover cost while doing it"."""

    equity: float = 1.0
    # The book currently held. long_weights/short_weights are what
    # realize_formation_day is called with each day; net_weights is the
    # signed net book the NEXT formation measures its turnover against.
    long_weights: dict[str, float] = field(default_factory=dict)
    short_weights: dict[str, float] = field(default_factory=dict)
    net_weights: dict[str, float] = field(default_factory=dict)
    rows_since_formation: int | None = None
    # The most recent formation's turnover charge, waiting to be applied on
    # that formation's FIRST realization day — the harness's own convention
    # (_replay_sleeve charges it at j == i + 1), which is what keeps the
    # cost landing on the day the rebalance actually settles into the
    # return stream rather than on the formation close itself.
    pending_turnover_cost: float = 0.0
    gross_notional_held: float = 0.0
    n_formations: int = 0
    n_realized_days: int = 0
    last_formation_date: str | None = None


@dataclass
class CrossSectionalForwardDayResult:
    """One processed real day.

    `realized` is False on exactly one kind of day: a formation that had
    nothing to realize against it yet (the very first day of a
    registration). Those days are recorded — they are real processed days
    and the audit trail should show them — but they are NOT counted toward
    n_forward_trading_days, because a day with no realized return is not a
    day of out-of-sample track record.

    `net_return` is named to match the pairs path's day-result dicts
    deliberately: forward_validation_service.check_underperformance reads
    exactly that key and nothing else, so the auto-pruning rule already
    shipped for pairs/momentum applies here through the same function
    rather than through a second copy of it."""

    date: pd.Timestamp
    realized: bool
    reformed: bool
    gross_return: float
    turnover_cost: float
    financing_cost: float
    net_return: float
    equity: float
    n_long: int
    n_short: int
    n_eligible: int | None
    turnover: float | None
    skipped_reason: str | None


def validate_spec_is_forward_tickable(spec: CrossSectionalSpec, config: CrossSectionalConfig) -> None:
    """Refuse, loudly and up front, any spec/config this ticker cannot
    reproduce EXACTLY as the batch harness would. See the module docstring
    for why each of these is a refusal rather than an approximation."""
    if spec.cohort_formation_days is not None:
        raise ForwardTickNotSupportedError(
            f"{spec.pattern_id} sets cohort_formation_days={spec.cohort_formation_days} (overlapping "
            "cohorts). Forward ticking carries ONE book; reproducing several staggered concurrent "
            "sleeves is unbuilt, and approximating them with a single sleeve would forward-validate a "
            "different strategy than the one that was backtested."
        )
    if config.impute_delisting_returns:
        raise ForwardTickNotSupportedError(
            f"{spec.pattern_id}'s config sets impute_delisting_returns=True. That imputation fires on "
            "the day a price stops appearing anywhere LATER in the frame, which is not knowable on a "
            "live tick (today is always the frame's end). Forward ticking always uses the harness's "
            "default drop-and-renormalize convention, so this family would be ticked under different "
            "cost rules than it was backtested with."
        )
    if spec.holding_days < 1:
        raise ForwardTickNotSupportedError(f"{spec.pattern_id} has holding_days={spec.holding_days}.")


def step_one_cross_sectional_day(
    data: CrossSectionalData,
    spec: CrossSectionalSpec,
    config: CrossSectionalConfig,
    is_member: MembershipFn,
    state: CrossSectionalForwardState,
    position: int,
) -> tuple[CrossSectionalForwardState, CrossSectionalForwardDayResult]:
    """Advance one row. Returns a NEW state (never mutates the input) plus
    that day's result.

    ORDER OF OPERATIONS, and why it is realize-then-reform. In the batch
    harness a formation at row i is held through row i + holding_days, and
    the NEXT formation is at that same row i + holding_days — so that row is
    simultaneously the old book's last realized day and the new book's
    formation date. Realizing first and reforming second reproduces that
    exactly. Reforming first would silently earn the last day of each hold
    on the NEW book, which is a different strategy (and a mildly
    look-ahead-flavored one).

    `position` must be >= 1: realizing a day needs the previous row to
    price it against."""
    index = data.close.index
    if position < 1 or position >= len(index):
        raise ValueError(f"position {position} out of range for a panel of {len(index)} rows (needs 1..n-1).")

    today = index[position]

    gross_return = 0.0
    turnover_cost = 0.0
    financing_cost = 0.0
    net_return = 0.0
    equity = state.equity
    realized = False
    rows_since_formation = state.rows_since_formation
    pending_turnover_cost = state.pending_turnover_cost
    n_realized_days = state.n_realized_days

    if rows_since_formation is not None:
        # --- realize today's P&L on the book held since yesterday's close --
        # Only the two rows that price this day are used. pct_change is
        # row-local, so this is exactly the value the batch harness's
        # whole-frame daily_returns_all.iloc[position] carries, NaNs and
        # all — a name with no price on either row yields NaN and is
        # dropped-and-renormalized inside _leg_weighted_return.
        day_returns = data.close.iloc[position - 1 : position + 1].pct_change(fill_method=None).iloc[-1]
        gross_return = realize_formation_day(day_returns, state.long_weights, state.short_weights)

        # The formation's turnover charge lands on its FIRST realization
        # day — _replay_sleeve's `cost if j == i + 1` convention, which is
        # precisely "the first realized day after the formation row".
        turnover_cost = pending_turnover_cost if rows_since_formation == 0 else 0.0
        pending_turnover_cost = 0.0

        financing_per_notional_day = (config.financing_bps_per_year / 10_000.0) / FINANCING_DAYS_PER_YEAR
        if financing_per_notional_day and state.gross_notional_held:
            calendar_days_held = float((index[position] - index[position - 1]).days)
            financing_cost = financing_per_notional_day * state.gross_notional_held * calendar_days_held

        net_return = gross_return - turnover_cost - financing_cost
        equity = state.equity * (1.0 + net_return)
        realized = True
        rows_since_formation += 1
        n_realized_days += 1

    # --- reform? --------------------------------------------------------
    # Two triggers, both from the batch schedule: there is no book yet (the
    # registration's very first day), or this book has been held for its
    # full holding_days and today is its successor formation date.
    reform = rows_since_formation is None or rows_since_formation >= spec.holding_days

    long_weights = state.long_weights
    short_weights = state.short_weights
    net_weights = state.net_weights
    gross_notional_held = state.gross_notional_held
    n_formations = state.n_formations
    last_formation_date = state.last_formation_date
    n_eligible: int | None = None
    turnover: float | None = None
    skipped_reason: str | None = None

    if reform:
        outcome = form_portfolio(data, spec, config, is_member, position, state.net_weights)
        long_weights = outcome.long_weights
        short_weights = outcome.realized_short_weights
        net_weights = outcome.net_weights
        pending_turnover_cost = outcome.turnover_cost
        gross_notional_held = outcome.gross_notional_held
        rows_since_formation = 0
        n_formations += 1
        last_formation_date = today.strftime("%Y-%m-%d")
        n_eligible = outcome.record.n_eligible
        turnover = outcome.record.turnover
        skipped_reason = outcome.record.skipped_reason

    new_state = CrossSectionalForwardState(
        equity=equity,
        long_weights=long_weights,
        short_weights=short_weights,
        net_weights=net_weights,
        rows_since_formation=rows_since_formation,
        pending_turnover_cost=pending_turnover_cost,
        gross_notional_held=gross_notional_held,
        n_formations=n_formations,
        n_realized_days=n_realized_days,
        last_formation_date=last_formation_date,
    )
    day_result = CrossSectionalForwardDayResult(
        date=today,
        realized=realized,
        reformed=reform,
        gross_return=gross_return,
        turnover_cost=turnover_cost,
        financing_cost=financing_cost,
        net_return=net_return,
        equity=equity,
        n_long=len(long_weights),
        n_short=len(short_weights),
        n_eligible=n_eligible,
        turnover=turnover,
        skipped_reason=skipped_reason,
    )
    return new_state, day_result


def rows_to_process(
    index: pd.DatetimeIndex,
    last_processed_date: date | None,
    max_rows: int = MAX_CATCHUP_ROWS_PER_TICK,
) -> list[int]:
    """Which panel rows this tick should step onto, in order.

    FIRST EVER TICK (last_processed_date is None) returns ONLY the panel's
    last row. This is the single most important line in the file for the
    integrity of the whole mechanism: a forward-validation track record must
    start TODAY and accumulate from data that did not exist at registration
    time. Backfilling the panel's history here would silently manufacture an
    instant "forward" record out of the very backward data the registration
    was decided on — precisely the look-ahead this exists to be immune to.

    Afterwards: every row strictly after last_processed_date, oldest first,
    capped at max_rows (see MAX_CATCHUP_ROWS_PER_TICK). Row 0 is never
    returned — realizing a day needs a previous row to price it against."""
    n = len(index)
    if n < 2:
        return []
    if last_processed_date is None:
        return [n - 1]
    positions = [p for p in range(1, n) if index[p].date() > last_processed_date]
    return positions[:max_rows]


def advance_forward_validation(
    data: CrossSectionalData,
    spec: CrossSectionalSpec,
    config: CrossSectionalConfig,
    is_member: MembershipFn,
    state: CrossSectionalForwardState,
    last_processed_date: date | None,
    max_rows: int = MAX_CATCHUP_ROWS_PER_TICK,
) -> tuple[CrossSectionalForwardState, list[CrossSectionalForwardDayResult]]:
    """Step onto every unprocessed panel row (see rows_to_process), in
    order. Returns the resulting state and one result per processed day —
    an empty list when there is no new row, which is the common case on
    most ticks and must be a pure no-op."""
    results: list[CrossSectionalForwardDayResult] = []
    for position in rows_to_process(data.close.index, last_processed_date, max_rows):
        state, day_result = step_one_cross_sectional_day(data, spec, config, is_member, state, position)
        results.append(day_result)
    return state, results


# --- persistence -------------------------------------------------------------


def serialize_cross_sectional_forward_state(state: CrossSectionalForwardState) -> dict:
    return {
        "equity": state.equity,
        "long_weights": state.long_weights,
        "short_weights": state.short_weights,
        "net_weights": state.net_weights,
        "rows_since_formation": state.rows_since_formation,
        "pending_turnover_cost": state.pending_turnover_cost,
        "gross_notional_held": state.gross_notional_held,
        "n_formations": state.n_formations,
        "n_realized_days": state.n_realized_days,
        "last_formation_date": state.last_formation_date,
    }


def deserialize_cross_sectional_forward_state(data: dict) -> CrossSectionalForwardState:
    return CrossSectionalForwardState(
        equity=data["equity"],
        long_weights=dict(data["long_weights"]),
        short_weights=dict(data["short_weights"]),
        net_weights=dict(data["net_weights"]),
        rows_since_formation=data["rows_since_formation"],
        pending_turnover_cost=data["pending_turnover_cost"],
        gross_notional_held=data["gross_notional_held"],
        n_formations=data["n_formations"],
        n_realized_days=data["n_realized_days"],
        last_formation_date=data["last_formation_date"],
    )


def initial_state_json() -> str:
    return json.dumps(serialize_cross_sectional_forward_state(CrossSectionalForwardState()))


def day_result_to_dict(day_result: CrossSectionalForwardDayResult) -> dict:
    return {
        "date": day_result.date.strftime("%Y-%m-%d"),
        "realized": day_result.realized,
        "reformed": day_result.reformed,
        "gross_return": day_result.gross_return,
        "turnover_cost": day_result.turnover_cost,
        "financing_cost": day_result.financing_cost,
        "net_return": day_result.net_return,
        "equity": day_result.equity,
        "n_long": day_result.n_long,
        "n_short": day_result.n_short,
    }


def formation_to_dict(day_result: CrossSectionalForwardDayResult) -> dict:
    """The formation audit trail, kept separately from the daily returns
    for the same reason cross_sectional.FormationRecord is kept per
    formation rather than aggregated: a surprising forward result must be
    auditable down to exactly which names were held from which date."""
    return {
        "date": day_result.date.strftime("%Y-%m-%d"),
        "n_eligible": day_result.n_eligible,
        "n_long": day_result.n_long,
        "n_short": day_result.n_short,
        "turnover": day_result.turnover,
        "skipped_reason": day_result.skipped_reason,
    }


__all__ = [
    "MAX_CATCHUP_ROWS_PER_TICK",
    "CrossSectionalForwardDayResult",
    "CrossSectionalForwardState",
    "ForwardTickNotSupportedError",
    "advance_forward_validation",
    "day_result_to_dict",
    "deserialize_cross_sectional_forward_state",
    "formation_to_dict",
    "initial_state_json",
    "rows_to_process",
    "serialize_cross_sectional_forward_state",
    "step_one_cross_sectional_day",
    "validate_spec_is_forward_tickable",
]
