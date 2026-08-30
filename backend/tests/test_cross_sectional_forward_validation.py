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
