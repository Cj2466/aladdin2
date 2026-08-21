from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PriceBar(Base):
    """Shared price cache, deliberately not user-scoped — public reference
    data (adjusted close), identical for every user watching a ticker."""

    __tablename__ = "price_bars"

    ticker: Mapped[str] = mapped_column(String(10), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    adj_close: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(20), default="yfinance")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
