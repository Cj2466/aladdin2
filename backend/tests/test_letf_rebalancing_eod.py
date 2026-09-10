"""Synthetic known-answer validation for letf_rebalancing_eod.

Nothing in this file trusts a formula on sight. The section 4.1 regression is
validated by generating a panel in which the true b is CHOSEN and checking it is
recovered; the verdict logic is validated on series whose Sharpe is constructed;
the tie convention, the |r| cut, the C2 permutation's reproducibility and the
session-usability rules are each checked against a case whose answer was written
down before the code ran. That is the standard CLAUDE.md section 4 sets for any
formula this project did not itself derive.

The panel builder is exercised through fully synthetic minute bars and a
synthetic AUM frame, so every input is known exactly.
"""

from __future__ import annotations

from datetime import time as dt_time

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.letf_rebalancing_eod import (
    ABS_RETURN_CUT,
    CROSSINGS_PER_TRADED_DAY,
    MECHANISM_GATE_MIN_T,
    MIN_LAST_BAR_START,
    MIN_SESSION_BARS,
    PRE_REGISTERED_N_LOCAL,
    PRIMARY_WINDOW,
    SHUFFLE_SEED,
    TRAILING_SESSIONS,
    UNDERLYINGS,
    LetfRebalancingError,
    LetfSpec,
    LetfSummary,
    build_coefficients,
    build_family,
    build_panel,
    build_positions,
    cost_arm,
    power_inputs,
    regression_4_1,
    replay_spec,
    screen_letf_rebalancing,
    shuffled_coefficient,
    spec_returns,
    usable_sessions,
)

TZ = "America/New_York"
FULL_SESSION_MINUTES = 390

# Four ProShares funds on one underlying, the pre-registered leverage levels.
FUND_MAP = {
    "SSO": ("SPY", 2.0),
    "SDS": ("SPY", -2.0),
    "UPRO": ("SPY", 3.0),
    "SPXU": ("SPY", -3.0),
    "QLD": ("QQQ", 2.0),
    "QID": ("QQQ", -2.0),
    "TQQQ": ("QQQ", 3.0),
    "SQQQ": ("QQQ", -3.0),
    "UWM": ("IWM", 2.0),
    "TWM": ("IWM", -2.0),
    "URTY": ("IWM", 3.0),
    "SRTY": ("IWM", -3.0),
}


# ---------------------------------------------------------------------------
# synthetic bars
# ---------------------------------------------------------------------------


def _session_minutes(day: pd.Timestamp, n: int = FULL_SESSION_MINUTES) -> pd.DatetimeIndex:
    start = pd.Timestamp(f"{day:%Y-%m-%d} 09:30", tz=TZ)
    return pd.DatetimeIndex([start + pd.Timedelta(minutes=i) for i in range(n)])


def synthetic_bars(
    dates: list[pd.Timestamp],
    *,
    r_to_window: list[float],
    y_window: list[float],
    start_price: float = 100.0,
    minutes_by_day: dict[int, int] | None = None,
    volume: float = 1_000_000.0,
) -> pd.DataFrame:
    """Bars whose r_open->15:30 and y are EXACTLY the requested values.

    Every bar before the 15:30 bar closes at the previous session's close, the
    bar starting at 15:30 OPENS at prev_close*(1+r) and every bar from 15:30 on
    closes at prev_close*(1+r)*(1+y). So:
        r_open->1530 = requested r_to_window   exactly
        y_1530       = requested y_window      exactly
    Day 0 is a warm-up with no predecessor."""
    rows: list[pd.DataFrame] = []
    prev_close = start_price
    for i, day in enumerate(dates):
        n = (minutes_by_day or {}).get(i, FULL_SESSION_MINUTES)
        index = _session_minutes(day, n)
        r = r_to_window[i] if i < len(r_to_window) else 0.0
        y = y_window[i] if i < len(y_window) else 0.0
        window_open = prev_close * (1.0 + r)
        session_close = window_open * (1.0 + y)
        opens, closes = [], []
        for stamp in index:
            if stamp.time() < PRIMARY_WINDOW:
                opens.append(prev_close)
                closes.append(prev_close)
            elif stamp.time() == PRIMARY_WINDOW:
                opens.append(window_open)
                closes.append(session_close)
            else:
                opens.append(session_close)
                closes.append(session_close)
        rows.append(
            pd.DataFrame(
                {
                    "open": opens,
                    "high": closes,
                    "low": closes,
                    "close": closes,
                    "volume": np.full(len(index), volume),
                },
                index=index,
            )
        )
        prev_close = session_close
    return pd.concat(rows)


def synthetic_aum(dates: list[pd.Timestamp], *, level: float = 1e9) -> pd.DataFrame:
    """One AUM row per fund per session date, at a constant level."""
    rows = []
    for ticker in FUND_MAP:
        for day in dates:
            rows.append({"Date": pd.Timestamp(day), "Ticker": ticker, "aum": level})
    return pd.DataFrame(rows)


def _business_days(n: int, start: str = "2020-01-06") -> list[pd.Timestamp]:
    return list(pd.bdate_range(start, periods=n))


def _panel_from(
    r_by_day: list[float], y_by_day: list[float], *, n_days: int | None = None
) -> pd.DataFrame:
    n = n_days or len(r_by_day)
    dates = _business_days(n)
    bars = {
        ticker: synthetic_bars(dates, r_to_window=r_by_day, y_window=y_by_day)
        for ticker in UNDERLYINGS
    }
    panel, _ = build_panel(bars, synthetic_aum(dates), FUND_MAP)
    return panel


# ---------------------------------------------------------------------------
# the grid itself
# ---------------------------------------------------------------------------


def test_grid_is_exactly_the_pre_registered_twenty_specs():
    specs = build_family()
    assert len(specs) == PRE_REGISTERED_N_LOCAL == 20
    ids = [s.spec_id for s in specs]
    assert len(set(ids)) == 20
    # 17 trading specs + 3 controls (PREREGISTRATION section 3).
    assert sum(1 for s in specs if s.is_control) == 3
    assert sum(1 for s in specs if s.kind == "A") == 6
    assert sum(1 for s in specs if s.kind == "B") == 6
    assert sum(1 for s in specs if s.kind == "P") == 2
    assert sum(1 for s in specs if s.kind == "R") == 3
    assert {s.spec_id for s in specs if s.is_control} == {
        "C1_constant_aum_P_1530",
        "C2_shuffled_aum_P_1530",
        "C3_wrong_window_P_1000",
    }


def test_every_spec_carries_a_citation_and_a_hypothesis():
    for spec in build_family():
        assert spec.citation.strip()
        assert len(spec.hypothesis) > 60


# ---------------------------------------------------------------------------
# the panel's own arithmetic
# ---------------------------------------------------------------------------


def test_panel_recovers_the_constructed_r_and_y_exactly():
    n = 40
    rng = np.random.default_rng(7)
    r = list(rng.normal(0.0, 0.01, n))
    y = list(rng.normal(0.0, 0.004, n))
    panel = _panel_from(r, y)
    spy = panel[panel["underlying"] == "SPY"].sort_values("date")
    # Day 0 is the warm-up and days 1..TRAILING_SESSIONS-1 lack a full trailing
    # window, so the panel starts at index TRAILING_SESSIONS.
    offset = TRAILING_SESSIONS
    np.testing.assert_allclose(spy["r_1530"].to_numpy(), r[offset:], rtol=0, atol=1e-12)
    np.testing.assert_allclose(spy["y_1530"].to_numpy(), y[offset:], rtol=0, atol=1e-12)


def test_coefficient_is_the_previous_dates_aum_never_todays():
    """The whole point-in-time contract in one test: K_{u,t} must be built from
    the AUM row dated STRICTLY BEFORE t."""
    dates = _business_days(5)
    rows = []
    for i, day in enumerate(dates):
        for ticker in FUND_MAP:
            rows.append({"Date": day, "Ticker": ticker, "aum": float(i + 1)})
    aum = pd.DataFrame(rows)
    coefficients = build_coefficients(aum, pd.DatetimeIndex(dates), FUND_MAP)
    # sum of L^2-L over one underlying's four funds = 2 + 6 + 6 + 12 = 26.
    weight_sum = 26.0
    values = coefficients.coefficient["SPY"].to_numpy()
    assert np.isnan(values[0])  # no row dated before the first session
    for i in range(1, len(dates)):
        # A_{t-1} on session i is the row dated dates[i-1], whose value is i.
        assert values[i] == pytest.approx(float(i) * weight_sum)
        assert coefficients.as_of_date["SPY"].iloc[i] == dates[i - 1]


def test_coefficient_refuses_a_fund_whose_leverage_cannot_rebalance():
    dates = _business_days(3)
    aum = pd.DataFrame(
        [{"Date": d, "Ticker": "XXXX", "aum": 1e9} for d in dates]
    )
    # L = 1 gives L^2 - L = 0: an unleveraged fund never rebalances, so it must
    # not be able to enter K silently as a zero.
    with pytest.raises(LetfRebalancingError, match="forbids"):
        build_coefficients(aum, pd.DatetimeIndex(dates), {"XXXX": ("SPY", 1.0)})


# ---------------------------------------------------------------------------
# session usability (PREREGISTRATION section 2, copied from intraday_momentum)
# ---------------------------------------------------------------------------


def test_u3_drops_a_session_with_too_few_bars():
    dates = _business_days(6)
    bars = synthetic_bars(
        dates,
        r_to_window=[0.01] * 6,
        y_window=[0.001] * 6,
        minutes_by_day={3: MIN_SESSION_BARS - 1},
    )
    _, drops = usable_sessions(bars)
    assert drops["too_few_bars"] == [dates[3].strftime("%Y-%m-%d")]
    assert not drops["late_bar"] and not drops["incomplete_blocks"]


def test_u2_drops_a_session_that_does_not_run_to_the_close():
    # 375 bars ends at 15:44, before MIN_LAST_BAR_START (15:55), but is above
    # the U3 floor only if the floor is lowered -- so use a count that clears
    # U3 in spirit by checking the rule ordering: U3 fires first at 375.
    assert MIN_SESSION_BARS == 380
    assert MIN_LAST_BAR_START == dt_time(15, 55)
    dates = _business_days(6)
    bars = synthetic_bars(
        dates, r_to_window=[0.01] * 6, y_window=[0.001] * 6, minutes_by_day={2: 385}
    )
    _, drops = usable_sessions(bars)
    # 385 bars from 09:30 ends at a 15:54 start: past U3, caught by U2.
    assert drops["late_bar"] == [dates[2].strftime("%Y-%m-%d")]
    assert not drops["too_few_bars"]


def test_panel_is_balanced_across_the_three_underlyings():
    dates = _business_days(30)
    r, y = [0.01] * 30, [0.001] * 30
    bars = {t: synthetic_bars(dates, r_to_window=r, y_window=y) for t in UNDERLYINGS}
    # Break one session for IWM only; it must vanish from ALL THREE.
    bars["IWM"] = synthetic_bars(
        dates, r_to_window=r, y_window=y, minutes_by_day={25: MIN_SESSION_BARS - 1}
    )
    panel, audit = build_panel(bars, synthetic_aum(dates), FUND_MAP)
    broken = dates[25].normalize()
    assert broken not in set(panel["date"])
    assert audit.dropped_not_common_to_all == [broken.strftime("%Y-%m-%d")]
    counts = panel.groupby("date")["underlying"].nunique()
    assert set(counts.unique()) == {3}


# ---------------------------------------------------------------------------
# positions: the tie convention and the |r| cut
# ---------------------------------------------------------------------------


def _single_spec(kind: str, spec_id: str) -> LetfSpec:
    return next(s for s in build_family() if s.kind == kind and s.spec_id == spec_id)


def test_tie_convention_is_short_not_flat():
    """PREREGISTRATION section 3: 'long y if x > 0, short if x <= 0 (tie =
    short, as GHLZ Eq. 4)'. A session with r exactly 0 must be SHORT."""
    n = 30
    r = [0.01] * n
    r[27] = 0.0
    panel = _panel_from(r, [0.002] * n)
    positions = build_positions(panel, _single_spec("A", "A_SPY_1530"))
    tie_date = panel["date"].unique()[27 - TRAILING_SESSIONS]
    assert positions.loc[tie_date, "SPY"] == -1.0
    assert (positions.drop(index=tie_date)["SPY"] == 1.0).all()


def test_b_spec_is_flat_strictly_below_the_cut_and_on_at_the_cut():
    """PREREGISTRATION section 3: spec B is 'flat when |r_open->w| < 0.50%', so
    the boundary itself TRADES. r is overwritten directly on the panel rather
    than steered through the synthetic prices, because a price ratio cannot
    represent 0.0050 exactly and the point of this test is the comparison
    operator, not floating-point price arithmetic."""
    n = 30
    panel = _panel_from([0.01] * n, [0.002] * n)
    dates = list(panel["date"].unique())
    spy = (panel["underlying"] == "SPY").to_numpy()
    for offset, value in ((-3, ABS_RETURN_CUT - 1e-9), (-2, ABS_RETURN_CUT), (-1, -ABS_RETURN_CUT)):
        mask = spy & (panel["date"] == dates[offset]).to_numpy()
        panel.loc[mask, "r_1530"] = value
        panel.loc[mask, "x_1530"] = (
            panel.loc[mask, "K"] * value / panel.loc[mask, "adv20"]
        )
    positions = build_positions(panel, _single_spec("B", "B_SPY_1530"))
    assert positions.loc[dates[-3], "SPY"] == 0.0  # strictly below -> FLAT
    assert positions.loc[dates[-2], "SPY"] == 1.0  # exactly at the cut -> LONG
    assert positions.loc[dates[-1], "SPY"] == -1.0  # at the cut, negative -> SHORT
    assert ABS_RETURN_CUT == 0.0050


def test_a_spec_earns_the_constructed_magnitude_minus_the_cost():
    """The known answer: y always moves WITH r by exactly 25 bp, so the A rule
    earns +25 bp gross every day and 25 bp minus two crossings net."""
    n = 40
    rng = np.random.default_rng(3)
    r = list(rng.choice([0.01, -0.01], n))
    magnitude = 0.0025
    y = [magnitude if x > 0 else -magnitude for x in r]
    panel = _panel_from(r, y)
    arm = cost_arm("verdict")
    net, gross, notional = spec_returns(panel, _single_spec("A", "A_SPY_1530"), arm.one_way_bps)
    np.testing.assert_allclose(gross.to_numpy(), magnitude, rtol=0, atol=1e-12)
    expected_cost = CROSSINGS_PER_TRADED_DAY * arm.one_way_bps / 1e4
    np.testing.assert_allclose(net.to_numpy(), magnitude - expected_cost, rtol=0, atol=1e-12)
    np.testing.assert_allclose(notional.to_numpy(), 1.0, rtol=0, atol=1e-12)


# ---------------------------------------------------------------------------
# ADDENDUM_01's algebraic claim, checked numerically
# ---------------------------------------------------------------------------


def test_c1_and_c2_are_exactly_the_pooled_spec_and_c3_is_not():
    """ADDENDUM_01 section 1: K > 0 and ADV > 0 make sign(x) == sign(r)
    identically, so rescaling or permuting K cannot change a single position."""
    n = 60
    rng = np.random.default_rng(11)
    r = list(rng.normal(0.0, 0.008, n))
    y = list(rng.normal(0.0, 0.003, n))
    panel = _panel_from(r, y)
    specs = {s.spec_id: s for s in build_family()}
    base, _, _ = spec_returns(panel, specs["P_1530"], 1.0)
    for control in ("C1_constant_aum_P_1530", "C2_shuffled_aum_P_1530"):
        other, _, _ = spec_returns(panel, specs[control], 1.0)
        np.testing.assert_allclose(other.to_numpy(), base.to_numpy(), rtol=0, atol=0.0)
    c3, _, _ = spec_returns(panel, specs["C3_wrong_window_P_1000"], 1.0)
    # C3 changes the window, not the coefficient, so it is a real control.
    assert not np.allclose(c3.to_numpy(), base.to_numpy(), rtol=0, atol=1e-12)


def test_c2_permutation_is_reproducible_with_the_pre_registered_seed():
    n = 40
    panel = _panel_from(list(np.linspace(-0.02, 0.02, n)), [0.001] * n)
    first = shuffled_coefficient(panel, SHUFFLE_SEED)
    second = shuffled_coefficient(panel, SHUFFLE_SEED)
    pd.testing.assert_frame_equal(first, second)
    assert SHUFFLE_SEED == 12345
    # It really is a permutation: same multiset, per underlying.
    original = panel.pivot(index="date", columns="underlying", values="K")
    for underlying in UNDERLYINGS:
        np.testing.assert_allclose(
            np.sort(first[underlying].to_numpy()),
            np.sort(original[underlying].to_numpy()),
            rtol=0,
            atol=1e-9,
        )


# ---------------------------------------------------------------------------
# section 4.1: recover a KNOWN b
# ---------------------------------------------------------------------------


def test_regression_4_1_recovers_a_known_beta():
    """Generate y = beta * (x*100) + noise on a real panel's own x, then check
    the estimator returns beta. The panel is built first so x carries the real
    construction (K from AUM, ADV from volume); only y is replaced."""
    n = 400
    rng = np.random.default_rng(23)
    r = list(rng.normal(0.0, 0.01, n))
    panel = _panel_from(r, list(rng.normal(0.0, 0.003, n)))
    true_beta = 0.75
    sigma = panel["sigma20"].to_numpy()
    noise = rng.normal(0.0, 0.05, len(panel))
    # y/sigma = beta * (x*100) + noise, with NO loading on the control, so the
    # estimator must return beta for `flow` and about zero for the control.
    panel = panel.copy()
    panel["y_1530"] = (true_beta * panel["x_1530"].to_numpy() * 100.0 + noise) * sigma
    fit = regression_4_1(panel, PRIMARY_WINDOW)
    assert fit.b == pytest.approx(true_beta, abs=0.02)
    assert abs(fit.c) < 0.05
    assert fit.n_clusters == panel["date"].nunique()
    assert fit.n_observations == len(panel.dropna(subset=["x_1530", "y_1530", "sigma20"]))
    assert fit.passes_gate() is True


def test_regression_4_1_gate_fails_on_a_zero_and_on_a_negative_effect():
    n = 400
    rng = np.random.default_rng(29)
    panel = _panel_from(list(rng.normal(0.0, 0.01, n)), list(rng.normal(0.0, 0.003, n)))
    sigma = panel["sigma20"].to_numpy()
    for true_beta in (0.0, -0.75):
        shaped = panel.copy()
        shaped["y_1530"] = (
            true_beta * shaped["x_1530"].to_numpy() * 100.0 + rng.normal(0.0, 0.05, len(shaped))
        ) * sigma
        fit = regression_4_1(shaped, PRIMARY_WINDOW)
        assert fit.passes_gate() is False
    assert MECHANISM_GATE_MIN_T == 2.0


# ---------------------------------------------------------------------------
# the power block reads nothing but sigma(y) and |r|
# ---------------------------------------------------------------------------


def test_power_inputs_translate_the_tuzun_claim_linearly():
    n = 60
    r = [0.01] * n  # |r| is exactly 1% every session
    panel = _panel_from(r, list(np.random.default_rng(5).normal(0.0, 0.003, n)))
    inputs = power_inputs(panel, PRIMARY_WINDOW)
    assert inputs.mean_abs_r == pytest.approx(0.01)
    # 6.9 bp per 1% of |r|, and |r| is exactly 1%, so E[gross] is exactly 6.9bp.
    assert inputs.expected_gross_daily_return_full == pytest.approx(6.9e-4)
    assert inputs.expected_gross_daily_return_half == pytest.approx(3.45e-4)
    assert inputs.round_trip_cost == pytest.approx(2e-4)
    # ADDENDUM_01 section 4's declared sigma_SR.
    assert inputs.sigma_sr_annualized == pytest.approx(
        float(np.sqrt(inputs.periods_per_year / inputs.n_observations))
    )


# ---------------------------------------------------------------------------
# the verdict logic on series of KNOWN Sharpe
# ---------------------------------------------------------------------------


def _summary_with(sharpes: dict[str, float], *, gate_passes: bool) -> LetfSummary:
    """A LetfSummary whose spec Sharpes are exactly `sharpes`, for testing the
    verdict branches without going through a replay."""
    from app.services.research_lab.letf_rebalancing_eod import MechanismRegression

    def _regression(b: float, t: float) -> MechanismRegression:
        return MechanismRegression(
            label="test",
            window="1530",
            n_observations=1000,
            n_clusters=100,
            b=b,
            b_t=t,
            b_se=abs(b / t) if t else 1.0,
            c=0.0,
            c_t=0.0,
            a=0.0,
            r_squared_pct=0.0,
            tuzun_reference=None,
            is_placebo=False,
        )

    from app.services.research_lab.letf_rebalancing_eod import LetfResult

    specs = {s.spec_id: s for s in build_family()}
    results = []
    for spec_id, sharpe in sharpes.items():
        spec = specs[spec_id]
        results.append(
            LetfResult(
                spec_id=spec_id,
                kind=spec.kind,
                window="1530",
                underlyings=spec.underlyings,
                is_control=spec.is_control,
                citation=spec.citation,
                hypothesis=spec.hypothesis,
                cost_arm="verdict",
                one_way_bps=1.0,
                n_trading_days=2000,
                first_day="2016-01-05",
                last_day="2026-09-09",
                sharpe_annualized=sharpe,
                gross_sharpe_annualized=sharpe,
                annualized_return=0.0,
                annualized_volatility=0.1,
                hit_rate=0.5,
                n_traded_days=2000,
                n_flat_days=0,
                total_cost_drag=0.0,
                breakeven_one_way_bps=None,
                dsr_by_n={20: 0.99 if sharpe > 1.0 else 0.10, 397: 0.96 if sharpe > 1.5 else 0.05},
                preservation={},
                deflated_sharpe=None,
            )
        )
    regression = _regression(1.0, 3.0) if gate_passes else _regression(-1.0, -3.0)
    return LetfSummary(
        audit=None,
        panel=pd.DataFrame(),
        n_local=20,
        denominators=[20, 397],
        periods_per_year=252.0,
        sigma_sr_annualized=0.2,
        results_by_arm={"verdict": results},
        mechanism=regression,
        mechanism_secondary=regression,
        mechanism_placebo=regression,
        reversal=regression,
    )


def test_verdict_is_momentum_not_letf_when_the_mechanism_gate_fails():
    """PREREGISTRATION section 4.1: if the gate fails, the verdict is written as
    'momentum, not LETF' WHATEVER the trading specs show."""
    summary = _summary_with({"P_1530": 2.0, "A_SPY_1530": 1.9}, gate_passes=False)
    verdict, rationale = summary.verdict()
    assert verdict == "momentum_not_letf"
    assert "no spec is recommended" in rationale.lower()


def test_verdict_branches_on_the_ladder_when_the_gate_passes():
    passes_all = _summary_with({"P_1530": 2.0}, gate_passes=True)
    assert passes_all.verdict()[0] == "passes_all_rungs"
    unresolved = _summary_with({"P_1530": 1.2}, gate_passes=True)
    assert unresolved.verdict()[0] == "unresolved"
    fails = _summary_with({"P_1530": 0.2}, gate_passes=True)
    assert fails.verdict()[0] == "fails_at_n_local"


def test_verdict_ignores_controls_when_choosing_the_best_candidate():
    summary = _summary_with(
        {"P_1530": 0.2, "C3_wrong_window_P_1000": 9.9}, gate_passes=True
    )
    assert summary.best_candidate().spec_id == "P_1530"
    assert summary.best_control().spec_id == "C3_wrong_window_P_1000"
    assert summary.verdict()[0] == "fails_at_n_local"


# ---------------------------------------------------------------------------
# the screen wires preservation and DSR onto every spec, controls included
# ---------------------------------------------------------------------------


def test_screen_scores_every_spec_including_controls():
    n = 120
    rng = np.random.default_rng(41)
    panel = _panel_from(list(rng.normal(0.0, 0.008, n)), list(rng.normal(0.0, 0.003, n)))
    results = screen_letf_rebalancing(panel, build_family(), cost_arm_key="verdict")
    assert len(results) == PRE_REGISTERED_N_LOCAL
    for result in results:
        # preservation_score with NO EXCEPTIONS (CLAUDE.md section 4).
        assert "preservation_score" in result.preservation
        assert result.dsr_by_n
        assert result.n_trading_days > 0


def test_a_negative_cost_is_refused_rather_than_clamped():
    n = 30
    panel = _panel_from([0.01] * n, [0.002] * n)
    with pytest.raises(LetfRebalancingError, match="non-negative"):
        replay_spec(panel, _single_spec("A", "A_SPY_1530"), -1.0)


def test_sigma20_is_the_std_of_the_trailing_closes_returns_with_no_duplicate():
    """Orchestrator correction 2026-09-11 (DEVIATIONS_FROM_SOURCE D4): sigma20 must
    be the ddof=1 standard deviation of the close-to-close returns among the
    twenty trailing sessions -- nineteen returns, and never a spurious zero from
    the previous close counted against itself."""
    n = 60
    rng = np.random.default_rng(31)
    r = list(rng.normal(0.0, 0.01, n))
    y = list(rng.normal(0.0, 0.003, n))
    dates = _business_days(n)
    bars = {ticker: synthetic_bars(dates, r_to_window=r, y_window=y) for ticker in UNDERLYINGS}
    panel, _ = build_panel(bars, synthetic_aum(dates), FUND_MAP)
    spy = panel[panel["underlying"] == "SPY"].sort_values("date").reset_index(drop=True)
    closes = spy["close"].to_numpy()
    # row k's twenty trailing sessions end with row k-1; their closes are
    # closes[k-20:k] once the panel's own leading drop is accounted for. Use the
    # panel's prev_close chain instead of assuming the offset: rebuild from the
    # panel rows themselves for a row deep enough to have twenty predecessors.
    k = 30
    trailing = closes[k - 20 : k]
    expected = float(np.std(np.diff(trailing) / trailing[:-1], ddof=1))
    assert spy.loc[k, "sigma20"] == pytest.approx(expected, rel=1e-12)
    assert spy.loc[k, "prev_close"] == pytest.approx(closes[k - 1], rel=1e-12)
