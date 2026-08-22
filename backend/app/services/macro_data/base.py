from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


class MacroDataError(Exception):
    """Raised when a macro data provider fails to return usable data (a
    missing API key, an upstream HTTP failure). Never raised for an
    individual missing observation — see MacroObservationResult."""


@dataclass
class MacroObservationResult:
    observation_date: date
    value: float


class MacroDataProvider(ABC):
    """A source of economic-indicator observations (FRED, in practice).
    Kept abstract, mirroring MarketDataProvider, so the cache/router layer
    never depends on FRED specifically."""

    @abstractmethod
    def get_latest_observations(
        self, series_id: str, fred_units: str, limit: int = 5
    ) -> list[MacroObservationResult]:
        """Most recent `limit` observations, newest first. Fetching a few
        (not just one) absorbs FRED's habit of revising the most recent 1-2
        readings for some series (e.g. GDP) without a separate backfill job."""
        raise NotImplementedError

    @abstractmethod
    def get_observation_history(
        self, series_id: str, fred_units: str, start: date, end: date
    ) -> list[MacroObservationResult]:
        """All observations in [start, end], ascending by date."""
        raise NotImplementedError
