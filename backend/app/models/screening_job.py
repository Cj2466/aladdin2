from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ScreeningJob(Base):
    """A user's request to screen the fixed ticker universe for candidates
    of one strategy. Deliberately has a REAL "failed" status, unlike
    SweepJob — a sweep has many independent combos where
    completed+failed==total already captures partial failure, but a
    screening job is one indivisible unit of work (the universe fetch
    either succeeds or it doesn't), so it needs its own failure state
    plus an error_message rather than borrowing SweepJob's convention."""

    __tablename__ = "screening_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    strategy_name: Mapped[str] = mapped_column(String(50), index=True)
    universe_size: Mapped[int] = mapped_column(Integer)  # frozen snapshot at submission time
    n_tickers_resolved: Mapped[int] = mapped_column(Integer, default=0)
    n_candidates_found: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)  # queued|running|completed|failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_ticked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
