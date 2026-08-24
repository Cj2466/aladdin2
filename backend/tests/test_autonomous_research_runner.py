from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app import dependencies
from app.models.experiment_run import ExperimentRun
from app.models.screening_candidate import ScreeningCandidate
from app.models.screening_job import ScreeningJob
from app.models.user import User
from app.services.research_lab import autonomous_research_runner as runner_module
from app.services.research_lab import ticker_universe
from app.services.research_lab.momentum import STRATEGY_NAME as MOMENTUM_STRATEGY_NAME
from app.services.research_lab.ou_pairs import STRATEGY_NAME as PAIRS_STRATEGY_NAME
from app.services.risk.errors import MissingTickerDataError


@pytest.fixture(autouse=True)
def patch_runner_session(test_db_engine, monkeypatch):
    testing_session_local = sessionmaker(bind=test_db_engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(runner_module, "SessionLocal", testing_session_local)


@pytest.fixture(autouse=True)
def patch_universe(monkeypatch):
    monkeypatch.setattr(ticker_universe, "SCREENING_UNIVERSE", ["AAPL", "MSFT", "GLD", "SPY"])


def _patch_provider(monkeypatch, canned_prices):
    def fake_get_price_history(tickers, start, end):
        present = [t for t in tickers if t in canned_prices.columns]
        missing = [t for t in tickers if t not in canned_prices.columns]
        return canned_prices[present], missing

    monkeypatch.setattr(dependencies.provider, "get_price_history", fake_get_price_history)


def _session_local(test_db_engine):
    return sessionmaker(bind=test_db_engine)


def _patch_today(monkeypatch, fixed_date: date) -> None:
    # datetime.date is an immutable built-in type — its `today` classmethod
    # can't be monkeypatched directly (raises TypeError). Replace the `date`
    # name the runner module actually calls instead.
    class FakeDate(date):
        @classmethod
        def today(cls):
            return fixed_date

    monkeypatch.setattr(runner_module, "date", FakeDate)


def test_ensure_system_user_is_idempotent(test_db_engine):
    runner = runner_module.AutonomousResearchRunner()
    first_id = runner._ensure_system_user()
    second_id = runner._ensure_system_user()
    assert first_id == second_id

    with _session_local(test_db_engine)() as db:
        count = db.execute(select(User)).scalars().all()
        assert len(count) == 1


def test_tick_creates_one_job_per_strategy_on_a_weekday(test_db_engine, monkeypatch):
    _patch_today(monkeypatch, date(2026, 8, 19))  # a Wednesday
    runner = runner_module.AutonomousResearchRunner()
    system_user_id = runner._ensure_system_user()
    runner._ensure_todays_screening_jobs(system_user_id)

    with _session_local(test_db_engine)() as db:
        jobs = db.execute(select(ScreeningJob).where(ScreeningJob.user_id == system_user_id)).scalars().all()
    assert len(jobs) == 2
    assert {j.strategy_name for j in jobs} == {MOMENTUM_STRATEGY_NAME, PAIRS_STRATEGY_NAME}
    assert all(j.status == "queued" for j in jobs)


def test_tick_is_idempotent_within_the_same_day(test_db_engine, monkeypatch):
    _patch_today(monkeypatch, date(2026, 8, 19))  # a Wednesday
    runner = runner_module.AutonomousResearchRunner()
    system_user_id = runner._ensure_system_user()
    runner._ensure_todays_screening_jobs(system_user_id)
    runner._ensure_todays_screening_jobs(system_user_id)

    with _session_local(test_db_engine)() as db:
        jobs = db.execute(select(ScreeningJob).where(ScreeningJob.user_id == system_user_id)).scalars().all()
    assert len(jobs) == 2


def test_tick_skips_job_creation_on_weekend(test_db_engine, monkeypatch):
    _patch_today(monkeypatch, date(2026, 8, 22))  # a Saturday
    runner = runner_module.AutonomousResearchRunner()
    system_user_id = runner._ensure_system_user()
    runner._ensure_todays_screening_jobs(system_user_id)

    with _session_local(test_db_engine)() as db:
        jobs = db.execute(select(ScreeningJob).where(ScreeningJob.user_id == system_user_id)).scalars().all()
    assert len(jobs) == 0


def _create_completed_job(db, user_id: int, strategy_name: str, tickers: list[str]) -> ScreeningJob:
    job = ScreeningJob(
        user_id=user_id,
        strategy_name=strategy_name,
        universe_size=4,
        n_tickers_resolved=4,
        n_candidates_found=len(tickers),
        status="completed",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    for i, ticker in enumerate(tickers):
        db.add(ScreeningCandidate(job_id=job.id, ticker_a=ticker, ticker_b=ticker, score=float(10 - i), direction="long"))
    db.commit()
    return job


@pytest.mark.asyncio
async def test_tick_triggers_auto_backtests_for_completed_unflagged_system_jobs(
    test_db_engine, canned_prices, monkeypatch
):
    _patch_provider(monkeypatch, canned_prices)
    runner = runner_module.AutonomousResearchRunner()
    system_user_id = runner._ensure_system_user()

    with _session_local(test_db_engine)() as db:
        job = _create_completed_job(db, system_user_id, MOMENTUM_STRATEGY_NAME, ["AAPL", "MSFT"])
        job_id = job.id

    runner._trigger_top_candidate_backtests(job_id, MOMENTUM_STRATEGY_NAME)

    with _session_local(test_db_engine)() as db:
        refreshed = db.get(ScreeningJob, job_id)
        assert refreshed.auto_backtests_triggered is True
        runs = db.execute(select(ExperimentRun).where(ExperimentRun.strategy_name == MOMENTUM_STRATEGY_NAME)).scalars().all()
        assert len(runs) == 2
        assert {r.ticker_a for r in runs} == {"AAPL", "MSFT"}


@pytest.mark.asyncio
async def test_auto_backtest_respects_top_k_cap(test_db_engine, canned_prices, monkeypatch):
    _patch_provider(monkeypatch, canned_prices)
    runner = runner_module.AutonomousResearchRunner()
    system_user_id = runner._ensure_system_user()

    # 4 candidates, but only AAPL/MSFT/GLD/SPY exist in canned_prices — cap
    # AUTO_BACKTEST_TOP_K itself is what's under test, so patch it down to 2
    # rather than relying on there being more real candidates than tickers.
    monkeypatch.setattr(runner_module, "AUTO_BACKTEST_TOP_K", 2)

    with _session_local(test_db_engine)() as db:
        job = _create_completed_job(db, system_user_id, PAIRS_STRATEGY_NAME, [])
        job_id = job.id
        for i, (a, b) in enumerate([("AAPL", "MSFT"), ("GLD", "SPY"), ("AAPL", "GLD")]):
            db.add(ScreeningCandidate(job_id=job_id, ticker_a=a, ticker_b=b, score=float(10 - i)))
        db.commit()

    runner._trigger_top_candidate_backtests(job_id, PAIRS_STRATEGY_NAME)

    with _session_local(test_db_engine)() as db:
        runs = db.execute(select(ExperimentRun).where(ExperimentRun.strategy_name == PAIRS_STRATEGY_NAME)).scalars().all()
        assert len(runs) == 2


@pytest.mark.asyncio
async def test_auto_backtest_skips_a_failing_candidate_without_blocking_siblings(
    test_db_engine, canned_prices, monkeypatch
):
    def flaky_get_price_history(tickers, start, end):
        if "AAPL" in tickers:
            raise MissingTickerDataError(["AAPL"], label="ticker")
        present = [t for t in tickers if t in canned_prices.columns]
        missing = [t for t in tickers if t not in canned_prices.columns]
        return canned_prices[present], missing

    monkeypatch.setattr(dependencies.provider, "get_price_history", flaky_get_price_history)

    runner = runner_module.AutonomousResearchRunner()
    system_user_id = runner._ensure_system_user()

    with _session_local(test_db_engine)() as db:
        job = _create_completed_job(db, system_user_id, MOMENTUM_STRATEGY_NAME, ["AAPL", "MSFT"])
        job_id = job.id

    runner._trigger_top_candidate_backtests(job_id, MOMENTUM_STRATEGY_NAME)

    with _session_local(test_db_engine)() as db:
        refreshed = db.get(ScreeningJob, job_id)
        assert refreshed.auto_backtests_triggered is True
        runs = db.execute(select(ExperimentRun).where(ExperimentRun.strategy_name == MOMENTUM_STRATEGY_NAME)).scalars().all()
        assert len(runs) == 1
        assert runs[0].ticker_a == "MSFT"


@pytest.mark.asyncio
async def test_user_submitted_completed_jobs_are_never_auto_backtested(
    test_db_engine, register_and_verify, client, canned_prices, monkeypatch
):
    _patch_provider(monkeypatch, canned_prices)
    user = register_and_verify(client)
    runner = runner_module.AutonomousResearchRunner()

    with _session_local(test_db_engine)() as db:
        job = _create_completed_job(db, user["id"], MOMENTUM_STRATEGY_NAME, ["AAPL"])
        job_id = job.id

    await runner._tick()

    with _session_local(test_db_engine)() as db:
        refreshed = db.get(ScreeningJob, job_id)
        assert refreshed.auto_backtests_triggered is False  # never touched — not system-owned
        runs = db.execute(select(ExperimentRun)).scalars().all()
        assert runs == []
