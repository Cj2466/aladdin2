from pydantic import BaseModel, Field, field_validator

from app.schemas.risk import (
    HoldingIn,
    validate_no_duplicate_tickers,
    validate_weights_sum_to_one,
)
from app.schemas.stress import ExposureSliceOut


class PortfolioFactorRiskRequest(BaseModel):
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


class FactorExposureOut(BaseModel):
    factor: str  # stable key, e.g. "market"
    label: str  # display label, e.g. "Market"
    exposure: float  # portfolio-level weighted beta, in beta units (can be negative)
    contribution_pct: float  # share of TOTAL portfolio variance; unclamped, can rarely be negative


class HoldingFactorFitOut(BaseModel):
    ticker: str
    betas: dict[str, float]  # factor key -> beta
    r_squared: float
    idiosyncratic_volatility_annualized: float


class PortfolioFactorRiskResponse(BaseModel):
    as_of: str
    lookback_years: int
    factor_detail: list[FactorExposureOut]
    # Display-ready breakdown for SectorExposureChart: N factors + "Stock-specific",
    # negative contributions clamped to 0 (see factor_detail for true signed values).
    risk_contribution: list[ExposureSliceOut]
    idiosyncratic_risk_pct: float
    factor_variance_annualized: float
    idiosyncratic_variance_annualized: float
    total_variance_annualized: float
    holdings: list[HoldingFactorFitOut]
    warnings: list[str] = Field(default_factory=list)


class SavedPortfolioFactorRiskResponse(PortfolioFactorRiskResponse):
    portfolio_id: int
