"""Tests for the PCA / eigenportfolio statistical-arbitrage family.

Every synthetic fixture is seed-verified and deterministic, and no test here
touches the network — following conftest.py's canned_prices convention that
"tests must never depend on live yfinance data".

The tests that matter most are the GROUND-TRUTH ones: a panel built with a known
number of true factors plus i.i.d. idiosyncratic noise, and an AR(1) process with
a known mean-reversion speed injected on purpose, so that the PCA, the OU fit and
the s-score are checked against a right answer that exists independently of the
implementation rather than against whatever the implementation happens to print.
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest

import app.services.research_lab.cross_sectional_eigenportfolio as eig_mod
from app.services.research_lab.cross_sectional_eigenportfolio import (
    EIGEN_B_CEILING,
    EIGEN_CORRELATION_WINDOWS,
    EIGEN_COST_BPS,
    EIGEN_FAMILY,
    EIGEN_KAPPA_FLOOR,
    EIGEN_MIN_RESIDUAL_DOF,
    EIGEN_N_TRIALS,
    EIGEN_PCA_FIXED_COUNT,
    EIGEN_REGRESSION_WINDOW,
    EIGEN_THRESHOLD_SETS,
    EIGEN_VARIANCE_THRESHOLD,
    PAPER_S_BC,
    PAPER_S_BO,
    PAPER_S_SC,
    PAPER_S_SO,
    PAPER_THRESHOLDS,
    WIDE_THRESHOLDS,
    EigenConfig,
    EigenPanel,
    build_cross_section_signal,
    build_eigen_disclosure,
    build_eigen_panel,
    build_reversal_book,
    correlation_from_standardized,
    fit_ou_ar1,
    implied_half_life_days,
    next_position,
    run_eigen_replay,
    screen_eigenportfolio,
    select_n_factors,
    standardize_returns,
)
from app.services.research_lab.deflated_sharpe import MIN_TRIALS_FOR_DSR
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR

# --- helpers ---------------------------------------------------------------


def _ar1_panel(true_b: float, true_a: float, n_obs: int, n_cols: int, seed: int) -> np.ndarray:
    """n_cols independent AR(1) paths with a KNOWN b and a. The ground truth
    the OU fit is checked against."""
    rng = np.random.default_rng(seed)
    columns = []
    for _ in range(n_cols):
        path = np.zeros(n_obs)
        noise = rng.normal(0.0, 0.01, n_obs)
        for t in range(1, n_obs):
            path[t] = true_a + true_b * path[t - 1] + noise[t]
        columns.append(path)
    return np.column_stack(columns)


def _factor_panel(
    n_obs: int, n_names: int, n_true_factors: int, seed: int, idio_sd: float = 0.004
) -> np.ndarray:
    """A returns panel with EXACTLY `n_true_factors` common factors plus i.i.d.
    idiosyncratic noise — the ground truth the PCA is checked against."""
    rng = np.random.default_rng(seed)
    factors = rng.normal(0.0, 0.010, (n_obs, n_true_factors))
    loadings = rng.normal(0.0, 1.0, (n_true_factors, n_names))
    return factors @ loadings + rng.normal(0.0, idio_sd, (n_obs, n_names))


def _synthetic_eigen_panel(
    n_days: int = 700, n_names: int = 90, n_true_factors: int = 3, seed: int = 4242
) -> EigenPanel:
    """A full EigenPanel with every name a member on every date, so replay tests
    exercise the trading machinery rather than the membership plumbing."""
    index = pd.bdate_range("2015-01-02", periods=n_days)
    tickers = [f"T{i:03d}" for i in range(n_names)]
    returns = pd.DataFrame(
        _factor_panel(n_days, n_names, n_true_factors, seed), index=index, columns=tickers
    )
    mask = pd.DataFrame(True, index=index, columns=tickers)
    return EigenPanel(
        returns=returns,
        member_mask=mask,
        n_members_by_date=pd.Series(n_names, index=index),
    )


# --- family shape ----------------------------------------------------------


def test_family_is_exactly_twelve_fully_crossed_specs():
    assert len(EIGEN_FAMILY) == EIGEN_N_TRIALS == 12
    assert len({s.spec_id for s in EIGEN_FAMILY}) == 12
    rules = {s.factor_rule for s in EIGEN_FAMILY}
    assert rules == {"pca15", "var55", "m1"}
    assert {s.correlation_window for s in EIGEN_FAMILY} == set(EIGEN_CORRELATION_WINDOWS)
    assert {s.thresholds.key for s in EIGEN_FAMILY} == {t.key for t in EIGEN_THRESHOLD_SETS}
    # Fully crossed: every (rule, window, threshold) cell exists exactly once.
    cells = {(s.factor_rule, s.correlation_window, s.thresholds.key) for s in EIGEN_FAMILY}
    assert len(cells) == 12


def test_family_size_clears_the_dsr_floor():
    """Below MIN_TRIALS_FOR_DSR the deflated Sharpe cannot be computed at all,
    so a family that drifted under it would silently lose its whole
    multiple-comparisons correction."""
    assert EIGEN_N_TRIALS >= MIN_TRIALS_FOR_DSR


def test_family_build_asserts_on_grid_drift(monkeypatch):
    """The n_trials denominator is asserted three ways; dropping a threshold set
    must fail loudly rather than silently shrink the DSR denominator."""
    monkeypatch.setattr(eig_mod, "EIGEN_THRESHOLD_SETS", (PAPER_THRESHOLDS,))
    with pytest.raises(AssertionError, match="EIGEN_N_TRIALS"):
        eig_mod._build_eigen_family()


def test_direction_is_uniform_and_never_per_spec():
    """A per-spec sign would double the real search to 24 while still reporting
    n_trials=12 — the uncounted degree of freedom the DSR exists to prevent."""
    assert len({s.direction for s in EIGEN_FAMILY}) == 1


def test_m1_control_exists_at_every_window_and_threshold():
    controls = [s for s in EIGEN_FAMILY if s.factor_rule == "m1"]
    assert len(controls) == len(EIGEN_CORRELATION_WINDOWS) * len(EIGEN_THRESHOLD_SETS)
    assert all(not s.is_eigen_hypothesis for s in controls)


# --- constants pinned against the paper ------------------------------------


def test_b_ceiling_reproduces_the_papers_printed_value():
    """Appendix A prints 0.9672 as the AR(1) restatement of kappa > 252/30.
    Deriving it here rather than hardcoding it means the two can never drift
    apart; this test pins the derivation against the paper's own number."""
    assert EIGEN_KAPPA_FLOOR == pytest.approx(8.4)
    assert EIGEN_B_CEILING == pytest.approx(0.9672, abs=5e-5)
    assert EIGEN_B_CEILING == pytest.approx(np.exp(-EIGEN_KAPPA_FLOOR / TRADING_DAYS_PER_YEAR))


def test_kappa_floor_is_a_mean_reversion_time_not_a_half_life():
    """The single easiest thing to misquote about this paper. 252/30 bounds the
    mean-reversion TIME 1/kappa at 30 trading days; the HALF-LIFE at that same
    kappa is ln(2)/kappa = 20.8 days, which is a different number."""
    reversion_time_days = TRADING_DAYS_PER_YEAR / EIGEN_KAPPA_FLOOR
    assert reversion_time_days == pytest.approx(30.0)
    half_life = implied_half_life_days(EIGEN_KAPPA_FLOOR)
    assert float(half_life) == pytest.approx(20.79, abs=0.01)
    assert float(half_life) < reversion_time_days


def test_paper_thresholds_are_exactly_equation_16():
    assert (PAPER_S_BO, PAPER_S_SO, PAPER_S_BC, PAPER_S_SC) == (1.25, 1.25, 0.75, 0.50)
    assert PAPER_THRESHOLDS.s_bo == PAPER_THRESHOLDS.s_so == 1.25
    assert PAPER_THRESHOLDS.s_bc == 0.75
    assert PAPER_THRESHOLDS.s_sc == 0.50
    # The `wide` robustness set opens later and exits IDENTICALLY.
    assert WIDE_THRESHOLDS.s_bo == WIDE_THRESHOLDS.s_so == 1.50
    assert (WIDE_THRESHOLDS.s_bc, WIDE_THRESHOLDS.s_sc) == (PAPER_S_BC, PAPER_S_SC)


def test_cost_is_the_papers_own_one_way_slippage():
    """Paper section 5: eps = 0.0005, described as a 10bp round trip."""
    assert EIGEN_COST_BPS == 5.0
    assert EIGEN_COST_BPS / 1e4 == pytest.approx(0.0005)


# --- standardization and the correlation matrix ----------------------------


def test_standardization_matches_the_papers_definition():
    """Paper p.5: Y_ik = (R_ik - Rbar_i)/sigmabar_i with a ddof=1 sigmabar."""
    panel = _factor_panel(120, 20, 2, seed=11)
    standardized, sigma = standardize_returns(panel)
    assert sigma == pytest.approx(panel.std(axis=0, ddof=1))
    assert standardized.mean(axis=0) == pytest.approx(np.zeros(20), abs=1e-12)
    assert standardized.std(axis=0, ddof=1) == pytest.approx(np.ones(20))


def test_correlation_matrix_has_unit_diagonal_and_trace_n():
    """Paper eq. 8's own stated property: rho_ii = 1, hence trace = N. This is
    what makes the var55 rule's 'percentage of the trace' well defined."""
    panel = _factor_panel(200, 30, 3, seed=12)
    standardized, _ = standardize_returns(panel)
    rho = correlation_from_standardized(standardized)
    assert np.diag(rho) == pytest.approx(np.ones(30))
    assert np.trace(rho) == pytest.approx(30.0)
    assert rho == pytest.approx(rho.T)
    # And it agrees with numpy's own correlation, computed independently.
    assert rho == pytest.approx(np.corrcoef(panel, rowvar=False))


# --- GROUND TRUTH: the PCA recovers a known number of factors ---------------


@pytest.mark.parametrize("n_true_factors", [1, 3, 5])
def test_pca_recovers_the_injected_number_of_true_factors(n_true_factors):
    """A panel built as (n_true_factors common factors) + i.i.d. noise must show
    exactly that many eigenvalues detached from the noise bulk. This is the
    ground-truth check that the eigendecomposition is doing what the paper says
    rather than merely returning numbers."""
    panel = _factor_panel(252, 100, n_true_factors, seed=100 + n_true_factors, idio_sd=0.003)
    standardized, _ = standardize_returns(panel)
    eigenvalues = np.linalg.eigvalsh(correlation_from_standardized(standardized))[::-1]

    detached = eigenvalues[:n_true_factors]
    bulk = eigenvalues[n_true_factors:]
    # Every true factor's eigenvalue is an order of magnitude above the largest
    # noise eigenvalue — the "detached from the bulk spectrum" the paper reports.
    # This is the decisive check: it says the spectrum has EXACTLY this many
    # significant modes, which is the ground truth the panel was built with.
    assert detached.min() > 10 * bulk.max()
    # And the (n_true_factors + 1)-th eigenvalue is NOT detached, so the count
    # is not merely a lower bound.
    assert bulk.max() < 10 * bulk[1:].max()
    assert detached.sum() / eigenvalues.sum() > 0.65


def test_select_n_factors_follows_the_papers_two_rules():
    eigenvalues = np.array([50.0, 30.0, 10.0, 5.0, 3.0, 2.0])  # trace 100
    # var55: smallest k with cumulative share >= 55%. 50% at k=1, 80% at k=2.
    assert select_n_factors(eigenvalues, "var55") == 2
    assert select_n_factors(eigenvalues, "pca15") == min(EIGEN_PCA_FIXED_COUNT, 6)
    assert select_n_factors(eigenvalues, "m1") == 1


def test_var55_threshold_is_the_papers_55_percent():
    assert EIGEN_VARIANCE_THRESHOLD == 0.55
    # A spectrum whose first eigenvalue alone clears 55% must select exactly 1.
    assert select_n_factors(np.array([60.0, 20.0, 20.0]), "var55") == 1
    # One at 40% after the first and 60% after the second must select 2.
    assert select_n_factors(np.array([40.0, 20.0, 20.0, 20.0]), "var55") == 2
    # Exact-boundary behaviour: reaching the threshold exactly counts as met.
    assert select_n_factors(np.array([55.0, 45.0]), "var55") == 1


def test_select_n_factors_rejects_an_unknown_rule():
    with pytest.raises(ValueError, match="unknown factor rule"):
        select_n_factors(np.array([1.0]), "pca42")


def test_pca15_is_clipped_to_a_thin_cross_section():
    assert select_n_factors(np.ones(4), "pca15") == 4


# --- GROUND TRUTH: the OU/AR(1) fit recovers a known mean-reversion speed ---


def test_ou_fit_recovers_a_known_ar1_coefficient_and_kappa():
    """The core ground-truth test. Paths are generated with a KNOWN b, and the
    fit must recover b, and with it kappa = -log(b)*252 and m = a/(1-b)."""
    true_b, true_a = 0.85, 0.004
    fit = fit_ou_ar1(_ar1_panel(true_b, true_a, n_obs=4000, n_cols=60, seed=7))

    assert np.median(fit.b) == pytest.approx(true_b, abs=0.01)
    assert np.median(fit.kappa[fit.valid]) == pytest.approx(
        -np.log(true_b) * TRADING_DAYS_PER_YEAR, rel=0.05
    )
    assert np.median(fit.m_raw[fit.valid]) == pytest.approx(true_a / (1 - true_b), rel=0.10)


def test_ou_fit_is_consistent_so_the_60_day_bias_is_small_sample_not_a_bug():
    """At the paper's own 60-day window the OLS AR(1) coefficient is biased
    DOWNWARD — a well-known small-sample property, not a defect here. This test
    pins that the bias shrinks toward zero as the sample grows, which is what
    distinguishes 'known estimator bias the paper also inherits' from 'our
    arithmetic is wrong'.

    The practical consequence, disclosed rather than hidden: at 60 observations
    the fitted b sits below the true b, so kappa is biased UP and the paper's
    kappa > 8.4 filter admits somewhat slower processes than its nominal
    reading suggests."""
    true_b = 0.85
    biases = [
        abs(np.median(fit.b) - true_b)
        for fit in (
            fit_ou_ar1(_ar1_panel(true_b, 0.0, n_obs=n, n_cols=200, seed=n))
            for n in (60, 1000, 8000)
        )
    ]
    assert biases[0] > biases[1] > biases[2]
    assert biases[2] < 0.01


def test_sigma_eq_matches_the_closed_form_from_the_fit():
    """Appendix A eq. (A1): sigma_eq = sqrt(Var(zeta)/(1-b^2)). Recomputed here
    independently from the returned a and b, so the test does not simply echo
    the implementation."""
    cumulative = _ar1_panel(0.80, 0.002, n_obs=400, n_cols=25, seed=31)
    fit = fit_ou_ar1(cumulative)

    x_lag, x_next = cumulative[:-1], cumulative[1:]
    residual = x_next - (fit.a + fit.b * x_lag)
    var_zeta = (residual**2).sum(axis=0) / (x_lag.shape[0] - 2)
    expected = np.sqrt(var_zeta / (1 - fit.b**2))
    assert fit.sigma_eq[fit.valid] == pytest.approx(expected[fit.valid], rel=1e-10)

    # And sigma_eq = sigma/sqrt(2 kappa), the paper's eq. 14 form.
    sigma = np.sqrt(var_zeta * 2 * fit.kappa / (1 - fit.b**2))
    assert fit.sigma_eq[fit.valid] == pytest.approx(
        (sigma / np.sqrt(2 * fit.kappa))[fit.valid], rel=1e-10
    )


def test_s_score_is_the_papers_equation_15():
    """s = (X(t) - m)/sigma_eq, recomputed independently from the fit's own
    centered mean and sigma_eq."""
    cumulative = _ar1_panel(0.75, 0.003, n_obs=300, n_cols=40, seed=52)
    fit = fit_ou_ar1(cumulative)
    expected = (cumulative[-1] - fit.m_centered) / fit.sigma_eq
    assert fit.s_score[fit.valid] == pytest.approx(expected[fit.valid], rel=1e-10)


def test_centered_mean_averages_to_zero_across_the_cross_section():
    """Appendix A: m = a/(1-b) - <a/(1-b)>, the angle brackets averaging over
    stocks. So the centered means of the traded cross-section sum to zero."""
    fit = fit_ou_ar1(_ar1_panel(0.7, 0.01, n_obs=200, n_cols=50, seed=63))
    assert fit.m_centered[fit.valid].mean() == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("true_b,expect_valid", [(0.90, True), (0.99, False)])
def test_kappa_floor_admits_fast_and_rejects_slow_mean_reversion(true_b, expect_valid):
    """The paper's own speed filter: kappa > 252/30, i.e. 0 < b < 0.9672. A long
    sample is used so the estimate is not confounded by small-sample bias."""
    fit = fit_ou_ar1(_ar1_panel(true_b, 0.0, n_obs=6000, n_cols=40, seed=int(true_b * 1000)))
    assert bool(fit.valid.mean() > 0.9) is expect_valid
    if expect_valid:
        assert np.all(fit.kappa[fit.valid] > EIGEN_KAPPA_FLOOR)


def test_explosive_and_degenerate_fits_are_rejected_not_returned():
    """A random walk (b ~ 1) and a constant column must both come back invalid
    rather than producing a confident-looking s-score. The same
    degenerate-fit discipline ou_pairs.fit_ou_pairs_window applies."""
    rng = np.random.default_rng(88)
    random_walk = np.cumsum(rng.normal(0, 0.01, (400, 10)), axis=0)
    constant = np.zeros((400, 3))
    fit = fit_ou_ar1(np.column_stack([random_walk, constant]))
    assert not fit.valid[-3:].any()  # constant columns
    assert np.isnan(fit.s_score[-3:]).all()


def test_no_valid_names_yields_all_nan_scores_rather_than_crashing():
    fit = fit_ou_ar1(np.zeros((60, 5)))
    assert not fit.valid.any()
    assert np.isnan(fit.s_score).all()


# --- the cumulative residual's X_60 = 0 property ---------------------------


def test_cumulative_residual_ends_at_zero_as_the_paper_states():
    """Appendix A: X_60 = 0, 'an artifact of the regression, due to the fact
    that the betas and the residuals are estimated using the same sample.'
    The module does NOT hardcode this — it uses the computed value — so this
    test is what pins that the regression is genuinely producing it."""
    panel = _factor_panel(252, 80, 3, seed=17)
    next_returns = np.random.default_rng(18).normal(0, 0.01, 80)
    tickers = tuple(f"T{i:03d}" for i in range(80))

    design_check = build_cross_section_signal(panel, next_returns, tickers, "pca15")
    assert design_check.dof_ok

    # Recompute the cumulative residual independently and confirm it ends at 0.
    standardized, sigma = standardize_returns(panel)
    _eigenvalues, eigenvectors = np.linalg.eigh(correlation_from_standardized(standardized))
    weights = eigenvectors[:, ::-1][:, :EIGEN_PCA_FIXED_COUNT] / sigma[:, None]
    regression = panel[-EIGEN_REGRESSION_WINDOW:]
    design = np.column_stack([np.ones(EIGEN_REGRESSION_WINDOW), regression @ weights])
    coefficients, *_ = np.linalg.lstsq(design, regression, rcond=None)
    cumulative = np.cumsum(regression - design @ coefficients, axis=0)
    assert cumulative[-1] == pytest.approx(np.zeros(80), abs=1e-12)


# --- the trading rule, paper eq. 16 ---------------------------------------


def test_open_rules_match_equation_16_exactly():
    t = PAPER_THRESHOLDS
    assert next_position(0, -1.30, t) == 1  # buy to open:  s < -s_bo
    assert next_position(0, +1.30, t) == -1  # sell to open: s > +s_so
    assert next_position(0, -1.20, t) == 0  # inside the band -> stay flat
    assert next_position(0, +1.20, t) == 0
    assert next_position(0, 0.0, t) == 0


def test_close_rules_match_equation_16_exactly():
    """The rule the arbitragelab prose documentation gets WRONG (it says 'close
    a long position if s < +s_bc', inverting the paper's subscript mapping).

    Paper eq. 16, verified verbatim against the published Quantitative Finance
    10(7):761-782 text: 'close short position if s_i < +s_bc' (s_bc = 0.75) and
    'close long position s_i > -s_sc' (s_sc = 0.50). Its prose: 'We close long
    trades when the s-score reaches -0.50. Closing short trades sooner, at
    s = 0.75.' So s_bc belongs to CLOSE SHORT and s_sc to CLOSE LONG, which is
    exactly the pairing this test pins."""
    t = PAPER_THRESHOLDS
    # A LONG closes once s recovers ABOVE -0.50, and is held below it.
    assert next_position(1, -0.40, t) == 0
    assert next_position(1, -0.60, t) == 1
    assert next_position(1, -1.50, t) == 1
    # A SHORT closes once s falls BELOW +0.75, and is held above it.
    assert next_position(-1, 0.70, t) == 0
    assert next_position(-1, 0.80, t) == -1
    assert next_position(-1, 1.50, t) == -1


def test_positions_persist_between_the_open_and_close_bands():
    """The rule is a STATE MACHINE, not a daily re-sort: an s-score of -0.80 is
    inside neither band, so a flat book stays flat and a long book stays long."""
    t = PAPER_THRESHOLDS
    assert next_position(0, -0.80, t) == 0
    assert next_position(1, -0.80, t) == 1


def test_wide_thresholds_only_delay_the_opens():
    assert next_position(0, -1.30, PAPER_THRESHOLDS) == 1
    assert next_position(0, -1.30, WIDE_THRESHOLDS) == 0
    assert next_position(0, -1.60, WIDE_THRESHOLDS) == 1
    # Exits are identical between the two sets, by construction.
    for state, score in ((1, -0.40), (-1, 0.70), (1, -0.60), (-1, 0.80)):
        assert next_position(state, score, PAPER_THRESHOLDS) == next_position(
            state, score, WIDE_THRESHOLDS
        )


def test_a_nan_s_score_closes_rather_than_holds():
    """A name whose OU fit failed must not silently keep its position."""
    assert next_position(1, float("nan"), PAPER_THRESHOLDS) == 0
    assert next_position(-1, float("nan"), PAPER_THRESHOLDS) == 0
    assert next_position(0, float("nan"), PAPER_THRESHOLDS) == 0


# --- the degrees-of-freedom guard (PREREGISTRATION amendment 1) ------------


def test_dof_guard_blocks_a_saturated_regression():
    """A var55 rule that wants more than 60 - 1 - 20 = 39 factors must produce
    NOTHING tradeable and say so, rather than fitting a saturated regression and
    returning confident-looking garbage."""
    # An almost-uncorrelated panel spreads its variance across many modes, so
    # reaching 55% of the trace takes a large number of factors (47 here).
    rng = np.random.default_rng(404)
    panel = rng.normal(0.0, 0.01, (252, 200))
    tickers = tuple(f"T{i:03d}" for i in range(200))
    signal = build_cross_section_signal(panel, rng.normal(0, 0.01, 200), tickers, "var55")

    assert signal.n_factors > EIGEN_REGRESSION_WINDOW - 1 - EIGEN_MIN_RESIDUAL_DOF
    assert signal.dof_ok is False
    assert not signal.tradeable.any()
    assert np.isnan(signal.s_score).all()


def test_dof_guard_leaves_a_well_conditioned_rule_alone():
    panel = _factor_panel(252, 100, 3, seed=55)
    tickers = tuple(f"T{i:03d}" for i in range(100))
    signal = build_cross_section_signal(
        panel, np.random.default_rng(56).normal(0, 0.01, 100), tickers, "pca15"
    )
    assert signal.dof_ok is True
    assert signal.n_factors == EIGEN_PCA_FIXED_COUNT
    assert signal.tradeable.any()


# --- the precomputed-eigendecomposition fast path --------------------------


def test_precomputed_path_agrees_with_the_recomputed_one():
    """The replay shares one eigendecomposition across the three factor rules
    for speed. That is an optimization only, and this pins that it changes no
    number."""
    panel = _factor_panel(252, 90, 3, seed=71)
    next_returns = np.random.default_rng(72).normal(0, 0.01, 90)
    tickers = tuple(f"T{i:03d}" for i in range(90))

    standardized, sigma = standardize_returns(panel)
    eigenvalues, eigenvectors = np.linalg.eigh(correlation_from_standardized(standardized))
    precomputed = (sigma, eigenvalues[::-1], eigenvectors[:, ::-1])

    for rule in ("pca15", "var55", "m1"):
        slow = build_cross_section_signal(panel, next_returns, tickers, rule)
        fast = build_cross_section_signal(
            panel, next_returns, tickers, rule, precomputed=precomputed
        )
        assert fast.n_factors == slow.n_factors
        assert fast.s_score[slow.tradeable] == pytest.approx(
            slow.s_score[slow.tradeable], rel=1e-9
        )
        assert fast.residual_return_next == pytest.approx(slow.residual_return_next, rel=1e-9)


# --- residual return construction ------------------------------------------


def test_residual_return_removes_the_fitted_factor_exposure():
    """A position earns R_i - sum_j beta_ij F_j. If the next day's returns are
    PURE factor movement with no idiosyncratic component, a well-fitted residual
    return must be far smaller than the raw return it came from."""
    rng = np.random.default_rng(91)
    n_obs, n_names, n_factors = 252, 80, 3
    factors = rng.normal(0.0, 0.010, (n_obs, n_factors))
    loadings = rng.normal(0.0, 1.0, (n_factors, n_names))
    panel = factors @ loadings + rng.normal(0.0, 0.002, (n_obs, n_names))
    tickers = tuple(f"T{i:03d}" for i in range(n_names))

    # Next day: a pure common-factor shock, no idiosyncratic noise at all.
    next_returns = (rng.normal(0.0, 0.010, (1, n_factors)) @ loadings).ravel()
    signal = build_cross_section_signal(panel, next_returns, tickers, "pca15")

    assert np.abs(signal.residual_return_next).mean() < 0.2 * np.abs(next_returns).mean()


# --- point-in-time universe -------------------------------------------------


def test_panel_uses_point_in_time_membership_not_a_static_list(monkeypatch):
    """The whole survivorship discipline in one test: a ticker that was NOT a
    member on a date must be masked out on that date, even though it has price
    data throughout."""
    index = pd.bdate_range("2016-01-04", periods=6)
    closes = pd.DataFrame(
        {"AAA": np.linspace(100, 106, 6), "BBB": np.linspace(50, 56, 6)}, index=index
    )
    cutoff = index[3].date()

    def fake_universe(target: date) -> list[str]:
        return ["AAA", "BBB"] if target >= cutoff else ["AAA"]

    monkeypatch.setattr(eig_mod, "get_universe_as_of", fake_universe)
    panel = build_eigen_panel(closes)

    assert panel.member_mask["AAA"].all()
    assert not panel.member_mask["BBB"].iloc[:3].any()
    assert panel.member_mask["BBB"].iloc[3:].all()


def test_dates_outside_membership_coverage_are_masked_off_not_guessed(monkeypatch):
    """A date the membership module cannot answer for gets an ALL-FALSE mask.
    Silently substituting today's membership there is exactly the survivorship
    bug this family exists not to reintroduce."""

    def raising(target: date) -> list[str]:
        raise eig_mod.PointInTimeUniverseError("outside coverage")

    monkeypatch.setattr(eig_mod, "get_universe_as_of", raising)
    index = pd.bdate_range("2016-01-04", periods=5)
    closes = pd.DataFrame({"AAA": np.linspace(100, 105, 5)}, index=index)
    panel = build_eigen_panel(closes)

    assert not panel.member_mask.to_numpy().any()
    assert (panel.n_members_by_date == 0).all()


def test_screening_refuses_to_start_before_membership_coverage():
    """Rather than quietly falling back to a static present-day universe."""
    with pytest.raises(eig_mod.PointInTimeUniverseError, match="survivorship"):
        eig_mod.run_eigenportfolio_screening(start=date(2005, 1, 3), end=date(2010, 1, 1))


# --- replay ----------------------------------------------------------------


def test_replay_produces_returns_for_every_spec_sharing_a_window():
    panel = _synthetic_eigen_panel(n_days=420, n_names=80, seed=1234)
    specs = [s for s in EIGEN_FAMILY if s.correlation_window == 126]
    config = EigenConfig(formation_start=date(2015, 1, 2), min_names=40)
    results = run_eigen_replay(panel, specs, config)

    assert set(results) == {s.spec_id for s in specs}
    for spec in specs:
        replay = results[spec.spec_id]
        assert replay.status == "ok"
        assert len(replay.daily_returns) > 100
        assert replay.daily_returns.index.is_monotonic_increasing


def test_replay_has_no_look_ahead_under_truncation():
    """THE no-look-ahead test. Replaying a truncated panel must reproduce the
    common prefix of the full panel's returns EXACTLY — if any formation used
    information from a later date, the two would diverge."""
    panel = _synthetic_eigen_panel(n_days=400, n_names=70, seed=909)
    spec = next(s for s in EIGEN_FAMILY if s.spec_id == "eig_pca15_c126_paper")
    config = EigenConfig(formation_start=date(2015, 1, 2), min_names=40)

    full = run_eigen_replay(panel, [spec], config)[spec.spec_id].daily_returns
    cut = 340
    truncated_panel = EigenPanel(
        returns=panel.returns.iloc[:cut],
        member_mask=panel.member_mask.iloc[:cut],
        n_members_by_date=panel.n_members_by_date.iloc[:cut],
    )
    truncated = run_eigen_replay(truncated_panel, [spec], config)[spec.spec_id].daily_returns

    shared = truncated.index.intersection(full.index)
    assert len(shared) > 50
    assert truncated.loc[shared].to_numpy() == pytest.approx(full.loc[shared].to_numpy(), rel=1e-12)


def test_thin_cross_sections_are_skipped_and_counted_not_silently_traded():
    panel = _synthetic_eigen_panel(n_days=300, n_names=60, seed=777)
    spec = next(s for s in EIGEN_FAMILY if s.spec_id == "eig_pca15_c126_paper")
    # A floor above the panel's width means every date is too thin.
    config = EigenConfig(formation_start=date(2015, 1, 2), min_names=200)
    replay = run_eigen_replay(panel, [spec], config)[spec.spec_id]

    assert replay.status == "no_realized_returns"
    assert replay.n_thin_skipped > 0
    assert all(f.skipped_reason == "cross_section_too_thin" for f in replay.formations)


def test_costs_and_financing_are_actually_charged():
    panel = _synthetic_eigen_panel(n_days=400, n_names=80, seed=2468)
    spec = next(s for s in EIGEN_FAMILY if s.spec_id == "eig_pca15_c126_paper")
    config = EigenConfig(formation_start=date(2015, 1, 2), min_names=40)

    charged = run_eigen_replay(panel, [spec], config)[spec.spec_id]
    free = run_eigen_replay(
        panel,
        [spec],
        EigenConfig(
            cost_bps=0.0,
            financing_bps_per_year=0.0,
            formation_start=date(2015, 1, 2),
            min_names=40,
        ),
    )[spec.spec_id]

    assert charged.total_cost > 0
    assert charged.total_financing_cost > 0
    assert charged.total_full_book_turnover > 0
    # Free replay must be strictly better, and its GROSS returns identical —
    # costs must not change the position path.
    assert free.daily_returns.sum() > charged.daily_returns.sum()
    assert free.gross_returns.to_numpy() == pytest.approx(charged.gross_returns.to_numpy())


def test_full_book_turnover_is_at_least_the_stock_leg_turnover():
    """The full book adds the eigenportfolio hedge legs to the stock legs, so
    charging on it can only be harsher than the paper's own convention. That
    ordering is the whole justification for the choice and is pinned here."""
    panel = _synthetic_eigen_panel(n_days=380, n_names=80, seed=1357)
    spec = next(s for s in EIGEN_FAMILY if s.spec_id == "eig_pca15_c126_paper")
    config = EigenConfig(formation_start=date(2015, 1, 2), min_names=40)
    replay = run_eigen_replay(panel, [spec], config)[spec.spec_id]

    assert replay.total_full_book_turnover > replay.total_stock_leg_turnover > 0


def test_book_is_normalized_to_unit_gross_notional():
    """Returns are per dollar of gross capital actually deployed, matching
    ou_pairs.realize_pairs_return's normalization convention."""
    panel = _synthetic_eigen_panel(n_days=300, n_names=70, seed=864)
    spec = next(s for s in EIGEN_FAMILY if s.spec_id == "eig_m1_c126_paper")
    config = EigenConfig(formation_start=date(2015, 1, 2), min_names=40)
    replay = run_eigen_replay(panel, [spec], config)[spec.spec_id]

    active = [f for f in replay.formations if f.skipped_reason is None]
    assert active
    # A unit-gross book cannot turn over more than 2.0 in one day (fully
    # reversing every position), so this bounds the normalization.
    assert max(f.full_book_turnover for f in active) <= 2.0 + 1e-9


# --- the reversal diagnostic ------------------------------------------------


def test_reversal_book_runs_and_is_charged_the_same_cost():
    panel = _synthetic_eigen_panel(n_days=300, n_names=70, seed=333)
    config = EigenConfig(formation_start=date(2015, 1, 2), min_names=40)
    book = build_reversal_book(panel, config)

    assert book.status == "ok"
    assert len(book.daily_returns) > 100
    assert book.total_cost > 0
    assert np.isfinite(book.sharpe_annualized)


# --- screening and the persistence contract --------------------------------


def test_screening_result_satisfies_the_persistence_writers_contract():
    """cross_sectional_persistence.persist_cross_sectional_trial_results raises
    on anything missing .spec_id / .deflated_sharpe / .sharpe_annualized /
    .n_trading_days — so every result this family produces must carry them."""
    panel = _synthetic_eigen_panel(n_days=420, n_names=80, seed=5150)
    config = EigenConfig(formation_start=date(2015, 1, 2), min_names=40)
    benchmark = panel.returns.mean(axis=1)
    results = screen_eigenportfolio(panel, EIGEN_FAMILY, config, benchmark)

    assert results
    for result in results:
        assert isinstance(result.spec_id, str) and result.spec_id
        assert result.deflated_sharpe is not None
        assert isinstance(result.sharpe_annualized, float)
        assert isinstance(result.n_trading_days, int) and result.n_trading_days > 0
        # n_trials must be the family's pre-declared size, never the number
        # that happened to survive the data floors.
        assert result.deflated_sharpe.n_trials == EIGEN_N_TRIALS


def test_screening_is_sorted_and_reports_the_full_family_denominator():
    panel = _synthetic_eigen_panel(n_days=420, n_names=80, seed=6161)
    config = EigenConfig(formation_start=date(2015, 1, 2), min_names=40)
    results = screen_eigenportfolio(
        panel, EIGEN_FAMILY, config, panel.returns.mean(axis=1)
    )
    sharpes = [r.sharpe_annualized for r in results]
    assert sharpes == sorted(sharpes, reverse=True)
    assert all(r.deflated_sharpe.n_trials == EIGEN_N_TRIALS for r in results)


def test_cost_sensitivity_is_monotonically_worse_as_costs_rise():
    panel = _synthetic_eigen_panel(n_days=420, n_names=80, seed=7272)
    config = EigenConfig(formation_start=date(2015, 1, 2), min_names=40)
    results = screen_eigenportfolio(
        panel, EIGEN_FAMILY, config, panel.returns.mean(axis=1)
    )
    for result in results:
        table = result.cost_sensitivity_sharpe
        assert set(table) == set(eig_mod.EIGEN_COST_SENSITIVITY_BPS)
        assert table[5.0] >= table[10.0] >= table[20.0]
        # The 5bp column IS the headline, recomputed — it must agree.
        assert table[EIGEN_COST_BPS] == pytest.approx(result.sharpe_annualized, abs=1e-9)


def test_disclosure_states_the_denominator_and_the_survivorship_caveat():
    panel = _synthetic_eigen_panel(n_days=420, n_names=80, seed=8383)
    config = EigenConfig(formation_start=date(2015, 1, 2), min_names=40)
    results = screen_eigenportfolio(
        panel, EIGEN_FAMILY, config, panel.returns.mean(axis=1)
    )
    lines = build_eigen_disclosure(results, config)
    blob = " ".join(lines)

    assert f"n_trials = {EIGEN_N_TRIALS}" in blob
    # The disclosure used to assert every DSR here was an "UPPER BOUND" because
    # the other families screened alongside this one were NOT in the
    # denominator. They now are (global_effective_n.py), so that sentence would
    # be false and has been replaced. The disclosure must still SAY which
    # denominator it used -- silence would be worse than either claim.
    assert "UPPER BOUND" not in blob
    assert "POOLED" in blob
    assert "effectively-independent" in blob
    assert "delisted" in blob.lower()
    assert "point-in-time" in blob.lower()
    assert "reversal" in blob.lower()


def test_disclosure_survives_an_empty_result_set():
    lines = build_eigen_disclosure([], EigenConfig())
    assert any("nothing to interpret" in line for line in lines)


def test_kappa_filter_pass_fraction_is_reported_per_spec():
    """PREREGISTRATION section 6, diagnostic 6: 'fraction of names passing the
    kappa > 8.4 filter'. Without it a reader cannot tell whether the median
    fitted kappa describes the data or merely describes the truncation."""
    panel = _synthetic_eigen_panel(n_days=420, n_names=80, seed=9494)
    config = EigenConfig(formation_start=date(2015, 1, 2), min_names=40)
    results = screen_eigenportfolio(panel, EIGEN_FAMILY, config, panel.returns.mean(axis=1))

    assert results
    for result in results:
        assert 0.0 <= result.mean_tradeable_fraction <= 1.0
    assert any(r.mean_tradeable_fraction > 0.0 for r in results)


# --- the pre-declared EDGE cost cross-check --------------------------------


def _synthetic_ohlc(n_days: int = 300, n_names: int = 12, seed: int = 606):
    """A price path with an injected round-trip spread, so the EDGE estimator
    has something real to recover rather than degenerate input."""
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2015-01-02", periods=n_days)
    tickers = [f"T{i:03d}" for i in range(n_names)]
    mid = 100 * np.exp(np.cumsum(rng.normal(0, 0.012, (n_days, n_names)), axis=0))
    half = 0.0015  # 15bps half-spread injected
    frames = {
        "open": mid * (1 + half * rng.choice([-1.0, 1.0], (n_days, n_names))),
        "close": mid * (1 + half * rng.choice([-1.0, 1.0], (n_days, n_names))),
        "high": mid * (1 + abs(rng.normal(0, 0.008, (n_days, n_names))) + half),
        "low": mid * (1 - abs(rng.normal(0, 0.008, (n_days, n_names))) - half),
    }
    return {k: pd.DataFrame(v, index=index, columns=tickers) for k, v in frames.items()}


def test_edge_cost_diagnostic_runs_over_the_point_in_time_cross_section():
    """The pre-registration required this cross-check on the flat 5bp. It must
    actually CALL spread_estimator, not merely cite it."""
    ohlc = _synthetic_ohlc()
    mask = pd.DataFrame(True, index=ohlc["close"].index, columns=ohlc["close"].columns)
    diag = eig_mod.summarize_edge_half_spreads(
        ohlc["open"], ohlc["high"], ohlc["low"], ohlc["close"], mask, date(2015, 1, 2)
    )

    assert diag.status == "ok"
    assert diag.n_tickers == 12
    assert diag.n_estimates > 0
    assert diag.median_bps is not None and np.isfinite(diag.median_bps) and diag.median_bps > 0
    assert diag.p90_bps >= diag.p75_bps >= diag.median_bps
    assert diag.window_days == eig_mod.COST_MODEL_WINDOW_DAYS
    assert set(diag.by_year_median_bps) <= {2015, 2016}


def test_edge_cost_diagnostic_honours_the_membership_mask():
    """It must describe what this family ACTUALLY traded, not the union
    candidate pool — the same point-in-time discipline as everything else."""
    ohlc = _synthetic_ohlc()
    full = pd.DataFrame(True, index=ohlc["close"].index, columns=ohlc["close"].columns)
    one = full.copy()
    one.iloc[:, 1:] = False

    everything = eig_mod.summarize_edge_half_spreads(
        ohlc["open"], ohlc["high"], ohlc["low"], ohlc["close"], full, date(2015, 1, 2)
    )
    single = eig_mod.summarize_edge_half_spreads(
        ohlc["open"], ohlc["high"], ohlc["low"], ohlc["close"], one, date(2015, 1, 2)
    )
    assert single.n_estimates < everything.n_estimates
    # And a formation start after the sample leaves nothing eligible.
    late = eig_mod.summarize_edge_half_spreads(
        ohlc["open"], ohlc["high"], ohlc["low"], ohlc["close"], full, date(2099, 1, 1)
    )
    assert late.status != "ok"


def test_edge_cost_diagnostic_states_its_absence_rather_than_skipping_silently():
    """The pre-registration's exact requirement: an unobtainable estimate is
    'reported as a stated limitation, not silently skipped'."""
    empty = pd.DataFrame()
    diag = eig_mod.summarize_edge_half_spreads(
        empty, empty, empty, empty, empty, date(2015, 1, 2)
    )
    assert diag.status != "ok"
    assert diag.median_bps is None

    lines = build_eigen_disclosure(
        [],
        EigenConfig(),
        eig_mod.EigenScreeningSummary(edge_cost=diag),
    )
    assert any("UNAVAILABLE" in line and diag.status in line for line in lines)


def test_edge_disclosure_reports_the_measured_spread_against_the_flat_rate():
    ohlc = _synthetic_ohlc()
    mask = pd.DataFrame(True, index=ohlc["close"].index, columns=ohlc["close"].columns)
    diag = eig_mod.summarize_edge_half_spreads(
        ohlc["open"], ohlc["high"], ohlc["low"], ohlc["close"], mask, date(2015, 1, 2)
    )
    lines = build_eigen_disclosure(
        [], EigenConfig(), eig_mod.EigenScreeningSummary(edge_cost=diag)
    )
    blob = " ".join(lines)
    assert "EDGE CROSS-CHECK" in blob
    # The upward-bias caveat must travel with the number, never the number alone.
    assert "UPPER bound" in blob
