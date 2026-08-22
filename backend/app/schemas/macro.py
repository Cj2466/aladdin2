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


class EpisodeOutcomeOut(BaseModel):
    episode_start: str
    episode_end: str
    trading_days_in_episode: int
    return_6m: float | None
    return_6m_status: Literal["ok", "too_recent", "benchmark_unavailable"]
    return_12m: float | None
    return_12m_status: Literal["ok", "too_recent", "benchmark_unavailable"]
    return_18m: float | None
    return_18m_status: Literal["ok", "too_recent", "benchmark_unavailable"]


class HistoricalAnalogResponse(BaseModel):
    series_id: str
    series_label: str
    threshold: float
    direction: Literal["up", "down"]
    benchmark: str
    history_start: str
    history_end: str
    episode_count: int
    episodes: list[EpisodeOutcomeOut]
    caveat: str  # server-authored, always present — never omittable by a frontend change


class MacroHistoryPointOut(BaseModel):
    date: str
    value: float


class SeriesProjectionOut(BaseModel):
    series_id: str
    label: str
    unit: str
    decimals: int
    status: Literal["ok", "insufficient_history"]
    as_of_date: str | None
    last_value: float | None
    recent_history: list[MacroHistoryPointOut]  # last ~90 obs, for chart context
    horizon_trading_days: int
    horizon_label: str  # "~1 month (21 trading days)"
    point_estimate: float | None
    band_low: float | None
    band_high: float | None
    band_confidence_pct: float  # 80.0, fixed (10th-90th percentile)
    r_squared: float | None
    trend_strength: Literal["weak", "moderate", "strong"] | None
    point_estimate_outside_historical_range: bool | None


class SeriesProjectionsResponse(BaseModel):
    projections: list[SeriesProjectionOut]
    generated_at: str
    methodology_note: str  # canned, server-authored, always present
