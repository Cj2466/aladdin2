"""Registering a cross-sectional spec for forward validation.

Mirrors forward_validation_service.py function-for-function (config hash,
idempotent register-or-get, owned-lookup with a 404-not-403 convention) and
REUSES its constants and its underperformance rule rather than restating
them — MIN_FORWARD_VALIDATION_TRADING_DAYS, MIN_FORWARD_DAYS_FOR_SHARPE and
check_underperformance are all imported from there, so the two paths can
never drift on what "enough forward data" or "underperforming" means.

The one place this file deliberately does NOT simply reuse the pairs number
is the graduation threshold — see graduation_threshold_for.
"""

import hashlib
import json
from datetime import date
from typing import Protocol

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cross_sectional_forward_validation import (
    CrossSectionalForwardValidationRegistration,
)
from app.models.user import User
from app.services.forward_validation_service import (
    MIN_FORWARD_VALIDATION_TRADING_DAYS,
)
from app.services.research_lab.cross_sectional import CrossSectionalSpec
from app.services.research_lab.cross_sectional_forward import (
    initial_state_json,
    validate_spec_is_forward_tickable,
)
from app.services.research_lab.cross_sectional_forward_registry import (
    CrossSectionalFamilyAdapter,
    config_fingerprint,
    config_identity,
    resolve_spec,
    spec_fingerprint,
    spec_identity,
)

# How many COMPLETE holding periods a cross-sectional registration must
# accumulate before it can graduate, on top of the pairs path's day floor.
#
# WHY THE PAIRS NUMBER ALONE IS THE WRONG FLOOR HERE. A pairs/momentum
# registration re-decides its position every single day, so 126 forward days
# is 126 decisions. A cross-sectional spec that reforms every holding_days
# rows makes ONE decision per formation: at the Crypto family's 180-row hold,
# 126 forward days would graduate a registration in the MIDDLE OF ITS FIRST
# HOLD — a "track record" of one unfinished bet, and of zero completed
# round trips through the strategy's own formation/turnover cycle. Reporting
# that as forward-validated would be exactly the kind of manufactured
# positive this project's overnight-autonomy guardrail exists to prevent.
#
# 2 is a floor, and a thin one, and this must be said wherever it is
# surfaced: two independent formations cannot resolve a signal. What
# graduation means here is only "enough REAL out-of-sample data has now
# accumulated to be worth looking at", never "this works" — the same thing
# MIN_FORWARD_VALIDATION_TRADING_DAYS' own docstring says about spanning
# regimes ("explicitly a floor, not a guarantee"). The evidence a reader
# should weigh is the realized daily series over those days, with the
# formation count disclosed beside it, not the status word.
MIN_FORWARD_COMPLETE_HOLDS = 2

# The one status a registration can only reach by an explicit human decision
# to STOP SPENDING CALENDAR TIME on a hypothesis — never by anything the
# runner computes.
#
# The other three terminal-ish statuses are all EARNED by the forward data:
# "forward_validated" by accumulating enough of it, "underperforming" by the
# trailing-window rule, "spec_drift" by the fingerprints moving. "retired" is
# the opposite kind of event: the forward record is fine, the QUESTION was
# found not to be worth asking, so the clock is stopped from outside.
#
# WHY A STATUS AND NOT A DELETE. Deleting the row would destroy the
# accumulated day/formation history and, worse, the written record that the
# registration was ever made — and a forward-validation programme that can
# silently un-make its own decisions is not one whose surviving rows mean
# anything. A retired row keeps every field it had, keeps its rationale
# verbatim, and gains a dated closing entry saying why it was withdrawn.
#
# It is deliberately absent from CrossSectionalForwardValidationRunner.
# ACTIVE_STATUSES, so a retired row is never loaded and never ticks again.
# Un-retiring is a human decision (a new, separately argued registration),
# exactly as un-parking a "spec_drift" row is.
RETIRED_STATUS = "retired"


class _HasRegistrationFingerprints(Protocol):
    """What the drift checks below actually read. Satisfied both by
    CrossSectionalForwardValidationRegistration (the ORM row) and by
    CrossSectionalForwardValidationRunner's plain thread-boundary snapshot,
    which is the point — the runner must not have to re-open a session just
    to run a comparison it already holds every input for."""

    family_key: str
    pattern_id: str
    started_at: date
    spec_fingerprint: str
    config_fingerprint: str
    spec_snapshot_json: str
    config_snapshot_json: str


def graduation_threshold_for(spec: CrossSectionalSpec) -> int:
    """max(the pairs path's day floor, MIN_FORWARD_COMPLETE_HOLDS complete
    holds). Never below MIN_FORWARD_VALIDATION_TRADING_DAYS, so a
    short-holding cross-sectional family inherits the existing floor
    unchanged; above it exactly when the holding period demands it."""
    return max(MIN_FORWARD_VALIDATION_TRADING_DAYS, MIN_FORWARD_COMPLETE_HOLDS * spec.holding_days)


def compute_cross_sectional_forward_validation_config_hash(
    family_key: str, pattern_id: str, spec_hash: str, config_hash: str
) -> str:
    """Persistent identity for an ongoing registration — deliberately NOT
    date-folded, and deliberately excluding user_id, on exactly the reasoning
    compute_forward_validation_config_hash documents for the pairs path.

    Built from the REFERENCE (family_key, pattern_id) plus the two
    fingerprints, so two registrations of the same pattern_id under
    materially different market assumptions are correctly distinct rows,
    while a re-registration of the identical thing is correctly the same
    row."""
    payload = {
        "family_key": family_key,
        "pattern_id": pattern_id,
        "spec_fingerprint": spec_hash,
        "config_fingerprint": config_hash,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def register_or_get_cross_sectional_forward_validation(
    db: Session,
    *,
    user_id: int,
    family_key: str,
    pattern_id: str,
    rationale: str,
    started_at: date | None = None,
) -> tuple[CrossSectionalForwardValidationRegistration, bool]:
    """Idempotent create-or-return — never resets accumulated progress on an
    existing registration, exactly like the pairs path. Returns
    (registration, created).

    The spec is RESOLVED, not described: (family_key, pattern_id) is looked
    up in the family's own registry, so an unknown pattern_id raises rather
    than creating a row that refers to nothing. Anything the resolved spec
    or config cannot support forward (overlapping cohorts, delisting
    imputation) raises here too — before a clock starts, never mid-tick.

    `rationale` is required, with no default. A forward-validation slot is a
    claim that this particular hypothesis was worth real calendar time, and
    a row that cannot say why it was created cannot be told apart from an
    automatic one.

    `started_at` defaults to today and exists as a parameter only so tests
    can be deterministic — production callers pass nothing."""
    if not rationale or not rationale.strip():
        raise ValueError(
            "A cross-sectional forward-validation registration requires a written rationale: it is a "
            "claim on real calendar time and must record why this hypothesis, out of its family, was "
            "worth it."
        )

    adapter, spec = resolve_spec(family_key, pattern_id)
    config = adapter.build_config()
    validate_spec_is_forward_tickable(spec, config)

    spec_hash = spec_fingerprint(spec)
    cfg_hash = config_fingerprint(config)
    config_hash = compute_cross_sectional_forward_validation_config_hash(
        family_key, pattern_id, spec_hash, cfg_hash
    )

    existing = db.execute(
        select(CrossSectionalForwardValidationRegistration).where(
            CrossSectionalForwardValidationRegistration.user_id == user_id,
            CrossSectionalForwardValidationRegistration.config_hash == config_hash,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    registration = CrossSectionalForwardValidationRegistration(
        user_id=user_id,
        family_key=family_key,
        pattern_id=pattern_id,
        module_path=adapter.module_path,
        spec_family=spec.family,
        citation=spec.citation,
        universe_rule=adapter.universe_rule,
        family_n_trials=adapter.n_trials,
        config_hash=config_hash,
        spec_fingerprint=spec_hash,
        config_fingerprint=cfg_hash,
        spec_snapshot_json=json.dumps(spec_identity(spec), sort_keys=True),
        config_snapshot_json=json.dumps(config_identity(config), sort_keys=True),
        registration_rationale=rationale.strip(),
        status="in_progress",
        min_trading_days_threshold=graduation_threshold_for(spec),
        n_forward_trading_days=0,
        n_formations=0,
        started_at=started_at if started_at is not None else date.today(),
        carry_state_json=initial_state_json(),
        day_results_json="[]",
        formations_json="[]",
    )
    db.add(registration)
    db.commit()
    db.refresh(registration)
    return registration, True


def get_owned_cross_sectional_forward_validation_registration(
    db: Session, registration_id: int, user: User
) -> CrossSectionalForwardValidationRegistration:
    """404 (not 403) whether missing or owned by someone else — same
    non-enumeration reasoning as get_owned_forward_validation_registration."""
    registration = db.execute(
        select(CrossSectionalForwardValidationRegistration).where(
            CrossSectionalForwardValidationRegistration.id == registration_id,
            CrossSectionalForwardValidationRegistration.user_id == user.id,
        )
    ).scalar_one_or_none()
    if registration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cross-sectional forward validation registration not found",
        )
    return registration


def detect_spec_drift(
    registration: "_HasRegistrationFingerprints",
    adapter: CrossSectionalFamilyAdapter,
    spec: CrossSectionalSpec,
) -> str | None:
    """None if the live family still declares exactly what this row was
    registered against; otherwise a human-readable description of what
    moved. See the registry module docstring for why a drifted registration
    is parked rather than carried on with.

    Typed against a Protocol rather than the ORM class so the runner can
    pass its plain thread-boundary snapshot (which carries every field read
    here) instead of re-reading the row."""
    del adapter  # resolved by the caller; kept in the signature for call-site clarity
    live_spec = spec_fingerprint(spec)
    if live_spec != registration.spec_fingerprint:
        return (
            f"spec {registration.pattern_id} in family {registration.family_key} no longer matches the "
            f"definition registered on {registration.started_at}: registered "
            f"{registration.spec_snapshot_json}, live {json.dumps(spec_identity(spec), sort_keys=True)}"
        )
    return None


def detect_config_drift(
    registration: "_HasRegistrationFingerprints", config_hash_now: str, config_now: dict
) -> str | None:
    if config_hash_now != registration.config_fingerprint:
        return (
            f"family {registration.family_key}'s market config no longer matches the one registered on "
            f"{registration.started_at}: registered {registration.config_snapshot_json}, live "
            f"{json.dumps(config_now, sort_keys=True)}"
        )
    return None


__all__ = [
    "MIN_FORWARD_COMPLETE_HOLDS",
    "RETIRED_STATUS",
    "compute_cross_sectional_forward_validation_config_hash",
    "detect_config_drift",
    "detect_spec_drift",
    "get_owned_cross_sectional_forward_validation_registration",
    "graduation_threshold_for",
    "register_or_get_cross_sectional_forward_validation",
]
