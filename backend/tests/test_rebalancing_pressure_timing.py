"""Tests for the institutional-rebalancing-pressure family.

The load-bearing one is test_recursion_reproduces_the_papers_own_worked_example:
CLAUDE.md forbids trusting a published formula implemented from memory, and
[HMM26] footnote 8 hands us a known answer for exactly the recursion this whole
family rests on. Everything else is timing, cost arithmetic, grid-size and
sign-convention pinning.
"""

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import app.services.research_lab.rebalancing_pressure_timing as rp
from app.services.research_lab.rebalancing_pressure_timing import (
    BASELINE_COST_ARM,
    COST_ARMS,
    DELTA_GRID,
    MONTH_START_REVERSAL_LAG,
    REBALANCING_COST_BPS,
    REBALANCING_DIRECTION,
    REBALANCING_FAMILY,
    REBALANCING_HOLDING_DAYS,
    REBALANCING_N_TRIALS,
    REBALANCING_SHORT_BORROW_BPS_PER_YEAR,
    REBALANCING_SIZINGS,
    SIGNAL_RESCALE,
    TARGET_EQUITY_WEIGHT,
    TRADED_UNIVERSE,
    WEEK4_TRADING_DAYS,
    RebalancingConfig,
    align_rebalancing_data,
    averaged_threshold_signal,
    build_target_positions,
    calendar_signal_series,
    last_n_trading_days_mask,
    month_end_flags,
    policy_d_denominators,
    rebalanced_weight,
    run_rebalancing_backtest,
    screen_rebalancing_pressure,
    sleeve_smoothed_positions,
    threshold_reset_count,
    threshold_signal_series,
    trailing_window_signal,
    week4_modified_calendar_position,
)

BACKEND = Path(__file__).resolve().parents[1]


# --- synthetic-data helpers ------------------------------------------------


def _panel(equity_returns, bond_returns, start="2020-01-01"):
    """A two-column close panel whose pct_change reproduces the given returns
    exactly from the SECOND row onward (the first row's return is NaN, as it
    is for any real price series)."""
    n = len(equity_returns)
    index = pd.bdate_range(start, periods=n + 1)
    equity = [100.0]
    bond = [100.0]
    for e, b in zip(equity_returns, bond_returns, strict=True):
        equity.append(equity[-1] * (1.0 + e))
        bond.append(bond[-1] * (1.0 + b))
    return pd.DataFrame(
        {rp.EQUITY_TICKER: equity, rp.BOND_TICKER: bond}, index=index
    )


def _random_panel(n=1400, seed=20260906):
    rng = np.random.default_rng(seed)
    return _panel(
        rng.normal(0.0004, 0.011, n).tolist(),
        rng.normal(0.0002, 0.004, n).tolist(),
        start="2015-01-01",
    )


# --- THE known-answer check (pre-registration fidelity check F11) ----------


def test_recursion_reproduces_the_papers_own_worked_example():
    """[HMM26] footnote 8, verbatim: "If the equity market increases by 10%
    and the bond market remains unchanged, the portfolio value becomes
    66 + 40 = $106. The equity allocation is now 66/106 = 62.26%."

    This is the whole family's primitive, and CLAUDE.md forbids trusting a
    published formula implemented from memory. The paper hands us the answer;
    this asserts it to machine precision AND to the paper's own printed 4
    significant figures."""
    w = rebalanced_weight(TARGET_EQUITY_WEIGHT, 0.10, 0.0)
    assert w == pytest.approx(66.0 / 106.0, rel=0, abs=1e-15)
    assert round(w, 4) == 0.6226

    # [HMM26] p.10: "both rebalancing signals should increase by
    # approximately 2.26%" in exactly this scenario.
    assert (w - TARGET_EQUITY_WEIGHT) * 100 == pytest.approx(2.26, abs=0.01)

    # The paper's second known answer from the same footnote: the required
    # rebalancing trade is 0.60 x 0.40 x 10% = 2.4% of portfolio value.
    assert TARGET_EQUITY_WEIGHT * (1 - TARGET_EQUITY_WEIGHT) * 0.10 == pytest.approx(0.024)


def test_recursion_is_a_no_op_when_both_legs_return_zero():
    assert rebalanced_weight(0.60, 0.0, 0.0) == pytest.approx(0.60)
    assert rebalanced_weight(0.37, 0.0, 0.0) == pytest.approx(0.37)


def test_recursion_is_scale_free_in_the_obvious_way():
    """Equal returns on both legs cannot move the weight, whatever they are."""
    for r in (-0.2, -0.01, 0.0, 0.05, 0.4):
        assert rebalanced_weight(0.60, r, r) == pytest.approx(0.60)


def test_recursion_refuses_a_non_finite_or_wiped_out_portfolio():
    assert np.isnan(rebalanced_weight(np.nan, 0.01, 0.0))
    assert np.isnan(rebalanced_weight(0.6, np.nan, 0.0))
    # Both legs to zero: the portfolio value is 0 and the allocation is
    # undefined, not 0/0 = some number.
    assert np.isnan(rebalanced_weight(0.6, -1.0, -1.0))


# --- the pre-declared grid -------------------------------------------------


def test_family_size_is_exactly_the_pre_declared_denominator():
    assert len(REBALANCING_FAMILY) == REBALANCING_N_TRIALS == 24
    assert len({s.spec_id for s in REBALANCING_FAMILY}) == 24
    assert (
        len(rp._SIGNAL_DEFINITIONS) * len(REBALANCING_SIZINGS) * len(REBALANCING_HOLDING_DAYS)
        == REBALANCING_N_TRIALS
    )


def test_the_control_appears_in_every_cell_and_nothing_else_is_a_control():
    controls = [s for s in REBALANCING_FAMILY if s.is_control]
    assert len(controls) == len(REBALANCING_SIZINGS) * len(REBALANCING_HOLDING_DAYS) == 4
    assert {s.signal_key for s in controls} == {"trailing21_ctrl"}


def test_direction_is_a_single_pre_declared_constant():
    """A per-spec sign would double the real search to 48 while still
    reporting n_trials = 24 -- the exact uncounted-degree-of-freedom failure
    the DSR exists to prevent."""
    assert REBALANCING_DIRECTION == -1.0


def test_delta_grid_is_the_papers_published_one():
    """[HMM26] Eq. (2): "delta values that span the range 0%-2.5% with
    increments of 0.1%"."""
    assert len(DELTA_GRID) == 26
    assert DELTA_GRID[0] == 0.0
    assert DELTA_GRID[-1] == 0.025
    assert np.allclose(np.diff(DELTA_GRID), 0.001)


def test_holding_axis_excludes_long_holds():
    """A 21-day hold of a next-day prediction is a different claim, not a
    slower version of this one (pre-registration section 5)."""
    assert REBALANCING_HOLDING_DAYS == (1, 5)
    assert all(s.holding_days <= 5 for s in REBALANCING_FAMILY)


# --- the threshold recursion ----------------------------------------------


def test_delta_zero_rebalances_every_day_and_the_signal_is_the_one_day_deviation():
    """[HMM26] p.11: "When delta = 0, the 60/40 portfolio rebalances 252 times
    per year (i.e., every business day)." With the state reset every day, the
    signal must be exactly the ONE-period deviation from 60%."""
    rng = np.random.default_rng(7)
    e = rng.normal(0.0, 0.01, 200)
    b = rng.normal(0.0, 0.004, 200)
    panel = _panel(e.tolist(), b.tolist())
    data = align_rebalancing_data(panel)

    signal = threshold_signal_series(data.equity_returns, data.bond_returns, 0.0)
    expected = [
        rebalanced_weight(TARGET_EQUITY_WEIGHT, re, rb) - TARGET_EQUITY_WEIGHT
        for re, rb in zip(e, b, strict=True)
    ]
    assert np.allclose(signal.to_numpy()[1:], expected, atol=1e-15)

    resets = threshold_reset_count(data.equity_returns, data.bond_returns, 0.0)
    assert resets == len(e)  # every usable day


def test_a_wide_band_never_fires_and_the_weight_just_drifts():
    """With delta far beyond anything the path reaches, no reset ever happens,
    so the signal is the fully-drifted deviation from an unrebalanced 60/40."""
    e = [0.001] * 50
    b = [0.0] * 50
    data = align_rebalancing_data(_panel(e, b))
    signal = threshold_signal_series(data.equity_returns, data.bond_returns, 0.99)
    assert threshold_reset_count(data.equity_returns, data.bond_returns, 0.99) == 0

    w = TARGET_EQUITY_WEIGHT
    for i, (re, rb) in enumerate(zip(e, b, strict=True), start=1):
        w = rebalanced_weight(w, re, rb)
        assert signal.iloc[i] == pytest.approx(w - TARGET_EQUITY_WEIGHT)


def test_two_sided_and_one_sided_triggers_genuinely_differ_on_a_falling_equity_path():
    """The pre-registration's deviation D2. Appendix B's LITERAL rule resets
    only on POSITIVE breaches, so on a path where equities keep losing the
    one-sided state never resets and its deviation drifts without bound, while
    the two-sided band pins it near -delta. [HMM26] p.14 reports the signal's
    average value as POSITIVE, which is impossible under the one-sided rule --
    the evidence on which the pre-registration made two-sided primary."""
    e = [-0.01] * 120
    b = [0.0] * 120
    data = align_rebalancing_data(_panel(e, b))

    two = threshold_signal_series(data.equity_returns, data.bond_returns, 0.02, two_sided=True)
    one = threshold_signal_series(data.equity_returns, data.bond_returns, 0.02, two_sided=False)

    assert threshold_reset_count(data.equity_returns, data.bond_returns, 0.02, two_sided=True) > 0
    assert (
        threshold_reset_count(data.equity_returns, data.bond_returns, 0.02, two_sided=False) == 0
    )
    # The two-sided band keeps the deviation bounded; the one-sided one does not.
    assert two.min() > -0.05
    assert one.min() < -0.20


def test_averaged_threshold_signal_is_the_plain_mean_of_its_26_arms():
    data = align_rebalancing_data(_random_panel(n=300))
    averaged = averaged_threshold_signal(data.equity_returns, data.bond_returns)
    arms = pd.concat(
        [threshold_signal_series(data.equity_returns, data.bond_returns, d) for d in DELTA_GRID],
        axis=1,
    )
    assert np.allclose(
        averaged.dropna().to_numpy(), arms.mean(axis=1).dropna().to_numpy(), atol=1e-15
    )


# --- the calendar recursion and the week4 gate ----------------------------


def test_month_end_flags_pick_the_last_trading_day_of_each_month():
    index = pd.DatetimeIndex(
        ["2021-01-28", "2021-01-29", "2021-02-01", "2021-02-25", "2021-02-26", "2021-03-01"]
    )
    flags = month_end_flags(index)
    assert list(flags) == [False, True, False, False, True, True]  # last row is always flagged


def test_last_n_trading_days_mask_counts_trading_days_not_calendar_days():
    index = pd.DatetimeIndex(
        [
            "2021-01-25",
            "2021-01-26",
            "2021-01-27",
            "2021-01-28",
            "2021-01-29",
            "2021-02-01",
            "2021-02-02",
        ]
    )
    mask = last_n_trading_days_mask(index, 3)
    # January's block is the first five rows; its last three are 27th-29th.
    assert list(mask[:5]) == [False, False, True, True, True]
    # February's (partial) block is two rows, both inside its own last three.
    assert list(mask[5:]) == [True, True]


def test_calendar_signal_resets_after_month_end():
    """[HMM26] Eq. (B.2) as displayed: the state resets on the day AFTER the
    month-end day. So on the SECOND trading day of a month the signal must be
    the single-day deviation from a freshly rebalanced 60/40."""
    index = pd.bdate_range("2021-01-25", periods=12)
    rng = np.random.default_rng(11)
    e = rng.normal(0.0, 0.01, len(index) - 1)
    b = rng.normal(0.0, 0.004, len(index) - 1)
    panel = _panel(e.tolist(), b.tolist())
    panel.index = index
    data = align_rebalancing_data(panel)

    signal = calendar_signal_series(data.equity_returns, data.bond_returns)
    flags = month_end_flags(data.close.index)
    month_end_positions = [i for i, f in enumerate(flags[:-1]) if f]
    assert month_end_positions, "the fixture must span a month boundary"
    for pos in month_end_positions:
        # pos+1 is the first day of the new month: state is reset going INTO
        # pos+2, so pos+2's signal is a pure one-day deviation.
        if pos + 2 >= len(data.close.index):
            continue
        expected = (
            rebalanced_weight(
                TARGET_EQUITY_WEIGHT,
                data.equity_returns.iloc[pos + 2],
                data.bond_returns.iloc[pos + 2],
            )
            - TARGET_EQUITY_WEIGHT
        )
        assert signal.iloc[pos + 2] == pytest.approx(expected)


def test_week4_position_is_flat_away_from_month_end_and_reverses_on_the_first_day():
    """[HMM26] Section 4: sign(-Calendar Signal_t) inside week4, +sign(Calendar
    Signal_{t-4}) on the first trading day of a month -- note the MISSING minus,
    which is the paper's own reversal leg -- and zero everywhere else."""
    data = align_rebalancing_data(_random_panel(n=400, seed=3))
    calendar = calendar_signal_series(data.equity_returns, data.bond_returns)
    position = week4_modified_calendar_position(calendar, use_sign=True)

    index = data.close.index
    week4 = last_n_trading_days_mask(index, WEEK4_TRADING_DAYS)
    is_month_end = month_end_flags(index)
    first_of_month = np.zeros(len(index), dtype=bool)
    first_of_month[1:] = is_month_end[:-1]

    other = ~week4 & ~first_of_month
    assert set(np.unique(position.to_numpy()[other][~np.isnan(position.to_numpy()[other])])) == {
        0.0
    }

    for i in np.flatnonzero(week4 & ~first_of_month):
        if np.isnan(calendar.iloc[i]) or calendar.iloc[i] == 0.0:
            continue
        assert position.iloc[i] == -np.sign(calendar.iloc[i])

    reversal_days = np.flatnonzero(first_of_month)
    checked = 0
    for i in reversal_days:
        if i < MONTH_START_REVERSAL_LAG:
            continue
        source = calendar.iloc[i - MONTH_START_REVERSAL_LAG]
        if np.isnan(source) or source == 0.0:
            continue
        # SAME sign as the lagged signal, not the negated one.
        assert position.iloc[i] == np.sign(source)
        checked += 1
    assert checked > 3


def test_the_control_signal_has_no_trigger_and_no_calendar():
    """The trailing-window control is a pure function of the last 21 days of
    returns: identical inputs on two disjoint stretches must give identical
    signals, which is exactly what a triggered or calendrical recursion could
    not do."""
    e = [0.002, -0.001, 0.0005] * 40
    b = [0.0001] * 120
    data = align_rebalancing_data(_panel(e, b))
    control = trailing_window_signal(data.equity_returns, data.bond_returns, 21)
    assert control.iloc[:21].isna().all()  # min_periods is enforced
    assert control.iloc[60] == pytest.approx(control.iloc[60 + 3], abs=1e-12)


# --- sleeves ---------------------------------------------------------------


def test_h1_sleeve_book_is_the_daily_target_exactly():
    targets = pd.Series([0.1, -0.4, 0.7, 0.0], index=pd.bdate_range("2021-01-04", periods=4))
    assert sleeve_smoothed_positions(targets, 1).equals(targets)


def test_h5_sleeve_book_is_a_strict_five_day_mean():
    targets = pd.Series(
        [1.0, 2.0, 3.0, 4.0, 5.0, 6.0], index=pd.bdate_range("2021-01-04", periods=6)
    )
    smoothed = sleeve_smoothed_positions(targets, 5)
    assert smoothed.iloc[:4].isna().all()  # a partial sleeve average is refused
    assert smoothed.iloc[4] == pytest.approx(3.0)
    assert smoothed.iloc[5] == pytest.approx(4.0)


# --- backtest timing and cost arithmetic -----------------------------------


def _constant_signal_spec(value: float):
    """A spec whose target position is a known constant, so the replay's
    arithmetic can be checked by hand."""

    class _Spec:
        spec_id = "fixture"
        signal_key = "fixture"
        sizing = "scaled"
        holding_days = 1
        citation = ""
        hypothesis = ""
        is_control = False

    spec = _Spec()
    rp._DEFINITION_BY_KEY["fixture"] = rp.SignalDefinition(
        key="fixture",
        hypothesis="",
        citation="",
        is_control=False,
        raw_builder=None,
        position_builder=lambda e, b, use_sign: pd.Series(value, index=e.index),
    )
    return spec


def test_the_position_formed_at_t_earns_day_t_plus_ones_return_and_nothing_earlier():
    """THE look-ahead test. With a constant unit position and zero costs, every
    realized return must equal that day's spread return exactly, and the
    series must start one day AFTER the first formation."""
    e = [0.01, -0.02, 0.03, 0.005, -0.001]
    b = [0.0] * 5
    data = align_rebalancing_data(_panel(e, b))
    spec = _constant_signal_spec(1.0)
    config = RebalancingConfig(
        cost_bps=0.0, short_borrow_bps_per_year=0.0, formation_start=date(2000, 1, 1)
    )
    replay = run_rebalancing_backtest(data, spec, config)
    assert replay.status == "ok"
    # First usable position is at index 0 (the constant series has no NaN),
    # earning index 1's spread; the last realized day is the final row.
    expected = data.spread_returns.iloc[1:]
    assert np.allclose(replay.daily_returns.to_numpy(), expected.to_numpy(), atol=1e-15)
    assert replay.daily_returns.index[0] == data.close.index[1]


def test_turnover_cost_is_two_units_of_gross_notional_per_unit_of_position_change():
    """A flat-to-unit swing trades one long leg and one short leg, i.e. 2.0
    gross notional, so it costs 2 x cost_bps."""
    data = align_rebalancing_data(_panel([0.0] * 4, [0.0] * 4))
    spec = _constant_signal_spec(1.0)
    config = RebalancingConfig(
        cost_bps=3.0, short_borrow_bps_per_year=0.0, formation_start=date(2000, 1, 1)
    )
    replay = run_rebalancing_backtest(data, spec, config)
    # Only the opening trade (0 -> 1) has turnover; the position is constant
    # thereafter.
    assert replay.total_turnover == pytest.approx(1.0)
    assert replay.total_cost == pytest.approx(3.0 / 1e4 * 2.0 * 1.0)
    assert replay.daily_returns.iloc[0] == pytest.approx(-3.0 / 1e4 * 2.0)
    assert replay.daily_returns.iloc[1] == pytest.approx(0.0)


def test_financing_accrues_on_calendar_days_so_a_weekend_costs_three():
    """Charging per TRADING day would undercharge a continuously-held book by
    about 31%; the same reasoning cross_sectional.FINANCING_DAYS_PER_YEAR
    documents."""
    data = align_rebalancing_data(_panel([0.0] * 6, [0.0] * 6))
    spec = _constant_signal_spec(1.0)
    config = RebalancingConfig(
        cost_bps=0.0, short_borrow_bps_per_year=365.0, formation_start=date(2000, 1, 1)
    )
    replay = run_rebalancing_backtest(data, spec, config)
    daily_rate = 365.0 / 1e4 / rp.FINANCING_DAYS_PER_YEAR
    gaps = np.diff(data.close.index.to_numpy()).astype("timedelta64[D]").astype(int)
    expected = -daily_rate * gaps
    assert np.allclose(replay.daily_returns.to_numpy(), expected, atol=1e-15)
    # A Friday->Monday step really did cost three days.
    assert 3 in set(gaps)


def test_sign_sizing_carries_the_pre_declared_direction():
    """A POSITIVE signal means the simulated portfolio is OVERWEIGHT equity,
    which [HMM26] p.10 says predicts a LOWER equity-minus-bond return -- so
    the position must be SHORT the spread."""
    data = align_rebalancing_data(_random_panel(n=200, seed=5))
    spec = next(
        s
        for s in REBALANCING_FAMILY
        if s.signal_key == "threshold" and s.sizing == "sign" and s.holding_days == 1
    )
    positions = build_target_positions(data, spec)
    signal = averaged_threshold_signal(data.equity_returns, data.bond_returns)
    joined = pd.concat([positions.rename("p"), signal.rename("s")], axis=1).dropna()
    joined = joined[joined["s"] != 0.0]
    assert len(joined) > 50
    assert (np.sign(joined["p"]) == -np.sign(joined["s"])).all()


def test_scaled_sizing_uses_the_papers_own_1_point_5_percent_constant():
    data = align_rebalancing_data(_random_panel(n=200, seed=6))
    spec = next(
        s
        for s in REBALANCING_FAMILY
        if s.signal_key == "threshold" and s.sizing == "scaled" and s.holding_days == 1
    )
    positions = build_target_positions(data, spec)
    signal = averaged_threshold_signal(data.equity_returns, data.bond_returns)
    expected = REBALANCING_DIRECTION * signal / SIGNAL_RESCALE
    assert np.allclose(positions.dropna().to_numpy(), expected.dropna().to_numpy(), atol=1e-15)
    assert SIGNAL_RESCALE == 0.015


# --- screening -------------------------------------------------------------


def test_screening_produces_a_full_policy_d_record_for_every_spec():
    data = align_rebalancing_data(_random_panel(n=1600))
    denominators = [24, 481, 857]
    results = screen_rebalancing_pressure(
        data,
        REBALANCING_FAMILY,
        RebalancingConfig(formation_start=date(2015, 6, 1)),
        denominators=denominators,
    )
    assert len(results) == REBALANCING_N_TRIALS
    for r in results:
        assert set(r.dsr_by_n) == set(denominators)
        # preservation_score is computed for EVERY spec, no exceptions.
        assert "preservation_score" in r.preservation
        assert r.deflated_sharpe.n_trials == 24
        assert r.confound.spec_id == r.spec_id
    # DSR is strictly decreasing in N, so the ladder must be monotone.
    for r in results:
        values = [r.dsr_by_n[n] for n in denominators]
        if all(v is not None for v in values):
            assert values[0] >= values[1] >= values[2]


def test_a_pure_noise_panel_does_not_pass():
    """On returns with no signal in them at all, nothing may clear the 0.95
    bar -- the cheapest possible check that the machinery is not manufacturing
    positives."""
    data = align_rebalancing_data(_random_panel(n=1600, seed=999))
    results = screen_rebalancing_pressure(
        data,
        REBALANCING_FAMILY,
        RebalancingConfig(formation_start=date(2015, 6, 1)),
        denominators=[24, 481, 857],
    )
    assert all((r.dsr_by_n[24] or 0.0) < 0.95 for r in results)


def test_cost_arms_are_ordered_and_the_baseline_is_the_sourced_one():
    keys = [a.key for a in COST_ARMS]
    assert keys == ["cost_free", "baseline", "stress"]
    baseline = next(a for a in COST_ARMS if a.key == BASELINE_COST_ARM)
    assert baseline.cost_bps == REBALANCING_COST_BPS == 2.0
    # SOURCED: Beneish/Lee/Nichols 2015 p.15 general collateral.
    assert baseline.short_borrow_bps_per_year == REBALANCING_SHORT_BORROW_BPS_PER_YEAR == 34.0
    assert COST_ARMS[0].cost_bps == 0.0
    assert COST_ARMS[2].cost_bps > baseline.cost_bps


def test_higher_costs_never_raise_a_sharpe():
    data = align_rebalancing_data(_random_panel(n=1200, seed=42))
    cheap = screen_rebalancing_pressure(
        data,
        REBALANCING_FAMILY,
        RebalancingConfig(cost_bps=0.0, short_borrow_bps_per_year=0.0, formation_start=date(2015, 6, 1)),
        denominators=[24],
    )
    dear = screen_rebalancing_pressure(
        data,
        REBALANCING_FAMILY,
        RebalancingConfig(cost_bps=20.0, short_borrow_bps_per_year=200.0, formation_start=date(2015, 6, 1)),
        denominators=[24],
    )
    cheap_by_id = {r.spec_id: r.sharpe_annualized for r in cheap}
    for r in dear:
        assert r.sharpe_annualized <= cheap_by_id[r.spec_id] + 1e-12


def test_policy_d_denominators_match_the_committed_ladder_artifact():
    """The pooled rungs come from dsr_policy_n.json, the explicit POLICY
    artifact. Until 2026-09-06 this test read them off global_effective_n.json's
    `n_specs_clustered` / `raw_pooled_distinct_trials` — provenance fields on a
    MEASUREMENT artifact, which is exactly the accidental promotion that
    dsr_policy_n.py exists to undo."""
    artifact = json.loads(
        (BACKEND / "app/services/research_lab/dsr_policy_n.json").read_text()
    )
    ladder = artifact["ladder"]
    assert policy_d_denominators() == sorted(
        {24, ladder["n_mechanisms"], ladder["n_effective"], ladder["n_raw"]}
    )


def test_traded_universe_is_the_pair_vol_regime_timing_already_uses():
    from app.services.research_lab.vol_regime_timing import TARGET_EQUITY_VS_DURATION

    assert TRADED_UNIVERSE == ("SPY", "IEF")
    assert TARGET_EQUITY_VS_DURATION.risk_on == rp.EQUITY_TICKER
    assert TARGET_EQUITY_VS_DURATION.risk_off == rp.BOND_TICKER


# --- the committed run artifact -------------------------------------------


def test_the_committed_run_report_matches_this_modules_declared_constants():
    """Pins the checked-in result against the code that produced it, so a
    later change to the grid or the bar cannot silently orphan the report."""
    payload = json.loads(
        (BACKEND / "data/research_runs/rebalancing_pressure_2026-09-06.json").read_text()
    )
    assert payload["declared_n_trials"] == REBALANCING_N_TRIALS
    assert payload["n_trials"] == REBALANCING_N_TRIALS
    # THE REPORT KEEPS THE LADDER IT WAS RUN UNDER, and this assertion no
    # longer compares it against today's. Until 2026-09-06 this read
    # `== policy_d_denominators()`; the ladder then moved from {24, 481, 857}
    # to dsr_policy_n.json's rungs, which would orphan a report that is a
    # HISTORICAL RECORD of a run made under the old one. Rewriting the report
    # to match is not an option either: this family's recorded verdict is
    # definite_negative, i.e. decided at n_local, and CLAUDE.md's rule is not
    # to retroactively re-apply a newly-stricter rule to an already-declined
    # candidate — a stricter gate can only keep it declined.
    #
    # What is still pinned is everything that makes the report self-consistent:
    # its lowest rung is the denominator the run actually deflated at, its
    # rungs ascend, and (below) its verdict is reproducible from its own
    # numbers. Those are the properties that would catch a corrupted or
    # hand-edited artifact.
    assert payload["denominators"][0] == REBALANCING_N_TRIALS == 24
    assert payload["denominators"] == sorted(set(payload["denominators"]))
    assert payload["verdict"] == "definite_negative", (
        "if this family were ever NOT definite_negative, the ladder move would "
        "have to be re-applied to it rather than left historical"
    )
    assert payload["validated_edge_bar"] == rp.VALIDATED_EDGE_BAR
    assert len(payload["results_by_cost_arm"][BASELINE_COST_ARM]) == REBALANCING_N_TRIALS
    # The verdict recorded in the artifact must be the one the rule produces
    # from the artifact's own numbers.
    from app.services.research_lab.registration_scorecard import policy_d_verdict

    baseline = payload["results_by_cost_arm"][BASELINE_COST_ARM]
    best = max(baseline, key=lambda r: (r["dsr_by_n"]["24"] if r["dsr_by_n"]["24"] is not None else -1.0))
    assert payload["best_spec"] == best["spec_id"]
    assert payload["verdict"] == policy_d_verdict(
        dsr_by_n={int(k): v for k, v in best["dsr_by_n"].items()},
        threshold=rp.VALIDATED_EDGE_BAR,
        n_local=24,
    )
