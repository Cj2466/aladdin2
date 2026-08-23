from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ExperimentRun(Base):
    """Shared results cache for research-lab backtests, not user-scoped —
    same reasoning as RiskResult, whose metadata-columns-plus-one-JSON-blob
    shape this mirrors exactly (a backtest result — equity curve, trade
    log, metrics — is exactly the variably-shaped-payload case that
    pattern exists for)."""

    __tablename__ = "experiment_runs"
    __table_args__ = (UniqueConstraint("input_hash", name="uq_experiment_runs_input_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(50), index=True)
    ticker_a: Mapped[str] = mapped_column(String(10), index=True)
    ticker_b: Mapped[str] = mapped_column(String(10), index=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    computed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    results_json: Mapped[str] = mapped_column(Text)
