from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ALLOWED_RISK_METRICS = {
    "volatility_annualized",
    "var_historical_95",
    "var_parametric_95",
    "cvar_95",
    "beta",
    "hhi",
    "avg_pairwise_correlation",
}


class AlertRuleCreate(BaseModel):
    portfolio_id: int
    rule_type: Literal["price_move", "risk_metric"]
    ticker: str | None = Field(default=None, max_length=10)
    metric: str | None = Field(default=None, max_length=30)
    threshold_pct: float = Field(gt=0)
    direction: Literal["up", "down"]

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, v: str | None) -> str | None:
        return v.strip().upper() if v else v

    @model_validator(mode="after")
    def validate_type_specific_fields(self) -> "AlertRuleCreate":
        if self.rule_type == "price_move":
            if not self.ticker:
                raise ValueError("ticker is required for price_move rules")
        else:
            if self.metric not in ALLOWED_RISK_METRICS:
                raise ValueError(f"metric must be one of {sorted(ALLOWED_RISK_METRICS)}")
        return self


class AlertRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    portfolio_id: int
    rule_type: str
    ticker: str | None
    metric: str | None
    threshold_pct: float
    direction: str
    is_active: bool
    last_checked_at: datetime | None
    last_fired_at: datetime | None
    created_at: datetime


class AlertEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alert_rule_id: int
    message: str
    triggered_value: float
    created_at: datetime
    is_read: bool
    email_sent: bool
