from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, sessionmaker

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.dependencies import get_provider
from app.models.user import User
from app.schemas.stress import (
    ExposureSliceOut,
    HoldingStressOut,
    ScenarioOut,
    StressTestRequest,
    StressTestResponse,
)
from app.services.market_data.base import MarketDataError, MarketDataProvider, TickerMetadataResult
from app.services.market_data.metadata_cache import get_ticker_metadata_cached
from app.services.market_data.price_cache import get_price_history_cached
from app.services.portfolio_service import get_owned_portfolio, to_weights_dict
from app.services.risk.exposure import aggregate_asset_class_exposure, aggregate_sector_exposure
from app.services.risk.stress import compute_stress_impact

router = APIRouter(prefix="/api/portfolios", tags=["stress"])

METADATA_FETCH_WORKERS = 5


def _fetch_metadata(
    session_factory: sessionmaker, provider: MarketDataProvider, ticker: str
) -> TickerMetadataResult | None:
    # Each worker gets its own session — SQLAlchemy sessions aren't
    # thread-safe to share, and the request's own `db` session is already
    # in use on the main thread for the price-history query. Built from the
    # request session's own bind (not the global app.db.SessionLocal) so
    # this respects whatever engine the request is actually using — the
    # production engine at runtime, or the test suite's overridden one.
    with session_factory() as db:
        return get_ticker_metadata_cached(db, provider, ticker)


def _build_response(
    weights: dict[str, float], benchmark: str, db: Session, provider: MarketDataProvider
) -> StressTestResponse:
    def prices_fn(tickers, start, end):
        return get_price_history_cached(db, provider, tickers, start, end)

    try:
        scenario_results = compute_stress_impact(weights, benchmark, prices_fn)
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    tickers = list(weights)
    session_factory = sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False)
    with ThreadPoolExecutor(max_workers=METADATA_FETCH_WORKERS) as executor:
        results = list(
            executor.map(lambda t: _fetch_metadata(session_factory, provider, t), tickers)
        )
    metadata: dict[str, TickerMetadataResult | None] = dict(zip(tickers, results))
    warnings: list[str] = [
        f"No sector/asset-class metadata available for {ticker}"
        for ticker, result in metadata.items()
        if result is None
    ]

    sector_exposure = aggregate_sector_exposure(weights, metadata)
    asset_class_exposure = aggregate_asset_class_exposure(weights, metadata)

    return StressTestResponse(
        scenarios=[
            ScenarioOut(
                scenario_id=s.scenario_id,
                label=s.label,
                description=s.description,
                start=s.start,
                end=s.end,
                portfolio_return=s.portfolio_return,
                benchmark_return=s.benchmark_return,
                has_estimated=s.has_estimated,
                holdings=[
                    HoldingStressOut(
                        ticker=h.ticker, weight=h.weight, return_pct=h.return_pct, basis=h.basis
                    )
                    for h in s.holdings
                ],
            )
            for s in scenario_results
        ],
        sector_exposure=[ExposureSliceOut(label=e.label, weight=e.weight) for e in sector_exposure],
        asset_class_exposure=[
            ExposureSliceOut(label=e.label, weight=e.weight) for e in asset_class_exposure
        ],
        warnings=warnings,
    )


@router.post("/stress-test", response_model=StressTestResponse)
def stress_test_portfolio(
    request: StressTestRequest,
    db: Session = Depends(get_db),
    provider: MarketDataProvider = Depends(get_provider),
) -> StressTestResponse:
    weights = {h.ticker: h.weight for h in request.holdings}
    return _build_response(weights, request.benchmark, db, provider)


@router.get("/{portfolio_id}/stress-test", response_model=StressTestResponse)
def stress_test_saved_portfolio(
    portfolio_id: int,
    benchmark: str = "SPY",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    provider: MarketDataProvider = Depends(get_provider),
) -> StressTestResponse:
    portfolio = get_owned_portfolio(db, portfolio_id, current_user)
    weights = to_weights_dict(portfolio)
    return _build_response(weights, benchmark.strip().upper(), db, provider)
