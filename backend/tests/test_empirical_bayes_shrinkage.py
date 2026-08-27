"""Validation of the empirical-Bayes shrinkage estimator.

THE LOAD-BEARING TESTS IN THIS FILE ARE THE GROUND-TRUTH ONES.

This project has already been burned once by an estimator that passed a full
suite of self-consistency and rank-order tests and was still badly wrong: the
hand-rolled Corwin-Schultz spread estimator (commits ffede8c -> c32ee32), whose
tests only checked that the code computed what the author intended and that its
output was monotone in the right direction. Neither property is evidence of
correctness. It shipped with a severe literature-documented bias in exactly the
regime that mattered and had to be replaced wholesale.

So the tests that matter here are the ones that CONSTRUCT the population
themselves — draw true effects theta_i from a known N(mu, tau^2), corrupt them
with known noise, and check that the estimator recovers the truth it was never
shown. Specifically:

  1. test_recovers_known_mu_and_tau2*        -- parameter recovery vs. truth
  2. test_shrinkage_beats_raw_on_mse*        -- THE point of shrinkage: the
                                                shrunk estimates must be closer
                                                to the TRUE theta_i than the raw
                                                observations are. If this fails,
                                                the estimator is worthless no
                                                matter how self-consistent.
  3. test_matches_chen_dim_closed_form       -- an EXTERNAL check: reduces
                                                exactly to the published
                                                1 - 1/Var(t) factor.
  4. test_q_test_is_calibrated_under_null    -- the heterogeneity test's false-
                                                positive rate is what it claims.

Everything else in this file is a guard rail, not a validation.
"""

import json

import numpy as np
import pytest
from scipy.stats import norm

from app.services.research_lab.empirical_bayes_shrinkage import (
    MIN_TRIALS_FOR_SHRINKAGE,
    TrialObservation,
    cochran_q,
    dersimonian_laird_tau2,
    fit_empirical_bayes,
    fit_empirical_bayes_by_group,
    paule_mandel_tau2,
    sharpe_standard_error,
    sharpe_standard_error_annualized,
    trial_from_experiment_run,
)

# --- helpers -----------------------------------------------------------------


def _simulate(mu: float, tau2: float, k: int, seed: int, se_lo: float = 0.25, se_hi: float = 0.55):
    """Build a population with KNOWN truth. Returns (observations, theta_true)."""
    rng = np.random.default_rng(seed)
    se = rng.uniform(se_lo, se_hi, k)
    theta_true = rng.normal(mu, np.sqrt(tau2), k)
    theta_hat = theta_true + rng.normal(0.0, se)
    obs = [
        TrialObservation(trial_id=f"t{i}", theta_hat=float(theta_hat[i]), se=float(se[i]))
        for i in range(k)
    ]
    return obs, theta_true


# --- 1. PARAMETER RECOVERY AGAINST KNOWN TRUTH -------------------------------


@pytest.mark.parametrize(
    "mu,tau2",
    [
        (0.0, 0.09),  # tau = 0.30 Sharpe units — moderate real dispersion
        (0.35, 0.09),  # non-zero population mean
        (-0.20, 0.25),  # negative mean, larger dispersion
        (0.0, 1.00),  # tau = 1.0 — dispersion far exceeding typical se
    ],
)
def test_recovers_known_mu_and_tau2(mu, tau2):
    """Average the estimator over many independent populations and confirm it
    lands on the truth it was never told. Averaging is essential: a single
    k=200 draw has a tau^2 CV around 26%, so a one-shot assertion would be
    testing the seed, not the estimator."""
    mus, tau2s = [], []
    for seed in range(60):
        obs, _ = _simulate(mu, tau2, k=200, seed=seed)
        res = fit_empirical_bayes(obs)
        mus.append(res.mu_hat)
        tau2s.append(res.tau2_hat)

    assert np.mean(mus) == pytest.approx(mu, abs=0.02), f"mu_hat mean {np.mean(mus):.4f} vs true {mu}"
    # 8% relative tolerance: the estimator is unbiased before the max(0, .)
    # clip, and at tau2 >= 0.09 with k=200 the clip almost never binds.
    assert np.mean(tau2s) == pytest.approx(tau2, rel=0.08), f"tau2_hat mean {np.mean(tau2s):.4f} vs true {tau2}"


def test_recovers_near_zero_tau2_by_shrinking_hard():
    """The regime this project cares most about: essentially ALL of the apparent
    cross-trial dispersion is noise. The estimator must recognise that and
    collapse nearly every trial onto the population mean."""
    weights, tau2s, pvals = [], [], []
    for seed in range(60):
        obs, _ = _simulate(mu=0.0, tau2=0.0, k=200, seed=1000 + seed)
        res = fit_empirical_bayes(obs)
        weights.append(res.mean_shrinkage_weight)
        tau2s.append(res.tau2_hat)
        pvals.append(res.heterogeneity_p_value)

    # tau^2 is clipped at zero and therefore cannot be unbiased under this null;
    # it must nonetheless be SMALL relative to the within-trial variances
    # (mean se^2 ~= 0.16 here).
    assert np.mean(tau2s) < 0.02, f"tau2_hat mean {np.mean(tau2s):.4f} should be ~0"
    # Hard shrinkage: trials keep well under a fifth of their own estimate.
    assert np.mean(weights) < 0.20, f"mean shrinkage weight {np.mean(weights):.3f} should be near 0"
    # And the Q-test should not be manufacturing significance.
    assert np.mean([p < 0.05 for p in pvals]) < 0.12


def test_large_tau2_leaves_estimates_nearly_alone():
    """The mirror image: when true dispersion dwarfs the measurement noise,
    shrinkage should be almost a no-op. An estimator that shrinks hard here
    would be destroying real signal."""
    weights = []
    for seed in range(40):
        obs, _ = _simulate(mu=0.0, tau2=9.0, k=200, seed=2000 + seed)  # tau=3.0 vs se~0.4
        res = fit_empirical_bayes(obs)
        weights.append(res.mean_shrinkage_weight)
    assert np.mean(weights) > 0.97, f"mean shrinkage weight {np.mean(weights):.4f} should be ~1"


# --- 2. THE POINT OF SHRINKAGE: MSE AGAINST KNOWN TRUE VALUES ----------------


@pytest.mark.parametrize(
    "mu,tau2,label",
    [
        (0.0, 0.0, "tau2=0 (pure noise population)"),
        (0.30, 0.01, "tau2 tiny relative to se"),
        (0.0, 0.09, "tau2 comparable to se"),
        (-0.15, 0.25, "tau2 above se"),
        (0.0, 9.00, "tau2 dwarfing se"),
    ],
)
def test_shrinkage_beats_raw_on_mse(mu, tau2, label):
    """THE decisive test. Shrinkage exists to reduce mean-squared error against
    the TRUE effects. Prove that directly, against truth we injected ourselves,
    at every dispersion regime — not merely that the formula runs."""
    mse_raw_total, mse_shrunk_total = 0.0, 0.0
    for seed in range(80):
        obs, theta_true = _simulate(mu, tau2, k=100, seed=3000 + seed)
        res = fit_empirical_bayes(obs)
        raw = np.array([t.theta_hat for t in res.trials])
        shrunk = np.array([t.theta_shrunk for t in res.trials])
        mse_raw_total += float(np.mean((raw - theta_true) ** 2))
        mse_shrunk_total += float(np.mean((shrunk - theta_true) ** 2))

    assert mse_shrunk_total < mse_raw_total, (
        f"{label}: shrunk MSE {mse_shrunk_total:.5f} did NOT beat raw MSE {mse_raw_total:.5f}"
    )


def test_mse_improvement_is_dramatic_when_dispersion_is_noise():
    """Not just 'better' — quantify it. When the population is pure noise the
    shrunk estimator should cut MSE by most of its value, because the best
    possible estimate of every trial really is the common mean."""
    mse_raw, mse_shrunk = 0.0, 0.0
    for seed in range(80):
        obs, theta_true = _simulate(mu=0.0, tau2=0.0, k=100, seed=4000 + seed)
        res = fit_empirical_bayes(obs)
        raw = np.array([t.theta_hat for t in res.trials])
        shrunk = np.array([t.theta_shrunk for t in res.trials])
        mse_raw += float(np.mean((raw - theta_true) ** 2))
        mse_shrunk += float(np.mean((shrunk - theta_true) ** 2))
    ratio = mse_shrunk / mse_raw
    assert ratio < 0.15, f"expected a >85% MSE reduction under a pure-noise population, got {1 - ratio:.1%}"


def test_shrinkage_beats_raw_on_mse_with_extreme_heteroskedasticity():
    """Unequal sample sizes are the whole reason this module works in Sharpe
    space rather than the paper's t-stat space. Confirm the MSE gain survives
    se_i spanning more than an order of magnitude."""
    mse_raw, mse_shrunk = 0.0, 0.0
    for seed in range(80):
        obs, theta_true = _simulate(mu=0.1, tau2=0.09, k=100, seed=5000 + seed, se_lo=0.05, se_hi=1.50)
        res = fit_empirical_bayes(obs)
        raw = np.array([t.theta_hat for t in res.trials])
        shrunk = np.array([t.theta_shrunk for t in res.trials])
        mse_raw += float(np.mean((raw - theta_true) ** 2))
        mse_shrunk += float(np.mean((shrunk - theta_true) ** 2))
    assert mse_shrunk < mse_raw


def test_paule_mandel_also_beats_raw_on_mse():
    """The non-default tau^2 estimator must clear the same bar."""
    mse_raw, mse_shrunk = 0.0, 0.0
    for seed in range(40):
        obs, theta_true = _simulate(mu=0.0, tau2=0.09, k=100, seed=6000 + seed)
        res = fit_empirical_bayes(obs, tau2_method="paule-mandel")
        raw = np.array([t.theta_hat for t in res.trials])
        shrunk = np.array([t.theta_shrunk for t in res.trials])
        mse_raw += float(np.mean((raw - theta_true) ** 2))
        mse_shrunk += float(np.mean((shrunk - theta_true) ** 2))
    assert mse_shrunk < mse_raw


# --- 3. EXTERNAL CHECK AGAINST THE PUBLISHED CLOSED FORM ---------------------


def test_matches_chen_dim_closed_form():
    """Chen & Dim (arXiv:2311.10685) Eq. 15, in t-statistic space:

        E(mu_i | t_i) = [1 - 1/Var_hat(t_i)] * t_i

    A t-statistic has se = 1 by construction, so their homoskedastic form is
    the se_i = 1 special case of this module's heteroskedastic estimator. This
    is a genuine EXTERNAL check — the target comes from the published paper,
    not from this implementation.

    Derivation of the exact identity, so the tolerance can be 1e-12 rather than
    a fudge: with all se_i = 1 the DL weights are w_i = 1, so sum_w = k,
    sum_w^2 = k, and C = k - k/k = k - 1. Then
        tau^2 = (Q - (k-1))/(k-1) = Q/(k-1) - 1 = Var_hat(t) - 1
    (Var_hat with ddof=1, since Q = sum (t_i - tbar)^2 when w_i = 1), and
        B = tau^2/(tau^2 + 1) = (Var_hat - 1)/Var_hat = 1 - 1/Var_hat(t).
    """
    rng = np.random.default_rng(99)
    t_stats = rng.normal(0.4, 1.8, 300)  # Var(t) comfortably > 1, so tau^2 > 0
    obs = [TrialObservation(trial_id=f"t{i}", theta_hat=float(v), se=1.0) for i, v in enumerate(t_stats)]

    res = fit_empirical_bayes(obs, prior_mean=0.0)

    expected_factor = 1.0 - 1.0 / np.var(t_stats, ddof=1)
    for trial in res.trials:
        assert trial.shrinkage_weight == pytest.approx(expected_factor, abs=1e-12)
        # With the prior mean pinned at zero, the posterior is exactly the
        # paper's [1 - 1/Var(t)] * t.
        assert trial.theta_shrunk == pytest.approx(expected_factor * trial.theta_hat, abs=1e-12)


def test_chen_dim_form_degenerates_when_variance_below_one():
    """If the observed t-stats are LESS dispersed than unit noise alone would
    make them, 1 - 1/Var(t) is negative — there is no real dispersion to find
    and the estimator must clip to total shrinkage, not return a negative
    (sign-flipping) weight."""
    rng = np.random.default_rng(5)
    t_stats = rng.normal(0.0, 0.3, 200)  # Var(t) ~= 0.09 << 1
    obs = [TrialObservation(trial_id=f"t{i}", theta_hat=float(v), se=1.0) for i, v in enumerate(t_stats)]
    res = fit_empirical_bayes(obs, prior_mean=0.0)
    assert res.tau2_hat == 0.0
    assert all(t.shrinkage_weight == 0.0 for t in res.trials)
    assert all(t.theta_shrunk == 0.0 for t in res.trials)


# --- 4. THE HETEROGENEITY TEST'S OWN CALIBRATION -----------------------------


def test_q_test_is_calibrated_under_null():
    """Cochran's Q is the module's honest gate on whether ANY real dispersion
    exists (tau_hat cannot serve that role — it is clipped at zero and so
    upward-biased under the null). A gate is only worth having if its
    false-positive rate is what it claims, so measure it against a population
    built with tau^2 = exactly 0."""
    pvals = []
    for seed in range(400):
        obs, _ = _simulate(mu=0.2, tau2=0.0, k=40, seed=7000 + seed)
        pvals.append(fit_empirical_bayes(obs).heterogeneity_p_value)
    rejection_rate = float(np.mean([p < 0.05 for p in pvals]))
    assert 0.02 < rejection_rate < 0.09, f"nominal 5% test rejected {rejection_rate:.1%} of the time"


def test_q_test_has_power_against_real_dispersion():
    """The complement: when dispersion IS real, the gate must actually open."""
    pvals = []
    for seed in range(100):
        obs, _ = _simulate(mu=0.0, tau2=0.25, k=40, seed=8000 + seed)
        pvals.append(fit_empirical_bayes(obs).heterogeneity_p_value)
    assert float(np.mean([p < 0.05 for p in pvals])) > 0.90


# --- sharpe_standard_error ---------------------------------------------------


def test_sharpe_se_matches_monte_carlo_reference():
    """Reference values from the 200,000-replication Monte Carlo run this
    session against a KNOWN injected true Sharpe (see module docstring). The
    analytic formula was within 1.2% of the empirical SE at every point tested;
    these assertions pin the analytic side of that comparison."""
    # sr_daily=0.0, n=250 -> sqrt(1/249) = 0.063372
    assert sharpe_standard_error(0.0, 250) == pytest.approx(0.063372, abs=1e-5)
    # sr_daily=0.40, n=750 -> sqrt(1.08/749) = 0.037974
    assert sharpe_standard_error(0.40, 750) == pytest.approx(0.037974, abs=1e-5)


def test_sharpe_se_shrinks_with_sample_size():
    ses = [sharpe_standard_error(0.05, n) for n in [30, 60, 250, 750, 2500]]
    assert all(s is not None for s in ses)
    assert ses == sorted(ses, reverse=True)


def test_sharpe_se_guards_match_deflated_sharpe_module():
    # Same non-positive variance term deflated_sharpe.probabilistic_sharpe_ratio
    # guards against: skew=3, kurt=1.5, sr=1 -> 1 - 3 + 0.125 = -1.875.
    assert sharpe_standard_error(1.0, 100, skewness=3.0, kurtosis=1.5) is None
    # Below the observation floor, sqrt(n-1) is undefined.
    assert sharpe_standard_error(0.1, 1) is None


def test_annualized_se_round_trips_the_scale():
    """se_annualized must equal se_daily * sqrt(periods_per_year), with the
    (1 + SR^2/2) term evaluated at DAILY scale. The bug being guarded against
    is evaluating that term at annualized scale."""
    sr_ann, n, ppy = 0.95, 750, 252
    got = sharpe_standard_error_annualized(sr_ann, n, periods_per_year=ppy)
    expected = sharpe_standard_error(sr_ann / np.sqrt(ppy), n) * np.sqrt(ppy)
    assert got == pytest.approx(expected, abs=1e-12)
    # And it must NOT equal the unit-mixed version.
    wrong = sharpe_standard_error(sr_ann, n) * np.sqrt(ppy)
    assert abs(got - wrong) > 0.05


def test_crypto_periods_per_year_changes_the_se():
    """365-day crypto vs 252-day equity: the same annualized Sharpe over the
    same number of bars gets a different SE, matching metrics.py's
    CALENDAR_DAYS_PER_YEAR distinction."""
    a = sharpe_standard_error_annualized(0.9, 1000, periods_per_year=252)
    b = sharpe_standard_error_annualized(0.9, 1000, periods_per_year=365)
    assert a is not None and b is not None
    assert a != b
    assert b > a  # sqrt(365) > sqrt(252) dominates the small SR-correction term


# --- tau^2 estimator internals ----------------------------------------------


def test_dl_and_pm_agree_when_dispersion_is_substantial():
    """Measured this session at k=60: indistinguishable for tau^2 >= 0.25.
    They are genuinely different estimators — one closed-form, one an iterative
    root-find — so agreeing to within 10% is a real cross-check, not a
    tautology. Below tau^2 = 0.25 they diverge and DL is the better of the two,
    which is why it is the default; see the module docstring."""
    obs, _ = _simulate(mu=0.0, tau2=0.25, k=300, seed=42)
    theta = np.array([o.theta_hat for o in obs])
    se = np.array([o.se for o in obs])
    dl = dersimonian_laird_tau2(theta, se)
    pm = paule_mandel_tau2(theta, se)
    assert dl == pytest.approx(pm, rel=0.10)


def test_tau2_estimators_clip_at_zero_never_negative():
    for seed in range(30):
        obs, _ = _simulate(mu=0.0, tau2=0.0, k=30, seed=9000 + seed)
        theta = np.array([o.theta_hat for o in obs])
        se = np.array([o.se for o in obs])
        assert dersimonian_laird_tau2(theta, se) >= 0.0
        assert paule_mandel_tau2(theta, se) >= 0.0


def test_cochran_q_is_zero_for_identical_estimates():
    theta = np.array([0.3, 0.3, 0.3, 0.3])
    se = np.array([0.1, 0.2, 0.3, 0.4])
    q, df, p = cochran_q(theta, se)
    assert q == pytest.approx(0.0, abs=1e-12)
    assert df == 3
    assert p == pytest.approx(1.0)


# --- shrinkage mechanics -----------------------------------------------------


def test_noisier_trials_are_shrunk_harder():
    """The defining property: shrinkage must be proportional to unreliability."""
    obs = [
        TrialObservation(trial_id=f"t{i}", theta_hat=1.0, se=se)
        for i, se in enumerate([0.05, 0.10, 0.20, 0.40, 0.80, 1.60] * 3)
    ]
    # Add spread so tau^2 > 0.
    obs += [TrialObservation(trial_id=f"s{i}", theta_hat=v, se=0.2) for i, v in enumerate([-1.0, 0.0, 2.0, 3.0])]
    res = fit_empirical_bayes(obs)
    assert res.tau2_hat > 0
    by_se = sorted(res.trials, key=lambda t: t.se)
    weights = [t.shrinkage_weight for t in by_se]
    assert weights == sorted(weights, reverse=True)


def test_shrunk_estimates_lie_between_raw_and_prior_mean():
    obs, _ = _simulate(mu=0.4, tau2=0.09, k=100, seed=77)
    res = fit_empirical_bayes(obs)
    for t in res.trials:
        lo, hi = sorted([res.mu_hat, t.theta_hat])
        assert lo - 1e-12 <= t.theta_shrunk <= hi + 1e-12


def test_prior_mean_zero_shrinks_toward_zero_not_the_population_mean():
    obs, _ = _simulate(mu=1.5, tau2=0.04, k=100, seed=88)
    free = fit_empirical_bayes(obs)
    pinned = fit_empirical_bayes(obs, prior_mean=0.0)
    assert free.mu_hat == pytest.approx(1.5, abs=0.1)
    assert pinned.mu_hat == 0.0
    assert np.mean([t.theta_shrunk for t in pinned.trials]) < np.mean([t.theta_shrunk for t in free.trials])


def test_posterior_sd_is_below_raw_se():
    """Borrowing strength across the population must tighten each trial's
    interval relative to standing alone."""
    obs, _ = _simulate(mu=0.0, tau2=0.09, k=100, seed=123)
    res = fit_empirical_bayes(obs)
    for t in res.trials:
        assert t.posterior_sd < t.se


def test_prob_positive_matches_posterior():
    obs, _ = _simulate(mu=0.2, tau2=0.09, k=100, seed=222)
    res = fit_empirical_bayes(obs)
    for t in res.trials:
        assert t.prob_positive == pytest.approx(norm.cdf(t.theta_shrunk / t.posterior_sd), abs=1e-12)


def test_ranking_is_reordered_by_heteroskedastic_shrinkage():
    """A high-Sharpe trial measured over a short sample can and should fall
    below a slightly lower-Sharpe trial measured over a long one. If shrinkage
    never reorders anything it adds nothing to a raw-Sharpe sort."""
    obs = [
        TrialObservation(trial_id="short_but_flashy", theta_hat=1.40, se=1.20),
        TrialObservation(trial_id="long_and_steady", theta_hat=1.10, se=0.15),
    ]
    obs += [
        TrialObservation(trial_id=f"filler{i}", theta_hat=v, se=0.30)
        for i, v in enumerate([0.1, -0.2, 0.35, 0.0, -0.1, 0.25, 0.05, -0.3, 0.15, 0.2])
    ]
    res = fit_empirical_bayes(obs)
    by_id = {t.trial_id: t for t in res.trials}
    assert by_id["short_but_flashy"].rank_raw < by_id["long_and_steady"].rank_raw  # raw: flashy wins
    assert by_id["long_and_steady"].rank_shrunk < by_id["short_but_flashy"].rank_shrunk  # shrunk: steady wins


# --- the two documented limitations, enforced rather than merely asserted ----


def test_homoskedastic_shrinkage_never_reorders():
    """DOCUMENTED LIMITATION 1. With equal se_i, theta_shrunk is an affine,
    strictly increasing function of theta_hat, so the post-shrinkage ranking is
    the raw ranking exactly. Anyone reading a shrunk leaderboard of equal-length
    backtests is reading a raw-Sharpe leaderboard with different numbers on it."""
    rng = np.random.default_rng(606)
    obs = [TrialObservation(f"t{i}", float(v), 0.40) for i, v in enumerate(rng.normal(0, 0.7, 200))]
    res = fit_empirical_bayes(obs)
    assert res.tau2_hat > 0
    for t in res.trials:
        assert t.rank_shrunk == t.rank_raw


def test_single_outlier_is_erased_but_a_subpopulation_survives():
    """DOCUMENTED LIMITATION 2. One genuinely-skilled trial among 211 nulls does
    not move a variance estimated from 212 trials, so the Gaussian prior crushes
    it. A subpopulation of the same per-trial strength is recovered easily.

    This test exists to keep that limitation VISIBLE. It is the reason Chen &
    Dim fit a two-component normal mixture rather than a single Gaussian, and
    the reason no one should read a null result here as proof that no single
    pattern in a mined family works."""
    k, se, true_sr = 212, 0.40, 1.2  # per-trial t-stat of 3.0

    def population(n_skilled, seed):
        rng = np.random.default_rng(seed)
        truth = np.zeros(k)
        truth[:n_skilled] = true_sr
        hat = truth + rng.normal(0, se, k)
        return [TrialObservation(f"p{i:03d}", float(hat[i]), se) for i in range(k)]

    lone = fit_empirical_bayes(population(1, seed=7))
    assert lone.tau2_hat == 0.0, "a single t=3 outlier should not register as dispersion"
    planted = next(t for t in lone.trials if t.trial_id == "p000")
    assert abs(planted.theta_shrunk) < 0.1, "its estimate collapses to the population mean"

    many = fit_empirical_bayes(population(10, seed=110))
    # tau_hat (the SD), not tau2_hat (the variance) — measured at 0.267 here.
    assert many.tau_hat > 0.15, "ten skilled trials SHOULD register as real dispersion"
    recovered = sum(1 for t in many.trials if int(t.trial_id[1:]) < 10 and t.rank_shrunk <= 10)
    assert recovered >= 7


# --- floors, guards, grouping ------------------------------------------------


def test_below_floor_returns_unshrunk_estimates():
    obs, _ = _simulate(mu=0.0, tau2=0.09, k=MIN_TRIALS_FOR_SHRINKAGE - 1, seed=1)
    res = fit_empirical_bayes(obs)
    assert res.floor_met is False
    assert np.isnan(res.tau2_hat)
    assert all(t.theta_shrunk == t.theta_hat for t in res.trials)
    assert all(t.shrinkage_weight == 1.0 for t in res.trials)
    assert "too few" in res.interpretation.lower()


def test_at_floor_shrinkage_engages():
    obs, _ = _simulate(mu=0.0, tau2=0.09, k=MIN_TRIALS_FOR_SHRINKAGE, seed=2)
    res = fit_empirical_bayes(obs)
    assert res.floor_met is True
    assert not np.isnan(res.tau2_hat)


def test_non_finite_and_non_positive_se_rows_are_dropped():
    obs, _ = _simulate(mu=0.0, tau2=0.09, k=20, seed=3)
    obs += [
        TrialObservation(trial_id="bad_se_zero", theta_hat=5.0, se=0.0),
        TrialObservation(trial_id="bad_se_neg", theta_hat=5.0, se=-0.2),
        TrialObservation(trial_id="bad_theta", theta_hat=float("nan"), se=0.3),
        TrialObservation(trial_id="bad_inf", theta_hat=float("inf"), se=0.3),
    ]
    res = fit_empirical_bayes(obs)
    assert res.n_trials == 20
    assert {"bad_se_zero", "bad_se_neg", "bad_theta", "bad_inf"}.isdisjoint({t.trial_id for t in res.trials})


def test_unknown_tau2_method_raises():
    obs, _ = _simulate(mu=0.0, tau2=0.09, k=20, seed=4)
    with pytest.raises(ValueError, match="tau2_method"):
        fit_empirical_bayes(obs, tau2_method="james-stein-ish")


def test_empty_population_does_not_crash():
    res = fit_empirical_bayes([])
    assert res.n_trials == 0
    assert res.floor_met is False
    assert res.trials == []


def test_grouped_fit_estimates_a_separate_prior_per_group():
    """Pooling families with different true-effect distributions inflates tau^2
    with BETWEEN-family variation and then under-shrinks everything. Build two
    families that differ only in dispersion and confirm the per-group fit sees
    that difference while the pooled fit blurs it."""
    tight, _ = _simulate(mu=0.0, tau2=0.0, k=120, seed=11)
    wide, _ = _simulate(mu=0.0, tau2=1.0, k=120, seed=12)
    obs = [TrialObservation(o.trial_id + "_a", o.theta_hat, o.se, group="tight") for o in tight]
    obs += [TrialObservation(o.trial_id + "_b", o.theta_hat, o.se, group="wide") for o in wide]

    per_group = fit_empirical_bayes_by_group(obs)
    assert set(per_group) == {"tight", "wide"}
    assert per_group["tight"].tau2_hat < 0.05
    assert per_group["wide"].tau2_hat > 0.5

    pooled = fit_empirical_bayes(obs)
    # The pooled prior sits between the two and therefore under-shrinks the
    # tight family badly — the exact failure mode grouping exists to avoid.
    assert pooled.tau2_hat > per_group["tight"].tau2_hat
    assert pooled.mean_shrinkage_weight > per_group["tight"].mean_shrinkage_weight


def test_grouped_fit_respects_the_floor_per_group():
    obs = [TrialObservation(f"a{i}", 0.1 * i, 0.3, group="big") for i in range(20)]
    obs += [TrialObservation(f"b{i}", 0.1 * i, 0.3, group="small") for i in range(4)]
    res = fit_empirical_bayes_by_group(obs)
    assert res["big"].floor_met is True
    assert res["small"].floor_met is False


# --- experiment_runs loader --------------------------------------------------


def _run_json(sharpe=0.85, n_obs=750, skew=0.1, kurt=4.0, n_trading_days=750):
    """Mirrors the real PairsBacktestResponse.model_dump_json() shape stored in
    experiment_runs.results_json (app/schemas/research_lab.py)."""
    return json.dumps(
        {
            "status": "ok",
            "sharpe_net": sharpe,
            "num_trades": 42,
            "n_trading_days": n_trading_days,
            "deflated_sharpe": {
                "sharpe_net_annualized": sharpe,
                "n_observations": n_obs,
                "skewness": skew,
                "kurtosis": kurt,
                "dsr": 0.31,
            },
        }
    )


def test_loader_reads_n_from_results_json_not_from_num_trades():
    """The trap this loader exists to avoid: num_trades (42 here) is a count of
    TRADES, not of return observations (750). Using it as n would understate
    se_i by ~4x and inflate confidence in the false-positive direction."""
    obs = trial_from_experiment_run(7, "pairs", "KO", "PEP", _run_json())
    assert obs is not None
    expected = sharpe_standard_error_annualized(0.85, 750, periods_per_year=252, skewness=0.1, kurtosis=4.0)
    assert obs.se == pytest.approx(expected, abs=1e-12)
    se_if_num_trades_used = sharpe_standard_error_annualized(0.85, 42, periods_per_year=252, skewness=0.1, kurtosis=4.0)
    assert obs.se < se_if_num_trades_used / 3


def test_loader_populates_identity_fields():
    obs = trial_from_experiment_run(7, "pairs", "KO", "PEP", _run_json())
    assert obs.trial_id == "7"
    assert obs.group == "pairs"
    assert obs.theta_hat == 0.85
    assert "KO/PEP" in obs.label
    # Momentum rows store ticker_a == ticker_b; the label must not read "AAPL/AAPL".
    solo = trial_from_experiment_run(8, "momentum", "AAPL", "AAPL", _run_json())
    assert "AAPL/AAPL" not in solo.label
    assert "AAPL" in solo.label


def test_loader_falls_back_to_n_trading_days():
    payload = json.loads(_run_json())
    del payload["deflated_sharpe"]["n_observations"]
    obs = trial_from_experiment_run(1, "pairs", "A", "B", json.dumps(payload))
    assert obs is not None
    assert obs.se == pytest.approx(
        sharpe_standard_error_annualized(0.85, 750, periods_per_year=252, skewness=0.1, kurtosis=4.0), abs=1e-12
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.pop("sharpe_net"),
        lambda p: (p.pop("deflated_sharpe"), p.pop("n_trading_days")),
        lambda p: p["deflated_sharpe"].update({"n_observations": 1}),
        # Non-positive PSR variance term — the deflated_sharpe.py guard.
        lambda p: p["deflated_sharpe"].update({"skewness": 300.0, "kurtosis": 1.5}),
    ],
)
def test_loader_returns_none_rather_than_fabricating_an_se(mutate):
    payload = json.loads(_run_json())
    mutate(payload)
    assert trial_from_experiment_run(1, "pairs", "A", "B", json.dumps(payload)) is None


def test_loader_survives_malformed_json():
    assert trial_from_experiment_run(1, "pairs", "A", "B", "not json at all") is None
    assert trial_from_experiment_run(1, "pairs", "A", "B", "[1,2,3]") is None
    assert trial_from_experiment_run(1, "pairs", "A", "B", "") is None


def test_loader_respects_periods_per_year():
    equity = trial_from_experiment_run(1, "pairs", "A", "B", _run_json())
    crypto = trial_from_experiment_run(1, "pairs", "A", "B", _run_json(), periods_per_year=365.0)
    assert crypto.se > equity.se


def test_interpretation_reports_the_null_honestly():
    """Under a pure-noise population the prose must say so, and must explicitly
    warn that tau_hat > 0 is not evidence of dispersion."""
    # seed 2 is one of the draws where the clip does NOT bind: tau2_hat lands at
    # 0.0104 (spuriously non-zero) while Q still cannot reject at p=0.246 —
    # exactly the trap this branch's prose exists to defuse.
    obs, _ = _simulate(mu=0.0, tau2=0.0, k=150, seed=2)
    res = fit_empirical_bayes(obs)
    assert res.tau2_hat > 0.0
    assert res.heterogeneity_p_value > 0.10
    text = res.interpretation.lower()
    assert "pure estimation noise" in text
    assert "not evidence" in text
    assert "should not be treated as a discovery" in text


def test_interpretation_discloses_the_degenerate_all_tied_case():
    """When tau_hat collapses to exactly zero, every shrunk estimate is the SAME
    number and rank_shrunk is just input order. Reporting a "top-ranked trial
    after shrinkage" from that would be manufacturing a finding out of a tie, so
    the prose has to name the degeneracy."""
    rng = np.random.default_rng(4242)
    # Observed spread strictly smaller than the stated se -> Q << df -> tau^2 = 0.
    obs = [
        TrialObservation(f"t{i}", float(v), 1.0)
        for i, v in enumerate(rng.normal(0.0, 0.2, 120))
    ]
    res = fit_empirical_bayes(obs)
    assert res.tau2_hat == 0.0
    shrunk = {round(t.theta_shrunk, 12) for t in res.trials}
    assert len(shrunk) == 1, "all shrunk estimates must be identical when tau^2 = 0"
    text = res.interpretation.lower()
    assert "identical" in text
    assert "arbitrary tie-break" in text
    assert "no trial in this population is distinguishable" in text
