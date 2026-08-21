from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class RiskResult(Base):
    __tablename__ = "risk_results"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "input_hash", name="uq_risk_results_portfolio_input"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), index=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    computed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    metrics_json: Mapped[str] = mapped_column(Text)
