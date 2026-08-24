import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.config import settings
from app.models.user import User


def get_system_user_id(db: Session) -> int | None:
    """Read-only — never creates a row, so a GET endpoint checking for
    system-owned jobs never has the side effect of provisioning the
    account. Returns None if AutonomousResearchRunner hasn't ticked yet
    (e.g. a brand-new deployment)."""
    return db.execute(select(User.id).where(User.email == settings.system_account_email)).scalar_one_or_none()


def get_or_create_system_user(db: Session) -> User:
    """Idempotent get-or-create for the account that owns autonomously
    created ScreeningJob rows. is_verified is set directly rather than
    through the email-verification flow — this account never logs in, so
    there's no inbox to click a link from. password_hash is a random
    value nobody ever records, run through the same hasher every real
    account uses, purely to satisfy the NOT NULL/format constraint."""
    existing = db.execute(select(User).where(User.email == settings.system_account_email)).scalar_one_or_none()
    if existing is not None:
        return existing

    user = User(
        email=settings.system_account_email,
        password_hash=hash_password(secrets.token_urlsafe(32)),
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
