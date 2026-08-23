import json

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app import dependencies
from app.models.experiment_run import ExperimentRun
from app.models.sweep_job import SweepJob
from app.services.research_lab import sweep_runner as runner_module
from app.services.research_lab.backtest_result import compute_pairs_backtest_input_hash
from app.services.research_lab.ou_pairs import STRATEGY_NAME
from app.services.risk.errors import MissingTickerDataError


@pytest.fixture(autouse=True)
def patch_runner_session(test_db_engine, monkeypatch):
    """SweepRunner opens its own SessionLocal directly — point that at the
    same per-test SQLite engine, mirroring test_forward_validation.py's
    patch_runner_session exactly."""
    testing_session_local = sessionmaker(bind=test_db_engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(runner_module, "SessionLocal", testing_session_local)


def _patch_provider(monkeypatch, canned_prices):
    def fake_get_price_history(tickers, start, end):
        present = [t for t in tickers if t in canned_prices.columns]
        missing = [t for t in tickers if t not in canned_prices.columns]
        return canned_prices[present], missing

    monkeypatch.setattr(dependencies.provider, "get_price_history", fake_get_price_history)


def _create_job(db, user_id: int, *, ticker_a="AAPL", ticker_b="MSFT", fit_window_days_values, lookback_years=3):
    grid_spec = {
        "fit_window_days": fit_window_days_values,
        "entry_z": [2.0],
        "exit_z": [0.0],
        "cost_bps": [10.0],
    }
    job = SweepJob(
        user_id=user_id,
        strategy_name=STRATEGY_NAME,
        ticker_a=ticker_a,
        ticker_b=ticker_b,
        lookback_years=lookback_years,
        grid_spec_json=json.dumps(grid_spec),
        total_configurations=len(fit_window_days_values),
        configurations_completed=0,
        configurations_failed=0,
        status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@pytest.mark.asyncio
async def test_batches_across_ticks_and_completes(test_db_engine, register_and_verify, client, canned_prices, monkeypatch):
    monkeypatch.setattr(runner_module, "BATCH_SIZE", 2)
    _patch_provider(monkeypatch, canned_prices)
    user = register_and_verify(client)

    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        job = _create_job(db, user["id"], fit_window_days_values=[100, 150, 200])
        job_id = job.id

    runner = runner_module.SweepRunner()
    await runner._tick()
    with session_local() as db:
        j = db.get(SweepJob, job_id)
        assert j.configurations_completed == 2
        assert j.status == "running"

    await runner._tick()
    with session_local() as db:
        j = db.get(SweepJob, job_id)
        assert j.configurations_completed == 3
        assert j.status == "completed"
        assert j.completed_at is not None

        rows = db.execute(select(ExperimentRun).where(ExperimentRun.sweep_id == job_id)).scalars().all()
        assert len(rows) == 3
        for row in rows:
            assert row.configurations_tested == 3


@pytest.mark.asyncio
async def test_reuses_existing_experiment_run_without_duplicating(
    test_db_engine, register_and_verify, client, canned_prices, monkeypatch
):
    _patch_provider(monkeypatch, canned_prices)
    user = register_and_verify(client)

    input_hash = compute_pairs_backtest_input_hash(
        ticker_a="AAPL", ticker_b="MSFT", fit_window_days=100, entry_z=2.0, exit_z=0.0, cost_bps=10.0, lookback_years=3
    )

    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        job = _create_job(db, user["id"], fit_window_days_values=[100])
        job_id = job.id

        pre_existing = ExperimentRun(
            strategy_name=STRATEGY_NAME,
            ticker_a="AAPL",
            ticker_b="MSFT",
            input_hash=input_hash,
            results_json=json.dumps({"status": "ok"}),
            status="ok",
            fit_window_days=100,
            entry_z=2.0,
            exit_z=0.0,
            cost_bps=10.0,
            lookback_years=3,
            num_trades=0,
            sweep_id=None,
            configurations_tested=1,
        )
        db.add(pre_existing)
        db.commit()
        pre_existing_id = pre_existing.id

    runner = runner_module.SweepRunner()
    await runner._tick()

    with session_local() as db:
        rows = db.execute(select(ExperimentRun).where(ExperimentRun.input_hash == input_hash)).scalars().all()
        assert len(rows) == 1  # reused, not duplicated
        assert rows[0].id == pre_existing_id
        assert rows[0].sweep_id is None  # provenance never overwritten by the sweep that reused it
        assert rows[0].configurations_tested == 1

        j = db.get(SweepJob, job_id)
        assert j.configurations_completed == 1
        assert j.status == "completed"


@pytest.mark.asyncio
async def test_round_robin_fairness_across_two_jobs(
    test_db_engine, register_and_verify, client, canned_prices, monkeypatch
):
    monkeypatch.setattr(runner_module, "BATCH_SIZE", 4)
    _patch_provider(monkeypatch, canned_prices)
    user = register_and_verify(client)

    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        big_job = _create_job(
            db, user["id"], ticker_a="AAPL", ticker_b="MSFT", fit_window_days_values=[100, 110, 120, 130, 140, 150]
        )
        small_job = _create_job(db, user["id"], ticker_a="GLD", ticker_b="SPY", fit_window_days_values=[100])
        big_id, small_id = big_job.id, small_job.id

    runner = runner_module.SweepRunner()
    await runner._tick()

    with session_local() as db:
        big = db.get(SweepJob, big_id)
        small = db.get(SweepJob, small_id)
        # The small job's single combo is never starved by the large job
        # monopolizing the whole batch — it completes within the same tick.
        assert small.configurations_completed == 1
        assert small.status == "completed"
        # Round-robin caps how much of the batch one job can claim before
        # every other active job gets a turn.
        assert big.configurations_completed == 3
        assert big.status == "running"


@pytest.mark.asyncio
async def test_per_combo_failure_increments_failed_and_job_still_completes(
    test_db_engine, register_and_verify, client, canned_prices, monkeypatch
):
    _patch_provider(monkeypatch, canned_prices)
    user = register_and_verify(client)

    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        job = _create_job(db, user["id"], fit_window_days_values=[100, 150])
        job_id = job.id

    real_run_pairs_backtest = runner_module.run_pairs_backtest

    def flaky_run_pairs_backtest(ticker_a, ticker_b, lookback_years, prices_fn, config):
        if config.fit_window_days == 150:
            raise MissingTickerDataError(["MSFT"], label="pair")
        return real_run_pairs_backtest(ticker_a, ticker_b, lookback_years, prices_fn, config)

    monkeypatch.setattr(runner_module, "run_pairs_backtest", flaky_run_pairs_backtest)

    runner = runner_module.SweepRunner()
    await runner._tick()

    with session_local() as db:
        j = db.get(SweepJob, job_id)
        assert j.configurations_completed == 1
        assert j.configurations_failed == 1
        assert j.status == "completed"

        rows = db.execute(select(ExperimentRun).where(ExperimentRun.sweep_id == job_id)).scalars().all()
        assert len(rows) == 1
        assert rows[0].fit_window_days == 100
