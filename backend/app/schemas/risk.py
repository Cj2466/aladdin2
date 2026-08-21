from pydantic import BaseModel, Field, field_validator


class HoldingIn(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)
    weight: float = Field(gt=0, le=1)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, v: str) -> str:
        return v.strip().upper()


def validate_weights_sum_to_one(holdings: list[HoldingIn]) -> list[HoldingIn]:
    total = sum(h.weight for h in holdings)
    if not (0.995 <= total <= 1.005):
        raise ValueError(f"Holding weights must sum to ~1.0, got {total:.4f}")
    return holdings


def validate_no_duplicate_tickers(holdings: list[HoldingIn]) -> list[HoldingIn]:
    tickers = [h.ticker for h in holdings]
    if len(tickers) != len(set(tickers)):
        raise ValueError("Duplicate tickers in holdings")
    return holdings


class PortfolioAnalyzeRequest(BaseModel):
    holdings: list[HoldingIn] = Field(min_length=1, max_length=50)
    benchmark: str = Field(default="SPY", min_length=1, max_length=10)
    lookback_years: int = Field(default=3, ge=1, le=10)

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


class PortfolioAnalyzeResponse(BaseModel):
    as_of: str
    volatility_annualized: float
    var_historical_95: float
    var_parametric_95: float
    cvar_95: float
    beta: float
    hhi: float
    avg_pairwise_correlation: float
    correlation_matrix: dict[str, dict[str, float]]
    warnings: list[str] = Field(default_factory=list)
