# Candidate sourcing — Ground A (US micro/small-cap corner) and Ground B (high-bet-count crypto)
**Date**: 2026-09-11 · **Type**: sourcing-stage review. Nothing here is a build, a
pre-registration, a DSR result or a registration. No `app/` file was touched, no DB row was
written, and the full backend test suite was **not** run — nothing under `app/` changed, so there
is nothing for it to re-verify. Deliverables are documents, power-check outputs and source
extracts only.

**The one rule in force**: every factual or numerical claim below is either (a) taken from a
document listed in `sources/SOURCES.md` that I fetched and read myself (URL, fetch date, SHA-256,
and exactly what I read are recorded there), or (b) explicitly labelled **T4
(RECALLED-NOT-VERIFIED)**, **COULD-NOT-ACCESS** or **H (hypothesis)**. Arithmetic I did myself is
labelled "my calculation" every time.

**Sources read**: 9 (`sources/SOURCES.md`). Attempted and not used: 2 (`COULD_NOT_VERIFY.md`).

---

## 0. The short answer

**No candidate in either ground is PROCEED-eligible.** That is not a failure to look hard enough;
it is one arithmetic fact plus one measured fact, and the two together are the useful output of
this task.

**The arithmetic fact.** `sourcing_power_check`'s standard error is
`sigma_SR_annualized = sqrt(periods_per_year / n_observations)`, and since
`n_observations = periods_per_year x years_of_data`, that is exactly `sqrt(1 / years_of_data)`.
Sampling frequency cancels; only **calendar years**, **grid size** and the **claimed Sharpe**
move the verdict. With the data windows this project actually holds, the minimum source-claimed
NET annualized Sharpe that clears the 0.80 power floor is (my computation, committed at
`power_checks/ADMISSIBILITY_THRESHOLDS.txt`):

| data window | years | n_local=5 | n_local=8 | n_local=16 |
|---|---|---|---|---|
| US equity (Alpaca daily, 2016-01-04 → 2026-09-10) | 10.683 | **2.253** | **2.416** | **2.626** |
| Crypto spot (Binance klines, 2017-08 → 2026-09-10) | 9.112 | 2.440 | 2.617 | 2.843 |
| Crypto futures OI/metrics (2020-09-01 → 2026-09-10) | 6.027 | 3.001 | 3.219 | 3.498 |

(at declared fractions {1.0, 0.5}; halve for the fraction-1.0-only column in that file.)

**The measured fact.** Nothing in the published cross-sectional anomaly literature claims a NET
Sharpe anywhere near 2.4 once costs and post-publication decay are applied. Chen & Velikov's
empirical-Bayes estimate of the cross-anomaly distribution of **true** annualized net Sharpe
ratios, in post-publication post-2005 data with cost-optimized equal-weighted implementations, is
mean **0.11**, standard deviation **0.20** (their Table 4 Panel A, at nu_SR = 100) — and with
value-weighting the estimated dispersion is **zero**, i.e. their estimator cannot distinguish the
anomalies at all (Panel B, sigma-hat_SR = 0.00, mu-hat_SR = 0.04). The best NET microcap number I
could source anywhere — Novy-Marx & Velikov's Table 13 microcap PEAD(SUE) — implies an annualized
Sharpe of **0.93** over fifty years of data (my calculation from their t-statistic), and that is
a full-sample number with no post-publication decay applied at all. It is a factor of ~2.6 short
of what 10.7 years can certify.

**What this means for the project, stated plainly.** The binding constraint is not mechanism
quality, plausibility, or bet count. It is `claimed_net_Sharpe x sqrt(years_of_data)`. Ground A —
the microcap corner — fails on the *Sharpe* term by roughly a factor of 2.5, and no amount of
breadth, rebalancing frequency or cleverness moves it, because breadth and frequency do not enter
this arithmetic at all. This is the same conclusion the perp-basis decline reached by a different
route, and it generalises: **sourcing candidates from the published anomaly literature cannot
produce a PROCEED under this project's current gate, on this project's current data windows.**
Section 5 says what would.

---

## 1. What "fraction 0.5" stands for

Every power check below is run at `--offset-fractions 1.0 0.5`. Under CLAUDE.md section 4 the
verdict is decided at the **most conservative declared fraction**, i.e. 0.5.

**0.5 is post-publication decay, sourced from McLean & Pontiff (2016)**: "Portfolio returns are
26% lower out-of-sample and 58% lower post-publication" (their abstract, read). A 58% decline
leaves 42% of the in-sample return, i.e. a multiplier of **0.42**. I use **0.5**, which is
therefore *more lenient* than the sourced decay, not less. I also note — and this matters for
how the declines below should be read — that **0.5 is more lenient still** relative to Chen &
Velikov's direct estimate of the modern net level (mean true net annualized Sharpe 0.11 across
anomalies). So the declines are not artifacts of a harsh fraction; a fair fraction would decline
these candidates harder.

For the two candidates whose source claim is **already** a modern/out-of-sample number rather
than an in-sample one, applying 0.5 double-counts decay. I flag that where it applies, and report
the fraction-1.0 power alongside so the reader can see what the verdict would be without it.
In no case does that change the verdict.

---

## 2. Ground A — US micro/small-cap corner

### 2.1 The evidence base, and why the microcap corner is a real corner

- **Microcaps are the corner**: Hou, Xue & Zhang report Fama-French's (2008) figures that
  microcaps are only **3% of total NYSE-Amex-NASDAQ market capitalization but 60% of the number of
  stocks**, and define them as below the 20th percentile of NYSE market equity. HXZ's own stated
  reason for their replication failures is cost: *"because of high costs in trading these stocks,
  anomalies in microcaps are more apparent than real."* **[T2, source #5]**
- **The corner survives costs — but only at low and mid turnover.** Novy-Marx & Velikov's Table
  13 sorts value-weighted decile long/short strategies into micro / small / large size bins
  (breakpoints: 20th and 50th percentile of NYSE) and reports gross AND net returns with
  t-statistics. Their own reading of it: for **low-turnover** strategies "the transactions costs
  seem to be immaterial for the low-turnover anomalies, even for the micro caps"; for
  **mid-turnover**, microcaps keep most of their advantage (ValMomProf gross 1.67% / net 1.27%
  per month in micro); for **high-turnover**, "the extremely high gross returns across the
  microcaps turn severely negative once we account for transactions costs." **[T2, source #3]**
- **Costs do not extrapolate.** NMV's Figure 1 and Table 1 show the cost/size relation is convex,
  and their Appendix A.2 "highlights the danger of extrapolating transaction costs estimated on
  large, relatively liquid stocks to small stocks using a linear model." **[T2, source #3]** Any
  microcap build here must estimate spreads on the microcap names themselves, not scale the S&P
  500 assumption. (The project already has `spread_estimator.py` and the `bidask` package for
  this; `cross_sectional_small_mid_cap.py` already measured median estimated spread 33.6 bps on
  the S&P 600 vs 22.6 bps on the S&P 500.)
- **Post-publication, the level effect survives but decay is real**: McLean & Pontiff's 58%
  post-publication decline, with the costly-arbitrage interaction leaving harder-to-arbitrage
  portfolios retaining more. **[T1, source #4]**
- **But the modern net level is tiny**: Chen & Velikov, as quoted in §0. **[T2, source #1]**

### 2.2 Cost evidence for a $100k–$1M book — what I could and could not source

The brief asked for the best available evidence on realistic costs for a $100k–$1M microcap book
so the pre-check could use a NET claimed Sharpe. What exists and what I used:

- **Used**: NMV's net-of-effective-spread returns *by size bin* (Table 13). This is the only
  source I found that reports microcap net returns separately, computed with Hasbrouck-style
  effective spreads and the buy/hold-spread ("sS") mitigation. NMV state the measure "is
  nevertheless conservative, because it assumes market orders", i.e. it is a **taker** cost.
- **Used**: Chen & Velikov's modern-era net levels, which incorporate effective spreads,
  post-publication effects and the post-2005 technology era, and which explicitly **omit price
  impact** — so they too are an upper bound on net profitability.
- **Could not source**: any measurement of microcap trading costs at a $100k–$1M book size, or
  for a patient limit-order (maker) participant. Both NMV and Chen & Velikov measure a
  spread-crossing cost that does not depend on book size. This is exactly hypothesis **H3** in the
  hunting-ground review, and it remains unmeasured. I did **not** fetch Frazzini, Israel &
  Moskowitz "Trading Costs" or a Corwin-Schultz paper — see `COULD_NOT_VERIFY.md`; nothing below
  depends on them.

**Consequence**: every net claimed Sharpe in §2.4 is a **taker** cost number, which is the
conservative side for a decline and the correct side for this project's cost convention.

### 2.3 Novelty check against the 55 tried families

Every tried equity family runs on a large- or small-cap index universe, not the microcap corner.
Checked directly in the modules: `cross_sectional_pead.py` states *"this family's whole universe
is S&P 500 constituents"* and even notes in its own docstring that *"PEAD generally is
concentrated in small, illiquid, high-arbitrage-cost names"* — i.e. the tried family excludes the
exact region the effect is claimed to live in. `cross_sectional_small_mid_cap.py` (the
`small_cap_*` family keys) re-runs existing signals on the **S&P 600 small-cap index**, which by
construction contains no microcaps. `cross_sectional_quality.py` runs on the point-in-time S&P
500 union universe.

So under the brief's rule ("a small-cap variant of a tried anomaly counts as tried unless the
paper's claim is specifically about the microcap corner AND the tried family excluded microcaps"),
the microcap variants below are **novel on both limbs**: NMV Table 13 is a microcap-specific
claim, and every tried family excluded microcaps. That novelty is genuine — and it does not save
any of them from the power gate.

### 2.4 The candidates, with arithmetic

**How the claimed Sharpe is derived (my calculation, stated once).** NMV report monthly net
returns and t-statistics over a sample the paper describes as 1963–2013, with the full-period
figure given elsewhere in the paper as 07/1963–12/2012 (**49.5 years**). For a mean-return
t-statistic on monthly returns, `t = SR_monthly x sqrt(n_months)`, so
`SR_annual = t x sqrt(12 / n_months) = t / sqrt(years)`. I use 49.5 years. Sensitivity: at 50.5
years every figure below falls by about 1% (e.g. PEAD(SUE) 0.9324 → 0.9231), which changes no
verdict. **NMV report no Sharpe ratios themselves; this conversion is mine.**

**Bets per year (my calculation).** All mid-turnover rows are **monthly** rebalances. A microcap
universe under Alpaca's 2016+ coverage is, order of magnitude, 1,000–2,500 names (not measured
here — see `COULD_NOT_VERIFY.md` §C.1); a decile long/short at 1,500 names holds ~300 names, so
name-level bets are `12 x 300 = 3,600/yr`, while **portfolio-level independent bets are 12/yr**.
The power gate sees the portfolio, not the names: this is precisely the H1 "count bets" point,
and it is why breadth cannot rescue any row below.

| # | candidate (proposed family key) | source row (NMV Table 13) | net return | t | claimed NET Sharpe (mine) | bets/yr (portfolio / name-level) | power @1.0, n_local=8 | power @0.5, n_local=8 | verdict |
|---|---|---|---|---|---|---|---|---|---|
| A1 | `microcap_pead_sue` | Panel B, PEAD (SUE), Micro | +1.10%/mo | 6.56 | **0.9324** | 12 / ~3,600 | 0.4768 | **0.0569** | DECLINE_AT_SOURCING |
| A2 | `microcap_valmomprof` | Panel B, ValMomProf, Micro | +1.27%/mo | 6.14 | 0.8727 | 12 / ~3,600 | 0.4001 | 0.0466 | DECLINE_AT_SOURCING |
| A3 | `microcap_roe` | Panel B, Return-on-book-equity, Micro | +1.24%/mo | 4.75 | 0.6751 | 12 / ~3,600 | 0.1844 | 0.0227 | DECLINE_AT_SOURCING |
| A4 | `microcap_net_issuance` | Panel B, Net Issuance, Micro | +0.74%/mo | 3.63 | 0.5159 | 12 / ~3,600 | 0.0780 | 0.0118 | DECLINE_AT_SOURCING |
| A5 | `smallcap_hf_combo` | Panel C, High-frequency Combo, Small | +0.35%/mo | 3.40 | 0.4832 | ~12 / high | 0.0635 | 0.0103 | DECLINE_AT_SOURCING |
| A6 | `largecap_industry_rel_reversal_lowvol` | Panel C, Industry Relative Reversals (Low Vol), Large | +0.31%/mo | 2.73 | 0.3880 | ~12 / high | 0.0331 | 0.0067 | DECLINE_AT_SOURCING |
| A7 | `microcap_short_run_reversal_liqprov` | see §2.5 — the one case where power passes and economics fails | **−1.90%/mo** | −7.86 | negative | ~250 / very high | (gross 4.50: 1.000) | (gross 4.50: 1.000) | DECLINE_AT_SOURCING, on economics |

A5 and A6 are included deliberately even though they sit **outside** the microcap corner: NMV's
Table 13 Panel C shows they are the **only two high-turnover strategies that survive costs at
all**, and they survive in the small- and large-cap bins while going severely negative in
microcaps. That is the direct empirical contradiction of the "high turnover in the microcap
corner" thesis, and it belongs in the record next to the thesis.

Each row's exact CLI invocation and full output is in `power_checks/<key>.txt` / `.json`. The
command form for every Ground A row (only `--claimed-sharpe` and the key differ):

```
python data/research_runs/sourcing_power_check.py \
  --claimed-sharpe 0.9324 --periods-per-year 252 --years-of-data 10.683093771389458 \
  --n-local 8 --offset-fractions 1.0 0.5
```

`--years-of-data 10.683093771389458` is `(2026-09-10 − 2016-01-04)/365.25`, i.e. Alpaca's measured
daily-bar history (`alpaca_delisted_coverage_2026-09-11/`) — the only free source this project
holds that covers delisted microcaps. A longer window is not available for free: the P2
delisted-securities gap on the paid-decisions list is exactly the constraint that pins these rows
at 10.68 years.

### 2.5 A7 in detail — the one candidate where the power gate passes

Short-horizon reversal read as paid liquidity provision (Nagel) is the most attractive-looking
microcap idea in the literature, and it is the one place where the two gates disagree, so it gets
its own treatment.

**The claim.** Nagel, *Evaporating Liquidity*, Jan 1998–Dec 2010, NYSE/Amex/Nasdaq stocks from
CRSP. Table 1, individual-stock reversal, market-hedged: annualized Sharpe **9.58** on
transaction-price returns and **4.91** on quote-midpoint returns (raw, unhedged: 8.44 and 4.50).
Nagel states the transaction-price/midpoint gap means "a substantial portion, although by far not
all, of the reversal strategy returns with transaction prices arise from the bid-ask bounce", so
the midpoint number is the honest one. Section 3.4 / Figure 4: "the lowest 'quality' stocks
(small, illiquid, high volatility) generally offer the highest reversal strategy returns" — a
microcap-concentration claim in the paper's own words. Bets/yr are very high (daily rebalance
across the CRSP cross-section). **[T2, source #2]**

**Why it still declines.** Nagel's own caveat: "Fixed costs for high-speed market access and
technological requirements for successful placement of orders that capture order flow probably
play an important role... After accounting for these fixed costs, Sharpe ratios would likely be
much less extreme." And the net number exists elsewhere: NMV Table 13 Panel C reports monthly
short-run reversal net of effective spreads as **−1.90%/month (t = −7.86)** in microcaps,
**−0.84% (t = −3.97)** in small caps and **−0.51% (t = −2.54)** in large caps. The strategy's
return *is* the spread; a taker pays it twice.

**The record**: `power_checks/microcap_short_run_reversal_liqprov_GROSS.{txt,json}` runs the CLI
at Nagel's 4.50 and returns **PROCEED** with power 1.000 at both fractions. That file is labelled
`_GROSS` because **4.50 is not a net claim and must never be cited as one**; the CLI's own
`--claimed-sharpe` contract says "net of this project's cost model", and the net claim sourced
from NMV is negative, which the CLI cannot represent. The decline is therefore recorded on
**economics**, not on power, and it is the only such case in this task.

**Independent corroboration from Ground B**: Kitron & Wengrowicz measure the same mechanism at
15-minute horizon in crypto and in US equities and reach the same conclusion by direct
measurement — "the gross edge peaks near 1.3 bp per trade against a 5 bp cheapest round-trip
cost: large enough to detect, too small to clear benchmark spot capture costs" — and find the
equity side is already arbitraged away (significant directional reversal in 2.7% of 187 US stocks
and ETFs vs 90% of 183 Binance pairs). **[T2, source #7]**

### 2.6 Data path for Ground A (what is held, what is not)

| need | held? | evidence |
|---|---|---|
| Microcap daily bars incl. delisted names, 2016→ | **YES** | `alpaca_delisted_coverage_2026-09-11/`: 23/23 testable lockup windows resolved (100%) vs yfinance 12/23; 54/56 full-history symbols. Caveat 1 there (symbol re-use is not handled by the vendor) is load-bearing for a microcap universe and would have to be solved per-name from the SEC submissions store. |
| Delisting dates | **YES** (indirect) | SEC submissions store (`edgar_submissions_store.py`), last filing per CIK. |
| Fundamentals for A2/A3/A4 (book equity, net income, share issuance) | **PARTLY** | `edgar_facts_store/` holds 163 CIKs — an S&P-500-scale roster, **not** a microcap roster. A microcap build would need a large ingestion run first (~1,000+ new CIKs). Not measured here. |
| Earnings announcement dates + SUE for A1 | **PARTLY** | `edgar_submissions_store` retains 8-K indexes for 503 tickers; the known unfixed defect (`cross_sectional_pead` has no successor-shell CIK resolution) would have to be fixed first, and the microcap roster ingested. |
| Pre-2016 microcap history | **NO** | P2 paid gap (Norgate Platinum/Diamond or equivalent). This is the single input that would move the power arithmetic; see §5. |

---

## 3. Ground B — crypto with high bet counts

### 3.1 Novelty baseline

The four tried crypto families are `crypto` (28 specs: Jegadeesh-Titman cross-sectional momentum,
Liu-Tsyvinski-Wu size/momentum, De Bondt-Thaler long-horizon reversal, low-volatility, and
betting-against-beta), `funding_carry` and `funding_carry_pit` (delta-neutral perpetual funding
harvest on Binance USDT-margined perps), and `ofi_crypto` (order-flow imbalance, explicitly
orthogonalized against lagged returns so as not to be short-term reversal). Plus the
already-declined perp-basis candidate (`DECLINED_AT_SOURCING.md` entry 3 and its correction).

Anything in the LTW / C-3 / C-4 factor family is **tried**. That rules out the most obvious
high-bet-count crypto cross-sections up front.

### 3.2 Anti-evidence that arrived while sourcing

Borri, Liu, Tsyvinski & Wu (three of whom wrote the LTW factor papers `cross_sectional_crypto`
cites) revisit their own cross-section on an updated sample: the long-short returns based on
**size and value are significantly negative** and only **momentum** is significantly positive, and
"most of the smart beta strategies from the canonical factor zoo in the equity market either do
not generate significant hedged long-short strategy returns or are subsumed by the C-4 factor
model." Their Fact 9 reports the cryptocurrency **carry** Sharpe as **6.45** over 2020–2025,
falling to **4.06** from 2024, and turning **negative in 2025**. **[T2, source #8]**

Read against this project's record, that is three things at once: (i) independent confirmation
that `funding_carry`'s decline and the perp-basis decline were not premature — the ground has kept
decaying since; (ii) a warning that the reopen condition recorded for the perp basis is now less
likely to be met, not more; and (iii) evidence that expanding the crypto cross-section beyond what
`cross_sectional_crypto` already tested is unlikely to find anything the C-4 model does not
subsume.

### 3.3 Candidates

| # | candidate | mechanism + the source's own numbers | tier | novelty vs the 4 tried | bets/yr (my arithmetic) | pre-check | verdict |
|---|---|---|---|---|---|---|---|
| B1 | `crypto_short_horizon_sign_reversal` | 15-minute directional mean reversion: 90% of 183 Binance pairs carry significant out-of-sample directional reversal in every focal coin-year since 2021, vs 2.7% of 187 US stocks/ETFs; class-mean AUC gap +0.031 as designed, +0.011 (95% CI [+0.008,+0.014]) under the most conservative accounting; "the gross edge peaks near 1.3 bp per trade against a 5 bp cheapest round-trip cost" | T2 | **NOVEL** (the tried reversal is De Bondt-Thaler long-horizon; `ofi_crypto` is explicitly orthogonalized away from reversal) | 183 pairs x 96 fifteen-minute bars/day x 365 ≈ **6.4 million** signal evaluations/yr — the highest bet count of anything this project has ever sourced | **cannot be run**: the paper reports no Sharpe and no return volatility, and its own net-of-cost edge is **1.3 − 5 = −3.7 bp per trade**, i.e. negative. A negative net claim has no admissible `--claimed-sharpe`. | **DECLINE_AT_SOURCING**, on the source's own net-of-cost statement |
| B2 | `crypto_exchange_listing_drift` | Exchange-listing event study, 327 listings of 180 cryptocurrencies across 22 exchanges (the paper's own market-capitalization analysis uses a 322-event subsample; 327 is the count for the return results I cite). Sample start date is not stated in the text I read; the paper is dated 2019-09-08, so all events precede it: average abnormal return **+5.7%** on the listing day and **+9.2%** over (−3,+3); "listings on only a few exchanges yield significant positive short-term abnormal returns of up to 25.5%... other exchanges show no significant effects at all or even significant negative returns" | T2 | NOVEL (no event-driven crypto family exists) | 327 events across the whole sample and all 22 exchanges; Binance contributes 44–45. Even pooling every exchange this is **order 10²/yr**, and the tradable leg is smaller still | **cannot be run**: the paper reports abnormal returns and t/z tests, no Sharpe and no strategy volatility. Also: the day-0 return is not available to a participant who learns of the listing from the announcement (the paper says listing information "is communicated by the exchange at the day or the day before the event", and reads the pre-event drift as informed trading), and the Binance post-listing 3-day CAAR in its Table is **negative** | **DECLINE_AT_SOURCING**, on bet count + no sourced tradable post-event drift |
| B3 | `crypto_open_interest_positioning` | Open-interest / long-short-ratio positioning as a directional predictor across perps | **H** | would be novel | n/a | **cannot be run**: I found **no primary source** reporting a tradable effect size with a sample period. Everything the searches returned was exchange-blog or vendor-marketing material (T3 at best), plus one SSRN case study of the single October-2025 cascade event. CLAUDE.md requires a source paper's claim to pre-check against; there is none | **DECLINE_AT_SOURCING**, for want of a source-based claim |
| B4 | `crypto_liquidation_cascade` | Forced-liquidation cascades as a reversal trigger | **H** | would be novel | n/a | **cannot be run**, and separately **the data does not exist for free**: `data.binance.vision`'s `data/futures/um/daily/` prefix publishes aggTrades, bookDepth, bookTicker, indexPriceKlines, klines, markPriceKlines, metrics, premiumIndexKlines and trades — and **no liquidation dataset**; a direct fetch of a `liquidationSnapshot` object returns **HTTP 404** (probe committed at `sources/binance_vision_probe_2026-09-11.txt`) | **DECLINE_AT_SOURCING**, no source and no free historical data |

### 3.4 Data path for Ground B (verified live today)

From the committed probe (`sources/binance_vision_probe_2026-09-11.txt`, **T1**, primary vendor):

- **Spot daily klines**: earliest BTCUSDT month is **2017-08** → 9.112 years to 2026-09-10. Free.
- **Futures `metrics`** (the OI dataset): earliest BTCUSDT file is **2020-09-01** → 6.027 years.
  Columns: `create_time, symbol, sum_open_interest, sum_open_interest_value,
  count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio, count_long_short_ratio,
  sum_taker_long_short_vol_ratio`. Free — this is a real, previously-unused free dataset and it is
  the correct data path for B3 if a source is ever found for it.
- **Liquidations**: **not published**. 404, as above. Any liquidation-cascade family would need a
  paid vendor (Coinglass/Amberdata class) — **logged as a new paid-data gap, not acted on**, per
  CLAUDE.md section 4's deferral rule. Provisional label **P8**; the owner's list lives at
  `data/research_runs/PENDING_PAID_DATA_DECISIONS.md`.

Note the 6.027-year OI window raises the admissibility threshold to a claimed net Sharpe of
**3.219** at n_local=8 — higher than any crypto effect in the literature I read except the carry
trade the project has already declined and whose own authors now report it negative in 2025.

---

## 4. Declined at sourcing — summary

All eleven candidates considered are declined. Seven were run through the CLI (A1–A6 plus A7's
gross-claim informational run); four (B1–B4) could not be run because no source-based net Sharpe
exists, and each of those is declined on a stated non-power ground instead. Every one is appended
as a PROSPECTIVE entry to `data/research_runs/DECLINED_AT_SOURCING.md` (entries 4–14).

**Nothing is PROCEED-eligible. There is no ranked PROCEED section because it would be empty, and
writing one anyway would be the manufactured positive this project exists to avoid.**

---

## 5. What would actually change the answer

These are recommendations to the owner, not decisions, and not one of them is a candidate.

1. **The years term is the only free lever left, and it is a paid decision.** At a claimed net
   Sharpe of 0.9324 (the best microcap number in the literature) the CLI prints
   `years_to_detect = 26.22` at n_local=8 and fraction 1.0, and **`n/a`** at fraction 0.5 — i.e.
   even the full, undecayed claim would need **26.2 years** of daily data to reach 0.80 power,
   against the 10.68 years Alpaca supplies, and the half-claim is not reachable at any length the
   inversion returns (`power_checks/microcap_pead_sue.txt`). Pre-2016 microcap history with
   delistings is the P2 gap on the paid-decisions list. This is the first time that decision has
   had a specific number attached to what it buys — and the number says that even buying history
   back to 2000 (~26 years total) would only just clear the *undecayed* claim at the most lenient
   rung of the ladder.
2. **Or the Sharpe term, which means abandoning the published-anomaly literature as a source.**
   Chen & Velikov's mean true net annualized Sharpe of 0.11 is a statement about the whole
   population of published predictors. Sourcing candidates from that population cannot clear a
   gate that needs ~2.4. This is hunting-ground hypothesis **H2** (enumerate frictions, not
   anomalies) restated as arithmetic rather than intuition.
3. **Or measure H3 directly instead of assuming it.** The one genuinely unmeasured quantity in
   Ground A is what a $100k patient limit-order participant actually pays in a microcap. That is
   not a signal family and does not need one: it needs the project's own fills, or at minimum a
   microcap spread study on the names Alpaca covers. If microcap maker costs are materially below
   the taker spreads NMV and Chen & Velikov model, the *net* claims above rise — and they would
   have to rise by a factor of ~2.6 to matter, which is a large enough gap to be worth stating in
   advance as the test's own falsification condition.
4. **The free Binance futures `metrics`/OI dataset (2020-09 →) is real and unused.** It is not a
   candidate today because no source supports a claim on it, but it is the cheapest new data this
   project could put to work if a source ever appears.

---

## 6. Honest limits of this task

- I read 9 sources. That is at the top of the brief's 6–10 band but it is still a small slice of
  either literature, and **absence of a PROCEED here is not proof that none exists**.
- Three of the nine are re-reads of extracts the hunting-ground review committed; I read them
  myself and the SHA-256s match, but I did not independently re-fetch them.
- The conversion from NMV's t-statistics to annualized Sharpe ratios is **mine**, not theirs, and
  rests on their sample being 49.5 years; the paper states "1963 through 2013" in one place and
  "07/1963 - 12/2012" in another. The 1% sensitivity is shown in §2.4.
- The microcap universe size used in the bets/yr arithmetic (1,000–2,500 names) is an
  order-of-magnitude figure I did **not** measure against Alpaca's actual coverage.
- No candidate here has had a control-non-degeneracy proof written, because none is proceeding to
  pre-registration. If any is ever revived, that proof is required before build under CLAUDE.md
  section 4.
