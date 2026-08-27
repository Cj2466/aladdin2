"""Sizing, the two hard dollar caps, order planning and P&L attribution."""

import pytest

from app.services.execution.targets import (
    StrategyTarget,
    aggregate_targets,
    apply_caps,
    attribute_exposure,
    attribute_pnl,
    compute_allocated_capital,
    plan_orders,
)


def _target(registration_id: int, legs: dict[str, float], *, capital: float = 1000.0) -> StrategyTarget:
    return StrategyTarget(
        registration_id=registration_id,
        allocation_id=registration_id * 10,
        strategy_name="ou_pairs_v1",
        ticker_a="AAA",
        ticker_b="BBB",
        cost_bps=10.0,
        allocated_capital=capital,
        legs=legs,
    )


def _plan(**overrides):
    kwargs = {
        "net_targets": {},
        "current_values": {},
        "current_qtys": {},
        "open_order_tickers": set(),
        "managed_tickers": set(),
        "reference_prices": {},
        "min_order_notional": 5.0,
    }
    kwargs.update(overrides)
    if not kwargs["managed_tickers"]:
        kwargs["managed_tickers"] = set(kwargs["net_targets"]) | set(kwargs["current_values"])
    return plan_orders(**kwargs)


# --- capital ------------------------------------------------------------------


def test_allocated_capital_applies_the_capital_fraction():
    assert compute_allocated_capital(weight=0.4, equity=100_000.0, capital_fraction=0.5) == pytest.approx(20_000.0)


def test_allocated_capital_never_goes_negative():
    assert compute_allocated_capital(weight=-0.4, equity=100_000.0, capital_fraction=0.5) == 0.0


# --- aggregation --------------------------------------------------------------


def test_targets_are_netted_per_ticker_across_strategies():
    """Two strategies naming the same ticker must produce ONE target, or the
    tick would submit contradictory buy and sell orders for that symbol."""
    net = aggregate_targets([_target(1, {"AAA": 600.0}), _target(2, {"AAA": -250.0, "CCC": 100.0})])
    assert net == {"AAA": pytest.approx(350.0), "CCC": pytest.approx(100.0)}


# --- caps ---------------------------------------------------------------------


def test_per_ticker_cap_clamps_and_warns():
    capped, warnings = apply_caps(
        {"AAA": 2500.0, "BBB": -400.0}, max_position_notional=1000.0, max_total_notional=99_999.0
    )
    assert capped["AAA"] == pytest.approx(1000.0)
    assert capped["BBB"] == pytest.approx(-400.0)
    assert any("per-ticker cap" in w for w in warnings)


def test_total_gross_cap_scales_every_ticker_proportionally():
    """The test that catches "partial leg fill breaks market-neutrality": the
    RATIO between a pairs trade's two legs must survive the scaling exactly."""
    net = {"AAA": -600.0, "BBB": 900.0, "CCC": 500.0}
    capped, warnings = apply_caps(net, max_position_notional=1000.0, max_total_notional=1000.0)

    gross = sum(abs(v) for v in capped.values())
    assert gross == pytest.approx(1000.0)
    assert capped["BBB"] / capped["AAA"] == pytest.approx(900.0 / -600.0)
    assert all(capped[t] * net[t] > 0 for t in net)  # no sign flipped
    assert any("scaled every ticker" in w for w in warnings)


def test_caps_are_a_no_op_when_nothing_binds():
    net = {"AAA": 100.0, "BBB": -50.0}
    capped, warnings = apply_caps(net, max_position_notional=1000.0, max_total_notional=5000.0)
    assert capped == net
    assert warnings == []


# --- order planning -----------------------------------------------------------


def test_target_matching_current_submits_nothing():
    plan = _plan(net_targets={"AAA": 500.0}, current_values={"AAA": 502.0})
    assert plan.intents == []


def test_delta_below_the_minimum_is_ignored():
    plan = _plan(net_targets={"AAA": 504.0}, current_values={"AAA": 500.0}, min_order_notional=5.0)
    assert plan.intents == []


def test_opening_a_long_uses_a_notional_order():
    plan = _plan(net_targets={"AAA": 500.0}, current_values={})
    assert len(plan.intents) == 1
    intent = plan.intents[0]
    assert (intent.ticker, intent.side, intent.kind) == ("AAA", "buy", "notional")
    assert intent.notional == pytest.approx(500.0)


def test_reducing_a_long_uses_a_notional_sell():
    plan = _plan(net_targets={"AAA": 200.0}, current_values={"AAA": 500.0}, current_qtys={"AAA": 5.0})
    intent = plan.intents[0]
    assert (intent.side, intent.kind) == ("sell", "notional")
    assert intent.notional == pytest.approx(300.0)


def test_closing_a_long_fully_uses_an_exact_share_count():
    """A notional sell sized from a stale market value can be rejected for
    selling more than is held, and leaves dust when it isn't."""
    plan = _plan(net_targets={"AAA": 0.0}, current_values={"AAA": 500.0}, current_qtys={"AAA": 5.0})
    intent = plan.intents[0]
    assert (intent.side, intent.kind, intent.qty) == ("sell", "qty", 5.0)


def test_opening_a_short_uses_whole_shares_not_notional():
    """Alpaca marks every fractional sell as closing a long, so a notional
    order can never open a short."""
    plan = _plan(net_targets={"AAA": -500.0}, current_values={}, reference_prices={"AAA": 100.0})
    intent = plan.intents[0]
    assert (intent.side, intent.kind, intent.qty) == ("sell", "qty", 5.0)


def test_short_order_is_skipped_without_a_reference_price():
    plan = _plan(net_targets={"AAA": -500.0}, current_values={}, reference_prices={})
    assert plan.intents == []
    assert [(s.ticker, s.reason) for s in plan.skipped] == [("AAA", "no_reference_price")]


def test_short_order_is_skipped_when_it_rounds_below_one_share():
    plan = _plan(net_targets={"AAA": -50.0}, current_values={}, reference_prices={"AAA": 900.0})
    assert plan.intents == []
    assert [s.reason for s in plan.skipped] == ["below_one_share"]


def test_covering_a_short_uses_whole_shares():
    plan = _plan(
        net_targets={"AAA": -200.0},
        current_values={"AAA": -500.0},
        current_qtys={"AAA": -5.0},
        reference_prices={"AAA": 100.0},
    )
    intent = plan.intents[0]
    assert (intent.side, intent.kind, intent.qty) == ("buy", "qty", 3.0)


def test_a_long_never_flips_straight_into_a_short_in_one_order():
    """This tick flattens; the next tick — re-derived from the broker's real
    positions — opens the other side."""
    plan = _plan(
        net_targets={"AAA": -500.0},
        current_values={"AAA": 500.0},
        current_qtys={"AAA": 5.0},
        reference_prices={"AAA": 100.0},
    )
    intent = plan.intents[0]
    assert (intent.side, intent.kind, intent.qty) == ("sell", "qty", 5.0)  # flatten only


def test_ticker_with_an_open_order_is_skipped_not_stacked():
    plan = _plan(
        net_targets={"AAA": 500.0}, current_values={}, open_order_tickers={"AAA"}
    )
    assert plan.intents == []
    assert [s.reason for s in plan.skipped] == ["open_order_pending"]


def test_positions_this_system_never_traded_are_left_alone():
    """Without the managed-tickers bound, a position a human opened by hand
    would read as "target 0, currently long" and be liquidated next tick."""
    plan = _plan(
        net_targets={"AAA": 500.0},
        current_values={"AAA": 0.0, "ZZZ": 9_000.0},
        current_qtys={"ZZZ": 30.0},
        managed_tickers={"AAA"},
    )
    assert [i.ticker for i in plan.intents] == ["AAA"]


def test_one_order_per_ticker_per_tick():
    plan = _plan(net_targets={"AAA": 500.0, "BBB": 300.0}, current_values={})
    assert sorted(i.ticker for i in plan.intents) == ["AAA", "BBB"]
    assert len(plan.intents) == 2


# --- P&L attribution ----------------------------------------------------------


def test_sole_owner_of_a_ticker_receives_all_of_its_pnl():
    attributed = attribute_pnl([_target(1, {"AAA": 500.0})], {"AAA": -30.0})
    assert attributed[1] == pytest.approx(-30.0)


def test_shared_ticker_pnl_is_split_by_target_share():
    targets_ = [_target(1, {"AAA": 600.0}), _target(2, {"AAA": 200.0})]
    attributed = attribute_pnl(targets_, {"AAA": 80.0})
    assert attributed[1] == pytest.approx(60.0)
    assert attributed[2] == pytest.approx(20.0)
    assert attributed[1] + attributed[2] == pytest.approx(80.0)


def test_a_short_leg_receives_the_correctly_signed_share():
    targets_ = [_target(1, {"AAA": -400.0, "BBB": 600.0})]
    attributed = attribute_pnl(targets_, {"AAA": 10.0, "BBB": -4.0})
    assert attributed[1] == pytest.approx(6.0)


def test_fully_offsetting_targets_do_not_divide_by_zero():
    targets_ = [_target(1, {"AAA": 500.0}), _target(2, {"AAA": -500.0})]
    attributed = attribute_pnl(targets_, {"AAA": 10.0})
    assert attributed[1] == pytest.approx(5.0)
    assert attributed[2] == pytest.approx(5.0)


def test_ticker_with_no_target_contributes_no_attribution():
    attributed = attribute_pnl([_target(1, {"AAA": 500.0})], {"ZZZ": 100.0})
    assert attributed[1] == pytest.approx(0.0)


# --- exposure attribution (what a tripped strategy's target is frozen at) ------


def test_exposure_attribution_gives_a_sole_owner_the_whole_position():
    exposure = attribute_exposure([_target(1, {"AAA": 500.0})], {"AAA": 480.0})
    assert exposure[1] == {"AAA": pytest.approx(480.0)}


def test_exposure_attribution_splits_a_shared_ticker_by_target_share():
    targets_ = [_target(1, {"AAA": 600.0}), _target(2, {"AAA": 200.0})]
    exposure = attribute_exposure(targets_, {"AAA": 800.0})
    assert exposure[1]["AAA"] == pytest.approx(600.0)
    assert exposure[2]["AAA"] == pytest.approx(200.0)


def test_a_strategy_holding_nothing_yet_freezes_at_zero_exposure():
    """This is what stops a strategy OPENING a brand-new position on the very
    tick its own circuit breaker pulled it."""
    exposure = attribute_exposure([_target(1, {"AAA": 500.0})], {})
    assert exposure[1] == {}
