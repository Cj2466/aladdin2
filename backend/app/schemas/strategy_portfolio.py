from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.optimizer import PortfolioOptimizeResponse
from app.schemas.risk import PortfolioAnalyzeResponse

# PortfolioAnalyzeResponse / PortfolioOptimizeResponse / OptimizedHoldingOut
# are reused VERBATIM from the ticker-based risk feature — every field means
# exactly the same thing whether the "assets" are tickers or backtested
# strategy instances, so a parallel set of near-identical response models
# would be pure duplication. OptimizedHoldingOut.ticker carries
# str(experiment_run_id) here: an opaque, presentation-agnostic key the
# frontend maps to a human label, which needs no backend schema change.

MAX_ALLOCATIONS = 50  # same ceiling as PortfolioCreate.holdings


class StrategyAllocationIn(BaseModel):
    experiment_run_id: int
    weight: float = Field(gt=0, le=1)


def validate_allocation_weights_sum_to_one(
    allocations: list[StrategyAllocationIn],
) -> list[StrategyAllocationIn]:
    total = sum(a.weight for a in allocations)
    if not (0.995 <= total <= 1.005):
        raise ValueError(f"Allocation weights must sum to ~1.0, got {total:.4f}")
    return allocations


def validate_no_duplicate_runs(
    allocations: list[StrategyAllocationIn],
) -> list[StrategyAllocationIn]:
    run_ids = [a.experiment_run_id for a in allocations]
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("Duplicate experiment_run_id in allocations")
    return allocations


class _AllocationsPayload(BaseModel):
    """Shared validator wiring — mirrors how PortfolioCreate/
    PortfolioAnalyzeRequest/PortfolioOptimizeRequest each attach the same
    two holdings validators, factored once here since all four
    strategy-portfolio payloads need the identical pair."""

    allocations: list[StrategyAllocationIn] = Field(min_length=1, max_length=MAX_ALLOCATIONS)

    @field_validator("allocations")
    @classmethod
    def weights_sum_to_one(cls, allocations: list[StrategyAllocationIn]) -> list[StrategyAllocationIn]:
        return validate_allocation_weights_sum_to_one(allocations)

    @field_validator("allocations")
    @classmethod
    def no_duplicate_runs(cls, allocations: list[StrategyAllocationIn]) -> list[StrategyAllocationIn]:
        return validate_no_duplicate_runs(allocations)


class StrategyPortfolioCreate(_AllocationsPayload):
    name: str = Field(min_length=1, max_length=255)


class StrategyPortfolioUpdate(StrategyPortfolioCreate):
    pass


class StrategyAllocationOut(BaseModel):
    id: int
    experiment_run_id: int
    weight: float
    # Resolved at read time from the referenced ExperimentRun, never stored
    # as columns here — ExperimentRun stays the single source of truth, and
    # a run's metrics can't silently diverge from a stale copy.
    strategy_name: str
    ticker_a: str
    ticker_b: str
    status: str
    computed_at: datetime
    sharpe_net: float | None


class StrategyPortfolioOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    updated_at: datetime
    last_optimized_at: datetime | None
    # At most one of a user's portfolios may be live at a time — an app-level
    # invariant enforced atomically by the toggle endpoint, since SQLite cannot
    # easily express a partial unique index.
    is_live: bool
    allocations: list[StrategyAllocationOut]
    # Computed at read time (user_id == system_user_id), not a stored
    # column — the same pattern already established for
    # ScreeningJobOut.is_system and ForwardValidationRegistrationOut.is_system.
    is_system: bool


class StrategyPortfolioSummary(BaseModel):
    id: int
    name: str
    updated_at: datetime
    last_optimized_at: datetime | None
    allocation_count: int
    is_system: bool
    is_live: bool


class StrategyPortfolioAnalyzeRequest(_AllocationsPayload):
    benchmark: str = Field(default="SPY", min_length=1, max_length=10)

    @field_validator("benchmark")
    @classmethod
    def normalize_benchmark(cls, v: str) -> str:
        return v.strip().upper()


class StrategyPortfolioOptimizeRequest(_AllocationsPayload):
    # Deliberately no lookback_years: the measurement window is fully
    # determined by each selected run's own stored equity curve, so there
    # is nothing for a caller to choose.
    pass


class SavedStrategyPortfolioAnalyzeResponse(PortfolioAnalyzeResponse):
    strategy_portfolio_id: int


class SavedStrategyPortfolioOptimizeResponse(PortfolioOptimizeResponse):
    strategy_portfolio_id: int
