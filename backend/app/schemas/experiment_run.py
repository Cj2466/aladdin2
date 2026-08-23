from typing import Literal

from pydantic import BaseModel


class ExperimentRunSummaryOut(BaseModel):
    id: int
    strategy_name: str
    ticker_a: str
    ticker_b: str
    status: Literal["ok", "not_mean_reverting", "insufficient_history"]
    computed_at: str
    fit_window_days: int
    entry_z: float
    exit_z: float
    cost_bps: float
    lookback_years: int
    num_trades: int
    sharpe_net: float | None
    sharpe_gross: float | None
    max_drawdown_net: float | None
    win_rate: float | None
    sweep_id: int | None
    configurations_tested: int


class ExperimentRunLeaderboardResponse(BaseModel):
    results: list[ExperimentRunSummaryOut]
    total_matching: int
    limit: int
    offset: int
