"""THE MISSED-TRADING-DAY BUG, AND ITS TWO FIXES.

The bug: ForwardValidationRunner used to process only raw_data.iloc[-1] —
the single newest row — and then set last_processed_date to it. Every real
trading day in between (a sleeping free-tier host, a transient price-fetch
failure, a deploy restart) was permanently skipped: never counted toward
MIN_FORWARD_VALIDATION_TRADING_DAYS, never logged, never retried.

These tests pin both halves of the fix, and the property that matters more
than either: a catch-up over N missed days must be INDISTINGUISHABLE from N
separate ticks that each caught one day. Two independent ground truths are
used for that, deliberately —

  * an equal-by-construction one: the same registration ticked day by day
    versus ticked once over a gap, compared field by field on the persisted
    row, including the serialized carry state;
  * an external one: a single batch run_walk_forward over the same rows,
    which is the arithmetic the whole research lab is defined by.

The single-day path is re-pinned against both as a real regression check —
the fix must change how MANY days a tick applies, never what a day computes.
"""

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from sqlalchemy.orm import sessionmaker

from app import dependencies
from app.models.forward_validation import ForwardValidationRegistration
from app.services.forward_validation_service import (
    UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS,
)
from app.services.research_lab import forward_validation_backfill as backfill_module
from app.services.research_lab import forward_validation_runner as runner_module
from app.services.research_lab.engine import (
    MAX_CATCHUP_ROWS_PER_TICK,
    WalkForwardConfig,
    WalkForwardState,
    rows_to_process,
    run_walk_forward,
    serialize_walk_forward_state,
    step_one_day,
)
from app.services.research_lab.ou_pairs import (
    build_pairs_raw_data,
    fit_ou_pairs_window,
    realize_pairs_return,
)

FIT_WINDOW_DAYS = 100
ENTRY_Z = 2.0
EXIT_Z = 0.0
COST_BPS = 10.0
# High enough that graduation never fires inside these scenarios, so each
# test exercises exactly the transition it is about.
NO_GRADUATION = 10_000

# Fields whose value is a wall-clock stamp of when a milestone was RECORDED
# rather than which day it happened on. A replay cannot reconstruct them —
# the wall clock for a missed day has passed — and they are the only
# documented exception to the byte-for-byte equivalence below.
WALL_CLOCK_FIELDS = ("last_ticked_at", "graduated_at")

PERSISTED_FIELDS = (
    "status",
    "n_forward_trading_days",
    "last_processed_date",
    "carry_state_json",
    "day_results_json",
    "trades_json",
)


@pytest.fixture(autouse=True)
def patch_sessions(test_db_engine, monkeypatch):
    """Both the runner and the one-time backfill open their own
    SessionLocal directly (neither is a FastAPI route), so both are pointed
    at the same per-test SQLite engine — mirroring test_forward_validation's
    patch_runner_session exactly."""
    testing_session_local = sessionmaker(bind=test_db_engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(runner_module, "SessionLocal", testing_session_local)
    monkeypatch.setattr(backfill_module, "SessionLocal", testing_session_local)


def _synthetic_ou_frame(n: int, seed: int = 123) -> pd.DataFrame:
    """Byte-identical construction to test_forward_validation.py's own
    fixture, so these tests exercise the same numbers that file does. The
    C/D columns are exact copies of A/B: two registrations on identical
    price paths, which is what lets one be ticked day by day and the other
    over a gap and their results compared directly."""
    rng = np.random.default_rng(seed)
    log_a = np.cumsum(rng.normal(0, 0.01, n))
    spread = np.empty(n)
    spread[0] = 0.2
    for t in range(1, n):
        spread[t] = spread[t - 1] + 0.05 * (0.2 - spread[t - 1]) + 0.01 * rng.normal()
    log_b = 1.5 * log_a + spread
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    a, b = 100 * np.exp(log_a), 100 * np.exp(log_b)
    return pd.DataFrame({"A": a, "B": b, "C": a, "D": b}, index=dates)


def _make_prices_fn(frame: pd.DataFrame, cursors: dict):
    """One fake provider serving two independent "how much history exists
    right now" cursors, keyed by which pair is being asked for."""

    def fake_get_price_history(tickers, start, end):
        key = "never" if "A" in tickers else "gap"
        current = frame.iloc[: cursors[key]]
        present = [t for t in tickers if t in current.columns]
        missing = [t for t in tickers if t not in current.columns]
        return current[present], missing

    return fake_get_price_history


def _create_registration(
    db,
    user_id: int,
    *,
    ticker_a: str = "A",
    ticker_b: str = "B",
    config_hash: str = "gap-test",
    min_trading_days_threshold: int = NO_GRADUATION,
) -> int:
    registration = ForwardValidationRegistration(
        user_id=user_id,
        strategy_name="ou_pairs_v1",
        ticker_a=ticker_a,
        ticker_b=ticker_b,
        fit_window_days=FIT_WINDOW_DAYS,
        entry_z=ENTRY_Z,
        exit_z=EXIT_Z,
        cost_bps=COST_BPS,
        config_hash=config_hash,
        status="in_progress",
        min_trading_days_threshold=min_trading_days_threshold,
        n_forward_trading_days=0,
        started_at=date(2020, 1, 1),
        carry_state_json=json.dumps(serialize_walk_forward_state(WalkForwardState())),
        day_results_json="[]",
        trades_json="[]",
    )
    db.add(registration)
    db.commit()
    db.refresh(registration)
    return registration.id


def _config() -> WalkForwardConfig:
    return WalkForwardConfig(
        fit_window_days=FIT_WINDOW_DAYS, entry_z=ENTRY_Z, exit_z=EXIT_Z, cost_bps=COST_BPS
    )


def _batch_reference(frame: pd.DataFrame, n_rows: int, ticker_a: str = "A", ticker_b: str = "B"):
    """The external ground truth: one batch walk-forward over the same rows."""
    raw_data = build_pairs_raw_data(frame.iloc[:n_rows], ticker_a, ticker_b)
    return run_walk_forward(raw_data, _config(), fit_ou_pairs_window, realize_pairs_return)


def _assert_matches_batch(registration, batch) -> None:
    simulated = json.loads(registration.day_results_json)
    assert len(simulated) == len(batch.day_results)
    for sim, ref in zip(simulated, batch.day_results, strict=True):
        assert sim["date"] == ref.date.strftime("%Y-%m-%d")
        assert sim["position"] == ref.position
        assert sim["z_score"] == pytest.approx(ref.z_score)
        assert sim["raw_return"] == pytest.approx(ref.raw_return)
        assert sim["cost"] == pytest.approx(ref.cost)
        assert sim["net_return"] == pytest.approx(ref.net_return)
        assert sim["equity"] == pytest.approx(ref.equity)
    assert registration.n_forward_trading_days == len(batch.day_results)


# =========================================================================
# PART 1 — the tick itself backfills within-tick.
# =========================================================================


@pytest.mark.asyncio
async def test_multi_day_gap_is_recovered_within_one_tick(test_db_engine, register_and_verify, client, monkeypatch):
    """THE BUG, DIRECTLY. Five trading days pass with the process down; the
    next tick must land on all five, not just the newest.

    Before the fix this recorded 2 days and jumped last_processed_date over
    a week of real trading — four days permanently gone from the 126-day
    clock."""
    frame = _synthetic_ou_frame(FIT_WINDOW_DAYS + 30)
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration_id = _create_registration(db, user["id"])

    cursors = {"never": FIT_WINDOW_DAYS + 2, "gap": FIT_WINDOW_DAYS + 2}
    monkeypatch.setattr(dependencies.provider, "get_price_history", _make_prices_fn(frame, cursors))

    runner = runner_module.ForwardValidationRunner()
    await runner._tick()
    with session_local() as db:
        reg = db.get(ForwardValidationRegistration, registration_id)
        assert reg.n_forward_trading_days == 1
        first_date = reg.last_processed_date

    # The process is down for five trading days, then comes back.
    cursors["never"] += 5
    await runner._tick()

    expected_dates = [d.date() for d in frame.index[FIT_WINDOW_DAYS + 1 : FIT_WINDOW_DAYS + 7]]
    with session_local() as db:
        reg = db.get(ForwardValidationRegistration, registration_id)
        assert reg.n_forward_trading_days == 6
        assert reg.last_processed_date == expected_dates[-1]
        assert reg.last_processed_date > first_date
        recorded = [d["date"] for d in json.loads(reg.day_results_json)]
        assert recorded == [d.strftime("%Y-%m-%d") for d in expected_dates]
        # Every recovered day is a real, distinct trading day in order.
        assert recorded == sorted(recorded)
        assert len(set(recorded)) == len(recorded)
        # ...and the whole history equals one batch walk-forward over the
        # same rows — the external ground truth, not just self-consistency.
        _assert_matches_batch(reg, _batch_reference(frame, cursors["never"]))


@pytest.mark.asyncio
async def test_gap_recovery_is_identical_to_never_missing_a_tick(
    test_db_engine, register_and_verify, client, monkeypatch
):
    """The equivalence the whole change rests on, asserted field by field on
    the persisted row: two registrations on the SAME price path, one ticked
    once per day for six days, the other ticked once and then once more
    after a five-day blackout, must end byte-for-byte identical — including
    the serialized carry state, the closed-trade log and every stored
    float."""
    frame = _synthetic_ou_frame(FIT_WINDOW_DAYS + 30)
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        never_id = _create_registration(db, user["id"], ticker_a="A", ticker_b="B", config_hash="never")
        gap_id = _create_registration(db, user["id"], ticker_a="C", ticker_b="D", config_hash="gap")

    cursors = {"never": FIT_WINDOW_DAYS + 2, "gap": FIT_WINDOW_DAYS + 2}
    monkeypatch.setattr(dependencies.provider, "get_price_history", _make_prices_fn(frame, cursors))

    runner = runner_module.ForwardValidationRunner()
    await runner._tick()  # both start on the same day
    for _ in range(5):
        cursors["never"] += 1
        await runner._tick()  # only "never" has a new row; "gap" is a no-op
    with session_local() as db:
        # The scenario is real, not accidentally two identical daily paths:
        # at this point one registration is five days ahead of the other.
        assert db.get(ForwardValidationRegistration, never_id).n_forward_trading_days == 6
        assert db.get(ForwardValidationRegistration, gap_id).n_forward_trading_days == 1

    cursors["gap"] = cursors["never"]
    await runner._tick()  # "gap" catches up all five missed days at once

    with session_local() as db:
        never = db.get(ForwardValidationRegistration, never_id)
        gapped = db.get(ForwardValidationRegistration, gap_id)
        assert never.n_forward_trading_days == 6
        for field in PERSISTED_FIELDS:
            assert getattr(gapped, field) == getattr(never, field), field
        # The exception, stated rather than hidden: wall-clock stamps.
        for field in WALL_CLOCK_FIELDS:
            assert hasattr(gapped, field)


@pytest.mark.asyncio
async def test_single_new_day_per_tick_is_unchanged(test_db_engine, register_and_verify, client, monkeypatch):
    """REGRESSION CHECK. The overwhelmingly common case — exactly one new
    trading day per tick — must behave exactly as it did before the loop
    existed: one day applied, matching a batch walk-forward step for step."""
    frame = _synthetic_ou_frame(FIT_WINDOW_DAYS + 30)
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration_id = _create_registration(db, user["id"])

    cursors = {"never": FIT_WINDOW_DAYS + 1, "gap": FIT_WINDOW_DAYS + 1}
    monkeypatch.setattr(dependencies.provider, "get_price_history", _make_prices_fn(frame, cursors))

    runner = runner_module.ForwardValidationRunner()
    for expected in range(1, 13):
        cursors["never"] += 1
        await runner._tick()
        with session_local() as db:
            reg = db.get(ForwardValidationRegistration, registration_id)
            assert reg.n_forward_trading_days == expected
            assert reg.last_processed_date == frame.index[cursors["never"] - 1].date()

    with session_local() as db:
        _assert_matches_batch(
            db.get(ForwardValidationRegistration, registration_id), _batch_reference(frame, cursors["never"])
        )


@pytest.mark.asyncio
async def test_no_new_trading_day_is_still_a_pure_no_op(test_db_engine, register_and_verify, client, monkeypatch):
    frame = _synthetic_ou_frame(FIT_WINDOW_DAYS + 30)
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration_id = _create_registration(db, user["id"])

    cursors = {"never": FIT_WINDOW_DAYS + 3, "gap": FIT_WINDOW_DAYS + 3}
    monkeypatch.setattr(dependencies.provider, "get_price_history", _make_prices_fn(frame, cursors))

    runner = runner_module.ForwardValidationRunner()
    await runner._tick()
    with session_local() as db:
        before = {f: getattr(db.get(ForwardValidationRegistration, registration_id), f) for f in PERSISTED_FIELDS}

    await runner._tick()
    await runner._tick()
    with session_local() as db:
        reg = db.get(ForwardValidationRegistration, registration_id)
        assert {f: getattr(reg, f) for f in PERSISTED_FIELDS} == before


@pytest.mark.asyncio
async def test_first_ever_tick_never_backfills_history(test_db_engine, register_and_verify, client, monkeypatch):
    """The look-ahead guard. A registration that has never ticked starts
    TODAY — the catch-up loop must not turn a fresh registration into an
    instant "forward" record made of the backward data it was decided on."""
    frame = _synthetic_ou_frame(FIT_WINDOW_DAYS + 30)
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration_id = _create_registration(db, user["id"])

    cursors = {"never": FIT_WINDOW_DAYS + 20, "gap": FIT_WINDOW_DAYS + 20}
    monkeypatch.setattr(dependencies.provider, "get_price_history", _make_prices_fn(frame, cursors))

    runner = runner_module.ForwardValidationRunner()
    await runner._tick()
    with session_local() as db:
        reg = db.get(ForwardValidationRegistration, registration_id)
        assert reg.n_forward_trading_days == 1
        assert reg.last_processed_date == frame.index[cursors["never"] - 1].date()


@pytest.mark.asyncio
async def test_a_mid_gap_underperformance_flag_stops_the_replay(
    test_db_engine, register_and_verify, client, monkeypatch
):
    """A day that flips a registration to "underperforming" must STOP the
    catch-up there. In a never-missed history that registration would not
    have been loaded on the next day's tick, so the remaining missed days
    must not be accumulated either — the status transitions are evaluated
    per DAY, not once per tick."""
    frame = _synthetic_ou_frame(FIT_WINDOW_DAYS + 30)
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration_id = _create_registration(db, user["id"])
        reg = db.get(ForwardValidationRegistration, registration_id)
        # A pre-seeded bad trailing window, exactly as
        # test_forward_validation's own underperformance test does: this
        # makes the check fire on the FIRST recovered day.
        bad_days = [
            {
                "date": "2020-01-01",
                "position": -1,
                "z_score": None,
                "raw_return": -0.01,
                "cost": 0.0,
                "net_return": -0.01,
                "equity": 1.0,
            }
            for _ in range(UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS)
        ]
        reg.day_results_json = json.dumps(bad_days)
        reg.n_forward_trading_days = len(bad_days)
        reg.last_processed_date = frame.index[FIT_WINDOW_DAYS].date()
        db.commit()

    cursors = {"never": FIT_WINDOW_DAYS + 6, "gap": FIT_WINDOW_DAYS + 6}
    monkeypatch.setattr(dependencies.provider, "get_price_history", _make_prices_fn(frame, cursors))

    runner = runner_module.ForwardValidationRunner()
    await runner._tick()

    with session_local() as db:
        reg = db.get(ForwardValidationRegistration, registration_id)
        assert reg.status == "underperforming"
        # Exactly ONE of the five available missed days was applied.
        assert reg.n_forward_trading_days == UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS + 1
        assert reg.last_processed_date == frame.index[FIT_WINDOW_DAYS + 1].date()

    # ...and it stays parked: a later tick must not resume it.
    await runner._tick()
    with session_local() as db:
        reg = db.get(ForwardValidationRegistration, registration_id)
        assert reg.n_forward_trading_days == UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS + 1


def test_rows_to_process_semantics():
    """The row-selection rule itself, as a pure function."""
    index = pd.bdate_range("2026-01-01", periods=200)

    # First ever tick: the newest row ONLY, never history.
    assert rows_to_process(index, None, 100) == [199]

    # Afterwards: every row strictly after last_processed_date, oldest first.
    assert rows_to_process(index, index[150].date(), 100) == list(range(151, 200))
    # Strictly after — the already-processed day is never redone.
    assert rows_to_process(index, index[199].date(), 100) == []
    # Capped, and the cap keeps the OLDEST rows so successive ticks continue
    # forward rather than skipping.
    assert rows_to_process(index, index[100].date(), 100, max_rows=10) == list(range(101, 111))
    assert len(rows_to_process(index, index[0].date(), 100)) == min(99, MAX_CATCHUP_ROWS_PER_TICK)
    # Rows without a full fit window in front of them are never returned.
    assert min(rows_to_process(index, index[0].date(), 100)) >= 100
    # Not enough history at all.
    assert rows_to_process(index[:50], None, 100) == []


def test_unrecoverable_rows_are_reported_not_silently_dropped():
    index = pd.bdate_range("2026-01-01", periods=200)
    # A gap reaching back before the fit-window floor: those days cannot be
    # replayed from THIS frame, and the runner must be able to say so.
    lost = runner_module.unrecoverable_rows(index, index[10].date(), 100)
    assert lost == [d.date() for d in index[11:100]]
    # No gap below the floor -> nothing to report.
    assert runner_module.unrecoverable_rows(index, index[150].date(), 100) == []
    assert runner_module.unrecoverable_rows(index, None, 100) == []


# =========================================================================
# PART 2 — the one-time backfill of days already lost.
# =========================================================================


def _seed_gapped_registration(db, user_id: int, frame: pd.DataFrame, n_days_before_gap: int) -> tuple[int, date]:
    """Hand-construct a registration that stopped ticking mid-history, by
    stepping the FIRST n_days_before_gap days through step_one_day directly.

    Deliberately not by driving the runner: the backfill's expected outcome
    has to come from the walk-forward mechanics themselves, not from the
    code under test."""
    raw_data = build_pairs_raw_data(frame, "A", "B")
    state = WalkForwardState()
    day_results, trades = [], []
    for t in range(FIT_WINDOW_DAYS, FIT_WINDOW_DAYS + n_days_before_gap):
        state, day_result, closed_trade = step_one_day(
            raw_data.iloc[t - FIT_WINDOW_DAYS : t],
            raw_data.iloc[t],
            fit_ou_pairs_window,
            realize_pairs_return,
            state,
            _config(),
        )
        day_results.append(runner_module._day_result_to_dict(day_result))
        if closed_trade is not None:
            trades.append(runner_module._trade_to_dict(closed_trade))

    last_processed = raw_data.index[FIT_WINDOW_DAYS + n_days_before_gap - 1].date()
    registration = ForwardValidationRegistration(
        user_id=user_id,
        strategy_name="ou_pairs_v1",
        ticker_a="A",
        ticker_b="B",
        fit_window_days=FIT_WINDOW_DAYS,
        entry_z=ENTRY_Z,
        exit_z=EXIT_Z,
        cost_bps=COST_BPS,
        config_hash="backfill-test",
        status="in_progress",
        min_trading_days_threshold=NO_GRADUATION,
        n_forward_trading_days=n_days_before_gap,
        started_at=date(2020, 1, 1),
        last_processed_date=last_processed,
        carry_state_json=json.dumps(serialize_walk_forward_state(state)),
        day_results_json=json.dumps(day_results),
        trades_json=json.dumps(trades),
    )
    db.add(registration)
    db.commit()
    db.refresh(registration)
    return registration.id, last_processed


@pytest.fixture
def full_history_prices_fn(monkeypatch):
    """The backfill's world: all the history really does still exist — it
    was simply never processed."""

    def _install(frame: pd.DataFrame):
        def fake_get_price_history(tickers, start, end):
            present = [t for t in tickers if t in frame.columns]
            missing = [t for t in tickers if t not in frame.columns]
            return frame[present], missing

        monkeypatch.setattr(dependencies.provider, "get_price_history", fake_get_price_history)

    return _install


def test_backfill_recovers_a_known_gap_exactly(test_db_engine, register_and_verify, client, full_history_prices_fn):
    """A hand-constructed registration that stopped 12 days into a 30-day
    history, with a known correct answer: after the backfill its whole
    record must equal a single batch walk-forward over every row."""
    frame = _synthetic_ou_frame(FIT_WINDOW_DAYS + 31)
    full_history_prices_fn(frame)
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration_id, last_processed = _seed_gapped_registration(db, user["id"], frame, n_days_before_gap=12)

    batch = _batch_reference(frame, len(frame))
    today = frame.index[-1].date()

    outcomes = backfill_module.backfill_missed_days(today=today, apply=True)
    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.registration_id == registration_id
    assert outcome.n_forward_trading_days_before == 12
    assert outcome.n_forward_trading_days_after == len(batch.day_results)
    assert outcome.days_recovered == len(batch.day_results) - 12
    assert outcome.last_processed_date_before == last_processed
    assert outcome.last_processed_date_after == today
    assert outcome.recovered_dates[0] > last_processed
    assert outcome.recovered_dates[-1] == today
    assert len(outcome.recovered_dates) == outcome.days_recovered
    assert outcome.unrecoverable_dates == []

    with session_local() as db:
        reg = db.get(ForwardValidationRegistration, registration_id)
        _assert_matches_batch(reg, batch)
        assert reg.last_processed_date == today
        assert reg.status == "in_progress"
        # The carry state is the batch run's own final state, not merely a
        # plausible one — trades and open position included.
        replayed_state = json.loads(reg.carry_state_json)
        assert replayed_state["position"] == batch.day_results[-1].position
        assert replayed_state["equity"] == pytest.approx(batch.day_results[-1].equity)
        closed_trades = json.loads(reg.trades_json)
        batch_closed = [t for t in batch.trades if not t.still_open]
        assert len(closed_trades) == len(batch_closed)
        for stored, ref in zip(closed_trades, batch_closed, strict=True):
            assert stored["entry_date"] == ref.entry_date.strftime("%Y-%m-%d")
            assert stored["exit_date"] == ref.exit_date.strftime("%Y-%m-%d")
            assert stored["direction"] == ref.direction
            assert stored["holding_days"] == ref.holding_days
            assert stored["trade_return"] == pytest.approx(ref.trade_return)


def test_backfill_dry_run_writes_nothing(test_db_engine, register_and_verify, client, full_history_prices_fn):
    frame = _synthetic_ou_frame(FIT_WINDOW_DAYS + 31)
    full_history_prices_fn(frame)
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration_id, _ = _seed_gapped_registration(db, user["id"], frame, n_days_before_gap=12)
        before = {f: getattr(db.get(ForwardValidationRegistration, registration_id), f) for f in PERSISTED_FIELDS}

    outcomes = backfill_module.backfill_missed_days(today=frame.index[-1].date(), apply=False)
    assert outcomes[0].days_recovered > 0  # it reports what it WOULD do...

    with session_local() as db:
        reg = db.get(ForwardValidationRegistration, registration_id)
        assert {f: getattr(reg, f) for f in PERSISTED_FIELDS} == before  # ...and changes nothing


def test_backfill_is_idempotent(test_db_engine, register_and_verify, client, full_history_prices_fn):
    """Running it twice must be safe — the second pass finds no gap. This is
    the property that makes a one-time state rewrite re-runnable without
    fear of double-counting days."""
    frame = _synthetic_ou_frame(FIT_WINDOW_DAYS + 31)
    full_history_prices_fn(frame)
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration_id, _ = _seed_gapped_registration(db, user["id"], frame, n_days_before_gap=12)

    today = frame.index[-1].date()
    backfill_module.backfill_missed_days(today=today, apply=True)
    with session_local() as db:
        after_first = {f: getattr(db.get(ForwardValidationRegistration, registration_id), f) for f in PERSISTED_FIELDS}

    second = backfill_module.backfill_missed_days(today=today, apply=True)
    assert second[0].days_recovered == 0
    # The cheap early-out: last_processed_date is now `today`, so there is
    # provably no newer row and no price fetch is even attempted.
    assert second[0].note == "already current"
    with session_local() as db:
        reg = db.get(ForwardValidationRegistration, registration_id)
        assert {f: getattr(reg, f) for f in PERSISTED_FIELDS} == after_first

    # And the other no-op shape: the calendar has moved on (a weekend) but
    # no new trading row exists. It looks past the early-out, loads prices,
    # finds nothing to do, and still writes nothing.
    third = backfill_module.backfill_missed_days(today=today + timedelta(days=2), apply=True)
    assert third[0].days_recovered == 0
    assert "no gap" in third[0].note
    with session_local() as db:
        reg = db.get(ForwardValidationRegistration, registration_id)
        assert {f: getattr(reg, f) for f in PERSISTED_FIELDS} == after_first


def test_backfill_leaves_a_never_ticked_registration_alone(
    test_db_engine, register_and_verify, client, full_history_prices_fn
):
    """A registration with no last_processed_date has lost NOTHING — its
    first tick is defined to start from today. Replaying history into it
    would manufacture a forward record out of backward data."""
    frame = _synthetic_ou_frame(FIT_WINDOW_DAYS + 31)
    full_history_prices_fn(frame)
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration_id = _create_registration(db, user["id"])

    outcomes = backfill_module.backfill_missed_days(today=frame.index[-1].date(), apply=True)
    assert outcomes[0].days_recovered == 0
    assert "never ticked" in outcomes[0].note
    with session_local() as db:
        reg = db.get(ForwardValidationRegistration, registration_id)
        assert reg.n_forward_trading_days == 0
        assert reg.last_processed_date is None
        assert reg.day_results_json == "[]"


def test_backfill_skips_a_parked_underperforming_registration(
    test_db_engine, register_and_verify, client, full_history_prices_fn
):
    """"Underperforming" is a deliberate, deliberately-irreversible park.
    It stopped ticking on purpose, so it has no lost days to recover, and
    the backfill must not resurrect it."""
    frame = _synthetic_ou_frame(FIT_WINDOW_DAYS + 31)
    full_history_prices_fn(frame)
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration_id, _ = _seed_gapped_registration(db, user["id"], frame, n_days_before_gap=12)
        db.get(ForwardValidationRegistration, registration_id).status = "underperforming"
        db.commit()

    assert backfill_module.backfill_missed_days(today=frame.index[-1].date(), apply=True) == []
    with session_local() as db:
        assert db.get(ForwardValidationRegistration, registration_id).n_forward_trading_days == 12


def test_backfill_reports_days_it_cannot_recover(test_db_engine, register_and_verify, client, monkeypatch):
    """An outage older than the price history that can be loaded is the one
    case nothing can repair. It must be REPORTED, never silently skipped —
    a lost day that nobody is told about is the whole bug."""
    frame = _synthetic_ou_frame(FIT_WINDOW_DAYS + 31)
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration_id, _ = _seed_gapped_registration(db, user["id"], frame, n_days_before_gap=12)
        # Backdate it far past anything the frame can price.
        reg = db.get(ForwardValidationRegistration, registration_id)
        reg.last_processed_date = frame.index[0].date() - timedelta(days=1)
        db.commit()

    def fake_get_price_history(tickers, start, end):
        present = [t for t in tickers if t in frame.columns]
        return frame[present], [t for t in tickers if t not in frame.columns]

    monkeypatch.setattr(dependencies.provider, "get_price_history", fake_get_price_history)

    outcome = backfill_module.backfill_missed_days(today=frame.index[-1].date(), apply=True)[0]
    assert outcome.unrecoverable_dates  # said out loud, not swallowed
    assert outcome.unrecoverable_dates[0] >= frame.index[0].date()
    assert outcome.days_recovered > 0  # and everything that COULD be recovered still was


def test_a_concurrently_advanced_row_is_never_replayed_from_a_stale_state(
    test_db_engine, register_and_verify, client, full_history_prices_fn
):
    """The one-time backfill may be run against a database a live runner is
    also ticking. If the row moved between the snapshot and the write, the
    computed days descend from a stale carry state — appending them would
    double-count days AND overwrite the newer state. The safe answer is to
    do nothing and let the next pass resume from what the row now says."""
    frame = _synthetic_ou_frame(FIT_WINDOW_DAYS + 31)
    full_history_prices_fn(frame)
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration_id, last_processed = _seed_gapped_registration(db, user["id"], frame, n_days_before_gap=12)

    snapshots = runner_module.ForwardValidationRunner()._load_active_registrations()
    stale = snapshots[0]
    assert stale.last_processed_date == last_processed

    # Something else ticks the row while we hold the stale snapshot.
    with session_local() as db:
        moved = db.get(ForwardValidationRegistration, registration_id)
        moved.last_processed_date = last_processed + timedelta(days=1)
        db.commit()
        before = {f: getattr(moved, f) for f in PERSISTED_FIELDS}

    raw_data = build_pairs_raw_data(frame, "A", "B")
    with session_local() as db:
        assert runner_module.replay_registration(db, stale, raw_data) == 0
    with session_local() as db:
        reg = db.get(ForwardValidationRegistration, registration_id)
        assert {f: getattr(reg, f) for f in PERSISTED_FIELDS} == before


def test_report_renders_every_registration(test_db_engine, register_and_verify, client, full_history_prices_fn):
    frame = _synthetic_ou_frame(FIT_WINDOW_DAYS + 31)
    full_history_prices_fn(frame)
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        _seed_gapped_registration(db, user["id"], frame, n_days_before_gap=12)

    outcomes = backfill_module.backfill_missed_days(today=frame.index[-1].date(), apply=False)
    report = backfill_module.format_report(outcomes, apply=False)
    assert "DRY RUN" in report
    assert "n_forward_trading_days 12 ->" in report
    assert "trading day(s) recovered in total" in report
