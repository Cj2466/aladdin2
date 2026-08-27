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
