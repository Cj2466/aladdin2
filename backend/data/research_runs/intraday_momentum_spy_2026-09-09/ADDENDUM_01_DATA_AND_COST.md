# Addendum 01 — data audit, feed check, and the frozen baseline cost

**Dated 2026-09-09. Written and committed AFTER the bars were pulled and audited
but BEFORE any strategy return was computed.** Nothing here is informed by a
backtest result; every number below is a property of the raw data or of the
source paper's own arithmetic.

`PREREGISTRATION.md` §4 declared that the verdict arm's one-way cost would be
fixed "by a PROCEDURE declared now and frozen in a committed addendum before any
strategy return is computed". This is that addendum. It also reports the §2b
drop counts and the §2c feed check, both of which are data properties.

---

## 1. What was pulled

`data/research_runs/fetch_spy_1min_bars.py`, run 2026-09-09 against
`data.alpaca.markets` with `feed="sip"`, `adjustment="all"`,
`regular_session_only=True`:

* **1,046,038** SPY 1-minute bars, `2016-01-04 09:30 ET` → `2026-09-08 15:59 ET`
* **2,685** SPY 1-day bars over the same window
* Cache: `<MAIN checkout>/backend/data/spy_1min_bars/{SPY_1Min.pkl,SPY_1Day.pkl}`

2,685 sessions × 390 = 1,047,150; the actual 1,046,038 is 99.89% of a
theoretically perfect set.

## 2. Session row counts and the §2b drops (data property, not a result)

| minute bars in session | sessions |
|---|---|
| 390 (full) | **2,656** |
| 380–389 | 5 |
| < 380 | **24** |
| > 390 | 0 |

**29 sessions have fewer than 390 minutes; 24 of those fall below the
pre-registered U3 floor of 380 and are dropped.** They are, verbatim from the
audit:

* **17 half-day early closes** — the day after Thanksgiving, July 3, and
  Christmas Eve in most years (2016-11-25 342, 2017-07-03 338, 2017-11-24 337,
  2018-07-03 345, 2018-11-23 335, 2019-07-03 344, 2019-11-29 320, 2019-12-24
  278, 2020-11-27 352, 2020-12-24 323, 2022-11-25 330, 2023-07-03 308,
  2023-11-24 329, 2024-07-03 348, 2024-11-29 344, 2024-12-24 332, 2025-12-24
  358). These have **no 15:30–16:00 half-hour at all** — the market closed at
  13:00 — so r₁₃ does not exist and the trade is untradeable, not merely
  awkward. This is exactly the case U2/U3 were written for.
* **2 near-half-days** at 377 and 379 (2025-07-03, 2025-11-28), same category,
  caught by U3 rather than U2.
* **1 data gap**: 2019-08-12, 360 bars, last bar starting **15:31** — the only
  session in the sample failing U2. Cause not investigated; it is a vendor gap.
* **4 circuit-breaker days**: **2020-03-09, 2020-03-12, 2020-03-16 and
  2020-03-18**, each at exactly 376 bars — the four Level-1 market-wide
  circuit-breaker halts of the COVID crash. Each lost ~14 minutes to the halt.

**The circuit-breaker drop is disclosed prominently because it cuts against the
paper.** Those four days are the single most volatile days in the sample, and
the paper's Table 6 reports that intraday momentum is *strongest* in the high
first-half-hour-volatility tercile. The U3 rule removes them. **That rule was
pre-registered before the data was examined and is NOT being changed** — a
sensitivity re-run that admitted them would be a post-hoc rule change made after
seeing which days it excludes, which is precisely the move pre-registration
exists to prevent. It is recorded here so the reader can weigh it, and it is
noted as a limitation in the scorecard rather than quietly repaired.

**Net: 2,685 sessions − 24 unusable = 2,661 usable sessions.** The first usable
session has no predecessor and is dropped, and any day whose previous usable
session is more than 5 calendar days back is dropped, so the realized sample is
reported exactly by the runner.

## 3. Feed check (PREREGISTRATION §2c) — it is CONSOLIDATED (SIP), not IEX

Sum of the 1-minute `volume` column per session, against the same endpoint's
`1Day` bar volume for that session, all 2,685 common sessions:

| statistic | minute-sum ÷ daily |
|---|---|
| mean | 0.8306 |
| median | **0.8375** |
| p25 / p75 | 0.8012 / 0.8689 |
| min / max | 0.5513 / 0.9932 |

Spot values:

| date | minute-sum | 1Day bar | ratio |
|---|---|---|---|
| 2016-01-05 | 96,459,261 | 112,719,152 | 0.8557 |
| 2018-02-05 | 254,022,659 | 304,474,048 | 0.8343 |
| 2020-03-16 | 262,416,618 | 300,815,897 | 0.8723 |
| 2022-06-13 | 136,262,812 | 173,443,346 | 0.7856 |
| 2024-08-05 | 112,728,886 | 146,267,391 | 0.7707 |
| 2026-09-08 | 32,407,791 | 44,800,583 | 0.7234 |

**Finding: the free-tier account is returning full consolidated-tape (SIP)
volume for historical SPY minute bars, not IEX-only.** The decisive evidence is
the *absolute level*, not the ratio: SPY's consolidated daily volume runs
30–300M shares and these are 32–262M. IEX's share of consolidated US equity
volume is ~2–3%, which would have put an IEX-only minute-sum in the 1–8M range —
one to two orders of magnitude below what came back. This closes the caveat
raised in `ADDENDUM_ALPACA_PROBE.md` item 1 for *this* symbol and *this* window,
and it corroborates the 2026-08-26 measurement recorded in
`alpaca_provider.py`'s own header for a different symbol and period.

**The residual ~17% gap is explained and is not a feed problem.** The minute
frame is filtered to regular session bar-starts in [09:30, 16:00), so it
structurally excludes (a) pre-market and post-market volume and (b) the
**closing auction print**, which stamps at 16:00 and is a large single trade —
the project's own scoping memo §M1 quotes Bogousslavsky & Muravyev's measurement
that closing auctions were "7.48% of aggregate daily dollar volume in 2018". Two
excluded buckets of that size fully account for a 17% shortfall. The ratio also
*falls* over time (0.86 in 2016 → 0.72 in 2026), which is the direction the same
paper reports for the auction's growing share.

**Why this does not change the price-return test either way.** Every quantity in
PREREGISTRATION §1a is a ratio of two *prints*. Even on a thin feed, prints sit
inside the consolidated NBBO, so a last-print at 15:59 would differ from the
consolidated last-print by at most a fraction of a one-cent spread on a
$200–700 instrument (≤ 0.14 bps), against half-hour returns whose standard
deviation is measured in tens of basis points. What a thin feed *would* have
damaged is bar *availability* — and §2 shows 2,656 of 2,685 sessions are
complete to the minute, so it did not. **Where it would have mattered and does
not apply here:** any volume-based or auction-based construction. This family
uses neither.

---

## 4. THE PRE-REGISTERED COST PROCEDURE FAILED ITS OWN SANITY CHECK — and what
replaces it

### 4a. What the procedure returned

`PREREGISTRATION.md` §4 declared:

> baseline_one_way_bps = max( 0.5 , round_up_to_0.1bp( EDGE-estimated median
> effective HALF-spread of SPY over the full sample ) )

Run as declared —
`spread_estimator.estimate_effective_spread(open, high, low, close,
window_days=COST_MODEL_WINDOW_DAYS=63)` on the SPY daily OHLC just pulled, 2,623
non-NaN windows:

| statistic | one-way EDGE half-spread |
|---|---|
| median | **12.5859 bps** |
| mean | 16.9481 bps |
| p25 / p75 / p90 | 7.6574 / 18.3604 / 28.2487 bps |

### 4b. Why that number is rejected, on a check that does not use any result

**SPY's minimum tick is one cent.** The median SPY close over this sample is
**$362.04**, so a one-cent *full quoted spread* is **0.2762 bps** and a
half-spread is **0.1381 bps**. The EDGE estimate of 12.59 bps is **91×** the
widest possible half-spread implied by the minimum tick — it asserts a quoted
spread of about **$0.91** on a $362 instrument that quotes a penny wide with
enormous displayed size. That is not a bias, it is the estimator being out of
its domain: it infers spread from daily OHLC serial covariance, and for an index
ETF whose daily *range* (tens to hundreds of basis points) dwarfs its spread by
three orders of magnitude, the spread signal is buried in range noise.
`spread_estimator.py`'s own header already documents an upward bias in the
tight-spread regime ("at 21 days a true 10bps spread recovers as ~21bps") and
raised the window to 63 days to reduce it; that correction is nowhere near
enough at 0.14 bps.

Using 12.59 bps would have charged **63.4% per year** in costs (252 days × 2
crossings × 12.59 bps) against a source-claimed gross return of 6.67%/yr, i.e.
it would have decided the verdict by an estimator artefact — the exact
"manufacture a false negative" failure the scoping memo §4 (M3) warned about in
advance. **The procedure is therefore declared failed, publicly, rather than its
output being quietly used or quietly rounded down.**

### 4c. The replacement, fixed here before any strategy return exists

**`baseline` (THE VERDICT ARM) = 1.0 bp one-way**, i.e. 2.0 bp per traded day
(entry at 15:30 + exit at 16:00), i.e. **5.04% per year** on a
trade-every-day schedule.

Justification, all from sources or arithmetic, none from a result:

* It is **7.2× SPY's own quoted half-spread** at the sample-median price
  (0.1381 bps), and 3.6× its entire quoted spread. The margin is deliberate: it
  is there to cover market impact at the 15:30 entry and, more importantly, the
  closing-auction impact at the 16:00 exit — which the paper explicitly assumed
  away ("there will be no bid/ask spread effect here") and which the project's
  own memo §M1 measures at ~8.1 bps mean absolute deviation. 1 bp is ~12% of
  that deviation, a modest but non-zero participation charge.
* It is **4× the paper's own total round-trip spread charge** (the paper charges
  0.5 bp for the whole round trip; this charges 2.0 bp), so the verdict arm can
  never be accused of being more generous than the source.
* It **honours the pre-registered 0.5 bp floor** (doubled), which was the only
  part of the failed procedure that was anchored to a real cited number.
* It does **not** model commissions. US retail equity commissions went to zero
  in 2019; the paper's 2.52%/yr commission bound is obsolete, and charging it
  today would be the mirror-image error to 4b.
* No overnight borrow is charged on the short leg: the position is held for 30
  minutes and closed at the close. Stated, not silently omitted.

Two additional arms are reported at every rung so nothing rests on this choice:

| arm | one-way bps | annual cost at 252 traded days | role |
|---|---|---|---|
| `cost_free` | 0.0 | 0.00% | attribution only, never a verdict input |
| `spy_tick` | 0.1381 | 0.696% | **informational**: SPY's own quoted half-spread at the sample-median close — the most optimistic defensible number |
| `baseline` | **1.0** | **5.04%** | **THE VERDICT ARM** |
| `conservative` | 5.0 | 25.20% | `intraday_patterns.INTRADAY_COST_BPS`, the project-wide cross-sectional default |

The **break-even one-way cost** is reported for the best non-control spec, so a
reader can see exactly where the verdict flips rather than having to trust the
arm.

### 4d. The observation that matters most, and it needs no result at all

**This strategy is cost-dominated by construction, and that can be shown from
the paper's own numbers before running anything.** It opens and closes a
position every single trading day for a 30-minute hold, so it pays 504 crossings
a year against a source-claimed *gross* return of 6.67%/yr with a 6.19%/yr
standard deviation. Applying the arms above to the paper's own Table 5 row:

| one-way cost | annual cost | paper's gross 6.67% → net | implied Sharpe (σ = 6.19%) |
|---|---|---|---|
| 0.0 bp | 0.00% | 6.67% | 1.08 (the paper's own) |
| 0.1381 bp (SPY tick) | 0.70% | 5.97% | 0.96 |
| **1.0 bp (verdict arm)** | **5.04%** | **1.63%** | **0.26** |
| 5.0 bp (conservative) | 25.20% | −18.53% | −2.99 |

So **even a perfect 1993–2013-strength replication would net a Sharpe of about
0.26 at the verdict arm's cost**, and the whole claim lives inside the first
1.3 bps per side. That is arithmetic on Table 5, not a finding about 2016–2026,
and it is written down here before the 2016–2026 numbers exist so that it cannot
later be mistaken for a rationalisation of whatever they turn out to be.

It also means the pre-registered power block (PREREGISTRATION §5) is, if
anything, **generous**: it uses the paper's *gross* 1.08 as the claimed effect
while the test measures a *net* series.
