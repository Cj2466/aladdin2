from datetime import date, datetime

import httpx

from app.config import settings
from app.services.macro_data.base import (
    MacroDataError,
    MacroDataProvider,
    MacroObservationResult,
)

FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"


class FredProvider(MacroDataProvider):
    """Hand-rolled httpx client for FRED's REST API — a handful of simple
    GET/JSON endpoints, not worth a third-party dependency (same call this
    codebase already made for Resend email)."""

    def get_latest_observations(
        self, series_id: str, fred_units: str, limit: int = 5
    ) -> list[MacroObservationResult]:
        return self._request(
            series_id, fred_units, {"sort_order": "desc", "limit": limit}
        )

    def get_observation_history(
        self, series_id: str, fred_units: str, start: date, end: date
    ) -> list[MacroObservationResult]:
        results = self._request(
            series_id,
            fred_units,
            {"observation_start": start.isoformat(), "observation_end": end.isoformat()},
        )
        return sorted(results, key=lambda r: r.observation_date)

    def _request(
        self, series_id: str, fred_units: str, extra_params: dict
    ) -> list[MacroObservationResult]:
        if not settings.fred_api_key:
            raise MacroDataError("FRED_API_KEY is not configured.")

        params = {
            "series_id": series_id,
            "api_key": settings.fred_api_key,
            "file_type": "json",
            "units": fred_units,
            **extra_params,
        }
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(FRED_OBSERVATIONS_URL, params=params)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            raise MacroDataError(f"FRED request failed for {series_id}: {exc}") from exc

        results = []
        for obs in payload.get("observations", []):
            raw_value = obs.get("value")
            if raw_value is None or raw_value == ".":
                continue  # FRED's own sentinel for a missing data point — never fabricate a number
            results.append(
                MacroObservationResult(
                    observation_date=datetime.strptime(obs["date"], "%Y-%m-%d").date(),
                    value=float(raw_value),
                )
            )
        return results
