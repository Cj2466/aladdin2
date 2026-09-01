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
from app.services.research_lab import autonomous_tuning, ticker_universe
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

    runner._trigger_top_candidate_backtests(job_id, MOMENTUM_STRATEGY_NAME, system_user_id)

    with _session_local(test_db_engine)() as db:
        refreshed = db.get(ScreeningJob, job_id)
        assert refreshed.auto_backtests_triggered is True
        runs = db.execute(select(ExperimentRun).where(ExperimentRun.strategy_name == MOMENTUM_STRATEGY_NAME)).scalars().all()
        # Both top candidates get real backtests. The row COUNT is no longer 2:
        # each first-time candidate also runs autonomous_tuning's bounded grid,
        # and every combination in it is itself a real, stored ExperimentRun
        # (that's what makes the deflated Sharpe's n_trials honest). What must
        # still hold is the property this test has always covered — every top
        # candidate, and only those, got backtested.
        assert {r.ticker_a for r in runs} == {"AAPL", "MSFT"}
        assert len(runs) == 2 * len(autonomous_tuning.build_tuning_grid(MOMENTUM_STRATEGY_NAME))


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

    runner._trigger_top_candidate_backtests(job_id, PAIRS_STRATEGY_NAME, system_user_id)

    with _session_local(test_db_engine)() as db:
        runs = db.execute(select(ExperimentRun).where(ExperimentRun.strategy_name == PAIRS_STRATEGY_NAME)).scalars().all()
        # The cap is on CANDIDATES, not on stored rows (each candidate now also
        # runs a tuning grid) — so assert on distinct ticker pairs.
        assert {(r.ticker_a, r.ticker_b) for r in runs} == {("AAPL", "MSFT"), ("GLD", "SPY")}


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

    runner._trigger_top_candidate_backtests(job_id, MOMENTUM_STRATEGY_NAME, system_user_id)

    with _session_local(test_db_engine)() as db:
        refreshed = db.get(ScreeningJob, job_id)
        assert refreshed.auto_backtests_triggered is True
        runs = db.execute(select(ExperimentRun).where(ExperimentRun.strategy_name == MOMENTUM_STRATEGY_NAME)).scalars().all()
        # AAPL fails at every tuning combination AND at its own backtest;
        # MSFT is unaffected. Assert on distinct tickers, since MSFT now
        # contributes one row per surviving tuning combination.
        assert {r.ticker_a for r in runs} == {"MSFT"}


@pytest.mark.asyncio
async def test_known_underperforming_candidate_is_skipped_and_backfilled(
    test_db_engine, canned_prices, monkeypatch
):
    from app.models.forward_validation import ForwardValidationRegistration
    from app.services.forward_validation_service import compute_forward_validation_config_hash

    _patch_provider(monkeypatch, canned_prices)
    runner = runner_module.AutonomousResearchRunner()
    system_user_id = runner._ensure_system_user()

    with _session_local(test_db_engine)() as db:
        # 3 candidates, AUTO_BACKTEST_TOP_K left at its real default (5) —
        # the first (best-ranked) candidate's config is already flagged
        # underperforming, so it must be skipped and the other two backtested.
        job = _create_completed_job(db, system_user_id, MOMENTUM_STRATEGY_NAME, ["AAPL", "MSFT", "GLD"])
        job_id = job.id

        bad_hash = compute_forward_validation_config_hash(
            MOMENTUM_STRATEGY_NAME, "AAPL", "AAPL", 90, 2.0, 0.0, 5.0
        )
        db.add(
            ForwardValidationRegistration(
                user_id=system_user_id,
                strategy_name=MOMENTUM_STRATEGY_NAME,
                ticker_a="AAPL",
                ticker_b="AAPL",
                fit_window_days=90,
                entry_z=2.0,
                exit_z=0.0,
                cost_bps=5.0,
                config_hash=bad_hash,
                status="underperforming",
                min_trading_days_threshold=126,
                n_forward_trading_days=60,
                started_at=date(2026, 1, 1),
                carry_state_json="{}",
                day_results_json="[]",
                trades_json="[]",
            )
        )
        db.commit()

    runner._trigger_top_candidate_backtests(job_id, MOMENTUM_STRATEGY_NAME, system_user_id)

    with _session_local(test_db_engine)() as db:
        runs = db.execute(select(ExperimentRun).where(ExperimentRun.strategy_name == MOMENTUM_STRATEGY_NAME)).scalars().all()
        backtested_tickers = {r.ticker_a for r in runs}
        assert "AAPL" not in backtested_tickers  # skipped — known underperforming
        assert backtested_tickers == {"MSFT", "GLD"}

        # No new registration should have been created/touched for the
        # skipped candidate — its existing registration must stay exactly
        # as it was (still underperforming, still 60 days).
        regs = db.execute(
            select(ForwardValidationRegistration).where(ForwardValidationRegistration.config_hash == bad_hash)
        ).scalars().all()
        assert len(regs) == 1
        assert regs[0].status == "underperforming"
        assert regs[0].n_forward_trading_days == 60


@pytest.mark.asyncio
async def test_candidates_are_registered_under_the_tuned_config_not_the_bare_defaults(
    test_db_engine, canned_prices, monkeypatch
):
    from app.models.forward_validation import ForwardValidationRegistration

    _patch_provider(monkeypatch, canned_prices)
    runner = runner_module.AutonomousResearchRunner()
    system_user_id = runner._ensure_system_user()

    with _session_local(test_db_engine)() as db:
        job = _create_completed_job(db, system_user_id, MOMENTUM_STRATEGY_NAME, ["AAPL"])
        job_id = job.id

    runner._trigger_top_candidate_backtests(job_id, MOMENTUM_STRATEGY_NAME, system_user_id)

    grid = autonomous_tuning.build_tuning_grid(MOMENTUM_STRATEGY_NAME)
    with _session_local(test_db_engine)() as db:
        reg = db.execute(select(ForwardValidationRegistration)).scalars().one()
        chosen = autonomous_tuning.StrategyConfig(
            fit_window_days=reg.fit_window_days,
            entry_z=reg.entry_z,
            exit_z=reg.exit_z,
            cost_bps=reg.cost_bps,
        )
        # The registered config must be one the tuner actually evaluated...
        assert chosen in grid
        # ...and the backtest stored for this candidate must use that same
        # config, so the historical backtest and its ongoing forward tracking
        # stay directly comparable.
        matching = db.execute(
            select(ExperimentRun).where(
                ExperimentRun.ticker_a == "AAPL",
                ExperimentRun.fit_window_days == chosen.fit_window_days,
                ExperimentRun.entry_z == chosen.entry_z,
            )
        ).scalars().all()
        assert len(matching) == 1


@pytest.mark.asyncio
async def test_tuned_config_is_stable_across_ticks_so_progress_never_resets(
    test_db_engine, canned_prices, monkeypatch
):
    """The reuse-first rule: a candidate that reappears in the top-K on a
    later day keeps its original registration (and therefore keeps counting
    toward MIN_FORWARD_VALIDATION_TRADING_DAYS) instead of being re-tuned
    into a brand-new day-0 registration."""
    from app.models.forward_validation import ForwardValidationRegistration

    _patch_provider(monkeypatch, canned_prices)
    runner = runner_module.AutonomousResearchRunner()
    system_user_id = runner._ensure_system_user()

    with _session_local(test_db_engine)() as db:
        first_job = _create_completed_job(db, system_user_id, MOMENTUM_STRATEGY_NAME, ["AAPL"])
        first_job_id = first_job.id

    runner._trigger_top_candidate_backtests(first_job_id, MOMENTUM_STRATEGY_NAME, system_user_id)

    with _session_local(test_db_engine)() as db:
        reg = db.execute(select(ForwardValidationRegistration)).scalars().one()
        first_config = (reg.id, reg.fit_window_days, reg.entry_z, reg.exit_z, reg.cost_bps)
        runs_after_first = len(db.execute(select(ExperimentRun)).scalars().all())
        # Simulate a day's forward-validation progress accumulating.
        reg.n_forward_trading_days = 37
        db.commit()

        second_job = _create_completed_job(db, system_user_id, MOMENTUM_STRATEGY_NAME, ["AAPL"])
        second_job_id = second_job.id

    runner._trigger_top_candidate_backtests(second_job_id, MOMENTUM_STRATEGY_NAME, system_user_id)

    with _session_local(test_db_engine)() as db:
        regs = db.execute(select(ForwardValidationRegistration)).scalars().all()
        assert len(regs) == 1  # no second, competing registration
        assert (
            regs[0].id,
            regs[0].fit_window_days,
            regs[0].entry_z,
            regs[0].exit_z,
            regs[0].cost_bps,
        ) == first_config
        assert regs[0].n_forward_trading_days == 37  # progress untouched

        # And the tuning grid did not run a second time — the reuse path only
        # re-runs the one already-cached backtest for the reused config.
        assert len(db.execute(select(ExperimentRun)).scalars().all()) == runs_after_first


@pytest.mark.asyncio
async def test_fresh_tuning_budget_is_capped_per_job(test_db_engine, canned_prices, monkeypatch):
    _patch_provider(monkeypatch, canned_prices)
    monkeypatch.setattr(autonomous_tuning, "MAX_NEW_TUNINGS_PER_JOB", 1)

    runner = runner_module.AutonomousResearchRunner()
    system_user_id = runner._ensure_system_user()

    with _session_local(test_db_engine)() as db:
        job = _create_completed_job(db, system_user_id, MOMENTUM_STRATEGY_NAME, ["AAPL", "MSFT", "GLD"])
        job_id = job.id

    runner._trigger_top_candidate_backtests(job_id, MOMENTUM_STRATEGY_NAME, system_user_id)

    grid_size = len(autonomous_tuning.build_tuning_grid(MOMENTUM_STRATEGY_NAME))
    with _session_local(test_db_engine)() as db:
        runs = db.execute(select(ExperimentRun)).scalars().all()
        per_ticker = {t: len([r for r in runs if r.ticker_a == t]) for t in ("AAPL", "MSFT", "GLD")}

    # Exactly one candidate spent the budget and got the full grid; the other
    # two fell back to a single default-config backtest each, and get their
    # own turn on a later day.
    assert sorted(per_ticker.values()) == [1, 1, grid_size]
    assert per_ticker["AAPL"] == grid_size  # best-ranked candidate goes first


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


@pytest.mark.asyncio
async def test_registration_failure_never_costs_a_candidate_its_backtest_or_its_siblings(
    test_db_engine, canned_prices, monkeypatch
):
    """Backtest and registration sit in two independent try/excepts, not one
    nested pair. A registration that blows up must still leave that
    candidate's backtest stored, must not stop sibling candidates from
    getting BOTH, and must not leave the job un-flagged for retry forever."""
    from app.models.forward_validation import ForwardValidationRegistration

    _patch_provider(monkeypatch, canned_prices)
    runner = runner_module.AutonomousResearchRunner()
    system_user_id = runner._ensure_system_user()

    real_register = runner_module.register_or_get_forward_validation

    def flaky_register(db, **kwargs):
        if kwargs["ticker_a"] == "AAPL":
            raise RuntimeError("simulated registration failure for AAPL")
        return real_register(db, **kwargs)

    monkeypatch.setattr(runner_module, "register_or_get_forward_validation", flaky_register)

    with _session_local(test_db_engine)() as db:
        job = _create_completed_job(db, system_user_id, MOMENTUM_STRATEGY_NAME, ["AAPL", "MSFT"])
        job_id = job.id

    runner._trigger_top_candidate_backtests(job_id, MOMENTUM_STRATEGY_NAME, system_user_id)

    with _session_local(test_db_engine)() as db:
        backtested = {
            r.ticker_a
            for r in db.execute(
                select(ExperimentRun).where(ExperimentRun.strategy_name == MOMENTUM_STRATEGY_NAME)
            )
            .scalars()
            .all()
        }
        registered = {
            r.ticker_a for r in db.execute(select(ForwardValidationRegistration)).scalars().all()
        }
        assert db.get(ScreeningJob, job_id).auto_backtests_triggered is True

    # AAPL's registration raised, but the backtest that already ran survives...
    assert "AAPL" in backtested
    assert "AAPL" not in registered
    # ...and its sibling is entirely unaffected, getting both actions.
    assert "MSFT" in backtested
    assert "MSFT" in registered
