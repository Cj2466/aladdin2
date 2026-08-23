import json
from datetime import date

import numpy as np
import pandas as pd
import pytest
from sqlalchemy.orm import sessionmaker

from app import dependencies
from app.models.forward_validation import ForwardValidationRegistration
from app.services.research_lab import forward_validation_runner as runner_module
from app.services.research_lab.engine import (
    WalkForwardState,
    serialize_walk_forward_state,
)


@pytest.fixture(autouse=True)
def patch_runner_session(test_db_engine, monkeypatch):
    """ForwardValidationRunner opens its own SessionLocal directly (it's
    not a FastAPI route, so the get_db dependency override doesn't reach
    it) — point that at the same per-test SQLite engine, mirroring
    test_alerts.py's patch_checker_session exactly."""
    testing_session_local = sessionmaker(bind=test_db_engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(runner_module, "SessionLocal", testing_session_local)


def _default_state_json() -> str:
    return json.dumps(serialize_walk_forward_state(WalkForwardState()))


def _synthetic_ou_frame(n: int, seed: int = 123) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    log_a = np.cumsum(rng.normal(0, 0.01, n))
    spread = np.empty(n)
    spread[0] = 0.2
    for t in range(1, n):
        spread[t] = spread[t - 1] + 0.05 * (0.2 - spread[t - 1]) + 0.01 * rng.normal()
    log_b = 1.5 * log_a + spread
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    return pd.DataFrame({"A": 100 * np.exp(log_a), "B": 100 * np.exp(log_b)}, index=dates)


def _synthetic_trend_frame(n: int, seed: int = 123) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    log_price = np.cumsum(rng.normal(0.003, 0.001, n))
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    return pd.DataFrame({"A": 100 * np.exp(log_price)}, index=dates)


def _make_growing_prices_fn(full_frame: pd.DataFrame, cursor: dict):
    def fake_get_price_history(tickers, start, end):
        current = full_frame.iloc[: cursor["len"]]
        present = [t for t in tickers if t in current.columns]
        missing = [t for t in tickers if t not in current.columns]
        return current[present], missing

    return fake_get_price_history


def _create_registration(
    db, user_id: int, *, fit_window_days: int = 100, min_trading_days_threshold: int = 126
) -> ForwardValidationRegistration:
    registration = ForwardValidationRegistration(
        user_id=user_id,
        strategy_name="ou_pairs_v1",
        ticker_a="A",
        ticker_b="B",
        fit_window_days=fit_window_days,
        entry_z=2.0,
        exit_z=0.0,
        cost_bps=10.0,
        config_hash="test-hash",
        status="in_progress",
        min_trading_days_threshold=min_trading_days_threshold,
        n_forward_trading_days=0,
        started_at=date.today(),
        carry_state_json=_default_state_json(),
        day_results_json="[]",
        trades_json="[]",
    )
    db.add(registration)
    db.commit()
    db.refresh(registration)
    return registration


def _create_momentum_registration(
    db, user_id: int, *, fit_window_days: int = 90, min_trading_days_threshold: int = 126
) -> ForwardValidationRegistration:
    registration = ForwardValidationRegistration(
        user_id=user_id,
        strategy_name="momentum_v1",
        ticker_a="A",
        ticker_b="A",
        fit_window_days=fit_window_days,
        entry_z=2.0,
        exit_z=0.0,
        cost_bps=5.0,
        config_hash="test-hash-momentum",
        status="in_progress",
        min_trading_days_threshold=min_trading_days_threshold,
        n_forward_trading_days=0,
        started_at=date.today(),
        carry_state_json=_default_state_json(),
        day_results_json="[]",
        trades_json="[]",
    )
    db.add(registration)
    db.commit()
    db.refresh(registration)
    return registration


# --- B: idempotent no-op tick --------------------------------------------------


@pytest.mark.asyncio
async def test_no_new_trading_day_is_a_no_op(test_db_engine, register_and_verify, client, monkeypatch):
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration = _create_registration(db, user["id"], fit_window_days=100)
        registration_id = registration.id

    frame = _synthetic_ou_frame(150)
    cursor = {"len": 120}
    monkeypatch.setattr(dependencies.provider, "get_price_history", _make_growing_prices_fn(frame, cursor))

    runner = runner_module.ForwardValidationRunner()
    await runner._tick()
    with session_local() as db:
        after_first = db.get(ForwardValidationRegistration, registration_id)
        n_after_first = after_first.n_forward_trading_days
        carry_after_first = after_first.carry_state_json
        last_processed_after_first = after_first.last_processed_date

    # No new trading day available (cursor unchanged) — second tick must be a no-op.
    await runner._tick()
    with session_local() as db:
        after_second = db.get(ForwardValidationRegistration, registration_id)
        assert after_second.n_forward_trading_days == n_after_first
        assert after_second.carry_state_json == carry_after_first
        assert after_second.last_processed_date == last_processed_after_first


# --- C: state persistence across simulated ticks (no real waiting) ------------


@pytest.mark.asyncio
async def test_state_persists_across_simulated_ticks_matches_batch_backtest(
    test_db_engine, register_and_verify, client, monkeypatch
):
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
        registration = _create_registration(db, user["id"], fit_window_days=fit_window_days)
        registration_id = registration.id

    cursor = {"len": fit_window_days + 1}  # just enough for the first real tick
    monkeypatch.setattr(dependencies.provider, "get_price_history", _make_growing_prices_fn(frame, cursor))

    runner = runner_module.ForwardValidationRunner()
    for _ in range(n_simulated_days):
        cursor["len"] = min(cursor["len"] + 1, len(frame))
        await runner._tick()

    with session_local() as db:
        final = db.get(ForwardValidationRegistration, registration_id)
        simulated_day_results = json.loads(final.day_results_json)

    # Compare against a single batch run_walk_forward call over the same
    # full range — the two must agree exactly, proving state survives
    # tick-by-tick resumption, not just a single in-memory pass.
    raw_data = build_pairs_raw_data(frame.iloc[: cursor["len"]], "A", "B")
    config = WalkForwardConfig(fit_window_days=fit_window_days, entry_z=2.0, exit_z=0.0, cost_bps=10.0)
    batch_result = run_walk_forward(raw_data, config, fit_ou_pairs_window, realize_pairs_return)

    assert len(simulated_day_results) == len(batch_result.day_results)
    for sim, batch in zip(simulated_day_results, batch_result.day_results, strict=True):
        assert sim["date"] == batch.date.strftime("%Y-%m-%d")
        assert sim["position"] == batch.position
        assert sim["net_return"] == pytest.approx(batch.net_return)
        assert sim["equity"] == pytest.approx(batch.equity)


# --- D: graduation ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_graduates_exactly_at_threshold_and_keeps_ticking_after(
    test_db_engine, register_and_verify, client, monkeypatch
):
    fit_window_days = 100
    frame = _synthetic_ou_frame(fit_window_days + 10)

    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration = _create_registration(db, user["id"], fit_window_days=fit_window_days, min_trading_days_threshold=3)
        registration_id = registration.id

    # +1 for the pct_change row build_pairs_raw_data's dropna() removes, +1
    # more so the first tick already has fit_window_days+1 raw_data rows
    # (the runner requires len(raw_data) > fit_window_days to process at all).
    cursor = {"len": fit_window_days + 1}
    monkeypatch.setattr(dependencies.provider, "get_price_history", _make_growing_prices_fn(frame, cursor))

    runner = runner_module.ForwardValidationRunner()

    for expected_days in (1, 2):
        cursor["len"] += 1
        await runner._tick()
        with session_local() as db:
            reg = db.get(ForwardValidationRegistration, registration_id)
            assert reg.n_forward_trading_days == expected_days
            assert reg.status == "in_progress"
            assert reg.graduated_at is None

    # 3rd tick — graduation threshold reached exactly here.
    cursor["len"] += 1
    await runner._tick()
    with session_local() as db:
        reg = db.get(ForwardValidationRegistration, registration_id)
        assert reg.n_forward_trading_days == 3
        assert reg.status == "forward_validated"
        assert reg.graduated_at is not None

    # 4th tick — keeps ticking after graduation, doesn't freeze.
    cursor["len"] += 1
    await runner._tick()
    with session_local() as db:
        reg = db.get(ForwardValidationRegistration, registration_id)
        assert reg.n_forward_trading_days == 4
        assert reg.status == "forward_validated"


# --- C.5/D.5: momentum-flavored tick-simulation tests, mirroring B/C/D above ---


@pytest.mark.asyncio
async def test_state_persists_across_simulated_ticks_matches_batch_backtest_momentum(
    test_db_engine, register_and_verify, client, monkeypatch
):
    from app.services.research_lab.engine import WalkForwardConfig, run_walk_forward
    from app.services.research_lab.momentum import (
        apply_momentum_threshold_rule,
        build_momentum_raw_data,
        fit_momentum_window,
        realize_momentum_return,
    )

    fit_window_days = 90
    n_simulated_days = 30
    frame = _synthetic_trend_frame(fit_window_days + n_simulated_days + 5)

    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration = _create_momentum_registration(db, user["id"], fit_window_days=fit_window_days)
        registration_id = registration.id

    cursor = {"len": fit_window_days + 1}
    monkeypatch.setattr(dependencies.provider, "get_price_history", _make_growing_prices_fn(frame, cursor))

    runner = runner_module.ForwardValidationRunner()
    for _ in range(n_simulated_days):
        cursor["len"] = min(cursor["len"] + 1, len(frame))
        await runner._tick()

    with session_local() as db:
        final = db.get(ForwardValidationRegistration, registration_id)
        simulated_day_results = json.loads(final.day_results_json)

    raw_data = build_momentum_raw_data(frame.iloc[: cursor["len"]], "A")
    config = WalkForwardConfig(fit_window_days=fit_window_days, entry_z=2.0, exit_z=0.0, cost_bps=5.0)
    batch_result = run_walk_forward(
        raw_data,
        config,
        fit_momentum_window,
        realize_momentum_return,
        decide_position_fn=apply_momentum_threshold_rule,
        direction_labels=("long", "short"),
    )

    assert len(simulated_day_results) == len(batch_result.day_results)
    for sim, batch in zip(simulated_day_results, batch_result.day_results, strict=True):
        assert sim["date"] == batch.date.strftime("%Y-%m-%d")
        assert sim["position"] == batch.position
        assert sim["net_return"] == pytest.approx(batch.net_return)
        assert sim["equity"] == pytest.approx(batch.equity)


@pytest.mark.asyncio
async def test_graduates_exactly_at_threshold_and_keeps_ticking_after_momentum(
    test_db_engine, register_and_verify, client, monkeypatch
):
    fit_window_days = 90
    frame = _synthetic_trend_frame(fit_window_days + 10)

    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration = _create_momentum_registration(
            db, user["id"], fit_window_days=fit_window_days, min_trading_days_threshold=3
        )
        registration_id = registration.id

    cursor = {"len": fit_window_days + 1}
    monkeypatch.setattr(dependencies.provider, "get_price_history", _make_growing_prices_fn(frame, cursor))

    runner = runner_module.ForwardValidationRunner()

    for expected_days in (1, 2):
        cursor["len"] += 1
        await runner._tick()
        with session_local() as db:
            reg = db.get(ForwardValidationRegistration, registration_id)
            assert reg.n_forward_trading_days == expected_days
            assert reg.status == "in_progress"
            assert reg.graduated_at is None

    cursor["len"] += 1
    await runner._tick()
    with session_local() as db:
        reg = db.get(ForwardValidationRegistration, registration_id)
        assert reg.n_forward_trading_days == 3
        assert reg.status == "forward_validated"
        assert reg.graduated_at is not None

    cursor["len"] += 1
    await runner._tick()
    with session_local() as db:
        reg = db.get(ForwardValidationRegistration, registration_id)
        assert reg.n_forward_trading_days == 4
        assert reg.status == "forward_validated"


# --- E: endpoint / dedup behavior ----------------------------------------------


def _register_payload(ticker_a="KO", ticker_b="PEP"):
    return {"ticker_a": ticker_a, "ticker_b": ticker_b}


def test_register_requires_auth(client):
    response = client.post("/api/forward-validation", json=_register_payload())
    assert response.status_code == 401


def test_list_requires_auth(client):
    response = client.get("/api/forward-validation")
    assert response.status_code == 401


def test_duplicate_register_is_idempotent_and_preserves_progress(client, register_and_verify, test_db_engine):
    register_and_verify(client)

    first = client.post("/api/forward-validation", json=_register_payload())
    assert first.status_code == 201
    assert first.json()["created"] is True
    registration_id = first.json()["id"]

    # Manually bump progress, simulating real ticks having happened.
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        reg = db.get(ForwardValidationRegistration, registration_id)
        reg.n_forward_trading_days = 5
        db.commit()

    second = client.post("/api/forward-validation", json=_register_payload())
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["id"] == registration_id
    assert second.json()["n_forward_trading_days"] == 5  # dedup never resets progress


def test_two_different_users_get_independent_registrations(client, register_and_verify):
    from fastapi.testclient import TestClient

    from app.main import app

    register_and_verify(client, email="user_a@example.com")
    first = client.post("/api/forward-validation", json=_register_payload())
    assert first.status_code == 201

    other_client = TestClient(app)
    register_and_verify(other_client, email="user_b@example.com")
    second = other_client.post("/api/forward-validation", json=_register_payload())
    assert second.status_code == 201
    assert second.json()["id"] != first.json()["id"]


def test_delete_by_non_owner_is_404(client, register_and_verify):
    from fastapi.testclient import TestClient

    from app.main import app

    register_and_verify(client, email="owner_fv@example.com")
    created = client.post("/api/forward-validation", json=_register_payload())
    registration_id = created.json()["id"]

    other_client = TestClient(app)
    register_and_verify(other_client, email="intruder_fv@example.com")
    response = other_client.delete(f"/api/forward-validation/{registration_id}")
    assert response.status_code == 404


def test_delete_by_owner_succeeds(client, register_and_verify):
    register_and_verify(client)
    created = client.post("/api/forward-validation", json=_register_payload())
    registration_id = created.json()["id"]

    response = client.delete(f"/api/forward-validation/{registration_id}")
    assert response.status_code == 204

    listed = client.get("/api/forward-validation")
    assert listed.json() == []


def test_same_ticker_rejected(client, register_and_verify):
    register_and_verify(client)
    response = client.post("/api/forward-validation", json={"ticker_a": "KO", "ticker_b": "KO"})
    assert response.status_code == 422


# --- F: momentum endpoint / dedup behavior --------------------------------------


def _register_momentum_payload(ticker="AAPL"):
    return {"ticker": ticker}


def test_momentum_register_requires_auth(client):
    response = client.post("/api/forward-validation/momentum", json=_register_momentum_payload())
    assert response.status_code == 401


def test_momentum_duplicate_register_is_idempotent_and_preserves_progress(client, register_and_verify, test_db_engine):
    register_and_verify(client)

    first = client.post("/api/forward-validation/momentum", json=_register_momentum_payload())
    assert first.status_code == 201, first.text
    assert first.json()["created"] is True
    registration_id = first.json()["id"]

    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        reg = db.get(ForwardValidationRegistration, registration_id)
        reg.n_forward_trading_days = 5
        db.commit()

    second = client.post("/api/forward-validation/momentum", json=_register_momentum_payload())
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["id"] == registration_id
    assert second.json()["n_forward_trading_days"] == 5


def test_momentum_ticker_is_normalized_and_populates_both_columns(client, register_and_verify):
    register_and_verify(client)
    response = client.post("/api/forward-validation/momentum", json={"ticker": " aapl "})
    assert response.status_code == 201, response.text
    assert response.json()["ticker_a"] == response.json()["ticker_b"] == "AAPL"
    assert response.json()["strategy_name"] == "momentum_v1"
