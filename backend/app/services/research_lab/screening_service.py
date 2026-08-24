from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.screening_job import ScreeningJob
from app.models.user import User


def get_owned_screening_job(
    db: Session, screening_id: int, user: User, system_user_id: int | None = None
) -> ScreeningJob:
    """404 (not 403) whether missing or owned by someone else — same
    non-enumeration reasoning as get_owned_sweep_job. `system_user_id`,
    when provided, also permits read access to AutonomousResearchRunner's
    own jobs — visible to every logged-in user (not "owned" by any of
    them), never writable by anyone but the runner itself."""
    allowed_owner_ids = {user.id, system_user_id} - {None}
    job = db.execute(
        select(ScreeningJob).where(ScreeningJob.id == screening_id, ScreeningJob.user_id.in_(allowed_owner_ids))
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screening job not found")
    return job
