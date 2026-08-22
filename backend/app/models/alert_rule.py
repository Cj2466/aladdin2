from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.alert_event import AlertEvent
    from app.models.portfolio import Portfolio


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # Nullable — a macro_threshold rule isn't tied to any portfolio, only to
    # the user (see series_id below).
    portfolio_id: Mapped[int | None] = mapped_column(ForeignKey("portfolios.id"), index=True, nullable=True)
    rule_type: Mapped[str] = mapped_column(String(20))  # "price_move" | "risk_metric" | "macro_threshold"
    ticker: Mapped[str | None] = mapped_column(String(10), nullable=True)
    metric: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # FRED series id (e.g. "T10Y2Y") — only set for macro_threshold rules.
    series_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    threshold_pct: Mapped[float] = mapped_column(Float)
    direction: Mapped[str] = mapped_column(String(10))  # "up" | "down"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    portfolio: Mapped["Portfolio"] = relationship(back_populates="alert_rules")
    events: Mapped[list["AlertEvent"]] = relationship(
        back_populates="rule", cascade="all, delete-orphan"
    )
