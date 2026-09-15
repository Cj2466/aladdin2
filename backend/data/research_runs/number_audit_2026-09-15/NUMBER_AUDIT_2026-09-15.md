# Audit of every number and rule behind the current plan (2026-09-15)

Owner's instruction: check every mechanism, every threshold, and every number involved in this
work; confirm each is correct and by the book; find anything I invented that could cause a
problem. Done by the orchestrator directly, not delegated (CLAUDE.md rule 2 puts verification
with the orchestrator). Scripts: `audit_lockbox_numbers.py`, `audit_diversification_math.py` —
both written from the protocol only, importing no project helper and not `osap_lockbox.py`
(the project's own rule that a re-derivation sharing helpers is not independent).

---

## PART 1 — what verified CLEAN

| # | claim | how checked | result |
|---|---|---|---|
| V1 | OSAP source files unchanged since fetch | SHA-256 vs `osap/SOURCES.md` | **both match exactly** |
| V2 | headline pooled Sharpe 0.599 | fully independent re-derivation | **195 members, 612 months, mean 0.4202 %/mo, SR 0.5991** — exact |
| V3 | Newey-West t 4.27 | own Bartlett-kernel NW(6) | **4.2693**; naive t 4.2787, ratio 0.998, ρ₁=+0.081 — NW is genuinely applied and correctly makes little difference |
| V4 | √12 annualization is legitimate | Lo (2002) autocorrelation adjustment | scale factor 0.796 → **Lo-adjusted SR 0.672 > naive 0.599**; the naive figure is CONSERVATIVE, not inflated |
| V5 | effective-bets formula | read `coverage_map.py:59-67` | `M_eff = avg_var / var_pool` is the standard variance-based definition, correctly implemented, with the derivation in the comment |
| V6 | the √M diversification identity | recomputed on ONE identical sample | **exact: 0.1751 × √35.04 = 1.0364 = measured pooled, ratio 1.000** |
| V7 | `POWER_FLOOR = 0.80` | read `dsr_power.py:86-91` | honestly labelled "a convention, not a derivation", attributed to Cohen (1988) — correct practice |
| V8 | `SCREENING_FLOOR = 0.50` | `templates/REGISTRATION_SCORECARD_TEMPLATE.md:113-114` | a DOCUMENTED project convention ("screening floor, never proof"), with a written rationale — not invented ad hoc, but not externally sourced either |
| V9 | certifiability bar ≈ 2.4 | `PROJECT_WORKLIST.md:213` | **2.416** for US equity over 10.683 years — confirmed |

---

## PART 2 — problems found, worst first

### P1. The PASS verdict is one unsourced constant away from flipping — MOST SERIOUS

The standard haircut is `20/P bps per month = 4 legs × DEFAULT_XS_COST_BPS / P`.
`cross_sectional.py:297-305` says of that constant, in its own words: *"mirrors momentum.py's
DEFAULT_COST_BPS = 5.0 single-leg convention (itself half of pairs' two-leg 10bps), **not
independently recalibrated**"*. The 2026-09-12 cost audit traced the chain to
`ou_pairs.DEFAULT_COST_BPS = 10.0`, which carries no citation at all.

The protocol's own doubled-cost row: **Sharpe 0.412 — BELOW the 0.50 pass line.**

| haircut | pooled Sharpe | verdict against the 0.50 line |
|---|---|---|
| gross | 0.785 | PASS |
| standard (5 bp one-way) | **0.599** | **PASS** ← the reported verdict |
| doubled (10 bp one-way) | 0.412 | **FAIL** |

So "PASS" is true at 5 bp and false at 10 bp, and 5 bp is not sourced. This does not make the
result wrong — the protocol declared all three arms in advance and reported them — but the
headline should never be stated without the sensitivity beside it. **Step A2 (per-ticker measured
cost) is therefore not an optimisation; it is the thing that decides whether the verdict stands.**

### P2. "612 months / 51 years" describes a book that did not exist for two decades

Measured membership per month:

| month | members live |
|---|---|
| 1974-01 | **2** |
| 1980-01 | 4 |
| 1990-01 | 11 |
| 2000-01 | 43 |
| 2010-01 | 150 |
| 2020-01 | 192 |

**252 of 612 months (41%) have fewer than 20 members.** The pooled series is honest arithmetic,
but "a book of ~200 anomalies over 51 years" is not what the early half measures. Anywhere the
51-year framing is used, the membership profile must travel with it.

### P3. A consistency check I stated in conversation was wrong — MY ERROR

I told the owner: *"0.169 × √14.6 = 0.645 ≈ the measured 0.597, so the formula and the
measurement agree."* That string appears in **no committed file**; it was conversational only.
It paired three quantities from three different populations:

- `0.169` = median per-predictor Sharpe in the **post-SAMPLE** window (`RESULT_SET2_OSAP.md` row 5)
- `14.6` = effective bets among **23 CATEGORY pools of BUILDABLE predictors**
- `0.597` = pooled Sharpe over the **post-PUBLICATION** window, all 195

Done properly on one identical sample (2010-01 → 2024-12, 146 members present throughout):

| quantity | value |
|---|---|
| median member Sharpe | 0.1657 |
| mean member Sharpe | 0.1564 |
| **ratio-of-averages Sharpe** (the algebraically correct input to √M) | **0.1751** |
| effective independent bets among the 146 | **35.04** |
| measured pooled Sharpe | **1.0364** |
| 0.1751 × √35.04 | **1.0364 — ratio 1.000, exact** |

The underlying mathematics is sound. My arithmetic presenting it was not. Also note: the
median/mean-member versions are only approximations (ratios 0.946 / 0.893) — they are exact only
when every member has identical variance, which is not the case here.

### P4. `PSR ≥ 0.95` was a near-vacuous second gate

At n = 612 monthly observations, PSR against a zero benchmark clears 0.95 for any annualized
Sharpe above roughly **0.21**:

| annualized SR | approx PSR at n=612 |
|---|---|
| 0.10 | 0.76 |
| 0.20 | 0.92 |
| 0.30 | 0.98 |
| 0.50 | 0.9998 |

The declared pass line read as two conditions but was, at this sample length, effectively the
single condition "Sharpe ≥ 0.50". Not an error — PSR at N=1 was correctly specified and correctly
computed — but it should not be presented as independent corroboration.

### P5. Two result sets quoted to the owner are on UNMERGED branches

`spread-estimator-audit-2026-09-12` (cost-constant audit, spread-estimator audit, discarded-strategy
search) and `holding-period-2026-09-13` (the 1-month vs 12-month edge/cost table) are committed to
their branches but **not merged to main**, so they are outside main's test suite and outside the
end-to-end re-check. Governance debt, logged here.

### P6. No borrow cost, and shorting is assumed free AND available

The protocol states this ("the project's own equity default is 0; disclosed as lenient"), but the
disclosure understates it for this owner: OSAP's pools are 210 of 242 equal-weighted, so micro-caps
carry real weight, and micro-cap borrow for a retail account is frequently **unavailable at any
price**, not merely expensive. A long-short book that cannot be shorted is a different object from
the one measured.

### P7. My "roughly 1 losing year in 4" was slightly optimistic

Correct figure at annualized Sharpe 0.599, assuming normal returns:
**P(negative excess return in a year) = 27.5%, i.e. 1 in 3.6.**
At the doubled-cost 0.412 it is 34.0%, 1 in 2.9. Anomaly returns are negatively skewed and
fat-tailed, so the true frequency is likely worse than the normal figure, not better.

### P8. The sealed dataset's one-look budget has been drawn down further than declared

`LOCKBOX_PROTOCOL_OSAP.md` §6 says the look is not repeated and no variant may be promoted to
primary afterwards. Since the single look there have been: the coverage map (a **declared**
extension, @4c17e89), Set 3, the holding-period cut, and now this audit's C5/C6/C8. Each is
defensible on its own and none changed the verdict, but the dataset's remaining evidential value
is finite and shrinking.

**Binding consequence, recorded now:** the following numbers produced by THIS audit are
diagnostics of an existing result and **may never be promoted to a verdict or quoted as the
result**: months-with-≥20-members Sharpe 0.9568; 2010-2024 predictor-level pooled Sharpe 1.0364;
M_eff 35.04. They were obtained by selecting sub-windows after seeing the full-sample answer.

---

## PART 3 — what changes because of this audit

1. **A2 is now load-bearing, not preparatory.** P1 means the headline verdict is decided by the
   cost number. A2 must produce a per-ticker measured cost with an explicit measured-vs-assumed
   share, and the book's Sharpe must be re-stated at the measured cost before the result is used
   for anything.
2. **Every future statement of the 0.599 result carries three things**: the doubled-cost 0.412,
   the membership profile, and the no-borrow-cost caveat. Not as footnotes.
3. **Prefer slow members**, per the holding-period result — not because they earn more (they do
   not) but because P1 does not bite them: annual rebalancers give up 0.03 Sharpe to costs,
   monthly ones give up 0.28.
4. **Merge or explicitly park the two branches in P5** before any further work depends on them.
5. **The √M table quoted to the owner is superseded** by the corrected figures in P3.

## What this audit did NOT cover

The whole-market panel counts (14,451 symbols / 20,345,521 rows), the delisting outcome table,
the FSDS coverage percentages, the EDGAR announcement counts, and the 20 existing family
registrations were verified when they were built and are not re-verified here. The spread-estimator
audit's own four rules were read but its synthetic-audit numbers were not re-derived.
