from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.dependencies import get_macro_provider
from app.models.user import User
from app.schemas.macro import MacroDashboardResponse, MacroSeriesOut, YieldCurvePointOut
from app.services.macro_data.base import MacroDataProvider
from app.services.macro_data.cache import (
    MacroSeriesSnapshot,
    YieldCurvePoint,
    get_latest_macro_snapshot_cached,
    get_yield_curve_cached,
)
from app.services.macro_data.series import CADENCE_NEXT_RELEASE_HINT, MACRO_SERIES_BY_ID
from app.time_utils import utcnow_naive

router = APIRouter(prefix="/api/macro", tags=["macro"])


def _reference_period_label(observation_date: date, cadence: str) -> str:
    if cadence == "monthly":
        return observation_date.strftime("%B %Y")
    if cadence == "quarterly":
        quarter = (observation_date.month - 1) // 3 + 1
        return f"Q{quarter} {observation_date.year}"
    return observation_date.strftime("%b %d, %Y")


def _to_series_out(snapshot: MacroSeriesSnapshot) -> MacroSeriesOut:
    definition = MACRO_SERIES_BY_ID[snapshot.series_id]

    # GFDEBTN is cached in FRED's native units (millions of USD) — converted
    # to trillions here, at the display-building layer, so the cached value
    # stays a faithful mirror of what FRED actually reported.
    value = snapshot.value
    if value is not None and definition.unit == "usd_trillions":
        value = value / 1_000_000

    return MacroSeriesOut(
        series_id=snapshot.series_id,
        label=definition.label,
        category=definition.category,
        cadence=definition.cadence,
        unit=definition.unit,
        decimals=definition.decimals,
        value=value,
        observation_date=snapshot.observation_date.isoformat() if snapshot.observation_date else None,
        reference_period_label=(
            _reference_period_label(snapshot.observation_date, definition.cadence)
            if snapshot.observation_date
            else None
        ),
        fetched_at=snapshot.fetched_at.isoformat() if snapshot.fetched_at else None,
        next_release_hint=CADENCE_NEXT_RELEASE_HINT[definition.cadence],
        status=snapshot.status,
    )


def _to_curve_point_out(point: YieldCurvePoint) -> YieldCurvePointOut:
    return YieldCurvePointOut(
        maturity_label=point.maturity_label, today=point.today, one_year_ago=point.one_year_ago
    )


@router.get("/dashboard", response_model=MacroDashboardResponse)
def macro_dashboard(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
    provider: MacroDataProvider = Depends(get_macro_provider),
) -> MacroDashboardResponse:
    snapshot = get_latest_macro_snapshot_cached(db, provider)
    curve = get_yield_curve_cached(db, provider)
    return MacroDashboardResponse(
        series=[_to_series_out(s) for s in snapshot],
        yield_curve=[_to_curve_point_out(p) for p in curve],
        generated_at=utcnow_naive().isoformat(),
    )
