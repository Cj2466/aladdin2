"""Tests for the period-end marking-the-close family.

Three jobs, following this project's convention for a family test file:
  1. FAMILY SHAPE — the grid is exactly the 18 definitions the pre-registration
     declared, and the DSR denominator arithmetic matches.
  2. CONSTRUCTION FIDELITY — the event calendar, the two ranking windows, the
     three arms and the point-in-time guarantee are what Carhart, Kaniel, Musto
     & Reed (1999) actually specify, checked against planted data with a known
     answer rather than against the module's own output.
  3. REPORT CONSISTENCY — the committed run report and its JSON agree with each
     other, with the pre-registration, and with what the module recomputes from
     its own primitives.
"""

from __future__ import annotations

import json
from datetime import date
from itertools import pairwise
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    run_cross_sectional_backtest,
)
from app.services.research_lab.cross_sectional_quarter_end_marking import (
    MIN_EVENT_MONTH_TRADING_DAYS,
    PERIOD_MONTHS,
    PLACEBO_MONTHS,
    QEM_ARMS,
    QEM_COST_MULTIPLIERS,
    QEM_FAMILY,
    QEM_H126_SESSIONS,
    QEM_HOLDING_DAYS,
    QEM_LEG_WEIGHTING,
    QEM_N_TRIALS,
    QEM_PERFS,
    QEM_PERIODS,
    QEM_RANK_FRACTION,
    QEM_SPEC_CEILING,
    QUARTER_END_MONTHS,
    SMALL_CAP_COST_BPS,
    UNIVERSE_MULTIPLIER,
    VALIDATED_EDGE_BAR,
    YEAR_END_MONTHS,
    arm_exposed_dates,
    arm_pnl_window,
    build_all_qem_panels,
    build_qem_family,
    build_qem_panel,
    default_qem_config,
    event_returns,
    event_schedule,
    memoized_membership,
    perf_series,
    period_dummies,
    period_open_boundary,
    policy_d_denominators,
    quintile_profile,
    run_qem_universe,
    signal_qem,
    sleeve_scale,
    spec_id,
)
from app.services.research_lab.cross_sectional_small_mid_cap import (
    SMALL_CAP_COST_BPS as SMALL_MID_CAP_MODULE_COST_BPS,
)

_RUNS = Path(__file__).resolve().parents[1] / "data" / "research_runs"
REPORT_PATH = _RUNS / "quarter_end_marking_2026-09-06.txt"
JSON_PATH = _RUNS / "quarter_end_marking_2026-09-06.json"
PREREG_PATH = _RUNS / "quarter_end_marking_PREREGISTRATION.txt"


# ---------------------------------------------------------------------------
# synthetic price frames
# ---------------------------------------------------------------------------


def _calendar(start: str = "2015-01-01", end: str = "2021-12-31") -> pd.DatetimeIndex:
    """A business-day index. Good enough for event arithmetic: the module reads
    whatever sessions the index actually contains and never constructs a
    calendar date of its own."""
    return pd.bdate_range(start, end)


def _walk(index: pd.DatetimeIndex, tickers: list[str], seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0, 0.01, (len(index), len(tickers)))
    return pd.DataFrame(
        100.0 * np.exp(np.cumsum(steps, axis=0)), index=index, columns=tickers, dtype=float
    )


def _always_member(_ticker: str, _on: date) -> bool:
    return True


# ===========================================================================
# 1. FAMILY SHAPE
# ===========================================================================


def test_family_is_exactly_18_definitions_at_the_declared_ceiling():
    panels = build_all_qem_panels(_walk(_calendar(), ["A", "B", "C"]))
    specs = build_qem_family(panels)
    assert len(specs) == QEM_SPEC_CEILING == 18


def test_the_grid_is_the_declared_cross_product_and_nothing_else():
    panels = build_all_qem_panels(_walk(_calendar(), ["A", "B", "C"]))
    built = {s.pattern_id for s in build_qem_family(panels)}
    expected = {
        spec_id(period, arm, perf)
        for period in QEM_PERIODS
        for arm in QEM_ARMS
        for perf in QEM_PERFS
    }
    assert built == expected
    assert len(expected) == 3 * 3 * 2 == 18


def test_denominator_is_two_universes_times_the_grid():
    assert UNIVERSE_MULTIPLIER == 2
    assert QEM_N_TRIALS == UNIVERSE_MULTIPLIER * QEM_SPEC_CEILING == 36


def test_policy_d_ladder_is_ascending_and_starts_at_n_local():
    ladder = policy_d_denominators()
    assert ladder[0] == QEM_N_TRIALS, "the lowest tier must be the denominator the run deflates at"
    assert all(a < b for a, b in pairwise(ladder)), "denominators must be strictly ascending"
    assert len(ladder) == 3


def test_every_spec_carries_the_source_citation_including_the_paywall_disclosure():
    panels = build_all_qem_panels(_walk(_calendar(), ["A", "B", "C"]))
    for spec in build_qem_family(panels):
        assert spec.family == QEM_FAMILY
        assert "Carhart, Kaniel, Musto & Reed" in spec.citation
        assert "011-99" in spec.citation
        # The published-version disclosure is load-bearing, not decoration: a
        # reader must be able to tell from the spec alone that the JoF article
        # was not read.
        assert "PUBLISHED VERSION NOT OBTAINED" in spec.citation
        assert "Leaning for the Tape" in spec.citation


def test_construction_choices_are_the_papers_and_are_fixed_not_searched():
    panels = build_all_qem_panels(_walk(_calendar(), ["A", "B", "C"]))
    specs = build_qem_family(panels)
    # quintiles ([CKMR99] p.15), equal weighting (p.15), winner-minus-loser
    # (Table IV caption), a one-session hold, and NO cohort stagger.
    assert QEM_RANK_FRACTION == 0.2
    assert QEM_LEG_WEIGHTING == "equal"
    assert QEM_HOLDING_DAYS == 1
    assert all(s.rank_fraction == 0.2 for s in specs)
    assert all(s.leg_weighting == "equal" for s in specs)
    assert all(s.portfolio == "long_short" for s in specs)
    assert all(s.holding_days == 1 for s in specs)
    assert all(s.cohort_formation_days is None for s in specs)
    assert all(s.requires_fundamental_signal for s in specs)
    assert all(s.lookback_days == 1 for s in specs)


def test_a_missing_panel_is_rejected_loudly():
    panels = build_all_qem_panels(_walk(_calendar(), ["A", "B", "C"]))
    del panels["year_end_oval_perf_ptd"]
    with pytest.raises(ValueError, match="no panel supplied"):
        build_qem_family(panels)


def test_small_cap_cost_matches_the_module_that_pre_declared_it():
    assert SMALL_CAP_COST_BPS == SMALL_MID_CAP_MODULE_COST_BPS == 15.0


def test_the_two_universes_get_different_turnover_models_and_the_same_borrow():
    large = default_qem_config("sp500", date(2015, 1, 7))
    small = default_qem_config("sp600", date(2020, 1, 1))
    assert large.cost_model == "edge_spread"
    assert small.cost_model == "flat_bps"
    assert small.cost_bps == SMALL_CAP_COST_BPS
    assert large.financing_bps_per_year == small.financing_bps_per_year == 17.0


def test_cost_ladder_is_the_three_declared_multipliers_with_baseline_in_it():
    assert QEM_COST_MULTIPLIERS == (0.0, 1.0, 2.0)
    assert 1.0 in QEM_COST_MULTIPLIERS, "the baseline must be on the ladder to be comparable"


# ===========================================================================
# 2. CONSTRUCTION FIDELITY
# ===========================================================================


def test_month_sets_are_ckmr_table_i_caption_and_partition_the_year():
    """[CKMR99] Table I caption p.23: YEND = last trading day of December;
    QEND = last trading day of March, June or September; MEND = last day of
    January, February, April, May, July, August, October or November."""
    assert YEAR_END_MONTHS == (12,)
    assert QUARTER_END_MONTHS == (3, 6, 9)
    assert PLACEBO_MONTHS == (1, 2, 4, 5, 7, 8, 10, 11)
    assert 12 not in QUARTER_END_MONTHS, "QEND is 'other than a year-end' (Section III p.8)"
    assert not set(PLACEBO_MONTHS) & (set(QUARTER_END_MONTHS) | set(YEAR_END_MONTHS))
    assert set(YEAR_END_MONTHS) | set(QUARTER_END_MONTHS) | set(PLACEBO_MONTHS) == set(range(1, 13))
    assert sum(len(m) for m in PERIOD_MONTHS.values()) == 12


def test_event_dates_are_real_index_rows_around_the_last_session_of_the_month():
    index = _calendar("2016-01-01", "2018-12-31")
    events, _ = event_schedule(index, "year_end")
    assert [e.year for e in events] == [2016, 2017, 2018]
    for event in events:
        month_rows = index[(index.year == event.year) & (index.month == 12)]
        assert event.d0 == month_rows[-1]
        position = int(index.searchsorted(event.d0))
        assert event.d_minus_1 == index[position - 1]
        if event.d1 is not None:
            assert event.d1 == index[position + 1]
        assert event.d_minus_1 < event.d0


def test_the_last_event_in_the_window_has_no_next_day_rather_than_a_fabricated_one():
    index = _calendar("2016-01-01", "2018-12-31")
    events, _ = event_schedule(index, "year_end")
    assert events[-1].d0 == index[-1] or events[-1].d1 is not None
    if events[-1].d0 == index[-1]:
        assert events[-1].d1 is None


def test_a_truncated_month_is_skipped_and_counted_not_clamped():
    # A window ending on 10 December: December has far fewer than
    # MIN_EVENT_MONTH_TRADING_DAYS sessions, so its "last trading day" is an
    # artifact of the fetch, not a year-end.
    index = _calendar("2016-01-01", "2018-12-10")
    events, skipped = event_schedule(index, "year_end")
    assert [e.year for e in events] == [2016, 2017]
    assert "2018-12" in skipped
    assert len(index[(index.year == 2018) & (index.month == 12)]) < MIN_EVENT_MONTH_TRADING_DAYS


def test_perf_h126_is_exactly_the_126_session_return_ending_the_day_before_the_event():
    index = _calendar()
    close = _walk(index, ["A", "B"])
    events, _ = event_schedule(index, "year_end")
    event = events[2]
    got = perf_series(close, event, "perf_h126")
    end_position = int(index.searchsorted(event.d_minus_1))
    start = index[end_position - QEM_H126_SESSIONS]
    expected = close.loc[event.d_minus_1] / close.loc[start] - 1.0
    assert QEM_H126_SESSIONS == 126
    pd.testing.assert_series_equal(got, expected, check_names=False)


def test_perf_ptd_bases_on_the_last_close_strictly_before_the_period_opened():
    index = _calendar()
    close = _walk(index, ["A", "B"])
    for period, event_index in (("year_end", 2), ("quarter_end", 6), ("month_placebo", 9)):
        events, _ = event_schedule(index, period)
        event = events[event_index]
        boundary = period_open_boundary(event)
        prior = index[index < boundary][-1]
        expected = close.loc[event.d_minus_1] / close.loc[prior] - 1.0
        pd.testing.assert_series_equal(
            perf_series(close, event, "perf_ptd"), expected, check_names=False
        )
        assert prior < boundary <= event.d0


def test_period_open_boundary_is_the_year_quarter_or_month_start():
    index = _calendar()
    for period, expected_month in (("year_end", 1), ("month_placebo", None)):
        events, _ = event_schedule(index, period)
        for event in events:
            boundary = period_open_boundary(event)
            assert boundary.year == event.year
            assert boundary.day == 1
            if expected_month is not None:
                assert boundary.month == expected_month
            else:
                assert boundary.month == event.month
    events, _ = event_schedule(index, "quarter_end")
    assert {(e.month, period_open_boundary(e).month) for e in events} == {(3, 1), (6, 4), (9, 7)}


def test_panels_are_nan_everywhere_except_their_own_arm_formation_rows():
    index = _calendar()
    close = _walk(index, ["A", "B", "C"])
    day0 = build_qem_panel(close, period="year_end", arm="day0", perf="perf_h126")
    day1 = build_qem_panel(close, period="year_end", arm="day1", perf="perf_h126")
    oval = build_qem_panel(close, period="year_end", arm="oval", perf="perf_h126")

    day0_rows = day0.frame.dropna(how="all").index
    day1_rows = day1.frame.dropna(how="all").index
    oval_rows = oval.frame.dropna(how="all").index

    assert list(day0_rows) == [e.d_minus_1 for e in day0.events]
    assert list(day1_rows) == [e.d0 for e in day1.events]
    assert set(oval_rows) == set(day0_rows) | set(day1_rows)


def test_the_day1_arm_is_the_negated_day0_signal_and_oval_carries_both():
    index = _calendar()
    close = _walk(index, ["A", "B", "C"])
    day0 = build_qem_panel(close, period="year_end", arm="day0", perf="perf_ptd")
    day1 = build_qem_panel(close, period="year_end", arm="day1", perf="perf_ptd")
    oval = build_qem_panel(close, period="year_end", arm="oval", perf="perf_ptd")
    for event in oval.events:
        raw = perf_series(close, event, "perf_ptd")
        np.testing.assert_allclose(day0.frame.loc[event.d_minus_1].to_numpy(), raw.to_numpy())
        np.testing.assert_allclose(day1.frame.loc[event.d0].to_numpy(), -raw.to_numpy())
        np.testing.assert_allclose(oval.frame.loc[event.d_minus_1].to_numpy(), raw.to_numpy())
        np.testing.assert_allclose(oval.frame.loc[event.d0].to_numpy(), -raw.to_numpy())


def test_the_best_performer_ranks_highest_on_day0_and_lowest_on_day1():
    """The harness ranks HIGH-is-long. The day0 arm must go LONG the winner and
    the day1 arm must go SHORT it ([CKMR99] Table IV's b1 > 0, b2 < 0
    hypothesis, p.13)."""
    index = _calendar()
    close = pd.DataFrame(100.0, index=index, columns=["WIN", "FLAT", "LOSE"], dtype=float)
    close["WIN"] = np.linspace(100.0, 300.0, len(index))
    close["LOSE"] = np.linspace(100.0, 40.0, len(index))
    day0 = build_qem_panel(close, period="year_end", arm="day0", perf="perf_h126")
    day1 = build_qem_panel(close, period="year_end", arm="day1", perf="perf_h126")
    event = day0.events[2]
    row0 = day0.frame.loc[event.d_minus_1]
    row1 = day1.frame.loc[event.d0]
    assert row0.idxmax() == "WIN" and row0.idxmin() == "LOSE"
    assert row1.idxmax() == "LOSE" and row1.idxmin() == "WIN"


def test_the_day1_signal_cannot_see_day_zeros_own_return():
    """Pre-registration 4.4 and module section 2.4: the reversal arm must rank
    on a window ending d(-1). A planted, enormous d(0) return must therefore
    leave the d(0)-row signal byte-for-byte unchanged — otherwise the arm would
    be sorting on 'which stocks printed high at the close', which is bid-ask
    bounce, not marking."""
    index = _calendar()
    close = _walk(index, ["A", "B", "C"])
    before = build_qem_panel(close, period="year_end", arm="day1", perf="perf_h126")
    event = before.events[2]

    tampered = close.copy()
    tampered.loc[event.d0, "A"] *= 5.0  # a +400% day-0 print for A
    after = build_qem_panel(tampered, period="year_end", arm="day1", perf="perf_h126")

    np.testing.assert_allclose(
        before.frame.loc[event.d0].to_numpy(), after.frame.loc[event.d0].to_numpy()
    )


def test_future_prices_cannot_change_an_already_computed_event_value():
    index = _calendar()
    close = _walk(index, ["A", "B", "C"])
    before = build_qem_panel(close, period="year_end", arm="oval", perf="perf_ptd")
    event = before.events[1]

    tampered = close.copy()
    later = index[index > event.d0]
    tampered.loc[later, :] *= 7.0
    after = build_qem_panel(tampered, period="year_end", arm="oval", perf="perf_ptd")

    np.testing.assert_allclose(
        before.frame.loc[event.d_minus_1].to_numpy(), after.frame.loc[event.d_minus_1].to_numpy()
    )
    np.testing.assert_allclose(
        before.frame.loc[event.d0].to_numpy(), after.frame.loc[event.d0].to_numpy()
    )


def test_signal_fn_reads_only_the_formation_row_of_its_bound_panel():
    index = _calendar()
    close = _walk(index, ["A", "B", "C"])
    panel = build_qem_panel(close, period="year_end", arm="day0", perf="perf_h126")
    event = panel.events[1]

    view = CrossSectionalData(
        close=close.loc[:event.d_minus_1],
        fundamental_signal=panel.frame.loc[:event.d_minus_1],
    )
    got = signal_qem(view, panel=panel.frame)
    pd.testing.assert_series_equal(got, panel.frame.loc[event.d_minus_1], check_names=False)

    # A non-formation date yields an all-NaN signal, i.e. "no valid signal
    # today", which is what makes the harness skip and go flat.
    other = index[index.get_loc(event.d_minus_1) - 3]
    view2 = CrossSectionalData(
        close=close.loc[:other], fundamental_signal=panel.frame.loc[:other]
    )
    assert signal_qem(view2, panel=panel.frame).isna().all()


def test_signal_fn_refuses_without_the_fundamental_signal_carrier():
    index = _calendar()
    close = _walk(index, ["A", "B"])
    panel = build_qem_panel(close, period="year_end", arm="day0", perf="perf_h126")
    with pytest.raises(ValueError, match="requires_fundamental_signal"):
        signal_qem(CrossSectionalData(close=close), panel=panel.frame)


def test_unknown_period_arm_and_perf_are_rejected_loudly():
    index = _calendar()
    close = _walk(index, ["A", "B"])
    events, _ = event_schedule(index, "year_end")
    with pytest.raises(ValueError, match="unknown perf window"):
        perf_series(close, events[1], "perf_nonsense")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unknown arm"):
        arm_exposed_dates(events[1], "day7")  # type: ignore[arg-type]
    with pytest.raises(KeyError):
        event_schedule(index, "not_a_period")  # type: ignore[arg-type]


def test_event_schedule_on_an_empty_index_returns_nothing_rather_than_raising():
    empty = pd.DatetimeIndex([])
    for period in QEM_PERIODS:
        events, skipped = event_schedule(empty, period)
        assert events == [] and skipped == []


def test_exposed_dates_are_the_sessions_each_arm_is_actually_long_or_short_on():
    index = _calendar()
    events, _ = event_schedule(index, "year_end")
    event = events[1]
    assert arm_exposed_dates(event, "day0") == [event.d0]
    assert arm_exposed_dates(event, "day1") == [event.d1]
    assert arm_exposed_dates(event, "oval") == [event.d0, event.d1]


def test_the_pnl_window_is_one_session_longer_because_the_exit_charge_settles_late():
    """The harness charges a formation's turnover on its FIRST REALIZATION DAY,
    so the liquidation charge lands the session after the book goes flat.
    Compounding only the exposed sessions would report an entry-cost-only
    number."""
    index = _calendar()
    events, _ = event_schedule(index, "year_end")
    event = events[1]
    assert arm_pnl_window(event, "day0") == [event.d0, event.d1]
    assert arm_pnl_window(event, "day1") == [event.d1, event.d2]
    assert arm_pnl_window(event, "oval") == [event.d0, event.d1, event.d2]
    for arm in QEM_ARMS:
        assert len(arm_pnl_window(event, arm)) == len(arm_exposed_dates(event, arm)) + 1


def test_an_event_missing_its_settlement_session_yields_no_window_rather_than_a_truncated_one():
    index = _calendar("2016-01-01", "2018-12-31")
    events, _ = event_schedule(index, "year_end")
    last = events[-1]
    if last.d1 is None or last.d2 is None:
        for arm in QEM_ARMS:
            assert arm_pnl_window(last, arm) == []


def test_the_per_event_returns_account_for_the_whole_daily_series():
    """The strongest consistency check this family has: the book is exposed or
    being charged ONLY inside the per-event windows and is flat and free on
    every other session, so compounding the per-event returns must reproduce
    compounding the entire daily series. If the exit charge were being dropped
    from the windows, this would fail."""
    index = _calendar()
    tickers = [f"T{i:02d}" for i in range(40)]
    close = _walk(index, tickers, seed=21)
    panels = build_all_qem_panels(close)
    specs = {s.pattern_id: s for s in build_qem_family(panels)}
    config = CrossSectionalConfig(
        cost_bps=12.0,
        cost_model="flat_bps",
        formation_start=index[QEM_H126_SESSIONS + 5].date(),
        financing_bps_per_year=17.0,
        min_names_per_leg=4,
    )
    data = CrossSectionalData(
        close=close, fundamental_signal=panels["year_end_oval_perf_h126"].frame
    )
    for arm in QEM_ARMS:
        pid = spec_id("quarter_end", arm, "perf_ptd")
        replay = run_cross_sectional_backtest(data, specs[pid], config, _always_member)
        assert replay.status == "ok"
        stats = event_returns(replay, panels[f"quarter_end_{arm}_perf_ptd"])
        assert stats.n_events >= 3

        whole_series = float(np.prod(1.0 + replay.daily_returns.to_numpy()) - 1.0)
        from_events = float(np.prod(1.0 + np.asarray(stats.event_returns)) - 1.0)
        # The only sessions the event windows can miss are the tail ones an
        # unfinished last event leaves behind, so allow the series to differ
        # only by whatever the trailing partial event contributed.
        assert from_events == pytest.approx(whole_series, abs=5e-4), (
            f"{pid}: per-event returns compound to {from_events:+.8f} but the whole daily series "
            f"compounds to {whole_series:+.8f}"
        )


def test_the_per_event_return_is_net_of_the_exit_charge_not_just_the_entry():
    """Direct, single-number check of the same property: raising the cost rate
    must reduce a per-event return by BOTH sides of the round trip."""
    index = _calendar()
    tickers = [f"T{i:02d}" for i in range(40)]
    close = _walk(index, tickers, seed=23)
    panels = build_all_qem_panels(close)
    specs = {s.pattern_id: s for s in build_qem_family(panels)}
    data = CrossSectionalData(
        close=close, fundamental_signal=panels["year_end_oval_perf_h126"].frame
    )
    pid = spec_id("year_end", "day0", "perf_h126")
    means = {}
    for bps in (0.0, 10.0):
        config = CrossSectionalConfig(
            cost_bps=bps,
            cost_model="flat_bps",
            formation_start=index[QEM_H126_SESSIONS + 5].date(),
            financing_bps_per_year=0.0,
            min_names_per_leg=4,
        )
        replay = run_cross_sectional_backtest(data, specs[pid], config, _always_member)
        means[bps] = event_returns(replay, panels["year_end_day0_perf_h126"]).mean
    # Entry (2.0 of one-way gross notional) plus exit (2.0) at 10bp is 40bp per
    # event; entry alone would be 20bp. The observed drop must be the former.
    drop = means[0.0] - means[10.0]
    assert drop == pytest.approx(4.0 * 10.0 / 10_000.0, rel=0.02), (
        f"per-event cost drop was {drop:.6f}; entry-only would be ~0.0020, entry+exit ~0.0040"
    )


# --- the harness fit -------------------------------------------------------


def test_sleeve_scale_is_one_and_matches_the_harness_own_arithmetic():
    """Module section 6: holding_days=1 with cohort_formation_days=None gives
    cadence == holding_days, so n_sleeves = max(1, 1 // 1) = 1 and NOTHING the
    harness reports needs de-scaling. Pinned against the harness's own formula
    rather than asserted as a constant."""
    panels = build_all_qem_panels(_walk(_calendar(), ["A", "B", "C"]))
    for spec in build_qem_family(panels):
        cadence = (
            spec.cohort_formation_days
            if spec.cohort_formation_days is not None
            else spec.holding_days
        )
        assert max(1, spec.holding_days // cadence) == sleeve_scale(spec.holding_days) == 1


def test_oval_event_return_is_exactly_the_compounded_day0_and_day1_pair():
    """The whole reason `oval` exists: its realized per-event return must be
    the winner-minus-loser spread's d(0) return compounded with its d(1)
    return, i.e. [CKMR99] p.18's OVAL. Checked with costs OFF, because the oval
    arm really does pay a sign-flip charge the two single-day arms do not — see
    pre-registration section 7, and the next test."""
    index = _calendar()
    tickers = [f"T{i:02d}" for i in range(40)]
    close = _walk(index, tickers, seed=3)
    panels = build_all_qem_panels(close)
    specs = {s.pattern_id: s for s in build_qem_family(panels)}
    config = CrossSectionalConfig(
        cost_bps=0.0,
        cost_model="flat_bps",
        formation_start=index[QEM_H126_SESSIONS + 5].date(),
        financing_bps_per_year=0.0,
        min_names_per_leg=4,
    )
    data = CrossSectionalData(
        close=close, fundamental_signal=panels["year_end_oval_perf_h126"].frame
    )

    stats = {}
    for arm in QEM_ARMS:
        pid = spec_id("year_end", arm, "perf_h126")
        replay = run_cross_sectional_backtest(data, specs[pid], config, _always_member)
        assert replay.status == "ok"
        stats[arm] = event_returns(replay, panels[f"year_end_{arm}_perf_h126"])

    n = min(stats[a].n_events for a in QEM_ARMS)
    assert n >= 3
    d0 = np.asarray(stats["day0"].event_returns[:n])
    d1 = np.asarray(stats["day1"].event_returns[:n])
    oval = np.asarray(stats["oval"].event_returns[:n])
    np.testing.assert_allclose((1.0 + d0) * (1.0 + d1) - 1.0, oval, atol=1e-12)


def test_the_oval_arm_pays_the_sign_flip_and_therefore_more_turnover():
    """Pre-registration section 7's cost arithmetic, checked rather than
    asserted: day0/day1 each pay entry+exit (4.0 of one-way gross notional per
    event) while oval pays entry+flip+exit (8.0)."""
    index = _calendar()
    tickers = [f"T{i:02d}" for i in range(40)]
    close = _walk(index, tickers, seed=5)
    panels = build_all_qem_panels(close)
    specs = {s.pattern_id: s for s in build_qem_family(panels)}
    config = CrossSectionalConfig(
        cost_bps=10.0,
        cost_model="flat_bps",
        formation_start=index[QEM_H126_SESSIONS + 5].date(),
        financing_bps_per_year=0.0,
        min_names_per_leg=4,
    )
    data = CrossSectionalData(
        close=close, fundamental_signal=panels["year_end_oval_perf_h126"].frame
    )
    turnover = {}
    for arm in QEM_ARMS:
        pid = spec_id("year_end", arm, "perf_h126")
        replay = run_cross_sectional_backtest(data, specs[pid], config, _always_member)
        turnover[arm] = sum(f.turnover for f in replay.formations)
    assert turnover["oval"] > turnover["day0"] > 0.0
    assert turnover["oval"] > turnover["day1"] > 0.0


def test_the_book_is_flat_on_almost_every_session():
    """A one-day-hold calendar family holds nothing on the ~245 sessions a year
    that are not adjacent to a period end. Pinned because the DSR is computed on
    that zero-inflated series and a reader must know it."""
    index = _calendar()
    tickers = [f"T{i:02d}" for i in range(40)]
    close = _walk(index, tickers, seed=9)
    panels = build_all_qem_panels(close)
    specs = {s.pattern_id: s for s in build_qem_family(panels)}
    config = CrossSectionalConfig(
        cost_bps=0.0,
        cost_model="flat_bps",
        formation_start=index[QEM_H126_SESSIONS + 5].date(),
        financing_bps_per_year=0.0,
        min_names_per_leg=4,
    )
    data = CrossSectionalData(
        close=close, fundamental_signal=panels["year_end_oval_perf_h126"].frame
    )
    pid = spec_id("year_end", "day0", "perf_h126")
    replay = run_cross_sectional_backtest(data, specs[pid], config, _always_member)
    non_zero = int((replay.daily_returns != 0.0).sum())
    assert 0 < non_zero <= 2 * len(panels["year_end_day0_perf_h126"].events)
    assert non_zero < 0.05 * len(replay.daily_returns)


def test_period_dummies_match_the_ckmr_table_i_caption():
    index = _calendar("2016-01-01", "2019-12-31")
    dummies = period_dummies(index)
    assert list(dummies.columns) == ["YEND", "YBEG", "QEND", "QBEG", "MEND", "MBEG"]
    for period, end_col, beg_col in (
        ("year_end", "YEND", "YBEG"),
        ("quarter_end", "QEND", "QBEG"),
        ("month_placebo", "MEND", "MBEG"),
    ):
        events, _ = event_schedule(index, period)
        assert dummies[end_col].sum() == len(events)
        assert dummies[beg_col].sum() == len([e for e in events if e.d1 is not None])
        for event in events:
            assert dummies.loc[event.d0, end_col] == 1.0
            if event.d1 is not None:
                assert dummies.loc[event.d1, beg_col] == 1.0
    # No session is both a year-end and a quarter-end: that is exactly the
    # distinction the working paper's own abstract gets wrong (module section
    # 2.1) and the body gets right.
    assert (dummies["YEND"] * dummies["QEND"]).sum() == 0.0
    assert (dummies["QEND"] * dummies["MEND"]).sum() == 0.0
    assert (dummies["YEND"] * dummies["MEND"]).sum() == 0.0


def test_quintile_profile_is_five_buckets_of_the_declared_shape():
    index = _calendar()
    tickers = [f"T{i:02d}" for i in range(50)]
    close = _walk(index, tickers, seed=13)
    panel = build_qem_panel(close, period="quarter_end", arm="oval", perf="perf_ptd")
    profile = quintile_profile(close, panel, _always_member)
    assert profile.n_events > 0
    assert len(profile.day0_by_quintile) == len(profile.day1_by_quintile) == 5
    assert profile.oval_by_quintile == pytest.approx(
        [a - b for a, b in zip(profile.day0_by_quintile, profile.day1_by_quintile, strict=True)]
    )
    assert "bucket 0 = LOSER quintile" in profile.note


def test_memoized_membership_returns_exactly_what_the_real_gate_returns():
    calls: list[tuple[str, date]] = []

    def base(ticker: str, on: date) -> bool:
        calls.append((ticker, on))
        return ticker == "A" and on.year == 2018

    gate = memoized_membership(base)
    probes = [("A", date(2018, 5, 1)), ("A", date(2019, 5, 1)), ("B", date(2018, 5, 1))]
    first = [gate(t, d) for t, d in probes]
    second = [gate(t, d) for t, d in probes]
    assert first == second == [base(t, d) for t, d in probes]
    assert len(set(calls)) == 3, "each distinct (ticker, date) is asked of the real gate once"


def test_screening_start_before_membership_coverage_is_refused():
    with pytest.raises(ValueError, match="predates point-in-time membership coverage"):
        run_qem_universe("sp500", date(2010, 1, 4), date(2012, 1, 4))
    with pytest.raises(ValueError, match="predates point-in-time membership coverage"):
        run_qem_universe("sp600", date(2015, 1, 7), date(2016, 1, 7))


# ===========================================================================
# 3. THE PRE-REGISTRATION AND THE COMMITTED REPORT
# ===========================================================================


def test_preregistration_exists_and_declares_the_grid_this_module_builds():
    text = PREREG_PATH.read_text()
    assert "n_local 36" in text or "n_local = 36" in text
    assert "QEM_SPEC_CEILING = 18" in text
    for period in QEM_PERIODS:
        assert period in text
    for arm in QEM_ARMS:
        assert arm in text
    for perf in QEM_PERFS:
        assert perf in text
    # The two disclosures that make this build honest rather than merely
    # thorough.
    assert "doi:10.1111/1540-6261.00438" in text
    assert "FULL TEXT NOT OBTAINED" in text
    assert f"{VALIDATED_EDGE_BAR:.2f}" in text


@pytest.fixture(scope="module")
def run_payload() -> dict:
    if not JSON_PATH.exists():
        pytest.skip(f"{JSON_PATH.name} not committed yet")
    return json.loads(JSON_PATH.read_text())


def test_report_and_json_agree_on_the_verdict_and_the_denominator(run_payload):
    report = REPORT_PATH.read_text()
    assert run_payload["n_trials"] == QEM_N_TRIALS
    assert run_payload["verdict"].upper() in report
    assert f"n_local={QEM_N_TRIALS}" in report
    assert str(run_payload["denominators"]) in report


def test_json_carries_all_36_evaluations_across_both_universes(run_payload):
    universes = {u["universe"] for u in run_payload["universes"]}
    assert universes == {"sp500", "sp600"}
    total = sum(len(u["evaluations"]) for u in run_payload["universes"])
    assert total == QEM_N_TRIALS == 36
    for universe in run_payload["universes"]:
        built = {e["pattern_id"] for e in universe["evaluations"]}
        assert built == {
            spec_id(p, a, w) for p in QEM_PERIODS for a in QEM_ARMS for w in QEM_PERFS
        }


def test_every_spec_has_a_preservation_score_and_a_dsr_at_every_denominator(run_payload):
    """CLAUDE.md: preservation_score is a standard secondary check with NO
    exceptions, and DSR is reported across multiple N, never as one point."""
    denominators = [str(n) for n in run_payload["denominators"]]
    for universe in run_payload["universes"]:
        for evaluation in universe["evaluations"]:
            assert "preservation_score" in evaluation["preservation"]
            assert set(evaluation["dsr_by_n"]) == set(denominators)


def test_dsr_is_monotonically_non_increasing_in_the_denominator(run_payload):
    denominators = sorted(run_payload["denominators"])
    for universe in run_payload["universes"]:
        for evaluation in universe["evaluations"]:
            values = [evaluation["dsr_by_n"][str(n)] for n in denominators]
            present = [v for v in values if v is not None]
            for a, b in pairwise(present):
                assert b <= a + 1e-9, (
                    f"{evaluation['pattern_id']}: DSR rose with N ({values}); DSR is strictly "
                    "decreasing in the number of trials"
                )


def test_verdict_in_the_report_is_what_policy_d_computes_from_the_reported_dsrs(run_payload):
    from app.services.research_lab.registration_scorecard import policy_d_verdict

    evaluations = [e for u in run_payload["universes"] for e in u["evaluations"]]
    best = max(
        evaluations,
        key=lambda e: (
            e["dsr_by_n"][str(QEM_N_TRIALS)]
            if e["dsr_by_n"][str(QEM_N_TRIALS)] is not None
            else -1.0
        ),
    )
    recomputed = policy_d_verdict(
        dsr_by_n={int(k): v for k, v in best["dsr_by_n"].items()},
        threshold=VALIDATED_EDGE_BAR,
        n_local=QEM_N_TRIALS,
    )
    assert recomputed == run_payload["verdict"]
    assert best["pattern_id"] in run_payload["best_spec"]


def test_event_counts_never_exceed_the_events_the_calendar_actually_has(run_payload):
    for universe in run_payload["universes"]:
        by_period = {k: len(v) for k, v in universe["events_by_period"].items()}
        for evaluation in universe["evaluations"]:
            assert evaluation["events"]["n_events"] <= by_period[evaluation["period"]], (
                f"{evaluation['pattern_id']} reports more events than the "
                f"{evaluation['period']} calendar contains"
            )
        # The placebo is the better-powered arm by construction, and that is
        # the whole reason it can override the verdict.
        assert by_period["month_placebo"] > by_period["year_end"]


def test_every_spec_reports_sleeve_scale_one_so_nothing_needed_de_scaling(run_payload):
    for universe in run_payload["universes"]:
        for evaluation in universe["evaluations"]:
            assert evaluation["sleeve_scale"] == 1


def test_each_universe_reports_the_cost_model_the_preregistration_declared(run_payload):
    by_universe = {u["universe"]: u for u in run_payload["universes"]}
    assert by_universe["sp500"]["cost_model"] == "edge_spread"
    assert by_universe["sp600"]["cost_model"] == "flat_bps"
    assert by_universe["sp600"]["cost_bps"] == SMALL_CAP_COST_BPS
    for universe in by_universe.values():
        assert universe["financing_bps_per_year"] == 17.0


def test_cost_ladder_is_present_and_a_higher_charge_never_raises_the_sharpe(run_payload):
    for universe in run_payload["universes"]:
        arms = {a["multiplier"]: a for a in universe["cost_arms"]}
        assert set(arms) == set(QEM_COST_MULTIPLIERS)
        for pid in arms[1.0]["sharpe_by_pattern"]:
            free = arms[0.0]["sharpe_by_pattern"][pid]
            base = arms[1.0]["sharpe_by_pattern"][pid]
            stressed = arms[2.0]["sharpe_by_pattern"][pid]
            assert free >= base - 1e-9, f"{pid}: charging costs raised the Sharpe"
            assert base >= stressed - 1e-9, f"{pid}: doubling costs raised the Sharpe"


def test_the_placebo_override_result_is_recorded_either_way(run_payload):
    assert isinstance(run_payload["placebo_override_triggered"], bool)
    assert run_payload["placebo_override_detail"]
    report = REPORT_PATH.read_text()
    assert "BINDING OVERRIDE (i)" in report
    assert f"TRIGGERED: {run_payload['placebo_override_triggered']}" in report


def test_the_fidelity_diagnostics_are_actually_in_the_committed_report(run_payload):
    report = REPORT_PATH.read_text()
    assert "FIDELITY CHECK F1" in report
    assert "F3_cross_sectional_lag_slope" in report
    for universe in run_payload["universes"]:
        assert len(universe["quintile_profiles"]) == len(QEM_PERIODS) * len(QEM_PERFS) == 6
        labels = {d["label"] for d in universe["dummy_regressions"]}
        assert "F3_cross_sectional_lag_slope" in labels
