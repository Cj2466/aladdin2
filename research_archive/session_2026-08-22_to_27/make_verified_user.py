import sys
sys.path.insert(0, ".")
from app.db import SessionLocal
from app.models.user import User
from app.auth.security import hash_password
from sqlalchemy import select

db = SessionLocal()
try:
    existing = db.execute(select(User).where(User.email == "verify-phase35@test.local")).scalar_one_or_none()
    if existing is None:
        u = User(email="verify-phase35@test.local", password_hash=hash_password("TestPass123!"), is_verified=True)
        db.add(u)
        db.commit()
        print("created")
    else:
        print("already exists")
finally:
    db.close()
