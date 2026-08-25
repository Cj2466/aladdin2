from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class LiveOrder(Base):
    """The execution audit log: one row per order this system submitted (or
    deliberately declined to submit) to the broker.

    Same "typed columns for what's queried, JSON for the rest" convention as
    ExperimentRun — the broker's full response is kept verbatim in
    raw_response_json so a post-mortem never depends on having predicted which
    field would matter.

    This is an audit log, NOT a position mirror. The runner never reads it to
    decide what to trade; it re-derives current exposure from the broker's own
    /positions every tick. A stale local position cache is exactly the failure
    mode that causes double-order bugs — the same reasoning finnhub_ws_client
    already documents for re-deriving its subscription set from live state.
    """

    __tablename__ = "live_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    # Which strategy instance asked for this. Both are recorded because they
    # answer different questions: the registration is the durable identity
    # (survives portfolio re-optimization), the allocation is what actually
    # sized it on the day.
    forward_validation_registration_id: Mapped[int | None] = mapped_column(
        ForeignKey("forward_validation_registrations.id"), nullable=True, index=True
    )
    strategy_portfolio_allocation_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategy_portfolio_allocations.id"), nullable=True, index=True
    )

    ticker: Mapped[str] = mapped_column(String(10), index=True)
    side: Mapped[str] = mapped_column(String(10))
    # Exactly one of these is set, mirroring the two order shapes the broker
    # accepts. Alpaca does not permit short selling through notional/fractional
    # orders (confirmed against their docs), so any order that opens or extends
    # a short is submitted as whole shares instead.
    notional_requested: Mapped[float | None] = mapped_column(Float, nullable=True)
    qty_requested: Mapped[float | None] = mapped_column(Float, nullable=True)

    # "submitted" until the broker acknowledges; then the broker's own status
    # verbatim ("new"/"filled"/"canceled"/...). "rejected" for a broker
    # refusal, "error" for a local/transport failure, "skipped" for an order
    # this system deliberately declined to send (recorded so a decline is
    # auditable rather than invisible).
    status: Mapped[str] = mapped_column(String(20), index=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # Unique so a retry can never produce a duplicate order: the broker itself
    # rejects a repeated client_order_id, making idempotency the broker's
    # guarantee rather than ours.
    client_order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    submitted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    filled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    filled_avg_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    filled_qty: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- execution-quality measurement ---------------------------------------
    # The price the SIGNAL was computed on: the most recent cached daily close
    # for this ticker at the moment the order was decided. That is the correct
    # reference for testing this project's cost_bps assumption, because the
    # backtest realizes close-to-close returns and charges cost_bps against
    # them — so "what did we actually pay relative to that close" is exactly
    # the assumption under test. NULL when no cached close was available; the
    # order is still sent (a monitoring metric must never gate trading).
    decision_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Signed so that POSITIVE always means adverse (a cost), matching cost_bps'
    # own sign: paying above the decision price on a buy, or receiving below it
    # on a sell.
    realized_slippage_bps: Mapped[float | None] = mapped_column(Float, nullable=True)
    # The cost_bps this strategy's backtest and forward-validation assumed —
    # copied onto the row at submission so the comparison stays valid even if
    # the registration is later re-registered at a different cost.
    assumed_cost_bps: Mapped[float | None] = mapped_column(Float, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response_json: Mapped[str | None] = mapped_column(Text, nullable=True)
