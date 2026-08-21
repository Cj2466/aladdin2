from pydantic import BaseModel, Field, field_validator

from app.schemas.risk import HoldingIn, validate_no_duplicate_tickers, validate_weights_sum_to_one


class StressTestRequest(BaseModel):
    holdings: list[HoldingIn] = Field(min_length=1, max_length=50)
    benchmark: str = Field(default="SPY", min_length=1, max_length=10)

    @field_validator("benchmark")
    @classmethod
    def normalize_benchmark(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("holdings")
    @classmethod
    def weights_sum_to_one(cls, holdings: list[HoldingIn]) -> list[HoldingIn]:
        return validate_weights_sum_to_one(holdings)

    @field_validator("holdings")
    @classmethod
    def no_duplicate_tickers(cls, holdings: list[HoldingIn]) -> list[HoldingIn]:
        return validate_no_duplicate_tickers(holdings)


class HoldingStressOut(BaseModel):
    ticker: str
    weight: float
    return_pct: float
    basis: str


class ScenarioOut(BaseModel):
    scenario_id: str
    label: str
    description: str
    start: str
    end: str
    portfolio_return: float
    benchmark_return: float
    has_estimated: bool
    holdings: list[HoldingStressOut]


class ExposureSliceOut(BaseModel):
    label: str
    weight: float


class StressTestResponse(BaseModel):
    scenarios: list[ScenarioOut]
    sector_exposure: list[ExposureSliceOut]
    asset_class_exposure: list[ExposureSliceOut]
    warnings: list[str] = Field(default_factory=list)
