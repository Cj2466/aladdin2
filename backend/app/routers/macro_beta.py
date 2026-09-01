from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models.macro_commodity_beta import MacroCommodityBeta
from app.models.user import User
from app.schemas.macro_beta import (
    MACRO_BETA_EVIDENCE_DISCLAIMER,
    MacroBetaResponse,
    MacroBetaRowOut,
    MacroDriverCatalogResponse,
    MacroDriverOut,
)
from app.services.research_lab.macro_beta import (
    MACRO_DRIVERS,
    MACRO_DRIVERS_BY_ID,
    MacroDriver,
)

router = APIRouter(prefix="/api/macro-beta", tags=["macro-beta"])


def _to_driver_out(driver: MacroDriver) -> MacroDriverOut:
    return MacroDriverOut(
        driver_id=driver.driver_id,
        source=driver.source,
        symbol=driver.symbol,
        kind=driver.kind,
        label=driver.label,
        mechanism=driver.mechanism,
    )


def _to_row_out(row: MacroCommodityBeta) -> MacroBetaRowOut:
    return MacroBetaRowOut(
        driver=row.driver,
        ticker=row.ticker,
        as_of_date=row.as_of_date.isoformat(),
        window_days=row.window_days,
        beta_full_sample=row.beta_full_sample,
        beta_shock_days=row.beta_shock_days,
        correlation_full_sample=row.correlation_full_sample,
        n_observations_full_sample=row.n_observations_full_sample,
        n_observations_shock_days=row.n_observations_shock_days,
        t_stat_full_sample=row.t_stat_full_sample,
        sign_agreement=row.sign_agreement,
    )


@router.get("/drivers", response_model=MacroDriverCatalogResponse)
def list_macro_drivers(
    _current_user: User = Depends(get_current_user),
) -> MacroDriverCatalogResponse:
    """The 13 pre-declared drivers. Static — the roster is frozen by the
    family's pre-registration and this endpoint reads no database."""
    return MacroDriverCatalogResponse(
        drivers=[_to_driver_out(d) for d in MACRO_DRIVERS],
        disclaimer=MACRO_BETA_EVIDENCE_DISCLAIMER,
    )


@router.get("/{driver}", response_model=MacroBetaResponse)
def get_macro_betas_for_driver(
    driver: str,
    limit: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> MacroBetaResponse:
    """Top-N tickers by |beta| for ONE driver, from the newest as_of_date
    generation only.

    Scoped to a single driver deliberately: betas are not comparable across
    driver kinds (dimensionless for a price driver, per-basis-point for a rate
    driver), so a cross-driver |beta| ranking would be meaningless. See
    MacroCommodityBeta's docstring.

    Reads only the newest generation. The table is append-only and holds every
    past generation, but mixing generations in one ranking would silently
    compare betas measured at different times.
    """
    definition = MACRO_DRIVERS_BY_ID.get(driver)
    if definition is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"driver must be one of {sorted(MACRO_DRIVERS_BY_ID)}",
        )

    newest = db.execute(
        select(func.max(MacroCommodityBeta.as_of_date)).where(MacroCommodityBeta.driver == driver)
    ).scalar_one_or_none()
    if newest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No betas have been computed yet for driver {driver}.",
        )

    rows = (
        db.execute(
            select(MacroCommodityBeta)
            .where(MacroCommodityBeta.driver == driver)
            .where(MacroCommodityBeta.as_of_date == newest)
            .order_by(func.abs(MacroCommodityBeta.beta_full_sample).desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )

    return MacroBetaResponse(
        driver=_to_driver_out(definition),
        as_of_date=newest.isoformat(),
        rows=[_to_row_out(r) for r in rows],
        disclaimer=MACRO_BETA_EVIDENCE_DISCLAIMER,
    )
