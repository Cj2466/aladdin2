"""Execution-quality measurement: what real fills actually cost, versus the
fixed cost_bps every backtest and forward-validation registration assumes.

Every result this system produces is net of an ASSUMED cost — 10bps for pairs,
5bps for momentum — and until now nothing anywhere measured whether real fills
match that. If real slippage runs materially above the assumption over a
meaningful sample, every Sharpe, every deflated Sharpe, and every portfolio
weight derived from them is optimistic by a quantity nobody has looked at.

This module MEASURES and DISCLOSES. It deliberately does not act: it never
adjusts cost_bps, never halts on slippage, never re-weights anything. Deciding
what a divergence means — a bad assumption, a bad venue, a temporarily illiquid
name, or too small a sample to say — is a judgment call for a human reading the
numbers, and automating a response to a statistic this new would be exactly the
kind of unexamined assumption the measurement exists to catch.

Reference price. Slippage here is measured against the price the SIGNAL was
computed on: the most recent cached daily close for that ticker at decision
time. That is not an approximation of "the mid at the moment of routing" — it
is the correct denominator for the assumption under test. The walk-forward
engine realizes close-to-close returns (ou_pairs' ret_a/ret_b, momentum's ret)
and charges cost_bps against position changes on that series, so the claim
being validated is precisely "trading at that close costs cost_bps". Measured
this way the number is a full implementation shortfall (overnight gap + spread
+ impact), which is what actually erodes the backtested edge.

Comparability. engine.step_one_day charges
    cost = (cost_bps / 10_000) * abs(new_position - prev_position)
so one unit of position change — entering, or exiting — is charged cost_bps
ONCE, against the strategy's full gross notional. A one-way fill's slippage is
therefore directly comparable to cost_bps, and for a pairs trade the two legs'
notional-weighted mean is the right aggregate (their notionals sum to the
normalized gross that cost_bps is charged against).
"""

from dataclasses import dataclass

# Below this many filled orders, an average slippage number is dominated by
# whichever two or three fills happened to land in the sample. Same
# floor-below-which-don't-trust-it convention this codebase already applies at
# the trial-count level (deflated_sharpe.MIN_TRIALS_FOR_DSR = 5) and the
# strategy-count level (MIN_STRATEGIES_FOR_AUTONOMOUS_PORTFOLIO = 5) — applied
# here at the fill-count level. Aggregates below it are still returned, but
# flagged as not yet meaningful rather than quietly presented as a finding.
MIN_FILLS_FOR_MEANINGFUL_SLIPPAGE = 20

BUY_SIDES = ("buy",)


def compute_slippage_bps(*, decision_price: float, filled_avg_price: float, side: str) -> float:
    """Signed so POSITIVE is always adverse, matching cost_bps' own sign: on a
    buy, paying above the decision price costs money; on a sell, receiving
    below it does."""
    if decision_price <= 0:
        raise ValueError("decision_price must be positive")
    raw = (filled_avg_price - decision_price) / decision_price
    if side.lower() not in BUY_SIDES:
        raw = -raw
    return raw * 10_000.0


@dataclass(frozen=True)
class SlippageAggregate:
    """One slice's execution-quality summary. `n_fills` is reported next to
    every average precisely so an average over three fills is never mistaken
    for a finding."""

    label: str
    n_fills: int
    notional_weighted_mean_bps: float | None
    simple_mean_bps: float | None
    median_bps: float | None
    worst_bps: float | None
    assumed_cost_bps: float | None
    # notional_weighted_mean_bps - assumed_cost_bps; positive means real fills
    # are costing MORE than every backtest for this strategy assumed.
    excess_vs_assumed_bps: float | None
    meaningful_sample: bool


@dataclass(frozen=True)
class FillObservation:
    label: str
    slippage_bps: float
    notional: float
    assumed_cost_bps: float | None


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def aggregate(label: str, fills: list[FillObservation]) -> SlippageAggregate:
    if not fills:
        return SlippageAggregate(
            label=label,
            n_fills=0,
            notional_weighted_mean_bps=None,
            simple_mean_bps=None,
            median_bps=None,
            worst_bps=None,
            assumed_cost_bps=None,
            excess_vs_assumed_bps=None,
            meaningful_sample=False,
        )

    values = [f.slippage_bps for f in fills]
    total_notional = sum(abs(f.notional) for f in fills)
    if total_notional > 0:
        weighted = sum(f.slippage_bps * abs(f.notional) for f in fills) / total_notional
    else:
        weighted = sum(values) / len(values)

    assumed_values = [f.assumed_cost_bps for f in fills if f.assumed_cost_bps is not None]
    # Averaged rather than asserted-identical: an aggregate can legitimately
    # span strategies with different assumptions (pairs 10bps, momentum 5bps),
    # in which case the honest comparison point is the notional-blind mean of
    # what was assumed.
    assumed = sum(assumed_values) / len(assumed_values) if assumed_values else None

    return SlippageAggregate(
        label=label,
        n_fills=len(fills),
        notional_weighted_mean_bps=weighted,
        simple_mean_bps=sum(values) / len(values),
        median_bps=_median(values),
        worst_bps=max(values),
        assumed_cost_bps=assumed,
        excess_vs_assumed_bps=(weighted - assumed) if assumed is not None else None,
        meaningful_sample=len(fills) >= MIN_FILLS_FOR_MEANINGFUL_SLIPPAGE,
    )
