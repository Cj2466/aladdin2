from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.strategy_portfolio import StrategyPortfolio
from app.models.user import User


def get_owned_strategy_portfolio(
    db: Session, strategy_portfolio_id: int, user: User, system_user_id: int | None = None
) -> StrategyPortfolio:
    """404 (not 403) whether the portfolio is missing or owned by someone
    else — same non-enumeration reasoning as get_owned_portfolio /
    get_owned_alert_rule.

    `system_user_id` widens READ paths only (get/analyze/optimize) so the
    autonomously-maintained system portfolio is visible to a real user,
    exactly as get_owned_screening_job was widened in Phase 3. Mutating
    paths (PUT/DELETE) deliberately pass None: no real user's id can ever
    equal the system account's, so a real user can see the system portfolio
    but never edit or delete it."""
    owner_filter = (
        or_(StrategyPortfolio.user_id == user.id, StrategyPortfolio.user_id == system_user_id)
        if system_user_id is not None
        else StrategyPortfolio.user_id == user.id
    )
    portfolio = db.execute(
        select(StrategyPortfolio)
        .where(StrategyPortfolio.id == strategy_portfolio_id, owner_filter)
        .options(selectinload(StrategyPortfolio.allocations))
    ).scalar_one_or_none()
    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Strategy portfolio not found"
        )
    return portfolio


def to_allocations_dict(portfolio: StrategyPortfolio) -> dict[int, float]:
    return {a.experiment_run_id: a.weight for a in portfolio.allocations}
