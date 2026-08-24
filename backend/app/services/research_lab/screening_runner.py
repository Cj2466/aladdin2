import asyncio
import logging
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select, update

from app import dependencies
from app.config import settings
from app.db import SessionLocal
from app.models.screening_candidate import ScreeningCandidate
from app.models.screening_job import ScreeningJob
from app.services.market_data.base import MarketDataError
from app.services.market_data.price_cache import get_price_history_cached
from app.services.research_lab import momentum, ticker_universe
from app.services.research_lab.screening import (
    screen_momentum_universe,
    screen_pairs_universe,
)
from app.time_utils import utcnow_naive

logger = logging.getLogger(__name__)

# 760 calendar days (up from 180) so the HMM volatility-regime tag has its
# required HMM_WINDOW_TRADING_DAYS=500 trading days of history available —
# empirically verified 2026-08-25: 499/503 S&P 500 tickers get >=500
# trading-day rows over this window; the 4 shortfalls are recent listings,
# handled by classify_regime_hmm's own graceful insufficient-history skip.
MOMENTUM_SCREENING_LOOKBACK_CALENDAR_DAYS = 760
# 750 calendar days (up from 425) so screening.py's cointegration filter has
# its required COINTEGRATION_WINDOW_TRADING_DAYS=500 trading days of history
# available upstream, on top of the existing 253-trading-day correlation
# tail — purely additive, the correlation stage itself is untouched.
PAIRS_SCREENING_LOOKBACK_CALENDAR_DAYS = 750


@dataclass
class _JobSnapshot:
    id: int
    strategy_name: str


class ScreeningRunner:
    """Periodic background task, launched alongside the other research-lab
    runners in main.py's lifespan. Deliberately modeled on
    ForwardValidationRunner's shape (a whole job processed in one tick via
    asyncio.gather) rather than SweepRunner's BATCH_SIZE/round-robin
    shape — a screening job's total work is one fast unit (empirically
    ~9-11s for the whole universe fetch+score at 503 tickers, re-verified
    after the Phase 3 108->503 universe expansion), not many independent
    slow units, so there's no fairness problem BATCH_SIZE/round-robin
    exists to solve."""

    async def run(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Screening tick failed; will retry next interval.")
            await asyncio.sleep(settings.screening_check_interval_seconds)

    async def _tick(self) -> None:
        jobs = await asyncio.to_thread(self._load_queued_jobs)
        if not jobs:
            return
        await asyncio.to_thread(self._mark_jobs_running, [j.id for j in jobs])
        results = await asyncio.gather(
            *(asyncio.to_thread(self._process_job, j) for j in jobs), return_exceptions=True
        )
        for j, result in zip(jobs, results, strict=True):
            if isinstance(result, Exception):
                # _process_job already handles its own failure state internally —
                # reaching here means a bug in the runner itself, not an expected
                # data/market failure. Never leave the job silently "running."
                logger.exception("Screening job %s escaped its own error handling: %s", j.id, result)
                await asyncio.to_thread(self._mark_job_failed, j.id, str(result))

    # --- sync, thread-dispatched units of work -------------------------------

    def _load_queued_jobs(self) -> list[_JobSnapshot]:
        db = SessionLocal()
        try:
            rows = db.execute(select(ScreeningJob).where(ScreeningJob.status == "queued")).scalars().all()
            return [_JobSnapshot(id=r.id, strategy_name=r.strategy_name) for r in rows]
        finally:
            db.close()

    def _mark_jobs_running(self, job_ids: list[int]) -> None:
        db = SessionLocal()
        try:
            db.execute(
                update(ScreeningJob)
                .where(ScreeningJob.id.in_(job_ids))
                .values(status="running", last_ticked_at=utcnow_naive())
            )
            db.commit()
        finally:
            db.close()

    def _mark_job_failed(self, job_id: int, error_message: str) -> None:
        db = SessionLocal()
        try:
            db.execute(
                update(ScreeningJob)
                .where(ScreeningJob.id == job_id)
                .values(status="failed", error_message=error_message[:2000])
            )
            db.commit()
        finally:
            db.close()

    def _process_job(self, snapshot: _JobSnapshot) -> None:
        db = SessionLocal()
        try:
            is_momentum = snapshot.strategy_name == momentum.STRATEGY_NAME
            lookback_days = (
                MOMENTUM_SCREENING_LOOKBACK_CALENDAR_DAYS if is_momentum else PAIRS_SCREENING_LOOKBACK_CALENDAR_DAYS
            )
            end = date.today()
            start = end - timedelta(days=lookback_days)

            try:
                # Reference the module attribute (not a `from ... import` binding)
                # so tests can monkeypatch ticker_universe.SCREENING_UNIVERSE and
                # have it take effect here — same gotcha this codebase already
                # documents for auth_router.send_email in conftest.py.
                prices, missing = get_price_history_cached(
                    db, dependencies.provider, ticker_universe.SCREENING_UNIVERSE, start, end
                )
            except MarketDataError as exc:
                self._fail(db, snapshot.id, str(exc))
                return

            n_resolved = len(ticker_universe.SCREENING_UNIVERSE) - len(missing)

            if is_momentum:
                candidates = screen_momentum_universe(prices)
                rows = [
                    ScreeningCandidate(
                        job_id=snapshot.id,
                        ticker_a=c.ticker,
                        ticker_b=c.ticker,
                        score=c.t_stat,
                        direction=c.direction,
                        regime=c.regime,
                        hac_significant=c.hac_significant,
                        regime_hmm=c.regime_hmm,
                    )
                    for c in candidates
                ]
            else:
                candidates = screen_pairs_universe(prices)
                rows = [
                    ScreeningCandidate(
                        job_id=snapshot.id,
                        ticker_a=c.ticker_a,
                        ticker_b=c.ticker_b,
                        score=c.correlation,
                        direction=None,
                        regime=None,
                        hac_significant=None,
                        regime_hmm=None,
                    )
                    for c in candidates
                ]

            db.add_all(rows)
            job = db.get(ScreeningJob, snapshot.id)
            if job is None:
                db.rollback()
                return
            job.n_tickers_resolved = n_resolved
            job.n_candidates_found = len(rows)
            job.status = "completed"
            job.completed_at = utcnow_naive()
            db.commit()
        except Exception as exc:
            # Any failure must produce a terminal "failed" state, not a stuck "running" job.
            self._fail(db, snapshot.id, str(exc))
        finally:
            db.close()

    def _fail(self, db, job_id: int, error_message: str) -> None:
        db.rollback()
        job = db.get(ScreeningJob, job_id)
        if job is None:
            return
        job.status = "failed"
        job.error_message = error_message[:2000]
        db.commit()
