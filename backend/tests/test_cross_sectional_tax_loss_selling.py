"""Tests for the tax-loss-selling / turn-of-the-year family.

Three jobs, following this project's convention for a family test file:
  1. FAMILY SHAPE — the grid is exactly the 16 definitions the
     pre-registration declared, and the DSR denominator arithmetic matches.
  2. CONSTRUCTION FIDELITY — the anchor dates, the loss windows and the two
     signal forms are what Poterba & Weisbenner (2001) actually specify, and
     the point-in-time guarantee holds against planted future data.
  3. REPORT CONSISTENCY — the committed run report and its JSON agree with
     each other, with the pre-registration, and with what the module
     recomputes from its own primitives.
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
from app.services.research_lab.cross_sectional_small_mid_cap import (
    SMALL_CAP_COST_BPS as SMALL_MID_CAP_MODULE_COST_BPS,
)
from app.services.research_lab.cross_sectional_tax_loss_selling import (
    DECEMBER_WINDOWS,
    MIN_ANCHOR_MONTH_TRADING_DAYS,
    PLACEBO_WINDOW,
    SMALL_CAP_COST_BPS,
    TAX_LOSS_COHORT_FORMATION_DAYS,
    TAX_LOSS_FAMILY,
    TAX_LOSS_FORMATION_OFFSET,
    TAX_LOSS_FORMS,
    TAX_LOSS_HOLDING_DAYS,
    TAX_LOSS_N_TRIALS,
    TAX_LOSS_RANK_FRACTION,
    TAX_LOSS_SIGNAL_END_OFFSET,
    TAX_LOSS_SPEC_CEILING,
    UNIVERSE_MULTIPLIER,
    VALIDATED_EDGE_BAR,
    anchor_month_for,
    anchor_schedule,
    annual_event_returns,
    build_all_tax_loss_panels,
    build_tax_loss_family,
    build_tax_loss_panel,
    default_tax_loss_config,
    memoized_membership,
    policy_d_denominators,
    signal_tax_loss,
    sleeve_scale,
    spec_id,
    window_bounds,
)

_RUNS = Path(__file__).resolve().parents[1] / "data" / "research_runs"
REPORT_PATH = _RUNS / "tax_loss_selling_2026-09-06.txt"
JSON_PATH = _RUNS / "tax_loss_selling_2026-09-06.json"
PREREG_PATH = _RUNS / "tax_loss_selling_PREREGISTRATION.txt"


# ---------------------------------------------------------------------------
# synthetic price frames
# ---------------------------------------------------------------------------


def _calendar(start: str = "2016-01-04", end: str = "2021-12-31") -> pd.DatetimeIndex:
    """A business-day index. Good enough for anchor arithmetic: the module
    reads whatever sessions the index actually contains, and never constructs
    a calendar date of its own."""
    return pd.bdate_range(start, end)


def _flat_close(index: pd.DatetimeIndex, tickers: list[str], level: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame(level, index=index, columns=tickers, dtype=float)


def _planted_close(
    index: pd.DatetimeIndex, year_returns: dict[str, float], base: float = 100.0
) -> pd.DataFrame:
    """Each ticker's price walks LINEARLY to a planted full-calendar-year
    return within every year, so its accrued gain/loss at any December date is
    a known, hand-checkable number."""
    frame = pd.DataFrame(index=index, dtype=float)
    for ticker, annual in year_returns.items():
        values = []
        for year in sorted({int(y) for y in index.year}):
            days = index[index.year == year]
            step = np.linspace(0.0, annual, len(days) + 1)[1:]
            start_level = base * ((1.0 + annual) ** (year - int(index.year.min())))
            values.append(pd.Series(start_level * (1.0 + step), index=days))
        frame[ticker] = pd.concat(values)
    return frame


# ---------------------------------------------------------------------------
# 1. FAMILY SHAPE
# ---------------------------------------------------------------------------


def _panels_for(index: pd.DatetimeIndex, tickers: list[str]):
    close = _flat_close(index, tickers)
    return build_all_tax_loss_panels(close, close)


def test_family_is_exactly_16_definitions_at_the_declared_ceiling():
    specs = build_tax_loss_family(_panels_for(_calendar(), ["A", "B"]))
    assert len(specs) == 16 == TAX_LOSS_SPEC_CEILING


def test_the_grid_is_the_declared_cross_product_and_nothing_else():
    specs = build_tax_loss_family(_panels_for(_calendar(), ["A", "B"]))
    expected = {
        spec_id(window, form, holding)
        for window in (*DECEMBER_WINDOWS, PLACEBO_WINDOW)
        for form in TAX_LOSS_FORMS
        for holding in TAX_LOSS_HOLDING_DAYS
    }
    assert {s.pattern_id for s in specs} == expected
    assert len(expected) == TAX_LOSS_SPEC_CEILING


def test_denominator_is_two_universes_times_the_grid():
    assert UNIVERSE_MULTIPLIER == 2
    assert TAX_LOSS_N_TRIALS == UNIVERSE_MULTIPLIER * TAX_LOSS_SPEC_CEILING == 32


def test_policy_d_ladder_is_ascending_and_starts_at_n_local():
    from app.services.research_lab.dsr_policy_n import load_dsr_policy_ladder

    ladder = policy_d_denominators()
    assert ladder == sorted(ladder)
    assert ladder[0] >= TAX_LOSS_N_TRIALS
    # Was `len(ladder) == 3` until 2026-09-06; see dsr_policy_n.py.
    assert set(load_dsr_policy_ladder().pooled_rungs) <= set(ladder)


def test_every_spec_carries_the_poterba_weisbenner_citation():
    for spec in build_tax_loss_family(_panels_for(_calendar(), ["A", "B"])):
        assert spec.family == TAX_LOSS_FAMILY
        assert "Poterba" in spec.citation
        assert "Weisbenner" in spec.citation
        assert "Journal of Finance 56(1)" in spec.citation
        # The two abstract-only sources must be flagged as such in the very
        # string that travels with every persisted row.
        assert "ABSTRACT-LEVEL ONLY" in spec.citation


def test_lossonly_is_universe_hedged_and_signed_is_long_short():
    """Pre-registration 3.4: [PW01] estimates no winner effect, so the
    faithful construction has no short-the-winners leg."""
    for spec in build_tax_loss_family(_panels_for(_calendar(), ["A", "B"])):
        if "lossonly" in spec.pattern_id:
            assert spec.portfolio == "long_universe_hedged"
        else:
            assert spec.portfolio == "long_short"


def test_rank_fraction_and_weighting_are_fixed_not_searched():
    for spec in build_tax_loss_family(_panels_for(_calendar(), ["A", "B"])):
        assert spec.rank_fraction == TAX_LOSS_RANK_FRACTION == 0.1
        assert spec.leg_weighting == "magnitude"


def test_a_missing_panel_is_rejected_loudly():
    panels = _panels_for(_calendar(), ["A", "B"])
    del panels[f"{DECEMBER_WINDOWS[0]}_lossonly"]
    with pytest.raises(ValueError, match="no panel supplied"):
        build_tax_loss_family(panels)


def test_small_cap_cost_matches_the_module_that_pre_declared_it():
    """The S&P 600 flat cost is restated by value here rather than imported.
    This is the guard that stops the two drifting apart silently."""
    assert SMALL_CAP_COST_BPS == SMALL_MID_CAP_MODULE_COST_BPS == 15.0


def test_the_two_universes_get_different_turnover_models_and_the_same_borrow():
    large = default_tax_loss_config("sp500", date(2015, 1, 7))
    small = default_tax_loss_config("sp600", date(2020, 1, 1))
    assert large.cost_model == "edge_spread"
    assert small.cost_model == "flat_bps"
    assert small.cost_bps == SMALL_CAP_COST_BPS
    # 34 bps/yr on the short leg alone == 17.0 on the gross-notional basis.
    assert large.financing_bps_per_year == small.financing_bps_per_year == 17.0


# ---------------------------------------------------------------------------
# 2. CONSTRUCTION FIDELITY
# ---------------------------------------------------------------------------


def test_anchor_is_the_second_to_last_session_and_signal_ends_six_from_last():
    index = _calendar()
    for anchor in anchor_schedule(index, anchor_month=12):
        december = index[(index.year == anchor.year) & (index.month == 12)]
        assert anchor.last_session == december[-1]
        assert anchor.formation == december[-TAX_LOSS_FORMATION_OFFSET]
        assert anchor.signal_end == december[-TAX_LOSS_SIGNAL_END_OFFSET]
        # [PW01] excludes "the last five trading days of December" from LOSS:
        # exactly five sessions sit strictly after signal_end.
        assert len(december[december > anchor.signal_end]) == 5


def test_the_signal_never_reads_a_price_on_or_after_the_formation_date():
    """The four-trading-day gap is [PW01]'s own Eq.(1a) exclusion and is the
    structural reason this family cannot look ahead."""
    index = _calendar()
    for window in (*DECEMBER_WINDOWS, PLACEBO_WINDOW):
        for anchor in anchor_schedule(index, anchor_month=anchor_month_for(window)):
            bounds = window_bounds(index, anchor, window)
            if bounds is None:
                continue
            start, end = bounds
            assert start < end < anchor.formation
            assert len(index[(index > end) & (index < anchor.formation)]) >= 1


def test_jan_jun_and_jul_dec_partition_full_year_exactly():
    index = _calendar()
    for anchor in anchor_schedule(index, anchor_month=12):
        full = window_bounds(index, anchor, "full_year")
        first = window_bounds(index, anchor, "jan_jun")
        second = window_bounds(index, anchor, "jul_dec")
        if not (full and first and second):
            continue
        assert full[0] == first[0]
        assert first[1] == second[0]  # no gap, no double count
        assert second[1] == full[1]


def test_placebo_shares_the_jan_jun_ranking_variable_and_differs_only_in_month():
    """Pre-registration section 5: this is the whole design of the placebo."""
    assert anchor_month_for(PLACEBO_WINDOW) == 6
    for window in DECEMBER_WINDOWS:
        assert anchor_month_for(window) == 12
    index = _calendar()
    first_year = int(index.year.min())
    for anchor in anchor_schedule(index, anchor_month=6):
        bounds = window_bounds(index, anchor, PLACEBO_WINDOW)
        if anchor.year == first_year:
            # The first year in the index has no prior-year close to open the
            # window on, so it is refused rather than opened on a truncated
            # base price. Counted in TaxLossPanel.skipped_years, never guessed.
            assert bounds is None
            continue
        assert bounds is not None
        start, end = bounds
        # Same shape as the December jan_jun window: opens at the last close
        # of the prior year, closes six sessions before the month's end.
        assert start.year == anchor.year - 1
        assert end.month == 6


def test_a_year_without_a_prior_year_close_is_skipped_and_counted():
    index = _calendar()
    close = _planted_close(index, {"A": -0.2, "B": 0.2, "C": 0.05})
    panel = build_tax_loss_panel(close, close, window="full_year", form="lossonly")
    assert int(index.year.min()) in panel.skipped_years
    assert int(index.year.min()) not in {a.year for a in panel.anchors}


def test_a_truncated_anchor_month_is_skipped_not_clamped():
    """A December cut short by the data window would otherwise anchor the
    trade on a date that is not the month's real last session."""
    index = _calendar(end="2021-12-08")  # only ~6 December 2021 sessions
    years = {a.year for a in anchor_schedule(index, anchor_month=12)}
    assert 2021 not in years
    assert 2020 in years
    full = _calendar(end="2021-12-31")
    assert len(full[(full.year == 2021) & (full.month == 12)]) >= MIN_ANCHOR_MONTH_TRADING_DAYS


def test_lossonly_is_zero_for_gainers_and_the_magnitude_for_losers():
    """[PW01] Eqs.(1a)/(1b) plus 'We set LOSS equal to zero if the firm
    experienced a capital gain.'"""
    index = _calendar()
    close = _planted_close(index, {"WINNER": 0.40, "LOSER": -0.25, "FLAT": 0.0})
    panel = build_tax_loss_panel(close, close, window="full_year", form="lossonly")
    anchor = panel.anchors[-1].formation
    row = panel.frame.loc[anchor]
    assert row["WINNER"] == 0.0
    assert row["LOSER"] > 0.0
    assert row["FLAT"] == pytest.approx(0.0, abs=1e-12)
    # The magnitude is the accrued loss itself, not a rank or a z-score.
    bounds = window_bounds(index, panel.anchors[-1], "full_year")
    expected = -(close.loc[bounds[1], "LOSER"] / close.loc[bounds[0], "LOSER"] - 1.0)
    assert row["LOSER"] == pytest.approx(expected)


def test_signed_keeps_the_winner_side_and_is_the_negated_return():
    index = _calendar()
    close = _planted_close(index, {"WINNER": 0.40, "LOSER": -0.25})
    panel = build_tax_loss_panel(close, close, window="full_year", form="signed")
    anchor = panel.anchors[-1]
    row = panel.frame.loc[anchor.formation]
    bounds = window_bounds(index, anchor, "full_year")
    for ticker in ("WINNER", "LOSER"):
        expected = -(close.loc[bounds[1], ticker] / close.loc[bounds[0], ticker] - 1.0)
        assert row[ticker] == pytest.approx(expected)
    assert row["WINNER"] < 0.0 < row["LOSER"]


def test_the_biggest_loser_ranks_highest_so_the_harness_goes_long_it():
    index = _calendar()
    close = _planted_close(index, {"MILD": -0.05, "SEVERE": -0.40, "WINNER": 0.30})
    for form in TAX_LOSS_FORMS:
        panel = build_tax_loss_panel(close, close, window="full_year", form=form)
        row = panel.frame.loc[panel.anchors[-1].formation]
        assert row["SEVERE"] > row["MILD"] > row["WINNER"] or (
            form == "lossonly" and row["SEVERE"] > row["MILD"] > 0.0 == row["WINNER"]
        )


def test_the_panel_is_nan_on_every_non_anchor_date():
    index = _calendar()
    close = _planted_close(index, {"A": -0.2, "B": 0.2})
    panel = build_tax_loss_panel(close, close, window="full_year", form="lossonly")
    anchors = {a.formation for a in panel.anchors}
    non_anchor = panel.frame.drop(index=list(anchors))
    assert non_anchor.isna().to_numpy().all()
    assert panel.frame.loc[list(anchors)].notna().to_numpy().any()


def test_future_prices_cannot_change_an_already_computed_anchor_value():
    """Truncation invariance: rewriting every price AFTER the signal-window
    end must leave that anchor's signal byte-identical."""
    index = _calendar()
    close = _planted_close(index, {"A": -0.2, "B": 0.2, "C": -0.5})
    panel = build_tax_loss_panel(close, close, window="full_year", form="lossonly")
    anchor = panel.anchors[-1]
    tampered = close.copy()
    after = index[index > anchor.signal_end]
    tampered.loc[after] = tampered.loc[after] * 5.0
    tampered_panel = build_tax_loss_panel(tampered, tampered, window="full_year", form="lossonly")
    pd.testing.assert_series_equal(
        panel.frame.loc[anchor.formation], tampered_panel.frame.loc[anchor.formation]
    )


def test_signal_fn_reads_only_the_formation_row_of_its_bound_panel():
    index = _calendar()
    close = _planted_close(index, {"A": -0.2, "B": 0.2})
    panel = build_tax_loss_panel(close, close, window="full_year", form="lossonly")
    anchor = panel.anchors[-1].formation
    view = CrossSectionalData(close=close.loc[:anchor], fundamental_signal=panel.frame.loc[:anchor])
    signal = signal_tax_loss(view, panel=panel.frame)
    pd.testing.assert_series_equal(
        signal.dropna(), panel.frame.loc[anchor].dropna(), check_names=False
    )
    # A non-anchor formation date yields no signal at all, not a stale one.
    other = close.index[close.index < anchor][-3]
    view = CrossSectionalData(close=close.loc[:other], fundamental_signal=panel.frame.loc[:other])
    assert signal_tax_loss(view, panel=panel.frame).isna().all()


def test_signal_fn_refuses_without_the_fundamental_signal_carrier():
    index = _calendar()
    close = _planted_close(index, {"A": -0.2})
    with pytest.raises(ValueError, match="requires_fundamental_signal"):
        signal_tax_loss(CrossSectionalData(close=close), panel=close)


def test_unknown_window_and_form_are_rejected_loudly():
    index = _calendar()
    close = _planted_close(index, {"A": -0.2})
    anchor = anchor_schedule(index, anchor_month=12)[-1]
    with pytest.raises(ValueError, match="unknown tax-loss window"):
        window_bounds(index, anchor, "not_a_window")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unknown tax-loss signal form"):
        build_tax_loss_panel(close, close, window="full_year", form="not_a_form")  # type: ignore[arg-type]


def test_anchor_schedule_on_an_empty_index_returns_nothing_rather_than_raising():
    assert anchor_schedule(pd.DatetimeIndex([]), anchor_month=12) == []


# --- the sleeve-scaling deviation, pinned rather than assumed ---------------


def test_sleeve_scale_matches_the_harness_own_n_sleeves_arithmetic():
    for holding in TAX_LOSS_HOLDING_DAYS:
        assert sleeve_scale(holding) == max(1, holding // TAX_LOSS_COHORT_FORMATION_DAYS)
        assert sleeve_scale(holding) == holding


def _tied_leg_frame(
    index: pd.DatetimeIndex, *, n_tickers: int = 60, n_losers: int = 6, planted_loss: float = -0.20
) -> pd.DataFrame:
    """A random-walk price frame whose LAST full_year window is rigged so the
    long leg is exactly `n_losers` names tied at the same accrued loss.

    Why the tie matters: cross_sectional._leg_weights degrades to EQUAL weight
    when a leg's members carry no magnitude spread, so the harness's book
    becomes hand-computable and the 1/holding_days scaling claim can be pinned
    EXACTLY rather than approximately. Only the two window-boundary rows are
    overwritten — the signal reads nothing else — so every held day is still a
    real, non-degenerate random return."""
    rng = np.random.default_rng(3)
    tickers = [f"T{i:02d}" for i in range(n_tickers)]
    steps = rng.normal(0.0004, 0.012, size=(len(index), n_tickers))
    close = pd.DataFrame(
        100.0 * np.cumprod(1.0 + steps, axis=0), index=index, columns=tickers, dtype=float
    )
    anchor = anchor_schedule(index, anchor_month=12)[-1]
    start, end = window_bounds(index, anchor, "full_year")
    close.loc[start] = 100.0
    planted = np.full(n_tickers, 1.0 + 0.15)
    planted[:n_losers] = 1.0 + planted_loss
    close.loc[end] = 100.0 * planted
    return close


def test_blended_daily_return_is_exactly_one_over_holding_days_of_the_real_book():
    """Pre-registration 3.7, pinned EXACTLY rather than assumed.

    The harness runs `holding_days` staggered sleeves and only one of them ever
    carries a book, so the reported series must be the real once-a-year book's
    series divided by exactly that count, on every held day."""
    index = _calendar(start="2015-01-02", end="2019-12-31")
    close = _tied_leg_frame(index)
    panels = build_all_tax_loss_panels(close, close)
    spec = next(
        s
        for s in build_tax_loss_family(panels)
        if s.pattern_id == spec_id("full_year", "lossonly", 6)
    )
    replay = run_cross_sectional_backtest(
        CrossSectionalData(close=close, fundamental_signal=panels["full_year_lossonly"].frame),
        spec,
        CrossSectionalConfig(cost_bps=0.0, formation_start=date(2015, 1, 2)),
        lambda ticker, on: True,
    )
    assert replay.status == "ok"
    formed = [f for f in replay.formations if f.skipped_reason is None]
    assert formed, "the December anchor must be reached by exactly one sleeve"

    record = formed[-1]
    assert len(record.long_tickers) == 6  # the six tied losers, equal weighted
    daily_all = close.pct_change(fill_method=None)
    held = replay.daily_returns.index[replay.daily_returns.index > record.date][
        : spec.holding_days
    ]
    for day in held:
        by_hand = float(daily_all.loc[day, record.long_tickers].mean()) - float(
            daily_all.loc[day, record.short_tickers].mean()
        )
        blended = float(replay.daily_returns.loc[day]) * sleeve_scale(spec.holding_days)
        assert blended == pytest.approx(by_hand, rel=1e-9, abs=1e-12)

    # And every day outside a formed hold is EXACTLY zero, because all
    # `holding_days` sleeves are flat there.
    all_held: set[pd.Timestamp] = set()
    for rec in formed:
        after = replay.daily_returns.index[replay.daily_returns.index > rec.date]
        all_held.update(after[: spec.holding_days])
    outside = replay.daily_returns.drop(index=sorted(all_held))
    assert (outside.to_numpy() == 0.0).all()


def test_sharpe_is_invariant_to_the_sleeve_scaling_but_annual_return_is_not():
    """The reason the deviation in 3.7 is reportable rather than disqualifying:
    every statistic the verdict reads is scale-invariant, and the two that are
    not are de-scaled in the report."""
    from app.services.research_lab.metrics import sharpe_ratio

    rng = np.random.default_rng(5)
    series = pd.Series(rng.normal(0.0, 0.01, 800))
    for scale in (6, 21):
        assert sharpe_ratio(series / scale) == pytest.approx(sharpe_ratio(series))
        assert (series / scale).mean() * 252 != pytest.approx(series.mean() * 252)


def test_annual_event_returns_recover_one_number_per_formed_formation():
    index = _calendar(start="2015-01-02", end="2019-12-31")
    close = _tied_leg_frame(index)
    panels = build_all_tax_loss_panels(close, close)
    spec = next(
        s
        for s in build_tax_loss_family(panels)
        if s.pattern_id == spec_id("full_year", "lossonly", 6)
    )
    replay = run_cross_sectional_backtest(
        CrossSectionalData(close=close, fundamental_signal=panels["full_year_lossonly"].frame),
        spec,
        CrossSectionalConfig(cost_bps=0.0, formation_start=date(2015, 1, 2)),
        lambda ticker, on: True,
    )
    formed = [f for f in replay.formations if f.skipped_reason is None]
    stats = annual_event_returns(replay, spec.holding_days)
    assert stats.n_events == len(formed) >= 1
    assert stats.event_dates == [f.date.date().isoformat() for f in formed]
    assert 0.0 <= stats.hit_rate <= 1.0
    assert stats.mean == pytest.approx(float(np.mean(stats.event_returns)))

    # One formation per turn of the year, never two.
    assert len({d[:4] for d in stats.event_dates}) == len(stats.event_dates)


def test_memoized_membership_returns_exactly_what_the_real_gate_returns():
    calls: list[tuple[str, date]] = []

    def base(ticker: str, on: date) -> bool:
        calls.append((ticker, on))
        return ticker == "IN"

    gate = memoized_membership(base)
    assert gate("IN", date(2020, 1, 2)) is True
    assert gate("OUT", date(2020, 1, 2)) is False
    assert gate("IN", date(2020, 1, 2)) is True
    assert gate("OUT", date(2020, 1, 2)) is False
    assert len(calls) == 2  # each distinct question asked once


def test_screening_start_before_membership_coverage_is_refused():
    from app.services.research_lab.cross_sectional_tax_loss_selling import (
        run_tax_loss_universe,
    )

    with pytest.raises(ValueError, match="predates point-in-time membership"):
        run_tax_loss_universe("sp500", date(2010, 1, 4), date(2020, 1, 1))
    with pytest.raises(ValueError, match="predates point-in-time membership"):
        run_tax_loss_universe("sp600", date(2015, 1, 7), date(2020, 1, 1))


# ---------------------------------------------------------------------------
# 3. REPORT / PRE-REGISTRATION CONSISTENCY
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def run_payload() -> dict:
    if not JSON_PATH.exists():
        pytest.skip(f"{JSON_PATH.name} has not been produced yet")
    return json.loads(JSON_PATH.read_text())


def test_preregistration_exists_and_declares_the_grid_this_module_builds():
    text = PREREG_PATH.read_text()
    assert "n_local = 32" in text
    assert "TAX_LOSS_SPEC_CEILING = 16" in text
    assert "0.95" in text and "VALIDATED-EDGE" in text
    # The two abstract-only sources must be flagged in the pre-registration.
    assert text.count("ABSTRACT-LEVEL ONLY") >= 2


def test_report_and_json_agree_on_the_verdict_and_the_denominator(run_payload):
    report = REPORT_PATH.read_text()
    assert run_payload["n_trials"] == TAX_LOSS_N_TRIALS == 32
    assert run_payload["validated_edge_bar"] == VALIDATED_EDGE_BAR
    assert run_payload["verdict"].upper() in report
    assert str(run_payload["denominators"]) in report


def test_json_carries_all_32_evaluations_across_both_universes(run_payload):
    universes = run_payload["universes"]
    assert {u["universe"] for u in universes} == {"sp500", "sp600"}
    for universe in universes:
        ids = [e["pattern_id"] for e in universe["evaluations"]]
        assert len(ids) == len(set(ids))
        assert len(ids) == TAX_LOSS_SPEC_CEILING, (
            f"{universe['universe']} reported {len(ids)} of {TAX_LOSS_SPEC_CEILING} specs"
        )


def test_every_spec_has_a_preservation_score_and_a_dsr_at_every_denominator(run_payload):
    """CLAUDE.md: preservation_score with no exceptions, DSR across multiple
    N. This is the test that makes 'no exceptions' mechanical."""
    denominators = {str(n) for n in run_payload["denominators"]}
    for universe in run_payload["universes"]:
        for evaluation in universe["evaluations"]:
            assert set(evaluation["dsr_by_n"]) == denominators
            preservation = evaluation["preservation"]
            assert "preservation_score" in preservation
            assert preservation["preservation_score"] is not None
            assert preservation["credibility"] is not None


def test_dsr_is_monotonically_non_increasing_in_the_denominator(run_payload):
    """DSR is strictly decreasing in N, so a three-point ladder BRACKETS every
    N between. A violation would mean the ladder was not computed on one
    consistent return series."""
    ordered = sorted(run_payload["denominators"])
    for universe in run_payload["universes"]:
        for evaluation in universe["evaluations"]:
            values = [evaluation["dsr_by_n"][str(n)] for n in ordered]
            values = [v for v in values if v is not None]
            assert all(a >= b - 1e-12 for a, b in pairwise(values)), (
                f"{universe['universe']}/{evaluation['pattern_id']} DSR ladder is not monotone: {values}"
            )


def test_verdict_in_the_report_is_what_policy_d_computes_from_the_reported_dsrs(run_payload):
    from app.services.research_lab.registration_scorecard import policy_d_verdict

    n_local = run_payload["n_trials"]
    evaluations = [e for u in run_payload["universes"] for e in u["evaluations"]]
    best = max(
        evaluations,
        key=lambda e: (
            e["dsr_by_n"][str(n_local)] if e["dsr_by_n"][str(n_local)] is not None else -1.0
        ),
    )
    dsr_by_n = {int(n): v for n, v in best["dsr_by_n"].items()}
    assert run_payload["verdict"] == policy_d_verdict(
        dsr_by_n=dsr_by_n, threshold=VALIDATED_EDGE_BAR, n_local=n_local
    )
    assert run_payload["best_spec"].endswith(best["pattern_id"])


def test_annual_event_count_never_exceeds_the_years_in_the_window(run_payload):
    """The effective independent sample is one observation per turn of the
    year. If a spec ever reported more, the anchor schedule would be firing
    more than once a year and the whole family would be mis-specified."""
    for universe in run_payload["universes"]:
        start = date.fromisoformat(universe["formation_start"])
        end = date.fromisoformat(universe["window_end"])
        max_events = end.year - start.year + 1
        for evaluation in universe["evaluations"]:
            assert evaluation["annual"]["n_events"] <= max_events
            assert evaluation["annual"]["n_events"] == evaluation["n_formations"]


def test_each_universe_reports_the_cost_model_the_preregistration_declared(run_payload):
    by_universe = {u["universe"]: u for u in run_payload["universes"]}
    assert by_universe["sp500"]["cost_model"] == "edge_spread"
    assert by_universe["sp600"]["cost_model"] == "flat_bps"
    assert by_universe["sp600"]["cost_bps"] == SMALL_CAP_COST_BPS
    for universe in by_universe.values():
        assert universe["financing_bps_per_year"] == 17.0


def test_borrow_ladder_is_present_and_a_higher_rate_never_raises_the_sharpe(run_payload):
    for universe in run_payload["universes"]:
        arms = {a["key"]: a for a in universe["borrow_arms"]}
        assert {"borrow_0bp", "borrow_34bp", "borrow_430bp"} <= set(arms)
        for pattern_id in arms["borrow_0bp"]["sharpe_by_pattern"]:
            free = arms["borrow_0bp"]["sharpe_by_pattern"][pattern_id]
            expensive = arms["borrow_430bp"]["sharpe_by_pattern"][pattern_id]
            assert expensive <= free + 1e-9, (
                f"{pattern_id}: 430bp borrow produced a HIGHER Sharpe than 0bp"
            )
