"""Drift detection for the shared code a LIVE forward registration stands on.

THE GAP THIS CLOSES. cross_sectional_forward_registry already re-derives
spec_fingerprint and config_fingerprint every tick and parks a row in
"spec_drift" when either moves. Neither covers the code UNDERNEATH the spec —
how prices are adjusted, how the universe is built, what the cost model
charges, how the DSR denominator is chosen. Three real incidents moved exactly
that layer (the price-store rewrite 77e77d7..61bd307, the CRSP dividend
convention a3ba0bc, short_interest's mid-split price freeze fa614ac) and every
one was found by someone happening to investigate.

WHAT A FAILURE HERE MEANS. Not "something is broken" — the price-store rewrite
moved everything and changed no verdict. It means a dependency of a live
registration changed and nobody has written down what that did. The fix is to
re-verify, append an acknowledgement, and re-pin — in that order. Re-pinning
without the acknowledgement is caught separately by
test_no_baseline_was_bumped_without_an_acknowledgement, so the record cannot
be skipped by editing one hash.

AND SINCE 2026-09-05, RE-PINNING WITH NO ACKNOWLEDGEMENT AT ALL IS CAUGHT TOO.
It was not before: the check looked up a dependency's acknowledgements and,
finding none, treated that as "this file never moved" — so the one shortcut
nobody would leave a trace for was the one that passed. The synthetic
manifests at the bottom of this file exercise both shapes side by side (a
re-pin with a WRONG acknowledgement, a re-pin with ZERO acknowledgements) plus
the legitimate case that must keep passing, because a red-case test that only
ever saw the wrong-ack shape is precisely how the hole stayed open.

NOTHING HERE CHANGES A REGISTRATION'S STATUS. A red test is the entire output.
"""

import json
from pathlib import Path

import pytest

from app.services.research_lab.live_registration_dependencies import (
    BACKEND_ROOT,
    REFRESH_COMMAND,
    DependencyManifestError,
    file_sha256,
    load_manifest,
)
from app.services.research_lab.registration_scorecard import (
    RETIRED_LIVE_REGISTRATION_FAMILY_KEYS,
    live_registration_family_keys,
)


@pytest.fixture(scope="module")
def manifest():
    return load_manifest()


def test_every_live_registration_is_pinned(manifest):
    """A registration wired into app/main.py's lifespan but absent from the
    manifest is unmonitored — which is the state the manifest exists to end.
    Retired registrations are excluded: they accumulate no new ticks, so there
    is nothing left for drift protection to guard (see
    RETIRED_LIVE_REGISTRATION_FAMILY_KEYS's own docstring)."""
    live = {
        key: pattern
        for key, pattern in live_registration_family_keys().items()
        if key not in RETIRED_LIVE_REGISTRATION_FAMILY_KEYS
    }
    pinned = {(r.family_key, r.pattern_id) for r in manifest.registrations}
    missing = sorted(set(live.items()) - pinned)
    assert not missing, (
        f"live registration(s) {missing} are not pinned in the dependency manifest. "
        f"Regenerate it: {REFRESH_COMMAND}"
    )


def test_the_manifest_pins_nothing_that_no_longer_exists(manifest):
    gone = [
        dep.path
        for dep in manifest.all_dependencies().values()
        if not (BACKEND_ROOT / dep.path).is_file()
    ]
    assert not gone, (
        f"pinned file(s) {gone} no longer exist. A deleted dependency of a live registration is "
        f"drift of the loudest kind — re-verify what replaced it, then {REFRESH_COMMAND}"
    )


def test_no_live_registration_dependency_has_changed_unacknowledged(manifest):
    """THE test. Every pinned file must still hash to its pinned baseline."""
    report = []
    for reg in manifest.registrations:
        for dep, current in reg.drift():
            report.append(
                f"  {reg.family_key}/{reg.pattern_id}\n"
                f"    {dep.path}\n"
                f"      pinned  {dep.sha256}\n"
                f"      current {current or '(file missing)'}\n"
                f"      why it matters: {dep.why}"
            )
    shared_drift = [
        (dep, dep.current_sha256())
        for dep in manifest.shared
        if dep.current_sha256() != dep.sha256
    ]
    for dep, current in shared_drift:
        report.append(
            f"  [shared tick path — affects EVERY live registration]\n"
            f"    {dep.path}\n"
            f"      pinned  {dep.sha256}\n"
            f"      current {current or '(file missing)'}\n"
            f"      why it matters: {dep.why}"
        )

    if report:
        pytest.fail(
            "a live forward registration's dependencies changed since they were pinned:\n\n"
            + "\n".join(report)
            + "\n\nThis is NOT automatically a problem — the price-store rewrite moved every "
            "adjusted price in the project and changed no verdict. What it must not be is "
            "unnoticed. In order:\n"
            "  1. re-verify what the change does to the affected registration's numbers;\n"
            "  2. append an acknowledgement entry (date, dependency, old/new sha256, commit, "
            "what you re-ran, what you found — including 'nothing changed');\n"
            f"  3. then re-pin: {REFRESH_COMMAND}\n"
            "Never change a registration's status to make this pass; that is the repo owner's "
            "decision, not a side effect of a code change."
        )


def test_no_baseline_was_bumped_without_an_acknowledgement(manifest):
    """Re-pinning is the easy way to silence the test above. This makes it the
    hard way: a dependency's pinned baseline must be REACHABLE from the hash it
    was first pinned to (original_sha256) by its own acknowledgements, each one
    naming the specific old -> new transition it made.

    That covers both shapes. A wrong acknowledgement breaks a link. NO
    acknowledgement leaves the chain sitting at original_sha256 while the
    baseline has moved, which is also a break — and used not to be."""
    bad = []
    for reg in manifest.registrations:
        for _dep, reason in reg.unrecorded_baseline_bumps():
            bad.append(f"  {reg.family_key}: {reason}")
    assert not bad, (
        "a dependency baseline was moved without a matching acknowledgement:\n" + "\n".join(bad)
    )


def test_no_shared_tick_path_baseline_was_bumped_without_an_acknowledgement(manifest):
    """The same rule for the shared tick path — the files EVERY live
    registration runs through, where an unrecorded re-pin is worse rather than
    better.

    This half was unguarded until 2026-09-05 and 26d1ce1's own acknowledgement
    for cross_sectional_forward_registry.py says so in writing. shared_tick_path
    entries carry no acknowledgements list of their own, so the check reads the
    UNION of every registration's — which is where a shared file's
    acknowledgement actually gets filed."""
    bad = [f"  [shared tick path] {reason}" for _dep, reason in manifest.shared_baseline_bumps()]
    assert not bad, (
        "a SHARED dependency baseline was moved without a matching acknowledgement:\n"
        + "\n".join(bad)
    )


def test_every_pinned_dependency_records_where_its_chain_starts(manifest):
    """original_sha256 is what makes the two tests above able to see a missing
    acknowledgement at all. A dependency without one would be unguarded in
    exactly the old way, so its absence is a failure in its own right rather
    than something load_manifest quietly fills in."""
    for dep in manifest.all_dependencies().values():
        assert len(dep.original_sha256) == 64, f"{dep.path} has no usable original_sha256"


def test_a_path_pinned_twice_is_pinned_to_the_same_hash(manifest):
    # all_dependencies() raises on a contradiction; calling it IS the check.
    assert manifest.all_dependencies()


def test_the_manifest_covers_the_modules_the_incidents_actually_touched(manifest):
    """Regression guard on the manifest's SCOPE, not its hashes. If a future
    refactor moves the price store or the cost model out of the traced set,
    this manifest silently stops watching the exact files whose changes
    produced the three incidents it was built for."""
    paths = set(manifest.all_dependencies())
    for required in (
        "app/services/market_data/price_store.py",  # price rewrite + dividend convention
        "app/services/research_lab/cross_sectional.py",  # the harness / cost model
        "app/services/research_lab/deflated_sharpe.py",
        "app/services/research_lab/global_effective_n.py",
        "app/services/research_lab/global_effective_n.json",  # the pooled N itself
        "app/services/research_lab/sp500_membership_history.py",
    ):
        assert required in paths, f"{required} is no longer pinned by the manifest"

    # spread_estimator is lazy_prices' cost basis specifically, and the one
    # dependency currently known to be wrong (the 10-40x large-cap
    # overstatement). It must be pinned against THAT registration.
    lazy = manifest.by_key("lazy_prices_jaccard_full")
    assert "app/services/research_lab/spread_estimator.py" in {d.path for d in lazy.dependencies}


def test_hashes_are_of_the_real_files(manifest):
    """Cheap end-to-end check that the pinned digests were computed the way
    this module recomputes them — a mismatch in hashing convention would make
    every other test in this file vacuously red or vacuously green."""
    dep = manifest.by_key("lazy_prices_jaccard_full").dependencies[0]
    assert file_sha256(BACKEND_ROOT / dep.path) == dep.current_sha256()


def test_a_malformed_manifest_is_refused_rather_than_half_read(tmp_path: Path):
    bad = tmp_path / "m.json"
    bad.write_text('{"schema": "live_registration_dependencies/v99"}')
    with pytest.raises(DependencyManifestError, match="declares schema"):
        load_manifest(bad)

    bad.write_text('{"schema": "live_registration_dependencies/v1", "hash_algorithm": "md5"}')
    with pytest.raises(DependencyManifestError, match="only sha256"):
        load_manifest(bad)

    bad.write_text(
        '{"schema": "live_registration_dependencies/v1", "hash_algorithm": "sha256", '
        '"registrations": {}}'
    )
    with pytest.raises(DependencyManifestError, match="pins no registrations"):
        load_manifest(bad)


def test_an_acknowledgement_with_an_empty_field_is_refused(tmp_path: Path):
    bad = tmp_path / "m.json"
    bad.write_text(
        '{"schema": "live_registration_dependencies/v1", "hash_algorithm": "sha256", '
        '"registrations": {"x/y": {"family_key": "x", "pattern_id": "y", "module_path": "z.py", '
        '"dependencies": [], "acknowledgements": [{"date": "2026-09-05", "dependency": "z.py", '
        f'"old_sha256": "{"a" * 64}", "new_sha256": "{"b" * 64}", "commit": "abc1234", '
        '"reverified": "", "finding": "nothing"}]}}}'
    )
    with pytest.raises(DependencyManifestError, match="reverified"):
        load_manifest(bad)


# ---------------------------------------------------------------------------
# THE RE-PIN CASES, ON SYNTHETIC MANIFESTS
# ---------------------------------------------------------------------------
#
# Written against hand-built manifests rather than the real one because the
# real one is (and must stay) green: a red case that can only be observed by
# breaking the committed manifest is a red case nobody runs. Every manifest
# below differs from the green baseline in ONE field, so what each test proves
# is unambiguous.
#
# THE HASHES ARE FAKE AND THE PATHS ARE NOT REAL FILES. Deliberate: these
# exercise the chain arithmetic in unrecorded_baseline_bumps() /
# shared_baseline_bumps(), which never touches the filesystem. Drift against
# real file contents is what
# test_no_live_registration_dependency_has_changed_unacknowledged covers.

ORIGINAL = "1" * 64  # what the file was first pinned to
BUMPED = "2" * 64  # what someone re-pinned it to
THIRD = "3" * 64  # a second, later move
UNRELATED = "9" * 64  # a hash that is neither


def _ack(dependency: str, old: str, new: str, date: str = "2026-09-05") -> dict:
    return {
        "date": date,
        "dependency": dependency,
        "old_sha256": old,
        "new_sha256": new,
        "commit": "abc1234",
        "reverified": "re-ran the family's screening on the frozen snapshot",
        "finding": "no verdict moved",
    }


def _manifest(
    tmp_path: Path,
    *,
    pinned: str,
    acknowledgements: list[dict],
    original: str = ORIGINAL,
    shared: list[dict] | None = None,
) -> Path:
    """A one-registration, one-dependency manifest. `pinned` is the current
    baseline and `original` the hash it was first pinned to, so pinned !=
    original IS the re-pin the acknowledgements have to account for."""
    payload = {
        "schema": "live_registration_dependencies/v1",
        "hash_algorithm": "sha256",
        "shared_tick_path": shared or [],
        "registrations": {
            "fam/spec": {
                "family_key": "fam",
                "pattern_id": "spec",
                "module_path": "app/services/research_lab/fam.py",
                "dependencies": [
                    {
                        "path": "app/services/research_lab/dep.py",
                        "sha256": pinned,
                        "original_sha256": original,
                        "why": "the thing the registration stands on",
                    }
                ],
                "acknowledgements": acknowledgements,
            }
        },
    }
    target = tmp_path / "m.json"
    target.write_text(json.dumps(payload))
    return target


def _bumps(path: Path) -> list[str]:
    return [reason for _dep, reason in load_manifest(path).by_key("fam").unrecorded_baseline_bumps()]


def test_a_repin_with_no_acknowledgement_at_all_is_caught(tmp_path: Path):
    """THE GAP, as a red case. This is the exact shape that used to pass:
    a dependency re-pinned from one hash to another with an EMPTY
    acknowledgements list, which the old implementation read as "this file
    never moved" and skipped.

    If this test ever goes green while the assertion below is unchanged, the
    hole is back."""
    reasons = _bumps(_manifest(tmp_path, pinned=BUMPED, acknowledgements=[]))
    assert len(reasons) == 1
    assert "NOT ONE acknowledgement names this path" in reasons[0]
    # The message must name the transition that has to be recorded, or the
    # reader is told a rule was broken without being told what to write.
    assert ORIGINAL[:12] in reasons[0] and BUMPED[:12] in reasons[0]


def test_a_repin_with_an_acknowledgement_for_a_different_transition_is_caught(tmp_path: Path):
    """The shape the old implementation DID catch, kept as a red case beside
    the one it did not: an acknowledgement exists, but its new_sha256 is not
    where the baseline actually landed."""
    reasons = _bumps(
        _manifest(
            tmp_path,
            pinned=BUMPED,
            acknowledgements=[_ack("app/services/research_lab/dep.py", ORIGINAL, UNRELATED)],
        )
    )
    assert len(reasons) == 1
    assert "chain ends at" in reasons[0]


def test_an_acknowledgement_that_starts_from_the_wrong_hash_is_caught(tmp_path: Path):
    """An acknowledgement that lands on the right baseline but claims to have
    started somewhere the file never was. It describes a transition that did
    not happen, so it is not a record of this one."""
    reasons = _bumps(
        _manifest(
            tmp_path,
            pinned=BUMPED,
            acknowledgements=[_ack("app/services/research_lab/dep.py", UNRELATED, BUMPED)],
        )
    )
    assert len(reasons) == 1
    assert "records old_sha256" in reasons[0]


def test_an_acknowledgement_for_another_file_does_not_cover_this_one(tmp_path: Path):
    """Acknowledgements are per PATH. One written about a sibling dependency
    must not launder a bump to this one — that would make any registration
    with an acknowledgement history a free pass for every file it pins."""
    reasons = _bumps(
        _manifest(
            tmp_path,
            pinned=BUMPED,
            acknowledgements=[_ack("app/services/research_lab/other.py", ORIGINAL, BUMPED)],
        )
    )
    assert len(reasons) == 1
    assert "NOT ONE acknowledgement names this path" in reasons[0]


def test_a_repin_with_a_matching_acknowledgement_passes(tmp_path: Path):
    """THE GREEN CASE, and the one that stops the fix from being "fail on any
    hash change". A move that was looked at, written down, and then re-pinned
    is exactly what the mechanism asks for."""
    assert not _bumps(
        _manifest(
            tmp_path,
            pinned=BUMPED,
            acknowledgements=[_ack("app/services/research_lab/dep.py", ORIGINAL, BUMPED)],
        )
    )


def test_a_second_move_needs_its_own_acknowledgement(tmp_path: Path):
    """A file that moves twice owes two entries, chained. The first one alone
    does not cover the second move — otherwise one acknowledgement would
    licence every future re-pin of that path."""
    one = _ack("app/services/research_lab/dep.py", ORIGINAL, BUMPED)
    two = _ack("app/services/research_lab/dep.py", BUMPED, THIRD)
    assert not _bumps(_manifest(tmp_path, pinned=THIRD, acknowledgements=[one, two]))
    reasons = _bumps(_manifest(tmp_path, pinned=THIRD, acknowledgements=[one]))
    assert len(reasons) == 1
    assert "chain ends at" in reasons[0]


def test_a_dependency_that_never_moved_needs_nothing(tmp_path: Path):
    """The overwhelmingly common case: pinned == original, no acknowledgements,
    silence."""
    assert not _bumps(_manifest(tmp_path, pinned=ORIGINAL, acknowledgements=[]))


def test_a_shared_tick_path_repin_with_no_acknowledgement_is_caught(tmp_path: Path):
    """The same gap on the shared side, which was unguarded for a second
    reason: shared_tick_path entries carry no acknowledgements list, and the
    per-registration walk never looked at them at all."""
    shared_dep = {
        "path": "app/services/research_lab/shared.py",
        "sha256": BUMPED,
        "original_sha256": ORIGINAL,
        "why": "every tick runs through it",
    }
    path = _manifest(tmp_path, pinned=ORIGINAL, acknowledgements=[], shared=[shared_dep])
    reasons = [reason for _dep, reason in load_manifest(path).shared_baseline_bumps()]
    assert len(reasons) == 1
    assert "NOT ONE acknowledgement names this path" in reasons[0]


def test_a_shared_repin_acknowledged_under_any_registration_passes(tmp_path: Path):
    """26d1ce1 filed cross_sectional_forward_registry.py's acknowledgement
    under lazy_prices, because the schema gives a shared entry nowhere else to
    put one. Reading the union of every registration's acknowledgements is what
    makes that filing count."""
    shared_dep = {
        "path": "app/services/research_lab/shared.py",
        "sha256": BUMPED,
        "original_sha256": ORIGINAL,
        "why": "every tick runs through it",
    }
    path = _manifest(
        tmp_path,
        pinned=ORIGINAL,
        acknowledgements=[_ack("app/services/research_lab/shared.py", ORIGINAL, BUMPED)],
        shared=[shared_dep],
    )
    assert not load_manifest(path).shared_baseline_bumps()


def test_a_dependency_with_no_original_sha256_is_refused(tmp_path: Path):
    """Deleting the field must not be the new way to make a bump invisible.
    load_manifest refuses rather than defaulting original_sha256 to the current
    baseline, which would restore the original hole exactly."""
    payload = json.loads(_manifest(tmp_path, pinned=BUMPED, acknowledgements=[]).read_text())
    del payload["registrations"]["fam/spec"]["dependencies"][0]["original_sha256"]
    target = tmp_path / "no_original.json"
    target.write_text(json.dumps(payload))
    with pytest.raises(DependencyManifestError, match="original_sha256"):
        load_manifest(target)
