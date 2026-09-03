"""Cross-sectional forward validation.

Mirrors tests/test_forward_validation.py's conventions throughout: the same
patch_runner_session fixture technique (the runner opens its own SessionLocal
directly, so the get_db override does not reach it), synthetic deterministic
price frames instead of any network call, a growing-cursor fake panel that
simulates real days arriving one at a time, and — the load-bearing one — a
test that a tick-by-tick forward replay matches a single batch
run_cross_sectional_backtest call over the same range EXACTLY.
"""

import json
import logging
import os
import threading
import time
from dataclasses import replace
from datetime import date, timedelta
from itertools import pairwise

import numpy as np
import pandas as pd
import pytest
from sqlalchemy.orm import sessionmaker

from app.models.cross_sectional_forward_validation import (
    CrossSectionalForwardValidationRegistration,
)
from app.services.cross_sectional_forward_validation_service import (
    MIN_FORWARD_COMPLETE_HOLDS,
    compute_cross_sectional_forward_validation_config_hash,
    graduation_threshold_for,
    register_or_get_cross_sectional_forward_validation,
)
from app.services.forward_validation_service import MIN_FORWARD_VALIDATION_TRADING_DAYS
from app.services.research_lab import (
    cross_sectional_forward_registry as registry_module,
)
from app.services.research_lab import (
    cross_sectional_forward_validation_runner as runner_module,
)
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalSpec,
    fixed_universe_membership,
    run_cross_sectional_backtest,
)
from app.services.research_lab.cross_sectional_forward import (
    CrossSectionalForwardState,
    ForwardTickNotSupportedError,
    advance_forward_validation,
    deserialize_cross_sectional_forward_state,
    initial_state_json,
    rows_to_process,
    serialize_cross_sectional_forward_state,
    validate_spec_is_forward_tickable,
)
from app.services.research_lab.cross_sectional_forward_registry import (
    CrossSectionalFamilyAdapter,
    CrossSectionalLivePanel,
    UnknownCrossSectionalFamilyError,
    UnknownCrossSectionalSpecError,
    config_fingerprint,
    resolve_spec,
    spec_fingerprint,
)

TEST_FAMILY_KEY = "test_xs_family"
TEST_PATTERN_ID = "xs_test_momentum_h5"
N_TICKERS = 20
HOLDING_DAYS = 5
LOOKBACK_DAYS = 20


# --- synthetic family -------------------------------------------------------


def _synthetic_panel(n_rows: int, seed: int = 7) -> pd.DataFrame:
    """A deterministic (dates x tickers) close panel with genuine
    cross-sectional dispersion, so ranking actually separates names."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n_rows)
    drifts = np.linspace(-0.0015, 0.0015, N_TICKERS)
    data = {}
    for i in range(N_TICKERS):
        shocks = rng.normal(drifts[i], 0.02, n_rows)
        data[f"T{i:02d}"] = 100.0 * np.exp(np.cumsum(shocks))
    return pd.DataFrame(data, index=dates)


def _signal_trailing_return(history: CrossSectionalData) -> pd.Series:
    window = history.close.iloc[-10:]
    if len(window) < 2:
        return pd.Series(np.nan, index=history.close.columns, dtype=float)
    signal = window.iloc[-1] / window.iloc[0] - 1.0
    return signal.replace([np.inf, -np.inf], np.nan)


def _test_spec(**overrides) -> CrossSectionalSpec:
    spec = CrossSectionalSpec(
        pattern_id=TEST_PATTERN_ID,
        family="test_family",
        citation="synthetic; no literature claim",
        signal_fn=_signal_trailing_return,
        lookback_days=LOOKBACK_DAYS,
        holding_days=HOLDING_DAYS,
        portfolio="long_short",
        rank_fraction=0.2,
        leg_weighting="magnitude",
    )
    return replace(spec, **overrides) if overrides else spec


def _test_config() -> CrossSectionalConfig:
    # Both cost components deliberately non-zero: the turnover charge and
    # the time-based financing charge are what the forward path most easily
    # gets subtly wrong (charged twice, charged on the wrong day, charged on
    # trading days instead of calendar days), so every equivalence test
    # below is run with both switched on.
    return CrossSectionalConfig(
        cost_bps=30.0,
        min_names_per_leg=3,
        financing_bps_per_year=400.0,
        periods_per_year=365.0,
    )


class _FakePanelSource:
    """A family whose live panel grows one row at a time, so the runner can
    be ticked through simulated real days without any network call — the
    cross-sectional analogue of test_forward_validation's
    _make_growing_prices_fn."""

    def __init__(self, full: pd.DataFrame, n_rows: int):
        self.full = full
        self.cursor = {"len": n_rows}
        self.calls = 0
        self.last_end: date | None = None

    def __call__(self, end: date) -> CrossSectionalLivePanel:
        self.last_end = end
        self.calls += 1
        close = self.full.iloc[: self.cursor["len"]]
        return CrossSectionalLivePanel(
            data=CrossSectionalData(close=close),
            membership_fn=fixed_universe_membership(list(self.full.columns)),
            n_tickers=len(close.columns),
            last_row_date=close.index[-1].date(),
        )


@pytest.fixture
def synthetic_family(monkeypatch):
    """Registers a synthetic family in the adapter registry for the duration
    of one test, and returns its panel source so the test can advance the
    cursor. monkeypatch.setitem on the private registry dict restores it
    afterwards, so no test leaks a family into another."""
    full = _synthetic_panel(LOOKBACK_DAYS + 60)
    source = _FakePanelSource(full, n_rows=LOOKBACK_DAYS + 5)
    adapter = CrossSectionalFamilyAdapter(
        family_key=TEST_FAMILY_KEY,
        module_path="tests/test_cross_sectional_forward_validation.py",
        universe_rule="synthetic fixed universe; every ticker eligible on every date",
        n_trials=9,
        build_specs=lambda: [_test_spec()],
        build_config=_test_config,
        build_live_panel=source,
    )
    monkeypatch.setitem(registry_module._registry, TEST_FAMILY_KEY, adapter)
    return source


@pytest.fixture(autouse=True)
def patch_runner_session(test_db_engine, monkeypatch):
    """CrossSectionalForwardValidationRunner opens its own SessionLocal
    directly (it's not a FastAPI route, so the get_db dependency override
    doesn't reach it) — point that at the same per-test SQLite engine,
    mirroring test_forward_validation.py's patch_runner_session exactly."""
    testing_session_local = sessionmaker(bind=test_db_engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(runner_module, "SessionLocal", testing_session_local)


def _create_registration(
    db, user_id: int, *, min_trading_days_threshold: int = 360, started_at: date | None = None
) -> CrossSectionalForwardValidationRegistration:
    spec = _test_spec()
    config = _test_config()
    registration = CrossSectionalForwardValidationRegistration(
        user_id=user_id,
        family_key=TEST_FAMILY_KEY,
        pattern_id=TEST_PATTERN_ID,
        module_path="tests/test_cross_sectional_forward_validation.py",
        spec_family=spec.family,
        citation=spec.citation,
        universe_rule="synthetic",
        family_n_trials=9,
        config_hash="test-xs-hash",
        spec_fingerprint=spec_fingerprint(spec),
        config_fingerprint=config_fingerprint(config),
        spec_snapshot_json=json.dumps(registry_module.spec_identity(spec), sort_keys=True),
        config_snapshot_json=json.dumps(registry_module.config_identity(config), sort_keys=True),
        registration_rationale="test registration",
        status="in_progress",
        min_trading_days_threshold=min_trading_days_threshold,
        n_forward_trading_days=0,
        n_formations=0,
        started_at=started_at if started_at is not None else date.today(),
        carry_state_json=initial_state_json(),
        day_results_json="[]",
        formations_json="[]",
    )
    db.add(registration)
    db.commit()
    db.refresh(registration)
    return registration


# --- A: the reference-not-copy contract ------------------------------------


def test_resolve_spec_returns_the_familys_own_spec_object():
    """The registration path must never re-declare a spec — it looks the
    real one up in the family's own registry."""
    adapter, spec = resolve_spec("cross_sectional_crypto", "xc_btcbeta_l180_h180")
    assert spec is not None
    assert spec.pattern_id == "xc_btcbeta_l180_h180"
    assert spec.family == "crypto_betting_against_beta"
    # The exact production parameters, not an approximation of them.
    assert spec.holding_days == 180
    assert spec.lookback_days == 730
    assert spec.rank_fraction == 0.2
    assert spec.leg_weighting == "inverse_vol"
    assert spec.portfolio == "long_short"
    assert spec.cohort_formation_days is None
    # And it IS one of the objects build_crypto_family() produces.
    assert any(s.pattern_id == spec.pattern_id for s in adapter.build_specs())


def test_resolve_spec_rejects_unknown_family_and_unknown_pattern():
    with pytest.raises(UnknownCrossSectionalFamilyError):
        resolve_spec("no_such_family", "whatever")
    with pytest.raises(UnknownCrossSectionalSpecError):
        resolve_spec("cross_sectional_crypto", "xc_btcbeta_l999_h999")


def test_spec_fingerprint_changes_when_the_family_definition_changes():
    spec = _test_spec()
    assert spec_fingerprint(spec) == spec_fingerprint(_test_spec())
    assert spec_fingerprint(spec) != spec_fingerprint(_test_spec(holding_days=HOLDING_DAYS + 1))
    assert spec_fingerprint(spec) != spec_fingerprint(_test_spec(rank_fraction=0.3))
    assert spec_fingerprint(spec) != spec_fingerprint(_test_spec(leg_weighting="equal"))


def test_config_fingerprint_ignores_formation_start_but_not_costs():
    config = _test_config()
    with_start = _test_config()
    with_start.formation_start = date(2020, 1, 1)
    # formation_start bounds a BACKTEST's first formation and has no forward
    # meaning, so moving it must not read as drift.
    assert config_fingerprint(config) == config_fingerprint(with_start)

    costlier = _test_config()
    costlier.cost_bps = 60.0
    assert config_fingerprint(config) != config_fingerprint(costlier)


# --- B: what the forward ticker refuses to do ------------------------------


def test_overlapping_cohorts_are_refused_not_approximated():
    with pytest.raises(ForwardTickNotSupportedError, match="cohort_formation_days"):
        validate_spec_is_forward_tickable(_test_spec(cohort_formation_days=2), _test_config())


def test_delisting_imputation_is_refused_not_approximated():
    config = _test_config()
    config.impute_delisting_returns = True
    with pytest.raises(ForwardTickNotSupportedError, match="impute_delisting_returns"):
        validate_spec_is_forward_tickable(_test_spec(), config)


# --- C: the first tick must not backfill history ---------------------------


def test_first_ever_tick_processes_only_todays_row():
    """The integrity property of the whole mechanism: a brand-new
    registration must start its record TODAY, never manufacture one out of
    the backward data it was decided on."""
    index = _synthetic_panel(50).index
    assert rows_to_process(index, None) == [49]


def test_subsequent_ticks_catch_up_every_missed_row_in_order():
    index = _synthetic_panel(50).index
    last = index[45].date()
    assert rows_to_process(index, last) == [46, 47, 48, 49]


def test_catchup_is_bounded():
    index = _synthetic_panel(300).index
    positions = rows_to_process(index, index[0].date(), max_rows=10)
    assert len(positions) == 10
    assert positions == list(range(1, 11))


def test_no_new_row_is_a_no_op():
    index = _synthetic_panel(50).index
    assert rows_to_process(index, index[-1].date()) == []


# --- D: THE equivalence test — forward replay == batch backtest ------------


def test_forward_tick_by_tick_matches_batch_cross_sectional_backtest_exactly():
    """The single most important test in this file.

    A forward registration started at row `start` and ticked one real day at
    a time must produce EXACTLY the daily net returns a batch
    run_cross_sectional_backtest produces when its first formation is forced
    to that same row. Same formation dates, same legs, same weights, same
    turnover charge on the same day, same calendar-day financing accrual.

    If this ever fails, the forward path has grown arithmetic of its own and
    is no longer validating the strategy that was backtested."""
    n_rows = LOOKBACK_DAYS + 41
    full = _synthetic_panel(n_rows)
    spec = _test_spec()
    config = _test_config()
    membership = fixed_universe_membership(list(full.columns))

    start = LOOKBACK_DAYS  # the batch harness's own first_formation
    data_full = CrossSectionalData(close=full)

    # Batch: force first_formation to `start` by setting formation_start to
    # that row's calendar date (which is exactly what the production entry
    # points do).
    batch_config = _test_config()
    batch_config.formation_start = full.index[start].date()
    batch = run_cross_sectional_backtest(data_full, spec, batch_config, membership)
    assert batch.status == "ok"

    # Forward: register "on" the start row, then tick one row at a time.
    state = CrossSectionalForwardState()
    last_processed: date | None = None
    forward_returns: dict[pd.Timestamp, float] = {}
    forward_formations: list[pd.Timestamp] = []
    for row in range(start, n_rows):
        panel = CrossSectionalData(close=full.iloc[: row + 1])
        state, results = advance_forward_validation(
            panel, spec, config, membership, state, last_processed
        )
        for day_result in results:
            if day_result.reformed:
                forward_formations.append(day_result.date)
            if day_result.realized:
                forward_returns[day_result.date] = day_result.net_return
        if results:
            last_processed = results[-1].date.date()

    batch_returns = {ts: float(v) for ts, v in batch.daily_returns.items()}
    assert set(forward_returns) == set(batch_returns), "forward and batch realized different day sets"
    assert len(batch_returns) > 20, "the fixture must exercise several holds"
    for ts, batch_value in batch_returns.items():
        assert forward_returns[ts] == pytest.approx(batch_value, abs=1e-12), f"mismatch on {ts}"

    # Formation dates agree — with ONE correct, documented divergence at the
    # very end. The batch loop is `range(start, n - 1, holding_days)`: it
    # refuses to form on the frame's LAST row, because a backtest has no
    # tomorrow to realize such a formation against. A live tick that lands on
    # a formation date DOES form, because tomorrow's real data is exactly
    # what it is waiting for. So the forward list is the batch list, possibly
    # plus one trailing formation on the panel's final row.
    batch_formation_dates = [f.date for f in batch.formations]
    assert forward_formations[: len(batch_formation_dates)] == batch_formation_dates
    extra = forward_formations[len(batch_formation_dates) :]
    assert extra in ([], [full.index[-1]]), f"unexpected extra formations: {extra}"


def test_the_real_bab_spec_ticks_forward_identically_to_the_batch_harness():
    """The same equivalence property, run on the ACTUAL registered strategy
    rather than a simplified stand-in: xc_btcbeta_l180_h180's real signal
    closure, its real inverse-vol leg weighting (with its own external basis
    frame and whole-leg fallback), its real 180-row hold, and the real Crypto
    config (30bp turnover, 400bps/yr financing, 365-day year).

    Prices are synthetic — tests must never depend on live data — but the
    STRATEGY is production. This is what makes the BAB registration's forward
    record trustworthy: the thing being ticked is the thing that was
    backtested, weighting fallbacks and all."""
    from app.services.research_lab.cross_sectional_crypto import (
        CRYPTO_MARKET_TICKER,
        build_inverse_vol_basis,
    )

    _adapter, spec = resolve_spec("cross_sectional_crypto", "xc_btcbeta_l180_h180")
    config = _adapter.build_config()

    # A calendar-day (24/7) panel, as crypto really is, long enough for the
    # spec's declared 730-row lookback plus several 180-row holds.
    rng = np.random.default_rng(11)
    n_rows = 730 + 400
    dates = pd.date_range(end=pd.Timestamp.today().normalize(), periods=n_rows, freq="D")
    tickers = [CRYPTO_MARKET_TICKER] + [f"C{i:02d}-USD" for i in range(29)]
    market = rng.normal(0.0004, 0.03, n_rows)
    columns = {}
    for i, ticker in enumerate(tickers):
        beta = 0.2 + 0.06 * i  # real cross-sectional beta dispersion to rank on
        shocks = beta * market + rng.normal(0.0, 0.02, n_rows)
        columns[ticker] = 100.0 * np.exp(np.cumsum(shocks))
    close = pd.DataFrame(columns, index=dates)

    membership = fixed_universe_membership(tickers)
    basis_full = build_inverse_vol_basis(close)
    data_full = CrossSectionalData(close=close, leg_weight_basis=basis_full)

    start = spec.lookback_days
    batch_config = _adapter.build_config()
    batch_config.formation_start = close.index[start].date()
    batch = run_cross_sectional_backtest(data_full, spec, batch_config, membership)
    assert batch.status == "ok"

    state = CrossSectionalForwardState()
    last_processed: date | None = None
    forward_returns: dict[pd.Timestamp, float] = {}
    for row in range(start, n_rows):
        window = close.iloc[: row + 1]
        # The basis is rebuilt from the live panel each tick, exactly as the
        # runner's adapter does — never sliced from a frame that saw the
        # future.
        panel = CrossSectionalData(close=window, leg_weight_basis=build_inverse_vol_basis(window))
        state, results = advance_forward_validation(panel, spec, config, membership, state, last_processed)
        for day_result in results:
            if day_result.realized:
                forward_returns[day_result.date] = day_result.net_return
        if results:
            last_processed = results[-1].date.date()

    batch_returns = {ts: float(v) for ts, v in batch.daily_returns.items()}
    assert len(batch_returns) > 300
    assert set(forward_returns) == set(batch_returns)
    for ts, batch_value in batch_returns.items():
        assert forward_returns[ts] == pytest.approx(batch_value, abs=1e-12), f"mismatch on {ts}"

    # And the real spec really did exercise its 180-row cadence.
    assert state.n_formations >= 2


def test_forward_replay_reforms_only_on_formation_dates():
    """Between formations the book is HELD — the signal is not consulted and
    nothing is re-decided. A cross-sectional spec that reformed daily would
    be a different (and far more expensive) strategy than the one screened."""
    n_rows = LOOKBACK_DAYS + 21
    full = _synthetic_panel(n_rows)
    spec = _test_spec()
    config = _test_config()
    membership = fixed_universe_membership(list(full.columns))

    state = CrossSectionalForwardState()
    last_processed: date | None = None
    reform_rows: list[int] = []
    for row in range(LOOKBACK_DAYS, n_rows):
        panel = CrossSectionalData(close=full.iloc[: row + 1])
        state, results = advance_forward_validation(panel, spec, config, membership, state, last_processed)
        for day_result in results:
            if day_result.reformed:
                reform_rows.append(row)
        if results:
            last_processed = results[-1].date.date()

    assert reform_rows[0] == LOOKBACK_DAYS
    gaps = {b - a for a, b in pairwise(reform_rows)}
    assert gaps == {HOLDING_DAYS}, f"reformed on the wrong cadence: {reform_rows}"


def test_turnover_cost_is_charged_once_per_formation_on_its_first_realized_day():
    n_rows = LOOKBACK_DAYS + 13
    full = _synthetic_panel(n_rows)
    spec = _test_spec()
    config = _test_config()
    membership = fixed_universe_membership(list(full.columns))

    state = CrossSectionalForwardState()
    last_processed: date | None = None
    charged: list[tuple[int, float]] = []
    for row in range(LOOKBACK_DAYS, n_rows):
        panel = CrossSectionalData(close=full.iloc[: row + 1])
        state, results = advance_forward_validation(panel, spec, config, membership, state, last_processed)
        for day_result in results:
            if day_result.turnover_cost:
                charged.append((row, day_result.turnover_cost))
        if results:
            last_processed = results[-1].date.date()

    # One charge per formation, each landing on exactly the row AFTER its
    # formation — never on the formation row itself and never twice.
    charged_rows = [r for r, _ in charged]
    formation_rows = list(range(LOOKBACK_DAYS, n_rows, HOLDING_DAYS))
    expected = [f + 1 for f in formation_rows if f + 1 < n_rows]
    assert charged_rows == expected
    assert len(charged_rows) == len(set(charged_rows))
    assert all(cost > 0 for _, cost in charged)


def test_financing_accrues_on_calendar_days_not_rows():
    """A Friday-to-Monday day must carry three days of financing, matching
    the harness's FINANCING_DAYS_PER_YEAR convention. The synthetic panel is
    a business-day index, so weekends are exactly the gap to look for."""
    n_rows = LOOKBACK_DAYS + 12
    full = _synthetic_panel(n_rows)
    spec = _test_spec()
    config = _test_config()
    membership = fixed_universe_membership(list(full.columns))

    state = CrossSectionalForwardState()
    last_processed: date | None = None
    by_gap: dict[int, list[float]] = {}
    for row in range(LOOKBACK_DAYS, n_rows):
        panel = CrossSectionalData(close=full.iloc[: row + 1])
        state, results = advance_forward_validation(panel, spec, config, membership, state, last_processed)
        for day_result in results:
            if day_result.realized and day_result.financing_cost:
                gap = (full.index[row] - full.index[row - 1]).days
                by_gap.setdefault(gap, []).append(day_result.financing_cost)
        if results:
            last_processed = results[-1].date.date()

    assert 1 in by_gap and 3 in by_gap, f"fixture did not span a weekend: {sorted(by_gap)}"
    one_day = np.mean(by_gap[1])
    three_day = np.mean(by_gap[3])
    assert three_day == pytest.approx(3.0 * one_day, rel=1e-9)


def test_forward_state_survives_a_serialize_deserialize_round_trip():
    n_rows = LOOKBACK_DAYS + 9
    full = _synthetic_panel(n_rows)
    spec = _test_spec()
    config = _test_config()
    membership = fixed_universe_membership(list(full.columns))

    state = CrossSectionalForwardState()
    last_processed: date | None = None
    for row in range(LOOKBACK_DAYS, n_rows):
        panel = CrossSectionalData(close=full.iloc[: row + 1])
        state, results = advance_forward_validation(panel, spec, config, membership, state, last_processed)
        if results:
            last_processed = results[-1].date.date()
        # Round-trip through JSON on EVERY step, exactly as a real tick does.
        state = deserialize_cross_sectional_forward_state(
            json.loads(json.dumps(serialize_cross_sectional_forward_state(state)))
        )

    assert state.n_formations >= 1
    assert state.long_weights and state.short_weights
    assert state.rows_since_formation is not None


# --- E: the runner ----------------------------------------------------------


@pytest.mark.asyncio
async def test_runner_advances_a_registration_one_real_day_at_a_time(
    test_db_engine, register_and_verify, client, synthetic_family
):
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration_id = _create_registration(db, user["id"]).id

    runner = runner_module.CrossSectionalForwardValidationRunner()

    # First tick: forms today's book, realizes nothing yet.
    await runner._tick()
    with session_local() as db:
        reg = db.get(CrossSectionalForwardValidationRegistration, registration_id)
        assert reg.n_formations == 1
        assert reg.n_forward_trading_days == 0
        assert reg.last_processed_date is not None
        assert len(json.loads(reg.formations_json)) == 1

    # Then five real days arrive, one per tick.
    for expected in range(1, 6):
        synthetic_family.cursor["len"] += 1
        await runner._tick()
        with session_local() as db:
            reg = db.get(CrossSectionalForwardValidationRegistration, registration_id)
            assert reg.n_forward_trading_days == expected
            days = json.loads(reg.day_results_json)
            assert len(days) == expected + 1  # +1 for the formation-only first day
            assert days[-1]["realized"] is True


@pytest.mark.asyncio
async def test_runner_tick_with_no_new_row_is_a_no_op(
    test_db_engine, register_and_verify, client, synthetic_family
):
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration_id = _create_registration(db, user["id"]).id

    runner = runner_module.CrossSectionalForwardValidationRunner()
    await runner._tick()
    with session_local() as db:
        reg = db.get(CrossSectionalForwardValidationRegistration, registration_id)
        before = (reg.n_forward_trading_days, reg.carry_state_json, reg.last_processed_date, reg.n_formations)

    await runner._tick()
    with session_local() as db:
        reg = db.get(CrossSectionalForwardValidationRegistration, registration_id)
        assert (
            reg.n_forward_trading_days,
            reg.carry_state_json,
            reg.last_processed_date,
            reg.n_formations,
        ) == before


@pytest.mark.asyncio
async def test_runner_uses_utc_today_not_local_today_for_the_panel_end_date(
    test_db_engine, register_and_verify, client, synthetic_family, monkeypatch
):
    """Real bug, found by adversarial verify: _process_family used
    date.today() (LOCAL) as yf.download's exclusive `end` bound. Between
    00:00-07:00 local in a timezone ahead of UTC, local date is already
    UTC's tomorrow, so `end` leaks the still-forming UTC bar -- which this
    runner then realizes as a permanent daily return and never revisits.
    Pins the fix: the panel source must be called with utcnow_naive().date(),
    not date.today(), even when the two disagree."""
    import datetime as dt_module

    from app.time_utils import utcnow_naive as real_utcnow_naive

    fake_utc_now = real_utcnow_naive().replace(hour=3, minute=0, second=0, microsecond=0)

    class _FakeLocalDate(dt_module.date):
        """A date subclass whose .today() is deliberately one day AHEAD of
        the faked UTC clock -- exactly the 00:00-07:00-local scenario."""

        @classmethod
        def today(cls):
            return (fake_utc_now + dt_module.timedelta(days=1)).date()

    monkeypatch.setattr(runner_module, "utcnow_naive", lambda: fake_utc_now)
    monkeypatch.setattr(runner_module, "date", _FakeLocalDate)

    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        _create_registration(db, user["id"])

    runner = runner_module.CrossSectionalForwardValidationRunner()
    await runner._tick()

    assert synthetic_family.last_end == fake_utc_now.date()
    assert synthetic_family.last_end != _FakeLocalDate.today()


@pytest.mark.asyncio
async def test_runner_skips_the_panel_download_when_nothing_is_pending(
    test_db_engine, register_and_verify, client, synthetic_family, monkeypatch
):
    """The cheap pre-check: a registration already processed THROUGH TODAY
    cannot have a newer row (today's is the newest that can exist), so the
    multi-year panel download must be skipped entirely. This matters because
    a cross-sectional family fetches outside get_price_history_cached, so —
    unlike the pairs runner — it does not get a free same-day no-op.

    Clock is mocked to a fixed UTC instant (same pattern as the sibling test
    above, test_runner_uses_utc_today_not_local_today_for_the_panel_end_date)
    rather than using real date.today()/utcnow_naive(). Found by this exact
    bug class recurring a fourth time this session: this test used LOCAL
    date.today() to set up last_processed_date, but the runner's own pending
    check (line ~196 of the runner, already correctly fixed) compares
    against utcnow_naive().date() — between 00:00-07:00 in a timezone ahead
    of UTC, "yesterday" by local date is still "today" by UTC date, so the
    second assertion below flaked specifically in that window. Pinning the
    clock removes the dependency on what time of day the suite happens to
    run, rather than merely relocating the same fragility to a different
    real-clock call."""
    from app.time_utils import utcnow_naive as real_utcnow_naive

    fixed_now = real_utcnow_naive().replace(hour=12, minute=0, second=0, microsecond=0)
    monkeypatch.setattr(runner_module, "utcnow_naive", lambda: fixed_now)
    today = fixed_now.date()

    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration = _create_registration(db, user["id"])
        registration.last_processed_date = today
        db.commit()
        registration_id = registration.id

    runner = runner_module.CrossSectionalForwardValidationRunner()
    await runner._tick()
    assert synthetic_family.calls == 0, "panel was built with nothing pending"

    # ...and it IS built once something is pending again.
    with session_local() as db:
        pending = db.get(CrossSectionalForwardValidationRegistration, registration_id)
        pending.last_processed_date = today - timedelta(days=1)
        db.commit()
    await runner._tick()
    assert synthetic_family.calls == 1


@pytest.mark.asyncio
async def test_runner_graduates_at_the_threshold_and_keeps_ticking(
    test_db_engine, register_and_verify, client, synthetic_family
):
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration_id = _create_registration(db, user["id"], min_trading_days_threshold=3).id

    runner = runner_module.CrossSectionalForwardValidationRunner()
    await runner._tick()  # formation only, 0 realized days

    for expected in (1, 2):
        synthetic_family.cursor["len"] += 1
        await runner._tick()
        with session_local() as db:
            reg = db.get(CrossSectionalForwardValidationRegistration, registration_id)
            assert reg.n_forward_trading_days == expected
            assert reg.status == "in_progress"
            assert reg.graduated_at is None

    synthetic_family.cursor["len"] += 1
    await runner._tick()
    with session_local() as db:
        reg = db.get(CrossSectionalForwardValidationRegistration, registration_id)
        assert reg.n_forward_trading_days == 3
        assert reg.status == "forward_validated"
        assert reg.graduated_at is not None

    synthetic_family.cursor["len"] += 1
    await runner._tick()
    with session_local() as db:
        reg = db.get(CrossSectionalForwardValidationRegistration, registration_id)
        assert reg.n_forward_trading_days == 4
        assert reg.status == "forward_validated"


@pytest.mark.asyncio
async def test_runner_catches_up_missed_days_rather_than_skipping_them(
    test_db_engine, register_and_verify, client, synthetic_family
):
    """A runner that was down must not drop the intervening days' real
    returns from the track record while still capturing the price move
    across them."""
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration_id = _create_registration(db, user["id"]).id

    runner = runner_module.CrossSectionalForwardValidationRunner()
    await runner._tick()

    synthetic_family.cursor["len"] += 4  # four real days passed while "down"
    await runner._tick()
    with session_local() as db:
        reg = db.get(CrossSectionalForwardValidationRegistration, registration_id)
        assert reg.n_forward_trading_days == 4


@pytest.mark.asyncio
async def test_runner_parks_a_registration_whose_family_definition_drifted(
    test_db_engine, register_and_verify, client, synthetic_family, monkeypatch
):
    """A family edited after registration must STOP the clock, not silently
    blend a second strategy into the same track record."""
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration_id = _create_registration(db, user["id"]).id

    runner = runner_module.CrossSectionalForwardValidationRunner()
    await runner._tick()

    drifted = replace(registry_module._registry[TEST_FAMILY_KEY].build_specs()[0], holding_days=9)
    monkeypatch.setitem(
        registry_module._registry,
        TEST_FAMILY_KEY,
        replace(registry_module._registry[TEST_FAMILY_KEY], build_specs=lambda: [drifted]),
    )

    synthetic_family.cursor["len"] += 1
    await runner._tick()
    with session_local() as db:
        reg = db.get(CrossSectionalForwardValidationRegistration, registration_id)
        assert reg.status == "spec_drift"
        assert reg.n_forward_trading_days == 0, "a drifted registration must not accumulate any day"

    # ...and stays parked: ACTIVE_STATUSES excludes it, so it is never loaded again.
    synthetic_family.cursor["len"] += 1
    await runner._tick()
    with session_local() as db:
        reg = db.get(CrossSectionalForwardValidationRegistration, registration_id)
        assert reg.status == "spec_drift"
        assert reg.n_forward_trading_days == 0


@pytest.mark.asyncio
async def test_runner_flags_underperformance_on_the_familys_own_calendar(
    test_db_engine, register_and_verify, client, synthetic_family
):
    from app.services.forward_validation_service import (
        UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS,
    )

    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration = _create_registration(db, user["id"], min_trading_days_threshold=10_000)
        # Pre-seed a bad trailing window directly rather than simulating 60
        # real ticks — check_underperformance reads only the `net_return`
        # key (and this path's `realized` filter), so this minimal shape is
        # sufficient and much faster. Mirrors test_forward_validation.py.
        bad = [
            {"date": "2020-01-01", "realized": True, "reformed": False, "net_return": -0.01, "equity": 1.0}
            for _ in range(UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS)
        ]
        registration.day_results_json = json.dumps(bad)
        registration.n_forward_trading_days = len(bad)
        db.commit()
        registration_id = registration.id

    runner = runner_module.CrossSectionalForwardValidationRunner()
    await runner._tick()
    with session_local() as db:
        reg = db.get(CrossSectionalForwardValidationRegistration, registration_id)
        assert reg.status == "underperforming"


# --- F: registration service -----------------------------------------------


def test_registration_is_idempotent_and_never_resets_progress(
    test_db_engine, register_and_verify, client, synthetic_family
):
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        first, created = register_or_get_cross_sectional_forward_validation(
            db,
            user_id=user["id"],
            family_key=TEST_FAMILY_KEY,
            pattern_id=TEST_PATTERN_ID,
            rationale="a deliberate, disclosed test registration with a real reason",
        )
        assert created is True
        first.n_forward_trading_days = 42
        db.commit()

        again, created_again = register_or_get_cross_sectional_forward_validation(
            db,
            user_id=user["id"],
            family_key=TEST_FAMILY_KEY,
            pattern_id=TEST_PATTERN_ID,
            rationale="a second submit of the identical registration",
        )
        assert created_again is False
        assert again.id == first.id
        assert again.n_forward_trading_days == 42


def test_registration_requires_a_written_rationale(
    test_db_engine, register_and_verify, client, synthetic_family
):
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db, pytest.raises(ValueError, match="rationale"):
        register_or_get_cross_sectional_forward_validation(
            db,
            user_id=user["id"],
            family_key=TEST_FAMILY_KEY,
            pattern_id=TEST_PATTERN_ID,
            rationale="   ",
        )


def test_registration_refuses_an_unsupported_spec_before_any_clock_starts(
    test_db_engine, register_and_verify, client, monkeypatch
):
    source = _FakePanelSource(_synthetic_panel(40), n_rows=30)
    monkeypatch.setitem(
        registry_module._registry,
        TEST_FAMILY_KEY,
        CrossSectionalFamilyAdapter(
            family_key=TEST_FAMILY_KEY,
            module_path="tests",
            universe_rule="synthetic",
            n_trials=1,
            build_specs=lambda: [_test_spec(cohort_formation_days=2)],
            build_config=_test_config,
            build_live_panel=source,
        ),
    )
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        with pytest.raises(ForwardTickNotSupportedError):
            register_or_get_cross_sectional_forward_validation(
                db,
                user_id=user["id"],
                family_key=TEST_FAMILY_KEY,
                pattern_id=TEST_PATTERN_ID,
                rationale="should never be written — the spec cannot be ticked forward",
            )
        assert db.query(CrossSectionalForwardValidationRegistration).count() == 0


def test_config_hash_is_stable_and_distinguishes_specs():
    a = compute_cross_sectional_forward_validation_config_hash("f", "p1", "s1", "c1")
    assert a == compute_cross_sectional_forward_validation_config_hash("f", "p1", "s1", "c1")
    assert a != compute_cross_sectional_forward_validation_config_hash("f", "p2", "s1", "c1")
    assert a != compute_cross_sectional_forward_validation_config_hash("f", "p1", "s2", "c1")
    assert a != compute_cross_sectional_forward_validation_config_hash("f", "p1", "s1", "c2")


def test_graduation_threshold_never_below_the_pairs_floor_and_covers_complete_holds():
    short_hold = _test_spec(holding_days=5)
    assert graduation_threshold_for(short_hold) == MIN_FORWARD_VALIDATION_TRADING_DAYS

    long_hold = _test_spec(holding_days=180)
    assert graduation_threshold_for(long_hold) == MIN_FORWARD_COMPLETE_HOLDS * 180
    assert graduation_threshold_for(long_hold) > MIN_FORWARD_VALIDATION_TRADING_DAYS


# --- G: the API -------------------------------------------------------------


def test_register_and_list_via_api(client, register_and_verify, synthetic_family):
    register_and_verify(client)
    response = client.post(
        "/api/cross-sectional-forward-validation",
        json={
            "family_key": TEST_FAMILY_KEY,
            "pattern_id": TEST_PATTERN_ID,
            "rationale": "a deliberate, disclosed registration made for a written reason",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created"] is True
    assert body["pattern_id"] == TEST_PATTERN_ID
    assert body["holding_days"] == HOLDING_DAYS
    assert body["status"] == "in_progress"
    assert body["sharpe_forward_so_far"] is None  # too few days to report one

    # Idempotent resubmit -> 200, created False.
    again = client.post(
        "/api/cross-sectional-forward-validation",
        json={
            "family_key": TEST_FAMILY_KEY,
            "pattern_id": TEST_PATTERN_ID,
            "rationale": "a deliberate, disclosed registration made for a written reason",
        },
    )
    assert again.status_code == 200, again.text
    assert again.json()["created"] is False

    listing = client.get("/api/cross-sectional-forward-validation")
    assert listing.status_code == 200
    assert [r["pattern_id"] for r in listing.json()] == [TEST_PATTERN_ID]


def test_register_unknown_pattern_is_404(client, register_and_verify, synthetic_family):
    register_and_verify(client)
    response = client.post(
        "/api/cross-sectional-forward-validation",
        json={
            "family_key": TEST_FAMILY_KEY,
            "pattern_id": "not_a_real_pattern",
            "rationale": "this should 404 rather than create a row referring to nothing",
        },
    )
    assert response.status_code == 404, response.text


def test_families_endpoint_lists_the_real_crypto_family(client, register_and_verify):
    register_and_verify(client)
    response = client.get("/api/cross-sectional-forward-validation/families")
    assert response.status_code == 200
    families = {f["family_key"]: f for f in response.json()}
    crypto = families["cross_sectional_crypto"]
    assert crypto["n_trials"] == 28
    assert len(crypto["pattern_ids"]) == 28
    assert "xc_btcbeta_l180_h180" in crypto["pattern_ids"]


# --- H: the BAB registration -----------------------------------------------


def test_bab_registration_uses_the_real_production_spec(test_db_engine, register_and_verify, client):
    from app.services.research_lab.bab_forward_registration import (
        BAB_FAMILY_KEY,
        BAB_PATTERN_ID,
        register_bab_forward_validation,
    )

    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    today = date.today()
    with session_local() as db:
        registration, created = register_bab_forward_validation(db, user["id"])
        assert created is True
        assert registration.family_key == BAB_FAMILY_KEY == "cross_sectional_crypto"
        assert registration.pattern_id == BAB_PATTERN_ID == "xc_btcbeta_l180_h180"
        assert registration.spec_family == "crypto_betting_against_beta"
        assert registration.family_n_trials == 28
        assert registration.started_at == today
        assert registration.status == "in_progress"
        assert registration.n_forward_trading_days == 0

        # The REAL production parameters, snapshotted from the family's own
        # spec — not an approximation typed into the registration.
        spec_snapshot = json.loads(registration.spec_snapshot_json)
        assert spec_snapshot["holding_days"] == 180
        assert spec_snapshot["lookback_days"] == 730
        assert spec_snapshot["rank_fraction"] == 0.2
        assert spec_snapshot["leg_weighting"] == "inverse_vol"
        assert spec_snapshot["portfolio"] == "long_short"
        assert spec_snapshot["cohort_formation_days"] is None

        config_snapshot = json.loads(registration.config_snapshot_json)
        assert config_snapshot["cost_bps"] == 30.0
        assert config_snapshot["financing_bps_per_year"] == 400.0
        assert config_snapshot["periods_per_year"] == 365.0
        assert config_snapshot["min_names_per_leg"] == 5

        # 2 complete 180-row holds, not the pairs path's 126 days.
        assert registration.min_trading_days_threshold == 360

        # The disclosure is ON THE ROW, not only in a docstring.
        rationale = registration.registration_rationale
        assert "NOT AN AUTOMATIC ONE" in rationale
        assert "28" in rationale
        assert "multiple-comparisons" in rationale
        assert "post-hoc trial-count shrinkage" in rationale


def test_bab_registration_is_idempotent(test_db_engine, register_and_verify, client):
    from app.services.research_lab.bab_forward_registration import (
        register_bab_forward_validation,
    )

    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        first, created_first = register_bab_forward_validation(db, user["id"])
        first_id = first.id
        assert created_first is True
        second, created_second = register_bab_forward_validation(db, user["id"])
        assert created_second is False
        assert second.id == first_id


def test_bab_started_at_is_a_real_today_not_a_backdate(test_db_engine, register_and_verify, client):
    """A forward-validation clock that could be backdated would let a
    registration inherit backward data as if it were forward data — the one
    thing this mechanism must be structurally incapable of."""
    from app.services.research_lab.bab_forward_registration import (
        register_bab_forward_validation,
    )

    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration, _ = register_bab_forward_validation(db, user["id"])
        assert registration.started_at == date.today()
        assert registration.last_processed_date is None
        assert json.loads(registration.day_results_json) == []
        assert json.loads(registration.formations_json) == []
        state = deserialize_cross_sectional_forward_state(json.loads(registration.carry_state_json))
        assert state.rows_since_formation is None
        assert state.n_formations == 0
        assert state.equity == 1.0
        assert registration.started_at > date.today() - timedelta(days=1)


# --- I: the two SEC-fundamentals QUALITY family adapters --------------------
#
# quality_cbop / cbop_ls_h63 and quality_noa_industry_neutral /
# noa_neutral_ls_h126_median are the two individually-registered forward
# hypotheses of 2026-08-30. Everything below is offline: the live panel
# builders take injectable provider/edgar arguments for exactly this reason,
# and no test here touches the network (the Crypto adapter's own panel
# builder is likewise never exercised against yfinance in this suite).

QUALITY_CBOP_PATTERN_ID = "cbop_ls_h63"
QUALITY_NOA_NEUTRAL_PATTERN_ID = "noa_neutral_ls_h126_median"
N_QUALITY_TICKERS = 60


def _today() -> date:
    """UTC today — the SAME clock CrossSectionalForwardValidationRunner.
    _process_family uses for the panel's `end` bound. Using the local date
    here would make these tests disagree with the runner by a day whenever
    local time runs ahead of UTC, which is the exact bug that path already
    carries a regression test for above."""
    from app.time_utils import utcnow_naive

    return utcnow_naive().date()


@pytest.fixture(autouse=True)
def reset_quality_live_state(monkeypatch):
    """The quality adapters carry two pieces of module state — the per-`end`
    panel memo and the published live bucket panel. Rebind both per test so
    no test can see another's, and so monkeypatch restores the production
    values afterwards."""
    monkeypatch.setattr(registry_module, "_QUALITY_PANEL_MEMO", {})
    monkeypatch.setattr(registry_module, "_LIVE_NOA_NEUTRAL_BUCKET_FRAME", None)


def _quality_fiscal_ends(today: date) -> list[date]:
    """Three consecutive fiscal-year ends whose year-over-year gaps sit
    inside cross_sectional_quality's 250..480-day annual-pair window, anchored
    on `today` so the newest value's filing age stays well inside
    FUNDAMENTAL_MAX_STALENESS_DAYS however long from now the suite runs."""
    last_end = today - timedelta(days=240)
    return [last_end - timedelta(days=730), last_end - timedelta(days=365), last_end]


def _resolved(value: float, filed: date):
    from app.services.market_data.edgar_xbrl_provider import ResolvedItem

    return ResolvedItem(value=value, filed=filed, tag="synthetic:Tag", tier=0)


def _quality_extraction(today: date, *, common_equity: float, cogs: float):
    """A LineItemExtraction shaped exactly as extract_line_items returns one,
    carrying every key _ITEM_RESOLVERS produces. Both factor formulas are
    computed from it by the FAMILY'S OWN compute_* functions, so this fixture
    exercises the real arithmetic rather than a stand-in for it.

    With assets flat at 1000 and the accrual accounts flat year to year,
    CbOP = (500 - cogs - 50) / 1000 and NOA = (50 + 200 + common_equity -
    100) / 1000 — so `cogs` and `common_equity` are the two dispersion
    handles the ranking actually separates names on."""
    from app.services.market_data.edgar_xbrl_provider import LineItemExtraction

    ends = _quality_fiscal_ends(today)
    filed = {e: e + timedelta(days=60) for e in ends}
    flat = {
        "assets": 1000.0,
        "revenue": 500.0,
        "cogs": cogs,
        "sga": 50.0,
        "cash_and_short_term_investments": 100.0,
        "common_equity": common_equity,
        "short_term_debt": 50.0,
        "long_term_debt": 200.0,
        "minority_interest": 0.0,
        "preferred_stock": 0.0,
        "receivables": 40.0,
        "inventory": 30.0,
        "prepaid": 10.0,
        "deferred_revenue": 20.0,
        "accounts_payable": 25.0,
        "accrued_expenses": 15.0,
    }
    items = {
        name: {e: _resolved(value, filed[e]) for e in ends} for name, value in flat.items()
    }
    return LineItemExtraction(items=items)


class _FakeYFinance:
    """Returns one prepared close panel whatever window it is asked for —
    the shape YFinanceProvider.get_price_history returns (frame, missing)."""

    def __init__(self, close: pd.DataFrame):
        self.close = close
        self.calls = 0

    def get_price_history(self, tickers, start, end):
        self.calls += 1
        return self.close, [t for t in tickers if t not in self.close.columns]


class _FakeEdgar:
    """The two EdgarXbrlProvider methods the quality panels call, with the
    same (result, missing_cik, failed) contract."""

    def __init__(self, extractions: dict, sic_histories: dict):
        self.extractions = extractions
        self.sic_histories = sic_histories
        self.line_item_calls = 0
        self.sic_calls = 0
        self.sic_tickers_asked: list[str] = []

    def fetch_line_items_for_tickers(self, tickers):
        self.line_item_calls += 1
        resolved = {t: e for t, e in self.extractions.items() if t in set(tickers)}
        return resolved, sorted(t for t in tickers if t not in self.extractions), []

    def fetch_sic_history_for_tickers(self, tickers):
        self.sic_calls += 1
        self.sic_tickers_asked = list(tickers)
        resolved = {t: h for t, h in self.sic_histories.items() if t in set(tickers)}
        return resolved, [], []


def _real_sample_members(n: int, today: date) -> list[str]:
    """The first `n` names of the families' OWN seeded sample that were index
    members today — so the real was_member gate the adapters install actually
    admits them, rather than the test asserting on an empty cross-section."""
    from app.services.research_lab.cross_sectional_quality import build_quality_sample
    from app.services.research_lab.sp500_membership_history import (
        MEMBERSHIP_DATA_AS_OF,
        MEMBERSHIP_DATA_START,
        was_member,
    )

    sample, _size = build_quality_sample(MEMBERSHIP_DATA_START, MEMBERSHIP_DATA_AS_OF)
    return [t for t in sample if was_member(t, today)][:n]


def _quality_offline_panel_inputs(n_tickers: int = N_QUALITY_TICKERS):
    """(tickers, fake yfinance, fake edgar) for the real live-panel builders.

    Buckets are assigned round-robin over the family's own SECTOR_BUCKETS so
    every bucket clears MIN_BUCKET_SIZE, and the SIC events are dated well
    before the price window so the step panel classifies every name on every
    row."""
    from app.services.market_data.edgar_xbrl_provider import SicHistory
    from app.services.research_lab.cross_sectional_quality_neutral import SECTOR_BUCKETS

    today = _today()
    tickers = _real_sample_members(n_tickers, today)
    assert len(tickers) == n_tickers, f"only {len(tickers)} sampled names are members today"

    dates = pd.bdate_range(end=pd.Timestamp(today) - pd.Timedelta(days=1), periods=120)
    rng = np.random.default_rng(11)
    close = pd.DataFrame(
        {t: 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, len(dates)))) for t in tickers},
        index=dates,
    )

    # One representative SIC per bucket, so sic_to_bucket lands each name in
    # the bucket this fixture intends.
    sic_for_bucket = {
        "reit": 6798,
        "financial": 6021,
        "tech": 7372,
        "healthcare": 2834,
        "energy_utility": 4911,
        "telecom_media": 4813,
        "consumer": 5812,
        "industrial": 3714,
    }
    extractions = {}
    sic_histories = {}
    for i, ticker in enumerate(tickers):
        extractions[ticker] = _quality_extraction(
            today, common_equity=300.0 + 10.0 * i, cogs=250.0 + 2.0 * i
        )
        bucket = SECTOR_BUCKETS[i % len(SECTOR_BUCKETS)]
        sic_histories[ticker] = SicHistory(
            cik=1000 + i,
            events=[(today - timedelta(days=3000), sic_for_bucket[bucket])],
            current_sic=sic_for_bucket[bucket],
        )
    return tickers, _FakeYFinance(close), _FakeEdgar(extractions, sic_histories)


# --- I.1: the reference-not-copy contract, for the two real families -------


def test_quality_adapters_resolve_the_families_own_production_specs():
    """Both registrations must resolve to the SAME spec objects the
    2026-08-28 production screenings ran — not an approximation typed here."""
    from app.services.research_lab.cross_sectional_quality import CBOP_FAMILY
    from app.services.research_lab.cross_sectional_quality_neutral import (
        build_noa_neutral_family,
    )

    adapter, spec = resolve_spec("quality_cbop", QUALITY_CBOP_PATTERN_ID)
    assert spec is CBOP_FAMILY[[s.pattern_id for s in CBOP_FAMILY].index(QUALITY_CBOP_PATTERN_ID)]
    assert spec.family == "cash_operating_profitability"
    assert (spec.holding_days, spec.lookback_days, spec.rank_fraction) == (63, 1, 0.1)
    assert spec.portfolio == "long_short"
    assert spec.leg_weighting == "magnitude"
    assert spec.requires_fundamental_signal is True
    assert adapter.module_path == "app/services/research_lab/cross_sectional_quality.py"
    # The family's OWN pre-declared denominator, 9 — never pooled with the
    # NOA sibling built in the same session.
    assert adapter.n_trials == 9
    assert len(adapter.build_specs()) == 9

    adapter, spec = resolve_spec("quality_noa_industry_neutral", QUALITY_NOA_NEUTRAL_PATTERN_ID)
    assert spec.family == "net_operating_assets_industry_neutral"
    assert (spec.holding_days, spec.lookback_days, spec.rank_fraction) == (126, 1, 0.1)
    assert spec.portfolio == "long_short"
    assert spec.leg_weighting == "magnitude"
    assert spec.requires_fundamental_signal is True
    assert adapter.module_path == "app/services/research_lab/cross_sectional_quality_neutral.py"
    # 18, NOT this family's own 9: the raw NOA family's 9 trials are carried
    # into the denominator, which is what its DSR was actually deflated
    # against. Recording 9 would launder that sequential search out of the row.
    assert adapter.n_trials == 18
    assert {s.pattern_id for s in adapter.build_specs()} == {
        s.pattern_id for s in build_noa_neutral_family(pd.DataFrame())
    }


def test_quality_adapters_expose_exactly_the_families_pattern_ids():
    _adapter, _spec = resolve_spec("quality_cbop", "cbop_hedged_h252")  # a sibling resolves too
    with pytest.raises(UnknownCrossSectionalSpecError):
        resolve_spec("quality_cbop", "noa_neutral_ls_h126_median")  # not this family's
    with pytest.raises(UnknownCrossSectionalSpecError):
        resolve_spec("quality_noa_industry_neutral", "noa_low_ls_h126")  # the RAW family's id


def test_both_target_specs_are_forward_tickable_and_not_refused():
    """The two refusals validate_spec_is_forward_tickable exists for —
    overlapping cohorts and delisting imputation — must be genuinely absent
    from these exact config objects, not merely assumed absent."""
    for family_key, pattern_id in (
        ("quality_cbop", QUALITY_CBOP_PATTERN_ID),
        ("quality_noa_industry_neutral", QUALITY_NOA_NEUTRAL_PATTERN_ID),
    ):
        adapter, spec = resolve_spec(family_key, pattern_id)
        config = adapter.build_config()
        assert spec.cohort_formation_days is None
        assert config.impute_delisting_returns is False
        assert spec.holding_days >= 1
        validate_spec_is_forward_tickable(spec, config)  # must not raise


def test_quality_fingerprints_match_what_the_families_declare_today():
    """Re-derive both fingerprints from the family modules DIRECTLY, without
    going through the registry, and require agreement — the drift check is
    only meaningful if the two paths agree on what the spec is."""
    from app.services.research_lab.cross_sectional_quality import (
        CBOP_FAMILY,
        default_quality_config,
    )
    from app.services.research_lab.cross_sectional_quality_neutral import (
        build_noa_neutral_family,
    )

    direct_cbop = next(s for s in CBOP_FAMILY if s.pattern_id == QUALITY_CBOP_PATTERN_ID)
    adapter, spec = resolve_spec("quality_cbop", QUALITY_CBOP_PATTERN_ID)
    assert spec_fingerprint(spec) == spec_fingerprint(direct_cbop)
    assert config_fingerprint(adapter.build_config()) == config_fingerprint(default_quality_config())

    direct_noa = next(
        s
        for s in build_noa_neutral_family(pd.DataFrame())
        if s.pattern_id == QUALITY_NOA_NEUTRAL_PATTERN_ID
    )
    adapter, spec = resolve_spec("quality_noa_industry_neutral", QUALITY_NOA_NEUTRAL_PATTERN_ID)
    assert spec_fingerprint(spec) == spec_fingerprint(direct_noa)
    assert config_fingerprint(adapter.build_config()) == config_fingerprint(default_quality_config())

    # Fingerprints are STABLE across repeated resolution (the drift check
    # re-derives them on every single tick).
    assert spec_fingerprint(resolve_spec("quality_cbop", QUALITY_CBOP_PATTERN_ID)[1]) == spec_fingerprint(
        direct_cbop
    )


def test_noa_neutral_fingerprint_is_independent_of_the_live_bucket_panel(monkeypatch):
    """The industry-neutral specs close over a runtime bucket panel that
    changes every day. If that leaked into spec_identity, every tick would
    read as spec_drift and park the registration. It must not."""
    before = spec_fingerprint(resolve_spec("quality_noa_industry_neutral", QUALITY_NOA_NEUTRAL_PATTERN_ID)[1])
    frame = pd.DataFrame(
        {"AAPL": ["tech"] * 3}, index=pd.date_range("2026-01-01", periods=3)
    )
    monkeypatch.setattr(registry_module, "_LIVE_NOA_NEUTRAL_BUCKET_FRAME", frame)
    after = spec_fingerprint(resolve_spec("quality_noa_industry_neutral", QUALITY_NOA_NEUTRAL_PATTERN_ID)[1])
    assert before == after


def test_noa_neutral_specs_without_a_live_panel_refuse_to_form_rather_than_rank_nothing():
    """The identity-only bucket frame is for fingerprinting, and must FAIL
    LOUDLY if anything ever tries to tick with it — a silently empty book
    would realize exactly 0.0 a day and be recorded as flat performance."""
    from app.services.research_lab.cross_sectional import form_portfolio

    adapter, spec = resolve_spec("quality_noa_industry_neutral", QUALITY_NOA_NEUTRAL_PATTERN_ID)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=10)
    tickers = [f"Q{i:02d}" for i in range(N_QUALITY_TICKERS)]
    close = pd.DataFrame(1.0, index=dates, columns=tickers)
    data = CrossSectionalData(
        close=close, fundamental_signal=pd.DataFrame(0.5, index=dates, columns=tickers)
    )
    with pytest.raises(KeyError):
        form_portfolio(
            data,
            spec,
            adapter.build_config(),
            fixed_universe_membership(tickers),
            len(dates) - 1,
            {},
        )


# --- I.2: the live panel builders ------------------------------------------


def test_cbop_live_panel_is_built_by_the_familys_own_pipeline():
    tickers, fake_yf, fake_edgar = _quality_offline_panel_inputs()
    from app.services.research_lab.sp500_membership_history import was_member

    panel = registry_module.build_cbop_live_panel(
        _today(), provider=fake_yf, edgar=fake_edgar
    )
    assert panel.n_tickers == N_QUALITY_TICKERS
    assert panel.last_row_date == fake_yf.close.index[-1].date()
    assert panel.data.fundamental_signal is not None
    assert list(panel.data.fundamental_signal.columns) == list(panel.data.close.columns)
    assert panel.data.fundamental_signal.index.equals(panel.data.close.index)
    # The whole cross-section is populated and genuinely dispersed — a
    # constant column would rank nothing.
    newest = panel.data.fundamental_signal.iloc[-1]
    assert newest.notna().all()
    assert newest.nunique() == N_QUALITY_TICKERS
    # CbOP = (revenue - cogs - sga) / lagged assets, computed by the family's
    # own compute_cbop_observations from the fixture's own numbers.
    assert newest[tickers[0]] == pytest.approx((500.0 - 250.0 - 50.0) / 1000.0)
    # THE survivorship gate: the harness's own S&P 500 membership function,
    # which is exactly what run_quality_screening gets by passing
    # membership_fn=None.
    assert panel.membership_fn is was_member
    # A quality panel ranks on fundamentals only — no leg-weighting basis,
    # which is what "magnitude" weighting means.
    assert panel.data.leg_weight_basis is None


def test_noa_neutral_live_panel_adds_the_point_in_time_bucket_panel():
    tickers, fake_yf, fake_edgar = _quality_offline_panel_inputs()
    from app.services.research_lab.sp500_membership_history import was_member

    panel = registry_module.build_noa_neutral_live_panel(
        _today(), provider=fake_yf, edgar=fake_edgar
    )
    assert panel.n_tickers == N_QUALITY_TICKERS
    assert panel.membership_fn is was_member
    newest = panel.data.fundamental_signal.iloc[-1]
    assert newest.notna().all()
    # NOA = (short-term debt + long-term debt + common equity - cash) /
    # lagged assets, by the family's own compute_noa_observations.
    assert newest[tickers[0]] == pytest.approx((50.0 + 200.0 + 300.0 - 100.0) / 1000.0)

    # The bucket panel was PUBLISHED, and the family's own specs bind to it.
    published = registry_module._LIVE_NOA_NEUTRAL_BUCKET_FRAME
    assert published is not None
    assert published.index.equals(panel.data.close.index)
    assert published.iloc[-1].notna().all()
    assert set(published.iloc[-1]) <= set(
        __import__(
            "app.services.research_lab.cross_sectional_quality_neutral",
            fromlist=["SECTOR_BUCKETS"],
        ).SECTOR_BUCKETS
    )
    # SIC history is fetched only for names EDGAR resolves a CIK for, exactly
    # as run_noa_neutral_screening does.
    assert set(fake_edgar.sic_tickers_asked) == set(tickers)


def test_noa_neutral_live_specs_can_actually_form_a_book_on_the_live_panel():
    """The end-to-end claim the identity-only frame test is the negative of:
    once build_live_panel has published a bucket panel, the family's own
    specs rank the live cross-section and produce two real legs."""
    from app.services.research_lab.cross_sectional import form_portfolio

    _tickers, fake_yf, fake_edgar = _quality_offline_panel_inputs()
    panel = registry_module.build_noa_neutral_live_panel(
        _today(), provider=fake_yf, edgar=fake_edgar
    )
    adapter, spec = resolve_spec("quality_noa_industry_neutral", QUALITY_NOA_NEUTRAL_PATTERN_ID)
    outcome = form_portfolio(
        panel.data,
        spec,
        adapter.build_config(),
        panel.membership_fn,
        len(panel.data.close.index) - 1,
        {},
    )
    assert outcome.record.skipped_reason is None
    assert len(outcome.long_weights) >= adapter.build_config().min_names_per_leg
    assert len(outcome.realized_short_weights) >= adapter.build_config().min_names_per_leg
    assert set(outcome.long_weights).isdisjoint(outcome.realized_short_weights)


@pytest.mark.parametrize(
    "builder_name", ["build_cbop_live_panel", "build_noa_neutral_live_panel"]
)
def test_quality_live_panel_refuses_an_empty_price_panel(builder_name):
    _tickers, fake_yf, fake_edgar = _quality_offline_panel_inputs()
    fake_yf.close = pd.DataFrame()
    with pytest.raises(registry_module.CrossSectionalPanelUnavailableError):
        getattr(registry_module, builder_name)(_today(), provider=fake_yf, edgar=fake_edgar)


@pytest.mark.parametrize(
    "builder_name", ["build_cbop_live_panel", "build_noa_neutral_live_panel"]
)
def test_quality_live_panel_refuses_a_panel_that_can_rank_nothing(builder_name):
    """An EDGAR outage leaves an all-NaN factor frame. Ticking on it would
    hold an empty book realizing exactly 0.0 every day — a data outage
    written into the track record as flat performance. It must raise the
    transient panel-unavailable error instead, so the row is untouched and
    the next tick retries."""
    _tickers, fake_yf, fake_edgar = _quality_offline_panel_inputs()
    fake_edgar.extractions = {}
    with pytest.raises(registry_module.CrossSectionalPanelUnavailableError):
        getattr(registry_module, builder_name)(_today(), provider=fake_yf, edgar=fake_edgar)


def test_noa_neutral_live_panel_refuses_a_panel_with_no_industry_buckets():
    _tickers, fake_yf, fake_edgar = _quality_offline_panel_inputs()
    fake_edgar.sic_histories = {}
    with pytest.raises(registry_module.CrossSectionalPanelUnavailableError):
        registry_module.build_noa_neutral_live_panel(
            _today(), provider=fake_yf, edgar=fake_edgar
        )


def test_quality_live_panel_is_memoized_per_end_date():
    """The runner keeps a family pending all day after its one real row is
    processed, so it calls build_live_panel ~47 more times for the same
    `end`. Each rebuild is a 200-ticker multi-year download plus the whole
    EDGAR pipeline, and cannot return anything different."""
    _tickers, fake_yf, fake_edgar = _quality_offline_panel_inputs()
    today = _today()
    first = registry_module.build_cbop_live_panel(today, provider=fake_yf, edgar=fake_edgar)
    second = registry_module.build_cbop_live_panel(today, provider=fake_yf, edgar=fake_edgar)
    assert second is first
    assert fake_yf.calls == 1
    assert fake_edgar.line_item_calls == 1

    # A new UTC day always rebuilds.
    registry_module.build_cbop_live_panel(
        today + timedelta(days=1), provider=fake_yf, edgar=fake_edgar
    )
    assert fake_yf.calls == 2


def test_noa_neutral_memo_hit_republishes_the_bucket_panel_it_was_built_with(monkeypatch):
    """A memo hit must leave the module holder pointing at the SAME bucket
    panel the memoized close panel was built against — otherwise a
    subsequent resolve_spec could bind the family's specs to a stale one."""
    _tickers, fake_yf, fake_edgar = _quality_offline_panel_inputs()
    today = _today()
    registry_module.build_noa_neutral_live_panel(today, provider=fake_yf, edgar=fake_edgar)
    built = registry_module._LIVE_NOA_NEUTRAL_BUCKET_FRAME
    monkeypatch.setattr(registry_module, "_LIVE_NOA_NEUTRAL_BUCKET_FRAME", None)
    registry_module.build_noa_neutral_live_panel(today, provider=fake_yf, edgar=fake_edgar)
    assert registry_module._LIVE_NOA_NEUTRAL_BUCKET_FRAME is built
    assert fake_edgar.sic_calls == 1


def test_quality_candidate_sample_window_is_pinned_to_vendored_coverage():
    """The seeded 200-name sample is a function of the WHOLE membership
    union, so one added index member re-draws it entirely. The live
    MembershipRefreshRunner extends coverage in process, so the sample
    window's end is pinned — and the pin must be a no-op TODAY (identical to
    what the families' own production runs drew), only biting once a refresh
    would otherwise have changed the universe underneath a live row."""
    from app.services.research_lab.cross_sectional_quality import build_quality_sample
    from app.services.research_lab.sp500_membership_history import (
        MEMBERSHIP_DATA_AS_OF,
        MEMBERSHIP_DATA_START,
    )

    pinned, pinned_size = build_quality_sample(MEMBERSHIP_DATA_START, MEMBERSHIP_DATA_AS_OF)
    as_run = build_quality_sample(MEMBERSHIP_DATA_START, _today())
    assert (pinned, pinned_size) == as_run
    assert len(pinned) == 200

    captured = {}

    class _CapturingYFinance(_FakeYFinance):
        def get_price_history(self, tickers, start, end):
            captured["tickers"] = list(tickers)
            captured["end"] = end
            return super().get_price_history(tickers, start, end)

    _t, fake_yf, fake_edgar = _quality_offline_panel_inputs()
    capturing = _CapturingYFinance(fake_yf.close)
    registry_module.build_cbop_live_panel(_today(), provider=capturing, edgar=fake_edgar)
    # The SAMPLE is the pinned one; the PRICE window's end is the live tick
    # date, because that half must move.
    assert captured["tickers"] == pinned
    assert captured["end"] == _today()


def test_the_registered_candidate_sample_is_fingerprinted_against_a_literal():
    """The window pin stops a live membership REFRESH re-drawing the sample.
    It cannot stop a RE-VENDORING of the membership literals, which moves
    MEMBERSHIP_DATA_AS_OF forward by design and would re-draw it straight
    through the pin — and no other guard here can see that, because a
    universe is data and the registration row stores no copy of it."""
    from app.services.research_lab.cross_sectional_quality import build_quality_sample
    from app.services.research_lab.sp500_membership_history import (
        MEMBERSHIP_DATA_AS_OF,
        MEMBERSHIP_DATA_START,
    )

    sample, size = build_quality_sample(MEMBERSHIP_DATA_START, MEMBERSHIP_DATA_AS_OF)
    assert (size, len(sample)) == (768, 200)
    assert (
        registry_module.quality_sample_fingerprint(sample, size)
        == registry_module.QUALITY_LIVE_SAMPLE_FINGERPRINT
    ), "the live sample no longer matches what the two registrations were created against"


def test_a_redrawn_candidate_sample_stops_the_tick_rather_than_changing_universe(monkeypatch):
    """A wholesale re-draw must NOT be tolerated, and must NOT be reported as
    the transient outage that CrossSectionalPanelUnavailableError means (that
    one is retried forever in silence, which is right for a data gap and
    wrong for a permanent universe change)."""
    _tickers, fake_yf, fake_edgar = _quality_offline_panel_inputs()
    real = registry_module.build_quality_sample
    monkeypatch.setattr(
        registry_module,
        "build_quality_sample",
        lambda start, end: (sorted([*real(start, end)[0][:-1], "ZZZZNEW"]), 769),
    )
    for builder in ("build_cbop_live_panel", "build_noa_neutral_live_panel"):
        with pytest.raises(registry_module.CrossSectionalUniverseDriftError) as exc:
            getattr(registry_module, builder)(_today(), provider=fake_yf, edgar=fake_edgar)
        assert "re-draw" in str(exc.value)
    assert not issubclass(
        registry_module.CrossSectionalUniverseDriftError,
        registry_module.CrossSectionalPanelUnavailableError,
    )


# --- I.3: a real registration, ticked by the real generic runner -----------


def _quality_runner_panel(spec_holding_days: int):
    """A growing synthetic panel plus the bucket frame the industry-neutral
    specs need, wide enough (60 names, deciles) that a 6-name leg clears
    min_names_per_leg."""
    from app.services.research_lab.cross_sectional_quality_neutral import SECTOR_BUCKETS

    del spec_holding_days
    n_rows = 40
    # Ends on YESTERDAY (UTC), exactly as a real panel does: yfinance's
    # `end` bound is exclusive, so the newest row a live tick can ever see
    # is the previous session's.
    dates = pd.bdate_range(end=pd.Timestamp(_today()) - pd.Timedelta(days=1), periods=n_rows)
    tickers = [f"Q{i:02d}" for i in range(N_QUALITY_TICKERS)]
    rng = np.random.default_rng(23)
    close = pd.DataFrame(
        {t: 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, n_rows))) for t in tickers},
        index=dates,
    )
    fundamental = pd.DataFrame(
        {t: float(i) / N_QUALITY_TICKERS for i, t in enumerate(tickers)}, index=dates
    )
    buckets = pd.DataFrame(
        {t: [SECTOR_BUCKETS[i % len(SECTOR_BUCKETS)]] * n_rows for i, t in enumerate(tickers)},
        index=dates,
    )
    return close, fundamental, buckets, tickers


class _QualityFakePanelSource:
    """A growing live panel for one quality family. For the industry-neutral
    family it also publishes the bucket panel, which is exactly the contract
    the real build_noa_neutral_live_panel keeps."""

    def __init__(self, close, fundamental, buckets, tickers, n_rows, publish_buckets):
        self.close = close
        self.fundamental = fundamental
        self.buckets = buckets
        self.tickers = tickers
        self.cursor = {"len": n_rows}
        self.publish_buckets = publish_buckets

    def __call__(self, end: date) -> CrossSectionalLivePanel:
        n = self.cursor["len"]
        close = self.close.iloc[:n]
        if self.publish_buckets:
            registry_module._LIVE_NOA_NEUTRAL_BUCKET_FRAME = self.buckets.iloc[:n]
        return CrossSectionalLivePanel(
            data=CrossSectionalData(close=close, fundamental_signal=self.fundamental.iloc[:n]),
            membership_fn=fixed_universe_membership(self.tickers),
            n_tickers=len(close.columns),
            last_row_date=close.index[-1].date(),
        )


@pytest.fixture
def quality_families_with_offline_panels(monkeypatch):
    """Both real quality adapters, unchanged except that build_live_panel is
    an offline growing panel — so the generic runner, the real specs, the
    real config and the real drift checks are all exercised, and only the
    network is replaced."""
    sources = {}
    for family_key in ("quality_cbop", "quality_noa_industry_neutral"):
        adapter = registry_module.get_family_adapter(family_key)
        close, fundamental, buckets, tickers = _quality_runner_panel(0)
        source = _QualityFakePanelSource(
            close,
            fundamental,
            buckets,
            tickers,
            n_rows=10,
            publish_buckets=family_key == "quality_noa_industry_neutral",
        )
        monkeypatch.setitem(
            registry_module._registry,
            family_key,
            replace(adapter, build_live_panel=source),
        )
        sources[family_key] = source
    return sources


@pytest.mark.parametrize(
    ("family_key", "pattern_id", "expected_threshold"),
    [
        ("quality_cbop", QUALITY_CBOP_PATTERN_ID, 126),
        ("quality_noa_industry_neutral", QUALITY_NOA_NEUTRAL_PATTERN_ID, 252),
    ],
)
@pytest.mark.asyncio
async def test_a_registered_quality_row_ticks_forward_through_the_generic_runner(
    test_db_engine,
    register_and_verify,
    client,
    quality_families_with_offline_panels,
    family_key,
    pattern_id,
    expected_threshold,
):
    """The whole path, for real: register through the production service,
    then let the existing generic runner (untouched by this work) resolve the
    family by family_key, re-derive and compare fingerprints, form a book on
    the live panel and realize real days against it."""
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration, created = register_or_get_cross_sectional_forward_validation(
            db,
            user_id=user["id"],
            family_key=family_key,
            pattern_id=pattern_id,
            rationale="offline integration test of a real quality registration",
        )
        assert created is True
        registration_id = registration.id
        # max(the pairs floor of 126, 2 complete holds).
        assert registration.min_trading_days_threshold == expected_threshold
        assert registration.status == "in_progress"
        assert registration.last_processed_date is None

    runner = runner_module.CrossSectionalForwardValidationRunner()

    await runner._tick()
    with session_local() as db:
        reg = db.get(CrossSectionalForwardValidationRegistration, registration_id)
        # A first tick forms today's book and realizes nothing — it must NOT
        # backfill the panel's history into a "forward" record.
        assert reg.status == "in_progress"
        assert reg.n_formations == 1
        assert reg.n_forward_trading_days == 0
        formations = json.loads(reg.formations_json)
        assert len(formations) == 1
        assert formations[0]["skipped_reason"] is None
        assert formations[0]["n_long"] >= 5

    source = quality_families_with_offline_panels[family_key]
    for expected in range(1, 4):
        source.cursor["len"] += 1
        await runner._tick()
        with session_local() as db:
            reg = db.get(CrossSectionalForwardValidationRegistration, registration_id)
            assert reg.n_forward_trading_days == expected
            assert reg.status == "in_progress"  # nowhere near 126/252 days
            days = json.loads(reg.day_results_json)
            assert len(days) == expected + 1
            assert days[-1]["realized"] is True
            assert days[-1]["n_long"] >= 5


def test_quality_registrations_are_idempotent_and_distinct_rows(
    test_db_engine, register_and_verify, client
):
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        cbop, created_a = register_or_get_cross_sectional_forward_validation(
            db,
            user_id=user["id"],
            family_key="quality_cbop",
            pattern_id=QUALITY_CBOP_PATTERN_ID,
            rationale="r1",
        )
        noa, created_b = register_or_get_cross_sectional_forward_validation(
            db,
            user_id=user["id"],
            family_key="quality_noa_industry_neutral",
            pattern_id=QUALITY_NOA_NEUTRAL_PATTERN_ID,
            rationale="r2",
        )
        assert created_a and created_b
        # Same config fingerprint (both families use default_quality_config),
        # so the config_hash MUST still separate them by the reference.
        assert cbop.config_fingerprint == noa.config_fingerprint
        assert cbop.config_hash != noa.config_hash
        assert cbop.family_n_trials == 9
        assert noa.family_n_trials == 18

        again, created_again = register_or_get_cross_sectional_forward_validation(
            db,
            user_id=user["id"],
            family_key="quality_cbop",
            pattern_id=QUALITY_CBOP_PATTERN_ID,
            rationale="r1 again",
        )
        assert created_again is False
        assert again.id == cbop.id


def test_families_endpoint_lists_both_quality_families(client, register_and_verify):
    """The /families listing must stay cheap — it calls build_specs for every
    registered family, and a family whose build_specs needed live data would
    turn an authenticated GET into a multi-hundred-request EDGAR fetch."""
    register_and_verify(client)
    response = client.get("/api/cross-sectional-forward-validation/families")
    assert response.status_code == 200
    families = {f["family_key"]: f for f in response.json()}
    assert families["quality_cbop"]["n_trials"] == 9
    assert QUALITY_CBOP_PATTERN_ID in families["quality_cbop"]["pattern_ids"]
    assert families["quality_noa_industry_neutral"]["n_trials"] == 18
    assert (
        QUALITY_NOA_NEUTRAL_PATTERN_ID
        in families["quality_noa_industry_neutral"]["pattern_ids"]
    )
    for key in ("quality_cbop", "quality_noa_industry_neutral"):
        assert len(families[key]["pattern_ids"]) == 9
        # The universe rule is snapshotted onto every registration, so it has
        # to actually SAY what the universe is.
        rule = families[key]["universe_rule"]
        assert "SEEDED RANDOM SAMPLE" in rule
        assert "was_member" in rule
        assert "PINNED" in rule


# --- I.4: the EDGAR cache bound the live path depends on -------------------


def test_edgar_companyfacts_cache_is_unbounded_by_default_and_bounded_on_request(tmp_path):
    """Default (every backtest, every existing caller): a cached
    companyfacts document is served forever, so a re-run reads the identical
    bytes its persisted numbers were computed from. With max_cache_age_days
    set — which is what the live quality panels construct — an aged file is
    refetched, because a frozen document would hold every firm's fundamentals
    at their registration-day vintage until FUNDAMENTAL_MAX_STALENESS_DAYS
    retired the name from the cross-section entirely."""
    import os

    from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider

    cached_path = tmp_path / "CIK0000000042.json"
    cached_path.write_text(json.dumps({"facts": {"us-gaap": {}}, "marker": "from-disk"}))
    old = pd.Timestamp.today().timestamp() - 5 * 86_400
    os.utime(cached_path, (old, old))

    def _refuse_network(_self, url):
        raise AssertionError(f"must not fetch {url}")

    unbounded = EdgarXbrlProvider(cache_dir=tmp_path, user_agent="test")
    monkey = unbounded._get_json
    unbounded._get_json = lambda url: _refuse_network(unbounded, url)  # type: ignore[method-assign]
    assert unbounded.get_company_facts(42)["marker"] == "from-disk"
    unbounded._get_json = monkey  # type: ignore[method-assign]

    bounded = EdgarXbrlProvider(cache_dir=tmp_path, user_agent="test", max_cache_age_days=1)
    fetched = {"marker": "from-network"}
    bounded._get_json = lambda _url: fetched  # type: ignore[method-assign]
    assert bounded.get_company_facts(42)["marker"] == "from-network"
    # And the refetch rewrote the cache, so it is fresh again.
    assert json.loads(cached_path.read_text())["marker"] == "from-network"
    assert bounded.get_company_facts(42)["marker"] == "from-network"


def test_live_quality_edgar_provider_is_constructed_with_the_cache_bound():
    provider = registry_module._live_edgar_provider()
    assert provider.max_cache_age_days == registry_module.QUALITY_LIVE_EDGAR_MAX_CACHE_AGE_DAYS
    assert registry_module.QUALITY_LIVE_EDGAR_MAX_CACHE_AGE_DAYS == 1


def test_a_refetched_cache_file_is_published_atomically(tmp_path):
    """A reader must never observe a half-written cache document.

    Bounding the cache age is what makes this reachable at all: before it,
    each file was written exactly once and thereafter only read, so no two
    callers were ever at one path together. Now BOTH quality families rebuild
    on the first tick of each UTC day and the runner ticks families
    concurrently (asyncio.gather over asyncio.to_thread), walking the same
    CIKs at the same pace — and a ~4 MB document streamed through an 8 KB
    buffer by a plain write_text was measurably readable mid-write, raising
    JSONDecodeError, which is not an EdgarFetchError and so is absorbed by
    nothing downstream."""
    from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider

    big = {"facts": {"us-gaap": {f"T{i}": {"units": {"USD": [{"v": i}] * 60}} for i in range(2000)}}}
    path = tmp_path / "CIK0000000042.json"
    path.write_text(json.dumps({"marker": "old"}))

    provider = EdgarXbrlProvider(cache_dir=tmp_path, user_agent="test", max_cache_age_days=1)
    provider._get_json = lambda _url: big  # type: ignore[method-assign]

    seen: list[object] = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            try:
                seen.append(json.loads(path.read_text()).get("marker", "new"))
            except FileNotFoundError:
                seen.append("missing")
            except json.JSONDecodeError as exc:  # the bug this guards against
                seen.append(exc)
                return

    thread = threading.Thread(target=reader)
    thread.start()
    try:
        for _ in range(25):
            os.utime(path, (time.time() - 10 * 86_400,) * 2)  # expire it again
            provider.get_company_facts(42)
    finally:
        stop.set()
        thread.join()

    torn = [s for s in seen if isinstance(s, Exception)]
    assert not torn, f"reader observed a partially written cache file: {torn[0]}"
    assert seen, "the reader never got to look at the file"
    # The publish leaves no temp file behind (tmp_path also holds the suite's
    # own test.db, so this checks for leftovers rather than an exact listing).
    assert [p.name for p in tmp_path.iterdir() if p.suffix == ".tmp"] == []
    assert json.loads(path.read_text())["facts"]["us-gaap"]["T0"]["units"]["USD"][0]["v"] == 0


# --- I.5: the two quality registrations ------------------------------------


def _assert_quality_registration_shape(cbop, noa, cbop_created, noa_created, today):
    """Asserted inside the caller's open session — every attribute below is
    a lazy-loadable ORM column, and reading one off a detached instance
    raises rather than returning the value."""
    from app.services.research_lab.quality_forward_registration import (
        CBOP_PATTERN_ID,
        NOA_NEUTRAL_PATTERN_ID,
    )

    assert cbop_created and noa_created

    assert (cbop.family_key, cbop.pattern_id) == ("quality_cbop", CBOP_PATTERN_ID)
    assert cbop.spec_family == "cash_operating_profitability"
    assert cbop.family_n_trials == 9
    assert cbop.module_path == "app/services/research_lab/cross_sectional_quality.py"
    assert cbop.status == "in_progress"
    assert cbop.n_forward_trading_days == 0
    assert cbop.n_formations == 0
    # max(the pairs floor of 126, 2 x holding_days=63) — exactly two
    # complete holds.
    assert cbop.min_trading_days_threshold == 126

    assert (noa.family_key, noa.pattern_id) == (
        "quality_noa_industry_neutral",
        NOA_NEUTRAL_PATTERN_ID,
    )
    assert noa.spec_family == "net_operating_assets_industry_neutral"
    # 18, not 9 — the raw NOA family's trials are carried into the
    # denominator this DSR was actually deflated against.
    assert noa.family_n_trials == 18
    assert noa.module_path == "app/services/research_lab/cross_sectional_quality_neutral.py"
    assert noa.min_trading_days_threshold == 252

    for registration, holding_days in ((cbop, 63), (noa, 126)):
        # The REAL production parameters, snapshotted from each family's own
        # spec — not an approximation typed into the registration.
        spec_snapshot = json.loads(registration.spec_snapshot_json)
        assert spec_snapshot["holding_days"] == holding_days
        assert spec_snapshot["lookback_days"] == 1
        assert spec_snapshot["rank_fraction"] == 0.1
        assert spec_snapshot["portfolio"] == "long_short"
        assert spec_snapshot["leg_weighting"] == "magnitude"
        assert spec_snapshot["cohort_formation_days"] is None

        config_snapshot = json.loads(registration.config_snapshot_json)
        assert config_snapshot["cost_bps"] == 5.0
        assert config_snapshot["financing_bps_per_year"] == 0.0
        assert config_snapshot["periods_per_year"] == 252  # equities, not crypto's 365
        assert config_snapshot["impute_delisting_returns"] is False

        # A real fingerprint, and a clock that starts TODAY holding nothing.
        assert len(registration.spec_fingerprint) == 64
        assert len(registration.config_fingerprint) == 64
        # A forward clock that could be backdated would let a registration
        # inherit backward data as if it were forward data. The window is a
        # day wide only because the service stamps the LOCAL date while
        # `today` here is UTC's.
        assert today <= registration.started_at <= today + timedelta(days=1)
        assert registration.last_processed_date is None
        assert json.loads(registration.day_results_json) == []
        state = deserialize_cross_sectional_forward_state(
            json.loads(registration.carry_state_json)
        )
        assert (state.equity, state.n_formations, state.rows_since_formation) == (1.0, 0, None)


def test_quality_registrations_use_the_real_production_specs(
    test_db_engine, register_and_verify, client
):
    from app.services.research_lab.quality_forward_registration import (
        register_quality_forward_validations,
    )

    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    today = _today()
    with session_local() as db:
        (cbop, cbop_created), (noa, noa_created) = register_quality_forward_validations(
            db, user["id"]
        )
        _assert_quality_registration_shape(cbop, noa, cbop_created, noa_created, today)


def test_quality_registration_rationales_disclose_what_they_must(
    test_db_engine, register_and_verify, client
):
    """A forward slot is a claim on real calendar time. These rows must say
    on their own face that neither family cleared this project's bar, what
    the DSR denominator was, and that TWO registrations mean a
    selection-over-two — not leave any of it to a docstring."""
    from app.services.research_lab.quality_forward_registration import (
        register_quality_forward_validations,
    )

    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        (cbop, _), (noa, _) = register_quality_forward_validations(db, user["id"])
        _assert_quality_rationales(cbop, noa)


def _assert_quality_rationales(cbop, noa):
    """Asserted inside the caller's open session — see
    _assert_quality_registration_shape."""
    for registration in (cbop, noa):
        rationale = registration.registration_rationale
        assert "NOT AN AUTOMATIC ONE" in rationale
        assert "graduation means ONLY" in rationale
        assert "TWO completed formations" in rationale
        assert "negative forward result is" in rationale
        assert "selection over two" in rationale

    assert "NOT A CLAIM OF VALIDATED EDGE" in cbop.registration_rationale
    assert "0.8174" in cbop.registration_rationale
    assert "9-trial" in cbop.registration_rationale
    # The lesson from the raw-NOA false alarm has to be ON the row.
    assert "0.968" in cbop.registration_rationale

    assert "HONEST NEGATIVE" in noa.registration_rationale
    assert "18-trial" in noa.registration_rationale
    assert "coin flip" in noa.registration_rationale
    assert "EXPECTED outcome" in noa.registration_rationale


def test_quality_registrations_are_idempotent_and_never_reset_progress(
    test_db_engine, register_and_verify, client
):
    from app.services.research_lab.quality_forward_registration import (
        register_quality_forward_validations,
    )

    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        first = register_quality_forward_validations(db, user["id"])
        ids = [r.id for r, _ in first]
        assert all(created for _, created in first)

        cbop = db.get(CrossSectionalForwardValidationRegistration, ids[0])
        cbop.n_forward_trading_days = 40
        db.commit()

        second = register_quality_forward_validations(db, user["id"])
        assert [r.id for r, _ in second] == ids
        assert not any(created for _, created in second)
        assert second[0][0].n_forward_trading_days == 40


def test_quality_registrations_are_owned_by_the_system_account_convention(
    test_db_engine, register_and_verify, client
):
    """The autonomous-ownership convention this project already uses for
    ScreeningJob and StrategyPortfolio rows: the rows belong to
    settings.system_account_email, and the listing endpoint surfaces them to
    any authenticated user with is_system=True rather than hiding them
    behind whichever human happened to run the registration."""
    from app.services.research_lab.quality_forward_registration import (
        register_quality_forward_validations,
    )
    from app.services.research_lab.system_account import get_or_create_system_user

    register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        system_user = get_or_create_system_user(db)
        register_quality_forward_validations(db, system_user.id)

    listing = client.get("/api/cross-sectional-forward-validation")
    assert listing.status_code == 200
    rows = {r["pattern_id"]: r for r in listing.json()}
    assert set(rows) == {"cbop_ls_h63", "noa_neutral_ls_h126_median"}
    assert all(r["is_system"] for r in rows.values())
    assert rows["cbop_ls_h63"]["holding_days"] == 63
    assert rows["noa_neutral_ls_h126_median"]["holding_days"] == 126
    assert all(r["periods_per_year"] == 252 for r in rows.values())
    assert all(r["sharpe_forward_so_far"] is None for r in rows.values())


# --- I.6: the app-startup registration path ---------------------------------
#
# WHY THESE TESTS EXIST AT ALL, AND WHY THEY CALL THE FUNCTION DIRECTLY.
# main.py's lifespan is never entered by this suite — conftest builds
# TestClient(fastapi_app) WITHOUT a `with` block, and starlette only runs the
# lifespan inside the context manager (test_lifespan_is_never_entered_by_the_
# test_client below pins that, because it is the property that keeps ten
# background runners and now this registration out of every test DB). That
# safety is also why the suite cannot exercise the startup path incidentally:
# the only way to test it is to call it directly, which is what follows.


@pytest.fixture
def patch_startup_session(test_db_engine, monkeypatch):
    """The startup step opens its own SessionLocal (it has no request to take
    a get_db session from), exactly like every runner — so point that module
    attribute at the test engine, the same technique patch_runner_session
    above already uses."""
    from app.services.research_lab import quality_forward_registration as startup_module

    monkeypatch.setattr(
        startup_module,
        "SessionLocal",
        sessionmaker(bind=test_db_engine, autoflush=False, autocommit=False),
    )
    return startup_module


def test_lifespan_is_never_entered_by_the_test_client(monkeypatch, client):
    """The load-bearing safety property behind this whole suite: conftest
    builds TestClient(fastapi_app) WITHOUT a `with` block, and starlette only
    runs the lifespan inside the context manager — so the startup
    registration, like the twelve background runners beside it, cannot fire as a
    side effect of a test making a request.

    Asserted on the CALL, not on a row count. The startup step opens the real
    app SessionLocal (the get_db override does not reach it), so if lifespan
    ever did run under the suite it would write to the DEVELOPER's aladdin2.db
    rather than to the per-test database — a row-count assertion on the test
    DB would pass while the damage happened somewhere else entirely."""
    import app.main as main_module

    called: list[str] = []

    async def _spy() -> None:
        called.append("startup registration ran")

    monkeypatch.setattr(
        main_module, "register_quality_forward_validations_on_startup", _spy
    )
    # BOTH startup registrations are spied. An unspied one would not just
    # weaken this test, it would write to the developer's real aladdin2.db
    # the moment lifespan ever did run under the suite.
    monkeypatch.setattr(
        main_module, "register_short_interest_forward_validation_on_startup", _spy
    )

    assert client.get("/health").json() == {"status": "ok"}
    assert called == [], (
        "main.py's lifespan ran under the test suite: every test would now be "
        "registering forward validations (and starting ten background runners) "
        "against the real dev database."
    )


@pytest.mark.asyncio
async def test_lifespan_awaits_the_registration_before_starting_the_runners(monkeypatch):
    """The POSITIVE CONTROL for the test above — without it, that one's
    `called == []` could pass because the spy is simply never reachable — and
    the only direct test of main.py's own wiring: that BOTH registrations are
    awaited, each exactly once, BEFORE the first background task is created.

    Entering the real lifespan is safe here precisely because the body is
    empty: __aenter__ creates the twelve tasks but never awaits after the last
    create_task, so __aexit__ cancels every one of them before the event loop
    has run a single line of any runner's body. The registrations themselves
    are spied out, so nothing touches a database either."""
    import asyncio

    import app.main as main_module

    order: list[str] = []

    async def _quality_spy() -> None:
        order.append("quality registration")

    async def _short_interest_spy() -> None:
        order.append("short interest registration")

    monkeypatch.setattr(
        main_module, "register_quality_forward_validations_on_startup", _quality_spy
    )
    monkeypatch.setattr(
        main_module, "register_short_interest_forward_validation_on_startup", _short_interest_spy
    )

    real_create_task = asyncio.create_task

    def _tracking_create_task(coro, *args, **kwargs):
        order.append("background task")
        return real_create_task(coro, *args, **kwargs)

    monkeypatch.setattr(asyncio, "create_task", _tracking_create_task)

    async with main_module.lifespan(main_module.app):
        pass

    assert order.count("quality registration") == 1, order
    assert order.count("short interest registration") == 1, order
    assert order[:2] == ["quality registration", "short interest registration"], order
    assert order.count("background task") == 12, order


def test_startup_registration_creates_both_rows_when_absent(
    test_db_engine, patch_startup_session
):
    outcomes = patch_startup_session.register_quality_forward_validations_once()

    assert len(outcomes) == 2
    assert all("CREATED" in line for line in outcomes)
    assert "family_key=quality_cbop pattern_id=cbop_ls_h63" in outcomes[0]
    assert (
        "family_key=quality_noa_industry_neutral pattern_id=noa_neutral_ls_h126_median"
        in outcomes[1]
    )
    # Enough detail on the line to be checked against the row from a log
    # viewer alone: id, family, pattern, status.
    assert all("status=in_progress" in line for line in outcomes)

    from app.services.research_lab.system_account import get_or_create_system_user

    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        rows = (
            db.query(CrossSectionalForwardValidationRegistration)
            .order_by(CrossSectionalForwardValidationRegistration.id)
            .all()
        )
        assert [r.pattern_id for r in rows] == ["cbop_ls_h63", "noa_neutral_ls_h126_median"]
        # The system-account ownership convention, not a human's user_id.
        system_user_id = get_or_create_system_user(db).id
        assert {r.user_id for r in rows} == {system_user_id}
        for row, line in zip(rows, outcomes, strict=True):
            assert f"id={row.id} " in line
            assert f"user_id={system_user_id} " in line


def test_startup_registration_no_ops_when_the_rows_already_exist(
    test_db_engine, patch_startup_session
):
    """The property that matters most on a host that restarts the process on
    every deploy and every wake-from-sleep: a second run must find, not
    recreate, and must not touch an accumulated clock."""
    first = patch_startup_session.register_quality_forward_validations_once()
    assert all("CREATED" in line for line in first)

    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        rows = (
            db.query(CrossSectionalForwardValidationRegistration)
            .order_by(CrossSectionalForwardValidationRegistration.id)
            .all()
        )
        ids = [r.id for r in rows]
        rows[0].n_forward_trading_days = 40  # accumulated progress to protect
        db.commit()

    second = patch_startup_session.register_quality_forward_validations_once()
    assert all("ALREADY EXISTS" in line for line in second)
    assert [line.split("id=")[1].split(" ")[0] for line in second] == [str(i) for i in ids]
    assert "n_forward_trading_days=40" in second[0]

    with session_local() as db:
        assert db.query(CrossSectionalForwardValidationRegistration).count() == 2
        assert db.get(CrossSectionalForwardValidationRegistration, ids[0]).n_forward_trading_days == 40


STARTUP_LOGGER_NAME = "app.services.research_lab.quality_forward_registration"


def _startup_log_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == STARTUP_LOGGER_NAME]


@pytest.mark.asyncio
async def test_startup_wrapper_logs_created_then_already_exists(
    test_db_engine, patch_startup_session, caplog
):
    """The async wrapper main.py actually awaits — both passes, through the
    real logging module, at the level and with the fields a reader of Render's
    log viewer would grep for."""
    with caplog.at_level(logging.INFO, logger=STARTUP_LOGGER_NAME):
        await patch_startup_session.register_quality_forward_validations_on_startup()
        created_lines = _startup_log_lines(caplog)
        caplog.clear()
        await patch_startup_session.register_quality_forward_validations_on_startup()
        second_lines = _startup_log_lines(caplog)

    assert len(created_lines) == 2
    assert all("CREATED" in line for line in created_lines)
    assert len(second_lines) == 2
    assert all("ALREADY EXISTS" in line for line in second_lines)

    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        assert db.query(CrossSectionalForwardValidationRegistration).count() == 2


@pytest.mark.parametrize(
    ("broken", "expected_in_traceback"),
    [
        # The realistic boot-time failure: the database is unreachable, so
        # even opening a session raises.
        ("session_factory", "simulated database outage at startup"),
        # And a failure part-way through, after a session exists — proving
        # the guard is around the whole step, not just the connect.
        ("registration", "simulated failure mid-registration"),
    ],
)
@pytest.mark.asyncio
async def test_startup_wrapper_never_raises_and_logs_the_failure(
    test_db_engine, patch_startup_session, monkeypatch, caplog, broken, expected_in_traceback
):
    """A failure on one process start must not take the API down with it —
    lifespan awaits this directly, so anything escaping here would abort
    startup entirely and leave Render with no service at all."""
    if broken == "session_factory":

        def _broken_session_factory():
            raise RuntimeError("simulated database outage at startup")

        monkeypatch.setattr(patch_startup_session, "SessionLocal", _broken_session_factory)
    else:

        def _broken_registration(*args, **kwargs):
            raise RuntimeError("simulated failure mid-registration")

        monkeypatch.setattr(
            patch_startup_session, "register_quality_forward_validations", _broken_registration
        )

    with caplog.at_level(logging.ERROR, logger=STARTUP_LOGGER_NAME):
        result = await patch_startup_session.register_quality_forward_validations_on_startup()

    assert result is None  # returned normally; nothing propagated
    failures = [r for r in caplog.records if r.name == STARTUP_LOGGER_NAME]
    assert len(failures) == 1
    assert failures[0].levelno == logging.ERROR
    assert "failed on startup" in failures[0].getMessage()
    # logger.exception, not logger.error: the traceback has to be in the log,
    # or a Render reader cannot tell WHY it failed.
    assert failures[0].exc_info is not None
    assert expected_in_traceback in caplog.text

    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        assert db.query(CrossSectionalForwardValidationRegistration).count() == 0


def test_startup_registration_never_builds_a_live_panel(patch_startup_session, monkeypatch):
    """Startup must not touch EDGAR or yfinance. If it did, a cold Render
    free-tier boot could sit behind a multi-minute fundamentals fetch and read
    as a hung deploy to the health check. Every registered family's live-panel
    builder is replaced with a detonator: the registration path resolves specs
    and config in memory only, so none of them may fire.

    Deliberately the SYNC entry point, not the never-raising async wrapper —
    the wrapper would catch the detonator's AssertionError and log it, and the
    test would pass vacuously."""

    def _explode(*args, **kwargs):
        raise AssertionError("startup registration built a live panel (network fetch)")

    for family_key in registry_module.registered_family_keys():
        adapter = registry_module.get_family_adapter(family_key)
        monkeypatch.setitem(
            registry_module._registry, family_key, replace(adapter, build_live_panel=_explode)
        )
    # The detonator is really armed on the adapters the registration path
    # resolves — without this the test could pass by patching nothing.
    assert all(
        registry_module.get_family_adapter(k).build_live_panel is _explode
        for k in registry_module.registered_family_keys()
    )

    outcomes = patch_startup_session.register_quality_forward_validations_once()
    assert len(outcomes) == 2
    assert all("CREATED" in line for line in outcomes)


# --- J: the short-interest registration (2026-09-02) ------------------------
#
# short_interest_ratio / si_ratio_hedged_h21 is the THIRD individually
# registered forward hypothesis, and the first whose family's own verdict was
# an honest negative under a bar it missed by 0.002. Everything below is
# offline: build_short_interest_live_panel takes injectable provider / finra /
# sec_shares / edgar arguments for exactly this reason, and no test here
# touches the network — which matters more for this family than any other,
# since its real panel is ~209 FINRA cycle files plus ~37 SEC frames plus a
# ~690-ticker multi-year price history.

SHORT_INTEREST_FAMILY_KEY = "short_interest_ratio"
SHORT_INTEREST_PATTERN = "si_ratio_hedged_h21"
# 120, not the quality suite's 60: this family's rank_fraction is the paper's
# 5% tail, so a 60-name cross-section would give 3-name legs and be refused by
# the harness's DEFAULT_MIN_NAMES_PER_LEG floor of 5 before ranking anything.
N_SHORT_INTEREST_TICKERS = 120


@pytest.fixture(autouse=True)
def reset_short_interest_live_state(monkeypatch):
    """The short-interest adapter carries one piece of module state, its
    per-`end` panel memo. Rebind it per test so no test can see another's
    (a memo built from fakes leaking into a later test would be worse than
    useless), and so monkeypatch restores production's afterwards."""
    monkeypatch.setattr(registry_module, "_SHORT_INTEREST_PANEL_MEMO", {})


class _FakeFinra:
    """FinraShortInterestProvider.fetch_observations_for_tickers' contract:
    (ticker -> chronological observations, diagnostics)."""

    def __init__(self, observations: dict, error: Exception | None = None):
        self.observations = observations
        self.error = error
        self.calls = 0
        self.window: tuple[date, date] | None = None

    def fetch_observations_for_tickers(self, tickers, start, end):
        from app.services.market_data.finra_short_interest_provider import (
            ShortInterestFetchDiagnostics,
        )

        self.calls += 1
        self.window = (start, end)
        if self.error is not None:
            raise self.error
        return (
            {t: self.observations.get(t, []) for t in tickers},
            ShortInterestFetchDiagnostics(),
        )


class _FakeSecShares:
    """SecSharesOutstandingProvider.fetch_share_counts' contract."""

    def __init__(self, share_counts: dict, error: Exception | None = None):
        self.share_counts = share_counts
        self.error = error
        self.calls = 0
        self.ciks_asked: dict = {}

    def fetch_share_counts(self, ticker_to_cik, start, end, *, missing_from_map=()):
        from app.services.market_data.sec_shares_outstanding_provider import (
            ShareCountDiagnostics,
        )

        self.calls += 1
        self.ciks_asked = dict(ticker_to_cik)
        if self.error is not None:
            raise self.error
        diagnostics = ShareCountDiagnostics()
        diagnostics.tickers_without_cik = sorted(missing_from_map)
        return {t: self.share_counts.get(t, []) for t in ticker_to_cik}, diagnostics


class _FakeShortInterestEdgar:
    """The one EdgarXbrlProvider method this family's live panel calls."""

    def __init__(self, cik_map: dict):
        self.cik_map = cik_map
        self.calls = 0

    def get_ticker_cik_map(self):
        self.calls += 1
        return self.cik_map


def _short_interest_members(n: int, today: date) -> list[str]:
    """The first `n` names of the family's OWN point-in-time union universe
    that were index members today — so the real was_member gate the adapter
    installs actually admits them."""
    from app.services.research_lab.cross_sectional_short_interest import (
        SHORT_INTEREST_FORMATION_START,
    )
    from app.services.research_lab.sp500_membership_history import (
        get_universe_over,
        was_member,
    )

    universe = get_universe_over(SHORT_INTEREST_FORMATION_START, today)
    return [t for t in universe if was_member(t, today)][:n]


def _short_interest_offline_panel_inputs(n_tickers: int = N_SHORT_INTEREST_TICKERS):
    """(tickers, fake yfinance, fake finra, fake sec-shares, fake edgar) for
    the REAL live-panel builder.

    Every ticker gets two FINRA cycles inside the family's 45-day staleness
    bound and one share count inside the 400-day one, with short shares
    dispersed across names so the ranking has something to separate them on.
    The ratio and the days-to-cover are deliberately given DIFFERENT orderings
    (average daily volume rises with i faster than short shares do), so a test
    can tell which of the two panels the builder actually served."""
    from app.services.market_data.finra_short_interest_provider import (
        ShortInterestObservation,
    )
    from app.services.market_data.sec_shares_outstanding_provider import (
        ShareCountObservation,
    )

    today = _today()
    tickers = _short_interest_members(n_tickers, today)
    assert len(tickers) == n_tickers, f"only {len(tickers)} union names are members today"

    dates = pd.bdate_range(end=pd.Timestamp(today) - pd.Timedelta(days=1), periods=120)
    rng = np.random.default_rng(7)
    close = pd.DataFrame(
        {t: 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, len(dates)))) for t in tickers},
        index=dates,
    )

    observations = {}
    share_counts = {}
    for i, ticker in enumerate(tickers):
        observations[ticker] = [
            ShortInterestObservation(
                symbol=ticker,
                settlement_date=today - timedelta(days=44),
                available=today - timedelta(days=30),
                short_shares=100_000.0 * (i + 1),
                average_daily_volume=1_000_000.0 + 50_000.0 * i,
                market_class="NYSE",
            ),
            ShortInterestObservation(
                symbol=ticker,
                settlement_date=today - timedelta(days=24),
                available=today - timedelta(days=10),
                short_shares=110_000.0 * (i + 1),
                average_daily_volume=1_000_000.0 + 50_000.0 * i,
                market_class="NYSE",
            ),
        ]
        share_counts[ticker] = [
            ShareCountObservation(
                as_of=today - timedelta(days=290),
                available=today - timedelta(days=200),
                shares=100_000_000.0,
            )
        ]

    return (
        tickers,
        _FakeYFinance(close),
        _FakeFinra(observations),
        _FakeSecShares(share_counts),
        _FakeShortInterestEdgar({t: 1000 + i for i, t in enumerate(tickers)}),
    )


def _build_short_interest_panel(fakes, end: date | None = None):
    _tickers, fake_yf, fake_finra, fake_shares, fake_edgar = fakes
    return registry_module.build_short_interest_live_panel(
        end if end is not None else _today(),
        provider=fake_yf,
        finra=fake_finra,
        sec_shares=fake_shares,
        edgar=fake_edgar,
    )


# --- J.1: the reference-not-copy contract ----------------------------------


def test_short_interest_adapter_resolves_the_familys_own_production_spec():
    """The registration must resolve to the SAME spec object the 2026-09-02
    production screening ran — not an approximation typed into a registration
    module."""
    from app.services.research_lab.cross_sectional_short_interest import (
        build_short_interest_family,
        default_short_interest_config,
    )

    adapter, spec = resolve_spec(SHORT_INTEREST_FAMILY_KEY, SHORT_INTEREST_PATTERN)
    direct = next(
        s for s in build_short_interest_family() if s.pattern_id == SHORT_INTEREST_PATTERN
    )
    assert spec_fingerprint(spec) == spec_fingerprint(direct)
    assert config_fingerprint(adapter.build_config()) == config_fingerprint(
        default_short_interest_config()
    )

    # The REAL production parameters of the registered cell: the paper's own
    # measure x the paper's own long-side reading x the paper's own monthly
    # rebalance, at the paper's own 5th-percentile cutoff.
    assert spec.family == "short_interest"
    assert (spec.holding_days, spec.lookback_days, spec.rank_fraction) == (21, 1, 0.05)
    assert spec.portfolio == "long_universe_hedged"
    assert spec.leg_weighting == "magnitude"
    assert spec.cohort_formation_days is None
    assert spec.requires_fundamental_signal is True
    assert adapter.module_path == "app/services/research_lab/cross_sectional_short_interest.py"
    # 12, NOT the 6 pattern_ids this key exposes: the family screened both
    # normalizer halves under one pre-declared denominator, which is what the
    # persisted trial rows record.
    assert adapter.n_trials == 12


def test_short_interest_adapter_exposes_only_the_ratio_half():
    """THE SAFETY PROPERTY behind the family_key. Both normalizers' signals
    read CrossSectionalData.fundamental_signal, and which quantity that slot
    holds is DATA — invisible to spec_identity, config_identity and every
    drift check. An adapter serving the ratio panel while exposing the
    days-to-cover pattern_ids would tick them on the wrong variable forever,
    with a matching fingerprint on every tick. So they do not resolve at
    all."""
    adapter = registry_module.get_family_adapter(SHORT_INTEREST_FAMILY_KEY)
    pattern_ids = sorted(s.pattern_id for s in adapter.build_specs())
    assert pattern_ids == [
        "si_ratio_hedged_h126",
        "si_ratio_hedged_h21",
        "si_ratio_hedged_h63",
        "si_ratio_ls_h126",
        "si_ratio_ls_h21",
        "si_ratio_ls_h63",
    ]
    for days_to_cover_spec in ("si_dtc_hedged_h63", "si_dtc_ls_h63", "si_dtc_hedged_h21"):
        with pytest.raises(registry_module.UnknownCrossSectionalSpecError):
            resolve_spec(SHORT_INTEREST_FAMILY_KEY, days_to_cover_spec)


def test_short_interest_spec_is_forward_tickable():
    """Refused configurations raise at REGISTRATION time, never mid-tick —
    so this is checked before a 126-day clock can start."""
    adapter, spec = resolve_spec(SHORT_INTEREST_FAMILY_KEY, SHORT_INTEREST_PATTERN)
    validate_spec_is_forward_tickable(spec, adapter.build_config())
    # The day floor binds, not the two-hold rule: 2 x 21 = 42 < 126.
    assert graduation_threshold_for(spec) == MIN_FORWARD_VALIDATION_TRADING_DAYS == 126
    assert MIN_FORWARD_COMPLETE_HOLDS * spec.holding_days == 42


# --- J.2: the live panel builder -------------------------------------------


def test_short_interest_live_panel_serves_the_RATIO_not_days_to_cover():
    """The single most important property of this adapter. Both panels are
    built by the family's own build_short_interest_panels; the ranked one
    must be short shares / SHARES OUTSTANDING — the paper's own measure and
    the one this registration is about — not short shares / average daily
    volume, which the family's own diagnostic found is substantially a
    trading-volume sort."""
    from app.services.research_lab.sp500_membership_history import was_member

    fakes = _short_interest_offline_panel_inputs()
    tickers, fake_yf, _finra, _shares, _edgar = fakes
    panel = _build_short_interest_panel(fakes)

    assert panel.n_tickers == N_SHORT_INTEREST_TICKERS
    assert panel.last_row_date == fake_yf.close.index[-1].date()
    assert panel.membership_fn is was_member
    assert panel.data.leg_weight_basis is None  # "magnitude" weighting ranks on the signal itself

    newest = panel.data.fundamental_signal.iloc[-1]
    assert newest.notna().all()
    for i, ticker in enumerate(tickers[:5]):
        # The newest visible cycle's short shares over the point-in-time
        # share count — NOT that cycle's days-to-cover.
        assert newest[ticker] == pytest.approx(110_000.0 * (i + 1) / 100_000_000.0)
        days_to_cover = 110_000.0 * (i + 1) / (1_000_000.0 + 50_000.0 * i)
        assert newest[ticker] != pytest.approx(days_to_cover)
    assert list(panel.data.fundamental_signal.columns) == list(panel.data.close.columns)
    assert panel.data.fundamental_signal.index.equals(panel.data.close.index)


def test_short_interest_live_panel_applies_the_common_cross_section_mask():
    """A name with no point-in-time share count carries no RATIO, and the
    family's mask then refuses it from BOTH panels rather than letting the
    two normalizer halves rank different universes. The live panel inherits
    that because it calls the family's own builder."""
    fakes = _short_interest_offline_panel_inputs()
    tickers, _yf, _finra, fake_shares, _edgar = fakes
    fake_shares.share_counts[tickers[0]] = []

    panel = _build_short_interest_panel(fakes)
    signal = panel.data.fundamental_signal
    assert signal[tickers[0]].isna().all()
    assert signal[tickers[1]].iloc[-1] == pytest.approx(110_000.0 * 2 / 100_000_000.0)


def test_short_interest_live_panel_asks_its_providers_for_the_familys_own_windows():
    """The live builder is run_short_interest_screening's data-preparation
    block, not a re-derivation of it: the FINRA fetch starts at the family's
    own cycle-fetch constant and only CIK-resolvable priced names reach the
    share-count fetch."""
    from app.services.research_lab.cross_sectional_short_interest import (
        SHORT_INTEREST_CYCLE_FETCH_START,
    )

    fakes = _short_interest_offline_panel_inputs()
    tickers, _yf, fake_finra, fake_shares, fake_edgar = fakes
    del fake_edgar.cik_map[tickers[0]]  # a name SEC's current-day map cannot resolve

    _build_short_interest_panel(fakes)
    assert fake_finra.window == (SHORT_INTEREST_CYCLE_FETCH_START, _today())
    assert tickers[0] not in fake_shares.ciks_asked
    assert len(fake_shares.ciks_asked) == N_SHORT_INTEREST_TICKERS - 1


def test_short_interest_live_specs_can_form_a_real_book_on_the_live_panel():
    """End to end: the family's own spec ranks the live cross-section and
    produces a long tail hedged against the eligible universe."""
    from app.services.research_lab.cross_sectional import form_portfolio

    fakes = _short_interest_offline_panel_inputs()
    panel = _build_short_interest_panel(fakes)
    adapter, spec = resolve_spec(SHORT_INTEREST_FAMILY_KEY, SHORT_INTEREST_PATTERN)
    config = adapter.build_config()

    outcome = form_portfolio(
        panel.data, spec, config, panel.membership_fn, len(panel.data.close.index) - 1, {}
    )
    assert outcome.record.skipped_reason is None
    # The 5% LOW tail is long; the hedge is the whole eligible universe.
    assert len(outcome.long_weights) >= config.min_names_per_leg
    assert len(outcome.realized_short_weights) > len(outcome.long_weights)
    tickers = fakes[0]
    assert set(outcome.long_weights) <= set(tickers[:12])  # the smallest ratios, by construction


def test_short_interest_live_panel_refuses_an_empty_price_panel():
    fakes = _short_interest_offline_panel_inputs()
    fakes[1].close = pd.DataFrame()
    with pytest.raises(registry_module.CrossSectionalPanelUnavailableError):
        _build_short_interest_panel(fakes)


def test_short_interest_live_panel_refuses_a_panel_that_can_rank_nothing():
    """A share-count outage leaves an all-NaN ratio panel. Ticking on it
    would hold an empty book realizing exactly 0.0 every day — an outage
    written into the track record as flat performance."""
    fakes = _short_interest_offline_panel_inputs()
    fakes[3].share_counts = {}
    with pytest.raises(registry_module.CrossSectionalPanelUnavailableError):
        _build_short_interest_panel(fakes)


@pytest.mark.parametrize("broken", ["finra", "sec_shares"])
def test_short_interest_live_panel_translates_a_vendor_outage_into_panel_unavailable(broken):
    """A vendor failure means "no data this tick, retry in half an hour",
    which is exactly CrossSectionalPanelUnavailableError's contract — and the
    runner catches that one specifically, leaving the registration untouched
    rather than logging an unhandled provider error."""
    from app.services.market_data.finra_short_interest_provider import (
        FinraShortInterestFetchError,
    )
    from app.services.market_data.sec_shares_outstanding_provider import (
        SecSharesFetchError,
    )

    fakes = _short_interest_offline_panel_inputs()
    if broken == "finra":
        fakes[2].error = FinraShortInterestFetchError("simulated FINRA outage")
    else:
        fakes[3].error = SecSharesFetchError("simulated SEC frames outage")

    with pytest.raises(registry_module.CrossSectionalPanelUnavailableError) as excinfo:
        _build_short_interest_panel(fakes)
    assert "simulated" in str(excinfo.value)


def test_short_interest_live_panel_is_memoized_per_end_date():
    """The runner keeps a family pending all day after its one real row is
    processed, so it calls build_live_panel ~47 more times for the same
    `end`. Each rebuild here is ~209 FINRA files plus ~37 SEC frames plus a
    ~690-ticker multi-year price history, and cannot return anything
    different."""
    fakes = _short_interest_offline_panel_inputs()
    _tickers, fake_yf, fake_finra, fake_shares, fake_edgar = fakes
    today = _today()

    first = _build_short_interest_panel(fakes, today)
    second = _build_short_interest_panel(fakes, today)
    assert second is first
    assert (fake_yf.calls, fake_finra.calls, fake_shares.calls, fake_edgar.calls) == (1, 1, 1, 1)

    # A new UTC day always rebuilds.
    _build_short_interest_panel(fakes, today + timedelta(days=1))
    assert (fake_yf.calls, fake_finra.calls) == (2, 2)


def test_short_interest_live_share_count_provider_is_constructed_with_the_cache_bound():
    """Production passes no providers, so the ONE thing that keeps the SEC
    frames cache from freezing the share-count denominator is that the
    builder constructs a bounded provider by default. Asserted on a real
    build with only the network-touching halves faked out."""
    from app.services.market_data.sec_shares_outstanding_provider import (
        VISIBILITY_LAG_DAYS,
        SecSharesOutstandingProvider,
    )

    constructed: list[SecSharesOutstandingProvider] = []
    real_provider_cls = registry_module.SecSharesOutstandingProvider

    def _capturing(*args, **kwargs):
        provider = real_provider_cls(*args, **kwargs)
        constructed.append(provider)
        return provider

    fakes = _short_interest_offline_panel_inputs()
    _tickers, fake_yf, fake_finra, _fake_shares, fake_edgar = fakes
    try:
        registry_module.SecSharesOutstandingProvider = _capturing  # type: ignore[misc]
        # sec_shares deliberately NOT injected, so the default is constructed.
        with pytest.raises(registry_module.CrossSectionalPanelUnavailableError):
            registry_module.build_short_interest_live_panel(
                _today(), provider=fake_yf, finra=fake_finra, edgar=fake_edgar
            )
    finally:
        registry_module.SecSharesOutstandingProvider = real_provider_cls  # type: ignore[misc]

    assert len(constructed) == 1
    assert (
        constructed[0].max_cache_age_days
        == registry_module.SHORT_INTEREST_LIVE_FRAME_MAX_CACHE_AGE_DAYS
        == 7
    )
    # The bound only has to be much shorter than the 90-day visibility lag —
    # a record this project may not read for 90 days does not need same-day
    # pickup, it needs to not be frozen out entirely.
    assert registry_module.SHORT_INTEREST_LIVE_FRAME_MAX_CACHE_AGE_DAYS < VISIBILITY_LAG_DAYS


def test_short_interest_live_edgar_provider_is_the_bounded_one():
    """The ticker->CIK map is one of the two MUTABLE EDGAR caches: frozen, it
    would keep a newly added index member out of the share-count denominator
    (and so out of the ranked cross-section) indefinitely."""
    assert registry_module._live_edgar_provider().max_cache_age_days == 1


def test_sec_frames_cache_is_unbounded_by_default_and_bounded_on_request(tmp_path):
    """Default (every backtest, every existing caller): a cached frame is
    served forever, so a re-run reads the identical bytes its persisted
    numbers were computed from. With max_cache_age_days set — which is what
    the live short-interest panel constructs — an aged file is refetched,
    because the frame of the quarter currently IN PROGRESS is first requested
    when it is nearly empty and would otherwise be served in that state
    forever."""
    from app.services.market_data.sec_shares_outstanding_provider import (
        SecSharesOutstandingProvider,
    )

    cached = tmp_path / "CY2026Q3I.json"
    cached.write_text(json.dumps({"data": [{"cik": 1, "end": "2026-07-01", "val": 5.0}]}))
    old = time.time() - 30 * 86_400
    os.utime(cached, (old, old))

    unbounded = SecSharesOutstandingProvider(cache_dir=tmp_path)
    unbounded._session = None  # any network use would raise AttributeError
    assert unbounded.fetch_frame(2026, 3)["data"][0]["val"] == 5.0

    bounded = SecSharesOutstandingProvider(cache_dir=tmp_path, max_cache_age_days=7)

    class _Response:
        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {"data": [{"cik": 1, "end": "2026-08-01", "val": 9.0}]}

    class _Session:
        def __init__(self) -> None:
            self.headers: dict = {}

        def get(self, _url, timeout=None):
            return _Response()

    bounded._session = _Session()
    bounded._sleep = lambda _seconds: None
    assert bounded.fetch_frame(2026, 3)["data"][0]["val"] == 9.0
    # The refetch rewrote the cache, so it is fresh again and is now served.
    assert json.loads(cached.read_text())["data"][0]["val"] == 9.0
    bounded._session = None
    assert bounded.fetch_frame(2026, 3)["data"][0]["val"] == 9.0


# --- J.3: the registration row ---------------------------------------------


def _assert_short_interest_registration_shape(registration, created, today):
    """Asserted inside the caller's open session — every attribute below is a
    lazy-loadable ORM column, and reading one off a detached instance raises
    rather than returning the value."""
    assert created
    assert (registration.family_key, registration.pattern_id) == (
        SHORT_INTEREST_FAMILY_KEY,
        "si_ratio_hedged_h21",
    )
    assert registration.spec_family == "short_interest"
    assert registration.family_n_trials == 12
    assert registration.module_path == "app/services/research_lab/cross_sectional_short_interest.py"
    assert registration.status == "in_progress"
    assert registration.n_forward_trading_days == 0
    assert registration.n_formations == 0
    # max(the pairs floor of 126, 2 x holding_days=21) — the FLOOR binds here,
    # so this row graduates on six completed monthly formations, not two.
    assert registration.min_trading_days_threshold == 126

    # The REAL production parameters, snapshotted from the family's own spec.
    spec_snapshot = json.loads(registration.spec_snapshot_json)
    assert spec_snapshot["holding_days"] == 21
    assert spec_snapshot["lookback_days"] == 1
    assert spec_snapshot["rank_fraction"] == 0.05
    assert spec_snapshot["portfolio"] == "long_universe_hedged"
    assert spec_snapshot["leg_weighting"] == "magnitude"
    assert spec_snapshot["cohort_formation_days"] is None
    assert spec_snapshot["family"] == "short_interest"

    config_snapshot = json.loads(registration.config_snapshot_json)
    assert config_snapshot["cost_bps"] == 5.0
    assert config_snapshot["financing_bps_per_year"] == 0.0
    assert config_snapshot["periods_per_year"] == 252  # equities, not crypto's 365
    assert config_snapshot["impute_delisting_returns"] is False

    assert len(registration.spec_fingerprint) == 64
    assert len(registration.config_fingerprint) == 64
    assert today <= registration.started_at <= today + timedelta(days=1)
    assert registration.last_processed_date is None
    assert json.loads(registration.day_results_json) == []
    state = deserialize_cross_sectional_forward_state(json.loads(registration.carry_state_json))
    assert (state.equity, state.n_formations, state.rows_since_formation) == (1.0, 0, None)


def test_short_interest_registration_uses_the_real_production_spec(
    test_db_engine, register_and_verify, client
):
    from app.services.research_lab.short_interest_forward_registration import (
        SHORT_INTEREST_PATTERN_ID,
        register_short_interest_forward_validation,
    )

    assert SHORT_INTEREST_PATTERN_ID == SHORT_INTEREST_PATTERN
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    today = _today()
    with session_local() as db:
        registration, created = register_short_interest_forward_validation(db, user["id"])
        _assert_short_interest_registration_shape(registration, created, today)


def test_short_interest_registration_rationale_discloses_what_it_must(
    test_db_engine, register_and_verify, client
):
    """A forward slot is a claim on real calendar time. This row must say on
    its own face that its family returned a negative, what its own DSR and
    denominator were, WHY a lower-scoring spec was registered instead of the
    family's best, that it is still a selection, and that there are now three
    live registrations — not leave any of it to a docstring."""
    from app.services.research_lab.short_interest_forward_registration import (
        register_short_interest_forward_validation,
    )

    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration, _created = register_short_interest_forward_validation(db, user["id"])
        rationale = registration.registration_rationale

    assert "NOT AN AUTOMATIC ONE" in rationale
    assert "NOT A CLAIM OF VALIDATED EDGE" in rationale
    assert "HONEST NEGATIVE" in rationale
    # Its own numbers, and the denominator they were deflated against.
    assert "0.7962" in rationale
    assert "12-trial denominator" in rationale
    assert "2,169 realized" in rationale
    # The volume confound is the entire reason this spec and not the best one.
    assert "72.7th" in rationale and "33.2nd" in rationale
    assert "sorting on low days-to-cover is substantially sorting on high volume" in rationale
    assert "IT IS STILL A SELECTION" in rationale
    assert "DEPARTS from the family" in rationale
    # How to read it, and what it costs the other two rows.
    assert "graduation means ONLY" in rationale
    assert "SIX completed monthly formations" in rationale
    assert "negative forward result is a real result" in rationale
    assert "THREE LIVE REGISTRATIONS" in rationale
    assert "selection over three" in rationale


def test_short_interest_registration_is_idempotent_and_never_resets_progress(
    test_db_engine, register_and_verify, client
):
    from app.services.research_lab.short_interest_forward_registration import (
        register_short_interest_forward_validation,
    )

    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        first, created = register_short_interest_forward_validation(db, user["id"])
        assert created
        registration_id = first.id

        first.n_forward_trading_days = 40  # accumulated progress to protect
        first.n_formations = 2
        db.commit()

        again, created_again = register_short_interest_forward_validation(db, user["id"])
        assert created_again is False
        assert again.id == registration_id
        assert again.n_forward_trading_days == 40
        assert again.n_formations == 2
        assert db.query(CrossSectionalForwardValidationRegistration).count() == 1


def test_short_interest_registration_is_a_distinct_row_from_the_quality_ones(
    test_db_engine, register_and_verify, client
):
    """Three registrations, three rows, three config hashes — and the listing
    endpoint surfaces all three as system rows, because 'the best of the
    three' is a selection over three and the losers may never be dropped."""
    from app.services.research_lab.quality_forward_registration import (
        register_quality_forward_validations,
    )
    from app.services.research_lab.short_interest_forward_registration import (
        register_short_interest_forward_validation,
    )
    from app.services.research_lab.system_account import get_or_create_system_user

    register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        system_user = get_or_create_system_user(db)
        register_quality_forward_validations(db, system_user.id)
        register_short_interest_forward_validation(db, system_user.id)
        hashes = {
            r.config_hash
            for r in db.query(CrossSectionalForwardValidationRegistration).all()
        }
        assert len(hashes) == 3

    listing = client.get("/api/cross-sectional-forward-validation")
    assert listing.status_code == 200
    rows = {r["pattern_id"]: r for r in listing.json()}
    assert set(rows) == {"cbop_ls_h63", "noa_neutral_ls_h126_median", "si_ratio_hedged_h21"}
    assert all(r["is_system"] for r in rows.values())
    assert rows["si_ratio_hedged_h21"]["holding_days"] == 21
    assert rows["si_ratio_hedged_h21"]["periods_per_year"] == 252
    assert rows["si_ratio_hedged_h21"]["sharpe_forward_so_far"] is None


def test_families_endpoint_lists_the_short_interest_ratio_family(client, register_and_verify):
    """The /families listing must stay cheap — build_specs for this family
    touches no data at all, which is what keeps an authenticated GET from
    turning into a 209-file FINRA fetch."""
    register_and_verify(client)
    response = client.get("/api/cross-sectional-forward-validation/families")
    assert response.status_code == 200
    families = {f["family_key"]: f for f in response.json()}
    family = families[SHORT_INTEREST_FAMILY_KEY]
    assert family["n_trials"] == 12
    assert len(family["pattern_ids"]) == 6
    assert SHORT_INTEREST_PATTERN in family["pattern_ids"]
    assert not any(p.startswith("si_dtc") for p in family["pattern_ids"])
    assert family["module_path"] == "app/services/research_lab/cross_sectional_short_interest.py"
    assert "point-in-time S&P 500 UNION" in family["universe_rule"]
    assert "FLATTERS THE RESULTS" in family["universe_rule"]


# --- J.4: the app-startup registration path --------------------------------


@pytest.fixture
def patch_short_interest_startup_session(test_db_engine, monkeypatch):
    """The startup step opens its own SessionLocal (it has no request to take
    a get_db session from), exactly like every runner — so point that module
    attribute at the test engine."""
    from app.services.research_lab import (
        short_interest_forward_registration as startup_module,
    )

    monkeypatch.setattr(
        startup_module,
        "SessionLocal",
        sessionmaker(bind=test_db_engine, autoflush=False, autocommit=False),
    )
    return startup_module


SHORT_INTEREST_STARTUP_LOGGER_NAME = (
    "app.services.research_lab.short_interest_forward_registration"
)


def _short_interest_startup_log_lines(caplog) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == SHORT_INTEREST_STARTUP_LOGGER_NAME
    ]


def test_short_interest_startup_registration_creates_the_row_when_absent(
    test_db_engine, patch_short_interest_startup_session
):
    outcomes = patch_short_interest_startup_session.register_short_interest_forward_validation_once()

    assert len(outcomes) == 1
    assert "CREATED" in outcomes[0]
    assert "family_key=short_interest_ratio pattern_id=si_ratio_hedged_h21" in outcomes[0]
    assert "status=in_progress" in outcomes[0]
    assert "threshold=126" in outcomes[0]

    from app.services.research_lab.system_account import get_or_create_system_user

    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        rows = db.query(CrossSectionalForwardValidationRegistration).all()
        assert [r.pattern_id for r in rows] == ["si_ratio_hedged_h21"]
        # The system-account ownership convention, not a human's user_id.
        system_user_id = get_or_create_system_user(db).id
        assert rows[0].user_id == system_user_id
        assert f"id={rows[0].id} " in outcomes[0]
        assert f"user_id={system_user_id} " in outcomes[0]


def test_short_interest_startup_registration_no_ops_when_the_row_already_exists(
    test_db_engine, patch_short_interest_startup_session
):
    """The property that matters most on a host that restarts the process on
    every deploy and every wake-from-sleep: a second run must find, not
    recreate, and must not touch an accumulated clock."""
    first = patch_short_interest_startup_session.register_short_interest_forward_validation_once()
    assert "CREATED" in first[0]

    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        row = db.query(CrossSectionalForwardValidationRegistration).one()
        row_id = row.id
        row.n_forward_trading_days = 40  # accumulated progress to protect
        db.commit()

    second = patch_short_interest_startup_session.register_short_interest_forward_validation_once()
    assert "ALREADY EXISTS" in second[0]
    assert f"id={row_id} " in second[0]
    assert "n_forward_trading_days=40" in second[0]

    with session_local() as db:
        assert db.query(CrossSectionalForwardValidationRegistration).count() == 1
        assert (
            db.get(CrossSectionalForwardValidationRegistration, row_id).n_forward_trading_days
            == 40
        )


@pytest.mark.asyncio
async def test_short_interest_startup_wrapper_logs_created_then_already_exists(
    test_db_engine, patch_short_interest_startup_session, caplog
):
    """The async wrapper main.py actually awaits — both passes, through the
    real logging module, at the level and with the fields a reader of Render's
    log viewer would grep for."""
    module = patch_short_interest_startup_session
    with caplog.at_level(logging.INFO, logger=SHORT_INTEREST_STARTUP_LOGGER_NAME):
        await module.register_short_interest_forward_validation_on_startup()
        created_lines = _short_interest_startup_log_lines(caplog)
        caplog.clear()
        await module.register_short_interest_forward_validation_on_startup()
        second_lines = _short_interest_startup_log_lines(caplog)

    assert len(created_lines) == 1 and "CREATED" in created_lines[0]
    assert len(second_lines) == 1 and "ALREADY EXISTS" in second_lines[0]

    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        assert db.query(CrossSectionalForwardValidationRegistration).count() == 1


@pytest.mark.parametrize(
    ("broken", "expected_in_traceback"),
    [
        ("session_factory", "simulated database outage at startup"),
        ("registration", "simulated failure mid-registration"),
    ],
)
@pytest.mark.asyncio
async def test_short_interest_startup_wrapper_never_raises_and_logs_the_failure(
    test_db_engine,
    patch_short_interest_startup_session,
    monkeypatch,
    caplog,
    broken,
    expected_in_traceback,
):
    """A failure on one process start must not take the API down with it —
    lifespan awaits this directly, so anything escaping here would abort
    startup entirely."""
    module = patch_short_interest_startup_session
    if broken == "session_factory":

        def _broken_session_factory():
            raise RuntimeError("simulated database outage at startup")

        monkeypatch.setattr(module, "SessionLocal", _broken_session_factory)
    else:

        def _broken_registration(*args, **kwargs):
            raise RuntimeError("simulated failure mid-registration")

        monkeypatch.setattr(
            module, "register_short_interest_forward_validation", _broken_registration
        )

    with caplog.at_level(logging.ERROR, logger=SHORT_INTEREST_STARTUP_LOGGER_NAME):
        result = await module.register_short_interest_forward_validation_on_startup()

    assert result is None  # returned normally; nothing propagated
    failures = [r for r in caplog.records if r.name == SHORT_INTEREST_STARTUP_LOGGER_NAME]
    assert len(failures) == 1
    assert failures[0].levelno == logging.ERROR
    assert "failed on startup" in failures[0].getMessage()
    assert failures[0].exc_info is not None
    assert expected_in_traceback in caplog.text

    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        assert db.query(CrossSectionalForwardValidationRegistration).count() == 0


def test_short_interest_startup_registration_never_builds_a_live_panel(
    patch_short_interest_startup_session, monkeypatch
):
    """Startup must not touch FINRA, SEC or yfinance. This family's live
    panel is by far the heaviest in the project (~209 cycle files, ~37 SEC
    frames, ~690 tickers of multi-year history), so a cold boot that built it
    would read as a hung deploy to Render's health check. Every registered
    family's live-panel builder is replaced with a detonator; none may fire.

    Deliberately the SYNC entry point, not the never-raising async wrapper —
    the wrapper would catch the detonator's AssertionError and log it, and the
    test would pass vacuously."""

    def _explode(*args, **kwargs):
        raise AssertionError("startup registration built a live panel (network fetch)")

    for family_key in registry_module.registered_family_keys():
        adapter = registry_module.get_family_adapter(family_key)
        monkeypatch.setitem(
            registry_module._registry, family_key, replace(adapter, build_live_panel=_explode)
        )
    assert (
        registry_module.get_family_adapter(SHORT_INTEREST_FAMILY_KEY).build_live_panel is _explode
    )

    outcomes = (
        patch_short_interest_startup_session.register_short_interest_forward_validation_once()
    )
    assert len(outcomes) == 1
    assert "CREATED" in outcomes[0]


# --- J.5: the equivalence property of section D, on THIS registered spec ----


def test_the_real_short_interest_spec_ticks_forward_identically_to_the_batch_harness():
    """Section D's equivalence property, run on the ACTUAL registered
    strategy: si_ratio_hedged_h21's real signal, its real 5%-tail rank
    fraction, its real 21-row hold and the real short-interest config.

    This one earns its own test rather than riding on the BAB and synthetic
    versions, because si_ratio_hedged_h21 is the FIRST long_universe_hedged
    spec this project has ever ticked forward — every previously registered
    spec is long_short. The hedge leg is an equal-weighted basket of the whole
    eligible cross-section rather than a ranked tail, so its turnover and its
    drop-and-renormalize behavior are a genuinely different path through
    form_portfolio and realize_formation_day.

    Prices and the ratio panel are synthetic — tests must never depend on
    live data — but the STRATEGY is production."""
    _adapter, spec = resolve_spec(SHORT_INTEREST_FAMILY_KEY, SHORT_INTEREST_PATTERN)
    config = _adapter.build_config()
    assert spec.portfolio == "long_universe_hedged"

    rng = np.random.default_rng(23)
    n_rows = 200
    tickers = [f"S{i:03d}" for i in range(120)]  # 5% of 120 = 6 names, above the floor of 5
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n_rows)
    close = pd.DataFrame(
        {t: 100.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.015, n_rows))) for t in tickers},
        index=dates,
    )
    # A bi-monthly STEP panel, as the real short-interest panel is: the
    # ranking variable refreshes roughly twice a month and is held flat in
    # between, so consecutive formations really do re-rank on new values.
    ratio = pd.DataFrame(index=dates, columns=tickers, dtype=float)
    for block_start in range(0, n_rows, 11):
        ratio.iloc[block_start : block_start + 11] = rng.uniform(0.005, 0.12, len(tickers))

    membership = fixed_universe_membership(tickers)
    data_full = CrossSectionalData(close=close, fundamental_signal=ratio)

    start = spec.lookback_days
    batch_config = _adapter.build_config()
    batch_config.formation_start = close.index[start].date()
    batch = run_cross_sectional_backtest(data_full, spec, batch_config, membership)
    assert batch.status == "ok"

    state = CrossSectionalForwardState()
    last_processed: date | None = None
    forward_returns: dict[pd.Timestamp, float] = {}
    for row in range(start, n_rows):
        panel = CrossSectionalData(
            close=close.iloc[: row + 1], fundamental_signal=ratio.iloc[: row + 1]
        )
        state, results = advance_forward_validation(
            panel, spec, config, membership, state, last_processed
        )
        for day_result in results:
            if day_result.realized:
                forward_returns[day_result.date] = day_result.net_return
        if results:
            last_processed = results[-1].date.date()

    batch_returns = {ts: float(v) for ts, v in batch.daily_returns.items()}
    assert len(batch_returns) > 150
    assert set(forward_returns) == set(batch_returns)
    for ts, batch_value in batch_returns.items():
        assert forward_returns[ts] == pytest.approx(batch_value, abs=1e-12), f"mismatch on {ts}"

    # The real spec really did exercise its monthly cadence several times over
    # — the whole point of a 21-day hold reaching graduation in six formations.
    assert state.n_formations >= 6


# --- K: the lazy_prices registration (2026-09-03) ---------------------------
#
# lazy_prices_jaccard_full / lazy_jaccard_full_h126_ivol is the FOURTH
# individually registered forward hypothesis, and the first from a text/NLP
# family. Everything below is offline: build_lazy_prices_live_panel takes
# injectable provider / text_provider arguments for exactly this reason, and
# no test here touches the network — which matters more for this family than
# any other, since its real panel is ~7,798 real 10-K documents (this
# project's single most expensive live fetch by a wide margin).

LAZY_PRICES_FAMILY_KEY = "lazy_prices_jaccard_full"
LAZY_PRICES_PATTERN = "lazy_jaccard_full_h126_ivol"
# 30, not a smaller number: rank_fraction=0.2 needs >= 5 names per leg
# (DEFAULT_MIN_NAMES_PER_LEG) to rank anything, i.e. >= 25 rankable names.
N_LAZY_PRICES_TICKERS = 30

_LAZY_LETTERS = "abcdefghijklmnopqrstuvwxyz"


def _lazy_token(n: int) -> str:
    """A fully-alphabetic, non-stopword token distinct for every n < 676 —
    deliberately not digit-suffixed ('tok7'): cross_sectional_lazy_prices.
    tokenize keeps only runs of >= 2 ASCII letters, so a digit suffix would be
    stripped and collapse every token into the same alphabetic stem, which
    would silently defeat this fixture's whole point (real cross-sectional
    dispersion in jaccard similarity)."""
    return f"tok{_LAZY_LETTERS[(n // 26) % 26]}{_LAZY_LETTERS[n % 26]}"


def _lazy_replacement_token(i: int, j: int) -> str:
    return f"rep{_LAZY_LETTERS[i % 26]}{_LAZY_LETTERS[j % 26]}x"


_LAZY_N_BASE_TOKENS = 120


def _lazy_previous_text() -> str:
    return " ".join(_lazy_token(n) for n in range(_LAZY_N_BASE_TOKENS))


def _lazy_current_text(n_replaced: int) -> str:
    """The previous document with its first `n_replaced` tokens swapped for
    brand-new ones — a bigger n_replaced is a bigger real vocabulary change,
    so jaccard similarity strictly decreases as n_replaced grows."""
    tokens = [_lazy_token(n) for n in range(_LAZY_N_BASE_TOKENS)]
    for j in range(n_replaced):
        tokens[j] = _lazy_replacement_token(n_replaced, j)
    return " ".join(tokens)


def _lazy_filing(cik, accession, filing_date, form="10-K", report_date=None):
    """A FilingRef whose acceptance is 10:00 UTC on filing_date — comfortably
    morning US/Eastern, so availability_date() resolves to filing_date itself
    with no cutoff-hour surprise, keeping this fixture's dates simple."""
    from datetime import UTC, datetime

    from app.services.market_data.edgar_filing_text_provider import FilingRef

    return FilingRef(
        cik=cik,
        accession=accession,
        form=form,
        filing_date=filing_date,
        acceptance_utc=datetime(
            filing_date.year, filing_date.month, filing_date.day, 10, 0, 0, tzinfo=UTC
        ).isoformat(),
        report_date=report_date,
        primary_document=f"{accession}.htm",
    )


class _FakeLazyPricesTextProvider:
    """EdgarFilingTextProvider.build_filing_index / get_filing_text's real
    contracts: ({ticker: [FilingRef]}, FilingIndexReport) and str
    respectively. Counts calls so memoization is observable without any
    network."""

    def __init__(self, filing_index: dict, texts: dict[str, str]):
        self.filing_index = filing_index
        self.texts = texts
        self.build_index_calls = 0
        self.get_text_calls = 0
        self.last_requested_tickers: list[str] = []

    def build_filing_index(self, tickers, forms=("10-K",)):
        from app.services.market_data.edgar_filing_text_provider import (
            FilingIndexReport,
        )

        self.build_index_calls += 1
        self.last_requested_tickers = list(tickers)
        index = {t: self.filing_index[t] for t in tickers if t in self.filing_index}
        return index, FilingIndexReport(
            n_tickers_requested=len(tickers),
            n_tickers_cik_resolved=len(index),
            n_tickers_indexed=len(index),
            n_filings_listed=sum(len(v) for v in index.values()),
        )

    def get_filing_text(self, filing) -> str:
        self.get_text_calls += 1
        return self.texts[filing.accession]


class _FakeYFinanceOHLCV:
    """YFinanceProvider.get_daily_ohlcv's real contract: a dict of five wide
    (dates x tickers) frames keyed open/high/low/close/volume, plus a missing
    list."""

    def __init__(self, frames: dict[str, pd.DataFrame]):
        self.frames = frames
        self.calls = 0

    def get_daily_ohlcv(self, tickers, start, end):
        self.calls += 1
        close = self.frames.get("close", pd.DataFrame())
        missing = [t for t in tickers if t not in close.columns]
        return self.frames, missing


def _lazy_prices_members(n: int, today: date) -> list[str]:
    """The first `n` names of the family's OWN point-in-time union universe
    that were index members today — so the real was_member gate the adapter
    installs actually admits them."""
    from app.services.research_lab.sp500_membership_history import (
        MEMBERSHIP_DATA_START,
        get_universe_over,
        was_member,
    )

    universe = get_universe_over(MEMBERSHIP_DATA_START, today)
    return [t for t in universe if was_member(t, today)][:n]


def _lazy_prices_offline_panel_inputs(n_tickers: int = N_LAZY_PRICES_TICKERS):
    """(tickers, fake yfinance, fake EDGAR filing-text provider) for the REAL
    live-panel builder. Every ticker gets exactly one same-type consecutive
    10-K pair, with a STRICTLY INCREASING number of replaced tokens by ticker
    index — so the resulting jaccard/full similarity panel has genuine,
    monotone cross-sectional dispersion to rank on."""
    today = _today()
    tickers = _lazy_prices_members(n_tickers, today)
    assert len(tickers) == n_tickers, f"only {len(tickers)} union names are members today"

    dates = pd.bdate_range(end=pd.Timestamp(today) - pd.Timedelta(days=1), periods=260)
    rng = np.random.default_rng(11)
    close = pd.DataFrame(
        {t: 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, len(dates)))) for t in tickers},
        index=dates,
    )
    frames = {
        "open": close.shift(1).bfill(),
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": pd.DataFrame(1_000_000.0, index=dates, columns=tickers),
    }

    filing_index: dict = {}
    texts: dict[str, str] = {}
    for i, ticker in enumerate(tickers):
        n_replaced = 2 * i + 2
        prev_accession = f"000-prev-{i:04d}"
        cur_accession = f"000-cur-{i:04d}"
        previous = _lazy_filing(
            cik=2000 + i,
            accession=prev_accession,
            filing_date=today - timedelta(days=400),
            report_date=today - timedelta(days=460),
        )
        current = _lazy_filing(
            cik=2000 + i,
            accession=cur_accession,
            filing_date=today - timedelta(days=40),
            report_date=today - timedelta(days=100),
        )
        filing_index[ticker] = [previous, current]
        texts[prev_accession] = _lazy_previous_text()
        texts[cur_accession] = _lazy_current_text(n_replaced)

    return tickers, _FakeYFinanceOHLCV(frames), _FakeLazyPricesTextProvider(filing_index, texts)


def _build_lazy_prices_panel(fakes, end: date | None = None):
    _tickers, fake_yf, fake_text = fakes
    return registry_module.build_lazy_prices_live_panel(
        end if end is not None else _today(), provider=fake_yf, text_provider=fake_text
    )


@pytest.fixture(autouse=True)
def reset_lazy_prices_live_state(monkeypatch):
    """The lazy_prices adapter carries one piece of module state, its
    per-`end` panel memo. Rebind it per test so no test can see another's (a
    memo built from fakes leaking into a later test would be worse than
    useless), and so monkeypatch restores production's afterwards."""
    monkeypatch.setattr(registry_module, "_LAZY_PRICES_PANEL_MEMO", {})


# --- K.1: the reference-not-copy contract ------------------------------------


def test_lazy_prices_adapter_resolves_the_familys_own_production_spec():
    """The registration must resolve to the SAME spec object the 2026-09-01
    production screening ran — not an approximation typed into a registration
    module."""
    from app.services.research_lab.cross_sectional_lazy_prices import (
        LAZY_PRICES_FAMILY,
        default_lazy_prices_config,
    )

    adapter, spec = resolve_spec(LAZY_PRICES_FAMILY_KEY, LAZY_PRICES_PATTERN)
    direct = next(s.spec for s in LAZY_PRICES_FAMILY if s.spec.pattern_id == LAZY_PRICES_PATTERN)
    assert spec_fingerprint(spec) == spec_fingerprint(direct)
    assert config_fingerprint(adapter.build_config()) == config_fingerprint(
        default_lazy_prices_config()
    )

    # The REAL production parameters of the registered cell: the family's own
    # best-DSR spec, taken as is (see the registration module's docstring for
    # why no deviation was made, unlike the short-interest precedent).
    assert spec.family == "lazy_prices"
    assert (spec.holding_days, spec.lookback_days, spec.rank_fraction) == (126, 1, 0.2)
    assert spec.portfolio == "long_short"
    assert spec.leg_weighting == "inverse_vol"
    assert spec.cohort_formation_days is None
    assert spec.requires_fundamental_signal is True
    assert adapter.module_path == "app/services/research_lab/cross_sectional_lazy_prices.py"
    # 36, NOT the 6 pattern_ids this key exposes: the family pools all 36
    # Sharpes into one sigma_sr before deflating any of them.
    assert adapter.n_trials == 36


def test_lazy_prices_adapter_exposes_only_the_jaccard_full_panel():
    """THE SAFETY PROPERTY behind the family_key. All 36 of this family's
    specs read CrossSectionalData.fundamental_signal, and which of the six
    similarity panels that slot holds is DATA — invisible to spec_identity,
    config_identity and every drift check. An adapter serving the jaccard/
    full panel while exposing a cosine or section-scope pattern_id would tick
    it on the wrong variable forever, with a matching fingerprint on every
    tick. So they do not resolve at all."""
    adapter = registry_module.get_family_adapter(LAZY_PRICES_FAMILY_KEY)
    pattern_ids = sorted(s.pattern_id for s in adapter.build_specs())
    assert pattern_ids == [
        "lazy_jaccard_full_h126_eq",
        "lazy_jaccard_full_h126_ivol",
        "lazy_jaccard_full_h21_eq",
        "lazy_jaccard_full_h21_ivol",
        "lazy_jaccard_full_h63_eq",
        "lazy_jaccard_full_h63_ivol",
    ]
    for other_panel_spec in (
        "lazy_cosine_full_h126_ivol",
        "lazy_jaccard_rf_h126_ivol",
        "lazy_jaccard_mda_h126_ivol",
        "lazy_cosine_rf_h63_eq",
    ):
        with pytest.raises(registry_module.UnknownCrossSectionalSpecError):
            resolve_spec(LAZY_PRICES_FAMILY_KEY, other_panel_spec)


def test_lazy_prices_spec_is_forward_tickable():
    """Refused configurations raise at REGISTRATION time, never mid-tick — so
    this is checked before a 252-day clock can start."""
    adapter, spec = resolve_spec(LAZY_PRICES_FAMILY_KEY, LAZY_PRICES_PATTERN)
    validate_spec_is_forward_tickable(spec, adapter.build_config())
    # The two-hold rule binds here, not the day floor: 2 x 126 = 252 > 126.
    assert graduation_threshold_for(spec) == MIN_FORWARD_COMPLETE_HOLDS * spec.holding_days == 252
    assert MIN_FORWARD_VALIDATION_TRADING_DAYS < 252


# --- K.2: the live panel builder ----------------------------------------------


def test_lazy_prices_live_panel_matches_the_familys_own_similarity_math():
    """The single most important property of this adapter: the panel's values
    must be exactly what cross_sectional_lazy_prices.jaccard_similarity /
    term_counts compute on the SAME two texts — not a re-derivation that could
    quietly drift from the family's own pipeline."""
    from app.services.research_lab.cross_sectional_lazy_prices import (
        jaccard_similarity,
        term_counts,
    )
    from app.services.research_lab.sp500_membership_history import was_member

    fakes = _lazy_prices_offline_panel_inputs()
    tickers, fake_yf, fake_text = fakes
    panel = _build_lazy_prices_panel(fakes)

    assert panel.n_tickers == N_LAZY_PRICES_TICKERS
    assert panel.last_row_date == fake_yf.frames["close"].index[-1].date()
    assert panel.membership_fn is was_member
    assert panel.data.leg_weight_basis is not None  # the inverse_vol spec needs it
    assert panel.data.half_spread is not None  # default config is cost_model="edge_spread"

    newest = panel.data.fundamental_signal.iloc[-1]
    assert newest.notna().all()
    for i, ticker in enumerate(tickers):
        prev_text = fake_text.texts[f"000-prev-{i:04d}"]
        cur_text = fake_text.texts[f"000-cur-{i:04d}"]
        expected = jaccard_similarity(term_counts(prev_text), term_counts(cur_text))
        assert newest[ticker] == pytest.approx(expected)
    # Monotone by construction: ticker i had 2i+2 tokens replaced, so
    # similarity strictly decreases with i — the fixture's whole point.
    values = [newest[t] for t in tickers]
    assert values == sorted(values, reverse=True)
    assert list(panel.data.fundamental_signal.columns) == list(panel.data.close.columns)


def test_lazy_prices_live_specs_can_form_a_real_book_on_the_live_panel():
    """End to end: the family's own spec ranks the live cross-section into a
    long tail of 'non-changers' (high similarity) and a short tail of
    'changers' (low similarity) — signal_lazy_prices' own sign convention."""
    from app.services.research_lab.cross_sectional import form_portfolio

    fakes = _lazy_prices_offline_panel_inputs()
    tickers, _fake_yf, _fake_text = fakes
    panel = _build_lazy_prices_panel(fakes)
    adapter, spec = resolve_spec(LAZY_PRICES_FAMILY_KEY, LAZY_PRICES_PATTERN)
    config = adapter.build_config()

    outcome = form_portfolio(
        panel.data, spec, config, panel.membership_fn, len(panel.data.close.index) - 1, {}
    )
    assert outcome.record.skipped_reason is None
    assert len(outcome.long_weights) >= config.min_names_per_leg
    assert len(outcome.realized_short_weights) >= config.min_names_per_leg
    # Low-i tickers had the fewest tokens replaced (highest similarity ->
    # non-changers -> long leg); high-i tickers had the most (changers ->
    # short leg).
    n_per_leg = max(round(N_LAZY_PRICES_TICKERS * spec.rank_fraction), config.min_names_per_leg)
    assert set(outcome.long_weights) <= set(tickers[:n_per_leg])
    assert set(outcome.realized_short_weights) <= set(tickers[-n_per_leg:])


def test_lazy_prices_live_panel_refuses_an_empty_price_panel():
    fakes = _lazy_prices_offline_panel_inputs()
    _tickers, fake_yf, _fake_text = fakes
    fake_yf.frames = {k: pd.DataFrame() for k in fake_yf.frames}
    with pytest.raises(registry_module.CrossSectionalPanelUnavailableError):
        _build_lazy_prices_panel(fakes)


def test_lazy_prices_live_panel_refuses_a_panel_that_can_rank_nothing():
    """A total EDGAR outage leaves an all-empty filing index and therefore an
    all-NaN similarity panel. Ticking on it would hold an empty book realizing
    exactly 0.0 every day — an outage written into the track record as flat
    performance."""
    fakes = _lazy_prices_offline_panel_inputs()
    _tickers, _fake_yf, fake_text = fakes
    fake_text.filing_index = {}
    with pytest.raises(registry_module.CrossSectionalPanelUnavailableError):
        _build_lazy_prices_panel(fakes)


def test_lazy_prices_live_panel_only_fetches_text_for_priced_tickers():
    """Filings are indexed only for tickers that resolved prices — the same
    discipline run_lazy_prices_screening documents: a ticker with no price
    history can never be ranked, so fetching its filings would spend requests
    a live tick cannot use."""
    fakes = _lazy_prices_offline_panel_inputs()
    tickers, fake_yf, fake_text = fakes
    dropped = tickers[0]
    fake_yf.frames = {k: v.drop(columns=[dropped]) for k, v in fake_yf.frames.items()}

    panel = _build_lazy_prices_panel(fakes)
    assert dropped not in fake_text.last_requested_tickers
    assert set(fake_text.last_requested_tickers) == set(tickers[1:])
    assert dropped not in panel.data.close.columns


def test_lazy_prices_live_panel_is_memoized_per_end_date():
    """The runner keeps a family pending all day after its one real new row
    is processed, so it calls build_live_panel ~47 more times for the same
    `end`. Each rebuild here is this project's single most expensive live
    fetch by a wide margin and cannot return anything different."""
    fakes = _lazy_prices_offline_panel_inputs()
    _tickers, fake_yf, fake_text = fakes
    today = _today()

    first = _build_lazy_prices_panel(fakes, today)
    second = _build_lazy_prices_panel(fakes, today)
    assert second is first
    assert (fake_yf.calls, fake_text.build_index_calls) == (1, 1)

    # A new UTC day always rebuilds.
    _build_lazy_prices_panel(fakes, today + timedelta(days=1))
    assert (fake_yf.calls, fake_text.build_index_calls) == (2, 2)


# --- K.3: the registration row -------------------------------------------


def _assert_lazy_prices_registration_shape(registration, created, today):
    """Asserted inside the caller's open session — every attribute below is a
    lazy-loadable ORM column, and reading one off a detached instance raises
    rather than returning the value."""
    assert created
    assert (registration.family_key, registration.pattern_id) == (
        LAZY_PRICES_FAMILY_KEY,
        LAZY_PRICES_PATTERN,
    )
    assert registration.spec_family == "lazy_prices"
    assert registration.family_n_trials == 36
    assert registration.module_path == "app/services/research_lab/cross_sectional_lazy_prices.py"
    assert registration.status == "in_progress"
    assert registration.n_forward_trading_days == 0
    assert registration.n_formations == 0
    # max(126, 2 x holding_days=126) — the TWO-HOLD rule binds here, so this
    # row graduates on two completed ~semiannual formations (~1 year).
    assert registration.min_trading_days_threshold == 252

    spec_snapshot = json.loads(registration.spec_snapshot_json)
    assert spec_snapshot["holding_days"] == 126
    assert spec_snapshot["lookback_days"] == 1
    assert spec_snapshot["rank_fraction"] == 0.2
    assert spec_snapshot["portfolio"] == "long_short"
    assert spec_snapshot["leg_weighting"] == "inverse_vol"
    assert spec_snapshot["cohort_formation_days"] is None
    assert spec_snapshot["family"] == "lazy_prices"

    config_snapshot = json.loads(registration.config_snapshot_json)
    assert config_snapshot["cost_bps"] == 5.0
    assert config_snapshot["financing_bps_per_year"] == 0.0
    assert config_snapshot["periods_per_year"] == 252  # equities, not crypto's 365
    assert config_snapshot["impute_delisting_returns"] is False

    assert len(registration.spec_fingerprint) == 64
    assert len(registration.config_fingerprint) == 64
    assert today <= registration.started_at <= today + timedelta(days=1)
    assert registration.last_processed_date is None
    assert json.loads(registration.day_results_json) == []
    state = deserialize_cross_sectional_forward_state(json.loads(registration.carry_state_json))
    assert (state.equity, state.n_formations, state.rows_since_formation) == (1.0, 0, None)


def test_lazy_prices_registration_uses_the_real_production_spec(
    test_db_engine, register_and_verify, client
):
    from app.services.research_lab.lazy_prices_forward_registration import (
        LAZY_PRICES_PATTERN_ID,
        register_lazy_prices_forward_validation,
    )

    assert LAZY_PRICES_PATTERN_ID == LAZY_PRICES_PATTERN
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    today = _today()
    with session_local() as db:
        registration, created = register_lazy_prices_forward_validation(db, user["id"])
        _assert_lazy_prices_registration_shape(registration, created, today)


def test_lazy_prices_registration_rationale_discloses_what_it_must(
    test_db_engine, register_and_verify, client
):
    """A forward slot is a claim on real calendar time. This row must say on
    its own face that its family returned a negative, what its own DSR and
    denominator were, why NO deviation was made from the family's top-DSR
    spec (unlike the short-interest precedent), what adversarial check was
    run to justify that, and that there are now four live registrations — not
    leave any of it to a docstring."""
    from app.services.research_lab.lazy_prices_forward_registration import (
        register_lazy_prices_forward_validation,
    )

    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration, _created = register_lazy_prices_forward_validation(db, user["id"])
        rationale = registration.registration_rationale

    assert "NOT AN AUTOMATIC ONE" in rationale
    assert "NOT A CLAIM OF VALIDATED EDGE" in rationale
    assert "HONEST NEGATIVE" in rationale
    assert "0.7540" in rationale
    assert "36-trial denominator" in rationale
    assert "2,926 realized" in rationale
    # Why no deviation, unlike short-interest's.
    assert "WHY THIS SPEC AND NOT A DEVIATION" in rationale
    assert "0.197" in rationale and "0.119" in rationale
    assert "No comparable confound was found by it" in rationale
    # THE 2026-09-03 CORRECTION, which is the point of these four assertions:
    # the original adversarial check was underpowered and measured the wrong
    # length variable, and a row that still recites its conclusion without
    # saying so would be worse than one that never made the claim. The
    # correction must travel with the row, not only with the docstring.
    assert "CORRECTION APPENDED 2026-09-03" in rationale
    assert "UNDERPOWERED AND MEASURED THE WRONG LENGTH VARIABLE" in rationale
    assert "vocabulary-size ceiling" in rationale
    assert "min(|A|,|B|)/max(|A|,|B|)" in rationale
    # And the correction must own its own limitation: the already-live row
    # cannot receive this text, because config_hash excludes the rationale.
    assert "reaches only a registration row created" in rationale
    # How to read it, and what it costs the other three rows.
    assert "graduation means ONLY" in rationale
    assert "TWO completed formations" in rationale
    assert "negative forward result is a real result" in rationale
    assert "FOUR LIVE REGISTRATIONS" in rationale
    assert "selection over four" in rationale


def test_lazy_prices_registration_is_idempotent_and_never_resets_progress(
    test_db_engine, register_and_verify, client
):
    from app.services.research_lab.lazy_prices_forward_registration import (
        register_lazy_prices_forward_validation,
    )

    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        first, created = register_lazy_prices_forward_validation(db, user["id"])
        assert created
        registration_id = first.id

        first.n_forward_trading_days = 60  # accumulated progress to protect
        first.n_formations = 1
        db.commit()

        again, created_again = register_lazy_prices_forward_validation(db, user["id"])
        assert created_again is False
        assert again.id == registration_id
        assert again.n_forward_trading_days == 60
        assert again.n_formations == 1
        assert db.query(CrossSectionalForwardValidationRegistration).count() == 1


def test_lazy_prices_registration_is_a_distinct_row_from_the_other_three(
    test_db_engine, register_and_verify, client
):
    """Four registrations, four rows, four config hashes — and the listing
    endpoint surfaces all four as system rows, because 'the best of the four'
    is a selection over four and the losers may never be dropped."""
    from app.services.research_lab.lazy_prices_forward_registration import (
        register_lazy_prices_forward_validation,
    )
    from app.services.research_lab.quality_forward_registration import (
        register_quality_forward_validations,
    )
    from app.services.research_lab.short_interest_forward_registration import (
        register_short_interest_forward_validation,
    )
    from app.services.research_lab.system_account import get_or_create_system_user

    register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        system_user = get_or_create_system_user(db)
        register_quality_forward_validations(db, system_user.id)
        register_short_interest_forward_validation(db, system_user.id)
        register_lazy_prices_forward_validation(db, system_user.id)
        hashes = {
            r.config_hash
            for r in db.query(CrossSectionalForwardValidationRegistration).all()
        }
        assert len(hashes) == 4

    listing = client.get("/api/cross-sectional-forward-validation")
    assert listing.status_code == 200
    rows = {r["pattern_id"]: r for r in listing.json()}
    assert set(rows) == {
        "cbop_ls_h63",
        "noa_neutral_ls_h126_median",
        "si_ratio_hedged_h21",
        "lazy_jaccard_full_h126_ivol",
    }
    assert all(r["is_system"] for r in rows.values())
    assert rows[LAZY_PRICES_PATTERN]["holding_days"] == 126
    assert rows[LAZY_PRICES_PATTERN]["periods_per_year"] == 252
    assert rows[LAZY_PRICES_PATTERN]["sharpe_forward_so_far"] is None


def test_families_endpoint_lists_the_lazy_prices_jaccard_full_family(client, register_and_verify):
    """The /families listing must stay cheap — build_specs for this family
    touches no data at all, which is what keeps an authenticated GET from
    turning into a many-thousand-document EDGAR fetch."""
    register_and_verify(client)
    response = client.get("/api/cross-sectional-forward-validation/families")
    assert response.status_code == 200
    families = {f["family_key"]: f for f in response.json()}
    family = families[LAZY_PRICES_FAMILY_KEY]
    assert family["n_trials"] == 36
    assert len(family["pattern_ids"]) == 6
    assert LAZY_PRICES_PATTERN in family["pattern_ids"]
    assert not any(p.startswith("lazy_cosine") for p in family["pattern_ids"])
    assert not any("_rf_" in p or "_mda_" in p for p in family["pattern_ids"])
    assert family["module_path"] == "app/services/research_lab/cross_sectional_lazy_prices.py"
    assert "point-in-time S&P 500 UNION" in family["universe_rule"]
    assert "XOM" in family["universe_rule"]


# --- K.4: the app-startup registration path -----------------------------------


@pytest.fixture
def patch_lazy_prices_startup_session(test_db_engine, monkeypatch):
    """The startup step opens its own SessionLocal (it has no request to take
    a get_db session from), exactly like every runner — so point that module
    attribute at the test engine."""
    from app.services.research_lab import (
        lazy_prices_forward_registration as startup_module,
    )

    monkeypatch.setattr(
        startup_module,
        "SessionLocal",
        sessionmaker(bind=test_db_engine, autoflush=False, autocommit=False),
    )
    return startup_module


LAZY_PRICES_STARTUP_LOGGER_NAME = "app.services.research_lab.lazy_prices_forward_registration"


def _lazy_prices_startup_log_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == LAZY_PRICES_STARTUP_LOGGER_NAME]


def test_lazy_prices_startup_registration_creates_the_row_when_absent(
    test_db_engine, patch_lazy_prices_startup_session
):
    outcomes = patch_lazy_prices_startup_session.register_lazy_prices_forward_validation_once()

    assert len(outcomes) == 1
    assert "CREATED" in outcomes[0]
    assert (
        "family_key=lazy_prices_jaccard_full pattern_id=lazy_jaccard_full_h126_ivol" in outcomes[0]
    )
    assert "status=in_progress" in outcomes[0]
    assert "threshold=252" in outcomes[0]

    from app.services.research_lab.system_account import get_or_create_system_user

    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        rows = db.query(CrossSectionalForwardValidationRegistration).all()
        assert [r.pattern_id for r in rows] == [LAZY_PRICES_PATTERN]
        system_user_id = get_or_create_system_user(db).id
        assert rows[0].user_id == system_user_id
        assert f"id={rows[0].id} " in outcomes[0]
        assert f"user_id={system_user_id} " in outcomes[0]


def test_lazy_prices_startup_registration_no_ops_when_the_row_already_exists(
    test_db_engine, patch_lazy_prices_startup_session
):
    """The property that matters most on a host that restarts the process on
    every deploy and every wake-from-sleep: a second run must find, not
    recreate, and must not touch an accumulated clock."""
    first = patch_lazy_prices_startup_session.register_lazy_prices_forward_validation_once()
    assert "CREATED" in first[0]

    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        row = db.query(CrossSectionalForwardValidationRegistration).one()
        row_id = row.id
        row.n_forward_trading_days = 60  # accumulated progress to protect
        db.commit()

    second = patch_lazy_prices_startup_session.register_lazy_prices_forward_validation_once()
    assert "ALREADY EXISTS" in second[0]
    assert f"id={row_id} " in second[0]
    assert "n_forward_trading_days=60" in second[0]

    with session_local() as db:
        assert db.query(CrossSectionalForwardValidationRegistration).count() == 1
        assert (
            db.get(CrossSectionalForwardValidationRegistration, row_id).n_forward_trading_days
            == 60
        )


@pytest.mark.asyncio
async def test_lazy_prices_startup_wrapper_logs_created_then_already_exists(
    test_db_engine, patch_lazy_prices_startup_session, caplog
):
    """The async wrapper main.py actually awaits — both passes, through the
    real logging module, at the level and with the fields a reader of
    Render's log viewer would grep for."""
    module = patch_lazy_prices_startup_session
    with caplog.at_level(logging.INFO, logger=LAZY_PRICES_STARTUP_LOGGER_NAME):
        await module.register_lazy_prices_forward_validation_on_startup()
        created_lines = _lazy_prices_startup_log_lines(caplog)
        caplog.clear()
        await module.register_lazy_prices_forward_validation_on_startup()
        second_lines = _lazy_prices_startup_log_lines(caplog)

    assert len(created_lines) == 1 and "CREATED" in created_lines[0]
    assert len(second_lines) == 1 and "ALREADY EXISTS" in second_lines[0]

    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        assert db.query(CrossSectionalForwardValidationRegistration).count() == 1


@pytest.mark.parametrize(
    ("broken", "expected_in_traceback"),
    [
        ("session_factory", "simulated database outage at startup"),
        ("registration", "simulated failure mid-registration"),
    ],
)
@pytest.mark.asyncio
async def test_lazy_prices_startup_wrapper_never_raises_and_logs_the_failure(
    test_db_engine,
    patch_lazy_prices_startup_session,
    monkeypatch,
    caplog,
    broken,
    expected_in_traceback,
):
    """A failure on one process start must not take the API down with it —
    lifespan awaits this directly, so anything escaping here would abort
    startup entirely."""
    module = patch_lazy_prices_startup_session
    if broken == "session_factory":

        def _broken_session_factory():
            raise RuntimeError("simulated database outage at startup")

        monkeypatch.setattr(module, "SessionLocal", _broken_session_factory)
    else:

        def _broken_registration(*args, **kwargs):
            raise RuntimeError("simulated failure mid-registration")

        monkeypatch.setattr(module, "register_lazy_prices_forward_validation", _broken_registration)

    with caplog.at_level(logging.ERROR, logger=LAZY_PRICES_STARTUP_LOGGER_NAME):
        result = await module.register_lazy_prices_forward_validation_on_startup()

    assert result is None  # returned normally; nothing propagated
    failures = [r for r in caplog.records if r.name == LAZY_PRICES_STARTUP_LOGGER_NAME]
    assert len(failures) == 1
    assert failures[0].levelno == logging.ERROR
    assert "failed on startup" in failures[0].getMessage()
    assert failures[0].exc_info is not None
    assert expected_in_traceback in caplog.text

    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        assert db.query(CrossSectionalForwardValidationRegistration).count() == 0


def test_lazy_prices_startup_registration_never_builds_a_live_panel(
    patch_lazy_prices_startup_session, monkeypatch
):
    """Startup must not touch SEC EDGAR or yfinance. This family's live panel
    is by far the heaviest in the project (thousands of real 10-K document
    fetches to rebuild history), so a cold boot that built it would read as a
    hung deploy to Render's health check — or simply never finish before the
    health check gives up. Every registered family's live-panel builder is
    replaced with a detonator; none may fire.

    Deliberately the SYNC entry point, not the never-raising async wrapper —
    the wrapper would catch the detonator's AssertionError and log it, and the
    test would pass vacuously."""

    def _explode(*args, **kwargs):
        raise AssertionError("startup registration built a live panel (network fetch)")

    for family_key in registry_module.registered_family_keys():
        adapter = registry_module.get_family_adapter(family_key)
        monkeypatch.setitem(
            registry_module._registry, family_key, replace(adapter, build_live_panel=_explode)
        )
    assert (
        registry_module.get_family_adapter(LAZY_PRICES_FAMILY_KEY).build_live_panel is _explode
    )

    outcomes = patch_lazy_prices_startup_session.register_lazy_prices_forward_validation_once()
    assert len(outcomes) == 1
    assert "CREATED" in outcomes[0]


# --- K.5: the equivalence property of section D, on THIS registered spec ----


def test_the_real_lazy_prices_spec_ticks_forward_identically_to_the_batch_harness():
    """Section D's equivalence property — a tick-by-tick forward replay must
    reproduce run_cross_sectional_backtest's daily net returns EXACTLY — run
    on the ACTUAL registered strategy: lazy_jaccard_full_h126_ivol's real
    126-row hold, its real quintile rank fraction, its real inverse-vol leg
    weighting and the real lazy_prices edge_spread config, all resolved
    through the registry rather than typed in here.

    It earns its own test rather than riding on J.5 and the BAB/synthetic
    versions, because this spec is the FIRST registered spec to combine two
    paths neither of those exercises together:

      * leg_weighting == "inverse_vol", i.e. BASIS-weighted legs read from
        CrossSectionalData.leg_weight_basis. si_ratio_hedged_h21, cbop_ls_h63
        and noa_neutral_ls_h126_median are all equal/magnitude weighted, so
        _resolve_leg_weights' basis branch — and its whole-leg fallback — has
        never been ticked forward before.
      * holding_days == 126, six months, the longest hold in the project. A
        realize-then-reform boundary that arrives once every 126 rows is a
        far weaker constraint than h21's, so an off-by-one in the forward
        cadence would go unnoticed for a whole quarter before diverging.

    Prices, OHLC and the similarity panel are synthetic — tests must never
    depend on live data, and this family's real panel is ~7,798 real 10-K
    fetches — but the STRATEGY and both derived frames are production: the
    half-spread comes from the real build_edge_half_spread_frame and the leg
    basis from the family's own build_inverse_vol_basis, exactly as
    build_lazy_prices_live_panel assembles them.

    THE PANEL IS A STAGGERED ANNUAL STEP FRAME, deliberately, because that is
    the shape of the real one: a filing-language similarity refreshes only
    when the firm files, roughly once a year, and filers' fiscal year-ends are
    spread across the calendar. So each formation re-ranks a cross-section in
    which a different slice of names has just refreshed — the behaviour a
    forward clock has to reproduce — rather than a frame that either never
    moves or moves everywhere at once."""
    from app.services.research_lab.cross_sectional_lazy_prices import (
        build_inverse_vol_basis,
    )
    from app.services.research_lab.spread_estimator import (
        COST_MODEL_WINDOW_DAYS,
        build_edge_half_spread_frame,
    )

    adapter, spec = resolve_spec(LAZY_PRICES_FAMILY_KEY, LAZY_PRICES_PATTERN)
    config = adapter.build_config()
    # Pinned here rather than assumed: if the registration is ever repointed
    # at a different cell, this test must fail loudly rather than quietly
    # keep proving the property about a spec nobody registered.
    assert (spec.holding_days, spec.rank_fraction) == (126, 0.2)
    assert spec.portfolio == "long_short"
    assert spec.leg_weighting == "inverse_vol"
    assert config.cost_model == "edge_spread"

    rng = np.random.default_rng(31)
    n_rows = 700  # ~2.8 years of business days: five 126-row holds plus warm-up
    tickers = [f"L{i:02d}" for i in range(N_LAZY_PRICES_TICKERS)]
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n_rows)

    close = pd.DataFrame(
        {
            t: 100.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.014, n_rows)))
            for t in tickers
        },
        index=dates,
    )
    # Synthetic intraday range around each close, so the REAL EDGE estimator
    # has something to estimate from. The per-DAY randomness is load-bearing,
    # not decoration: EDGE reads intraday log ratios, and a constant-width
    # band around the close makes its squared-spread estimate degenerate, so
    # every cell comes back NaN and the whole replay silently prices on the
    # flat fallback instead (measured — that is what the first version of this
    # fixture did, and assertion (3) below caught it).
    shape = (n_rows, len(tickers))
    open_ = close.shift(1).fillna(close.iloc[0]) * (
        1.0 + pd.DataFrame(rng.normal(0.0, 0.001, shape), index=dates, columns=tickers)
    )
    widths = pd.DataFrame(rng.uniform(0.0005, 0.004, shape), index=dates, columns=tickers)
    high = np.maximum(close, open_) * (1.0 + widths)
    low = np.minimum(close, open_) * (1.0 - widths)
    half_spread = build_edge_half_spread_frame(open_, high, low, close)
    leg_weight_basis = build_inverse_vol_basis(close)

    # A staggered annual step frame in the family's own realized jaccard/full
    # range (data/research_runs/lazy_prices_2026-09-01.txt section 5: mean
    # 0.880, p10 0.829, p90 0.927).
    signal = pd.DataFrame(index=dates, columns=tickers, dtype=float)
    for i, ticker in enumerate(tickers):
        refresh_rows = sorted({0, *range((i * 8) % 252, n_rows, 252)})
        for row_start, row_end in zip(refresh_rows, [*refresh_rows[1:], n_rows]):
            signal.iloc[row_start:row_end, i] = float(rng.uniform(0.78, 0.94))
    assert signal.notna().all().all()

    # The first formation waits for BOTH derived frames to warm up — the
    # inverse-vol basis (63-day window, 40 min periods) and the EDGE
    # half-spread (COST_MODEL_WINDOW_DAYS). Starting earlier would make the
    # first formations fall back off the very basis-weighting path this test
    # exists to exercise, and the assertions below check it did not.
    start = COST_MODEL_WINDOW_DAYS + 17
    assert bool(leg_weight_basis.iloc[start].notna().all())

    membership = fixed_universe_membership(tickers)
    data_full = CrossSectionalData(
        close=close,
        fundamental_signal=signal,
        half_spread=half_spread,
        leg_weight_basis=leg_weight_basis,
    )

    batch_config = adapter.build_config()
    batch_config.formation_start = close.index[start].date()
    batch = run_cross_sectional_backtest(data_full, spec, batch_config, membership)
    assert batch.status == "ok"

    state = CrossSectionalForwardState()
    last_processed: date | None = None
    forward_returns: dict[pd.Timestamp, float] = {}
    for row in range(start, n_rows):
        panel = CrossSectionalData(
            close=close.iloc[: row + 1],
            fundamental_signal=signal.iloc[: row + 1],
            half_spread=half_spread.iloc[: row + 1],
            leg_weight_basis=leg_weight_basis.iloc[: row + 1],
        )
        state, results = advance_forward_validation(
            panel, spec, config, membership, state, last_processed
        )
        for day_result in results:
            if day_result.realized:
                forward_returns[day_result.date] = day_result.net_return
        if results:
            last_processed = results[-1].date.date()

    batch_returns = {ts: float(v) for ts, v in batch.daily_returns.items()}
    assert len(batch_returns) > 600
    assert set(forward_returns) == set(batch_returns)
    for ts, batch_value in batch_returns.items():
        assert forward_returns[ts] == pytest.approx(batch_value, abs=1e-12), f"mismatch on {ts}"

    # NON-VACUITY, three ways. (1) The 126-row cadence really did roll over
    # several times, so the realize-then-reform boundary was crossed at real
    # formations and not merely at the first one.
    formed = [f for f in batch.formations if f.skipped_reason is None]
    assert state.n_formations == len(batch.formations) >= 5
    assert len(formed) == len(batch.formations)

    # (2) Every leg really was INVERSE-VOL weighted. _resolve_leg_weights
    # falls back to magnitude weighting for a whole leg whenever any member's
    # basis cell is missing or non-positive, and records it — so a green test
    # on a fallen-back replay would prove nothing about the basis path.
    assert not any(f.long_leg_value_weight_fallback for f in formed)
    assert not any(f.short_leg_value_weight_fallback for f in formed)

    # (3) Real EDGE half-spreads, not the flat fallback, priced most of what
    # this replay traded.
    assert batch.total_cost > 0.0
    traded = sum(f.turnover for f in batch.formations)
    fallback = sum(f.edge_flat_fallback_notional for f in batch.formations)
    assert traded > 0.0
    assert fallback < 0.5 * traded
