from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.strategy_portfolio_allocation import StrategyPortfolioAllocation


class StrategyPortfolio(Base):
    """A user's saved combination of already-backtested strategy instances
    (ExperimentRun rows) into one portfolio with explicit risk budgeting —
    the strategy-level analogue of Portfolio/Holding, which combines
    tickers.

    User-scoped like Portfolio (needs to show up in "my portfolios", needs
    ownership for delete), unlike ExperimentRun's shared pure-function
    cache."""

    __tablename__ = "strategy_portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Only ever written by AutonomousPortfolioRunner, and only for the
    # system-owned portfolio it maintains — its once-per-calendar-day
    # re-optimization guard. NULL for every user-built portfolio (nothing
    # re-optimizes those on a schedule; a user clicks Optimize themselves).
    # Deliberately NOT updated_at: that column is bumped by any membership
    # edit too, so it can't distinguish "weights were re-derived from
    # returns today" from "a row was touched today".
    last_optimized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Two-directional cascade with back_populates, mirroring
    # Portfolio.holdings exactly — NOT the one-directional
    # Portfolio.risk_results shape, whose own comment documents the
    # SQLite-doesn't-enforce-FKs/Postgres-does bug this codebase already
    # hit once. Nothing here needs a one-directional relationship, so that
    # bug class doesn't apply; noted so it isn't reintroduced later.
    allocations: Mapped[list["StrategyPortfolioAllocation"]] = relationship(
        back_populates="strategy_portfolio", cascade="all, delete-orphan"
    )
