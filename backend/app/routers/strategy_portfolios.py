from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.auth.dependencies import get_current_user
from app.config import settings
from app.db import get_db
from app.dependencies import get_provider
from app.models.experiment_run import ExperimentRun
from app.models.strategy_portfolio import StrategyPortfolio
from app.models.strategy_portfolio_allocation import StrategyPortfolioAllocation
from app.models.user import User
from app.schemas.execution import SetLivePortfolioRequest
from app.schemas.optimizer import OptimizedHoldingOut, PortfolioOptimizeResponse
from app.schemas.risk import PortfolioAnalyzeResponse
from app.schemas.strategy_portfolio import (
    SavedStrategyPortfolioAnalyzeResponse,
    SavedStrategyPortfolioOptimizeResponse,
    StrategyAllocationOut,
    StrategyPortfolioAnalyzeRequest,
    StrategyPortfolioCreate,
    StrategyPortfolioOptimizeRequest,
    StrategyPortfolioOut,
    StrategyPortfolioSummary,
    StrategyPortfolioUpdate,
)
from app.services.market_data.base import MarketDataError, MarketDataProvider
from app.services.research_lab.strategy_portfolio_returns import (
    MissingExperimentRunError,
    compute_strategy_portfolio_optimization,
    compute_strategy_portfolio_risk,
)
from app.services.research_lab.system_account import get_system_user_id
from app.services.risk.errors import (
    InsufficientHistoryError,
    MissingTickerDataError,
    OptimizationInfeasibleError,
)
from app.services.risk.optimizer import DEFAULT_MAX_WEIGHT
from app.services.strategy_portfolio_service import (
    get_owned_strategy_portfolio,
    to_allocations_dict,
)

# Its own file, matching the established precedent that screening.py and
# sweeps.py are each their own module despite all being "research-lab"
# concerns, rather than folding into the already-large research_lab.py.
# Not split further (the ticker feature has portfolios.py/optimizer.py/
# stress.py/factor_risk.py) since this ships with exactly two kinds of
# analysis on a brand-new entity — split later if a stress/factor analogue
# is ever added.
router = APIRouter(prefix="/api/research-lab/strategy-portfolios", tags=["research-lab"])


def _to_portfolio_out(
    portfolio: StrategyPortfolio, runs: dict[int, ExperimentRun], system_user_id: int | None
) -> StrategyPortfolioOut:
    allocations = []
    for allocation in portfolio.allocations:
        run = runs.get(allocation.experiment_run_id)
        if run is None:
            # A referenced run vanished (nothing deletes ExperimentRun rows
            # today, but the FK carries no cascade by design). Surfacing the
            # allocation with placeholders keeps the portfolio readable and
            # editable; analyze/optimize raise MissingExperimentRunError.
            allocations.append(
                StrategyAllocationOut(
                    id=allocation.id,
                    experiment_run_id=allocation.experiment_run_id,
                    weight=allocation.weight,
                    strategy_name="unknown",
                    ticker_a="",
                    ticker_b="",
                    status="missing",
                    computed_at=portfolio.created_at,
                    sharpe_net=None,
                )
            )
            continue
        allocations.append(
            StrategyAllocationOut(
                id=allocation.id,
                experiment_run_id=allocation.experiment_run_id,
                weight=allocation.weight,
                strategy_name=run.strategy_name,
                ticker_a=run.ticker_a,
                ticker_b=run.ticker_b,
                status=run.status,
                computed_at=run.computed_at,
                sharpe_net=run.sharpe_net,
            )
        )
    return StrategyPortfolioOut(
        id=portfolio.id,
        name=portfolio.name,
        created_at=portfolio.created_at,
        updated_at=portfolio.updated_at,
        last_optimized_at=portfolio.last_optimized_at,
        is_live=bool(portfolio.is_live),
        allocations=allocations,
        is_system=system_user_id is not None and portfolio.user_id == system_user_id,
    )


def _load_runs(db: Session, portfolio: StrategyPortfolio) -> dict[int, ExperimentRun]:
    run_ids = [a.experiment_run_id for a in portfolio.allocations]
    if not run_ids:
        return {}
    rows = db.execute(select(ExperimentRun).where(ExperimentRun.id.in_(run_ids))).scalars().all()
    return {r.id: r for r in rows}


def _analyze(
    db: Session, provider: MarketDataProvider, allocations: dict[int, float], benchmark: str
) -> PortfolioAnalyzeResponse:
    try:
        return compute_strategy_portfolio_risk(db, provider, allocations, benchmark)
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (MissingExperimentRunError, MissingTickerDataError, InsufficientHistoryError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _optimize(db: Session, allocations: dict[int, float]) -> PortfolioOptimizeResponse:
    try:
        result, measured_years = compute_strategy_portfolio_optimization(
            db, allocations, settings.risk_free_rate
        )
    except (
        MissingExperimentRunError,
        InsufficientHistoryError,
        OptimizationInfeasibleError,
    ) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    warnings = list(result.warnings)
    if round(measured_years) < 1:
        # lookback_years is an int on the shared response model, so a
        # sub-year overlap window would round to a bare "0" with no way to
        # tell whether that meant 3 days or 5 months. Say it precisely
        # instead of letting the rounding quietly swallow it.
        warnings.append(
            f"Measured over only ~{measured_years:.2f} years of overlapping strategy "
            "returns — too short to round to a whole year."
        )

    return PortfolioOptimizeResponse(
        as_of=result.as_of,
        # The ACTUAL measured overlap window, not an echoed-back request
        # parameter (there isn't one here) — strictly more honest than the
        # ticker version, which reports what was asked for rather than what
        # was measured.
        lookback_years=round(measured_years),
        risk_free_rate=settings.risk_free_rate,
        max_weight_cap=DEFAULT_MAX_WEIGHT,
        optimized_weights=[
            OptimizedHoldingOut(ticker=key, weight=w) for key, w in result.optimized_weights.items()
        ],
        optimized_expected_return=result.optimized.expected_return,
        optimized_volatility=result.optimized.volatility,
        optimized_sharpe=result.optimized.sharpe,
        current_expected_return=result.current.expected_return,
        current_volatility=result.current.volatility,
        current_sharpe=result.current.sharpe,
        warnings=warnings,
    )


# --- CRUD ------------------------------------------------------------------


@router.post("", response_model=StrategyPortfolioOut, status_code=status.HTTP_201_CREATED)
def create_strategy_portfolio(
    payload: StrategyPortfolioCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StrategyPortfolioOut:
    portfolio = StrategyPortfolio(user_id=current_user.id, name=payload.name)
    portfolio.allocations = [
        StrategyPortfolioAllocation(experiment_run_id=a.experiment_run_id, weight=a.weight)
        for a in payload.allocations
    ]
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)
    # A real login can never be system-owned — is_system is always False here.
    return _to_portfolio_out(portfolio, _load_runs(db, portfolio), system_user_id=None)


@router.get("", response_model=list[StrategyPortfolioSummary])
def list_strategy_portfolios(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[StrategyPortfolioSummary]:
    # Widened to include the autonomously-maintained system portfolio,
    # exactly like list_screening_jobs / list_forward_validation_registrations.
    # Inert in any DB where no system user exists.
    system_user_id = get_system_user_id(db)
    owner_filter = (
        or_(
            StrategyPortfolio.user_id == current_user.id,
            StrategyPortfolio.user_id == system_user_id,
        )
        if system_user_id is not None
        else StrategyPortfolio.user_id == current_user.id
    )
    portfolios = (
        db.execute(
            select(StrategyPortfolio)
            .where(owner_filter)
            .options(selectinload(StrategyPortfolio.allocations))
            .order_by(StrategyPortfolio.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return [
        StrategyPortfolioSummary(
            id=p.id,
            name=p.name,
            updated_at=p.updated_at,
            last_optimized_at=p.last_optimized_at,
            allocation_count=len(p.allocations),
            is_system=system_user_id is not None and p.user_id == system_user_id,
            is_live=bool(p.is_live),
        )
        for p in portfolios
    ]


@router.get("/{strategy_portfolio_id}", response_model=StrategyPortfolioOut)
def get_strategy_portfolio(
    strategy_portfolio_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StrategyPortfolioOut:
    system_user_id = get_system_user_id(db)
    portfolio = get_owned_strategy_portfolio(db, strategy_portfolio_id, current_user, system_user_id)
    return _to_portfolio_out(portfolio, _load_runs(db, portfolio), system_user_id)


@router.put("/{strategy_portfolio_id}", response_model=StrategyPortfolioOut)
def update_strategy_portfolio(
    strategy_portfolio_id: int,
    payload: StrategyPortfolioUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StrategyPortfolioOut:
    # Strict ownership (no system_user_id) — the system portfolio is
    # read-only to every real user.
    portfolio = get_owned_strategy_portfolio(db, strategy_portfolio_id, current_user)
    portfolio.name = payload.name
    # Clear-and-flush before re-populating, unlike update_portfolio's
    # straight reassignment: StrategyPortfolioAllocation carries a
    # (strategy_portfolio_id, experiment_run_id) UNIQUE constraint that
    # Holding doesn't, and a single flush would otherwise INSERT a
    # re-submitted allocation before DELETEing the old row for the same
    # run — a real IntegrityError, caught by
    # test_create_list_get_update_delete_round_trip.
    portfolio.allocations.clear()
    db.flush()
    portfolio.allocations = [
        StrategyPortfolioAllocation(experiment_run_id=a.experiment_run_id, weight=a.weight)
        for a in payload.allocations
    ]
    db.commit()
    db.refresh(portfolio)
    return _to_portfolio_out(portfolio, _load_runs(db, portfolio), system_user_id=None)


@router.post("/{strategy_portfolio_id}/live", response_model=StrategyPortfolioOut)
def set_strategy_portfolio_live(
    strategy_portfolio_id: int,
    payload: SetLivePortfolioRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StrategyPortfolioOut:
    """Mark which single portfolio ExecutionRunner is allowed to trade.

    Deliberately the ONE mutating path widened to the system-owned portfolio,
    unlike PUT and DELETE. The autonomous chain — screen, backtest, register,
    graduate, prune, combine, optimize — culminates in exactly that portfolio,
    so refusing to let an operator mark it live would mean the fully autonomous
    pipeline could never actually be traded. It is an operator control, not an
    edit of the research content.

    Setting one live clears every other portfolio owned by the SAME owner in
    the same transaction: at most one live portfolio per user, enforced
    atomically here because SQLite cannot easily express a partial unique
    index. Two independently-optimized portfolios trading one broker account
    would break both the capital-fraction accounting and cross-portfolio risk.

    This never starts trading by itself. The kill switch is separate and
    defaults to halted; a human still has to resume.
    """
    system_user_id = get_system_user_id(db)
    portfolio = get_owned_strategy_portfolio(db, strategy_portfolio_id, current_user, system_user_id)

    if payload.is_live:
        db.execute(
            update(StrategyPortfolio)
            .where(
                StrategyPortfolio.user_id == portfolio.user_id,
                StrategyPortfolio.id != portfolio.id,
                StrategyPortfolio.is_live.is_(True),
            )
            .values(is_live=False)
        )
    portfolio.is_live = payload.is_live
    db.commit()
    db.refresh(portfolio)
    return _to_portfolio_out(portfolio, _load_runs(db, portfolio), system_user_id)


@router.delete("/{strategy_portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_strategy_portfolio(
    strategy_portfolio_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    portfolio = get_owned_strategy_portfolio(db, strategy_portfolio_id, current_user)
    db.delete(portfolio)
    db.commit()


# --- Analysis ---------------------------------------------------------------


@router.post("/analyze", response_model=PortfolioAnalyzeResponse)
def analyze_strategy_portfolio(
    request: StrategyPortfolioAnalyzeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    provider: MarketDataProvider = Depends(get_provider),
) -> PortfolioAnalyzeResponse:
    allocations = {a.experiment_run_id: a.weight for a in request.allocations}
    return _analyze(db, provider, allocations, request.benchmark)


@router.get("/{strategy_portfolio_id}/analyze", response_model=SavedStrategyPortfolioAnalyzeResponse)
def analyze_saved_strategy_portfolio(
    strategy_portfolio_id: int,
    benchmark: str = "SPY",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    provider: MarketDataProvider = Depends(get_provider),
) -> SavedStrategyPortfolioAnalyzeResponse:
    system_user_id = get_system_user_id(db)
    portfolio = get_owned_strategy_portfolio(db, strategy_portfolio_id, current_user, system_user_id)
    # No RiskResult-style cache table for v1, deliberately: the ticker
    # feature caches because fetching N tickers' multi-year histories from a
    # live provider is expensive. That expense doesn't exist here — the
    # returns are already in results_json, and only one (already-cached)
    # benchmark ticker is fetched.
    result = _analyze(
        db, provider, to_allocations_dict(portfolio), benchmark.strip().upper()
    )
    return SavedStrategyPortfolioAnalyzeResponse(
        **result.model_dump(), strategy_portfolio_id=strategy_portfolio_id
    )


@router.post("/optimize", response_model=PortfolioOptimizeResponse)
def optimize_strategy_portfolio(
    request: StrategyPortfolioOptimizeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PortfolioOptimizeResponse:
    # No `provider` dependency: this path makes no network call at all.
    allocations = {a.experiment_run_id: a.weight for a in request.allocations}
    return _optimize(db, allocations)


@router.get("/{strategy_portfolio_id}/optimize", response_model=SavedStrategyPortfolioOptimizeResponse)
def optimize_saved_strategy_portfolio(
    strategy_portfolio_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SavedStrategyPortfolioOptimizeResponse:
    system_user_id = get_system_user_id(db)
    portfolio = get_owned_strategy_portfolio(db, strategy_portfolio_id, current_user, system_user_id)
    result = _optimize(db, to_allocations_dict(portfolio))
    return SavedStrategyPortfolioOptimizeResponse(
        **result.model_dump(), strategy_portfolio_id=strategy_portfolio_id
    )
