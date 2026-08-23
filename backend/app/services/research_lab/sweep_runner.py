import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import dependencies
from app.config import settings
from app.db import SessionLocal
from app.models.experiment_run import ExperimentRun
from app.models.sweep_job import SweepJob
from app.schemas.sweep import SweepGridSpec
from app.services.market_data.base import MarketDataError
from app.services.market_data.price_cache import get_price_history_cached
from app.services.research_lab.backtest_result import (
    build_pairs_backtest_response,
    compute_pairs_backtest_input_hash,
)
from app.services.research_lab.engine import WalkForwardConfig
from app.services.research_lab.ou_pairs import STRATEGY_NAME, run_pairs_backtest
from app.services.research_lab.sweep_service import expand_sweep_grid
from app.services.risk.errors import InsufficientHistoryError, MissingTickerDataError
from app.time_utils import utcnow_naive

logger = logging.getLogger(__name__)

# Per-tick cap across ALL active jobs, round-robin — a 200-combo sweep at
# 15s/10-per-tick completes in ~5 minutes worst case.
BATCH_SIZE = 10


@dataclass
class _JobSnapshot:
    """Plain data crossing the thread/session boundary, not a detached ORM
    instance — same rationale as AlertChecker's _PriceRuleSnapshot."""

    id: int
    strategy_name: str
    ticker_a: str
    ticker_b: str
    lookback_years: int
    grid_spec_json: str
    total_configurations: int
    configurations_completed: int
    configurations_failed: int
    created_at: datetime


@dataclass
class _WorkUnit:
    job_id: int
    combo_index: int
    ticker_a: str
    ticker_b: str
    lookback_years: int
    total_configurations: int
    fit_window_days: int
    entry_z: float
    exit_z: float
    cost_bps: float


class SweepRunner:
    """Periodic background task, launched alongside AlertChecker and
    ForwardValidationRunner in main.py's lifespan. Advances active sweep
    jobs by at most BATCH_SIZE combinations per tick, round-robin across
    all active jobs so one large sweep never starves a smaller concurrent
    one — neither existing runner needed this since neither bounds work
    across many objects per tick."""

    async def run(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Sweep tick failed; will retry next interval.")
            await asyncio.sleep(settings.sweep_check_interval_seconds)

    async def _tick(self) -> None:
        jobs = await asyncio.to_thread(self._load_active_jobs)
        if not jobs:
            return
        work_units = self._plan_batch(jobs)
        if not work_units:
            return
        await asyncio.to_thread(self._mark_jobs_running, {wu.job_id for wu in work_units})
        results = await asyncio.gather(
            *(asyncio.to_thread(self._process_combo, wu) for wu in work_units), return_exceptions=True
        )
        for wu, result in zip(work_units, results, strict=True):
            if isinstance(result, Exception):
                logger.warning(
                    "Sweep tick failed for job %s combo %s: %s", wu.job_id, wu.combo_index, result
                )
                await asyncio.to_thread(self._mark_combo_failed, wu.job_id)

    def _plan_batch(self, jobs: list[_JobSnapshot]) -> list[_WorkUnit]:
        """Round-robin, oldest-created-first: at most one combo per job per
        pass over the active job list, repeated until BATCH_SIZE is filled
        or every active job has no more combos to hand out this tick."""
        jobs_sorted = sorted(jobs, key=lambda j: j.created_at)
        combos_by_job = {j.id: expand_sweep_grid(SweepGridSpec(**json.loads(j.grid_spec_json))) for j in jobs_sorted}
        next_index = {j.id: j.configurations_completed + j.configurations_failed for j in jobs_sorted}

        work_units: list[_WorkUnit] = []
        while len(work_units) < BATCH_SIZE:
            progressed = False
            for j in jobs_sorted:
                if len(work_units) >= BATCH_SIZE:
                    break
                idx = next_index[j.id]
                combos = combos_by_job[j.id]
                if idx >= len(combos):
                    continue
                combo = combos[idx]
                work_units.append(
                    _WorkUnit(
                        job_id=j.id,
                        combo_index=idx,
                        ticker_a=j.ticker_a,
                        ticker_b=j.ticker_b,
                        lookback_years=j.lookback_years,
                        total_configurations=j.total_configurations,
                        fit_window_days=combo["fit_window_days"],
                        entry_z=combo["entry_z"],
                        exit_z=combo["exit_z"],
                        cost_bps=combo["cost_bps"],
                    )
                )
                next_index[j.id] += 1
                progressed = True
            if not progressed:
                break
        return work_units

    # --- sync, thread-dispatched units of work -------------------------------

    def _load_active_jobs(self) -> list[_JobSnapshot]:
        db = SessionLocal()
        try:
            rows = (
                db.execute(select(SweepJob).where(SweepJob.status.in_(["queued", "running"])))
                .scalars()
                .all()
            )
            return [
                _JobSnapshot(
                    id=r.id,
                    strategy_name=r.strategy_name,
                    ticker_a=r.ticker_a,
                    ticker_b=r.ticker_b,
                    lookback_years=r.lookback_years,
                    grid_spec_json=r.grid_spec_json,
                    total_configurations=r.total_configurations,
                    configurations_completed=r.configurations_completed,
                    configurations_failed=r.configurations_failed,
                    created_at=r.created_at,
                )
                for r in rows
            ]
        finally:
            db.close()

    def _mark_jobs_running(self, job_ids: set[int]) -> None:
        db = SessionLocal()
        try:
            now = utcnow_naive()
            db.execute(
                update(SweepJob)
                .where(SweepJob.id.in_(job_ids), SweepJob.status == "queued")
                .values(status="running", last_ticked_at=now)
            )
            db.execute(
                update(SweepJob).where(SweepJob.id.in_(job_ids), SweepJob.status == "running").values(last_ticked_at=now)
            )
            db.commit()
        finally:
            db.close()

    def _process_combo(self, wu: _WorkUnit) -> None:
        db = SessionLocal()
        try:
            input_hash = compute_pairs_backtest_input_hash(
                ticker_a=wu.ticker_a,
                ticker_b=wu.ticker_b,
                fit_window_days=wu.fit_window_days,
                entry_z=wu.entry_z,
                exit_z=wu.exit_z,
                cost_bps=wu.cost_bps,
                lookback_years=wu.lookback_years,
            )
            existing = db.execute(
                select(ExperimentRun).where(ExperimentRun.input_hash == input_hash)
            ).scalar_one_or_none()

            if existing is None:
                config = WalkForwardConfig(
                    fit_window_days=wu.fit_window_days,
                    entry_z=wu.entry_z,
                    exit_z=wu.exit_z,
                    cost_bps=wu.cost_bps,
                )

                def prices_fn(tickers: list[str], start, end):
                    return get_price_history_cached(db, dependencies.provider, tickers, start, end)

                try:
                    result = run_pairs_backtest(wu.ticker_a, wu.ticker_b, wu.lookback_years, prices_fn, config)
                except (MarketDataError, MissingTickerDataError, InsufficientHistoryError) as exc:
                    raise RuntimeError(f"combo failed: {exc}") from exc

                response = build_pairs_backtest_response(
                    result,
                    ticker_a=wu.ticker_a,
                    ticker_b=wu.ticker_b,
                    fit_window_days=wu.fit_window_days,
                    entry_z=wu.entry_z,
                    exit_z=wu.exit_z,
                    cost_bps=wu.cost_bps,
                    lookback_years=wu.lookback_years,
                    cached=False,
                    configurations_tested=wu.total_configurations,
                )
                db.add(
                    ExperimentRun(
                        strategy_name=STRATEGY_NAME,
                        ticker_a=wu.ticker_a,
                        ticker_b=wu.ticker_b,
                        input_hash=input_hash,
                        results_json=response.model_dump_json(),
                        status=response.status,
                        fit_window_days=wu.fit_window_days,
                        entry_z=wu.entry_z,
                        exit_z=wu.exit_z,
                        cost_bps=wu.cost_bps,
                        lookback_years=wu.lookback_years,
                        num_trades=response.num_trades,
                        sharpe_net=response.sharpe_net,
                        sharpe_gross=response.sharpe_gross,
                        max_drawdown_net=response.max_drawdown_net,
                        win_rate=response.win_rate,
                        sweep_id=wu.job_id,
                        configurations_tested=wu.total_configurations,
                    )
                )
            # An existing row (from a prior standalone backtest, or a
            # different sweep that already computed this exact combo) is
            # reused untouched — its sweep_id/configurations_tested stays
            # attributed to whoever computed it first.

            db.execute(
                update(SweepJob)
                .where(SweepJob.id == wu.job_id)
                .values(configurations_completed=SweepJob.configurations_completed + 1)
            )
            db.commit()
            self._maybe_complete(db, wu.job_id)
        finally:
            db.close()

    def _mark_combo_failed(self, job_id: int) -> None:
        db = SessionLocal()
        try:
            db.execute(
                update(SweepJob).where(SweepJob.id == job_id).values(configurations_failed=SweepJob.configurations_failed + 1)
            )
            db.commit()
            self._maybe_complete(db, job_id)
        finally:
            db.close()

    def _maybe_complete(self, db: Session, job_id: int) -> None:
        job = db.get(SweepJob, job_id)
        if job is None:
            return
        if job.status != "completed" and job.configurations_completed + job.configurations_failed >= job.total_configurations:
            job.status = "completed"
            job.completed_at = utcnow_naive()
            db.commit()
