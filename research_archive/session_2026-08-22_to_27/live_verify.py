"""LIVE verification of Phase 5 against the real Alpaca PAPER account.

Read paths only in phases 1-6. Phase 7 is an explicit, deliberate, minimum-
notional order test that is gated behind an argv flag.
"""

import json
import sys

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a3f3b867d41fcaf68/backend")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 registers every model
from app.config import settings
from app.db import Base
from app.services.execution import alpaca_client, execution_runner as runner_module
from app.services.execution.execution_control_service import (
    RESUME_CONFIRMATION,
    ResumeRefused,
    get_control,
    resume,
)
from app.services.execution.execution_runner import ExecutionRunner

DB_PATH = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/live_verify.db"


def hr(title):
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


hr("1. Mode and credentials")
print("alpaca_paper_trading      :", settings.alpaca_paper_trading)
print("alpaca_live_trading_confirmed:", settings.alpaca_live_trading_confirmed)
print("is_paper()                :", alpaca_client.is_paper())
print("base_url()                :", alpaca_client.base_url())
assert alpaca_client.is_paper(), "REFUSING TO CONTINUE: not in paper mode"
assert alpaca_client.base_url() == alpaca_client.PAPER_BASE_URL
print("key configured            :", bool(settings.alpaca_api_key))

hr("2. Live reads through the real client")
account = alpaca_client.get_account()
print("account.status      :", account["status"])
print("account.account_number:", account["account_number"])
print("equity (raw)        :", repr(account["equity"]), "-> parsed", alpaca_client.account_float(account, "equity"))
print("last_equity (raw)   :", repr(account["last_equity"]), "-> parsed", alpaca_client.account_float(account, "last_equity"))
print("trading_blocked     :", account["trading_blocked"], " account_blocked:", account["account_blocked"])
print("shorting_enabled    :", account.get("shorting_enabled"))

clock = alpaca_client.get_clock()
print("clock.is_open       :", clock["is_open"])
print("clock.timestamp     :", clock["timestamp"])
print("clock.next_open     :", clock["next_open"])

positions = alpaca_client.get_positions()
print("positions           :", len(positions), "open")
for p in positions:
    print(
        f"   {p['symbol']} side={p['side']} qty={p['qty']!r} market_value={p['market_value']!r} "
        f"-> signed_value={alpaca_client.position_signed_market_value(p)} "
        f"signed_qty={alpaca_client.position_signed_qty(p)}"
    )

open_orders = alpaca_client.get_open_orders()
print("open orders         :", len(open_orders))

hr("3. Full ExecutionRunner tick against the REAL broker, trading HALTED")
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
runner_module.SessionLocal = factory

calls = []
for name in ("get_account", "get_clock", "get_positions", "get_open_orders",
             "submit_notional_order", "submit_qty_order", "cancel_all_orders"):
    original = getattr(alpaca_client, name)

    def wrap(_name=name, _orig=original):
        def inner(*a, **kw):
            calls.append(_name)
            return _orig(*a, **kw)
        return inner

    setattr(alpaca_client, name, wrap())

with factory() as db:
    control = get_control(db)
    print("seeded control: halted =", control.trading_halted, " reason =", control.halted_reason)

calls.clear()
status = ExecutionRunner()._tick_sync()
print("tick status         :", status)
print("broker calls made   :", calls)
assert status == "halted" and calls == [], "A halted tick must make ZERO broker calls"
print("PASS: the kill switch short-circuits before any broker call.")

hr("4. Resume, then tick against the REAL broker with no live portfolio")
with factory() as db:
    resume(db, user_id=1, confirmation=RESUME_CONFIRMATION)
    print("resumed: halted =", get_control(db).trading_halted)

calls.clear()
status = ExecutionRunner()._tick_sync()
print("tick status         :", status)
print("broker calls made   :", calls)
assert "submit_notional_order" not in calls and "submit_qty_order" not in calls
print("PASS: real account/clock reads succeeded; zero orders submitted.")

hr("5. Simulated daily-loss breach against the real account (limit set to 0%)")
# The real account is flat on the day (equity == last_equity), so a 0% limit
# makes any non-positive P&L a breach — a genuine live exercise of the breaker
# path, including the REAL cancel_all_orders call.
real_limit = settings.execution_daily_loss_limit_pct
settings.execution_daily_loss_limit_pct = 0.0
settings.execution_alert_email = ""  # no email in a test
calls.clear()
status = ExecutionRunner()._tick_sync()
settings.execution_daily_loss_limit_pct = real_limit
print("tick status         :", status)
print("broker calls made   :", calls)
with factory() as db:
    control = get_control(db)
    print("halted              :", control.trading_halted)
    print("halted_reason       :", control.halted_reason)
    print("daily_loss_breach_at:", control.daily_loss_breach_at)
    print("daily_loss_breach_pct:", control.daily_loss_breach_pct)
assert status == "daily_loss_breach"
assert "cancel_all_orders" in calls, "A breach must cancel open orders"
print("PASS: the breaker halted trading and cancelled open orders against the real account.")

hr("6. Resume gates after a same-day breach")
with factory() as db:
    try:
        resume(db, user_id=1, confirmation="resume live trading")
        print("FAIL: a wrong confirmation was accepted")
    except ResumeRefused as exc:
        print("wrong confirmation refused :", exc)
    try:
        resume(db, user_id=1, confirmation=RESUME_CONFIRMATION)
        print("FAIL: resume succeeded on the same day as a breach")
    except ResumeRefused as exc:
        print("same-day resume refused    :", exc)
    print("still halted               :", get_control(db).trading_halted)
    assert get_control(db).trading_halted is True

calls.clear()
status = ExecutionRunner()._tick_sync()
print("next tick status           :", status, "| broker calls:", calls)
assert status == "halted" and calls == []
print("PASS: one-shot per breach — no repeated cancels or emails.")

if "--place-test-order" not in sys.argv:
    hr("7. SKIPPED: live order test (pass --place-test-order to run)")
    sys.exit(0)

hr("7. DELIBERATE minimum-notional order test on the PAPER account")
print("Placing ONE $1.00 notional BUY of AAPL, then cancelling it immediately.")
print("Market open:", clock["is_open"], "-> a day order placed while closed cannot fill.")
import uuid

client_order_id = f"aladdin2-verify-{uuid.uuid4()}"
try:
    response = alpaca_client.submit_notional_order(
        symbol="AAPL", notional=1.00, side="buy", client_order_id=client_order_id
    )
    print("submitted:", json.dumps({k: response[k] for k in ("id", "status", "symbol", "notional", "side", "type", "time_in_force")}, indent=2))
    order_id = response["id"]

    fetched = alpaca_client.get_order(order_id)
    print("status after submit:", fetched["status"], "filled_qty:", fetched.get("filled_qty"))

    cancelled = alpaca_client.cancel_all_orders()
    print("cancel_all_orders ->", len(cancelled), "affected")

    final = alpaca_client.get_order(order_id)
    print("final status:", final["status"], "filled_qty:", final.get("filled_qty"))

    after = alpaca_client.get_positions()
    print("positions after:", [(p["symbol"], p["qty"]) for p in after])
except Exception as exc:
    print("ORDER TEST FAILED:", exc)
    raise
