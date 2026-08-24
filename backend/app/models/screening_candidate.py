from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ScreeningCandidate(Base):
    """One result row from a ScreeningJob — promoted to its own table
    rather than a JSON blob, mirroring ExperimentRun's own convention of
    promoting whatever a leaderboard genuinely needs to sort/filter on.
    Storage stays bounded regardless of universe size since only passing,
    capped candidates are ever stored (see screening.py's MAX_* constants),
    never the full combinatorial space."""

    __tablename__ = "screening_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("screening_jobs.id"), index=True)

    ticker_a: Mapped[str] = mapped_column(String(10), index=True)
    ticker_b: Mapped[str] = mapped_column(String(10), index=True)  # == ticker_a for momentum
    score: Mapped[float] = mapped_column(Float)  # momentum: signed t-stat; pairs: signed correlation
    direction: Mapped[str | None] = mapped_column(String(10), nullable=True)  # momentum only: "long"|"short"

    discovered_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
