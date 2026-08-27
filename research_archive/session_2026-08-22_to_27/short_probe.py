"""Empirically confirm, against the real paper account, that:
  (a) a NOTIONAL sell that would open a short is REJECTED, and
  (b) a whole-share sell that would open a short is ACCEPTED.

This is the constraint the runner's order-shape routing exists for.
Both orders are placed with the market CLOSED so neither can fill, and both
are cancelled immediately.
"""

import sys
import uuid

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a3f3b867d41fcaf68/backend")

from app.services.execution import alpaca_client
from app.services.execution.alpaca_client import AlpacaError

assert alpaca_client.is_paper(), "REFUSING: not paper mode"

clock = alpaca_client.get_clock()
print("market open:", clock["is_open"], "(a day order placed while closed cannot fill)")
print("positions before:", alpaca_client.get_positions())

print("\n--- (a) NOTIONAL sell $1 AAPL while flat (would open a short) ---")
try:
    response = alpaca_client.submit_notional_order(
        symbol="AAPL", notional=1.00, side="sell", client_order_id=f"probe-a-{uuid.uuid4()}"
    )
    print("ACCEPTED (unexpected):", response.get("id"), response.get("status"))
except AlpacaError as exc:
    print("REJECTED as expected:", str(exc)[:300])

print("\n--- (b) QTY sell 1 share AAPL while flat (would open a short) ---")
order_id = None
try:
    response = alpaca_client.submit_qty_order(
        symbol="AAPL", qty=1, side="sell", client_order_id=f"probe-b-{uuid.uuid4()}"
    )
    order_id = response["id"]
    print("ACCEPTED:", order_id, response.get("status"), "qty=", response.get("qty"))
except AlpacaError as exc:
    print("REJECTED:", str(exc)[:300])

print("\n--- cleanup ---")
cancelled = alpaca_client.cancel_all_orders()
print("cancel_all_orders ->", len(cancelled), "affected")
if order_id:
    print("final status of (b):", alpaca_client.get_order(order_id)["status"])
print("open orders after:", len(alpaca_client.get_open_orders()))
print("positions after  :", alpaca_client.get_positions())
