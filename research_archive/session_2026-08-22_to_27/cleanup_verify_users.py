import sys
sys.path.insert(0, ".")
from app.db import SessionLocal
from app.models.user import User
from sqlalchemy import select

db = SessionLocal()
try:
    for email in ("verify-phase35@test.local", "aladdin2verifycheck@gmail.com"):
        u = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if u is not None:
            db.delete(u)
    db.commit()
    print("cleaned up")
finally:
    db.close()
