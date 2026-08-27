"""ExecutionRunner: the full safety matrix.

Mirrors test_forward_validation.py's SessionLocal monkeypatch pattern — the
runner is not a FastAPI route, so conftest's get_db override never reaches it.
"""

import json
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.experiment_run import ExperimentRun
from app.models.forward_validation import ForwardValidationRegistration
from app.models.live_order import LiveOrder
from app.models.price_bar import PriceBar
from app.models.strategy_execution_state import StrategyExecutionState
from app.models.strategy_portfolio import StrategyPortfolio
from app.models.strategy_portfolio_allocation import StrategyPortfolioAllocation
from app.models.user import User
from app.services.execution import alpaca_client, execution_runner as runner_module
from app.services.execution import strategy_breaker
from app.services.execution.alpaca_client import AlpacaError
from app.services.execution.execution_control_service import get_control, halt
from app.services.execution.execution_runner import ExecutionRunner
from app.services.forward_validation_service import compute_forward_validation_config_hash
from app.services.research_lab.engine import WalkForwardState, serialize_walk_forward_state

MOMENTUM = "momentum_v1"
PAIRS = "ou_pairs_v1"


class _Broker:
    """A scripted broker. Every call is recorded so a test can assert that a
    fail-closed path made ZERO submissions, not merely that nothing filled."""

    def __init__(self):
        self.account = {
            "equity": "100000",
            "last_equity": "100000",
            "cash": "100000",
            "buying_power": "400000",
            "status": "ACTIVE",
            "trading_blocked": False,
            "account_blocked": False,
        }
        self.clock = {"is_open": True}
        self.positions: list[dict] = []
        self.open_orders: list[dict] = []
        self.orders_by_id: dict[str, dict] = {}
        self.submitted: list[dict] = []
        self.cancel_calls = 0
        self.fail: set[str] = set()
        self._next_id = 0

    def _maybe_fail(self, name):
        if name in self.fail:
            raise AlpacaError(f"simulated {name} failure")

    def get_account(self, **_kw):
        self._maybe_fail("account")
        return self.account

    def get_clock(self, **_kw):
        self._maybe_fail("clock")
        return self.clock

    def get_positions(self, **_kw):
        self._maybe_fail("positions")
        return self.positions

    def get_open_orders(self, _symbol=None, **_kw):
        self._maybe_fail("open_orders")
        return self.open_orders

    def get_order(self, order_id, **_kw):
        self._maybe_fail("get_order")
        return self.orders_by_id[order_id]

    def cancel_all_orders(self, **_kw):
        self.cancel_calls += 1
        cancelled = list(self.open_orders)
        self.open_orders = []
        return cancelled

    def _submit(self, payload):
        self._maybe_fail("submit")
        self._next_id += 1
        order_id = f"broker-{self._next_id}"
        response = {"id": order_id, "status": "accepted", **payload}
        self.submitted.append(payload)
        self.orders_by_id[order_id] = response
        # A real broker reports a just-accepted order as open until it fills,
        # which is what stops the next tick stacking a second one.
        self.open_orders.append({"symbol": payload["symbol"], "id": order_id})
        return response

    def fill_all(self, prices: dict[str, float]) -> None:
        """Mark every working order filled at the given price per symbol."""
        for order_id, order in self.orders_by_id.items():
            if order["status"] in ("filled", "canceled"):
                continue
            self.orders_by_id[order_id] = {
                **order,
                "status": "filled",
                "filled_qty": "10",
                "filled_avg_price": str(prices[order["symbol"]]),
                "filled_at": "2026-08-26T14:31:00Z",
            }
        self.open_orders = []

    def submit_notional_order(self, *, symbol, notional, side, client_order_id, **_kw):
        return self._submit(
            {"symbol": symbol, "notional": notional, "side": side, "client_order_id": client_order_id}
        )

    def submit_qty_order(self, *, symbol, qty, side, client_order_id, **_kw):
        return self._submit(
            {"symbol": symbol, "qty": qty, "side": side, "client_order_id": client_order_id}
        )


def _position(symbol, *, qty, price, intraday_pnl=0.0):
    value = abs(qty) * price
    side = "long" if qty >= 0 else "short"
    return {
        "symbol": symbol,
        "side": side,
        # Negative for a short, matching the convention real payloads use — the
        # client derives the sign from `side` regardless.
        "qty": str(qty),
        "market_value": str(value if qty >= 0 else -value),
        "unrealized_intraday_pl": str(intraday_pnl),
        "current_price": str(price),
    }


@pytest.fixture
def broker(monkeypatch):
    fake = _Broker()
    for name in (
        "get_account", "get_clock", "get_positions", "get_open_orders", "get_order",
        "cancel_all_orders", "submit_notional_order", "submit_qty_order",
    ):
        monkeypatch.setattr(alpaca_client, name, getattr(fake, name))
    monkeypatch.setattr(settings, "alpaca_api_key", "k")
    monkeypatch.setattr(settings, "alpaca_api_secret", "s")
    return fake


@pytest.fixture
def emails(monkeypatch):
    sent = []
    monkeypatch.setattr(runner_module, "send_email", lambda to, subject, body: sent.append(subject))
    monkeypatch.setattr(settings, "execution_alert_email", "ops@example.com")
    return sent


@pytest.fixture
def session_local(test_db_engine, monkeypatch):
    factory = sessionmaker(bind=test_db_engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(runner_module, "SessionLocal", factory)
    return factory


@pytest.fixture
def world(session_local):
    """A live portfolio with two forward-validated momentum strategies and one
    pairs strategy, all owned by one user."""
    with session_local() as db:
        user = User(email="trader@example.com", password_hash="x", is_verified=True)
        db.add(user)
        db.flush()

        portfolio = StrategyPortfolio(user_id=user.id, name="Live", is_live=True)
        db.add(portfolio)
        db.flush()

        for ticker, price in (("AAA", 100.0), ("BBB", 50.0), ("CCC", 25.0)):
            db.add(
                PriceBar(ticker=ticker, date=date.today() - timedelta(days=1), adj_close=price)
            )

        registration_ids = {}
        for ticker in ("AAA", "BBB"):
            _register_momentum(db, user.id, portfolio.id, ticker, registration_ids, weight=0.4)
        db.commit()
        return {
            "user_id": user.id,
            "portfolio_id": portfolio.id,
            "registrations": registration_ids,
        }


def _register_momentum(db, user_id, portfolio_id, ticker, out, *, weight, position=1, status="forward_validated"):
    config = dict(
        strategy_name=MOMENTUM, ticker_a=ticker, ticker_b=ticker,
        fit_window_days=90, entry_z=2.0, exit_z=0.0, cost_bps=5.0,
    )
    run = ExperimentRun(
        **config, input_hash=f"h-{ticker}", results_json="{}", status="ok",
        lookback_years=5, num_trades=3,
    )
    db.add(run)
    db.flush()
    registration = ForwardValidationRegistration(
        user_id=user_id, **config,
        config_hash=compute_forward_validation_config_hash(**config),
        status=status, min_trading_days_threshold=126, n_forward_trading_days=200,
        started_at=date.today() - timedelta(days=300),
        carry_state_json=json.dumps(
            serialize_walk_forward_state(WalkForwardState(position=position))
        ),
    )
    db.add(registration)
    db.flush()
    db.add(
        StrategyPortfolioAllocation(
            strategy_portfolio_id=portfolio_id, experiment_run_id=run.id, weight=weight
        )
    )
    out[ticker] = registration.id
    return registration


def _tick(runner=None) -> str:
    return (runner or ExecutionRunner())._tick_sync()


# --- kill switch --------------------------------------------------------------


def test_halted_makes_zero_broker_calls(broker, world, session_local):
    """The kill switch is checked before ANY broker call, including the
    account read."""
    assert _tick() == "halted"
    assert broker.submitted == []
    assert broker.cancel_calls == 0


def test_a_fresh_database_starts_halted(session_local):
    """A deploy, a restored backup, or any new database must never silently
    begin trading."""
    with session_local() as db:
        control = get_control(db)
        assert control.trading_halted is True
        assert control.halted_reason == "startup_default"


@pytest.fixture
def trading_enabled(session_local, world):
    with session_local() as db:
        control = get_control(db)
        control.trading_halted = False
        db.commit()
    return world


# --- the daily-loss circuit breaker -------------------------------------------


def test_loss_breach_halts_cancels_and_emails_exactly_once(broker, trading_enabled, session_local, emails):
    broker.account["equity"] = "96000"  # -4%, past the 3% limit
    broker.open_orders = [{"symbol": "AAA", "id": "o1"}]

    assert _tick() == "daily_loss_breach"
    assert broker.cancel_calls == 1
    assert len(emails) == 1
    assert broker.submitted == []

    # A second consecutive tick finds trading already halted and takes no
    # further action — one-shot per breach, not one email per minute.
    assert _tick() == "halted"
    assert broker.cancel_calls == 1
    assert len(emails) == 1


def test_loss_breach_records_the_breach_for_the_resume_gate(broker, trading_enabled, session_local):
    broker.account["equity"] = "96000"
    _tick()
    with session_local() as db:
        control = get_control(db)
        assert control.trading_halted is True
        assert control.daily_loss_breach_at is not None
        assert control.daily_loss_breach_pct == pytest.approx(-0.04)


def test_a_loss_inside_the_limit_does_not_halt(broker, trading_enabled, session_local):
    broker.account["equity"] = "98000"  # -2%
    status = _tick()
    assert status.startswith("ok")
    with session_local() as db:
        assert get_control(db).trading_halted is False


def test_positions_are_never_force_liquidated_on_a_breach(broker, trading_enabled, session_local):
    """Forced flattening during exactly the stressed moment that triggered a
    halt can realize a worse price than waiting."""
    broker.positions = [_position("AAA", qty=10, price=100.0)]
    broker.account["equity"] = "96000"
    _tick()
    assert broker.submitted == []


def test_broker_reported_account_block_halts(broker, trading_enabled, session_local):
    broker.account["account_blocked"] = True
    assert _tick() == "broker_blocked"
    with session_local() as db:
        assert get_control(db).trading_halted is True


# --- fail-closed reads --------------------------------------------------------


@pytest.mark.parametrize(
    "failure,expected",
    [
        ("account", "account_read_failed"),
        ("clock", "clock_read_failed"),
        ("positions", "positions_read_failed"),
        ("open_orders", "positions_read_failed"),
    ],
)
def test_any_failed_read_submits_nothing_and_halts_nothing(
    broker, trading_enabled, session_local, failure, expected
):
    """Fail closed, never fail open: no "assume flat", no "assume open". The
    tick just does nothing and leaves state untouched."""
    broker.fail.add(failure)
    assert _tick() == expected
    assert broker.submitted == []
    with session_local() as db:
        assert get_control(db).trading_halted is False  # a read failure is not a halt


def test_market_closed_submits_nothing(broker, trading_enabled, session_local):
    broker.clock = {"is_open": False}
    assert _tick() == "market_closed"
    assert broker.submitted == []


def test_missing_credentials_short_circuit_the_tick(broker, trading_enabled, monkeypatch):
    monkeypatch.setattr(settings, "alpaca_api_key", "")
    assert _tick() == "no_credentials"
    assert broker.submitted == []


# --- the rebalance ------------------------------------------------------------


def test_flat_account_opens_one_order_per_ticker(broker, trading_enabled, session_local):
    status = _tick()
    assert status == "ok:2_orders"
    by_symbol = {o["symbol"]: o for o in broker.submitted}
    assert set(by_symbol) == {"AAA", "BBB"}
    # 0.4 weight x 0.5 capital fraction x 100k equity = 20k, clamped by the
    # $1000 per-ticker cap.
    assert by_symbol["AAA"]["notional"] == pytest.approx(settings.execution_max_position_notional)


def test_target_already_matching_current_submits_nothing(broker, trading_enabled, session_local):
    _tick()
    broker.fill_all({"AAA": 100.0, "BBB": 50.0})
    broker.submitted.clear()
    cap = settings.execution_max_position_notional
    broker.positions = [
        _position("AAA", qty=cap / 100.0, price=100.0),
        _position("BBB", qty=cap / 50.0, price=50.0),
    ]
    assert _tick() == "ok:0_orders"
    assert broker.submitted == []


def test_a_ticker_with_an_open_order_is_skipped_not_stacked(broker, trading_enabled, session_local):
    broker.open_orders = [{"symbol": "AAA", "id": "o1"}]
    _tick()
    assert [o["symbol"] for o in broker.submitted] == ["BBB"]


def test_no_live_portfolio_means_no_trading(broker, trading_enabled, session_local):
    with session_local() as db:
        portfolio = db.get(StrategyPortfolio, trading_enabled["portfolio_id"])
        portfolio.is_live = False
        db.commit()
    assert _tick() == "no_live_portfolio"
    assert broker.submitted == []


def test_a_flat_signal_produces_no_target(broker, trading_enabled, session_local):
    with session_local() as db:
        registration = db.get(
            ForwardValidationRegistration, trading_enabled["registrations"]["AAA"]
        )
        registration.carry_state_json = json.dumps(
            serialize_walk_forward_state(WalkForwardState(position=0))
        )
        db.commit()
    _tick()
    assert [o["symbol"] for o in broker.submitted] == ["BBB"]


def test_a_short_signal_routes_to_a_whole_share_order(broker, trading_enabled, session_local):
    """Alpaca cannot open a short through a notional order."""
    with session_local() as db:
        registration = db.get(
            ForwardValidationRegistration, trading_enabled["registrations"]["AAA"]
        )
        registration.carry_state_json = json.dumps(
            serialize_walk_forward_state(WalkForwardState(position=-1))
        )
        db.commit()
    _tick()
    order = next(o for o in broker.submitted if o["symbol"] == "AAA")
    assert order["side"] == "sell"
    assert "qty" in order and "notional" not in order
    assert order["qty"] == pytest.approx(10.0)  # $1000 cap / $100 close


# --- allocation resolution ----------------------------------------------------


def test_an_in_progress_registration_is_not_traded(broker, trading_enabled, session_local):
    """Trading capital against a configuration that has not cleared its own
    126-day evidence bar is a different decision from continuing to measure it."""
    with session_local() as db:
        registration = db.get(
            ForwardValidationRegistration, trading_enabled["registrations"]["AAA"]
        )
        registration.status = "in_progress"
        db.commit()
    _tick()
    assert [o["symbol"] for o in broker.submitted] == ["BBB"]


def test_an_underperforming_registration_is_not_traded(broker, trading_enabled, session_local):
    with session_local() as db:
        registration = db.get(
            ForwardValidationRegistration, trading_enabled["registrations"]["BBB"]
        )
        registration.status = "underperforming"
        db.commit()
    _tick()
    assert [o["symbol"] for o in broker.submitted] == ["AAA"]


def test_an_unregistered_allocation_is_skipped_and_the_rest_still_trades(
    broker, trading_enabled, session_local
):
    """One bad reference must never cost the whole tick."""
    with session_local() as db:
        orphan = ExperimentRun(
            strategy_name=MOMENTUM, ticker_a="ZZZ", ticker_b="ZZZ", fit_window_days=90,
            entry_z=2.0, exit_z=0.0, cost_bps=5.0, input_hash="orphan", results_json="{}",
            status="ok", lookback_years=5, num_trades=1,
        )
        db.add(orphan)
        db.flush()
        db.add(
            StrategyPortfolioAllocation(
                strategy_portfolio_id=trading_enabled["portfolio_id"],
                experiment_run_id=orphan.id, weight=0.2,
            )
        )
        db.commit()
    _tick()
    assert sorted(o["symbol"] for o in broker.submitted) == ["AAA", "BBB"]


# --- the hard dollar caps -----------------------------------------------------


def test_the_total_gross_cap_scales_every_leg_and_preserves_the_pairs_ratio(
    broker, session_local, monkeypatch
):
    """A partially-honored pairs trade stops being market-neutral, which is a
    worse and different risk than simply being smaller."""
    # Only the TOTAL cap binds. The per-ticker clamp is deliberately left
    # slack: it is a blunt per-symbol ceiling that can legitimately clamp one
    # leg and not the other (documented in apply_caps), so mixing it in would
    # test the wrong rule.
    monkeypatch.setattr(settings, "execution_max_position_notional", 100_000.0)
    monkeypatch.setattr(settings, "execution_max_total_notional", 30_000.0)

    with session_local() as db:
        user = User(email="pairs@example.com", password_hash="x", is_verified=True)
        db.add(user)
        db.flush()
        portfolio = StrategyPortfolio(user_id=user.id, name="Pairs", is_live=True)
        db.add(portfolio)
        db.flush()
        for ticker, price in (("AAA", 100.0), ("BBB", 50.0)):
            db.add(PriceBar(ticker=ticker, date=date.today(), adj_close=price))

        config = dict(
            strategy_name=PAIRS, ticker_a="AAA", ticker_b="BBB", fit_window_days=252,
            entry_z=2.0, exit_z=0.0, cost_bps=10.0,
        )
        run = ExperimentRun(
            **config, input_hash="p1", results_json="{}", status="ok", lookback_years=5, num_trades=2
        )
        db.add(run)
        db.flush()
        db.add(
            ForwardValidationRegistration(
                user_id=user.id, **config,
                config_hash=compute_forward_validation_config_hash(**config),
                status="forward_validated", min_trading_days_threshold=126,
                n_forward_trading_days=200, started_at=date.today() - timedelta(days=300),
                carry_state_json=json.dumps(
                    serialize_walk_forward_state(
                        WalkForwardState(position=1, last_fit_params={"hedge_ratio": 0.8})
                    )
                ),
            )
        )
        db.add(
            StrategyPortfolioAllocation(
                strategy_portfolio_id=portfolio.id, experiment_run_id=run.id, weight=1.0
            )
        )
        get_control(db).trading_halted = False
        db.commit()

    _tick()

    by_symbol = {o["symbol"]: o for o in broker.submitted}
    # hedge_ratio 0.8 -> gross 1.8: long BBB 1/1.8, short AAA 0.8/1.8. The
    # ratio between the two legs must survive the total-gross scaling — this is
    # the assertion that catches "trimmed one leg and left the other".
    long_leg = by_symbol["BBB"]["notional"]
    short_leg = by_symbol["AAA"]["qty"] * 100.0  # whole shares at the $100 close
    assert short_leg / long_leg == pytest.approx(0.8, rel=0.01)
    assert long_leg + short_leg <= settings.execution_max_total_notional
    # The cap genuinely bound: uncapped this would have been $50,000 gross.
    assert long_leg + short_leg > settings.execution_max_total_notional * 0.95


# --- the per-strategy circuit breaker -----------------------------------------


def _seed_losing_history(db, registration_id, *, days=25, daily_return=-0.004):
    state = StrategyExecutionState(
        user_id=db.query(ForwardValidationRegistration).get(registration_id).user_id,
        forward_validation_registration_id=registration_id,
        day_pnl_json=json.dumps(
            [
                {
                    "date": (date(2026, 1, 1) + timedelta(days=i)).isoformat(),
                    "pnl": daily_return * 1000.0,
                    "return": daily_return,
                    "allocated_capital": 1000.0,
                }
                for i in range(days)
            ]
        ),
    )
    db.add(state)
    return state


def test_one_breaching_strategy_is_pulled_while_the_others_keep_trading(
    broker, trading_enabled, session_local, emails
):
    with session_local() as db:
        _seed_losing_history(db, trading_enabled["registrations"]["AAA"])
        db.commit()

    _tick()

    # AAA is pulled; BBB trades normally; the account itself is untouched.
    assert [o["symbol"] for o in broker.submitted] == ["BBB"]
    with session_local() as db:
        assert get_control(db).trading_halted is False
        state = db.query(StrategyExecutionState).filter_by(
            forward_validation_registration_id=trading_enabled["registrations"]["AAA"]
        ).one()
        assert state.halted_at is not None
        assert state.halted_reason == "trailing_sharpe_breach"
        assert state.halted_trailing_sharpe <= strategy_breaker.BREAKER_SHARPE_THRESHOLD
    assert any("pulled from live execution" in subject for subject in emails)


def test_a_pulled_strategy_holds_its_position_instead_of_being_liquidated(
    broker, trading_enabled, session_local
):
    """Dropping a halted strategy from the aggregate would lower its tickers'
    targets and make the very next tick SELL — force-liquidating during exactly
    the event that triggered the halt."""
    _tick()  # open the initial positions
    broker.fill_all({"AAA": 100.0, "BBB": 50.0})
    cap = settings.execution_max_position_notional
    broker.positions = [
        _position("AAA", qty=cap / 100.0, price=100.0, intraday_pnl=-4.0),
        _position("BBB", qty=cap / 50.0, price=50.0),
    ]
    with session_local() as db:
        state = db.query(StrategyExecutionState).filter_by(
            forward_validation_registration_id=trading_enabled["registrations"]["AAA"]
        ).one()
        state.day_pnl_json = json.dumps(
            [
                {
                    "date": (date(2026, 1, 1) + timedelta(days=i)).isoformat(),
                    "pnl": -4.0, "return": -0.004, "allocated_capital": 1000.0,
                }
                for i in range(25)
            ]
        )
        db.commit()
    broker.submitted.clear()

    _tick()  # trips the breaker and freezes AAA's target
    broker.submitted.clear()
    _tick()  # the tick that would liquidate, if the freeze did not work

    assert broker.submitted == []
    with session_local() as db:
        state = db.query(StrategyExecutionState).filter_by(
            forward_validation_registration_id=trading_enabled["registrations"]["AAA"]
        ).one()
        assert json.loads(state.frozen_target_json)["AAA"] > 0


def test_the_account_wide_breaker_still_halts_everything_independently(
    broker, trading_enabled, session_local, emails
):
    """The two layers are independent: a healthy per-strategy picture does not
    stop the account-wide breaker."""
    broker.account["equity"] = "96000"
    assert _tick() == "daily_loss_breach"
    assert broker.submitted == []
    with session_local() as db:
        assert get_control(db).trading_halted is True


def test_a_healthy_strategy_is_never_pulled(broker, trading_enabled, session_local):
    with session_local() as db:
        _seed_losing_history(db, trading_enabled["registrations"]["AAA"], daily_return=0.004)
        db.commit()
    _tick()
    with session_local() as db:
        state = db.query(StrategyExecutionState).filter_by(
            forward_validation_registration_id=trading_enabled["registrations"]["AAA"]
        ).one()
        assert state.halted_at is None


def test_pnl_is_recorded_once_per_trading_day_not_once_per_tick(
    broker, trading_enabled, session_local
):
    broker.positions = [_position("AAA", qty=10, price=100.0, intraday_pnl=-3.0)]
    for _ in range(4):
        _tick()
    with session_local() as db:
        state = db.query(StrategyExecutionState).filter_by(
            forward_validation_registration_id=trading_enabled["registrations"]["AAA"]
        ).one()
        assert len(json.loads(state.day_pnl_json)) == 1


# --- the audit log and slippage -----------------------------------------------


def test_every_submission_writes_a_live_order_row(broker, trading_enabled, session_local):
    _tick()
    with session_local() as db:
        orders = db.query(LiveOrder).all()
        assert {o.ticker for o in orders} == {"AAA", "BBB"}
        assert all(o.broker_order_id is not None for o in orders)
        assert all(o.client_order_id.startswith("aladdin2-") for o in orders)
        # The decision price and the assumed cost are captured at submission,
        # so slippage stays comparable even if the registration changes later.
        assert all(o.decision_price is not None for o in orders)
        assert all(o.assumed_cost_bps == 5.0 for o in orders)


def test_client_order_ids_are_unique_across_ticks(broker, trading_enabled, session_local):
    _tick()
    broker.fill_all({"AAA": 100.0, "BBB": 50.0})
    _tick()
    with session_local() as db:
        ids = [o.client_order_id for o in db.query(LiveOrder).all()]
        assert len(ids) == len(set(ids))


def test_a_broker_rejection_is_recorded_not_swallowed(broker, trading_enabled, session_local):
    broker.fail.add("submit")
    _tick()
    with session_local() as db:
        orders = db.query(LiveOrder).all()
        assert orders
        assert all(o.status == "error" for o in orders)
        assert all("simulated submit failure" in (o.error_message or "") for o in orders)


def test_a_fill_is_reconciled_into_realized_slippage(broker, trading_enabled, session_local):
    _tick()
    # $100 close filled at $100.20 -> 20bps adverse on a buy.
    broker.fill_all({"AAA": 100.20, "BBB": 50.10})
    # The account now holds what those fills bought, so the next tick's only
    # work is reconciliation.
    broker.positions = [
        _position("AAA", qty=10, price=100.0),
        _position("BBB", qty=20, price=50.0),
    ]

    _tick()

    with session_local() as db:
        aaa = db.query(LiveOrder).filter_by(ticker="AAA").one()
        assert aaa.status == "filled"
        assert aaa.filled_avg_price == pytest.approx(100.20)
        assert aaa.realized_slippage_bps == pytest.approx(20.0)
        # Real slippage of 20bps against an assumed 5bps is exactly the silent
        # divergence this measurement exists to make visible.
        assert aaa.assumed_cost_bps == 5.0


def test_reconciliation_failure_does_not_stop_the_tick(broker, trading_enabled, session_local):
    _tick()
    broker.fail.add("get_order")
    broker.open_orders = []
    status = _tick()
    assert status.startswith("ok")


def test_a_manual_halt_recorded_by_the_service_stops_the_next_tick(
    broker, trading_enabled, session_local
):
    with session_local() as db:
        halt(db, reason="manual:test", user_id=trading_enabled["user_id"])
    assert _tick() == "halted"
    assert broker.submitted == []
