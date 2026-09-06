"""THE DSR DENOMINATOR LADDER, as an explicit POLICY artifact.

WHY THIS MODULE EXISTS AT ALL, AND WHY IT IS NOT global_effective_n.py
=====================================================================
Policy D (registration_scorecard.py) reports every family's DSR at several
n_trials values and reads a two-tier verdict off them. Until 2026-09-06 the
values it used were:

    n_local   the family's own pre-declared grid size
    481       global_effective_n.json's `n_specs_clustered`
    857       global_effective_n.json's `raw_pooled_distinct_trials`

The second and third were never chosen as denominators. They are PROVENANCE
fields on a MEASUREMENT artifact — 481 is "how many specs happened to carry a
usable realized return series when the pooled ONC run was assembled", an
artifact of data availability, and 857 was that run's raw population count on
2026-09-04. registration_scorecard.py read them directly, and in doing so
promoted two incidental bookkeeping numbers into the project's
multiple-testing correction without anyone deciding they should be.

That accidental promotion is the actual defect this module fixes. The ladder
is a POLICY choice informed by several estimators; it is not a by-product of
whichever measurement run happened to be committed last. Keeping it in its own
artifact means:

  * global_effective_n.json stays exactly what it is — the honest record that
    ONC was tried on this project's real data and DEGENERATED (E[K]=2, its own
    structural floor, unanimously across 25 seeds). That record is preserved
    untouched and is still cited below as one input.
  * a change to the ladder is a visible, reviewable edit to a file whose only
    job is the ladder, rather than a silent consequence of re-running a
    clustering script.

WHY ONC DEGENERATED — MEASURED, NOT ASSUMED (2026-09-06)
========================================================
The reason matters, because "the data has no structure" and "the estimator
could not see the structure" call for different replacements. It is the
second, and the evidence is in
data/research_runs/dsr_policy_n_decision_2026-09-06.txt:

  * NOT sparsity. Every one of the 115,440 spec pairs clears
    MIN_OVERLAP_FOR_CORRELATION; the smallest pairwise overlap is 1365
    observations. No correlation cell was ever filled by the paper's
    fillna(0). The matrix ONC clustered was fully populated with real
    correlations.
  * THE STRUCTURE IS THERE. Within-family mean |rho| is 0.4676 against a
    between-family 0.0813 (5.75x). 26.3% of within-family pairs exceed
    |rho|=0.7 versus 0.04% of between-family pairs. The correlation matrix has
    75 eigenvalues above 1 and needs 87 components for 90% of its variance.
  * ONC'S OBJECTIVE PICKED THE WORSE ANSWER. ONC maximizes the silhouette
    t-statistic q = mean(S)/std(S) (Lopez de Prado & Lewis 2019, Section 8.1),
    not the mean silhouette. Scored on this project's own matrix:

        k=2   (what ONC returned)   q=2.5344   mean silhouette 0.2350
        k=28                        q=1.8185   mean silhouette 0.3715
        k=87                        q=2.0153   mean silhouette 0.4422
        k=120                       q=2.0430   mean silhouette 0.4669

    k=2 maximizes q by having a LOW STANDARD DEVIATION of silhouettes, while
    being materially worse on the silhouette itself than partitions at k=28
    through k=200. The "mean silhouette 0.235 <= 0.25, therefore no
    substantial structure" conclusion recorded on 2026-09-04/05 was taken AT
    ONC's k=2 answer; the same data supports partitions scoring up to 0.4669,
    inside Kaufman & Rousseeuw's 0.26-0.50 band.

  * BUT THE FAMILY LABELS ARE NOT THE HIDDEN PARTITION EITHER, and this
    correction matters enough to state plainly because an earlier draft of
    this module got it wrong. Scoring the TRUE family partition (each spec
    labelled by its family_key, k=28) gives q=0.7361 and mean silhouette
    0.1937 -- LOWER than k=2's 0.2350. The 0.3715 figure above is k-means'
    OWN k=28 solution, not the family partition. So the correlation geometry
    carries real structure that does not line up with family boundaries:
    there is sub-family structure (which is why k=120 outscores k=28) and
    some cross-family structure. That is a direct caution against reading a
    family count as an independent-bet count -- see RUNG 2.

So the failure is a known weakness of a ratio objective on a
high-dimensional, near-constant feature space (80.0% of all pairs sit at
D in [0.65, 0.75], i.e. rho ~ 0), not an absence of structure. This module
therefore replaces ONC's answer with estimators that do not depend on
k-means finding a partition, rather than concluding the question is
unanswerable.

DELIBERATELY NOT DONE: "fixing" ONC by swapping its objective to the mean
silhouette. That would be a deviation from the cited paper's algorithm
invented to make the answer come out differently, which is the opposite of
this project's mechanism-fidelity rule. effective_n_clustering.py is left
implementing the paper as written; this module routes around it.

THE FOUR RUNGS
==============
Every rung is a measured quantity with a stated derivation. See the decision
memo for the full arithmetic and the per-family tables.

  RUNG 1  n_local        the family's own pre-declared grid size (9..48).
                         CLAUDE.md's mandated LENIENT tier. Unchanged.

  RUNG 2  N_MECHANISMS   distinct economic mechanisms searched project-wide.
                         Replaces the "30". A ROBUSTNESS TIER, NOT AN
                         ESTIMATE OF INDEPENDENT TRIALS — the distinction is
                         load-bearing and is stated here because this
                         project's own working hypothesis ("count families,
                         ~38, as a defensible middle ground") turned out to be
                         SUPPORTED AS STRUCTURE BUT NOT LICENSED AS A
                         DENOMINATOR:

                           - Supported as structure. Measured within-family
                             mean |rho| 0.4676 against between-family 0.0813
                             (5.75x); 26.3% of within-family pairs exceed
                             |rho|=0.7 versus 0.04% between. Jensen, Kelly &
                             Pedersen (2023, JF 78(5)) find the same shape and
                             calibrate a block structure at 0.55 within-theme
                             / 0.03 across-theme, stating that "the factor
                             research universe should not be viewed as
                             hundreds of distinct factors".
                           - NOT licensed as a denominator. The DSR paper's
                             OWN implied-independent-trials estimator
                             (Appendix A.3, Eq. 9, see RUNG 4) needs an
                             average pairwise correlation of 0.9650 to deflate
                             this project's pool to 37. The measured value is
                             0.0314. Nothing in the literature adopts an
                             economic-mechanism count AS the correction
                             denominator; the closest precedent is Harvey, Liu
                             & Zhu (2016) taking "a haircut to 113 factors"
                             from 316 as a ROBUSTNESS CHECK, which moved their
                             Holm hurdle 3.64 -> 3.29 and which they describe
                             as not materially changing conclusions.
                           - And the family labels do not match the
                             correlation geometry anyway (see the diagnosis
                             above: the true family partition scores WORSE
                             than k=2).

                         It is kept as a rung because CLAUDE.md requires the
                         honest RANGE to be reported and this is the lenient
                         end of that range with a real published precedent.
                         It must never be read as "the" N.

                         NOTE the "30" it replaces was NOT arbitrary, contrary
                         to how it has been described: it is
                         variance_effective_n = 29.90 over the pooled matrix.
                         It is dropped because effective_n_clustering.py's own
                         docstring says that statistic "is a RISK statistic,
                         not a breadth statistic... says nothing about whether
                         the N forecasts carry independent INFORMATION" — i.e.
                         the module that defines it forbids this exact use.

  RUNG 3  N_EFFECTIVE    effective independent TRIALS across the whole pool,
                         from the ANTI-CONSERVATIVE eigenvalue estimators.
                         Replaces 481.
                         Li & Ji (2005) gives 169.0 on the real 481-spec
                         matrix and Galwey (2009) gives 152.0; summing each
                         family's own internal effective count instead gives
                         189.7 / 191.2, bracketing the same answer from a
                         different direction. The measured redundancy ratio is
                         0.3160 (Galwey) to 0.3514 (Li & Ji); the Li & Ji
                         ratio applied to the full raw pool gives 362.
                         LABELLED ANTI-CONSERVATIVE ON PURPOSE: Halle,
                         Djurovic, Andreassen & Langaas (arXiv:1612.04535)
                         show by simulation that "the methods of Li and Ji
                         (2005) and Galwey (2009) do not control the FWER at
                         level alpha = 0.05", while Cheverud (2001) and Gao
                         et al. (2008) are conservative. This rung is
                         therefore a LOWER bound on the honest denominator,
                         which is exactly what makes it useful as an
                         intermediate rung and disqualifying as the top one.

  RUNG 4  N_RAW          every distinct (family_key, trial_id) pair persisted
                         to cross_sectional_trial_results — the most
                         conservative N measured. Replaces 857, the same
                         quantity counted on 2026-09-04 and since grown.
                         THIS RUNG IS NOT MERELY THE "assume nothing is
                         redundant" bound; three independent estimators put
                         the honest answer within 3% of it:

                           DSR Appendix A.3 Eq. (9)  N_hat = 998.6  (96.9%)
                           Cheverud (2001)   ratio to raw          97.0%
                           Nyholt   (2004)   ratio to raw          97.0%

                         Eq. (9) is Bailey & Lopez de Prado's own
                         clustering-free estimator, N_hat = rho_bar +
                         (1-rho_bar)M, and with a measured rho_bar of 0.0314
                         it barely deflates: the pool's pairwise correlation
                         is dominated by the 110,051 BETWEEN-family pairs at
                         mean rho 0.0159, not by the 5,389 within-family pairs
                         at 0.3490. Bailey, Borwein, Lopez de Prado & Zhu
                         (2014) independently note that treating all trials as
                         independent "leads to a quite conservative estimate",
                         which is the correct reading of this rung.

MONOTONICITY is what makes a four-point report sufficient rather than a sample
of a curve, and it is unchanged from Policy D's original argument: DSR =
PSR(SR0(N)), SR0 is strictly increasing in N, PSR is strictly decreasing in
its benchmark, so DSR is strictly decreasing in N and the rungs bracket every
N between them.

WHAT THIS MODULE DOES NOT DO: decide any registration's operational status. It
reports denominators. Nothing here reads or writes the registration table, and
no value here is part of spec_identity() or config_identity(), so no change to
this file can move a config_fingerprint or park a live row.

References (see the decision memo for what was verified against the fetched
source and what was not):
  Bailey & Lopez de Prado (2014), "The Deflated Sharpe Ratio", J. Portfolio
    Management 40(5). SSRN 2460551. -- the DSR itself.
  Bailey, Borwein, Lopez de Prado & Zhu (2014), "Pseudo-Mathematics and
    Financial Charlatanism", Notices of the AMS 61(5) 458-471. -- the False
    Strategy theorem that consumes N.
  Lopez de Prado & Lewis (2019), "Detection of false investment strategies
    using unsupervised learning methods", Quantitative Finance 19(9)
    1555-1565. -- ONC, the estimator that degenerated here.
  Li & Ji (2005), "Adjusting multiple testing in multilocus analyses using the
    eigenvalues of a correlation matrix", Heredity 95, 221-227.
  Galwey (2009), "A new measure of the effective number of tests, a practical
    tool for comparing families of non-independent significance tests",
    Genetic Epidemiology 33(7), 559-568.
  Harvey, Liu & Zhu (2016), "...and the Cross-Section of Expected Returns",
    Review of Financial Studies 29(1), 5-68.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / "dsr_policy_n.json"

EXPECTED_SCHEMA = "dsr_policy_n/v1"

# Past this many NEW distinct trials beyond the pool the ladder was measured
# against, the ladder is reported stale. Same value and same reasoning as
# global_effective_n.STALENESS_THRESHOLD_NEW_TRIALS: a stale ladder is still
# the best measured one available, so this is a signal, never a refusal.
STALENESS_THRESHOLD_NEW_TRIALS = 100


class DsrPolicyNError(ValueError):
    """The ladder artifact is unusable. Loud, never a silent default: a DSR
    computed against a quietly-wrong denominator looks exactly like one
    computed against the right denominator, and nothing downstream would
    surface the difference."""


@dataclass(frozen=True)
class DsrPolicyLadder:
    """The pooled rungs plus everything needed to judge how much to trust
    them. n_local is NOT stored here — it belongs to the family, and
    denominators_for() splices it in."""

    n_mechanisms: int
    n_effective: int
    n_raw: int
    measured_at: str
    run_tag: str
    rationale: dict[str, str]
    provenance: dict[str, object]
    report: str

    @property
    def pooled_rungs(self) -> tuple[int, int, int]:
        """The three project-wide rungs, ascending."""
        return (self.n_mechanisms, self.n_effective, self.n_raw)

    def denominators_for(self, n_local: int) -> list[int]:
        """The full ascending ladder for a family whose own pre-declared grid
        has `n_local` specs.

        De-duplicated, so a family whose own grid already exceeds a pooled
        rung is judged once at that N rather than twice. Sorted, because
        policy_d_verdict reads the LOWEST as the lenient tier and the HIGHEST
        as the pass tier."""
        local = int(n_local)
        if local < 1:
            raise DsrPolicyNError(
                f"n_local={n_local} is not a real grid size. This argument is the count of specs "
                "the family actually screened; 0 or negative would ask for a ladder with no "
                "lenient tier at all."
            )
        return sorted({local, *self.pooled_rungs})

    def is_stale_against(
        self, current_distinct_trials: int, *, threshold: int = STALENESS_THRESHOLD_NEW_TRIALS
    ) -> bool:
        """True once the project has accumulated `threshold` or more distinct
        trials beyond the pool this ladder was measured against. Nothing here
        reads a database, so importing this module stays side-effect free."""
        return (int(current_distinct_trials) - self.n_raw) >= threshold

    def summary(self) -> str:
        return (
            f"DSR ladder: n_local < {self.n_mechanisms} mechanisms < {self.n_effective} effective "
            f"trials < {self.n_raw} raw trials; measured {self.measured_at}, run_tag={self.run_tag}"
        )


@lru_cache(maxsize=1)
def load_dsr_policy_ladder(path: str | None = None) -> DsrPolicyLadder:
    """Read the committed ladder.

    RAISES rather than defaulting if the file is missing, unreadable, on an
    unknown schema, or carries a non-ascending ladder."""
    config_path = Path(path) if path is not None else CONFIG_PATH
    try:
        payload = json.loads(config_path.read_text())
    except FileNotFoundError as exc:
        raise DsrPolicyNError(
            f"dsr_policy_n.json not found at {config_path}. It is a TRACKED policy artifact, not "
            "a generated cache. Nothing falls back to a per-family trial count."
        ) from exc
    except (TypeError, ValueError) as exc:
        raise DsrPolicyNError(f"dsr_policy_n.json at {config_path} is not readable JSON") from exc

    schema = payload.get("schema")
    if schema != EXPECTED_SCHEMA:
        raise DsrPolicyNError(
            f"dsr_policy_n.json declares schema {schema!r}, this module reads "
            f"{EXPECTED_SCHEMA!r}. Refusing to guess at a layout change."
        )

    ladder = payload.get("ladder")
    if not isinstance(ladder, dict):
        raise DsrPolicyNError("dsr_policy_n.json has no 'ladder' object")

    try:
        n_mechanisms = int(ladder["n_mechanisms"])
        n_effective = int(ladder["n_effective"])
        n_raw = int(ladder["n_raw"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DsrPolicyNError(
            "dsr_policy_n.json's ladder needs integer n_mechanisms, n_effective and n_raw"
        ) from exc

    # STRICTLY ascending. A ladder whose rungs are out of order (or equal)
    # would silently collapse the two-tier verdict: policy_d_verdict reads the
    # highest N as the pass tier, so a mis-ordered ladder could make a more
    # lenient N the pass tier and turn an UNRESOLVED into a PASS.
    if not (2 <= n_mechanisms < n_effective < n_raw):
        raise DsrPolicyNError(
            f"dsr_policy_n.json's rungs must satisfy 2 <= n_mechanisms < n_effective < n_raw; got "
            f"{n_mechanisms}, {n_effective}, {n_raw}. An out-of-order ladder would make a more "
            "lenient denominator the pass tier."
        )

    return DsrPolicyLadder(
        n_mechanisms=n_mechanisms,
        n_effective=n_effective,
        n_raw=n_raw,
        measured_at=str(payload.get("measured_at", "unknown")),
        run_tag=str(payload.get("run_tag", "unknown")),
        rationale=dict(payload.get("rationale", {})),
        provenance=dict(payload.get("provenance", {})),
        report=str(payload.get("report", "")),
    )


def dsr_policy_denominators(n_local: int) -> list[int]:
    """Module-level convenience: the full ascending DSR ladder for a family
    whose own pre-declared grid has `n_local` specs.

    This is the function every family's policy_d_denominators() now calls in
    place of reading global_effective_n.json's provenance fields."""
    return load_dsr_policy_ladder().denominators_for(n_local)
