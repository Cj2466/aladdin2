# Day 1 — census of the 20 existing candidate BOOK members (2026-09-12)

Orchestrator: Fable 5.1 (main session). Sub-agents: none. Everything below was computed or
read by the orchestrator. Worktree `member-census-2026-09-12`.

## 0. What this answers

Step 0's Day 1 question (`STEP0_WEEK_PLAN_2026-09-12.md`): of the 20 specs that would be the
BOOK's members today (16 Dormant, 4 Active), how many satisfy the NEW sourcing criterion —

- **(i) forced loser**: an identifiable participant must trade against the position regardless of
  price (a mechanical seller/buyer), so the return is not a bet on being smarter than a voluntary
  counterparty; and
- **(ii) not collectable by big money** (first principle F5): the edge sits where a large fund cannot
  profitably collect it — otherwise competition compresses it to the large fund's cost, not ours —

and how correlated they are with each other (F4: pooled Sharpe ≈ s·√(M/(1+(M−1)ρ))).

Part A is a **statistical measurement** (scripts committed here). Part B is the orchestrator's
**classification judgment** on each member's mechanism, made from the source each family's own
module cites; it is a reading, not a measurement, and is labelled as such. Nothing here changes any
registration, manifest or rule.

## A. Pairwise correlation — measured

Script: `member_census.py`. Inputs: the committed per-spec net daily return matrix captured on
2026-09-05 (`global_effective_n_return_matrix_2026-09-05.csv.gz`, 18 of the 20 specs) plus
`capture_missing_two.py`, which reuses the Dormant re-scorer's own capture path for the two
families built after that run. Pairwise ρ on common days, reported only when ≥ 252 overlap days.

Disclosures:
- The 09-05 matrix PRE-DATES the 2026-09-09 price-store repair (APH/MNST/RUSHA fabricated days),
  so the equity series carry those defects. The Dormant looks measured the resulting Sharpe drift at
  ≤ 0.02 per family; a correlation is less sensitive than a Sharpe to three tickers' single days,
  but this was not re-measured here.
- `dividend_payment_pressure` replayed nothing on the first attempt: its payment calendar
  (`data/dividend_payment_calendar.json`) is gitignored and resolved per-WORKTREE, so the worktree
  had none while the MAIN checkout held the 2026-09-09 file (2.78 MB). The main checkout's file was
  copied into the worktree unchanged (SHA-256 prefix be87cd4fba9847d9cf19 on both) and the capture
  re-run — the same calendar the 09-09 Dormant re-measurement used, not a fresh non-point-in-time
  rebuild (a rebuild had been started and was stopped before it wrote anything). Same class of
  per-worktree routing gap as the price store had before 2026-09-09; logged in PROJECT_WORKLIST §6.5.

### A.1 Results (20 of 20 series, 190 pairs; from `member_census_summary.json`)

| quantity | value |
|---|---|
| mean pairwise ρ | 0.018 |
| mean |ρ| | 0.072 |
| largest |ρ| | 0.426 — residual_momentum × round_c (lps_intraday) |
| pairs with |ρ| ≥ 0.30 | 8 (listed below) |
| pooled Sharpe if every member's TRUE Sharpe were 0.3, ρ = 0.018 (approximation) | 1.16 at M=20; 1.33 at M=30 |

Independently re-derived (plain-Python, no shared helper, scratch `rederive_rho.py`):
rm×lps 0.4262861486398814 on 2,927 days; cbop×si 0.39047466862782443 on 2,166; ag×bonds
−0.02461493295185466 on 2,927 — all equal to the script's values to the last digit.

The eight pairs at |ρ| ≥ 0.30, and what they mean:

| pair | ρ | reading |
|---|---|---|
| residual_momentum × round_c/lps_intraday | 0.43 | both are S&P 500 return-persistence sorts |
| round_c/lps_intraday × small_cap_disposition | 0.42 | persistence vs capital-gains-overhang share a momentum loading |
| quality_cbop × short_interest | 0.39 | both long "clean large-cap quality"; the two definite_negative live cards |
| pead_ear × round_c/lps_intraday | 0.39 | post-announcement drift is a persistence sort |
| correlation_risk_premium × vol_regime | 0.34 | both are SPY/IEF timing on option-implied state variables |
| round_c/lps_intraday × quality_cbop | 0.33 | |
| round_c/lps_intraday × short_interest | 0.31 | |
| pead_ear × small_cap_disposition | 0.31 | |

**round_c/lps_intraday appears in 5 of the 8**: it is the correlation hub of the current membership.
Under the BOOK's own admission logic it would be the first member a portfolio-level pre-check
would refuse (it adds the least independent power).

### A.2 What the numbers say

The average member pair is close to independent (mean ρ 0.02, in line with the 0.05 the BOOK
pre-registration assumed), so F4's √M diversification is real for THIS membership — **if** the
members have any true edge. That "if" is the whole question, and Part A cannot answer it: every
one of these Sharpes was estimated on the same data that selected the spec.

### A.3 The two late-captured members

| member | series | strongest |ρ| with any other member |
|---|---|---|
| rebalancing_pressure / rebal_threshold_scaled_h1 | 5,810 days | −0.14 (correlation_risk_premium), −0.09 (bonds), +0.09 (dividend_payment_pressure) |
| dividend_payment_pressure / divpay_raw_payment_top10 | 2,180 days, 2018-01-03 → 2026-09-04 | +0.09 (rebalancing_pressure), −0.08 (CRP), −0.07 (vol_regime) |

Both are near-independent of everything else, including of each other — consistent with two
different forced flows (month-end 60/40 rebalancing; dated dividend reinvestment) landing on the
same instrument at different times.

## B. Forced-loser / big-money classification — orchestrator's judgment

For each member: the mechanism as the family's own module states it (source cited there), then the two
criteria, then a verdict — **ADMISSIBLE** (both hold), **DOUBTFUL** (one holds or arguable),
**NOT** (neither). Persisted net Sharpe is the in-sample value from the Dormant manifest or the live
scorecard, quoted only to show size; it is not evidence of an edge.

| # | member (pool) | mechanism per source | (i) forced loser? | (ii) big money can't collect? | verdict |
|---|---|---|---|---|---|
| 1 | asset_growth / ag_low_ls_h126 (Dormant, 0.29) | Cooper-Gulen-Schill investment effect, S&P 500 EDGAR fundamentals | no — voluntary mispricing story | no — liquid large caps, published 2008 | NOT |
| 2 | best_ideas_13f / bi_conviction_count_h63 (Dormant, 0.67) | Antón-Cohen-Polk: managers' largest active bets, public 13F | no | no — the paper tests manager skill, not outsider tradability; large caps | NOT |
| 3 | bonds / bonds_curve_carry_l63_h126 (Dormant, 0.34) | term-structure carry across 8 Treasury/credit ETFs | no established forced counterparty in the source | no — the most liquid market on earth | NOT (a risk premium; belongs to Path B, not to an edge book) |
| 4 | buyback / nsi_l504_ls_h126 (Dormant, 0.45) | net share issuance, S&P 500 | no — management timing, voluntary | no | NOT |
| 5 | commodities / cmd_momentum_l126_h126_inverse_vol (Dormant, 0.90) | Erb-Harvey momentum across 11 commodity ETFs | no (hedgers are a carry story, not a momentum story) | no — ETF-liquid, CTA-crowded | NOT |
| 6 | correlation_risk_premium / crp_realized_21d_h63 (Dormant, 0.26) | Driessen-Maenhout-Vilkov: implied − realized correlation as a SPY timing signal | no — option writers sell it voluntarily | no — SPY | NOT (risk premium) |
| 7 | dividend_payment_pressure / divpay_raw_payment_top10 (Dormant, 0.40) | Hartzmark-Solomon AER 2025: market-wide dividend PAYMENTS are mechanically reinvested → predictable SPY pressure | **YES** — reinvestment is mechanical and dated | **no** — the instrument is SPY and the paper is in the AER; any fund can front-run it at lower cost than we pay | DOUBTFUL (passes i, fails ii) |
| 8 | eigenportfolio_statarb / eig_m1_c252_wide (Dormant, 0.09, HIGH bucket) | Avellaneda-Lee residual mean reversion, S&P 500 | no | no — the natural home of large stat-arb desks at far lower cost | NOT |
| 9 | fx / fx_momentum_l63_h126_inverse_vol (Dormant, 0.16) | G10 momentum | no | no | NOT |
| 10 | insider_opportunistic / insider_opp_buy_h21_c2_equal (Dormant, 0.07) | Cohen-Malloy-Pomorski: opportunistic insider buys | no — information, not forced trading | no — S&P 500, public Form 4 | NOT |
| 11 | pead_ear / pead_ear_wm1p1_h126_equal (Dormant, 0.10) | post-earnings drift via announcement return, S&P 500 8-Ks | no — underreaction | no on S&P 500; the literature (McLean-Pontiff; NMV Table 13) says it survives only in the costly-to-arbitrage corner | NOT here; **re-test candidate for the micro-cap corner (Day 2–3)** |
| 12 | rebalancing_pressure / rebal_threshold_scaled_h1 (Dormant, 0.57) | Harvey-Mazzoleni-Melone: 60/40 rebalancers must trade at month-end / thresholds | **YES** — rebalancing is mandated by policy | **no** — SPY vs IEF; the paper itself documents hedge funds front-running it | DOUBTFUL (passes i, fails ii) |
| 13 | residual_momentum / rm_ff3_residual_neutral_ls_h21 (Dormant, 0.29) | Blitz-Huij-Martens residual momentum, S&P 500 | no | no | NOT |
| 14 | round_c / lps_intraday_l252_h63 (Dormant, 0.28) | Lou-Polk-Skouras overnight/intraday clientele persistence | no — clienteles differ, nobody is forced | no | NOT; also the correlation hub (§A.1) |
| 15 | small_cap_disposition / sc600_cgo_ls_decile_l504_h252 (Dormant, 0.45) | Grinblatt-Han capital-gains overhang on the S&P 600 | partly — disposition-prone holders sell winners/hold losers, a behavioural regularity, not a mandate | partly — S&P 600 is index-covered and institutionally traded; below it, less so | DOUBTFUL; **re-test candidate below the S&P 600 (Day 2–3)** |
| 16 | vol_regime / vol_vxn_vix_h21_spy_ief (Dormant, 0.23) | implied-vol dislocation timing SPY/IEF | no | no | NOT |
| 17 | quality_cbop / cbop_ls_h63 (Active, 0.46, definite_negative) | Ball et al. cash-based operating profitability, S&P 500 | no | no | NOT |
| 18 | lazy_prices / lazy_jaccard_full_h126_ivol (Active, 0.60, underpowered) | Cohen-Malloy-Nguyen 10-K text change | no — inattention, voluntary | no — large-cap NLP is now industrial | NOT |
| 19 | short_interest / si_ratio_hedged_h21 (Active, 0.45, definite_negative) | low short interest → positive abnormal return | no established forced counterparty | no | NOT |
| 20 | crypto / xc_btcbeta_l180_h180 (Active, 0.94, underpowered) | Frazzini-Pedersen betting-against-beta in crypto | partly — leverage-CONSTRAINED investors overpay for beta (a constraint, not a forced trade) | partly — mandate-constrained institutions cannot hold most of this universe, which is a real F5 argument | DOUBTFUL |

### B.1 Count

| verdict | members |
|---|---|
| ADMISSIBLE (both criteria) | **0** |
| DOUBTFUL | 4 — dividend_payment_pressure, rebalancing_pressure, small_cap_disposition, crypto BAB |
| NOT | 16 |

Under criterion (i) alone (a genuinely forced counterparty), exactly two members qualify —
dividend_payment_pressure and rebalancing_pressure — and both fail (ii) for the same reason: the
forced flow lands in SPY/IEF, the cheapest instruments in the world for a large fund to trade.

### B.2 What this means for Step 0

1. **The existing 20 do not seed the BOOK under the new criterion.** If the five principles are
   adopted, the BOOK's first members would have to come from Day 2–3's corner, not from what is
   parked today. (Under the OLD rules — statistical close, no mechanism requirement — all 20 remain
   valid Dormant/Active members; nothing here removes them, rule 6 and the Dormant rules apply.)
2. **The corner is the only place the criterion can be satisfied with free data**: (ii) fails for every
   S&P 500/SPY/ETF/G10 member by construction. Day 2–3's plan (micro-cap panel with delisted names;
   re-ask the forced-loser mechanisms there — pead_ear, small_cap_disposition, fund-flow fire sales,
   tax-loss selling, index deletions of tiny names) is the right test, and the census makes it the
   only test.
3. **Correlation is not the binding constraint; edge existence is.** Mean ρ 0.018 says diversification
   works; 0 admissible members says there is nothing yet to diversify.
4. Honest expectation for Day 6, restated: the most likely outcome is 0–2 admissible members. Every
   Sharpe quoted above is in-sample and would need the ~3-year wait to mean anything even if admitted.

## C. Verification trail

- ρ script output re-derived independently for three pairs (§A.1), equal to the last digit.
- Member list = manifest entries (16, asserted in the script) + the four pattern ids imported from the
  registration modules themselves (not typed by hand).
- Classification sources: each family's module docstring (citation and mechanism statement), read
  2026-09-12; the two live definite_negative / two underpowered verdicts from the four scorecards.
- Not verified: whether the 09-05 series would change materially on the repaired store (disclosed §A).
