"""Tests for the margin-credit family.

THE LOAD-BEARING ONE IS test_recursive_signal_ignores_the_future. [DKP16] p.16
says the out-of-sample predictors must be "computed RECURSIVELY using only the
data available up to time t to avoid look-ahead bias", and a full-sample
detrend hiding inside something labelled out-of-sample would silently
invalidate every out-of-sample number this family produces while still
returning plausible-looking output. It is paired with
test_insample_detrend_does_see_the_future, which proves that test actually has
power rather than passing vacuously.

The other formula-from-memory guards, per CLAUDE.md: the paper's own
margin-accounting worked example (p.7-8), its own two-month reporting-lag
example (June 1995 -> August 1995, p.11), and its own GDP-vintage example
(a prediction in August 1997 uses the Q1 1997 value, p.12).
"""

import csv

import numpy as np
import pandas as pd
import pytest

import app.services.research_lab.margin_credit_timing as mc
from app.services.research_lab.margin_credit_timing import (
    BASELINE_COST_ARM,
    BURN_IN_MONTHS,
    COST_ARMS,
    DEFINITION_ARMS,
    ESTIMATION_MODES,
    GDP_REALTIME_CSV,
    MARGIN_CREDIT_FAMILY,
    MARGIN_CREDIT_N_TRIALS,
    PREDICTORS,
    REPORTING_LAG_MONTHS,
    RISK_AVERSION_GAMMA,
    SPLIT_FIRST_MONTH,
    STRATEGIES,
    VARIANCE_WINDOW_MONTHS,
    WEIGHT_CLIP_HIGH,
    WEIGHT_CLIP_LOW,
    MarginCreditConfig,
    _shift_month,
    build_forecasts,
    build_margin_credit_panel,
    build_weights,
    detrend_full_sample,
    detrend_recursive,
    load_finra_margin_statistics,
    margin_credit_identity,
    run_margin_credit_backtest,
)

# --------------------------------------------------------------------------
# formula-from-memory guards: the paper's own worked examples
# --------------------------------------------------------------------------


def test_margin_credit_identity_matches_the_papers_worked_example():
    """[DKP16] Section 2.2, p.7-8. The paper prints all four situations of a
    10-share Apple position bought with a 60% margin requirement; the identity
    must reproduce every one of them, not just the interesting one."""
    # Situation 0: price 100, position 1000, debt 400, equity 600 -> credit 0
    assert margin_credit_identity(1000.0, 0.60, 400.0) == pytest.approx(0.0)
    # Situation 1: price falls to 50, position 500, debt 400 -> credit 0
    # (equity is BELOW the requirement here: a margin call, not negative credit)
    assert margin_credit_identity(500.0, 0.60, 400.0) == pytest.approx(0.0)
    # Situation 2: price rises to 250, position 2500, debt 400 -> credit 600.
    # The paper: "This excess 24% of the position value i.e. 600 is reflected
    # as margin credit."
    assert margin_credit_identity(2500.0, 0.60, 400.0) == pytest.approx(600.0)
    # Situation 3: credit withdrawn -> position 2500, debt 1000 -> credit 0
    assert margin_credit_identity(2500.0, 0.60, 1000.0) == pytest.approx(0.0)
    # Situation 4: credit reinvested -> position 3500, debt 1400 -> credit 0
    assert margin_credit_identity(3500.0, 0.60, 1400.0) == pytest.approx(0.0)


def test_reporting_lag_is_the_papers_two_months():
    """[DKP16] p.11 verbatim: "we use the June 1995 numbers for August 1995"."""
    assert REPORTING_LAG_MONTHS == 2
    assert _shift_month("1995-08", -REPORTING_LAG_MONTHS) == "1995-06"
    # and the year boundary, which is where an off-by-one hides
    assert _shift_month("1997-01", -2) == "1996-11"
    assert _shift_month("1996-12", 1) == "1997-01"


def test_panel_applies_the_reporting_lag_to_every_row():
    panel = build_margin_credit_panel()
    for signal_month, row in panel.frame.iterrows():
        assert row["data_month"] == _shift_month(signal_month, -REPORTING_LAG_MONTHS)


def test_gdp_vintage_rule_reproduces_the_papers_august_1997_example():
    """[DKP16] p.12: a prediction made in August 1997 uses "the Q1 1997 GDP
    value". The committed real-time snapshot must say exactly that, and must
    also show that a Q2 1997 figure WAS already available -- otherwise the rule
    would be reproducing the paper's answer by accident rather than by applying
    its extra lag."""
    rows = {r["signal_month_end"]: r for r in csv.DictReader(GDP_REALTIME_CSV.open())}
    august_1997 = rows["1997-08-31"]
    assert august_1997["gdp_quarter_start"] == "1997-01-01"
    assert august_1997["latest_quarter_available"] == "1997-04-01"


def test_every_realtime_vintage_is_exactly_one_quarter_behind_the_latest():
    """The extra lag must be applied uniformly, not only in the month the test
    above happens to check."""
    for row in csv.DictReader(GDP_REALTIME_CSV.open()):
        chosen = pd.Period(row["gdp_quarter_start"], freq="Q")
        latest = pd.Period(row["latest_quarter_available"], freq="Q")
        # .ordinal rather than subtracting Periods: pandas 3 returns a
        # QuarterEnd offset from Period - Period, which compares unequal to the
        # integer 1 and would make this assertion pass or fail for the wrong
        # reason.
        assert latest.ordinal - chosen.ordinal == 1


# --------------------------------------------------------------------------
# THE LOAD-BEARING PAIR: recursive estimation must not see the future
# --------------------------------------------------------------------------


def _series_with_a_poisoned_tail(n: int, cut: int) -> tuple[pd.Series, pd.Series]:
    """(clean, poisoned) where the two are identical up to `cut` and wildly
    different after it."""
    rng = np.random.default_rng(20260906)
    index = [f"{2000 + i // 12:04d}-{i % 12 + 1:02d}" for i in range(n)]
    base = np.linspace(0.01, 0.03, n) + rng.normal(0, 0.001, n)
    clean = pd.Series(base, index=index)
    poisoned = clean.copy()
    poisoned.iloc[cut + 1 :] = base[cut + 1 :] * 1000.0 - 50.0
    return clean, poisoned


def test_recursive_signal_ignores_the_future():
    """[DKP16] p.16: MC and MD "are computed recursively using only the data
    available up to time t to avoid look-ahead bias."

    Replace everything after a cut date with garbage. Every recursive value at
    or before the cut must be BIT-IDENTICAL, because none of them is allowed to
    have looked at what changed."""
    clean, poisoned = _series_with_a_poisoned_tail(240, cut=150)
    a = detrend_recursive(clean)
    b = detrend_recursive(poisoned)
    pd.testing.assert_series_equal(a.iloc[: 151], b.iloc[: 151])
    # and the test must be able to see the poison at all
    assert not np.allclose(
        a.iloc[151:].to_numpy(dtype=float), b.iloc[151:].to_numpy(dtype=float)
    )


def test_insample_detrend_does_see_the_future():
    """The negative control that gives the test above its power: the SAME
    poisoning must change the in-sample arm's values BEFORE the cut, because a
    full-sample fit genuinely does use the whole sample. If this ever passes as
    'unchanged', the poisoning is too weak and the look-ahead test above proves
    nothing."""
    clean, poisoned = _series_with_a_poisoned_tail(240, cut=150)
    a = detrend_full_sample(clean)
    b = detrend_full_sample(poisoned)
    assert not np.allclose(
        a.iloc[:151].to_numpy(dtype=float), b.iloc[:151].to_numpy(dtype=float)
    )


def test_recursive_forecast_ignores_the_future():
    """The same poisoning test one level up, on the whole forecast pipeline --
    detrend, standardize AND predictive regression -- against the real panel.

    This is the test that would catch a look-ahead reintroduced in
    build_forecasts even if detrend_recursive itself stayed correct."""
    panel = build_margin_credit_panel()
    cut = panel.frame.index[len(panel.frame) - 40]

    poisoned_frame = panel.frame.copy()
    tail = poisoned_frame.index > cut
    for column in ("mc_proxy", "mc_faithful", "debit_margin", "excess_log", "excess_simple"):
        poisoned_frame.loc[tail, column] = poisoned_frame.loc[tail, column] * -500.0
    poisoned = mc.MarginCreditPanel(frame=poisoned_frame, finra=panel.finra)

    a = build_forecasts(panel, arm="proxy", predictor="mc", mode="recursive")
    b = build_forecasts(poisoned, arm="proxy", predictor="mc", mode="recursive")
    pd.testing.assert_series_equal(a[a.index <= cut].dropna(), b[b.index <= cut].dropna())


def test_recursive_forecast_never_uses_the_return_it_is_forecasting():
    """The off-by-one that build_forecasts' docstring calls load-bearing:
    the fit at month t may use pairs (signal_j, return_{j+1}) only for
    j <= t-1. Poison ONLY the single return being forecast and require the
    forecast to be unchanged."""
    panel = build_margin_credit_panel()
    forecasts = build_forecasts(panel, arm="proxy", predictor="mc", mode="recursive")
    target = forecasts.dropna().index[5]

    poisoned_frame = panel.frame.copy()
    poisoned_frame.loc[target, "excess_log"] = -9.0
    poisoned = mc.MarginCreditPanel(frame=poisoned_frame, finra=panel.finra)
    poisoned_forecasts = build_forecasts(poisoned, arm="proxy", predictor="mc", mode="recursive")

    assert poisoned_forecasts[target] == pytest.approx(forecasts[target])


# --------------------------------------------------------------------------
# the detrend itself, against a synthetic known answer
# --------------------------------------------------------------------------


def test_detrend_recovers_a_known_trend_exactly():
    """[DKP16] p.16's regression against a genuinely known answer.

    The wave is first made EXACTLY ORTHOGONAL to [1, t] by removing its own
    projection onto them. Only then is "line + wave, detrended, equals the
    wave standardized" a true statement -- a raw sine is NOT orthogonal to a
    linear trend over a finite sample, the fit absorbs part of it into the
    slope, and asserting against the raw wave would be asserting against an
    answer that is simply wrong (it was, by up to 5.5%, before this was
    corrected)."""
    n = 200
    t = np.arange(n, dtype=float)
    design = np.column_stack([np.ones(n), t])
    raw_wave = np.sin(t / 7.0)
    coeffs, *_ = np.linalg.lstsq(design, raw_wave, rcond=None)
    wave = raw_wave - design @ coeffs  # now orthogonal to both columns

    index = [f"{2000 + i // 12:04d}-{i % 12 + 1:02d}" for i in range(n)]
    series = pd.Series(3.0 + 0.05 * t + wave, index=index)

    out = detrend_full_sample(series)
    expected = wave / np.std(wave, ddof=1)
    np.testing.assert_allclose(out.to_numpy(dtype=float), expected, atol=1e-9)
    assert out.mean() == pytest.approx(0.0, abs=1e-12)
    assert out.std(ddof=1) == pytest.approx(1.0)


def test_detrend_removes_a_pure_linear_trend_from_a_known_construction():
    """The complementary known answer: the SLOPE the regression finds must be
    the slope that was put in."""
    n = 150
    t = np.arange(n, dtype=float)
    index = [f"{2000 + i // 12:04d}-{i % 12 + 1:02d}" for i in range(n)]
    rng = np.random.default_rng(7)
    noise = rng.normal(0.0, 0.5, n)
    series = pd.Series(2.0 + 0.25 * t + noise, index=index)
    intercept, slope, _ = mc._ols_trend_residuals(series.to_numpy(dtype=float))
    assert slope == pytest.approx(0.25, abs=0.02)
    assert intercept == pytest.approx(2.0, abs=0.2)


def test_detrend_is_degenerate_on_a_pure_line_rather_than_dividing_by_zero():
    n = 60
    index = [f"{2000 + i // 12:04d}-{i % 12 + 1:02d}" for i in range(n)]
    series = pd.Series(1.0 + 0.5 * np.arange(n, dtype=float), index=index)
    assert detrend_full_sample(series).empty


# --------------------------------------------------------------------------
# the 2010-02 definitional break
# --------------------------------------------------------------------------


def test_faithful_arm_is_absent_before_the_2010_split_and_is_never_backfilled():
    """FINRA reports free credit in MARGIN accounts only from 2010-02. A
    back-filled value there would be an invention, so the column must be NaN,
    not zero and not carried back."""
    finra = load_finra_margin_statistics()
    before = finra[finra.index < SPLIT_FIRST_MONTH]
    after = finra[finra.index >= SPLIT_FIRST_MONTH]
    assert len(before) > 0 and len(after) > 0
    assert before["mc_faithful"].isna().all()
    assert after["mc_faithful"].notna().all()


def test_proxy_arm_is_the_combined_total_on_both_sides_of_the_seam():
    """Through 2010-01 the reported cash column IS the combined figure (FINRA's
    own footnote); from 2010-02 the combined figure is the sum of the two."""
    finra = load_finra_margin_statistics()
    before = finra.loc["2010-01"]
    after = finra.loc["2010-02"]
    assert before["mc_proxy"] == pytest.approx(before["free_credit_cash_reported"])
    assert after["mc_proxy"] == pytest.approx(
        after["free_credit_cash_reported"] + after["free_credit_margin_reported"]
    )
    # and it is continuous across the seam, which is the claim the family rests
    # its `proxy` arm on
    assert abs(after["mc_proxy"] / before["mc_proxy"] - 1.0) < 0.10


def test_the_as_reported_cash_column_is_NOT_continuous_across_the_seam():
    """The mirror image, pinned so nobody later 'simplifies' the proxy arm into
    reading column C straight through. The raw column drops by more than half
    at the seam -- that is the definitional split itself."""
    finra = load_finra_margin_statistics()
    before = finra.loc["2010-01", "free_credit_cash_reported"]
    after = finra.loc["2010-02", "free_credit_cash_reported"]
    assert after / before - 1.0 < -0.5


def test_faithful_arm_signals_start_after_the_split_plus_the_reporting_lag():
    panel = build_margin_credit_panel()
    ratio = mc.build_ratio_series(panel, arm="faithful", predictor="mc", mode="recursive")
    first = ratio.dropna().index[0]
    assert first == _shift_month(SPLIT_FIRST_MONTH, REPORTING_LAG_MONTHS)


# --------------------------------------------------------------------------
# grid, weights and streams
# --------------------------------------------------------------------------


def test_grid_is_exactly_the_pre_registered_24_specs():
    assert MARGIN_CREDIT_N_TRIALS == 24
    assert len(MARGIN_CREDIT_FAMILY) == 24
    assert len({s.spec_id for s in MARGIN_CREDIT_FAMILY}) == 24
    assert set(PREDICTORS) == {"mc", "md", "histmean"}
    assert set(DEFINITION_ARMS) == {"faithful", "proxy"}
    assert set(ESTIMATION_MODES) == {"insample", "recursive"}
    assert set(STRATEGIES) == {"longonly", "meanvar"}
    assert sum(s.is_control for s in MARGIN_CREDIT_FAMILY) == 8


def test_paper_constants_are_the_papers_and_are_not_searched():
    """[DKP16] Eq. (9), p.26: gamma = 3, w in [-0.5, 1.5], 10-year variance
    window. Pinned so a later 'tuning' pass has to change a test to happen."""
    assert RISK_AVERSION_GAMMA == 3.0
    assert (WEIGHT_CLIP_LOW, WEIGHT_CLIP_HIGH) == (-0.5, 1.5)
    assert VARIANCE_WINDOW_MONTHS == 120
    assert BURN_IN_MONTHS == 120


def test_longonly_weight_is_one_iff_the_forecast_is_positive():
    """[DKP16] p.28 verbatim: "The investment weight is 1 in S&P 500, when the
    prediction is positive and 0 otherwise"."""
    panel = build_margin_credit_panel()
    spec = next(
        s
        for s in MARGIN_CREDIT_FAMILY
        if s.spec_id == "mc__proxy__recursive__longonly"
    )
    forecasts = build_forecasts(panel, arm="proxy", predictor="mc", mode="recursive")
    weights = build_weights(panel, spec)
    both = pd.concat([forecasts.rename("f"), weights.rename("w")], axis=1).dropna()
    assert len(both) > 50
    assert set(both["w"].unique()) <= {0.0, 1.0}
    assert (both.loc[both["f"] > 0, "w"] == 1.0).all()
    assert (both.loc[both["f"] <= 0, "w"] == 0.0).all()


def test_meanvar_weight_respects_the_papers_clip():
    panel = build_margin_credit_panel()
    spec = next(
        s for s in MARGIN_CREDIT_FAMILY if s.spec_id == "mc__proxy__recursive__meanvar"
    )
    weights = build_weights(panel, spec).dropna()
    assert len(weights) > 50
    assert weights.min() >= WEIGHT_CLIP_LOW - 1e-12
    assert weights.max() <= WEIGHT_CLIP_HIGH + 1e-12


def test_overlay_is_exactly_the_strategy_minus_a_costless_buy_and_hold():
    """The pre-registration's section 6 definition, pinned:
        overlay = (w - 1) * excess - costs
                = strategy - benchmark
    with the SAME cost charged to both, which is what makes the overlay the
    incremental bet against holding the market."""
    panel = build_margin_credit_panel()
    spec = next(
        s for s in MARGIN_CREDIT_FAMILY if s.spec_id == "mc__proxy__recursive__longonly"
    )
    replay = run_margin_credit_backtest(panel, spec, MarginCreditConfig())
    assert replay.status == "ok"
    np.testing.assert_allclose(
        replay.overlay_returns.to_numpy(dtype=float),
        (replay.strategy_returns - replay.benchmark_returns).to_numpy(dtype=float),
        atol=1e-15,
    )


def test_costs_are_monotone_in_the_cost_arm():
    """A stricter cost arm can never produce a HIGHER net return than a looser
    one on the same weights."""
    panel = build_margin_credit_panel()
    spec = next(
        s for s in MARGIN_CREDIT_FAMILY if s.spec_id == "mc__proxy__recursive__meanvar"
    )
    by_arm = {}
    for arm in COST_ARMS:
        replay = run_margin_credit_backtest(
            panel,
            spec,
            MarginCreditConfig(
                cost_bps=arm.cost_bps, short_borrow_bps_per_year=arm.short_borrow_bps_per_year
            ),
        )
        by_arm[arm.key] = replay.strategy_returns.sum()
    assert by_arm["cost_free"] >= by_arm["baseline"] >= by_arm["stress"]


def test_backtest_never_lets_a_return_reach_the_weight_that_earned_it():
    """The timing contract, checked structurally rather than by inspection: the
    panel row for month t must carry the return for month t+1, so poisoning
    month t+1's return cannot change the weight held at t."""
    panel = build_margin_credit_panel()
    spec = next(
        s for s in MARGIN_CREDIT_FAMILY if s.spec_id == "mc__proxy__recursive__longonly"
    )
    weights = build_weights(panel, spec)
    target = weights.dropna().index[10]

    poisoned_frame = panel.frame.copy()
    poisoned_frame.loc[target, "excess_simple"] = -0.99
    poisoned = mc.MarginCreditPanel(frame=poisoned_frame, finra=panel.finra)
    assert build_weights(poisoned, spec)[target] == pytest.approx(weights[target])


# --------------------------------------------------------------------------
# screening wiring
# --------------------------------------------------------------------------


def test_screen_reports_dsr_at_every_pre_registered_denominator_and_scores_preservation():
    """CLAUDE.md requires DSR across multiple N and preservation_score with no
    exceptions; this pins both onto every screened spec rather than trusting
    the runner to remember."""
    summary = mc.run_margin_credit_screening()
    assert summary.denominators == mc.policy_d_denominators()
    assert len(summary.denominators) >= 2
    results = summary.results_by_cost_arm[BASELINE_COST_ARM]
    assert len(results) >= 20
    for r in results:
        assert set(r.dsr_by_n) == set(summary.denominators)
        assert r.preservation["preservation_score"] is not None
        assert r.preservation["periods_per_year"] == mc.MONTHS_PER_YEAR
        # the verdict fields describe the OVERLAY, not the strategy: the
        # observation count preservation_score saw must be the overlay's own.
        assert r.n_trading_days == r.preservation["n_observations"]


def test_verdict_is_two_tier_policy_d_on_the_overlay():
    summary = mc.run_margin_credit_screening()
    verdict, spec_id = summary.verdict()
    assert verdict in {"definite_negative", "unresolved", "pass"}
    assert spec_id is not None
