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
    sha256: str
    why: str

    def absolute(self) -> Path:
        return BACKEND_ROOT / self.path

    def current_sha256(self) -> str | None:
        target = self.absolute()
        return file_sha256(target) if target.is_file() else None


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

    def unrecorded_baseline_bumps(self, *, original: RegistrationDependencies | None = None):
        """Dependencies whose pinned baseline is not the ORIGINAL capture and
        whose latest acknowledgement does not name that baseline as its
        new_sha256 — i.e. someone re-pinned without recording the look.

        `original` is unused today (the first capture IS the current file) and
        is accepted so a future caller can diff against a git-historical
        manifest without changing this signature."""
        del original
        acked_by_dep: dict[str, list[Acknowledgement]] = {}
        for ack in self.acknowledgements:
            acked_by_dep.setdefault(ack.dependency, []).append(ack)
        bad = []
        for dep in self.dependencies:
            acks = acked_by_dep.get(dep.path)
            if not acks:
                continue  # never moved; the baseline is the original capture
            if acks[-1].new_sha256 != dep.sha256:
                bad.append((dep, acks[-1]))
        return bad


@dataclass(frozen=True)
class DependencyManifest:
    captured_at: str
    hash_algorithm: str
    shared: tuple[Dependency, ...]
    registrations: tuple[RegistrationDependencies, ...]

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
                merged[dep.path] = dep
        return merged


def _dep(payload: dict, where: str) -> Dependency:
    for key in ("path", "sha256", "why"):
        if key not in payload:
            raise DependencyManifestError(f"{where}: dependency missing {key!r}")
    if len(payload["sha256"]) != 64:
        raise DependencyManifestError(f"{where}: {payload['path']} has a malformed sha256")
    return Dependency(path=payload["path"], sha256=payload["sha256"], why=payload["why"])


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
