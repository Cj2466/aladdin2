from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.research_lab import TickerPairValidatorMixin
from app.services.research_lab.ou_pairs import (
    DEFAULT_COST_BPS,
    DEFAULT_ENTRY_Z,
    DEFAULT_EXIT_Z,
    DEFAULT_FIT_WINDOW_DAYS,
    DEFAULT_LOOKBACK_YEARS,
)


def _dedup_sorted(values: list[float]) -> list[float]:
    # Determinism + no wasted combo budget on literal duplicates.
    return sorted(set(values))


class SweepGridSpec(BaseModel):
    fit_window_days: list[int] = Field(default_factory=lambda: [DEFAULT_FIT_WINDOW_DAYS], min_length=1)
    entry_z: list[float] = Field(default_factory=lambda: [DEFAULT_ENTRY_Z], min_length=1)
    exit_z: list[float] = Field(default_factory=lambda: [DEFAULT_EXIT_Z], min_length=1)
    cost_bps: list[float] = Field(default_factory=lambda: [DEFAULT_COST_BPS], min_length=1)

    @field_validator("fit_window_days")
    @classmethod
    def _validate_fit_window_days(cls, v: list[int]) -> list[int]:
        for x in v:
            if not (60 <= x <= 756):
                raise ValueError("Each fit_window_days value must be between 60 and 756.")
        return sorted(set(v))

    @field_validator("entry_z")
    @classmethod
    def _validate_entry_z(cls, v: list[float]) -> list[float]:
        for x in v:
            if not (0 < x <= 5):
                raise ValueError("Each entry_z value must be > 0 and <= 5.")
        return _dedup_sorted(v)

    @field_validator("exit_z")
    @classmethod
    def _validate_exit_z(cls, v: list[float]) -> list[float]:
        for x in v:
            if x < 0:
                raise ValueError("Each exit_z value must be >= 0.")
        return _dedup_sorted(v)

    @field_validator("cost_bps")
    @classmethod
    def _validate_cost_bps(cls, v: list[float]) -> list[float]:
        for x in v:
            if not (0 <= x <= 500):
                raise ValueError("Each cost_bps value must be between 0 and 500.")
        return _dedup_sorted(v)


class SweepJobCreateRequest(TickerPairValidatorMixin, BaseModel):
    ticker_a: str = Field(min_length=1, max_length=10)
    ticker_b: str = Field(min_length=1, max_length=10)
    lookback_years: int = Field(default=DEFAULT_LOOKBACK_YEARS, ge=2, le=10)
    grid: SweepGridSpec = Field(default_factory=SweepGridSpec)


class SweepJobOut(BaseModel):
    id: int
    strategy_name: str
    ticker_a: str
    ticker_b: str
    lookback_years: int
    grid: SweepGridSpec
    total_configurations: int
    configurations_completed: int
    configurations_failed: int
    status: Literal["queued", "running", "completed"]
    created_at: str
    completed_at: str | None
