import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app import dependencies
from app.config import (
    OPTIMIZATION_METHOD_HRP,
    OPTIMIZATION_METHOD_MEAN_VARIANCE,
    Settings,
    settings,
)
from app.models.experiment_run import ExperimentRun
from app.models.forward_validation import ForwardValidationRegistration
from app.models.price_bar import PriceBar
from app.models.strategy_portfolio import StrategyPortfolio
from app.services.forward_validation_service import compute_forward_validation_config_hash
from app.services.research_lab import autonomous_portfolio_runner as runner_module
from app.services.research_lab import strategy_portfolio_returns as returns_module
from app.services.research_lab.autonomous_portfolio_runner import (
    EQUAL_WEIGHT_FALLBACK_METHOD,
    MIN_STRATEGIES_FOR_AUTONOMOUS_PORTFOLIO,
    SYSTEM_PORTFOLIO_NAME,
    AutonomousPortfolioRunner,
)
from app.services.research_lab.backtest_result import run_and_store_momentum_backtest
from app.services.research_lab.strategy_portfolio_returns import build_returns_frame
from app.services.risk.optimizer import (
    DEFAULT_MAX_WEIGHT,
    compute_portfolio_optimization_from_returns,
)

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
        # ...and the fallback SAYS it was a fallback rather than passing
        # equal weights off as an optimization result.
        assert (
            db.get(StrategyPortfolio, portfolio.id).last_optimization_method
            == EQUAL_WEIGHT_FALLBACK_METHOD
        )
    assert len(weights) == len(TICKERS)
    assert sum(weights) == pytest.approx(1.0, abs=1e-6)


# --- optimizer method selection (the mean-variance / HRP A/B toggle) ----------
#
# Every test below drives the REAL runner over the REAL ExperimentRun rows
# seeded by graduated_world (produced by run_and_store_momentum_backtest, so
# their stored equity curves have exactly the production shape) — the
# dispatch is never faked, only observed.


@pytest.fixture
def spy_optimizers(monkeypatch):
    """Count calls to each optimizer AS SEEN BY THE DISPATCH SITE.

    Patched on strategy_portfolio_returns' own module namespace, which is
    where compute_strategy_portfolio_optimization looks the two functions
    up — patching them on optimizer.py/hrp_optimizer.py instead would miss
    the already-bound from-imports and silently observe nothing."""
    calls = {OPTIMIZATION_METHOD_MEAN_VARIANCE: 0, OPTIMIZATION_METHOD_HRP: 0}

    real_mv = returns_module.compute_portfolio_optimization_from_returns
    real_hrp = returns_module.compute_hrp_portfolio_optimization_from_returns

    def counting_mv(*args, **kwargs):
        calls[OPTIMIZATION_METHOD_MEAN_VARIANCE] += 1
        return real_mv(*args, **kwargs)

    def counting_hrp(*args, **kwargs):
        calls[OPTIMIZATION_METHOD_HRP] += 1
        return real_hrp(*args, **kwargs)

    monkeypatch.setattr(returns_module, "compute_portfolio_optimization_from_returns", counting_mv)
    monkeypatch.setattr(
        returns_module, "compute_hrp_portfolio_optimization_from_returns", counting_hrp
    )
    return calls


@pytest.fixture
def select_method(monkeypatch):
    """Set settings.autonomous_portfolio_optimization_method for one test.
    monkeypatch restores the process-wide Settings singleton afterwards, so
    no test can leak a non-default method into another."""

    def _select(method: str) -> None:
        monkeypatch.setattr(settings, "autonomous_portfolio_optimization_method", method)

    return _select


def _stored_weights(session_local, portfolio_id: int) -> dict[int, float]:
    with session_local() as db:
        return {
            a.experiment_run_id: a.weight
            for a in db.get(StrategyPortfolio, portfolio_id).allocations
        }


def _stored_method(session_local, portfolio_id: int) -> str | None:
    with session_local() as db:
        return db.get(StrategyPortfolio, portfolio_id).last_optimization_method


def test_the_shipped_default_is_mean_variance(graduated_world):
    """Guards the thing the whole toggle promises: an operator who sets
    nothing gets the behaviour the runner has always had."""
    assert (
        Settings().autonomous_portfolio_optimization_method == OPTIMIZATION_METHOD_MEAN_VARIANCE
    )


def test_an_unrecognized_method_is_refused_at_config_load_not_silently_defaulted():
    """A typo'd env var must NOT quietly fall back to mean-variance — that
    would leave an operator believing HRP was running while mean-variance
    weights kept being written, which is exactly the confusion the
    last_optimization_method column exists to prevent."""
    with pytest.raises(ValidationError) as excinfo:
        Settings(autonomous_portfolio_optimization_method="hierarchical_risk_parity")
    assert "unknown optimization method" in str(excinfo.value)
    # ...but a differently-cased/padded real value is accepted, normalized.
    assert (
        Settings(autonomous_portfolio_optimization_method="  HRP ").autonomous_portfolio_optimization_method
        == OPTIMIZATION_METHOD_HRP
    )


@pytest.mark.asyncio
async def test_the_default_tick_dispatches_to_mean_variance_and_never_touches_hrp(
    graduated_world, spy_optimizers
):
    runner, system_user_id, session_local, register = graduated_world
    register({t: "forward_validated" for t in TICKERS})

    await runner._tick()

    assert spy_optimizers[OPTIMIZATION_METHOD_MEAN_VARIANCE] == 1
    assert spy_optimizers[OPTIMIZATION_METHOD_HRP] == 0
    portfolio = _load_portfolio(session_local, system_user_id)
    assert _stored_method(session_local, portfolio.id) == OPTIMIZATION_METHOD_MEAN_VARIANCE


@pytest.mark.asyncio
async def test_selecting_hrp_dispatches_to_hrp_and_never_touches_mean_variance(
    graduated_world, spy_optimizers, select_method
):
    runner, system_user_id, session_local, register = graduated_world
    select_method(OPTIMIZATION_METHOD_HRP)
    register({t: "forward_validated" for t in TICKERS})

    await runner._tick()

    assert spy_optimizers[OPTIMIZATION_METHOD_HRP] == 1
    assert spy_optimizers[OPTIMIZATION_METHOD_MEAN_VARIANCE] == 0
    portfolio = _load_portfolio(session_local, system_user_id)
    assert _stored_method(session_local, portfolio.id) == OPTIMIZATION_METHOD_HRP


@pytest.mark.asyncio
async def test_hrp_produces_valid_weights_on_the_runners_real_strategy_set(
    graduated_world, select_method
):
    runner, system_user_id, session_local, register = graduated_world
    select_method(OPTIMIZATION_METHOD_HRP)
    register({t: "forward_validated" for t in TICKERS})

    await runner._tick()

    portfolio = _load_portfolio(session_local, system_user_id)
    weights = _stored_weights(session_local, portfolio.id)
    assert len(weights) == len(TICKERS)
    assert all(w >= 0.0 for w in weights.values())
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-3)
    # Every member is funded: HRP's recursive bisection multiplies each
    # asset's weight by alphas in (0, 1), so nothing is ever driven to
    # exactly zero the way the capped max-Sharpe solution drives most
    # members to zero.
    assert all(w > 0.0 for w in weights.values())
    # No weight sits pinned AT DEFAULT_MAX_WEIGHT, the characteristic
    # fingerprint of the capped mean-variance solution — so a future
    # accidental capping of the HRP path would show up here.
    assert not any(w == pytest.approx(DEFAULT_MAX_WEIGHT) for w in weights.values())
    with session_local() as db:
        assert db.get(StrategyPortfolio, portfolio.id).last_optimized_at is not None


@pytest.mark.asyncio
async def test_the_two_methods_produce_genuinely_different_allocations(
    graduated_world, select_method
):
    """The toggle must actually change the portfolio, or "selectable A/B"
    would be a claim with nothing behind it. Also pins the real shape of the
    difference on this fixture's data: the capped mean-variance path funds
    only a few members (at the 0.4 cap it CAN'T fund more than 3
    meaningfully), while HRP funds every one of them."""
    runner, system_user_id, session_local, register = graduated_world
    register({t: "forward_validated" for t in TICKERS})

    await runner._tick()
    portfolio = _load_portfolio(session_local, system_user_id)
    mean_variance_weights = _stored_weights(session_local, portfolio.id)

    # Clear the once-a-day guard and re-run the same members under HRP.
    with session_local() as db:
        db.get(StrategyPortfolio, portfolio.id).last_optimized_at = None
        db.commit()
    select_method(OPTIMIZATION_METHOD_HRP)
    await runner._tick()
    hrp_weights = _stored_weights(session_local, portfolio.id)

    assert set(hrp_weights) == set(mean_variance_weights)  # same members...
    assert hrp_weights != mean_variance_weights  # ...different allocation
    assert sum(hrp_weights.values()) == pytest.approx(1.0, abs=1e-3)

    mv_funded = sum(1 for w in mean_variance_weights.values() if w > 1e-9)
    hrp_funded = sum(1 for w in hrp_weights.values() if w > 1e-9)
    assert mv_funded < len(TICKERS), "capped mean-variance should zero out some members here"
    assert hrp_funded == len(TICKERS), "HRP allocates to every member"
    assert max(mean_variance_weights.values()) <= DEFAULT_MAX_WEIGHT + 1e-6


@pytest.mark.asyncio
async def test_the_default_path_still_writes_exactly_the_untouched_optimizers_weights(
    graduated_world
):
    """The real regression check: with HRP not selected, the weights on the
    books must be bit-for-bit what optimizer.py's SLSQP max-Sharpe returns
    for this member set at DEFAULT_MAX_WEIGHT — recomputed here directly
    from the untouched function, NOT from the dispatch under test. If the
    method parameter ever leaked into the default path (a changed cap, a
    different frame, a different `current` normalization), this fails."""
    runner, system_user_id, session_local, register = graduated_world
    register({t: "forward_validated" for t in TICKERS})

    await runner._tick()

    portfolio = _load_portfolio(session_local, system_user_id)
    stored = _stored_weights(session_local, portfolio.id)

    with session_local() as db:
        frame, _runs = build_returns_frame(db, sorted(stored))
        # The runner feeds the optimizer the stored weights normalized to
        # sum to 1; on a freshly-built portfolio those are the provisional
        # 1/n written by _sync_membership.
        n = len(stored)
        expected = compute_portfolio_optimization_from_returns(
            frame,
            {str(run_id): 1.0 / n for run_id in sorted(stored)},
            settings.risk_free_rate,
            as_of=str(frame.index.max().date()),
            max_weight=DEFAULT_MAX_WEIGHT,
            insufficient_history_label="selected strategies",
        ).optimized_weights

    assert stored == {int(k): v for k, v in expected.items()}
    assert _stored_method(session_local, portfolio.id) == OPTIMIZATION_METHOD_MEAN_VARIANCE


@pytest.mark.asyncio
async def test_hrp_failing_still_falls_back_to_equal_weight_and_says_so(
    graduated_world, select_method, monkeypatch
):
    """HRP REFUSES a degenerate covariance matrix (a member whose stored
    equity curve never moved) rather than patching it. That refusal must
    behave exactly like the mean-variance path's: equal weight, recorded as
    a fallback, tick survives — not an unhandled ValueError that costs the
    whole tick including its membership sync.

    Not hypothetical: measured against the project's real dev DB, 1 of 230
    distinct stored configs has an exactly-flat return series over its full
    window, and flat-over-a-sub-window is far more common than that."""
    runner, system_user_id, session_local, register = graduated_world
    select_method(OPTIMIZATION_METHOD_HRP)
    register({t: "forward_validated" for t in TICKERS})

    with session_local() as db:
        run = db.execute(
            select(ExperimentRun).where(ExperimentRun.ticker_a == TICKERS[0])
        ).scalars().one()
        payload = json.loads(run.results_json)
        # A strategy that never traded: the equity curve is a flat line, so
        # its return series has exactly zero variance.
        for point in payload["equity_curve"]:
            point["equity"] = 1.0
        run.results_json = json.dumps(payload)
        db.commit()

    await runner._tick()  # must not raise

    portfolio = _load_portfolio(session_local, system_user_id)
    weights = _stored_weights(session_local, portfolio.id)
    assert len(weights) == len(TICKERS)
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)
    assert all(w == pytest.approx(1.0 / len(TICKERS)) for w in weights.values())
    assert _stored_method(session_local, portfolio.id) == EQUAL_WEIGHT_FALLBACK_METHOD
    with session_local() as db:
        assert db.get(StrategyPortfolio, portfolio.id).last_optimized_at is None
