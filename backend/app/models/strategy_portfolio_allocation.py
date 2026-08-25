from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.strategy_portfolio import StrategyPortfolio


class StrategyPortfolioAllocation(Base):
    """One backtested strategy instance's slice of a StrategyPortfolio.

    `weight` is NOT NULL, unlike Holding.weight — Holding is nullable only
    because it has an alternate quantity+cost_basis sizing path, which a
    backtested strategy has no analogue for.

    No relationship is declared on ExperimentRun's side, and no
    ondelete="CASCADE" is set on the FK: ExperimentRun is a shared,
    non-user-scoped cache row (per its own docstring) that must stay
    decoupled from user-owned entities, and a cascade would let a future
    cache-cleanup job silently delete pieces of a user's saved portfolio.
    Nothing in the codebase deletes ExperimentRun rows today, so orphaning
    isn't a live risk; a missing/non-"ok" reference is instead validated
    lazily at analyze/optimize time (MissingExperimentRunError), mirroring
    the existing precedent that PortfolioCreate validates structure only
    and defers ticker-data-exists checks to /analyze."""

    __tablename__ = "strategy_portfolio_allocations"
    __table_args__ = (
        UniqueConstraint(
            "strategy_portfolio_id", "experiment_run_id", name="uq_strategy_allocation_portfolio_run"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("strategy_portfolios.id"), index=True
    )
    experiment_run_id: Mapped[int] = mapped_column(ForeignKey("experiment_runs.id"), index=True)
    weight: Mapped[float] = mapped_column(Float)

    strategy_portfolio: Mapped["StrategyPortfolio"] = relationship(back_populates="allocations")
