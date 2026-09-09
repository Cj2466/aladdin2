"""Structural checks on the MECHANICAL-FIELDS-ONLY scorecard drafts in
data/research_runs/scorecard_drafts_2026-09-10/.

These drafts exist to make progress on the registration-scorecard gap
(tests/test_registration_scorecards.py::test_every_family_has_a_scorecard is
DELIBERATELY red — see that module's docstring) WITHOUT fabricating Layer 2
mechanism-fidelity citations from the code. This file does not — and must
not — assert that the drafts are complete scorecards; it asserts the
opposite: that they honestly declare themselves incomplete and never smuggle
in an unearned source citation.

Fast and hermetic: reads only the four committed JSON files, never touches
the DB or the network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
DRAFTS_DIR = BACKEND / "data" / "research_runs" / "scorecard_drafts_2026-09-10"
VALIDATOR_SCORECARD_DIR = BACKEND / "data" / "research_runs" / "scorecards"

EXPECTED_DRAFT_FAMILY_KEYS = (
    "quality_cbop",
    "short_interest_ratio",
    "lazy_prices_jaccard_full",
    "cross_sectional_crypto",
)


def _draft_paths() -> list[Path]:
    return sorted(DRAFTS_DIR.glob("*_SCORECARD_DRAFT.json"))


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def test_drafts_directory_exists_and_is_not_empty():
    assert DRAFTS_DIR.is_dir(), f"expected drafts directory at {DRAFTS_DIR}"
    paths = _draft_paths()
    assert paths, f"no *_SCORECARD_DRAFT.json files found under {DRAFTS_DIR}"


def test_all_four_live_families_have_a_draft():
    found = {p.name[: -len("_SCORECARD_DRAFT.json")] for p in _draft_paths()}
    missing = set(EXPECTED_DRAFT_FAMILY_KEYS) - found
    assert not missing, f"missing draft(s) for {sorted(missing)}; found {sorted(found)}"


@pytest.mark.parametrize("path", _draft_paths(), ids=lambda p: p.name)
def test_every_draft_carries_draft_status_and_a_nonempty_gaps_list(path: Path):
    """(a) from the task brief: every emitted draft must carry draft_status
    and a non-empty gaps list."""
    payload = _load(path)
    assert "draft_status" in payload, f"{path.name}: missing draft_status"
    status = payload["draft_status"]
    assert isinstance(status, str) and status.strip(), f"{path.name}: draft_status must be a non-empty string"
    assert "INCOMPLETE" in status.upper(), (
        f"{path.name}: draft_status must say the draft is incomplete, got {status!r}"
    )

    gaps = payload.get("gaps")
    assert isinstance(gaps, list) and len(gaps) > 0, f"{path.name}: gaps must be a non-empty list"
    for i, entry in enumerate(gaps):
        assert isinstance(entry, dict), f"{path.name}: gaps[{i}] must be an object"
        assert entry.get("field"), f"{path.name}: gaps[{i}] missing a non-empty 'field'"
        assert entry.get("reason"), f"{path.name}: gaps[{i}] missing a non-empty 'reason'"


@pytest.mark.parametrize("path", _draft_paths(), ids=lambda p: p.name)
def test_no_draft_has_a_nonempty_layer_2_source_citation(path: Path):
    """(b) the anti-fabrication guard: layer_2_mechanism_fidelity must be
    entirely absent/null in a mechanical-fields-only draft. If it is present
    at all, its source_citation must not be a real-looking (non-empty,
    non-placeholder) string -- that would mean a citation was fabricated
    from code, which is exactly what these drafts must never do."""
    payload = _load(path)
    layer_2 = payload.get("layer_2_mechanism_fidelity")
    if layer_2 is None:
        return  # the expected, correct state for a mechanical-only draft
    assert isinstance(layer_2, dict), f"{path.name}: layer_2_mechanism_fidelity must be null or an object"
    citation = layer_2.get("source_citation")
    assert citation in (None, ""), (
        f"{path.name}: layer_2_mechanism_fidelity.source_citation is {citation!r} -- a "
        "mechanical-fields-only draft must never carry a filled Layer 2 citation, fabricated "
        "or otherwise"
    )


@pytest.mark.parametrize("path", _draft_paths(), ids=lambda p: p.name)
def test_no_draft_asserts_a_verdict_or_decision(path: Path):
    """Companion to the citation guard: the judgment fields this draft
    generator must not fill (verdict, decision, decision_rationale) stay
    null. A computed-for-reference value is fine as long as it does not
    live under the real 'verdict' key."""
    payload = _load(path)
    assert payload.get("decision") is None, f"{path.name}: decision must be null in a draft"
    assert payload.get("decision_rationale") is None, f"{path.name}: decision_rationale must be null in a draft"
    layer_1 = payload.get("layer_1_statistical") or {}
    assert layer_1.get("verdict") is None, f"{path.name}: layer_1_statistical.verdict must be null in a draft"


def test_drafts_directory_is_not_the_validators_directory():
    """(c) from the task brief: the drafts directory must not be the one
    registration_scorecard.py's validator (and the completeness test) reads
    from. Putting an incomplete card there would either fail to parse or
    silently satisfy the completeness check while asserting nothing about
    Layer 2 -- neither is acceptable."""
    assert DRAFTS_DIR.resolve() != VALIDATOR_SCORECARD_DIR.resolve(), (
        f"drafts directory {DRAFTS_DIR} must differ from the validator's directory "
        f"{VALIDATOR_SCORECARD_DIR}"
    )
    # And no draft file has leaked into the validator's directory under a
    # name the completeness test would pick up.
    if VALIDATOR_SCORECARD_DIR.is_dir():
        leaked = list(VALIDATOR_SCORECARD_DIR.glob("*_SCORECARD_DRAFT.json"))
        assert not leaked, f"draft file(s) found inside the validator's directory: {leaked}"


@pytest.mark.parametrize("path", _draft_paths(), ids=lambda p: p.name)
def test_dsr_by_n_includes_n_local_and_every_pooled_rung(path: Path):
    """Sanity check on the one thing these drafts DO compute: dsr_by_n must
    include the family's own n_local and the pooled ladder rungs this
    project currently uses (43, 397, 1131), read live from the committed
    ladder artifact rather than hardcoded, so this test tracks the ladder
    instead of pinning a stale snapshot of it."""
    from app.services.research_lab.registration_scorecard import (
        required_pooled_denominators,
    )

    payload = _load(path)
    layer_1 = payload["layer_1_statistical"]
    n_local = layer_1["n_local"]
    dsr_by_n = {int(k): v for k, v in layer_1["dsr_by_n"].items()}
    assert n_local in dsr_by_n, f"{path.name}: dsr_by_n missing n_local={n_local}"
    for pooled_n in required_pooled_denominators():
        if pooled_n <= n_local:
            continue
        assert pooled_n in dsr_by_n, f"{path.name}: dsr_by_n missing pooled rung {pooled_n}"
