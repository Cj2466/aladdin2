from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models.alert_event import AlertEvent
from app.models.alert_rule import AlertRule
from app.models.user import User
from app.schemas.alerts import AlertEventOut, AlertRuleCreate, AlertRuleOut
from app.services.alert_service import get_owned_alert_rule
from app.services.portfolio_service import get_owned_portfolio

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("/rules", response_model=list[AlertRuleOut])
def list_alert_rules(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[AlertRule]:
    return (
        db.execute(select(AlertRule).where(AlertRule.user_id == current_user.id))
        .scalars()
        .all()
    )


@router.post("/rules", response_model=AlertRuleOut, status_code=status.HTTP_201_CREATED)
def create_alert_rule(
    payload: AlertRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlertRule:
    get_owned_portfolio(db, payload.portfolio_id, current_user)
    rule = AlertRule(user_id=current_user.id, **payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    rule = get_owned_alert_rule(db, rule_id, current_user)
    db.delete(rule)
    db.commit()


@router.get("", response_model=list[AlertEventOut])
def list_alert_events(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AlertEvent]:
    return (
        db.execute(
            select(AlertEvent)
            .where(AlertEvent.user_id == current_user.id)
            .order_by(AlertEvent.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )


@router.patch("/{event_id}/read", response_model=AlertEventOut)
def mark_alert_read(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlertEvent:
    event = db.execute(
        select(AlertEvent).where(AlertEvent.id == event_id, AlertEvent.user_id == current_user.id)
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert event not found")
    event.is_read = True
    db.commit()
    db.refresh(event)
    return event
