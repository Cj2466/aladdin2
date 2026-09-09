# Intraday / daily-event data scoping — 2026-09-09

**Purpose.** The criteria audit and fix of 2026-09-09
(`../criteria_audit_2026-09-09/CRITERIA_AUDIT_2026-09-09.md`,
`../criteria_fix_2026-09-09/CRITERIA_FIX_2026-09-09.md`) measured that with
~11.6 years of daily data, **0 of 50** persisted families had 80% power to
detect a true annualized Sharpe of 0.5 at the 0.95 DSR bar, and that such an
edge would need **183.3 years** of daily data (N=12, σ_SR=0.19). The owner's
working conclusion was that small edges can only be certified where the number
of *independent bets per year* is very large — i.e. intraday and daily-event
mechanisms across thousands of stocks. This memo turns that into numbers before
any money is spent.

**Scope discipline.** No production code. One computation (§3), run through the
project's own validated `dsr_power` module. Already-logged paid-data items
(Norgate futures ~$270/yr; a real borrow-rate feed; HY OAS history; options
dealer-gamma "P6") are **not** re-researched here.

**Evidence rule.** Every price, history-depth, field and availability claim below
is either quoted from the vendor's own page with URL and fetch date, or marked
**UNVERIFIED**. All fetches were made **2026-09-09**. **13 claims are marked
UNVERIFIED**; they are listed together in §6.

---

## 0. Headline finding, stated before the detail

The premise "more independent bets per year ⇒ faster certification" is, as
literally stated, **false in this project's own gate**, and §3 measures it.

Holding the *annualized* Sharpe fixed and raising `periods_per_year` from 252
(one daily P&L observation) to 504,000 (2,000 stocks × 252 days, all treated as
independent) moves years-to-detect for a true annualized Sharpe of 0.5 from
**221.68 years to 221.58 years** — a 0.05% improvement. Sampling the same
annualized-Sharpe process more finely adds essentially nothing, because both the
required Sharpe and the Sharpe standard error rescale with the sampling
frequency; what survives is calendar time.

What *does* move the number is the **annualized Sharpe itself**, steeply:

| true annualized Sharpe | years to detect (N=12, σ=0.2) |
|---|---|
| 0.50 | 221.68 |
| 1.00 | 13.92 |
| 2.09 | 2.02 |
| 3.62 | 0.59 |

So the correct restatement of the owner's thesis is: **breadth is valuable
because it raises the achievable annualized Sharpe of the combined book, not
because it shortens the sample.** That distinction changes what is worth buying,
and it is why the recommendation in §5 is much cheaper than the question
implied.

---

## 1. Mechanisms (literature, opened and verified)

Six mechanisms. Each source was actually fetched; where a specific number could
not be extracted from the source I opened, it is marked UNVERIFIED rather than
recalled.

### M1 — Closing-auction price deviation and overnight reversal

**Source, opened:** Bogousslavsky, V. and Muravyev, D., "Who Trades at the
Close? Implications for Price Discovery and Liquidity", working-paper PDF
(June 2021 version), fetched 2026-09-09 from
`https://static1.squarespace.com/static/6310c0b9bb63a25599f4418c/t/634ffc92f81e226b2c30654f/1666186387645/who-trades-at-the-close_June2021.pdf`.
Published version: *Journal of Financial Markets* 66 (2023), 100819
(EconPapers record fetched 2026-09-09).

**Verified quantities (from the fetched PDF):**

* Sample: "common stocks listed on the NYSE and Nasdaq with a price greater than
  $5", TAQ, **January 2010 to December 2018**. 2,946 Nasdaq-listed stocks
  ("52.41% of all observations"), so ~5,600 stocks total.
* "The average (absolute) deviation is 8.1 basis points (bps), only slightly
  higher than the average half bid-ask spread of 7.6 bps."
* "Deviations are occasionally large and exceed 63 bps".
* "the reversal coefficient is -0.85, or 85% of the deviation is reversed by the
  next morning". Adjusted for the bid-ask bounce the coefficient is **-0.95**.
  For large / small stocks, "110% and 85% of the price deviation is reversed".
* Large-deviation subsample (price impact > 19.70 bps): "about 66% of the price
  impact reverses overnight".
* "For stocks with sufficient after-hours liquidity, one-third to one-half of
  the reversal occurs within the first 30 minutes after the close."
* Auction share of volume: "7.48% of aggregate daily dollar volume in 2018, up
  from 3.11% in 2010"; "$15.2 billion are traded in the closing auction across
  U.S. stocks on a typical [day] in 2018".

**Effect size in the paper's own units:** ~8.1 bps average absolute deviation,
of which ~85% reverts by the next open. **No Sharpe ratio is reported**, and the
paper makes no profitability claim for a reversal strategy — it explicitly
frames the deviation as compensation for liquidity provision and auction
participation costs.

**Horizon:** close → next morning open (overnight), with 1/3–1/2 of the move
back within 30 minutes after the close for liquid names.

**Independent bets per year:** ~5,600 stocks × 252 days ≈ **1.4 million
stock-events/year** gross. Honest reduction: a same-day cross-section of
auction-deviation reversals shares a market-wide overnight return and a
market-wide liquidity-provision factor, so the *portfolio* produces **252 P&L
observations per year**, and the effective independent count is somewhere
between 252 and 1.4M. This project has never successfully measured that
effective count for its own trials (`effective_n_clustering.py` failed to find
real structure; see `project_dsr_policy_n_decision_2026-09-06`), so no point
estimate is offered here.

### M2 — Market-on-close (MOC) order-imbalance reversal

**Source, partially opened.** Bogousslavsky & Muravyev's fetched PDF cites it
directly: "Wu and Jegadeesh (2020) argue that reversal strategies based on
market-on-close order imbalances are profitable." That *citation* is verified.
The Wu & Jegadeesh paper itself (SSRN 3732955 / *Journal of Financial Economics*,
"Closing auctions: Nasdaq versus NYSE") returned **HTTP 403** on fetch
2026-09-09; SSRN blocks automated retrieval.

**UNVERIFIED (search-snippet only, not opened):** a reported long/short
risk-adjusted return of **13.2 basis points per day**, a 3–5 day dissipation of
the temporary price-impact component, and "21% (43%) of the closing auction
return reversed at the NYSE (Nasdaq) overnight". **Do not build on these.** If
13.2 bps/day were real and net, it would imply an enormous Sharpe and would
dominate every other row in this memo — which is precisely why it must be
verified from the paper before it is used.

**Independent bets per year:** same order as M1 (imbalance is published for every
auction-participating symbol), with the same cross-sectional-correlation caveat.

### M3 — Market intraday momentum (first half-hour predicts last half-hour)

**Primary source, NOT opened:** Gao, L., Han, Y., Li, S. Z. and Zhou, G.,
"Market intraday momentum", *Journal of Financial Economics* 129(2) (2018),
394–414. SSRN abstract page 2440866 returned **HTTP 403** on fetch 2026-09-09.
Its abstract was returned by search ("Based on high frequency S&P 500
exchange-traded fund (ETF) data from 1993–2013 … the first half-hour return on
the market as measured from the previous day's market close predicts the last
half-hour return"), and the sample/claim are independently corroborated below,
but **the paper's own reported strategy Sharpe ratio, success rate and
break-even cost are UNVERIFIED** (§6, item 1).

**Independent replication, opened and verified:** Limkriangkrai, M., Chai, D.
and Zheng, G., "Market intraday momentum: APAC evidence", *Pacific-Basin
Finance Journal* 80 (2023), 102086, open-access PDF fetched 2026-09-09 from
`https://researchmgt.monash.edu/ws/files/519509174/494419119_oa.pdf`.

*(Note: this URL was returned by a search for the Gao et al. paper and is a
different paper. It is used here as a corroborating replication, not as the
primary source.)*

Verified from that PDF, its Table 2 Panel A, SPY, **JAN1996–DEC2013**:

* Model (1), r₁ → rₙ: in-sample **R² = 0.017**, out-of-sample **R²_OS = 0.017**.
* Model (2), rₙ₋₁ → rₙ: R² = 0.009, R²_OS = 0.005.
* Model (3), both: R² = 0.026, R²_OS = 0.023.
* "Overall, our results indicate successful replication of the [US result]."

**Horizon:** intraday, one 30-minute position per day.
**Universe:** one instrument (SPY). The paper reports the effect for ten other
liquid ETFs; APAC evidence is mixed (China and Japan yes, Hong Kong and
Singapore no).

**Independent bets per year:** **252** — one instrument, one non-overlapping
trade per day. This mechanism has *the fewest* bets per year of the six, and §3
shows why it is nonetheless the best candidate.

### M4 — Overnight vs intraday return decomposition ("tug of war")

**Source, opened:** Lou, D., Polk, C. and Skouras, S., "A tug of war: Overnight
versus intraday expected returns", *Journal of Financial Economics* 134(1)
(2019), 192–213, author PDF fetched 2026-09-09 from
`https://personal.lse.ac.uk/polk/research/TugOfWar.pdf`.

**Verified quantities from that PDF:**

* Sample: "Our core Center for Research in Security Prices (CRSP)-Compustat US
  sample spans the period **1993–2013**, constrained by the availability of TAQ
  data." Stocks below $5 and the bottom NYSE size quintile are excluded.
* Construction requires the **VWAP in the first half hour of trading
  (9:30–10:00 am) as reported in TAQ** to split close-to-close into overnight
  and intraday components.
* Momentum hedge portfolio: "average overnight excess return of **3.47% per
  month** with an associated t-statistic of **16.57**"; three-factor version
  "also 3.47% per month (t-statistic of 16.83)"; the intraday leg is
  "−3.02% per month with a t-statistic of −9.74" (three-factor alpha).
* A second strategy: "**2.41% per month** (t-statistic of **7.70**)" overnight
  with "a three-factor overnight alpha of **−1.77% per month** (t-statistic of
  −7.89)" — i.e. offsetting signs across the two periods.
* Cross-sectional sorting variables "generate variation in the spread between
  overnight and intraday momentum returns **on the order of 2% per month**."

**Horizon:** monthly rebalance, but the position must be turned over at the open
and the close of every trading day to isolate the overnight leg.

**Independent bets per year:** 12 portfolio formations/year × ~2,000 eligible
stocks; the P&L series is monthly (**12 observations/year**) unless the daily
overnight/intraday legs are treated as the return series (**504/year**).

### M5 — ETF creation/redemption flow as observable non-fundamental demand

**Source, opened (abstract page):** Brown, D. C., Davies, S. W. and
Ringgenberg, M. C., "ETF Arbitrage, Non-Fundamental Demand, and Return
Predictability", *Review of Finance* 25(4) (July 2021), 937–972,
DOI 10.1093/rof/rfaa027, abstract page fetched 2026-09-09 from
`https://academic.oup.com/rof/article-abstract/25/4/937/5919085`.

**Verified from that page:** "creation and redemption activities (ETF flows)
provide signals of non-fundamental demand shocks"; a strategy "short in
high-flow ETFs and long in low-flow ETFs generates **excess returns of 1.1–2.0%
per month**".

**UNVERIFIED:** the sample period, the number of ETFs, the t-statistics, and any
Sharpe ratio — the full text is paywalled and the abstract page does not state
them (§6, item 11).

**Horizon:** monthly. **Universe:** US-listed ETFs.
**Independent bets per year:** 12 formations × (number of ETFs, UNVERIFIED);
P&L series is **12 observations/year**.

### M6 — Month-end institutional liquidity demand ("dash for cash")

**Source, opened:** Etula, E., Rinne, K., Suominen, M. and Vaittinen, L.,
"Dash for Cash: Month-End Liquidity Needs and the Predictability of Stock
Returns", 27 August 2015 working paper, PDF fetched 2026-09-09 from
`https://www.aeaweb.org/conference/2016/retrieve.php?pdfid=21226&tk=zHQNB4Rz`.
Published as "Dash for Cash: Monthly Market Impact of Institutional Liquidity
Needs", *Review of Financial Studies* 33(1) (2020), 75–111 (Oxford Academic and
EconPapers records fetched 2026-09-09; note the search result initially
mis-attributed it to JFQA — corrected here).

**Verified quantities from that PDF:**

* "Our main sample starts in **1980**"; cross-sectional stock data from CRSP,
  "sample period is from January 1980 to December [2013]".
* "the average annualized S&P 500 return from T-8 to T-4 is **−3.4%** versus
  **28.6%** from T-3 to T+3."
* Footnote 9, verbatim: "the CAPM alpha of the strategy is **5.6% per annum**,
  the Fama and French (1993) three-factor alpha is **6.2% per annum**; and the
  alpha with respect to a five-factor model that also includes the momentum
  factor of Carhart (1997) and the liquidity factor of Pastor and Stambaugh
  (2003) is **6.3% per annum**. All alphas are statistically significant at the
  1% level."
* The strategy holds the index for "seven business days around the turn of the
  month" (T-3 to T+3).

**Horizon:** a 7-business-day window each month.
**Universe:** the market index (plus a cross-sectional CRSP version).
**Independent bets per year:** **12** at the index level. This is the *worst* of
the six on bets-per-year and needs no new data at all.

### Bets-per-year summary, with the honest correlation note

| | mechanism | gross bets/yr | P&L observations/yr | honest note |
|---|---|---|---|---|
| M1 | closing-auction reversal | ~1.4M | 252 | same-day cross-section shares overnight market + liquidity factors |
| M2 | MOC imbalance reversal | ~1.4M | 252 | same as M1; effect size UNVERIFIED |
| M3 | intraday momentum | 252 | 252 | single instrument, genuinely non-overlapping day to day |
| M4 | overnight/intraday tug of war | ~24k | 12 (or 504 daily-leg) | monthly formation; daily legs are highly cross-correlated |
| M5 | ETF flow | 12 × n_ETFs | 12 | ETFs overlap heavily in underlying holdings |
| M6 | dash for cash | 12 | 12 | market-level, one bet per month |

---

## 2. Data required, and what vendors actually sell

All fetches 2026-09-09. Prices are quoted from the vendor's own page or marked
UNVERIFIED.

### What each mechanism needs

| mechanism | data required |
|---|---|
| M1 | official closing auction price + pre-close (15:59) NBBO midpoint + next-day open, for the full US common-stock cross-section incl. delisted |
| M2 | **closing-auction imbalance messages** (Nasdaq NOII; NYSE imbalance feed) — paid, exchange-licensed |
| M3 | 1-minute (or 30-minute) bars for SPY only |
| M4 | daily open and close per stock; the paper uses first-half-hour TAQ VWAP, so a strict replication needs intraday bars |
| M5 | daily ETF shares outstanding + ETF NAV + ETF close |
| M6 | daily index/stock closes only — **already held by this project** |

### Vendors

**Polygon.io → Massive.** `https://polygon.io/pricing` **301-redirects to
`https://massive.com/pricing`** (verified 2026-09-09); Polygon appears to have
rebranded. Quoted from `https://massive.com/pricing`, fetched 2026-09-09:

| plan | price | history depth (quoted) | granularity | API limit |
|---|---|---|---|---|
| Stocks Basic | **$0/month** | "2 Years Historical Data" | end-of-day, minute aggregates | "5 API Calls / Minute" |
| Stocks Starter | **$29/month** | "5 Years Historical Data" | 15-min delayed, minute + second aggregates | unlimited |
| Stocks Developer | **$79/month** | "10 Years Historical Data" | 15-min delayed, minute + second aggregates, **trades** | unlimited |
| Stocks Advanced | **$199/month** | "20+ Years Historical Data" | real-time quotes + trades, minute/second aggregates | unlimited |

Corporate actions are listed as included on all tiers. **UNVERIFIED:** splits,
dividends and delisted-ticker handling are not separately detailed on the
pricing page (§6, item 13).

**Databento.** Quoted from `https://databento.com/pricing`, fetched 2026-09-09:

* Standard: **"$199 per month"**, "1 year of L1 history".
* Plus: **"$1,750 license fees per month"**, annual contract, "16+ years of L1
  history".
* Unlimited: **"$4,500 license fees per month"**, annual contract, "16+ years in
  all schemas".
* New signups: **"$125 in free credits that can be used towards historical
  data"**, expiring "6 months after signup". *(This matches the credit already
  logged in `PENDING_PAID_DATA_DECISIONS.md` — not re-researched.)*

Critically, from `https://databento.com/blog/introducing-databento-us-equities`
(fetched 2026-09-09), the **Standard $199/month plan provides only "1 month of
L2 (MBP-10) and L3 (MBO, Imbalance) history"** alongside "7 years of OHLCV
history" and "12 months of L0 and L1 history". The same page confirms the
Integrated feeds "provide auction imbalance data from NYSE-operated venues,
complementing the imbalance data already available through Nasdaq
TotalView-ITCH."

**So: one month of imbalance history at $199/month; multi-year imbalance history
requires Plus ($1,750/month) or Unlimited ($4,500/month), i.e. $21,000–$54,000
per year on an annual contract.** That single verified fact decides §5.

**UNVERIFIED for Databento:** the per-GB usage rate for historical US equities
(the pricing page says "usage-based pricing ($/GB)" without stating the rate),
and the XNAS.ITCH history start date — `databento.com/datasets/XNAS.ITCH` and
`/datasets` and `/docs/...` all render client-side and returned no content to
either WebFetch or curl (the raw HTML is a "You need to enable JavaScript"
shell). A search snippet gives 2018 as the tick-history start; that is
**UNVERIFIED** (§6, items 7–8).

**FirstRate Data.** Quoted from
`https://firstratedata.com/b/22/stock-complete-historical-intraday`, fetched
2026-09-09 ("Stocks Complete"):

* "16300" tickers = "9300 most liquid US stocks" + **"Over 7000 delisted
  stocks"** — the only intraday product found with explicit delisted coverage.
* History: **"Jan 2000 - Sep 2026"** (~26.7 years).
* Granularity: "1-minute, 5-minute, 30-minute, 1-hour, 1-day".
* "1 month of free updates are included. Updates are **$59.95 per month**
  thereafter ($79 if fundamentals are included)."

And from `https://firstratedata.com/cb/4/complete-stocks-etf` ("Stocks and ETFs
Bundle"): "10120" tickers, "Over 7000 delisted tickers", "Jan 2000 - Sep 2026",
updates **"$79.95 per month"**.

**UNVERIFIED: the one-time purchase price of either bundle.** The page renders
the price through a client-side currency widget; both WebFetch and a raw curl of
the HTML returned the update subscription figures but no purchase price (§6,
item 4). Do not assume a number — ask the vendor.

**Alpaca.** Quoted from `https://alpaca.markets/data`, fetched 2026-09-09:

* Free: **$0/month**, "7+ years" historical, **IEX only**.
* Algo Trader Plus: **$99/month**, "7+ years" historical, "All US Exchanges"
  (SIP), real-time websocket, unlimited symbols.

**UNVERIFIED:** delisted-symbol coverage is not stated on the page (§6, item 10).
IEX-only free data is ~2–3% of consolidated volume and is **not** usable for
auction or closing-price work.

**Tiingo.** Quoted from `https://www.tiingo.com/pricing`, fetched 2026-09-09:

* Starter: **"$0/month"**, "109,883" securities, "30+ Years" price history,
  "500" unique symbols/month, "50" max requests/hour.
* Power: **"$30/month"**, "109,883" symbols/month, "10,000" requests/hour,
  "IEX Feed" listed.

**UNVERIFIED:** the depth of Tiingo's intraday/IEX history is not stated on the
pricing page (§6, item 10). Again IEX-only — not consolidated tape.

**Kibot.** Not fetched in this pass; **UNVERIFIED entirely**. Listed here only so
its absence is explicit rather than silent.

**Cboe DataShop.** `https://datashop.cboe.com/` fetched 2026-09-09: the landing
page lists "Equities" under asset classes and data types "Historical, tick,
intraday, daily, quarterly", but **no product prices are published on it** —
it directs to contact sales (+1 800 307-8979). Price **not published**
(§6, item 5). Note also that Cboe's equities tape is Cboe's own four exchanges,
not NYSE/Nasdaq auctions.

**Nasdaq Data Link.** `https://data.nasdaq.com/databases` fetched 2026-09-09
returned only the page title; no product or price information was extractable.
**UNVERIFIED** (§6, item 6).

**Free auction-imbalance data — checked, and it is one day.** Nasdaq operates a
public archive at `https://emi.nasdaq.com/ITCH/Nasdaq ITCH/`, which lists
multi-GB ITCH 5.0 sample files from 2018–2026. Its `NOII/` subdirectory —
directly listed by curl on 2026-09-09 — contains **exactly one file**:

```
5/9/2022  8:08 PM   96588423   S050922-v50-NOII.txt.gz
```

**One trading day (2022-05-09) of net-order-imbalance data.** Enough to validate
a parser and confirm field layout; useless as a research sample. Licensing terms
for this archive are **UNVERIFIED** (§6, item 12).

---

## 3. Power (computed, not guessed)

**Script:** `power_grid.py` in this directory. **Output:**
`power_grid_output.txt`. Run with
`/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/venv/bin/python` from
the worktree's `backend/` directory. It calls
`app.services.research_lab.dsr_power.years_to_detect` and
`.min_detectable_sharpe` as-is; no formula is retyped.

**Unit contract** (from that module's docstring, read before use): every Sharpe
argument is **annualized**; `periods_per_year` is the number of per-period
returns the DSR gate is computed on per year; `n_observations` = years ×
`periods_per_year`. Threshold 0.95, power target 0.80 (the module's
`POWER_FLOOR`), normal moments.

**Harness check.** Before reading anything off the grid, the script reproduces
two already-committed numbers from
`../criteria_fix_2026-09-09/validate_dsr_power_output.txt`:

```
years_to_detect(S=0.50, N=12, sigma=0.19, ppy=252) = 183.3 (committed value: 183.3)
min_detectable_sharpe(n=2926, N=12, sigma=0.19, ppy=252) = 1.047 (committed value: 1.047)
```

Both match exactly, so the harness is calling the module correctly.

### 3a. Independence assumption, stated explicitly

The task asked for bets-per-year to be used as `periods_per_year`. That is
correct **only if every bet is an independently observed return draw**. For a
cross-sectional book of K stocks traded the same day it is not: those K bets
share a common daily factor, so the strategy's P&L series still has 252
observations per year, and extra breadth raises the achievable Sharpe rather
than the observation count. Both readings were therefore computed. The
bets-as-periods reading is the **optimistic upper bound**.

### 3b. Years to detect vs periods_per_year — the invariance result

At threshold 0.95, 80% power, true annualized Sharpe 0.5:

| periods_per_year | meaning | N=12, σ=0.2 | N=12, σ=0.5 | N=36, σ=0.2 | N=36, σ=0.5 |
|---|---|---|---|---|---|
| 252 | one daily P&L observation | **221.68 yr** | never | never | never |
| 504 | two non-overlapping intraday legs/day | 221.63 | never | never | never |
| 2,520 | 10 intraday observations/day | 221.59 | never | never | never |
| 25,200 | 100 effective independent bets/day | 221.59 | never | never | never |
| 504,000 | 2,000 stocks × 252 days, **all independent** | **221.58 yr** | never | never | never |

("never" = the gate is unreachable within the module's 500-year search bound.)

A 2,000× increase in assumed independent bets buys **0.10 years**. The same
invariance holds at every Sharpe tested (e.g. S=2.09, N=12, σ=0.2: 2.02 yr at
ppy=252 vs 2.00 yr at ppy=504,000). **This is the memo's central measured
result and it contradicts the premise that motivated the memo.**

### 3c. Years to detect vs annualized Sharpe — what actually moves

Threshold 0.95, 80% power, ppy=252:

| true annualized Sharpe | N=12, σ=0.2 | N=36, σ=0.2 | N=12, σ=0.5 | N=36, σ=0.5 |
|---|---|---|---|---|
| 0.30 | never | never | never | never |
| 0.50 | 221.68 | never | never | never |
| 0.75 | 35.58 | 60.25 | never | never |
| 1.00 | 13.92 | 19.03 | 220.53 | never |
| 1.25 | 7.37 | 9.21 | 35.55 | 199.64 |
| 1.50 | 4.56 | 5.41 | 13.93 | 34.17 |
| 2.00 | 2.24 | 2.53 | 4.57 | 7.26 |
| **2.09** | **2.02** | **2.26** | **3.94** | **6.03** |
| 2.50 | 1.33 | 1.46 | 2.25 | 3.07 |
| 3.00 | 0.88 | 0.95 | 1.34 | 1.69 |
| **3.62** | **0.59** | **0.62** | **0.82** | **0.97** |

And the inverse view — the smallest true annualized Sharpe detectable with a
given calendar budget:

| calendar years | N=12, σ=0.2 | N=36, σ=0.2 | N=12, σ=0.5 | N=36, σ=0.5 |
|---|---|---|---|---|
| 1.0 | 2.838 | 2.935 | 3.343 | 3.588 |
| 2.0 | 2.098 | 2.195 | 2.601 | 2.844 |
| 3.0 | 1.773 | 1.870 | 2.274 | 2.517 |
| 5.0 | 1.447 | 1.544 | 1.948 | 2.190 |
| 11.6 | 1.064 | 1.160 | 1.564 | 1.806 |

Note how brutal σ_SR is: at σ=0.5 (a wide trial grid) even a true Sharpe of 1.0
needs 220 years at N=12 and is unreachable at N=36. **Grid discipline is worth
more than any dataset.**

### 3d. Converting each mechanism's claimed effect to an annualized Sharpe

**M3, intraday momentum — convertible.** The verified quantity is
R²_OS = 0.017 for r₁ → rₙ (Limkriangkrai et al. 2023, Table 2 Panel A, SPY
1996–2013). Derivation, shown rather than cited, for the maximal Sharpe of a
strategy that scales its position with a linear forecast:

> Let rₜ = b·xₜ + eₜ with xₜ ⟂ eₜ, and take the position wₜ ∝ xₜ. Strategy
> return is xₜrₜ, with mean b·σ²ₓ and (leading-order) variance σ²ₓσ²ₑ. So
> SR_per_period = b·σ²ₓ / (σₓσₑ) = b·σₓ / σₑ. From R² = b²σ²ₓ/σ²ᵣ we get
> b·σₓ = R·σᵣ, and σₑ = σᵣ√(1−R²). Hence
> **SR_per_period = R / √(1−R²)**, with R = √(R²).

With R² = 0.017: R = 0.13038, SR_per_period = 0.13038/√0.983 = **0.13150** per
day (one trade per day) → annualized × √252 = **2.088 ≈ 2.09**.

This is an **upper bound**: it assumes the out-of-sample coefficient is known,
optimal position scaling, and **zero transaction costs**. It is my arithmetic
applied to the paper's verified R², not a number the paper reports.

**M4, tug of war — convertible.** t = 16.57 for the overnight momentum hedge
portfolio over 1993–2013 = 252 monthly observations. SR_monthly = t/√n =
16.57/√252 = 16.57/15.8745 = **1.0438**; annualized = 1.0438 × √12 =
**3.6160 ≈ 3.62**. Caveats stated: the exact n may be a few months short of 252
after lead/lag losses (which would *raise* the implied Sharpe), and this is
**gross**, on a portfolio that must be fully turned over at both the open and
the close of every trading day.

**M1 — not convertible.** The paper reports basis-point deviations and a
reversal coefficient, no return series and no Sharpe. Note directly, though:
mean deviation 8.1 bps × 85% reversion = **~6.9 bps gross per round trip**
against an average half-spread of 7.6 bps — i.e. the average deviation does not
cover half of one crossing, let alone the project's 5 bps one-way cost model
(10 bps round trip). Only the large-deviation tail (>19.70 bps impact, 66%
reverting ≈ 13 bps, or >63 bps deviations) can clear costs.

**M2 — not convertible** (source not opened; the one number in circulation is
UNVERIFIED).

**M5 — not convertible** from the abstract: 1.1–2.0%/month with no volatility
and no t-statistic.

**M6 — not convertible**: 5.6–6.3%/yr alpha with no reported strategy volatility.

### 3e. The table asked for

Years of data to reach 80% power at threshold 0.95. "bets/yr as ppy" is the
optimistic reading of §3a; "P&L ppy" is the defensible one. Because of §3b the
two columns are indistinguishable, which is itself the point.

| mech | claimed effect (verified) | annualized Sharpe | bets/yr used as ppy | N=12 σ=0.2 | N=36 σ=0.2 | N=12 σ=0.5 | N=36 σ=0.5 |
|---|---|---|---|---|---|---|---|
| M1 | 8.1 bps dev, 85% reverts | **not convertible** (scenario 0.50) | 504,000 | 221.58 | never | never | never |
| M2 | UNVERIFIED | **not convertible** | 504,000 | — | — | — | — |
| M3 | R²_OS = 0.017 | **2.09** (derived §3d) | 252 | **2.02** | **2.26** | **3.94** | **6.03** |
| M4 | 3.47%/mo, t=16.57 | **3.62** (derived §3d) | 504 | **0.58** | 0.61 | 0.80 | 0.97 |
| M5 | 1.1–2.0%/mo | **not convertible** (scenario 1.00) | 12 → ppy 12 not run; at ppy 252 | 13.92 | 19.03 | 220.53 | never |
| M6 | 5.6–6.3%/yr alpha | **not convertible** (scenario 0.50) | 12 | 221.68 | never | never | never |

Scenario rows use the project's own reference micro-edge (0.5) or a generous 1.0
purely to show what such an edge would cost in calendar time; they are **not**
attributions to the papers.

---

## 4. Blockers, bluntly

**M1 — closing-auction reversal.**
* **Killed by the cost model on the average stock.** 6.9 bps of expected
  reversion vs 10 bps round-trip at the project's 5 bps one-way model, before
  borrow on the short leg. Only a rare tail is tradeable.
* Needs the **official auction price plus the 15:59 NBBO midpoint** — not a
  daily close. The project's current free daily feed cannot produce the deviation
  at all.
* Survivorship: needs delisted names. Only FirstRate's "Complete" bundles were
  found to state delisted coverage, and their price is UNVERIFIED.
* Capacity: the deviation *is* the compensation to liquidity providers. Taking
  it means standing in the auction with size, which requires exactly the
  low-latency execution this project does not have.
* The paper itself never claims the reversal is profitable net of costs.

**M2 — MOC imbalance.**
* **Data cost is the blocker and it is verified: $1,750/month minimum** for
  multi-year imbalance history at Databento (Plus tier, annual contract) —
  $21,000/yr, roughly 78× the already-declined Norgate item.
* The $199/month Standard tier gives **one month** of imbalance history. One
  month cannot power anything (§3c: even a true Sharpe of 2.84 needs a full
  year).
* Free alternative checked and rejected: Nasdaq's public archive holds **one
  day** of NOII.
* Effect size is UNVERIFIED, so the spend would be on an unquantified claim.
* Same execution blocker as M1 — the trade is *in* or *immediately after* the
  auction.

**M3 — intraday momentum.**
* **Single instrument.** No cross-sectional breadth, no diversification, and one
  instrument means the "many uncorrelated micro-edges" goal is not served
  directly by this family alone.
* The 2.09 Sharpe is a zero-cost upper bound. SPY's spread is ~1 bp, but the
  project's 5 bps one-way cost model is calibrated for a broad cross-section and
  would be punitive and unrealistic here — **using it unchanged would
  manufacture a false negative**, and changing it for one family needs an
  explicit, logged, reviewed justification (CLAUDE.md §4, cost realism).
* The effect is documented on 1993–2013 data. It is 13 years old, widely
  publicised, and plausibly arbitraged. Any test must run 2014→2026 as the real
  out-of-sample.
* Timing risk: a 30-minute close-window position is exactly where the closing
  auction now absorbs 7.5% of daily volume (M1's finding), so the execution
  assumption matters more than it did in the paper's sample.
* Grid discipline: at σ=0.5 and N=36 this needs 6.03 years. At σ=0.2 and N=12,
  2.02 years. **The pre-registered grid size decides whether this is testable.**

**M4 — tug of war.**
* **Turnover is the whole problem.** Isolating the overnight leg means a full
  round trip every single day. At 5 bps one-way that is ~25 bps/day of cost
  against a gross edge of 3.47%/month ≈ 17 bps/day. **Net negative by roughly
  8 bps/day at the project's own cost model**, before borrow. The 3.62 Sharpe is
  a gross number that a retail cost stack destroys.
* The paper's construction needs first-half-hour TAQ VWAP; substituting the open
  print is a deviation that must be logged under mechanism-fidelity review.
* Survivorship: 1993–2013 CRSP with delistings; a live rebuild needs PIT
  universe membership the project does not have for intraday data.
* Borrow: the short leg is a real borrow-rate dependency, which is an already
  logged open paid-data gap.

**M5 — ETF flow.**
* Needs daily ETF **shares outstanding**, which is the hard field; no vendor
  checked here states it. Not a price problem, a coverage problem.
* Monthly horizon → 12 P&L observations/year → nothing about the power problem
  improves.
* Effect size unconvertible from the abstract; the full text is paywalled.

**M6 — dash for cash.**
* 12 bets/year and needs no new data. Testable today at zero cost — and by §3c
  a 0.5-Sharpe version of it is undetectable in 221 years. It is the clearest
  illustration of why "more data vendors" is not the binding constraint.
* Sample 1980–2013; the RFS publication was 2020. Heavily publicised.

**Cross-cutting.**
* **No real capital and no low-latency execution exist** (CLAUDE.md §1;
  `ExecutionControl.trading_halted` defaults True). Every auction-adjacent
  mechanism (M1, M2, and the close leg of M4) assumes execution capability the
  project does not have and is not close to having. Buying the data does not buy
  the ability to act on it.
* **PIT universe.** The project has no point-in-time intraday universe. This has
  already burned it once (`project_lazy_prices_confound_2026-09-03`: ticker→CIK
  resolution was not point-in-time, making reruns non-monotonic).
* **σ_SR discipline dominates data spend.** §3c: moving from σ=0.5 to σ=0.2 at
  a true Sharpe of 1.0 takes years-to-detect from 220.53 to 13.92 — a 16× gain,
  free. No purchase in this memo comes close to that.

---

## 5. Recommendation

**Ranking by (years-to-detect × data cost × blocker severity):**

| rank | mech | years to detect | incremental data cost | blocker severity |
|---|---|---|---|---|
| 1 | **M3 intraday momentum** | 2.02–6.03 | **$0–$79/mo** (verified) | moderate: single instrument, cost-model calibration, likely decayed |
| 2 | M4 tug of war | 0.58–0.97 | $0–$79/mo | **severe: net negative at 5 bps/side; ~25 bps/day cost vs ~17 bps/day gross** |
| 3 | M5 ETF flow | ≥13.9 (scenario) | unknown; shares-outstanding coverage unsolved | severe: field availability, 12 obs/yr |
| 4 | M6 dash for cash | 221.7 (scenario) | **$0** | severe: 12 bets/yr, widely published |
| 5 | M1 closing-auction reversal | 221.6 (scenario) | FirstRate bundle (price UNVERIFIED) + auction price feed | **severe: 6.9 bps gross vs 10 bps round trip** |
| 6 | M2 MOC imbalance | unknown (effect UNVERIFIED) | **$1,750/mo = $21,000/yr** (verified) | **severe: cost, execution, unverified claim** |

### The recommendation itself

**Buy nothing yet. If one purchase is made, it is Massive (formerly Polygon.io)
"Stocks Developer" at $79/month, verified from `https://massive.com/pricing` on
2026-09-09, giving "10 Years Historical Data" with minute aggregates and
trades.** That is the entire data requirement for M3, and 10 years covers the
full 2014→2026 out-of-sample window that matters. The $199/month "Stocks
Advanced" tier ("20+ Years Historical Data") is only worth it if an in-sample
1996–2013 replication of Gao et al. is wanted before the out-of-sample test —
defensible, but a second decision.

**What it buys in years-to-detect: 2.02 years (N=12, σ_SR=0.2) to 6.03 years
(N=36, σ_SR=0.5), against 183 years for a true 0.5 Sharpe on daily data**
(`validate_dsr_power_output.txt`, reproduced exactly by this memo's harness).

**But the honest attribution matters more than the headline.** That improvement
does **not** come from the data being intraday, and §3b measures that directly:
raising assumed independent bets 2,000-fold changes years-to-detect by 0.05%.
It comes entirely from M3's **converted annualized Sharpe of 2.09** being large,
which in turn comes from an R²_OS of 1.7% on a *once-daily* bet and is a
**zero-cost upper bound**. If realistic costs cut that Sharpe to 1.0, the same
grid needs 13.92 years and the purchase buys nothing at all. **The purchase is
therefore only justified as a cheap test of whether the net Sharpe survives
costs — not as a route to certifying a 0.5-Sharpe micro-edge, which no dataset
in this memo makes reachable.**

**Explicitly not recommended:** the Databento Plus tier at $1,750/month
($21,000/yr, verified). It is the only verified route to multi-year auction
imbalance history, and it fails on three independent grounds — the effect size
it would test is UNVERIFIED, the mechanism it serves is already negative at the
project's cost model (6.9 bps gross vs 10 bps round trip), and the execution
capability to act on it does not exist.

**The free action that dominates every purchase:** the σ_SR and n_trials
discipline in §3c. Going from a wide grid (σ=0.5, N=36) to a tight
pre-registered one (σ=0.2, N=12) at a true Sharpe of 1.0 moves years-to-detect
from "never" to 13.92. That costs nothing and should be settled before any
invoice.

**Owner sign-off required** for any purchase (CLAUDE.md §4: paid-data gaps are
logged, not acted on). Nothing here has been bought, subscribed to, or
committed.

---

## 6. The 13 UNVERIFIED claims, listed together

1. **Gao et al. (2018) own reported strategy Sharpe / success rate /
   break-even cost.** SSRN 2440866 returned HTTP 403 on 2026-09-09. The sample
   (1993–2013, S&P 500 ETF) and the qualitative claim are corroborated by the
   fetched Limkriangkrai et al. (2023) replication; the strategy performance
   figures are not.
2. **Wu & Jegadeesh "13.2 basis points per day"** MOC-reversal risk-adjusted
   return. Search snippet only; SSRN 3732955 returned HTTP 403.
3. **Wu & Jegadeesh "21% (43%) of the closing auction return reversed at the
   NYSE (Nasdaq) overnight"** and the "3–5 days" dissipation. Search snippet
   only.
4. **FirstRate Data one-time bundle purchase price** (both "Stocks Complete" and
   "Stocks and ETFs Bundle"). Rendered client-side; not present in the raw HTML
   fetched by curl. Only the update subscription prices ($59.95 / $79.95 per
   month) were verified.
5. **Cboe DataShop US equities product prices.** Not published on
   `datashop.cboe.com`; the page directs to sales. This is a "price not
   published, contact sales", not a guess.
6. **Nasdaq Data Link product list and prices.** `data.nasdaq.com/databases`
   returned only the page title on fetch.
7. **Databento per-GB usage rate for historical US equities.** The pricing page
   states "usage-based pricing ($/GB)" without the rate.
8. **Databento XNAS.ITCH history start date.** A search snippet says 2018; the
   dataset, catalog and docs pages are all JavaScript-only and returned no
   content to WebFetch or curl.
9. **The √breadth scaling of information ratio in breadth** (Grinold's
   "fundamental law"), used qualitatively in §0 to explain *why* breadth raises
   annualized Sharpe. The source was not opened, so the scaling is asserted, not
   verified. Nothing numerical in this memo depends on it — §3's numbers come
   from `dsr_power` alone.
10. **Alpaca and Tiingo delisted-symbol coverage, and Tiingo intraday history
    depth.** Not stated on either pricing page.
11. **Brown, Davies & Ringgenberg (2021) sample period, ETF count and
    t-statistics.** Abstract page only; full text paywalled. The "1.1–2.0% per
    month" figure IS verified from the abstract page.
12. **Licensing terms of the `emi.nasdaq.com` public ITCH/NOII archive.** The
    directory listing and its single NOII file (2022-05-09) are verified; the
    terms of use are not.
13. **Massive (Polygon.io) handling of splits, dividends and delisted
    tickers.** "Corporate Actions" is listed as included on all tiers; the
    pricing page does not detail delisted-ticker coverage.

**Kibot** was not fetched at all in this pass and is therefore wholly
unassessed, noted here so its absence is explicit.

---

## 7. Files in this directory

* `INTRADAY_DATA_SCOPING.md` — this memo.
* `power_grid.py` — the §3 computation; calls `dsr_power` unchanged and includes
  the reproduction check against `criteria_fix_2026-09-09`.
* `power_grid_output.txt` — its committed output.

Worktree `.claude/worktrees/intraday-scoping`, branch
`intraday-scoping-2026-09-09`. **Not merged to main.**
