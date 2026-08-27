"""Empirical-Bayes (James-Stein style) shrinkage across a POPULATION of trials.

Companion to deflated_sharpe.py, answering the complementary question.
deflated_sharpe.py asks, of one trial at a time: "given that N configurations
were searched, could this one's Sharpe have come from luck?" — a binary-ish
significance gate applied to each trial in isolation. This module instead uses
the whole population of trials as its own reference distribution: it estimates
how much TRUE effect-size dispersion exists across trials, then pulls each
individual noisy estimate toward the population mean by an amount proportional
to how unreliable that individual estimate is.

Motivated by Chen & Dim, "High-Throughput Asset Pricing" (arXiv:2311.10685).
Their finding, applying empirical Bayes to 136,000 mined long-short strategies:
"Multiple testing methods popular in finance fail to identify most out-of-sample
performers," while EB "uniquely provides unbiased predictions with transparent
intuition." Their shrinkage formula (their Eq. 15) is stated in t-statistic
space with a prior mean of zero:

    E(mu_i | t_i) = [1 - 1/Var_hat(t_i)] * t_i

DELIBERATE DEVIATION FROM THE PAPER, and why. Chen & Dim shrink t-statistics.
That is safe for them because their 136,000 strategies all run over
substantially the same sample, so every t_i carries the same amount of
information. It is NOT safe here. This project's trials span daily 5-year
equity backtests, 365-day-a-year crypto series, and hourly intraday bars, so
n_observations varies by more than an order of magnitude across the population.
A common prior on the true t-statistic would assert that a trial with more data
has a LARGER true effect, since t = SR * sqrt(n) grows with n at fixed true
Sharpe — an artifact of sample length masquerading as economic signal.

So this module shrinks ANNUALIZED SHARPE RATIOS with heteroskedastic standard
errors se_i, which is the economically comparable quantity across families. The
paper's homoskedastic form is the special case se_i = 1 for all i, and
test_empirical_bayes_shrinkage.py asserts that this implementation reproduces
their 1 - 1/Var(t) factor exactly in that case.

VERIFICATION PERFORMED THIS SESSION — every numeric claim below was produced by
direct execution against this project's own venv, not recalled from literature:

- se(SR_hat) ~= sqrt((1 + SR^2/2) / (n - 1)) was confirmed by 200,000-replication
  Monte Carlo against a KNOWN injected true Sharpe, across true daily Sharpes
  of 0.00/0.03/0.06/0.10/0.20/0.40 and n of 60/250/750/2500. Empirical-to-
  analytic ratio stayed within 0.998-1.012 everywhere. The (n-1) denominator
  (the convention deflated_sharpe.py's PSR already uses via its sqrt(n-1) term)
  beat the (n) denominator that sharpe_robustness.py uses at small n
  (1.011 vs 1.020 at n=60) and the two are indistinguishable by n=750, so the
  (n-1) form is used here.

- DerSimonian-Laird vs Paule-Mandel for tau^2 (k=60, 4000 reps): contrary to the
  common recommendation to prefer the iterative Paule-Mandel estimator, DL was
  never worse and was sometimes materially better. For tau^2 >= 0.25 the two are
  indistinguishable (both within 1.5% bias in BOTH a near-homoskedastic
  se~U(.35,.45) regime and a strongly heteroskedastic se~U(.10,1.20) one). They
  separate as tau^2 falls, and every separation favours DL: at tau^2 = 0.09 under
  strong heteroskedasticity DL was +0.5% biased against PM's +9.3%; at
  tau^2 = 0.01, +58% against PM's +131%; and at true tau^2 = 0 exactly, DL
  returned 0.0101 against PM's 0.0173. Since the near-zero regime is exactly the
  one this project cares most about — the honest null in which apparent
  cross-trial dispersion is entirely noise — DL is the default. PM remains
  available for cross-checking.

- BOTH estimators are UPWARD-biased at true tau^2 = 0, necessarily so: the
  underlying moment estimator (Q - df)/C is unbiased but can go negative, and
  clipping it at zero can only raise its mean. Measured at k=60, true tau^2=0:
  DL mean 0.0101-0.0113, i.e. an apparent tau_hat of ~0.10 annualized-Sharpe
  units out of pure noise. CONSEQUENCE, and the single most important caveat in
  this module: tau_hat > 0 is NOT by itself evidence that real dispersion
  exists. Use heterogeneity_p_value (Cochran's Q against chi2_{k-1}), which IS
  a proper test of the tau^2 = 0 null, before reading anything into tau_hat.

- Instability of tau^2_hat vs the number of sibling trials k (3000 reps, true
  tau^2 = 0.09, se~U(.25,.55)): the coefficient of variation of the estimate
  itself runs 168%/137%/105%/78%/66%/53%/36% at k=3/5/10/20/30/50/100, and the
  probability of collapsing to a degenerate exactly-zero prior runs
  47%/36%/22%/10%/4.6%/1.8%/0%. As with MIN_TRIALS_FOR_DSR there is no sharp
  cutoff; k=10 is roughly where the estimate stops being decided by which two or
  three trials happened to land in the sample.

TWO MEASURED LIMITATIONS THAT CHANGE HOW THE OUTPUT SHOULD BE READ:

- SHRINKAGE DOES NOT RE-RANK A HOMOSKEDASTIC POPULATION. When every trial has
  the same se, theta_shrunk is an affine, strictly increasing function of
  theta_hat, so the post-shrinkage ordering is IDENTICAL to a naive raw-Sharpe
  sort. Measured over 200 populations of 212 trials: Spearman correlation
  against the true theta_i was 0.5786 for both raw and shrunk at tau^2 = 0.09,
  and top-10 precision 2.77 for both. EB's contribution there is an unbiased
  MAGNITUDE, not a better order — which is precisely Chen & Dim's own reported
  result that "naively mining for the largest Sharpe ratios leads to similar
  performance ... though EB uniquely provides unbiased predictions". Re-ranking
  only becomes real when the se_i differ, and there it genuinely helps: with
  se~U(0.10,1.40), Spearman rose 0.3664 -> 0.4478 and top-10 precision 1.21 ->
  2.19 at tau^2 = 0.09.

- A SINGLE GENUINELY-SKILLED TRIAL IN A LARGE NULL POPULATION GETS ERASED. The
  Gaussian prior has thin tails and one outlier barely moves a variance
  estimated from 212 trials. Measured (K=212, se=0.40, one planted skilled
  trial): at a true t-stat of 3.0 or 5.0, tau_hat stayed at exactly 0 and the
  planted trial's shrunk estimate collapsed to the population mean (-0.040 and
  -0.036 against true Sharpes of 1.2 and 2.0). It took a t-stat near 10 before
  tau_hat became non-zero and the estimate survived (0.857 of a true 4.0). A
  SUBPOPULATION is recovered far more readily — 10 skilled trials at t=3 gave
  tau_hat 0.267 and put 8 of the 10 in the top 10. This is the known cost of a
  single-Gaussian prior, and it is exactly why Chen & Dim fit a TWO-COMPONENT
  NORMAL MIXTURE by quasi-maximum likelihood instead: the mixture's second
  component supplies the fat tail a lone real edge needs to survive. Adopting
  that prior is the natural next step and is deliberately NOT attempted here.

WHAT THIS CORRECTS, AND WHAT IT DOES NOT. Shrinkage fixes the noise in trials'
estimates RELATIVE TO EACH OTHER. It does not fix a bias shared by the whole
population. If only "interesting" configurations were ever recorded, the
population mean mu_hat is itself selected-upward, and shrinking toward it pulls
every trial toward a contaminated target rather than away from it. Passing
prior_mean=0.0 (Chen & Dim's own choice of target) is the conservative response
and is why that parameter exists.

References:
  Chen & Dim (2023), "High-Throughput Asset Pricing", arXiv:2311.10685.
  DerSimonian & Laird (1986), "Meta-analysis in clinical trials",
    Controlled Clinical Trials 7(3), 177-188. -- the tau^2 moment estimator.
  Paule & Mandel (1982), J. Res. Natl. Bur. Stand. 87(5), 377-385.
  Cochran (1954), Biometrics 10(1), 101-129. -- the Q heterogeneity statistic.
  Higgins & Thompson (2002), Statistics in Medicine 21(11), 1539-1558. -- I^2.
  Efron & Morris (1973), JASA 68(341), 117-130. -- the EB/James-Stein framing.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq
from scipy.stats import chi2, norm

# Below this many sibling trials the tau^2 estimate is dominated by which
# handful of trials happened to be sampled -- CV > 100% and a >20% chance of
# collapsing to an exactly-zero prior (see the module docstring's measured
# table). Deliberately stricter than deflated_sharpe.MIN_TRIALS_FOR_DSR = 5,
# because estimating a whole variance COMPONENT from k trials is a harder
# problem than estimating the sigma_SR scale that the DSR benchmark needs.
MIN_TRIALS_FOR_SHRINKAGE = 10

# Matches deflated_sharpe.MIN_OBSERVATIONS_FOR_PSR: sqrt(n-1) is undefined below
# this, and the SE formula shares that denominator.
MIN_OBSERVATIONS_FOR_SE = 2

# Brent bracketing for the Paule-Mandel root find. The upper bound is doubled
# from 1.0 until the estimating function turns negative; this caps that search
# so a pathological input cannot spin forever.
_PM_MAX_BRACKET_DOUBLINGS = 200
_PM_XTOL = 1e-12


@dataclass
class TrialObservation:
    """One already-completed trial. `theta_hat` and `se` must be in the SAME
    units as each other and as every other trial in the population -- this
    module does no unit conversion whatsoever, exactly as
    deflated_sharpe.probabilistic_sharpe_ratio does none. Annualized Sharpe is
    the intended choice (see module docstring); pass se from
    sharpe_standard_error()."""

    trial_id: str
    theta_hat: float
    se: float
    group: str | None = None
    label: str | None = None


@dataclass
class ShrunkTrial:
    trial_id: str
    label: str | None
    group: str | None
    theta_hat: float
    se: float
    # tau^2 / (tau^2 + se_i^2): the weight this trial's OWN estimate keeps.
    # 1.0 = trusted as-is, 0.0 = discarded entirely in favour of the prior mean.
    shrinkage_weight: float
    theta_shrunk: float
    posterior_sd: float
    prob_positive: float
    rank_raw: int
    rank_shrunk: int


@dataclass
class EmpiricalBayesResult:
    n_trials: int
    mu_hat: float
    tau2_hat: float
    tau_hat: float
    tau2_method: str
    prior_mean_was_estimated: bool
    # Cochran's Q against chi2_{k-1}: a PROPER test of the tau^2 = 0 null.
    # Read this before reading tau_hat -- see module docstring.
    q_statistic: float
    q_df: int
    heterogeneity_p_value: float
    i_squared: float
    mean_se_squared: float
    observed_variance: float
    mean_shrinkage_weight: float
    trials: list[ShrunkTrial]
    floor_met: bool
    interpretation: str


def sharpe_standard_error(
    sharpe: float,
    n_observations: int,
    *,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float | None:
    """Standard error of a Sharpe estimate, in whatever scale `sharpe` is in.

    UNIT-AGNOSTIC and scale-equivariant, deliberately, for the same reason
    deflated_sharpe.probabilistic_sharpe_ratio takes no periods_per_year: pass
    an annualized Sharpe and you get an annualized SE, pass a daily Sharpe and
    you get a daily SE. There is one catch that makes this NOT a pure rescaling,
    and it is the reason this function is not simply sqrt(1/(n-1)): the
    (1 + SR^2/2) correction term is itself a function of SR, so it must be
    evaluated at the SAME scale as n_observations counts. Feeding an ANNUALIZED
    Sharpe in alongside a DAILY n inflates that term by the annualization factor
    (a 0.06 daily Sharpe becomes 0.95 annualized, turning a correction of
    1.0018 into 1.45) -- the identical unit-mixing bug deflated_sharpe.py's
    module docstring documents.

    So: callers holding an annualized Sharpe should pass the DAILY Sharpe here
    and re-annualize the returned SE themselves, which is exactly what
    sharpe_standard_error_annualized() does.

    The default skewness=0 / kurtosis=3 reduces to the classic Mertens (2002)
    normal-case form. Non-normal inputs use the same generalized variance term
    deflated_sharpe.probabilistic_sharpe_ratio uses, and inherit its guard: that
    term can go non-positive for real input combinations (skew=3, kurt=1.5,
    sr=1 -> -1.875), in which case there is no honest SE to return and this
    returns None rather than a nan."""
    if n_observations < MIN_OBSERVATIONS_FOR_SE:
        return None
    variance_term = 1 - skewness * sharpe + ((kurtosis - 1) / 4) * sharpe**2
    if variance_term <= 0 or not np.isfinite(variance_term):
        return None
    se = np.sqrt(variance_term / (n_observations - 1))
    return float(se) if np.isfinite(se) and se > 0 else None


def sharpe_standard_error_annualized(
    sharpe_annualized: float,
    n_observations: int,
    *,
    periods_per_year: float,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float | None:
    """The one place in this module that crosses between annualized and
    per-period scale, mirroring compute_deflated_sharpe's role in its own
    module. De-annualizes the point estimate, computes the per-period SE at
    the matching scale, then re-annualizes the SE.

    periods_per_year must be whatever was used to annualize sharpe_annualized
    in the first place -- 252 for equity/bond/FX/commodity,
    metrics.CALENDAR_DAYS_PER_YEAR (365) for crypto, and the bars-per-year count
    for intraday families. Getting it wrong biases se_i for that family only,
    which in a pooled fit silently changes how hard THAT family gets shrunk
    relative to the others."""
    scale = np.sqrt(periods_per_year)
    se_per_period = sharpe_standard_error(
        sharpe_annualized / scale, n_observations, skewness=skewness, kurtosis=kurtosis
    )
    if se_per_period is None:
        return None
    return float(se_per_period * scale)


def _weighted_mean(theta: np.ndarray, weights: np.ndarray) -> float:
    return float(np.sum(weights * theta) / np.sum(weights))


def cochran_q(theta: np.ndarray, se: np.ndarray) -> tuple[float, int, float]:
    """Cochran's Q and its chi2_{k-1} p-value, testing the null that every trial
    shares one common true effect (tau^2 = 0).

    This is the honest gate on whether ANY real cross-trial dispersion exists.
    tau_hat alone cannot answer that question, because tau_hat is clipped at
    zero and therefore upward-biased under the null -- measured at 0.0101 for a
    true value of exactly 0 (see module docstring). Returns (Q, df, p)."""
    w = 1.0 / se**2
    mu_fixed = _weighted_mean(theta, w)
    q = float(np.sum(w * (theta - mu_fixed) ** 2))
    df = len(theta) - 1
    if df < 1:
        return q, df, float("nan")
    return q, df, float(chi2.sf(q, df))


def dersimonian_laird_tau2(theta: np.ndarray, se: np.ndarray) -> float:
    """DerSimonian & Laird (1986) method-of-moments estimator of the
    between-trial variance, generalized to unequal se_i.

    tau^2 = max(0, (Q - (k-1)) / C),  C = sum(w) - sum(w^2)/sum(w),  w = 1/se^2

    The intuition is exactly the one the task describes as
    "weighted_var(theta_hat) - mean(se_i^2)": Q's expectation under tau^2 = 0 is
    its degrees of freedom k-1, so any excess of Q over k-1 is dispersion the
    within-trial noise cannot account for, and C is the scaling that converts
    that excess back into variance units. Closed-form, no iteration.

    Chosen as this module's default over Paule-Mandel on MEASURED grounds, not
    on the literature's general recommendation -- see the module docstring."""
    w = 1.0 / se**2
    q, df, _ = cochran_q(theta, se)
    if df < 1:
        return 0.0
    sum_w = np.sum(w)
    c = sum_w - np.sum(w**2) / sum_w
    if c <= 0 or not np.isfinite(c):
        return 0.0
    return max(0.0, float((q - df) / c))


def _pm_estimating_function(tau2: float, theta: np.ndarray, se: np.ndarray) -> float:
    w = 1.0 / (tau2 + se**2)
    mu = _weighted_mean(theta, w)
    return float(np.sum(w * (theta - mu) ** 2) - (len(theta) - 1))


def paule_mandel_tau2(theta: np.ndarray, se: np.ndarray) -> float:
    """Paule & Mandel (1982): choose tau^2 so that the generalized Q computed
    with the FULL weights 1/(tau^2 + se_i^2) equals its own expectation k-1.

    Equivalent to iterating DerSimonian-Laird to a fixed point. Kept as a
    cross-check rather than the default: measured to be indistinguishable from
    DL for tau^2 >= 0.25 and progressively WORSE below that (+9.3% vs DL's
    +0.5% at true tau^2 = 0.09, and +131% vs +58% at true tau^2 = 0.01, both
    under strong heteroskedasticity).

    The estimating function is monotonically decreasing in tau^2, so a sign
    change brackets a unique root."""
    if len(theta) - 1 < 1:
        return 0.0
    if _pm_estimating_function(0.0, theta, se) <= 0:
        return 0.0
    hi = 1.0
    for _ in range(_PM_MAX_BRACKET_DOUBLINGS):
        if _pm_estimating_function(hi, theta, se) < 0:
            break
        hi *= 2.0
    else:
        return float(hi)  # never turned negative -- degenerate, report the cap
    return float(brentq(_pm_estimating_function, 0.0, hi, args=(theta, se), xtol=_PM_XTOL))


TAU2_METHODS = {
    "dersimonian-laird": dersimonian_laird_tau2,
    "paule-mandel": paule_mandel_tau2,
}


def _build_interpretation(
    n_trials: int,
    floor_met: bool,
    tau_hat: float,
    mu_hat: float,
    heterogeneity_p: float,
    i_squared: float,
    mean_weight: float,
    prior_mean_was_estimated: bool,
) -> str:
    if not floor_met:
        return (
            f"Only {n_trials} trial(s) in this population (need >={MIN_TRIALS_FOR_SHRINKAGE}) — too few to "
            "estimate cross-trial dispersion. At this count the tau^2 estimate has a coefficient of "
            "variation above 100% and better than a 1-in-5 chance of collapsing to exactly zero, so no "
            "shrinkage was applied and the raw estimates are returned unchanged."
        )

    target = f"the estimated population mean ({mu_hat:.3f})" if prior_mean_was_estimated else f"a fixed prior mean of {mu_hat:.3f}"

    if tau_hat == 0.0:
        # Total collapse. Every theta_shrunk equals mu exactly, so rank_shrunk
        # is whatever order the inputs arrived in. Saying "the top-ranked trial
        # after shrinkage is X" here would be inventing a result out of a tie.
        return (
            f"Across N={n_trials} trials the estimated true-effect dispersion is exactly zero "
            f"(Cochran's Q p={heterogeneity_p:.3f}): the observed spread in these Sharpes is no larger than "
            "their own measurement noise alone would produce. Every trial's shrunk estimate is therefore "
            f"IDENTICAL — all equal to {mu_hat:.3f} — and the post-shrinkage ranking is an arbitrary "
            "tie-break carrying no information. The honest conclusion is that no trial in this population "
            "is distinguishable from any other, not that whichever one happens to sort first is best."
        )

    if heterogeneity_p > 0.10:
        return (
            f"Across N={n_trials} trials, Cochran's Q cannot reject the null that every trial shares one "
            f"single common true effect (p={heterogeneity_p:.3f}). The honest reading is that the spread "
            f"between these trials' Sharpes is consistent with pure estimation noise: the apparent "
            f"tau_hat={tau_hat:.3f} is not evidence of real dispersion, because tau_hat is clipped at zero "
            f"and is upward-biased under exactly this null. Each trial keeps only {mean_weight:.0%} of its "
            f"own estimate on average, the rest being pulled to {target}. Post-shrinkage ranking here "
            "reflects sample size as much as skill and should not be treated as a discovery."
        )

    return (
        f"Across N={n_trials} trials, Cochran's Q rejects the single-common-effect null "
        f"(p={heterogeneity_p:.4f}), and I^2={i_squared:.0%} of the observed spread is attributable to "
        f"genuine differences between trials rather than within-trial noise. Estimated true-effect "
        f"dispersion tau_hat={tau_hat:.3f} around a mean of {mu_hat:.3f}. Each trial retains "
        f"{mean_weight:.0%} of its own estimate on average, the remainder shrunk toward {target}. "
        "Real dispersion existing does NOT mean any individual trial is validated — it means the "
        "ranking below carries some signal rather than none."
    )


def fit_empirical_bayes(
    observations: Sequence[TrialObservation],
    *,
    tau2_method: str = "dersimonian-laird",
    prior_mean: float | None = None,
) -> EmpiricalBayesResult:
    """Fit the Gaussian-Gaussian empirical-Bayes model over an already-collected
    population of trials and return each trial's shrunk posterior.

    Model:  theta_hat_i | theta_i ~ N(theta_i, se_i^2)   [known se_i]
            theta_i               ~ N(mu, tau^2)         [unknown mu, tau^2]
    Posterior mean:  mu + B_i * (theta_hat_i - mu),  B_i = tau^2/(tau^2 + se_i^2)

    prior_mean=None estimates mu from the data as the tau^2-aware weighted mean.
    Pass prior_mean=0.0 for Chen & Dim's own choice of shrinking toward zero,
    which is the conservative option when the recorded population may itself be
    selected — see the module docstring's "what this does not correct".

    PURE FUNCTION. Touches no database, mutates no input, and is wired into no
    pipeline. Diagnostic output for human review only."""
    if tau2_method not in TAU2_METHODS:
        raise ValueError(f"tau2_method must be one of {sorted(TAU2_METHODS)}, got {tau2_method!r}")

    usable = [o for o in observations if np.isfinite(o.theta_hat) and np.isfinite(o.se) and o.se > 0]
    k = len(usable)
    theta = np.array([o.theta_hat for o in usable], dtype=float)
    se = np.array([o.se for o in usable], dtype=float)

    floor_met = k >= MIN_TRIALS_FOR_SHRINKAGE

    if not floor_met:
        # No shrinkage at all rather than shrinkage the data cannot support.
        # An unreliable correction applied silently is worse than no correction.
        trials = _assemble(usable, theta, theta, se, np.ones(k), np.full(k, np.nan), np.full(k, np.nan))
        return EmpiricalBayesResult(
            n_trials=k,
            mu_hat=float(np.mean(theta)) if k else float("nan"),
            tau2_hat=float("nan"),
            tau_hat=float("nan"),
            tau2_method=tau2_method,
            prior_mean_was_estimated=prior_mean is None,
            q_statistic=float("nan"),
            q_df=max(0, k - 1),
            heterogeneity_p_value=float("nan"),
            i_squared=float("nan"),
            mean_se_squared=float(np.mean(se**2)) if k else float("nan"),
            observed_variance=float(np.var(theta, ddof=1)) if k > 1 else float("nan"),
            mean_shrinkage_weight=1.0,
            trials=trials,
            floor_met=False,
            interpretation=_build_interpretation(k, False, float("nan"), float("nan"), float("nan"), float("nan"), 1.0, prior_mean is None),
        )

    q_stat, q_df, q_p = cochran_q(theta, se)
    tau2 = TAU2_METHODS[tau2_method](theta, se)
    i_squared = max(0.0, (q_stat - q_df) / q_stat) if q_stat > 0 else 0.0

    # Weights use the FULL variance tau^2 + se_i^2 (random-effects weighting),
    # not the fixed-effects 1/se_i^2. Using fixed-effects weights here would
    # over-trust the longest-sample trials in setting the shrinkage target.
    w = 1.0 / (tau2 + se**2)
    mu = _weighted_mean(theta, w) if prior_mean is None else float(prior_mean)

    shrink_w = tau2 / (tau2 + se**2)
    theta_shrunk = mu + shrink_w * (theta - mu)

    # Posterior variance, conditional on (mu_hat, tau2_hat) being correct:
    #   B_i * se_i^2                        -- the usual EB posterior variance
    # + (1 - B_i)^2 * Var(mu_hat)           -- extra, since mu was itself estimated
    # HONEST UNDERSTATEMENT: this propagates uncertainty in mu but NOT the
    # (large, per the docstring's CV table) uncertainty in tau^2 itself. Real
    # posterior intervals are wider than posterior_sd implies.
    var_mu = 1.0 / np.sum(w) if prior_mean is None else 0.0
    posterior_var = shrink_w * se**2 + (1.0 - shrink_w) ** 2 * var_mu
    posterior_sd = np.sqrt(posterior_var)

    with np.errstate(divide="ignore", invalid="ignore"):
        prob_positive = np.where(posterior_sd > 0, norm.cdf(theta_shrunk / posterior_sd), np.nan)

    trials = _assemble(usable, theta, theta_shrunk, se, shrink_w, posterior_sd, prob_positive)

    return EmpiricalBayesResult(
        n_trials=k,
        mu_hat=mu,
        tau2_hat=float(tau2),
        tau_hat=float(np.sqrt(tau2)),
        tau2_method=tau2_method,
        prior_mean_was_estimated=prior_mean is None,
        q_statistic=q_stat,
        q_df=q_df,
        heterogeneity_p_value=q_p,
        i_squared=float(i_squared),
        mean_se_squared=float(np.mean(se**2)),
        observed_variance=float(np.var(theta, ddof=1)),
        mean_shrinkage_weight=float(np.mean(shrink_w)),
        trials=trials,
        floor_met=True,
        interpretation=_build_interpretation(
            k, True, float(np.sqrt(tau2)), mu, q_p, float(i_squared), float(np.mean(shrink_w)), prior_mean is None
        ),
    )


def _assemble(
    usable: Sequence[TrialObservation],
    theta: np.ndarray,
    theta_shrunk: np.ndarray,
    se: np.ndarray,
    shrink_w: np.ndarray,
    posterior_sd: np.ndarray,
    prob_positive: np.ndarray,
) -> list[ShrunkTrial]:
    """Rank 1 = best. Computed on both scales so callers can see directly
    whether shrinkage reordered anything."""
    rank_raw = _ranks_desc(theta)
    rank_shrunk = _ranks_desc(theta_shrunk)
    return [
        ShrunkTrial(
            trial_id=o.trial_id,
            label=o.label,
            group=o.group,
            theta_hat=float(theta[i]),
            se=float(se[i]),
            shrinkage_weight=float(shrink_w[i]),
            theta_shrunk=float(theta_shrunk[i]),
            posterior_sd=float(posterior_sd[i]),
            prob_positive=float(prob_positive[i]),
            rank_raw=int(rank_raw[i]),
            rank_shrunk=int(rank_shrunk[i]),
        )
        for i, o in enumerate(usable)
    ]


def _ranks_desc(values: np.ndarray) -> np.ndarray:
    order = np.argsort(-values, kind="stable")
    ranks = np.empty(len(values), dtype=int)
    ranks[order] = np.arange(1, len(values) + 1)
    return ranks


def trial_from_experiment_run(
    run_id: int,
    strategy_name: str,
    ticker_a: str,
    ticker_b: str,
    results_json: str,
    *,
    periods_per_year: float = 252.0,
) -> TrialObservation | None:
    """Map one stored ExperimentRun row onto a TrialObservation.

    WHY THIS IS NOT A ONE-LINER, and why it is worth having as tested code: the
    observation count this estimator needs is NOT a column on experiment_runs.
    The table promotes sharpe_net, sharpe_gross, max_drawdown_net, win_rate and
    num_trades to real columns, but num_trades is a count of TRADES, not of
    return observations, and using it as n would understate se_i by roughly the
    average holding period — inflating confidence in exactly the direction that
    manufactures false positives. The genuine observation count lives only
    inside results_json, at $.deflated_sharpe.n_observations (with
    $.n_trading_days as a fallback).

    Reads $.deflated_sharpe for n_observations, skewness and kurtosis, which
    deflated_sharpe.compute_deflated_sharpe already computed and stored on the
    way in, so the SE here is built from the same moments its PSR/DSR used
    rather than from a second, possibly divergent estimate.

    Returns None for any row that cannot yield an honest (sharpe, se) pair —
    a non-"ok" run, a missing sub-object, too few observations, or a
    non-positive PSR variance term. Silently defaulting such a row to a
    plausible-looking SE would put a fabricated trial into the population.

    periods_per_year defaults to 252 because every writer of this table today
    (run_and_store_pairs_backtest, run_and_store_momentum_backtest,
    SweepRunner._process_combo) is an equity strategy. A 365-day-a-year family
    stored here in future must pass its own value — see
    metrics.CALENDAR_DAYS_PER_YEAR."""
    try:
        payload = json.loads(results_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None

    sharpe = payload.get("sharpe_net")
    ds = payload.get("deflated_sharpe") or {}
    n_obs = ds.get("n_observations") or payload.get("n_trading_days")
    if sharpe is None or n_obs is None:
        return None

    se = sharpe_standard_error_annualized(
        float(sharpe),
        int(n_obs),
        periods_per_year=periods_per_year,
        skewness=float(ds.get("skewness", 0.0) or 0.0),
        kurtosis=float(ds.get("kurtosis", 3.0) or 3.0),
    )
    if se is None:
        return None

    pair = ticker_a if ticker_a == ticker_b else f"{ticker_a}/{ticker_b}"
    return TrialObservation(
        trial_id=str(run_id),
        theta_hat=float(sharpe),
        se=se,
        group=strategy_name,
        label=f"{strategy_name} {pair} (n={int(n_obs)})",
    )


def fit_empirical_bayes_by_group(
    observations: Sequence[TrialObservation],
    *,
    tau2_method: str = "dersimonian-laird",
    prior_mean: float | None = None,
) -> dict[str, EmpiricalBayesResult]:
    """Fit a SEPARATE prior per group, as Chen & Dim do per strategy family
    ("separately for each strategy family").

    This matters and is not cosmetic. Pooling families with genuinely different
    true-effect distributions into one prior inflates tau^2 with between-family
    variation, which then under-shrinks every trial in every family. Splitting
    costs statistical power per group, so groups below
    MIN_TRIALS_FOR_SHRINKAGE come back with floor_met=False and unshrunk
    estimates rather than a fabricated prior."""
    groups: dict[str, list[TrialObservation]] = {}
    for o in observations:
        groups.setdefault(o.group or "ungrouped", []).append(o)
    return {
        name: fit_empirical_bayes(members, tau2_method=tau2_method, prior_mean=prior_mean)
        for name, members in sorted(groups.items())
    }
