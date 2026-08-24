import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app import dependencies
from app.models.screening_candidate import ScreeningCandidate
from app.models.screening_job import ScreeningJob
from app.services.market_data.base import MarketDataError
from app.services.research_lab import screening_runner as runner_module
from app.services.research_lab import ticker_universe
from app.services.research_lab.momentum import STRATEGY_NAME as MOMENTUM_STRATEGY_NAME
from app.services.research_lab.ou_pairs import STRATEGY_NAME as PAIRS_STRATEGY_NAME


@pytest.fixture(autouse=True)
def patch_runner_session(test_db_engine, monkeypatch):
    """ScreeningRunner opens its own SessionLocal directly — point that at
    the same per-test SQLite engine, mirroring test_sweep_runner.py's
    patch_runner_session exactly."""
    testing_session_local = sessionmaker(bind=test_db_engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(runner_module, "SessionLocal", testing_session_local)


@pytest.fixture(autouse=True)
def patch_universe(monkeypatch):
    """Screening code references ticker_universe.SCREENING_UNIVERSE at call
    time (module attribute access, not a `from ... import` binding), so
    monkeypatching the module attribute here takes effect — same gotcha
    this codebase already documents for auth_router.send_email."""
    monkeypatch.setattr(ticker_universe, "SCREENING_UNIVERSE", ["AAPL", "MSFT", "GLD", "SPY"])


def _patch_provider(monkeypatch, canned_prices):
    def fake_get_price_history(tickers, start, end):
        present = [t for t in tickers if t in canned_prices.columns]
        missing = [t for t in tickers if t not in canned_prices.columns]
        return canned_prices[present], missing

    monkeypatch.setattr(dependencies.provider, "get_price_history", fake_get_price_history)


def _create_job(db, user_id: int, strategy_name: str) -> ScreeningJob:
    job = ScreeningJob(
        user_id=user_id,
        strategy_name=strategy_name,
        universe_size=4,
        status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@pytest.mark.asyncio
async def test_screening_job_completes_within_one_tick_momentum(
    test_db_engine, register_and_verify, client, canned_prices, monkeypatch
):
    _patch_provider(monkeypatch, canned_prices)
    user = register_and_verify(client)

    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        job = _create_job(db, user["id"], MOMENTUM_STRATEGY_NAME)
        job_id = job.id

    runner = runner_module.ScreeningRunner()
    await runner._tick()

    with session_local() as db:
        j = db.get(ScreeningJob, job_id)
        assert j.status == "completed"
        assert j.n_tickers_resolved == 4
        assert j.completed_at is not None

        rows = db.execute(select(ScreeningCandidate).where(ScreeningCandidate.job_id == job_id)).scalars().all()
        assert j.n_candidates_found == len(rows)
        for row in rows:
            assert row.ticker_a == row.ticker_b  # single-asset strategy
            assert row.direction in ("long", "short")


@pytest.mark.asyncio
async def test_screening_job_completes_within_one_tick_pairs(
    test_db_engine, register_and_verify, client, canned_prices, monkeypatch
):
    _patch_provider(monkeypatch, canned_prices)
    user = register_and_verify(client)

    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        job = _create_job(db, user["id"], PAIRS_STRATEGY_NAME)
        job_id = job.id

    runner = runner_module.ScreeningRunner()
    await runner._tick()

    with session_local() as db:
        j = db.get(ScreeningJob, job_id)
        assert j.status == "completed"
        assert j.n_tickers_resolved == 4

        rows = db.execute(select(ScreeningCandidate).where(ScreeningCandidate.job_id == job_id)).scalars().all()
        assert j.n_candidates_found == len(rows)
        for row in rows:
            assert row.direction is None


@pytest.mark.asyncio
async def test_screening_job_marks_failed_on_market_data_error(
    test_db_engine, register_and_verify, client, monkeypatch
):
    def raise_market_data_error(tickers, start, end):
        raise MarketDataError("simulated provider outage")

    monkeypatch.setattr(dependencies.provider, "get_price_history", raise_market_data_error)
    user = register_and_verify(client)

    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        job = _create_job(db, user["id"], MOMENTUM_STRATEGY_NAME)
        job_id = job.id

    runner = runner_module.ScreeningRunner()
    await runner._tick()

    with session_local() as db:
        j = db.get(ScreeningJob, job_id)
        assert j.status == "failed"
        assert j.error_message is not None
        assert "simulated provider outage" in j.error_message

        rows = db.execute(select(ScreeningCandidate).where(ScreeningCandidate.job_id == job_id)).scalars().all()
        assert len(rows) == 0


@pytest.mark.asyncio
async def test_screening_runner_processes_a_pairs_job_and_a_momentum_job_together(
    test_db_engine, register_and_verify, client, canned_prices, monkeypatch
):
    """Proves the strategy dispatch inside _process_job actually
    differentiates per-job within a single tick — the test that would fail
    loudly if the branch were wrong."""
    _patch_provider(monkeypatch, canned_prices)
    user = register_and_verify(client)

    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        pairs_job = _create_job(db, user["id"], PAIRS_STRATEGY_NAME)
        momentum_job = _create_job(db, user["id"], MOMENTUM_STRATEGY_NAME)
        pairs_id, momentum_id = pairs_job.id, momentum_job.id

    runner = runner_module.ScreeningRunner()
    await runner._tick()

    with session_local() as db:
        pairs_row = db.get(ScreeningJob, pairs_id)
        momentum_row = db.get(ScreeningJob, momentum_id)
        assert pairs_row.status == "completed"
        assert momentum_row.status == "completed"

        pairs_candidates = (
            db.execute(select(ScreeningCandidate).where(ScreeningCandidate.job_id == pairs_id)).scalars().all()
        )
        momentum_candidates = (
            db.execute(select(ScreeningCandidate).where(ScreeningCandidate.job_id == momentum_id)).scalars().all()
        )
        assert all(c.direction is None for c in pairs_candidates)
        assert all(c.direction in ("long", "short") for c in momentum_candidates)
        assert all(c.ticker_a != c.ticker_b for c in pairs_candidates) or len(pairs_candidates) == 0
        assert all(c.ticker_a == c.ticker_b for c in momentum_candidates)
