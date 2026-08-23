import hashlib
import json
from datetime import date

import pandas as pd

from app.schemas.research_lab import (
    EquityCurvePointOut,
    PairsBacktestResponse,
    SearchContextOut,
    TradeOut,
)
from app.services.research_lab import metrics
from app.services.research_lab.engine import ExperimentResult
from app.services.research_lab.ou_pairs import STRATEGY_NAME
from app.services.risk.volatility import annualized_volatility

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

SINGLE_CONFIG_SEARCH_NOTE = "This is 1 configuration tested, not selected from a search over parameters."


def compute_pairs_backtest_input_hash(
    *,
    ticker_a: str,
    ticker_b: str,
    fit_window_days: int,
    entry_z: float,
    exit_z: float,
    cost_bps: float,
    lookback_years: int,
) -> str:
    # Folds in today's date: lookback_years is relative to "today" (like
    # optimizer.py's own lookback_years), so a request made today covers a
    # different date range than the identical request made tomorrow —
    # mirrors compute_risk_input_hash's exact reasoning. Every varying
    # sweep parameter is part of this payload, so date-folding never
    # causes sweep-combination hash collisions.
    payload = {
        "strategy": STRATEGY_NAME,
        "ticker_a": ticker_a,
        "ticker_b": ticker_b,
        "fit_window_days": fit_window_days,
        "entry_z": entry_z,
        "exit_z": exit_z,
        "cost_bps": cost_bps,
        "lookback_years": lookback_years,
        "date": str(date.today()),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def build_pairs_backtest_response(
    result: ExperimentResult,
    *,
    ticker_a: str,
    ticker_b: str,
    fit_window_days: int,
    entry_z: float,
    exit_z: float,
    cost_bps: float,
    lookback_years: int,
    cached: bool,
    configurations_tested: int = 1,
) -> PairsBacktestResponse:
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

    if configurations_tested <= 1:
        search_note = SINGLE_CONFIG_SEARCH_NOTE
    else:
        search_note = (
            f"This is 1 of {configurations_tested} configurations tested together in one parameter "
            "sweep — compare against the full sweep before trusting any single result."
        )

    return PairsBacktestResponse(
        status=result.status,
        as_of=str(date.today()),
        ticker_a=ticker_a,
        ticker_b=ticker_b,
        fit_window_days=fit_window_days,
        entry_z=entry_z,
        exit_z=exit_z,
        cost_bps=cost_bps,
        lookback_years=lookback_years,
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
        search_context=SearchContextOut(configurations_tested=configurations_tested, note=search_note),
        methodology_note=METHODOLOGY_NOTE,
        warnings=result.warnings,
        cached=cached,
    )
