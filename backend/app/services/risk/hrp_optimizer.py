"""Hierarchical Risk Parity (HRP) portfolio construction.

Parallel ALTERNATIVE to optimizer.py's mean-variance max-Sharpe optimizer —
available infrastructure, deliberately NOT wired into any live/default code
path. Nothing imports this module from a router or pipeline; the existing
optimizer's default behaviour is untouched.

PRIMARY SOURCE — implemented from the actual sources, not from memory:

  Lopez de Prado, M. (2016): "Building Diversified Portfolios that
  Outperform Out-of-Sample." Journal of Portfolio Management 42(4), 59-69.
  Working paper: SSRN 2708678. The same algorithm reappears in Lopez de
  Prado, "Advances in Financial Machine Learning" (Wiley, 2018), Chapter 16
  ("Machine Learning Asset Allocation"), and in "Machine Learning for Asset
  Managers" (Cambridge, 2020).

  HONEST SOURCING NOTE: SSRN's full-text PDF was bot-blocked (HTTP 403)
  during this implementation session, so the JPM print edition's own
  equation/exhibit numbers could not be read directly and are deliberately
  NOT cited below — citing them from memory is exactly what this project's
  methodology forbids. The algorithm was instead implemented from, and every
  step below is cited against, four mutually-consistent sources that WERE
  pulled and read line-by-line this session:

  [A] The author's own reference implementation, posted by him at
      https://quantresearch.org/HRP.py.txt (header "On 20151227 by MLdP
      <lopezdeprado@lbl.gov>") — functions correlDist, getQuasiDiag,
      getRecBipart, getClusterVar, getIVP, generateData, main. This is the
      code printed in the paper's appendix and again as AFML Ch. 16's
      snippets. Where this module says "the author's code", it means this
      file.
  [B] The author's own presentation slides for this exact paper (SSRN
      2713516), read via the SlideShare transcript: the formula set
      (correlation-distance, Euclidean distance between columns of D,
      argmin cluster formation, min-linkage update, inverse-variance
      weights diag(V)^-1/tr(diag(V)^-1), cluster variance w'Vw, split
      factor alpha = 1 - V1/(V1+V2)) and the Monte Carlo design/results
      (10 series x 520 obs, 260-obs estimation window, rebalance every 22
      obs, 10,000 paths; out-of-sample variance HRP 0.0671 vs CLA 0.1157
      (+72.47%) vs IVP 0.0928 (+38.24%)).
  [C] AFML (2018) Ch. 16, pp. 224-226, quoted verbatim on the
      quasi-diagonalization step via Bechis (2020, LUISS thesis, Section
      2.3): "We know that each row of the linkage matrix merges two
      branches into one. We replace clusters in (y_{N-1,1}, y_{N-1,2}) with
      their constituents recursively until no clusters remain. These
      replacements preserve the order of the clustering. The output is a
      sorted list of original nodes."
  [D] Two independently-written full derivations cross-confirming the same
      formula set: Bechis (2020), "Machine Learning Portfolio Optimization:
      Hierarchical Risk Parity and Modern Portfolio Theory", LUISS thesis,
      Section 2.3, its eqs. (53)-(60); and Wikipedia, "Hierarchical Risk
      Parity" (fetched this session).

THE ALGORITHM — three stages (paper's own stage names, per [B]/[D]):

  Stage 1, TREE CLUSTERING:
    (1a) Correlation-distance ([A] correlDist; [B]; [D] eq. 53):
             d_ij = sqrt( (1 - rho_ij) / 2 )
         a proper distance metric; rho=+1 -> 0, rho=0 -> sqrt(1/2),
         rho=-1 -> 1.
    (1b) "Distance of distances" ([B]; [D] eq. 54): the Euclidean distance
         between columns i and j of the matrix D from (1a),
             dtilde_ij = sqrt( sum_k (d_ki - d_kj)^2 ),
         so two assets are close when they are similarly correlated with
         EVERYTHING, not merely with each other.
    (1c) Single-linkage agglomerative clustering on dtilde ([B]; [D]
         eqs. 55-56): repeatedly merge the pair at minimum dtilde, with
         cluster-to-item distance min over members (single linkage).
         IMPLEMENTATION NOTE, verified against [A]: the author's code calls
         sch.linkage(dist, 'single') passing the FULL SQUARE matrix D.
         scipy interprets a square 2-D input as raw observation vectors and
         clusters on the Euclidean distances BETWEEN ITS ROWS — which is
         exactly dtilde. Text and code agree once that is observed (the
         same reading as effective_n_clustering.py's note on the ONC
         paper's Snippet 1, which uses the identical construction). This
         module computes dtilde EXPLICITLY (pdist of D's rows) and passes
         the condensed form — numerically identical to [A], but no longer
         dependent on scipy's ambiguous square-input interpretation, which
         modern scipy flags with a ClusterWarning.
         KNOWN VARIANT, for cross-check readers: PyPortfolioOpt 1.6.0's
         HRPOpt.optimize() clusters on the condensed d itself (step 1a,
         skipping 1b) — a deviation from both the paper's text and the
         author's code. tests/test_hrp_optimizer.py quantifies the effect.

  Stage 2, QUASI-DIAGONALIZATION ([A] getQuasiDiag; [C]): walk the linkage
    matrix top-down, recursively replacing each cluster id with its two
    constituents while preserving order, yielding a permutation of the
    assets under which correlated assets sit adjacent (the covariance
    matrix becomes quasi-diagonal). Ported line-for-line from [A]
    (Python-3/pandas-2 mechanical fixes only, marked inline).

  Stage 3, RECURSIVE BISECTION ([A] getRecBipart/getClusterVar/getIVP;
    [B]; [D] eqs. 57-60): start with w_i = 1 for all i; recursively split
    the Stage-2-sorted list IN HALF BY COUNT (floor(len/2) — the split is
    on the sorted list, NOT on the dendrogram's own branch boundaries;
    that is what [A] does and [D] eq. 59-60 describe); for each
    (left, right) pair compute each half's variance as
        V_half = w' V_sub w   with   w = diag(V_sub)^-1 / tr(diag(V_sub)^-1)
    (the inverse-variance portfolio of the half, "optimal for a diagonal
    covariance matrix" — [D] Section 2.3.3), then scale the left half's
    weights by
        alpha = 1 - V_left / (V_left + V_right)
    and the right half's by (1 - alpha). Because every asset's weight is a
    product of factors in [0, 1] and each split conserves the parent's
    total, the result satisfies 0 <= w_i <= 1 and sum(w) = 1 by
    construction ([D], end of Section 2.3.3).

CLOSED-FORM CONSEQUENCES this module's tests verify (derived in
tests/test_hrp_optimizer.py, not asserted from authority):
  - For a DIAGONAL covariance matrix, HRP reduces exactly to the
    inverse-variance portfolio (every split hands each half its share of
    total precision), hence: equal weights for identical uncorrelated
    assets (any N, not just powers of 2), and sigma2^2/(sigma1^2+sigma2^2)
    for two uncorrelated assets.
  - Weights are invariant to rescaling the covariance matrix (alpha is a
    ratio of variances; correlations unchanged) — so daily vs annualized
    covariance yields identical weights.

GUARDS THIS MODULE ADDS THAT THE SOURCES DO NOT SPECIFY (each flagged
inline; none alters the algorithm on well-posed inputs — [A] assumes a
clean, non-degenerate covariance matrix and specifies no input handling):
  - n=1 returns {asset: 1.0} ([A] requires n>=2 for linkage). UNVERIFIED
    against the paper — the paper never discusses a one-asset portfolio.
  - A non-positive or non-finite variance on the diagonal raises ValueError
    (inverse-variance weights are undefined; [A] would silently produce
    inf/NaN). UNVERIFIED against the paper for the same reason.
  - NaN correlations raise ValueError rather than being filled: unlike the
    ONC paper (whose own snippet does fillna(0), see
    effective_n_clustering.py), no source for THIS algorithm specifies a
    fill convention, and inventing one silently is what this project's
    methodology forbids. Callers must pass complete matrices.
  - (1 - rho)/2 is clipped into [0, 1] before the sqrt, guarding float
    noise like rho = 1 + 1e-16 producing sqrt(-eps) = NaN. Same guard
    PyPortfolioOpt applies; UNVERIFIED against the paper (no source
    discusses float noise).
  - Asset ordering note: for GENERIC inputs (all pairwise dtilde
    distinct), the dendrogram is unique and the output is invariant to
    input column order (tested). For inputs with EXACT ties (e.g. a
    perfectly symmetric correlation matrix), scipy's tie-breaking decides
    the leaf order and the split boundaries, so different input orders can
    yield different (all individually valid) weight vectors. No source
    specifies a tie-breaking rule; this module inherits scipy's, and
    flags rather than hides the fact. (For the fully-symmetric special
    case of IDENTICAL uncorrelated assets the weights are equal under
    every tie-break, so the closed-form test is unaffected.) Measured
    consequence while building the tests: on a tied input, even rescaling
    the covariance (daily -> annualized) perturbs cov_to_corr by ~1 ulp
    and can flip the tie-break, changing the tree — scale invariance, like
    order invariance, is exact only on tie-free inputs.

PURE FUNCTIONS, UNWIRED. Nothing here reads a database, mutates an input,
or is imported by any live pipeline; optimizer.py is untouched. Matching
the shipping convention of effective_n_clustering.py and
empirical_bayes_shrinkage.py: diagnostic/available infrastructure for
explicit callers (a human, a research script, a future opt-in endpoint
parameter), never a silent replacement for the existing default.

WHY BOTH OPTIMIZERS EXIST SIDE BY SIDE: the paper's stated motivation
([B]; [D] Section 2.3) is that quadratic optimizers invert an
ill-conditioned covariance matrix, concentrating the portfolio in
whichever corner estimation noise favors ("Markowitz's curse"), while HRP
never inverts the matrix at all — it only ever divides variances of
inverse-variance-weighted sub-clusters — and therefore produces more
stable weights out of sample. tests/test_hrp_optimizer.py measures exactly
that claim against optimizer.py's own SLSQP max-Sharpe on Monte Carlo
draws from a known covariance (see the test file's docstring for the
measured numbers).

References:
  Lopez de Prado (2016), "Building Diversified Portfolios that Outperform
    Out-of-Sample", JPM 42(4), 59-69. SSRN 2708678. -- the algorithm.
  Lopez de Prado (2018), "Advances in Financial Machine Learning", Wiley,
    Ch. 16. -- same algorithm, book form; pp. 224-226 quoted via [C].
  https://quantresearch.org/HRP.py.txt -- the author's own implementation,
    read line-by-line this session; the normative reference for every step.
  SSRN 2713516 -- the author's own slides for the paper (formula set and
    Monte Carlo design), read via SlideShare transcript this session.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import scipy.cluster.hierarchy as sch
from scipy.spatial.distance import pdist

from app.services.risk.engine import MIN_OBS_FOR_ANY_ESTIMATE
from app.services.risk.errors import InsufficientHistoryError
from app.services.risk.optimizer import (
    OptimizationResult,
    _portfolio_stats,
)
from app.services.risk.volatility import TRADING_DAYS_PER_YEAR


@dataclass
class HRPResult:
    """Output of one HRP allocation. weights maps asset -> weight in the
    caller's original column order; quasi_diag_order is the Stage 2
    permutation (adjacent = correlated), kept because it is the
    human-readable diagnostic of WHY the allocation split where it did;
    linkage_matrix is the raw scipy linkage (n-1 x 4, [left, right,
    distance, count] per merge) as plain lists for JSON-friendliness."""

    weights: dict[str, float]
    quasi_diag_order: list[str]
    linkage_matrix: list[list[float]] = field(default_factory=list)


def _validate_cov(cov: pd.DataFrame) -> None:
    """Input guards — module additions, not paper steps (see module
    docstring): [A] assumes a clean covariance matrix and specifies no
    handling for degenerate input, so degenerate input is REFUSED, never
    silently patched."""
    if cov.shape[0] != cov.shape[1]:
        raise ValueError(f"covariance matrix must be square, got {cov.shape}")
    if list(cov.index) != list(cov.columns):
        raise ValueError("covariance matrix index and columns must match (same assets, same order)")
    if len(set(cov.columns)) != len(cov.columns):
        raise ValueError("covariance matrix has duplicate asset labels")
    values = cov.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(
            "covariance matrix contains NaN/inf — no source for this algorithm specifies a "
            "fill convention, so incomplete matrices are refused rather than silently patched"
        )
    diag = np.diag(values)
    if (diag <= 0).any():
        bad = [str(c) for c, v in zip(cov.columns, diag) if v <= 0]
        raise ValueError(
            f"non-positive variance for {', '.join(bad)} — inverse-variance weights are "
            "undefined (the paper does not address zero-variance assets)"
        )
    if not np.allclose(values, values.T, rtol=0.0, atol=1e-8 * max(1.0, float(np.abs(diag).max()))):
        raise ValueError("covariance matrix is not symmetric")


def cov_to_corr(cov: pd.DataFrame) -> pd.DataFrame:
    """corr_ij = cov_ij / sqrt(cov_ii * cov_jj) — standard identity, used
    when a caller supplies only a covariance matrix ([A]'s main() computes
    corr directly from returns; this is the same quantity)."""
    vols = np.sqrt(np.diag(cov.to_numpy(dtype=float)))
    corr = cov.to_numpy(dtype=float) / np.outer(vols, vols)
    return pd.DataFrame(corr, index=cov.index, columns=cov.columns)


def correlation_distance(corr: pd.DataFrame) -> pd.DataFrame:
    """Stage 1a: d_ij = sqrt((1 - rho_ij)/2) — [A] correlDist, [B], [D]
    eq. 53. rho=+1 -> 0, rho=0 -> sqrt(1/2), rho=-1 -> 1.

    The clip of (1-rho)/2 into [0, 1] is a float-noise guard (module
    addition, flagged in the module docstring). NaN correlations are
    refused, not filled — also flagged there.

    NOTE: effective_n_clustering.correlation_to_distance implements the
    same formula for the ONC paper. Deliberately NOT imported here: that
    module's fillna(0) convention is the ONC paper's own snippet behaviour
    and has no source in the HRP paper, and risk/ does not import from
    research_lab/ (the dependency points the other way)."""
    values = corr.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(
            "correlation matrix contains NaN/inf — refused rather than silently filled "
            "(no fill convention exists in any source for this algorithm)"
        )
    dist = np.sqrt(np.clip((1.0 - values) / 2.0, 0.0, 1.0))
    return pd.DataFrame(dist, index=corr.index, columns=corr.columns)


def hrp_linkage(corr: pd.DataFrame) -> np.ndarray:
    """Stages 1b + 1c: single-linkage clustering on the DISTANCE OF
    DISTANCES dtilde_ij = ||D_col_i - D_col_j||_2 ([B]; [D] eqs. 54-56).

    pdist(D_rows, euclidean) IS dtilde (D is symmetric, so rows ==
    columns), passed condensed. This reproduces the author's own
    sch.linkage(D, 'single') square-matrix call exactly — scipy treats a
    square input as observation vectors and clusters on Euclidean
    row-to-row distances — without relying on that ambiguous (and now
    ClusterWarning-flagged) interpretation. Equivalence to the author's
    exact call is asserted in tests/test_hrp_optimizer.py."""
    dist = correlation_distance(corr)
    dtilde_condensed = pdist(dist.to_numpy(), metric="euclidean")
    return sch.linkage(dtilde_condensed, method="single")


def quasi_diagonal_order(link: np.ndarray) -> list[int]:
    """Stage 2 ([A] getQuasiDiag, ported line-for-line; [C]): expand the
    final merge's two branches recursively, preserving order, until only
    original items remain. Returns positional indices into the original
    asset order.

    Port notes (mechanical py3/pandas-2 fixes only): Series.append (removed
    in pandas 2) -> pd.concat; iteration/indexing otherwise verbatim.
    Equivalence to scipy's own leaves_list (an independent implementation
    of the same traversal) is asserted in the tests."""
    link = link.astype(int)
    sort_ix = pd.Series([link[-1, 0], link[-1, 1]])
    num_items = link[-1, 3]  # number of original items
    while sort_ix.max() >= num_items:
        sort_ix.index = range(0, sort_ix.shape[0] * 2, 2)  # make space
        df0 = sort_ix[sort_ix >= num_items]  # find clusters
        i = df0.index
        j = df0.values - num_items
        sort_ix[i] = link[j, 0]  # item 1
        df0 = pd.Series(link[j, 1], index=i + 1)
        sort_ix = pd.concat([sort_ix, df0])  # PORT: was sortIx.append(df0)
        sort_ix = sort_ix.sort_index()  # re-sort
        sort_ix.index = range(sort_ix.shape[0])  # re-index
    return sort_ix.tolist()


def _inverse_variance_weights(cov: pd.DataFrame) -> np.ndarray:
    """[A] getIVP / [B]: w = diag(V)^-1 / tr(diag(V)^-1)."""
    ivp = 1.0 / np.diag(cov.to_numpy(dtype=float))
    return ivp / ivp.sum()


def _cluster_variance(cov: pd.DataFrame, members: list[str]) -> float:
    """[A] getClusterVar / [B], [D] eqs. 57-58: the variance w'Vw of the
    cluster's inverse-variance portfolio."""
    sub = cov.loc[members, members]
    w = _inverse_variance_weights(sub)
    return float(w @ sub.to_numpy(dtype=float) @ w)


def recursive_bisection_weights(cov: pd.DataFrame, sorted_assets: list[str]) -> pd.Series:
    """Stage 3 ([A] getRecBipart, ported line-for-line; [B]; [D] eqs.
    57-60). The split is len//2 BY COUNT of the sorted list — [A]'s exact
    rule (py2 len(i)/2 on ints), NOT a split at the dendrogram's own branch
    boundary. alpha = 1 - V_left/(V_left+V_right) scales the left half,
    (1 - alpha) the right."""
    w = pd.Series(1.0, index=sorted_assets)
    clusters: list[list[str]] = [list(sorted_assets)]
    while len(clusters) > 0:
        clusters = [
            c[j:k]
            for c in clusters
            for j, k in ((0, len(c) // 2), (len(c) // 2, len(c)))  # PORT: was len/2 (py2 int div)
            if len(c) > 1
        ]  # bi-section
        for i in range(0, len(clusters), 2):  # parse in pairs
            left = clusters[i]
            right = clusters[i + 1]
            var_left = _cluster_variance(cov, left)
            var_right = _cluster_variance(cov, right)
            alpha = 1.0 - var_left / (var_left + var_right)
            w[left] *= alpha  # weight 1
            w[right] *= 1.0 - alpha  # weight 2
    return w


def compute_hrp_weights(cov: pd.DataFrame, corr: pd.DataFrame | None = None) -> HRPResult:
    """The full three-stage HRP allocation on an already-estimated
    covariance (and optionally correlation) matrix. Pure function.

    corr defaults to the correlation implied by cov — identical to [A]'s
    main(), which computes x.cov() and x.corr() from the same sample, when
    the caller did the same. Supplying corr explicitly exists so a caller
    experimenting with, e.g., a shrunk covariance but raw correlations can
    do so deliberately.

    Weight keys are returned in the caller's original column order (the
    quasi-diagonal order ships separately in the result)."""
    _validate_cov(cov)
    original_columns = list(cov.columns)
    assets = [str(c) for c in original_columns]

    if len(assets) == 1:
        # Module addition, UNVERIFIED against the paper (flagged in module
        # docstring): [A]'s linkage needs n >= 2; a one-asset portfolio can
        # only be fully allocated to that asset.
        return HRPResult(weights={assets[0]: 1.0}, quasi_diag_order=[assets[0]])

    if corr is None:
        corr = cov_to_corr(cov)
    else:
        if list(corr.index) != original_columns or list(corr.columns) != original_columns:
            raise ValueError("corr and cov must share the same assets in the same order")

    # BUG FIX (found by adversarial verification, not caught by the
    # original build's own 44 tests -- all of which happened to use
    # already-string labels like "A0"): recursive_bisection_weights ->
    # _cluster_variance slices `cov` with the STRINGIFIED labels in
    # `sorted_assets` (built from `assets` below), but cov itself kept
    # whatever labels the caller passed in. Any non-string column labels
    # -- including integers, which is exactly what the paper's OWN worked
    # example uses (generateData's columns=range(1, n+1)) -- raised a
    # KeyError. Normalizing cov's labels to the same stringified `assets`
    # once, here, means every downstream .loc[] call operates in one
    # consistent label space instead of silently mixing two. A copy, not
    # a mutation, matching this module's pure-function contract.
    cov = cov.copy()
    cov.index = assets
    cov.columns = assets

    link = hrp_linkage(corr)
    order = quasi_diagonal_order(link)
    sorted_assets = [assets[i] for i in order]  # [A]: corr.index[sortIx].tolist()
    w = recursive_bisection_weights(cov, sorted_assets)

    return HRPResult(
        weights={a: float(w[a]) for a in assets},
        quasi_diag_order=sorted_assets,
        linkage_matrix=[[float(v) for v in row] for row in link],
    )


def compute_hrp_weights_from_returns(asset_returns: pd.DataFrame) -> HRPResult:
    """HRP from a T x N frame of per-period returns: sample cov + sample
    corr, exactly [A]'s main() (cov, corr = x.cov(), x.corr()). No
    annualization on purpose — HRP weights are invariant to rescaling the
    covariance (see module docstring; tested), so annualizing here would be
    dead code dressed up as a step."""
    return compute_hrp_weights(asset_returns.cov(), asset_returns.corr())


def compute_hrp_portfolio_optimization_from_returns(
    asset_returns: pd.DataFrame,
    weights: dict[str, float],
    risk_free_rate: float,
    as_of: str,
    warnings: list[str] | None = None,
    insufficient_history_label: str = "holdings",
) -> OptimizationResult:
    """Drop-in-shaped counterpart to optimizer.py's
    compute_portfolio_optimization_from_returns, so a caller (or a future
    opt-in endpoint parameter) can surface HRP through the exact same
    OptimizationResult contract and compare like with like. Deliberately
    reuses optimizer._portfolio_stats — same annualization
    (TRADING_DAYS_PER_YEAR), same Sharpe convention, same before/after
    framing — rather than a parallel copy.

    Differences from the mean-variance version, on purpose:
      - No max_weight cap parameter: the cap exists there to stop
        mean-variance corner solutions under estimation error (see
        DEFAULT_MAX_WEIGHT's comment in optimizer.py). HRP cannot produce
        a corner solution — every weight is a product of alpha in [0, 1]
        splits — and no source applies a cap to HRP, so offering one here
        would be an uncited embellishment.
      - No expected-returns input to the allocation: HRP uses only the
        covariance structure ([B]: the paper "fully concentrates on the
        covariance matrix, hence dropping the forecasted returns" — [D]
        Section 2.3). Mean returns appear ONLY in the reported
        PortfolioStats, for comparability with the mean-variance result.

    Same rounding convention as the mean-variance path (4 decimals on the
    reported weights)."""
    warnings = warnings if warnings is not None else []
    tickers = list(weights.keys())

    n_obs = len(asset_returns)
    if n_obs < MIN_OBS_FOR_ANY_ESTIMATE:
        raise InsufficientHistoryError(n_obs, label=insufficient_history_label)

    frame = asset_returns[tickers]
    hrp = compute_hrp_weights_from_returns(frame)

    mean_returns = frame.mean() * TRADING_DAYS_PER_YEAR
    cov_matrix = frame.cov() * TRADING_DAYS_PER_YEAR

    hrp_w = np.array([hrp.weights[t] for t in tickers])
    hrp_w = np.round(hrp_w, 4)  # same reporting convention as optimizer.py

    optimized_stats = _portfolio_stats(hrp_w, mean_returns, cov_matrix, risk_free_rate)
    current_w = np.array([weights[t] for t in tickers])
    current_stats = _portfolio_stats(current_w, mean_returns, cov_matrix, risk_free_rate)

    return OptimizationResult(
        as_of=as_of,
        optimized_weights=dict(zip(tickers, hrp_w.tolist())),
        optimized=optimized_stats,
        current=current_stats,
        warnings=warnings,
    )
