from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TickerMetadata(Base):
    """Shared metadata cache (sector/industry/asset class), not user-scoped —
    same reasoning as PriceBar."""

    __tablename__ = "ticker_metadata"

    ticker: Mapped[str] = mapped_column(String(10), primary_key=True)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    asset_class: Mapped[str | None] = mapped_column(String(20), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
