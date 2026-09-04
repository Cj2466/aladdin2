"""Validation of the pooled, project-wide DSR denominator.

THE LOAD-BEARING TEST IN THIS FILE IS test_denominator_never_shrinks.

Everything else here is schema and plumbing. That one test is the safety
property the whole change rests on: effective_n_clustering.py's own docstring
records that ONC UNDER-counts genuinely independent trials, and that an
under-count LOWERS the expected-max-Sharpe hurdle. A wiring that could hand a
family a SMALLER denominator than it used before would therefore be capable of
making a strategy look more significant than the previous, already-too-generous
method did -- strictly worse than the bug being fixed. max() is what forecloses
that, and this file pins it rather than trusting the one-line implementation to
stay a max() through future edits.

The committed-artifact tests exist for the second failure mode this change can
have: a silently stale or corrupt global_effective_n.json. The loader is
required to RAISE on every malformed input rather than fall back to a default,
because a DSR computed against a quietly-wrong denominator is indistinguishable
from a correct one at every point downstream.
"""

import json

import pytest

from app.services.research_lab.global_effective_n import (
    CONFIG_PATH,
    EXPECTED_SCHEMA,
    STALENESS_THRESHOLD_NEW_TRIALS,
    GlobalEffectiveN,
    dsr_n_trials,
    load_global_effective_n,
)


def _make(n_effective: int = 40, **overrides) -> GlobalEffectiveN:
    base = {
        "n_effective": n_effective,
        "computed_at": "2026-09-04",
        "run_tag": "test",
        "headline_seed": 1,
        "n_effective_headline_seed": n_effective,
        "n_effective_seed_range": (n_effective, n_effective),
        "n_seeds": 25,
        "cluster_count_distribution": {str(n_effective): 25},
        "mean_silhouette": 0.5,
        "n_specs_clustered": 400,
        "n_families_clustered": 25,
        "raw_pooled_distinct_trials": 800,
        "raw_pooled_rows": 2200,
        "raw_pooled_families": 32,
        "estimator": "ONC",
        "provenance": "test",
        "report": "test",
    }
    base.update(overrides)
    return GlobalEffectiveN(**base)


# ---------------------------------------------------------------------------
# THE safety property
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n_effective", [2, 5, 12, 40, 212, 1000])
def test_denominator_never_shrinks(n_effective: int) -> None:
    """For EVERY local grid size, the pooled denominator is at least the local
    one. This is the property that makes the correction safe to ship despite
    ONC's documented under-counting: no family's DSR can come out easier than
    it was before, whatever E[K] turns out to be."""
    cfg = _make(n_effective)
    for local in range(1, 600):
        assert cfg.dsr_n_trials(local) >= local, local


@pytest.mark.parametrize("n_effective", [2, 5, 12, 40, 212])
def test_denominator_is_at_least_the_pooled_count(n_effective: int) -> None:
    """...and at least the pooled count, for every local size at or below it.
    The two bounds together ARE max(); asserting both separately means a
    regression to either min() or "always local" fails loudly."""
    cfg = _make(n_effective)
    for local in range(1, 600):
        assert cfg.dsr_n_trials(local) == max(local, n_effective), local


def test_zero_or_negative_grid_size_is_refused() -> None:
    """A grid size of 0 would be a caller with no pre-declared family at all;
    silently accepting it would hand back the global number as if a real floor
    had been checked."""
    cfg = _make()
    for bad in (0, -1, -100):
        with pytest.raises(ValueError, match="not a real grid size"):
            cfg.dsr_n_trials(bad)


# ---------------------------------------------------------------------------
# The committed artifact
# ---------------------------------------------------------------------------


def test_committed_artifact_loads_and_is_self_consistent() -> None:
    """The tracked global_effective_n.json is the production input. If it is
    ever committed malformed, every DSR in the project silently changes or
    every screening run dies -- so it is checked here, not only where it is
    generated."""
    cfg = load_global_effective_n()
    assert cfg.n_effective >= 2  # ONC's own structural floor
    lo, hi = cfg.n_effective_seed_range
    assert lo <= cfg.n_effective <= hi, (lo, cfg.n_effective, hi)
    assert lo <= cfg.n_effective_headline_seed <= hi
    assert cfg.n_specs_clustered > 0
    assert cfg.n_families_clustered > 0
    # E[K] is bounded above by N-1 by construction (effective_n_clustering's
    # own documented structural limitation) -- a value at or above the
    # clustered population size would mean the artifact did not come from ONC.
    assert cfg.n_effective < cfg.n_specs_clustered
    assert cfg.raw_pooled_distinct_trials >= cfg.n_specs_clustered
    assert sum(cfg.cluster_count_distribution.values()) == cfg.n_seeds
    assert cfg.summary()  # renders without raising


def test_module_level_helper_matches_the_loaded_config() -> None:
    cfg = load_global_effective_n()
    for local in (1, 9, 15, 36, 212):
        assert dsr_n_trials(local) == cfg.dsr_n_trials(local)


def test_loader_raises_on_missing_file(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="TRACKED file"):
        load_global_effective_n(str(tmp_path / "nope.json"))


def test_loader_raises_on_unknown_schema(tmp_path) -> None:
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps({"schema": "something/v9", "n_effective": 40}))
    with pytest.raises(ValueError, match="declares schema"):
        load_global_effective_n(str(path))


@pytest.mark.parametrize("bad", [1, 0, -3, None, "40", 12.5])
def test_loader_raises_on_impossible_n_effective(tmp_path, bad) -> None:
    """Below 2 is not a small measurement, it is a corrupt artifact: ONC's
    candidate range starts at k=2 and cannot return fewer."""
    path = tmp_path / f"cfg_{bad}.json"
    path.write_text(json.dumps({"schema": EXPECTED_SCHEMA, "n_effective": bad}))
    with pytest.raises(ValueError, match="corrupt"):
        load_global_effective_n(str(path))


def test_loader_raises_on_unparseable_json(tmp_path) -> None:
    path = tmp_path / "cfg.json"
    path.write_text("{not json")
    with pytest.raises(ValueError, match="not readable JSON"):
        load_global_effective_n(str(path))


def test_config_path_points_at_a_tracked_file() -> None:
    """The artifact lives beside the module that reads it, inside app/, not in
    a gitignored data directory -- so it travels with a deploy and shows up in
    a diff when it changes."""
    assert CONFIG_PATH.exists()
    assert CONFIG_PATH.name == "global_effective_n.json"
    assert CONFIG_PATH.parent.name == "research_lab"


# ---------------------------------------------------------------------------
# Staleness
# ---------------------------------------------------------------------------


def test_staleness_is_measured_against_the_population_it_was_computed_from() -> None:
    cfg = _make(raw_pooled_distinct_trials=800)
    assert not cfg.is_stale_against(800)
    assert not cfg.is_stale_against(800 + STALENESS_THRESHOLD_NEW_TRIALS - 1)
    assert cfg.is_stale_against(800 + STALENESS_THRESHOLD_NEW_TRIALS)
    # A SHRINKING population (rows deleted) is not staleness in this sense.
    assert not cfg.is_stale_against(10)


def test_staleness_threshold_is_overridable() -> None:
    cfg = _make(raw_pooled_distinct_trials=800)
    assert cfg.is_stale_against(801, threshold=1)
    assert not cfg.is_stale_against(801, threshold=2)


# ---------------------------------------------------------------------------
# "The fix stays fixed": every DSR call site is pooled
# ---------------------------------------------------------------------------
#
# The bug this change fixes was not one wrong line, it was a HABIT: twenty-odd
# modules each independently decided that their own grid size was the
# denominator. Nothing stopped the twenty-first from doing the same. This test
# is that stop -- a new family that calls compute_deflated_sharpe without
# routing its denominator through global_effective_n fails here, at the
# structural level, rather than quietly shipping a too-generous DSR that looks
# exactly like a correct one.

import ast
from pathlib import Path

_APP = Path(__file__).resolve().parent.parent / "app"
_RESEARCH_LAB = _APP / "services" / "research_lab"

# Call sites deliberately NOT pooled, each with the reason. Anything not on
# this list must be pooled; anything on it must still be here for a reason a
# reader can check.
_UNPOOLED_BY_DESIGN = {
    "deflated_sharpe.py": "defines compute_deflated_sharpe; it has no denominator of its own",
    "effective_n_clustering.py": "estimates E[K]; importing the consumer would be circular",
    # ------------------------------------------------------------------
    # THE TWO PAIRS-TRADING CALL SITES. Left unpooled DELIBERATELY, and
    # flagged for the repo owner rather than decided unilaterally, because
    # they are not the bug this change fixes and pooling them is a modelling
    # judgement with a visible consequence.
    #
    # Neither hardcodes a family grid size -- the thing that was wrong
    # everywhere else. Both COUNT THE ACTUAL SIBLING POPULATION at runtime:
    # every ExperimentRun for the same strategy_name/ticker_a/ticker_b. That
    # is a genuinely different search (a user tuning parameters for one pair)
    # from the cross-sectional family search, and whether the two should share
    # one denominator is a question about what search produced the candidate,
    # not a bug.
    #
    # The consequence of pooling them, measured rather than asserted: sibling
    # counts here are routinely 2-4, i.e. BELOW deflated_sharpe's
    # MIN_TRIALS_FOR_DSR of 5, so those runs currently report "not enough
    # sibling trials to deflate" and no DSR at all. Pooling would push every
    # one of them over the floor and start showing a (heavily deflated) DSR
    # where the UI now shows none -- a visible behaviour change on a
    # user-facing surface. Defensible, arguably more honest, and not this
    # change's to make.
    "autonomous_tuning.py": (
        "pairs-trading parameter tuning; denominator is the runtime sibling-trial count for "
        "one strategy/ticker pair, not a hardcoded family grid. Pooling it is an open decision "
        "for the repo owner -- see the block comment above."
    ),
    "routers/research_lab.py": (
        "the pairs-trading UI read path; same runtime sibling-trial denominator as "
        "autonomous_tuning.py and the same open decision."
    ),
}


def _modules_calling_compute_deflated_sharpe() -> dict[str, Path]:
    """Every module in app/ that CALLS compute_deflated_sharpe.

    Scans app/routers as well as app/services/research_lab: the two
    pairs-trading call sites live outside the family directory, and a scan
    that only globbed the family directory would exempt them by accident
    rather than by decision -- which is exactly the failure mode this test
    exists to prevent."""
    found: dict[str, Path] = {}
    candidates = sorted(_RESEARCH_LAB.glob("*.py")) + sorted((_APP / "routers").glob("*.py"))
    for path in candidates:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "compute_deflated_sharpe"
            ):
                key = path.name
                if path.parent.name != "research_lab":
                    key = f"{path.parent.name}/{path.name}"
                found[key] = path
                break
    return found


def test_every_research_lab_dsr_call_site_routes_through_the_pooled_denominator() -> None:
    callers = _modules_calling_compute_deflated_sharpe()
    assert callers, "found no compute_deflated_sharpe call sites at all -- the scan is broken"

    unpooled = []
    for name, path in callers.items():
        if name in _UNPOOLED_BY_DESIGN:
            continue
        if "global_effective_n import dsr_n_trials" not in path.read_text():
            unpooled.append(name)
    assert not unpooled, (
        f"{unpooled} call compute_deflated_sharpe without importing dsr_n_trials. Every family's "
        "DSR denominator must be the pooled project-wide count, not that family's own grid size "
        "-- see global_effective_n.py. If a new call site genuinely should not be pooled, add it "
        "to _UNPOOLED_BY_DESIGN with the reason."
    )


def test_the_unpooled_exemptions_still_exist_and_still_do_not_pool() -> None:
    """An exemption that names a deleted file, or a file that has since been
    pooled, is a stale comment pretending to be a decision."""
    callers = _modules_calling_compute_deflated_sharpe()
    for name in _UNPOOLED_BY_DESIGN:
        path = _APP / ("routers/research_lab.py" if "/" in name else f"services/research_lab/{name}")
        assert path.exists(), f"{name} is exempted from pooling but no longer exists"
        if name in ("deflated_sharpe.py", "effective_n_clustering.py"):
            continue
        assert name in callers, (
            f"{name} is exempted from pooling but no longer calls compute_deflated_sharpe -- "
            "the exemption is now a stale comment and should be deleted."
        )
        assert "global_effective_n import dsr_n_trials" not in path.read_text(), (
            f"{name} is listed as unpooled by design but now imports dsr_n_trials. If it was "
            "pooled on purpose, remove it from _UNPOOLED_BY_DESIGN."
        )


def test_the_shared_harness_is_pooled() -> None:
    """cross_sectional.py is the single call site covering ~20 families, so it
    gets its own assertion rather than only being caught by the sweep above."""
    text = (_RESEARCH_LAB / "cross_sectional.py").read_text()
    assert "from app.services.research_lab.global_effective_n import dsr_n_trials" in text
    assert "dsr_n_trials(n_trials)" in text
