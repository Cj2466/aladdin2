# DRAFT pre-registration — `sparse_ownership_firesale_count` (NOT LOCKED; a decision aid for the owner's R3 waiver, 2026-09-12 02:50 Bangkok)

Status: DRAFT. Nothing here has been run; no return, no position, no DB row exists for this
family. It becomes a pre-registration only if the owner waives rule R3 for ledger entry #16 and
the control non-degeneracy proof (§6) is committed. Until then it is the cheapest way to see what
the waiver buys and costs. Orchestrator: Fable 5.1.

## 1. Hypothesis (Coval & Stafford 2007, Eq. 4, page 10 of the 2005 WP already read in full 2026-09-08)

Stocks whose mutual-fund owners face large redemptions are sold regardless of price; the net
COUNT of constrained sellers over the number of owners (Eq. 4, unweighted) predicts a temporary
decline and reversal. The 2026-09-08 test was untestable on S&P 500/600 because the median stock
had 643/246 fund owners and the paper's −15%/+25% cutoffs were never reached. The corner
measured 2026-09-12 has 1,070–1,810 listed names per quarter with 5–47 fund owners
(`breadth_universe_intersection.json`) — the paper's own regime (worked example: 47 owners).

## 2. Universe (point-in-time, delisted names included)

Per formation month-end: listed US common stocks whose CUSIP had **5–47 N-PORT fund-report
owners at the latest PUBLIC quarter** (publication lag: 60 days after quarter end, from
SUBMISSION.FILING_DATE — the existing provider carries it), mapped to a ticker through SEC
fails-to-deliver observations nearest in time (existing `CusipTickerMap.resolve`), with Alpaca
SIP daily bars (active ∪ inactive assets, plain tickers), each delisted name CUT at its last
listed bar. Paper's footnote 6 minimum of 10 owners is KEPT (so effectively 10–47). Names with
median daily dollar volume below a pre-declared floor are excluded (floor to be set from the
FIRST formation year only, e.g. its 25th percentile, and stated here before lock).

## 3. Signal and cutoffs — the one design change from 2026-09-08

Eq. 4 as implemented in `cross_sectional_firesale_pressure.build_pressure_panels` (unchanged code).
The paper's cutoffs are distributional (fn. 7: "approximately correspond to the 5th and 95th
percentiles of the PRESSURE variable"). Per the 2026-09-08 lesson, cutoffs are **percentile-
defined, frozen on the first 12 formation months** (2020-06 → 2021-05, the earliest with a
public N-PORT current-and-prior quarter), never re-estimated. Both the paper's fixed −15%/+25%
and the frozen percentiles are reported; the percentile arm is primary.

## 4. Grid (the paper's own Table 5 structure, one universe)

flow threshold {5%, 10%} × leg {long, short, long_short} × weighting {equal, value} = **12 specs**,
n_local = 12; DSR ladder from `dsr_policy_n` (currently 43/397/1131). Formation: monthly,
positions from stocks that crossed a cutoff within the past 365 days but not the last 91
(paper §III.A, fn. 10), minimum 10 firms per leg else the leg earns 0 (paper's own rule).

## 5. Cost model

Baseline arm from the project's cost model with the bid-ask estimator (`spread_estimator.py`)
per name per month — micro-caps will show spreads an order of magnitude above S&P 600's; the
2026-09-11 memo's median dollar volume of delisted names ($137k/day) means position sizes are
capped by liquidity; a capacity line is reported (informational, CLAUDE.md). Zero-cost arm reported
for diagnosis only; the VERDICT arm is the baseline.

## 6. Controls — non-degeneracy to be PROVEN before lock (CLAUDE.md rule)

C1 unconstrained panel (paper's own control: PRESSURE computed with every fund, no flow gate) —
differs from the spec by construction (different gate set) — algebraic proof: the constrained
count is a subset sum, so positions differ whenever any owner is unconstrained.
C2 flow-shuffled placebo: fund flows permuted across funds within each quarter → different
constrained set → different PRESSURE; non-degeneracy shown by a synthetic-data run committed with
the lock. C3 breadth placebo: the same rule on names with 48–200 owners (where the mechanism
should be weaker) — a monotonicity check, not a gate.

## 7. Verdict rule (BOOK admission, not certification)

Under the five principles the family is NOT certified alone. It is PRODUCED (Step 0 rule P3) if the
primary-arm best spec's net in-sample Sharpe ≥ 0.30 AND C1/C2 do not match it (Dormant placebo-
override rule); it then enters the Dormant pool at its frozen spec and is scored by looks. Single-
family DSR is still reported across the ladder, with the honest power block:

| claim (gross, paper t/√25) | fraction 0.5 | power to clear 0.95 at n_local 12, 6.8 y | verdict under the OLD rule |
|---|---|---|---|
| 0.44 (t = 2.22) | 0.22 | **0.0031** | DECLINE |
| 0.70 (t = 3.50) | 0.35 | **0.0082** | DECLINE |

(`sourcing_power_check` run 2026-09-12, N-PORT window 2019q4 → 2026q2 = 6.8 y.) BOOK power gain
from a first member at true 0.30 (`book_power_gain.py`, M = 0 → 1): 0 → 0.029 in 10 y. That is the
whole economic content of the waiver: one member does almost nothing; the BOOK needs ~30.

## 8. Prior, stated before any number

Negative. The 2026-09-08 exploratory arm (percentile cutoffs, S&P 600) was −0.026%/mo long-short;
Wardlaw (2020) says flow-pressure measures embed the realized return (unverified whether the count
measure is exempt); HXZ say micro-cap anomalies are "more apparent than real" after costs; the
paper's own effect at |flow| > 5% is "of mixed statistical reliability". If built, the most likely
outcome is a placebo-matched or cost-negative result, i.e. an honest negative.

## 9. What the build costs (for the owner's decision)

Data: re-extract FUND_REPORTED_HOLDING for the sparse-universe CUSIP set for 27 quarters
(`fetch_nport_bulk_firesale.py` already streams by range request; ~1 min/quarter measured);
Alpaca daily bars for ~3–4k names 2016 → (minutes); FTD archives already cached (routed to the
main checkout since `7fe393d`). Build: Opus, sequential, reusing the fire-sale module with a new
universe adapter — roughly one working day including the orchestrator's own re-derivation and the
full suite. No purchase. Risk: two per-worktree cache gaps were fixed tonight; symbol re-use cuts
and split handling on delisted names are the two places a wrong number would most likely hide.
