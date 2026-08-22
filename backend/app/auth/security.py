import hashlib
import secrets
from datetime import datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.time_utils import utcnow_naive

SESSION_LIFETIME = timedelta(days=14)
# Short — a leaked reset link grants account takeover, unlike a session.
PASSWORD_RESET_LIFETIME = timedelta(hours=1)
# Longer than the reset window since it's lower-stakes (proves email
# ownership, doesn't grant access to an existing account's data).
EMAIL_VERIFICATION_LIFETIME = timedelta(hours=48)

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    return True


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Sessions are stored hashed so a DB dump/leak doesn't hand over live
    sessions, mirroring the password-hash reasoning."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry() -> datetime:
    return utcnow_naive() + SESSION_LIFETIME


def password_reset_expiry() -> datetime:
    return utcnow_naive() + PASSWORD_RESET_LIFETIME


def email_verification_expiry() -> datetime:
    return utcnow_naive() + EMAIL_VERIFICATION_LIFETIME
