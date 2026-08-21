from pydantic import BaseModel, Field, field_validator

from app.schemas.risk import HoldingIn, validate_no_duplicate_tickers, validate_weights_sum_to_one


class PortfolioOptimizeRequest(BaseModel):
    holdings: list[HoldingIn] = Field(min_length=1, max_length=50)
    lookback_years: int = Field(default=3, ge=1, le=10)

    @field_validator("holdings")
    @classmethod
    def weights_sum_to_one(cls, holdings: list[HoldingIn]) -> list[HoldingIn]:
        return validate_weights_sum_to_one(holdings)

    @field_validator("holdings")
    @classmethod
    def no_duplicate_tickers(cls, holdings: list[HoldingIn]) -> list[HoldingIn]:
        return validate_no_duplicate_tickers(holdings)


class OptimizedHoldingOut(BaseModel):
    ticker: str
    weight: float


class PortfolioOptimizeResponse(BaseModel):
    as_of: str
    lookback_years: int
    risk_free_rate: float
    max_weight_cap: float
    optimized_weights: list[OptimizedHoldingOut]
    optimized_expected_return: float
    optimized_volatility: float
    optimized_sharpe: float
    current_expected_return: float
    current_volatility: float
    current_sharpe: float
    warnings: list[str] = Field(default_factory=list)


class SavedPortfolioOptimizeResponse(PortfolioOptimizeResponse):
    portfolio_id: int
