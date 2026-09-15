# Every documented mechanism of the Medallion Fund, graded, and what of it we can have

Owner's instruction, 2026-09-15: "ไปหาข้อมูลและรวบรวมกลไกทุกอย่างของ medallions fund หา
อย่างครบถ้วน ว่าอันไหนทำได้บ้างอันไหนที่เราทำไม่ได้บ้าง แล้วเขียนข้อกำหนดมา คิดอย่างรอบคอบ"

This domain is full of myth. **Every row below carries an evidence grade**, and the grades are
the point of the document. Nothing here is asserted because it is widely repeated.

| grade | meaning |
|---|---|
| **P** | PRIMARY — sworn testimony, regulatory record, or peer-reviewed publication |
| **J** | JOURNALISM — Zuckerman's book or a major outlet; reported, not independently verifiable |
| **I** | INFERENCE — my own reasoning from P or J facts, labelled as mine |
| **U** | UNVERIFIED — widely repeated with no traceable primary source |

Primary sources used: **US Senate Permanent Subcommittee on Investigations, "Abuse of Structured
Financial Products: Misusing Basket Options to Avoid Taxes and Leverage Limits", hearing of
22 July 2014** (transcript fetched and read); **Cornell, "Medallion Fund: The Ultimate
Counterexample?", Journal of Portfolio Management 2020**. Journalism: Zuckerman, *The Man Who
Solved the Market* (2019), via published chapter notes.

---

## PART 1 — THE MECHANISMS

### A. Data

| # | mechanism | grade | can we? |
|---|---|---|---|
| A1 | Tick-by-tick price data collected from the 1960s onward, bought on magnetic tape and hand-cleaned, when everyone else used daily closes | J | **NO** — we have 10.7 years of daily bars |
| A2 | Data cleaning treated as a first-class research activity, not preparation | J | **YES** — and we already do it; the 2026-09-15 audit is exactly this |
| A3 | Non-price data: weather, satellite imagery, shipping | U | **NO** (and unproven it mattered) |
| A4 | ~50,000 cores, petabyte warehouse growing ~40 TB/day | U | **NO** |

**A2 is the one transferable item in this group, and it is not a small one.** Their own history
says the data work came before the models worked.

### B. Modelling

| # | mechanism | grade | can we? |
|---|---|---|---|
| B1 | Hidden Markov models fitted by Baum–Welch | J (strong: Leonard Baum, co-author of the algorithm, was an early collaborator) | **YES, technically** — but see the limit below |
| B2 | High-dimensional kernel regression | J | **YES, technically** |
| B3 | ONE monolithic cross-asset model rather than per-researcher systems | J (Laufer/Simons) | **YES — and this is a real, free choice we have not made** |
| B4 | No requirement to explain WHY a pattern works | J | **NO — deliberately refused**, see Part 3 |
| B5 | Automated signal discovery | U | partial |

**The limit on B1/B2:** the algorithms are free and in every library. What is not free is the
sample size that makes them safe. Fitting a high-dimensional model to 10.7 years of daily bars
is how this project's own 58 honest negatives were produced.

### C. Signals

| # | mechanism | grade | can we? |
|---|---|---|---|
| C1 | Short-horizon trend continuation and mean reversion | J | **tested, NEGATIVE** — see Part 3 |
| C2 | "We make money from the reactions people have to price moves" — employee, quoted | J | in principle |
| C3 | Day-of-week sequences (Monday follows Friday; Tuesday reverts) | J | **tested, NEGATIVE** |
| C4 | The "twenty-four hour effect" — yesterday's trading predicts today's | J | **tested, NEGATIVE** |
| C5 | Prices fall before and rise after scheduled economic releases | J | **partially open** — we have never built the release calendar |
| C6 | Statistical arbitrage: "trying to determine relationships between different assets and whether one asset's price is out of kilter" — Rosenthal, under oath | **P** | partial (our eigenportfolio family) |
| C7 | A signal named "Déjà Vu" | J | unknown — the NAME is public, the content is not |

**Every C-row above that is specific enough to test, we have tested.** See Part 3.

### D. Portfolio construction

| # | mechanism | grade | can we? |
|---|---|---|---|
| D1 | Thousands of instruments held simultaneously | P | **YES** — breadth is free to us |
| D2 | Continuous position sizing proportional to signal strength, not binary buy/sell | J/I | **YES** |
| D3 | Many weak, weakly-correlated signals rather than a few strong ones | J | **YES — this is already our design** |
| D4 | **Portfolio turnover about 87% every 3 months** — Rosenthal, under oath | **P** | **YES** — see the correction in Part 3 |

### E. Execution

| # | mechanism | grade | can we? |
|---|---|---|---|
| E1 | "more than 100,000 trades a day, more than 30 million trades a year" — Rosenthal, under oath | **P** | **NO** |
| E2 | "Renaissance … would direct trades directly to the exchange. That direction would take milliseconds. There was no practical way for the bank to intervene" — Rosenthal, under oath | **P** | **PARTIAL** — retail DMA exists; millisecond control does not |
| E3 | Orders sliced small to avoid moving the price | J/I | **NOT NEEDED** — our size has no impact |
| E4 | Earning the spread rather than paying it (liquidity provision) | **I — MY INFERENCE, NOT DOCUMENTED** | untested |

**E4 is flagged hard.** I have used it repeatedly in conversation as if established. It is my
inference from their cost structure. No primary or journalistic source I found states that
Medallion is a net liquidity provider. It may be true; it is not evidenced.

### F. Leverage and legal structure

| # | mechanism | grade | can we? |
|---|---|---|---|
| F1 | Leverage "as high as 20:1" via bank basket options, against the 2:1 Regulation T limit — Senator Levin | **P** | **NO** — retail Reg T is 2:1 |
| F2 | Converting short-term gains into long-term for tax | **P** | **NO — and must not** |
| F3 | 60 basket options 2000–2014, ~$34bn pre-tax profit through them | **P** | — |
| F4 | The IRS ruled F2 improper; insiders settled for ~$7bn in 2021 | **P** | — |

**F1 is the mechanism most likely to be underweighted by anyone reading the return figures.**

### G. Organisation

| # | mechanism | grade | can we? |
|---|---|---|---|
| G1 | "more than 200 to 250 employees, including 90 Ph.D.s" — Rosenthal, under oath | **P** | **NO** |
| G2 | One shared codebase; everyone sees everything | J | **YES** |
| G3 | Hire scientists, not finance people | J | n/a |

### H. Capital discipline

| # | mechanism | grade | can we? |
|---|---|---|---|
| H1 | Hard cap around $10bn; outside money returned (sources differ: 1993 for the first closure, ~2005 for completion — **the discrepancy is left standing, not resolved**) | J | **YES, by accident** — we are far below any cap |
| H2 | Size discipline treated as part of the strategy rather than a constraint on it | J/I | **YES** |
| H3 | Fees 5% management + 44% performance | J | n/a |

---

## PART 2 — THE SCOREBOARD

Of 26 mechanisms identified:

| verdict | count | which |
|---|---|---|
| **We can have it** | **10** | A2, B3, D1, D2, D3, D4, E3(n/a), G2, H1, H2 |
| **Partial** | 4 | B1, B2, C6, E2 |
| **Cannot** | 9 | A1, A3, A4, E1, F1, F2, G1, and the sample size behind B1/B2 |
| **Refused on principle** | 1 | B4 |
| **Tested and negative** | 3 | C1, C3, C4 |
| **Open** | 2 | C5, E4 |

---

## PART 3 — TWO CORRECTIONS THIS RESEARCH FORCES ON ME

### Correction 1 — WITHDRAWN THE SAME DAY. See Correction 1-bis below; the original text is kept.

~~Medallion's holding period is MONTHS, not days. I told the owner "about 2 days."~~

I said Medallion holds each position "ประมาณ 2 วัน", from a secondary web source. The **primary
source contradicts it.** Under oath, RenTec's own counsel Jonathan Rosenthal:

> "The Renaissance hedge funds traded often, more than 100,000 trades a day, more than 30 million
> trades a year, and they traded quickly, turning over their portfolio almost completely every
> 3 months." … "The turnover in 3 months' time was about 87 percent."

**Trades ≠ position changes.** Over 100,000 trades a day against a few thousand positions means
each position is worked through many child orders — that is ORDER SLICING (E3), not turnover.
The position-level turnover is **~87% per quarter**, i.e. an average holding period on the order
of **three to four months**.

**This materially narrows the distance between their design and ours.** I told the owner our
direction was "300x different" from Medallion on the time axis. Against the primary source it is
roughly 3–8x, not 300x.

### Correction 1-bis — THE ABOVE IS WITHDRAWN. The owner asked "how do you know?" and the answer is that I did not.

The owner's question ("คุณรู้ได้ยังไงว่า Medallion ถือหุ้นเป็นเดือน ไม่ใช่ 2 วัน") sent me back to
pull the **full transcript directly** rather than a fetched summary. Three things in it defeat
Correction 1, two of them on the same page as the sentence I built it on.

**1. The arithmetic does not survive contact with the other primary number.** If a few thousand
positions each turned over in ~2 days, quarterly turnover would be on the order of 3,000–4,500%,
not 87%. Those two figures cannot both describe the same quantity. That means "turnover" in
Rosenthal's sentence is almost certainly NOT gross traded value over portfolio value — it is more
likely how much of the portfolio's COMPOSITION changed. Under that reading, a book can churn the
same names all day while its membership drifts slowly, which is exactly consistent with 100,000
trades a day AND 87% quarterly turnover AND short holding periods. **I picked a definition of
"turnover" without checking it and manufactured an average holding period out of it.**

**2. RenTec's own counsel calls it short-term in the very next clause**, which the fetched
summary cut off:

> "…turning over their portfolio almost completely every 3 months. **Because the hedge funds
> adopted a short-term trading** [strategy]…"

**3. The chairman characterises the securities as days-to-seconds, twice:**

> "When securities are held for **weeks or days or even seconds**, it is surreal to characterize
> those trading profits as long-term capital gains."
> "It was fiction to treat the profits from **trades lasting days or even seconds** as long-term
> capital gains."

**And the one long holding period in the record is the WRAPPER, not the stock.** RenTec's witness:

> "The average holding period of **the Deutsche Bank options** from 2000 through 2009 was around
> **450 days**. For Barclays, it was around 400 days."

That is the option contract, held past a year for tax treatment, while the securities inside were
traded continuously — which was the entire subject of the hearing. Conflating the two is the exact
error the hearing existed to expose, and it is adjacent to the error I made.

**What the record actually supports:** Medallion's securities trading is SHORT-TERM. The public
record does not fix a typical holding period, and the "about 2 days" figure — which has no primary
source — is not contradicted by it and may well be closer than my correction was.

**Consequence for the rest of this document:** R1's "the gap is 3–8x, not 300x" is WITHDRAWN. The
gap between Medallion's holding period and a quarterly-to-annual rebalance is large and
unquantified from public evidence. **R1 is restated below.**

**Consequence for me:** I issued a confident numerical correction built on one unchecked word
("turnover"), and it took the owner asking "how do you know" to catch it. The failure mode is the
same one this project's rules exist for — a number that felt solid because it came from a good
source, without checking that the source meant what I assumed.

### Correction 2 — "they earn the spread instead of paying it" is MY inference, not a fact

E4 above. I have leaned on it repeatedly. No source I found supports it directly. It should be
treated as a hypothesis about Medallion, and separately as a testable question about US
(measurement B in the current plan), but it must stop being quoted as something Medallion is
known to do.

### And one thing that is NOT a correction, because we already tested it

C1/C3/C4 — trend-continuation, day-of-week sequences, yesterday-predicts-today — are the specific
Medallion-style signals that are publicly described. This project ran a **pre-registered,
theory-free pattern scan** over 1,437 US names and 25 crypto pairs on 2026-09-11 and found
**nothing that beat its own placebo**. We did not fail to try their approach. We tried it and it
was empty, which is what a 30-year-old published pattern should be.

---

## PART 4 — THE REQUIREMENTS, WRITTEN AS RULES

What follows is a specification, not a summary. Each rule names the mechanism it comes from.

### R1. Breadth replaces frequency — and the size of the gap is UNKNOWN
From D1, D4, E1, as restated by Correction 1-bis. We cannot place 100,000 orders a day. We CAN
hold thousands of names. **What we cannot do is quantify how far our holding period sits from
theirs**: the public record establishes that Medallion's securities trading is short-term and that
at least 87% of the portfolio's composition changes within three months, but not a typical holding
period. Any claim of the form "we are N times slower than Medallion" is unsupported and must not
be made. **Design target stands on its own merits — quarterly-to-annual rebalance, thousands of
names — justified by OUR measured costs (A2, 2026-09-15), not by proximity to Medallion.**

### R2. Many weak signals, never a few strong ones
From D3, B3. Already our design. The binding number is the count of *independent* bets, which our
own coverage map puts at 10–15 from the published-anomaly route — short of the ~30 the BOOK needs.

### R3. One model, one codebase, one set of numbers
From B3, G2. **This is a free choice we have not made.** Our 20 families are 20 separate modules
with separate conventions; the 2026-09-15 audit found three different cost conventions in one
file. Consolidation costs nothing but work and is the most Medallion-like thing available to us.

### R4. Data work is research, not preparation
From A2. Continue treating audits like 2026-09-15 as first-class output.

### R5. Position size is continuous, never binary
From D2. No "buy list" — a weight per name proportional to signal strength divided by cost and risk.

### R6. Size discipline is deliberate, and we already have it for free
From H1, H2. Our capital is far below any capacity limit, and HXZ price the equal-weighted
anomaly corner at $26.6bn of capacity against $2,015.65bn value-weighted. **This is the one axis
on which we are structurally advantaged and Medallion was structurally constrained.**

### R7. We do NOT adopt "no need to know why"
From B4. Refused deliberately. Medallion could accept unexplained patterns because their sample
sizes made overfitting detectable. Ours do not: this project measured a Sharpe of **2.37 on data
with a TRUE edge of zero** when specs were selected after the fact. Without their data, dropping
the mechanism requirement does not buy their freedom, it buys false positives.

### R8. Leverage is a first-class part of the return, and ours is capped at 2:1
From F1. Medallion ran up to 20:1. **Any return target must be stated at OUR leverage.** A book
with Sharpe 0.7 and 5% volatility returns ~3.5%/yr unlevered; the owner's 10%/yr target needs
about 3x, which exceeds Reg T on a cash-margin account. **This is an unresolved gap in the plan
and is recorded here as such for the first time.**

### R9. Nothing from F2 — ever
The tax structure produced part of the reported return and was ruled improper. Out of scope.

### R10. Execution venue is a design variable, not an afterthought
From E2, E3. We cannot have millisecond routing. We CAN choose venue and order type — auction,
midpoint, resting limit — and the 2026-09-15 cost work shows that choice may matter more to us
than any signal decision. Measurements A and B in the current plan are this rule's first test.

---

## What this document does NOT establish

It does not say the mechanisms above are why Medallion made 66% a year. Nobody outside the firm
knows that, and the largest single documented contributor to the reported figures is F1 leverage
plus F2 tax treatment, neither of which is a trading insight. The transferable part is a design
philosophy — breadth, weak signals, position sizing, data discipline, size discipline — and this
project already had most of it before reading any of this.
