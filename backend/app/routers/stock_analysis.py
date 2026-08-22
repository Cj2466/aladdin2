from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.dependencies import get_finnhub_fundamentals_client, get_macro_provider
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.stock_analysis import (
    RecommendationTrendOut,
    StockAnalysisResponse,
    StockFundamentalsOut,
)
from app.services.macro_data.base import MacroDataProvider
from app.services.macro_data.cache import (
    get_latest_macro_snapshot_cached,
    macro_snapshot_to_out,
)
from app.services.macro_data.series import STOCK_MACRO_CONTEXT_SERIES_IDS
from app.services.stock_analysis.cache import (
    StockFundamentalsResult,
    get_stock_fundamentals_cached,
)
from app.services.stock_analysis.finnhub_fundamentals import (
    FinnhubFundamentalsClient,
    FinnhubFundamentalsError,
)
from app.time_utils import utcnow_naive

router = APIRouter(prefix="/api/stocks", tags=["stock-analysis"])


def _to_fundamentals_out(result: StockFundamentalsResult) -> StockFundamentalsOut:
    return StockFundamentalsOut(
        ticker=result.ticker,
        company_name=result.company_name,
        exchange=result.exchange,
        country=result.country,
        currency=result.currency,
        ipo_date=result.ipo_date,
        market_capitalization=result.market_capitalization,
        share_outstanding=result.share_outstanding,
        finnhub_industry=result.finnhub_industry,
        weburl=result.weburl,
        logo=result.logo,
        week52_high=result.week52_high,
        week52_low=result.week52_low,
        beta=result.beta,
        pe_ttm=result.pe_ttm,
        eps_ttm=result.eps_ttm,
        roe_ttm=result.roe_ttm,
        roa_ttm=result.roa_ttm,
        gross_margin_ttm=result.gross_margin_ttm,
        net_margin_ttm=result.net_margin_ttm,
        current_ratio=result.current_ratio,
        quick_ratio=result.quick_ratio,
        debt_to_equity=result.debt_to_equity,
        dividend_yield_ttm=result.dividend_yield_ttm,
        avg_10day_volume=result.avg_10day_volume,
        recommendation_trend=[
            RecommendationTrendOut(
                period=t.period,
                strong_buy=t.strong_buy,
                buy=t.buy,
                hold=t.hold,
                sell=t.sell,
                strong_sell=t.strong_sell,
            )
            for t in result.recommendation_trend
        ],
        peers=result.peers,
        fetched_at=result.fetched_at.isoformat(),
    )


@router.get("/{ticker}/analysis", response_model=StockAnalysisResponse)
@limiter.limit("20/minute")
def get_stock_analysis(
    request: Request,
    ticker: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
    macro_provider: MacroDataProvider = Depends(get_macro_provider),
    fundamentals_client: FinnhubFundamentalsClient = Depends(get_finnhub_fundamentals_client),
) -> StockAnalysisResponse:
    ticker = ticker.strip().upper()

    try:
        fundamentals = get_stock_fundamentals_cached(db, fundamentals_client, ticker)
    except FinnhubFundamentalsError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    if fundamentals is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No data available for ticker '{ticker}'."
        )

    # Curated rates + inflation series only — a stock's macro backdrop, not
    # the full ~16-series dashboard. A failure here degrades to an empty
    # list (get_latest_macro_snapshot_cached already isolates per-series
    # failures) rather than ever breaking the fundamentals half above.
    snapshot = get_latest_macro_snapshot_cached(db, macro_provider)
    macro_context = [
        macro_snapshot_to_out(s) for s in snapshot if s.series_id in STOCK_MACRO_CONTEXT_SERIES_IDS
    ]

    return StockAnalysisResponse(
        fundamentals=_to_fundamentals_out(fundamentals),
        macro_context=macro_context,
        generated_at=utcnow_naive().isoformat(),
    )
