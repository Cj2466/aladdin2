import asyncio
from datetime import date

import pytest

from app.config import settings
from app.services.research_lab import membership_refresh_runner as runner_module
from app.services.research_lab.membership_refresh_runner import MembershipRefreshRunner
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_AS_OF,
    MembershipExtension,
    clear_membership_extension,
    membership_coverage_end,
)
from app.services.research_lab.sp500_membership_refresh import RefreshOutcome


@pytest.fixture(autouse=True)
def vendored_only():
    """Same reasoning as test_sp500_membership_refresh.py: the extension is
    process-global, so a test that leaves one applied would change what
    every later test sees."""
    clear_membership_extension()
    yield
    clear_membership_extension()


def _outcome(extension: MembershipExtension | None) -> RefreshOutcome:
    return RefreshOutcome(
        extension=extension,
        warnings=(),
        coverage_end=extension.coverage_end if extension else MEMBERSHIP_DATA_AS_OF,
        n_dated_events=0,
        n_live_dated_additions=0,
        live_as_of=None,
    )


async def _run_n_ticks(runner: MembershipRefreshRunner, monkeypatch, n: int) -> list[float]:
    """Drives the real `run` loop for n ticks by making sleep record its
    interval and then cancel, so the loop's own scheduling — not a
    reimplementation of it — is what gets asserted on."""
    intervals: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        intervals.append(seconds)
        if len(intervals) >= n:
            raise asyncio.CancelledError

    monkeypatch.setattr(runner_module.asyncio, "sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        await runner.run()
    return intervals


async def test_a_successful_tick_applies_the_extension_and_sleeps_the_full_interval(monkeypatch):
    extension = MembershipExtension(
        coverage_end=date(2026, 7, 15),
        events=((date(2026, 7, 15), ("NEWA",), ()),),
    )
    monkeypatch.setattr(runner_module, "refresh_membership_data", lambda: _outcome(extension))

    runner = MembershipRefreshRunner()
    # The runner delegates applying to refresh_membership_data, which is
    # faked here — so assert on scheduling, and let
    # test_sp500_membership_refresh.py own the applying.
    intervals = await _run_n_ticks(runner, monkeypatch, 1)
    assert intervals == [settings.membership_refresh_interval_seconds]


async def test_a_tick_that_applied_nothing_retries_sooner(monkeypatch):
    monkeypatch.setattr(runner_module, "refresh_membership_data", lambda: _outcome(None))

    intervals = await _run_n_ticks(MembershipRefreshRunner(), monkeypatch, 1)
    assert intervals == [settings.membership_refresh_retry_interval_seconds]
    # ...and nothing was cleared: still on the last known-good (here,
    # vendored) data rather than in a broken state.
    assert membership_coverage_end() == MEMBERSHIP_DATA_AS_OF


async def test_an_unexpected_exception_never_stops_the_loop(monkeypatch):
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise RuntimeError("upstream exploded in a way refresh_membership_data did not expect")

    monkeypatch.setattr(runner_module, "refresh_membership_data", boom)

    intervals = await _run_n_ticks(MembershipRefreshRunner(), monkeypatch, 3)
    assert calls["n"] == 3
    assert intervals == [settings.membership_refresh_retry_interval_seconds] * 3
    assert membership_coverage_end() == MEMBERSHIP_DATA_AS_OF


async def test_cancellation_propagates_rather_than_being_swallowed(monkeypatch):
    def cancel():
        raise asyncio.CancelledError

    monkeypatch.setattr(runner_module, "refresh_membership_data", cancel)

    # Shutdown must actually shut down — main.py's lifespan cancels this
    # task and then awaits it.
    with pytest.raises(asyncio.CancelledError):
        await MembershipRefreshRunner().run()
