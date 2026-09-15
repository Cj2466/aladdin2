# Written BEFORE running: does trading more often reduce the chance of losing?

Owner's question, 2026-09-15: "ยิ่งเทรดด้วยความถี่ที่เยอะจะยิ่งลดโอกาสขาดทุนจริงมั้ย"

## What is actually being asked, separated into two claims

**Claim 1 (statistical):** more independent bets → law of large numbers → lower chance of ending
in the red. I have told the owner this is true, with a coin-flip table (51% edge: 58% chance of
profit over 100 bets, 97.7% over 10,000).

**Claim 2 (practical):** trading more OFTEN gives you more bets, therefore Claim 1 applies.
**This is the step I believe is false**, and it is what the experiment tests.

## My predictions, recorded before any number exists

**P1.** With a FIXED annual edge split across N trades per year and ZERO cost, the probability of
a losing year will be **the same at every N**. Frequency alone buys nothing. Any variation across
N will be simulation noise, not a trend.

**P2.** With a realistic per-trade cost, the probability of a losing year will **rise monotonically
with N**, because cost is charged per trade while the edge is not.

**P3.** In the only case where frequency helps — where each trade carries its OWN fresh edge, so
the annual Sharpe grows with √N — the probability of a losing year falls steeply. **This is the
Medallion case, and it is a statement about the EDGE renewing, not about frequency.**

**P4 (the real-world check).** Among the 195 sealed predictors, those whose own papers rebalance
MONTHLY will **not** show a lower share of losing years than those that rebalance ANNUALLY, once
each is measured on its own sealed window at zero cost.

## What would refute me

If P4 comes out the other way — monthly predictors losing in meaningfully fewer years than annual
ones at zero cost — then frequency does buy something real that the simulation's structure misses,
and I would have to withdraw the "frequency alone buys nothing" framing I have used all day.

## Scope and honesty notes

- The empirical arm is a DESCRIPTIVE cut of the already-computed sealed series, at zero cost, with
  no selection and no verdict — the same standing as the 2026-09-13 holding-period cut. It does
  not spend a new look.
- "Losing year" means a negative 12-month compounded return, measured on non-overlapping calendar
  years, and for the simulation on a normal-returns model whose fat tails are absent; real anomaly
  returns are negatively skewed, so every probability here is optimistic.
