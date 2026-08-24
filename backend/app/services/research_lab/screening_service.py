from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.screening_job import ScreeningJob
from app.models.user import User


def get_owned_screening_job(db: Session, screening_id: int, user: User) -> ScreeningJob:
    """404 (not 403) whether missing or owned by someone else — same
    non-enumeration reasoning as get_owned_sweep_job."""
    job = db.execute(
        select(ScreeningJob).where(ScreeningJob.id == screening_id, ScreeningJob.user_id == user.id)
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screening job not found")
    return job
