"""Validation of continuous-time Kelly sizing against KNOWN correct answers.

SAME POSTURE AS test_hrp_optimizer.py AND test_rmt_denoising.py, for the
same reason: a hand-rolled estimator in this codebase once passed every
self-consistency test its author wrote and was still wrong, because no test
ever fed it an input whose right answer was known independently of the
code. Every load-bearing test here therefore checks against something the
implementation could not have produced:

  1. THE HJB OBJECTIVE ITSELF. test_closed_form_maximizes_the_merton_hjb_maximand
     builds Merton's own maximand from [M69] eq. (58) with the CRRA trial
     solution substituted in, and asserts (a) that Merton's maximand is at
     least as high at the module's closed form as at whatever point scipy's
     optimizer finds, and (b) that the numerical argmax agrees to 1e-6.
     That is the derivation being re-run numerically rather than
     re-asserted; if the module's formula were wrong by any factor, a
     general-purpose optimizer would beat it and (a) would fail.

  2. TWO PUBLISHED WORKED EXAMPLES, checked against the sources' own printed
     numbers: [T06] Example 7.2 (S&P 500, f* = 2.2222) and [Z11] section
     1.4 footnote 2 (US equities 1926-2001, x = 1.5288). The latter doubles
     as a disambiguation of a formula whose exponent the PDF text layer lost
     — the arithmetic only works for sigma^2, not sigma.

  3. TWO PUBLISHED CLOSED FORMS FOR THE FRACTIONAL CASE: [T06] eq. (7.6)'s
     growth ratio c(2 - c) and [T06] eq. (7.13)'s ruin exponent
     x^(2/c - 1). The second is checked by SIMULATION against the analytic
     value, which validates the Monte Carlo machinery itself.

  4. A HAND CALCULATION on a 2x2 whose inverse is written out in the test.

  5. THE ESTIMATION-RISK CLAIM, MEASURED, NOT ASSERTED. The Monte Carlo is
     run at reduced trial counts and the module docstring's two headline
     findings are re-asserted: that half Kelly beats full Kelly on median
     growth under estimation noise, and that the empirical growth-optimal
     fraction lands where the analytic c* says it should.

  6. WIRING, BIT-EQUALITY. With denoise left alone, the from-returns path
     is asserted float64-bit-identical to the hand-assembled moments path.

Reference values are computed in the tests from first principles wherever
possible (np.linalg.inv rather than the module's np.linalg.solve, explicit
sums rather than the module's vectorized forms), so the tests are not
merely re-running the implementation.
"""

import numpy as np
import pandas as pd
import pytest
from scipy.optimize import minimize

from app.services.risk.errors import InsufficientHistoryError
from app.services.risk.hrp_optimizer import compute_hrp_weights_from_returns
from app.services.risk.kelly_sizing import (
    DEFAULT_KELLY_FRACTION,
    ZERO_GROWTH_KELLY_MULTIPLE,
    compute_kelly_leverage_from_returns,
    compute_kelly_sizing_from_returns,
    estimation_risk_monte_carlo,
    full_kelly_weights,
    growth_optimal_kelly_fraction,
    growth_rate,
    kelly_leverage_for_weights,
    kelly_weights,
    max_sharpe_ratio,
    simulate_wealth_paths,
)
from app.services.risk.volatility import TRADING_DAYS_PER_YEAR

# --------------------------------------------------------------------------
# Fixtures: a ground-truth (mu, Sigma, r) with a KNOWN answer.
# --------------------------------------------------------------------------

ASSETS_2 = ["X", "Y"]
MU_2 = pd.Series([0.10, 0.14], index=ASSETS_2)
# Deliberately written out entry by entry so the hand calculation in
# test_two_asset_hand_calculation can quote it.
COV_2 = pd.DataFrame(
    [[0.04, 0.012], [0.012, 0.09]], index=ASSETS_2, columns=ASSETS_2
)
RF_2 = 0.03


def _synthetic(n, mu_lo, mu_hi, vol_lo, vol_hi, rho):
    assets = [f"A{i}" for i in range(n)]
    mu = pd.Series(np.linspace(mu_lo, mu_hi, n), index=assets)
    vols = np.linspace(vol_lo, vol_hi, n)
    corr = np.full((n, n), rho)
    np.fill_diagonal(corr, 1.0)
    cov = pd.DataFrame(corr * np.outer(vols, vols), index=assets, columns=assets)
    return mu, cov


def _returns_frame(n=6, t=800, seed=7):
    mu, cov = _synthetic(n, 0.06, 0.16, 0.14, 0.28, 0.25)
    rng = np.random.default_rng(seed)
    chol = np.linalg.cholesky(cov.to_numpy() / TRADING_DAYS_PER_YEAR)
    sample = mu.to_numpy() / TRADING_DAYS_PER_YEAR + rng.standard_normal((t, n)) @ chol.T
    return pd.DataFrame(sample, columns=list(mu.index))


# ==========================================================================
# 1. THE HJB OBJECTIVE — the derivation, re-run numerically.
# ==========================================================================


@pytest.mark.parametrize("gamma_merton", [0.0, -1.0, -3.0, 0.5, -9.0])
def test_closed_form_maximizes_the_merton_hjb_maximand(gamma_merton):
    """[M69] eq. (58)'s maximand, with [M69] eq. (22)'s CRRA trial solution
    J(W) = W^gamma/gamma substituted in and consumption dropped, is

        Phi(w) = J'(W)[w'(alpha - r) + r]W + (1/2) J''(W) w' Omega w W^2

    With J' = W^(gamma-1) and J'' = (gamma-1)W^(gamma-2) this is
    W^gamma * ( [w'(alpha-r) + r] + (1/2)(gamma-1) w' Omega w ), whose
    maximizer is [M69] eq. (60): w* = (1/(1-gamma)) Omega^-1 (alpha - r).

    This test does NOT assume that. It hands Phi to scipy and checks the
    numerical argmax against the module's closed form. [M69]'s gamma is
    the exponent, so relative risk aversion is 1 - gamma; gamma = 0 is log
    utility / full Kelly.
    """
    mu, cov = _synthetic(5, 0.06, 0.15, 0.14, 0.26, 0.3)
    r = 0.035
    wealth = 3.7  # arbitrary; the maximizer must not depend on it
    omega = cov.to_numpy()
    excess = mu.to_numpy() - r

    def negative_phi(w):
        drift = float(w @ excess) + r
        quad = float(w @ omega @ w)
        j_prime = wealth ** (gamma_merton - 1.0)
        j_double = (gamma_merton - 1.0) * wealth ** (gamma_merton - 2.0)
        phi = j_prime * drift * wealth + 0.5 * j_double * quad * wealth**2
        return -phi

    numeric = minimize(negative_phi, np.zeros(5), method="BFGS", tol=1e-14).x

    risk_aversion = 1.0 - gamma_merton  # [M69]: "1 - gamma is Pratt's measure"
    closed_form = kelly_weights(mu, cov, r, kelly_fraction=1.0 / risk_aversion)
    expected = np.array([closed_form.weights[a] for a in mu.index])

    # THE PRIMARY ASSERTION, and the one that does not depend on any
    # optimizer's stopping rule: Merton's own maximand is at least as high
    # at the closed form as at whatever point a general-purpose optimizer
    # found. If eq. (60) were wrong by any factor, BFGS would beat it.
    assert -negative_phi(expected) >= -negative_phi(numeric) - 1e-13

    # And the argmax agrees. 1e-6 is BFGS's finite-difference convergence
    # floor on this objective (it reports "precision loss" while sitting
    # ~1e-7 away and does not improve with tighter tol), not a discrepancy
    # in the formula. Seven significant figures is far more than enough to
    # distinguish (1/(1-gamma)) Omega^-1(alpha-r) from any other scaling.
    np.testing.assert_allclose(numeric, expected, rtol=0, atol=1e-6)
    np.testing.assert_allclose(
        numeric / np.linalg.norm(numeric), expected / np.linalg.norm(expected),
        rtol=0, atol=1e-7,
    )


def test_merton_maximand_reduces_to_thorp_growth_rate_at_log_utility():
    """At [M69]'s gamma = 0 (log utility), Phi(w)/W^gamma above is exactly
    r + w'(alpha - r) - (1/2) w' Omega w, which is [T06] section 8.4's
    g_inf = m - s^2/2. The two independent derivations are the same
    function, not merely the same answer."""
    mu, cov = _synthetic(4, 0.05, 0.13, 0.12, 0.24, 0.2)
    r = 0.02
    rng = np.random.default_rng(3)
    omega = cov.to_numpy()
    excess = mu.to_numpy() - r
    for _ in range(20):
        w = rng.normal(size=4) * 2.0
        merton_phi = (float(w @ excess) + r) + 0.5 * (0.0 - 1.0) * float(w @ omega @ w)
        assert merton_phi == pytest.approx(growth_rate(w, mu, cov, r), rel=0, abs=1e-14)


def test_first_order_condition_scalar_is_one_over_risk_aversion():
    """[M71] footnote 16 defines the whole preference dependence as the
    scalar m = -J_W/(W J_WW). For the CRRA trial solution J = W^g/g that
    scalar is 1/(1-g), i.e. one over relative risk aversion. Checked by
    numerical differentiation rather than by algebra."""
    wealth = 2.3
    # h = 1e-4 balances the central second difference's truncation error
    # (~h^2) against its roundoff amplification (~eps/h^2); at 1e-5 the
    # latter alone is ~1e-6 relative and the test would be measuring
    # float noise rather than the identity.
    h = 1e-4
    for gamma in (0.0, -1.0, -3.0, 0.5):

        def j(w, g=gamma):
            return w**g / g if g != 0 else np.log(w)

        j_w = (j(wealth + h) - j(wealth - h)) / (2 * h)
        j_ww = (j(wealth + h) - 2 * j(wealth) + j(wealth - h)) / h**2
        m = -j_w / (wealth * j_ww)
        assert m == pytest.approx(1.0 / (1.0 - gamma), rel=1e-5)


# ==========================================================================
# 2. GROUND TRUTH: the closed form against independent calculations.
# ==========================================================================


def test_two_asset_hand_calculation():
    """Sigma = [[0.04, 0.012], [0.012, 0.09]], det = 0.04*0.09 - 0.012^2
    = 0.0036 - 0.000144 = 0.003456. Sigma^-1 = (1/det)[[0.09, -0.012],
    [-0.012, 0.04]]. Excess = (0.07, 0.11).

        w_X = (0.09*0.07 - 0.012*0.11)/0.003456
            = (0.0063 - 0.00132)/0.003456 = 0.00498/0.003456
        w_Y = (-0.012*0.07 + 0.04*0.11)/0.003456
            = (-0.00084 + 0.0044)/0.003456 = 0.00356/0.003456

    Written out here as literal arithmetic so the expected values do not
    come from any matrix routine."""
    det = 0.04 * 0.09 - 0.012 * 0.012
    assert det == pytest.approx(0.003456, rel=0, abs=1e-15)
    expected_x = (0.09 * 0.07 - 0.012 * 0.11) / det
    expected_y = (-0.012 * 0.07 + 0.04 * 0.11) / det
    assert expected_x == pytest.approx(1.4409722222222223, rel=1e-12)
    assert expected_y == pytest.approx(1.0300925925925926, rel=1e-12)

    w = full_kelly_weights(MU_2, COV_2, RF_2)
    assert w["X"] == pytest.approx(expected_x, rel=0, abs=1e-12)
    assert w["Y"] == pytest.approx(expected_y, rel=0, abs=1e-12)


@pytest.mark.parametrize("n", [2, 5, 12, 30])
def test_matches_explicit_matrix_inverse(n):
    """The module uses np.linalg.solve; this checks it against the literal
    np.linalg.inv(Sigma) @ (mu - r) that [M69] eq. (60) and [T06] eq. (8.2)
    are written as."""
    mu, cov = _synthetic(n, 0.04, 0.18, 0.10, 0.35, 0.28)
    r = 0.025
    expected = np.linalg.inv(cov.to_numpy()) @ (mu.to_numpy() - r)
    got = full_kelly_weights(mu, cov, r).to_numpy()
    np.testing.assert_allclose(got, expected, rtol=1e-10, atol=1e-12)


def test_diagonal_covariance_gives_per_asset_kelly():
    """[T06] section 8.4, verbatim: "When all the securities are
    uncorrelated, C is diagonal and we have f_i* = (m_i - r)/s_ii"."""
    assets = ["a", "b", "c"]
    mu = pd.Series([0.09, 0.12, 0.05], index=assets)
    variances = [0.04, 0.09, 0.01]
    cov = pd.DataFrame(np.diag(variances), index=assets, columns=assets)
    r = 0.02
    w = full_kelly_weights(mu, cov, r)
    for a, v, m in zip(assets, variances, mu):
        assert w[a] == pytest.approx((m - r) / v, rel=1e-12)


def test_full_kelly_growth_rate_is_r_plus_half_theta_squared():
    """[T06] eq. (8.2): g_inf(F*) = r + (F*)'C F*/2, and F*'CF* =
    (M-R)'C^-1(M-R) = theta^2. Both halves checked separately."""
    mu, cov = _synthetic(7, 0.05, 0.17, 0.12, 0.3, 0.22)
    r = 0.03
    res = kelly_weights(mu, cov, r, kelly_fraction=1.0)
    theta = max_sharpe_ratio(mu, cov, r)
    w = np.array([res.weights[a] for a in mu.index])
    quad = float(w @ cov.to_numpy() @ w)
    assert quad == pytest.approx(theta**2, rel=1e-10)
    assert res.growth_rate == pytest.approx(r + 0.5 * theta**2, rel=1e-10)
    assert res.growth_rate == pytest.approx(res.full_kelly_growth_rate, rel=1e-12)
    # And the identity used in the real-data section: at full Kelly the
    # portfolio's own volatility EQUALS theta.
    assert res.volatility == pytest.approx(theta, rel=1e-10)


def test_full_kelly_is_the_growth_rate_argmax():
    """Independent of any formula: brute-force the growth rate over
    perturbations of the closed-form weights and confirm nothing beats
    them. This is the 'standard quadratic maximization problem' [T06]
    section 8.4 says it is."""
    mu, cov = _synthetic(5, 0.05, 0.15, 0.13, 0.27, 0.2)
    r = 0.03
    star = full_kelly_weights(mu, cov, r).to_numpy()
    best = growth_rate(star, mu, cov, r)
    rng = np.random.default_rng(11)
    for _ in range(400):
        perturbed = star + rng.normal(scale=0.3, size=star.shape)
        assert growth_rate(perturbed, mu, cov, r) <= best + 1e-12
    numeric = minimize(
        lambda w: -growth_rate(w, mu, cov, r), np.zeros(5), method="BFGS", tol=1e-14
    ).x
    np.testing.assert_allclose(numeric, star, rtol=0, atol=1e-7)


# ==========================================================================
# 3. FRACTIONAL KELLY — exactness of the 1/gamma scaling.
# ==========================================================================


@pytest.mark.parametrize("c", [0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0])
def test_fractional_kelly_scales_exactly(c):
    """[Z11] p. 9's f = 1/R_R against [M69] eq. (60)'s 1/(1-gamma): in this
    unconstrained lognormal setting the two are the same algebra, so
    fractional weights are EXACTLY c times the full-Kelly weights, to
    float64 bit equality of the products (not merely to a tolerance)."""
    mu, cov = _synthetic(8, 0.04, 0.16, 0.11, 0.29, 0.31)
    r = 0.028
    full = kelly_weights(mu, cov, r, kelly_fraction=1.0)
    frac = kelly_weights(mu, cov, r, kelly_fraction=c)
    for a in mu.index:
        assert frac.weights[a] == full.full_kelly_weights[a] * c
    assert frac.risk_aversion == pytest.approx(1.0 / c, rel=1e-15)
    assert frac.gross_leverage == pytest.approx(c * full.gross_leverage, rel=1e-12)


def test_half_kelly_is_exactly_risk_aversion_two():
    """The task's specific question, answered on the record: half-Kelly
    weights ARE exactly half the full-Kelly weights here, because
    pi*(gamma) = (1/gamma) Sigma^-1(mu - r) is exactly linear in 1/gamma.
    Half Kelly == relative risk aversion 2 == [Z11] Table 1.1's -1/w."""
    half = kelly_weights(MU_2, COV_2, RF_2, kelly_fraction=0.5)
    full = kelly_weights(MU_2, COV_2, RF_2, kelly_fraction=1.0)
    assert half.risk_aversion == 2.0
    for a in ASSETS_2:
        assert half.weights[a] == full.weights[a] / 2.0
    assert DEFAULT_KELLY_FRACTION == 0.5


@pytest.mark.parametrize("c", [0.25, 0.5, 1.0, 1.5, 2.0])
def test_thorp_7_6_growth_ratio_c_times_two_minus_c(c):
    """[T06] eq. (7.6), r = 0: g_inf(c f*)/g_inf(f*) = c(2 - c). At
    c = 0.5 that is 0.75 — [T06] p. 415's "3/4 the growth rate"; at c = 2
    it is 0 — [Z11] p. 8's "growth rate of zero plus the risk-free rate"."""
    mu, cov = _synthetic(6, 0.05, 0.14, 0.12, 0.26, 0.2)
    r = 0.0
    star = full_kelly_weights(mu, cov, r)
    g_star = growth_rate(star, mu, cov, r)
    g_c = growth_rate(star * c, mu, cov, r)
    assert g_c / g_star == pytest.approx(c * (2.0 - c), rel=1e-10, abs=1e-12)


def test_double_kelly_growth_rate_returns_to_the_risk_free_rate():
    """[Z11] p. 8, verbatim: "the investor who wagers exactly twice this
    amount has a growth rate of zero plus the risk-free rate of interest".
    Checked at a NON-zero r, where the c(2-c) form does not directly
    apply."""
    r = 0.045
    star = full_kelly_weights(MU_2, COV_2, r)
    assert growth_rate(star * ZERO_GROWTH_KELLY_MULTIPLE, MU_2, COV_2, r) == pytest.approx(
        r, rel=0, abs=1e-14
    )


# ==========================================================================
# 4. PUBLISHED WORKED EXAMPLES.
# ==========================================================================


def test_ziemba_footnote_2_arithmetic_disambiguates_the_formula():
    """[Z11] section 1.4, footnote 2: US equities 1926-2001, mu_R = 0.102,
    sigma_R = 0.203, r = 0.039, "the Kelly strategy is x = 1.5288". The
    printed formula lost its exponent in the PDF text layer. Only
    (mu - r)/sigma^2 reproduces the printed number; (mu - r)/sigma does
    not. This test IS that disambiguation, kept so the reasoning is
    reproducible rather than asserted in prose."""
    mu_r, sigma_r, r = 0.102, 0.203, 0.039
    assert (mu_r - r) / sigma_r**2 == pytest.approx(1.5288, rel=0, abs=5e-5)
    assert (mu_r - r) / sigma_r == pytest.approx(0.3103, rel=0, abs=5e-5)

    # And the module reproduces it through its ordinary single-asset path.
    mu = pd.Series([mu_r], index=["EQ"])
    cov = pd.DataFrame([[sigma_r**2]], index=["EQ"], columns=["EQ"])
    assert full_kelly_weights(mu, cov, r)["EQ"] == pytest.approx(1.5288, rel=0, abs=5e-5)
    lev = kelly_leverage_for_weights({"EQ": 1.0}, mu, cov, r, kelly_fraction=1.0)
    assert lev.full_kelly_leverage == pytest.approx(1.5288, rel=0, abs=5e-5)


def test_thorp_example_7_2_sp500():
    """[T06] Example 7.2, p. 409: "m = .11, s = .15, r = .06" gives
    "f* = 2.2 (repeating)", g_inf(f*) = .11(repeating 5),
    Sdev(G_inf(f*)) = .3(repeating)."""
    m, s, r = 0.11, 0.15, 0.06
    mu = pd.Series([m], index=["SP"])
    cov = pd.DataFrame([[s**2]], index=["SP"], columns=["SP"])
    res = kelly_weights(mu, cov, r, kelly_fraction=1.0)
    assert res.weights["SP"] == pytest.approx(2.0 + 2.0 / 9.0, rel=1e-10)  # 2.222...
    assert res.growth_rate == pytest.approx(0.11 + 5.0 / 9.0 * 0.01, rel=1e-9)
    assert res.growth_rate == pytest.approx(0.1155555555, rel=0, abs=1e-9)
    assert res.volatility == pytest.approx(1.0 / 3.0, rel=1e-9)


def test_thorp_p407_unlevered_growth_rate():
    """[T06] p. 409: "With the usual unlevered f = 1 ... g_inf(1) =
    m - s^2/2 = .09875" for m = .11, s = .15."""
    mu = pd.Series([0.11], index=["SP"])
    cov = pd.DataFrame([[0.15**2]], index=["SP"], columns=["SP"])
    assert growth_rate(np.array([1.0]), mu, cov, 0.06) == pytest.approx(0.09875, rel=1e-12)


# ==========================================================================
# 5. INVARIANCES.
# ==========================================================================


@pytest.mark.parametrize("k", [1.0, 252.0, 1.0 / 252.0, 12.0])
def test_kelly_weights_are_time_scale_invariant(k):
    """Scaling mu, r and Sigma all by k leaves Sigma^-1(mu - r 1)
    unchanged, so daily and annualized inputs give the same weights. The
    same property HRP has for a different reason (see hrp_optimizer)."""
    base = full_kelly_weights(MU_2, COV_2, RF_2)
    scaled = full_kelly_weights(MU_2 * k, COV_2 * k, RF_2 * k)
    np.testing.assert_allclose(scaled.to_numpy(), base.to_numpy(), rtol=1e-11, atol=0)


@pytest.mark.parametrize("k", [0.5, 1.0, 3.0, 100.0])
def test_leverage_is_invariant_to_rescaling_the_direction(k):
    """lambda* = w'(mu-r)/(w'Sigma w) scales as 1/k when w scales by k, so
    the PRODUCT lambda* w — the actual position — is unchanged. Documented
    in kelly_leverage_for_weights' docstring; asserted here."""
    w = {"X": 0.6, "Y": 0.4}
    base = kelly_leverage_for_weights(w, MU_2, COV_2, RF_2, kelly_fraction=1.0)
    scaled = kelly_leverage_for_weights(
        {a: v * k for a, v in w.items()}, MU_2, COV_2, RF_2, kelly_fraction=1.0
    )
    assert scaled.full_kelly_leverage == pytest.approx(base.full_kelly_leverage / k, rel=1e-11)
    for a in w:
        assert scaled.scaled_weights[a] == pytest.approx(base.scaled_weights[a], rel=1e-11)
    assert scaled.growth_rate == pytest.approx(base.growth_rate, rel=1e-11)


def test_leverage_of_the_full_kelly_direction_is_exactly_one():
    """The sharpest consistency check between the two entry points: the
    full-Kelly vector is ALREADY optimally scaled, so asking
    kelly_leverage_for_weights how much of it to hold must answer 1."""
    mu, cov = _synthetic(6, 0.05, 0.16, 0.12, 0.28, 0.25)
    r = 0.03
    star = full_kelly_weights(mu, cov, r)
    lev = kelly_leverage_for_weights(star, mu, cov, r, kelly_fraction=1.0)
    assert lev.full_kelly_leverage == pytest.approx(1.0, rel=1e-10)
    assert lev.portfolio_sharpe == pytest.approx(max_sharpe_ratio(mu, cov, r), rel=1e-10)


def test_leverage_on_a_single_asset_equals_that_asset_s_kelly_weight():
    """A one-name direction must reduce to [T06] eq. (7.3)'s
    f* = (m - r)/s^2, with no reference to the other assets."""
    mu, cov = _synthetic(5, 0.06, 0.15, 0.13, 0.27, 0.4)
    r = 0.02
    direction = {a: (1.0 if a == "A2" else 0.0) for a in mu.index}
    lev = kelly_leverage_for_weights(direction, mu, cov, r, kelly_fraction=1.0)
    expected = (mu["A2"] - r) / cov.loc["A2", "A2"]
    assert lev.full_kelly_leverage == pytest.approx(expected, rel=1e-12)


def test_leverage_reports_zero_growth_and_negative_edge_honestly():
    """Nothing is clamped: a direction with negative expected excess return
    gets a negative lambda*, and zero_growth_leverage is 2 lambda*."""
    mu = pd.Series([0.01, 0.005], index=ASSETS_2)  # both below r
    lev = kelly_leverage_for_weights({"X": 0.5, "Y": 0.5}, mu, COV_2, 0.03, kelly_fraction=1.0)
    assert lev.full_kelly_leverage < 0
    assert lev.portfolio_sharpe < 0
    assert lev.zero_growth_leverage == pytest.approx(2.0 * lev.full_kelly_leverage, rel=1e-14)
    assert growth_rate(
        pd.Series([0.5, 0.5], index=ASSETS_2) * lev.zero_growth_leverage, mu, COV_2, 0.03
    ) == pytest.approx(0.03, rel=0, abs=1e-15)


# ==========================================================================
# 6. growth_optimal_kelly_fraction.
# ==========================================================================


def test_growth_optimal_fraction_mu_only_formula():
    """c* = theta^2/(theta^2 + N/T_years) — this module's own derivation.
    Checked against arithmetic written out here."""
    assert growth_optimal_kelly_fraction(
        0.64, 10, 5.0, include_covariance_penalty=False
    ) == pytest.approx(0.64 / (0.64 + 2.0), rel=1e-14)
    # Real-data configuration from the module docstring.
    assert growth_optimal_kelly_fraction(
        2.3142, 12, 1254 / TRADING_DAYS_PER_YEAR, include_covariance_penalty=False
    ) == pytest.approx(0.4897, rel=0, abs=5e-5)


def test_growth_optimal_fraction_kan_zhou_factor():
    """[P10] eq. (2.17): c* = [(T-N-1)(T-N-4)/(T(T-2))] (theta^2/(theta^2+N/T)).
    The bracket is spelled out here rather than imported from the module."""
    theta2, n, t = 2.3142, 12, 1254
    years = t / TRADING_DAYS_PER_YEAR
    bracket = ((t - n - 1) * (t - n - 4)) / (t * (t - 2))
    expected = bracket * theta2 / (theta2 + n / years)
    assert growth_optimal_kelly_fraction(theta2, n, years, n_obs=t) == pytest.approx(
        expected, rel=1e-14
    )
    assert bracket < 1.0  # the covariance penalty always shrinks further
    assert expected == pytest.approx(0.4792, rel=0, abs=5e-5)


def test_growth_optimal_fraction_edge_cases():
    assert growth_optimal_kelly_fraction(0.0, 5, 3.0, include_covariance_penalty=False) == 0.0
    # T <= N + 4 is [P10]'s own stated precondition.
    with pytest.raises(ValueError, match=r"T > N \+ 4"):
        growth_optimal_kelly_fraction(1.0, 20, 0.05, n_obs=22)
    with pytest.raises(ValueError, match="theta_squared"):
        growth_optimal_kelly_fraction(-1.0, 5, 3.0)
    with pytest.raises(ValueError, match="n_years"):
        growth_optimal_kelly_fraction(1.0, 5, 0.0)
    # More data -> less shrinkage; more assets -> more shrinkage.
    a = growth_optimal_kelly_fraction(0.5, 10, 5.0, include_covariance_penalty=False)
    b = growth_optimal_kelly_fraction(0.5, 10, 50.0, include_covariance_penalty=False)
    c = growth_optimal_kelly_fraction(0.5, 40, 5.0, include_covariance_penalty=False)
    assert a < b < 1.0
    assert c < a


# ==========================================================================
# 7. THE SIMULATOR, validated against [T06] eq. (7.13).
# ==========================================================================


@pytest.mark.parametrize("c", [0.5, 1.0, 1.5])
def test_simulator_reproduces_thorp_7_13_ruin_probability(c):
    """[T06] eq. (7.13): Prob(V(t, c f*)/V_0 <= x for some t) = x^(2/c - 1)
    for r = 0. Simulated here at a reduced path count; see the module
    docstring for the full 40,000-path table and for why every cell comes
    out slightly LOW (finite-horizon truncation of an 'ever' probability,
    demonstrated there by extending the horizon)."""
    m, s = 0.10, 0.20
    f_star = m / s**2
    f = c * f_star
    g = f * m - 0.5 * f**2 * s**2
    rng = np.random.default_rng(2026)
    n_paths, ppy, years = 6000, 252, 40
    horizon = years * ppy
    shocks = rng.standard_normal((n_paths, horizon))
    paths = simulate_wealth_paths(g, f * s, horizon, ppy, shocks)
    simulated = float((paths.min(axis=1) <= np.log(0.5)).mean())
    predicted = 0.5 ** (2.0 / c - 1.0)
    # Tolerance covers Monte Carlo error plus the documented downward
    # truncation bias, which is largest at c = 1.5.
    assert simulated <= predicted + 0.02
    assert simulated >= predicted - 0.06


def test_simulator_drift_and_diffusion_match_the_growth_rate():
    """simulate_wealth_paths must have drift exactly growth_rate() and
    diffusion exactly the portfolio volatility — otherwise the Monte Carlo
    is measuring something other than the closed form it is compared to."""
    rng = np.random.default_rng(5)
    ppy, horizon, n = 252, 252 * 30, 4000
    g, vol = 0.12, 0.25
    shocks = rng.standard_normal((n, horizon))
    paths = simulate_wealth_paths(g, vol, horizon, ppy, shocks)
    terminal_log = paths[:, -1]
    years = horizon / ppy
    assert terminal_log.mean() / years == pytest.approx(g, rel=0.05)
    assert terminal_log.std(ddof=1) / np.sqrt(years) == pytest.approx(vol, rel=0.05)


# ==========================================================================
# 8. THE ESTIMATION-RISK DEMONSTRATION, re-measured.
# ==========================================================================


def _config_a():
    return _synthetic(10, 0.07, 0.13, 0.16, 0.30, 0.35), 0.04


def _config_b():
    return _synthetic(5, 0.12, 0.20, 0.15, 0.25, 0.15), 0.04


def test_half_kelly_beats_full_kelly_under_estimation_noise():
    """THE LOAD-BEARING RESULT. Configuration B of the module docstring:
    with the SAME estimation noise and the SAME market paths, half Kelly
    beats full Kelly on the thing full Kelly is defined to maximize — the
    growth rate — and is far safer at the same time. Reduced to 1,500
    trials here; the docstring's table is at 4,000."""
    (mu, cov), r = _config_b()
    res = estimation_risk_monte_carlo(
        mu, cov, r, estimation_obs=2520, horizon_obs=1260,
        kelly_fractions=(0.5, 1.0), n_trials=1500, seed=12345,
    )
    half, full = res.rows[0], res.rows[1]
    assert half.kelly_fraction == 0.5 and full.kelly_fraction == 1.0
    assert half.median_growth_rate > full.median_growth_rate
    assert half.mean_growth_rate > full.mean_growth_rate
    assert half.prob_terminal_below_half < full.prob_terminal_below_half
    assert half.prob_max_drawdown_over_half < full.prob_max_drawdown_over_half
    # And both are far below the oracle: estimation error costs more than
    # the choice of c ever recovers.
    assert res.oracle_growth_rate > half.median_growth_rate
    assert res.true_max_sharpe == pytest.approx(1.0530, rel=0, abs=5e-4)


def test_full_kelly_is_ruinous_on_a_realistic_universe():
    """Configuration A: 10 assets, 5 years of daily data. The docstring
    reports a median terminal wealth of 0.016x at full Kelly. Asserted
    here as 'catastrophic' rather than to four decimals, so the test does
    not become a snapshot of the RNG."""
    (mu, cov), r = _config_a()
    res = estimation_risk_monte_carlo(
        mu, cov, r, estimation_obs=1260, horizon_obs=1260,
        kelly_fractions=(0.1, 1.0), n_trials=1500, seed=12345,
    )
    tenth, full = res.rows[0], res.rows[1]
    assert full.median_terminal_wealth < 0.1
    assert full.prob_growth_below_risk_free > 0.99
    assert full.median_growth_rate < -0.5
    # A tenth of Kelly, on the same noise, is comfortably positive.
    assert tenth.median_growth_rate > r
    assert tenth.median_terminal_wealth > 1.1
    assert res.oracle_growth_rate == pytest.approx(r + 0.4183**2 / 2, rel=0, abs=1e-3)


@pytest.mark.parametrize("config,grid,tol", [("a", 0.02, 0.03), ("b", 0.05, 0.09)])
def test_empirical_growth_optimal_fraction_matches_the_analytic_prediction(config, grid, tol):
    """INDEPENDENT NUMERICAL VERIFICATION of a formula transcribed from a
    SECONDARY source ([P10] eq. 2.17, attributed to Kan and Zhou 2007,
    whose own PDF 404'd this session). The Monte Carlo's empirical argmax
    of MEAN true growth is compared to the analytic c*.

    Note the prediction being tested is really the shared
    theta^2/(theta^2 + N/T) core; at these T the [P10] covariance factor
    moves c* by under 2%, well inside the grid resolution."""
    if config == "a":
        (mu, cov), r = _config_a()
        t_est = 1260
        fractions = tuple(np.round(np.arange(grid, 0.4, grid), 6))
    else:
        (mu, cov), r = _config_b()
        t_est = 2520
        fractions = tuple(np.round(np.arange(0.3, 1.05, grid), 6))

    res = estimation_risk_monte_carlo(
        mu, cov, r, estimation_obs=t_est, horizon_obs=252,
        kelly_fractions=fractions, n_trials=1500, seed=12345,
    )
    means = np.array([row.mean_growth_rate for row in res.rows])
    argmax = res.rows[int(means.argmax())].kelly_fraction
    assert argmax == pytest.approx(res.predicted_optimal_fraction_kan_zhou, abs=tol)
    assert argmax == pytest.approx(res.predicted_optimal_fraction_mu_only, abs=tol)
    assert res.predicted_optimal_fraction_kan_zhou < res.predicted_optimal_fraction_mu_only


def test_monte_carlo_shares_estimation_noise_and_paths_across_fractions():
    """The comparison is only meaningful if every fraction in a trial sees
    the same pi_hat and the same shocks. Checked structurally: at the same
    seed, adding fractions to the tuple must not change the rows that were
    already there."""
    (mu, cov), r = _config_b()
    kwargs = {"estimation_obs": 2520, "horizon_obs": 252, "n_trials": 200, "seed": 99}
    two = estimation_risk_monte_carlo(mu, cov, r, kelly_fractions=(0.5, 1.0), **kwargs)
    four = estimation_risk_monte_carlo(
        mu, cov, r, kelly_fractions=(0.5, 1.0, 1.5, 2.0), **kwargs
    )
    for a, b in zip(two.rows, four.rows[:2]):
        assert a.median_growth_rate == b.median_growth_rate
        assert a.median_terminal_wealth == b.median_terminal_wealth
        assert a.prob_max_drawdown_over_half == b.prob_max_drawdown_over_half


def test_monte_carlo_guards():
    (mu, cov), r = _config_b()
    with pytest.raises(ValueError, match="must exceed the number of assets"):
        estimation_risk_monte_carlo(mu, cov, r, estimation_obs=3, horizon_obs=10, n_trials=2)
    with pytest.raises(ValueError, match="horizon_obs"):
        estimation_risk_monte_carlo(mu, cov, r, estimation_obs=100, horizon_obs=0, n_trials=2)
    with pytest.raises(ValueError, match="n_trials"):
        estimation_risk_monte_carlo(mu, cov, r, estimation_obs=100, horizon_obs=5, n_trials=0)


# ==========================================================================
# 9. FROM-RETURNS ENTRY POINTS AND THE OPT-IN DENOISING.
# ==========================================================================


def test_from_returns_matches_hand_assembled_moments_bit_for_bit():
    """The from-returns path must be exactly optimizer.py's estimation
    convention (sample mean and cov, annualized by TRADING_DAYS_PER_YEAR)
    and nothing else."""
    rets = _returns_frame()
    mu = rets.mean() * TRADING_DAYS_PER_YEAR
    cov = rets.cov() * TRADING_DAYS_PER_YEAR
    expected = kelly_weights(mu, cov, 0.03, 0.5)
    got = compute_kelly_sizing_from_returns(rets, 0.03, 0.5)
    for a in rets.columns:
        assert got.weights[a] == expected.weights[a]  # bit equality
    assert got.gross_leverage == expected.gross_leverage
    assert got.denoise is None


def test_denoise_defaults_off_and_changes_the_answer_when_on():
    rets = _returns_frame(n=8, t=1000, seed=21)
    off = compute_kelly_sizing_from_returns(rets, 0.03, 1.0)
    off_explicit = compute_kelly_sizing_from_returns(rets, 0.03, 1.0, denoise=False)
    on = compute_kelly_sizing_from_returns(rets, 0.03, 1.0, denoise=True)
    for a in rets.columns:
        assert off.weights[a] == off_explicit.weights[a]  # bit-identical
    assert off.denoise is None and off_explicit.denoise is None
    assert on.denoise is not None
    assert on.denoise.n_signal + on.denoise.n_noise == rets.shape[1]
    assert any(on.weights[a] != off.weights[a] for a in rets.columns)
    # Denoising must not touch the individual variances, so it cannot be
    # changing anything through the diagonal.
    assert on.denoise.covariance is not None
    np.testing.assert_allclose(
        np.diag(on.denoise.covariance.to_numpy()),
        np.diag(rets.cov().to_numpy() * TRADING_DAYS_PER_YEAR),
        rtol=1e-10,
    )


def test_leverage_from_returns_composes_with_hrp():
    """The documented composition: HRP picks the direction, Kelly picks the
    scale. Neither module is modified for the other."""
    rets = _returns_frame(n=6, t=900, seed=33)
    hrp = compute_hrp_weights_from_returns(rets)
    assert sum(hrp.weights.values()) == pytest.approx(1.0, rel=1e-9)
    lev = compute_kelly_leverage_from_returns(rets, hrp.weights, 0.03, 0.5)
    assert lev.leverage == pytest.approx(0.5 * lev.full_kelly_leverage, rel=1e-14)
    # The scaled weights are the HRP weights times the leverage.
    for a, w in hrp.weights.items():
        assert lev.scaled_weights[a] == pytest.approx(w * lev.leverage, rel=1e-12)
    # And the growth rate at full Kelly leverage beats any other leverage.
    mu = rets.mean() * TRADING_DAYS_PER_YEAR
    cov = rets.cov() * TRADING_DAYS_PER_YEAR
    w = pd.Series(hrp.weights)[list(rets.columns)]
    for mult in (0.3, 0.7, 1.3, 2.0):
        assert growth_rate(w * lev.full_kelly_leverage * mult, mu, cov, 0.03) <= (
            lev.full_kelly_growth_rate + 1e-12
        )


def test_weights_out_of_order_are_reindexed_not_misread():
    rets = _returns_frame(n=5, t=600, seed=44)
    ordered = {a: 0.2 for a in rets.columns}
    shuffled = {a: 0.2 for a in reversed(list(rets.columns))}
    a = compute_kelly_leverage_from_returns(rets, ordered, 0.02, 1.0)
    b = compute_kelly_leverage_from_returns(rets, shuffled, 0.02, 1.0)
    assert a.full_kelly_leverage == pytest.approx(b.full_kelly_leverage, rel=1e-14)


def test_insufficient_history_is_refused():
    rets = _returns_frame(n=3, t=5, seed=1)
    with pytest.raises(InsufficientHistoryError):
        compute_kelly_sizing_from_returns(rets, 0.02)
    with pytest.raises(InsufficientHistoryError):
        compute_kelly_leverage_from_returns(rets, {c: 1 / 3 for c in rets.columns}, 0.02)


# ==========================================================================
# 10. GUARDS. Degenerate input is refused, never patched.
# ==========================================================================


def test_non_square_covariance_is_refused():
    cov = pd.DataFrame(np.eye(2, 3), index=["a", "b"], columns=["a", "b", "c"])
    with pytest.raises(ValueError, match="square"):
        full_kelly_weights(pd.Series([0.1, 0.1], index=["a", "b"]), cov, 0.02)


def test_mismatched_mu_index_is_refused():
    mu = pd.Series([0.1, 0.2], index=["Y", "X"])  # right names, wrong order
    with pytest.raises(ValueError, match="same order"):
        full_kelly_weights(mu, COV_2, RF_2)


def test_nan_inputs_are_refused():
    cov = COV_2.copy()
    cov.iloc[0, 1] = np.nan
    cov.iloc[1, 0] = np.nan
    with pytest.raises(ValueError, match="NaN/inf"):
        full_kelly_weights(MU_2, cov, RF_2)
    mu = MU_2.copy()
    mu.iloc[0] = np.inf
    with pytest.raises(ValueError, match="NaN/inf"):
        full_kelly_weights(mu, COV_2, RF_2)


def test_asymmetric_covariance_is_refused():
    cov = COV_2.copy()
    cov.iloc[0, 1] = 0.05
    with pytest.raises(ValueError, match="not symmetric"):
        full_kelly_weights(MU_2, cov, RF_2)


def test_non_positive_variance_is_refused():
    cov = COV_2.copy()
    cov.iloc[1, 1] = 0.0
    with pytest.raises(ValueError, match="non-positive variance"):
        full_kelly_weights(MU_2, cov, RF_2)


def test_duplicate_labels_are_refused():
    cov = pd.DataFrame(np.eye(2) * 0.04, index=["X", "X"], columns=["X", "X"])
    with pytest.raises(ValueError, match="duplicate"):
        full_kelly_weights(pd.Series([0.1, 0.1], index=["X", "X"]), cov, 0.02)


@pytest.mark.parametrize("c", [0.0, -0.5, np.nan, np.inf])
def test_non_positive_kelly_fraction_is_refused(c):
    with pytest.raises(ValueError, match="kelly_fraction"):
        kelly_weights(MU_2, COV_2, RF_2, kelly_fraction=c)
    with pytest.raises(ValueError, match="kelly_fraction"):
        kelly_leverage_for_weights({"X": 0.5, "Y": 0.5}, MU_2, COV_2, RF_2, kelly_fraction=c)


def test_leverage_refuses_missing_or_extra_assets():
    with pytest.raises(ValueError, match="missing assets"):
        kelly_leverage_for_weights({"X": 1.0}, MU_2, COV_2, RF_2)
    with pytest.raises(ValueError, match="absent from the covariance"):
        kelly_leverage_for_weights({"X": 0.5, "Y": 0.4, "Z": 0.1}, MU_2, COV_2, RF_2)


def test_leverage_refuses_a_zero_variance_direction():
    with pytest.raises(ValueError, match="zero portfolio variance"):
        kelly_leverage_for_weights({"X": 0.0, "Y": 0.0}, MU_2, COV_2, RF_2)


def test_singular_covariance_is_refused_with_thorps_explanation():
    """[T06] section 8.4's own example of the failure: two securities in a
    fixed price ratio give det C = 0."""
    assets = ["BRKA", "BRKB", "SPY"]
    base = np.array([[0.04, 0.04, 0.01], [0.04, 0.04, 0.01], [0.01, 0.01, 0.03]])
    cov = pd.DataFrame(base, index=assets, columns=assets)
    mu = pd.Series([0.12, 0.12, 0.09], index=assets)
    with pytest.raises((ValueError, np.linalg.LinAlgError)):
        full_kelly_weights(mu, cov, 0.03)
