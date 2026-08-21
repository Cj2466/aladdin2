from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import hash_token
from app.db import get_db
from app.models.auth_session import AuthSession
from app.models.user import User
from app.time_utils import utcnow_naive

SESSION_COOKIE_NAME = "aladdin2_session"


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    unauthenticated = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise unauthenticated

    token_hash = hash_token(token)
    session = db.execute(
        select(AuthSession).where(AuthSession.token_hash == token_hash)
    ).scalar_one_or_none()
    if session is None or session.expires_at < utcnow_naive():
        raise unauthenticated

    user = db.get(User, session.user_id)
    if user is None:
        raise unauthenticated

    return user
