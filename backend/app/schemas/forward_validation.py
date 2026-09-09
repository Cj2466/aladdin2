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


class UnderperformanceAdvisoryOut(BaseModel):
    """The trailing-window underperformance signal and its calibrated
    companion, surfaced for a human instead of flipping status — see
    forward_validation_service.UnderperformanceAdvisory for why (2026-09-09)."""

    n_realized_days: int
    trailing_flag: bool
    trailing_sharpe_annualized: float | None
    whole_record_sharpe_annualized: float | None
    whole_record_psr_vs_zero: float | None
    # Retirement rule R-2026-09-09-v2: recommendation only (rule 6).
    retirement_rule_id: str | None = None
    retirement_bucket: str | None = None
    retirement_statistic: float | None = None
    retirement_boundary: float | None = None
    retirement_recommended: bool = False
    retirement_first_trigger_day: int | None = None


class ForwardValidationRegistrationOut(BaseModel):
    id: int
    strategy_name: str
    ticker_a: str
    ticker_b: str
    fit_window_days: int
    entry_z: float
    exit_z: float
    cost_bps: float
    # "underperforming" is no longer set by the runner (2026-09-09); it stays
    # in the vocabulary as a state a human may put a row into.
    status: Literal["in_progress", "forward_validated", "underperforming"]
    underperformance_advisory: UnderperformanceAdvisoryOut
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
