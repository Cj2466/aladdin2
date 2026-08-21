from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alert_rule import AlertRule
from app.models.user import User


def get_owned_alert_rule(db: Session, rule_id: int, user: User) -> AlertRule:
    """404 (not 403) whether the rule is missing or owned by someone else —
    same non-enumeration reasoning as get_owned_portfolio."""
    rule = db.execute(
        select(AlertRule).where(AlertRule.id == rule_id, AlertRule.user_id == user.id)
    ).scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")
    return rule
