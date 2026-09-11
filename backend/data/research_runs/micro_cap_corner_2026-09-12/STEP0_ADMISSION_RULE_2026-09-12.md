# Step 0 admission rule — declared BEFORE any corner candidate is measured (2026-09-12 ~02:05 Bangkok)

Orchestrator: Fable 5.1. This is the rule Step 0 uses to COUNT "admissible members" on Day 6.
It is a trial rule for this week only; it changes no project rule (CLAUDE.md untouched), no
registration, no manifest. If the owner adopts the five principles, a portfolio-level version of
this rule would be proposed for CLAUDE.md then — not now.

Why it is written now: the Day 1 census gave 0 admissible of 20 under criteria (i)/(ii) alone.
Day 2–5 will measure new candidates in the micro-cap corner; the count must not be able to move
the goalposts after seeing results.

## A. A candidate counts as ADMISSIBLE AT SOURCING when all of R1–R6 hold

| rule | requirement | evidence required |
|---|---|---|
| R1 forced loser | an identifiable participant must trade against the position by rule (fund redemption, index rule, mandate/price-level constraint, tax rule, margin/delisting rule) — not merely "underreaction" or "sentiment" | the primary source names the rule; quoted in the sourcing file |
| R2 closed corner | the traded instruments are ones large capital cannot profitably collect: below-NYSE-20th-percentile market cap or equivalently illiquid, or held out by a documented mandate constraint | the source or a follow-up measures the effect BY size / breadth and it survives only in the corner; or the constraint is documented |
| R3 size | the source's claimed NET Sharpe, at the conservative fraction 0.5 of the claim, is ≥ 0.30 — the BOOK's own assumed member Sharpe (book pre-registration 2026-09-09: 30 members at 0.3, ρ 0.05) | derivation shown (t/√years or μ/σ); "my calculation" labelled; cost basis stated |
| R4 independence | expected ρ with every member already counted admissible ≤ 0.30 (measured on returns once built; at sourcing, argued from mechanism and instruments) | Day 1 pairwise table as the reference; 0.30 is the level at which 5 of 8 Day-1 pairs clustered on one hub |
| R5 BOOK power gain | adding the candidate raises the BOOK's power to clear 0.95 in 10 years, computed with the existing `sourcing_power_check` on the pooled Sharpe s·√(M/(1+(M−1)ρ̄)) for M+1 vs M members (no new formula) | the two power numbers, with inputs |
| R6 free data | buildable now on data the project holds (Alpaca 2016+ incl. delisted; N-PORT 2019q4+; EDGAR; FINRA; 13F) with any gap logged as a paid decision, not bought | data path stated; missing pieces listed |

A candidate failing any of R1–R3 or R6 is DECLINED AT SOURCING and recorded in
`DECLINED_AT_SOURCING.md` (existing rule). R4/R5 failing means "redundant with the book", recorded
the same way with the ρ or power numbers.

## B. A candidate counts as PRODUCED (the Day 6 number) when, in addition

| rule | requirement |
|---|---|
| P1 | pre-registration committed before any return is computed, with the control non-degeneracy proof (existing rule) |
| P2 | built and independently re-derived by the orchestrator from raw files with separate code (existing practice) |
| P3 | its net in-sample Sharpe at the baseline cost arm ≥ 0.30 AND its placebo/no-signal control does not match it (Dormant pool's placebo-override rule) |
| P4 | measured ρ against every other produced member ≤ 0.30 |

P3 is deliberately the SCREENING level, not the 0.95 certification: under the five principles the
BOOK is what gets certified, over calendar time. An in-sample 0.30 is not evidence of an edge —
it is the admission ticket to be watched.

## C. What Day 6 reports

"Admissible at sourcing: A. Produced: X (list)." Decision point 1 uses X: X ≥ 3 → owner decides
Path A's 3-year wait; X ≤ 1 → discuss Path B. X = 2 → owner's call, with the two members' ρ shown.

## D. Honest expectation, recorded before results

The 2026-09-11 sourcing found the best net micro-cap claim in the literature at 0.93 (NMV Table
13, PEAD) — which passes R3 easily but fails R1 (underreaction, not forced). Forced-flow claims
in the corner are typically reported as event abnormal returns, not Sharpes, so R3's derivation
will often be the binding uncertainty. Most likely outcome: 1–3 admissible at sourcing, 0–2 produced.
