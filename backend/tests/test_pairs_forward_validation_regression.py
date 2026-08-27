"""PROOF THAT THE LIVE PAIRS/MOMENTUM FORWARD-VALIDATION PATH IS UNCHANGED.

The cross-sectional forward-validation work touched three shared things:
cross_sectional.py (a pure extraction of _replay_sleeve's loop body),
forward_validation_service.check_underperformance (one defaulted keyword-only
parameter), and main.py (one more background task and one more router). This
file pins the pairs/momentum mechanism against all three, so a regression in
it fails loudly here rather than silently on a live registration.

It is deliberately structural, not just behavioral: several assertions below
check that the live path's DATABASE QUERY and SNAPSHOT SHAPE still cannot see
a cross-sectional row at all. That is the property the parallel-table design
was chosen for (see the model's class docstring), and a property is worth
asserting, not just documenting.
"""

import inspect
import json
from datetime import date

import numpy as np
import pandas as pd
import pytest
from sqlalchemy.orm import sessionmaker

from app import dependencies
from app.models.cross_sectional_forward_validation import (
    CrossSectionalForwardValidationRegistration,
)
from app.models.forward_validation import ForwardValidationRegistration
from app.services.forward_validation_service import (
    MIN_FORWARD_DAYS_FOR_SHARPE,
    MIN_FORWARD_VALIDATION_TRADING_DAYS,
    UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS,
    UNDERPERFORMANCE_SHARPE_THRESHOLD,
    check_underperformance,
)
from app.services.research_lab import forward_validation_runner as pairs_runner_module
from app.services.research_lab import metrics
from app.services.research_lab.engine import (
    WalkForwardState,
    serialize_walk_forward_state,
)


def _synthetic_ou_frame(n: int, seed: int = 123) -> pd.DataFrame:
    """Byte-identical to test_forward_validation.py's own fixture, so this
    file pins the SAME numbers that file's tests exercise."""
    rng = np.random.default_rng(seed)
    log_a = np.cumsum(rng.normal(0, 0.01, n))
    spread = np.empty(n)
    spread[0] = 0.2
    for t in range(1, n):
        spread[t] = spread[t - 1] + 0.05 * (0.2 - spread[t - 1]) + 0.01 * rng.normal()
    log_b = 1.5 * log_a + spread
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    return pd.DataFrame({"A": 100 * np.exp(log_a), "B": 100 * np.exp(log_b)}, index=dates)


# --- 1: the constants the mechanism is gated on ----------------------------


def test_forward_validation_constants_are_unchanged():
    assert MIN_FORWARD_VALIDATION_TRADING_DAYS == 126
    assert MIN_FORWARD_DAYS_FOR_SHARPE == 20
    assert UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS == 60
    assert UNDERPERFORMANCE_SHARPE_THRESHOLD == -0.5


# --- 2: check_underperformance's no-argument behavior is untouched ---------


def test_check_underperformance_default_is_still_the_252_day_exchange_year():
    """The one shared function this work changed gained a keyword-only
    parameter defaulted to TRADING_DAYS_PER_YEAR — exactly the pattern
    metrics.sharpe_ratio itself uses. This pins that the DEFAULT call, which
    is the only call the pairs runner makes, is byte-for-byte what it was:
    identical to explicitly passing 252, and NOT to passing 365."""
    day_results = [{"net_return": r} for r in np.linspace(-0.02, 0.001, UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS)]
    default = check_underperformance(day_results)
    assert default == check_underperformance(day_results, periods_per_year=metrics.TRADING_DAYS_PER_YEAR)
    assert metrics.TRADING_DAYS_PER_YEAR == 252

    signature = inspect.signature(check_underperformance)
    periods = signature.parameters["periods_per_year"]
    assert periods.kind is inspect.Parameter.KEYWORD_ONLY
    assert periods.default == metrics.TRADING_DAYS_PER_YEAR

    # And the threshold arithmetic itself is unchanged.
    bad = [{"net_return": -0.005} for _ in range(UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS)]
    good = [{"net_return": 0.001} for _ in range(UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS)]
    assert check_underperformance(bad) is True
    assert check_underperformance(good) is False
    assert check_underperformance(bad[:10]) is False


# --- 3: the live runner cannot see a cross-sectional row ------------------


def test_pairs_runner_query_targets_only_the_pairs_table():
    """The parallel-table design's decisive property, asserted rather than
    trusted: ForwardValidationRunner._load_active_registrations selects from
    forward_validation_registrations and nothing else, so no discriminator
    filter is needed for it to stay correct."""
    source = inspect.getsource(pairs_runner_module.ForwardValidationRunner._load_active_registrations)
    assert "ForwardValidationRegistration" in source
    assert "CrossSectionalForwardValidationRegistration" not in source
    assert "family_key" not in source
    # The whole module, too — the pairs path has no knowledge of the other one.
    module_source = inspect.getsource(pairs_runner_module)
    assert "cross_sectional" not in module_source


def test_pairs_runner_snapshot_shape_is_unchanged():
    fields = set(pairs_runner_module._RegistrationSnapshot.__dataclass_fields__)
    assert fields == {
        "id",
        "strategy_name",
        "ticker_a",
        "ticker_b",
        "fit_window_days",
        "entry_z",
        "exit_z",
        "cost_bps",
        "last_processed_date",
        "min_trading_days_threshold",
        "n_forward_trading_days",
        "carry_state_json",
        "day_results_json",
        "trades_json",
    }


def test_the_two_registration_tables_are_separate():
    assert ForwardValidationRegistration.__tablename__ == "forward_validation_registrations"
    assert (
        CrossSectionalForwardValidationRegistration.__tablename__
        == "cross_sectional_forward_validation_registrations"
    )
    # Not a subclass, not a polymorphic union — two independent mappings.
    assert not issubclass(CrossSectionalForwardValidationRegistration, ForwardValidationRegistration)
    pairs_columns = {c.name for c in ForwardValidationRegistration.__table__.columns}
    # The pairs table gained no discriminator and lost nothing.
    assert pairs_columns == {
        "id",
        "user_id",
        "strategy_name",
        "ticker_a",
        "ticker_b",
        "fit_window_days",
        "entry_z",
        "exit_z",
        "cost_bps",
        "config_hash",
        "status",
        "min_trading_days_threshold",
        "n_forward_trading_days",
        "started_at",
        "last_processed_date",
        "last_ticked_at",
        "graduated_at",
        "created_at",
        "carry_state_json",
        "day_results_json",
        "trades_json",
    }


# --- 4: end-to-end — the live path still ticks identically ----------------


@pytest.fixture(autouse=True)
def patch_runner_session(test_db_engine, monkeypatch):
    testing_session_local = sessionmaker(bind=test_db_engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(pairs_runner_module, "SessionLocal", testing_session_local)


def _make_growing_prices_fn(full_frame: pd.DataFrame, cursor: dict):
    def fake_get_price_history(tickers, start, end):
        current = full_frame.iloc[: cursor["len"]]
        present = [t for t in tickers if t in current.columns]
        missing = [t for t in tickers if t not in current.columns]
        return current[present], missing

    return fake_get_price_history


@pytest.mark.asyncio
async def test_pairs_forward_validation_still_matches_a_batch_walk_forward(
    test_db_engine, register_and_verify, client, monkeypatch
):
    """The live mechanism's own equivalence property, re-asserted here after
    the shared-code changes: ticking day by day must still reproduce a single
    batch run_walk_forward call exactly."""
    from app.services.research_lab.engine import WalkForwardConfig, run_walk_forward
    from app.services.research_lab.ou_pairs import (
        build_pairs_raw_data,
        fit_ou_pairs_window,
        realize_pairs_return,
    )

    fit_window_days = 100
    n_simulated_days = 30
    frame = _synthetic_ou_frame(fit_window_days + n_simulated_days + 5)

    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration = ForwardValidationRegistration(
            user_id=user["id"],
            strategy_name="ou_pairs_v1",
            ticker_a="A",
            ticker_b="B",
            fit_window_days=fit_window_days,
            entry_z=2.0,
            exit_z=0.0,
            cost_bps=10.0,
            config_hash="regression-hash",
            status="in_progress",
            min_trading_days_threshold=MIN_FORWARD_VALIDATION_TRADING_DAYS,
            n_forward_trading_days=0,
            started_at=date.today(),
            carry_state_json=json.dumps(serialize_walk_forward_state(WalkForwardState())),
            day_results_json="[]",
            trades_json="[]",
        )
        db.add(registration)
        db.commit()
        db.refresh(registration)
        registration_id = registration.id

    cursor = {"len": fit_window_days + 1}
    monkeypatch.setattr(dependencies.provider, "get_price_history", _make_growing_prices_fn(frame, cursor))

    runner = pairs_runner_module.ForwardValidationRunner()
    for _ in range(n_simulated_days):
        cursor["len"] = min(cursor["len"] + 1, len(frame))
        await runner._tick()

    with session_local() as db:
        final = db.get(ForwardValidationRegistration, registration_id)
        simulated = json.loads(final.day_results_json)

    raw_data = build_pairs_raw_data(frame.iloc[: cursor["len"]], "A", "B")
    config = WalkForwardConfig(fit_window_days=fit_window_days, entry_z=2.0, exit_z=0.0, cost_bps=10.0)
    batch = run_walk_forward(raw_data, config, fit_ou_pairs_window, realize_pairs_return)

    assert len(simulated) == len(batch.day_results)
    for sim, ref in zip(simulated, batch.day_results, strict=True):
        assert sim["date"] == ref.date.strftime("%Y-%m-%d")
        assert sim["position"] == ref.position
        assert sim["net_return"] == pytest.approx(ref.net_return)
        assert sim["equity"] == pytest.approx(ref.equity)


@pytest.mark.asyncio
async def test_pairs_runner_ignores_a_cross_sectional_registration_entirely(
    test_db_engine, register_and_verify, client, monkeypatch
):
    """Both kinds of registration coexisting in one database: the pairs
    runner must load and advance ONLY its own, and must not error on, touch,
    or even see the other."""
    from app.services.research_lab.cross_sectional_forward import initial_state_json

    fit_window_days = 100
    frame = _synthetic_ou_frame(fit_window_days + 10)

    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        pairs = ForwardValidationRegistration(
            user_id=user["id"],
            strategy_name="ou_pairs_v1",
            ticker_a="A",
            ticker_b="B",
            fit_window_days=fit_window_days,
            entry_z=2.0,
            exit_z=0.0,
            cost_bps=10.0,
            config_hash="coexist-hash",
            status="in_progress",
            min_trading_days_threshold=MIN_FORWARD_VALIDATION_TRADING_DAYS,
            n_forward_trading_days=0,
            started_at=date.today(),
            carry_state_json=json.dumps(serialize_walk_forward_state(WalkForwardState())),
            day_results_json="[]",
            trades_json="[]",
        )
        cross_sectional = CrossSectionalForwardValidationRegistration(
            user_id=user["id"],
            family_key="cross_sectional_crypto",
            pattern_id="xc_btcbeta_l180_h180",
            module_path="app/services/research_lab/cross_sectional_crypto.py",
            spec_family="crypto_betting_against_beta",
            citation="Frazzini & Pedersen (2014)",
            universe_rule="point-in-time liquidity gate",
            family_n_trials=28,
            config_hash="xs-coexist-hash",
            spec_fingerprint="a" * 64,
            config_fingerprint="b" * 64,
            spec_snapshot_json="{}",
            config_snapshot_json="{}",
            registration_rationale="coexistence test",
            status="in_progress",
            min_trading_days_threshold=360,
            n_forward_trading_days=0,
            n_formations=0,
            started_at=date.today(),
            carry_state_json=initial_state_json(),
            day_results_json="[]",
            formations_json="[]",
        )
        db.add_all([pairs, cross_sectional])
        db.commit()
        db.refresh(pairs)
        db.refresh(cross_sectional)
        pairs_id, cross_sectional_id = pairs.id, cross_sectional.id

    cursor = {"len": fit_window_days + 2}
    monkeypatch.setattr(dependencies.provider, "get_price_history", _make_growing_prices_fn(frame, cursor))

    runner = pairs_runner_module.ForwardValidationRunner()
    # The pairs runner loads by status only — proof it still returns exactly
    # one row despite two "in_progress" registrations existing.
    snapshots = runner._load_active_registrations()
    assert len(snapshots) == 1
    assert snapshots[0].id == pairs_id

    await runner._tick()
    with session_local() as db:
        assert db.get(ForwardValidationRegistration, pairs_id).n_forward_trading_days == 1
        untouched = db.get(CrossSectionalForwardValidationRegistration, cross_sectional_id)
        assert untouched.n_forward_trading_days == 0
        assert untouched.last_ticked_at is None
        assert untouched.status == "in_progress"
