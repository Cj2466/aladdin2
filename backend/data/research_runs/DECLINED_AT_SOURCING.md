# DECLINED_AT_SOURCING ledger

Every family whose claimed effect fails `app.services.research_lab.
sourcing_power_check.sourcing_power_check`'s pre-build power pre-check (power
at the most conservative declared fraction of the claim, at n_local, below
`dsr_power.POWER_FLOOR` = 0.80) is recorded here BEFORE the family is built.
CLAUDE.md section 4 requires this check going forward; see that file for the
rule text.

Fields: family key, the inputs the check was run with, the resulting power at
the deciding tier, and whether the entry is retrospective (the family was
already built before this module existed) or prospective (checked before any
build).

---

## 1. `letf_rebalancing_eod` -- RETROSPECTIVE

This family was built and DECLINED on 2026-09-11 (module-level mechanism gate
failure, per its scorecard); this pre-check module (`sourcing_power_check.py`)
did not exist until this task. It is entered here to show what the check
would have said, using the family's OWN pre-registered power block
(`data/research_runs/letf_rebalancing_2026-09-11/power_block.json`), which had
already done this exact calculation by hand before any strategy return was
computed (POWER_BLOCK.md, PREREGISTRATION section 4.3).

- Inputs: `claimed_sharpe_annualized=0.41468259575966804` (the 50%-of-Tuzun
  arm -- Ivanov & Lenkey's own measured flow-offset strength, the deciding
  arm the pre-registration named in advance), `periods_per_year=
  248.75109762396693`, `years_of_data=2637/248.75109762396693=10.601008...`,
  `n_local=20`, `bar=0.95`, `offset_fractions=(1.0,)`.
- Ladder read live: `[20, 43, 397, 1131]`.
- `sigma_sr_annualized` (this module's formula, `sqrt(periods_per_year /
  n_observations)`): `0.30713367617589954` -- IDENTICAL to the family's own
  declared value, because both use the same precedent formula.
- **power at n_local = 20: 0.014014885044634329** -- an EXACT bit-for-bit
  match to the family's own recorded `power_at_claimed_sharpe` for this arm
  (power_block.json, `arms.half_tuzun.sigma_sr_declared__bar_0.95`).
- Verdict: `DECLINE_AT_SOURCING` (0.014 << 0.80).
- Independently re-run via the CLI for this ledger:
  `python data/research_runs/sourcing_power_check.py --claimed-sharpe
  0.41468259575966804 --periods-per-year 248.75109762396693 --years-of-data
  10.601008872025316 --n-local 20 --bar 0.95 --offset-fractions 1.0`

## 2. `intraday_momentum_spy` -- RETROSPECTIVE

Built and DECLINED on 2026-09-09 for a different reason (the paper's r1
predictor has the wrong sign out of sample -- see project memory
`project_intraday_momentum_spy_2026-09-09.md`), so this check's verdict does
not change any outcome. Entered here because the task asked for the retro
check to be run and recorded.

- Inputs: `claimed_sharpe_annualized=1.08` (Gao, Han, Li & Zhou's own claim,
  as recorded in the family's `run_output.json` `power["0.95"].
  claimed_sharpe_annualized`), `periods_per_year=252` (the family's own
  preservation-block convention), `years_of_data=2660/252=10.555555...`
  (`sample.n_trading_days` from `run_output.json`), `n_local=8`, `bar=0.95`,
  `offset_fractions=(1.0, 0.5)`.
- Ladder read live TODAY: `[8, 43, 397, 1131]`. The family's OWN
  `run_output.json` (written 2026-09-09) recorded `[8, 37, 362, 1031]` --
  the pooled rungs (37/362/1031 -> 43/397/1131) moved between then and now.
  This module always reads the current ladder, so this entry uses the
  current one; it is not a discrepancy in this module.
- `sigma_sr_annualized` (this module's pre-build formula): `0.30779350562554625`.
  **This is NOT the family's realized sigma_SR** (`0.5740485047348345`,
  `RUN_REPORT.txt` line 212, computed AFTER the 8 specs were built and
  scored) -- sourcing time has no realized moments to use, so this module's
  proxy and the family's post-hoc realized value are expected to differ, and
  do (documented in `tests/test_sourcing_power_check.py`'s intraday
  regression test).
- Power at n_local=8: 0.6564 at fraction 1.0 (claimed 1.08), 0.0884 at
  fraction 0.5 (claimed 0.54). For comparison, the family's own realized-
  sigma_SR run reported power 0.1951 at bar 0.95 for the full claim
  (`run_output.json` `power["0.95"].power_at_claimed_sharpe`) -- a different
  number from this module's 0.6564 at the same fraction, precisely because
  the sigma_SR inputs differ as described above.
- **Deciding tier: smallest fraction (0.5) at n_local (8) = 0.08841180215148192.**
- Verdict: `DECLINE_AT_SOURCING` (0.0884 << 0.80).
- Independently re-run via the CLI for this ledger:
  `python data/research_runs/sourcing_power_check.py --claimed-sharpe 1.08
  --periods-per-year 252 --years-of-data 10.555555555555555 --n-local 8
  --bar 0.95 --offset-fractions 1.0 0.5`

## 3. crypto perpetual-futures basis (He, Manela, Ross & von Wachter, arXiv:2212.06888v6) -- PROSPECTIVE

Checked 2026-09-11 by the orchestrator BEFORE any build, as the rule requires; the first
prospective entry. Full record: `data/research_runs/perp_basis_sourcing_2026-09-11/`
(`FEASIBILITY_AND_SOURCING_2026-09-11.md`, `sourcing_power_perp_basis.py`, JSON output).

- Claimed effects: the paper's own Table 6 High-tier ("typically an individual trader", MAKER
  fees) annualized Sharpe ratios BTC 1.80 / ETH 2.55 / BNB 4.84 / DOGE 3.58 / ADA 2.68, used as-is
  (the paper's Lucca-Moench annualization equals the calendar-time Sharpe with zeros when flat --
  derivation in the memo). Conservative declared claim: the paper's own Table 7 per-year Sharpe
  for 2022-2023, the regime the authors call a structural break (BTC 0.69, ETH 0.98, BNB 0.74,
  DOGE 0.76, ADA 0.88).
- Inputs: `periods_per_year=365`, `n_local=16` (declared), `bar=0.95`, `sigma_SR=sqrt(365/n)`,
  windows 7.0 y (2019-09 -> 2026-09) and 2.5 y out-of-sample only (2024-03 -> 2026-09).
- Power at the conservative claim, n_local: 7.0 y -> BTC 0.052, ETH 0.200, BNB 0.070, DOGE 0.076,
  ADA 0.132; 2.5 y OOS -> 0.009-0.029. Power at the full in-sample claim on the OOS window alone:
  BTC 0.273, ETH 0.718, ADA 0.782 (BNB/DOGE > 0.95).
- Verdict: **DECLINE_AT_SOURCING** as a signal test. A build could only replicate the paper's
  published in-sample years; the edge itself (post-break) is not certifiable at this project's bar.
- Reopen condition: a descriptive measurement of the hourly deviation series showing the
  post-2024 opportunity is back at a magnitude whose implied Sharpe clears the pre-check.

### Entry 3 — CORRECTION (appended 2026-09-11, after the Fable adversarial review)

The "conservative claim" numbers in entry 3 were Table 8 (long-spot-only), mislabeled as
Table 7; see `perp_basis_sourcing_2026-09-11/FEASIBILITY_AND_SOURCING_2026-09-11.md`
CORRECTION 01 and `ADVERSARIAL_REVIEW_2026-09-11.md`. Corrected Table 7 2022–23 mean Sharpe:
BTC 1.01, ETH 1.46, BNB 2.90, DOGE 1.17, ADA 1.73. Corrected power at that claim — 7.0 y:
0.219 / 0.666 / 1.000 / 0.363 / 0.867, pool 0.936; 2.5 y out-of-sample only: 0.032 / 0.128 /
0.868 / 0.055 / 0.235, pool 0.315. **Verdict unchanged: DECLINE_AT_SOURCING**, decided on the
out-of-sample window (only BNB clears; the pool does not) and on Table 7's implied 2–10 trades
per year per coin. The reopen condition stands.

---

## Entries 4-14 — candidate sourcing, 2026-09-11 (all PROSPECTIVE)

Full record: `data/research_runs/candidate_sourcing_2026-09-11/`
(`CANDIDATE_SOURCING_2026-09-11.md`, `candidates_ranked.csv`, `power_checks/`,
`COULD_NOT_VERIFY.md`, `sources/`). Eleven candidates were sourced in the two grounds the task
allowed — the US micro/small-cap corner and high-bet-count crypto — and **none is
PROCEED-eligible**. Nothing was built; no `app/` file was touched.

**Shared inputs for entries 4-10** (Ground A): `periods_per_year=252`,
`years_of_data=10.683093771389458` (= (2026-09-10 − 2016-01-04)/365.25, Alpaca's measured daily-bar
history, the only free source this project holds that covers delisted microcaps — see
`alpaca_delisted_coverage_2026-09-11/`), `n_local=8`, `bar=0.95`,
`offset_fractions=(1.0, 0.5)`. Ladder read live: `[8, 43, 397, 1131]`;
`sigma_SR_annualized = 0.305959`.

**What the 0.5 fraction stands for**: post-publication decay, from McLean & Pontiff (JF 2016),
"Portfolio returns are 26% lower out-of-sample and 58% lower post-publication" — a 58% decline
leaves a multiplier of 0.42, so 0.5 is *more lenient* than the sourced decay. It is more lenient
still against Chen & Velikov (FEDS 2020-039), whose empirical Bayes estimate of the cross-anomaly
distribution of **true** annualized net Sharpe ratios in post-publication post-2005 data is mean
**0.11**, s.d. **0.20** (Table 4 Panel A), and zero dispersion under value-weighting (Panel B).

**Claimed Sharpe derivation for entries 4-10** (my calculation, not the source's): Novy-Marx &
Velikov (NBER WP 20721) Table 13 reports monthly net returns and t-statistics by size bin; for a
mean-return t-statistic, `SR_annual = t / sqrt(years)`, with years = 49.5 (07/1963-12/2012).
NMV report no Sharpe ratios themselves. Sensitivity at 50.5 years is ~1% and changes no verdict.

| # | family key | claimed NET Sharpe | source row | power @1.0, N=8 | power @0.5, N=8 | verdict |
|---|---|---|---|---|---|---|
| 4 | `microcap_pead_sue` | 0.9324 (t=6.56) | NMV T13 Panel B, PEAD (SUE), Micro, net +1.10%/mo | 0.4768 | **0.0569** | DECLINE_AT_SOURCING |
| 5 | `microcap_valmomprof` | 0.8727 (t=6.14) | NMV T13 Panel B, ValMomProf, Micro, net +1.27%/mo | 0.4001 | 0.0466 | DECLINE_AT_SOURCING |
| 6 | `microcap_roe` | 0.6751 (t=4.75) | NMV T13 Panel B, Return-on-book-equity, Micro, net +1.24%/mo | 0.1844 | 0.0227 | DECLINE_AT_SOURCING |
| 7 | `microcap_net_issuance` | 0.5159 (t=3.63) | NMV T13 Panel B, Net Issuance, Micro, net +0.74%/mo | 0.0780 | 0.0118 | DECLINE_AT_SOURCING |
| 8 | `smallcap_hf_combo` | 0.4832 (t=3.40) | NMV T13 Panel C, High-frequency Combo, **Small** (Micro is net −0.66%/mo, t=−5.12) | 0.0635 | 0.0103 | DECLINE_AT_SOURCING |
| 9 | `largecap_industry_rel_reversal_lowvol` | 0.3880 (t=2.73) | NMV T13 Panel C, Industry Relative Reversals (Low Vol), **Large** (Micro is net −0.86%/mo, t=−5.36) | 0.0331 | 0.0067 | DECLINE_AT_SOURCING |

Each has its CLI output committed at
`candidate_sourcing_2026-09-11/power_checks/<key>.{txt,json}`. The invocation form:

```
python data/research_runs/sourcing_power_check.py \
  --claimed-sharpe 0.9324 --periods-per-year 252 --years-of-data 10.683093771389458 \
  --n-local 8 --offset-fractions 1.0 0.5
```

### 10. `microcap_short_run_reversal_liqprov` — PROSPECTIVE, declined on ECONOMICS, not power

The only candidate in this task whose **power gate passes**, recorded separately because the two
gates disagree and that distinction is the informative part.

- Source: Nagel, "Evaporating Liquidity" (NBER WP 17653; RFS 25(7), 2012 — I read the working
  paper). Table 1, Jan 1998 – Dec 2010: individual-stock reversal annualized Sharpe **8.44**
  (transaction prices) / **4.50** (quote midpoints), raw; 9.58 / 4.91 market-hedged. Section 3.4:
  "the lowest 'quality' stocks (small, illiquid, high volatility) generally offer the highest
  reversal strategy returns."
- Power at Nagel's **4.50**: `PROCEED`, power 1.0000 at both fractions
  (`power_checks/microcap_short_run_reversal_liqprov_GROSS.{txt,json}`). **That file is labelled
  `_GROSS` because 4.50 is gross of all trading costs and must never be cited as a net claim** —
  the CLI's `--claimed-sharpe` contract is "net of this project's cost model".
- The sourced NET claim is **negative**: NMV Table 13 Panel C, Short-run Reversals, net of
  effective spreads — Micro **−1.90%/mo (t=−7.86)**, Small −0.84% (t=−3.97), Large −0.51%
  (t=−2.54). The strategy's return *is* the spread; a taker pays it twice. Nagel says the same in
  his own words ("After accounting for these fixed costs, Sharpe ratios would likely be much less
  extreme").
- Independent corroboration at a different horizon and asset class: Kitron & Wengrowicz
  (arXiv:2608.21888v1) measure 15-minute directional reversal across 183 Binance pairs and 187 US
  stocks/ETFs and report "the gross edge peaks near 1.3 bp per trade against a 5 bp cheapest
  round-trip cost" — detectable, not capturable — and find the equity side already arbitraged
  (2.7% of US names significant vs 90% of crypto pairs).
- **Verdict: DECLINE_AT_SOURCING on economics.** No `--claimed-sharpe` can represent a negative
  net claim, so no power run decides this one.
- **Reopen condition**: a direct measurement of what a patient limit-order (maker) participant
  actually pays in microcaps at a $100k-$1M book — the unmeasured quantity behind hunting-ground
  hypothesis H3. Nobody I could source has measured it (see `COULD_NOT_VERIFY.md` §B.5).

### 11-14. Ground B — four crypto candidates, none runnable through the pre-check

| # | family key | why it cannot be pre-checked | verdict |
|---|---|---|---|
| 11 | `crypto_short_horizon_sign_reversal` | Kitron & Wengrowicz (arXiv:2608.21888v1) report AUC gaps and bp-per-trade, no Sharpe and no return volatility; and their own net-of-cost edge is **1.3 − 5 = −3.7 bp per trade**. A negative net claim has no admissible `--claimed-sharpe`. Bet count ≈ 183 pairs × 96 fifteen-minute bars/day × 365 ≈ **6.4m/yr**, the highest this project has sourced — and it does not help. | DECLINE_AT_SOURCING, on the source's own net-of-cost statement |
| 12 | `crypto_exchange_listing_drift` | Ante (BRL WP No. 3): 327 listings of 180 coins across 22 exchanges, AAR +5.7% on the listing day, CAAR +9.2% over (−3,+3) — but abnormal returns only, no Sharpe. Bet count is order **10²/yr pooled across every exchange**. The day-0 return is not available to someone who learns of the listing from the announcement (the paper reads pre-event drift as informed trading), and the Binance post-listing 3-day CAAR is negative. | DECLINE_AT_SOURCING, on bet count + no sourced tradable drift |
| 13 | `crypto_open_interest_positioning` | **No primary source found.** Searches returned exchange blogs and vendor guides only. The free data *does* exist and is verified: `data.binance.vision` `data/futures/um/daily/metrics/` from **2020-09-01** (6.027 years), columns `sum_open_interest`, `sum_open_interest_value`, the top-trader and overall long/short ratios, and `sum_taker_long_short_vol_ratio`. At 6.027 years the admissibility threshold is a claimed net Sharpe of **3.219** at n_local=8. | DECLINE_AT_SOURCING, for want of a source-based claim |
| 14 | `crypto_liquidation_cascade` | No primary source, **and no free historical data**: the `data/futures/um/daily/` prefix listing publishes aggTrades, bookDepth, bookTicker, indexPriceKlines, klines, markPriceKlines, metrics, premiumIndexKlines, trades — and no liquidation dataset; a direct `liquidationSnapshot` fetch returns **HTTP 404** (probe committed at `candidate_sourcing_2026-09-11/sources/binance_vision_probe_2026-09-11.txt`). Verified for Binance only. | DECLINE_AT_SOURCING; new paid-data gap logged provisionally as **P8**, not acted on |

### The general finding these fourteen entries share

`sigma_SR_annualized = sqrt(periods_per_year / n_observations) = sqrt(1 / years_of_data)`, so
sampling frequency and breadth cancel out of the pre-check entirely and only **calendar years**,
**n_local** and the **claimed net Sharpe** move it. The minimum source-claimed net annualized
Sharpe that returns PROCEED on this project's actual data windows
(`candidate_sourcing_2026-09-11/power_checks/ADMISSIBILITY_THRESHOLDS.txt`):

| window | years | n_local 5 | n_local 8 | n_local 16 |
|---|---|---|---|---|
| US equity (Alpaca 2016-01-04 → 2026-09-10) | 10.683 | 2.253 | **2.416** | 2.626 |
| Crypto spot (Binance 2017-08 → 2026-09-10) | 9.112 | 2.440 | 2.617 | 2.843 |
| Crypto futures OI/metrics (2020-09-01 → 2026-09-10) | 6.027 | 3.001 | 3.219 | 3.498 |

The best NET microcap claim in the literature is 0.93 — a factor of 2.6 short. Chen & Velikov put
the modern-era population mean at 0.11. **Sourcing candidates from the published cross-sectional
anomaly literature cannot produce a PROCEED under this gate on these windows**, which is a
statement about the search space, not about any one candidate.

### 15–17. Step 0 micro-cap corner (2026-09-12, orchestrator Fable; sourcing by an Opus agent, quotations re-verified against the extracted sources) — checked against the Step 0 admission rule R1–R6 (`micro_cap_corner_2026-09-12/STEP0_ADMISSION_RULE_2026-09-12.md`, declared before these results)

| # | family key | source and claim | rule that fails | verdict |
|---|---|---|---|---|
| 15 | `microcap_delisting_forced_exit` | Macey, O'Hara & Pompilio (2004 WP, fn. 45): "SEC rules preclude most institutions from holding unlisted shares, thus forcing owners to move out of these shares"; average close $0.95 on the last NYSE day vs $0.48 on the first Pink Sheet day; the authors themselves: "it is implausible that returns remain positive when overall trading costs are properly included" (median first-day spread 25%). R1 YES, R2 YES (the exclusion is legal, not merely economic). | **R6 (data): the whole trade is on post-delisting OTC bars. Measured 2026-09-12: Alpaca's free tier returns HTTP 403 for `feed=otc`; `feed=sip` returns 0 bars after each of 12 sampled names' last listed bar.** No net Sharpe derivable from the paper (R3 unmeasurable). | DECLINE_AT_SOURCING on R6; paid gap logged as P9 (Alpaca OTC feed) |
| 16 | `sparse_ownership_firesale_count` (Coval-Stafford Eq. 4 unweighted count on the sparse-ownership listed universe measured today: 1,070–1,468 listed names/quarter with 5–47 fund owners, `micro_cap_corner_2026-09-12/breadth_universe_intersection.json`) | Coval & Stafford (JFE 2007; 2005 WP read 2026-09-08), Table 5.b at \|flow\| > 10%: 1.68%/mo t = 2.22 to 2.64%/mo t = 3.50, sample 1980–2004 (25 y) → GROSS Sharpe t/√25 = **0.44 to 0.70 (my calculation)**; the paper reports no net figure; N-PORT gives 2019q4 → 2026q2 = 6.8 y. R1 YES (redemption-forced sales — with Wardlaw JF 2020's measurement critique unresolved: abstract only, SSRN 403, Wiley gated; the count measure contains no realized price so the critique may not bite, but that is my reasoning, not the paper's). R2 YES on breadth (the corner the 2026-09-08 test could not reach). | **R3: at the conservative fraction 0.5 the claim is 0.22 (lower bound) to 0.35 (upper bound) GROSS; the rule requires ≥ 0.30 NET.** Fails at the paper's lower bound and on any cost haircut at the upper bound (median daily dollar volume of the delisted sample: $137k). R5 would pass trivially (M = 0). | DECLINE_AT_SOURCING on R3 (conservative reading); the ONLY corner candidate that is otherwise buildable on free data — recorded so the owner can waive R3 knowingly |
| 17 | `russell_reconstitution_microcap` | Chang, Hong & Liskovich (NBER w19290): at the Russell 3000 cut-off (the micro-cap boundary) addition +3.6% (t = 1.45), deletion +3.3% (t = 1.25) — "insignificant"; the significant 5% effect is at the 1000 cut-off in $1bn+ names. Appel-Gormley-Keim: 32% of near-cut-off names misassigned even with CRSP; Russell's assignment rule is proprietary; no free constituent history. | R2 (the effect lives in large caps), R3 (insignificant in the corner), R6 (no free Russell membership) | DECLINE_AT_SOURCING |

Also re-declined without a new entry: `microcap_tax_loss_selling` (the project's own S&P 600 June placebo +0.53 beat the December spec +0.42–0.50, Dormant POPULATE_REPORT 2026-09-09); `spac_trust_redemption_floor` (entry reviewed 2026-09-11, ~40 bets/yr); `cef_openending_liquidation` (no primary source found).

**What the corner measurement established, independent of these verdicts:** the sparse-ownership listed universe EXISTS on free data (N-PORT breadth × SEC fails-to-deliver CUSIP map × Alpaca incl. 2,100 delisted plain tickers), which the 2026-09-08 fire-sale test lacked. It is the first free universe in this project where R2 holds. Its use is gated by R3, i.e. by the size of the forced-flow claims themselves.
