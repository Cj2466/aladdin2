"""Effective number of trials via ONC correlation clustering.

Companion diagnostic to deflated_sharpe.py, answering a question that module
must currently take on faith. compute_deflated_sharpe() accepts n_trials as an
input — a raw, pre-registered count ("212 pattern definitions", "48 vol-regime
specs") — and every count of that kind OVERSTATES the search breadth whenever
many of the definitions are correlated variants of one another. Two trials
whose return streams correlate at 0.95 are not two independent draws from the
noise distribution, and treating them as such inflates SR0 (the
expected-max-Sharpe hurdle) and makes the DSR *more* conservative than the
honest correction requires — or, in the Sidak/FWER direction, misstates the
familywise error rate. This module estimates the number of EFFECTIVELY
uncorrelated trials, E[K], by clustering the trials' return streams on their
correlation structure and counting clusters.

PRIMARY SOURCE — implemented from the actual paper, not from memory:

  Lopez de Prado, M. and M. Lewis (2019): "Detection of false investment
  strategies using unsupervised learning methods." Quantitative Finance,
  Vol. 19, No. 9, pp. 1555-1565. Working-paper version: SSRN 3167017
  (version of November 1, 2018), whose full text — including the Python
  reference snippets in its appendix — was pulled and read line-by-line
  during this implementation session. Section and page references below are
  to that SSRN version. The same algorithm appears, with small variations
  noted below, as "ONC" in Lopez de Prado, "Machine Learning for Asset
  Managers" (Cambridge, 2020), Section 4.4, code snippets 4.1-4.2.

THE ALGORITHM, as specified in the paper:

  1. Distance metric (Section 8.1, p. 9, displayed equation):
         D_ij = sqrt( (1/2) * (1 - rho_ij) )
     a proper metric (non-negativity, identity, symmetry, sub-additivity).

  2. Distance of distances (Section 8.1, pp. 9-10): clustering is performed
     not on D but on D~_ij = sqrt( sum_k (D_ik - D_jk)^2 ), the Euclidean
     distance between columns of D, "thereby reducing noise and adding
     robustness". IMPLEMENTATION NOTE: the paper's own Snippet 1 (Appendix
     A.1, p. 15) never materializes D~ explicitly — it feeds the rows of D to
     sklearn KMeans as feature vectors, and because k-means and
     silhouette_samples both use Euclidean distances BETWEEN those row
     vectors, the metric they actually operate on is exactly D~. This module
     does the same, for the same reason: text and code agree once that
     observation is made.

  3. Cluster quality (Section 8.1, p. 10): with S_i the Rousseeuw (1987)
     silhouette score of trial i,
         S_i = (b_i - a_i) / max(a_i, b_i)
     the quality of a clustering is its silhouette t-value
         q = E[{S_i}] / sqrt(V[{S_i}])
     Variance here is the population variance (ddof=0): the paper's snippets
     call .std() on numpy arrays, whose default is ddof=0, and this module
     matches that convention exactly rather than silently upgrading to ddof=1.

  4. Base clustering (Section 8.1, p. 10 and Snippet 1, p. 15): a double
     loop — outer over n_init random initializations, inner over candidate
     cluster counts k = 2, ..., N-1 ("we try different k=2,...,N-1", p. 10) —
     fitting KMeans(n_clusters=k, n_init=1) each time and keeping the
     clustering with the highest q.

  5. Top-level recursion (Section 8.1, pp. 10-11 and Snippet 2, p. 16):
     compute the per-cluster quality t-stat
         q_k = mean(silh members of k) / std(silh members of k)
     take the average q-bar over clusters, and mark for redo the clusters
     with q_k < q-bar. If the number of redo clusters K1 <= 2, return the
     base clustering unchanged ("If the number of clusters to rerun is
     K1<=2, then we return the clustering given by the base algorithm",
     pp. 10-11). Otherwise recursively re-cluster the union of the redo
     clusters' members, splice the result onto the accepted clusters,
     recompute silhouettes on the FULL distance matrix under the spliced
     labels, and accept the splice only if the mean per-cluster t-stat of
     the spliced clustering exceeds the mean t-stat that THE REDO CLUSTERS
     had under the old clustering (Snippet 2: `if newTstatMean<=meanRedoTstat:
     return corr1,clstrs,silh`). NOTE ON VARIANTS, CORRECTED by adversarial
     verification: the emoen/Machine-Learning-for-Asset-Managers GitHub
     transcription of the book version (MLAM snippet 4.2 — still not
     checked against the book itself) was initially reported here as
     stopping at K1<=1. That was wrong: emoen's EXECUTABLE code stops at
     K1<=2, identical to the paper — `<=1` appears only in a stale
     docstring comment and a print string in that repo, not in the code
     path that actually runs, and the original build read the comment
     instead of tracing execution. The verified real differences from the
     paper, confirmed by running emoen's code directly: (a) it compares the
     spliced clustering's quality against the mean t-stat of ALL old
     clusters, not just the redone ones (the one part of the original note
     that WAS correct); (b) it caps the candidate cluster count at
     floor(N/2) rather than the paper's N-1; (c) it uses KMeans(n_init=10)
     inside the k-loop rather than the paper's n_init=1 (relying on the
     OUTER n_init loop for restarts, as this module and the paper both do).
     This module follows the PAPER on all three points, which is the
     version this project cites throughout.

  6. E[K] (Section 8.2, p. 11): the number of clusters returned by the
     procedure above IS the estimate of the number of effectively
     uncorrelated trials, E[K], to be used in the False Strategy theorem
     (Section 6, p. 8) in place of the raw trial count N.

GUARDS THIS MODULE ADDS THAT THE PAPER DOES NOT SPECIFY (each flagged
inline as well — none of these alters the algorithm on well-posed inputs,
they only keep degenerate inputs from raising or poisoning a mean with NaN):

  - A singleton cluster's silhouette t-stat is 0/0. sklearn (following
    Rousseeuw's convention) defines a lone point's silhouette as 0, so a
    singleton cluster is assigned quality 0.0 here. UNVERIFIED AGAINST THE
    PAPER: the paper never says what to do with singleton clusters; 0.0 is
    this module's choice, chosen so that a singleton (which is evidence of
    a poorly-separated clustering, not a good one) sorts below any cluster
    whose members cohere.
  - A cluster whose members' silhouettes are all identical has std = 0 and
    a t-stat of +/-inf under the paper's formula; it is kept as +inf when
    the mean is positive (identically-well-clustered members) and mapped to
    0.0 when the mean is <= 0. UNVERIFIED AGAINST THE PAPER for the same
    reason.
  - Correlations are clipped into [-1, 1] before the distance transform
    (numerical guard; the paper's own cov2corr in Snippet 3 clips the same
    way when GENERATING matrices, but Snippet 1 does not re-clip on input).
  - NaN correlations are filled with 0 — this one IS the paper's own code
    (`corr0.fillna(0)`, Snippet 1).
  - KMeans fits that raise (duplicate points making k infeasible, etc.) are
    skipped rather than allowed to abort the whole search.

STRUCTURAL LIMITATIONS — honest, by construction, and worth reading before
trusting any output of this module:

  - E[K] >= 2 ALWAYS. The candidate range starts at k=2, so even a
    population of perfectly identical trials comes back as 2 clusters, never
    1. The paper never addresses the K=1 case. Consequently this diagnostic
    can only ever REDUCE an n_trials of 3+ toward 2, and says nothing
    meaningful about populations that are genuinely one trial repeated.
  - E[K] <= N-1 ALWAYS, for the mirror-image reason. For a population of
    genuinely independent trials, the honest count is N; ONC can return at
    most N-1 and in practice (measured in this module's test suite) returns
    far less on unstructured noise, because k-means will happily carve
    featureless noise into a few large blobs. UNDER-counting trials LOWERS
    the expected-max-Sharpe hurdle, which is ANTI-conservative for the DSR.
    Therefore: treat this module's E[K] as a lower bound on search breadth,
    to be read ALONGSIDE the raw pre-registered count, never as an
    automatic replacement for it. That asymmetry is the reason this module
    ships unwired.
  - The paper's own Monte Carlo validation (Section 9.2, p. 13) covers
    N in {20, 40, 80, 160} with K from 3 up to N/2 and block sizes >= 2.
    Behaviour outside that envelope (K > N/2, i.e. mostly-singleton
    populations) is NOT validated by the paper and is measured
    independently in this module's tests.

WHAT THIS MODULE DELIBERATELY DOES NOT IMPLEMENT: Section 8.2's estimator of
E[V[{SR_k}]] (minimum-variance intra-cluster aggregation into K cluster-level
return streams, then the variance of their annualized Sharpes). That is the
second meta-research variable of the paper and the natural next step, but it
is a separate estimator with its own failure modes, and bolting it on without
its own ground-truth validation would repeat exactly the mistake this
project's verification rule exists to prevent.

ONE COMPANION FUNCTION THAT IS NOT FROM THE PAPER: variance_effective_n().
Added 2026-09-04 when this module was first applied to real registered
strategies (data/research_runs/run_effective_n_clustering.py) and the
headline population — the live forward-validation book — turned out to be
FOUR to FIVE specs, i.e. below MIN_TRIALS_FOR_CLUSTERING and inside the
range where the structural [2, N-1] bound makes ONC's answer uninformative
by construction. variance_effective_n is two lines of elementary algebra
(derived in full in its own docstring, so it needs no citation), is defined
at every N >= 2, is deterministic, and answers the narrower variance-
diversification question rather than ONC's partition question. It is
labelled as not-the-paper's at both call sites and in its docstring; it does
not feed the False Strategy theorem and must not be substituted for E[K].

PURE FUNCTIONS, UNWIRED. Nothing here reads a database, mutates an input, or
is imported by any live pipeline; deflated_sharpe.py is untouched. Diagnostic
output for human review only, matching empirical_bayes_shrinkage.py.

References:
  Lopez de Prado & Lewis (2019), "Detection of false investment strategies
    using unsupervised learning methods", Quantitative Finance 19(9),
    1555-1565. SSRN 3167017. -- the algorithm, Sections 8.1, 9.1, Snippets 1-3.
  Lopez de Prado (2020), "Machine Learning for Asset Managers", Cambridge
    Elements in Quantitative Finance, Section 4.4. -- book variant (secondary,
    seen only via the emoen GitHub transcription; divergences flagged above).
  Rousseeuw (1987), "Silhouettes: a Graphical Aid to the Interpretation and
    Validation of Cluster Analysis", J. Comput. Appl. Math. 20, 53-65.
    -- the silhouette score.
  Bailey, Borwein, Lopez de Prado & Zhu (2014), "Pseudo-mathematics and
    financial charlatanism", Notices of the AMS 61(5), 458-471. -- the False
    Strategy theorem that consumes E[K].
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_samples

from app.services.research_lab.deflated_sharpe import derive_returns_from_equity_curve

# Below this many trials, "how many effectively uncorrelated trials" is not a
# question clustering can answer: the base search space is k = 2..N-1, so at
# N = 4 the algorithm chooses between exactly two candidate counts, and the
# silhouette t-stat that drives the choice is computed from a handful of
# points. Set to 10 to match MIN_TRIALS_FOR_SHRINKAGE in
# empirical_bayes_shrinkage.py — the same "population-level estimate needs a
# real population" argument applies. Measured behaviour below the floor is
# reported (floor_met=False) rather than refused, so a human can still look.
MIN_TRIALS_FOR_CLUSTERING = 10

# Pairwise return correlations computed from fewer overlapping observations
# than this are dropped (the pair's correlation is set to NaN -> 0 via the
# paper's own fillna(0) convention) rather than trusted. 60 overlapping
# per-period observations is the same order as the smallest samples this
# project's other diagnostics accept.
MIN_OVERLAP_FOR_CORRELATION = 60

_DEFAULT_N_INIT = 10  # the paper's Snippet 1 default (n_init=10)

# A silhouette std at or below this is treated as exactly zero (the
# degenerate-cluster case), not compared with ==0.0 -- see
# _silhouette_tstat's docstring for the real recursion bug this tolerance
# closes. 1e-9 sits many orders of magnitude above float64 accumulation
# noise on inputs this module's tests actually exercise (~1e-16) and many
# orders below any silhouette spread that should be read as real variation.
_SILHOUETTE_STD_ZERO_TOLERANCE = 1e-9

# cluster_kmeans_top recurses on the union of "redo" clusters' members. A
# well-formed recursion strictly shrinks that set each call (the paper's
# own worked example does). If it doesn't -- the redo set is the ENTIRE
# input again -- the recursion cannot converge and will exhaust Python's
# stack. Found by adversarial verification: exactly this happened on
# perfectly symmetric matrices even after the tolerance fix above closes
# the float-precision root cause; this is a second, independent guard
# against the same failure class (no-progress recursion), not a
# duplicate of it.
_MAX_ONC_RECURSION_DEPTH = 20

# Below this MEAN silhouette, _build_interpretation withholds its confident
# "N genuinely distinct bets" sentence (the raw E[K] number is still
# reported regardless). Kaufman & Rousseeuw's own published interpretation
# scale for the silhouette coefficient (Kaufman & Rousseeuw, 1990, "Finding
# Groups in Data: An Introduction to Cluster Analysis", as reproduced on
# Wikipedia's "Silhouette (clustering)" article, verified via live web
# search during this fix rather than recalled from memory): 0.71-1.00
# strong structure, 0.51-0.70 reasonable structure, 0.26-0.50 weak/possibly
# artificial, <=0.25 no substantial structure found. This module uses the
# bottom breakpoint: below it, a cluster count is not evidence of anything
# beyond what pure noise would also produce.
_MIN_SILHOUETTE_FOR_INTERPRETING_CLUSTERS = 0.25


@dataclass
class ClusterInfo:
    cluster_id: int
    members: list[str]
    # mean/std (ddof=0) of the members' silhouette scores — the per-cluster
    # quality t-stat q_k of Section 8.1 / Snippet 2.
    quality_tstat: float


@dataclass
class ClusteringResult:
    """Output of one ONC clustering pass (base or top-level)."""

    labels: dict[str, int]  # trial name -> cluster id
    clusters: list[ClusterInfo]
    silhouette: dict[str, float]  # trial name -> silhouette score S_i
    # q = mean(S_i)/std(S_i) over ALL trials (Section 8.1, p. 10) for the
    # winning clustering.
    overall_quality: float

    @property
    def n_clusters(self) -> int:
        return len(self.clusters)


@dataclass
class EffectiveNResult:
    """E[K] alongside the raw count it deflates — the side-by-side IS the
    deliverable; neither number replaces the other."""

    n_trials_raw: int  # trials handed to this function
    n_trials_clustered: int  # trials that survived data-quality drops
    n_effective: int  # E[K]: the ONC cluster count
    effective_over_raw: float  # n_effective / n_trials_clustered
    overall_quality: float
    mean_silhouette: float
    clusters: list[ClusterInfo]
    dropped_trials: dict[str, str] = field(default_factory=dict)  # name -> reason
    floor_met: bool = True
    interpretation: str = ""


def correlation_to_distance(corr: pd.DataFrame) -> pd.DataFrame:
    """D_ij = sqrt((1 - rho_ij)/2) — Lopez de Prado & Lewis (2019), Section
    8.1, p. 9. rho=1 -> 0, rho=0 -> sqrt(1/2), rho=-1 -> 1.

    NaNs are filled with 0 first (the paper's Snippet 1: corr0.fillna(0)),
    and correlations are clipped to [-1, 1] as a numerical guard (flagged in
    the module docstring — the clip is this module's addition)."""
    clipped = corr.fillna(0).clip(-1.0, 1.0)
    return ((1.0 - clipped) / 2.0) ** 0.5


def _silhouette_tstat(silh_values: np.ndarray) -> float:
    """q_k = mean/std (ddof=0) of a cluster's silhouette scores.

    Guards for the two degenerate cases the paper does not specify (see
    module docstring): std ~= 0 yields +inf for a positive mean
    (identically-well-clustered) and 0.0 otherwise (which covers the
    singleton cluster, whose sklearn silhouette is exactly 0).

    BUG FIX (found by adversarial verification, not in the original build):
    the guard used to compare std == 0.0 exactly. On a perfectly symmetric
    correlation matrix (e.g. exact block structure with identical
    within/across-block correlations), every member of a cluster gets a
    numerically-near-identical but not bit-identical silhouette, so std
    lands around 1e-16 -- finite floating-point noise, not zero. The exact
    guard let that through, producing a t-stat around 1/1e-16, i.e. a huge
    but FINITE number instead of the intended +inf, which then fed into
    cluster_kmeans_top's redo-selection logic in a way that never converged
    -- traced to an unbounded recursion (RecursionError after minutes of
    CPU burn) on inputs like a 30x30 exact block matrix. Comparing against
    a tolerance rather than exact equality closes this -- the tolerance is
    set far above float64 accumulation noise (~1e-12 for a handful of
    subtractions) and far below any silhouette spread that should be read
    as real variation."""
    mean = float(np.mean(silh_values))
    std = float(np.std(silh_values))  # ddof=0, matching the paper's snippets
    if std <= _SILHOUETTE_STD_ZERO_TOLERANCE:
        return float("inf") if mean > 0 else 0.0
    return mean / std


def cluster_kmeans_base(
    corr: pd.DataFrame,
    *,
    max_num_clusters: int | None = None,
    n_init: int = _DEFAULT_N_INIT,
    random_state: int | None = None,
) -> ClusteringResult:
    """The paper's Snippet 1 (Appendix A.1, p. 15): double loop over n_init
    initializations x k = 2..max_num_clusters, KMeans(n_clusters=k, n_init=1)
    per attempt, keep the clustering with the highest silhouette t-value q.

    max_num_clusters defaults to N-1, the paper's own range ("we try
    different k=2,...,N-1", Section 8.1, p. 10; Snippet 2 passes
    corr0.shape[1]-1 explicitly).

    The KMeans feature matrix is D itself: each trial's row of distances is
    its feature vector, so the Euclidean metric k-means minimizes over is the
    paper's distance-of-distances D~ (see module docstring, point 2).

    random_state is this module's addition for reproducibility — the paper's
    snippet leaves sklearn unseeded. Passing None reproduces the paper's
    unseeded behaviour."""
    n = corr.shape[0]
    if n < 3:
        raise ValueError(f"ONC needs at least 3 trials to choose among k>=2 clusterings, got {n}")
    if max_num_clusters is None:
        max_num_clusters = n - 1
    max_num_clusters = min(max_num_clusters, n - 1)

    dist = correlation_to_distance(corr)
    dist_values = dist.to_numpy()
    rng = np.random.default_rng(random_state)

    best_silh: np.ndarray | None = None
    best_labels: np.ndarray | None = None
    best_q = float("-inf")

    for _ in range(n_init):
        for k in range(2, max_num_clusters + 1):
            # n_init=1 here because the OUTER loop supplies the restarts —
            # exactly Snippet 1's KMeans(n_clusters=i, n_init=1).
            kmeans = KMeans(
                n_clusters=k,
                n_init=1,
                random_state=int(rng.integers(0, 2**32 - 1)),
            )
            try:
                labels = kmeans.fit_predict(dist_values)
            except ValueError:
                continue  # infeasible k for degenerate inputs — guard, not paper
            if len(np.unique(labels)) < 2:
                continue  # silhouette undefined — guard, not paper
            silh = silhouette_samples(dist_values, labels)
            std = silh.std()  # ddof=0
            if std <= _SILHOUETTE_STD_ZERO_TOLERANCE:
                continue  # q undefined (~0-variance silhouettes) — guard, not paper; see
                # _SILHOUETTE_STD_ZERO_TOLERANCE's module-level comment for why this is a
                # tolerance now, not exact equality
            q = silh.mean() / std
            # Snippet 1's `if np.isnan(stat[1]) or stat[0]>stat[1]`:
            # keep the first clustering seen, then any strict improvement.
            if q > best_q:
                best_q = q
                best_silh = silh
                best_labels = labels

    if best_labels is None:
        raise ValueError(
            "ONC base clustering found no valid clustering — every KMeans fit was degenerate"
        )

    names = list(corr.columns)
    return _assemble_clustering(names, best_labels, best_silh, float(best_q))


def _assemble_clustering(
    names: list[str], labels: np.ndarray, silh: np.ndarray, overall_q: float
) -> ClusteringResult:
    """Relabel clusters 0..K-1 in deterministic (first-member) order and
    package per-cluster quality t-stats."""
    silhouette = {name: float(s) for name, s in zip(names, silh)}
    clusters: list[ClusterInfo] = []
    label_map: dict[int, int] = {}
    for raw_label in labels:
        if int(raw_label) not in label_map:
            label_map[int(raw_label)] = len(label_map)
    members_by_cluster: dict[int, list[str]] = {}
    for name, raw_label in zip(names, labels):
        members_by_cluster.setdefault(label_map[int(raw_label)], []).append(name)
    for cid in sorted(members_by_cluster):
        members = members_by_cluster[cid]
        clusters.append(
            ClusterInfo(
                cluster_id=cid,
                members=members,
                quality_tstat=_silhouette_tstat(np.array([silhouette[m] for m in members])),
            )
        )
    label_dict = {name: label_map[int(raw)] for name, raw in zip(names, labels)}
    return ClusteringResult(
        labels=label_dict, clusters=clusters, silhouette=silhouette, overall_quality=overall_q
    )


def _spliced_clustering(
    corr: pd.DataFrame,
    accepted: list[ClusterInfo],
    redone: list[ClusterInfo],
) -> ClusteringResult:
    """The paper's makeNewOutputs (Snippet 2, pp. 15-16): concatenate the
    accepted clusters with the re-clustered ones, then recompute every
    trial's silhouette on the FULL distance matrix under the spliced labels
    — not on any sub-matrix — so the spliced clustering's quality is
    measured on the same footing as the base clustering's."""
    dist = correlation_to_distance(corr).to_numpy()
    names = list(corr.columns)
    name_to_pos = {name: i for i, name in enumerate(names)}
    labels = np.zeros(len(names), dtype=int)
    for new_id, cluster in enumerate([*accepted, *redone]):
        for member in cluster.members:
            labels[name_to_pos[member]] = new_id
    silh = silhouette_samples(dist, labels)
    std = silh.std()  # ddof=0
    overall_q = float(silh.mean() / std) if std > 0 else 0.0
    return _assemble_clustering(names, labels, silh, overall_q)


def cluster_kmeans_top(
    corr: pd.DataFrame,
    *,
    n_init: int = _DEFAULT_N_INIT,
    random_state: int | None = None,
    _depth: int = 0,
) -> ClusteringResult:
    """The paper's Snippet 2 (Appendix A.2, pp. 15-16): base-cluster, find
    the clusters whose quality t-stat sits below the cross-cluster average,
    and — if more than two such clusters exist — recursively re-cluster
    their members, keeping the splice only if it improves on the redo
    clusters' own average quality.

    Faithful to the PAPER's acceptance rule: the spliced clustering's mean
    per-cluster t-stat is compared against meanRedoTstat, the mean t-stat
    that the redo clusters had under the OLD clustering (Snippet 2's
    `if newTstatMean<=meanRedoTstat`). See the module docstring for how the
    book variant differs and why the paper version is used here.

    _depth is an internal recursion counter, not a public parameter — see
    _MAX_ONC_RECURSION_DEPTH's module-level comment for why it exists."""
    base = cluster_kmeans_base(
        corr, max_num_clusters=corr.shape[1] - 1, n_init=n_init, random_state=random_state
    )

    tstats = {c.cluster_id: c.quality_tstat for c in base.clusters}
    # Snippet 2: tStatMean=np.mean(clusterTstats.values()). With the +inf
    # guard value for a zero-variance cluster this mean is +inf, no cluster
    # sits below it... except that every FINITE cluster then gets redone,
    # which is the natural reading: only the perfect clusters are safe.
    tstat_mean = float(np.mean(list(tstats.values())))
    redo_ids = [cid for cid, t in tstats.items() if t < tstat_mean]

    # "If the number of clusters to rerun is K1<=2, then we return the
    # clustering given by the base algorithm" — Section 8.1, pp. 10-11.
    if len(redo_ids) <= 2:
        return base

    redo_members = [m for c in base.clusters if c.cluster_id in redo_ids for m in c.members]
    accepted = [c for c in base.clusters if c.cluster_id not in redo_ids]
    mean_redo_tstat = float(np.mean([tstats[cid] for cid in redo_ids]))

    # SAFETY GUARD (found by adversarial verification): a well-formed
    # recursion strictly shrinks redo_members below len(corr) each call. On
    # a perfectly symmetric input, near-identical (not bit-identical)
    # silhouettes could in principle still put every cluster back in the
    # redo set even after the tolerance fix in _silhouette_tstat, which
    # would recurse on the SAME full input forever. Independent of the
    # tolerance fix's own effectiveness, refuse to recurse on a
    # non-shrinking or over-deep call and fall back to the base clustering
    # -- a real answer bounded below optimal, never a stack exhaustion.
    if len(redo_members) >= len(corr) or _depth >= _MAX_ONC_RECURSION_DEPTH:
        return base

    sub = cluster_kmeans_top(
        corr.loc[redo_members, redo_members],
        n_init=n_init,
        random_state=random_state,
        _depth=_depth + 1,
    )

    spliced = _spliced_clustering(corr, accepted, sub.clusters)
    new_tstat_mean = float(np.mean([c.quality_tstat for c in spliced.clusters]))

    # Snippet 2's acceptance rule, verbatim in spirit:
    #   if newTstatMean <= meanRedoTstat: return the base clustering
    if new_tstat_mean <= mean_redo_tstat:
        return base
    return spliced


def _build_interpretation(
    n_raw: int, n_clustered: int, n_effective: int, floor_met: bool, mean_silh: float
) -> str:
    if not floor_met:
        return (
            f"Only {n_clustered} clusterable trial(s) (need >={MIN_TRIALS_FOR_CLUSTERING}) — too few "
            "for the cluster count to mean anything. The ONC search space at this size is a handful of "
            "candidate partitions judged by silhouette statistics computed from single-digit samples. "
            "The raw trial count remains the only honest multiplicity number for this population."
        )
    parts = [
        (
            f"Of {n_raw} recorded trials ({n_clustered} clusterable), ONC finds {n_effective} effectively "
            f"uncorrelated cluster(s) — an effective-to-raw ratio of {n_effective / max(n_clustered, 1):.2f}. "
        )
    ]
    # BUG FIX (found by adversarial verification, not in the original build):
    # this sentence used to fire whenever n_effective < n_clustered, with NO
    # check on whether the clustering itself was trustworthy. On ou_pairs_v1
    # (median pairwise trial-return correlation 0.000 — i.e. no real
    # structure), it asserted "explored roughly 2 genuinely distinct bets"
    # anyway, because k-means will always carve unstructured noise into SOME
    # small number of blobs (see the module docstring's "E[K] <= N-1 always"
    # structural limitation) — a confident claim the data does not support,
    # in the exact spirit of the false-positive this project's whole
    # methodology exists to prevent. Gated on Kaufman & Rousseeuw's own
    # published silhouette interpretation scale (as reproduced on
    # Wikipedia's "Silhouette (clustering)" article, itself citing Kaufman &
    # Rousseeuw 1990, "Finding Groups in Data"): <=0.25 = "no substantial
    # structure found". Below that bar this function no longer asserts a
    # bet count at all — the raw n_effective number is still reported
    # above and in the structured result either way, only the confident
    # PROSE is withheld.
    if n_effective < n_clustered and mean_silh > _MIN_SILHOUETTE_FOR_INTERPRETING_CLUSTERS:
        parts.append(
            f"Read this as: the {n_clustered} trials explored roughly {n_effective} genuinely distinct "
            "bets; the remainder are correlated variants re-testing the same underlying pattern. "
        )
    elif n_effective < n_clustered:
        parts.append(
            f"Mean silhouette {mean_silh:.3f} is at or below {_MIN_SILHOUETTE_FOR_INTERPRETING_CLUSTERS} "
            "(Kaufman & Rousseeuw's own \"no substantial structure found\" threshold), so despite "
            f"E[K]={n_effective} being less than {n_clustered}, this is NOT read as evidence of "
            f"{n_effective} genuinely distinct bets — it is k-means carving weakly- or unstructured "
            "data into some small number of blobs, the documented under-counting failure mode. "
            "Treat the raw trial count as the only honest multiplicity number for this population. "
        )
    parts.append(
        "CAVEATS (structural, see module docstring): E[K] is bounded to [2, N-1] by construction, "
        "k-means under-counts genuinely independent trials, and under-counting LOWERS the "
        "expected-max-Sharpe hurdle — so treat E[K] as a lower bound on search breadth to read "
        f"alongside the raw count of {n_raw}, not as a replacement for it. "
        f"Mean silhouette {mean_silh:.3f} (near 0 = weak cluster structure, near 1 = strong)."
    )
    return "".join(parts)


def variance_effective_n(corr: pd.DataFrame) -> float:
    """N_eff = N^2 / (1'C1) — the number of MUTUALLY UNCORRELATED unit-variance
    series whose equal-weighted average would have the same variance as an
    equal-weighted average of these N.

    NOT FROM LOPEZ DE PRADO & LEWIS. This is not part of ONC and is not
    claimed to be; it is two lines of elementary algebra, reproduced here in
    full so no citation is needed and nothing has to be taken on trust:

        P    = (1/N) * sum_i X_i          equal-weighted, X_i unit variance
        V[P] = (1/N^2) * sum_i sum_j rho_ij = (1/N^2) * 1'C1
        if the N series were mutually uncorrelated, 1'C1 = N, so V[P] = 1/N
        define N_eff by V[P] = 1/N_eff   =>   N_eff = N^2 / (1'C1)

    Equivalently N_eff = N / (1 + (N-1) * rho_bar) with rho_bar the mean
    off-diagonal correlation, so rho_bar = 0 gives N_eff = N and rho_bar = 1
    gives N_eff = 1.

    WHY THIS EXISTS ALONGSIDE ONC, rather than instead of it. ONC's candidate
    range starts at k=2 and its own MIN_TRIALS_FOR_CLUSTERING floor is 10, so
    on a small population — for instance a live registered book of four or
    five strategies — it cannot say anything: the cluster count is bounded
    into [2, N-1] and chosen by silhouette statistics computed from
    single-digit samples. This function is defined at every N >= 2, is
    deterministic (no k-means restarts), and degrades gracefully. It answers
    a genuinely different and narrower question, and the difference matters:

      * ONC counts GROUPS of trials that behave alike — a partition.
      * This counts VARIANCE diversification — how much an equal-weighted
        combination's risk falls relative to N independent draws.

    WHAT IT IS NOT, stated so the number is never over-read:
      * It is a RISK statistic, not a breadth statistic. It says nothing
        about whether the N forecasts carry independent INFORMATION, which is
        what the fundamental-law/breadth argument actually needs. Two
        strategies can be uncorrelated in realized returns and still be
        driven by one underlying idea.
      * It assumes equal weights. A different weighting has a different
        effective N.
      * A sample correlation matrix built pairwise (pandas .corr with
        min_periods) need not be positive semi-definite, so 1'C1 can in
        principle come out at or below zero on badly-overlapping data; that
        case returns NaN rather than a fabricated number.
      * With genuinely negative average correlation the formula returns MORE
        than N, which is correct in the variance sense (hedging diversifies
        more than independence does) but must not be read as "more than N
        independent bets".

    NaNs are filled with 0 before the sum, matching correlation_to_distance's
    convention (itself the paper's Snippet 1 fillna(0)), so an unmeasurable
    pair contributes as "unknown = uncorrelated"."""
    n = corr.shape[0]
    if n == 0:
        return float("nan")
    total = float(np.nansum(corr.fillna(0.0).to_numpy()))
    if not np.isfinite(total) or total <= 0.0:
        return float("nan")
    return (n * n) / total


def estimate_effective_n_from_correlation(
    corr: pd.DataFrame,
    *,
    n_init: int = _DEFAULT_N_INIT,
    random_state: int | None = None,
    dropped_trials: dict[str, str] | None = None,
    n_trials_raw: int | None = None,
) -> EffectiveNResult:
    """E[K] for an already-computed trial-correlation matrix.

    dropped_trials / n_trials_raw let a caller that pre-filtered the
    population (estimate_effective_n_from_returns does) carry the honest
    raw count through to the report."""
    dropped = dict(dropped_trials or {})
    n_clustered = corr.shape[0]
    n_raw = n_trials_raw if n_trials_raw is not None else n_clustered + len(dropped)
    floor_met = n_clustered >= MIN_TRIALS_FOR_CLUSTERING

    if n_clustered < 3:
        # Below the algorithm's mechanical minimum there is nothing to run.
        return EffectiveNResult(
            n_trials_raw=n_raw,
            n_trials_clustered=n_clustered,
            n_effective=n_clustered,
            effective_over_raw=1.0 if n_clustered else float("nan"),
            overall_quality=float("nan"),
            mean_silhouette=float("nan"),
            clusters=[],
            dropped_trials=dropped,
            floor_met=False,
            interpretation=_build_interpretation(n_raw, n_clustered, n_clustered, False, float("nan")),
        )

    clustering = cluster_kmeans_top(corr, n_init=n_init, random_state=random_state)
    mean_silh = float(np.mean(list(clustering.silhouette.values())))
    return EffectiveNResult(
        n_trials_raw=n_raw,
        n_trials_clustered=n_clustered,
        n_effective=clustering.n_clusters,
        effective_over_raw=clustering.n_clusters / n_clustered,
        overall_quality=clustering.overall_quality,
        mean_silhouette=mean_silh,
        clusters=clustering.clusters,
        dropped_trials=dropped,
        floor_met=floor_met,
        interpretation=_build_interpretation(
            n_raw, n_clustered, clustering.n_clusters, floor_met, mean_silh
        ),
    )


def estimate_effective_n_from_returns(
    returns_by_trial: pd.DataFrame,
    *,
    n_init: int = _DEFAULT_N_INIT,
    random_state: int | None = None,
    min_overlap: int = MIN_OVERLAP_FOR_CORRELATION,
) -> EffectiveNResult:
    """E[K] from a T x N matrix of per-period trial returns (columns =
    trials, index = period labels/dates; NaN where a trial has no
    observation).

    Data-quality drops applied BEFORE clustering, each recorded with its
    reason in dropped_trials rather than silently: a trial with fewer than
    min_overlap finite observations, or with zero return variance (a flat
    equity curve cannot be correlated with anything), contributes no usable
    correlation and would otherwise enter the matrix as the paper's
    fillna(0) — i.e. as a fabricated "uncorrelated" trial inflating E[K].

    The correlation matrix is computed pairwise over each pair's overlapping
    observations (pandas .corr(min_periods=min_overlap)); pairs with less
    overlap than min_overlap become NaN and take the paper's fillna(0)
    treatment, which is the conservative "unknown = uncorrelated" reading."""
    dropped: dict[str, str] = {}
    usable_cols: list[str] = []
    for col in returns_by_trial.columns:
        series = returns_by_trial[col].dropna()
        if len(series) < min_overlap:
            dropped[str(col)] = f"only {len(series)} return observations (need >={min_overlap})"
            continue
        if float(series.std(ddof=0)) == 0.0:
            dropped[str(col)] = "zero return variance (flat equity curve) — correlation undefined"
            continue
        usable_cols.append(col)

    corr = returns_by_trial[usable_cols].corr(min_periods=min_overlap)
    return estimate_effective_n_from_correlation(
        corr,
        n_init=n_init,
        random_state=random_state,
        dropped_trials=dropped,
        n_trials_raw=len(returns_by_trial.columns),
    )


@dataclass
class PooledEffectiveNResult:
    """E[K] over an ARBITRARY trial population, measured across a seed sweep.

    The sweep is the point. ONC is a stochastic k-means search (Section 8.1's
    outer loop over n_init random initializations), so one seed's cluster
    count is one draw from a distribution, not a measurement. Reporting a
    single seed's E[K] as if it were exact is the same overclaimed precision
    this module's own interpretation-gating exists to prevent, one level up.

    `mode` is the headline: the most frequently returned cluster count across
    the sweep, ties broken toward the LARGER count. Larger is the conservative
    tie-break for a multiplicity denominator — a bigger N raises the
    expected-max-Sharpe hurdle — and it is chosen here rather than left to
    dict ordering so the tie-break is a stated decision instead of an
    accident of iteration order."""

    headline: EffectiveNResult  # the result at headline_seed
    counts: dict[int, int]  # cluster count -> how many seeds produced it
    mode: int
    minimum: int
    maximum: int
    silhouette_range: tuple[float, float] | None
    seeds: list[int]
    n_trials_raw: int
    n_trials_clustered: int

    @property
    def is_point_estimate(self) -> bool:
        """True when every seed agreed. When False, the range — not the mode
        alone — is the honest statement of what was measured."""
        return self.minimum == self.maximum


def pooled_effective_n(
    returns_by_trial: pd.DataFrame,
    *,
    seeds: Sequence[int],
    headline_seed: int | None = None,
    n_init: int = _DEFAULT_N_INIT,
    min_overlap: int = MIN_OVERLAP_FOR_CORRELATION,
) -> PooledEffectiveNResult:
    """Run the ONC estimator over an arbitrary pooled trial population, across
    a seed sweep, and return the distribution of cluster counts rather than one
    draw from it.

    GENERALIZED, NOT REDESIGNED. Every statistical choice here is the one
    already in this module and already applied by
    data/research_runs/run_effective_n_clustering.py: the same
    correlation-to-distance transform (Section 8.1), the same
    cluster_kmeans_top recursion, the same MIN_OVERLAP_FOR_CORRELATION
    pairwise-overlap rule, the same data-quality drops. What changes is the
    INPUT SCOPE. That script hardcoded three populations, and its headline one
    (POP-B) was "every spec whose persisted DSR clears the 0.50 floor" — a set
    selected ON THE OUTCOME. A search-breadth denominator conditioned on
    success counts only the trials that won, which is precisely backwards for
    a multiple-comparisons correction: the trials that were run and FAILED are
    the ones the correction exists to price in. This function takes whatever
    population the caller assembled and imposes no floor of its own.

    The seed-sweep logic itself is lifted from that script's private
    _seed_sweep so both callers share one implementation instead of two that
    can drift.

    `returns_by_trial` is the T x N matrix estimate_effective_n_from_returns
    consumes: columns = trials, index = dates, NaN where a trial has no
    observation on a date.

    Raises ValueError on an empty seed list rather than inventing one — a
    caller that forgot the sweep should be told, not silently handed a single
    unseeded draw."""
    seeds = list(seeds)
    if not seeds:
        raise ValueError(
            "pooled_effective_n needs at least one seed. ONC is a stochastic search; the seed "
            "sweep is what turns its answer from one draw into a measured distribution."
        )
    if headline_seed is None:
        headline_seed = seeds[0]

    # The correlation matrix and the data-quality drops are computed ONCE and
    # reused across every seed: they do not depend on the k-means seed, and
    # recomputing a several-hundred-column pairwise correlation per seed would
    # dominate the runtime for no change in the answer.
    dropped: dict[str, str] = {}
    usable_cols: list[str] = []
    for col in returns_by_trial.columns:
        series = returns_by_trial[col].dropna()
        if len(series) < min_overlap:
            dropped[str(col)] = f"only {len(series)} return observations (need >={min_overlap})"
            continue
        if float(series.std(ddof=0)) == 0.0:
            dropped[str(col)] = "zero return variance (flat equity curve) — correlation undefined"
            continue
        usable_cols.append(col)
    corr = returns_by_trial[usable_cols].corr(min_periods=min_overlap)
    n_raw = len(returns_by_trial.columns)

    counts: dict[int, int] = {}
    silhouettes: list[float] = []
    headline: EffectiveNResult | None = None
    for seed in seeds:
        res = estimate_effective_n_from_correlation(
            corr,
            n_init=n_init,
            random_state=seed,
            dropped_trials=dropped,
            n_trials_raw=n_raw,
        )
        counts[res.n_effective] = counts.get(res.n_effective, 0) + 1
        if np.isfinite(res.mean_silhouette):
            silhouettes.append(res.mean_silhouette)
        if seed == headline_seed:
            headline = res
    if headline is None:
        headline = estimate_effective_n_from_correlation(
            corr,
            n_init=n_init,
            random_state=headline_seed,
            dropped_trials=dropped,
            n_trials_raw=n_raw,
        )

    # Ties broken toward the LARGER count — see the dataclass docstring.
    top_frequency = max(counts.values())
    mode = max(k for k, v in counts.items() if v == top_frequency)

    return PooledEffectiveNResult(
        headline=headline,
        counts=counts,
        mode=mode,
        minimum=min(counts),
        maximum=max(counts),
        silhouette_range=(min(silhouettes), max(silhouettes)) if silhouettes else None,
        seeds=seeds,
        n_trials_raw=n_raw,
        n_trials_clustered=len(usable_cols),
    )


def trial_returns_from_experiment_run(
    run_id: int,
    strategy_name: str,
    ticker_a: str,
    ticker_b: str,
    results_json: str,
) -> tuple[str, pd.Series] | None:
    """Map one stored ExperimentRun row onto a (trial_name, date-indexed
    per-period return series) pair, for assembly into the T x N matrix
    estimate_effective_n_from_returns() consumes.

    Reuses deflated_sharpe.derive_returns_from_equity_curve for the
    equity->returns math — that function already encodes (and its tests
    verify) the walk-forward engine's prepend-1.0 convention, under which
    the derived return series has exactly one return per stored equity
    point. That length identity is what lets each return be indexed by its
    equity point's own date here; it is asserted rather than assumed.

    Returns None for rows that cannot yield an honest return stream (bad
    JSON, non-"ok" status, missing/misshapen equity curve) — a fabricated
    flat series would enter the correlation matrix as a spurious
    "uncorrelated" trial."""
    try:
        payload = json.loads(results_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        return None
    curve = payload.get("equity_curve")
    if not isinstance(curve, list) or not curve:
        return None
    try:
        dates = [point["date"] for point in curve]
        equity = [float(point["equity"]) for point in curve]
    except (TypeError, KeyError, ValueError):
        return None

    returns = derive_returns_from_equity_curve(equity)
    if len(returns) != len(dates):
        # derive_returns_from_equity_curve guarantees one return per stored
        # equity point; a mismatch means the curve is not what this mapper
        # assumes, and indexing by date would silently misalign every value.
        return None

    pair = ticker_a if ticker_a == ticker_b else f"{ticker_a}/{ticker_b}"
    name = f"{run_id}:{strategy_name}:{pair}"
    series = pd.Series(returns.to_numpy(), index=pd.to_datetime(dates), name=name)
    # Defensive: a duplicated date inside one curve would make the later
    # DataFrame join explode combinatorially.
    series = series[~series.index.duplicated(keep="first")]
    return name, series


def returns_matrix_from_trials(trials: Sequence[tuple[str, pd.Series]]) -> pd.DataFrame:
    """Outer-join date-indexed trial return series into the T x N matrix
    estimate_effective_n_from_returns() consumes. NaN where a trial has no
    observation on a date — handled there, not here."""
    if not trials:
        return pd.DataFrame()
    return pd.DataFrame({name: series for name, series in trials}).sort_index()
