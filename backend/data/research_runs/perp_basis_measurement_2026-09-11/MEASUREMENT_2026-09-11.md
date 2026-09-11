# Crypto perp-basis deviation — descriptive measurement (2026-09-11)

**This is a descriptive data measurement, not a strategy test.** No Sharpe, no DSR,
no verdict, no registration, no DB write — per the sourcing decision in
`../perp_basis_sourcing_2026-09-11/FEASIBILITY_AND_SOURCING_2026-09-11.md`
("DECLINE_AT_SOURCING as a signal test") section 5's proposed follow-up: measure
whether the futures-spot deviation opportunity is still present after the
paper's 2024-03-11 sample end, without backtesting a strategy. Note: that
sourcing document's own text refers to a "CORRECTION 01" and an
`ADVERSARIAL_REVIEW_2026-09-11.md`; neither file exists in
`perp_basis_sourcing_2026-09-11/` at the time of this run (checked directly)
— proceeding on the sourcing document as written, flagged here rather than
silently assumed resolved.

Paper: He, Manela, Ross & von Wachter, "Fundamentals of Perpetual Futures"
(source text `../hunting_ground_review_2026-09-11/sources/
perpetual_futures_fundamentals.txt`; every line number below cites that file).

## 1. Definition implemented

Eq. (8), lines 935-937:

```
rho = kappa * (1 - exp(-(f - s))) - (r - r')
f = ln(perp close), s = ln(spot close), kappa = 1095
```

`r' = 0` per line 956 ("no interest is paid on spot crypto holdings"). This
script uses the EXACT form of Eq. (8), not the paper's own stated
approximation `rho ~= kappa*(f-s) - (r-r')` (line 937) — the exact form is
one line of extra code and removes an unnecessary approximation error, and
the paper itself notes the difference is negligible (footnote 8, line 940).

**r = 0 throughout.** This project does not hold the Aave USDT
supply/borrow-rate series the paper uses (lines 908-913, 962-965). The
extracted paper text gives no NUMERIC magnitude for that rate anywhere
outside Figure 8 (a plot, not a table) — checked directly, nothing found.
Disclosure per the task brief: **unquantified, single-digit %/yr order — a
GUESS at magnitude only**, not a number used anywhere in this script. Against
bounds of order +-180%/yr (High tier) to +-320%/yr (retail-taker, see below),
a single-digit r shifts rho by low single-digit percentage points — small
relative to bound width, but not zero, and every number below is explicitly
on the r=0 basis.

## 2. Symbols

Five paper coins (line 793-795): BTCUSDT, ETHUSDT, BNBUSDT, DOGEUSDT, ADAUSDT.

Plus the 20 largest OTHER Binance USDT-margined perps by trailing 30-day
(2026-07-30 .. 2026-08-28 inclusive) median DAILY quote_volume (dollar
turnover), computed from this repo's existing daily-kline cache
(`backend/data/binance_futures/klines_1d_*.csv`, fetched through 2026-08-29
by `BinanceFuturesProvider`, 73 symbols on file) — **not** a fresh fetch,
since that cache already covers the ranking window. Full ranked table (all
59 candidates measured, this repo does not hold every Binance perp so this
is a ranking within the 73-symbol cache, not the true universe-wide top 20 —
disclosed as a limitation):

| rank | symbol | 30d median daily quote_volume (USDT) |
|---|---|---|
| 1 | SOLUSDT | 1,048,044,580 |
| 2 | XRPUSDT | 397,167,548 |
| 3 | ZECUSDT | 387,828,035 |
| 4 | LINKUSDT | 115,642,500 |
| 5 | UNIUSDT | 91,087,604 |
| 6 | NEARUSDT | 83,907,684 |
| 7 | AVAXUSDT | 73,168,329 |
| 8 | AAVEUSDT | 63,421,286 |
| 9 | FILUSDT | 40,531,471 |
| 10 | BCHUSDT | 40,304,862 |
| 11 | TRXUSDT | 35,806,926 |
| 12 | LTCUSDT | 34,664,921 |
| 13 | XMRUSDT | 32,648,771 |
| 14 | XLMUSDT | 31,697,652 |
| 15 | DOTUSDT | 30,319,433 |
| 16 | CRVUSDT | 16,967,260 |
| 17 | HBARUSDT | 15,564,803 |
| 18 | ICPUSDT | 14,786,974 |
| 19 | ETCUSDT | 14,712,882 |
| 20 | ATOMUSDT | 13,927,145 |

(21st-25th, not used: DASHUSDT 10,653,988; ALGOUSDT 9,727,794; GALAUSDT
6,686,553; CHZUSDT 6,293,837; SANDUSDT 5,946,911. Full 59-symbol ranking
reproducible from `fetch_binance_hourly.py`'s ranking logic against the
existing daily cache.)

25 symbols total. Every one has both a Binance spot and Binance USDT perp
market — verified by the fetch itself completing without a permanent
"never listed" (-1121/-1122) answer on either market for any of the 25 (see
`alignment_report.csv`; a symbol that failed this would show 0 rows on one
side).

## 3. Bounds

**High tier** (Table 3, line 866), quoted directly: rho_l = -179.5%,
rho_u = +179.2%.

**Retail-taker bound**: same formula as Table 3's footnote (line 878):
`rho_l = kappa*log(1-C)`, `rho_u = kappa*log(1+C)`, C = round-trip % cost of
the long-spot/short-perp trade. The paper explicitly uses MAKER fees ("We
consider trading costs for makers instead of takers because institutions
typically trade maker orders", lines 847-848) — a retail participant hitting
market orders pays TAKER fees instead, which this measurement fetches live
rather than assumes:

- Spot taker (non-VIP/regular): **0.100%** — fetched 2026-09-11 via WebFetch
  from `https://www.binance.com/en/fee/trading`: "Spot Trading: 0.100% taker
  fee" for non-VIP users.
- USDS-M futures taker (Regular User / VIP 0): **0.050%** — fetched
  2026-09-11 via WebFetch from
  `https://www.binance.com/en/support/faq/detail/360033544231`: "a Regular
  User's maker fee is 0.02% and a Regular User's taker fee is 0.05%".

C = 2*(0.00100 + 0.00050) = 0.00300 (the "2x(spot+futures)" construction —
open leg pays spot+futures once, close leg pays spot+futures again — is the
same one that reproduces the paper's own High-tier bound EXACTLY from its
own per-side maker fees: `1095*ln(1+2*(0.000675+0.000144)) = 1.792 = 179.2%`,
asserted as a self-test in `measure_deviation.py`'s `__main__`, which prints
PASS/fails loudly before any measurement runs). Retail-taker bound computed
by the script: rho_u/rho_l values are in `measurement_summary.json` and
quoted in the results tables below.

Both fee numbers were fetched live, not recalled — flagged **VERIFIED**, not
"ASSUMED", per the task brief's fallback instruction (10bp/5bp was the
brief's own fallback guess and happens to match what was actually found).

## 4. Excursion / close rule

Line 1122-1128: "whenever rho enters the region outside the annualized
round-trip trading costs in Table 3, we open the position. We close the
position when rho first goes back to 0." Implemented as a state machine over
the hourly rho series (`measure_deviation.py:find_excursions`): open on the
first hour rho exits [rho_l, rho_u], close on the first subsequent hour rho
crosses back through 0, duration measured in elapsed hours from the
timestamps (not bar counts, so a data gap does not compress it). Applied
separately for the High-tier bound and the retail-taker bound.

## 5. Data fetched

`fetch_binance_hourly.py`: hourly (`interval=1h`) klines, keyless public
endpoints (`api.binance.com/api/v3/klines` for spot,
`fapi.binance.com/fapi/v1/klines` for perp), 2019-01-01 through the last
fully closed UTC hour at fetch time, for all 25 symbols x 2 markets. Raw
bars land in the MAIN checkout's `backend/data/binance_hourly/` (gitignored,
`backend/.gitignore` line added this run) — not committed; only the
aggregated CSVs below and the two scripts are committed, per the task brief.
Each (market, symbol) file has a sidecar `.meta.json` with row count, first/
last timestamp, fetch time and the CSV's SHA-256.

### Alignment (missing bars per side)

See `alignment_report.csv`. Reported per symbol: union hours (spot ∪ perp),
aligned hours actually used for rho (spot ∩ perp), and hours missing on each
side. **Most of "missing perp" reflects each contract's later Binance perp
listing date relative to its spot listing, not a real data gap within the
tradeable-on-both-markets window** — e.g. BTCUSDT spot starts 2019-01-01 in
this fetch's requested window but the perp did not exist until 2019-09-08.
The measurement below only ever uses the aligned (inner-join) hours.

## 6. Results

### 6a. Deviation summary (`deviation_summary.csv`)

Per symbol x year (2019/2020..2026-partial, plus "All"): `active_pct_high_tier`
/ `active_pct_retail_taker` (fraction of hours a position would be OPEN under
each bound — see 6c for why this, not the instantaneous exceedance share, is
the right comparator to the paper's own "Active %"), the instantaneous
exceedance shares (`share_above_high_u`, `share_below_high_l`,
`share_beyond_retail_taker` — a narrower, different quantity, kept for
transparency), and rho's mean/median/p5/p95 both raw and as a 7-day moving
average (the numeric equivalent of the paper's Figure 3, line 1044-1049).

Headline (2025 / 2026-partial-through-09-11), from `active_pct_high_tier`
(full table in `deviation_summary.csv`):

| symbol | 2025 active % (High tier) | 2026-partial active % |
|---|---|---|
| BTCUSDT | see CSV — n_excursions=1, tiny | 0 excursions |
| ETHUSDT | n_excursions=1, tiny | 0 excursions |
| BNBUSDT | 13 excursions | 0 excursions |
| 20-alt median | 10.5 excursions | 12.0 excursions |

(Excursion counts, the more legible "trades per year" framing, are in 6b —
`active_pct_high_tier` and excursion count move together but are not the
same axis; both are in the CSVs.)

### 6b. Excursions (`excursions.csv`)

Per symbol x bound x year: excursion count (= "trades per year" the sourcing
decision's open question rests on), mean/median duration in hours, mean
|rho| at entry.

**2025 / 2026-partial excursion counts, High-tier bound:**

| symbol | 2025 | 2026-partial |
|---|---|---|
| BTCUSDT | 1 | 0 |
| ETHUSDT | 1 | 0 |
| BNBUSDT | 13 | 0 |
| 20-alt median | 10.5 | 12.0 |

**Same, retail-taker bound (the practically relevant one for a small
participant):**

| symbol | 2025 | 2026-partial |
|---|---|---|
| BTCUSDT | 0 | 0 |
| ETHUSDT | 0 | 0 |
| BNBUSDT | 1 | 0 |
| 20-alt median | 1.0 | 0.0 |

Reading: BTC and ETH have gone essentially dormant at BOTH bounds in
2025-2026 — 0-1 excursions/year, versus the paper's pre-2022 double digits.
The altcoin corner (the 20-largest-other-perps universe) still produces a
double-digit excursion count per year at the High-tier bound, but almost all
of that count collapses at the retail-taker bound (median 1.0 in 2025, 0.0 in
2026-partial) — meaning most of what still crosses the paper's own
(institutional maker-fee) High tier does NOT clear the wider cost bound a
retail participant actually faces. **This directly answers the sourcing
memo's open question**: the opportunity as a RETAIL-taker-cost strategy looks
close to extinct across the board in 2025-2026 year-to-date, not just for the
five paper coins — consistent with, and sharper than, the paper's own
post-2022 structural-break finding (Table 7) that the sourcing memo's power
pre-check already flagged as underpowered to trade profitably.

### 6c. Replication check against Table 7 (`replication_check.csv`)

**First pass (discarded, kept here for the record): a naive comparison of
the instantaneous "rho is beyond the High-tier bound RIGHT NOW" hourly share
against Table 7's Active% was off by 5x-100x for every symbol/year (e.g. BTC
2021: my 5.8% vs the paper's 34.43%) — a genuinely large, suspicious gap, not
explainable by r=0 alone.** Investigated per the task brief's instruction
rather than reported as-is. Re-reading Table 7's own text (line 1201-1204,
"the average duration of open-to-close positions" is reported as a SEPARATE
column, OtC time, FROM Active%) shows Active% must be the fraction of hours
a position is OPEN — which, per the close rule (line 1128), persists for the
WHOLE excursion from entry until rho first returns to 0, not just the hours
where rho happens to be beyond the bound at that instant. Cross-checked by
hand for BTC 2021: this repo's own excursion state machine finds 18
excursions averaging 168.5 hours each = 3,033 active hours of 8,760 in the
year = 34.6%, against the paper's reported 34.43% — a near-exact match. Fixed
by adding `compute_active_mask` (open-to-close occupancy, not instantaneous
exceedance) and using THAT for the comparison below. This was a
comparator-definition bug on this measurement's first pass, not a data or
formula bug — logged here rather than silently corrected, per the
never-fabricate rule.

**Corrected comparison** (`active_pct_high_tier`, r=0, vs Table 7's Active%,
nonzero Aave r), for the five paper coins over each coin's own Table-2
sample start (line 816-824: BTC/ETH 2020-01-08, BNB 2020-02-10, DOGE
2020-07-10, ADA 2020-01-31) through the paper's sample end (2024-03-11, line
812):

| symbol | years within ~2pp of paper | largest remaining gap |
|---|---|---|
| BTCUSDT | 2020, 2021, 2022, 2023, 2024, All (all within 1.6pp) | 2020: +1.61pp |
| ETHUSDT | 2020, 2021, 2023, All (within 1.8pp) | 2022: +3.61pp |
| BNBUSDT | 2020, 2021, 2022, All (within 1.6pp) | 2024: -6.28pp |
| DOGEUSDT | 2021, 2023 (within 1.8pp) | 2022: -10.96pp |
| ADAUSDT | 2020, 2021, 2024 (within 1pp) | 2022: -17.07pp, 2023: -17.08pp |

Full table in `replication_check.csv`. **Verdict: REPLICATES CLOSELY for
BTC/ETH/BNB** (every year within ~6.3pp, most within ~2pp, of the paper's own
Active%, on the r=0 approximation this measurement is disclosed as using
throughout) — this is within the range a nonzero-but-small Aave rate could
plausibly explain, exactly the caveat in section 1. **DOGE and ADA show
larger residual gaps concentrated in 2022-2023** (up to 17pp for ADA), all in
the direction of this measurement UNDER-counting active hours relative to
the paper. This is consistent with, but not confirmed by, elevated Aave
borrow/supply rates during the 2022 crypto-credit stress period (Terra/3AC/
FTX; USDT depeg concerns) pushing the paper's own nonzero-r series across the
threshold more often than r=0 would — this measurement does not hold the
Aave series and cannot confirm this explanation, so it is reported as the
MOST LIKELY cause, not a proven one.

Price field used: kline element [4], the CLOSE of each hourly bar — the
paper does not specify which OHLC field it used within the hour beyond
"prices ... at a 1-hour frequency" (line 799-800); close is the natural
reading and is what `BinanceFuturesProvider` (this repo's existing daily
fetcher) already uses for the same reason.

Table 7 identification check (per the task brief): the "All" column of the
Active% block BEFORE the "Table 7" caption (line 1333) was checked against
Table 6's High-tier Active% column (line 1216, 1224, 1232, 1240, 1248) and
matches exactly (20.06/22.68/35.02/28.79/34.60 for BTC/ETH/BNB/DOGE/ADA) —
confirming that block is Table 7's body, not Table 8's, as the brief warned
a previous reader got wrong.

### 6d. Cross-symbol correlation, 2024-03 onward (`rho_correlation_2024_03_onward.csv`)

Hourly rho, 2024-03-01 onward, Pearson correlation. **24 of the 25 symbols**,
not 25: XMRUSDT's Binance SPOT market ends 2024-02-20 (`spot_XMRUSDT.meta.json`
`"last": "2024-02-20T02:00:00"`) — Binance delisted Monero spot trading
around that date (a real, known 2024 privacy-coin delisting, not a fetch
defect; the perp side continues serving data through 2026-09-11, so a rho
series cannot be formed for XMR past its spot-delisting date and this
symbol's aligned history ends there). It is excluded from the 2024-03-onward
correlation window by the script's own `len(s) > 100` liquidity/coverage
gate, not manually.

**Mean pairwise correlation: 0.543** (`mean_pairwise_rho_correlation_
2024_03_onward` in `measurement_summary.json`). Full 24x24 matrix in
`rho_correlation_2024_03_onward.csv`. A moderate positive correlation — rho
deviations move together across the perp universe to a meaningful degree,
consistent with the paper's own finding (line 1093-1096) that "no-arbitrage
price deviations are highly correlated among themselves" even though they
are largely UNcorrelated with spot returns.

## 7. Could not verify

- The Aave USDT supply/borrow rate series (magnitude unquantified in the
  extracted paper text; r=0 used throughout, disclosed everywhere above).
- Whether the CORRECTION 01 / ADVERSARIAL_REVIEW referenced by this task's
  brief actually exist somewhere else in the repo under a different name —
  searched `perp_basis_sourcing_2026-09-11/` and the whole repo for
  `*perp*`; neither file was found. Proceeded on the sourcing memo as
  written.
- Binance's fee schedule beyond "Regular User" (VIP 0): higher VIP tiers,
  and any current promotional/BNB-discount fee structure, were not checked
  — the retail-taker bound uses the plain Regular-User taker rate, which is
  the conservative (widest-cost, narrowest-opportunity) choice for "a
  retail participant."
- Venue access from Thailand (same gap the sourcing memo recorded, not
  re-investigated here — out of scope for a data measurement).

## 8. Deliverables

- `fetch_binance_hourly.py` — raw hourly spot+perp fetch, keyless, throttled/retrying.
- `measure_deviation.py` — rho computation, bounds, excursion state machine, all CSV/JSON outputs.
- `deviation_summary.csv`, `excursions.csv`, `alignment_report.csv`,
  `replication_check.csv`, `rho_correlation_2024_03_onward.csv`,
  `measurement_summary.json` — this run's outputs.
- This file.

`ruff check` clean on both scripts (verified before each was run). No return
statistics, no Sharpe, no DSR computed anywhere in this deliverable. The full
backend test suite was **not** run — nothing under `app/` changed, only new
files under `data/research_runs/` and a `.gitignore` addition, per the task
brief's own instruction to skip it.
