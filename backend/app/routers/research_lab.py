import json
from dataclasses import asdict
from typing import Literal

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.dependencies import get_provider
from app.models.experiment_run import ExperimentRun
from app.models.user import User
from app.schemas.experiment_run import (
    ExperimentRunLeaderboardResponse,
    ExperimentRunSummaryOut,
)
from app.schemas.research_lab import (
    DeflatedSharpeOut,
    MomentumBacktestRequest,
    PairsBacktestRequest,
    PairsBacktestResponse,
    SharpeRobustnessOut,
)
from app.services.market_data.base import MarketDataError, MarketDataProvider
from app.services.research_lab.backtest_result import (
    run_and_store_momentum_backtest,
    run_and_store_pairs_backtest,
)
from app.services.research_lab.deflated_sharpe import (
    compute_deflated_sharpe,
    derive_returns_from_equity_curve,
)
from app.services.research_lab.sharpe_robustness import compute_sharpe_robustness
from app.services.risk.errors import InsufficientHistoryError, MissingTickerDataError

router = APIRouter(prefix="/api/research-lab", tags=["research-lab"])

SORTABLE_COLUMNS = {
    "sharpe_net": ExperimentRun.sharpe_net,
    "sharpe_gross": ExperimentRun.sharpe_gross,
    "max_drawdown_net": ExperimentRun.max_drawdown_net,
    "num_trades": ExperimentRun.num_trades,
    "win_rate": ExperimentRun.win_rate,
    "computed_at": ExperimentRun.computed_at,
}


def _to_summary_out(row: ExperimentRun, n_trials_same_setup: int) -> ExperimentRunSummaryOut:
    return ExperimentRunSummaryOut(
        id=row.id,
        strategy_name=row.strategy_name,
        ticker_a=row.ticker_a,
        ticker_b=row.ticker_b,
        status=row.status,
        computed_at=row.computed_at.isoformat(),
        fit_window_days=row.fit_window_days,
        entry_z=row.entry_z,
        exit_z=row.exit_z,
        cost_bps=row.cost_bps,
        lookback_years=row.lookback_years,
        num_trades=row.num_trades,
        sharpe_net=row.sharpe_net,
        sharpe_gross=row.sharpe_gross,
        max_drawdown_net=row.max_drawdown_net,
        win_rate=row.win_rate,
        sweep_id=row.sweep_id,
        configurations_tested=row.configurations_tested,
        n_trials_same_setup=n_trials_same_setup,
    )


@router.post("/pairs-backtest", response_model=PairsBacktestResponse)
def run_pairs_backtest_endpoint(
    request: PairsBacktestRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
    provider: MarketDataProvider = Depends(get_provider),
) -> PairsBacktestResponse:
    try:
        return run_and_store_pairs_backtest(
            db,
            provider,
            ticker_a=request.ticker_a,
            ticker_b=request.ticker_b,
            fit_window_days=request.fit_window_days,
            entry_z=request.entry_z,
            exit_z=request.exit_z,
            cost_bps=request.cost_bps,
            lookback_years=request.lookback_years,
        )
    except MarketDataError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except MissingTickerDataError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except InsufficientHistoryError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/momentum-backtest", response_model=PairsBacktestResponse)
def run_momentum_backtest_endpoint(
    request: MomentumBacktestRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
    provider: MarketDataProvider = Depends(get_provider),
) -> PairsBacktestResponse:
    try:
        return run_and_store_momentum_backtest(
            db,
            provider,
            ticker=request.ticker,
            fit_window_days=request.fit_window_days,
            entry_z=request.entry_z,
            exit_z=request.exit_z,
            cost_bps=request.cost_bps,
            lookback_years=request.lookback_years,
        )
    except MarketDataError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except MissingTickerDataError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except InsufficientHistoryError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/experiment-runs", response_model=ExperimentRunLeaderboardResponse)
def list_experiment_runs(
    sort_by: Literal["sharpe_net", "sharpe_gross", "max_drawdown_net", "num_trades", "win_rate", "computed_at"] = "sharpe_net",
    sort_dir: Literal["asc", "desc"] = "desc",
    ticker_a: str | None = None,
    ticker_b: str | None = None,
    strategy_name: str | None = None,
    sweep_id: int | None = None,
    status_filter: Literal["ok", "not_mean_reverting", "insufficient_history", "not_trending"] | None = Query(
        default=None, alias="status"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> ExperimentRunLeaderboardResponse:
    query = select(ExperimentRun)
    count_query = select(func.count()).select_from(ExperimentRun)
    if ticker_a is not None:
        query = query.where(ExperimentRun.ticker_a == ticker_a.strip().upper())
        count_query = count_query.where(ExperimentRun.ticker_a == ticker_a.strip().upper())
    if ticker_b is not None:
        query = query.where(ExperimentRun.ticker_b == ticker_b.strip().upper())
        count_query = count_query.where(ExperimentRun.ticker_b == ticker_b.strip().upper())
    if strategy_name is not None:
        query = query.where(ExperimentRun.strategy_name == strategy_name)
        count_query = count_query.where(ExperimentRun.strategy_name == strategy_name)
    if sweep_id is not None:
        query = query.where(ExperimentRun.sweep_id == sweep_id)
        count_query = count_query.where(ExperimentRun.sweep_id == sweep_id)
    if status_filter is not None:
        query = query.where(ExperimentRun.status == status_filter)
        count_query = count_query.where(ExperimentRun.status == status_filter)

    total_matching = db.execute(count_query).scalar_one()

    sort_column = SORTABLE_COLUMNS[sort_by]
    # nulls_last regardless of direction — a None Sharpe from an
    # insufficient_history row must never sort ahead of real numbers.
    order = sort_column.desc().nulls_last() if sort_dir == "desc" else sort_column.asc().nulls_last()
    query = query.order_by(order).limit(limit).offset(offset)

    rows = db.execute(query).scalars().all()

    # Cheap all-time trial count per (strategy, ticker_a, ticker_b) present on this
    # page — one aggregate query for the whole page, not N+1 per row. Distinct from
    # configurations_tested (sweep-scoped only) — see deflated_sharpe.py's module
    # docstring for why this is the honest N for a multiple-comparisons correction.
    triplets = {(r.strategy_name, r.ticker_a, r.ticker_b) for r in rows}
    trial_counts: dict[tuple[str, str, str], int] = {}
    if triplets:
        group_rows = db.execute(
            select(ExperimentRun.strategy_name, ExperimentRun.ticker_a, ExperimentRun.ticker_b, func.count())
            .where(tuple_(ExperimentRun.strategy_name, ExperimentRun.ticker_a, ExperimentRun.ticker_b).in_(triplets))
            .where(ExperimentRun.status == "ok", ExperimentRun.sharpe_net.is_not(None))
            .group_by(ExperimentRun.strategy_name, ExperimentRun.ticker_a, ExperimentRun.ticker_b)
        ).all()
        trial_counts = {(s, a, b): n for s, a, b, n in group_rows}

    return ExperimentRunLeaderboardResponse(
        results=[
            _to_summary_out(r, trial_counts.get((r.strategy_name, r.ticker_a, r.ticker_b), 0)) for r in rows
        ],
        total_matching=total_matching,
        limit=limit,
        offset=offset,
    )


@router.get("/experiment-runs/{run_id}", response_model=PairsBacktestResponse)
def get_experiment_run_detail(
    run_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> PairsBacktestResponse:
    row = db.get(ExperimentRun, run_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experiment run not found")

    # A cached results_json blob predating strategy_name's addition to
    # PairsBacktestResponse (Phase 1.5) won't have the key — the row's own
    # typed strategy_name column (NOT NULL, always populated) is the
    # authoritative fallback, not a guess.
    payload = json.loads(row.results_json)
    payload.setdefault("strategy_name", row.strategy_name)
    response = PairsBacktestResponse(**payload)

    if row.status == "ok" and row.sharpe_net is not None:
        sibling_sharpes = (
            db.execute(
                select(ExperimentRun.sharpe_net).where(
                    ExperimentRun.strategy_name == row.strategy_name,
                    ExperimentRun.ticker_a == row.ticker_a,
                    ExperimentRun.ticker_b == row.ticker_b,
                    ExperimentRun.status == "ok",
                    ExperimentRun.sharpe_net.is_not(None),
                )
            )
            .scalars()
            .all()
        )
        n_trials = len(sibling_sharpes)
        sigma_sr = float(np.std(sibling_sharpes, ddof=1)) if n_trials >= 2 else None
        returns = derive_returns_from_equity_curve([p.equity for p in response.equity_curve])
        result = compute_deflated_sharpe(row.sharpe_net, returns, n_trials, sigma_sr)
        response.deflated_sharpe = DeflatedSharpeOut(**asdict(result))

        robustness = compute_sharpe_robustness(
            returns, [t.holding_days for t in response.trade_log], row.sharpe_net
        )
        if robustness is not None:
            response.sharpe_robustness = SharpeRobustnessOut(**asdict(robustness))

    return response
