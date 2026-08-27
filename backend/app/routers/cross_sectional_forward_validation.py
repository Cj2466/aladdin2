"""Cross-sectional forward-validation endpoints.

A SEPARATE router module rather than new handlers appended to
routers/forward_validation.py: that file is the live pairs/momentum path,
and leaving it literally untouched is the cheapest possible proof that this
work did not change it. The shapes below mirror it closely (idempotent POST
returning 201/200, a list that includes system-owned rows, a DELETE behind
an owned-lookup) so the two read as siblings.
"""

import json

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models.cross_sectional_forward_validation import (
    CrossSectionalForwardValidationRegistration,
)
from app.models.user import User
from app.schemas.cross_sectional_forward_validation import (
    CrossSectionalFamilyOut,
    CrossSectionalForwardValidationRegisterRequest,
    CrossSectionalForwardValidationRegisterResponse,
    CrossSectionalForwardValidationRegistrationOut,
)
from app.services.cross_sectional_forward_validation_service import (
    get_owned_cross_sectional_forward_validation_registration,
    register_or_get_cross_sectional_forward_validation,
)
from app.services.forward_validation_service import MIN_FORWARD_DAYS_FOR_SHARPE
from app.services.research_lab import metrics
from app.services.research_lab.cross_sectional_forward import (
    ForwardTickNotSupportedError,
    deserialize_cross_sectional_forward_state,
)
from app.services.research_lab.cross_sectional_forward_registry import (
    UnknownCrossSectionalFamilyError,
    UnknownCrossSectionalSpecError,
    get_family_adapter,
    registered_family_keys,
    resolve_spec,
)
from app.services.research_lab.system_account import get_system_user_id

router = APIRouter(prefix="/api/cross-sectional-forward-validation", tags=["forward-validation"])


def _to_registration_out(
    registration: CrossSectionalForwardValidationRegistration, system_user_id: int | None
) -> CrossSectionalForwardValidationRegistrationOut:
    state = deserialize_cross_sectional_forward_state(json.loads(registration.carry_state_json))
    spec_snapshot = json.loads(registration.spec_snapshot_json)
    config_snapshot = json.loads(registration.config_snapshot_json)
    periods_per_year = float(config_snapshot.get("periods_per_year", metrics.TRADING_DAYS_PER_YEAR))

    sharpe_forward_so_far = None
    if registration.n_forward_trading_days >= MIN_FORWARD_DAYS_FOR_SHARPE:
        day_results = json.loads(registration.day_results_json)
        net_returns = pd.Series([d["net_return"] for d in day_results if d.get("realized")])
        # The family's OWN calendar, from the snapshot rather than a
        # constant: a 365-observation crypto year annualized at 252 would
        # understate this Sharpe by ~17%.
        sharpe_forward_so_far = metrics.sharpe_ratio(net_returns, periods_per_year=periods_per_year)

    return CrossSectionalForwardValidationRegistrationOut(
        id=registration.id,
        family_key=registration.family_key,
        pattern_id=registration.pattern_id,
        module_path=registration.module_path,
        spec_family=registration.spec_family,
        citation=registration.citation,
        universe_rule=registration.universe_rule,
        family_n_trials=registration.family_n_trials,
        registration_rationale=registration.registration_rationale,
        spec_snapshot=spec_snapshot,
        config_snapshot=config_snapshot,
        status=registration.status,
        started_at=registration.started_at.isoformat(),
        last_processed_date=(
            registration.last_processed_date.isoformat() if registration.last_processed_date else None
        ),
        n_forward_trading_days=registration.n_forward_trading_days,
        n_formations=registration.n_formations,
        min_trading_days_threshold=registration.min_trading_days_threshold,
        graduated_at=registration.graduated_at.isoformat() if registration.graduated_at else None,
        n_long=len(state.long_weights),
        n_short=len(state.short_weights),
        days_into_current_hold=state.rows_since_formation,
        holding_days=int(spec_snapshot["holding_days"]),
        sharpe_forward_so_far=sharpe_forward_so_far,
        periods_per_year=periods_per_year,
        equity=state.equity,
        is_system=system_user_id is not None and registration.user_id == system_user_id,
    )


@router.get("/families", response_model=list[CrossSectionalFamilyOut])
def list_cross_sectional_families(
    _current_user: User = Depends(get_current_user),
) -> list[CrossSectionalFamilyOut]:
    """What can be registered, and under exactly which pattern_ids — the
    discoverable half of "a registration is a reference, not a copy"."""
    out: list[CrossSectionalFamilyOut] = []
    for family_key in registered_family_keys():
        adapter = get_family_adapter(family_key)
        out.append(
            CrossSectionalFamilyOut(
                family_key=adapter.family_key,
                module_path=adapter.module_path,
                universe_rule=adapter.universe_rule,
                n_trials=adapter.n_trials,
                pattern_ids=sorted(s.pattern_id for s in adapter.build_specs()),
            )
        )
    return out


@router.post(
    "", response_model=CrossSectionalForwardValidationRegisterResponse, status_code=status.HTTP_201_CREATED
)
def register_cross_sectional_forward_validation(
    payload: CrossSectionalForwardValidationRegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CrossSectionalForwardValidationRegisterResponse:
    try:
        # Resolved first so an unknown family/pattern is a 404 rather than a
        # 500 — and so nothing is written for one.
        resolve_spec(payload.family_key, payload.pattern_id)
        registration, created = register_or_get_cross_sectional_forward_validation(
            db,
            user_id=current_user.id,
            family_key=payload.family_key,
            pattern_id=payload.pattern_id,
            rationale=payload.rationale,
        )
    except (UnknownCrossSectionalFamilyError, UnknownCrossSectionalSpecError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
    except ForwardTickNotSupportedError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None

    # Idempotent — never resets accumulated progress. A deliberate restart
    # is a DELETE + fresh POST, not a duplicate submit.
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    out = _to_registration_out(registration, system_user_id=None)
    return CrossSectionalForwardValidationRegisterResponse(**out.model_dump(), created=created)


@router.get("", response_model=list[CrossSectionalForwardValidationRegistrationOut])
def list_cross_sectional_forward_validation_registrations(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CrossSectionalForwardValidationRegistrationOut]:
    system_user_id = get_system_user_id(db)
    ownership_filter = (
        or_(
            CrossSectionalForwardValidationRegistration.user_id == current_user.id,
            CrossSectionalForwardValidationRegistration.user_id == system_user_id,
        )
        if system_user_id is not None
        else CrossSectionalForwardValidationRegistration.user_id == current_user.id
    )
    rows = (
        db.execute(
            select(CrossSectionalForwardValidationRegistration)
            .where(ownership_filter)
            .order_by(CrossSectionalForwardValidationRegistration.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return [_to_registration_out(r, system_user_id) for r in rows]


@router.delete("/{registration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cross_sectional_forward_validation_registration(
    registration_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    registration = get_owned_cross_sectional_forward_validation_registration(db, registration_id, current_user)
    db.delete(registration)
    db.commit()
