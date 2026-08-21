from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.dependencies import get_provider
from app.models.user import User
from app.services.market_data.base import MarketDataError, MarketDataProvider
from app.services.market_data.price_cache import get_price_history_cached
from app.services.portfolio_service import get_owned_portfolio, to_weights_dict
from app.services.reports.csv_report import build_csv_report
from app.services.reports.pdf_report import build_pdf_report
from app.services.risk.engine import compute_portfolio_risk
from app.services.risk.errors import InsufficientHistoryError, MissingTickerDataError
from app.services.risk.stress import compute_stress_impact

router = APIRouter(prefix="/api/portfolios", tags=["export"])


@router.get("/{portfolio_id}/export")
def export_portfolio_report(
    portfolio_id: int,
    format: Literal["csv", "pdf"] = "csv",
    benchmark: str = "SPY",
    lookback_years: int = 3,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    provider: MarketDataProvider = Depends(get_provider),
) -> Response:
    portfolio = get_owned_portfolio(db, portfolio_id, current_user)
    weights = to_weights_dict(portfolio)
    benchmark = benchmark.strip().upper()

    def prices_fn(tickers, start, end):
        return get_price_history_cached(db, provider, tickers, start, end)

    try:
        analyze_result = compute_portfolio_risk(weights, benchmark, lookback_years, prices_fn)
        stress_results = compute_stress_impact(weights, benchmark, prices_fn)
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except MissingTickerDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InsufficientHistoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if format == "csv":
        body: bytes | str = build_csv_report(portfolio, analyze_result, stress_results)
        media_type = "text/csv"
    else:
        body = build_pdf_report(portfolio, analyze_result, stress_results)
        media_type = "application/pdf"

    filename = f"portfolio_{portfolio_id}_report.{format}"
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
