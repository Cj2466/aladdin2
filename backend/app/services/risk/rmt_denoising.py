"""Random Matrix Theory (RMT) denoising of correlation matrices.

An empirical correlation matrix estimated from T observations of N assets
is, under the null hypothesis of independent returns, still not the
identity: finite T alone manufactures a whole spectrum of non-trivial
eigenvalues (Laloux et al. [A], footnote dagger: "even if the 'true'
correlation matrix Ctrue is the identity matrix, its empirical
determination from a finite time series will generate non trivial
eigenvectors and eigenvalues"). Random Matrix Theory says exactly WHERE
those pure-noise eigenvalues must lie — inside a sharp interval
[lambda_minus, lambda_plus] — so eigenvalues outside it are the only ones
that can carry real information. This module locates that interval and
rebuilds the correlation matrix with the in-interval (noise) eigenvalues
collapsed onto a single constant.

SHIPPED OPT-IN, NEVER A DEFAULT. Same convention as hrp_optimizer.py and
effective_n_clustering.py: nothing in this codebase denoises anything
unless a caller explicitly asks. The one wiring that exists is
hrp_optimizer's `denoise_q` / `denoise` parameters, which default to
None/False; with them unset every existing code path produces
bit-identical results to before this module existed (asserted in
tests/test_rmt_denoising.py).

PRIMARY SOURCES — implemented from sources actually fetched and read
line-by-line during this implementation session, not from memory:

  [A] Laloux, L., P. Cizeau, J.-P. Bouchaud and M. Potters, "Noise
      Dressing of Financial Correlation Matrices", arXiv:cond-mat/9810255v1
      (20 Oct 1998). The full 3-page preprint PDF was downloaded and read
      verbatim this session; every "[A] eq. (n)" below is that preprint's
      own equation number. THE FIRST APPLICATION of this spectrum to
      financial correlation matrices, and the origin of the
      fit-sigma2-to-the-bulk convention this module implements.
      SOURCING LIMIT: only the arXiv preprint was read. The journal
      version's volume/page are deliberately NOT cited — they do not
      appear in the preprint and citing them would be a memory claim.

  [B] Plerou, V., P. Gopikrishnan, B. Rosenow, L. A. N. Amaral, T. Guhr
      and H. E. Stanley, "A Random Matrix Approach to Cross-Correlations
      in Financial Data", arXiv:cond-mat/0108023v1 (1 Aug 2001). Full
      text downloaded and read this session; "[B] eq. (n)" refers to it.
      The independent contemporaneous derivation, and the source of the
      economic interpretation this module's diagnostics are read against
      (largest eigenvalue = the market; the next few = business sectors).

  [C] Lopez de Prado, M., "Machine Learning for Asset Managers"
      (Cambridge, 2020), Chapter 2, code snippets 2.1-2.6.
      SOURCING LIMIT, stated plainly: the BOOK ITSELF WAS NOT READ. What
      was read this session is the emoen/Machine-Learning-for-Asset-Managers
      GitHub transcription of its snippets
      (Machine_Learning_for_Asset_Managers/ch2_marcenko_pastur_pdf.py),
      whose functions carry the book's own snippet numbers and titles
      ("#snippet 2.1", "# code snippet 2.5 - denoising by constant
      residual eigenvalue"). This is the same source, with the same
      caveat, that effective_n_clustering.py already relies on for MLAM
      Ch. 4. Everything attributed to [C] below is quoted from that file,
      and is independently corroborated by [D] and [E].

  [D] enjine-com/mcos, mcos/covariance_transformer.py (fetched and read
      this session): an INDEPENDENT third-party port which states it is
      "modified from" Section 4.2 of Lopez de Prado, "A Robust Estimator
      of the Efficient Frontier" (SSRN 3469961). Its DeNoiserCovarianceTransformer
      is structurally identical to [C] — same bounds, same density, same
      optimizer bounds (1e-5, 1-1e-5), same searchsorted index, same
      constant-residual substitution, same final rescale.
      SOURCING LIMIT: SSRN's own PDF returned HTTP 403 to this session
      (the identical bot block hrp_optimizer.py documents), so Section 4.2
      itself was NOT read; [D] is used only as corroboration of [C].

  [E] MathWorks documentation for `covarianceDenoising`
      (mathworks.com/help/finance/covariancedenoising.html, fetched this
      session): an independent COMMERCIAL implementation whose doc page
      spells out the same seven-step algorithm and cites only [C]. Used
      here as a third, non-Python confirmation that the steps below are
      the standard convention and not one repo's idiosyncrasy.

  NOT VERIFIED, AND THEREFORE NOT CITED AS READ: Marchenko, V. A. and
  L. A. Pastur (1967). The 1967 original was not fetched. Worth
  recording precisely because it cuts against the module's own name:
  NEITHER [A] NOR [B] CITES MARCHENKO-PASTUR FOR THIS DENSITY. Both
  attribute it to A. M. Sengupta and P. P. Mitra ([A] ref. [5],
  cond-mat/9709283; [B] ref. [24], Phys. Rev. E 60 (1999) 3389).
  "Marchenko-Pastur" is the name [C], [D] and [E] use, and the name this
  module uses for findability — but the attribution chain in the two
  finance papers actually read is Sengupta-Mitra.

  INDEPENDENTLY RE-VERIFIED (second pass, separate session, both PDFs
  re-downloaded from arXiv and re-read rather than taking the above on
  trust): the strings "Marchenko", "Marcenko" and "Pastur" occur ZERO
  times in either preprint. [A] introduces eq. (3) with "is exactly known
  in the limit N -> infinity, T -> infinity and Q = T/N >= 1 fixed [5]",
  where [5] is "A.M. Sengupta and P.P. Mitra, Distribution of Singular
  Values for Some Random Matrices, cond-mat/9709283 preprint". [B]
  introduces eq. (6) with "it was shown analytically [24] that the
  distribution Prm(lambda) ...", where [24] is "A. M. Sengupta and P. P.
  Mitra, Phys. Rev. E 60 (1999) 3389". [B]'s neighbouring ref. [23],
  which might be mistaken for the missing MP citation, is F. J. Dyson,
  Revista Mexicana de Fisica 20, 231 (1971) — also not Marchenko-Pastur.
  So the attribution finding is exact, not a misreading of a partial
  bibliography.

THE SPECTRUM.

  Let Q = T/N >= 1 (T observations, N assets). [A] eq. (3), verbatim from
  the preprint, gives the density of eigenvalues of a correlation matrix
  built from i.i.d. data, in the limit N, T -> infinity at fixed Q:

      rho(lambda) = Q/(2 pi sigma^2) * sqrt((l_max - lambda)(lambda - l_min)) / lambda
      l_max/min   = sigma^2 (1 + 1/Q +/- 2 sqrt(1/Q))

  "with lambda in [l_min, l_max], and where sigma^2 is equal to the
  variance of the elements of M" ([A], immediately after eq. (3)).

  [B] eq. (6)-(7) is the same statement with sigma^2 = 1 and Q written as
  L/N:  P_rm(lambda) = Q/(2 pi) sqrt((l_+ - l)(l - l_-))/l,
        l_+/- = 1 + 1/Q +/- 2 sqrt(1/Q).

  [C] snippet 2.1 (`mpPDF`) writes the bounds in the equivalent
  completed-square form this module uses:

      eMin, eMax = var*(1-(1./q)**.5)**2, var*(1+(1./q)**.5)**2
      pdf = q/(2*np.pi*var*eVal)*((eMax-eVal)*(eVal-eMin))**.5

  sigma^2(1 +/- sqrt(1/Q))^2 == sigma^2(1 + 1/Q +/- 2 sqrt(1/Q)) is an
  algebraic identity; both forms are asserted equal in the tests. The
  density was also checked numerically this session (scipy.integrate.quad,
  Q in {1.5, 2.5, 6.448, 20}, sigma^2 in {1, 0.74}): total mass 1.000000
  and mean exactly sigma^2 in every case, i.e. the constant in [A] eq. (3)
  is a correctly normalized density. That is a self-check, not a citation.

  Reproduction check against [B]'s own printed numbers: [B] reports that
  for N=1000, L=6448 (Q=6.448) eq. (7) gives "lambda_- = 0.36 and
  lambda_+ = 1.94". This module's marchenko_pastur_bounds(6.448, 1.0)
  returns (0.36753, 1.94272) — lambda_+ agrees to the printed precision;
  lambda_- rounds to 0.37 against their printed 0.36, consistent with
  truncation rather than rounding on their side. Asserted in the tests.

SIGMA^2 IS FITTED, NOT ASSUMED TO BE 1. This is the single most
consequential detail and the one informal descriptions gloss over, so it
is documented with quotes:

  [A], p. 2, having found the largest empirical eigenvalue 25x above the
  predicted l_max: "The simplest 'pure noise' hypothesis is therefore
  inconsistent with the value of lambda_1. A more reasonable idea is that
  the components of the correlation matrix which are orthogonal to the
  'market' is pure noise. This amounts to subtracting the contribution of
  lambda_max from the nominal value sigma^2 = 1, leading to
  sigma^2 = 1 - lambda_max/N = 0.85 ... Several eigenvalues are still
  above lambda_max and might contain some information, thereby reducing
  the variance of the effectively random part of the correlation matrix.
  ONE CAN THEREFORE TREAT sigma^2 AS AN ADJUSTABLE PARAMETER. The best fit
  is obtained for sigma^2 = 0.74" (emphasis added).

  [C] snippet 2.4 turns "adjustable parameter" into a concrete numerical
  procedure, which is what this module implements:
      errPDFs(var, eVal, q, bWidth, pts=1000): fit a Gaussian KDE to the
        EMPIRICAL eigenvalues, evaluate it on the theoretical density's
        own grid, and return sum((empirical - theoretical)**2).
      findMaxEval(eVal, q, bWidth): scipy.optimize.minimize over var,
        x0 = 0.5, bounds ((1E-5, 1-1E-5),); on failure fall back to
        var = 1; return eMax = var*(1+(1./q)**.5)**2.
  [D] reproduces this exactly (same x0, same bounds, same fallback).
  [E] states the same step in words: "Fit the Marchenko-Pastur
  distribution to the empirical distribution by minimizing the mean
  squared error (MSE) between the empirical probability density function
  (pdf) and the fitted Marchenko-Pastur pdf. This gives the theoretical
  bounds lambda+ and lambda- on the eigenvalues associated with noise."

  So: sigma^2 = 1 is the PLEROU convention ([B] eq. (7) has no sigma^2 at
  all) and is available here via an explicit sigma2= argument, but the
  DEFAULT is the fitted Laloux/Lopez de Prado convention.

  On the (1e-5, 1-1e-5) upper bound: it is [C]'s and [D]'s literal bound,
  reproduced here rather than reasoned about. OBSERVATION, NOT A CITED
  CLAIM: it is consistent with the fact that a correlation matrix has
  trace N, so its eigenvalues average exactly 1; once any eigenvalue is
  above the bulk, the bulk's own variance must be below 1. A consequence
  worth knowing is that this module CANNOT report sigma^2 >= 1, so on a
  genuinely structureless matrix (where the honest answer is sigma^2 = 1)
  the fit saturates just under 1. MEASURED, not assumed: on i.i.d. data
  with T=2000, N=200 the optimizer reports SUCCESS and returns exactly
  0.99999 — the bound itself — at every bandwidth tried. That is a
  converged fit sitting on its constraint, NOT [C]'s `else: var=1`
  failure fallback, which is why fit_succeeded is surfaced as a separate
  field from the value. The pure-noise test measures this and confirms
  the denoised matrix is still the identity.

  KNOWN SOFT SPOT, flagged rather than hidden: [C]'s errPDFs fits the KDE
  to ALL N eigenvalues, signal ones included, but compares against a
  theoretical density that integrates to 1 over [l_min, l_max] alone. The
  empirical density therefore carries less than unit mass on the
  comparison grid whenever signal exists, which biases the fitted sigma^2
  downward — arguably the mechanism by which the fit "knows" to shrink
  the bulk, and certainly the reason a matrix with a huge market
  eigenvalue gets a small sigma^2. That reading is THIS MODULE'S
  OBSERVATION while implementing, not a claim made by any source; it is
  recorded because it explains the fitted values and because a reader who
  assumed a mass-matched fit would be surprised by them.

  BANDWIDTH IS AN OPEN HYPERPARAMETER, per the book itself. [C]'s fitKDE
  signature defaults to bWidth=.15, but its own worked example calls
  findMaxEval(..., bWidth=.01); [D] defaults to 0.25. MLAM Exercise 2.7
  ("Extend function fitKDE in code snippet 2.2, so that it estimates
  through cross-validation the optimal value of bWidth") — quoted from
  the emoen repo's ch2_fitKDE_find_best_bandwidth.py, read this session —
  confirms the book does not fix it.

  This module defaults to 0.15, [C]'s own declared default for fitKDE,
  chosen over [C]'s worked-example 0.01 on MEASURED evidence rather than
  preference. 75 spiked-population ground-truth cases (N in
  {50,100,200,300}, T/N in {5,10}, k in {1,2,3,5,8}, true noise variance
  in {0.3,0.5,0.7}; the construction is in tests/test_rmt_denoising.py),
  scoring recovery of the known k and of the known sigma^2:

      bWidth   exact k    n_signal error     sigma^2 mean abs err
      0.01     62/75      -1 .. +1           0.045  (max 0.700)
      0.05     75/75       0 ..  0           0.024  (max 0.700)
      0.10     75/75       0 ..  0           0.038  (max 0.060)
      0.15     75/75       0 ..  0           0.072  (max 0.115)
      0.25     75/75       0 ..  0           0.261  (max 0.700)
      0.50     73/75      -1 ..  0           0.499  (max 0.700)

  0.05-0.15 all recover k exactly on every case; 0.01 both over- and
  under-counts, and 0.25/0.50 recover k here only because this design's
  spikes are far above the band — their sigma^2 is barely fitted at all
  (it saturates at the upper bound, i.e. they silently degrade to the
  [B] sigma^2 = 1 convention). 0.15 is the value inside the robust range
  that a source actually states, so it is the default; the parameter is
  exposed on every entry point for callers who want [C]'s 0.01 or a
  cross-validated value. Direction of the residual error at 0.15 is
  worth knowing: sigma^2 is biased slightly HIGH (+0.072 mean), which
  widens the noise band and makes the method slightly CONSERVATIVE about
  declaring signal.

THE DENOISING STEP — "constant residual eigenvalue" ([C] snippet 2.5's
own title):

    eVal_[nFacts:] = eVal_[nFacts:].sum()/float(eVal_.shape[0] - nFacts)
    corr1 = np.dot(eVec, np.diag(eVal_)).dot(eVec.T)
    corr1 = cov2corr(corr1)

  with the signal count taken, verbatim from [C]'s worked example, as
      nFacts = eVal.shape[0] - np.diag(eVal)[::-1].searchsorted(eMax)
  i.e. the number of eigenvalues >= lambda_plus. Every eigenvalue BELOW
  lambda_plus is replaced by their common average — note that this
  includes eigenvalues below lambda_MINUS, which [A] and [B] both discuss
  as a separate deviation (the smallest eigenvalues are where [A] warns
  the noise is worst). [C]'s procedure does not treat them separately and
  neither does this module; lambda_minus is computed and REPORTED as a
  diagnostic but is not itself a threshold. Flagged because a reader who
  expects "clip only inside [l_-, l_+]" will otherwise misread the code.

  Why replace rather than delete: [C]'s comment on snippet 2.5 —
  "Operation invariante to trace(Correlation) / The Trace of a square
  matrix is the _Sum_ of its eigenvalues" — replacing a block of
  eigenvalues by their own mean leaves their sum, and so the trace,
  unchanged, which is what keeps the result a correlation matrix.
  WHAT THE FINAL RESCALE ACTUALLY DOES — this module's own measurement,
  and worth stating because the obvious guess is wrong in BOTH
  directions. The rescale is part of the algorithm in all three of [C]
  (`corr1 = cov2corr(corr1)  # Rescaling the correlation matrix to have
  1s on the main diagonal`), [D], and [E] (step 6: "rescale C^ so that
  the main diagonal only has ones"), so it is kept regardless; the
  question is only what it costs.

    - It does NOT cost trace. The first guess — that rescaling perturbs
      the carefully preserved trace — is FALSE, and measurably so:
      forcing every diagonal entry to exactly 1 forces the trace to
      exactly N by definition. Measured at 2.2e-16 on the diagonal and
      an exact N trace on all five synthetic cases and the real
      490-name universe. So the trace is preserved twice over, once by
      the substitution and again by the rescale.
    - The rescale IS doing real work, because the reconstructed matrix's
      diagonal is far from all-ones before it: measured range
      0.9665-1.0396 on a clean synthetic case, and 0.5661-1.2565 on the
      real S&P 500 universe. Without it the output would not be a
      correlation matrix at all.
    - What it DOES change is the SPECTRUM. After the rescale the
      "constant residual eigenvalue" is no longer constant, and the
      preserved signal eigenvalues are no longer exactly preserved:
      measured on the real universe, lambda_1 moves 138.919 -> 136.755
      and the residual block, exactly 0.4121 before the rescale, SPREADS
      OUT afterwards; on synthetic cases the largest shift is ~0.09. So
      "constant residual eigenvalue" names an INTERMEDIATE state, not the
      returned matrix.
      PRECISION FIX from the independent verification pass: an earlier
      draft of this paragraph quoted that spread as a single number,
      "0.4121 -> 0.3284". That is only its LOWER END. Re-measured on a
      one-day-longer window (T = 1255), the post-rescale residual block
      spans 0.3283 to 0.7133 around the 0.4121 it replaced — so the
      rescale does not shift the residual level down by 20%, it smears a
      flat level across a range roughly twice as wide as the shift.
      Quoting one endpoint as "the residual level" understated it.
      RMTDenoiseResult.denoised_eigenvalues reports that intermediate
      spectrum — the one the algorithm constructs — and the returned
      matrix's own spectrum differs from it. Both facts are asserted in
      the tests.

MEASURED ON THIS PROJECT'S REAL DATA — reported as found, not curated.
Universe: research_lab/ticker_universe.SCREENING_UNIVERSE (the 503-name
S&P 500 snapshot), 5 years of daily returns pulled through this
codebase's own path (YFinanceProvider.get_price_history ->
risk/returns.compute_daily_returns -> risk/correlation.correlation_matrix,
i.e. exactly what risk/engine.py runs). 490 of 503 names had complete
overlapping history; T = 1254, N = 490, q = 2.559, window 2021-08-31 to
2026-08-28. Spectrum (trace = 490): 138.92, 34.37, 17.54, 13.62, 10.65,
8.67, 7.97, 5.50, 5.45, 4.42, ...

  bWidth  sigma^2  lambda_+  n_signal        signal share of trace
  0.01    0.99999*  2.641     18  ( 3.7%)     55.6%
  0.05    0.471     1.245     52  (10.6%)     67.3%
  0.10    0.551     1.456     40  ( 8.2%)     64.0%
  0.15    0.634     1.675     32  ( 6.5%)     61.5%   <- shipped default
  0.25    0.806     2.129     23  ( 4.7%)     58.0%
  (*) saturated at the upper bound, i.e. degenerated to sigma^2 = 1.
  Fixing sigma^2 = 1 ([B]'s convention) gives lambda_+ = 2.641, 18 signal.
  Fixing sigma^2 = 1 - lambda_1/N = 0.716 ([A]'s "subtract the market"
  starting point) gives lambda_+ = 1.892, 26 signal.

IS THAT ECONOMICALLY SENSIBLE? The honest answer is yes on identity, only
partly on count.

  The IDENTITIES check out, using the two papers' own tests. [A], p. 2, on
  the largest eigenvalue: "The corresponding eigenvector is, as expected,
  the 'market' itself, i.e. it has roughly equal components on all the N
  stocks." Measured here: eigenvector 1 (lambda = 138.9, 28.4% of the
  whole trace) has ALL 490 components of the same sign, mean loading
  0.0438 against the 1/sqrt(490) = 0.0452 of a perfectly equal-weighted
  market vector, sd 0.0111. It is the market. [B]'s abstract on the rest:
  "these 'deviating eigenvectors' ... shows distinct groups, whose
  identities correspond to conventionally-identified business sectors."
  Measured here against the universe file's own GICS sector labels, as a
  sector's share of squared loading relative to its share of the
  universe: ev2 Utilities x4.2, ev3 Energy x6.5, ev6 Energy x5.0 +
  Financials, ev7 Real Estate x2.7, ev9 Health Care x3.6, ev11 Real
  Estate x6.3, ev12 Consumer Staples x3.2. Sectors, exactly as [B] says.

  The COUNT is defensible but not "a handful". 32 of 490 is 6.5%, which
  sits right on [A]'s own finding for the 1990s S&P 500 ("less than 6% of
  the eigenvectors ... appear to carry some information", N = 406,
  Q = 3.22) and is the same order as [B]'s "a few (~20)" of N = 1000. But
  it is bandwidth-dependent across the whole plausible range (18 to 52),
  so the count should be quoted with its bandwidth or not at all.

  AND THE BOUNDARY IS NOT ECONOMICALLY SHARP, which no source discusses
  and which this module therefore states as its own measurement: the
  sector-concentration test does NOT stop at lambda_plus. ev32 (the last
  "signal" eigenvector) shows Materials at x2.6; ev33, ev41, ev61 and
  ev101 — all classified noise — show top-sector lifts of x2.4, x1.8,
  x2.2 and x2.3. Whatever lambda_plus separates, it is not "has a
  recognizable sector identity" versus "does not".

  Two further honest numbers. (i) The fitted sigma^2 = 0.634 is NOT the
  mean of the eigenvalues it classifies as noise, which is 0.412. On the
  synthetic ground truth those two agree; on real data they do not, which
  says the real bulk is not well described by a single MP density —
  consistent with [A]'s own remark that "a better fit could be obtained
  by allowing for a slightly smaller effective value of Q". (ii) 74 of
  the 490 eigenvalues fall BELOW lambda_minus (smallest: 0.0016), and
  [C]'s procedure lumps them in with the bulk and replaces them by the
  same 0.412. Those are the near-redundant pairs, and they are precisely
  what [A] warns about — "it is precisely the eigenvectors corresponding
  to these smallest eigenvalues which determine, in Markowitz theory, the
  least risky portfolios". Denoising as specified DESTROYS that
  structure. Flagged, not fixed: no source specifies a different
  treatment, and inventing one is what this project's methodology
  forbids.

  Effect on HRP over the same 490 names (the wired option, default off):
  max single-weight change 0.0053, mean 0.00046, total absolute turnover
  0.223, effective positions (1/HHI) 332.3 -> 337.0, largest holding
  0.0110 (CME) -> 0.0085 (KO). Real but small. NO CLAIM IS MADE THAT THIS
  IS AN IMPROVEMENT — that would need an out-of-sample measurement of the
  kind commit 739b07e ran for HRP itself, which has NOT been done here.

  HOW STABLE ARE THOSE SIX NUMBERS? Independently re-run one day later
  (T = 1255 rather than 1254, everything else identical), the MAGNITUDES
  reproduce and the IDENTITY does not: max change 0.0041, mean 0.00043,
  turnover 0.2123, 1/HHI 329.9 -> 340.0, largest holding 0.0114 (CME) ->
  0.0086 (RSG, not KO). Recorded because it is the honest scope of the
  line above: HRP's tree is built from a hierarchical clustering, which
  is discontinuous in its input, so WHICH name ends up largest after
  denoising is not stable to a single extra day of data even though the
  size of the effect is. Read the six numbers as "small, and this is
  roughly how small", never as a per-ticker prediction.

DEVIATIONS FROM [C], EACH DELIBERATE AND EACH FLAGGED:
  - Eigendecomposition uses np.linalg.eigh, not [C]'s np.linalg.eig.
    A correlation matrix is real symmetric; eigh is the routine for that
    case and guarantees real eigenvalues and an orthonormal eigenbasis,
    where eig can return complex dtypes and non-orthogonal vectors on
    degenerate spectra. [D] independently made the same substitution.
    The tests assert the two agree to floating-point tolerance on
    well-conditioned inputs.
  - Guards [C] does not specify (non-square / mismatched labels / NaN /
    non-symmetric input, q <= 1, an all-signal spectrum) raise ValueError
    rather than silently producing NaN. Same posture as
    hrp_optimizer._validate_cov: [C] assumes a clean matrix and specifies
    no input handling, so degenerate input is REFUSED, never patched.
    Each is marked inline as a module addition.

PURE FUNCTIONS. Nothing here reads a database or mutates an input.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.neighbors import KernelDensity

# [C] snippet 2.4's own default number of grid points for the theoretical
# density (errPDFs(..., pts=1000)); [D] uses the same value.
DEFAULT_PDF_POINTS = 1000

# [C] snippet 2.2's own declared default (`def fitKDE(obs, bWidth=.15,
# ...)`), kept because it is BOTH a value a source states AND, per the
# 75-case ground-truth table in the module docstring, inside the range
# that recovers the true factor count exactly. NOT a canonical constant:
# the book leaves bandwidth to the reader (Exercise 2.7) and its own
# worked example passes .01. See "BANDWIDTH IS AN OPEN HYPERPARAMETER".
DEFAULT_KDE_BANDWIDTH = 0.15

# [C] snippet 2.4 / [D]: scipy.optimize.minimize bounds and starting point
# for the sigma^2 search, reproduced literally.
_SIGMA2_BOUNDS = (1e-5, 1 - 1e-5)
_SIGMA2_X0 = 0.5


@dataclass
class MarchenkoPasturFit:
    """Result of fitting the Marchenko-Pastur density to an empirical
    eigenvalue spectrum ([C] snippet 2.4 `findMaxEval`, which returns
    (eMax, var); the extra fields are diagnostics, not algorithm)."""

    sigma2: float
    lambda_minus: float
    lambda_plus: float
    q: float
    bandwidth: float
    sse: float
    # False when scipy's minimize did not converge, in which case sigma2
    # is [C]'s literal fallback of 1 (`if out['success']: var=out['x'][0]
    # else: var=1`) rather than the last iterate. Surfaced so a caller can
    # tell a fitted sigma^2 from a fallen-back one — [C] cannot.
    fit_succeeded: bool


@dataclass
class RMTDenoiseResult:
    """Output of one denoising pass.

    Shaped as a dataclass rather than a bare DataFrame for the same reason
    HRPResult is: the matrix alone destroys the diagnostics that say WHY
    it looks the way it does, and the signal/noise split is the entire
    point of the method.

    `correlation` is ALWAYS the denoised correlation matrix, carrying the
    caller's original index/columns. `covariance` is None from
    denoise_correlation_matrix (which was never given the variances) and
    is the denoised covariance from denoise_covariance_matrix — kept as a
    separate field rather than overloading `correlation`, so no caller can
    ever mistake one matrix for the other."""

    correlation: pd.DataFrame
    n_signal: int
    n_noise: int
    eigenvalues: list[float]  # original spectrum, descending
    denoised_eigenvalues: list[float]  # after the constant-residual step
    fit: MarchenkoPasturFit
    covariance: pd.DataFrame | None = None


def marchenko_pastur_bounds(q: float, sigma2: float = 1.0) -> tuple[float, float]:
    """(lambda_minus, lambda_plus) = sigma^2 (1 -/+ sqrt(1/q))^2.

    [C] snippet 2.1, first line, verbatim:
        eMin, eMax = var*(1-(1./q)**.5)**2, var*(1+(1./q)**.5)**2
    identical by algebra to [A] eq. (3)'s sigma^2(1 + 1/Q -/+ 2 sqrt(1/Q))
    and, at sigma2=1, to [B] eq. (7).

    q is T/N — sample length over number of variables ([C] snippet 2.1's
    own comment, "#q=T/N"; [A] "Q = T/N >= 1"; [B] "Q == L/N"). Note the
    OPPOSITE convention (q = N/T) is also in circulation, so callers
    should pass q > 1 for a well-determined matrix.

    MODULE GUARD, not a step in any source: q <= 1 is refused. At q = 1
    the density diverges as 1/sqrt(lambda) ([A], p. 2: "except in the
    limit Q = 1 (lambda_min = 0) where it diverges as ~ 1/sqrt(lambda)"),
    and below 1 the cited form does not apply at all; either way the SSE
    fit downstream would be operating on infinities."""
    if not np.isfinite(q) or q <= 1.0:
        raise ValueError(
            f"q must be > 1 (q = T/N, sample length over number of assets); got {q}. "
            "At q = 1 the Marchenko-Pastur density diverges at lambda_minus = 0, and "
            "below 1 the cited form does not apply."
        )
    if not np.isfinite(sigma2) or sigma2 <= 0.0:
        raise ValueError(f"sigma2 must be finite and positive; got {sigma2}")
    root = (1.0 / q) ** 0.5
    return float(sigma2 * (1.0 - root) ** 2), float(sigma2 * (1.0 + root) ** 2)


def marchenko_pastur_pdf(
    q: float, sigma2: float = 1.0, pts: int = DEFAULT_PDF_POINTS
) -> pd.Series:
    """The theoretical density, indexed by lambda on a `pts`-point linear
    grid spanning [lambda_minus, lambda_plus].

    [C] snippet 2.1 (`mpPDF`), verbatim:
        pdf = q/(2*np.pi*var*eVal)*((eMax-eVal)*(eVal-eMin))**.5
    which is [A] eq. (3), rho(l) = Q/(2 pi sigma^2) sqrt((l_max-l)(l-l_min))/l.

    Returns a pd.Series exactly as [C] does — the index IS the grid the
    empirical KDE is evaluated on in the fit below, so keeping them
    together is load-bearing, not cosmetic."""
    lambda_minus, lambda_plus = marchenko_pastur_bounds(q, sigma2)
    grid = np.linspace(lambda_minus, lambda_plus, pts)
    density = (
        q
        / (2 * np.pi * sigma2 * grid)
        * ((lambda_plus - grid) * (grid - lambda_minus)) ** 0.5
    )
    return pd.Series(density, index=grid)


def fit_kde(
    obs: np.ndarray,
    bandwidth: float = DEFAULT_KDE_BANDWIDTH,
    kernel: str = "gaussian",
    x: np.ndarray | None = None,
) -> pd.Series:
    """Gaussian kernel density estimate of `obs`, evaluated at `x`.

    [C] snippet 2.2 (`fitKDE`), ported with no behavioural change: same
    sklearn KernelDensity, same reshape handling, same
    exp(score_samples) -> pd.Series indexed by x. [D] is an independent
    port of the same function."""
    obs = np.asarray(obs, dtype=float)
    if obs.ndim == 1:
        obs = obs.reshape(-1, 1)
    kde = KernelDensity(kernel=kernel, bandwidth=bandwidth).fit(obs)
    grid = np.unique(obs) if x is None else np.asarray(x, dtype=float)
    grid = grid.reshape(-1, 1) if grid.ndim == 1 else grid
    log_prob = kde.score_samples(grid)
    return pd.Series(np.exp(log_prob), index=grid.flatten())


def marchenko_pastur_sse(
    sigma2: float,
    eigenvalues: np.ndarray,
    q: float,
    bandwidth: float = DEFAULT_KDE_BANDWIDTH,
    pts: int = DEFAULT_PDF_POINTS,
) -> float:
    """Sum of squared differences between the theoretical MP density at
    this sigma^2 and a KDE of the empirical eigenvalues, on the
    theoretical density's own grid.

    [C] snippet 2.4 (`errPDFs`), verbatim apart from the debug print:
        pdf0 = mpPDF(var, q, pts); pdf1 = fitKDE(eVal, bWidth, x=pdf0.index.values)
        sse = np.sum((pdf1-pdf0)**2)

    NOTE, per the module docstring's "KNOWN SOFT SPOT": `eigenvalues` here
    is [C]'s FULL spectrum, signal eigenvalues included — not the bulk
    only. That is deliberate reproduction of the reference, not an
    oversight."""
    theoretical = marchenko_pastur_pdf(q, sigma2, pts)
    empirical = fit_kde(eigenvalues, bandwidth, x=theoretical.index.values)
    return float(np.sum((empirical - theoretical) ** 2))


def fit_marchenko_pastur(
    eigenvalues: np.ndarray, q: float, bandwidth: float = DEFAULT_KDE_BANDWIDTH
) -> MarchenkoPasturFit:
    """Fit sigma^2 to the empirical eigenvalue distribution and return the
    implied noise band.

    [C] snippet 2.4 (`findMaxEval`), ported with its exact optimizer
    configuration — x0 = 0.5, bounds ((1e-5, 1-1e-5),), and the literal
    `if out['success']: var = out['x'][0] else: var = 1` fallback. [D]
    reproduces the same three choices independently.

    This is the "adjustable parameter" of [A] made numerical: sigma^2 is
    NOT assumed to be 1. See the module docstring for the quotes."""
    eigenvalues = np.asarray(eigenvalues, dtype=float)
    if eigenvalues.ndim != 1:
        raise ValueError(f"eigenvalues must be 1-D; got shape {eigenvalues.shape}")
    if not np.isfinite(eigenvalues).all():
        raise ValueError("eigenvalues contain NaN/inf")

    out = minimize(
        lambda x: marchenko_pastur_sse(float(x[0]), eigenvalues, q, bandwidth),
        x0=np.array([_SIGMA2_X0]),
        bounds=(_SIGMA2_BOUNDS,),
    )
    succeeded = bool(out["success"])
    sigma2 = float(out["x"][0]) if succeeded else 1.0  # [C]'s literal fallback
    lambda_minus, lambda_plus = marchenko_pastur_bounds(q, sigma2)
    return MarchenkoPasturFit(
        sigma2=sigma2,
        lambda_minus=lambda_minus,
        lambda_plus=lambda_plus,
        q=q,
        bandwidth=bandwidth,
        sse=marchenko_pastur_sse(sigma2, eigenvalues, q, bandwidth),
        fit_succeeded=succeeded,
    )


def _eigendecompose(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Eigenvalues (1-D, DESCENDING) and matching eigenvectors (columns).

    [C] snippet 2.2 (`getPCA`) sorts descending the same way; it uses
    np.linalg.eig and returns eVal as a diagonal matrix. This uses eigh
    (see the module docstring's DEVIATIONS section) and returns the
    eigenvalues flat, because every use site here immediately does
    np.diag(eVal) to undo [C]'s diagonalization."""
    eigenvalues, eigenvectors = np.linalg.eigh(matrix)
    order = eigenvalues.argsort()[::-1]
    return eigenvalues[order], eigenvectors[:, order]


def _cov_to_corr(cov: np.ndarray) -> np.ndarray:
    """[C] snippet 2.3 (`cov2corr`), verbatim including the clip:
        corr = cov/np.outer(std,std); corr[corr<-1], corr[corr>1] = -1,1
    Used here for its second job in [C] — rescaling a reconstructed matrix
    so the main diagonal is exactly 1."""
    std = np.sqrt(np.diag(cov))
    corr = cov / np.outer(std, std)
    corr[corr < -1], corr[corr > 1] = -1.0, 1.0  # "for numerical errors"
    return corr


def _corr_to_cov(corr: np.ndarray, std: np.ndarray) -> np.ndarray:
    """[C] snippet 2.3 (`corr2cov`), verbatim: cov = corr * np.outer(std, std)."""
    return corr * np.outer(std, std)


def count_signal_eigenvalues(eigenvalues_desc: np.ndarray, lambda_plus: float) -> int:
    """How many eigenvalues are at or above lambda_plus.

    [C]'s worked example, verbatim:
        nFacts = eVal.shape[0] - np.diag(eVal)[::-1].searchsorted(eMax)
    `[::-1]` turns the descending spectrum ascending, and searchsorted's
    default side='left' returns the count of entries strictly below eMax,
    so n - that is the count >= eMax. [D] uses the identical expression."""
    ascending = np.asarray(eigenvalues_desc, dtype=float)[::-1]
    return int(len(ascending) - ascending.searchsorted(lambda_plus))


def _validate_corr(corr: pd.DataFrame) -> None:
    """MODULE ADDITIONS, not steps in any source — [C] assumes a clean
    matrix and specifies no input handling, so degenerate input is
    REFUSED rather than silently turned into NaN. Deliberately mirrors
    hrp_optimizer._validate_cov's posture and messages."""
    if corr.shape[0] != corr.shape[1]:
        raise ValueError(f"correlation matrix must be square, got {corr.shape}")
    if list(corr.index) != list(corr.columns):
        raise ValueError("correlation matrix index and columns must match")
    values = corr.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(
            "correlation matrix contains NaN/inf — refused rather than silently filled "
            "(no source for this algorithm specifies a fill convention)"
        )
    if not np.allclose(values, values.T, rtol=0.0, atol=1e-8):
        raise ValueError("correlation matrix is not symmetric")
    if not np.allclose(np.diag(values), 1.0, rtol=0.0, atol=1e-8):
        raise ValueError(
            "matrix diagonal is not all ones — this function takes a CORRELATION "
            "matrix; use denoise_covariance_matrix for a covariance matrix"
        )


def denoise_correlation_matrix(
    corr: pd.DataFrame,
    q: float,
    bandwidth: float = DEFAULT_KDE_BANDWIDTH,
    sigma2: float | None = None,
) -> RMTDenoiseResult:
    """RMT-denoise a correlation matrix by the constant-residual-eigenvalue
    method ([C] snippet 2.5; [E] steps 1-6).

    q = T/N, the sample length used to estimate `corr` over the number of
    assets. The caller supplies it because a correlation matrix carries no
    record of how many observations produced it — passing the wrong q
    silently moves the noise band, so it is required, never guessed.

    sigma2 defaults to None = FIT IT to the empirical spectrum, the
    [A]/[C] convention. Pass an explicit float to fix it — sigma2=1.0
    reproduces the [B] (Plerou et al.) convention, in which the bounds are
    the pure-null bounds and no fitting happens at all.

    Returns an RMTDenoiseResult; `.correlation` is the denoised matrix
    with the caller's original labels."""
    _validate_corr(corr)
    values = corr.to_numpy(dtype=float)
    n = values.shape[0]

    eigenvalues, eigenvectors = _eigendecompose(values)

    if sigma2 is None:
        fit = fit_marchenko_pastur(eigenvalues, q, bandwidth)
    else:
        lambda_minus, lambda_plus = marchenko_pastur_bounds(q, sigma2)
        fit = MarchenkoPasturFit(
            sigma2=float(sigma2),
            lambda_minus=lambda_minus,
            lambda_plus=lambda_plus,
            q=q,
            bandwidth=bandwidth,
            sse=marchenko_pastur_sse(sigma2, eigenvalues, q, bandwidth),
            fit_succeeded=True,  # nothing was fitted; the caller fixed it
        )

    n_signal = count_signal_eigenvalues(eigenvalues, fit.lambda_plus)

    if n_signal >= n:
        # MODULE ADDITION, flagged: [C] would evaluate an empty slice's
        # sum()/0.0 here and return a matrix full of NaN. Every eigenvalue
        # is signal, so denoising has nothing to do; return the input
        # untouched (copied, keeping this function pure).
        denoised_values = values.copy()
        denoised_eigenvalues = eigenvalues.copy()
    else:
        denoised_eigenvalues = eigenvalues.copy()
        # [C] snippet 2.5, verbatim: the noise block becomes its own mean,
        # which leaves its sum -- and so the trace -- unchanged.
        denoised_eigenvalues[n_signal:] = denoised_eigenvalues[n_signal:].sum() / float(
            n - n_signal
        )
        rebuilt = (eigenvectors @ np.diag(denoised_eigenvalues)) @ eigenvectors.T
        # [C]: "Rescaling the correlation matrix to have 1s on the main
        # diagonal"; [E] step 6. See the module docstring's MEASURED
        # CAVEAT on what this does to the trace.
        denoised_values = _cov_to_corr(rebuilt)

    return RMTDenoiseResult(
        correlation=pd.DataFrame(denoised_values, index=corr.index, columns=corr.columns),
        n_signal=n_signal,
        n_noise=n - n_signal,
        eigenvalues=[float(v) for v in eigenvalues],
        denoised_eigenvalues=[float(v) for v in denoised_eigenvalues],
        fit=fit,
    )


def denoise_covariance_matrix(
    cov: pd.DataFrame,
    q: float,
    bandwidth: float = DEFAULT_KDE_BANDWIDTH,
    sigma2: float | None = None,
) -> RMTDenoiseResult:
    """Covariance counterpart: correlation-denoise, then put the ORIGINAL
    standard deviations back ([E] steps 1 and 7; [D]'s transform(), which
    does exactly `corr_to_cov(denoised_corr, np.diag(cov)**.5)`).

    The individual variances are deliberately NOT touched — a single
    asset's variance is estimated from T observations of one series and is
    comparatively well determined, whereas the N(N-1)/2 correlations are
    the part [A] shows to be noise-dominated.

    The result's `.covariance` is the denoised covariance matrix and
    `.correlation` the denoised correlation matrix it was built from; both
    are populated here."""
    if cov.shape[0] != cov.shape[1] or list(cov.index) != list(cov.columns):
        raise ValueError("covariance matrix must be square with matching index/columns")
    values = cov.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("covariance matrix contains NaN/inf")
    std = np.sqrt(np.diag(values))
    if (std <= 0).any():
        raise ValueError(
            "non-positive variance on the covariance diagonal — the correlation matrix "
            "is undefined (no source addresses zero-variance assets)"
        )
    corr = pd.DataFrame(_cov_to_corr(values), index=cov.index, columns=cov.columns)
    result = denoise_correlation_matrix(corr, q, bandwidth=bandwidth, sigma2=sigma2)
    denoised_cov = _corr_to_cov(result.correlation.to_numpy(dtype=float), std)
    result.covariance = pd.DataFrame(denoised_cov, index=cov.index, columns=cov.columns)
    return result
