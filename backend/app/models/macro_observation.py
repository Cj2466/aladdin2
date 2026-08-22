from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MacroObservation(Base):
    """Shared FRED data-point cache, not user-scoped — public reference
    data, identical for every user. `observation_date` is FRED's own
    reference/as-of date for the value (e.g. the month CPI describes);
    `fetched_at` is only cache bookkeeping (when we last checked FRED).
    Keeping these distinct is what lets the UI honestly label a value
    "as of July 2026" instead of implying today's date."""

    __tablename__ = "macro_observations"

    series_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    observation_date: Mapped[date] = mapped_column(Date, primary_key=True)
    value: Mapped[float] = mapped_column(Float)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
