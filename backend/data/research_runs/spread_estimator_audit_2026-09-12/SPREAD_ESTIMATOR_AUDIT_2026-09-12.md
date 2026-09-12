# Audit of the spread estimator before using it on the whole market (2026-09-12)

Owner's instruction: before using a tool, check the tool itself — its form and its internal
mechanism. Done by the orchestrator (Opus 5) with its own simulation, not by reading the module's
documentation. Script and raw output committed beside this file.

## Method
Simulate daily OHLC from a random walk plus a KNOWN bid-ask bounce (every trade prints at the
efficient price ±s, i.e. at bid or ask), then ask the estimator's own engine — `bidask.edge_rolling`,
the source paper's reference implementation, called exactly as `spread_estimator.
estimate_effective_spread` calls it — what it recovers at the production window of 63 days.

## Finding 1 — the estimator has a NOISE FLOOR, and below it the answer is invented

| true full spread | recovered (w=63) | ratio |
|---|---|---|
| 1 bp | 14.3 bp | **14× too high** |
| 2 bp | 14.5 bp | 7.2× |
| 4 bp | 14.4 bp | 3.6× |
| 10 bp | 17.9 bp | 1.8× |
| 20 bp | 24.9 bp | 1.24× |
| 50 bp | 45.5 bp | 0.91× |
| 100 bp | 95.2 bp | 0.95× |
| 200 bp | 191 bp | 0.96× |
| 500 bp | 493 bp | 0.99× |
| 1000 bp | 998 bp | 1.00× |

Above roughly 50 bp the estimator is accurate to within 5–9%. Below it, the output converges to a
floor that has nothing to do with the true spread. This reproduces the module's own documented
"10–40× for large caps" warning and puts a number on where the transition is.

## Finding 2 — the floor SCALES WITH VOLATILITY, which changes how the tool must be used

Simulating a true spread of exactly ZERO and reading what comes back:

| daily volatility | recovered "spread" (w=63) |
|---|---|
| 1% | 7.2 bp |
| 2% | 14.4 bp |
| 4% | 28.8 bp |
| 8% | 57.5 bp |
| 16% | 115.1 bp |

The floor is proportional to volatility: floor ≈ 0.088 × (daily vol in bp) at 390 trades/day,
0.118× at 78 trades/day, 0.065× at 1,000 trades/day (three seeds each). **So there is no single
"trustworthy above 50 bp" threshold — the threshold is per stock and rises with its own
volatility.** This matters precisely for the whole-market panel: micro-caps are both wide-spread
AND volatile, so a 6%-daily-vol name carries a floor around 45–70 bp, and any estimate near that
level for that name is noise wearing a number.

## Finding 3 — the paper's own convention fails LOUDLY; the module's default fails QUIETLY

`edge_rolling(sign=False)` (what `build_edge_half_spread_frame` uses) folds negative squared-spread
estimates to positive with abs(). `sign=True` plus truncation at zero is the paper's canonical
Eq. (14). Measured, at 2% daily vol:

| true full spread | sign=False | sign=True |
|---|---|---|
| 2 bp | 14.45 | **0.00** |
| 10 bp | 17.86 | **0.00** |
| 50 bp | 45.48 | 45.48 |
| 200 bp | 191.3 | 191.3 |
| 1000 bp | 997.8 | 997.8 |

Identical where the estimator works; zero where it does not. A zero says "cannot measure this",
which a caller can act on; 14 bp says "this stock costs 14 bp", which is false and unchallengeable.
The module already sets `CALIBRATED_SIGN_MODE = True` for its calibrated builder — this audit is
the measured justification for using that convention everywhere on the whole-market panel.

## Consequences for Step A2 (how the tool WILL be used)
1. Use `sign=True` with truncation at zero. Never the abs() fold.
2. Compute each ticker's own floor from its own realized volatility (coefficient above, re-measured
   on our real bars rather than carried from this simulation) and treat any estimate not materially
   above that ticker's floor as MISSING, not as a cost.
3. Where the estimate is missing, fall back to a level sourced from published spread data for that
   liquidity bucket — never to a single market-wide constant. The module's own
   `SP500_TARGET_MEDIAN_HALF_SPREAD = 0.0002` is documented as a US large-cap universe property and
   would be wrong applied to a panel that is mostly micro-cap.
4. Report the share of ticker-months served by each source (measured / floored / fallback) in every
   result that uses costs, so a reader can see how much of a cost figure is estimated and how much
   is assumed.

## What this audit did NOT establish
The simulation is a single microstructure model (constant spread, symmetric bounce, no overnight
gaps, no tick grid, no intraday volatility pattern). The module's own notes attribute part of the
real-data bias to overnight gap dynamics, which this simulation does not reproduce — so the real-data
floor may be HIGHER than simulated here. That is the next measurement, and it belongs in A2 against
the actual panel, not to a simulation.
