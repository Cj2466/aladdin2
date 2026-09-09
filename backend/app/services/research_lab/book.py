"""THE PRE-REGISTERED BOOK — the equal-weight composite of every frozen spec in
Active or Dormant, with membership fixed by RULE on membership dates and
scored ONLY on days after inception.

WHY IT EXISTS (measured 2026-09-09). At a fixed annualized Sharpe the time to
certify an edge does not depend on how finely it is sampled; a true 0.5 needs
~222 years, a true 1.0 ~14, a true 2.0 ~2 (intraday_data_scoping_2026-09-09,
re-derived with dsr_power). The only honest way to a HIGHER annualized
Sharpe is combining independent edges: M members of Sharpe s at pairwise
correlation rho give about s*sqrt(M/(1+(M-1)*rho)). That is CLAUDE.md §7's
"many small micro-edges" thesis as arithmetic, and this module is its test.

WHY IT IS NOT THE REJECTED "OPTION D". Choosing members in sample lets pure
noise raise a portfolio's in-sample Sharpe — book_gates.py GB2 measured 2.37
for 30 null specs picked by in-sample Sharpe from 200. The book avoids that
entirely: membership is a mechanical function of pool state on
pre-declared dates, and the composite is scored only on returns after
inception (GB2: 0.029 false promotion post-inception, at a 0.05 bar). No
member selection touches the scored segment, so there is nothing to deflate
and the statistic is the same N=1 PSR_ext the Dormant pool uses, with the
same look schedule and the same calibrated boundaries (dormant_pool.C_K).

THE RULE, in full: data/research_runs/book_2026-09-09/BOOK_PREREGISTRATION.md
(committed before the gates were run) and its gate output.

WHAT PROMOTION IS. The book earns an Active forward-tracking slot of its
own. NOT capital. If most members are null the book fails its looks
(GB4: 80% null members -> 8% promotion in ten years) and that is the
finding about the research process, reported as such.

WHAT THIS MODULE DOES NOT DO. It does not fetch anyone's returns — the
Dormant re-scorer and the forward registrations do — and it does not decide
inception: the manifest ships with inception = null, an owner decision.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.services.research_lab.dormant_pool import (
    BUCKET_LOW,
    C_K,
    K_MAX,
    DormantEntry,
    LookResult,
    assign_bucket,
    evaluate_look,
    lag1_autocorrelation,
)
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR

SCHEMA = "book/v1"
MANIFEST_PATH = Path(__file__).resolve().parents[3] / "data" / "research_runs" / "book_2026-09-09" / "book_manifest.json"


class BookError(ValueError):
    """The book manifest or a composition input is unusable. Raised, never
    defaulted, for the same reason as every governance artifact here."""


@dataclass(frozen=True)
class MembershipSnapshot:
    """One membership date's member list. Append-only in the manifest: a
    later snapshot may add or (on mechanism closure only) drop a member; an
    earlier snapshot is never edited."""

    membership_date: date
    members: tuple[str, ...]  # "family_key/pattern_id", sorted
    source: str  # where the Active/Dormant state was read from, for the record


@dataclass(frozen=True)
class BookManifest:
    inception: date | None
    phi_hat_pre_inception: float | None
    bucket: str | None
    snapshots: tuple[MembershipSnapshot, ...]

    def members_on(self, day: date) -> tuple[str, ...]:
        """The member list in force on `day`: the latest snapshot at or
        before it. Empty before the first snapshot."""
        current: tuple[str, ...] = ()
        for snap in self.snapshots:
            if snap.membership_date <= day:
                current = snap.members
        return current


def member_key(family_key: str, pattern_id: str) -> str:
    return f"{family_key}/{pattern_id}"


def compose_book(member_returns: dict[str, pd.Series], manifest: BookManifest) -> pd.Series:
    """The book's realized net daily return: on each date, the equal-weight
    mean over the members IN FORCE on that date that have a return that day.
    Members absent on a day (between formations, off-calendar) simply do not
    count and the weights renormalize — no fill, no scaling, no estimate.

    `member_returns` maps member_key -> that member's realized net per-period
    returns (any date range; only dates after inception and while the member
    is in force are used)."""
    if manifest.inception is None:
        raise BookError("the book has no inception date; nothing can be composed before the owner declares one")
    if not manifest.snapshots:
        raise BookError("the book has no membership snapshot")
    frames = []
    for key, series in member_returns.items():
        s = pd.Series(series, dtype=float).dropna()
        s.index = pd.DatetimeIndex(s.index)
        s = s[s.index > pd.Timestamp(manifest.inception)]
        if s.empty:
            continue
        in_force = np.array([key in manifest.members_on(ts.date()) for ts in s.index])
        s = s[in_force]
        if not s.empty:
            frames.append(s.rename(key))
    if not frames:
        return pd.Series(dtype=float)
    wide = pd.concat(frames, axis=1)
    counts = wide.notna().sum(axis=1)
    composite = wide.mean(axis=1, skipna=True)[counts > 0]
    return composite.sort_index()


def pre_inception_bucket(member_returns: dict[str, pd.Series], manifest: BookManifest) -> tuple[float, str]:
    """The book's autocorrelation bucket, fixed from the composite of the
    FIRST snapshot's members over data strictly BEFORE inception — so the
    bucket cannot be chosen on the scored segment. Same rule as a Dormant
    entry's phi_hat_entry."""
    if manifest.inception is None or not manifest.snapshots:
        raise BookError("inception and a first snapshot are needed before the bucket can be fixed")
    first = manifest.snapshots[0].members
    frames = []
    for key in first:
        if key not in member_returns:
            continue
        s = pd.Series(member_returns[key], dtype=float).dropna()
        s.index = pd.DatetimeIndex(s.index)
        s = s[s.index <= pd.Timestamp(manifest.inception)]
        if not s.empty:
            frames.append(s.rename(key))
    if not frames:
        raise BookError("no pre-inception returns for any first-snapshot member; the bucket cannot be measured")
    composite = pd.concat(frames, axis=1).mean(axis=1, skipna=True).dropna()
    if len(composite) < 3 or float(composite.std(ddof=1)) == 0:
        raise BookError("pre-inception composite too short or degenerate to measure autocorrelation")
    phi = lag1_autocorrelation(composite)
    return phi, assign_bucket(phi)


def book_entry(manifest: BookManifest) -> DormantEntry:
    """The book expressed as a Dormant-pool entry so evaluate_look can score
    it with no second code path: same boundary table, same look schedule."""
    if manifest.inception is None or manifest.bucket is None or manifest.phi_hat_pre_inception is None:
        raise BookError("the book needs inception, phi_hat_pre_inception and bucket fixed before it can be scored")
    if manifest.bucket not in C_K:
        raise BookError(f"unknown bucket {manifest.bucket!r}")
    return DormantEntry(
        family_key="book",
        pattern_id="equal_weight_active_plus_dormant",
        spec_fingerprint="rule: BOOK_PREREGISTRATION.md section 2",
        config_fingerprint="rule: BOOK_PREREGISTRATION.md section 3",
        window_end_at_entry=manifest.inception,
        entered_at=manifest.inception,
        periods_per_year=float(TRADING_DAYS_PER_YEAR),
        phi_hat_entry=manifest.phi_hat_pre_inception,
        bucket=manifest.bucket,
        pit_ok=True,
        rescorable=True,
        mechanism_review="not applicable: the book is a test of the research process, not of one mechanism",
        entry_rationale="BOOK_PREREGISTRATION.md section 1",
    )


def score_book(member_returns: dict[str, pd.Series], manifest: BookManifest) -> LookResult:
    composite = compose_book(member_returns, manifest)
    return evaluate_look(composite, book_entry(manifest))


# --- manifest ---------------------------------------------------------------


def parse_manifest(payload: dict[str, Any], where: str = "<book manifest>") -> BookManifest:
    if payload.get("schema") != SCHEMA:
        raise BookError(f"{where}: declares schema {payload.get('schema')!r}, this module reads {SCHEMA!r}")
    inception_raw = payload.get("inception")
    inception = date.fromisoformat(inception_raw) if inception_raw else None
    phi = payload.get("phi_hat_pre_inception")
    bucket = payload.get("bucket")
    if (phi is None) != (bucket is None):
        raise BookError(f"{where}: phi_hat_pre_inception and bucket must be set together")
    if bucket is not None:
        if bucket not in C_K:
            raise BookError(f"{where}: bucket must be one of {sorted(C_K)}")
        if assign_bucket(float(phi)) != bucket:
            raise BookError(f"{where}: bucket {bucket!r} disagrees with phi_hat_pre_inception={phi}; it is computed, never chosen")
    snaps_raw = payload.get("snapshots")
    if not isinstance(snaps_raw, list):
        raise BookError(f"{where}: 'snapshots' must be a list")
    snaps: list[MembershipSnapshot] = []
    last: date | None = None
    for i, raw in enumerate(snaps_raw):
        sub = f"{where}.snapshots[{i}]"
        try:
            d = date.fromisoformat(raw["membership_date"])
        except (KeyError, TypeError, ValueError) as exc:
            raise BookError(f"{sub}: membership_date must be an ISO date") from exc
        if last is not None and d <= last:
            raise BookError(f"{sub}: membership dates must strictly increase (append-only)")
        last = d
        members = raw.get("members")
        if not isinstance(members, list) or any(not isinstance(m, str) or "/" not in m for m in members):
            raise BookError(f"{sub}: members must be a list of 'family_key/pattern_id' strings")
        if len(set(members)) != len(members):
            raise BookError(f"{sub}: duplicate member")
        source = raw.get("source")
        if not isinstance(source, str) or not source.strip():
            raise BookError(f"{sub}: source is required")
        if inception is not None and d < inception:
            raise BookError(f"{sub}: membership date {d} precedes inception {inception}")
        snaps.append(MembershipSnapshot(d, tuple(sorted(members)), source))
    if inception is not None and (not snaps or snaps[0].membership_date != inception):
        raise BookError(f"{where}: the first snapshot must be dated exactly at inception {inception}")
    return BookManifest(inception=inception, phi_hat_pre_inception=None if phi is None else float(phi), bucket=bucket, snapshots=tuple(snaps))


def load_manifest(path: Path | None = None) -> BookManifest:
    path = path or MANIFEST_PATH
    return parse_manifest(json.loads(path.read_text()), str(path))


__all__ = [
    "BUCKET_LOW", "K_MAX", "SCHEMA", "BookError", "BookManifest", "MembershipSnapshot",
    "book_entry", "compose_book", "load_manifest", "member_key", "parse_manifest",
    "pre_inception_bucket", "score_book",
]
