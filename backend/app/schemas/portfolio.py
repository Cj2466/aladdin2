from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.risk import (
    HoldingIn,
    PortfolioAnalyzeResponse,
    validate_no_duplicate_tickers,
    validate_weights_sum_to_one,
)


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    base_currency: str = Field(default="USD", min_length=1, max_length=3)
    holdings: list[HoldingIn] = Field(min_length=1, max_length=50)

    @field_validator("holdings")
    @classmethod
    def weights_sum_to_one(cls, holdings: list[HoldingIn]) -> list[HoldingIn]:
        return validate_weights_sum_to_one(holdings)

    @field_validator("holdings")
    @classmethod
    def no_duplicate_tickers(cls, holdings: list[HoldingIn]) -> list[HoldingIn]:
        return validate_no_duplicate_tickers(holdings)


class PortfolioUpdate(PortfolioCreate):
    pass


class HoldingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    weight: float | None


class PortfolioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    base_currency: str
    created_at: datetime
    updated_at: datetime
    holdings: list[HoldingOut]


class PortfolioSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    base_currency: str
    updated_at: datetime
    holding_count: int


class SavedPortfolioAnalyzeResponse(PortfolioAnalyzeResponse):
    portfolio_id: int
    cached: bool
