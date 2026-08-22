from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.dependencies import (
    get_cleveland_fed_provider,
    get_macro_provider,
    get_provider,
)
from app.models.user import User
from app.schemas.macro import (
    EpisodeOutcomeOut,
    HistoricalAnalogResponse,
    MacroDashboardResponse,
    MacroHistoryPointOut,
    MacroSeriesCatalogEntry,
    MacroSeriesOut,
    SeriesProjectionOut,
    SeriesProjectionsResponse,
    YieldCurvePointOut,
)
from app.services.historical_analog.episodes import find_crossing_episodes
from app.services.historical_analog.outcomes import compute_episode_outcomes
from app.services.macro_data.base import MacroDataProvider
from app.services.macro_data.cache import (
    MacroSeriesSnapshot,
    YieldCurvePoint,
    get_cleveland_fed_nowcasts_cached,
    get_latest_macro_snapshot_cached,
    get_macro_history_cached,
    get_yield_curve_cached,
)
from app.services.macro_data.cleveland_fed_provider import ClevelandFedNowcastProvider
from app.services.macro_data.projection import (
    FORECAST_HORIZON_TRADING_DAYS,
    LONG_LOOKBACK_TRADING_DAYS,
    PROJECTABLE_SERIES_IDS,
    compute_series_projection,
)
from app.services.macro_data.series import (
    CADENCE_NEXT_RELEASE_HINT,
    CLEVELAND_FED_SERIES_BY_ID,
    MACRO_SERIES,
    MACRO_SERIES_BY_ID,
)
from app.services.market_data.base import MarketDataProvider
from app.services.market_data.price_cache import get_price_history_cached
from app.time_utils import utcnow_naive

router = APIRouter(prefix="/api/macro", tags=["macro"])

# v1 only supports yield-curve inversions — the underlying functions are
# fully generic (threshold/direction/series_id are all parameters), this
# allowlist just keeps the public API surface deliberately narrow for now.
HISTORICAL_ANALOG_ALLOWLIST: dict[str, tuple[float, Literal["up", "down"]]] = {
    "T10Y2Y": (0.0, "down"),
}
# Earlier than any series here actually starts — FRED just returns
# whatever it truly has from that point forward.
HISTORICAL_ANALOG_HISTORY_START = date(1970, 1, 1)

PROJECTION_METHODOLOGY_NOTE = (
    "These are naive statistical projections, not forecasts — a linear trend fit over the "
    "last ~1 quarter, extended ~1 month forward. Macro series do not move linearly, and this "
    "method has no track record of accuracy. The shaded band is the actual historical range "
    "of real 1-month moves this series has made (10th-90th percentile), not a model's estimate "
    "of its own confidence. Treat 'weak' trend series and any point estimate outside the "
    "historical band as especially unreliable."
)
TRADING_DAYS_PER_YEAR = 252
# LONG_LOOKBACK_TRADING_DAYS (~5 years) expressed as calendar days, since
# get_macro_history_cached takes a calendar-date range, not a trading-day
# count.
PROJECTION_HISTORY_LOOKBACK_DAYS = round((LONG_LOOKBACK_TRADING_DAYS / TRADING_DAYS_PER_YEAR) * 365.25)
PROJECTION_RECENT_HISTORY_POINTS = 90


def _reference_period_label(observation_date: date, cadence: str) -> str:
    if cadence == "monthly":
        return observation_date.strftime("%B %Y")
    if cadence == "quarterly":
        quarter = (observation_date.month - 1) // 3 + 1
        return f"Q{quarter} {observation_date.year}"
    return observation_date.strftime("%b %d, %Y")


def _to_series_out(snapshot: MacroSeriesSnapshot) -> MacroSeriesOut:
    definition = MACRO_SERIES_BY_ID.get(snapshot.series_id) or CLEVELAND_FED_SERIES_BY_ID[snapshot.series_id]

    # GFDEBTN is cached in FRED's native units (millions of USD) — converted
    # to trillions here, at the display-building layer, so the cached value
    # stays a faithful mirror of what FRED actually reported.
    value = snapshot.value
    if value is not None and definition.unit == "usd_trillions":
        value = value / 1_000_000

    return MacroSeriesOut(
        series_id=snapshot.series_id,
        label=definition.label,
        category=definition.category,
        cadence=definition.cadence,
        unit=definition.unit,
        decimals=definition.decimals,
        value=value,
        observation_date=snapshot.observation_date.isoformat() if snapshot.observation_date else None,
        reference_period_label=(
            _reference_period_label(snapshot.observation_date, definition.cadence)
            if snapshot.observation_date
            else None
        ),
        fetched_at=snapshot.fetched_at.isoformat() if snapshot.fetched_at else None,
        next_release_hint=CADENCE_NEXT_RELEASE_HINT[definition.cadence],
        status=snapshot.status,
    )


def _to_curve_point_out(point: YieldCurvePoint) -> YieldCurvePointOut:
    return YieldCurvePointOut(
        maturity_label=point.maturity_label, today=point.today, one_year_ago=point.one_year_ago
    )


@router.get("/dashboard", response_model=MacroDashboardResponse)
def macro_dashboard(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
    provider: MacroDataProvider = Depends(get_macro_provider),
    cleveland_provider: ClevelandFedNowcastProvider = Depends(get_cleveland_fed_provider),
) -> MacroDashboardResponse:
    snapshot = get_latest_macro_snapshot_cached(db, provider)
    cleveland_snapshot = get_cleveland_fed_nowcasts_cached(db, cleveland_provider)
    curve = get_yield_curve_cached(db, provider)
    return MacroDashboardResponse(
        series=[_to_series_out(s) for s in [*snapshot, *cleveland_snapshot]],
        yield_curve=[_to_curve_point_out(p) for p in curve],
        generated_at=utcnow_naive().isoformat(),
    )


@router.get("/series", response_model=list[MacroSeriesCatalogEntry])
def list_macro_series(_current_user: User = Depends(get_current_user)) -> list[MacroSeriesCatalogEntry]:
    """Static catalog (no provider/DB call) — powers the macro-alert rule
    creation dropdown on the frontend."""
    return [
        MacroSeriesCatalogEntry(
            series_id=d.series_id, label=d.label, category=d.category, unit=d.unit
        )
        for d in MACRO_SERIES
    ]


@router.get("/historical-analog", response_model=HistoricalAnalogResponse)
def historical_analog(
    series_id: str = "T10Y2Y",
    benchmark: str = "SPY",
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
    macro_provider: MacroDataProvider = Depends(get_macro_provider),
    provider: MarketDataProvider = Depends(get_provider),
) -> HistoricalAnalogResponse:
    if series_id not in HISTORICAL_ANALOG_ALLOWLIST:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"series_id must be one of {sorted(HISTORICAL_ANALOG_ALLOWLIST)}",
        )
    threshold, direction = HISTORICAL_ANALOG_ALLOWLIST[series_id]
    definition = MACRO_SERIES_BY_ID[series_id]
    benchmark = benchmark.strip().upper()

    history = get_macro_history_cached(
        db, macro_provider, series_id, definition.fred_units, HISTORICAL_ANALOG_HISTORY_START, date.today()
    )
    if not history:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="No historical data available for this series."
        )

    predicate = (lambda v: v >= threshold) if direction == "up" else (lambda v: v <= threshold)
    episodes = find_crossing_episodes(history, predicate)

    def prices_fn(tickers, start, end):
        return get_price_history_cached(db, provider, tickers, start, end)

    outcomes = compute_episode_outcomes(episodes, benchmark, prices_fn)

    return HistoricalAnalogResponse(
        series_id=series_id,
        series_label=definition.label,
        threshold=threshold,
        direction=direction,
        benchmark=benchmark,
        history_start=history[0].observation_date.isoformat(),
        history_end=history[-1].observation_date.isoformat(),
        episode_count=len(episodes),
        episodes=[
            EpisodeOutcomeOut(
                episode_start=o.episode_start.isoformat(),
                episode_end=o.episode_end.isoformat(),
                trading_days_in_episode=o.trading_days_in_episode,
                return_6m=o.returns[6][0],
                return_6m_status=o.returns[6][1],
                return_12m=o.returns[12][0],
                return_12m_status=o.returns[12][1],
                return_18m=o.returns[18][0],
                return_18m_status=o.returns[18][1],
            )
            for o in outcomes
        ],
        caveat=(
            f"Only {len(episodes)} episode{'s' if len(episodes) != 1 else ''} since "
            f"{history[0].observation_date.isoformat()} — a small sample. This shows what "
            "actually happened after past inversions, not a prediction of what happens this time."
        ),
    )


@router.get("/projections", response_model=SeriesProjectionsResponse)
def series_projections(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
    macro_provider: MacroDataProvider = Depends(get_macro_provider),
) -> SeriesProjectionsResponse:
    end = date.today()
    start = end - timedelta(days=PROJECTION_HISTORY_LOOKBACK_DAYS)

    projections: list[SeriesProjectionOut] = []
    for series_id in PROJECTABLE_SERIES_IDS:
        definition = MACRO_SERIES_BY_ID[series_id]
        history = get_macro_history_cached(db, macro_provider, series_id, definition.fred_units, start, end)
        result = compute_series_projection(history)

        recent = history[-PROJECTION_RECENT_HISTORY_POINTS:]
        projections.append(
            SeriesProjectionOut(
                series_id=series_id,
                label=definition.label,
                unit=definition.unit,
                decimals=definition.decimals,
                status=result.status,
                as_of_date=result.as_of_date.isoformat() if result.as_of_date else None,
                last_value=result.last_value,
                recent_history=[
                    MacroHistoryPointOut(date=o.observation_date.isoformat(), value=o.value) for o in recent
                ],
                horizon_trading_days=FORECAST_HORIZON_TRADING_DAYS,
                horizon_label=f"~1 month ({FORECAST_HORIZON_TRADING_DAYS} trading days)",
                point_estimate=result.point_estimate,
                band_low=result.band_low,
                band_high=result.band_high,
                band_confidence_pct=80.0,
                r_squared=result.r_squared,
                trend_strength=result.trend_strength,
                point_estimate_outside_historical_range=result.point_estimate_outside_historical_range,
            )
        )

    return SeriesProjectionsResponse(
        projections=projections,
        generated_at=utcnow_naive().isoformat(),
        methodology_note=PROJECTION_METHODOLOGY_NOTE,
    )
