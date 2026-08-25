from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class StrategyExecutionState(Base):
    """Per-strategy live-execution state: the rolling realized-P&L ledger the
    per-strategy circuit breaker judges, plus that breaker's own halt record.

    Keyed on ForwardValidationRegistration — the durable strategy identity
    already used everywhere else in this system (a StrategyPortfolioAllocation
    is re-pointed at a fresher ExperimentRun on any re-optimization, so it is
    the wrong thing to accumulate history against).

    day_pnl_json follows ForwardValidationRegistration.day_results_json's own
    established shape rather than introducing a second per-day table: a list of
    {"date","pnl","return","allocated_capital"} objects, trimmed to the most
    recent DAY_PNL_HISTORY_LIMIT entries, which bounds the row's size
    permanently while keeping the whole rolling window in one read.

    frozen_target_json is what makes "pull this strategy without liquidating
    it" actually work. Per-ticker targets are aggregated across every live
    strategy before being diffed against the broker's real positions — so
    simply dropping a halted strategy from that aggregation would lower the
    ticker's target and make the very next tick SELL its position, i.e.
    force-liquidate during exactly the event that triggered the halt. Instead
    the strategy's last computed target is frozen here and keeps contributing
    to the aggregate: existing positions are held, and no new orders are ever
    generated for it because its contribution stops changing.
    """

    __tablename__ = "strategy_execution_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    forward_validation_registration_id: Mapped[int] = mapped_column(
        ForeignKey("forward_validation_registrations.id"), unique=True, index=True
    )
    # Informational: the allocation that most recently sized this strategy.
    strategy_portfolio_allocation_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategy_portfolio_allocations.id"), nullable=True
    )

    day_pnl_json: Mapped[str] = mapped_column(Text, default="[]")
    # The trading day day_pnl_json's last entry belongs to. Used to decide
    # whether a tick appends a new day or updates the current one in place —
    # the runner ticks ~390 times per session and must record one row per day,
    # not 390.
    last_marked_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    halted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    halted_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    halted_trailing_sharpe: Mapped[float | None] = mapped_column(Float, nullable=True)
    halted_trailing_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frozen_target_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    resumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resumed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
