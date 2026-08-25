import asyncio
import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select

from app import dependencies
from app.config import settings
from app.db import SessionLocal
from app.models.forward_validation import ForwardValidationRegistration
from app.models.screening_candidate import ScreeningCandidate
from app.models.screening_job import ScreeningJob
from app.services.forward_validation_service import (
    compute_forward_validation_config_hash,
    register_or_get_forward_validation,
)
from app.services.market_data.base import MarketDataError
from app.services.research_lab import (
    autonomous_tuning,
    momentum,
    ou_pairs,
    ticker_universe,
)
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
#
# Per-candidate parameter tuning (autonomous_tuning) adds rows on top of
# this, but only for candidates seen for the first time and only up to
# MAX_NEW_TUNINGS_PER_JOB per job per day — see that module's own sizing
# comment, which bounds the combined worst case against the same free-tier
# storage ceiling this number was originally sized against.
AUTO_BACKTEST_TOP_K = 5

# Pull this many times AUTO_BACKTEST_TOP_K candidates so a candidate whose
# config already has an "underperforming" forward-validation registration
# (see forward_validation_service.check_underperformance) can be skipped
# and backfilled by the next-best candidate, rather than silently shrinking
# that day's batch below AUTO_BACKTEST_TOP_K. The feedback loop this closes:
# without it, a known-bad configuration would keep re-consuming one of the
# scarce daily backtest/registration slots forever, since screening's own
# score has no memory of past forward-validation outcomes.
AUTO_BACKTEST_CANDIDATE_BUFFER_MULTIPLIER = 3


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
            # Pull a widened buffer (see AUTO_BACKTEST_CANDIDATE_BUFFER_MULTIPLIER) —
            # not just AUTO_BACKTEST_TOP_K — so a known-underperforming candidate can
            # be skipped and backfilled from further down the ranked list.
            candidates = (
                db.execute(
                    select(ScreeningCandidate)
                    .where(ScreeningCandidate.job_id == job_id)
                    .order_by(ScreeningCandidate.id)
                    .limit(AUTO_BACKTEST_TOP_K * AUTO_BACKTEST_CANDIDATE_BUFFER_MULTIPLIER)
                )
                .scalars()
                .all()
            )

            strategy_name = momentum.STRATEGY_NAME if is_momentum else ou_pairs.STRATEGY_NAME
            lookback_years = (
                momentum.DEFAULT_LOOKBACK_YEARS if is_momentum else ou_pairs.DEFAULT_LOOKBACK_YEARS
            )

            n_processed = 0
            n_fresh_tunings = 0
            for candidate in candidates:
                if n_processed >= AUTO_BACKTEST_TOP_K:
                    break

                # Momentum rows carry ticker_b == ticker_a, the convention
                # already established everywhere else a single-asset strategy
                # crosses a 2-ticker-shaped boundary.
                ticker_b = candidate.ticker_a if is_momentum else candidate.ticker_b

                # Which parameters should this specific ticker/pair actually be
                # traded on? Until this call existed, the answer was always
                # "the strategy's DEFAULT_* constants," identically for every
                # candidate. autonomous_tuning reuses an existing registration's
                # config if there is one, otherwise runs a small DSR-ranked
                # parameter sweep (see that module for the full reasoning), and
                # falls back to those same defaults whenever the search can't
                # support an honest answer.
                try:
                    tuning = autonomous_tuning.resolve_candidate_config(
                        db,
                        dependencies.provider,
                        user_id=system_user_id,
                        strategy_name=strategy_name,
                        ticker_a=candidate.ticker_a,
                        ticker_b=ticker_b,
                        allow_tuning=n_fresh_tunings < autonomous_tuning.MAX_NEW_TUNINGS_PER_JOB,
                    )
                except Exception:
                    # Tuning is an enhancement, never a gate: anything unexpected
                    # here must degrade to the previous behaviour (bare defaults),
                    # not cost this candidate its backtest and registration.
                    logger.warning(
                        "Tuning failed for %s/%s (job %s); falling back to strategy defaults.",
                        candidate.ticker_a,
                        ticker_b,
                        job_id,
                        exc_info=True,
                    )
                    tuning = None
                config = (
                    tuning.config if tuning is not None else autonomous_tuning.default_config(strategy_name)
                )
                if tuning is not None and tuning.source == "tuned":
                    n_fresh_tunings += 1
                    logger.info(
                        "Tuned %s/%s (job %s): %s", candidate.ticker_a, ticker_b, job_id, tuning.note
                    )

                config_hash = compute_forward_validation_config_hash(
                    strategy_name,
                    candidate.ticker_a,
                    ticker_b,
                    config.fit_window_days,
                    config.entry_z,
                    config.exit_z,
                    config.cost_bps,
                )
                is_known_underperforming = db.execute(
                    select(ForwardValidationRegistration.id).where(
                        ForwardValidationRegistration.user_id == system_user_id,
                        ForwardValidationRegistration.config_hash == config_hash,
                        ForwardValidationRegistration.status == "underperforming",
                    )
                ).scalar_one_or_none()
                if is_known_underperforming is not None:
                    logger.info(
                        "Skipping known-underperforming candidate %s/%s (job %s); trying next candidate.",
                        candidate.ticker_a,
                        ticker_b,
                        job_id,
                    )
                    continue

                n_processed += 1
                try:
                    if is_momentum:
                        run_and_store_momentum_backtest(
                            db,
                            dependencies.provider,
                            ticker=candidate.ticker_a,
                            fit_window_days=config.fit_window_days,
                            entry_z=config.entry_z,
                            exit_z=config.exit_z,
                            cost_bps=config.cost_bps,
                            lookback_years=lookback_years,
                        )
                    else:
                        run_and_store_pairs_backtest(
                            db,
                            dependencies.provider,
                            ticker_a=candidate.ticker_a,
                            ticker_b=candidate.ticker_b,
                            fit_window_days=config.fit_window_days,
                            entry_z=config.entry_z,
                            exit_z=config.exit_z,
                            cost_bps=config.cost_bps,
                            lookback_years=lookback_years,
                        )
                except (MarketDataError, MissingTickerDataError, InsufficientHistoryError):
                    # One bad candidate (delisted mid-window, insufficient history,
                    # a transient provider failure that exhausted retries) must
                    # never block its siblings or leave the job stuck un-flagged.
                    logger.warning(
                        "Auto-backtest failed for %s/%s (job %s); continuing with remaining candidates.",
                        candidate.ticker_a,
                        ticker_b,
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
                #
                # Registered under the SAME tuned config the backtest above just
                # used — keeping the two directly comparable, and making the
                # registration's config_hash identity the tuned configuration
                # rather than the bare defaults. Idempotency is unchanged:
                # register_or_get_forward_validation still keys on
                # (user_id, config_hash), and autonomous_tuning's reuse-first
                # rule guarantees the same candidate resolves to the same config
                # on every later day, so a re-registration stays a no-op read and
                # never resets accumulated progress.
                try:
                    register_or_get_forward_validation(
                        db,
                        user_id=system_user_id,
                        strategy_name=strategy_name,
                        ticker_a=candidate.ticker_a,
                        ticker_b=ticker_b,
                        fit_window_days=config.fit_window_days,
                        entry_z=config.entry_z,
                        exit_z=config.exit_z,
                        cost_bps=config.cost_bps,
                    )
                except Exception:
                    logger.warning(
                        "Auto-registration for forward validation failed for %s/%s (job %s); continuing.",
                        candidate.ticker_a,
                        ticker_b,
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
