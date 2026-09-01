from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models.macro_event_detection import MacroEventDetection
from app.models.user import User
from app.schemas.macro_event import (
    MACRO_EVENT_EVIDENCE_DISCLAIMER,
    MacroEventDetectionOut,
    MacroEventDetectionsResponse,
)
from app.services.macro_event.drivers import ALL_SOURCES

router = APIRouter(prefix="/api/macro-event", tags=["macro-event"])


def _to_out(row: MacroEventDetection) -> MacroEventDetectionOut:
    return MacroEventDetectionOut(
        id=row.id,
        detected_at=row.detected_at.isoformat(),
        source=row.source,
        driver=row.driver,
        trigger_metric=row.trigger_metric,
        trigger_value=row.trigger_value,
        trigger_threshold=row.trigger_threshold,
        triggered=row.triggered,
        escalated=row.escalated,
        raw_metrics_json=row.raw_metrics_json,
        error=row.error,
    )


@router.get("/detections", response_model=MacroEventDetectionsResponse)
def list_macro_event_detections(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    source: str | None = Query(default=None),
    triggered_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> MacroEventDetectionsResponse:
    """Stage-A detection log, most recent first.

    READ-ONLY. This phase's API surface is deliberately a single read
    endpoint: there is nothing to act on yet, because Stage B (Phase 2.3) and
    the execution pathway (Phase 2.4) do not exist.

    `triggered_only` DEFAULTS TO FALSE ON PURPOSE. The non-triggers are the
    majority of this table and are its whole point — they are the denominator
    that makes the observed trigger RATE meaningful, and that rate is the only
    honest basis for the threshold calibration this phase exists to inform.
    A caller that filters to triggers alone sees a numerator with no
    denominator, which is precisely the mistake the table's design prevents.

    Ordered by detected_at DESC then id DESC. The id tiebreak matters rather
    than being decorative: all three sources on one tick share a single
    detected_at, so ordering on the timestamp alone leaves their relative order
    unspecified and a paged read could then repeat or skip a row across page
    boundaries.
    """
    if source is not None and source not in ALL_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"source must be one of {sorted(ALL_SOURCES)}",
        )

    filters = []
    if source is not None:
        filters.append(MacroEventDetection.source == source)
    if triggered_only:
        filters.append(MacroEventDetection.triggered.is_(True))

    total = db.execute(
        select(func.count()).select_from(MacroEventDetection).where(*filters)
    ).scalar_one()

    rows = (
        db.execute(
            select(MacroEventDetection)
            .where(*filters)
            .order_by(MacroEventDetection.detected_at.desc(), MacroEventDetection.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )

    return MacroEventDetectionsResponse(
        detections=[_to_out(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
        disclaimer=MACRO_EVENT_EVIDENCE_DISCLAIMER,
    )
