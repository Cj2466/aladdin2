import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.stock_fundamentals import StockFundamentals
from app.services.stock_analysis.finnhub_fundamentals import (
    FinnhubFundamentalsClient,
    FinnhubFundamentalsError,
    RecommendationTrendPoint,
)
from app.time_utils import utcnow_naive

# Fundamentals ratios move at most daily; the financial-statement data
# behind them updates quarterly — 24h caps Finnhub calls to at most one per
# ticker per day regardless of how many times it's viewed.
DEFAULT_TTL_HOURS = 24


@dataclass
class StockFundamentalsResult:
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
    recommendation_trend: list[RecommendationTrendPoint]
    peers: list[str]
    fetched_at: datetime


def get_stock_fundamentals_cached(
    db: Session,
    client: FinnhubFundamentalsClient,
    ticker: str,
    ttl_hours: int = DEFAULT_TTL_HOURS,
) -> StockFundamentalsResult | None:
    """Read-through cache over StockFundamentals.

    - Fresh cache (< ttl_hours old) -> served directly, no Finnhub call.
    - get_profile raises (network/config failure): serve stale cache if any
      row exists (stale-beats-blank, matching get_ticker_metadata_cached);
      if none exists, the exception propagates — there is genuinely nothing
      to show.
    - get_profile succeeds but returns None (Finnhub confirms no such
      ticker): return None. A stale cached row, if any, is NOT served here
      — unlike the failure case above, Finnhub actively said the ticker no
      longer exists (e.g. delisted), so silently serving old data would be
      more misleading than admitting it's gone.
    - get_profile succeeds with real data: metrics/recommendation/peers are
      each fetched independently, so one failing never blanks the profile
      or the other two — a failed one just falls back to whatever was
      cached before (or None/empty on a ticker's first-ever fetch),
      matching get_latest_macro_snapshot_cached's per-series isolation.
    """
    existing = db.get(StockFundamentals, ticker)
    if existing is not None and existing.fetched_at >= utcnow_naive() - timedelta(hours=ttl_hours):
        return _to_result(existing)

    try:
        profile = client.get_profile(ticker)
    except FinnhubFundamentalsError:
        if existing is not None:
            return _to_result(existing)
        raise

    if profile is None:
        return None

    try:
        metrics = client.get_metrics(ticker)
    except FinnhubFundamentalsError:
        metrics = None

    try:
        recommendation_trend_json = json.dumps([asdict(t) for t in client.get_recommendation_trends(ticker)])
    except FinnhubFundamentalsError:
        recommendation_trend_json = existing.recommendation_trend_json if existing is not None else None

    try:
        peers_json = json.dumps(client.get_peers(ticker))
    except FinnhubFundamentalsError:
        peers_json = existing.peers_json if existing is not None else None

    row = existing if existing is not None else StockFundamentals(ticker=ticker)
    row.company_name = profile.company_name
    row.exchange = profile.exchange
    row.country = profile.country
    row.currency = profile.currency
    row.ipo_date = profile.ipo_date
    row.market_capitalization = profile.market_capitalization
    row.share_outstanding = profile.share_outstanding
    row.finnhub_industry = profile.finnhub_industry
    row.weburl = profile.weburl
    row.logo = profile.logo
    if metrics is not None:
        row.week52_high = metrics.week52_high
        row.week52_low = metrics.week52_low
        row.beta = metrics.beta
        row.pe_ttm = metrics.pe_ttm
        row.eps_ttm = metrics.eps_ttm
        row.roe_ttm = metrics.roe_ttm
        row.roa_ttm = metrics.roa_ttm
        row.gross_margin_ttm = metrics.gross_margin_ttm
        row.net_margin_ttm = metrics.net_margin_ttm
        row.current_ratio = metrics.current_ratio
        row.quick_ratio = metrics.quick_ratio
        row.debt_to_equity = metrics.debt_to_equity
        row.dividend_yield_ttm = metrics.dividend_yield_ttm
        row.avg_10day_volume = metrics.avg_10day_volume
    row.recommendation_trend_json = recommendation_trend_json
    row.peers_json = peers_json
    row.fetched_at = utcnow_naive()

    if existing is None:
        db.add(row)
    db.commit()

    return _to_result(row)


def _to_result(row: StockFundamentals) -> StockFundamentalsResult:
    recommendation_trend = (
        [RecommendationTrendPoint(**t) for t in json.loads(row.recommendation_trend_json)]
        if row.recommendation_trend_json
        else []
    )
    peers = json.loads(row.peers_json) if row.peers_json else []
    return StockFundamentalsResult(
        ticker=row.ticker,
        company_name=row.company_name,
        exchange=row.exchange,
        country=row.country,
        currency=row.currency,
        ipo_date=row.ipo_date,
        market_capitalization=row.market_capitalization,
        share_outstanding=row.share_outstanding,
        finnhub_industry=row.finnhub_industry,
        weburl=row.weburl,
        logo=row.logo,
        week52_high=row.week52_high,
        week52_low=row.week52_low,
        beta=row.beta,
        pe_ttm=row.pe_ttm,
        eps_ttm=row.eps_ttm,
        roe_ttm=row.roe_ttm,
        roa_ttm=row.roa_ttm,
        gross_margin_ttm=row.gross_margin_ttm,
        net_margin_ttm=row.net_margin_ttm,
        current_ratio=row.current_ratio,
        quick_ratio=row.quick_ratio,
        debt_to_equity=row.debt_to_equity,
        dividend_yield_ttm=row.dividend_yield_ttm,
        avg_10day_volume=row.avg_10day_volume,
        recommendation_trend=recommendation_trend,
        peers=peers,
        fetched_at=row.fetched_at,
    )
