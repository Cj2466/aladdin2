import hashlib
import json
from datetime import date

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.dependencies import get_provider
from app.models.experiment_run import ExperimentRun
from app.models.user import User
from app.schemas.research_lab import (
    EquityCurvePointOut,
    PairsBacktestRequest,
    PairsBacktestResponse,
    SearchContextOut,
    TradeOut,
)
from app.services.market_data.base import MarketDataError, MarketDataProvider
from app.services.market_data.price_cache import get_price_history_cached
from app.services.research_lab import metrics
from app.services.research_lab.engine import ExperimentResult, WalkForwardConfig
from app.services.research_lab.ou_pairs import STRATEGY_NAME, run_pairs_backtest
from app.services.risk.errors import InsufficientHistoryError, MissingTickerDataError
from app.services.risk.volatility import annualized_volatility

router = APIRouter(prefix="/api/research-lab", tags=["research-lab"])

METHODOLOGY_NOTE = (
    "Research tool, not a trading signal. Each day's position is decided from a rolling "
    "Ornstein-Uhlenbeck/AR(1) fit on prior data only — day t's decision cannot see day t's own "
    "price move (verified by a dedicated test). The AR(1) fit-quality score measures how well the "
    "spread fits an AR(1) model over that window, NOT whether the two tickers are genuinely "
    "cointegrated: numerically verified this session, independent random walks pass this fit's "
    "own sanity check ~97-100% of the time with a spuriously 'strong' score. Only the walk-forward, "
    "out-of-sample Sharpe below carries evidentiary weight — a single window's fit quality does "
    "not. This is one configuration tested, not selected from a search (see search_context). "
    "Historical performance, however clean, is no guarantee of future performance."
)

SEARCH_CONTEXT_NOTE = "This is 1 configuration tested, not selected from a search over parameters."


def _compute_input_hash(request: PairsBacktestRequest) -> str:
    # Folds in today's date: lookback_years is relative to "today" (like
    # optimizer.py's own lookback_years), so a request made today covers a
    # different date range than the identical request made tomorrow —
    # mirrors compute_risk_input_hash's exact reasoning.
    payload = {
        "strategy": STRATEGY_NAME,
        "ticker_a": request.ticker_a,
        "ticker_b": request.ticker_b,
        "fit_window_days": request.fit_window_days,
        "entry_z": request.entry_z,
        "exit_z": request.exit_z,
        "cost_bps": request.cost_bps,
        "lookback_years": request.lookback_years,
        "date": str(date.today()),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _build_response(result: ExperimentResult, request: PairsBacktestRequest, *, cached: bool) -> PairsBacktestResponse:
    equity_curve = [
        EquityCurvePointOut(
            date=d.date.strftime("%Y-%m-%d"), equity=d.equity, position=d.position, z_score=d.z_score
        )
        for d in result.day_results
    ]
    trade_log = [
        TradeOut(
            entry_date=t.entry_date.strftime("%Y-%m-%d"),
            exit_date=t.exit_date.strftime("%Y-%m-%d") if t.exit_date is not None else None,
            direction=t.direction,
            holding_days=t.holding_days,
            trade_return=t.trade_return,
            still_open=t.still_open,
        )
        for t in result.trades
    ]

    has_days = len(result.day_results) > 0
    net_returns = pd.Series([d.net_return for d in result.day_results]) if has_days else None
    raw_returns = pd.Series([d.raw_return for d in result.day_results]) if has_days else None
    equity_series = pd.Series([d.equity for d in result.day_results]) if has_days else None

    return PairsBacktestResponse(
        status=result.status,
        as_of=str(date.today()),
        ticker_a=request.ticker_a,
        ticker_b=request.ticker_b,
        fit_window_days=request.fit_window_days,
        entry_z=request.entry_z,
        exit_z=request.exit_z,
        cost_bps=request.cost_bps,
        lookback_years=request.lookback_years,
        n_trading_days=result.n_trading_days,
        n_out_of_sample_days=result.n_out_of_sample_days,
        total_return_net=float(equity_series.iloc[-1] - 1.0) if has_days else None,
        annualized_return_net=float(net_returns.mean() * 252) if has_days else None,
        annualized_volatility_net=annualized_volatility(net_returns) if has_days else None,
        sharpe_net=metrics.sharpe_ratio(net_returns) if has_days else None,
        sharpe_gross=metrics.sharpe_ratio(raw_returns) if has_days else None,
        max_drawdown_net=metrics.max_drawdown(equity_series) if has_days else None,
        num_trades=len(result.trades),
        win_rate=metrics.hit_rate(result.trades),
        exposure_pct=metrics.exposure_pct(result.day_results) if has_days else None,
        total_cost_drag=metrics.total_cost_drag(result.day_results) if has_days else None,
        pct_days_mean_reverting=result.pct_days_mean_reverting,
        fit_quality_distribution=result.fit_quality_distribution,
        equity_curve=equity_curve,
        trade_log=trade_log,
        search_context=SearchContextOut(configurations_tested=1, note=SEARCH_CONTEXT_NOTE),
        methodology_note=METHODOLOGY_NOTE,
        warnings=result.warnings,
        cached=cached,
    )


@router.post("/pairs-backtest", response_model=PairsBacktestResponse)
def run_pairs_backtest_endpoint(
    request: PairsBacktestRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
    provider: MarketDataProvider = Depends(get_provider),
) -> PairsBacktestResponse:
    input_hash = _compute_input_hash(request)
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

    response = _build_response(result, request, cached=False)
    db.add(
        ExperimentRun(
            strategy_name=STRATEGY_NAME,
            ticker_a=request.ticker_a,
            ticker_b=request.ticker_b,
            input_hash=input_hash,
            results_json=response.model_dump_json(),
        )
    )
    db.commit()
    return response
