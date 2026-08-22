from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.macro_data.series import MACRO_SERIES_BY_ID

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
    portfolio_id: int | None = None
    rule_type: Literal["price_move", "risk_metric", "macro_threshold"]
    ticker: str | None = Field(default=None, max_length=10)
    metric: str | None = Field(default=None, max_length=30)
    series_id: str | None = Field(default=None, max_length=30)
    # Positive-only for price_move/risk_metric (a magnitude of move); any
    # sign for macro_threshold (a raw level — e.g. 0.0 for "curve inverts").
    # Enforced per rule_type below, not via a blanket Field constraint.
    threshold_pct: float
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
            if self.portfolio_id is None:
                raise ValueError("portfolio_id is required for price_move rules")
            if self.threshold_pct <= 0:
                raise ValueError("threshold_pct must be positive for price_move rules")
        elif self.rule_type == "risk_metric":
            if self.metric not in ALLOWED_RISK_METRICS:
                raise ValueError(f"metric must be one of {sorted(ALLOWED_RISK_METRICS)}")
            if self.portfolio_id is None:
                raise ValueError("portfolio_id is required for risk_metric rules")
            if self.threshold_pct <= 0:
                raise ValueError("threshold_pct must be positive for risk_metric rules")
        else:  # macro_threshold
            if self.series_id not in MACRO_SERIES_BY_ID:
                raise ValueError("series_id must be a known macro series")
        return self


class AlertRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    portfolio_id: int | None
    rule_type: str
    ticker: str | None
    metric: str | None
    series_id: str | None
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
