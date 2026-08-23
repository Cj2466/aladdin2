import json
from datetime import date
from typing import Literal

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.dependencies import get_provider
from app.models.experiment_run import ExperimentRun
from app.models.user import User
from app.schemas.experiment_run import ExperimentRunLeaderboardResponse, ExperimentRunSummaryOut
from app.schemas.research_lab import PairsBacktestRequest, PairsBacktestResponse
from app.services.market_data.base import MarketDataError, MarketDataProvider
from app.services.market_data.price_cache import get_price_history_cached
from app.services.research_lab.backtest_result import (
    build_pairs_backtest_response,
    compute_pairs_backtest_input_hash,
)
from app.services.research_lab.engine import WalkForwardConfig
from app.services.research_lab.ou_pairs import STRATEGY_NAME, run_pairs_backtest
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


def _to_summary_out(row: ExperimentRun) -> ExperimentRunSummaryOut:
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
    )


@router.post("/pairs-backtest", response_model=PairsBacktestResponse)
def run_pairs_backtest_endpoint(
    request: PairsBacktestRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
    provider: MarketDataProvider = Depends(get_provider),
) -> PairsBacktestResponse:
    input_hash = compute_pairs_backtest_input_hash(
        ticker_a=request.ticker_a,
        ticker_b=request.ticker_b,
        fit_window_days=request.fit_window_days,
        entry_z=request.entry_z,
        exit_z=request.exit_z,
        cost_bps=request.cost_bps,
        lookback_years=request.lookback_years,
    )
    cached_row = db.execute(
        select(ExperimentRun).where(ExperimentRun.input_hash == input_hash)
    ).scalar_one_or_none()
    if cached_row is not None:
        payload = json.loads(cached_row.results_json)
        payload["cached"] = True
        return PairsBacktestResponse(**payload)

    config = WalkForwardConfig(
        fit_window_days=request.fit_window_days,
        entry_z=request.entry_z,
        exit_z=request.exit_z,
        cost_bps=request.cost_bps,
    )

    def prices_fn(tickers: list[str], start: date, end: date) -> tuple[pd.DataFrame, list[str]]:
        return get_price_history_cached(db, provider, tickers, start, end)

    try:
        result = run_pairs_backtest(request.ticker_a, request.ticker_b, request.lookback_years, prices_fn, config)
    except MarketDataError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except MissingTickerDataError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except InsufficientHistoryError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    response = build_pairs_backtest_response(
        result,
        ticker_a=request.ticker_a,
        ticker_b=request.ticker_b,
        fit_window_days=request.fit_window_days,
        entry_z=request.entry_z,
        exit_z=request.exit_z,
        cost_bps=request.cost_bps,
        lookback_years=request.lookback_years,
        cached=False,
    )
    db.add(
        ExperimentRun(
            strategy_name=STRATEGY_NAME,
            ticker_a=request.ticker_a,
            ticker_b=request.ticker_b,
            input_hash=input_hash,
            results_json=response.model_dump_json(),
            status=response.status,
            fit_window_days=request.fit_window_days,
            entry_z=request.entry_z,
            exit_z=request.exit_z,
            cost_bps=request.cost_bps,
            lookback_years=request.lookback_years,
            num_trades=response.num_trades,
            sharpe_net=response.sharpe_net,
            sharpe_gross=response.sharpe_gross,
            max_drawdown_net=response.max_drawdown_net,
            win_rate=response.win_rate,
            configurations_tested=1,
        )
    )
    db.commit()
    return response


@router.get("/experiment-runs", response_model=ExperimentRunLeaderboardResponse)
def list_experiment_runs(
    sort_by: Literal["sharpe_net", "sharpe_gross", "max_drawdown_net", "num_trades", "win_rate", "computed_at"] = "sharpe_net",
    sort_dir: Literal["asc", "desc"] = "desc",
    ticker_a: str | None = None,
    ticker_b: str | None = None,
    strategy_name: str | None = None,
    sweep_id: int | None = None,
    status_filter: Literal["ok", "not_mean_reverting", "insufficient_history"] | None = Query(default=None, alias="status"),
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
    return ExperimentRunLeaderboardResponse(
        results=[_to_summary_out(r) for r in rows],
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
    return PairsBacktestResponse(**json.loads(row.results_json))
