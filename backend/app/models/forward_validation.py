from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ForwardValidationRegistration(Base):
    """A user's standing decision to track a specific backtested
    configuration going forward in real time — user-scoped like AlertRule
    (needs to show up in "my tracked signals", needs ownership for
    delete), unlike ExperimentRun's shared pure-function cache."""

    __tablename__ = "forward_validation_registrations"
    __table_args__ = (UniqueConstraint("user_id", "config_hash", name="uq_forward_validation_user_config"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    strategy_name: Mapped[str] = mapped_column(String(50), index=True)
    ticker_a: Mapped[str] = mapped_column(String(10), index=True)
    ticker_b: Mapped[str] = mapped_column(String(10), index=True)
    fit_window_days: Mapped[int]
    entry_z: Mapped[float]
    exit_z: Mapped[float]
    cost_bps: Mapped[float]
    config_hash: Mapped[str] = mapped_column(String(64))

    status: Mapped[str] = mapped_column(String(20), default="in_progress", index=True)  # "in_progress" | "forward_validated"
    # Snapshotted at creation — a later change to the graduation threshold
    # constant never retroactively alters an in-flight registration.
    min_trading_days_threshold: Mapped[int]
    n_forward_trading_days: Mapped[int] = mapped_column(default=0)

    started_at: Mapped[date] = mapped_column(Date)
    last_processed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_ticked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    graduated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Serialized WalkForwardState (engine.serialize_walk_forward_state) —
    # what lets a tick resume exactly where the previous one left off.
    carry_state_json: Mapped[str] = mapped_column(Text)
    day_results_json: Mapped[str] = mapped_column(Text, default="[]")
    trades_json: Mapped[str] = mapped_column(Text, default="[]")  # closed trades only
