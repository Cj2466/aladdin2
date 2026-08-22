from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.dependencies import get_provider
from app.models.user import User
from app.schemas.factor_risk import (
    FactorExposureOut,
    HoldingFactorFitOut,
    PortfolioFactorRiskRequest,
    PortfolioFactorRiskResponse,
    SavedPortfolioFactorRiskResponse,
)
from app.schemas.stress import ExposureSliceOut
from app.services.market_data.base import MarketDataError, MarketDataProvider
from app.services.market_data.price_cache import get_price_history_cached
from app.services.portfolio_service import get_owned_portfolio, to_weights_dict
from app.services.risk.errors import InsufficientHistoryError, MissingTickerDataError
from app.services.risk.factor_model import FACTOR_DEFINITIONS, compute_factor_risk

router = APIRouter(prefix="/api/portfolios", tags=["factor-risk"])


def _build_response(
    weights: dict[str, float], lookback_years: int, db: Session, provider: MarketDataProvider
) -> PortfolioFactorRiskResponse:
    def prices_fn(tickers, start, end):
        return get_price_history_cached(db, provider, tickers, start, end)

    try:
        result = compute_factor_risk(weights, lookback_years, prices_fn)
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except MissingTickerDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InsufficientHistoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    labels = {d.key: d.label for d in FACTOR_DEFINITIONS}

    factor_detail = [
        FactorExposureOut(
            factor=key,
            label=labels[key],
            exposure=result.factor_exposures[key],
            contribution_pct=result.factor_risk_contribution_pct[key],
        )
        for key in labels
    ]
    risk_contribution = [
        ExposureSliceOut(label=labels[key], weight=max(0.0, result.factor_risk_contribution_pct[key]))
        for key in labels
    ] + [ExposureSliceOut(label="Stock-specific", weight=result.idiosyncratic_risk_pct)]

    return PortfolioFactorRiskResponse(
        as_of=result.as_of,
        lookback_years=lookback_years,
        factor_detail=factor_detail,
        risk_contribution=risk_contribution,
        idiosyncratic_risk_pct=result.idiosyncratic_risk_pct,
        factor_variance_annualized=result.factor_variance_annualized,
        idiosyncratic_variance_annualized=result.idiosyncratic_variance_annualized,
        total_variance_annualized=result.total_variance_annualized,
        holdings=[
            HoldingFactorFitOut(
                ticker=h.ticker,
                betas=h.betas,
                r_squared=h.r_squared,
                idiosyncratic_volatility_annualized=h.idiosyncratic_volatility_annualized,
            )
            for h in result.holdings
        ],
        warnings=result.warnings,
    )


@router.post("/factor-risk", response_model=PortfolioFactorRiskResponse)
def factor_risk_portfolio(
    request: PortfolioFactorRiskRequest,
    db: Session = Depends(get_db),
    provider: MarketDataProvider = Depends(get_provider),
) -> PortfolioFactorRiskResponse:
    weights = {h.ticker: h.weight for h in request.holdings}
    return _build_response(weights, request.lookback_years, db, provider)


@router.get("/{portfolio_id}/factor-risk", response_model=SavedPortfolioFactorRiskResponse)
def factor_risk_saved_portfolio(
    portfolio_id: int,
    lookback_years: int = 3,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    provider: MarketDataProvider = Depends(get_provider),
) -> SavedPortfolioFactorRiskResponse:
    portfolio = get_owned_portfolio(db, portfolio_id, current_user)
    weights = to_weights_dict(portfolio)
    result = _build_response(weights, lookback_years, db, provider)
    return SavedPortfolioFactorRiskResponse(**result.model_dump(), portfolio_id=portfolio_id)
