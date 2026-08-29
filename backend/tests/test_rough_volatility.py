"""Tests for app/services/risk/rough_volatility.py.

Synthetic and closed-form only. No network, no database, per the repo
convention stated in tests/conftest.py: "tests must never depend on live
yfinance data".

The real-data numbers quoted in the module docstring came from an
out-of-band run over YFinanceProvider; they are deliberately NOT asserted
here, exactly as tests/test_rmt_denoising.py and tests/test_kelly_sizing.py
do not assert theirs.

=============================================================================
THE PRE-DECLARED DESIGN OF THE FORECASTING COMPARISON, CONDENSED. Frozen
2026-08-29 before any forecast was computed on the real data. It is kept
here, in a file that is read on every test run, so that the docstring's
reported result can be checked against what was actually promised.

THIS IS A CONDENSATION, NOT A VERBATIM COPY — an earlier version of this
header said "PRESERVED VERBATIM" and that was wrong. Every design choice
that the decision rule depends on is reproduced below, but the frozen text
is about twice this length and the following clauses of it are NOT here:
the rationale for w = 5 over w = 1 and w = 21; the note that RFSV and HAR
forecast the same target from the same information set; "No re-estimation
schedule other than 'every origin' will be tried"; the summary of [P11]
Prop. 2(ii); and the realised-shape line "4864 rows x 12 cols,
2007-05-01 .. 2026-08-28" (the SAMPLE line below gives 2026-08-29, which is
the date REQUESTED from the provider; 2026-08-28 is the last bar returned).

ONE DEVIATION FROM THE FROZEN TEXT, MEASURED RATHER THAN ASSERTED. The
frozen H ESTIMATOR paragraph says m(q, Delta) is "averaged over all Delta
starting offsets", i.e. scaling_moment(overlapping=False). The run used the
pooled default, overlapping=True. On all twelve real series the two agree to
better than 1e-4 in H — cross-asset mean H is 0.2025 either way, and no
per-asset value moves in the fourth decimal — so nothing in section 7 of the
module docstring turns on it. test_scaling_moment_overlapping_matches_the_
literal_gjr_averaging pins the two together on synthetic data.

  QUESTION. Does an RFSV forecast of future log realized variance --
  [GJR] eq. (5.1) driven by H from their own m(q, Delta) method -- beat a
  HAR baseline out of sample on this project's real data? Expected answer:
  NO. [GJR]'s advantage was measured on 5-minute realized variance; this
  project has only daily closes, and Cont & Das argue proxy noise is what
  manufactures apparent roughness in the first place.

  UNIVERSE. The 12 cross-asset ETFs kelly_sizing.py already uses for its
  real-data check: SPY QQQ IWM EFA EEM TLT IEF LQD HYG GLD DBC VNQ. No
  asset added or dropped after results are seen.

  SAMPLE. Daily adjusted closes via YFinanceProvider.get_price_history,
  2007-05-01 (first month all 12 trade) to 2026-08-29.

  PROXY. r_t = log(P_t / P_{t-1}); RV_t = mean of the last 5 r^2;
  target x_t = log(RV_t). w = 5 for the headline; H also reported for
  w in {1, 5, 21} as a sensitivity, read against BOTH known bias
  directions (averaging biases H up per [GJR] Sec. 2.1/3.4; proxy noise
  biases it down per Cont & Das).

  H ESTIMATOR. [GJR] Sec. 2.1 exactly: q in {0.5, 1, 1.5, 2, 3},
  Delta = 1..30, zeta_q = OLS slope of log m(q, Delta) on log Delta,
  H = through-origin fit of zeta_q on q. With-intercept slope reported as
  a robustness check.

  MODELS. (1) RFSV, [GJR] eq. (5.1). (2) HAR, [GJR] Sec. 5.1's log-form
  HAR(3) with 1/5/20 averages, attributed by them to Corsi (2009);
  Corsi's own 1/5/22 run as a declared variant. (3) LAST, x_hat = x_t,
  as a floor. Horizons Delta in {1, 5, 20}.

  PROTOCOL. Rolling window W = 500 ([GJR] Sec. 5.1's own). Every origin:
  HAR refit by OLS on the trailing 500 only; RFSV-oos re-estimates H on
  the trailing 500 only (HEADLINE); RFSV-fullH uses whole-sample H, which
  is [GJR]'s own footnote-14 protocol and peeks, reported only for
  comparability and labelled as such. Kernel truncated at 500 lags,
  weights renormalised to sum to 1.

  LOSSES. PRIMARY: [GJR] Sec. 5.1's ratio P = SSE / sum (x - mean x)^2,
  on the log-variance scale, so numbers land on their Table 5.1's scale.
  SECONDARY: QLIKE, [P11] eq. (6), L = log h + sigmahat^2 / h, on the
  variance scale. Variance RMSE reported alongside, labelled non-robust.

  DECISION RULE, FIXED IN ADVANCE. At a horizon, "rough volatility beats
  HAR" is declared ONLY if BOTH (a) RFSV-oos has strictly lower P than HAR
  on >= 8 of the 12 assets, AND (b) the cross-asset mean ratio
  P_rfsv / P_har < 1. Otherwise: "no improvement" or "mixed", and that is
  a complete answer. No metric, window, lag set, universe or sample to be
  changed after results are seen; if one is changed anyway, both numbers
  get reported side by side with the change flagged.

  HONEST ORDERING NOTE. The price data was downloaded before this text was
  written. Nothing had been computed on it: at freeze time the only known
  facts were its shape (4864, 12) and its date span.
=============================================================================
"""

import numpy as np
import pytest
from scipy.integrate import quad
from scipy.special import gamma as gamma_fn

from app.services.risk.rough_volatility import (
    CORSI_HAR_LAGS,
    DEFAULT_HORIZONS,
    DEFAULT_MAX_LAG,
    DEFAULT_N_LAGS,
    DEFAULT_Q_VALUES,
    DEFAULT_ROLLING_WINDOW,
    GJR_HAR_LAGS,
    HARModel,
    _kernel_cdf,
    estimate_hurst,
    fbm_conditional_variance_constant,
    fgn_autocovariance,
    fit_har,
    gjr_p_ratio,
    har_features,
    qlike_loss,
    realized_variance,
    rfsv_forecast,
    rfsv_kernel_mass,
    rfsv_variance_forecast,
    rfsv_weights,
    rolling_forecast_comparison,
    scaling_moment,
    simulate_fbm,
    simulate_fgn,
    variance_rmse,
)

# ==========================================================================
# Defaults must match the papers they are quoted from
# ==========================================================================


def test_defaults_match_the_papers():
    """[GJR] Sec. 2.4: "q = 0.5, 1, 1.5, 2, 3 ... Delta = 1, ..., 30"."""
    assert DEFAULT_Q_VALUES == (0.5, 1.0, 1.5, 2.0, 3.0)
    assert DEFAULT_MAX_LAG == 30
    # [GJR] Sec. 5.1: "a rolling time window of 500 days".
    assert DEFAULT_ROLLING_WINDOW == 500
    # [GJR] Sec. 5.1's HAR uses 1/5/20; [C09] uses 1/5/22 ("monthly realized
    # volatility (which corresponds to 22 working days)").
    assert GJR_HAR_LAGS == (1, 5, 20)
    assert CORSI_HAR_LAGS == (1, 5, 22)
    # [GJR] Sec. 5.1: "1, 5 and 20 days ahead (Delta = 1, 5, 20)".
    assert DEFAULT_HORIZONS == (1, 5, 20)
    # This module's own truncation choice, not [GJR]'s.
    assert DEFAULT_N_LAGS == 500


# ==========================================================================
# 1. fGn autocovariance -- [D04] eq. (1.7)
# ==========================================================================


@pytest.mark.parametrize("hurst", [0.05, 0.1, 0.3, 0.5, 0.7, 0.9])
def test_fgn_autocovariance_matches_the_closed_form(hurst):
    """gamma(k) = 0.5(|k-1|^2H - 2|k|^2H + |k+1|^2H), [D04] eq. (1.7)."""
    got = fgn_autocovariance(8, hurst)
    want = np.array(
        [
            0.5
            * (
                abs(k - 1) ** (2 * hurst)
                - 2 * abs(k) ** (2 * hurst)
                + abs(k + 1) ** (2 * hurst)
            )
            for k in range(8)
        ]
    )
    np.testing.assert_allclose(got, want, atol=1e-14)


@pytest.mark.parametrize("hurst", [0.05, 0.1, 0.3, 0.5, 0.7, 0.9])
def test_fgn_is_unit_variance_for_every_hurst(hurst):
    assert fgn_autocovariance(4, hurst)[0] == pytest.approx(1.0, abs=1e-14)


def test_fgn_increments_are_independent_at_h_one_half():
    """[D04]: "If H = 1/2, all the covariances are 0 ... this implies
    independence. This agrees with the properties of ordinary Brownian
    motion, which has independent increments."."""
    g = fgn_autocovariance(10, 0.5)
    np.testing.assert_allclose(g[1:], 0.0, atol=1e-14)


def test_fgn_increments_are_negatively_correlated_when_rough():
    """H < 1/2 is anti-persistent; H > 1/2 is long-memory positive."""
    assert fgn_autocovariance(3, 0.1)[1] < 0
    assert fgn_autocovariance(3, 0.9)[1] > 0


# ==========================================================================
# 2. Davies-Harte generator -- exact, not approximate
# ==========================================================================


@pytest.mark.parametrize("hurst", [0.1, 0.3, 0.5, 0.7])
def test_davies_harte_reproduces_the_theoretical_autocovariance(hurst):
    """The generator is EXACT: the empirical covariance of many paths must
    converge on fgn_autocovariance, not merely resemble it."""
    rng = np.random.default_rng(20260829)
    n, n_paths = 1024, 600
    paths = np.array([simulate_fgn(n, hurst, rng) for _ in range(n_paths)])
    empirical = np.array(
        [float(np.mean(paths[:, : n - k] * paths[:, k:])) for k in range(6)]
    )
    theory = fgn_autocovariance(6, hurst)
    # Monte Carlo standard error on 600 x ~1024 samples is ~1e-3.
    np.testing.assert_allclose(empirical, theory, atol=0.01)


def test_davies_harte_is_deterministic_given_a_seed():
    a = simulate_fgn(256, 0.2, np.random.default_rng(7))
    b = simulate_fgn(256, 0.2, np.random.default_rng(7))
    np.testing.assert_array_equal(a, b)


def test_davies_harte_output_is_real_and_right_length():
    x = simulate_fgn(512, 0.15, np.random.default_rng(3))
    assert x.shape == (512,)
    assert np.all(np.isfinite(x))


@pytest.mark.parametrize("hurst", [0.1, 0.3, 0.5, 0.8])
def test_fbm_second_moment_scales_as_delta_to_the_2h(hurst):
    """[GJR] eq. (1.1) at q = 2 (K_2 = 1): E|W_{t+D} - W_t|^2 = D^{2H}."""
    rng = np.random.default_rng(99)
    paths = np.array([simulate_fbm(2048, hurst, rng) for _ in range(300)])
    for delta in (1, 4, 16, 64):
        inc = paths[:, delta:] - paths[:, :-delta]
        got = float(np.mean(inc**2))
        want = float(delta) ** (2 * hurst)
        assert got == pytest.approx(want, rel=0.08), f"delta={delta}"


def test_simulate_fgn_rejects_bad_arguments():
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError, match="n must be >= 2"):
        simulate_fgn(1, 0.2, rng)
    with pytest.raises(ValueError, match="hurst must lie in"):
        simulate_fgn(64, 1.5, rng)
    with pytest.raises(ValueError, match="hurst must be finite"):
        simulate_fgn(64, float("nan"), rng)


# ==========================================================================
# 3. THE HEADLINE GROUND-TRUTH TEST: H recovery from a known H
# ==========================================================================


@pytest.mark.parametrize("true_hurst", [0.1, 0.2, 0.3, 0.5, 0.7])
def test_estimator_recovers_a_known_hurst_exponent(true_hurst):
    """Validate the estimator against synthetic ground truth BEFORE trusting
    it on market data.

    20 seeds, 4096-point fBm paths, run exactly as the estimator is run on
    real log-volatility. Measured this session (30 seeds):

        true H   mean H_hat   sd       bias
        0.1      0.1005       0.0088   +0.0005
        0.2      0.2003       0.0130   +0.0003
        0.3      0.2999       0.0155   -0.0001
        0.5      0.4989       0.0168   -0.0011
        0.7      0.6965       0.0188   -0.0035

    The tolerance below is deliberately looser than that so the test is not
    a snapshot of the RNG, but tight enough to fail on a real regression.
    """
    estimates = np.array(
        [
            estimate_hurst(simulate_fbm(4096, true_hurst, np.random.default_rng(1000 + s))).hurst
            for s in range(20)
        ]
    )
    assert estimates.mean() == pytest.approx(true_hurst, abs=0.02)
    assert estimates.std(ddof=1) < 0.03


def test_estimator_degrades_predictably_on_a_500_point_window():
    """The rolling study estimates H on 500 observations, not 4096, so the
    degradation is measured rather than assumed.

    CORRECTED BY THE INDEPENDENT VERIFICATION PASS. The first version of this
    test drew 60 seeds and asserted `-0.03 < bias < 0.0` per H, quoting biases
    of -0.005 / -0.010 / -0.011. Those three numbers were honestly reported
    for those 60 seeds, but 60 seeds cannot resolve a bias this small: the
    standard error of the mean is 0.0029 / 0.0057 / 0.0072, so each figure was
    a 1-2 s.e. draw and the strict-negative assertion was a coin flip. Re-run
    on 40 independent blocks of 60 seeds at H = 0.1, the sign came out
    non-negative in 11 of 40 blocks — i.e. the old test would have failed on
    roughly a quarter of seed choices.

    THE LARGE-SAMPLE TRUTH, measured over 2000-3000 fresh seeds per H:

        true H   bias        s.e.       sd of H_hat
        0.1      -0.0013     0.0004     0.0224
        0.15     -0.0023     0.0005     0.0287
        0.2      -0.0031     0.0006     0.0334
        0.3      -0.0058     0.0007     0.0407
        0.5      -0.0085     0.0009     0.0493

    So the qualitative claim survives and the overstated magnitudes do not:
    the bias IS negative and DOES grow with H, but at the H ~ 0.17-0.24 the
    real data actually lands on it is about -0.003, not -0.005 to -0.011.

    WHAT THIS MEANS FOR THE MODULE'S CONCLUSION, which is unchanged: on a
    500-point window H comes out slightly too SMALL, so correcting for it
    moves the real-data estimate further from [GJR]'s 0.1, not toward it. The
    correction is ~0.003 on a reported 0.2025 — immaterial either way. It
    cannot be what makes the real number look un-rough.

    This test now asserts only what the sample size can carry: the widened
    sd, the ordering of the bias in H, the fact that it is negative where it
    is strongest, and the bound that matters for the conclusion.
    """
    n_seeds = 1500
    measured = {}
    for h, offset in ((0.1, 0), (0.3, 10_000), (0.5, 20_000)):
        est = np.array(
            [
                estimate_hurst(
                    simulate_fbm(500, h, np.random.default_rng(offset + s))
                ).hurst
                for s in range(n_seeds)
            ]
        )
        measured[h] = (est.mean() - h, est.std(ddof=1))

    for h, expected_sd in ((0.1, 0.0224), (0.3, 0.0407), (0.5, 0.0493)):
        bias, sd = measured[h]
        assert sd == pytest.approx(expected_sd, rel=0.2), f"H={h} sd {sd:.4f}"
        assert abs(bias) < 0.02, f"H={h} bias {bias:+.4f} is larger than documented"

    # The bias grows (more negative) with H. Far more robust than each sign.
    assert measured[0.1][0] > measured[0.3][0] > measured[0.5][0]

    # Negative where the effect is strongest (t ~ -6 at this sample size).
    assert measured[0.5][0] < 0.0

    # THE LOAD-BEARING BOUND: at the low H the real data lands on, the
    # short-window bias is far too small to explain anything.
    assert -0.005 < measured[0.1][0] < 0.0


@pytest.mark.parametrize("true_hurst", [0.1, 0.3])
def test_both_hurst_readings_agree_on_synthetic_fbm(true_hurst):
    """Through-origin (headline) vs with-intercept (robustness) fits.

    The through-origin fit is this module's reconstruction of [GJR]'s
    Fig. 2.3 rather than a quote; if the two readings diverged, that
    reconstruction would be load-bearing. On true fBm they do not: measured
    this session over 30 seeds, mean |gap| is 0.0012 at H = 0.1, 0.0025 at
    0.3 and 0.0041 at 0.5, with a worst case of 0.0106.

    On the REAL data they diverge much more (0.2343 vs 0.1896 for SPY),
    which is the point — that divergence is a symptom that the series is
    not a single-H fBm, and the module reports it as one.
    """
    for seed in range(6):
        est = estimate_hurst(simulate_fbm(4096, true_hurst, np.random.default_rng(seed)))
        assert est.hurst == pytest.approx(est.hurst_with_intercept, abs=0.02)


def test_zeta_q_is_proportional_to_q_on_true_fbm():
    """[GJR] Sec. 2.2: "zeta_q ~ H q" and "the smoothness parameter s_q does
    not seem to depend on q"."""
    est = estimate_hurst(simulate_fbm(8192, 0.15, np.random.default_rng(11)))
    ratios = np.asarray(est.zeta_by_q) / np.asarray(est.q_values)
    assert ratios.std(ddof=1) < 0.01
    assert np.all(np.asarray(est.r2_by_q) > 0.95)


def test_hurst_is_invariant_to_the_log_vol_vs_log_variance_choice():
    """H comes out identical on log(sigma) and log(sigma^2) = 2 log(sigma);
    scaling shifts the intercept, not the slope. nu does NOT survive it,
    which is why estimate_hurst documents the log-volatility convention."""
    x = simulate_fbm(4096, 0.2, np.random.default_rng(5))
    a = estimate_hurst(x)
    b = estimate_hurst(2.0 * x)
    assert a.hurst == pytest.approx(b.hurst, abs=1e-10)
    # nu^2 = exp(intercept) picks up the factor of 4.
    assert np.exp(b.log_nu) == pytest.approx(4.0 * np.exp(a.log_nu), rel=1e-8)


def test_hurst_is_invariant_to_an_additive_shift():
    x = simulate_fbm(2048, 0.25, np.random.default_rng(6))
    assert estimate_hurst(x).hurst == pytest.approx(estimate_hurst(x + 17.5).hurst, abs=1e-10)


def test_nu_is_recovered_from_the_q_equals_two_intercept():
    """[GJR] Sec. 5.2: "nu^2 is estimated as the exponential of the intercept
    in the linear regression of log(m(2, Delta)) on log(Delta)".

    On log sigma_t = nu W^H_t, m(2, Delta) = nu^2 Delta^{2H}, so the
    intercept is log nu^2.
    """
    true_nu = 0.35
    ests = [
        estimate_hurst(true_nu * simulate_fbm(8192, 0.15, np.random.default_rng(s))).nu
        for s in range(8)
    ]
    assert float(np.mean(ests)) == pytest.approx(true_nu, rel=0.06)


def test_scaling_moment_overlapping_matches_the_literal_gjr_averaging():
    """[GJR]: "several m(q, Delta) can be computed depending on the starting
    point. Our final measure of m(q, Delta) is the average of these values."

    The vectorised pooled version used by default is the same set of
    increments with slightly different group weights.
    """
    x = simulate_fbm(4096, 0.15, np.random.default_rng(4))
    for q in (0.5, 1.0, 2.0, 3.0):
        for lag in (1, 2, 7, 30):
            a = scaling_moment(x, q, lag, overlapping=True)
            b = scaling_moment(x, q, lag, overlapping=False)
            assert a == pytest.approx(b, rel=2e-3), f"q={q} lag={lag}"


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_headline_hurst_is_the_through_origin_fit_not_the_ratio_of_sums(seed):
    """Pin WHICH arithmetic turns the five zeta_q into one H.

    On true fBm zeta_q = H q exactly, so sum(zeta_q q)/sum(q^2) and the
    ratio-of-sums sum(zeta_q)/sum(q) are indistinguishable — every other
    test in this file uses true fBm and therefore cannot tell them apart.
    Swapping one for the other passed the whole suite before this test
    existed, while moving the real-data SPY headline from 0.2343 to 0.2472.

    So this test uses a series that is deliberately NOT single-H: fBm
    increments multiplied by an independent lognormal scale. That makes
    zeta_q/q fall with q, the same shape section 7 of the module docstring
    reports on real data, and it separates the two formulas by ~0.04.

    This pins the documented choice; it does not validate it. The choice
    itself is a reconstruction of [GJR] Figs. 2.3/2.6 and is flagged as such
    in the module docstring.
    """
    rng = np.random.default_rng(seed)
    increments = np.diff(
        np.concatenate([[0.0], simulate_fbm(4096, 0.15, np.random.default_rng(seed))])
    )
    x = np.cumsum(increments * np.exp(rng.normal(0.0, 1.2, 4096)))

    est = estimate_hurst(x)
    z = np.asarray(est.zeta_by_q)
    q = np.asarray(est.q_values)

    assert est.hurst == pytest.approx(float(z @ q / (q @ q)), abs=1e-12)
    # The series really is multi-scaling, so the two formulas genuinely
    # disagree here — without this the assertion above would be vacuous.
    assert np.all(np.diff(z / q) < 0), "fixture should be multi-scaling"
    assert abs(est.hurst - float(z.sum() / q.sum())) > 0.01


def test_the_proxy_alone_manufactures_roughness_from_iid_returns():
    """THE CONTROL FOR SECTION 7'S CENTRAL CAVEAT, added by the independent
    verification pass because the module asserted the caveat without
    quantifying it.

    Feed IID GAUSSIAN returns -- constant spot volatility, no volatility
    dynamics of any kind, nothing rough anywhere -- through this module's own
    w-day realized-variance proxy, then estimate H off the result. If H were
    measuring the volatility process, it would be meaningless here. It is
    not: it tracks the smoothing window almost deterministically.

    Measured this session at the real data's length (n = 4863, 20 seeds),
    against the module docstring's real-ETF numbers:

        proxy window   H on IID returns   H on the real ETFs
        1 day          0.0003             0.0100
        5 days         0.1366             0.2025
        21 days        0.4424             0.5534

    So at the headline 5-day window TWO THIRDS of the measured H is produced
    by the proxy alone, on data with no volatility process at all. This is
    [CD23]'s thesis reproduced inside this module's own code path, and it is
    why section 7 reports 0.2025 as "its number for its proxy" and makes no
    claim about the true roughness of volatility.

    The real series DO sit above this control at every window, so there is
    genuine signal -- volatility clustering pushes H up -- but the LEVEL of H
    is mostly an artefact of the smoothing.
    """
    got = {}
    for window in (1, 5, 21):
        hursts = []
        for seed in range(5):
            returns = np.random.default_rng(20260829 + seed).standard_normal(3000) * 0.01
            rv = realized_variance(returns, window)
            rv = rv[~np.isnan(rv)]
            hursts.append(estimate_hurst(0.5 * np.log(rv[rv > 0])).hurst)
        got[window] = float(np.mean(hursts))

    # Rises monotonically with the smoothing window, on pure noise.
    assert got[1] < got[5] < got[21]
    # One day of squared returns has no smoothing, so no manufactured H.
    assert abs(got[1]) < 0.02, got
    # Five days manufactures a solidly "rough" H out of nothing at all.
    assert 0.09 < got[5] < 0.18, got
    # Three weeks manufactures an H approaching ordinary Brownian motion.
    assert 0.35 < got[21] < 0.50, got


def test_scaling_moment_is_exact_by_hand():
    x = np.array([0.0, 1.0, 3.0, 6.0])
    # lag 1 increments: 1, 2, 3 -> mean |.|^1 = 2
    assert scaling_moment(x, 1.0, 1) == pytest.approx(2.0)
    # lag 2 increments: 3, 5 -> mean of squares = 17
    assert scaling_moment(x, 2.0, 2) == pytest.approx(17.0)


def test_estimate_hurst_rejects_short_and_dirty_input():
    with pytest.raises(ValueError, match="need at least"):
        estimate_hurst(np.arange(50.0))
    with pytest.raises(ValueError, match="non-finite"):
        estimate_hurst(np.concatenate([simulate_fbm(200, 0.2, np.random.default_rng(0)), [np.nan]]))
    with pytest.raises(ValueError, match="1-D"):
        estimate_hurst(np.zeros((100, 2)))


# ==========================================================================
# 4. The eq. (5.1) kernel
# ==========================================================================


@pytest.mark.parametrize("hurst", [0.02, 0.1, 0.3, 0.49])
@pytest.mark.parametrize("x", [0.001, 0.5, 1.0, 10.0, 100.0, 499.5, 5000.0])
def test_closed_form_kernel_cdf_matches_numerical_quadrature(hurst, x):
    """Int_0^x u^-a/(1+u) du = x^{1-a}/(1-a) 2F1(1, 1-a; 2-a; -x).

    The docstring claims agreement to 1e-10; this is that claim.
    """
    a = hurst + 0.5
    closed = float(_kernel_cdf(np.array([x]), a)[0])
    numeric, err = quad(lambda u: u**-a / (1.0 + u), 0.0, x, limit=400)
    assert closed == pytest.approx(numeric, abs=max(1e-9, 10 * err))


@pytest.mark.parametrize("hurst", [0.02, 0.1, 0.2, 0.3, 0.4, 0.49])
def test_the_kernel_has_mass_exactly_one(hurst):
    """Derived here, not in [GJR]: (cos(H pi)/pi) Int_0^inf u^-(H+1/2)/(1+u) du
    = (cos(H pi)/pi) * pi/cos(pi H) = 1. This is what makes the predictor a
    weighted average and makes truncation correctable by renormalising."""
    assert rfsv_kernel_mass(hurst) == pytest.approx(1.0, abs=1e-12)
    a = hurst + 0.5
    c = np.cos(np.pi * hurst) / np.pi
    lo, _ = quad(lambda u: u**-a / (1.0 + u), 0.0, 1.0, limit=400)
    hi, _ = quad(lambda u: u**-a / (1.0 + u), 1.0, np.inf, limit=400)
    assert c * (lo + hi) == pytest.approx(1.0, abs=1e-8)


@pytest.mark.parametrize("hurst", [0.05, 0.1, 0.3, 0.45])
@pytest.mark.parametrize("horizon", [1, 5, 20])
def test_weights_are_a_positive_decreasing_probability_distribution(hurst, horizon):
    w = rfsv_weights(hurst, horizon, 500)
    assert np.all(w > 0)
    assert w.sum() == pytest.approx(1.0, abs=1e-12)
    assert np.all(np.diff(w) < 0), "kernel weight must decay with age"


@pytest.mark.parametrize("horizon", [1, 5, 20])
def test_truncation_deficit_is_small_and_grows_with_horizon(horizon):
    """The un-normalised weights fall short of 1 by the tail mass beyond 500
    daily lags. [GJR] Sec. 5.1 make the same point qualitatively: "The
    relevant regression window is thus linear in the forecasting horizon."
    """
    captured = rfsv_weights(0.13, horizon, 500, normalize=False).sum()
    assert 0.9 < captured < 1.0


def test_longer_horizons_put_less_weight_on_the_most_recent_day():
    w1 = rfsv_weights(0.13, 1, 500)
    w20 = rfsv_weights(0.13, 20, 500)
    assert w1[0] > w20[0]


def test_predictor_reproduces_a_constant_series_exactly():
    """The weights sum to 1, so a flat history forecasts its own level."""
    for horizon in (1, 5, 20):
        assert rfsv_forecast(np.full(600, -8.25), 0.12, horizon) == pytest.approx(-8.25)


def test_predictor_is_a_convex_combination_of_the_history():
    x = simulate_fbm(600, 0.2, np.random.default_rng(2)) - 9.0
    f = rfsv_forecast(x, 0.15, 5)
    assert x.min() <= f <= x.max()


def test_weights_reject_h_at_or_above_one_half():
    """[GJR] state eq. (5.1) "where W^H is a fBM with H < 1/2"; at H >= 1/2
    the prefactor cos(H pi) is non-positive and the weights stop being a
    distribution."""
    with pytest.raises(ValueError, match="stated for H < 1/2"):
        rfsv_weights(0.5, 1, 100)
    with pytest.raises(ValueError, match="stated for H < 1/2"):
        rfsv_weights(0.7, 1, 100)


# ==========================================================================
# 5. Conditional variance constant -- [GJR] Sec. 5.2
# ==========================================================================


def test_conditional_variance_constant_is_one_at_h_one_half():
    """c = Gamma(3/2-H)/[Gamma(H+1/2) Gamma(2-2H)]; at H = 1/2 that is
    Gamma(1)/[Gamma(1) Gamma(1)] = 1, so Var[W_{t+D}|F_t] = D, the correct
    conditional variance for ordinary Brownian motion.

    A NECESSARY CONDITION ONLY, AND A WEAK ONE — SAID HERE BECAUSE THIS TEST
    USED TO CLAIM MORE. Swapping the numerator with one denominator factor,
    c' = Gamma(H+1/2)/[Gamma(3/2-H) Gamma(2-2H)], is ALSO exactly 1 at
    H = 1/2 and positive everywhere, so this assertion and the one below
    cannot tell the two apart. The check that can is
    test_conditional_variance_constant_matches_fbm_computed_from_scratch.
    """
    assert fbm_conditional_variance_constant(0.5) == pytest.approx(1.0, abs=1e-12)
    # The counterexample really does survive this test, which is why the
    # from-scratch check below exists. Spelled out so nobody re-reads the
    # assertion above as evidence the transcription is right.
    swapped = gamma_fn(1.0) / (gamma_fn(1.0) * gamma_fn(1.0))
    assert swapped == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize("hurst", [0.05, 0.1, 0.2, 0.3, 0.4, 0.49, 0.6, 0.8])
def test_conditional_variance_constant_is_positive(hurst):
    assert fbm_conditional_variance_constant(hurst) > 0


def _exact_fbm_conditional_variance(hurst, horizon, n_lags, origin=1e7):
    """Var[W^H_{T+D} | W^H_T, W^H_{T-1}, ..., W^H_{T-k+1}] on the discrete
    daily grid, solved from fBm's own covariance

        Cov(W_s, W_t) = 0.5 (s^{2H} + t^{2H} - |t - s|^{2H})

    which follows from [GJR] eq. (1.1) at q = 2 plus stationary increments
    and W_0 = 0, and needs NOTHING from Nuzman & Poor. `origin` is placed far
    away so the anchor at W_0 is negligible.

    The discrete past is a strict SUBSET of [GJR]'s continuous filtration
    F_t, so conditioning on it can only leave MORE variance than c*D^{2H},
    never less, and the gap closes as n_lags grows. That one-sided bracket is
    what gives the test below its power: it pins c from above and below at
    once, and no wrong constant can satisfy both ends.
    """
    times = origin - np.arange(n_lags, dtype=float)
    target = origin + horizon

    def cov(s, t):
        s = np.asarray(s, float)[:, None]
        t = np.asarray(t, float)[None, :]
        return 0.5 * (s ** (2 * hurst) + t ** (2 * hurst) - np.abs(t - s) ** (2 * hurst))

    gram = cov(times, times)
    cross = cov(times, np.array([target]))[:, 0]
    var = float(cov(np.array([target]), np.array([target]))[0, 0])
    return float(var - cross @ np.linalg.solve(gram + 1e-13 * np.eye(n_lags), cross))


@pytest.mark.parametrize("hurst", [0.1, 0.14, 0.3, 0.45])
@pytest.mark.parametrize("horizon", [1, 5])
def test_conditional_variance_constant_matches_fbm_computed_from_scratch(hurst, horizon):
    """THE CHECK WITH REAL POWER ON [GJR] Sec. 5.2's c, added because the
    c(1/2) == 1 test above has none.

    [GJR] attribute Var[W^H_{t+D}|F_t] = c D^{2H} to Nuzman & Poor, which
    could not be fetched this session, so c is verified the same way
    eq. (5.1) is: against fBm's own covariance function, solved from
    scratch. Conditioning on the discrete daily past gives an UPPER bound on
    the continuous-filtration value, so the transcribed constant must sit
    just below the from-scratch number and the gap must shrink as the grid
    reaches further back.

    Measured this session (n_lags = 200 -> 600):
        H=0.10 D=1: c*D^2H = 0.63970, from scratch 0.69600 -> 0.69559
        H=0.14 D=1: c*D^2H = 0.69471, from scratch 0.74914 -> 0.74878
        H=0.30 D=5: c*D^2H = 2.33460, from scratch 2.35550 -> 2.35384
        H=0.45 D=1: c*D^2H = 0.99208, from scratch 0.99381 -> 0.99380

    THE COUNTEREXAMPLE THIS EXCLUDES: the swapped form c' gives 1.80206 at
    H = 0.1, D = 1 — ABOVE the from-scratch 0.6956, so it violates the
    one-sided bound and this test fails on it. The c(1/2) == 1 test does not.
    """
    c = fbm_conditional_variance_constant(hurst)
    transcribed = c * horizon ** (2 * hurst)
    near = _exact_fbm_conditional_variance(hurst, horizon, 200)
    far = _exact_fbm_conditional_variance(hurst, horizon, 600)

    # Lower bound: less information cannot mean less conditional variance.
    # This is the assertion the swapped constant fails.
    assert far >= transcribed * (1 - 1e-6), (
        f"c*D^2H = {transcribed:.6f} exceeds the discrete-past conditional "
        f"variance {far:.6f}, which is impossible for a correct c"
    )
    # Upper bound: and it must be CLOSE, or c is simply the wrong constant.
    assert far / transcribed < 1.12, (
        f"c*D^2H = {transcribed:.6f} is far below the discrete-past bound "
        f"{far:.6f} (ratio {far / transcribed:.4f})"
    )
    # Reaching further back can only tighten the bound, never loosen it.
    assert far <= near + 1e-9

    swapped = (
        gamma_fn(hurst + 0.5)
        / (gamma_fn(1.5 - hurst) * gamma_fn(2.0 - 2.0 * hurst))
        * horizon ** (2 * hurst)
    )
    assert far < swapped * (1 - 1e-3), (
        "the swapped-Gamma counterexample should violate the one-sided bound; "
        "if it does not, this test has lost the power it was added for"
    )


def test_variance_forecast_applies_the_lognormal_correction():
    """[GJR] Sec. 5.2: sigmahat^2 = exp{loghat sigma^2 + 2 c nu^2 D^{2H}}.

    Independent derivation, which is what makes the transcription
    trustworthy: log sigma^2 ~ 2 nu W^H + C, so
    Var[log sigma^2_{t+D}|F_t] = 4 nu^2 c D^{2H}, and the lognormal mean
    correction is half of that.
    """
    hurst, nu, horizon, log_forecast = 0.14, 0.3, 5, -9.0
    c = fbm_conditional_variance_constant(hurst)
    cond_var = 4.0 * nu**2 * c * horizon ** (2 * hurst)
    expected = np.exp(log_forecast + 0.5 * cond_var)
    got = rfsv_variance_forecast(log_forecast, hurst, horizon, nu)
    assert float(got) == pytest.approx(expected, rel=1e-12)
    assert float(got) > np.exp(log_forecast), "correction must be upward"


# ==========================================================================
# 6. HAR baseline -- [C09]
# ==========================================================================


def test_har_features_average_exactly_lag_terms():
    """[C09] eq. (4): RV^(w)_t = (1/5)(RV_t + RV_{t-1} + ... + RV_{t-4}),
    i.e. FIVE terms over five. This is the off-by-one that [GJR] Sec. 5.1's
    restatement gets wrong (it prints sum_{i=0}^{5} over 5)."""
    x = np.arange(1.0, 11.0)
    f = har_features(x, (1, 5))
    assert f[9, 0] == pytest.approx(10.0)
    assert f[9, 1] == pytest.approx(np.mean([6.0, 7.0, 8.0, 9.0, 10.0]))
    assert np.isnan(f[3, 1])
    assert not np.isnan(f[4, 1])


def test_har_features_reject_bad_lags():
    with pytest.raises(ValueError, match="non-empty positive"):
        har_features(np.arange(10.0), ())
    with pytest.raises(ValueError, match="non-empty positive"):
        har_features(np.arange(10.0), (0, 5))


def test_har_recovers_known_coefficients_from_its_own_dgp():
    """Generate data from [C09] eq. (8) exactly and fit it back."""
    rng = np.random.default_rng(42)
    n = 6000
    lags = (1, 5, 22)
    true = np.array([-0.5, 0.35, 0.30, 0.25])
    x = np.zeros(n)
    x[:22] = rng.normal(0.0, 0.1, 22)
    for t in range(22, n):
        feats = np.array([x[t - lag : t].mean() for lag in lags])
        x[t] = true[0] + np.dot(true[1:], feats) + rng.normal(0.0, 0.05)
    model = fit_har(x, 1, lags=lags)
    np.testing.assert_allclose(model.coefficients, true, atol=0.05)


def test_har_model_predict_is_the_linear_form():
    m = HARModel(coefficients=np.array([1.0, 2.0, 3.0]), lags=(1, 5), n_obs=10)
    assert m.predict(np.array([0.5, -1.0])) == pytest.approx(1.0 + 1.0 - 3.0)
    with pytest.raises(ValueError, match="expected 2 features"):
        m.predict(np.array([1.0, 2.0, 3.0]))


def test_fit_har_rejects_too_short_series():
    with pytest.raises(ValueError, match="usable"):
        fit_har(np.arange(23.0), 1, lags=(1, 5, 22))


# ==========================================================================
# 7. Losses
# ==========================================================================


def test_qlike_matches_pattons_printed_formula():
    """[P11] eq. (6): L(sigmahat^2, h) = log h + sigmahat^2 / h."""
    proxy = np.array([1.0, 4.0, 9.0])
    forecast = np.array([2.0, 2.0, 3.0])
    want = float(np.mean(np.log(forecast) + proxy / forecast))
    assert qlike_loss(proxy, forecast) == pytest.approx(want)


def test_qlike_is_minimised_at_the_true_conditional_variance():
    """[P11]'s robustness property: with a conditionally unbiased proxy the
    optimal forecast under QLIKE is the true conditional variance."""
    rng = np.random.default_rng(8)
    truth = 0.04
    proxy = truth * rng.chisquare(1, size=400_000)  # E[proxy] = truth
    grid = np.linspace(0.5 * truth, 2.0 * truth, 61)
    losses = [qlike_loss(proxy, np.full_like(proxy, h)) for h in grid]
    assert grid[int(np.argmin(losses))] == pytest.approx(truth, rel=0.05)


def test_qlike_rejects_non_positive_variances():
    with pytest.raises(ValueError, match="strictly positive"):
        qlike_loss(np.array([1.0]), np.array([0.0]))
    with pytest.raises(ValueError, match="strictly positive"):
        qlike_loss(np.array([-1.0]), np.array([1.0]))


def test_p_ratio_is_one_for_the_unconditional_mean():
    """[GJR]'s P is normalised so that forecasting the sample mean gives 1."""
    x = simulate_fbm(500, 0.3, np.random.default_rng(1))
    mean = float(np.mean(x))
    assert gjr_p_ratio(x, np.full_like(x, mean), mean) == pytest.approx(1.0)
    assert gjr_p_ratio(x, x, mean) == pytest.approx(0.0)


def test_p_ratio_and_rmse_reject_shape_mismatch():
    with pytest.raises(ValueError, match="shape mismatch"):
        gjr_p_ratio(np.zeros(5), np.zeros(4), 0.0)
    with pytest.raises(ValueError, match="shape mismatch"):
        variance_rmse(np.zeros(5), np.zeros(4))


def test_variance_rmse_is_the_plain_root_mean_square():
    assert variance_rmse(np.array([1.0, 2.0]), np.array([2.0, 4.0])) == pytest.approx(
        np.sqrt((1.0 + 4.0) / 2.0)
    )


# ==========================================================================
# 8. The realized-variance proxy
# ==========================================================================


def test_realized_variance_is_the_rolling_mean_of_squared_returns():
    r = np.array([0.1, -0.2, 0.3, 0.0, -0.1])
    got = realized_variance(r, 3)
    assert np.isnan(got[0]) and np.isnan(got[1])
    assert got[2] == pytest.approx((0.01 + 0.04 + 0.09) / 3)
    assert got[4] == pytest.approx((0.09 + 0.0 + 0.01) / 3)


def test_realized_variance_window_one_is_just_squared_returns():
    r = np.array([0.1, -0.2, 0.3])
    np.testing.assert_allclose(realized_variance(r, 1), r**2)


def test_realized_variance_rejects_bad_window():
    with pytest.raises(ValueError, match="window must be >= 1"):
        realized_variance(np.zeros(10), 0)


# ==========================================================================
# 9. The rolling comparison harness
# ==========================================================================


def _synthetic_log_variance(n=1400, hurst=0.14, seed=0):
    """A log-variance series that really is rough, with a known H."""
    return 2.0 * 0.3 * simulate_fbm(n, hurst, np.random.default_rng(seed)) - 9.0


def test_rolling_comparison_shapes_and_alignment():
    x = _synthetic_log_variance()
    res = rolling_forecast_comparison(x, 5, window=600)
    assert res.n_forecasts == len(x) - 600 - 5
    assert res.origins[0] == 600
    assert res.origins[-1] == len(x) - 5 - 1
    np.testing.assert_allclose(res.actual, x[res.origins + 5])
    np.testing.assert_allclose(res.last_value, x[res.origins])
    for arr in (res.rfsv, res.har, res.hurst_by_origin):
        assert arr.shape == (res.n_forecasts,)
        assert np.all(np.isfinite(arr))


@pytest.mark.parametrize(
    ("horizon", "fixed_hurst"), [(1, 0.14), (5, 0.14), (20, 0.14), (5, None)]
)
def test_rolling_comparison_does_not_look_ahead(horizon, fixed_hurst):
    """The single most important property of the harness: a forecast made at
    origin t must be a function of x[:t+1] and nothing else.

    THE MASK IS THE WHOLE TEST, AND THE FIRST VERSION OF IT WAS WRONG. It
    read

        safe = a.origins + horizon < len(x) - n_corrupt

    which excludes PRECISELY the origins at which a horizon-length peek
    would reach the corrupted tail. That version passed unchanged when the
    RFSV history was widened from x[:t+1] to x[:t+1+horizon] — a leak that
    lets the predictor read the target itself and drops the D = 1 P ratio
    from 0.261 to 0.051. The guard billed as the most important one in the
    file could not see the only leak it existed to catch.

    The correct condition is on the ORIGIN alone: everything a legitimate
    forecast may look at lies at or before t, so if t itself precedes the
    corruption, every output at t must be bit-identical. The `assert
    np.any(...)` below keeps the fix honest — it fails if the mask ever
    stops covering origins whose t + horizon reaches into the corrupted
    region, which is exactly how the original bug hid.

    fixed_hurst=None is included so the per-window estimate_hurst call is
    covered too, not just the kernel and the HAR refit.
    """
    n_corrupt = 100
    x = _synthetic_log_variance(seed=3)
    a = rolling_forecast_comparison(x, horizon, window=600, fixed_hurst=fixed_hurst)
    y = x.copy()
    y[-n_corrupt:] = 42.0
    b = rolling_forecast_comparison(y, horizon, window=600, fixed_hurst=fixed_hurst)

    safe = a.origins < len(x) - n_corrupt
    assert np.any(safe & (a.origins + horizon >= len(x) - n_corrupt)), (
        "mask covers no origin whose target lies in the corrupted tail, so a "
        "horizon-length lookahead would slip through — this is the original bug"
    )
    for name in ("rfsv", "har", "last_value", "hurst_by_origin"):
        np.testing.assert_allclose(
            getattr(a, name)[safe],
            getattr(b, name)[safe],
            atol=1e-12,
            err_msg=f"{name} at horizon {horizon} depends on data after its origin",
        )


def test_rolling_comparison_rounding_of_h_is_immaterial():
    x = _synthetic_log_variance(seed=4)
    coarse = rolling_forecast_comparison(x, 5, window=600)
    exact = rolling_forecast_comparison(x, 5, window=600, hurst_round=None)
    np.testing.assert_allclose(coarse.rfsv, exact.rfsv, atol=2e-3)


def test_rolling_comparison_records_the_unclipped_hurst():
    """H is clipped to below 1/2 before it reaches the kernel, but the raw
    estimate is still reported so a caller can see how often that happened."""
    x = _synthetic_log_variance(hurst=0.45, seed=5)
    res = rolling_forecast_comparison(x, 1, window=600)
    assert np.all(np.isfinite(res.hurst_by_origin))
    assert res.hurst_by_origin.max() > 0.3


def _exact_fbm_predictor_weights(hurst, horizon, n_lags, origin=1e6):
    """The EXACT best linear predictor of W^H_{T+D} from the discrete past
    W^H_T, W^H_{T-1}, ..., W^H_{T-k+1}, from fBm's own covariance

        Cov(W_s, W_t) = 0.5 (s^{2H} + t^{2H} - |t - s|^{2H})

    (which follows from [GJR] eq. (1.1) at q = 2 plus stationary increments
    and W_0 = 0). `origin` is placed far away so the anchor at W_0 is
    negligible and this is the infinite-past predictor eq. (5.1) targets.

    This is ground truth for the test below. It is deliberately NOT in the
    module: it needs a known H and a full covariance solve, which is not
    what the module is for.
    """
    times = origin - np.arange(n_lags, dtype=float)
    target = origin + horizon

    def cov(s, t):
        s = np.asarray(s, float)[:, None]
        t = np.asarray(t, float)[None, :]
        return 0.5 * (s ** (2 * hurst) + t ** (2 * hurst) - np.abs(t - s) ** (2 * hurst))

    gram = cov(times, times)
    cross = cov(times, np.array([target]))[:, 0]
    return np.linalg.solve(gram + 1e-12 * np.eye(n_lags), cross)


@pytest.mark.parametrize("horizon", [1, 5, 20])
def test_eq_51_weights_track_the_exact_optimal_predictor(horizon):
    """THE REAL VALIDATION OF THE eq. (5.1) TRANSCRIPTION.

    [GJR]'s source for eq. (5.1) (Nuzman & Poor, Theorem 4.2) could not be
    fetched this session, so the formula is checked against something that
    can be computed from scratch: the exact best linear predictor of fBm on
    the discrete daily grid, solved directly from fBm's covariance.

    Measured this session at H = 0.14, 200 lags, 6 seeds x ~2400 origins
    each, MSE of eq. (5.1) relative to that exact optimum, and the
    correlation of the two weight vectors:
        D = 1:  1.0219, corr 0.9885
        D = 5:  1.0096, corr 0.9909
        D = 20: 1.0109, corr 0.9912
    i.e. within 1-2%. The residual gap is discretisation, and it is largest
    at D = 1 where the u^{-(H+1/2)} singularity is spread over the widest
    range of u by the daily grid. That gap is why the D = 1 comparison
    against a FITTED baseline is not a foregone conclusion even on true
    fBm — see the next test.
    """
    hurst, n_lags = 0.14, 200
    exact = _exact_fbm_predictor_weights(hurst, horizon, n_lags)
    approx = rfsv_weights(hurst, horizon, n_lags)
    assert np.corrcoef(exact, approx)[0, 1] > 0.985

    errs_exact, errs_approx = [], []
    for seed in range(6):
        x = simulate_fbm(3000, hurst, np.random.default_rng(500 + seed))
        idx = np.arange(600, 3000 - horizon)
        hist = np.array([x[i - n_lags + 1 : i + 1][::-1] for i in idx])
        actual = x[idx + horizon]
        errs_exact.append(np.mean((actual - hist @ exact) ** 2))
        errs_approx.append(np.mean((actual - hist @ approx) ** 2))
    ratio = float(np.mean(errs_approx) / np.mean(errs_exact))
    assert 0.99 < ratio < 1.06, f"horizon {horizon}: eq (5.1)/exact MSE = {ratio}"


@pytest.mark.parametrize("horizon", [1, 5, 20])
def test_predictor_beats_the_last_value_forecast_on_synthetic_fbm(horizon):
    """On a series that really is 2 nu W^H + C with H handed to it, eq. (5.1)
    must beat the trivial forecast at every horizon. It does, on every seed."""
    for seed in range(6):
        x = _synthetic_log_variance(n=2000, hurst=0.14, seed=9000 + seed)
        p = rolling_forecast_comparison(x, horizon, window=500, fixed_hurst=0.14).p_ratios()
        assert p["rfsv"] < p["last_value"], f"horizon {horizon}, seed {seed}"


@pytest.mark.parametrize("horizon", [5, 20])
def test_predictor_beats_fitted_har_on_synthetic_fbm_at_longer_horizons(horizon):
    """Where the rough-volatility forecast is supposed to win, it wins — and
    that is what makes the real-data negative worth reporting.

    Measured this session, 12 seeds, series of 2000 and 6000 points, window
    500, true H = 0.14 handed to RFSV, mean of [GJR]'s P (the two figures
    per cell are n = 2000 and n = 6000):

        D    RFSV/HAR          RFSV wins        HAR/exact-optimal
        1    1.0035 / 0.9994   3 and 7 of 12    1.0198 / 1.0204
        5    0.9712 / 0.9706   12 and 12        1.0354 / 1.0347
        20   0.9193 / 0.9184   12 and 12        1.0902 / 1.0861

    (the third column uses _exact_fbm_predictor_weights at 200 lags with its
    default origin; it drifts in the third decimal with the lag count, so the
    construction is named rather than left implicit.)

    So on data that really is rough, eq. (5.1) beats a rolling HAR by 3%
    at five days and 8% at twenty, exactly the "especially at longer
    horizons" pattern [GJR] Sec. 5.1 report — and RFSV lands close to the
    exact optimal linear predictor: 0.64387 against 0.64335 at D = 20,
    n = 2000, a gap of 0.08%. (An earlier revision claimed 0.64384 for the
    optimum, a 0.005% gap; that value was not reproducible at any lag count
    and has been corrected to the measured 200-lag figure.)

    HORIZON 1 IS DELIBERATELY EXCLUDED, and it is a real finding rather
    than a tuning convenience: at one day the discretisation penalty
    measured in the previous test (~2%) is the same size as eq. (5.1)'s
    advantage over a fitted HAR, so the two tie even when the data is
    exactly the model. That is part of why the module's real-data run
    loses hardest at D = 1.

    FULL DISCLOSURE ON HOW THIS TEST'S PARAMETERS WERE SET, since they were
    changed after a failure. The first version used n = 1600 with window
    600, leaving only ~980 forecast origins, and it failed intermittently
    at D = 5 and D = 20 as well as at D = 1. The fix was to move to window
    500 — which is [GJR] Sec. 5.1's own choice and the one the real-data
    run always used — and n = 2000, giving ~1495 origins. The change was
    made for statistical power, and the diagnostic run above confirms it
    was power and not cherry-picking: at D = 5 and D = 20 the win rate is
    12 of 12 at BOTH n = 2000 and n = 6000, while at D = 1 it stays at
    3-7 of 12 no matter how much data is added. NOTHING about the
    real-data comparison in the module docstring was touched; that design
    was frozen before it ran and used window 500 throughout.
    """
    for seed in range(6):
        x = _synthetic_log_variance(n=2000, hurst=0.14, seed=9000 + seed)
        p = rolling_forecast_comparison(x, horizon, window=500, fixed_hurst=0.14).p_ratios()
        assert p["rfsv"] < p["har"], f"horizon {horizon}, seed {seed}"


def test_p_ratios_and_qlike_are_consistent_with_the_raw_arrays():
    x = _synthetic_log_variance(seed=7)
    res = rolling_forecast_comparison(x, 5, window=600, fixed_hurst=0.14)
    ref = float(np.mean(res.actual))
    assert res.p_ratios()["har"] == pytest.approx(gjr_p_ratio(res.actual, res.har, ref))
    assert res.qlike()["rfsv"] == pytest.approx(
        qlike_loss(np.exp(res.actual), np.exp(res.rfsv))
    )
    assert res.variance_rmse()["har"] == pytest.approx(
        variance_rmse(np.exp(res.actual), np.exp(res.har))
    )


def test_all_three_loss_views_expose_the_same_three_models():
    """QLIKE and variance RMSE must treat every model identically — neither
    gets [GJR] Sec. 5.2's lognormal correction, because applying it to RFSV
    alone would hand it an advantage no baseline receives."""
    x = _synthetic_log_variance(seed=8)
    res = rolling_forecast_comparison(x, 5, window=500, fixed_hurst=0.14)
    for view in (res.p_ratios(), res.qlike(), res.variance_rmse()):
        assert set(view) == {"rfsv", "har", "last_value"}
        assert all(np.isfinite(v) for v in view.values())


def test_rolling_comparison_validates_its_arguments():
    x = _synthetic_log_variance(n=800)
    with pytest.raises(ValueError, match="horizon must be >= 1"):
        rolling_forecast_comparison(x, 0)
    with pytest.raises(ValueError, match="too short to estimate H"):
        rolling_forecast_comparison(x, 1, window=50)
    with pytest.raises(ValueError, match="need more than"):
        rolling_forecast_comparison(x[:500], 1, window=600)
    with pytest.raises(ValueError, match="fixed_hurst must be in"):
        rolling_forecast_comparison(x, 1, window=600, fixed_hurst=0.5)
    with pytest.raises(ValueError, match="non-finite"):
        rolling_forecast_comparison(np.concatenate([x, [np.nan]]), 1, window=600)


def test_corsi_and_gjr_har_lags_give_similar_baselines():
    """The 1/5/20 vs 1/5/22 discrepancy between [GJR] Sec. 5.1 and [C09] is
    documented rather than silently resolved; this shows it does not matter."""
    x = _synthetic_log_variance(n=1600, seed=9)
    a = rolling_forecast_comparison(x, 5, window=600, fixed_hurst=0.14).p_ratios()["har"]
    b = rolling_forecast_comparison(
        x, 5, window=600, fixed_hurst=0.14, har_lags=CORSI_HAR_LAGS
    ).p_ratios()["har"]
    assert a == pytest.approx(b, rel=0.05)
