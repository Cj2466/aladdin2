"""Validation of RMT denoising against KNOWN correct answers.

THE LOAD-BEARING TESTS IN THIS FILE ARE THE GROUND-TRUTH ONES — same
rationale and same scar as test_hrp_optimizer.py and
test_effective_n_clustering.py: a hand-rolled estimator in this codebase
once passed every self-consistency test its author wrote and was still
badly wrong, because no test ever fed it an input whose right answer was
known independently of the code. So:

  1. GROUND TRUTH WITH AN EXACTLY KNOWN ANSWER. The generator builds a
     population correlation matrix

         C = B B^T + (1 - s) I,   every row of B of norm sqrt(s)

     so diag(C) == 1 exactly (it is a genuine correlation matrix) and its
     spectrum is k spikes plus (N - k) eigenvalues EXACTLY equal to
     (1 - s). Sampling T draws from C therefore produces a spectrum that
     is k spikes plus a Marchenko-Pastur bulk whose sigma^2 is known to
     be exactly 1 - s. Both the signal COUNT (k) and the fitted VARIANCE
     (1 - s) are then checkable against numbers the estimator never saw.
     Measured across 75 such cases (N in {50,100,200,300}, T/N in
     {5,10}, k in {1,2,3,5,8}, 1-s in {0.3,0.5,0.7}) at the shipped
     bandwidth: 75/75 exact k, sigma^2 mean absolute error 0.072. The
     table for other bandwidths is in rmt_denoising.py's docstring.

  2. THE PURE-NOISE LIMIT. i.i.d. returns have no structure at all, so
     the honest denoised answer is the IDENTITY MATRIX, and the tests
     assert it to ~1e-15 rather than to a loose tolerance. This is the
     test that would catch a threshold applied in the wrong direction.

  3. REFERENCE AGREEMENT. The Marchenko-Pastur bounds are checked against
     the printed numbers in Plerou et al. (arXiv:cond-mat/0108023), and
     the two published algebraic forms of the bounds — Laloux et al.'s
     sigma^2(1 + 1/Q +/- 2 sqrt(1/Q)) and Lopez de Prado's
     var*(1 +/- (1/q)**.5)**2 — are asserted equal. The density is
     checked to integrate to 1 with mean sigma^2, which pins the
     normalizing constant that an informal transcription would drop.

  4. WIRING, BIT-EQUALITY. With the opt-in flags left alone, HRP is
     asserted to return float64-BIT-IDENTICAL weights to a snapshot of
     its pre-denoising behaviour, reconstructed here from its own
     primitives. Same standard as the HRP-into-the-runner regression
     tests (commit 739b07e), for the same reason: "defaults to off" is a
     claim, and an unasserted claim is a wish.
"""

import numpy as np
import pandas as pd
import pytest
from scipy.integrate import quad

from app.services.risk.hrp_optimizer import (
    compute_hrp_weights,
    compute_hrp_weights_from_returns,
    cov_to_corr,
    hrp_linkage,
    quasi_diagonal_order,
    recursive_bisection_weights,
)
from app.services.risk.rmt_denoising import (
    DEFAULT_KDE_BANDWIDTH,
    count_signal_eigenvalues,
    denoise_correlation_matrix,
    denoise_covariance_matrix,
    fit_marchenko_pastur,
    marchenko_pastur_bounds,
    marchenko_pastur_pdf,
)

# ---------------------------------------------------------------------------
# Ground-truth generators
# ---------------------------------------------------------------------------


def spiked_population_correlation(n: int, k: int, noise_share: float, seed: int) -> np.ndarray:
    """C = B B^T + noise_share * I, with every row of B of norm
    sqrt(1 - noise_share).

    Row-normalizing B is what makes this a GROUND TRUTH rather than an
    approximate one: it forces diag(B B^T) to be exactly (1 - noise_share)
    for every asset, so diag(C) is exactly 1 (a real correlation matrix)
    and the (n - k) non-spike eigenvalues are exactly `noise_share`. A
    generator with heterogeneous loadings would smear those (n - k)
    eigenvalues into a band, and "the true sigma^2" would stop being a
    single number worth asserting against."""
    rng = np.random.default_rng(seed)
    w = rng.standard_normal((n, k))
    w /= np.linalg.norm(w, axis=1, keepdims=True)
    b = np.sqrt(1.0 - noise_share) * w
    return b @ b.T + noise_share * np.eye(n)


def sample_from_population(pop: np.ndarray, t: int, seed: int) -> pd.DataFrame:
    """T i.i.d. Gaussian draws with the given population correlation."""
    n = pop.shape[0]
    rng = np.random.default_rng(seed)
    chol = np.linalg.cholesky(pop + 1e-12 * np.eye(n))
    return pd.DataFrame(
        rng.standard_normal((t, n)) @ chol.T, columns=[f"A{i}" for i in range(n)]
    )


def iid_returns(t: int, n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame(rng.standard_normal((t, n)), columns=[f"A{i}" for i in range(n)])


# ---------------------------------------------------------------------------
# 3. The formula itself, against published numbers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("q", [1.5, 2.5, 6.448, 10.0, 20.0])
@pytest.mark.parametrize("sigma2", [0.3, 0.74, 1.0])
def test_bounds_match_laloux_expanded_form(q: float, sigma2: float):
    """Laloux et al. (arXiv:cond-mat/9810255) eq. (3) writes the edges as
        lambda_max/min = sigma^2 (1 + 1/Q +/- 2 sqrt(1/Q))
    while Lopez de Prado's snippet 2.1 writes
        var*(1 -/+ (1./q)**.5)**2.
    These are the same by completing the square. Asserting it here means a
    future edit to either form is caught rather than argued about."""
    lo, hi = marchenko_pastur_bounds(q, sigma2)
    assert hi == pytest.approx(sigma2 * (1 + 1 / q + 2 * (1 / q) ** 0.5), rel=0, abs=1e-14)
    assert lo == pytest.approx(sigma2 * (1 + 1 / q - 2 * (1 / q) ** 0.5), rel=0, abs=1e-14)


def test_bounds_reproduce_plerou_published_numbers():
    """Plerou et al. (arXiv:cond-mat/0108023), Section IV: "We examine
    dt = 30 min returns for N = 1000 stocks, each containing L = 6448
    records. Thus Q = 6.448, and we obtain lambda_- = 0.36 and
    lambda_+ = 1.94 from Eq. (7)."

    Computed: 0.3675 and 1.9427. lambda_+ matches their printed value to
    the digit; lambda_- prints as 0.37 against their 0.36, consistent with
    truncation on their side rather than a formula difference — the
    tolerance below is deliberately loose enough to accept that and tight
    enough to reject any real disagreement."""
    lo, hi = marchenko_pastur_bounds(6448 / 1000, sigma2=1.0)
    assert hi == pytest.approx(1.94, abs=0.005)
    assert lo == pytest.approx(0.365, abs=0.01)
    # The paper's headline ratio: its largest eigenvalue "lambda_1000 ~= 50
    # for the 2-yr period, which is ~= 25 times larger than
    # lambda_+ = 1.94". 50/1.9427 is 25.74, so their "~= 25" is itself a
    # rounded statement — the tolerance says so rather than hiding it.
    assert 50.0 / hi == pytest.approx(25.0, abs=1.0)


@pytest.mark.parametrize("q", [1.5, 2.5, 6.448, 20.0])
@pytest.mark.parametrize("sigma2", [0.5, 1.0])
def test_density_is_normalized_with_mean_sigma2(q: float, sigma2: float):
    """The constant Q/(2 pi sigma^2) in Laloux eq. (3) is exactly what
    makes rho a probability density with mean sigma^2. Dropping or
    mistyping it is the classic transcription error, and it would be
    invisible to every other test in this file (the bounds, and therefore
    the signal count, do not depend on it) — but it WOULD silently
    corrupt the sigma^2 fit, which compares densities. Hence this test."""
    lo, hi = marchenko_pastur_bounds(q, sigma2)

    def rho(lam: float) -> float:
        return q / (2 * np.pi * sigma2 * lam) * np.sqrt(max((hi - lam) * (lam - lo), 0.0))

    mass, _ = quad(rho, lo, hi, limit=400)
    mean, _ = quad(lambda lam: lam * rho(lam), lo, hi, limit=400)
    assert mass == pytest.approx(1.0, abs=1e-6)
    assert mean == pytest.approx(sigma2, abs=1e-6)


def test_pdf_series_matches_the_closed_form_on_its_own_grid():
    pdf = marchenko_pastur_pdf(q=5.0, sigma2=0.8, pts=50)
    lo, hi = marchenko_pastur_bounds(5.0, 0.8)
    assert len(pdf) == 50
    assert pdf.index[0] == pytest.approx(lo)
    assert pdf.index[-1] == pytest.approx(hi)
    grid = pdf.index.to_numpy()
    expected = (
        5.0 / (2 * np.pi * 0.8 * grid) * ((hi - grid) * (grid - lo)) ** 0.5
    )
    np.testing.assert_allclose(pdf.to_numpy(), expected, rtol=0, atol=1e-15)
    # Both endpoints are zeros of the square root, so the density vanishes
    # there — the signature shape of the MP bulk.
    assert pdf.iloc[0] == pytest.approx(0.0, abs=1e-12)
    assert pdf.iloc[-1] == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("q", [0.5, 1.0, -3.0])
def test_q_at_or_below_one_is_refused(q: float):
    """Module guard, not a paper step: at Q = 1 the density diverges at
    lambda_minus = 0 (Laloux, p. 2) and below 1 the cited form does not
    apply."""
    with pytest.raises(ValueError, match="q must be > 1"):
        marchenko_pastur_bounds(q)


def test_count_signal_eigenvalues_is_the_reference_expression():
    """Lopez de Prado's worked example computes the signal count as
        eVal.shape[0] - np.diag(eVal)[::-1].searchsorted(eMax)
    i.e. the number of eigenvalues >= eMax. Pinned on a hand-checkable
    spectrum so a refactor cannot quietly turn >= into >."""
    desc = np.array([5.0, 3.0, 2.0, 1.0, 0.5])
    assert count_signal_eigenvalues(desc, 2.5) == 2
    assert count_signal_eigenvalues(desc, 0.1) == 5
    assert count_signal_eigenvalues(desc, 9.0) == 0
    # Exactly ON the threshold counts as signal (searchsorted side='left').
    assert count_signal_eigenvalues(desc, 2.0) == 3


# ---------------------------------------------------------------------------
# 2. Pure noise -> the identity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("t", "n"), [(2000, 200), (1000, 100), (1500, 300)])
def test_pure_noise_denoises_to_the_identity(t: int, n: int):
    """i.i.d. returns contain nothing real. Every eigenvalue must fall
    inside the noise band, so the constant-residual step replaces the
    WHOLE spectrum with its mean — which for a correlation matrix is
    trace/N = 1 exactly — and V I V^T is the identity.

    This is the direction-of-threshold test: an implementation that kept
    eigenvalues BELOW lambda_plus as signal, or that compared against
    lambda_minus, would return something visibly non-diagonal here."""
    corr = iid_returns(t, n, seed=7).corr()
    result = denoise_correlation_matrix(corr, q=t / n)

    assert result.n_signal == 0
    assert result.n_noise == n
    np.testing.assert_allclose(result.correlation.to_numpy(), np.eye(n), rtol=0, atol=1e-12)
    # Not vacuous: the RAW matrix is nowhere near the identity.
    off_diag = corr.to_numpy()[~np.eye(n, dtype=bool)]
    assert np.abs(off_diag).max() > 0.05


def test_small_n_pure_noise_produces_a_finite_size_false_positive():
    """A DISCLOSED LIMITATION, recorded as a test rather than left to be
    rediscovered. The Marchenko-Pastur edges are an N -> infinity result.
    Laloux et al., p. 2: "Note that the above results are only valid in
    the limit N -> infinity. For finite N, the singularities present at
    both edges are smoothed: the edges become somewhat blurred, with a
    small probability of finding eigenvalues above lambda_max and below
    lambda_min, which goes to zero when N becomes large."

    Measured here: at N = 50, T = 500 on i.i.d. data — no structure
    whatsoever — exactly one eigenvalue lands above lambda_plus and is
    declared "signal". The same generator at N = 200 and N = 300 gives
    zero false positives (the test above). So on small universes a
    reported signal count of 1-2 is NOT evidence of a real factor, and
    this test exists so nobody has to guess whether that is a bug."""
    corr = iid_returns(500, 50, seed=7).corr()
    result = denoise_correlation_matrix(corr, q=10.0)

    assert result.n_signal == 1  # spurious: the data are i.i.d.
    assert result.eigenvalues[0] > result.fit.lambda_plus
    # The consequence is bounded, not catastrophic: the matrix is still
    # close to the identity, just not exactly it.
    off_diag = result.correlation.to_numpy()[~np.eye(50, dtype=bool)]
    assert np.abs(off_diag).max() < 0.2


def test_pure_noise_fit_saturates_at_the_upper_bound_and_reports_success():
    """Lopez de Prado's optimizer bounds sigma^2 into (1e-5, 1-1e-5), so
    the honest answer for structureless data — sigma^2 = 1 — is not
    representable. MEASURED behaviour, asserted so it cannot change
    unnoticed: the fit CONVERGES (success=True) onto the upper bound
    0.99999. That matters because it is NOT the reference code's
    `else: var = 1` failure fallback, and a reader seeing 1.0 in a report
    would otherwise be unable to tell the two apart."""
    corr = iid_returns(2000, 200, seed=7).corr()
    fit = fit_marchenko_pastur(
        np.linalg.eigvalsh(corr.to_numpy())[::-1], q=10.0, bandwidth=DEFAULT_KDE_BANDWIDTH
    )
    assert fit.fit_succeeded is True
    assert fit.sigma2 == pytest.approx(1 - 1e-5, abs=1e-9)


# ---------------------------------------------------------------------------
# 1. Spiked ground truth: known k, known sigma^2
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("k", [1, 2, 3, 5, 8])
@pytest.mark.parametrize("noise_share", [0.3, 0.5, 0.7])
def test_recovers_the_known_number_of_factors(k: int, noise_share: float):
    """The population has exactly k spikes above a bulk of exactly
    (n - k) eigenvalues equal to noise_share. The estimator sees only a
    sample and must recover k."""
    n, t = 100, 1000
    pop = spiked_population_correlation(n, k, noise_share, seed=3)
    corr = sample_from_population(pop, t, seed=3).corr()

    result = denoise_correlation_matrix(corr, q=t / n)
    assert result.n_signal == k
    assert result.n_noise == n - k


@pytest.mark.parametrize("noise_share", [0.3, 0.5, 0.7])
def test_recovers_the_known_noise_variance(noise_share: float):
    """sigma^2 is FITTED, not assumed to be 1 — the single most
    consequential detail in the method. The population's true noise
    variance is `noise_share` by construction, so this asserts the fit
    lands on a number it was never told.

    The 0.13 tolerance is not a fudge: it is the measured worst case over
    the 75-case grid in the module docstring at this bandwidth (max
    absolute error 0.115), rounded up. Note the assertion also FAILS if
    sigma^2 were hard-coded to 1, which is the point."""
    n, t = 100, 1000
    pop = spiked_population_correlation(n, 3, noise_share, seed=5)
    corr = sample_from_population(pop, t, seed=5).corr()

    result = denoise_correlation_matrix(corr, q=t / n)
    assert result.fit.sigma2 == pytest.approx(noise_share, abs=0.13)
    # ... and would be badly wrong under the sigma^2 = 1 convention:
    assert abs(1.0 - noise_share) > abs(result.fit.sigma2 - noise_share)


def test_denoising_preserves_the_signal_eigenvalues_and_flattens_the_rest():
    """The constant-residual step must leave the k signal eigenvalues
    ALONE and collapse every other eigenvalue onto one shared value.

    NOTE this is the INTERMEDIATE spectrum the algorithm constructs —
    `denoised_eigenvalues` — not the spectrum of the returned matrix. The
    final diagonal rescale moves both (see
    test_the_final_rescale_is_load_bearing_and_changes_the_spectrum)."""
    n, t, k = 100, 1000, 3
    pop = spiked_population_correlation(n, k, 0.5, seed=11)
    corr = sample_from_population(pop, t, seed=11).corr()

    result = denoise_correlation_matrix(corr, q=t / n)
    original = np.array(result.eigenvalues)
    denoised = np.array(result.denoised_eigenvalues)

    np.testing.assert_allclose(denoised[:k], original[:k], rtol=0, atol=0)
    assert len(set(np.round(denoised[k:], 12))) == 1
    assert denoised[k:][0] == pytest.approx(original[k:].mean(), rel=1e-12)


def test_constant_residual_substitution_preserves_the_trace():
    """Lopez de Prado's own comment on snippet 2.5: "Operation invariante
    to trace(Correlation) / The Trace of a square matrix is the _Sum_ of
    its eigenvalues". Replacing a block by its own mean cannot change its
    sum, so trace(denoised spectrum) == trace(original) == N exactly."""
    n, t = 100, 1000
    pop = spiked_population_correlation(n, 3, 0.5, seed=13)
    corr = sample_from_population(pop, t, seed=13).corr()

    result = denoise_correlation_matrix(corr, q=t / n)
    assert sum(result.eigenvalues) == pytest.approx(float(n), rel=1e-10)
    assert sum(result.denoised_eigenvalues) == pytest.approx(float(n), rel=1e-10)


def test_output_is_a_valid_correlation_matrix():
    """Diagonal exactly 1, symmetric, positive semi-definite — the three
    things that make the returned object usable as a correlation matrix
    at all, and therefore safe to hand to HRP."""
    n, t = 100, 1000
    pop = spiked_population_correlation(n, 3, 0.5, seed=17)
    corr = sample_from_population(pop, t, seed=17).corr()

    denoised = denoise_correlation_matrix(corr, q=t / n).correlation.to_numpy()
    np.testing.assert_allclose(np.diag(denoised), 1.0, rtol=0, atol=1e-14)
    assert np.trace(denoised) == pytest.approx(float(n), rel=1e-12)
    np.testing.assert_allclose(denoised, denoised.T, rtol=0, atol=1e-12)
    assert np.linalg.eigvalsh(denoised).min() > -1e-10


def test_the_final_rescale_is_load_bearing_and_changes_the_spectrum():
    """CORRECTING AN OBVIOUS-BUT-WRONG GUESS, which is why this test
    exists at all. The intuitive worry about the algorithm's final
    rescale (Lopez de Prado: "Rescaling the correlation matrix to have 1s
    on the main diagonal"; MathWorks step 6) is that it perturbs the
    trace the eigenvalue substitution worked to preserve. That is FALSE:
    forcing every diagonal entry to 1 forces the trace to exactly N, so
    the trace survives twice over.

    What the rescale really does is (a) genuine work — the reconstructed
    diagonal is nowhere near all-ones beforehand — and (b) move the
    SPECTRUM, so the returned matrix's eigenvalues are NOT the
    substituted ones and the "constant residual eigenvalue" is not
    constant in the output. Both are asserted here so the module
    docstring's claim is a measurement rather than a story."""
    n, t = 100, 1000
    pop = spiked_population_correlation(n, 3, 0.5, seed=17)
    corr = sample_from_population(pop, t, seed=17).corr()

    result = denoise_correlation_matrix(corr, q=t / n)
    substituted = np.array(result.denoised_eigenvalues)

    # (a) the pre-rescale reconstruction is NOT a correlation matrix ...
    _, evec = np.linalg.eigh(corr.to_numpy())
    order = np.linalg.eigvalsh(corr.to_numpy()).argsort()[::-1]
    evec = evec[:, order]
    rebuilt = (evec @ np.diag(substituted)) @ evec.T
    assert np.abs(np.diag(rebuilt) - 1.0).max() > 1e-3
    # ... though its trace already is N, because the substitution
    # preserved the eigenvalue sum.
    assert np.trace(rebuilt) == pytest.approx(float(n), rel=1e-10)

    # (b) the rescale moves the spectrum: the returned matrix's own
    # eigenvalues differ from the substituted ones, and its residual
    # block is no longer a single constant.
    final = np.linalg.eigvalsh(result.correlation.to_numpy())[::-1]
    assert np.abs(final - substituted).max() > 1e-3
    residual_block = final[result.n_signal :]
    assert residual_block.max() - residual_block.min() > 1e-6


def test_denoising_improves_conditioning():
    """The stated purpose of the method (Laloux: Markowitz's scheme "is
    not adequate, since its lowest eigenvalues (corresponding to the
    smallest risk portfolios) are dominated by noise"). Collapsing the
    noise block onto its mean lifts the smallest eigenvalue off the
    floor, so the condition number must fall.

    Bound set from measurement, not aspiration: on this synthetic case
    (N=100, T=500, q=5) it falls 118.6 -> 42.2, a factor of 2.8. The
    effect is far larger where it matters — on the real 490-name S&P 500
    universe at q=2.56 it falls 86,385 -> 384, a factor of 225 (see the
    real-data numbers in the build report). The 2x threshold here is the
    weakest claim the synthetic case supports."""
    n, t = 100, 500
    pop = spiked_population_correlation(n, 3, 0.5, seed=19)
    corr = sample_from_population(pop, t, seed=19).corr()

    denoised = denoise_correlation_matrix(corr, q=t / n).correlation
    before = np.linalg.cond(corr.to_numpy())
    after = np.linalg.cond(denoised.to_numpy())
    assert after < before / 2.0


def test_explicit_sigma2_reproduces_the_plerou_convention():
    """Passing sigma2 explicitly skips the fit entirely: the bounds become
    Plerou et al.'s eq. (7) with sigma^2 = 1. Asserted because that is the
    documented escape hatch from the fitted convention, and because it
    demonstrates the two conventions genuinely differ on real structure."""
    n, t = 100, 1000
    pop = spiked_population_correlation(n, 5, 0.4, seed=23)
    corr = sample_from_population(pop, t, seed=23).corr()

    fixed = denoise_correlation_matrix(corr, q=t / n, sigma2=1.0)
    assert fixed.fit.sigma2 == 1.0
    assert fixed.fit.lambda_plus == pytest.approx(marchenko_pastur_bounds(10.0, 1.0)[1])
    fitted = denoise_correlation_matrix(corr, q=t / n)
    # The fitted band is narrower here, because real structure has eaten
    # part of the variance — exactly Laloux's argument for fitting.
    assert fitted.fit.lambda_plus < fixed.fit.lambda_plus


def test_all_signal_spectrum_returns_the_input_unchanged():
    """Module addition, flagged in the docstring: the reference code would
    divide by zero (an empty slice's sum over a zero count) when every
    eigenvalue is signal. Forced here with an absurdly wide band."""
    corr = pd.DataFrame(
        [[1.0, 0.5], [0.5, 1.0]], index=["A", "B"], columns=["A", "B"]
    )
    result = denoise_correlation_matrix(corr, q=100.0, sigma2=1e-5)
    assert result.n_signal == 2
    assert result.n_noise == 0
    pd.testing.assert_frame_equal(result.correlation, corr)


# ---------------------------------------------------------------------------
# Input guards
# ---------------------------------------------------------------------------


def test_non_correlation_matrix_is_refused():
    cov = pd.DataFrame([[4.0, 1.0], [1.0, 9.0]], index=["A", "B"], columns=["A", "B"])
    with pytest.raises(ValueError, match="diagonal is not all ones"):
        denoise_correlation_matrix(cov, q=5.0)


def test_nan_correlation_is_refused():
    corr = pd.DataFrame(
        [[1.0, np.nan], [np.nan, 1.0]], index=["A", "B"], columns=["A", "B"]
    )
    with pytest.raises(ValueError, match="NaN/inf"):
        denoise_correlation_matrix(corr, q=5.0)


def test_asymmetric_matrix_is_refused():
    corr = pd.DataFrame([[1.0, 0.5], [0.2, 1.0]], index=["A", "B"], columns=["A", "B"])
    with pytest.raises(ValueError, match="not symmetric"):
        denoise_correlation_matrix(corr, q=5.0)


def test_zero_variance_covariance_is_refused():
    cov = pd.DataFrame([[0.0, 0.0], [0.0, 1.0]], index=["A", "B"], columns=["A", "B"])
    with pytest.raises(ValueError, match="non-positive variance"):
        denoise_covariance_matrix(cov, q=5.0)


# ---------------------------------------------------------------------------
# Covariance round trip
# ---------------------------------------------------------------------------


def test_covariance_denoising_leaves_individual_variances_untouched():
    """The deliberate design choice: correlations are denoised, variances
    are not. Diagonal of the denoised covariance == diagonal of the input,
    to machine precision."""
    n, t = 60, 600
    pop = spiked_population_correlation(n, 2, 0.5, seed=29)
    returns = sample_from_population(pop, t, seed=29)
    # Give the assets wildly different scales so a silently-rescaled
    # variance would be obvious.
    returns *= np.linspace(0.5, 5.0, n)
    cov = returns.cov()

    result = denoise_covariance_matrix(cov, q=t / n)
    assert result.covariance is not None
    np.testing.assert_allclose(
        np.diag(result.covariance.to_numpy()), np.diag(cov.to_numpy()), rtol=1e-12
    )
    np.testing.assert_allclose(
        np.diag(result.correlation.to_numpy()), 1.0, rtol=0, atol=1e-12
    )
    # The covariance really is the denoised correlation rescaled.
    std = np.sqrt(np.diag(cov.to_numpy()))
    np.testing.assert_allclose(
        result.covariance.to_numpy(),
        result.correlation.to_numpy() * np.outer(std, std),
        rtol=1e-12,
    )


def test_covariance_denoising_is_scale_equivariant():
    """Denoising a covariance and then annualizing it must equal
    annualizing and then denoising: the correlation matrix, which is all
    the method looks at, is scale-invariant."""
    n, t = 50, 500
    pop = spiked_population_correlation(n, 2, 0.5, seed=31)
    cov = sample_from_population(pop, t, seed=31).cov()

    a = denoise_covariance_matrix(cov, q=t / n).covariance
    b = denoise_covariance_matrix(cov * 252.0, q=t / n).covariance
    assert a is not None and b is not None
    np.testing.assert_allclose(a.to_numpy() * 252.0, b.to_numpy(), rtol=1e-10)


# ---------------------------------------------------------------------------
# 4. HRP wiring: the opt-in flag gates it, and OFF means bit-identical
# ---------------------------------------------------------------------------


def _hrp_weights_the_old_way(cov: pd.DataFrame, corr: pd.DataFrame) -> dict[str, float]:
    """HRP's three stages driven directly from its own primitives —
    hrp_linkage -> quasi_diagonal_order -> recursive_bisection_weights.

    This deliberately does NOT call compute_hrp_weights: it reconstructs
    what compute_hrp_weights did BEFORE the denoise parameter existed, so
    the bit-equality assertions below compare the new entry point against
    an independent path rather than against itself."""
    assets = [str(c) for c in cov.columns]
    cov = cov.copy()
    cov.index = assets
    cov.columns = assets
    link = hrp_linkage(corr)
    order = quasi_diagonal_order(link)
    sorted_assets = [assets[i] for i in order]
    w = recursive_bisection_weights(cov, sorted_assets)
    return {a: float(w[a]) for a in assets}


@pytest.mark.parametrize("seed", [41, 43, 47])
def test_hrp_default_is_bit_identical_to_the_pre_denoising_path(seed: int):
    """The load-bearing wiring assertion. With the flags left alone, every
    returned weight must match the pre-change algorithm's float64 BIT
    PATTERN — not "approximately", not "to 4 decimals". Same standard the
    HRP-into-the-runner regression tests used (commit 739b07e)."""
    n, t = 40, 400
    pop = spiked_population_correlation(n, 3, 0.5, seed=seed)
    returns = sample_from_population(pop, t, seed=seed)
    cov, corr = returns.cov(), returns.corr()

    expected = _hrp_weights_the_old_way(cov, corr)

    for actual in (
        compute_hrp_weights(cov).weights,
        compute_hrp_weights(cov, corr).weights,
        compute_hrp_weights_from_returns(returns).weights,
        compute_hrp_weights_from_returns(returns, denoise=False).weights,
    ):
        assert list(actual.keys()) == list(expected.keys())
        for asset in expected:
            assert actual[asset].hex() == expected[asset].hex(), asset


def test_hrp_default_result_reports_no_denoising():
    """`denoise=None` on the result is how a downstream reader tells a raw
    allocation from a denoised one; a default-path result must say so."""
    returns = sample_from_population(
        spiked_population_correlation(30, 2, 0.5, seed=53), 300, seed=53
    )
    assert compute_hrp_weights_from_returns(returns).denoise is None
    assert compute_hrp_weights(returns.cov()).denoise is None


def test_hrp_opt_in_actually_changes_the_allocation():
    """A flag that gates nothing is worse than no flag. Turning denoising
    ON must visibly move the weights, and must attach the diagnostics."""
    n, t = 40, 400
    returns = sample_from_population(
        spiked_population_correlation(n, 3, 0.5, seed=59), t, seed=59
    )
    off = compute_hrp_weights_from_returns(returns)
    on = compute_hrp_weights_from_returns(returns, denoise=True)

    assert on.denoise is not None
    assert on.denoise.n_signal + on.denoise.n_noise == n
    assert on.denoise.fit.q == pytest.approx(t / n)
    moved = max(abs(on.weights[a] - off.weights[a]) for a in off.weights)
    assert moved > 1e-6
    # Still a valid long-only fully-invested allocation.
    assert sum(on.weights.values()) == pytest.approx(1.0)
    assert min(on.weights.values()) >= 0.0


def test_hrp_denoise_q_matches_the_bool_entry_point():
    """compute_hrp_weights_from_returns(denoise=True) must be exactly
    compute_hrp_weights(cov, denoise_q=T/N) — i.e. the convenience
    wrapper derives q the way it claims to (T/N, not N/T)."""
    n, t = 40, 400
    returns = sample_from_population(
        spiked_population_correlation(n, 3, 0.5, seed=61), t, seed=61
    )
    via_bool = compute_hrp_weights_from_returns(returns, denoise=True).weights
    via_q = compute_hrp_weights(returns.cov(), denoise_q=t / n).weights
    for asset in via_bool:
        assert via_bool[asset].hex() == via_q[asset].hex()


def test_hrp_refuses_explicit_corr_together_with_denoise_q():
    returns = sample_from_population(
        spiked_population_correlation(20, 2, 0.5, seed=67), 200, seed=67
    )
    with pytest.raises(ValueError, match="not both"):
        compute_hrp_weights(returns.cov(), returns.corr(), denoise_q=10.0)


def test_hrp_denoising_uses_the_denoised_covariance_in_both_stages():
    """Stage 1 clusters correlations and Stage 3 divides cluster
    variances; both must see the DENOISED matrix. Verified by driving the
    old path with the denoised inputs and demanding bit-equality with the
    opt-in path — which pins WHICH matrix the option substitutes, not just
    that it substitutes something."""
    n, t = 30, 300
    returns = sample_from_population(
        spiked_population_correlation(n, 2, 0.5, seed=71), t, seed=71
    )
    cov = returns.cov()
    dn = denoise_covariance_matrix(cov, q=t / n)
    assert dn.covariance is not None

    expected = _hrp_weights_the_old_way(dn.covariance, dn.correlation)
    actual = compute_hrp_weights(cov, denoise_q=t / n).weights
    for asset in expected:
        assert actual[asset].hex() == expected[asset].hex(), asset


def test_denoising_leaves_each_assets_own_variance_alone_so_ivp_is_unchanged():
    """A consequence worth pinning: denoising rescales the diagonal back
    to 1, so diag(cov) survives, so the inverse-variance weights HRP uses
    inside every cluster are untouched. Anything that changed them would
    mean the diagonal rescale had been dropped."""
    n, t = 40, 400
    cov = sample_from_population(
        spiked_population_correlation(n, 3, 0.5, seed=73), t, seed=73
    ).cov()
    denoised = denoise_covariance_matrix(cov, q=t / n).covariance
    assert denoised is not None
    np.testing.assert_allclose(
        np.diag(denoised.to_numpy()), np.diag(cov.to_numpy()), rtol=1e-12
    )


def test_single_asset_hrp_ignores_the_flag():
    cov = pd.DataFrame([[0.04]], index=["A"], columns=["A"])
    assert compute_hrp_weights(cov, denoise_q=5.0).weights == {"A": 1.0}


def test_cov_to_corr_agrees_between_the_two_modules():
    """hrp_optimizer.cov_to_corr and rmt_denoising's internal one are
    separate implementations of the same identity (the latter adds Lopez
    de Prado's [-1, 1] clip). They must not drift apart, since the wiring
    passes matrices between them."""
    cov = sample_from_population(
        spiked_population_correlation(25, 2, 0.5, seed=79), 250, seed=79
    ).cov()
    result = denoise_covariance_matrix(cov, q=10.0)
    assert result.covariance is not None
    np.testing.assert_allclose(
        cov_to_corr(result.covariance).to_numpy(),
        result.correlation.to_numpy(),
        rtol=1e-12,
        atol=1e-12,
    )
