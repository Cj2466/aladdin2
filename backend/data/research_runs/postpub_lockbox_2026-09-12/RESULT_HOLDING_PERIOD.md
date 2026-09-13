# Does holding longer help? — measured on the 195 sealed predictors (2026-09-13)

Owner's question after we measured that a daily-trading family earns 1.9–3.9 bp gross per round
trip against a 2.0 bp cost: would holding longer fix it? Descriptive cut of the already-computed
sealed series (post-publication months, P-clean, ≥36 months). No new window, no selection, no
verdict. Edge is measured GROSS so the comparison is not circular — the haircut is 20/P by
construction and would mechanically flatter slow holders.

## The table

| holding (months) | predictors | median GROSS Sharpe | gross edge per trade | **edge ÷ cost** | share ≥1× | share ≥3× | pooled gross | pooled net |
|---|---|---|---|---|---|---|---|---|
| 1 | 98 | 0.291 | 0.27% | **1.37** | 65% | 19% | 0.814 | 0.531 |
| 3 | 7 | 0.333 | 1.28% | 6.38 | 86% | 71% | 0.371 | 0.334 |
| 6 | 2 | 0.199 | 1.55% | 7.74 | 100% | 100% | 0.296 | 0.270 |
| 12 | 87 | 0.255 | 2.30% | **11.51** | 78% | 71% | 0.659 | 0.632 |
| 36 | 1 | 0.122 | 7.91% | 39.57 | 100% | 100% | 0.122 | 0.119 |

Cost per round trip assumed 0.20% (4 legs × 5 bp). Across all 195: median edge ÷ cost 2.65;
72% clear 1×; only 46% clear the 3× margin we agreed to aim for.

## What it says — three findings, and the second is the one that matters

**1. Holding longer does NOT improve the signal.** Median gross Sharpe is flat across every
bucket: 0.29 (monthly), 0.33 (quarterly), 0.20 (semi-annual), 0.26 (annual). Slowing down buys no
extra edge quality. Anyone expecting "trade less, earn more per unit of risk" does not get it here.

**2. Holding longer buys an enormous SAFETY MARGIN against costs.** Gross edge per trade rises
0.27% → 2.30% (8.4×) from monthly to annual, so the edge-to-cost ratio goes 1.37 → 11.51. A monthly
rebalancer's median edge is only 37% above its cost; only 19% of them clear a 3× margin. An annual
rebalancer's edge is eleven times its cost. **For monthly strategies the cost assumption IS the
result; for annual strategies the cost assumption barely matters.** That is decisive for us, because
the cost assumption is precisely the thing we spent today discovering we cannot pin down for small
stocks.

**3. The fast pool still wins on gross, and loses most of the gap to costs.** Pooled gross:
monthly 0.814 vs annual 0.659 — the monthly bucket has 98 predictors and diversifies better. After
the haircut: monthly 0.531 vs annual 0.632. **The monthly pool gives up 0.28 Sharpe to costs; the
annual pool gives up 0.03.** So the fast book is better before costs and worse after, and its
after-cost number is the fragile one.

## What I would do with this (judgment, for the owner)
Prefer annual-rebalance mechanisms for the first BOOK members. Not because they earn more — they do
not — but because their verdict survives being wrong about costs, and our cost estimates for the
whole-market panel are exactly what the A2 audit showed we cannot yet trust below a per-stock noise
floor. Fast mechanisms stay on the list, but they should be built only after A2 gives a per-ticker
cost we believe, and they should carry their break-even cost in the result.

## Limits
Holding period is OSAP's `Portfolio Period` field, which is the paper's own rebalance cadence, not a
turnover measurement — a 12-month holder with 100% annual turnover and one with 40% look identical
here. The 3-, 6- and 36-month buckets have 7, 2 and 1 predictors and are too thin to lean on. The
cost per round trip is this project's flat 5 bp one-way, itself the unsourced constant the
2026-09-12 audit flagged; the RATIOS between buckets are unaffected by its level, the absolute
"clears 3×" shares are not.
