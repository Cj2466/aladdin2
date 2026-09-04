"""WHAT EACH LIVE REGISTRATION IS STANDING ON, AND WHETHER IT MOVED.

THE FAILURE THIS EXISTS TO CATCH, WHICH HAS HAPPENED THREE TIMES
================================================================
A forward registration is a claim that ONE fixed strategy is being tracked
forward from a fixed start date. The registry already defends the parts of
that claim it can see: spec_fingerprint and config_fingerprint are re-derived
every tick and a mismatch parks the row in "spec_drift" instead of letting it
accumulate a track record blended from two strategies.

Neither fingerprint covers the code and data UNDERNEATH the spec. A
registration's numbers also depend on how prices are adjusted, how the
universe is built, how the DSR denominator is chosen, and what the cost model
charges — none of which is in either snapshot. Three real incidents, all
found by someone happening to investigate rather than by anything failing:

  * 77e77d7..61bd307, the price-store rewrite. Prices moved from "trust
    Yahoo's adjusted close" to "store raw and adjust ourselves", touching 26
    families and 420 specs. No verdict changed — but that was the OUTCOME of
    a deliberate 26-family re-check, not something any test would have said.
  * a3ba0bc, the dividend convention. CRSP's convention was adopted inside
    price_store.py. Same shape: every adjusted price in the project moved.
  * fa614ac, short_interest's mid-split price freeze. A reproducibility gap
    diagnosed only because a rerun did not match.

And a fourth is live right now: spread_estimator.build_edge_half_spread_frame
is documented as overstating large-cap costs 10-40x, and lazy_prices_jaccard_
full trades on it. Swapping it for build_calibrated_half_spread_frame would
change that registration's accumulating returns WITHOUT changing either
fingerprint, because the half-spread frame is data the adapter builds, not a
config field. That is exactly the invisible class of change this manifest
makes visible.

WHAT THIS DOES, AND DELIBERATELY DOES NOT DO
============================================
DOES: pin a sha256 of every shared module each live registration's tick
actually depends on, traced from real imports (see the AST trace recorded in
`trace` on each entry), and fail a test when one moves.

DOES NOT: decide anything. A moved hash is not a verdict — the price-store
rewrite moved everything and changed no verdict. The test's demand is that
someone LOOKED, wrote down what they found, and then re-pinned. Bumping a
baseline without an acknowledgement whose new_sha256 matches it is itself a
test failure, so the record cannot be skipped by editing one number.

DOES NOT: touch any registration's status. Nothing in this module writes to
cross_sectional_forward_validation_registrations, and a hash mismatch is a
red test, never a status transition.

THE HOLE THAT WAS IN THAT LAST PARAGRAPH UNTIL 2026-09-05
========================================================
The sentence above was true only of a WRONG acknowledgement. The first
version of unrecorded_baseline_bumps() looked up a dependency's
acknowledgements and, finding none, wrote

    if not acks:
        continue  # never moved; the baseline is the original capture

— reading "no acknowledgement" as "nothing ever moved". So the cheapest way
to silence a red drift test was also the only one nothing caught: re-run the
refresh script, take the new hash, write NO acknowledgement at all. A wrong
acknowledgement failed; the absence of one passed. Found while exercising the
manifest during lazy_prices' cost-basis switch (26d1ce1), flagged there
rather than fixed, because closing it needs an answer to "compared against
WHAT baseline?" and that is a schema decision, not a one-line patch.

THE ANSWER, and it is deliberately the boring one: every pinned dependency
now also carries `original_sha256`, the hash it was FIRST pinned to. The
refresh script carries that field forward VERBATIM and never rewrites it
(see its `originals` handling), so it is the one hash in the file a re-pin
does not touch. baseline_chain_break() then walks

    original_sha256 --(ack 1: old -> new)--> ... --(ack n)--> sha256

and fails unless every link matches: each acknowledgement's old_sha256 must
be exactly where the chain currently stands, and the last one's new_sha256
must be exactly the pinned baseline. A re-pin with NO acknowledgement now
leaves the chain sitting at original_sha256 while the baseline has moved,
which is a break; a re-pin with a wrong acknowledgement is a break at that
link; a re-pin WITH a correct one passes, which is the whole point.

Acknowledgements are walked in MANIFEST ORDER, not by date. They are
append-only (see Acknowledgement's docstring) and two entries written the
same day carry the same date string, so file order is the only total order
the file actually has.

WHAT THIS STILL DOES NOT DEFEND AGAINST, stated rather than implied: someone
who edits original_sha256 itself, or deletes the acknowledgements, or hand-
writes a chain that never happened. Nothing self-contained in a single JSON
file can. What it now catches is the ACCIDENT and the SHORTCUT — re-pinning
because the test was red and the acknowledgement felt like paperwork — which
is what actually happens and what actually happened here. Deleting the field
is not a quiet escape either: load_manifest() REFUSES a dependency with no
original_sha256 rather than defaulting it to the current baseline, because
defaulting it would make "delete one line" the new version of this same hole.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = Path(__file__).resolve().parent / "live_registration_dependencies.json"
SCHEMA = "live_registration_dependencies/v1"

REFRESH_COMMAND = (
    "./venv/bin/python data/research_runs/refresh_live_registration_dependencies.py"
)


class DependencyManifestError(ValueError):
    """The manifest is unusable as a drift record. Loud, never a warning —
    a half-read manifest would report "no drift" for the entries it failed
    to parse, which is the one answer it must never give wrongly."""


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class Acknowledgement:
    """One recorded look at a dependency that moved. Append-only: entries are
    never edited or removed, so the history of what was re-verified and what
    it found stays readable."""

    date: str
    dependency: str
    old_sha256: str
    new_sha256: str
    commit: str
    reverified: str  # what was actually re-run or re-derived
    finding: str  # what it showed, INCLUDING "nothing changed"


@dataclass(frozen=True)
class Dependency:
    path: str
    sha256: str  # the CURRENT pinned baseline; a re-pin moves this
    why: str
    # The hash this path was FIRST pinned to. Written once, carried forward
    # verbatim by every regeneration, and never rewritten by a re-pin — that
    # immutability is the entire reason a missing acknowledgement is now
    # detectable at all (see the module docstring). Equal to `sha256` for any
    # dependency that has never moved.
    original_sha256: str = ""

    def absolute(self) -> Path:
        return BACKEND_ROOT / self.path

    def current_sha256(self) -> str | None:
        target = self.absolute()
        return file_sha256(target) if target.is_file() else None


def baseline_chain_break(dep: Dependency, acknowledgements: list[Acknowledgement]) -> str | None:
    """None when `dep`'s pinned baseline is reachable from its
    original_sha256 by the given acknowledgements; otherwise a sentence
    naming the exact transition that nobody recorded.

    `acknowledgements` is every entry naming this dependency's path, in
    manifest order. See the module docstring for why order and not date.

    THE TWO WAYS THIS RETURNS A REASON, and both were real failure modes:
      * a link does not match — an acknowledgement claims to move the file
        FROM a hash the chain is not standing on, or the last one lands
        somewhere other than the pinned baseline. This is the case the
        original implementation already caught.
      * the chain never leaves original_sha256 while the baseline has moved
        — i.e. the file was re-pinned with NO acknowledgement at all. This is
        the case it did not catch, and the one this function exists for."""
    expected = dep.original_sha256
    for i, ack in enumerate(acknowledgements, start=1):
        if ack.old_sha256 != expected:
            return (
                f"{dep.path}: acknowledgement {i} ({ack.date}, commit {ack.commit}) records "
                f"old_sha256 {ack.old_sha256[:12]}… but the chain from the original pin stands "
                f"at {expected[:12]}… — the acknowledgements do not describe the transitions "
                "this baseline actually made."
            )
        expected = ack.new_sha256
    if expected != dep.sha256:
        if not acknowledgements:
            return (
                f"{dep.path}: pinned to {dep.sha256[:12]}… but first pinned to "
                f"{dep.original_sha256[:12]}… and NOT ONE acknowledgement names this path. A "
                "baseline was re-pinned with no record of what the change did. Write the "
                f"acknowledgement for {dep.original_sha256[:12]}… -> {dep.sha256[:12]}… — that "
                "record is the mechanism, not paperwork around it."
            )
        return (
            f"{dep.path}: pinned to {dep.sha256[:12]}… but its acknowledgement chain ends at "
            f"{expected[:12]}… — no acknowledgement records the transition {expected[:12]}… -> "
            f"{dep.sha256[:12]}…"
        )
    return None


@dataclass(frozen=True)
class RegistrationDependencies:
    family_key: str
    pattern_id: str
    module_path: str
    trace: str
    dependencies: tuple[Dependency, ...]
    acknowledgements: tuple[Acknowledgement, ...]

    def drift(self) -> list[tuple[Dependency, str | None]]:
        """[(dependency, current_hash_or_None)] for every dependency whose
        content no longer matches its pinned baseline. A None current hash
        means the file is GONE, which is drift of the loudest kind."""
        moved = []
        for dep in self.dependencies:
            current = dep.current_sha256()
            if current != dep.sha256:
                moved.append((dep, current))
        return moved

    def acknowledgements_for(self, path: str) -> list[Acknowledgement]:
        """This registration's acknowledgements naming `path`, in manifest
        order (append-only; see Acknowledgement)."""
        return [ack for ack in self.acknowledgements if ack.dependency == path]

    def unrecorded_baseline_bumps(self) -> list[tuple[Dependency, str]]:
        """[(dependency, why)] for every dependency of THIS registration whose
        pinned baseline is not reachable from its original_sha256 by its own
        acknowledgements.

        Covers both shapes of the failure: a re-pin recorded WRONGLY, and a
        re-pin recorded NOT AT ALL. The second used to pass — see the module
        docstring's "THE HOLE THAT WAS IN THAT LAST PARAGRAPH"."""
        bad: list[tuple[Dependency, str]] = []
        for dep in self.dependencies:
            reason = baseline_chain_break(dep, self.acknowledgements_for(dep.path))
            if reason is not None:
                bad.append((dep, reason))
        return bad


@dataclass(frozen=True)
class DependencyManifest:
    captured_at: str
    hash_algorithm: str
    shared: tuple[Dependency, ...]
    registrations: tuple[RegistrationDependencies, ...]

    def shared_acknowledgements_for(self, path: str) -> list[Acknowledgement]:
        """Every registration's acknowledgements naming a SHARED-tick-path
        file, concatenated in (registration order, entry order).

        WHY THE UNION. shared_tick_path entries carry no acknowledgements list
        of their own in schema v1, so a shared file's acknowledgement is filed
        under whichever registration's work moved it — 26d1ce1 filed
        cross_sectional_forward_registry.py's under lazy_prices, and said in
        the entry itself that the shared path was consequently unguarded.
        Reading the union is what closes that half of the gap without a
        schema break: the record exists, it just does not live where a
        per-registration walk would look."""
        found: list[Acknowledgement] = []
        for reg in self.registrations:
            found.extend(reg.acknowledgements_for(path))
        return found

    def shared_baseline_bumps(self) -> list[tuple[Dependency, str]]:
        """The same chain check as RegistrationDependencies.unrecorded_
        baseline_bumps(), for the shared tick path — the files EVERY live
        registration runs through, where an unrecorded re-pin is worse rather
        than better."""
        bad: list[tuple[Dependency, str]] = []
        for dep in self.shared:
            reason = baseline_chain_break(dep, self.shared_acknowledgements_for(dep.path))
            if reason is not None:
                bad.append((dep, reason))
        return bad

    def by_key(self, family_key: str) -> RegistrationDependencies:
        for reg in self.registrations:
            if reg.family_key == family_key:
                return reg
        raise DependencyManifestError(f"no manifest entry for family_key {family_key!r}")

    def all_dependencies(self) -> dict[str, Dependency]:
        """path -> Dependency, shared entries plus every registration's. A
        path pinned in two places must be pinned to the SAME hash; that is
        checked here rather than left to produce a confusing per-entry
        failure later."""
        merged: dict[str, Dependency] = {}
        for dep in self.shared:
            merged[dep.path] = dep
        for reg in self.registrations:
            for dep in reg.dependencies:
                existing = merged.get(dep.path)
                if existing is not None and existing.sha256 != dep.sha256:
                    raise DependencyManifestError(
                        f"{dep.path} is pinned to two different hashes "
                        f"({existing.sha256[:12]}… and {dep.sha256[:12]}…) — regenerate with "
                        f"{REFRESH_COMMAND}"
                    )
                if existing is not None and existing.original_sha256 != dep.original_sha256:
                    # Two entries for one path that disagree about where it
                    # STARTED would let a bump be laundered through whichever
                    # copy the chain check happened to read.
                    raise DependencyManifestError(
                        f"{dep.path} records two different original_sha256 values "
                        f"({existing.original_sha256[:12]}… and {dep.original_sha256[:12]}…) — "
                        f"regenerate with {REFRESH_COMMAND}"
                    )
                merged[dep.path] = dep
        return merged


def _dep(payload: dict, where: str) -> Dependency:
    for key in ("path", "sha256", "why"):
        if key not in payload:
            raise DependencyManifestError(f"{where}: dependency missing {key!r}")
    if "original_sha256" not in payload:
        # REFUSED, NOT DEFAULTED. Defaulting it to `sha256` would restore
        # exactly the hole this field closes: deleting one line would once
        # again make a re-pin look like a file that never moved.
        raise DependencyManifestError(
            f"{where}: {payload['path']} has no 'original_sha256'. That field is the hash the "
            "path was FIRST pinned to and it is what makes a re-pin without an acknowledgement "
            f"detectable at all — it is never defaulted. Regenerate with {REFRESH_COMMAND}, "
            "which carries it forward verbatim."
        )
    for key in ("sha256", "original_sha256"):
        if len(payload[key]) != 64:
            raise DependencyManifestError(f"{where}: {payload['path']} has a malformed {key}")
    return Dependency(
        path=payload["path"],
        sha256=payload["sha256"],
        why=payload["why"],
        original_sha256=payload["original_sha256"],
    )


def _ack(payload: dict, where: str) -> Acknowledgement:
    required = ("date", "dependency", "old_sha256", "new_sha256", "commit", "reverified", "finding")
    for key in required:
        if key not in payload or not str(payload[key]).strip():
            raise DependencyManifestError(
                f"{where}: acknowledgement missing or empty {key!r}. An acknowledgement with no "
                "record of what was re-verified is not an acknowledgement."
            )
    return Acknowledgement(**{k: payload[k] for k in required})


def load_manifest(path: Path | None = None) -> DependencyManifest:
    target = path or MANIFEST_PATH
    try:
        payload = json.loads(target.read_text())
    except FileNotFoundError as exc:
        raise DependencyManifestError(
            f"{target} is missing. It is a TRACKED governance artifact — regenerate it with "
            f"{REFRESH_COMMAND} and commit it."
        ) from exc
    except ValueError as exc:
        raise DependencyManifestError(f"{target} is not readable JSON: {exc}") from exc

    if payload.get("schema") != SCHEMA:
        raise DependencyManifestError(
            f"{target} declares schema {payload.get('schema')!r}, this module reads {SCHEMA!r}"
        )
    if payload.get("hash_algorithm") != "sha256":
        raise DependencyManifestError(
            f"{target} declares hash_algorithm {payload.get('hash_algorithm')!r}; only sha256 is "
            "implemented, and silently hashing with something else would make every comparison "
            "meaningless."
        )

    shared = tuple(_dep(d, f"{target}:shared") for d in payload.get("shared_tick_path", []))
    registrations = []
    for key, entry in sorted(payload.get("registrations", {}).items()):
        where = f"{target}:registrations.{key}"
        registrations.append(
            RegistrationDependencies(
                family_key=entry["family_key"],
                pattern_id=entry["pattern_id"],
                module_path=entry["module_path"],
                trace=entry.get("trace", ""),
                dependencies=tuple(_dep(d, where) for d in entry.get("dependencies", [])),
                acknowledgements=tuple(
                    _ack(a, where) for a in entry.get("acknowledgements", [])
                ),
            )
        )
    if not registrations:
        raise DependencyManifestError(f"{target} pins no registrations at all")

    return DependencyManifest(
        captured_at=str(payload.get("captured_at", "unknown")),
        hash_algorithm="sha256",
        shared=shared,
        registrations=tuple(registrations),
    )
