"""Execution-quality measurement: realized slippage against assumed cost_bps."""

import pytest

from app.models.live_order import LiveOrder
from app.services.execution import slippage
from app.services.execution.execution_runner import apply_fill


# --- the arithmetic -----------------------------------------------------------


def test_buying_above_the_decision_price_is_positive_adverse_slippage():
    """Signed so positive is ALWAYS a cost, matching cost_bps' own sign."""
    bps = slippage.compute_slippage_bps(decision_price=100.0, filled_avg_price=100.10, side="buy")
    assert bps == pytest.approx(10.0)


def test_buying_below_the_decision_price_is_negative_slippage():
    bps = slippage.compute_slippage_bps(decision_price=100.0, filled_avg_price=99.95, side="buy")
    assert bps == pytest.approx(-5.0)


def test_selling_below_the_decision_price_is_positive_adverse_slippage():
    bps = slippage.compute_slippage_bps(decision_price=100.0, filled_avg_price=99.90, side="sell")
    assert bps == pytest.approx(10.0)


def test_selling_above_the_decision_price_is_negative_slippage():
    bps = slippage.compute_slippage_bps(decision_price=50.0, filled_avg_price=50.05, side="sell")
    assert bps == pytest.approx(-10.0)


def test_a_non_positive_decision_price_is_rejected_rather_than_producing_infinity():
    with pytest.raises(ValueError):
        slippage.compute_slippage_bps(decision_price=0.0, filled_avg_price=10.0, side="buy")


# --- recording a fill onto a LiveOrder ----------------------------------------


def test_apply_fill_records_price_qty_and_slippage():
    order = LiveOrder(
        user_id=1, ticker="AAPL", side="buy", status="new", client_order_id="c1",
        notional_requested=1000.0, decision_price=200.0, assumed_cost_bps=5.0,
    )
    apply_fill(
        order,
        {
            "status": "filled",
            "filled_qty": "5",
            "filled_avg_price": "200.30",
            "filled_at": "2026-08-26T14:31:02.123Z",
        },
    )
    assert order.status == "filled"
    assert order.filled_qty == pytest.approx(5.0)
    assert order.filled_avg_price == pytest.approx(200.30)
    assert order.realized_slippage_bps == pytest.approx(15.0)
    assert order.filled_at is not None and order.filled_at.tzinfo is None


def test_apply_fill_on_a_still_unfilled_order_records_status_only():
    order = LiveOrder(
        user_id=1, ticker="AAPL", side="buy", status="submitted", client_order_id="c2",
        decision_price=200.0,
    )
    apply_fill(order, {"status": "new", "filled_qty": "0", "filled_avg_price": None})
    assert order.status == "new"
    assert order.realized_slippage_bps is None
    assert order.filled_avg_price is None


def test_apply_fill_without_a_decision_price_still_records_the_fill():
    """Slippage is a monitoring metric — a missing reference price must never
    lose the fill record itself."""
    order = LiveOrder(
        user_id=1, ticker="AAPL", side="buy", status="new", client_order_id="c3",
        decision_price=None,
    )
    apply_fill(order, {"status": "filled", "filled_qty": "2", "filled_avg_price": "199.00"})
    assert order.filled_avg_price == pytest.approx(199.0)
    assert order.realized_slippage_bps is None


def test_apply_fill_tolerates_a_missing_filled_at():
    order = LiveOrder(
        user_id=1, ticker="AAPL", side="sell", status="new", client_order_id="c4",
        decision_price=100.0,
    )
    apply_fill(order, {"status": "filled", "filled_qty": "1", "filled_avg_price": "99.0"})
    assert order.filled_at is not None
    assert order.realized_slippage_bps == pytest.approx(100.0)


# --- aggregation --------------------------------------------------------------


def _fill(bps: float, notional: float, assumed: float | None = 10.0, label: str = "s"):
    return slippage.FillObservation(
        label=label, slippage_bps=bps, notional=notional, assumed_cost_bps=assumed
    )


def test_empty_aggregate_reports_nothing_rather_than_zero():
    """Zero slippage and no data must never look the same."""
    result = slippage.aggregate("all", [])
    assert result.n_fills == 0
    assert result.notional_weighted_mean_bps is None
    assert result.excess_vs_assumed_bps is None
    assert result.meaningful_sample is False


def test_notional_weighting_dominates_a_tiny_outlier_fill():
    """A $10 fill with 500bps of slippage must not swamp a $10,000 fill with
    8bps — the dollars are what erode the backtested edge."""
    result = slippage.aggregate("all", [_fill(8.0, 10_000.0), _fill(500.0, 10.0)])
    assert result.simple_mean_bps == pytest.approx(254.0)
    assert result.notional_weighted_mean_bps == pytest.approx(8.4914, rel=1e-3)


def test_excess_vs_assumed_is_the_headline_comparison():
    result = slippage.aggregate("pairs", [_fill(18.0, 1000.0, assumed=10.0)] * 5)
    assert result.assumed_cost_bps == pytest.approx(10.0)
    assert result.excess_vs_assumed_bps == pytest.approx(8.0)


def test_median_and_worst_are_reported():
    result = slippage.aggregate("all", [_fill(1.0, 100.0), _fill(5.0, 100.0), _fill(90.0, 100.0)])
    assert result.median_bps == pytest.approx(5.0)
    assert result.worst_bps == pytest.approx(90.0)


def test_small_samples_are_flagged_as_not_yet_meaningful():
    small = slippage.aggregate("all", [_fill(12.0, 100.0)] * 3)
    assert small.n_fills == 3
    assert small.meaningful_sample is False
    assert small.notional_weighted_mean_bps is not None  # still reported, just flagged

    big = slippage.aggregate(
        "all", [_fill(12.0, 100.0)] * slippage.MIN_FILLS_FOR_MEANINGFUL_SLIPPAGE
    )
    assert big.meaningful_sample is True


def test_mixed_assumptions_average_rather_than_pretending_to_one_value():
    """An aggregate can legitimately span pairs (10bps) and momentum (5bps)."""
    result = slippage.aggregate(
        "all", [_fill(10.0, 100.0, assumed=10.0), _fill(10.0, 100.0, assumed=5.0)]
    )
    assert result.assumed_cost_bps == pytest.approx(7.5)


def test_fills_with_no_recorded_assumption_leave_the_comparison_undefined():
    result = slippage.aggregate("all", [_fill(10.0, 100.0, assumed=None)])
    assert result.assumed_cost_bps is None
    assert result.excess_vs_assumed_bps is None


def test_zero_notional_fills_fall_back_to_a_simple_mean():
    result = slippage.aggregate("all", [_fill(10.0, 0.0), _fill(20.0, 0.0)])
    assert result.notional_weighted_mean_bps == pytest.approx(15.0)
