from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# The one row's primary key. Seeded by this table's migration; every read and
# write goes through execution_control_service, so exactly one module knows it.
SINGLETON_ID = 1


class ExecutionControl(Base):
    """The system-wide trading kill switch — a single row, seeded by its
    migration with trading_halted=True.

    That default is the most important thing in this file: a fresh deploy, a
    restored backup, or a brand-new database must NEVER silently start
    submitting orders. A human explicitly resumes, every time this table is
    created from scratch.

    Deliberately not user-scoped, unlike every other owned table here: this is
    a single-operator personal system trading one broker account, so "halt"
    means halt the account, not halt one person's slice of it. A per-user
    switch would create the illusion that one user's halt protects the account
    while another user's strategies keep trading it.
    """

    __tablename__ = "execution_control"

    id: Mapped[int] = mapped_column(primary_key=True)
    trading_halted: Mapped[bool] = mapped_column(Boolean, default=True)
    halted_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    halted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # NULL for an automatic halt (loss breach, broker-side block); set to the
    # acting user's id for a manual one.
    halted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # When the daily-loss circuit breaker last fired. Read by POST /resume,
    # which refuses to re-arm trading on the same trading day as a breach —
    # specifically so a stressed human cannot immediately undo the thing that
    # just protected them.
    daily_loss_breach_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    daily_loss_breach_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    resumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resumed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # Observability only — never read by any control-flow decision. Lets the
    # status page distinguish "halted" from "running but silently wedged".
    last_tick_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_tick_status: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
