"""The DSR denominator ladder: that it is what every family actually uses.

These tests exist because the defect they guard against was invisible: two
PROVENANCE fields on a measurement artifact (global_effective_n.json's
`n_specs_clustered` = 481 and `raw_pooled_distinct_trials` = 857) were read as
DENOMINATORS by registration_scorecard.py without anyone choosing them. A test
that only checked "the ladder has three rungs" would have passed throughout.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from app.services.research_lab.dsr_policy_n import (
    CONFIG_PATH,
    EXPECTED_SCHEMA,
    STALENESS_THRESHOLD_NEW_TRIALS,
    DsrPolicyNError,
    dsr_policy_denominators,
    load_dsr_policy_ladder,
)

RESEARCH_LAB = Path(__file__).resolve().parents[1] / "app" / "services" / "research_lab"


def _write(tmp_path: Path, **ladder_overrides) -> Path:
    ladder = {"n_mechanisms": 37, "n_effective": 362, "n_raw": 1031}
    ladder.update(ladder_overrides)
    path = tmp_path / "dsr_policy_n.json"
    path.write_text(json.dumps({
        "schema": EXPECTED_SCHEMA, "measured_at": "2026-09-06",
        "run_tag": "t", "ladder": ladder,
    }))
    return path


# --------------------------------------------------------------------------
# the committed artifact
# --------------------------------------------------------------------------
def test_committed_ladder_loads_and_is_strictly_ascending() -> None:
    lad = load_dsr_policy_ladder()
    assert lad.n_mechanisms < lad.n_effective < lad.n_raw
    assert lad.n_mechanisms >= 2


def test_committed_ladder_is_the_one_this_decision_recorded() -> None:
    """Pins the actual numbers. If a future run moves them, this test is the
    prompt to re-read the decision memo and re-verify, not to edit the number."""
    lad = load_dsr_policy_ladder()
    # 2026-09-06: (37, 362, 1031). Re-measured 2026-09-09 (dsr_policy_n_2026-09-09.json), re-verified
    # against every live registration (no verdict change at either bar) and adopted by the owner.
    assert (lad.n_mechanisms, lad.n_effective, lad.n_raw) == (43, 397, 1131)


def test_the_retired_denominators_are_gone_from_the_ladder() -> None:
    """481 and 857 were the accidental denominators. Neither may reappear as a
    rung."""
    lad = load_dsr_policy_ladder()
    assert 481 not in lad.pooled_rungs
    assert 857 not in lad.pooled_rungs
    # 30 (variance_effective_n, a risk statistic) is likewise retired
    assert 30 not in lad.pooled_rungs


def test_config_path_points_at_a_tracked_file() -> None:
    assert CONFIG_PATH.is_file()
    assert CONFIG_PATH.name == "dsr_policy_n.json"


# --------------------------------------------------------------------------
# denominators_for
# --------------------------------------------------------------------------
@pytest.mark.parametrize("n_local", [1, 9, 12, 24, 28, 36, 48, 212])
def test_the_family_grid_is_always_the_lenient_tier(n_local: int) -> None:
    """policy_d_verdict reads the LOWEST N as the lenient tier. A ladder that
    dropped n_local below its own floor would judge the family at a
    denominator it never searched."""
    rungs = dsr_policy_denominators(n_local)
    from app.services.research_lab.dsr_policy_n import load_dsr_policy_ladder

    assert min(rungs) == min(n_local, load_dsr_policy_ladder().n_mechanisms)  # derived, never retyped (43 since 2026-09-09)
    assert n_local in rungs


@pytest.mark.parametrize("n_local", [1, 9, 37, 362, 1031, 2000])
def test_ladder_is_sorted_and_deduplicated(n_local: int) -> None:
    rungs = dsr_policy_denominators(n_local)
    assert rungs == sorted(rungs)
    assert len(rungs) == len(set(rungs))


def test_a_family_larger_than_every_pooled_rung_is_still_judged_at_its_own_grid() -> None:
    rungs = dsr_policy_denominators(5000)
    assert max(rungs) == 5000


def test_zero_or_negative_grid_size_is_refused() -> None:
    for bad in (0, -1, -212):
        with pytest.raises(DsrPolicyNError):
            dsr_policy_denominators(bad)


# --------------------------------------------------------------------------
# the loader refuses rather than defaults
# --------------------------------------------------------------------------
def test_loader_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(DsrPolicyNError):
        load_dsr_policy_ladder.__wrapped__(str(tmp_path / "nope.json"))


def test_loader_raises_on_unknown_schema(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    path.write_text(json.dumps({"schema": "other/v9", "ladder": {}}))
    with pytest.raises(DsrPolicyNError):
        load_dsr_policy_ladder.__wrapped__(str(path))


@pytest.mark.parametrize("ladder", [
    {"n_mechanisms": 362, "n_effective": 37, "n_raw": 1031},   # out of order
    {"n_mechanisms": 37, "n_effective": 1031, "n_raw": 362},   # out of order
    {"n_mechanisms": 37, "n_effective": 37, "n_raw": 1031},    # equal rungs
    {"n_mechanisms": 1, "n_effective": 362, "n_raw": 1031},    # below 2
])
def test_loader_refuses_a_misordered_ladder(tmp_path: Path, ladder: dict) -> None:
    """A mis-ordered ladder would make a MORE LENIENT N the pass tier, turning
    an UNRESOLVED into a PASS silently. That is the one failure this artifact
    must never have."""
    path = _write(tmp_path, **ladder)
    with pytest.raises(DsrPolicyNError):
        load_dsr_policy_ladder.__wrapped__(str(path))


def test_staleness_is_measured_against_the_pool_the_ladder_was_built_on() -> None:
    lad = load_dsr_policy_ladder()
    assert not lad.is_stale_against(lad.n_raw)
    assert not lad.is_stale_against(lad.n_raw + STALENESS_THRESHOLD_NEW_TRIALS - 1)
    assert lad.is_stale_against(lad.n_raw + STALENESS_THRESHOLD_NEW_TRIALS)


# --------------------------------------------------------------------------
# THE WIRING — every policy_d_denominators routes through the ladder
# --------------------------------------------------------------------------
def _modules_defining_policy_d_denominators() -> list[Path]:
    found = []
    for path in sorted(RESEARCH_LAB.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "policy_d_denominators":
                found.append(path)
                break
    return found


def test_there_is_at_least_one_policy_d_call_site() -> None:
    """Guards the two tests below against passing vacuously if the function
    were renamed."""
    assert len(_modules_defining_policy_d_denominators()) >= 7


RETIRED_PROVENANCE_FIELDS = {"n_specs_clustered", "raw_pooled_distinct_trials"}


def _policy_d_function_node(path: Path) -> ast.FunctionDef:
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.FunctionDef) and node.name == "policy_d_denominators":
            return node
    raise AssertionError(f"no policy_d_denominators in {path}")


def test_no_policy_d_call_site_still_reads_the_provenance_fields() -> None:
    """The actual regression. `n_specs_clustered` and `raw_pooled_distinct_trials`
    are bookkeeping on a MEASUREMENT artifact; reading either as a denominator
    is the defect dsr_policy_n.py exists to undo.

    Checked on the AST rather than by substring, deliberately in BOTH
    directions: substring matching would flag a comment that merely explains
    the history (these functions carry exactly such a comment), and would also
    MISS a real access spelled getattr(artifact, "n_specs" + "_clustered").
    Attribute nodes are what an actual read compiles to."""
    offenders: list[tuple[str, str]] = []
    for path in _modules_defining_policy_d_denominators():
        fn = _policy_d_function_node(path)
        for node in ast.walk(fn):
            if isinstance(node, ast.Attribute) and node.attr in RETIRED_PROVENANCE_FIELDS:
                offenders.append((path.name, node.attr))
            # a getattr() spelling of the same read
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "getattr" and len(node.args) >= 2
                    and isinstance(node.args[1], ast.Constant)
                    and node.args[1].value in RETIRED_PROVENANCE_FIELDS):
                offenders.append((path.name, str(node.args[1].value)))
    assert offenders == [], (
        f"these policy_d_denominators still read global_effective_n.json's provenance "
        f"fields as denominators: {offenders}")


def test_no_policy_d_call_site_still_loads_the_measurement_artifact() -> None:
    """Companion to the test above, closing the other half: a call site could
    stop touching the two field names while still importing the measurement
    artifact to derive a rung from it some other way. The ladder must come
    from dsr_policy_n and nowhere else."""
    offenders: list[str] = []
    for path in _modules_defining_policy_d_denominators():
        fn = _policy_d_function_node(path)
        for node in ast.walk(fn):
            if isinstance(node, ast.ImportFrom) and node.module and (
                    node.module.endswith("global_effective_n")):
                imported = {a.name for a in node.names}
                if imported - {"dsr_n_trials"}:
                    offenders.append(f"{path.name}: imports {sorted(imported)}")
    assert offenders == [], (
        "policy_d_denominators may import dsr_n_trials (the family-grid floor) from "
        f"global_effective_n, but must take its pooled rungs from dsr_policy_n: {offenders}")


def test_every_policy_d_call_site_returns_the_committed_ladder() -> None:
    import importlib

    lad = load_dsr_policy_ladder()
    checked = 0
    for path in _modules_defining_policy_d_denominators():
        mod = importlib.import_module(f"app.services.research_lab.{path.stem}")
        rungs = mod.policy_d_denominators()
        assert set(lad.pooled_rungs) <= set(rungs), (path.name, rungs)
        assert rungs == sorted(set(rungs)), (path.name, rungs)
        checked += 1
    assert checked >= 7
