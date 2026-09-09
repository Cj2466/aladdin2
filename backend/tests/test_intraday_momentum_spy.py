"""Synthetic known-answer validation for intraday_momentum_spy.

The replay is validated on bars whose answer is CONSTRUCTED and therefore known
in advance, before it is ever pointed at real data: bars where the last half-hour
always moves with the first by a fixed magnitude, so the paper's Eq. (4) rule
must earn exactly that magnitude minus the cost, every day, to the floating-point
epsilon. That is the standard this project applies to any formula it did not
write itself (CLAUDE.md section 4).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.intraday_momentum_spy import (
    CROSSINGS_PER_TRADED_DAY,
    DEADBAND,
    FULL_SESSION_MINUTES,
    IntradayMomentumError,
    IntradayMomentumSpec,
    breakeven_one_way_bps,
    build_family,
    build_half_hour_panel,
    build_positions,
    cost_arm,
    replay_spec,
    run_intraday_momentum_screening,
    screen_intraday_momentum,
)

TZ = "America/New_York"
# The constructed last-half-hour magnitude: 20 bps, moving WITH the sign of r1.
MAGNITUDE = 0.0020


def _session_minutes(day: pd.Timestamp, n: int = FULL_SESSION_MINUTES) -> pd.DatetimeIndex:
    """The first `n` regular-session bar-START minutes of `day`, 09:30 onward."""
    start = pd.Timestamp(f"{day:%Y-%m-%d} 09:30", tz=TZ)
    return pd.DatetimeIndex([start + pd.Timedelta(minutes=i) for i in range(n)])


def synthetic_bars(
    r1_by_day: list[float],
    *,
    magnitude: float = MAGNITUDE,
    start_date: str = "2020-01-06",
    minutes_by_day: list[int] | None = None,
) -> pd.DataFrame:
    """Bars with a KNOWN answer.

    Within each session every bar in blocks 1..12 closes at p1 and every bar in
    block 13 closes at p13, so:
        r1  = p1 / (previous session's p13) - 1 = the requested value
        r2..r12 = 0 exactly
        r13 = sign(r1) * magnitude exactly
    Hence eta(r1) = +magnitude every single day, gross.

    Day 0 is a warm-up: it has no predecessor, so the pre-registered rules drop
    it and it produces no row. Its r1 request is therefore ignored.
    """
    days = pd.bdate_range(start_date, periods=len(r1_by_day))
    minutes_by_day = minutes_by_day or [FULL_SESSION_MINUTES] * len(r1_by_day)
    frames = []
    previous_close = 100.0
    for day, r1, n_minutes in zip(days, r1_by_day, minutes_by_day, strict=True):
        index = _session_minutes(day, n_minutes)
        p1 = previous_close * (1.0 + r1)
        p13 = p1 * (1.0 + np.sign(r1) * magnitude)
        # Block 13 is bar-START times 15:30..15:59 -> minute offset 360..389.
        closes = np.where(np.arange(len(index)) >= 360, p13, p1)
        frames.append(
            pd.DataFrame(
                {
                    "open": closes,
                    "high": closes,
                    "low": closes,
                    "close": closes,
                    "volume": np.full(len(index), 1000.0),
                },
                index=index,
            )
        )
        previous_close = p13 if n_minutes > 360 else p1
    frame = pd.concat(frames).sort_index()
    frame.index.name = "timestamp"
    return frame


ALTERNATING = [0.01, -0.01, 0.02, -0.02, 0.015, -0.015, 0.03, -0.03, 0.005, -0.005]


# ---------------------------------------------------------------------------
# bar aggregation
# ---------------------------------------------------------------------------


def test_half_hour_panel_recovers_the_constructed_returns_exactly():
    panel, audit = build_half_hour_panel(synthetic_bars(ALTERNATING))

    # Day 0 has no predecessor and is dropped; the rest survive.
    assert audit.n_sessions == len(ALTERNATING)
    assert audit.n_usable == len(ALTERNATING)
    assert audit.dropped_no_previous == ["2020-01-06"]
    assert audit.n_traded_days == len(ALTERNATING) - 1
    assert len(panel) == len(ALTERNATING) - 1

    # Eq. (1): r1 measured from the PREVIOUS day's close, r2..r12 flat, r13 the
    # constructed move.
    np.testing.assert_allclose(panel["r1"].to_numpy(), ALTERNATING[1:], atol=1e-12)
    for j in range(2, 13):
        np.testing.assert_allclose(panel[f"r{j}"].to_numpy(), 0.0, atol=1e-12)
    expected_r13 = np.sign(ALTERNATING[1:]) * MAGNITUDE
    np.testing.assert_allclose(panel["r13"].to_numpy(), expected_r13, rtol=1e-10)


def test_block_boundaries_are_09_30_and_15_30():
    """p1 is the close of the 09:59 bar (block 1 ends before 10:00) and p13 is
    the close of the 15:59 bar (block 13 starts at 15:30)."""
    bars = synthetic_bars([0.01, 0.01])
    day = bars.index[-1].normalize()
    # Move the 15:29 bar (block 12) far away; r13 must change, because p12 does.
    perturbed = bars.copy()
    perturbed.loc[pd.Timestamp(f"{day:%Y-%m-%d} 15:29", tz=TZ), "close"] *= 1.5
    panel_a, _ = build_half_hour_panel(bars)
    panel_b, _ = build_half_hour_panel(perturbed)
    assert panel_a.loc[day, "r13"] != pytest.approx(panel_b.loc[day, "r13"])

    # The 15:30 bar is the FIRST bar of block 13, not the last of block 12, so
    # perturbing it must leave r12 untouched and move only r13.
    perturbed12 = bars.copy()
    perturbed12.loc[pd.Timestamp(f"{day:%Y-%m-%d} 15:30", tz=TZ), "close"] *= 1.5
    panel_d, _ = build_half_hour_panel(perturbed12)
    assert panel_d.loc[day, "r12"] == pytest.approx(panel_a.loc[day, "r12"], abs=1e-12)
    assert panel_d.loc[day, "r13"] == pytest.approx(panel_a.loc[day, "r13"], abs=1e-12)

    # And the 09:59 bar defines p1, so perturbing it moves r1.
    perturbed2 = bars.copy()
    perturbed2.loc[pd.Timestamp(f"{day:%Y-%m-%d} 09:59", tz=TZ), "close"] *= 1.01
    panel_c, _ = build_half_hour_panel(perturbed2)
    assert panel_c.loc[day, "r1"] == pytest.approx((1 + 0.01) * 1.01 - 1, rel=1e-9)


# ---------------------------------------------------------------------------
# pre-registered usability rules
# ---------------------------------------------------------------------------


def test_u3_drops_a_session_below_the_380_bar_floor():
    minutes = [FULL_SESSION_MINUTES] * 4
    minutes[2] = 370  # an early-close-shaped session
    _, audit = build_half_hour_panel(synthetic_bars(ALTERNATING[:4], minutes_by_day=minutes))
    assert audit.dropped_too_few_bars == ["2020-01-08"]
    assert audit.n_usable == 3


def test_u2_drops_a_session_whose_last_bar_starts_before_15_55():
    """385 bars clears the U3 floor, but the session stops at 15:54 -- there is
    no complete last half-hour, so the trade is untradeable."""
    minutes = [FULL_SESSION_MINUTES] * 4
    minutes[2] = 385  # last bar-start = 09:30 + 384 min = 15:54
    _, audit = build_half_hour_panel(synthetic_bars(ALTERNATING[:4], minutes_by_day=minutes))
    assert audit.dropped_late_bar == ["2020-01-08"]
    assert audit.dropped_too_few_bars == []


def test_u1_drops_a_session_missing_a_whole_block(monkeypatch):
    """U1 is defence in depth: for a WHOLE missing 30-minute block it is
    structurally subsumed by U3 (390 - 30 = 360 < 380), so the floor is lowered
    here purely to exercise the U1 code path in isolation. The research rule
    itself is unchanged."""
    monkeypatch.setattr(
        "app.services.research_lab.intraday_momentum_spy.MIN_SESSION_BARS", 300
    )
    bars = synthetic_bars(ALTERNATING[:4])
    day = bars.index[-1].normalize()
    # Drop all of block 5 (bar-starts 11:30..11:59 -> minute offsets 120..149).
    block5 = _session_minutes(day)[120:150]
    _, audit = build_half_hour_panel(bars.drop(index=block5))
    assert audit.dropped_incomplete_blocks == [f"{day:%Y-%m-%d}"]


def test_a_gap_longer_than_five_calendar_days_drops_the_day():
    """r1 is a return since the PREVIOUS CLOSE; a long gap would silently turn it
    into a multi-day return, which is not the paper's construction."""
    first = synthetic_bars([0.01, 0.01], start_date="2020-01-06")
    later = synthetic_bars([0.01, 0.01], start_date="2020-02-03")
    panel, audit = build_half_hour_panel(pd.concat([first, later]).sort_index())
    assert "2020-02-03" in audit.dropped_no_previous
    assert "2020-01-06" in audit.dropped_no_previous
    assert len(panel) == 2


def test_empty_bars_raise():
    with pytest.raises(IntradayMomentumError):
        build_half_hour_panel(pd.DataFrame())


# ---------------------------------------------------------------------------
# THE KNOWN-ANSWER REPLAY TEST
# ---------------------------------------------------------------------------


def _spec(spec_id: str) -> IntradayMomentumSpec:
    return next(s for s in build_family() if s.spec_id == spec_id)


def test_r1_sign_rule_earns_exactly_the_constructed_magnitude_gross():
    """Eq. (4) on bars where the last half-hour always moves WITH the first: the
    rule must earn exactly MAGNITUDE every day, gross, to floating-point."""
    panel, _ = build_half_hour_panel(synthetic_bars(ALTERNATING))
    replay = replay_spec(panel, _spec("r1__sign"), one_way_bps=0.0)

    assert replay.status == "ok"
    assert len(replay.daily_returns) == len(ALTERNATING) - 1
    np.testing.assert_allclose(replay.daily_returns.to_numpy(), MAGNITUDE, rtol=1e-10)
    assert replay.n_traded_days == len(ALTERNATING) - 1
    assert replay.n_flat_days == 0
    assert replay.success_rate == pytest.approx(1.0)
    assert replay.total_cost == pytest.approx(0.0)


@pytest.mark.parametrize("one_way_bps", [0.0, 0.1381, 1.0, 5.0, 12.5859])
def test_cost_arithmetic_is_exactly_two_crossings_per_traded_day(one_way_bps):
    """A traded day pays CROSSINGS_PER_TRADED_DAY one-way crossings and a flat
    day pays zero -- the rule the pre-registration fixed, checked against the
    constructed answer at every arm this family reports plus the REJECTED EDGE
    number, so the arithmetic is verified across the whole range."""
    panel, _ = build_half_hour_panel(synthetic_bars(ALTERNATING))
    replay = replay_spec(panel, _spec("r1__sign"), one_way_bps=one_way_bps)

    expected = MAGNITUDE - CROSSINGS_PER_TRADED_DAY * one_way_bps / 1e4
    np.testing.assert_allclose(replay.daily_returns.to_numpy(), expected, rtol=1e-9)
    np.testing.assert_allclose(replay.gross_returns.to_numpy(), MAGNITUDE, rtol=1e-10)
    assert replay.total_cost == pytest.approx(
        len(ALTERNATING[1:]) * CROSSINGS_PER_TRADED_DAY * one_way_bps / 1e4
    )


def test_negative_cost_is_rejected():
    panel, _ = build_half_hour_panel(synthetic_bars(ALTERNATING))
    with pytest.raises(IntradayMomentumError):
        replay_spec(panel, _spec("r1__sign"), one_way_bps=-1.0)


def test_the_tie_convention_is_short_not_flat():
    """Eq. (4) says r <= 0 is SHORT, never flat. r2 and r12 are exactly 0 in the
    synthetic bars, so both must go SHORT every day -- and therefore earn -r13,
    which is -sign(r1)*MAGNITUDE and so alternates with r1 rather than being a
    constant. That is the whole point: a rule keyed to a signal carrying no
    information about r13 earns the coin flip, not the constructed edge."""
    panel, _ = build_half_hour_panel(synthetic_bars(ALTERNATING))
    expected = -np.sign(ALTERNATING[1:]) * MAGNITUDE
    for spec_id in ("r12__sign", "placebo_r2__sign"):
        replay = replay_spec(panel, _spec(spec_id), one_way_bps=0.0)
        assert set(replay.positions.unique()) == {-1.0}
        np.testing.assert_allclose(replay.daily_returns.to_numpy(), expected, rtol=1e-10)
        # It tracks the coin flip exactly, and nothing else: every observation
        # is +/-MAGNITUDE, and its sign is the OPPOSITE of the day's r1 sign.
        assert set(np.sign(replay.daily_returns.to_numpy())) == {-1.0, 1.0}


def test_deadband_goes_flat_below_the_threshold_and_costs_nothing_there():
    """|r1| = 5bp is inside the 10bp dead-band -> flat, zero return, zero cost.
    |r1| = 200bp is outside it -> identical to the sign rule."""
    inside, outside = 0.0005, 0.02
    assert inside < DEADBAND < outside
    panel, _ = build_half_hour_panel(synthetic_bars([0.01, outside, inside, -inside, -outside]))
    replay = replay_spec(panel, _spec("r1__deadband10bp"), one_way_bps=1.0)

    per_day_cost = CROSSINGS_PER_TRADED_DAY * 1.0 / 1e4
    np.testing.assert_allclose(
        replay.daily_returns.to_numpy(),
        [MAGNITUDE - per_day_cost, 0.0, 0.0, MAGNITUDE - per_day_cost],
        atol=1e-12,
    )
    assert replay.n_flat_days == 2
    assert replay.n_traded_days == 2
    assert replay.total_cost == pytest.approx(2 * per_day_cost)


def test_eq5_combination_stays_out_when_the_two_signals_disagree():
    """Eq. (5): trade only when r1 and r12 agree. r12 is exactly 0 in the
    synthetic bars, so a positive r1 disagrees with it and the position is flat;
    a non-positive r1 agrees (both <= 0) and the position is short."""
    panel, _ = build_half_hour_panel(synthetic_bars([0.01, 0.02, -0.02]))
    positions = build_positions(panel, _spec("r1_and_r12__sign"))
    assert list(positions) == [0.0, -1.0]
    # With the dead-band, r12 = 0 never clears it, so the spec is always flat.
    dead = build_positions(panel, _spec("r1_and_r12__deadband10bp"))
    assert list(dead) == [0.0, 0.0]


def test_no_look_ahead_positions_do_not_depend_on_r13():
    """Every quantity entering w_t is measurable by 15:30; r13 is not. Shuffling
    r13 must leave every spec's positions bit-identical."""
    panel, _ = build_half_hour_panel(synthetic_bars(ALTERNATING))
    shuffled = panel.copy()
    shuffled["r13"] = shuffled["r13"].to_numpy()[::-1]
    for spec in build_family():
        pd.testing.assert_series_equal(
            build_positions(panel, spec), build_positions(shuffled, spec)
        )


def test_breakeven_matches_hand_arithmetic():
    """Break-even = mean(gross) / (traded_fraction * crossings) * 1e4. On bars
    that pay MAGNITUDE every day with a position held every day, that is
    0.0020 / 2 * 1e4 = 10 bps one-way."""
    panel, _ = build_half_hour_panel(synthetic_bars(ALTERNATING))
    replay = replay_spec(panel, _spec("r1__sign"), one_way_bps=1.0)
    assert breakeven_one_way_bps(replay) == pytest.approx(10.0, rel=1e-9)
    # And at that cost the mean net return really is zero.
    at_breakeven = replay_spec(panel, _spec("r1__sign"), one_way_bps=10.0)
    assert at_breakeven.daily_returns.mean() == pytest.approx(0.0, abs=1e-15)


# ---------------------------------------------------------------------------
# grid, arms, screening plumbing
# ---------------------------------------------------------------------------


def test_the_grid_is_the_eight_pre_registered_specs_with_controls_counted():
    specs = build_family()
    assert [s.spec_id for s in specs] == [
        "r1__sign",
        "r1__deadband10bp",
        "r12__sign",
        "r12__deadband10bp",
        "r1_and_r12__sign",
        "r1_and_r12__deadband10bp",
        "placebo_r2__sign",
        "placebo_r2__deadband10bp",
    ]
    assert sum(s.is_control for s in specs) == 2
    assert len(specs) == 8


def test_cost_arms_are_the_four_declared_ones_with_baseline_at_one_bp():
    assert cost_arm("cost_free").one_way_bps == 0.0
    assert cost_arm("spy_tick").one_way_bps == pytest.approx(0.1381)
    assert cost_arm("baseline").one_way_bps == 1.0
    assert cost_arm("conservative").one_way_bps == 5.0
    with pytest.raises(IntradayMomentumError):
        cost_arm("whatever")


def _noisy_bars(n_days: int = 400, seed: int = 7) -> pd.DataFrame:
    """Bars with NO relationship between r1 and r13 -- a null world, so the
    screen must not produce a passing DSR on it."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2020-01-06", periods=n_days)
    frames = []
    previous_close = 100.0
    for day in days:
        index = _session_minutes(day)
        p1 = previous_close * (1.0 + rng.normal(0, 0.004))
        p13 = p1 * (1.0 + rng.normal(0, 0.002))
        closes = np.where(np.arange(len(index)) >= 360, p13, p1)
        frames.append(
            pd.DataFrame(
                {"open": closes, "high": closes, "low": closes, "close": closes,
                 "volume": np.full(len(index), 1000.0)},
                index=index,
            )
        )
        previous_close = p13
    frame = pd.concat(frames).sort_index()
    frame.index.name = "timestamp"
    return frame


def test_screening_produces_one_result_per_spec_with_the_full_ladder():
    panel, _ = build_half_hour_panel(_noisy_bars())
    results = screen_intraday_momentum(panel, build_family())
    assert len(results) == 8
    for r in results:
        assert sorted(r.dsr_by_n) == [8, 43, 397, 1131]  # ladder adopted 2026-09-09
        assert r.cost_arm == "baseline" and r.one_way_bps == 1.0
        # preservation_score is MANDATORY, no exceptions.
        assert "preservation_score" in r.preservation
        assert r.preservation["periods_per_year"] == 252.0
        # cross_sectional_persistence's contract.
        assert r.spec_id and r.n_trading_days > 0 and r.deflated_sharpe is not None
    assert results == sorted(results, key=lambda r: r.sharpe_annualized, reverse=True)


def test_a_null_world_does_not_clear_the_validated_bar():
    summary = run_intraday_momentum_screening(_noisy_bars())
    verdict, _ = summary.verdict()
    assert verdict == "fails_at_n_local"


def test_summary_reports_every_arm_and_the_placebo_override():
    summary = run_intraday_momentum_screening(_noisy_bars())
    assert set(summary.results_by_arm) == {"cost_free", "spy_tick", "baseline", "conservative"}
    assert summary.n_local == 8
    assert summary.denominators == [8, 43, 397, 1131]  # ladder adopted 2026-09-09
    best, placebo = summary.best_candidate(), summary.best_placebo()
    assert best is not None and not best.is_control
    assert placebo is not None and placebo.is_control
    assert summary.placebo_override_triggered() == (
        placebo.sharpe_annualized >= best.sharpe_annualized
    )


def test_costs_only_ever_reduce_the_sharpe_across_the_arms():
    """Monotonicity: a strictly larger one-way cost cannot raise a spec's net
    mean return. Cheap guard against a sign error in the cost path."""
    summary = run_intraday_momentum_screening(_noisy_bars())
    by_arm = {
        arm: {r.spec_id: r.annualized_return for r in results}
        for arm, results in summary.results_by_arm.items()
    }
    for spec_id in by_arm["cost_free"]:
        assert (
            by_arm["cost_free"][spec_id]
            >= by_arm["spy_tick"][spec_id]
            >= by_arm["baseline"][spec_id]
            >= by_arm["conservative"][spec_id]
        )
