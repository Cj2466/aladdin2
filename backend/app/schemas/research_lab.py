from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.research_lab.ou_pairs import (
    DEFAULT_COST_BPS,
    DEFAULT_ENTRY_Z,
    DEFAULT_EXIT_Z,
    DEFAULT_FIT_WINDOW_DAYS,
    DEFAULT_LOOKBACK_YEARS,
)


class PairsBacktestRequest(BaseModel):
    ticker_a: str = Field(min_length=1, max_length=10)
    ticker_b: str = Field(min_length=1, max_length=10)
    fit_window_days: int = Field(default=DEFAULT_FIT_WINDOW_DAYS, ge=60, le=756)
    entry_z: float = Field(default=DEFAULT_ENTRY_Z, gt=0, le=5)
    exit_z: float = Field(default=DEFAULT_EXIT_Z, ge=0)
    cost_bps: float = Field(default=DEFAULT_COST_BPS, ge=0, le=500)
    lookback_years: int = Field(default=DEFAULT_LOOKBACK_YEARS, ge=2, le=10)

    @field_validator("ticker_a", "ticker_b")
    @classmethod
    def _normalize_ticker(cls, v: str) -> str:
        return v.strip().upper()

    @model_validator(mode="after")
    def _validate_cross_fields(self) -> "PairsBacktestRequest":
        if self.ticker_a == self.ticker_b:
            raise ValueError("ticker_a and ticker_b must be different.")
        if self.exit_z >= self.entry_z:
            raise ValueError("exit_z must be less than entry_z.")
        return self


class EquityCurvePointOut(BaseModel):
    date: str
    equity: float
    position: int
    z_score: float | None


class TradeOut(BaseModel):
    entry_date: str
    exit_date: str | None
    direction: Literal["long_spread", "short_spread"]
    holding_days: int
    trade_return: float
    still_open: bool


class SearchContextOut(BaseModel):
    configurations_tested: int
    note: str


class PairsBacktestResponse(BaseModel):
    status: Literal["ok", "not_mean_reverting", "insufficient_history"]
    as_of: str
    ticker_a: str
    ticker_b: str
    fit_window_days: int
    entry_z: float
    exit_z: float
    cost_bps: float
    lookback_years: int
    n_trading_days: int
    n_out_of_sample_days: int
    total_return_net: float | None
    annualized_return_net: float | None
    annualized_volatility_net: float | None
    sharpe_net: float | None
    sharpe_gross: float | None
    max_drawdown_net: float | None
    num_trades: int
    win_rate: float | None
    exposure_pct: float | None
    total_cost_drag: float | None
    pct_days_mean_reverting: float
    fit_quality_distribution: dict[str, float]
    equity_curve: list[EquityCurvePointOut]
    trade_log: list[TradeOut]
    search_context: SearchContextOut
    methodology_note: str
    warnings: list[str] = Field(default_factory=list)
    cached: bool
