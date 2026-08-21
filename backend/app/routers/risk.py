from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_provider
from app.schemas.risk import PortfolioAnalyzeRequest, PortfolioAnalyzeResponse
from app.services.market_data.base import MarketDataError, MarketDataProvider
from app.services.market_data.price_cache import get_price_history_cached
from app.services.risk.engine import compute_portfolio_risk
from app.services.risk.errors import InsufficientHistoryError, MissingTickerDataError

router = APIRouter(prefix="/api/portfolios", tags=["risk"])


@router.post("/analyze", response_model=PortfolioAnalyzeResponse)
def analyze_portfolio(
    request: PortfolioAnalyzeRequest,
    db: Session = Depends(get_db),
    provider: MarketDataProvider = Depends(get_provider),
) -> PortfolioAnalyzeResponse:
    weights = {h.ticker: h.weight for h in request.holdings}

    def prices_fn(tickers, start, end):
        return get_price_history_cached(db, provider, tickers, start, end)

    try:
        return compute_portfolio_risk(weights, request.benchmark, request.lookback_years, prices_fn)
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except MissingTickerDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InsufficientHistoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
