import asyncio
import logging

from app.config import settings
from app.services.research_lab.sp500_membership_refresh import (
    RefreshOutcome,
    refresh_membership_data,
)

logger = logging.getLogger(__name__)


class MembershipRefreshRunner:
    """Periodic background task, launched alongside the other research-lab
    runners in main.py's lifespan. Keeps
    sp500_membership_history.py's point-in-time S&P 500 data from silently
    going stale the way ticker_universe.SCREENING_UNIVERSE does — that
    module is a checked-in snapshot, and without this nothing would ever
    move it forward again.

    Deliberately the thinnest runner in the codebase, and the only one
    that opens no SessionLocal at all: a refresh is one network round of
    three GETs whose entire output is a small immutable overlay held in
    process memory, recomputed from source every time. There is nothing
    worth persisting (re-deriving it costs one fetch), and nothing
    persisted means no schema, no migration, and — most importantly — no
    way to end up permanently stuck on a bad snapshot that got written to
    disk. A process restart simply falls back to the vendored literals
    until the first tick completes.

    Failure handling is delegated entirely to refresh_membership_data,
    which never raises for a network or data problem and never discards
    the last known-good data; this class only decides how soon to try
    again."""

    async def run(self) -> None:
        while True:
            interval = settings.membership_refresh_interval_seconds
            try:
                outcome = await asyncio.to_thread(self._tick)
                if not outcome.applied:
                    # Nothing was accepted this round (sources down, or the
                    # data failed validation). Come back sooner than the
                    # normal daily cadence so a transient outage doesn't
                    # cost a full day of freshness.
                    interval = min(interval, settings.membership_refresh_retry_interval_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("S&P 500 membership refresh tick failed; will retry next interval.")
                interval = min(interval, settings.membership_refresh_retry_interval_seconds)
            await asyncio.sleep(interval)

    # --- sync, thread-dispatched unit of work --------------------------------

    def _tick(self) -> RefreshOutcome:
        return refresh_membership_data()
