"""THE PROJECT-WIDE DSR DENOMINATOR, read from a committed artifact.

WHAT THIS REPLACES
==================
deflated_sharpe.compute_deflated_sharpe() takes n_trials and corrects the
Sharpe for having searched that many configurations. Until 2026-09-04 every
family passed its OWN grid size as that number:

    cross_sectional.screen_cross_sectional_family    n_trials = len(specs)
    cross_sectional_country_valmom.py:438            CVM_N_TRIALS = 15
    cross_sectional_bonds.py:640                     BONDS_N_TRIALS = 18
    cross_sectional_crypto.py:789                    CRYPTO_N_TRIALS = 28
    cross_sectional_lazy_prices.py:301               LAZY_PRICES_N_TRIALS = 36
    ... and roughly twenty more

That answers "how many variants did THIS family try". It is not the question
the False Strategy theorem asks. The selection that produced any registered
spec was made across the WHOLE project — thirty-odd families built, screened,
and kept or abandoned over months, with the choice of which family's best spec
to register made in full view of all the others. A per-family denominator
prices none of that in, and every family's DSR was therefore too generous by
an amount nobody had measured.

THE NUMBER THIS MODULE SERVES
=============================
Not the raw pooled trial count, which errs the other way: si_ratio_hedged_h21,
_h63 and _h126 are one bet observed at three holding periods, not three
independent draws, and counting them as three over-deflates. The number here
is E[K], the EFFECTIVELY INDEPENDENT trial count, measured by clustering every
persisted trial's realized return series on its correlation structure — ONC,
Lopez de Prado & Lewis (2019), implemented in effective_n_clustering.py and
run over the pooled population by
data/research_runs/run_global_effective_n.py.

WHY A COMMITTED JSON FILE AND NOT A CONSTANT IN THIS FILE
=========================================================
Because the honest value CHANGES as the project searches more. A constant in
code would go stale silently — every new family screened would make it more
wrong, and nothing in any diff or any report would say so. global_effective_n.json
carries the value together with the date, the run_tag, the number of specs
clustered, and the raw pooled trial count it was computed from, so a reader can
always see how old it is and against how much search. is_stale_against() turns
that into an answer rather than a judgement call.

THE ONE GUARD, and why it is not optional
=========================================
effective_n_clustering.py's own module docstring states the asymmetry plainly:
E[K] is bounded to [2, N-1] by construction, k-means UNDER-counts genuinely
independent trials, and under-counting LOWERS the expected-max-Sharpe hurdle —
anti-conservative. That asymmetry is the stated reason the module shipped
unwired for as long as it did.

dsr_n_trials() therefore never returns the global number alone. It returns

    max(local grid size, global effective N)

so the denominator can only ever GROW relative to what a family used before.
Three consequences worth stating because each one is load-bearing:

  * No family's DSR can be made MORE LENIENT by this change. Every corrected
    figure is <= the figure it replaces. A "fix" that could quietly lower some
    family's hurdle would be worse than the bug.
  * ONC's documented under-counting can only cost conservatism this project
    did not already have. If E[K] comes back too small, the family falls back
    to exactly its old denominator, which is the status quo.
  * It preserves screen_cross_sectional_family's existing anti-laundering
    invariant verbatim — that function already refuses an n_trials_override
    SMALLER than the specs actually screened, calling it "trial-count
    laundering". max() is that same rule, applied to the pooled number.

WHAT THIS MODULE DELIBERATELY DOES NOT DO: decide anything. It reports a
denominator. Whether a corrected DSR should change a live registration's
status is a human decision made on the numbers, not a side effect of loading a
config file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / "global_effective_n.json"

EXPECTED_SCHEMA = "global_effective_n/v1"

# Past this many NEW distinct trials beyond what the artifact was computed
# from, the stored E[K] is reported stale. Not a hard failure: a stale number
# is still the best measured one available, and refusing to compute a DSR
# because a config file is a month old would trade a small measurement error
# for no measurement at all. 100 is roughly one large family's worth of specs
# (phase_a's 212, lazy_prices' 36, vol_regime's 48) — i.e. the scale at which
# a genuinely new search direction could have moved the cluster count.
STALENESS_THRESHOLD_NEW_TRIALS = 100


@dataclass(frozen=True)
class GlobalEffectiveN:
    """The pooled denominator plus everything needed to judge how much to
    trust it. The provenance fields are not decoration: a bare integer with no
    date, no population size and no seed range is exactly the kind of
    unverifiable number this project's rules exist to prevent."""

    n_effective: int  # E[K], the mode across the seed sweep
    computed_at: str  # ISO date
    run_tag: str
    headline_seed: int
    n_effective_headline_seed: int
    n_effective_seed_range: tuple[int, int]
    n_seeds: int
    cluster_count_distribution: dict[str, int]
    mean_silhouette: float
    n_specs_clustered: int
    n_families_clustered: int
    raw_pooled_distinct_trials: int
    raw_pooled_rows: int
    raw_pooled_families: int
    estimator: str
    provenance: str
    report: str

    def dsr_n_trials(self, local_grid_size: int) -> int:
        """The n_trials to hand compute_deflated_sharpe for a family whose own
        pre-declared grid has `local_grid_size` specs.

        max(), never the global number alone — see the module docstring's
        "THE ONE GUARD". The denominator can only grow, so this correction can
        never make any family's DSR more lenient than it already was."""
        local = int(local_grid_size)
        if local < 1:
            raise ValueError(
                f"local_grid_size={local_grid_size} is not a real grid size. This argument is the "
                "count of specs the family actually screened; passing 0 or a negative would ask "
                "for a denominator with no lower bound at all."
            )
        return max(local, self.n_effective)

    def is_stale_against(
        self, current_distinct_trials: int, *, threshold: int = STALENESS_THRESHOLD_NEW_TRIALS
    ) -> bool:
        """True when the project has accumulated `threshold` or more distinct
        trials since this value was measured. Callers with a live database
        connection can surface it; nothing here reads a database itself, so
        importing this module stays free of side effects."""
        return (int(current_distinct_trials) - self.raw_pooled_distinct_trials) >= threshold

    def summary(self) -> str:
        lo, hi = self.n_effective_seed_range
        return (
            f"global effective N = {self.n_effective} (ONC E[K], mode of {self.n_seeds} seeds, "
            f"range {lo}..{hi}); measured {self.computed_at} on {self.n_specs_clustered} specs "
            f"across {self.n_families_clustered} families, against a raw pooled population of "
            f"{self.raw_pooled_distinct_trials} distinct trials in "
            f"{self.raw_pooled_families} families; run_tag={self.run_tag}"
        )


@lru_cache(maxsize=1)
def load_global_effective_n(path: str | None = None) -> GlobalEffectiveN:
    """Read the committed artifact.

    RAISES rather than defaulting if the file is missing, unreadable, on an
    unknown schema, or carries a non-positive n_effective. A silent fallback
    is the specific failure this whole change exists to remove: a DSR computed
    against a quietly-wrong denominator looks exactly like a DSR computed
    against the right one, and nothing downstream would ever surface the
    difference. Loud is the only safe behaviour here."""
    config_path = Path(path) if path is not None else CONFIG_PATH
    try:
        payload = json.loads(config_path.read_text())
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"global_effective_n.json not found at {config_path}. It is a TRACKED file, not a "
            "generated cache — regenerate it with "
            "`./venv/bin/python data/research_runs/run_global_effective_n.py --stage cluster` "
            "and commit the result. Nothing falls back to a per-family trial count."
        ) from exc
    except (TypeError, ValueError) as exc:
        raise ValueError(f"global_effective_n.json at {config_path} is not readable JSON") from exc

    schema = payload.get("schema")
    if schema != EXPECTED_SCHEMA:
        raise ValueError(
            f"global_effective_n.json declares schema {schema!r}, this module reads "
            f"{EXPECTED_SCHEMA!r}. Refusing to guess at a layout change."
        )
    n_effective = payload.get("n_effective")
    if not isinstance(n_effective, int) or n_effective < 2:
        # < 2 is the estimator's own structural floor (effective_n_clustering's
        # candidate range starts at k=2), so anything below it is a corrupt
        # artifact rather than a small measurement.
        raise ValueError(
            f"global_effective_n.json carries n_effective={n_effective!r}; ONC cannot return "
            "fewer than 2 clusters, so this artifact is corrupt."
        )
    seed_range = payload.get("n_effective_seed_range") or [n_effective, n_effective]

    return GlobalEffectiveN(
        n_effective=n_effective,
        computed_at=str(payload.get("computed_at", "unknown")),
        run_tag=str(payload.get("run_tag", "unknown")),
        headline_seed=int(payload.get("headline_seed", 0)),
        n_effective_headline_seed=int(payload.get("n_effective_headline_seed", n_effective)),
        n_effective_seed_range=(int(seed_range[0]), int(seed_range[1])),
        n_seeds=int(payload.get("n_seeds", 1)),
        cluster_count_distribution=dict(payload.get("cluster_count_distribution", {})),
        mean_silhouette=float(payload.get("mean_silhouette", float("nan"))),
        n_specs_clustered=int(payload.get("n_specs_clustered", 0)),
        n_families_clustered=int(payload.get("n_families_clustered", 0)),
        raw_pooled_distinct_trials=int(payload.get("raw_pooled_distinct_trials", 0)),
        raw_pooled_rows=int(payload.get("raw_pooled_rows", 0)),
        raw_pooled_families=int(payload.get("raw_pooled_families", 0)),
        estimator=str(payload.get("estimator", "")),
        provenance=str(payload.get("provenance", "")),
        report=str(payload.get("report", "")),
    )


def dsr_n_trials(local_grid_size: int) -> int:
    """Module-level convenience for the common call — the DSR denominator for
    a family whose own pre-declared grid has `local_grid_size` specs.

    This is the function every family's DSR call site now uses in place of its
    own `*_N_TRIALS` constant."""
    return load_global_effective_n().dsr_n_trials(local_grid_size)
