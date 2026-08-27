"""Hedge-ratio persistence and per-strategy live leg sizing.

The load-bearing correctness fix of Phase 5: before it, the hedge ratio a
pairs trade needs to size its two legs was computed fresh every walk-forward
tick and discarded every tick, never persisted anywhere.
"""

import json

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab import momentum, ou_pairs
from app.services.research_lab.engine import (
    OpenTrade,
    StrategyFit,
    WalkForwardConfig,
    WalkForwardState,
    deserialize_walk_forward_state,
    serialize_walk_forward_state,
    step_one_day,
)
from app.services.research_lab.strategy_registry import get_adapter


# --- serialization round-trip -------------------------------------------------


def test_serialize_round_trip_preserves_last_fit_params():
    state = WalkForwardState(
        position=1,
        equity=1.23,
        valid_count=7,
        fit_quality_counts={"weak": 1, "moderate": 2, "strong": 3},
        open_trade=OpenTrade(
            entry_date=pd.Timestamp("2026-01-05"),
            direction="long_spread",
            trade_equity=1.05,
            days_held=4,
        ),
        last_fit_params={"hedge_ratio": 0.83, "mu": -0.02},
    )

    restored = deserialize_walk_forward_state(
        json.loads(json.dumps(serialize_walk_forward_state(state)))
    )

    assert restored.last_fit_params == {"hedge_ratio": 0.83, "mu": -0.02}
    assert restored.position == 1
    assert restored.equity == pytest.approx(1.23)
    assert restored.open_trade is not None
    assert restored.open_trade.days_held == 4


def test_deserialize_tolerates_state_persisted_before_last_fit_params_existed():
    """Every carry_state_json row already in production predates this field.
    Read with .get(), not direct key access, so an old row round-trips and
    self-heals on its next tick instead of raising KeyError forever."""
    old_format = {
        "position": -1,
        "equity": 0.98,
        "valid_count": 3,
        "fit_quality_counts": {"weak": 1, "moderate": 1, "strong": 1},
        "open_trade": None,
    }

    restored = deserialize_walk_forward_state(old_format)

    assert restored.last_fit_params == {}
    assert restored.position == -1


def _pairs_window(n: int = 60, hedge: float = 0.7) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    log_a = np.cumsum(rng.normal(0.0005, 0.01, n)) + 4.0
    noise = rng.normal(0.0, 0.01, n)
    log_b = hedge * log_a + noise + 1.0
    return pd.DataFrame(
        {
            "log_a": log_a,
            "log_b": log_b,
            "ret_a": pd.Series(np.exp(log_a)).pct_change().fillna(0.0).to_numpy(),
            "ret_b": pd.Series(np.exp(log_b)).pct_change().fillna(0.0).to_numpy(),
        },
        index=pd.bdate_range("2026-01-01", periods=n),
    )


def test_step_one_day_populates_last_fit_params_every_step():
    frame = _pairs_window()
    window = frame.iloc[:-1]
    day_row = frame.iloc[-1]
    config = WalkForwardConfig(fit_window_days=len(window), entry_z=2.0, exit_z=0.0, cost_bps=10.0)

    new_state, _day, _trade = step_one_day(
        window, day_row, ou_pairs.fit_ou_pairs_window, ou_pairs.realize_pairs_return,
        WalkForwardState(), config,
    )

    assert "hedge_ratio" in new_state.last_fit_params


def test_step_one_day_populates_last_fit_params_even_on_an_invalid_fit():
    """fit_ou_pairs_window still returns a hedge_ratio on three of its four
    invalid-return paths — so an invalid step must still carry it forward, or
    a strategy that goes flat on a bad fit would have no ratio available the
    moment it re-enters."""
    frame = _pairs_window()
    window = frame.iloc[:-1]
    day_row = frame.iloc[-1]
    config = WalkForwardConfig(fit_window_days=len(window), entry_z=2.0, exit_z=0.0, cost_bps=10.0)

    def always_invalid(_window: pd.DataFrame) -> StrategyFit:
        return StrategyFit(
            is_valid=False, z_score=None, fit_quality=None, params={"hedge_ratio": 0.42}
        )

    new_state, _day, _trade = step_one_day(
        window, day_row, always_invalid, ou_pairs.realize_pairs_return,
        WalkForwardState(position=1), config,
    )

    assert new_state.position == 0  # forced flat by the invalid fit
    assert new_state.last_fit_params == {"hedge_ratio": 0.42}


# --- pairs leg sizing ---------------------------------------------------------


@pytest.mark.parametrize("position", [1, -1])
@pytest.mark.parametrize("hedge_ratio", [0.7, 1.4, -0.6])
def test_pairs_legs_match_realize_pairs_return_normalization(position, hedge_ratio):
    """The leg weights must reproduce realize_pairs_return's own arithmetic
    exactly: applying them to a day's returns has to give the same number the
    return function does, for any hedge ratio and either direction."""
    state = WalkForwardState(position=position, last_fit_params={"hedge_ratio": hedge_ratio})
    legs = ou_pairs.compute_pairs_target_legs(state, "AAA", "BBB")

    by_ticker = {leg.ticker: leg.signed_weight for leg in legs}
    row = pd.Series({"ret_a": 0.011, "ret_b": -0.004})
    fit = StrategyFit(
        is_valid=True, z_score=0.0, fit_quality="strong", params={"hedge_ratio": hedge_ratio}
    )

    from_legs = by_ticker["AAA"] * row["ret_a"] + by_ticker["BBB"] * row["ret_b"]
    from_engine = position * ou_pairs.realize_pairs_return(row, fit)

    assert from_legs == pytest.approx(from_engine)


@pytest.mark.parametrize("hedge_ratio", [0.7, 1.4, -0.6, 0.0])
def test_pairs_legs_always_deploy_exactly_the_allocated_capital(hedge_ratio):
    """sum(abs(signed_weight)) == 1.0 always. A naive non-normalized version
    would over-deploy by (1+|h|)x and silently break market-neutrality."""
    state = WalkForwardState(position=1, last_fit_params={"hedge_ratio": hedge_ratio})
    legs = ou_pairs.compute_pairs_target_legs(state, "AAA", "BBB")
    assert sum(abs(leg.signed_weight) for leg in legs) == pytest.approx(1.0)


def test_pairs_legs_are_opposite_signed():
    state = WalkForwardState(position=1, last_fit_params={"hedge_ratio": 0.8})
    legs = {leg.ticker: leg.signed_weight for leg in ou_pairs.compute_pairs_target_legs(state, "AAA", "BBB")}
    assert legs["BBB"] > 0 > legs["AAA"]


def test_pairs_legs_empty_when_flat():
    state = WalkForwardState(position=0, last_fit_params={"hedge_ratio": 0.8})
    assert ou_pairs.compute_pairs_target_legs(state, "AAA", "BBB") == []


def test_pairs_legs_empty_when_hedge_ratio_unknown():
    """Fail closed: a state restored from a pre-Phase-5 carry_state_json, or one
    whose last fit hit the zero-variance path, holds nothing rather than
    guessing a ratio."""
    state = WalkForwardState(position=1, last_fit_params={})
    assert ou_pairs.compute_pairs_target_legs(state, "AAA", "BBB") == []


# --- momentum leg sizing ------------------------------------------------------


@pytest.mark.parametrize("position", [1, -1])
def test_momentum_legs_are_full_notional_single_asset(position):
    state = WalkForwardState(position=position)
    legs = momentum.compute_momentum_target_legs(state, "AAA", "AAA")
    assert len(legs) == 1
    assert legs[0].ticker == "AAA"
    assert legs[0].signed_weight == pytest.approx(float(position))


def test_momentum_legs_ignore_ticker_b():
    state = WalkForwardState(position=1)
    legs = momentum.compute_momentum_target_legs(state, "AAA", "ZZZ")
    assert [leg.ticker for leg in legs] == ["AAA"]


def test_momentum_legs_empty_when_flat():
    assert momentum.compute_momentum_target_legs(WalkForwardState(position=0), "AAA", "AAA") == []


# --- registry wiring ----------------------------------------------------------


def test_both_strategies_expose_compute_target_legs_through_the_adapter():
    assert (
        get_adapter(ou_pairs.STRATEGY_NAME).compute_target_legs
        is ou_pairs.compute_pairs_target_legs
    )
    assert (
        get_adapter(momentum.STRATEGY_NAME).compute_target_legs
        is momentum.compute_momentum_target_legs
    )
