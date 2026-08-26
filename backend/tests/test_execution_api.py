"""Execution router: auth, the asymmetric halt/resume friction, the same-day
resume block, the audit log, and the slippage disclosure endpoint."""

from datetime import date, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.forward_validation import ForwardValidationRegistration
from app.models.live_order import LiveOrder
from app.models.strategy_execution_state import StrategyExecutionState
from app.models.user import User
from app.services.execution import alpaca_client
from app.services.execution.alpaca_client import AlpacaError
from app.services.execution.execution_control_service import RESUME_CONFIRMATION, get_control
from app.time_utils import utcnow_naive

BASE = "/api/execution"


@pytest.fixture
def db_session(test_db_engine):
    return sessionmaker(bind=test_db_engine, autoflush=False, autocommit=False)


@pytest.fixture
def no_broker(monkeypatch):
    """Default: no credentials, so /status exercises its own degraded path
    without any network call."""
    monkeypatch.setattr(settings, "alpaca_api_key", "")
    monkeypatch.setattr(settings, "alpaca_api_secret", "")


@pytest.fixture
def stub_broker(monkeypatch):
    monkeypatch.setattr(settings, "alpaca_api_key", "k")
    monkeypatch.setattr(settings, "alpaca_api_secret", "s")
    calls = {"cancel": 0}
    monkeypatch.setattr(
        alpaca_client, "get_account",
        lambda **_kw: {
            "equity": "100000", "last_equity": "99000", "cash": "50000",
            "buying_power": "200000", "status": "ACTIVE",
            "trading_blocked": False, "account_blocked": False,
        },
    )
    monkeypatch.setattr(alpaca_client, "get_clock", lambda **_kw: {"is_open": True})
    monkeypatch.setattr(
        alpaca_client, "get_positions",
        lambda **_kw: [
            {"symbol": "AAA", "side": "long", "qty": "10", "market_value": "1000",
             "avg_entry_price": "99", "current_price": "100", "unrealized_pl": "10"},
            {"symbol": "BBB", "side": "short", "qty": "-4", "market_value": "-200",
             "avg_entry_price": "52", "current_price": "50", "unrealized_pl": "8"},
        ],
    )

    def _cancel(**_kw):
        calls["cancel"] += 1
        return []

    monkeypatch.setattr(alpaca_client, "cancel_all_orders", _cancel)
    return calls


@pytest.fixture
def authed(client, register_and_verify, db_session):
    user = register_and_verify(client)
    return user


# --- auth ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "/status", None),
        ("post", "/halt", {"reason": "x"}),
        ("post", "/resume", {"confirmation": RESUME_CONFIRMATION}),
        ("get", "/orders", None),
        ("get", "/positions", None),
        ("post", "/strategies/1/resume", {"confirmation": RESUME_CONFIRMATION}),
    ],
)
def test_every_endpoint_requires_a_session(client, method, path, body, no_broker):
    response = getattr(client, method)(f"{BASE}{path}", json=body) if body else getattr(client, method)(f"{BASE}{path}")
    assert response.status_code == 401


# --- status -------------------------------------------------------------------


def test_status_reports_the_seeded_halted_state_and_the_live_limits(client, authed, no_broker):
    body = client.get(f"{BASE}/status").json()
    assert body["control"]["trading_halted"] is True
    assert body["settings"]["paper_trading"] is True
    assert body["settings"]["broker_base_url"] == alpaca_client.PAPER_BASE_URL
    assert body["settings"]["daily_loss_limit_pct"] == settings.execution_daily_loss_limit_pct


def test_status_surfaces_a_broker_failure_instead_of_showing_a_flat_account(
    client, authed, monkeypatch
):
    """"We do not know the account state" and "the account is empty" must never
    look the same on a control screen."""
    monkeypatch.setattr(settings, "alpaca_api_key", "k")
    monkeypatch.setattr(settings, "alpaca_api_secret", "s")

    def boom(**_kw):
        raise AlpacaError("broker down")

    monkeypatch.setattr(alpaca_client, "get_account", boom)

    body = client.get(f"{BASE}/status").json()
    assert body["account"] is None
    assert "broker down" in body["account_error"]


def test_status_includes_a_live_account_snapshot(client, authed, stub_broker):
    body = client.get(f"{BASE}/status").json()
    assert body["account"]["equity"] == pytest.approx(100000.0)
    assert body["account"]["daily_pnl_pct"] == pytest.approx((100000 - 99000) / 99000)
    assert body["market_open"] is True


# --- halt / resume ------------------------------------------------------------


def test_halt_needs_no_confirmation_and_cancels_open_orders(client, authed, stub_broker):
    """The safe direction should never have friction."""
    response = client.post(f"{BASE}/halt", json={"reason": "eyeballing it"})
    assert response.status_code == 200
    assert response.json()["trading_halted"] is True
    assert stub_broker["cancel"] == 1


def test_halt_is_idempotent(client, authed, stub_broker):
    client.post(f"{BASE}/halt", json={"reason": "one"})
    response = client.post(f"{BASE}/halt", json={"reason": "two"})
    assert response.status_code == 200
    assert response.json()["trading_halted"] is True


def test_halt_still_succeeds_when_the_broker_is_unreachable(client, authed, monkeypatch):
    """A halt that failed to record because a cancel threw would be much worse
    than a halt whose cancel failed."""
    monkeypatch.setattr(settings, "alpaca_api_key", "k")
    monkeypatch.setattr(settings, "alpaca_api_secret", "s")

    def boom(**_kw):
        raise AlpacaError("broker down")

    monkeypatch.setattr(alpaca_client, "cancel_all_orders", boom)

    response = client.post(f"{BASE}/halt", json={"reason": "x"})
    assert response.status_code == 200
    assert response.json()["trading_halted"] is True


def test_resume_rejects_a_wrong_confirmation(client, authed, no_broker):
    response = client.post(f"{BASE}/resume", json={"confirmation": "resume live trading"})
    assert response.status_code == 409
    assert client.get(f"{BASE}/status").json()["control"]["trading_halted"] is True


def test_resume_rejects_an_empty_confirmation(client, authed, no_broker):
    assert client.post(f"{BASE}/resume", json={"confirmation": ""}).status_code == 409


def test_resume_with_the_exact_confirmation_succeeds(client, authed, no_broker):
    response = client.post(f"{BASE}/resume", json={"confirmation": RESUME_CONFIRMATION})
    assert response.status_code == 200
    assert response.json()["trading_halted"] is False


def test_resume_is_blocked_for_the_rest_of_the_trading_day_after_a_breach(
    client, authed, db_session, no_broker
):
    """Specifically so a stressed human cannot immediately undo the thing that
    just protected them."""
    with db_session() as db:
        # get_control, not a bare db.get: a test DB is built from
        # Base.metadata.create_all, which does not run the migration's seed —
        # so this also exercises the lazy create-it-HALTED path.
        control = get_control(db)
        control.trading_halted = True
        control.halted_reason = "daily_loss_limit_breached"
        control.daily_loss_breach_at = utcnow_naive()
        control.daily_loss_breach_pct = -0.04
        db.commit()

    status = client.get(f"{BASE}/status").json()
    assert status["control"]["resume_blocked_until_next_trading_day"] is True

    response = client.post(f"{BASE}/resume", json={"confirmation": RESUME_CONFIRMATION})
    assert response.status_code == 409
    assert "circuit breaker" in response.json()["detail"]
    assert client.get(f"{BASE}/status").json()["control"]["trading_halted"] is True


def test_resume_is_allowed_again_once_the_breach_is_on_an_earlier_trading_day(
    client, authed, db_session, no_broker
):
    with db_session() as db:
        control = get_control(db)
        control.trading_halted = True
        control.daily_loss_breach_at = utcnow_naive() - timedelta(days=3)
        db.commit()

    response = client.post(f"{BASE}/resume", json={"confirmation": RESUME_CONFIRMATION})
    assert response.status_code == 200
    assert response.json()["trading_halted"] is False


# --- orders and positions -----------------------------------------------------


def _seed_order(db, user_id, **overrides):
    fields = dict(
        user_id=user_id, ticker="AAA", side="buy", notional_requested=1000.0,
        status="filled", client_order_id=f"c-{overrides.get('client_order_id', id(overrides))}",
        decision_price=100.0, filled_avg_price=100.15, filled_qty=10.0,
        realized_slippage_bps=15.0, assumed_cost_bps=5.0,
    )
    fields.update(overrides)
    order = LiveOrder(**fields)
    db.add(order)
    return order


def test_orders_endpoint_only_returns_the_callers_own_orders(client, authed, db_session):
    with db_session() as db:
        other = User(email="other@example.com", password_hash="x", is_verified=True)
        db.add(other)
        db.flush()
        _seed_order(db, authed["id"], client_order_id="mine")
        _seed_order(db, other.id, client_order_id="theirs", ticker="ZZZ")
        db.commit()

    tickers = [o["ticker"] for o in client.get(f"{BASE}/orders").json()]
    assert tickers == ["AAA"]


def test_orders_endpoint_exposes_the_slippage_columns(client, authed, db_session):
    with db_session() as db:
        _seed_order(db, authed["id"], client_order_id="s1")
        db.commit()
    order = client.get(f"{BASE}/orders").json()[0]
    assert order["decision_price"] == pytest.approx(100.0)
    assert order["realized_slippage_bps"] == pytest.approx(15.0)
    assert order["assumed_cost_bps"] == pytest.approx(5.0)


def test_positions_are_proxied_with_short_exposure_signed_negative(client, authed, stub_broker):
    positions = {p["ticker"]: p for p in client.get(f"{BASE}/positions").json()}
    assert positions["AAA"]["signed_market_value"] == pytest.approx(1000.0)
    assert positions["BBB"]["signed_market_value"] == pytest.approx(-200.0)
    assert positions["BBB"]["qty"] == pytest.approx(-4.0)


def test_positions_surface_a_broker_failure_as_502(client, authed, monkeypatch):
    monkeypatch.setattr(settings, "alpaca_api_key", "k")
    monkeypatch.setattr(settings, "alpaca_api_secret", "s")

    def boom(**_kw):
        raise AlpacaError("broker down")

    monkeypatch.setattr(alpaca_client, "get_positions", boom)
    assert client.get(f"{BASE}/positions").status_code == 502


# --- slippage disclosure ------------------------------------------------------


def test_slippage_report_is_empty_and_flagged_before_any_fills(client, authed, no_broker):
    report = client.get(f"{BASE}/status").json()["slippage"]
    assert report["overall"]["n_fills"] == 0
    assert report["overall"]["notional_weighted_mean_bps"] is None
    assert report["overall"]["meaningful_sample"] is False


def test_slippage_report_compares_real_fills_against_the_assumed_cost(
    client, authed, db_session, no_broker
):
    with db_session() as db:
        registration = ForwardValidationRegistration(
            user_id=authed["id"], strategy_name="momentum_v1", ticker_a="AAA", ticker_b="AAA",
            fit_window_days=90, entry_z=2.0, exit_z=0.0, cost_bps=5.0, config_hash="h",
            status="forward_validated", min_trading_days_threshold=126,
            n_forward_trading_days=200, started_at=date.today(), carry_state_json="{}",
        )
        db.add(registration)
        db.flush()
        for i in range(4):
            _seed_order(
                db, authed["id"], client_order_id=f"sl-{i}",
                forward_validation_registration_id=registration.id,
                realized_slippage_bps=15.0, assumed_cost_bps=5.0,
            )
        db.commit()

    report = client.get(f"{BASE}/status").json()["slippage"]
    assert report["overall"]["n_fills"] == 4
    assert report["overall"]["notional_weighted_mean_bps"] == pytest.approx(15.0)
    # Real fills costing 15bps against an assumed 5bps is exactly the silent
    # divergence this measurement exists to surface.
    assert report["overall"]["excess_vs_assumed_bps"] == pytest.approx(10.0)
    # ...but a 4-fill sample is flagged, not presented as a finding.
    assert report["overall"]["meaningful_sample"] is False
    assert report["per_strategy"][0]["label"] == "momentum_v1 AAA/AAA"


# --- per-strategy resume ------------------------------------------------------


def test_strategy_resume_requires_the_exact_confirmation(client, authed, db_session, no_broker):
    with db_session() as db:
        registration = ForwardValidationRegistration(
            user_id=authed["id"], strategy_name="momentum_v1", ticker_a="AAA", ticker_b="AAA",
            fit_window_days=90, entry_z=2.0, exit_z=0.0, cost_bps=5.0, config_hash="h2",
            status="forward_validated", min_trading_days_threshold=126,
            n_forward_trading_days=200, started_at=date.today(), carry_state_json="{}",
        )
        db.add(registration)
        db.flush()
        db.add(
            StrategyExecutionState(
                user_id=authed["id"],
                forward_validation_registration_id=registration.id,
                day_pnl_json="[]", halted_at=utcnow_naive(),
                halted_reason="trailing_sharpe_breach",
                frozen_target_json='{"AAA": 500.0}',
            )
        )
        db.commit()
        registration_id = registration.id

    assert client.post(
        f"{BASE}/strategies/{registration_id}/resume", json={"confirmation": "nope"}
    ).status_code == 409

    response = client.post(
        f"{BASE}/strategies/{registration_id}/resume",
        json={"confirmation": RESUME_CONFIRMATION},
    )
    assert response.status_code == 200
    assert response.json()["halted_at"] is None

    with db_session() as db:
        state = db.query(StrategyExecutionState).filter_by(
            forward_validation_registration_id=registration_id
        ).one()
        # The freeze is lifted too, so it tracks its live signal again rather
        # than staying pinned to the exposure it had when it tripped.
        assert state.frozen_target_json is None


def test_strategy_resume_404s_for_someone_elses_strategy(client, authed, db_session, no_broker):
    assert client.post(
        f"{BASE}/strategies/999/resume", json={"confirmation": RESUME_CONFIRMATION}
    ).status_code == 404


# --- StrategyExecutionStateOut's -inf sentinel serialization -----------------
#
# strategy_breaker.evaluate() reports a zero/near-zero-variance losing streak
# as trailing_sharpe=-inf (see strategy_breaker.py). Pydantic's default JSON
# mode serializes -inf as `null` -- indistinguishable on the wire from "not
# enough data yet" (trailing_sharpe is also None in that case), which would
# make the frontend render a halted strategy's Sharpe as the same blank
# placeholder used for insufficient data. These tests lock in the schema's
# field_serializer fix directly, independent of DB/runner plumbing.


def test_strategy_state_out_maps_negative_infinity_sharpe_to_a_finite_sentinel():
    from app.schemas.execution import StrategyExecutionStateOut

    state = StrategyExecutionStateOut(
        forward_validation_registration_id=1, strategy_name="momentum_v1",
        ticker_a="AAA", ticker_b="AAA", halted_at=None, halted_reason="breach",
        halted_trailing_sharpe=float("-inf"), halted_trailing_days=20,
        trailing_sharpe=float("-inf"), trailing_days=20, trailing_return=-0.05,
        breaker_threshold=-1.0, breaker_lookback_trading_days=20,
    )
    dumped = state.model_dump(mode="json")
    assert dumped["trailing_sharpe"] == -999.0
    assert dumped["halted_trailing_sharpe"] == -999.0
    # A finite sentinel, not null -- the frontend's `=== null` branch (the
    # "not enough data" placeholder) must NOT fire for this case.
    assert dumped["trailing_sharpe"] is not None


def test_strategy_state_out_leaves_none_and_finite_sharpe_unchanged():
    from app.schemas.execution import StrategyExecutionStateOut

    none_state = StrategyExecutionStateOut(
        forward_validation_registration_id=1, strategy_name="momentum_v1",
        ticker_a="AAA", ticker_b="AAA", halted_at=None, halted_reason=None,
        halted_trailing_sharpe=None, halted_trailing_days=None,
        trailing_sharpe=None, trailing_days=5, trailing_return=None,
        breaker_threshold=-1.0, breaker_lookback_trading_days=20,
    )
    assert none_state.model_dump(mode="json")["trailing_sharpe"] is None

    finite_state = StrategyExecutionStateOut(
        forward_validation_registration_id=1, strategy_name="momentum_v1",
        ticker_a="AAA", ticker_b="AAA", halted_at=None, halted_reason=None,
        halted_trailing_sharpe=None, halted_trailing_days=None,
        trailing_sharpe=1.234, trailing_days=20, trailing_return=0.01,
        breaker_threshold=-1.0, breaker_lookback_trading_days=20,
    )
    assert finite_state.model_dump(mode="json")["trailing_sharpe"] == pytest.approx(1.234)
