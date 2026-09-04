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

NOTHING HERE CHANGES A REGISTRATION'S STATUS. A red test is the entire output.
"""

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
    hard way: once a dependency has ever moved, its pinned baseline must equal
    the new_sha256 of its most recent acknowledgement."""
    bad = []
    for reg in manifest.registrations:
        for dep, ack in reg.unrecorded_baseline_bumps():
            bad.append(
                f"  {reg.family_key}: {dep.path} is pinned to {dep.sha256[:12]}… but its latest "
                f"acknowledgement ({ack.date}) records new_sha256 {ack.new_sha256[:12]}…"
            )
    assert not bad, (
        "a dependency baseline was moved without a matching acknowledgement:\n" + "\n".join(bad)
    )


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
