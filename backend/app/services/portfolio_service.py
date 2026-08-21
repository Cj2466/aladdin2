from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.portfolio import Portfolio
from app.models.user import User


def get_owned_portfolio(db: Session, portfolio_id: int, user: User) -> Portfolio:
    """404 (not 403) whether the portfolio is missing or owned by someone
    else — avoids leaking existence of other users' portfolios via
    status-code enumeration."""
    portfolio = db.execute(
        select(Portfolio)
        .where(Portfolio.id == portfolio_id, Portfolio.user_id == user.id)
        .options(selectinload(Portfolio.holdings))
    ).scalar_one_or_none()
    if portfolio is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found")
    return portfolio


def to_weights_dict(portfolio: Portfolio) -> dict[str, float]:
    return {h.ticker: h.weight for h in portfolio.holdings if h.weight is not None}
