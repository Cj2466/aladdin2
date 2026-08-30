"""Create the two 2026-08-30 quality forward-validation registrations.

Kept in backend/ ROOT, not a subdirectory: a confirmed environment bug makes
`import app` from a script inside a subdirectory of a worktree resolve to the
MAIN worktree's package instead of this one.

Idempotent — it calls register_quality_forward_validations, which is itself
idempotent by (user_id, config_hash) — so re-running never resets an
accumulated clock. Prints what it found or created, and then re-reads the
rows straight out of the database as an independent confirmation that they
are really there.
"""

import json

from app.db import SessionLocal
from app.services.research_lab.quality_forward_registration import (
    register_quality_forward_validations,
)
from app.services.research_lab.system_account import get_or_create_system_user


def main() -> None:
    db = SessionLocal()
    try:
        # The ownership convention this project already uses for every
        # autonomously created row (ScreeningJob via AutonomousResearchRunner,
        # StrategyPortfolio via AutonomousPortfolioRunner): the system account
        # at settings.system_account_email. The listing endpoints already
        # surface system-owned rows to any authenticated user with
        # is_system=True, so this is what makes these registrations visible as
        # the project's, not one human's.
        system_user = get_or_create_system_user(db)
        print(f"system account: id={system_user.id} email={system_user.email}")

        for registration, created in register_quality_forward_validations(db, system_user.id):
            print(
                f"{'CREATED' if created else 'EXISTS '} id={registration.id} "
                f"{registration.family_key}/{registration.pattern_id} "
                f"status={registration.status} started_at={registration.started_at} "
                f"n_trials={registration.family_n_trials} "
                f"threshold={registration.min_trading_days_threshold} "
                f"spec_fp={registration.spec_fingerprint} "
                f"config_fp={registration.config_fingerprint} "
                f"config_hash={registration.config_hash}"
            )
    finally:
        db.close()

    # Independent re-read, on a fresh session, straight from the table.
    db = SessionLocal()
    try:
        from app.models.cross_sectional_forward_validation import (
            CrossSectionalForwardValidationRegistration as Row,
        )

        rows = db.query(Row).order_by(Row.id).all()
        print(f"\n--- {len(rows)} row(s) in cross_sectional_forward_validation_registrations ---")
        for r in rows:
            print(
                json.dumps(
                    {
                        "id": r.id,
                        "user_id": r.user_id,
                        "family_key": r.family_key,
                        "pattern_id": r.pattern_id,
                        "spec_family": r.spec_family,
                        "module_path": r.module_path,
                        "status": r.status,
                        "started_at": r.started_at.isoformat(),
                        "last_processed_date": (
                            r.last_processed_date.isoformat() if r.last_processed_date else None
                        ),
                        "family_n_trials": r.family_n_trials,
                        "min_trading_days_threshold": r.min_trading_days_threshold,
                        "n_forward_trading_days": r.n_forward_trading_days,
                        "n_formations": r.n_formations,
                        "spec_fingerprint": r.spec_fingerprint,
                        "config_fingerprint": r.config_fingerprint,
                        "config_hash": r.config_hash,
                        "spec_snapshot": json.loads(r.spec_snapshot_json),
                        "config_snapshot": json.loads(r.config_snapshot_json),
                        "rationale_chars": len(r.registration_rationale),
                        "carry_state": json.loads(r.carry_state_json),
                    },
                    indent=2,
                )
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
