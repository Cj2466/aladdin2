"""Pure sizing, capping and order-planning arithmetic for one execution tick.

Deliberately free of database, broker and clock access so every rule in it —
especially the two hard dollar caps and the never-flip-through-zero rule — is
directly unit-testable without mocking a broker.
"""

import logging
import math
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StrategyTarget:
    """One live strategy instance's dollar targets for this tick."""

    registration_id: int
    allocation_id: int
    strategy_name: str
    ticker_a: str
    ticker_b: str
    cost_bps: float
    allocated_capital: float
    # ticker -> signed target notional in dollars. Positive long, negative short.
    legs: dict[str, float]
    # True when these targets are frozen at the value they had when this
    # strategy's own circuit breaker tripped. A frozen strategy keeps
    # contributing exactly this much to the aggregate — which is what holds its
    # positions steady instead of unwinding them — and never produces a new
    # order, because its contribution stops changing.
    frozen: bool = False


@dataclass
class OrderIntent:
    ticker: str
    side: str  # "buy" | "sell"
    kind: str  # "notional" | "qty"
    notional: float | None = None
    qty: float | None = None
    # Dollar size of the intended change, for logging/attribution regardless of
    # which order shape was chosen.
    delta_notional: float = 0.0


@dataclass
class SkippedOrder:
    ticker: str
    reason: str
    delta_notional: float = 0.0


@dataclass
class OrderPlan:
    intents: list[OrderIntent] = field(default_factory=list)
    skipped: list[SkippedOrder] = field(default_factory=list)


def compute_allocated_capital(
    *, weight: float, equity: float, capital_fraction: float
) -> float:
    """weight x capital_fraction x equity, with equity read fresh from the
    broker every tick and never cached — a stale equity reading is how a
    percentage-based sizing rule quietly turns into an unbounded one."""
    return max(0.0, weight) * max(0.0, capital_fraction) * max(0.0, equity)


def aggregate_targets(targets: list[StrategyTarget]) -> dict[str, float]:
    """Net every strategy's legs into ONE signed target per ticker.

    Two strategies, or the two legs of two different pairs trades, can name the
    same symbol. Netting before diffing is what stops one tick from submitting
    contradictory buy and sell orders for the same ticker.
    """
    net: dict[str, float] = {}
    for target in targets:
        for ticker, notional in target.legs.items():
            net[ticker] = net.get(ticker, 0.0) + notional
    return net


def apply_caps(
    net: dict[str, float], *, max_position_notional: float, max_total_notional: float
) -> tuple[dict[str, float], list[str]]:
    """The two hard dollar ceilings, applied in the specified order.

    These are not redundant with the optimizer's DEFAULT_MAX_WEIGHT: that is a
    FRACTION, so it scales up with equity — including with a bug that inflates
    an equity reading. These are fixed dollars and do not.

    1. Per-ticker clamp. A blunt ceiling that can, on its own, clamp one leg of
       a pairs trade and not the other and so break that trade's
       market-neutrality. That is accepted deliberately — a hard per-symbol
       ceiling is worth more than perfect neutrality at the ceiling — but it is
       logged loudly whenever it actually binds, rather than happening
       silently.
    2. Total-gross scaling. If gross exposure still exceeds the total cap,
       EVERY ticker is scaled by the same factor. Never trim one and leave
       another: a partially-honored pairs trade stops being market-neutral,
       which is a worse and different risk than simply being smaller.
    """
    warnings: list[str] = []

    clamped: dict[str, float] = {}
    for ticker, notional in net.items():
        capped = max(-max_position_notional, min(max_position_notional, notional))
        if abs(capped - notional) > 1e-9:
            warnings.append(
                f"{ticker}: per-ticker cap clamped ${abs(notional):,.2f} to "
                f"${abs(capped):,.2f}; a multi-leg strategy's neutrality may be affected."
            )
        clamped[ticker] = capped

    gross = sum(abs(v) for v in clamped.values())
    if gross > max_total_notional and gross > 0:
        scale = max_total_notional / gross
        clamped = {ticker: notional * scale for ticker, notional in clamped.items()}
        warnings.append(
            f"Total gross exposure ${gross:,.2f} exceeded the ${max_total_notional:,.2f} cap; "
            f"scaled every ticker by {scale:.4f} (leg ratios preserved)."
        )

    return clamped, warnings


def plan_orders(
    *,
    net_targets: dict[str, float],
    current_values: dict[str, float],
    current_qtys: dict[str, float],
    open_order_tickers: set[str],
    managed_tickers: set[str],
    reference_prices: dict[str, float],
    min_order_notional: float,
) -> OrderPlan:
    """Diff targets against the broker's REAL current positions and produce the
    orders that close the gap.

    The broker is the only source of truth for what is currently held. There is
    no local position-mirror table anywhere in this phase, deliberately: a stale
    local cache is exactly what causes double-order bugs, and asking Alpaca
    fresh every 60 seconds is trivially cheap. Same reasoning
    finnhub_ws_client already documents for re-deriving its subscriptions from
    live state instead of a separately tracked list.

    `managed_tickers` bounds what this function may touch to symbols this
    system itself put on (or wants on) the account. Without it, a position a
    human opened by hand would look like "target 0, currently long" and get
    liquidated by the next tick — which would directly contradict
    execution_capital_fraction's promise that this system only ever uses part
    of the account.

    Order-shape routing exists because Alpaca does not permit short selling
    through notional/fractional orders — verified directly against the real
    paper account, which answers a notional short sell with
    422 "fractional orders cannot be sold short" while accepting the same
    order as whole shares. Anything that opens, extends or reduces a SHORT is
    therefore submitted as whole shares, sized from a reference price.
    """
    plan = OrderPlan()

    for ticker in sorted(set(net_targets) | set(current_values)):
        if ticker not in managed_tickers:
            continue

        target = net_targets.get(ticker, 0.0)
        current_value = current_values.get(ticker, 0.0)
        current_qty = current_qtys.get(ticker, 0.0)

        # Never flip a long straight into a short (or back) in one order.
        # Alpaca's own wash-trade and short-locate handling makes such an order
        # unreliable, and splitting it costs nothing: this tick flattens, the
        # next tick — re-derived from the broker's real positions — opens the
        # other side.
        effective_target = target
        if current_value != 0.0 and target * current_value < 0.0:
            effective_target = 0.0

        delta = effective_target - current_value
        if abs(delta) < min_order_notional:
            continue

        if ticker in open_order_tickers:
            # An unfilled order from a previous tick is already working this
            # gap. Stacking a second one is the classic double-order bug.
            plan.skipped.append(SkippedOrder(ticker, "open_order_pending", delta))
            continue

        closing_fully = abs(effective_target) < 1e-9 and abs(current_qty) > 0.0
        if closing_fully:
            # Exact share count, so a full close leaves no rounding dust and
            # can never be rejected for selling more than is held.
            plan.intents.append(
                OrderIntent(
                    ticker=ticker,
                    side="sell" if current_qty > 0 else "buy",
                    kind="qty",
                    qty=abs(current_qty),
                    delta_notional=delta,
                )
            )
            continue

        long_only = effective_target > 0.0 and current_value >= 0.0
        if long_only:
            plan.intents.append(
                OrderIntent(
                    ticker=ticker,
                    side="buy" if delta > 0 else "sell",
                    kind="notional",
                    notional=abs(delta),
                    delta_notional=delta,
                )
            )
            continue

        price = reference_prices.get(ticker)
        if price is None or price <= 0:
            # Cannot size a short-side order without a price. Fail closed:
            # skip this ticker, recorded so the decline is auditable rather
            # than invisible.
            plan.skipped.append(SkippedOrder(ticker, "no_reference_price", delta))
            continue

        shares = math.floor(abs(delta) / price)
        if shares < 1:
            # Short legs cannot be fractional, so a sub-one-share adjustment is
            # simply not expressible. Skipped and recorded; the gap persists
            # and is re-evaluated next tick.
            plan.skipped.append(SkippedOrder(ticker, "below_one_share", delta))
            continue

        plan.intents.append(
            OrderIntent(
                ticker=ticker,
                side="buy" if delta > 0 else "sell",
                kind="qty",
                qty=float(shares),
                delta_notional=delta,
            )
        )

    return plan


def ticker_shares(targets: list[StrategyTarget]) -> dict[str, dict[int, float]]:
    """Each ticker's split across the strategies that asked for it, in
    proportion to their signed share of its netted target notional.

    Exact when one strategy drives a ticker (share == 1). Pro-rata by target
    when several share it — which is the same split that decided the order
    sizes in the first place, so it is at least self-consistent rather than
    arbitrary. Keyed by registration_id, the durable strategy identity.
    """
    net = aggregate_targets(targets)
    shares: dict[str, dict[int, float]] = {}

    for ticker, net_target in net.items():
        # Denominator is the sum of |leg|, not |sum of legs|: two strategies
        # holding opposite sides of the same ticker would otherwise divide by a
        # near-zero net and blow the split up.
        gross_target = sum(abs(t.legs.get(ticker, 0.0)) for t in targets)
        if gross_target <= 0:
            continue
        per_strategy: dict[int, float] = {}
        for target in targets:
            leg = target.legs.get(ticker, 0.0)
            if leg == 0.0:
                continue
            if abs(net_target) > 1e-9:
                per_strategy[target.registration_id] = leg / net_target
            else:
                # Fully offsetting targets: the account holds ~nothing in this
                # ticker, so there is essentially nothing to split. Fall back to
                # gross share so the arithmetic stays defined.
                per_strategy[target.registration_id] = abs(leg) / gross_target
        shares[ticker] = per_strategy

    return shares


def attribute_pnl(
    targets: list[StrategyTarget], position_pnl: dict[str, float]
) -> dict[int, float]:
    """Split each ticker's broker-reported session P&L across the strategies
    that asked for that ticker."""
    shares = ticker_shares(targets)
    attributed: dict[int, float] = {t.registration_id: 0.0 for t in targets}
    for ticker, pnl in position_pnl.items():
        for registration_id, share in shares.get(ticker, {}).items():
            attributed[registration_id] += pnl * share
    return attributed


def attribute_exposure(
    targets: list[StrategyTarget], current_values: dict[str, float]
) -> dict[int, dict[str, float]]:
    """Each strategy's share of the account's REAL current exposure, per ticker.

    This is what a tripped strategy's target gets frozen at — its actual
    holdings, not its desired target. Freezing at the desired target would let
    a strategy OPEN a brand-new position on the very tick its own circuit
    breaker pulled it; freezing at actual exposure makes that tick's diff
    approximately zero, so nothing is opened and nothing is unwound.
    """
    shares = ticker_shares(targets)
    exposure: dict[int, dict[str, float]] = {t.registration_id: {} for t in targets}
    for ticker, value in current_values.items():
        for registration_id, share in shares.get(ticker, {}).items():
            exposure[registration_id][ticker] = value * share
    return exposure
