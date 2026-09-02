"""Tests for the residual (idiosyncratic) momentum family
(cross_sectional_residual_momentum.py).

Mirrors test_cross_sectional_asset_growth.py's structure: family-shape
assertions against the pre-declared grid, hand-computed formula checks against
an independent per-ticker OLS, the two degeneracy traps that are load-bearing
for THIS signal specifically (an all-zero score when the scoring window equals
the estimation window, and a control arm that would otherwise get a timing
advantage over the arms it benchmarks), both signals' direction and refusal
contracts, the pre-declared median (not mean) industry centering, the
publication-lag point-in-time contract, and harness integration including
structural look-ahead impossibility.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalScreeningResult,
    CrossSectionalSpec,
    fixed_universe_membership,
    run_cross_sectional_backtest,
)
from app.services.research_lab.cross_sectional_quality import (
    QUALITY_RANK_FRACTION,
    build_point_in_time_factor_frame,
)
from app.services.research_lab.cross_sectional_quality_neutral import MIN_BUCKET_SIZE
from app.services.research_lab.cross_sectional_residual_momentum import (
    FF3_PUBLICATION_LAG_DAYS,
    RESIDUAL_MOM_ARMS,
    RESIDUAL_MOM_CONDITIONINGS,
    RESIDUAL_MOM_FAMILY,
    RESIDUAL_MOM_FORMATION_MONTHS,
    RESIDUAL_MOM_HOLDING_DAYS,
    RESIDUAL_MOM_MAX_STALENESS_DAYS,
    RESIDUAL_MOM_N_TRIALS,
    RESIDUAL_MOM_REGRESSION_MONTHS,
    _control_scores_for_window,
    _median_signal_age,
    align_factors_to_months,
    build_residual_momentum_family,
    build_residual_momentum_observations,
    compute_residual_momentum_scores,
    monthly_returns_from_daily_close,
    repool_deflated_sharpe,
    residual_scores_for_window,
    signal_residual_momentum,
    signal_residual_momentum_industry_neutral,
    specs_for_arm,
)
from app.services.research_lab.deflated_sharpe import (
    DeflatedSharpeResult,
    expected_max_sharpe_under_noise,
    probabilistic_sharpe_ratio,
)


def _synthetic_window(seed: int = 7, n_tickers: int = 5, n_factors: int = 3):
    rng = np.random.default_rng(seed)
    window = RESIDUAL_MOM_REGRESSION_MONTHS
    factors = rng.normal(0.0, 0.04, (window, n_factors))
    betas = rng.normal(1.0, 0.3, (n_factors, n_tickers))
    noise = rng.normal(0.0, 0.02, (window, n_tickers))
    alpha = rng.normal(0.001, 0.002, n_tickers)
    return alpha + factors @ betas + noise, factors


# --- Eq. 8 / Eq. 9 arithmetic ------------------------------------------------


def test_scores_match_an_independent_per_ticker_ols():
    """The implementation solves ONE least-squares system for the whole
    cross-section (the design matrix is identical across tickers). This pins
    that shortcut against the obvious, slow, per-ticker computation."""
    excess, factors = _synthetic_window()
    scores = residual_scores_for_window(
        excess, factors, formation_months=RESIDUAL_MOM_FORMATION_MONTHS
    )

    design = np.column_stack([np.ones(len(excess)), factors])
    expected = []
    for j in range(excess.shape[1]):
        coefficients, *_ = np.linalg.lstsq(design, excess[:, j], rcond=None)
        residuals = excess[:, j] - design @ coefficients
        scoring = residuals[-RESIDUAL_MOM_FORMATION_MONTHS:]
        expected.append(scoring.sum() / scoring.std(ddof=1))

    assert scores == pytest.approx(np.array(expected))


def test_the_scoring_window_must_be_a_strict_subset_of_the_estimation_window():
    """THE degeneracy trap for this family. OLS residuals sum to EXACTLY zero
    over the estimation window, so a scoring window equal to it would score
    every stock at ~0 and the family would be ranking floating-point noise
    while looking perfectly healthy end to end."""
    excess, factors = _synthetic_window()

    design = np.column_stack([np.ones(len(excess)), factors])
    coefficients, *_ = np.linalg.lstsq(design, excess, rcond=None)
    residuals = excess - design @ coefficients
    # The premise: full-window sums really are zero.
    assert np.abs(residuals.sum(axis=0)).max() < 1e-12
    # The signal is non-degenerate only because 11 < 36.
    assert np.abs(residuals[-RESIDUAL_MOM_FORMATION_MONTHS:].sum(axis=0)).min() > 1e-6

    with pytest.raises(ValueError, match="strictly less than"):
        residual_scores_for_window(
            excess, factors, formation_months=RESIDUAL_MOM_REGRESSION_MONTHS
        )
    with pytest.raises(ValueError, match="strictly less than"):
        residual_scores_for_window(excess, factors, formation_months=len(excess) + 1)


def test_standard_deviation_denominator_is_the_same_sort_as_equation_nine():
    """Hanauer Eq. 9 divides by sqrt(sum of squared deviations); this module
    divides by the sample standard deviation. They differ by sqrt(n-1), which
    is a constant common to the whole cross-section BECAUSE n is fixed at
    RESIDUAL_MOM_FORMATION_MONTHS for every scored name — so the two produce
    identical rankings. That equivalence is the justification given in the
    pre-registration, so it is pinned rather than asserted in prose."""
    excess, factors = _synthetic_window()
    scores = residual_scores_for_window(
        excess, factors, formation_months=RESIDUAL_MOM_FORMATION_MONTHS
    )

    design = np.column_stack([np.ones(len(excess)), factors])
    coefficients, *_ = np.linalg.lstsq(design, excess, rcond=None)
    residuals = excess - design @ coefficients
    scoring = residuals[-RESIDUAL_MOM_FORMATION_MONTHS:]
    eq9 = scoring.sum(axis=0) / np.sqrt(((scoring - scoring.mean(axis=0)) ** 2).sum(axis=0))

    ratio = eq9 / scores
    assert ratio == pytest.approx(np.full_like(ratio, 1 / np.sqrt(RESIDUAL_MOM_FORMATION_MONTHS - 1)))
    assert list(np.argsort(eq9)) == list(np.argsort(scores))


def test_alpha_is_absorbed_by_the_fit_and_never_added_back():
    """Prunier: 'only Blitz et al. (2011) do not include it [the alpha] in
    their calculation of the residual.' Adding a constant to one stock's whole
    return history must therefore not change its score at all."""
    excess, factors = _synthetic_window()
    shifted = excess.copy()
    shifted[:, 0] += 0.05  # a large constant alpha on ticker 0 only

    base = residual_scores_for_window(
        excess, factors, formation_months=RESIDUAL_MOM_FORMATION_MONTHS
    )
    after = residual_scores_for_window(
        shifted, factors, formation_months=RESIDUAL_MOM_FORMATION_MONTHS
    )
    assert after == pytest.approx(base)


def test_factor_exposure_is_removed_not_merely_reduced():
    """A stock whose entire return IS a factor exposure has no idiosyncratic
    return, so its residuals must be ~0 however large the exposure. This is the
    mechanism the whole family is testing."""
    window = RESIDUAL_MOM_REGRESSION_MONTHS
    rng = np.random.default_rng(11)
    factors = rng.normal(0.0, 0.05, (window, 1))
    pure_factor = np.column_stack([factors[:, 0] * 3.0, factors[:, 0] * -1.5])

    design = np.column_stack([np.ones(window), factors])
    coefficients, *_ = np.linalg.lstsq(design, pure_factor, rcond=None)
    residuals = pure_factor - design @ coefficients
    assert np.abs(residuals).max() < 1e-12
    # Betas are recovered, not merely shrunk.
    assert coefficients[1] == pytest.approx([3.0, -1.5])


def test_an_exactly_collinear_stock_is_refused_rather_than_scored_on_dust():
    """FOUND BY THIS TEST, NOT THEORISED, and the reason _MIN_RESIDUAL_STD
    exists. Eq. 9 is a RATIO of residual quantities, so it is scale-invariant —
    which is BHM's intent, but it has a degenerate limit. A stock that is an
    exact linear combination of the factors has residuals of floating-point
    dust (~1e-16), and dust divided by dust is an ARBITRARY O(1) score. Before
    the floor, this case produced scores of -5.22 and +5.22 — numbers
    indistinguishable from a strong genuine signal."""
    window = RESIDUAL_MOM_REGRESSION_MONTHS
    rng = np.random.default_rng(11)
    factors = rng.normal(0.0, 0.05, (window, 1))
    pure_factor = np.column_stack([factors[:, 0] * 3.0, factors[:, 0] * -1.5])
    scores = residual_scores_for_window(
        pure_factor, factors, formation_months=RESIDUAL_MOM_FORMATION_MONTHS
    )
    assert np.isnan(scores).all()


def test_the_floor_does_not_refuse_an_ordinary_low_volatility_stock():
    """The degeneracy floor must catch exact collinearity WITHOUT quietly
    dropping genuinely quiet names — the scale-invariance of Eq. 9 is a
    feature, and a floor set too high would silently delete half the
    cross-section."""
    window = RESIDUAL_MOM_REGRESSION_MONTHS
    rng = np.random.default_rng(23)
    factors = rng.normal(0.0, 0.05, (window, 1))
    # A residual volatility of 1 basis point per month is implausibly quiet for
    # a real equity, and must still be scored.
    quiet = factors[:, 0:1] * 1.2 + rng.normal(0.0, 0.0001, (window, 1))
    scores = residual_scores_for_window(
        quiet, factors, formation_months=RESIDUAL_MOM_FORMATION_MONTHS
    )
    assert np.isfinite(scores).all()


def test_the_score_is_scale_invariant_in_the_idiosyncratic_component():
    """Eq. 9's whole purpose: doubling a stock's idiosyncratic volatility
    without changing its SHAPE must not change its rank."""
    window = RESIDUAL_MOM_REGRESSION_MONTHS
    rng = np.random.default_rng(29)
    factors = rng.normal(0.0, 0.04, (window, 1))
    idiosyncratic = rng.normal(0.0, 0.02, (window, 2))
    base = factors @ np.array([[1.0, 0.5]]) + idiosyncratic
    scaled = factors @ np.array([[1.0, 0.5]]) + idiosyncratic * 4.0

    a = residual_scores_for_window(base, factors, formation_months=RESIDUAL_MOM_FORMATION_MONTHS)
    b = residual_scores_for_window(scaled, factors, formation_months=RESIDUAL_MOM_FORMATION_MONTHS)
    assert a == pytest.approx(b)


def test_a_recent_idiosyncratic_run_scores_high_but_a_constant_drift_does_not():
    """The economic content of "alpha is not added back", stated as a
    consequence rather than a formula. A stock that simply drifts up every
    month for three years has that drift absorbed entirely by the intercept and
    scores ~0. Only a run concentrated in the SCORING window scores high. This
    is exactly why a naive end-to-end fixture that plants a constant drift
    finds nothing."""
    window = RESIDUAL_MOM_REGRESSION_MONTHS
    rng = np.random.default_rng(31)
    factors = rng.normal(0.0, 0.04, (window, 1))
    noise = rng.normal(0.0, 0.02, (window, 2))
    base = factors @ np.array([[1.0, 1.0]]) + noise

    constant_drift = base.copy()
    constant_drift[:, 0] += 0.03  # +3%/month for the whole 36 months

    recent_run = base.copy()
    recent_run[-RESIDUAL_MOM_FORMATION_MONTHS:, 1] += 0.03  # only the scoring window

    plain = residual_scores_for_window(
        base, factors, formation_months=RESIDUAL_MOM_FORMATION_MONTHS
    )
    drifted = residual_scores_for_window(
        constant_drift, factors, formation_months=RESIDUAL_MOM_FORMATION_MONTHS
    )
    burst = residual_scores_for_window(
        recent_run, factors, formation_months=RESIDUAL_MOM_FORMATION_MONTHS
    )

    assert drifted[0] == pytest.approx(plain[0])  # constant drift: invisible
    assert burst[1] > plain[1] + 2.0  # recent run: strongly picked up


def test_zero_factor_arm_is_the_intercept_only_regression():
    """The control travels the same code path with k = 0 columns, which must
    mean 'demean by the window mean' rather than crashing or silently
    returning the raw sum."""
    excess, _ = _synthetic_window()
    scores = residual_scores_for_window(
        excess, np.empty((len(excess), 0)), formation_months=RESIDUAL_MOM_FORMATION_MONTHS
    )
    demeaned = excess - excess.mean(axis=0)
    scoring = demeaned[-RESIDUAL_MOM_FORMATION_MONTHS:]
    assert scores == pytest.approx(scoring.sum(axis=0) / scoring.std(axis=0, ddof=1))


def test_mismatched_factor_window_length_is_refused():
    excess, factors = _synthetic_window()
    with pytest.raises(ValueError, match="rows"):
        residual_scores_for_window(
            excess, factors[:-1], formation_months=RESIDUAL_MOM_FORMATION_MONTHS
        )


def test_control_arm_is_compounded_total_return_not_an_arithmetic_sum():
    returns = np.array([[0.10, -0.10]] * RESIDUAL_MOM_FORMATION_MONTHS)
    scores = _control_scores_for_window(
        returns, formation_months=RESIDUAL_MOM_FORMATION_MONTHS
    )
    assert scores[0] == pytest.approx(1.10**RESIDUAL_MOM_FORMATION_MONTHS - 1)
    assert scores[1] == pytest.approx(0.90**RESIDUAL_MOM_FORMATION_MONTHS - 1)
    # Compounding, not summing: 11 x 10% is 1.10^11 - 1 ~= 1.85, not 1.10.
    assert scores[0] > 1.5


def test_control_arm_reads_only_the_scoring_window():
    """Months earlier than the scoring window are part of the estimation
    window for the residual arms but must not leak into the control."""
    rng = np.random.default_rng(3)
    returns = rng.normal(0.0, 0.05, (RESIDUAL_MOM_REGRESSION_MONTHS, 4))
    baseline = _control_scores_for_window(
        returns, formation_months=RESIDUAL_MOM_FORMATION_MONTHS
    )
    tampered = returns.copy()
    tampered[: RESIDUAL_MOM_REGRESSION_MONTHS - RESIDUAL_MOM_FORMATION_MONTHS] += 0.5
    assert _control_scores_for_window(
        tampered, formation_months=RESIDUAL_MOM_FORMATION_MONTHS
    ) == pytest.approx(baseline)


# --- monthly panel construction ---------------------------------------------


def test_monthly_returns_use_month_end_marks_and_refuse_to_span_gaps():
    index = pd.bdate_range("2020-01-01", "2020-04-30")
    close = pd.DataFrame({"AAA": np.arange(1.0, len(index) + 1.0)}, index=index)
    # Blank out all of March: that month has no mark, so March's return AND
    # April's return must be NaN rather than April silently spanning two months.
    close.loc["2020-03-01":"2020-03-31", "AAA"] = np.nan

    monthly = monthly_returns_from_daily_close(close)
    assert np.isnan(monthly.loc["2020-03-31", "AAA"])
    assert np.isnan(monthly.loc["2020-04-30", "AAA"])
    jan_mark = close.loc[:"2020-01-31", "AAA"].dropna().iloc[-1]
    feb_mark = close.loc["2020-02-01":"2020-02-29", "AAA"].dropna().iloc[-1]
    assert monthly.loc["2020-02-29", "AAA"] == pytest.approx(feb_mark / jan_mark - 1)


def test_align_factors_refuses_a_frame_missing_a_required_column():
    monthly = pd.DataFrame(
        {"AAA": [0.0, 0.0]}, index=pd.to_datetime(["2020-01-31", "2020-02-29"])
    )
    factors = pd.DataFrame(
        {"mkt_rf": [0.01, 0.02], "rf": [0.0, 0.0]},
        index=pd.to_datetime(["2020-01-31", "2020-02-29"]),
    )
    with pytest.raises(ValueError, match="missing required columns"):
        align_factors_to_months(monthly, factors, ("mkt_rf", "smb"))


def test_align_factors_yields_nan_outside_coverage_never_a_forward_fill():
    monthly = pd.DataFrame(
        {"AAA": [0.0, 0.0, 0.0]},
        index=pd.to_datetime(["2020-01-31", "2020-02-29", "2020-03-31"]),
    )
    factors = pd.DataFrame(
        {"mkt_rf": [0.01, 0.02], "rf": [0.0, 0.0]},
        index=pd.to_datetime(["2020-01-31", "2020-02-29"]),
    )
    aligned = align_factors_to_months(monthly, factors, ("mkt_rf",))
    assert np.isnan(aligned.loc["2020-03-31", "mkt_rf"])


def _monthly_fixture(n_months: int = 60, n_tickers: int = 6, seed: int = 5):
    index = pd.date_range("2015-01-31", periods=n_months, freq="ME")
    rng = np.random.default_rng(seed)
    tickers = [f"T{i}" for i in range(n_tickers)]
    monthly = pd.DataFrame(
        rng.normal(0.01, 0.06, (n_months, n_tickers)), index=index, columns=tickers
    )
    factors = pd.DataFrame(
        {
            "mkt_rf": rng.normal(0.008, 0.04, n_months),
            "smb": rng.normal(0.0, 0.02, n_months),
            "hml": rng.normal(0.0, 0.02, n_months),
            "rf": np.full(n_months, 0.001),
        },
        index=index,
    )
    return monthly, factors


def test_all_three_arms_are_scored_on_exactly_the_same_months():
    """THE anti-rigging property. The control needs no factor data and could be
    scored for months where FF3 coverage has run out — which would hand the
    benchmark a timing advantage over the very arms it benchmarks."""
    monthly, factors = _monthly_fixture()
    # Delete the last 6 months of factor data, as a truncated French vintage
    # would.
    factors = factors.iloc[:-6]

    frames, diagnostics = compute_residual_momentum_scores(monthly, factors)
    scored = {name: frame.notna().any(axis=1) for name, frame in frames.items()}
    control, capm, ff3 = (
        scored["total_return_control"],
        scored["capm_residual"],
        scored["ff3_residual"],
    )
    assert control.equals(capm)
    assert control.equals(ff3)
    # And the uncovered months really are unscored for everyone.
    assert not control.loc[monthly.index[-6:]].any()
    assert diagnostics.n_months_without_factor_coverage == 6


def test_a_ticker_missing_any_month_of_the_estimation_window_is_refused_and_counted():
    monthly, factors = _monthly_fixture()
    monthly.iloc[10, 0] = np.nan  # one hole for T0

    frames, diagnostics = compute_residual_momentum_scores(monthly, factors)
    ff3 = frames["ff3_residual"]
    # T0 is unscored for every window containing month 10, and scored again
    # once the window has rolled past it.
    first_scored = RESIDUAL_MOM_REGRESSION_MONTHS - 1
    assert np.isnan(ff3.iloc[first_scored, 0])
    assert np.isfinite(ff3.iloc[10 + RESIDUAL_MOM_REGRESSION_MONTHS, 0])
    # Its peers are unaffected — a refusal is per ticker, not per month.
    assert np.isfinite(ff3.iloc[first_scored, 1])
    assert diagnostics.n_refused["incomplete_estimation_window"] > 0


def test_no_score_exists_before_a_full_estimation_window_has_elapsed():
    monthly, factors = _monthly_fixture()
    frames, _ = compute_residual_momentum_scores(monthly, factors)
    for frame in frames.values():
        head = frame.iloc[: RESIDUAL_MOM_REGRESSION_MONTHS - 1]
        assert head.isna().all().all()
        assert frame.iloc[RESIDUAL_MOM_REGRESSION_MONTHS - 1].notna().all()


def test_compute_scores_refuses_a_scoring_window_that_is_not_a_strict_subset():
    monthly, factors = _monthly_fixture()
    with pytest.raises(ValueError, match="strictly less than"):
        compute_residual_momentum_scores(
            monthly, factors, regression_months=12, formation_months=12
        )


# --- the publication-lag point-in-time contract ------------------------------


def test_observations_are_available_only_after_the_publication_lag():
    frame = pd.DataFrame(
        {"AAA": [1.0, 2.0]}, index=pd.to_datetime(["2020-01-31", "2020-02-29"])
    )
    observations = build_residual_momentum_observations(frame)
    events = observations["AAA"]
    assert [e.end for e in events] == [date(2020, 1, 31), date(2020, 2, 29)]
    assert [e.available for e in events] == [
        date(2020, 1, 31) + timedelta(days=FF3_PUBLICATION_LAG_DAYS),
        date(2020, 2, 29) + timedelta(days=FF3_PUBLICATION_LAG_DAYS),
    ]


def test_a_negative_publication_lag_is_refused():
    """A negative lag is the one bug in this family that would produce a
    better-looking result while remaining completely invisible in the output."""
    frame = pd.DataFrame({"AAA": [1.0]}, index=pd.to_datetime(["2020-01-31"]))
    with pytest.raises(ValueError, match="published"):
        build_residual_momentum_observations(frame, publication_lag_days=-1)


def test_nan_scores_produce_no_observation_at_all():
    frame = pd.DataFrame(
        {"AAA": [np.nan, 3.0]}, index=pd.to_datetime(["2020-01-31", "2020-02-29"])
    )
    assert len(build_residual_momentum_observations(frame)["AAA"]) == 1


def test_the_step_panel_never_shows_a_score_before_its_availability_date():
    """End-to-end point-in-time check: a January score must be invisible on
    every trading day before (month end + lag), and visible after."""
    index = pd.bdate_range("2020-01-01", "2020-06-30")
    close = pd.DataFrame({"AAA": np.ones(len(index))}, index=index)
    scores = pd.DataFrame({"AAA": [42.0]}, index=pd.to_datetime(["2020-01-31"]))
    observations = build_residual_momentum_observations(scores)
    panel, _ages, unusable = build_point_in_time_factor_frame(
        close, observations, max_staleness_days=RESIDUAL_MOM_MAX_STALENESS_DAYS
    )

    available_on = date(2020, 1, 31) + timedelta(days=FF3_PUBLICATION_LAG_DAYS)
    before = panel[panel.index.date < available_on]["AAA"]
    after = panel[panel.index.date >= available_on]["AAA"]
    assert before.isna().all()
    assert (after.dropna() == 42.0).all()
    assert not unusable


def test_the_score_goes_stale_rather_than_ranking_forever():
    """A monthly-refreshing signal must not still be ranking the cross-section
    a year later if its successors never arrived."""
    index = pd.bdate_range("2020-01-01", "2020-12-31")
    close = pd.DataFrame({"AAA": np.ones(len(index))}, index=index)
    scores = pd.DataFrame({"AAA": [42.0]}, index=pd.to_datetime(["2020-01-31"]))
    panel, _, _ = build_point_in_time_factor_frame(
        close,
        build_residual_momentum_observations(scores),
        max_staleness_days=RESIDUAL_MOM_MAX_STALENESS_DAYS,
    )
    assert panel["AAA"].notna().any()
    assert panel["AAA"].iloc[-1] != panel["AAA"].iloc[-1] or np.isnan(panel["AAA"].iloc[-1])
    assert np.isnan(panel["AAA"].iloc[-1]), "a December day must not rank on a January score"


# --- the pre-declared family shape -------------------------------------------


def _bucket_frame(close: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    return pd.DataFrame(
        {t: [mapping[t]] * len(close.index) for t in close.columns}, index=close.index
    )


def test_family_is_exactly_the_pre_declared_eighteen():
    close = pd.DataFrame(
        {"AAA": [1.0], "BBB": [1.0]}, index=pd.to_datetime(["2020-01-02"])
    )
    specs = build_residual_momentum_family(_bucket_frame(close, {"AAA": "tech", "BBB": "tech"}))

    assert len(specs) == RESIDUAL_MOM_N_TRIALS == 18
    assert RESIDUAL_MOM_N_TRIALS == (
        len(RESIDUAL_MOM_ARMS) * len(RESIDUAL_MOM_CONDITIONINGS) * len(RESIDUAL_MOM_HOLDING_DAYS)
    )
    assert len({s.pattern_id for s in specs}) == 18
    assert all(s.family == RESIDUAL_MOM_FAMILY for s in specs)
    assert all(s.portfolio == "long_short" for s in specs)
    assert all(s.requires_fundamental_signal for s in specs)
    # Deciles throughout — BHM's own sort, and NOT a grid axis here.
    assert {s.rank_fraction for s in specs} == {QUALITY_RANK_FRACTION}
    assert {s.holding_days for s in specs} == set(RESIDUAL_MOM_HOLDING_DAYS)


def test_the_regression_window_and_rank_fraction_are_not_searched_over():
    """Both are fixed at BHM's own values. If either ever became a tuple, the
    grid would silently grow and the DSR denominator would be wrong."""
    assert isinstance(RESIDUAL_MOM_REGRESSION_MONTHS, int)
    assert RESIDUAL_MOM_REGRESSION_MONTHS == 36
    assert RESIDUAL_MOM_FORMATION_MONTHS == 11
    assert isinstance(QUALITY_RANK_FRACTION, float)


def test_a_monthly_hold_is_included_unlike_the_annual_refresh_families():
    """The asset-growth family excluded a 21-day hold because its ranking
    variable refreshed once a year. This one refreshes MONTHLY, and 21 days is
    BHM's own rebalance, so its presence is deliberate."""
    assert 21 in RESIDUAL_MOM_HOLDING_DAYS


def test_specs_for_arm_partitions_the_family_into_three_sixes():
    close = pd.DataFrame({"AAA": [1.0]}, index=pd.to_datetime(["2020-01-02"]))
    specs = build_residual_momentum_family(_bucket_frame(close, {"AAA": "tech"}))
    seen: list[str] = []
    for arm, _columns in RESIDUAL_MOM_ARMS:
        subset = specs_for_arm(specs, arm)
        assert len(subset) == 6
        seen.extend(s.pattern_id for s in subset)
    assert sorted(seen) == sorted(s.pattern_id for s in specs)


# --- the two signal functions ------------------------------------------------


def _history(values: dict[str, float], buckets: dict[str, str] | None = None):
    index = pd.to_datetime(["2020-01-02", "2020-01-03"])
    tickers = list(values)
    close = pd.DataFrame({t: [1.0, 1.0] for t in tickers}, index=index)
    frame = pd.DataFrame({t: [np.nan, values[t]] for t in tickers}, index=index)
    data = CrossSectionalData(close=close, fundamental_signal=frame)
    bucket = _bucket_frame(close, buckets) if buckets else None
    return data, bucket


def test_raw_signal_is_top_is_long_and_passes_nan_through_as_a_refusal():
    data, _ = _history({"AAA": 2.0, "BBB": -1.0, "CCC": float("nan")})
    signal = signal_residual_momentum(data)
    assert signal["AAA"] > signal["BBB"]
    assert np.isnan(signal["CCC"])


def test_signals_refuse_to_run_without_a_fundamental_signal_frame():
    close = pd.DataFrame({"AAA": [1.0]}, index=pd.to_datetime(["2020-01-02"]))
    bare = CrossSectionalData(close=close)
    with pytest.raises(ValueError, match="requires_fundamental_signal"):
        signal_residual_momentum(bare)
    with pytest.raises(ValueError, match="requires_fundamental_signal"):
        signal_residual_momentum_industry_neutral(
            bare, bucket_frame=_bucket_frame(close, {"AAA": "tech"})
        )


def test_industry_neutral_centering_is_the_median_not_the_mean():
    """Pre-declared in advance: the score is a ratio whose denominator can be
    small for a quiet stock, so its tails are heavy and a bucket mean would be
    dragged by a single outlier."""
    values = {"A": 1.0, "B": 2.0, "C": 3.0, "D": 100.0}
    buckets = dict.fromkeys(values, "tech")
    data, bucket_frame = _history(values, buckets)
    signal = signal_residual_momentum_industry_neutral(data, bucket_frame=bucket_frame)

    median = 2.5
    assert signal["A"] == pytest.approx(1.0 - median)
    assert signal["D"] == pytest.approx(100.0 - median)
    # Under MEAN centering (mean = 26.5) A and B would both sit far below zero
    # and the ordering relative to the centre would be dominated by D.
    assert signal["B"] < 0 and signal["C"] > 0


def test_industry_neutral_centres_within_bucket_not_across_the_whole_universe():
    values = {"A": 1.0, "B": 3.0, "C": 10.0, "D": 30.0, "E": 20.0, "F": 40.0}
    buckets = {"A": "tech", "B": "tech", "C": "tech", "D": "energy", "E": "energy", "F": "energy"}
    data, bucket_frame = _history(values, buckets)
    signal = signal_residual_momentum_industry_neutral(data, bucket_frame=bucket_frame)
    assert signal["C"] == pytest.approx(10.0 - 3.0)
    assert signal["F"] == pytest.approx(40.0 - 30.0)
    # A whole-universe median (15.0) would have made C negative.
    assert signal["C"] > 0


def test_industry_neutral_refuses_a_bucket_below_min_bucket_size():
    values = {"A": 1.0, "B": 2.0, "C": 3.0, "D": 9.0}
    buckets = {"A": "tech", "B": "tech", "C": "tech", "D": "lonely"}
    data, bucket_frame = _history(values, buckets)
    signal = signal_residual_momentum_industry_neutral(data, bucket_frame=bucket_frame)
    assert MIN_BUCKET_SIZE == 3
    assert np.isnan(signal["D"])
    assert np.isfinite(signal["A"])


def test_industry_neutral_refuses_a_ticker_with_no_bucket():
    index = pd.to_datetime(["2020-01-02", "2020-01-03"])
    close = pd.DataFrame({t: [1.0, 1.0] for t in "ABCD"}, index=index)
    frame = pd.DataFrame({t: [np.nan, float(i + 1)] for i, t in enumerate("ABCD")}, index=index)
    bucket_frame = pd.DataFrame(
        {"A": ["tech"] * 2, "B": ["tech"] * 2, "C": ["tech"] * 2, "D": [None] * 2}, index=index
    )
    signal = signal_residual_momentum_industry_neutral(
        CrossSectionalData(close=close, fundamental_signal=frame), bucket_frame=bucket_frame
    )
    assert np.isnan(signal["D"])
    assert np.isfinite(signal["A"])


def test_industry_neutral_returns_all_nan_when_nothing_is_rankable():
    index = pd.to_datetime(["2020-01-02", "2020-01-03"])
    close = pd.DataFrame({"A": [1.0, 1.0]}, index=index)
    frame = pd.DataFrame({"A": [np.nan, np.nan]}, index=index)
    bucket_frame = pd.DataFrame({"A": ["tech"] * 2}, index=index)
    signal = signal_residual_momentum_industry_neutral(
        CrossSectionalData(close=close, fundamental_signal=frame), bucket_frame=bucket_frame
    )
    assert signal.isna().all()


# --- harness integration -----------------------------------------------------


def test_signal_cannot_see_the_future_through_the_harness():
    """Structural look-ahead impossibility: the signal is handed a view sliced
    to rows <= the formation date, so a frame whose LATER rows would flip the
    ranking cannot change the book formed earlier."""
    index = pd.bdate_range("2020-01-01", periods=80)
    close = pd.DataFrame(
        {
            "AAA": np.linspace(100.0, 130.0, len(index)),
            "BBB": np.linspace(100.0, 80.0, len(index)),
            "CCC": np.linspace(100.0, 110.0, len(index)),
            "DDD": np.linspace(100.0, 95.0, len(index)),
        },
        index=index,
    )
    honest = pd.DataFrame(
        {"AAA": 2.0, "BBB": -2.0, "CCC": 1.0, "DDD": -1.0}, index=index
    ).astype(float)
    # Identical up to the formation date, then violently reversed afterwards.
    tampered = honest.copy()
    tampered.iloc[40:] *= -50.0

    spec = CrossSectionalSpec(
        pattern_id="rm_probe",
        family=RESIDUAL_MOM_FAMILY,
        citation="test",
        signal_fn=signal_residual_momentum,
        lookback_days=1,
        holding_days=21,
        portfolio="long_short",
        rank_fraction=0.25,
        requires_fundamental_signal=True,
    )
    config = CrossSectionalConfig(min_names_per_leg=1, formation_start=index[0].date())
    membership = fixed_universe_membership(close.columns)

    a = run_cross_sectional_backtest(
        CrossSectionalData(close=close, fundamental_signal=honest), spec, config, membership
    )
    b = run_cross_sectional_backtest(
        CrossSectionalData(close=close, fundamental_signal=tampered), spec, config, membership
    )
    first_a = next(f for f in a.formations if f.skipped_reason is None)
    first_b = next(f for f in b.formations if f.skipped_reason is None)
    assert first_a.long_tickers == first_b.long_tickers
    assert first_a.short_tickers == first_b.short_tickers
    assert "AAA" in first_a.long_tickers
    assert "BBB" in first_a.short_tickers


def test_end_to_end_pipeline_ranks_exactly_what_the_score_panel_says():
    """A full small pipeline: daily closes -> monthly returns -> rolling FF3
    residual scores -> availability-dated step panel -> a formed book.

    The assertion is on the WIRING, not on an economic outcome: at every
    formation, the long leg must be exactly the top names of that formation's
    own panel row. An earlier version of this test planted a constant
    idiosyncratic drift into two tickers and expected them to win — and they
    did not, correctly: a constant drift is absorbed entirely by the regression
    intercept, which is precisely what
    test_a_recent_idiosyncratic_run_scores_high_but_a_constant_drift_does_not
    now pins. Asserting on wiring tests more and assumes less."""
    index = pd.bdate_range("2015-01-01", "2021-12-31")
    rng = np.random.default_rng(19)
    tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
    steps = rng.normal(0.0004, 0.012, (len(index), len(tickers)))
    close = pd.DataFrame(100.0 * np.exp(np.cumsum(steps, axis=0)), index=index, columns=tickers)

    monthly = monthly_returns_from_daily_close(close)
    factors = pd.DataFrame(
        {
            "mkt_rf": rng.normal(0.006, 0.035, len(monthly.index)),
            "smb": rng.normal(0.0, 0.02, len(monthly.index)),
            "hml": rng.normal(0.0, 0.02, len(monthly.index)),
            "rf": np.full(len(monthly.index), 0.001),
        },
        index=monthly.index,
    )

    frames, diagnostics = compute_residual_momentum_scores(monthly, factors)
    assert diagnostics.n_scored > 0
    # The degeneracy guard must not be silently eating this cross-section.
    assert not [k for k in diagnostics.n_refused if k.startswith("degenerate_residual_std")]

    panel, _ages, unusable = build_point_in_time_factor_frame(
        close,
        build_residual_momentum_observations(frames["ff3_residual"]),
        max_staleness_days=RESIDUAL_MOM_MAX_STALENESS_DAYS,
    )
    assert not unusable

    spec = CrossSectionalSpec(
        pattern_id="rm_e2e",
        family=RESIDUAL_MOM_FAMILY,
        citation="test",
        signal_fn=signal_residual_momentum,
        lookback_days=1,
        holding_days=21,
        portfolio="long_short",
        rank_fraction=1 / 3,
        requires_fundamental_signal=True,
    )
    result = run_cross_sectional_backtest(
        CrossSectionalData(close=close, fundamental_signal=panel),
        spec,
        CrossSectionalConfig(min_names_per_leg=1, formation_start=date(2019, 1, 2)),
        fixed_universe_membership(tickers),
    )
    assert result.status == "ok"
    formed = [f for f in result.formations if f.skipped_reason is None]
    assert len(formed) > 20

    for formation in formed:
        row = panel.loc[formation.date].dropna().sort_values(ascending=False)
        k = len(formation.long_tickers)
        assert k > 0
        assert set(formation.long_tickers) == set(row.index[:k])
        assert set(formation.short_tickers) == set(row.index[-len(formation.short_tickers):])


def test_reported_signal_age_measures_the_age_of_the_DATA_not_of_the_release():
    """The lag is meant to BITE, and the reported number must show it.

    build_point_in_time_factor_frame measures age from a value's AVAILABILITY
    date, which for this family already has the 45-day publication lag folded
    in — so the raw age is ~0 on the day a score lands. Reporting that would
    claim the signal is days old when its newest input is a two-month-old
    factor return. _median_signal_age adds the lag back for exactly that
    reason, and this test is what stops someone "simplifying" it away."""
    index = pd.bdate_range("2020-01-01", "2021-12-31")
    close = pd.DataFrame({"AAA": np.ones(len(index))}, index=index)
    months = pd.date_range("2020-01-31", "2021-11-30", freq="ME")
    scores = pd.DataFrame({"AAA": np.arange(float(len(months)))}, index=months)
    _, ages, _ = build_point_in_time_factor_frame(
        close,
        build_residual_momentum_observations(scores),
        max_staleness_days=RESIDUAL_MOM_MAX_STALENESS_DAYS,
    )
    # The raw helper age really does start at zero — the thing that would be
    # misleading to report.
    assert ages["AAA"].dropna().min() == 0.0
    # What this family reports is the age of the underlying DATA.
    reported = _median_signal_age(ages, date(2020, 6, 1))
    assert reported >= FF3_PUBLICATION_LAG_DAYS
    # A month-end score refreshing monthly sits ~45-75 days behind its data.
    assert FF3_PUBLICATION_LAG_DAYS <= reported <= FF3_PUBLICATION_LAG_DAYS + 31


# --- pooled sigma_SR ---------------------------------------------------------


def _screening_result(pattern_id: str, sharpe: float) -> CrossSectionalScreeningResult:
    daily = sharpe / np.sqrt(252.0)
    return CrossSectionalScreeningResult(
        pattern_id=pattern_id,
        family=RESIDUAL_MOM_FAMILY,
        citation="test",
        n_formations=50,
        n_skipped_formations=0,
        avg_names_per_leg=12.0,
        n_trading_days=2500,
        sharpe_annualized=sharpe,
        total_cost_drag=0.0,
        deflated_sharpe=DeflatedSharpeResult(
            sharpe_net_annualized=sharpe,
            sharpe_net_daily=daily,
            n_observations=2500,
            skewness=0.0,
            kurtosis=3.0,
            psr_vs_zero=0.5,
            n_trials=18,
            sigma_sr_annualized=0.01,  # a deliberately wrong, arm-local value
            expected_max_sharpe_noise_annualized=0.02,
            dsr=0.99,
            dsr_floor_met=True,
            interpretation="stale",
        ),
    )


def test_repooling_uses_the_dispersion_of_every_spec_not_just_one_arm():
    """n_trials_override fixes the DENOMINATOR but not sigma_SR, which the
    harness computes per call. Without repooling, each arm's DSR would be
    deflated against the spread of its own 6 Sharpes rather than the 18 the
    search actually spanned."""
    sharpes = [0.05 * i for i in range(18)]
    results = [_screening_result(f"rm_s{i}", s) for i, s in enumerate(sharpes)]
    repooled = repool_deflated_sharpe(results)

    expected_sigma = float(np.std(sharpes, ddof=1))
    assert all(r.deflated_sharpe.sigma_sr_annualized == pytest.approx(expected_sigma) for r in repooled)
    assert all(r.deflated_sharpe.n_trials == 18 for r in repooled)
    # The stale arm-local sigma is gone, and so is its DSR.
    assert all(r.deflated_sharpe.dsr != 0.99 for r in repooled)
    assert all("POOLED" in r.deflated_sharpe.interpretation for r in repooled)


def test_repooling_matches_the_shared_dsr_machinery_exactly():
    """A strict re-derivation, not a private reimplementation: the repooled DSR
    must equal what deflated_sharpe.py's own functions give for the same
    pooled sigma_SR."""
    sharpes = [-0.2, 0.0, 0.1, 0.3, 0.45, 0.6]
    results = [_screening_result(f"rm_s{i}", s) for i, s in enumerate(sharpes)]
    repooled = repool_deflated_sharpe(results, n_trials=18)

    sigma_sr = float(np.std(sharpes, ddof=1))
    sr0_daily = expected_max_sharpe_under_noise(sigma_sr / np.sqrt(252.0), 18)
    assert sr0_daily is not None
    for result in repooled:
        expected = probabilistic_sharpe_ratio(
            result.deflated_sharpe.sharpe_net_daily, sr0_daily, 2500, 0.0, 3.0
        )
        assert result.deflated_sharpe.dsr == pytest.approx(expected)
        assert result.deflated_sharpe.expected_max_sharpe_noise_annualized == pytest.approx(
            sr0_daily * np.sqrt(252.0)
        )


def test_repooling_is_a_no_op_on_a_single_result():
    results = [_screening_result("rm_only", 0.4)]
    assert repool_deflated_sharpe(results)[0].deflated_sharpe.dsr == 0.99


def test_repooling_preserves_the_per_spec_point_estimate_and_sample():
    """Only sigma_SR, SR0 and the DSR may change. If the Sharpe or the
    observation count moved, this would be a second backtest rather than a
    re-derivation."""
    results = [_screening_result(f"rm_s{i}", 0.1 * i) for i in range(18)]
    before = [(r.sharpe_annualized, r.deflated_sharpe.n_observations) for r in results]
    repooled = repool_deflated_sharpe(results)
    after = [(r.sharpe_annualized, r.deflated_sharpe.n_observations) for r in repooled]
    assert before == after


def test_an_in_progress_final_month_is_dropped_not_treated_as_a_full_month():
    """`resample("ME")` labels a two-day stub with a month-end date and returns
    a one-day figure that looks exactly like a monthly return. Feeding that into
    a 36-month regression would contaminate the betas and, if it reached the
    scoring window, the score.

    On the production run this was masked by the Fama-French coverage gate, but
    that was a coincidence of the committed factor vintage rather than a
    property of this function."""
    index = pd.bdate_range("2020-01-01", "2020-03-03")  # March is two days long
    close = pd.DataFrame({"AAA": np.arange(1.0, len(index) + 1.0)}, index=index)
    monthly = monthly_returns_from_daily_close(close)
    assert monthly.index[-1] == pd.Timestamp("2020-02-29")
    assert pd.Timestamp("2020-03-31") not in monthly.index


def test_a_final_month_that_really_ended_is_kept():
    index = pd.bdate_range("2020-01-01", "2020-03-31")
    close = pd.DataFrame({"AAA": np.arange(1.0, len(index) + 1.0)}, index=index)
    monthly = monthly_returns_from_daily_close(close)
    assert monthly.index[-1] == pd.Timestamp("2020-03-31")


def test_the_drop_rule_is_conservative_rather_than_calendar_clever():
    """A month whose last TRADING day precedes its calendar end is dropped too.
    That costs at most the newest month of signal — which the 45-day publication
    lag makes unusable anyway — and spares this function a trading calendar."""
    index = pd.bdate_range("2020-01-01", "2020-05-29")  # 2020-05-31 was a Sunday
    close = pd.DataFrame({"AAA": np.arange(1.0, len(index) + 1.0)}, index=index)
    monthly = monthly_returns_from_daily_close(close)
    assert monthly.index[-1] == pd.Timestamp("2020-04-30")


# --- constants that nothing else would catch drifting ------------------------
#
# Every test below exists because independent verification ran a mutation over
# this module and found the mutation SURVIVED the suite as it then stood. The
# code was correct in each case; nothing would have caught it becoming wrong.


def test_the_publication_lag_constant_itself_is_pinned():
    """MUTATION THAT SURVIVED: FF3_PUBLICATION_LAG_DAYS = 45 -> 0.

    The whole point-in-time defence rests on this one number, and the existing
    lag tests all derived their expectation FROM the constant, so they were
    tautological with respect to its value — set it to 0 and they still passed
    while the family silently started trading unpublished factor data.

    45 is not arbitrary: French's committed vintage carries data through
    2026-06-30 with an archive timestamp of 2026-08-03, a measured lag of 34
    days, and 45 is the conservative round number above it."""
    assert FF3_PUBLICATION_LAG_DAYS == 45
    assert FF3_PUBLICATION_LAG_DAYS > 34, "must exceed the measured French publication lag"
    assert RESIDUAL_MOM_MAX_STALENESS_DAYS == 75
    assert RESIDUAL_MOM_MAX_STALENESS_DAYS > FF3_PUBLICATION_LAG_DAYS, (
        "a staleness bound at or below the publication lag would refuse every score the "
        "instant it became available"
    )


def test_the_arms_factor_columns_are_pinned_exactly():
    """MUTATIONS THAT SURVIVED, all three: ff3 -> ('mkt_rf','smb');
    ff3 -> ('mkt_rf',) (a duplicate of the CAPM arm); and capm -> () (making it
    byte-identical to the total-return control).

    The suite imported RESIDUAL_MOM_ARMS but only ever used len() and the arm
    NAMES, and RESIDUAL_MOM_N_TRIALS is 3 x 2 x 3 regardless of column content —
    so the `len(specs) == 18` assertion caught nothing. Two arms could collapse
    into one while the report still printed three columns.

    The FF3-vs-CAPM-vs-control contrast IS this family's hypothesis, so the
    columns are pinned by value."""
    assert RESIDUAL_MOM_ARMS == (
        ("total_return_control", ()),
        ("capm_residual", ("mkt_rf",)),
        ("ff3_residual", ("mkt_rf", "smb", "hml")),
    )
    columns = [cols for _name, cols in RESIDUAL_MOM_ARMS]
    assert len({tuple(c) for c in columns}) == 3, "no two arms may share a factor set"
    # No momentum (UMD) factor anywhere: regressing momentum out of a momentum
    # signal is close to circular, and the build brief's "Carhart" claim was
    # checked and rejected. See the module docstring, section 1.
    assert not any("umd" in c or "mom" in c for cols in columns for c in cols)


def test_the_three_arms_really_produce_different_scores():
    """The value pinning above is necessary but not sufficient — this is the
    behavioural half. If two arms ever collapsed onto the same factor set, the
    report would print three columns of the same numbers."""
    monthly, factors = _monthly_fixture(n_months=60, n_tickers=8, seed=101)
    frames, _ = compute_residual_momentum_scores(monthly, factors)
    control = frames["total_return_control"].to_numpy()
    capm = frames["capm_residual"].to_numpy()
    ff3 = frames["ff3_residual"].to_numpy()
    finite = np.isfinite(control) & np.isfinite(capm) & np.isfinite(ff3)
    assert finite.sum() > 50
    assert not np.allclose(capm[finite], ff3[finite])
    assert not np.allclose(control[finite], capm[finite])
    assert not np.allclose(control[finite], ff3[finite])


def test_the_risk_free_rate_is_really_subtracted():
    """MUTATION THAT SURVIVED: excess_matrix = returns - rf -> returns.

    Eq. 8's left-hand side is the EXCESS return. Dropping RF entirely passed the
    whole suite, and it is not cosmetic — on the production run's real data it
    changed the cross-sectional ranking in roughly 8% of month cross-sections.

    A CONSTANT risk-free rate is NOT enough to detect this, and finding that out
    is half the value of the test: a level shift applied to every month is
    absorbed entirely by the regression intercept, so the residual arms are
    genuinely invariant to it (the same property as
    test_alpha_is_absorbed_by_the_fit_and_never_added_back). Only the TIME
    VARIATION of RF reaches the residual score — which is exactly what real RF
    has, ranging from ~0 to ~0.5%/month across this sample."""
    monthly, factors = _monthly_fixture(n_months=50, n_tickers=6, seed=7)
    zero_rf = factors.copy()
    zero_rf["rf"] = 0.0
    varying_rf = factors.copy()
    rng = np.random.default_rng(77)
    varying_rf["rf"] = rng.uniform(0.0, 0.005, len(factors))  # real RF's range

    a, _ = compute_residual_momentum_scores(monthly, zero_rf)
    b, _ = compute_residual_momentum_scores(monthly, varying_rf)
    for arm in ("total_return_control", "capm_residual", "ff3_residual"):
        x, y = a[arm].to_numpy(), b[arm].to_numpy()
        finite = np.isfinite(x) & np.isfinite(y)
        assert finite.sum() > 20
        assert not np.allclose(x[finite], y[finite]), f"{arm} ignored the risk-free rate"

    # The level-shift invariance itself, pinned so the above is not mistaken
    # for a claim that RF's level matters to the residual arms.
    flat_rf = factors.copy()
    flat_rf["rf"] = 0.02
    c, _ = compute_residual_momentum_scores(monthly, flat_rf)
    for arm in ("capm_residual", "ff3_residual"):
        x, y = a[arm].to_numpy(), c[arm].to_numpy()
        finite = np.isfinite(x) & np.isfinite(y)
        assert np.allclose(x[finite], y[finite]), (
            f"{arm} should be invariant to a CONSTANT rf — the intercept absorbs it"
        )


def test_the_control_compounds_excess_returns_as_pre_registered():
    """The pre-registration froze the control as 'the cumulative EXCESS return
    over the same 11 months'. It was first built on RAW returns, justified by
    'a common shift cannot reorder a ranking' — TRUE OF A SUM, FALSE OF THE
    COMPOUNDED PRODUCT actually computed. This is that counterexample."""
    r_a = np.array([1.0, 0.0])
    r_b = np.array([0.0, 1.0])
    rf = np.array([0.0, 0.5])
    raw = np.column_stack([r_a, r_b])
    excess = np.column_stack([r_a - rf, r_b - rf])

    raw_scores = _control_scores_for_window(raw, formation_months=2)
    excess_scores = _control_scores_for_window(excess, formation_months=2)
    assert raw_scores[0] == pytest.approx(raw_scores[1])  # raw ties...
    assert excess_scores[0] != pytest.approx(excess_scores[1])  # ...excess does not
    assert excess_scores == pytest.approx([0.0, 0.5])
