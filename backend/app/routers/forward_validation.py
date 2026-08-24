import json

import pandas as pd
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models.forward_validation import ForwardValidationRegistration
from app.models.user import User
from app.schemas.forward_validation import (
    ForwardValidationRegisterRequest,
    ForwardValidationRegisterResponse,
    ForwardValidationRegistrationOut,
    MomentumForwardValidationRegisterRequest,
)
from app.services.forward_validation_service import (
    MIN_FORWARD_DAYS_FOR_SHARPE,
    get_owned_forward_validation_registration,
    register_or_get_forward_validation,
)
from app.services.research_lab import metrics, momentum
from app.services.research_lab.engine import deserialize_walk_forward_state, summarize_fit_stats
from app.services.research_lab.ou_pairs import STRATEGY_NAME
from app.services.research_lab.system_account import get_system_user_id

router = APIRouter(prefix="/api/forward-validation", tags=["forward-validation"])


def _to_registration_out(
    registration: ForwardValidationRegistration, system_user_id: int | None
) -> ForwardValidationRegistrationOut:
    state = deserialize_walk_forward_state(json.loads(registration.carry_state_json))
    open_position = "flat"
    if state.open_trade is not None:
        open_position = state.open_trade.direction

    pct_days_mean_reverting_forward = None
    if registration.n_forward_trading_days > 0:
        pct_days_mean_reverting_forward, _ = summarize_fit_stats(state, registration.n_forward_trading_days)

    sharpe_forward_so_far = None
    if registration.n_forward_trading_days >= MIN_FORWARD_DAYS_FOR_SHARPE:
        day_results = json.loads(registration.day_results_json)
        net_returns = pd.Series([d["net_return"] for d in day_results])
        sharpe_forward_so_far = metrics.sharpe_ratio(net_returns)

    return ForwardValidationRegistrationOut(
        id=registration.id,
        strategy_name=registration.strategy_name,
        ticker_a=registration.ticker_a,
        ticker_b=registration.ticker_b,
        fit_window_days=registration.fit_window_days,
        entry_z=registration.entry_z,
        exit_z=registration.exit_z,
        cost_bps=registration.cost_bps,
        status=registration.status,
        started_at=registration.started_at.isoformat(),
        last_processed_date=registration.last_processed_date.isoformat() if registration.last_processed_date else None,
        n_forward_trading_days=registration.n_forward_trading_days,
        min_trading_days_threshold=registration.min_trading_days_threshold,
        graduated_at=registration.graduated_at.isoformat() if registration.graduated_at else None,
        open_position=open_position,
        pct_days_mean_reverting_forward=pct_days_mean_reverting_forward,
        sharpe_forward_so_far=sharpe_forward_so_far,
        is_system=system_user_id is not None and registration.user_id == system_user_id,
    )


@router.post("", response_model=ForwardValidationRegisterResponse, status_code=status.HTTP_201_CREATED)
def register_forward_validation(
    payload: ForwardValidationRegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ForwardValidationRegisterResponse:
    registration, created = register_or_get_forward_validation(
        db,
        user_id=current_user.id,
        strategy_name=STRATEGY_NAME,
        ticker_a=payload.ticker_a,
        ticker_b=payload.ticker_b,
        fit_window_days=payload.fit_window_days,
        entry_z=payload.entry_z,
        exit_z=payload.exit_z,
        cost_bps=payload.cost_bps,
    )
    # Idempotent — never resets accumulated progress. A deliberate restart
    # is a DELETE + fresh POST, not a duplicate submit.
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    out = _to_registration_out(registration, system_user_id=None)
    return ForwardValidationRegisterResponse(**out.model_dump(), created=created)


@router.post("/momentum", response_model=ForwardValidationRegisterResponse, status_code=status.HTTP_201_CREATED)
def register_momentum_forward_validation(
    payload: MomentumForwardValidationRegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ForwardValidationRegisterResponse:
    registration, created = register_or_get_forward_validation(
        db,
        user_id=current_user.id,
        strategy_name=momentum.STRATEGY_NAME,
        ticker_a=payload.ticker,
        ticker_b=payload.ticker,
        fit_window_days=payload.fit_window_days,
        entry_z=payload.entry_z,
        exit_z=payload.exit_z,
        cost_bps=payload.cost_bps,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    out = _to_registration_out(registration, system_user_id=None)
    return ForwardValidationRegisterResponse(**out.model_dump(), created=created)


@router.get("", response_model=list[ForwardValidationRegistrationOut])
def list_forward_validation_registrations(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ForwardValidationRegistrationOut]:
    system_user_id = get_system_user_id(db)
    ownership_filter = (
        or_(ForwardValidationRegistration.user_id == current_user.id, ForwardValidationRegistration.user_id == system_user_id)
        if system_user_id is not None
        else ForwardValidationRegistration.user_id == current_user.id
    )
    rows = (
        db.execute(
            select(ForwardValidationRegistration)
            .where(ownership_filter)
            .order_by(ForwardValidationRegistration.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return [_to_registration_out(r, system_user_id) for r in rows]


@router.delete("/{registration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_forward_validation_registration(
    registration_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    registration = get_owned_forward_validation_registration(db, registration_id, current_user)
    db.delete(registration)
    db.commit()
