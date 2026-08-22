from datetime import date

import httpx

from app.services.macro_data.base import MacroDataError, MacroObservationResult
from app.services.macro_data.series import CLEVELAND_FED_LABEL_MAP

CLEVELAND_FED_NOWCAST_URL = (
    "https://www.clevelandfed.org/-/media/files/webcharts/inflationnowcasting/nowcast_year.json"
)


def _extract_latest_value(dataset: list[dict], series_name: str) -> float | None:
    series = next((d for d in dataset if d.get("seriesname") == series_name), None)
    if series is None:
        return None
    for point in reversed(series.get("data", [])):
        raw = point.get("value")
        if raw in (None, ""):
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return None


class ClevelandFedNowcastProvider:
    """Not a MacroDataProvider subclass — Cleveland Fed's inflation
    nowcast has no FRED mirror. The only access path is the internal JSON
    file their own chart loads: an undocumented, unversioned FusionCharts
    payload, not a published API contract. It carries a short rolling
    window of MM/DD-labeled points with no year (not a historical archive)
    — this class doesn't try to parse those dates, it just takes the most
    recent non-blank value per series and stamps it with today's date,
    building history incrementally through repeated fetches like every
    other cached series. The broad exception handling below is deliberate:
    it's what lets an undocumented restructure degrade to "data
    unavailable" instead of a 500, which is the condition this source was
    accepted under."""

    def get_latest_nowcasts(self) -> dict[str, MacroObservationResult]:
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(CLEVELAND_FED_NOWCAST_URL)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            raise MacroDataError(f"Cleveland Fed nowcast request failed: {exc}") from exc

        try:
            dataset = payload[0]["dataset"]
        except (KeyError, IndexError, TypeError) as exc:
            raise MacroDataError(f"Cleveland Fed nowcast response has an unexpected shape: {exc}") from exc

        today = date.today()
        results: dict[str, MacroObservationResult] = {}
        for series_id, cf_label in CLEVELAND_FED_LABEL_MAP.items():
            value = _extract_latest_value(dataset, cf_label)
            if value is not None:
                results[series_id] = MacroObservationResult(observation_date=today, value=value)
        return results
