from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import SESSION_COOKIE_NAME, get_current_user
from app.auth.security import (
    generate_session_token,
    hash_password,
    hash_token,
    session_expiry,
    verify_password,
)
from app.config import settings
from app.db import get_db
from app.models.auth_session import AuthSession
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.auth import LoginRequest, RegisterRequest, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_MAX_AGE_SECONDS = 14 * 24 * 60 * 60


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


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def register(
    request: Request, payload: RegisterRequest, response: Response, db: Session = Depends(get_db)
) -> User:
    existing = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    _start_session(response, db, user)
    return user


@router.post("/login", response_model=UserOut)
@limiter.limit("10/minute")
def login(
    request: Request, payload: LoginRequest, response: Response, db: Session = Depends(get_db)
) -> User:
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

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
