import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.dependencies import get_provider
from app.models.holding import Holding
from app.models.portfolio import Portfolio
from app.models.risk_result import RiskResult
from app.models.user import User
from app.schemas.portfolio import (
    PortfolioCreate,
    PortfolioOut,
    PortfolioSummary,
    PortfolioUpdate,
    SavedPortfolioAnalyzeResponse,
)
from app.services.market_data.base import MarketDataError, MarketDataProvider
from app.services.market_data.price_cache import get_price_history_cached
from app.services.portfolio_service import (
    compute_risk_input_hash,
    get_owned_portfolio,
    to_weights_dict,
)
from app.services.risk.engine import compute_portfolio_risk
from app.services.risk.errors import InsufficientHistoryError, MissingTickerDataError

router = APIRouter(prefix="/api/portfolios", tags=["portfolios"])


@router.post("", response_model=PortfolioOut, status_code=status.HTTP_201_CREATED)
def create_portfolio(
    payload: PortfolioCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Portfolio:
    portfolio = Portfolio(
        user_id=current_user.id, name=payload.name, base_currency=payload.base_currency
    )
    portfolio.holdings = [Holding(ticker=h.ticker, weight=h.weight) for h in payload.holdings]
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)
    return portfolio


@router.get("", response_model=list[PortfolioSummary])
def list_portfolios(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PortfolioSummary]:
    portfolios = (
        db.execute(
            select(Portfolio)
            .where(Portfolio.user_id == current_user.id)
            .options(selectinload(Portfolio.holdings))
            .order_by(Portfolio.updated_at.desc())
        )
        .scalars()
        .all()
    )
    return [
        PortfolioSummary(
            id=p.id,
            name=p.name,
            base_currency=p.base_currency,
            updated_at=p.updated_at,
            holding_count=len(p.holdings),
        )
        for p in portfolios
    ]


@router.get("/{portfolio_id}", response_model=PortfolioOut)
def get_portfolio(
    portfolio_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Portfolio:
    return get_owned_portfolio(db, portfolio_id, current_user)


@router.put("/{portfolio_id}", response_model=PortfolioOut)
def update_portfolio(
    portfolio_id: int,
    payload: PortfolioUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Portfolio:
    portfolio = get_owned_portfolio(db, portfolio_id, current_user)
    portfolio.name = payload.name
    portfolio.base_currency = payload.base_currency
    portfolio.holdings = [Holding(ticker=h.ticker, weight=h.weight) for h in payload.holdings]
    db.commit()
    db.refresh(portfolio)
    return portfolio


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_portfolio(
    portfolio_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    portfolio = get_owned_portfolio(db, portfolio_id, current_user)
    db.delete(portfolio)
    db.commit()


@router.get("/{portfolio_id}/analyze", response_model=SavedPortfolioAnalyzeResponse)
def analyze_saved_portfolio(
    portfolio_id: int,
    benchmark: str = "SPY",
    lookback_years: int = 3,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    provider: MarketDataProvider = Depends(get_provider),
) -> SavedPortfolioAnalyzeResponse:
    portfolio = get_owned_portfolio(db, portfolio_id, current_user)
    weights = to_weights_dict(portfolio)
    benchmark = benchmark.strip().upper()

    input_hash = compute_risk_input_hash(weights, benchmark, lookback_years)
    cached_row = db.execute(
        select(RiskResult).where(
            RiskResult.portfolio_id == portfolio_id, RiskResult.input_hash == input_hash
        )
    ).scalar_one_or_none()
    if cached_row is not None:
        metrics = json.loads(cached_row.metrics_json)
        return SavedPortfolioAnalyzeResponse(**metrics, portfolio_id=portfolio_id, cached=True)

    def prices_fn(tickers, start, end):
        return get_price_history_cached(db, provider, tickers, start, end)

    try:
        result = compute_portfolio_risk(weights, benchmark, lookback_years, prices_fn)
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except MissingTickerDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InsufficientHistoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    db.add(
        RiskResult(
            portfolio_id=portfolio_id,
            input_hash=input_hash,
            metrics_json=result.model_dump_json(),
        )
    )
    db.commit()
    return SavedPortfolioAnalyzeResponse(**result.model_dump(), portfolio_id=portfolio_id, cached=False)
