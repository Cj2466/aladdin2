from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, false, func
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

    # WHICH allocator produced the weights currently stored on this
    # portfolio's allocations. Written by AutonomousPortfolioRunner every time
    # it writes weights, alongside (or, for the fallback, instead of)
    # last_optimized_at.
    #
    # Exists because the runner can now be pointed at either optimizer via
    # settings.autonomous_portfolio_optimization_method, and a set of weights
    # carries no evidence of how it was derived: a 0.4/0.3/0.3-shaped vector
    # from the capped mean-variance path and a spread-across-everything vector
    # from HRP are both just floats in the same column. Without this, nobody
    # reading the portfolio — a human in the UI, the execution runner, a
    # later comparison of the two methods — could tell which method was in
    # force when those weights were written.
    #
    # Three values, and deliberately not an enum column: config.py's
    # OPTIMIZATION_METHODS ("mean_variance", "hrp") plus "equal_weight" for
    # the runner's fallback, which is not an optimization method at all and
    # so has no place in the config's choice set. NULL for every portfolio
    # nothing has ever auto-reweighted, including every user-built one.
    last_optimization_method: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # The one portfolio ExecutionRunner is allowed to trade for this user.
    # Without it there is no way to know which of several saved portfolios is
    # meant to be traded, and live-trading two independently-optimized
    # portfolios against one broker account would break both the
    # capital-fraction accounting and cross-portfolio risk (each could size a
    # position in the same ticker without knowing about the other).
    #
    # At most one is_live portfolio per user is an APP-level invariant enforced
    # atomically in the toggle endpoint, not a DB constraint: SQLite cannot
    # easily express a partial unique index, and this codebase already targets
    # both SQLite and Postgres.
    is_live: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    # Two-directional cascade with back_populates, mirroring
    # Portfolio.holdings exactly — NOT the one-directional
    # Portfolio.risk_results shape, whose own comment documents the
    # SQLite-doesn't-enforce-FKs/Postgres-does bug this codebase already
    # hit once. Nothing here needs a one-directional relationship, so that
    # bug class doesn't apply; noted so it isn't reintroduced later.
    allocations: Mapped[list["StrategyPortfolioAllocation"]] = relationship(
        back_populates="strategy_portfolio", cascade="all, delete-orphan"
    )
