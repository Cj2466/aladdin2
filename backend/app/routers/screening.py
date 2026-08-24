from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models.screening_candidate import ScreeningCandidate
from app.models.screening_job import ScreeningJob
from app.models.user import User
from app.schemas.screening import (
    ScreeningCandidateOut,
    ScreeningJobCreateRequest,
    ScreeningJobDetailOut,
    ScreeningJobOut,
)
from app.services.research_lab import ticker_universe
from app.services.research_lab.screening import build_screening_methodology_note
from app.services.research_lab.screening_service import get_owned_screening_job

router = APIRouter(prefix="/api/research-lab/screening", tags=["research-lab"])


def _to_job_out(job: ScreeningJob) -> ScreeningJobOut:
    return ScreeningJobOut(
        id=job.id,
        strategy_name=job.strategy_name,
        universe_size=job.universe_size,
        n_tickers_resolved=job.n_tickers_resolved,
        n_candidates_found=job.n_candidates_found,
        status=job.status,
        error_message=job.error_message,
        created_at=job.created_at.isoformat(),
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )


@router.post("", response_model=ScreeningJobOut, status_code=status.HTTP_201_CREATED)
def create_screening_job(
    payload: ScreeningJobCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScreeningJobOut:
    # No synchronous ticker-sanity-check here, unlike sweeps.py's POST —
    # there's nothing to typo in a fixed universe, so that check has no
    # analog for this endpoint.
    job = ScreeningJob(
        user_id=current_user.id,
        strategy_name=payload.strategy_name,
        universe_size=len(ticker_universe.SCREENING_UNIVERSE),
        n_tickers_resolved=0,
        n_candidates_found=0,
        status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return _to_job_out(job)


@router.get("", response_model=list[ScreeningJobOut])
def list_screening_jobs(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ScreeningJobOut]:
    rows = (
        db.execute(
            select(ScreeningJob)
            .where(ScreeningJob.user_id == current_user.id)
            .order_by(ScreeningJob.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return [_to_job_out(r) for r in rows]


@router.get("/{screening_id}", response_model=ScreeningJobDetailOut)
def get_screening_job(
    screening_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScreeningJobDetailOut:
    job = get_owned_screening_job(db, screening_id, current_user)
    candidate_rows = (
        db.execute(
            select(ScreeningCandidate)
            .where(ScreeningCandidate.job_id == job.id)
            .order_by(ScreeningCandidate.id)
        )
        .scalars()
        .all()
    )
    candidates = [
        ScreeningCandidateOut(
            ticker_a=c.ticker_a,
            ticker_b=c.ticker_b,
            score=c.score,
            direction=c.direction,
            regime=c.regime,
            discovered_at=c.discovered_at.isoformat(),
        )
        for c in candidate_rows
    ]
    return ScreeningJobDetailOut(
        **_to_job_out(job).model_dump(),
        candidates=candidates,
        methodology_note=build_screening_methodology_note(job.strategy_name, job.universe_size),
    )
