from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.config import settings
from app.db import get_db
from app.dependencies import get_provider
from app.models.user import User
from app.schemas.optimizer import (
    OptimizedHoldingOut,
    PortfolioOptimizeRequest,
    PortfolioOptimizeResponse,
    SavedPortfolioOptimizeResponse,
)
from app.services.market_data.base import MarketDataError, MarketDataProvider
from app.services.market_data.price_cache import get_price_history_cached
from app.services.portfolio_service import get_owned_portfolio, to_weights_dict
from app.services.risk.errors import (
    InsufficientHistoryError,
    MissingTickerDataError,
    OptimizationInfeasibleError,
)
from app.services.risk.optimizer import DEFAULT_MAX_WEIGHT, compute_portfolio_optimization

router = APIRouter(prefix="/api/portfolios", tags=["optimizer"])


def _build_response(
    weights: dict[str, float], lookback_years: int, db: Session, provider: MarketDataProvider
) -> PortfolioOptimizeResponse:
    def prices_fn(tickers, start, end):
        return get_price_history_cached(db, provider, tickers, start, end)

    try:
        result = compute_portfolio_optimization(
            weights, lookback_years, prices_fn, settings.risk_free_rate
        )
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except MissingTickerDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InsufficientHistoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OptimizationInfeasibleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return PortfolioOptimizeResponse(
        as_of=result.as_of,
        lookback_years=lookback_years,
        risk_free_rate=settings.risk_free_rate,
        max_weight_cap=DEFAULT_MAX_WEIGHT,
        optimized_weights=[
            OptimizedHoldingOut(ticker=t, weight=w) for t, w in result.optimized_weights.items()
        ],
        optimized_expected_return=result.optimized.expected_return,
        optimized_volatility=result.optimized.volatility,
        optimized_sharpe=result.optimized.sharpe,
        current_expected_return=result.current.expected_return,
        current_volatility=result.current.volatility,
        current_sharpe=result.current.sharpe,
        warnings=result.warnings,
    )


@router.post("/optimize", response_model=PortfolioOptimizeResponse)
def optimize_portfolio(
    request: PortfolioOptimizeRequest,
    db: Session = Depends(get_db),
    provider: MarketDataProvider = Depends(get_provider),
) -> PortfolioOptimizeResponse:
    weights = {h.ticker: h.weight for h in request.holdings}
    return _build_response(weights, request.lookback_years, db, provider)


@router.get("/{portfolio_id}/optimize", response_model=SavedPortfolioOptimizeResponse)
def optimize_saved_portfolio(
    portfolio_id: int,
    lookback_years: int = 3,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    provider: MarketDataProvider = Depends(get_provider),
) -> SavedPortfolioOptimizeResponse:
    portfolio = get_owned_portfolio(db, portfolio_id, current_user)
    weights = to_weights_dict(portfolio)
    result = _build_response(weights, lookback_years, db, provider)
    return SavedPortfolioOptimizeResponse(**result.model_dump(), portfolio_id=portfolio_id)
