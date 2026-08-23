import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.dependencies import get_provider
from app.models.sweep_job import SweepJob
from app.models.user import User
from app.schemas.sweep import SweepGridSpec, SweepJobCreateRequest, SweepJobOut
from app.services.market_data.base import MarketDataError, MarketDataProvider
from app.services.market_data.price_cache import get_price_history_cached
from app.services.research_lab.ou_pairs import STRATEGY_NAME
from app.services.research_lab.sweep_service import MAX_SWEEP_COMBINATIONS, expand_sweep_grid, get_owned_sweep_job
from app.services.risk.errors import MissingTickerDataError

router = APIRouter(prefix="/api/research-lab/sweeps", tags=["research-lab"])

# Just enough history to confirm both tickers actually resolve — a full
# lookback fetch isn't needed for this sanity check, and would make a
# typo'd ticker fail slowly instead of immediately.
_TICKER_SANITY_CHECK_DAYS = 30


def _to_sweep_job_out(job: SweepJob) -> SweepJobOut:
    return SweepJobOut(
        id=job.id,
        strategy_name=job.strategy_name,
        ticker_a=job.ticker_a,
        ticker_b=job.ticker_b,
        lookback_years=job.lookback_years,
        grid=SweepGridSpec(**json.loads(job.grid_spec_json)),
        total_configurations=job.total_configurations,
        configurations_completed=job.configurations_completed,
        configurations_failed=job.configurations_failed,
        status=job.status,
        created_at=job.created_at.isoformat(),
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )


@router.post("", response_model=SweepJobOut, status_code=status.HTTP_201_CREATED)
def create_sweep_job(
    payload: SweepJobCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    provider: MarketDataProvider = Depends(get_provider),
) -> SweepJobOut:
    combos = expand_sweep_grid(payload.grid)
    if not combos:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No valid combinations in this grid — every combination had exit_z >= entry_z.",
        )
    if len(combos) > MAX_SWEEP_COMBINATIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"This grid has {len(combos)} valid combinations, above the {MAX_SWEEP_COMBINATIONS} limit per sweep.",
        )

    end = date.today()
    start = end - timedelta(days=_TICKER_SANITY_CHECK_DAYS)
    try:
        prices, _missing = get_price_history_cached(db, provider, [payload.ticker_a, payload.ticker_b], start, end)
    except MarketDataError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    missing_required = [t for t in (payload.ticker_a, payload.ticker_b) if t not in prices.columns]
    if missing_required:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(MissingTickerDataError(missing_required, label="pair")),
        )

    job = SweepJob(
        user_id=current_user.id,
        strategy_name=STRATEGY_NAME,
        ticker_a=payload.ticker_a,
        ticker_b=payload.ticker_b,
        lookback_years=payload.lookback_years,
        grid_spec_json=payload.grid.model_dump_json(),
        total_configurations=len(combos),
        configurations_completed=0,
        configurations_failed=0,
        status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return _to_sweep_job_out(job)


@router.get("", response_model=list[SweepJobOut])
def list_sweep_jobs(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SweepJobOut]:
    rows = (
        db.execute(
            select(SweepJob)
            .where(SweepJob.user_id == current_user.id)
            .order_by(SweepJob.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return [_to_sweep_job_out(r) for r in rows]


@router.get("/{sweep_id}", response_model=SweepJobOut)
def get_sweep_job(
    sweep_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SweepJobOut:
    job = get_owned_sweep_job(db, sweep_id, current_user)
    return _to_sweep_job_out(job)
