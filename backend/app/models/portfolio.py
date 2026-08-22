from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.alert_rule import AlertRule
    from app.models.holding import Holding
    from app.models.risk_result import RiskResult


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    base_currency: Mapped[str] = mapped_column(String(3), default="USD")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    holdings: Mapped[list["Holding"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )
    alert_rules: Mapped[list["AlertRule"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )
    # One-directional (no back_populates) — nothing in the codebase needs to
    # navigate from a RiskResult back to its portfolio, only ever queried
    # directly. Needed purely so deleting a portfolio cascades its cached
    # risk_results rows: SQLite never enforces this FK (no PRAGMA
    # foreign_keys set anywhere), so a missing cascade here was a silent
    # no-op locally, but Postgres enforces FKs by default, causing a 500 on
    # delete for any portfolio that had ever been analyzed.
    risk_results: Mapped[list["RiskResult"]] = relationship(cascade="all, delete-orphan")
