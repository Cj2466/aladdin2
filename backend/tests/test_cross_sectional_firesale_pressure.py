"""Tests for the Coval-Stafford fire-sale PRESSURE family.

The load-bearing one is `test_paper_worked_example`: it pins Eq.(4) against the
arithmetic the authors themselves print on page 11 of their own working paper.
If that test ever fails, the measure is no longer the paper's measure.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.cross_sectional_firesale_pressure import (
    FIRESALE_CUTOFF,
    INFLOW_CUTOFF,
    MIN_OWNERS,
    LegDiagnostics,
    OwnerObservation,
    _weights,
    calendar_time_returns,
    eligible_sets,
    month_end_snapshots,
    pressure,
    spec_id_for,
    verdict_for,
)


def _owner(series_id: str, before: float, after: float, flow: float) -> OwnerObservation:
    return OwnerObservation(series_id=series_id, shares_before=before, shares_after=after, flow=flow)


# --- Eq.(4) -------------------------------------------------------------------


def test_paper_worked_example():
    """Coval & Stafford (2005 working paper) page 11, verbatim:

    "suppose 47 funds own stock ABC at the start of January 2003. During the
     next three months, 13 owners experience outflows of at least 5%, of which
     11 reduce their holdings of ABC. One fund experiences an inflow of 5% and
     increases its holdings of ABC. In this example, the PRESSURE variable for
     ABC during this quarter would be calculated as (1-11)/47 = -21.3%."

    Note the fund count: 47 owners, of which 13 are distressed (11 selling, 2
    distressed but NOT selling), 1 is an inflow buyer, and the remaining 33 are
    unremarkable holders. The distressed-but-not-selling pair is the detail
    that separates a correct implementation from one that divides by the number
    of distressed funds instead of the number of owners.
    """
    owners = []
    # 11 distressed funds that reduce.
    for i in range(11):
        owners.append(_owner(f"sell{i}", 100.0, 50.0, -0.09))
    # 2 distressed funds that do NOT reduce (they hold).
    for i in range(2):
        owners.append(_owner(f"hold_distressed{i}", 100.0, 100.0, -0.09))
    # 1 fund with a >5% inflow that increases.
    owners.append(_owner("buy0", 100.0, 150.0, 0.06))
    # 33 ordinary owners with small flows, holding steady.
    for i in range(33):
        owners.append(_owner(f"plain{i}", 100.0, 100.0, 0.001))

    assert len(owners) == 47

    value = pressure(owners, flow_threshold=0.05)
    assert value == pytest.approx((1 - 11) / 47)
    assert value == pytest.approx(-0.2127659574, abs=1e-9)
    # The paper rounds this to -21.3%.
    assert round(value * 100, 1) == -21.3
    # And it clears the paper's own fire-sale cutoff.
    assert value <= FIRESALE_CUTOFF


def test_min_owners_refuses_rather_than_returning_a_small_denominator_number():
    """Footnote 6: "We require at least 10 mutual funds owners before we
    calculate the PRESSURE variable." A refusal, not a noisy reading."""
    owners = [_owner(f"f{i}", 100.0, 50.0, -0.09) for i in range(MIN_OWNERS - 1)]
    assert pressure(owners, flow_threshold=0.05) is None

    owners.append(_owner("one_more", 100.0, 50.0, -0.09))
    assert len(owners) == MIN_OWNERS
    assert pressure(owners, flow_threshold=0.05) == pytest.approx(-1.0)


def test_non_owners_at_start_are_excluded_from_numerator_and_denominator():
    """Own_{j,i,t-1} gates both. A fund that buys INTO a stock it did not own
    is not one of "the owners of the stock" whose commonality Eq.(4) measures."""
    held = [_owner(f"h{i}", 100.0, 100.0, 0.0) for i in range(10)]
    newcomers = [_owner(f"n{i}", 0.0, 500.0, 0.20) for i in range(10)]
    assert pressure(held + newcomers, flow_threshold=0.05) == pytest.approx(0.0)


def test_full_exit_counts_as_a_sell():
    """The paper speaks throughout of positions "reduced or eliminated"."""
    owners = [_owner(f"f{i}", 100.0, 0.0, -0.09) for i in range(10)]
    assert pressure(owners, flow_threshold=0.05) == pytest.approx(-1.0)


def test_flow_threshold_gates_who_counts():
    """A fund selling hard but with a SMALL flow is not a forced seller."""
    owners = [_owner(f"f{i}", 100.0, 10.0, -0.02) for i in range(20)]
    assert pressure(owners, flow_threshold=0.05) == pytest.approx(0.0)
    assert pressure(owners, flow_threshold=0.01) == pytest.approx(-1.0)


def test_ten_percent_arm_is_a_subset_of_the_five_percent_arm():
    """Table 5.b raises the gate to |flow| > 10%; every fund that qualifies
    there must also qualify at 5%, so pressure can only move toward zero."""
    rng = np.random.default_rng(11)
    owners = [
        _owner(f"f{i}", 100.0, float(rng.uniform(0, 200)), float(rng.uniform(-0.3, 0.3)))
        for i in range(60)
    ]
    at5 = pressure(owners, flow_threshold=0.05)
    at10 = pressure(owners, flow_threshold=0.10)
    assert at5 is not None and at10 is not None
    assert abs(at10) <= abs(at5) + 1e-12 or np.sign(at10) != np.sign(at5)


def test_unconstrained_control_ignores_flow_entirely():
    """Table 4 Panel B: "a 'pressure' variable, but one altered by removing the
    condition on flow from the calculation"."""
    owners = [_owner(f"f{i}", 100.0, 50.0, -0.001) for i in range(20)]
    assert pressure(owners, flow_threshold=0.05, constrained=True) == pytest.approx(0.0)
    assert pressure(owners, flow_threshold=0.05, constrained=False) == pytest.approx(-1.0)


def test_pressure_is_bounded_by_plus_and_minus_one():
    rng = np.random.default_rng(3)
    for _ in range(200):
        n = int(rng.integers(MIN_OWNERS, 80))
        owners = [
            _owner(f"f{i}", 100.0, float(rng.uniform(0, 300)), float(rng.uniform(-0.5, 0.5)))
            for i in range(n)
        ]
        value = pressure(owners, flow_threshold=0.05)
        assert value is not None
        assert -1.0 - 1e-12 <= value <= 1.0 + 1e-12


def test_inflow_cutoff_requires_widespread_constrained_buying():
    """PRESSURE >= +25% needs a quarter of all owners to be inflow-driven
    buyers, which is a much higher bar than the -15% sell side."""
    owners = [_owner(f"b{i}", 100.0, 200.0, 0.20) for i in range(6)]
    owners += [_owner(f"h{i}", 100.0, 100.0, 0.0) for i in range(14)]
    value = pressure(owners, flow_threshold=0.05)
    assert value == pytest.approx(6 / 20)
    assert value >= INFLOW_CUTOFF


# --- formation window ---------------------------------------------------------


def _panel(values: dict[str, list[float]], dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame(values, index=pd.DatetimeIndex([pd.Timestamp(d) for d in dates]))


def test_eligible_sets_honours_past_year_but_not_past_quarter():
    """Section III.A / footnote 10. A flag 30 days old is too recent to trade;
    a flag 400 days old is stale."""
    dates = ["2023-01-31", "2023-06-30", "2023-12-29", "2024-01-31"]
    panel = _panel(
        {
            "STALE": [-0.5, 0.0, 0.0, 0.0],  # 2023-01-31: >365d before 2024-02-29
            "GOOD": [0.0, -0.5, 0.0, 0.0],  # 2023-06-30: inside the window
            "TOOFRESH": [0.0, 0.0, 0.0, -0.5],  # 2024-01-31: inside the skip
        },
        dates,
    )
    snapshot = pd.Timestamp("2024-02-29")
    eligible = eligible_sets(panel, snapshot, cutoff=FIRESALE_CUTOFF, direction="below")
    assert eligible == {"GOOD"}


def test_eligible_sets_direction_above_for_the_inflow_leg():
    panel = _panel({"HOT": [0.4], "COLD": [-0.4]}, ["2023-06-30"])
    snapshot = pd.Timestamp("2023-12-29")
    assert eligible_sets(panel, snapshot, cutoff=INFLOW_CUTOFF, direction="above") == {"HOT"}
    assert eligible_sets(panel, snapshot, cutoff=FIRESALE_CUTOFF, direction="below") == {"COLD"}


def test_eligible_sets_on_empty_panel_is_empty_not_an_error():
    assert eligible_sets(pd.DataFrame(), pd.Timestamp("2024-01-31"), cutoff=-0.15, direction="below") == set()


# --- weighting ----------------------------------------------------------------


def test_equal_weights_sum_to_one():
    w = _weights(["A", "B", "C"], "equal", None)
    assert sum(w.values()) == pytest.approx(1.0)
    assert all(v == pytest.approx(1 / 3) for v in w.values())


def test_value_weights_track_caps_and_sum_to_one():
    caps = pd.Series({"A": 300.0, "B": 100.0})
    w = _weights(["A", "B"], "value", caps)
    assert sum(w.values()) == pytest.approx(1.0)
    assert w["A"] == pytest.approx(0.75)


def test_value_weighting_degrades_to_equal_only_when_no_cap_is_usable():
    caps = pd.Series({"A": np.nan, "B": np.nan})
    w = _weights(["A", "B"], "value", caps)
    assert w["A"] == pytest.approx(0.5)
    assert w["B"] == pytest.approx(0.5)


# --- portfolio ----------------------------------------------------------------


def _price_frame(tickers: list[str], months: int, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2021-01-01", periods=months * 22)
    data = {t: 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(index)))) for t in tickers}
    return pd.DataFrame(data, index=index)


def test_unformable_leg_earns_zero_rather_than_being_dropped():
    """The paper's footnote 12 fire-station problem: dropping idle months
    overstates the strategy. The month must survive in the series."""
    tickers = [f"T{i}" for i in range(20)]
    close = _price_frame(tickers, 18)
    empty_panel = pd.DataFrame(index=pd.DatetimeIndex([]))

    long_r, short_r, ls_r, diag = calendar_time_returns(
        empty_panel,
        close,
        members_on=lambda d: tickers,
        market_cap=None,
        half_spread=None,
        formation_start=close.index[0].date(),
        borrow_bps_per_year=0.0,
        weighting="equal",
    )
    assert len(long_r) > 0
    assert (long_r == 0.0).all()
    assert (ls_r == 0.0).all()
    assert diag.n_long_formable == 0
    assert diag.formable_fraction("long") == 0.0


def test_long_leg_is_market_hedged_so_a_flat_universe_pays_nothing():
    """Every stock moving identically must leave the market-hedged long leg at
    exactly zero — otherwise the leg is measuring beta, not the effect."""
    tickers = [f"T{i}" for i in range(20)]
    index = pd.bdate_range("2021-01-01", periods=18 * 22)
    path = 100 * np.exp(np.cumsum(np.full(len(index), 0.001)))
    close = pd.DataFrame({t: path for t in tickers}, index=index)

    snapshots = month_end_snapshots(index)
    panel = pd.DataFrame(
        {t: [-0.5] * len(snapshots) for t in tickers}, index=pd.DatetimeIndex(snapshots)
    )

    long_r, _short_r, _ls_r, diag = calendar_time_returns(
        panel,
        close,
        members_on=lambda d: tickers,
        market_cap=None,
        half_spread=None,
        formation_start=index[0].date(),
        borrow_bps_per_year=0.0,
        weighting="equal",
    )
    assert diag.n_long_formable > 0
    assert np.allclose(long_r.to_numpy(), 0.0, atol=1e-12)


def test_costs_and_borrow_can_only_reduce_the_long_short_return():
    tickers = [f"T{i}" for i in range(30)]
    close = _price_frame(tickers, 24, seed=5)
    snapshots = month_end_snapshots(close.index)
    panel = pd.DataFrame(
        {t: [-0.5 if i < 15 else 0.5 for _ in snapshots] for i, t in enumerate(tickers)},
        index=pd.DatetimeIndex(snapshots),
    )
    common = dict(
        members_on=lambda d: tickers,
        market_cap=None,
        formation_start=close.index[0].date(),
        weighting="equal",
    )
    _l, _s, gross, _d = calendar_time_returns(
        panel, close, half_spread=None, borrow_bps_per_year=0.0, **common
    )
    half = pd.DataFrame(0.001, index=close.index, columns=close.columns)
    _l2, _s2, net, _d2 = calendar_time_returns(
        panel, close, half_spread=half, borrow_bps_per_year=430.0, **common
    )
    assert (net <= gross + 1e-12).all()
    assert net.sum() < gross.sum()


# --- verdict rule -------------------------------------------------------------


def test_verdict_definite_negative_when_the_most_lenient_rung_fails():
    v, why = verdict_for({24: 0.30, 1031: 0.01}, [24, 1031])
    assert v == "DEFINITE_NEGATIVE"
    assert "most lenient" in why


def test_verdict_unresolved_when_only_the_lenient_rung_passes():
    v, _ = verdict_for({24: 0.97, 1031: 0.40}, [24, 1031])
    assert v == "UNRESOLVED"


def test_verdict_pass_only_when_the_most_conservative_rung_clears():
    v, _ = verdict_for({24: 0.99, 1031: 0.96}, [24, 1031])
    assert v == "PASS"


def test_unmeasurable_dsr_is_not_a_pass():
    v, _ = verdict_for({24: None, 1031: None}, [24, 1031])
    assert v == "DEFINITE_NEGATIVE"
    v2, _ = verdict_for({24: 0.99, 1031: None}, [24, 1031])
    assert v2 == "UNRESOLVED"


def test_spec_id_is_stable_and_readable():
    assert spec_id_for("sp600", 0.10, "long_short", "equal", "baseline") == (
        "sp600/cs_flow0.1_long_short_equal_baseline"
    )


def test_leg_diagnostics_fraction_uses_the_binding_leg_for_long_short():
    d = LegDiagnostics(n_months=10, n_long_formable=8, n_short_formable=3)
    assert d.formable_fraction("long_short") == pytest.approx(0.3)
