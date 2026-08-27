"""Validation of the HRP optimizer against KNOWN correct answers.

THE LOAD-BEARING TESTS IN THIS FILE ARE THE CLOSED-FORM AND GROUND-TRUTH
ONES — same rationale as test_effective_n_clustering.py, and the same scar:
this project's hand-rolled Corwin-Schultz estimator passed every
self-consistency test its author wrote and was still badly wrong, because no
test ever fed it an input with a KNOWN correct answer. So:

  1. CLOSED FORMS, derived in each test's docstring, not asserted from
     authority: identical uncorrelated assets -> exactly equal weights (any
     N); two uncorrelated assets -> sigma2^2/(sigma1^2+sigma2^2); ANY
     diagonal covariance -> exactly the inverse-variance portfolio.
  2. STRUCTURAL PURPOSE: a block of highly-correlated redundant assets is
     collectively under-weighted relative to an uncorrelated diversifier —
     the failure mode of quadratic optimizers HRP exists to avoid.
  3. INVARIANTS: weights non-negative and sum to 1; permutation invariance
     on generic (tie-free) inputs; scale invariance (daily vs annualized
     covariance).
  4. REFERENCE AGREEMENT: a golden test pinned to weights produced by Lopez
     de Prado's OWN posted code (quantresearch.org/HRP.py.txt, ported to
     py3 with mechanical fixes only) on the same pinned dataset.
  5. THE PAPER'S OUT-OF-SAMPLE STABILITY CLAIM, measured against this
     project's own mean-variance optimizer, not just asserted.

CROSS-CHECK RESULTS BEHIND THE GOLDEN TEST (run during the build, scripts
in the session scratchpad; 13 datasets: the paper's own generateData design
10 assets x 10,000 obs, plus block- and factor-structured samples N in
{5,10,20} x T in {150,600}):
  - this module vs Lopez de Prado's own code (py3 port): max |dw| = 0.0
    (bit-identical) on ALL 13 datasets.
  - this module vs PyPortfolioOpt 1.6.0 HRPOpt: max |dw| <= 1.9e-15 on the
    6/13 datasets where both produce the same dendrogram leaf order; up to
    2.6e-1 on the other 7 — PyPortfolioOpt single-links on the condensed
    correlation-distance d itself, NOT the paper's distance-of-distances
    dtilde (hierarchical_portfolio.py, optimize(): ssd.squareform(matrix)),
    so its Stage-1 tree can legitimately differ. Feeding MY Stages 2+3
    PyPortfolioOpt's own Stage-1 tree collapses every difference to
    <= 1.9e-15 across all 13 datasets: the divergence is entirely the
    documented Stage-1 metric variant, nothing else (a secondary,
    non-load-bearing difference: PyPortfolioOpt's HRPOpt.optimize() also
    rounds its correlation matrix to 6 decimals before clustering — of no
    measurable effect versus this module on the 13 tie-free datasets
    tested, but a further source of possible divergence on a tied input,
    same class of effect as this file's own tie-sensitivity test below).
    (Notably that means
    PyPortfolioOpt does NOT reproduce the paper's own worked-example data
    design — the author's code and this module do.)

OUT-OF-SAMPLE STABILITY MEASUREMENT behind test bound choices (200 Monte
Carlo draws, 10 assets, 2-block true covariance, T=252, details in the
stability test's docstring): per-asset weight std across draws — HRP mean
0.0245 / max 0.0666; project MV max-Sharpe (default 0.4 cap) mean 0.1454 /
max 0.1709 (5.94x less stable); OOS annualized variance under the TRUE
covariance — HRP 0.01379 +/- 0.00085 vs MV 0.03154 +/- 0.01945; the
deterministic true-cov IVP reference is 0.01371 and equal weight 0.02923.
Direction consistent with the paper's own published Monte Carlo (slides,
SSRN 2713516: out-of-sample variance HRP 0.0671 vs CLA min-variance 0.1157
(+72.47%) vs IVP 0.0928 (+38.24%)) — the paper compared min-variance CLA;
this project's optimizer is max-Sharpe, which also chases noisy means, so
the measured instability gap here being LARGER is expected, not anomalous.
"""

import warnings

import numpy as np
import pandas as pd
import pytest
import scipy.cluster.hierarchy as sch

from app.services.risk.errors import InsufficientHistoryError
from app.services.risk.hrp_optimizer import (
    HRPResult,
    compute_hrp_portfolio_optimization_from_returns,
    compute_hrp_weights,
    compute_hrp_weights_from_returns,
    correlation_distance,
    cov_to_corr,
    hrp_linkage,
    quasi_diagonal_order,
    recursive_bisection_weights,
)
from app.services.risk.optimizer import (
    OptimizationResult,
    compute_portfolio_optimization_from_returns,
)

# --- ground-truth constructors ----------------------------------------------


def diag_cov(variances: list[float]) -> pd.DataFrame:
    names = [f"A{i}" for i in range(len(variances))]
    return pd.DataFrame(np.diag(variances), index=names, columns=names)


def block_cov(
    n: int, block_sizes: list[int], rho_within: float, rho_across: float, ann_vols: np.ndarray
) -> pd.DataFrame:
    """Block correlation matrix with heterogeneous vols — the same
    construction family as test_effective_n_clustering.py's fixtures."""
    assert sum(block_sizes) == n
    corr = np.full((n, n), rho_across)
    start = 0
    for s in block_sizes:
        corr[start : start + s, start : start + s] = rho_within
        start += s
    np.fill_diagonal(corr, 1.0)
    cov = corr * np.outer(ann_vols, ann_vols)
    names = [f"A{i}" for i in range(n)]
    return pd.DataFrame(cov, index=names, columns=names)


def sampled_block_returns(seed: int, t: int = 300) -> pd.DataFrame:
    """Generic (tie-free) 6-asset, 2-block sample — the golden dataset's
    construction, reused for invariance tests at other seeds."""
    rng = np.random.default_rng(seed)
    corr = np.full((6, 6), 0.05)
    corr[:3, :3] = 0.7
    corr[3:, 3:] = 0.7
    np.fill_diagonal(corr, 1.0)
    ann_vols = np.array([0.12, 0.18, 0.25, 0.15, 0.30, 0.22])
    cov = corr * np.outer(ann_vols, ann_vols) / 252.0
    x = rng.multivariate_normal(np.zeros(6), cov, size=t)
    return pd.DataFrame(x, columns=[f"A{i}" for i in range(6)])


# --- 1. CLOSED FORMS (the load-bearing tests) --------------------------------


@pytest.mark.parametrize("n", [2, 3, 4, 5, 7, 8])
def test_identical_uncorrelated_assets_get_exactly_equal_weights(n: int):
    """DERIVATION: for a diagonal covariance sigma^2*I, every cluster of m
    assets has inverse-variance weights 1/m each and cluster variance
    sigma^2/m. A count-split into halves of sizes m0, m1 therefore gets
    alpha = 1 - (sigma^2/m0)/(sigma^2/m0 + sigma^2/m1) = m0/(m0+m1): each
    half receives exactly its member share, for ANY split sizes — so final
    weights are exactly 1/N for every N, not only powers of two."""
    result = compute_hrp_weights(diag_cov([0.04] * n))
    assert set(result.weights) == {f"A{i}" for i in range(n)}
    for w in result.weights.values():
        assert w == pytest.approx(1.0 / n, abs=1e-12)


@pytest.mark.parametrize(
    ("var0", "var1"),
    [(0.04, 0.08), (0.01, 0.04), (0.09, 0.21)],  # ratios 1:2, 1:4, 3:7
)
def test_two_uncorrelated_assets_inverse_variance_closed_form(var0: float, var1: float):
    """DERIVATION: two uncorrelated assets are one split. Each singleton's
    'cluster variance' is its own variance, so
    alpha_0 = 1 - v0/(v0+v1) = v1/(v0+v1), i.e. w0 = v1/(v0+v1) and
    w1 = v0/(v0+v1) — the inverse-variance allocation
    (1/v0)/((1/v0)+(1/v1)) after multiplying through by v0*v1."""
    result = compute_hrp_weights(diag_cov([var0, var1]))
    assert result.weights["A0"] == pytest.approx(var1 / (var0 + var1), abs=1e-12)
    assert result.weights["A1"] == pytest.approx(var0 / (var0 + var1), abs=1e-12)
    assert sum(result.weights.values()) == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize("n", [3, 5, 8])
def test_any_diagonal_covariance_reduces_exactly_to_ivp(n: int, seed: int):
    """DERIVATION (generalizes the two tests above): for a diagonal
    covariance, a cluster's inverse-variance portfolio has variance equal
    to the reciprocal of the cluster's total precision P = sum(1/v_i)
    (harmonic composition), so every split assigns the left half
    alpha = (1/P_right)^-1-composed share = P_left/(P_left+P_right) — its
    precision share. Telescoping down the recursion, asset i's final
    weight is (1/v_i)/sum_j(1/v_j): EXACTLY the inverse-variance
    portfolio, for any N and any variances. This is also the paper's own
    consistency anchor: traditional risk parity's IVP is the special case
    HRP must reduce to when there is no correlation structure to exploit."""
    rng = np.random.default_rng(seed)
    variances = rng.uniform(0.01, 0.25, size=n).tolist()
    result = compute_hrp_weights(diag_cov(variances))
    precisions = np.array([1.0 / v for v in variances])
    ivp = precisions / precisions.sum()
    for i in range(n):
        assert result.weights[f"A{i}"] == pytest.approx(ivp[i], abs=1e-12)


# --- 2. THE ALGORITHM'S STATED PURPOSE ---------------------------------------


def test_redundant_cluster_is_underweighted_vs_diversifier():
    """The paper's motivating scenario: several near-substitute assets plus
    one genuine diversifier, all with the SAME population variance. A
    naive 1/N gives the redundant block 4/5 of the capital; HRP must give
    the diversifier substantially more than 1/N and the block
    substantially less than 4/5.

    Construction (sampled, hence tie-free, matching the paper's own
    sampled-validation style): 4 assets sharing a common N(0,1) factor
    plus N(0, 0.33^2) idiosyncratic noise (within-block rho ~ 0.90), and
    one independent asset scaled to the same population variance.
    Measured across seeds 0-5: diversifier weight 0.317-0.346 (vs naive
    0.20), redundant-block sum 0.654-0.683 (vs naive 0.80). Seed 2 is
    pinned; bounds leave margin.

    HONEST STRUCTURAL NOTE, measured and shared bit-identically with the
    author's own code: the recursive bisection splits the sorted list BY
    COUNT (len//2), not at the dendrogram boundary, so with 5 assets the
    diversifier gets PAIRED with one redundant asset in the 2|3 split and
    that one redundant asset rides along with a near-diversifier weight
    (~0.32) while the remaining three are heavily under-weighted
    (~0.09-0.17). On 2 of 6 measured seeds the ride-along asset's weight
    marginally exceeded the diversifier's. That is a real, documented
    property of the published algorithm (the count-split critique later
    addressed by Pfitzinger & Katzke 2019's constrained-HRP variant), not
    an implementation artifact — asserting 'every redundant asset below
    average weight' would assert something the ALGORITHM does not do."""
    rng = np.random.default_rng(2)
    t = 1000
    sigma = 0.33
    common = rng.normal(size=(t, 1))
    block = np.repeat(common, 4, axis=1) + rng.normal(scale=sigma, size=(t, 4))
    diversifier = rng.normal(scale=np.sqrt(1 + sigma**2), size=(t, 1))
    frame = pd.DataFrame(
        np.concatenate([block, diversifier], axis=1), columns=["R0", "R1", "R2", "R3", "DIV"]
    )
    result = compute_hrp_weights_from_returns(frame)
    w = result.weights

    assert w["DIV"] > 0.28  # measured 0.317-0.346 across seeds; naive is 0.20
    assert w["DIV"] == max(w.values())  # holds at this pinned seed (see docstring)
    redundant_sum = w["R0"] + w["R1"] + w["R2"] + w["R3"]
    assert redundant_sum < 0.72  # measured 0.654-0.683; naive is 0.80
    assert redundant_sum + w["DIV"] == pytest.approx(1.0, abs=1e-12)


def test_ride_along_asset_can_outweigh_the_diversifier():
    """Exercises, rather than just documents, the ride-along property
    described in test_redundant_cluster_is_underweighted_vs_diversifier's
    docstring: because Stage 3 splits the quasi-diagonalized list BY COUNT
    (len//2), not at the dendrogram's own branch boundary, the redundant
    asset adjacent to DIV in the Stage-2 order gets paired with it alone in
    the top-level 2|3 split and can end up weighted like a SECOND
    diversifier, not like the other three redundant assets. The previous
    test's own assertion (`w["DIV"] == max(w.values())`) is pinned at a
    seed where this does NOT happen and would not catch a regression that
    broke the count-based split back toward the dendrogram boundary.

    Same construction, seed=0 (all other parameters identical to the
    sibling test): measured directly this session,
    quasi_diag_order = ['DIV', 'R0', 'R3', 'R1', 'R2'] -- R0 is DIV's
    Stage-2 neighbour and rides along at w=0.3402, ACTUALLY EXCEEDING
    DIV's own w=0.3170, while the other two redundant assets sit at
    0.088-0.167 -- nowhere near either of them. Finding the neighbour via
    quasi_diag_order (not hardcoding "R0") keeps the test tied to the
    mechanism, not to this one seed's incidental labelling."""
    rng = np.random.default_rng(0)
    t = 1000
    sigma = 0.33
    common = rng.normal(size=(t, 1))
    block = np.repeat(common, 4, axis=1) + rng.normal(scale=sigma, size=(t, 4))
    diversifier = rng.normal(scale=np.sqrt(1 + sigma**2), size=(t, 1))
    frame = pd.DataFrame(
        np.concatenate([block, diversifier], axis=1), columns=["R0", "R1", "R2", "R3", "DIV"]
    )
    result = compute_hrp_weights_from_returns(frame)
    w = result.weights
    order = result.quasi_diag_order

    div_pos = order.index("DIV")
    # DIV sits at one end of the sorted list (it's the least-similar asset
    # to everything else); its single Stage-2 neighbour is the ride-along
    # candidate under a count-based 2|3 split.
    assert div_pos in (0, len(order) - 1)
    neighbor = order[1] if div_pos == 0 else order[-2]
    others = [a for a in ("R0", "R1", "R2", "R3") if a != neighbor]

    assert w[neighbor] == pytest.approx(0.34015264571686643, abs=1e-9)
    assert w["DIV"] == pytest.approx(0.317027999844828, abs=1e-9)
    assert w[neighbor] > w["DIV"]  # the ride-along asset outweighs the real diversifier
    for other in others:
        assert w[other] < 0.20  # naive 1/5 -- the other redundant assets are NOT rescued


# --- 3. STRUCTURAL INVARIANTS ------------------------------------------------


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_weights_nonnegative_and_sum_to_one(seed: int):
    frame = sampled_block_returns(seed)
    result = compute_hrp_weights_from_returns(frame)
    assert sum(result.weights.values()) == pytest.approx(1.0, abs=1e-9)
    for w in result.weights.values():
        assert w > 0.0  # strictly: products of alphas in (0,1) starting from 1


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_permutation_invariance_on_generic_input(seed: int):
    """Permuting the input column order must not change any asset's weight
    on a GENERIC (tie-free) input — the tree, and hence the allocation,
    is a function of the correlation structure, not of column order. (For
    inputs with EXACT distance ties scipy's tie-breaking decides the tree
    and this invariance is NOT guaranteed — flagged in the module
    docstring; identical-asset ties still yield equal weights, covered by
    the closed-form test above.)"""
    frame = sampled_block_returns(seed)
    base = compute_hrp_weights_from_returns(frame)
    rng = np.random.default_rng(seed + 100)
    perm = rng.permutation(frame.shape[1])
    permuted = frame.iloc[:, perm]
    shuffled = compute_hrp_weights_from_returns(permuted)
    for asset, w in base.weights.items():
        assert shuffled.weights[asset] == pytest.approx(w, abs=1e-12)


def test_scale_invariance_daily_vs_annualized():
    """alpha = 1 - V0/(V0+V1) is a ratio of variances and the correlation
    matrix is scale-free, so multiplying the covariance by any positive
    constant (e.g. 252 for annualization) must leave weights identical —
    which is why compute_hrp_weights_from_returns does not annualize.

    Tested on a GENERIC (sampled, tie-free) covariance deliberately: on an
    EXACT block matrix, whose correlation entries tie by construction,
    rescaling perturbs cov_to_corr's float rounding by ~1 ulp, which flips
    scipy's tie-breaking between equal distances and yields a DIFFERENT
    (equally valid) tree — the exact-ties caveat already flagged in the
    module docstring, observed directly while writing this test. On
    tie-free inputs the invariance holds to float precision, as asserted
    here across seeds."""
    for seed in range(3):
        cov = sampled_block_returns(seed).cov()
        daily = compute_hrp_weights(cov)
        annual = compute_hrp_weights(cov * 252.0)
        for asset, w in daily.weights.items():
            assert annual.weights[asset] == pytest.approx(w, abs=1e-12)
        assert daily.quasi_diag_order == annual.quasi_diag_order


def test_scale_invariance_breaks_on_a_tied_input():
    """The exact-ties caveat the sibling test above only narrates in prose
    ("rescaling perturbs cov_to_corr's float rounding by ~1 ulp, which
    flips scipy's tie-breaking") was never itself asserted anywhere -- a
    regression that broke this specific claim (e.g. by rounding
    correlations before clustering, which would coincidentally paper over
    the ulp noise this test relies on) would go unnoticed. This test
    exercises it directly on a deliberately EXACT-tie construction: two
    3-asset blocks with identical within-block correlation, identical
    across-block correlation, and pairwise-identical per-asset vols
    (vols[3:] = vols[:3]) -- every distance a mirror-image asset has to
    everything else is bit-identical to its twin's, by construction.

    Bit-exact reproduction, recorded here (not just seeded) because the
    property depends on the EXACT float64 values produced by this call
    sequence, not merely on the seed: replay np.random.default_rng(0)
    through 4 identical draws (n_per_block, rho_within, rho_across, vols),
    keep only the 4th (trial index 3) -- discovered this session by
    scanning seed=0 for a tied construction where annualizing (x252) does
    flip the tie-break, since most tied constructions tried did NOT flip
    (the sibling test's own 3 seeds among them) and this is deliberately
    the one that does. Measured directly: daily order
    ['A2','A0','A1','A5','A3','A4'] -> annualized order
    ['A0','A1','A2','A3','A4','A5'], max|dw| = 0.0902 across the 6 assets
    -- a real, nontrivial reallocation from nothing but a unit change,
    not float noise at the level test_scale_invariance_daily_vs_annualized
    guards to 1e-12. This is a property of the published algorithm on
    degenerate (tied) input, not a bug: see the module docstring's
    'Asset ordering note'."""
    n = 6
    n_per_block = 3
    rho_within = 0.607692555740627
    rho_across = 0.11510326627856503
    vols = np.array(
        [
            0.3991629807367634,
            0.39425060163286907,
            0.3056625953442084,
            0.3991629807367634,
            0.39425060163286907,
            0.3056625953442084,
        ]
    )
    corr = np.full((n, n), rho_across)
    corr[:n_per_block, :n_per_block] = rho_within
    corr[n_per_block:, n_per_block:] = rho_within
    np.fill_diagonal(corr, 1.0)
    names = [f"A{i}" for i in range(n)]
    cov_daily = pd.DataFrame(corr * np.outer(vols, vols), index=names, columns=names)

    daily = compute_hrp_weights(cov_daily)
    annual = compute_hrp_weights(cov_daily * 252.0)

    assert daily.quasi_diag_order != annual.quasi_diag_order  # the tie-break DID flip
    max_dw = max(abs(daily.weights[a] - annual.weights[a]) for a in daily.weights)
    assert max_dw == pytest.approx(0.09015361539843869, abs=1e-9)
    assert max_dw > 0.05  # a real reallocation, not float noise
    # both allocations independently remain valid HRP outputs throughout
    for result in (daily, annual):
        assert sum(result.weights.values()) == pytest.approx(1.0, abs=1e-9)
        for w in result.weights.values():
            assert w > 0.0


# --- 4. STAGE-LEVEL AGREEMENT WITH THE SOURCES -------------------------------


def test_linkage_matches_authors_exact_square_matrix_call():
    """The author's code calls sch.linkage(D, 'single') on the FULL SQUARE
    distance matrix (scipy then clusters on Euclidean distances between
    D's rows — the paper's dtilde). This module passes pdist(D) condensed
    instead, claiming exact equivalence; assert it, per dataset, against
    the author's own call form (ClusterWarning suppressed, behaviour
    unchanged)."""
    for seed in range(3):
        frame = sampled_block_returns(seed)
        corr = frame.corr()
        mine = hrp_linkage(corr)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            authors = sch.linkage(correlation_distance(corr), "single")
        assert np.allclose(mine, authors, atol=1e-12)


def test_quasi_diag_order_matches_scipy_leaves_list():
    """getQuasiDiag (ported line-for-line) against scipy's own leaves_list
    — an independently-implemented traversal of the same dendrogram. Both
    must produce the identical leaf ordering."""
    for seed in range(5):
        frame = sampled_block_returns(seed)
        link = hrp_linkage(frame.corr())
        assert quasi_diagonal_order(link) == sch.leaves_list(link).tolist()


def test_golden_weights_match_lopez_de_prado_reference():
    """GOLDEN REGRESSION pinned to the author's own implementation: these
    exact weights were produced by BOTH this module and the py3 port of
    quantresearch.org/HRP.py.txt (max |difference| = 0.0, bit-identical)
    on this exact pinned dataset during the build's cross-check run. If
    this test ever fails, either the algorithm changed (a bug) or
    numpy/scipy changed sampling or linkage behaviour (investigate before
    touching the pins)."""
    frame = sampled_block_returns(7)
    result = compute_hrp_weights_from_returns(frame)
    expected = {
        "A0": 0.4676165003552266,
        "A1": 0.11177557090895783,
        "A2": 0.05358451998390461,
        "A3": 0.18266244611659996,
        "A4": 0.046149128162477494,
        "A5": 0.13821183447283353,
    }
    for asset, w in expected.items():
        assert result.weights[asset] == pytest.approx(w, abs=1e-10)
    assert result.quasi_diag_order == ["A5", "A3", "A4", "A0", "A1", "A2"]


# --- 5. THE PAPER'S OUT-OF-SAMPLE STABILITY CLAIM ----------------------------


def test_hrp_weights_are_more_stable_than_mean_variance_across_samples():
    """THE claim the paper exists to make, measured against this project's
    own optimizer rather than assumed: many independent samples from ONE
    known covariance structure; per-sample weights via HRP and via
    optimizer.py's SLSQP max-Sharpe (default 0.4 cap, equal-weight
    'current', rf=2%); stability = per-asset std of weights across
    samples, averaged over assets.

    True structure: 10 assets, two 5-asset correlation blocks (rho 0.7
    within, 0.1 across), annualized vols linspace 10%..40%, all true
    annualized means EQUAL at 6% — so every cross-asset preference the
    max-Sharpe step expresses is estimation noise, the regime the paper
    argues is realistic ('Markowitz's curse').

    Full-size measurement (200 draws, T=252, seed 42, run during the
    build): HRP mean weight-std 0.0245 vs MV 0.1454 — ratio 5.94x; OOS
    annualized variance under the true covariance 0.01379 +/- 0.00085
    (HRP) vs 0.03154 +/- 0.01945 (MV). This test re-measures at 40 draws
    (seeded, deterministic) and asserts the ratio with a wide margin: a
    genuine regression to parity would have to close a ~6x gap, while
    sampling wobble at 40 draws moves the ratio by far less."""
    n, t, n_draws = 10, 252, 40
    corr = np.full((n, n), 0.1)
    corr[:5, :5] = 0.7
    corr[5:, 5:] = 0.7
    np.fill_diagonal(corr, 1.0)
    ann_vols = np.linspace(0.10, 0.40, n)
    cov_daily = corr * np.outer(ann_vols, ann_vols) / 252.0
    mu_daily = np.full(n, 0.06 / 252.0)
    tickers = [f"A{i}" for i in range(n)]
    equal = {tk: 1.0 / n for tk in tickers}

    rng = np.random.default_rng(42)
    hrp_ws, mv_ws = [], []
    for _ in range(n_draws):
        frame = pd.DataFrame(
            rng.multivariate_normal(mu_daily, cov_daily, size=t), columns=tickers
        )
        hrp = compute_hrp_weights_from_returns(frame)
        hrp_ws.append([hrp.weights[tk] for tk in tickers])
        mv = compute_portfolio_optimization_from_returns(frame, equal, 0.02, as_of="mc")
        mv_ws.append([mv.optimized_weights[tk] for tk in tickers])

    hrp_std = np.array(hrp_ws).std(axis=0, ddof=1).mean()
    mv_std = np.array(mv_ws).std(axis=0, ddof=1).mean()
    assert hrp_std * 2.0 < mv_std, (
        f"HRP mean weight-std {hrp_std:.4f} not clearly more stable than "
        f"mean-variance {mv_std:.4f} — the paper's core claim regressed"
    )


# --- 6. INPUT GUARDS AND DEGENERATE CASES ------------------------------------


def test_single_asset_gets_full_weight():
    result = compute_hrp_weights(diag_cov([0.04]))
    assert result.weights == {"A0": 1.0}
    assert result.quasi_diag_order == ["A0"]


def test_zero_variance_asset_is_refused():
    with pytest.raises(ValueError, match="non-positive variance"):
        compute_hrp_weights(diag_cov([0.04, 0.0, 0.02]))


def test_nan_covariance_is_refused():
    cov = diag_cov([0.04, 0.02])
    cov.iloc[0, 1] = np.nan
    with pytest.raises(ValueError, match="NaN"):
        compute_hrp_weights(cov)


def test_asymmetric_covariance_is_refused():
    cov = diag_cov([0.04, 0.02])
    cov.iloc[0, 1] = 0.01  # cov.iloc[1, 0] stays 0 — not symmetric
    with pytest.raises(ValueError, match="not symmetric"):
        compute_hrp_weights(cov)


def test_mismatched_corr_labels_are_refused():
    cov = diag_cov([0.04, 0.02])
    corr = cov_to_corr(cov)
    corr.columns = ["B0", "B1"]
    corr.index = ["B0", "B1"]
    with pytest.raises(ValueError, match="same assets"):
        compute_hrp_weights(cov, corr)


def test_cov_to_corr_identity():
    cov = block_cov(4, [2, 2], 0.6, 0.1, np.array([0.1, 0.2, 0.3, 0.4]))
    corr = cov_to_corr(cov)
    assert np.allclose(np.diag(corr), 1.0)
    assert corr.loc["A0", "A1"] == pytest.approx(0.6)
    assert corr.loc["A0", "A2"] == pytest.approx(0.1)


def test_correlation_distance_endpoints():
    """d = sqrt((1-rho)/2): rho=+1 -> 0, rho=0 -> sqrt(1/2), rho=-1 -> 1
    (the metric's three anchor points, straight from the formula)."""
    corr = pd.DataFrame(
        [[1.0, 1.0, 0.0, -1.0], [1.0, 1.0, 0.0, -1.0], [0.0, 0.0, 1.0, 0.0], [-1.0, -1.0, 0.0, 1.0]],
        index=list("abcd"),
        columns=list("abcd"),
    )
    dist = correlation_distance(corr)
    assert dist.loc["a", "b"] == pytest.approx(0.0)
    assert dist.loc["a", "c"] == pytest.approx(np.sqrt(0.5))
    assert dist.loc["a", "d"] == pytest.approx(1.0)
    # float-noise guard: rho marginally above 1 must clip to distance 0, not NaN
    noisy = pd.DataFrame(
        [[1.0, 1.0 + 1e-15], [1.0 + 1e-15, 1.0]], index=list("ab"), columns=list("ab")
    )
    assert correlation_distance(noisy).loc["a", "b"] == 0.0


def test_recursive_bisection_two_singletons_directly():
    """Stage 3 in isolation on the smallest split: matches the two-asset
    closed form without going through Stages 1-2."""
    cov = diag_cov([0.04, 0.08])
    w = recursive_bisection_weights(cov, ["A0", "A1"])
    assert w["A0"] == pytest.approx(0.08 / 0.12, abs=1e-12)
    assert w["A1"] == pytest.approx(0.04 / 0.12, abs=1e-12)


# --- 7. THE OPTIMIZATION-RESULT-SHAPED WRAPPER -------------------------------


def test_wrapper_returns_optimization_result_contract():
    frame = sampled_block_returns(3)
    current = {f"A{i}": 1.0 / 6 for i in range(6)}
    result = compute_hrp_portfolio_optimization_from_returns(
        frame, current, risk_free_rate=0.02, as_of="2026-08-27"
    )
    assert isinstance(result, OptimizationResult)
    assert result.as_of == "2026-08-27"
    assert set(result.optimized_weights) == set(current)
    assert sum(result.optimized_weights.values()) == pytest.approx(1.0, abs=1e-3)
    for w in result.optimized_weights.values():
        assert 0.0 <= w <= 1.0
    # Stats are computed for both the HRP and the current allocation, on the
    # same annualized estimates, exactly like the mean-variance wrapper.
    assert result.optimized.volatility > 0
    assert result.current.volatility > 0
    assert result.warnings == []


def test_wrapper_raises_on_insufficient_history():
    frame = sampled_block_returns(0).iloc[:10]  # 10 < MIN_OBS_FOR_ANY_ESTIMATE
    with pytest.raises(InsufficientHistoryError):
        compute_hrp_portfolio_optimization_from_returns(
            frame, {f"A{i}": 1.0 / 6 for i in range(6)}, 0.02, as_of="x"
        )


def test_wrapper_universe_is_defined_by_weights_keys():
    """Like the mean-variance wrapper: weights' keys select (and order) the
    universe, even when the frame has extra columns."""
    frame = sampled_block_returns(4)
    subset = {f"A{i}": 1.0 / 3 for i in range(3)}
    result = compute_hrp_portfolio_optimization_from_returns(
        frame, subset, risk_free_rate=0.0, as_of="x"
    )
    assert set(result.optimized_weights) == set(subset)
    assert sum(result.optimized_weights.values()) == pytest.approx(1.0, abs=1e-3)


def test_result_dataclass_shape():
    frame = sampled_block_returns(5)
    result = compute_hrp_weights_from_returns(frame)
    assert isinstance(result, HRPResult)
    assert sorted(result.quasi_diag_order) == sorted(result.weights)
    # linkage matrix: n-1 merges, 4 columns, plain floats (JSON-friendly)
    assert len(result.linkage_matrix) == 5
    assert all(len(row) == 4 and all(isinstance(v, float) for v in row) for row in result.linkage_matrix)
