from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SweepJob(Base):
    """A user's one-time submission of a parameter grid to test — user-scoped
    like ForwardValidationRegistration (shows up as "my sweeps"), but with
    no uniqueness constraint: a job is a batch submission, not a standing
    registration, and resubmitting an identical grid is harmless since
    ExperimentRun.input_hash dedupes the actual compute one layer down."""

    __tablename__ = "sweep_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    strategy_name: Mapped[str] = mapped_column(String(50), index=True)
    ticker_a: Mapped[str] = mapped_column(String(10), index=True)
    ticker_b: Mapped[str] = mapped_column(String(10), index=True)
    lookback_years: Mapped[int] = mapped_column(Integer)  # fixed per job — not swept

    grid_spec_json: Mapped[str] = mapped_column(Text)
    total_configurations: Mapped[int] = mapped_column(Integer)
    configurations_completed: Mapped[int] = mapped_column(Integer, default=0)
    configurations_failed: Mapped[int] = mapped_column(Integer, default=0)

    # "queued" | "running" | "completed" — no job-level "failed"; a whole
    # sweep completing means every combo was attempted
    # (completed + failed == total), not that every combo succeeded.
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_ticked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
