"""MacroBetaRefreshRunner — staleness gating.

The runner's whole job is deciding WHEN to recompute, so that is what these
tests exercise. run_macro_beta_family itself is faked out: it is covered by
test_macro_beta.py, and calling the real one here would make a live yfinance
and FRED request, which this codebase's conventions forbid in an automated
test.

Mirrors tests/test_membership_refresh_runner.py's technique for driving the
real `run` loop (a fake asyncio.sleep that records its interval and then
cancels), so the loop's own scheduling — not a reimplementation of it — is
what gets asserted on.
"""

import asyncio
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.macro_commodity_beta import MacroCommodityBeta
from app.services.research_lab import macro_beta_refresh_runner as runner_module
from app.services.research_lab.macro_beta import MacroBetaRunSummary

TODAY = date(2026, 9, 1)


@pytest.fixture(autouse=True)
def patch_runner_session(test_db_engine, monkeypatch):
    """MacroBetaRefreshRunner opens its own SessionLocal directly (it is not a
    FastAPI route, so the get_db dependency override does not reach it) —
    point that at the same per-test SQLite engine, mirroring
    test_cross_sectional_forward_validation.py's patch_runner_session."""
    testing_session_local = sessionmaker(bind=test_db_engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(runner_module, "SessionLocal", testing_session_local)


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    """Pin "now" so a test's meaning never depends on the day it runs."""
    class _FrozenClock:
        @staticmethod
        def date():
            return TODAY

    monkeypatch.setattr(runner_module, "utcnow_naive", lambda: _FrozenClock())


@pytest.fixture
def recorded_computes(monkeypatch):
    """Replaces the real family run with a recorder. No network, and the
    call list is what the staleness assertions read."""
    calls: list[date] = []

    def fake_run(db, price_provider, macro_provider, tickers, *, end, **kwargs):
        calls.append(end)
        return MacroBetaRunSummary(
            as_of_date=end,
            window_days=252,
            n_rows=13,
            n_drivers_computed=13,
            rows_per_driver={},
            failed_drivers={},
            missing_tickers=[],
        )

    monkeypatch.setattr(runner_module, "run_macro_beta_family", fake_run)
    return calls


def _seed_generation(test_db_engine, as_of: date) -> None:
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        db.add(
            MacroCommodityBeta(
                driver="oil_uso",
                ticker="XOM",
                as_of_date=as_of,
                window_days=252,
                beta_full_sample=0.5,
                beta_shock_days=0.6,
                correlation_full_sample=0.4,
                n_observations_full_sample=252,
                n_observations_shock_days=25,
                t_stat_full_sample=3.1,
                sign_agreement=0.6,
            )
        )
        db.commit()


# --- the three staleness cases the design turns on ---------------------------


def test_an_empty_table_is_stale_and_does_get_recomputed(recorded_computes):
    """THE failure mode this gate most easily gets wrong. A fresh deploy has
    never computed anything; a staleness check that read "no rows" as
    "nothing to do" would leave the table empty forever, ticking daily and
    doing nothing. Empty must mean STALE."""
    outcome = runner_module.MacroBetaRefreshRunner()._tick()

    assert outcome.recomputed is True
    assert "empty" in outcome.reason
    assert recorded_computes == [TODAY]


def test_a_table_refreshed_yesterday_is_skipped(test_db_engine, recorded_computes):
    _seed_generation(test_db_engine, TODAY - timedelta(days=1))

    outcome = runner_module.MacroBetaRefreshRunner()._tick()

    assert outcome.recomputed is False
    assert "1d old" in outcome.reason
    assert recorded_computes == []


def test_a_table_refreshed_eight_days_ago_is_recomputed(test_db_engine, recorded_computes):
    _seed_generation(test_db_engine, TODAY - timedelta(days=8))

    outcome = runner_module.MacroBetaRefreshRunner()._tick()

    assert outcome.recomputed is True
    assert "8d old" in outcome.reason
    assert recorded_computes == [TODAY]


# --- the exact boundary ------------------------------------------------------


def test_exactly_at_the_staleness_bar_recomputes_but_one_day_short_does_not(
    test_db_engine, recorded_computes, monkeypatch
):
    """The bar is `age >= stale_after_days`, so 7 days recomputes and 6 does
    not. Pinned because an off-by-one here is invisible in production: it
    just silently shifts the refresh cadence by a day."""
    bar = settings.macro_beta_recompute_stale_after_days
    assert bar == 7

    _seed_generation(test_db_engine, TODAY - timedelta(days=bar - 1))
    assert runner_module.MacroBetaRefreshRunner()._tick().recomputed is False

    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        db.query(MacroCommodityBeta).delete()
        db.commit()

    _seed_generation(test_db_engine, TODAY - timedelta(days=bar))
    assert runner_module.MacroBetaRefreshRunner()._tick().recomputed is True


def test_the_newest_generation_decides_staleness_not_the_oldest(
    test_db_engine, recorded_computes
):
    """The table is append-only and accumulates generations. A stale OLD
    generation must not force a recompute when a fresh one already exists."""
    _seed_generation(test_db_engine, TODAY - timedelta(days=400))
    _seed_generation(test_db_engine, TODAY - timedelta(days=2))

    outcome = runner_module.MacroBetaRefreshRunner()._tick()

    assert outcome.recomputed is False
    assert recorded_computes == []


# --- the loop itself ---------------------------------------------------------


async def _run_n_ticks(runner, monkeypatch, n: int) -> list[float]:
    intervals: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        intervals.append(seconds)
        if len(intervals) >= n:
            raise asyncio.CancelledError

    monkeypatch.setattr(runner_module.asyncio, "sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        await runner.run()
    return intervals


async def test_the_loop_sleeps_the_configured_interval_between_ticks(
    monkeypatch, recorded_computes
):
    intervals = await _run_n_ticks(runner_module.MacroBetaRefreshRunner(), monkeypatch, 3)
    assert intervals == [settings.macro_beta_refresh_interval_seconds] * 3
    assert settings.macro_beta_refresh_interval_seconds == 86400


async def test_a_failing_tick_is_logged_and_the_loop_keeps_going(monkeypatch):
    """A transient yfinance or FRED outage must cost one cycle's freshness,
    never the runner itself. If this loop died, the table would silently stop
    refreshing until the next deploy."""
    def boom(*args, **kwargs):
        raise RuntimeError("yfinance is down")

    monkeypatch.setattr(runner_module, "run_macro_beta_family", boom)

    intervals = await _run_n_ticks(runner_module.MacroBetaRefreshRunner(), monkeypatch, 2)

    assert intervals == [settings.macro_beta_refresh_interval_seconds] * 2


async def test_cancellation_propagates_rather_than_being_swallowed(monkeypatch):
    """main.py's shutdown cancels this task and awaits it. A runner that
    caught CancelledError in its broad except would hang shutdown."""
    runner = runner_module.MacroBetaRefreshRunner()

    def cancel(*args, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(runner_module, "run_macro_beta_family", cancel)

    with pytest.raises(asyncio.CancelledError):
        await runner.run()
