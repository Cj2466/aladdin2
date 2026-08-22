from datetime import datetime

from sqlalchemy import DateTime, Float, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class StockFundamentals(Base):
    """Shared fundamentals cache, not user-scoped — same reasoning as
    TickerMetadata. Deliberately a separate table from TickerMetadata
    (sector/industry/asset-class, 30-day TTL): fundamentals refresh on a
    much shorter cycle and have a much wider field set."""

    __tablename__ = "stock_fundamentals"

    ticker: Mapped[str] = mapped_column(String(10), primary_key=True)

    # --- profile2 ---
    company_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    exchange: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(10), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ipo_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    market_capitalization: Mapped[float | None] = mapped_column(Float, nullable=True)
    share_outstanding: Mapped[float | None] = mapped_column(Float, nullable=True)
    finnhub_industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    weburl: Mapped[str | None] = mapped_column(String(300), nullable=True)
    logo: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # --- metric?metric=all, curated subset ---
    week52_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    week52_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    beta: Mapped[float | None] = mapped_column(Float, nullable=True)
    pe_ttm: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps_ttm: Mapped[float | None] = mapped_column(Float, nullable=True)
    roe_ttm: Mapped[float | None] = mapped_column(Float, nullable=True)
    roa_ttm: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_margin_ttm: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_margin_ttm: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    quick_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    debt_to_equity: Mapped[float | None] = mapped_column(Float, nullable=True)
    dividend_yield_ttm: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_10day_volume: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- variable-shape data, same JSON-text convention as RiskResult.metrics_json ---
    recommendation_trend_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    peers_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
