import asyncio
import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select

from app import dependencies
from app.config import settings
from app.db import SessionLocal
from app.models.screening_candidate import ScreeningCandidate
from app.models.screening_job import ScreeningJob
from app.services.forward_validation_service import register_or_get_forward_validation
from app.services.market_data.base import MarketDataError
from app.services.research_lab import momentum, ou_pairs, ticker_universe
from app.services.research_lab.backtest_result import (
    run_and_store_momentum_backtest,
    run_and_store_pairs_backtest,
)
from app.services.research_lab.system_account import get_or_create_system_user
from app.services.risk.errors import InsufficientHistoryError, MissingTickerDataError
from app.time_utils import utcnow_naive

logger = logging.getLogger(__name__)

# 5 candidates x 2 strategies x ~90 weekday-gated trading days in a 126-day
# window = ~900 new ExperimentRun rows over the entire window — ~1.8x the
# size of a single manual sweep (MAX_SWEEP_COMBINATIONS=500), and 25%/12.5%
# of MAX_MOMENTUM_CANDIDATES_STORED=20/MAX_PAIRS_CANDIDATES_STORED=40: a
# thin top slice of an already-curated shortlist, not "backtest everything
# stored." Most of these are cheap local-cache reads, not fresh network
# calls, since the same day's screening job just fetched and cached these
# exact tickers.
AUTO_BACKTEST_TOP_K = 5


@dataclass
class _PendingBacktestJob:
    id: int
    strategy_name: str


class AutonomousResearchRunner:
    """Periodic background task, launched alongside the other research-lab
    runners in main.py's lifespan. Unlike every other runner, this one
    doesn't just process rows a human already created — it creates its own
    ScreeningJob rows (owned by a dedicated system account) so real
    research keeps accumulating on days nobody logs in, then triggers real
    backtests on the resulting top candidates. ScreeningRunner/SweepRunner
    themselves are untouched: a system-owned job is indistinguishable from
    a user-submitted one to their own queued-job loading (no user_id
    filter there), so this runner's only job is to create rows and react
    to their completion, never to reimplement screening/backtest logic."""

    async def run(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Autonomous research tick failed; will retry next interval.")
            await asyncio.sleep(settings.autonomous_research_check_interval_seconds)

    async def _tick(self) -> None:
        system_user_id = await asyncio.to_thread(self._ensure_system_user)
        await asyncio.to_thread(self._ensure_todays_screening_jobs, system_user_id)
        pending = await asyncio.to_thread(self._load_jobs_needing_auto_backtests, system_user_id)
        for job in pending:
            await asyncio.to_thread(self._trigger_top_candidate_backtests, job.id, job.strategy_name, system_user_id)

    # --- sync, thread-dispatched units of work -------------------------------

    def _ensure_system_user(self) -> int:
        db = SessionLocal()
        try:
            return get_or_create_system_user(db).id
        finally:
            db.close()

    def _ensure_todays_screening_jobs(self, system_user_id: int) -> None:
        # Doesn't account for US market holidays (no trading-calendar
        # dependency added) — a small, explicitly-accepted gap. Weekend
        # gating alone removes the much larger source of redundant runs
        # (104 of 365 days/year); the remaining ~7% holiday case just
        # produces a hash-fresh-but-informationally-redundant row (thanks
        # to price_cache.py's own ROLLING_WINDOW_TOLERANCE_DAYS reusing the
        # last published bar), not wrong data.
        if date.today().weekday() >= 5:
            return

        db = SessionLocal()
        try:
            start_of_today = utcnow_naive().replace(hour=0, minute=0, second=0, microsecond=0)
            for strategy_name in (ou_pairs.STRATEGY_NAME, momentum.STRATEGY_NAME):
                existing = db.execute(
                    select(ScreeningJob.id).where(
                        ScreeningJob.user_id == system_user_id,
                        ScreeningJob.strategy_name == strategy_name,
                        ScreeningJob.created_at >= start_of_today,
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    continue
                db.add(
                    ScreeningJob(
                        user_id=system_user_id,
                        strategy_name=strategy_name,
                        # Reference the module attribute (not a `from ... import`
                        # binding) — same convention ScreeningRunner already
                        # follows, so tests can monkeypatch this too.
                        universe_size=len(ticker_universe.SCREENING_UNIVERSE),
                        status="queued",
                    )
                )
            db.commit()
        finally:
            db.close()

    def _load_jobs_needing_auto_backtests(self, system_user_id: int) -> list[_PendingBacktestJob]:
        db = SessionLocal()
        try:
            rows = db.execute(
                select(ScreeningJob).where(
                    ScreeningJob.user_id == system_user_id,
                    ScreeningJob.status == "completed",
                    ScreeningJob.auto_backtests_triggered.is_(False),
                )
            ).scalars().all()
            return [_PendingBacktestJob(id=r.id, strategy_name=r.strategy_name) for r in rows]
        finally:
            db.close()

    def _trigger_top_candidate_backtests(self, job_id: int, strategy_name: str, system_user_id: int) -> None:
        db = SessionLocal()
        try:
            is_momentum = strategy_name == momentum.STRATEGY_NAME
            # id order == rank order — ScreeningRunner already writes candidates
            # pre-sorted best-first (screen_momentum_universe/screen_pairs_universe
            # both sort before storing), so no separate rank column is needed.
            candidates = (
                db.execute(
                    select(ScreeningCandidate)
                    .where(ScreeningCandidate.job_id == job_id)
                    .order_by(ScreeningCandidate.id)
                    .limit(AUTO_BACKTEST_TOP_K)
                )
                .scalars()
                .all()
            )

            for candidate in candidates:
                try:
                    if is_momentum:
                        run_and_store_momentum_backtest(
                            db,
                            dependencies.provider,
                            ticker=candidate.ticker_a,
                            fit_window_days=momentum.DEFAULT_FIT_WINDOW_DAYS,
                            entry_z=momentum.DEFAULT_ENTRY_Z,
                            exit_z=momentum.DEFAULT_EXIT_Z,
                            cost_bps=momentum.DEFAULT_COST_BPS,
                            lookback_years=momentum.DEFAULT_LOOKBACK_YEARS,
                        )
                    else:
                        run_and_store_pairs_backtest(
                            db,
                            dependencies.provider,
                            ticker_a=candidate.ticker_a,
                            ticker_b=candidate.ticker_b,
                            fit_window_days=ou_pairs.DEFAULT_FIT_WINDOW_DAYS,
                            entry_z=ou_pairs.DEFAULT_ENTRY_Z,
                            exit_z=ou_pairs.DEFAULT_EXIT_Z,
                            cost_bps=ou_pairs.DEFAULT_COST_BPS,
                            lookback_years=ou_pairs.DEFAULT_LOOKBACK_YEARS,
                        )
                except (MarketDataError, MissingTickerDataError, InsufficientHistoryError):
                    # One bad candidate (delisted mid-window, insufficient history,
                    # a transient provider failure that exhausted retries) must
                    # never block its siblings or leave the job stuck un-flagged.
                    logger.warning(
                        "Auto-backtest failed for %s/%s (job %s); continuing with remaining candidates.",
                        candidate.ticker_a,
                        candidate.ticker_b,
                        job_id,
                        exc_info=True,
                    )

                # Independent try/except, not nested inside the backtest's — a
                # failed backtest must never skip registration, and a failed
                # registration must never skip the backtest. This is the one
                # real automation gap this phase closes: without it, a candidate
                # only ever gets a one-shot historical backtest, never the
                # ongoing real-time tracking that lets it actually graduate at
                # MIN_FORWARD_VALIDATION_TRADING_DAYS. No gating on the
                # backtest's own result — forward-validation itself is the
                # honest test; pre-filtering on a noisy small-sample metric
                # would defeat the point, and matches how the existing manual
                # registration flow isn't gated either.
                try:
                    if is_momentum:
                        register_or_get_forward_validation(
                            db,
                            user_id=system_user_id,
                            strategy_name=momentum.STRATEGY_NAME,
                            ticker_a=candidate.ticker_a,
                            ticker_b=candidate.ticker_a,
                            fit_window_days=momentum.DEFAULT_FIT_WINDOW_DAYS,
                            entry_z=momentum.DEFAULT_ENTRY_Z,
                            exit_z=momentum.DEFAULT_EXIT_Z,
                            cost_bps=momentum.DEFAULT_COST_BPS,
                        )
                    else:
                        register_or_get_forward_validation(
                            db,
                            user_id=system_user_id,
                            strategy_name=ou_pairs.STRATEGY_NAME,
                            ticker_a=candidate.ticker_a,
                            ticker_b=candidate.ticker_b,
                            fit_window_days=ou_pairs.DEFAULT_FIT_WINDOW_DAYS,
                            entry_z=ou_pairs.DEFAULT_ENTRY_Z,
                            exit_z=ou_pairs.DEFAULT_EXIT_Z,
                            cost_bps=ou_pairs.DEFAULT_COST_BPS,
                        )
                except Exception:
                    logger.warning(
                        "Auto-registration for forward validation failed for %s/%s (job %s); continuing.",
                        candidate.ticker_a,
                        candidate.ticker_b,
                        job_id,
                        exc_info=True,
                    )

            # An at-most-once attempt, not a guarantee every candidate backtested
            # cleanly — already-completed candidates are idempotent no-ops on any
            # future retry via their own input_hash cache-check, so this flag only
            # needs to prevent re-attempting the same job forever, not track
            # per-candidate success.
            job = db.get(ScreeningJob, job_id)
            if job is not None:
                job.auto_backtests_triggered = True
                db.commit()
        finally:
            db.close()
