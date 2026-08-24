from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.research_lab import (
    PairsConfigValidatorMixin,
    SingleTickerValidatorMixin,
    ZThresholdOrderValidatorMixin,
)
from app.services.research_lab import momentum
from app.services.research_lab.ou_pairs import (
    DEFAULT_COST_BPS,
    DEFAULT_ENTRY_Z,
    DEFAULT_EXIT_Z,
    DEFAULT_FIT_WINDOW_DAYS,
)


class ForwardValidationRegisterRequest(PairsConfigValidatorMixin, BaseModel):
    ticker_a: str = Field(min_length=1, max_length=10)
    ticker_b: str = Field(min_length=1, max_length=10)
    fit_window_days: int = Field(default=DEFAULT_FIT_WINDOW_DAYS, ge=60, le=756)
    entry_z: float = Field(default=DEFAULT_ENTRY_Z, gt=0, le=5)
    exit_z: float = Field(default=DEFAULT_EXIT_Z, ge=0)
    cost_bps: float = Field(default=DEFAULT_COST_BPS, ge=0, le=500)


class MomentumForwardValidationRegisterRequest(SingleTickerValidatorMixin, ZThresholdOrderValidatorMixin, BaseModel):
    ticker: str = Field(min_length=1, max_length=10)
    fit_window_days: int = Field(default=momentum.DEFAULT_FIT_WINDOW_DAYS, ge=60, le=756)
    entry_z: float = Field(default=momentum.DEFAULT_ENTRY_Z, gt=0, le=5)
    exit_z: float = Field(default=momentum.DEFAULT_EXIT_Z, ge=0)
    cost_bps: float = Field(default=momentum.DEFAULT_COST_BPS, ge=0, le=500)


class ForwardValidationRegistrationOut(BaseModel):
    id: int
    strategy_name: str
    ticker_a: str
    ticker_b: str
    fit_window_days: int
    entry_z: float
    exit_z: float
    cost_bps: float
    status: Literal["in_progress", "forward_validated"]
    started_at: str
    last_processed_date: str | None
    n_forward_trading_days: int
    min_trading_days_threshold: int
    graduated_at: str | None
    open_position: Literal["long_spread", "short_spread", "long", "short", "flat"]
    pct_days_mean_reverting_forward: float | None
    sharpe_forward_so_far: float | None
    is_system: bool


class ForwardValidationRegisterResponse(ForwardValidationRegistrationOut):
    created: bool
