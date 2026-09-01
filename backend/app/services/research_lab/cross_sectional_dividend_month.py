"""DIVIDEND MONTH PREMIUM -- placeholder while the source paper's actual
methodology is being verified. The full module docstring, the spec grid and
the pre-registration replace this file wholesale before any return is
computed. Only the cache path below is load-bearing right now: the data
acquisition script imports it so there is one source of truth for where the
fetched dividend calendar lives."""

from pathlib import Path

# Default on-disk cache for the fetched dividend calendar, following the
# data/ convention the EAP announcement calendar and the futures/insider
# caches use. Gitignored as a refetchable VENDOR INPUT, not a result.
DIVIDEND_CACHE_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "dividend_month_ex_date_calendar.json"
)
