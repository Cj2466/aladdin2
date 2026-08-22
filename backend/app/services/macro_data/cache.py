from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.macro_observation import MacroObservation
from app.services.macro_data.base import (
    MacroDataError,
    MacroDataProvider,
    MacroObservationResult,
)
from app.services.macro_data.cleveland_fed_provider import ClevelandFedNowcastProvider
from app.services.macro_data.series import (
    CADENCE_TTL,
    CLEVELAND_FED_SERIES,
    MACRO_SERIES,
    MACRO_SERIES_BY_ID,
    SCENARIO_MACRO_CONTEXT_SERIES_IDS,
    YIELD_CURVE_SERIES,
)
from app.time_utils import utcnow_naive

# Weekend/holiday + "today's reading may not be posted yet" tolerance for
# the yield-curve history window, mirroring ROLLING_WINDOW_TOLERANCE_DAYS
# in price_cache.py for the same reason.
ROLLING_WINDOW_TOLERANCE_DAYS = 4
YIELD_CURVE_LOOKBACK_DAYS = 370
ONE_YEAR_MATCH_TOLERANCE_DAYS = 10


@dataclass
class MacroSeriesSnapshot:
    series_id: str
    value: float | None
    observation_date: date | None
    fetched_at: datetime | None
    status: str  # "ok" | "unavailable"


@dataclass
class YieldCurvePoint:
    maturity_label: str
    today: float | None
    one_year_ago: float | None


@dataclass
class ScenarioMacroContextPoint:
    series_id: str
    label: str
    unit: str
    decimals: int
    start_value: float | None
    start_observation_date: date | None
    current_value: float | None
    current_observation_date: date | None


def _latest_cached_row(db: Session, series_id: str) -> MacroObservation | None:
    return db.execute(
        select(MacroObservation)
        .where(MacroObservation.series_id == series_id)
        .order_by(MacroObservation.observation_date.desc())
        .limit(1)
    ).scalar_one_or_none()


def _upsert_observations(
    db: Session, series_id: str, observations: list[MacroObservationResult]
) -> None:
    if not observations:
        return
    now = utcnow_naive()
    records = [
        {
            "series_id": series_id,
            "observation_date": obs.observation_date,
            "value": obs.value,
            "fetched_at": now,
        }
        for obs in observations
    ]
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    stmt = insert(MacroObservation).values(records)
    stmt = stmt.on_conflict_do_update(
        index_elements=["series_id", "observation_date"],
        set_={"value": stmt.excluded.value, "fetched_at": stmt.excluded.fetched_at},
    )
    db.execute(stmt)
    db.commit()


def get_latest_macro_snapshot_cached(
    db: Session, provider: MacroDataProvider
) -> list[MacroSeriesSnapshot]:
    """Read-through cache over MacroObservation, one row per series in
    MACRO_SERIES. A fetch failure for one series never blanks the others —
    it falls back to whatever's cached, or reports status="unavailable" if
    nothing has ever been cached for it."""
    now = utcnow_naive()
    snapshots: list[MacroSeriesSnapshot] = []

    for definition in MACRO_SERIES:
        cached = _latest_cached_row(db, definition.series_id)
        ttl = CADENCE_TTL[definition.cadence]
        is_stale = cached is None or (now - cached.fetched_at) > ttl

        if is_stale:
            try:
                observations = provider.get_latest_observations(
                    definition.series_id, definition.fred_units, limit=5
                )
                _upsert_observations(db, definition.series_id, observations)
                cached = _latest_cached_row(db, definition.series_id)
            except MacroDataError:
                pass  # serve whatever's cached (possibly still nothing)

        if cached is None:
            snapshots.append(
                MacroSeriesSnapshot(definition.series_id, None, None, None, "unavailable")
            )
        else:
            snapshots.append(
                MacroSeriesSnapshot(
                    definition.series_id, cached.value, cached.observation_date, cached.fetched_at, "ok"
                )
            )
    return snapshots


def get_macro_history_cached(
    db: Session,
    provider: MacroDataProvider,
    series_id: str,
    fred_units: str,
    start: date,
    end: date,
) -> list[MacroObservationResult]:
    """Read-through cache over a date range for a single series — same
    bounds-check/refetch/upsert shape as get_price_history_cached, scoped
    to one series instead of a ticker pivot."""
    is_rolling_window = end >= date.today()

    bounds = db.execute(
        select(func.min(MacroObservation.observation_date), func.max(MacroObservation.observation_date))
        .where(MacroObservation.series_id == series_id)
        .where(MacroObservation.observation_date >= start)
        .where(MacroObservation.observation_date <= end)
    ).one()
    cached_min, cached_max = bounds

    required_max = (end - timedelta(days=ROLLING_WINDOW_TOLERANCE_DAYS)) if is_rolling_window else end
    needs_fetch = cached_min is None or cached_min > start or cached_max < required_max

    if needs_fetch:
        try:
            observations = provider.get_observation_history(series_id, fred_units, start, end)
            _upsert_observations(db, series_id, observations)
        except MacroDataError:
            pass  # serve whatever's already cached for this range

    rows = db.execute(
        select(MacroObservation.observation_date, MacroObservation.value)
        .where(MacroObservation.series_id == series_id)
        .where(MacroObservation.observation_date >= start)
        .where(MacroObservation.observation_date <= end)
        .order_by(MacroObservation.observation_date.asc())
    ).all()
    return [MacroObservationResult(observation_date=d, value=v) for d, v in rows]


def get_yield_curve_cached(db: Session, provider: MacroDataProvider) -> list[YieldCurvePoint]:
    """Today vs. ~1-year-ago rate for each yield-curve maturity, reusing
    the same per-series history cache — no separate fetch mechanism."""
    end = date.today()
    start = end - timedelta(days=YIELD_CURVE_LOOKBACK_DAYS)
    one_year_ago_target = end - timedelta(days=365)

    points: list[YieldCurvePoint] = []
    for series_id, label in YIELD_CURVE_SERIES:
        definition = MACRO_SERIES_BY_ID[series_id]
        history = get_macro_history_cached(db, provider, series_id, definition.fred_units, start, end)

        if not history:
            points.append(YieldCurvePoint(label, None, None))
            continue

        today_value = history[-1].value
        nearest = min(history, key=lambda o: abs((o.observation_date - one_year_ago_target).days))
        one_year_ago_value = (
            nearest.value
            if abs((nearest.observation_date - one_year_ago_target).days) <= ONE_YEAR_MATCH_TOLERANCE_DAYS
            else None
        )
        points.append(YieldCurvePoint(label, today_value, one_year_ago_value))

    return points


NEAR_DATE_DEFAULT_TOLERANCE_DAYS = 10


def get_series_value_near_date_cached(
    db: Session,
    provider: MacroDataProvider,
    series_id: str,
    target_date: date,
    tolerance_days: int = NEAR_DATE_DEFAULT_TOLERANCE_DAYS,
) -> MacroObservationResult | None:
    """Nearest cached/fetched observation to target_date, or None if
    nothing falls within tolerance_days — generalizes the nearest-match
    pattern get_yield_curve_cached already uses, for an arbitrary
    series/date rather than just "today vs. a year ago"."""
    definition = MACRO_SERIES_BY_ID[series_id]
    start = target_date - timedelta(days=tolerance_days)
    end = min(target_date + timedelta(days=tolerance_days), date.today())
    if start > end:
        return None
    history = get_macro_history_cached(db, provider, series_id, definition.fred_units, start, end)
    if not history:
        return None
    nearest = min(history, key=lambda o: abs((o.observation_date - target_date).days))
    return nearest if abs((nearest.observation_date - target_date).days) <= tolerance_days else None


def get_scenario_macro_context_cached(
    db: Session, provider: MacroDataProvider, scenario_start: date
) -> list[ScenarioMacroContextPoint]:
    """Today vs. scenario-start reading for each series in
    SCENARIO_MACRO_CONTEXT_SERIES_IDS — pure comparison, not prediction."""
    today = date.today()
    points: list[ScenarioMacroContextPoint] = []
    for series_id in SCENARIO_MACRO_CONTEXT_SERIES_IDS:
        definition = MACRO_SERIES_BY_ID[series_id]
        start_obs = get_series_value_near_date_cached(db, provider, series_id, scenario_start)
        current_obs = get_series_value_near_date_cached(db, provider, series_id, today)
        points.append(
            ScenarioMacroContextPoint(
                series_id=series_id,
                label=definition.label,
                unit=definition.unit,
                decimals=definition.decimals,
                start_value=start_obs.value if start_obs else None,
                start_observation_date=start_obs.observation_date if start_obs else None,
                current_value=current_obs.value if current_obs else None,
                current_observation_date=current_obs.observation_date if current_obs else None,
            )
        )
    return points


def get_cleveland_fed_nowcasts_cached(
    db: Session, provider: ClevelandFedNowcastProvider
) -> list[MacroSeriesSnapshot]:
    """Same read-through contract as get_latest_macro_snapshot_cached
    (stale-serve, unavailable-if-never-cached, one bad fetch never crashes
    the caller) — but Cleveland Fed's payload contains every series in one
    HTTP call, so a single fetch refreshes both cached rows at once."""
    now = utcnow_naive()
    ttl = CADENCE_TTL["daily"]
    cached = {d.series_id: _latest_cached_row(db, d.series_id) for d in CLEVELAND_FED_SERIES}

    if any(row is None or (now - row.fetched_at) > ttl for row in cached.values()):
        try:
            fetched = provider.get_latest_nowcasts()
            for definition in CLEVELAND_FED_SERIES:
                if definition.series_id in fetched:
                    _upsert_observations(db, definition.series_id, [fetched[definition.series_id]])
            cached = {d.series_id: _latest_cached_row(db, d.series_id) for d in CLEVELAND_FED_SERIES}
        except MacroDataError:
            pass  # serve whatever's cached (possibly still nothing)

    snapshots: list[MacroSeriesSnapshot] = []
    for definition in CLEVELAND_FED_SERIES:
        row = cached[definition.series_id]
        if row is None:
            snapshots.append(MacroSeriesSnapshot(definition.series_id, None, None, None, "unavailable"))
        else:
            snapshots.append(
                MacroSeriesSnapshot(definition.series_id, row.value, row.observation_date, row.fetched_at, "ok")
            )
    return snapshots
