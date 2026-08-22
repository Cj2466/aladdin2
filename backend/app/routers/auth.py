from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.auth.dependencies import SESSION_COOKIE_NAME, get_current_user
from app.auth.security import (
    email_verification_expiry,
    generate_session_token,
    hash_password,
    hash_token,
    password_reset_expiry,
    session_expiry,
    verify_password,
)
from app.config import settings
from app.db import get_db
from app.models.auth_session import AuthSession
from app.models.user import User
from app.models.user_token import UserToken
from app.rate_limit import limiter
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    UserOut,
    VerifyEmailRequest,
)
from app.services.email.resend_client import send_email
from app.time_utils import utcnow_naive

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_MAX_AGE_SECONDS = 14 * 24 * 60 * 60
INVALID_TOKEN_DETAIL = "Invalid or expired token"
GENERIC_EMAIL_SENT_MESSAGE = "If that email is registered, check your inbox for a link."


def _start_session(response: Response, db: Session, user: User) -> None:
    token = generate_session_token()
    db.add(AuthSession(user_id=user.id, token_hash=hash_token(token), expires_at=session_expiry()))
    db.commit()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite=settings.cookie_samesite,
        secure=settings.cookie_secure,
        max_age=COOKIE_MAX_AGE_SECONDS,
        path="/",
    )


def _invalidate_all_sessions(db: Session, user_id: int) -> None:
    db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))


def _invalidate_outstanding_tokens(db: Session, user_id: int, purpose: str) -> None:
    db.execute(
        update(UserToken)
        .where(
            UserToken.user_id == user_id,
            UserToken.purpose == purpose,
            UserToken.used_at.is_(None),
        )
        .values(used_at=utcnow_naive())
    )


def _issue_token(db: Session, user: User, purpose: str) -> str:
    _invalidate_outstanding_tokens(db, user.id, purpose)
    raw_token = generate_session_token()
    expires_at = (
        password_reset_expiry() if purpose == "password_reset" else email_verification_expiry()
    )
    db.add(
        UserToken(
            user_id=user.id, purpose=purpose, token_hash=hash_token(raw_token), expires_at=expires_at
        )
    )
    db.commit()
    return raw_token


def _consume_token(db: Session, raw_token: str, purpose: str) -> UserToken:
    record = db.execute(
        select(UserToken).where(
            UserToken.token_hash == hash_token(raw_token), UserToken.purpose == purpose
        )
    ).scalar_one_or_none()
    # Every failure mode — not found, expired, already used — returns the
    # exact same detail string. A different message per case would let a
    # caller distinguish "this token existed but expired" from "this token
    # never existed at all", an oracle for probing guesses.
    if record is None or record.used_at is not None or record.expires_at < utcnow_naive():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_TOKEN_DETAIL)
    record.used_at = utcnow_naive()
    return record


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def register(request: Request, payload: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    existing = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(email=payload.email, password_hash=hash_password(payload.password), is_verified=False)
    db.add(user)
    db.commit()
    db.refresh(user)

    raw_token = _issue_token(db, user, "email_verification")
    link = f"{settings.frontend_url}/?verify_token={raw_token}"
    send_email(
        user.email,
        "Verify your Aladdin2 email",
        f"Welcome to Aladdin2. Verify your email to activate your account:\n\n{link}\n\n"
        "This link expires in 48 hours.",
    )
    return RegisterResponse(email=user.email)


@router.post("/login", response_model=UserOut)
@limiter.limit("10/minute")
def login(
    request: Request, payload: LoginRequest, response: Response, db: Session = Depends(get_db)
) -> User:
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Check your inbox or request a new verification email.",
        )

    _start_session(response, db, user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        session = db.execute(
            select(AuthSession).where(AuthSession.token_hash == hash_token(token))
        ).scalar_one_or_none()
        if session is not None:
            db.delete(session)
            db.commit()
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("5/minute")
def forgot_password(
    request: Request, payload: ForgotPasswordRequest, db: Session = Depends(get_db)
) -> MessageResponse:
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if user is not None:
        raw_token = _issue_token(db, user, "password_reset")
        link = f"{settings.frontend_url}/?reset_token={raw_token}"
        send_email(
            user.email,
            "Reset your Aladdin2 password",
            f"Reset your password:\n\n{link}\n\nThis link expires in 1 hour. "
            "If you didn't request this, you can ignore this email.",
        )
    # Identical response whether or not the email exists — no enumeration.
    return MessageResponse(message=GENERIC_EMAIL_SENT_MESSAGE)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> None:
    record = _consume_token(db, payload.token, "password_reset")
    user = db.get(User, record.user_id)
    user.password_hash = hash_password(payload.new_password)
    _invalidate_outstanding_tokens(db, user.id, "password_reset")
    # A password reset is treated as a possible-compromise signal — every
    # existing session dies, everywhere, forcing a fresh login.
    _invalidate_all_sessions(db, user.id)
    db.commit()


@router.post("/verify-email", response_model=UserOut)
def verify_email(payload: VerifyEmailRequest, response: Response, db: Session = Depends(get_db)) -> User:
    record = _consume_token(db, payload.token, "email_verification")
    user = db.get(User, record.user_id)
    user.is_verified = True
    db.commit()
    db.refresh(user)
    # Verifying is itself strong proof of ownership via a flow already in
    # progress — no reason to make them re-enter a password immediately.
    _start_session(response, db, user)
    return user


@router.post("/resend-verification", response_model=MessageResponse)
@limiter.limit("5/minute")
def resend_verification(
    request: Request, payload: ResendVerificationRequest, db: Session = Depends(get_db)
) -> MessageResponse:
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if user is not None and not user.is_verified:
        raw_token = _issue_token(db, user, "email_verification")
        link = f"{settings.frontend_url}/?verify_token={raw_token}"
        send_email(
            user.email,
            "Verify your Aladdin2 email",
            f"Verify your email to activate your account:\n\n{link}\n\nThis link expires in 48 hours.",
        )
    return MessageResponse(message=GENERIC_EMAIL_SENT_MESSAGE)
