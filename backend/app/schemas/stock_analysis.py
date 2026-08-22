from pydantic import BaseModel

from app.schemas.macro import MacroSeriesOut


class RecommendationTrendOut(BaseModel):
    period: str
    strong_buy: int
    buy: int
    hold: int
    sell: int
    strong_sell: int


class StockFundamentalsOut(BaseModel):
    ticker: str
    company_name: str | None
    exchange: str | None
    country: str | None
    currency: str | None
    ipo_date: str | None
    market_capitalization: float | None
    share_outstanding: float | None
    finnhub_industry: str | None
    weburl: str | None
    logo: str | None
    week52_high: float | None
    week52_low: float | None
    beta: float | None
    pe_ttm: float | None
    eps_ttm: float | None
    roe_ttm: float | None
    roa_ttm: float | None
    gross_margin_ttm: float | None
    net_margin_ttm: float | None
    current_ratio: float | None
    quick_ratio: float | None
    debt_to_equity: float | None
    dividend_yield_ttm: float | None
    avg_10day_volume: float | None
    recommendation_trend: list[RecommendationTrendOut]
    peers: list[str]
    fetched_at: str


class StockAnalysisResponse(BaseModel):
    fundamentals: StockFundamentalsOut
    # Reuses the existing macro schema — same shape as the main dashboard,
    # curated to STOCK_MACRO_CONTEXT_SERIES_IDS — so the frontend can reuse
    # MacroStatCard-style rendering as-is.
    macro_context: list[MacroSeriesOut]
    generated_at: str
