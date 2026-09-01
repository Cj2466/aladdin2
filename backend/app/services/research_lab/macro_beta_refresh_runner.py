import asyncio
import logging
from dataclasses import dataclass

from app.config import settings
from app.db import SessionLocal
from app.services.macro_data.fred_provider import FredProvider
from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.macro_beta import (
    latest_beta_as_of_date,
    run_macro_beta_family,
)
from app.services.research_lab.ticker_universe import SCREENING_UNIVERSE
from app.time_utils import utcnow_naive

logger = logging.getLogger(__name__)


@dataclass
class MacroBetaTickOutcome:
    recomputed: bool
    reason: str
    n_rows: int = 0


class MacroBetaRefreshRunner:
    """Periodic background task, launched alongside the other research-lab
    runners in main.py's lifespan. Keeps macro_commodity_betas from silently
    going stale.

    TWO SEPARATE CADENCES, and the distinction is the whole point of this
    class. It TICKS every macro_beta_refresh_interval_seconds (daily), but it
    only RECOMPUTES when the newest as_of_date is older than
    macro_beta_recompute_stale_after_days (7). A tick that finds the table
    fresh is a single indexed query and returns immediately.

    Why not just recompute on every tick: a 252-day rolling beta barely moves
    when one day rolls on and one rolls off, and the table is APPEND-ONLY (see
    MacroCommodityBeta's docstring), so every needless recompute writes a
    permanent ~6,500-row generation rather than overwriting anything. Daily
    recomputation would bloat the table sevenfold to chase noise.

    AN EMPTY TABLE COUNTS AS STALE. A fresh deploy has never computed
    anything, and a staleness check that treated "no rows" as "nothing to do"
    would leave the table empty forever — the runner would tick daily and do
    nothing, permanently. This is the specific failure mode
    test_macro_beta_refresh_runner.py pins first.

    A recompute is a real network round (503 tickers plus 7 ETFs of price
    history, plus 6 FRED series) and is dispatched to a thread so it never
    blocks the event loop. Failures are logged and retried on the next tick;
    nothing is ever partially written, because run_macro_beta_family commits
    once at the end.
    """

    async def run(self) -> None:
        while True:
            try:
                outcome = await asyncio.to_thread(self._tick)
                if outcome.recomputed:
                    logger.info(
                        "macro beta refresh: recomputed %d rows (%s)",
                        outcome.n_rows,
                        outcome.reason,
                    )
                else:
                    logger.info("macro beta refresh: skipped (%s)", outcome.reason)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Macro beta refresh tick failed; will retry next interval.")
            await asyncio.sleep(settings.macro_beta_refresh_interval_seconds)

    # --- sync, thread-dispatched unit of work --------------------------------

    def _tick(self) -> MacroBetaTickOutcome:
        today = utcnow_naive().date()
        db = SessionLocal()
        try:
            newest = latest_beta_as_of_date(db)
            if newest is not None:
                age_days = (today - newest).days
                if age_days < settings.macro_beta_recompute_stale_after_days:
                    return MacroBetaTickOutcome(
                        recomputed=False,
                        reason=(
                            f"newest as_of_date {newest} is {age_days}d old, "
                            f"below the {settings.macro_beta_recompute_stale_after_days}d bar"
                        ),
                    )
                reason = f"newest as_of_date {newest} is {age_days}d old"
            else:
                reason = "table is empty — never computed"

            summary = run_macro_beta_family(
                db,
                YFinanceProvider(),
                FredProvider(),
                SCREENING_UNIVERSE,
                end=today,
            )
            return MacroBetaTickOutcome(
                recomputed=True, reason=reason, n_rows=summary.n_rows
            )
        finally:
            db.close()
