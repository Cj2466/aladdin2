from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ExperimentRun(Base):
    """Shared results cache for research-lab backtests, not user-scoped —
    same reasoning as RiskResult, whose metadata-columns-plus-one-JSON-blob
    shape this mirrors exactly (a backtest result — equity curve, trade
    log, metrics — is exactly the variably-shaped-payload case that
    pattern exists for). The columns below are the subset a leaderboard
    genuinely needs to sort/filter on, promoted out of results_json;
    everything else (equity curve, trade log, fit-quality distribution)
    stays JSON-only, unlike RiskResult's fully-opaque blob."""

    __tablename__ = "experiment_runs"
    __table_args__ = (UniqueConstraint("input_hash", name="uq_experiment_runs_input_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(50), index=True)
    ticker_a: Mapped[str] = mapped_column(String(10), index=True)
    ticker_b: Mapped[str] = mapped_column(String(10), index=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    computed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    results_json: Mapped[str] = mapped_column(Text)

    # Always present for a real backtest response (config echoed back
    # regardless of status) — tightened to NOT NULL once the backfill
    # migration has populated every pre-existing row.
    status: Mapped[str] = mapped_column(String(20))
    fit_window_days: Mapped[int] = mapped_column(Integer)
    entry_z: Mapped[float] = mapped_column(Float)
    exit_z: Mapped[float] = mapped_column(Float)
    cost_bps: Mapped[float] = mapped_column(Float)
    lookback_years: Mapped[int] = mapped_column(Integer)
    num_trades: Mapped[int] = mapped_column(Integer)

    # Permanently nullable — _build_response itself produces None for
    # these on a non-"ok" status, which is correct modeling, not a gap to
    # backfill away.
    sharpe_net: Mapped[float | None] = mapped_column(Float, nullable=True)
    sharpe_gross: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown_net: Mapped[float | None] = mapped_column(Float, nullable=True)
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    # NULL = a standalone single-backtest run, never touched by SweepRunner.
    sweep_id: Mapped[int | None] = mapped_column(ForeignKey("sweep_jobs.id"), nullable=True, index=True)
    configurations_tested: Mapped[int] = mapped_column(Integer, default=1)
