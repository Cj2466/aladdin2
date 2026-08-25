import asyncio
import json
import logging
import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db import SessionLocal
from app.models.forward_validation import ForwardValidationRegistration
from app.models.live_order import LiveOrder
from app.models.price_bar import PriceBar
from app.models.strategy_execution_state import StrategyExecutionState
from app.models.strategy_portfolio import StrategyPortfolio
from app.services.email.resend_client import send_email
from app.services.execution import alpaca_client, slippage, strategy_breaker, targets
from app.services.execution.alpaca_client import AlpacaError
from app.services.execution.allocation_resolver import resolve_registration
from app.services.execution.execution_control_service import (
    eastern_trading_date,
    get_control,
    halt,
)
from app.services.research_lab.engine import deserialize_walk_forward_state
from app.services.research_lab.strategy_registry import get_adapter
from app.time_utils import utcnow_naive

logger = logging.getLogger(__name__)

# Broker order statuses that will never change again. Anything else stays in
# the reconciliation queue.
TERMINAL_ORDER_STATUSES = frozenset(
    {"filled", "canceled", "cancelled", "expired", "rejected", "done_for_day", "replaced", "stopped"}
)

# How many not-yet-terminal orders to reconcile per tick. Bounded so a backlog
# can never turn one tick into an unbounded sequence of broker calls.
RECONCILE_BATCH_SIZE = 50


class ExecutionRunner:
    """Turns forward-validated strategy signals into real broker orders.

    Modeled on ForwardValidationRunner: `while True: tick(); sleep()`,
    per-item isolation, all synchronous work dispatched through
    asyncio.to_thread. This is the ninth background task in main.py's
    lifespan().

    One tick, in order, every step of which returns immediately on failure
    rather than assuming anything:

      1. Kill switch. Halted -> return before a single broker call. Literally
         zero, not merely zero orders: it is a much easier property to verify,
         and the only cost is that fill reconciliation (step 2) pauses while
         halted and catches up on the first tick after a human resumes.
      2. Fill reconciliation. Poll not-yet-terminal orders, record fills and
         realized slippage. Best-effort and never gates trading.
      3. Account read -> daily-loss circuit breaker (Alpaca's own
         equity/last_equity, not our arithmetic).
      4. Clock read -> skip the whole rebalance if the market is closed.
      5. Positions and open orders read.
      6. Resolve the single is_live portfolio's allocations to live signals and
         size each one's target legs.
      7. Attribute broker P&L per strategy, record it, and run the per-strategy
         circuit breaker.
      8. Aggregate, cap, diff against real positions, submit only the deltas.

    Fail-closed is structural, not a convention: every external read that still
    fails after retries causes the tick to log and return with zero order
    submissions and zero state mutation. There is no "assume flat" and no
    "assume the market is open" anywhere in this file.
    """

    async def run(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Execution tick failed; will retry next interval.")
            await asyncio.sleep(settings.execution_check_interval_seconds)

    async def _tick(self) -> None:
        await asyncio.to_thread(self._tick_sync)

    # --- one synchronous tick -------------------------------------------------

    def _tick_sync(self) -> str:
        db = SessionLocal()
        try:
            control = get_control(db)
            if control.trading_halted:
                # One-shot per halt: a tick that finds trading already halted
                # returns immediately, so a breach never re-cancels or re-emails
                # on every subsequent tick.
                return self._finish(db, "halted")

            if not settings.alpaca_api_key or not settings.alpaca_api_secret:
                return self._finish(db, "no_credentials")

            self._reconcile_open_orders(db)

            try:
                account = alpaca_client.get_account()
            except AlpacaError as exc:
                logger.warning("Execution: account read failed, skipping tick: %s", exc)
                return self._finish(db, "account_read_failed")

            breach = self._check_daily_loss(db, account)
            if breach is not None:
                return self._finish(db, breach)

            if account.get("trading_blocked") or account.get("account_blocked"):
                halt(db, reason="broker_reported_account_blocked")
                self._cancel_all_safely()
                return self._finish(db, "broker_blocked")

            try:
                clock = alpaca_client.get_clock()
            except AlpacaError as exc:
                logger.warning("Execution: clock read failed, skipping tick: %s", exc)
                return self._finish(db, "clock_read_failed")
            if not clock.get("is_open"):
                return self._finish(db, "market_closed")

            try:
                positions = alpaca_client.get_positions()
                open_orders = alpaca_client.get_open_orders()
            except AlpacaError as exc:
                logger.warning("Execution: position/order read failed, skipping tick: %s", exc)
                return self._finish(db, "positions_read_failed")

            equity = alpaca_client.account_float(account, "equity")
            return self._finish(db, self._rebalance(db, account, equity, positions, open_orders))
        finally:
            db.close()

    def _finish(self, db: Session, status: str) -> str:
        control = get_control(db)
        control.last_tick_at = utcnow_naive()
        control.last_tick_status = status[:255]
        db.commit()
        return status

    # --- safety layers --------------------------------------------------------

    def _check_daily_loss(self, db: Session, account: dict) -> str | None:
        """Account-wide circuit breaker. Reads Alpaca's own server-side equity
        and last_equity rather than deriving equity from our own order history
        — which could itself have the bug that is losing the money."""
        try:
            equity = alpaca_client.account_float(account, "equity")
            last_equity = alpaca_client.account_float(account, "last_equity")
        except AlpacaError as exc:
            logger.warning("Execution: unusable account equity fields (%s); halting.", exc)
            halt(db, reason="unreadable_account_equity")
            self._cancel_all_safely()
            return "unreadable_equity_halt"

        if last_equity <= 0:
            return None  # nothing to measure against yet; not a breach

        daily_pnl_pct = (equity - last_equity) / last_equity
        if daily_pnl_pct > -settings.execution_daily_loss_limit_pct:
            return None

        logger.error(
            "DAILY LOSS CIRCUIT BREAKER: account P&L %.2f%% breached the %.2f%% limit. "
            "Halting all trading and cancelling open orders.",
            daily_pnl_pct * 100,
            -settings.execution_daily_loss_limit_pct * 100,
        )
        halt(db, reason="daily_loss_limit_breached", breach_pct=daily_pnl_pct)
        self._cancel_all_safely()
        self._send_breach_email(daily_pnl_pct, equity, last_equity)
        return "daily_loss_breach"

    def _cancel_all_safely(self) -> None:
        """Cancelling on a halt must never itself raise past the caller — a
        failed cancel is bad, but a halt that did not get recorded because the
        cancel threw would be much worse."""
        try:
            cancelled = alpaca_client.cancel_all_orders()
            logger.warning("Execution: cancelled %s open order(s) on halt.", len(cancelled))
        except AlpacaError:
            logger.exception("Execution: failed to cancel open orders during halt.")

    def _send_breach_email(self, pct: float, equity: float, last_equity: float) -> None:
        if not settings.execution_alert_email:
            return
        send_email(
            settings.execution_alert_email,
            "Aladdin2: daily-loss circuit breaker fired — trading halted",
            (
                f"Account P&L today: {pct * 100:.2f}% "
                f"(equity {equity:,.2f} vs. previous close {last_equity:,.2f}).\n"
                f"Limit: {-settings.execution_daily_loss_limit_pct * 100:.2f}%.\n\n"
                "All trading has been halted and every open order cancelled. Existing positions "
                "were deliberately NOT liquidated. Trading cannot be resumed until the next "
                "trading day."
            ),
        )

    # --- the rebalance --------------------------------------------------------

    def _rebalance(
        self,
        db: Session,
        account: dict,
        equity: float,
        positions: list[dict],
        open_orders: list[dict],
    ) -> str:
        del account
        portfolios = (
            db.execute(
                select(StrategyPortfolio)
                .where(StrategyPortfolio.is_live.is_(True))
                .options(selectinload(StrategyPortfolio.allocations))
            )
            .scalars()
            .all()
        )
        if not portfolios:
            return "no_live_portfolio"

        current_values = {
            p["symbol"]: alpaca_client.position_signed_market_value(p) for p in positions
        }
        current_qtys = {p["symbol"]: alpaca_client.position_signed_qty(p) for p in positions}
        position_pnl = {
            p["symbol"]: pnl
            for p in positions
            if (pnl := alpaca_client.position_intraday_pnl(p)) is not None
        }
        open_order_tickers = {o["symbol"] for o in open_orders if o.get("symbol")}
        trade_date = eastern_trading_date(utcnow_naive())

        submitted = 0
        for portfolio in portfolios:
            submitted += self._rebalance_portfolio(
                db,
                portfolio=portfolio,
                equity=equity,
                current_values=current_values,
                current_qtys=current_qtys,
                position_pnl=position_pnl,
                open_order_tickers=open_order_tickers,
                trade_date=trade_date,
            )
        return f"ok:{submitted}_orders"

    def _rebalance_portfolio(
        self,
        db: Session,
        *,
        portfolio: StrategyPortfolio,
        equity: float,
        current_values: dict[str, float],
        current_qtys: dict[str, float],
        position_pnl: dict[str, float],
        open_order_tickers: set[str],
        trade_date: date,
    ) -> int:
        user_id = portfolio.user_id
        strategy_targets: list[targets.StrategyTarget] = []
        registrations: dict[int, ForwardValidationRegistration] = {}

        for allocation in portfolio.allocations:
            registration = resolve_registration(db, allocation, user_id)
            if registration is None:
                continue
            registrations[registration.id] = registration

            state_row = self._get_or_create_state(db, user_id, registration.id, allocation.id)
            allocated_capital = targets.compute_allocated_capital(
                weight=allocation.weight,
                equity=equity,
                capital_fraction=settings.execution_capital_fraction,
            )

            if state_row.halted_at is not None:
                # Pulled by its own circuit breaker: keep contributing its
                # FROZEN target so the aggregate does not fall and unwind the
                # position, and never recompute it from a live signal again
                # until a human resumes it.
                frozen = json.loads(state_row.frozen_target_json or "{}")
                strategy_targets.append(
                    targets.StrategyTarget(
                        registration_id=registration.id,
                        allocation_id=allocation.id,
                        strategy_name=registration.strategy_name,
                        ticker_a=registration.ticker_a,
                        ticker_b=registration.ticker_b,
                        cost_bps=registration.cost_bps,
                        allocated_capital=allocated_capital,
                        legs={k: float(v) for k, v in frozen.items()},
                        frozen=True,
                    )
                )
                continue

            legs = self._compute_legs(registration, allocated_capital)
            strategy_targets.append(
                targets.StrategyTarget(
                    registration_id=registration.id,
                    allocation_id=allocation.id,
                    strategy_name=registration.strategy_name,
                    ticker_a=registration.ticker_a,
                    ticker_b=registration.ticker_b,
                    cost_bps=registration.cost_bps,
                    allocated_capital=allocated_capital,
                    legs=legs,
                )
            )

        if not strategy_targets:
            return 0

        # P&L attribution and the per-strategy breaker run BEFORE the aggregate
        # is built, so a strategy that trips THIS tick is frozen in time to act
        # on immediately rather than one tick later.
        newly_frozen = self._record_and_breaker(
            db,
            strategy_targets=strategy_targets,
            position_pnl=position_pnl,
            current_values=current_values,
            trade_date=trade_date,
        )
        if newly_frozen:
            # Swap a just-tripped strategy's desired target for its actual
            # exposure, so this very tick neither opens new exposure for it nor
            # unwinds what it already holds.
            strategy_targets = [
                (
                    targets.StrategyTarget(
                        registration_id=t.registration_id,
                        allocation_id=t.allocation_id,
                        strategy_name=t.strategy_name,
                        ticker_a=t.ticker_a,
                        ticker_b=t.ticker_b,
                        cost_bps=t.cost_bps,
                        allocated_capital=t.allocated_capital,
                        legs=newly_frozen[t.registration_id],
                        frozen=True,
                    )
                    if t.registration_id in newly_frozen
                    else t
                )
                for t in strategy_targets
            ]

        net = targets.aggregate_targets(strategy_targets)
        capped, cap_warnings = targets.apply_caps(
            net,
            max_position_notional=settings.execution_max_position_notional,
            max_total_notional=settings.execution_max_total_notional,
        )
        for warning in cap_warnings:
            logger.warning("Execution cap: %s", warning)

        reference_prices = self._reference_prices(db, set(capped) | set(current_values))
        managed = self._managed_tickers(db, user_id, set(capped))

        plan = targets.plan_orders(
            net_targets=capped,
            current_values=current_values,
            current_qtys=current_qtys,
            open_order_tickers=open_order_tickers,
            managed_tickers=managed,
            reference_prices=reference_prices,
            min_order_notional=settings.execution_min_order_notional,
        )

        owner = self._owner_by_ticker(strategy_targets)
        for skipped in plan.skipped:
            logger.info(
                "Execution: skipped %s (%s), delta $%.2f", skipped.ticker, skipped.reason, skipped.delta_notional
            )
            if skipped.reason != "open_order_pending":
                # Recorded so a decline is auditable rather than invisible.
                # "open_order_pending" is the normal, expected case and would
                # otherwise flood the log every tick a fill is pending.
                self._record_skip(db, user_id, skipped, owner, reference_prices)

        submitted = 0
        for intent in plan.intents:
            if self._submit(db, user_id, intent, owner, reference_prices):
                submitted += 1
        return submitted

    def _compute_legs(
        self, registration: ForwardValidationRegistration, allocated_capital: float
    ) -> dict[str, float]:
        """Turn a persisted WalkForwardState into signed dollar targets via the
        strategy's own registered compute_target_legs — never a special case in
        this runner."""
        try:
            adapter = get_adapter(registration.strategy_name)
        except ValueError:
            logger.warning(
                "Execution: registration %s has unknown strategy %r; skipping.",
                registration.id,
                registration.strategy_name,
            )
            return {}
        state = deserialize_walk_forward_state(json.loads(registration.carry_state_json))
        legs = adapter.compute_target_legs(state, registration.ticker_a, registration.ticker_b)
        aggregated: dict[str, float] = {}
        for leg in legs:
            aggregated[leg.ticker] = (
                aggregated.get(leg.ticker, 0.0) + leg.signed_weight * allocated_capital
            )
        return aggregated

    # --- per-strategy circuit breaker ----------------------------------------

    def _get_or_create_state(
        self, db: Session, user_id: int, registration_id: int, allocation_id: int
    ) -> StrategyExecutionState:
        state_row = db.execute(
            select(StrategyExecutionState).where(
                StrategyExecutionState.forward_validation_registration_id == registration_id
            )
        ).scalar_one_or_none()
        if state_row is None:
            state_row = StrategyExecutionState(
                user_id=user_id,
                forward_validation_registration_id=registration_id,
                strategy_portfolio_allocation_id=allocation_id,
                day_pnl_json="[]",
            )
            db.add(state_row)
            db.commit()
            db.refresh(state_row)
        elif state_row.strategy_portfolio_allocation_id != allocation_id:
            state_row.strategy_portfolio_allocation_id = allocation_id
            db.commit()
        return state_row

    def _record_and_breaker(
        self,
        db: Session,
        *,
        strategy_targets: list[targets.StrategyTarget],
        position_pnl: dict[str, float],
        current_values: dict[str, float],
        trade_date: date,
    ) -> dict[int, dict[str, float]]:
        """Record each strategy's attributed daily P&L and run its own circuit
        breaker. Returns the frozen targets of any strategy that tripped on
        THIS tick, so the caller can act on them immediately."""
        attributed = targets.attribute_pnl(strategy_targets, position_pnl)
        exposure = targets.attribute_exposure(strategy_targets, current_values)
        by_registration = {t.registration_id: t for t in strategy_targets}
        newly_frozen: dict[int, dict[str, float]] = {}

        for registration_id, pnl in attributed.items():
            target = by_registration[registration_id]
            state_row = db.execute(
                select(StrategyExecutionState).where(
                    StrategyExecutionState.forward_validation_registration_id == registration_id
                )
            ).scalar_one_or_none()
            if state_row is None:
                continue

            day_pnl = strategy_breaker.append_or_update_day(
                strategy_breaker.load_day_pnl(state_row.day_pnl_json),
                trade_date=trade_date,
                pnl=pnl,
                allocated_capital=target.allocated_capital,
            )
            state_row.day_pnl_json = json.dumps(day_pnl)
            state_row.last_marked_date = trade_date

            if state_row.halted_at is not None:
                db.commit()
                continue

            verdict = strategy_breaker.evaluate(day_pnl)
            if verdict.breached:
                logger.error(
                    "PER-STRATEGY CIRCUIT BREAKER: registration %s (%s %s/%s) trailing %s-day "
                    "Sharpe %.2f <= %.2f. Pulling it from the live execution set; its existing "
                    "positions are left untouched.",
                    registration_id,
                    target.strategy_name,
                    target.ticker_a,
                    target.ticker_b,
                    verdict.trailing_days,
                    verdict.trailing_sharpe if verdict.trailing_sharpe is not None else float("nan"),
                    strategy_breaker.BREAKER_SHARPE_THRESHOLD,
                )
                state_row.halted_at = utcnow_naive()
                state_row.halted_reason = "trailing_sharpe_breach"
                state_row.halted_trailing_sharpe = verdict.trailing_sharpe
                state_row.halted_trailing_days = verdict.trailing_days
                # Frozen at what it ACTUALLY holds, not what it wanted: keeping
                # its real exposure in the aggregate stops the next tick from
                # unwinding it, while dropping its desired target stops this
                # tick from opening anything new for it.
                frozen_legs = exposure.get(registration_id, {})
                state_row.frozen_target_json = json.dumps(frozen_legs)
                newly_frozen[registration_id] = frozen_legs
                self._send_strategy_breach_email(target, verdict)
            db.commit()

        return newly_frozen

    def _send_strategy_breach_email(
        self, target: targets.StrategyTarget, verdict: strategy_breaker.BreakerVerdict
    ) -> None:
        if not settings.execution_alert_email:
            return
        send_email(
            settings.execution_alert_email,
            f"Aladdin2: strategy pulled from live execution ({target.strategy_name} "
            f"{target.ticker_a}/{target.ticker_b})",
            (
                f"Trailing {verdict.trailing_days}-day realized Sharpe: "
                f"{verdict.trailing_sharpe:.2f} (threshold "
                f"{strategy_breaker.BREAKER_SHARPE_THRESHOLD:.2f}).\n"
                f"Trailing cumulative return: "
                f"{(verdict.trailing_return or 0.0) * 100:.2f}%.\n\n"
                "This strategy will submit no further orders. Its existing positions were "
                "deliberately NOT liquidated, and every other strategy — and the account as a "
                "whole — continues to trade normally.\n\n"
                f"{strategy_breaker.METHODOLOGY_NOTE}"
            ),
        )

    # --- submission and reconciliation ---------------------------------------

    def _owner_by_ticker(
        self, strategy_targets: list[targets.StrategyTarget]
    ) -> dict[str, targets.StrategyTarget]:
        """Which strategy an order for a given ticker is attributed to in the
        audit log. When several strategies name the same ticker the largest
        absolute leg wins — an approximation, and only ever used for labelling
        a LiveOrder row, never for sizing."""
        owner: dict[str, targets.StrategyTarget] = {}
        for target in strategy_targets:
            for ticker, notional in target.legs.items():
                incumbent = owner.get(ticker)
                if incumbent is None or abs(notional) > abs(incumbent.legs.get(ticker, 0.0)):
                    owner[ticker] = target
        return owner

    def _record_skip(
        self,
        db: Session,
        user_id: int,
        skipped: targets.SkippedOrder,
        owner: dict[str, targets.StrategyTarget],
        reference_prices: dict[str, float],
    ) -> None:
        target = owner.get(skipped.ticker)
        db.add(
            LiveOrder(
                user_id=user_id,
                forward_validation_registration_id=target.registration_id if target else None,
                strategy_portfolio_allocation_id=target.allocation_id if target else None,
                ticker=skipped.ticker,
                side="buy" if skipped.delta_notional > 0 else "sell",
                notional_requested=abs(skipped.delta_notional),
                status="skipped",
                client_order_id=f"aladdin2-skip-{uuid.uuid4()}",
                decision_price=reference_prices.get(skipped.ticker),
                assumed_cost_bps=target.cost_bps if target else None,
                error_message=skipped.reason,
            )
        )
        db.commit()

    def _submit(
        self,
        db: Session,
        user_id: int,
        intent: targets.OrderIntent,
        owner: dict[str, targets.StrategyTarget],
        reference_prices: dict[str, float],
    ) -> bool:
        target = owner.get(intent.ticker)
        client_order_id = f"aladdin2-{uuid.uuid4()}"
        order = LiveOrder(
            user_id=user_id,
            forward_validation_registration_id=target.registration_id if target else None,
            strategy_portfolio_allocation_id=target.allocation_id if target else None,
            ticker=intent.ticker,
            side=intent.side,
            notional_requested=intent.notional,
            qty_requested=intent.qty,
            status="submitted",
            client_order_id=client_order_id,
            decision_price=reference_prices.get(intent.ticker),
            assumed_cost_bps=target.cost_bps if target else None,
        )
        db.add(order)
        # Committed BEFORE the broker call, deliberately: if the process dies
        # mid-submission, the audit log still shows an order was attempted with
        # this exact client_order_id, and the broker's own uniqueness check on
        # that id prevents a duplicate on any retry.
        db.commit()

        try:
            if intent.kind == "notional":
                response = alpaca_client.submit_notional_order(
                    symbol=intent.ticker,
                    notional=intent.notional or 0.0,
                    side=intent.side,
                    client_order_id=client_order_id,
                )
            else:
                response = alpaca_client.submit_qty_order(
                    symbol=intent.ticker,
                    qty=intent.qty or 0.0,
                    side=intent.side,
                    client_order_id=client_order_id,
                )
        except AlpacaError as exc:
            order.status = "error"
            order.error_message = str(exc)[:2000]
            db.commit()
            logger.warning("Execution: order for %s failed: %s", intent.ticker, exc)
            return False

        order.broker_order_id = response.get("id")
        order.status = response.get("status") or "submitted"
        order.raw_response_json = json.dumps(response)
        db.commit()
        logger.info(
            "Execution: submitted %s %s %s (%s) -> broker order %s",
            intent.side,
            intent.ticker,
            f"${intent.notional:,.2f}" if intent.kind == "notional" else f"{intent.qty:g} sh",
            intent.kind,
            order.broker_order_id,
        )
        return True

    def _reconcile_open_orders(self, db: Session) -> None:
        """Poll every not-yet-terminal order and record its fill, including the
        realized slippage against the price the signal was computed on.

        Best-effort by design: a failure here logs and returns without touching
        anything else. Slippage is a monitoring metric — refusing to trade
        because a metric could not be computed would be strictly worse than
        trading without it.
        """
        pending = (
            db.execute(
                select(LiveOrder)
                .where(
                    LiveOrder.broker_order_id.is_not(None),
                    LiveOrder.status.not_in(list(TERMINAL_ORDER_STATUSES)),
                )
                .order_by(LiveOrder.id)
                .limit(RECONCILE_BATCH_SIZE)
            )
            .scalars()
            .all()
        )
        for order in pending:
            try:
                remote = alpaca_client.get_order(order.broker_order_id or "")
            except AlpacaError as exc:
                logger.info("Execution: could not reconcile order %s: %s", order.id, exc)
                continue
            apply_fill(order, remote)
        if pending:
            db.commit()

    # --- reference prices -----------------------------------------------------

    def _reference_prices(self, db: Session, tickers: set[str]) -> dict[str, float]:
        """The most recent CACHED daily close per ticker — a pure local read of
        the price_bars table this system already fills, with no network call at
        all. Deliberately not get_price_history_cached: that can fall through to
        a live fetch, and a multi-second network stall has no business sitting
        inside the order loop."""
        if not tickers:
            return {}
        rows = db.execute(
            select(PriceBar.ticker, PriceBar.date, PriceBar.adj_close)
            .where(PriceBar.ticker.in_(sorted(tickers)))
            .order_by(PriceBar.ticker, PriceBar.date.desc())
        ).all()
        latest: dict[str, float] = {}
        for ticker, _bar_date, adj_close in rows:
            if ticker not in latest and adj_close and adj_close > 0:
                latest[ticker] = float(adj_close)
        return latest

    def _managed_tickers(self, db: Session, user_id: int, target_tickers: set[str]) -> set[str]:
        """Symbols this system is allowed to touch: anything it currently wants,
        plus anything it has ever submitted an order for.

        Without this bound, a position a human opened by hand in the same
        account would read as "target 0, currently long" and be liquidated by
        the next tick — directly contradicting execution_capital_fraction's
        promise that this system only ever uses part of the account. Note this
        is a SCOPING read of the audit log, not a position mirror: quantities
        still come exclusively from the broker.
        """
        rows = (
            db.execute(select(LiveOrder.ticker).where(LiveOrder.user_id == user_id).distinct())
            .scalars()
            .all()
        )
        return set(target_tickers) | set(rows)


def apply_fill(order: LiveOrder, remote: dict) -> None:
    """Copy a broker order's terminal state onto its LiveOrder row and compute
    realized slippage. Module-level so the fill/slippage arithmetic is testable
    without constructing a runner or a broker."""
    order.status = remote.get("status") or order.status
    order.raw_response_json = json.dumps(remote)

    filled_qty = remote.get("filled_qty")
    filled_avg_price = remote.get("filled_avg_price")
    if filled_qty not in (None, ""):
        try:
            order.filled_qty = float(filled_qty)
        except (TypeError, ValueError):
            pass
    if filled_avg_price in (None, ""):
        return
    try:
        price = float(filled_avg_price)
    except (TypeError, ValueError):
        return
    if price <= 0:
        return

    order.filled_avg_price = price
    filled_at = remote.get("filled_at")
    if filled_at:
        try:
            order.filled_at = datetime.fromisoformat(str(filled_at).replace("Z", "+00:00")).replace(
                tzinfo=None
            )
        except ValueError:
            order.filled_at = utcnow_naive()
    else:
        order.filled_at = utcnow_naive()

    if order.decision_price and order.decision_price > 0:
        order.realized_slippage_bps = slippage.compute_slippage_bps(
            decision_price=order.decision_price,
            filled_avg_price=price,
            side=order.side,
        )
