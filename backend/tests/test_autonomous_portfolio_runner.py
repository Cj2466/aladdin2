import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app import dependencies
from app.models.experiment_run import ExperimentRun
from app.models.forward_validation import ForwardValidationRegistration
from app.models.price_bar import PriceBar
from app.models.strategy_portfolio import StrategyPortfolio
from app.services.forward_validation_service import compute_forward_validation_config_hash
from app.services.research_lab import autonomous_portfolio_runner as runner_module
from app.services.research_lab.autonomous_portfolio_runner import (
    MIN_STRATEGIES_FOR_AUTONOMOUS_PORTFOLIO,
    SYSTEM_PORTFOLIO_NAME,
    AutonomousPortfolioRunner,
)
from app.services.research_lab.backtest_result import run_and_store_momentum_backtest

# One more than the gate, so a test can drop a single member and still be
# above MIN_STRATEGIES_FOR_AUTONOMOUS_PORTFOLIO.
TICKERS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]

FIT_WINDOW_DAYS = 90
ENTRY_Z = 2.0
EXIT_Z = 0.0
COST_BPS = 5.0
STRATEGY = "momentum_v1"


@pytest.fixture(autouse=True)
def patch_runner_session(test_db_engine, monkeypatch):
    """AutonomousPortfolioRunner opens its own SessionLocal (it's not a
    FastAPI route, so the get_db override doesn't reach it) — point it at
    the per-test SQLite engine, mirroring test_forward_validation.py's
    patch_runner_session exactly."""
    testing_session_local = sessionmaker(bind=test_db_engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(runner_module, "SessionLocal", testing_session_local)


def _trending_frame(n_days: int = 700, shift: int = 0) -> pd.DataFrame:
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n_days)
    data = {}
    for i, ticker in enumerate(TICKERS):
        rng = np.random.default_rng(500 + i + shift * 37)
        drift = 0.0018 - 0.00035 * i
        log_price = np.cumsum(rng.normal(drift, 0.004 + 0.0008 * i, n_days))
        data[ticker] = 100.0 * np.exp(log_price)
    return pd.DataFrame(data, index=dates)


def _patch_provider(monkeypatch, frame: pd.DataFrame) -> None:
    def fake_get_price_history(tickers, start, end):
        present = [t for t in tickers if t in frame.columns]
        return frame[present], [t for t in tickers if t not in frame.columns]

    monkeypatch.setattr(dependencies.provider, "get_price_history", fake_get_price_history)


def _seed_runs(db, tickers: list[str]) -> None:
    for ticker in tickers:
        response = run_and_store_momentum_backtest(
            db,
            dependencies.provider,
            ticker=ticker,
            fit_window_days=FIT_WINDOW_DAYS,
            entry_z=ENTRY_Z,
            exit_z=EXIT_Z,
            cost_bps=COST_BPS,
            lookback_years=2,
        )
        assert response.status == "ok", f"{ticker}: {response.status}"


def _seed_registration(db, user_id: int, ticker: str, status: str) -> ForwardValidationRegistration:
    registration = ForwardValidationRegistration(
        user_id=user_id,
        strategy_name=STRATEGY,
        ticker_a=ticker,
        ticker_b=ticker,
        fit_window_days=FIT_WINDOW_DAYS,
        entry_z=ENTRY_Z,
        exit_z=EXIT_Z,
        cost_bps=COST_BPS,
        config_hash=compute_forward_validation_config_hash(
            STRATEGY, ticker, ticker, FIT_WINDOW_DAYS, ENTRY_Z, EXIT_Z, COST_BPS
        ),
        status=status,
        min_trading_days_threshold=126,
        n_forward_trading_days=130,
        started_at=date.today(),
        carry_state_json="{}",
        day_results_json="[]",
        trades_json="[]",
    )
    db.add(registration)
    db.commit()
    db.refresh(registration)
    return registration


@pytest.fixture
def graduated_world(test_db_engine, monkeypatch):
    """Real ExperimentRun rows for every ticker, plus a system user, with
    each ticker's registration status decided by the caller."""
    _patch_provider(monkeypatch, _trending_frame())
    runner = AutonomousPortfolioRunner()
    system_user_id = runner._ensure_system_user()

    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        _seed_runs(db, TICKERS)

    def _register(statuses: dict[str, str]) -> None:
        with session_local() as db:
            for ticker, status in statuses.items():
                _seed_registration(db, system_user_id, ticker, status)

    return runner, system_user_id, session_local, _register


def _load_portfolio(session_local, system_user_id) -> StrategyPortfolio | None:
    with session_local() as db:
        return db.execute(
            select(StrategyPortfolio).where(
                StrategyPortfolio.user_id == system_user_id,
                StrategyPortfolio.name == SYSTEM_PORTFOLIO_NAME,
            )
        ).scalar_one_or_none()


def _allocation_tickers(session_local, portfolio_id: int) -> set[str]:
    with session_local() as db:
        portfolio = db.get(StrategyPortfolio, portfolio_id)
        run_ids = [a.experiment_run_id for a in portfolio.allocations]
        runs = db.execute(select(ExperimentRun).where(ExperimentRun.id.in_(run_ids))).scalars().all()
    return {r.ticker_a for r in runs}


# --- minimum-count gate ------------------------------------------------------


@pytest.mark.asyncio
async def test_no_portfolio_is_built_below_the_minimum_strategy_count(graduated_world, test_db_engine):
    runner, system_user_id, session_local, register = graduated_world
    register({t: "forward_validated" for t in TICKERS[: MIN_STRATEGIES_FOR_AUTONOMOUS_PORTFOLIO - 1]})

    await runner._tick()

    assert _load_portfolio(session_local, system_user_id) is None


@pytest.mark.asyncio
async def test_portfolio_is_built_once_the_minimum_is_reached(graduated_world):
    runner, system_user_id, session_local, register = graduated_world
    register({t: "forward_validated" for t in TICKERS[:MIN_STRATEGIES_FOR_AUTONOMOUS_PORTFOLIO]})

    await runner._tick()

    portfolio = _load_portfolio(session_local, system_user_id)
    assert portfolio is not None
    with session_local() as db:
        refreshed = db.get(StrategyPortfolio, portfolio.id)
        weights = [a.weight for a in refreshed.allocations]
    assert len(weights) == MIN_STRATEGIES_FOR_AUTONOMOUS_PORTFOLIO
    assert sum(weights) == pytest.approx(1.0, abs=1e-3)
    assert all(w <= 0.4 + 1e-6 for w in weights)


# --- auto-inclusion of newly-graduated registrations --------------------------


@pytest.mark.asyncio
async def test_in_progress_registrations_are_not_included(graduated_world):
    runner, system_user_id, session_local, register = graduated_world
    statuses = {t: "forward_validated" for t in TICKERS[:MIN_STRATEGIES_FOR_AUTONOMOUS_PORTFOLIO]}
    statuses[TICKERS[MIN_STRATEGIES_FOR_AUTONOMOUS_PORTFOLIO]] = "in_progress"
    register(statuses)

    await runner._tick()

    portfolio = _load_portfolio(session_local, system_user_id)
    assert _allocation_tickers(session_local, portfolio.id) == set(
        TICKERS[:MIN_STRATEGIES_FOR_AUTONOMOUS_PORTFOLIO]
    )


@pytest.mark.asyncio
async def test_a_newly_graduated_registration_is_auto_added_on_the_next_tick(
    graduated_world, test_db_engine
):
    runner, system_user_id, session_local, register = graduated_world
    statuses = {t: "forward_validated" for t in TICKERS[:MIN_STRATEGIES_FOR_AUTONOMOUS_PORTFOLIO]}
    late = TICKERS[MIN_STRATEGIES_FOR_AUTONOMOUS_PORTFOLIO]
    statuses[late] = "in_progress"
    register(statuses)

    await runner._tick()
    portfolio = _load_portfolio(session_local, system_user_id)
    assert late not in _allocation_tickers(session_local, portfolio.id)

    # It graduates, exactly as ForwardValidationRunner would flip it.
    with session_local() as db:
        registration = db.execute(
            select(ForwardValidationRegistration).where(
                ForwardValidationRegistration.ticker_a == late
            )
        ).scalar_one()
        registration.status = "forward_validated"
        db.commit()

    await runner._tick()

    assert late in _allocation_tickers(session_local, portfolio.id)
    with session_local() as db:
        assert len(db.get(StrategyPortfolio, portfolio.id).allocations) == (
            MIN_STRATEGIES_FOR_AUTONOMOUS_PORTFOLIO + 1
        )


@pytest.mark.asyncio
async def test_membership_sync_is_idempotent_across_repeated_ticks(graduated_world):
    runner, system_user_id, session_local, register = graduated_world
    register({t: "forward_validated" for t in TICKERS})

    await runner._tick()
    portfolio = _load_portfolio(session_local, system_user_id)
    with session_local() as db:
        first = {
            (a.experiment_run_id, a.weight)
            for a in db.get(StrategyPortfolio, portfolio.id).allocations
        }
        first_optimized_at = db.get(StrategyPortfolio, portfolio.id).last_optimized_at

    await runner._tick()
    await runner._tick()

    with session_local() as db:
        refreshed = db.get(StrategyPortfolio, portfolio.id)
        assert {(a.experiment_run_id, a.weight) for a in refreshed.allocations} == first
        # Once-a-calendar-day guard: no membership change means no re-run.
        assert refreshed.last_optimized_at == first_optimized_at
    # And no duplicate portfolio row was created.
    with session_local() as db:
        assert len(db.execute(select(StrategyPortfolio)).scalars().all()) == 1


# --- underperformance pruning -------------------------------------------------


@pytest.mark.asyncio
async def test_underperforming_member_is_removed_and_survivors_reweighted(graduated_world):
    runner, system_user_id, session_local, register = graduated_world
    register({t: "forward_validated" for t in TICKERS})

    await runner._tick()
    portfolio = _load_portfolio(session_local, system_user_id)
    assert _allocation_tickers(session_local, portfolio.id) == set(TICKERS)

    pruned = TICKERS[0]
    with session_local() as db:
        registration = db.execute(
            select(ForwardValidationRegistration).where(
                ForwardValidationRegistration.ticker_a == pruned
            )
        ).scalar_one()
        # Exactly what ForwardValidationRunner's G1 check does.
        registration.status = "underperforming"
        db.commit()

    await runner._tick()

    remaining = _allocation_tickers(session_local, portfolio.id)
    assert pruned not in remaining
    assert remaining == set(TICKERS[1:])
    with session_local() as db:
        weights = [a.weight for a in db.get(StrategyPortfolio, portfolio.id).allocations]
    assert sum(weights) == pytest.approx(1.0, abs=1e-3)


@pytest.mark.asyncio
async def test_pruning_below_the_minimum_holds_survivors_at_equal_weight(graduated_world):
    runner, system_user_id, session_local, register = graduated_world
    register({t: "forward_validated" for t in TICKERS})
    await runner._tick()
    portfolio = _load_portfolio(session_local, system_user_id)

    # Prune down to one below the gate.
    doomed = TICKERS[: len(TICKERS) - (MIN_STRATEGIES_FOR_AUTONOMOUS_PORTFOLIO - 1)]
    with session_local() as db:
        for ticker in doomed:
            registration = db.execute(
                select(ForwardValidationRegistration).where(
                    ForwardValidationRegistration.ticker_a == ticker
                )
            ).scalar_one()
            registration.status = "underperforming"
        db.commit()

    await runner._tick()

    with session_local() as db:
        allocations = db.get(StrategyPortfolio, portfolio.id).allocations
        weights = [a.weight for a in allocations]
    assert len(weights) == MIN_STRATEGIES_FOR_AUTONOMOUS_PORTFOLIO - 1
    assert sum(weights) == pytest.approx(1.0, abs=1e-6)
    assert all(w == pytest.approx(1.0 / len(weights)) for w in weights)


@pytest.mark.asyncio
async def test_a_pruned_member_never_silently_returns(graduated_world):
    """G1 only ever transitions INTO "underperforming" — so a removed
    strategy can only come back if a human deliberately changes its status,
    not on its own."""
    runner, system_user_id, session_local, register = graduated_world
    register({t: "forward_validated" for t in TICKERS})
    await runner._tick()
    portfolio = _load_portfolio(session_local, system_user_id)

    pruned = TICKERS[0]
    with session_local() as db:
        db.execute(
            select(ForwardValidationRegistration).where(
                ForwardValidationRegistration.ticker_a == pruned
            )
        ).scalar_one().status = "underperforming"
        db.commit()

    for _ in range(3):
        await runner._tick()

    assert pruned not in _allocation_tickers(session_local, portfolio.id)


# --- re-optimization ----------------------------------------------------------


@pytest.mark.asyncio
async def test_reoptimization_updates_stored_weights_on_a_later_day(
    graduated_world, monkeypatch
):
    """Simulates the real daily cycle: yesterday's optimization is on the
    books, AutonomousResearchRunner stores a fresh ExperimentRun per config
    today, and this runner repoints at those and re-derives the weights."""
    runner, system_user_id, session_local, register = graduated_world
    register({t: "forward_validated" for t in TICKERS})

    await runner._tick()
    portfolio = _load_portfolio(session_local, system_user_id)
    with session_local() as db:
        before = {
            a.experiment_run_id: a.weight
            for a in db.get(StrategyPortfolio, portfolio.id).allocations
        }
        # Backdate the guard so today's tick is allowed to re-optimize,
        # exactly as a real overnight gap would.
        db.get(StrategyPortfolio, portfolio.id).last_optimized_at = None
        db.commit()

    # A new day's backtests: same configs, different (fresher) price data —
    # the same thing ExperimentRun's date-folded input_hash produces daily.
    _patch_provider(monkeypatch, _trending_frame(shift=1))
    with session_local() as db:
        # get_price_history_cached would otherwise serve the first frame
        # straight back out of price_bars, making "fresher data" a no-op.
        db.query(PriceBar).delete()
        for run in db.execute(select(ExperimentRun)).scalars().all():
            run.input_hash = f"stale-{run.id}"  # free the unique hash for today's row
        db.commit()
        _seed_runs(db, TICKERS)
        for run in db.execute(select(ExperimentRun)).scalars().all():
            if run.input_hash.startswith("stale-"):
                run.computed_at = run.computed_at - timedelta(days=1)
        db.commit()

    await runner._tick()

    with session_local() as db:
        refreshed = db.get(StrategyPortfolio, portfolio.id)
        after = {a.experiment_run_id: a.weight for a in refreshed.allocations}
        assert refreshed.last_optimized_at is not None

    # Every allocation now points at today's fresher run...
    assert set(after.keys()).isdisjoint(before.keys())
    # ...and the weights are genuinely re-derived, not copied forward.
    assert sorted(after.values()) != sorted(before.values())
    assert sum(after.values()) == pytest.approx(1.0, abs=1e-3)


@pytest.mark.asyncio
async def test_a_graduated_registration_with_no_ok_run_is_skipped_not_fatal(graduated_world):
    runner, system_user_id, session_local, register = graduated_world
    register({t: "forward_validated" for t in TICKERS})

    with session_local() as db:
        run = db.execute(
            select(ExperimentRun).where(ExperimentRun.ticker_a == TICKERS[0])
        ).scalars().one()
        run.status = "not_trending"
        db.commit()

    await runner._tick()

    portfolio = _load_portfolio(session_local, system_user_id)
    assert portfolio is not None
    assert _allocation_tickers(session_local, portfolio.id) == set(TICKERS[1:])


@pytest.mark.asyncio
async def test_other_users_registrations_and_portfolios_are_never_touched(
    graduated_world, register_and_verify, client
):
    runner, system_user_id, session_local, register = graduated_world
    register({t: "forward_validated" for t in TICKERS})

    user = register_and_verify(client, email="sp_runner_outsider@example.com")
    with session_local() as db:
        # A real user's own graduated registration for the same configs...
        for ticker in TICKERS:
            _seed_registration(db, user["id"], ticker, "forward_validated")
        # ...and their own strategy portfolio.
        mine = StrategyPortfolio(user_id=user["id"], name=SYSTEM_PORTFOLIO_NAME)
        db.add(mine)
        db.commit()
        mine_id = mine.id

    await runner._tick()

    with session_local() as db:
        assert db.get(StrategyPortfolio, mine_id).allocations == []
        system = db.execute(
            select(StrategyPortfolio).where(StrategyPortfolio.user_id == system_user_id)
        ).scalar_one()
        assert len(system.allocations) == len(TICKERS)


@pytest.mark.asyncio
async def test_tick_survives_a_failing_optimization(graduated_world, monkeypatch):
    """A broken results_json can't take down the loop, and can't leave the
    portfolio with weights that don't sum to 1."""
    runner, system_user_id, session_local, register = graduated_world
    register({t: "forward_validated" for t in TICKERS})

    with session_local() as db:
        for run in db.execute(select(ExperimentRun)).scalars().all():
            payload = json.loads(run.results_json)
            payload["equity_curve"] = payload["equity_curve"][:3]  # far below MIN_OBS_FOR_ANY_ESTIMATE
            run.results_json = json.dumps(payload)
        db.commit()

    await runner._tick()

    portfolio = _load_portfolio(session_local, system_user_id)
    with session_local() as db:
        allocations = db.get(StrategyPortfolio, portfolio.id).allocations
        weights = [a.weight for a in allocations]
        assert db.get(StrategyPortfolio, portfolio.id).last_optimized_at is None
    assert len(weights) == len(TICKERS)
    assert sum(weights) == pytest.approx(1.0, abs=1e-6)
