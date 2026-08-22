from typing import Literal

from pydantic import BaseModel


class MacroSeriesOut(BaseModel):
    series_id: str
    label: str
    category: str
    cadence: str
    unit: str
    decimals: int
    value: float | None
    observation_date: str | None
    reference_period_label: str | None  # e.g. "July 2026" / "Q2 2026"
    fetched_at: str | None
    next_release_hint: str
    status: Literal["ok", "unavailable"]


class YieldCurvePointOut(BaseModel):
    maturity_label: str  # "3M" | "2Y" | "10Y" | "30Y", fixed order
    today: float | None
    one_year_ago: float | None


class MacroDashboardResponse(BaseModel):
    series: list[MacroSeriesOut]
    yield_curve: list[YieldCurvePointOut]
    generated_at: str


class MacroSeriesCatalogEntry(BaseModel):
    series_id: str
    label: str
    category: str
    unit: str
