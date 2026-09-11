# Forced-flow mechanisms in the micro-cap / illiquid corner — sourcing report, 2026-09-12

Agent: research-sourcing sub-agent (Opus), worktree `member-census-2026-09-12`. Nothing was built,
no backtest was run, no DB row was written, no `app/` file was touched. Every number below is either
quoted from a source file committed under `sources/` (with its SHA-256 in `SOURCES.md`) or is
explicitly labelled **my calculation** with the arithmetic shown. Everything I tried and failed to
establish is in `COULD_NOT_VERIFY.md`.

## 0. The question this answers

Per `handover_2026-09-11/HANDOVER_2026-09-11.md` §2 and `member_census_2026-09-12/`, a candidate is
worth building only if BOTH hold:

- **(i)** an identifiable participant is **forced** to trade against the position regardless of price
  (a mandate, a rule, a redemption, a listing requirement — not an inattention or underreaction story);
- **(ii)** **large capital cannot profitably collect it**, which in US equities means roughly below the
  NYSE 20th market-cap percentile (HXZ's own microcap definition) or a similarly closed corner.

The 2026-09-11 round established a hard arithmetic constraint that governs everything here:
`sigma_SR = sqrt(1/years)`, so on the Alpaca window (10.683 y) the minimum source-claimed **net**
annualized Sharpe that returns PROCEED at `n_local=8` is **2.416**
(`candidate_sourcing_2026-09-11/power_checks/ADMISSIBILITY_THRESHOLDS.txt`). No candidate in this
report comes within a factor of two of that. That is the headline, and it is a statement about the
published literature, not about any one mechanism.

---

## 1. Summary table (ranked)

Rank is by *how close the candidate comes to satisfying (i) AND (ii) on a source I actually read*,
not by claimed effect size.

| # | key | mechanism (one line) | who is forced, by what rule | claimed effect (source's units) | net Sharpe / t | (i) | (ii) | verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | `microcap_delisting_forced_exit` | Institutions must exit a stock when it is involuntarily delisted from a listed exchange to the Pink Sheets / OTC | Regulated funds: "SEC rules preclude most institutions from holding unlisted shares, thus forcing owners to move out of these shares" (Macey-O'Hara-Pompilio 2004, fn. 45) | Avg close falls $0.95 (last NYSE day) → $0.48 (first Pink Sheet day); $100 equal-weighted in the delisted names rises to ~+30% within the first ~30 trading days then ends −20% by day 60 | none given; **gross**, and the authors themselves say costs kill it | **YES** | **YES** | **HOLD — the only candidate where both criteria plausibly hold, but the paper's own cost statement is near-fatal** |
| 2 | `microcap_fund_forced_sale_thin_capacity` | Redeeming open-end funds must sell predetermined holdings; someone must carry the inventory and demands a premium, concentrated in thin-capacity names | Open-end mutual funds facing investor redemptions (Eq. 34-36, Wang 2026) | Fama-MacBeth slope on `AbsInv`, fund-owned + low dollar volume: **97 / 375 / 730 bp** at 1/3/6m, t = 2.06 / 3.79 / 5.14 (Table 8). Portfolio sort, EW H−L: 44.09 bp/mo, t = 2.85 (Table 9) | **0.6076 gross** (my calculation, see §3.2) | **YES** | **NO as published** — the paper's headline tables *exclude* microcaps (NYSE 20th pct) by construction | **DECLINE at sourcing** (power, and the source does not cover the corner we need) |
| 3 | `russell_reconstitution_microcap` | Annual Russell reconstitution forces index funds to buy additions / sell deletions on a published date | Russell-tracking index funds, by index rules | 1000 cut-off: **+5.0% June addition effect, t = 2.65** (Table 4, bw 100, p=1); deletion +5.4%, t = 3.00 (Table 5); 1996-2012. **3000 cut-off (the microcap boundary): addition +3.6%, t = 1.45; deletion +3.3%, t = 1.25 — both insignificant** (Table 8, 2005-2012) | not derivable (no portfolio return series) | YES | **NO** — this is the most-arbitraged calendar event in US equities | **DECLINE** — insignificant exactly where we need it, and unimplementable on free data |
| 4 | `microcap_tax_loss_selling` | December tax-loss selling by taxable holders, concentrated in small/micro caps | Taxable individual and institutional holders, by the US tax code | (project's own prior result, not a new source) | — | partly | partly | **DECLINE — already falsified in this project** (June placebo +0.5259 / +0.5343 beat the December spec) |
| 5 | `spac_trust_redemption_floor` | SPAC common shares are redeemable at the pro-rata trust value, so the downside is structurally floored | SPAC sponsor/trust, by charter | Gahng-Ritter-Zhang: EW annualised SPAC-period return **23.9%** over an avg 16-month hold, 458 SPAC IPOs 2010-2020; worst SPAC in sample **+0.51%** annualised | — | YES | partly (the 15% redemption cap binds concerted large holders) | **ALREADY REVIEWED 2026-09-11** (hunting-ground rank 4); not re-sourced here. Bet count ~42/yr and the 2021+ cohort is low single digits |
| 6 | `cef_openending_liquidation` | Closed-end fund open-ending / liquidation forces the fund to sell its whole book | CEF board / activist-forced liquidation | — | — | YES | ? | **NOT SOURCED** — no primary academic source found for a *tradable underlying-stock* effect (see COULD_NOT_VERIFY §B.2) |

---

## 2. The anti-evidence, first

I put this before the candidates because two of the three papers below are strong enough to
disqualify a whole branch of the literature, and reporting the claims before the critique would
overstate what is here.

### 2.1 Wardlaw (JF 2020) — the flow-pressure measure is partly a realized return

Fetched: `sources/wardlaw_2020_repec_abstract.html`. **Abstract verbatim:**

> "A large and rapidly growing literature examines the impact of misvaluation on firm policies by
> using mutual fund outflow‐induced price pressure to isolate nonfundamental price variation. I
> demonstrate that the standard approach to computing outflow‐induced price pressure produces a
> measure that is inadvertently a direct function of a stock's actual realized return during the
> outflow quarter, raising doubts about its orthogonality to fundamentals. After removing these
> direct measurements of return, outflows generate a fairly negligible quarterly decline in returns,
> with no subsequent reversal, and many established results in this literature no longer hold. I
> provide suggestions for future analysis."

This is the single most important sentence in this report for candidate 2: **"a fairly negligible
quarterly decline in returns, with no subsequent reversal"**. The reversal *is* the trade. If there
is no reversal, there is no candidate 2.

**What I could not verify**: the magnitude behind "fairly negligible", which table it is in, and
whether Wardlaw's critique lands on Coval-Stafford's Eq. (4) *unweighted count* measure as hard as it
lands on Edmans-Goldstein-Jiang's share-weighted MFFlow. SSRN returned HTTP 403 and the Wiley
full text is paywalled. **I read the abstract only.** See COULD_NOT_VERIFY §A.1. This matters because
this project's own `coval_stafford_firesale` build deliberately implemented the unweighted count
(`coval_stafford_firesale_RESULTS.md` §1, Correction 2) — the version Coval & Stafford themselves
preferred precisely because share-weighted measures are "highly sensitive to reporting errors in fund
holdings". Whether that choice also dodges Wardlaw's critique is **unresolved and is a prerequisite
for any revival of candidate 2.**

A second, independent methodological attack exists and I did not read it: Berger, "Selection Bias in
Mutual Fund Fire Sales" (JFQA) — title and venue only, from a search-result listing. Not cited for
any claim.

### 2.2 Hou, Xue & Zhang — microcap anomalies are "more apparent than real"

From the extract already committed in this repo on 2026-09-11
(`candidate_sourcing_2026-09-11/sources/hou_xue_zhang_replicating_anomalies.txt`), verbatim:

> "Microcaps not only account for 60% of the number of stocks but are also the most costly to trade…
> Because of high costs in trading these stocks, anomalies in microcaps are more apparent than real."

and

> "With microcaps alleviated via New York Stock Exchange breakpoints and value-weighted returns, 286
> anomalies (64%) including 95 out of 102 liquidity variables (93%) [are insignificant]."

This is the direct answer to the strategic hope behind the whole micro-cap-corner direction. The
corner where criterion (ii) is satisfied is the same corner where HXZ say published effects do not
survive costs. Criterion (ii) and tradability are in **structural tension**, not merely in practical
tension. Nothing in today's sourcing resolves that tension; candidate 1 is the only one that even
addresses it, and it addresses it by having an effect large enough (a ~50% price drop) that a 25%
spread might not eat all of it — which is a statement about how bad that corner is, not how good.

### 2.3 Appel, Gormley & Keim — the Russell setting is not reproducible on public data

Fetched: `sources/appel_gormley_keim_russell_rd_wharton.pdf`. Verbatim (§3.1):

> "It is not possible to estimate equation (1), however, because the end-of-May market capitalization
> used by Russell to determine firms' index assignment at reconstitution is not observable to the
> econometrician. Specifically, Russell uses a proprietary market capitalization value that does not
> perfectly match up to market capitalizations reported in publicly-available databases like CRSP.
> … using 2006 end-of-May market caps, as calculated by CRSP, one finds that only 68% of the firms
> ranked between 950 and 1,000 were included in the Russell 1000; the remaining 32% were assigned to
> the Russell 2000 even though they were among the 1,000 largest market caps according to CRSP."

and, on why:

> "A second possibility is that Russell intentionally adds noise to the assignment process to avoid
> investors being able to perfectly predict which stocks will switch indexes during the
> reconstitution. Given the magnitude of the stock price effects of such switches (see Chang, Hong,
> and Liskovich 2015), being able to predict index switches represents a profitable trading
> opportunity and Russell may want to avoid facilitating such trades. Consistent with this
> possibility, Russell has been unwilling to share the historical market caps used to determine index
> assignments".

So: even with CRSP (which this project does not have), a third of the names near the cut-off are
misassigned. This project has **no Russell constituent history at all** and no market-cap history
other than what it can build from Alpaca prices × a share count it does not hold point-in-time.
Candidate 3 is not implementable here even before the power question.

---

## 3. Candidates, in rank order

### 3.1 `microcap_delisting_forced_exit` — rank 1, HOLD

**Mechanism.** A US-listed company fails a continued-listing standard, the exchange delists it
involuntarily, and it begins trading on the Pink Sheets / OTC. Regulated institutional holders must
exit, regardless of price, because they may not hold unlisted shares.

**Who is forced, by what rule.** Macey, O'Hara & Pompilio (2004 WP), footnote 45, verbatim:

> "One factor that may be influencing the initial behavior of these stocks is portfolio rebalancing,
> as the clientele of investors changes to reflect the unlisted status of these shares. SEC rules
> preclude most institutions from holding unlisted shares, thus forcing owners to move out of these
> shares."

That is criterion (i) stated by the authors themselves, as a mandate, not a preference. And unlike
every other candidate here, the corner is definitionally closed to large capital: the security is no
longer listed, so the institutions that *could* absorb it are the ones legally excluded.

**Claimed effect, in the paper's own units** (§III, Table 6/7 discussion):
- "on the last day of NYSE trading, the average stock in our sample closed at a price of $0.95; on
  the first day of Pink Sheet trading the average stock closed at $0.48." For the 9 largest names,
  $0.57 → $0.16. Excluding bankruptcies, $1.09 → $0.59. The authors' summary: "Essentially, being
  'evicted' reduces the stock's value by almost one-half."
- "Figure 2 plots the value of $100 invested in an equally weighted portfolio of our sample stocks
  formed on their first day of Pink Sheet Trading… After 60 trading days, the value of both
  portfolios has declined, with the overall sample losing approximately 20% of value and the larger
  firms losing more than 40%. Interestingly, the values of both portfolios increase over the first
  weeks of trading, with the overall sample portfolio trading above (and at times almost 30% higher)
  its initial value for more than the first 30 trading days."

**Sample.** 63 forced NYSE delistings in calendar year **2002**; 57 moved to the Pink Sheets, and
those 57 are the trading sample. **One year, one exchange, N=57.** This is the binding weakness.

**Net of costs?** **No, and the authors say so directly**, in the sentence immediately following the
figure discussion:

> "Given both the meager trading volume in small stocks, and the large spreads in all stocks,
> however, it is implausible that returns remain positive when overall trading costs are properly
> included."

Their measured costs: median percentage spread **25%** on the first day of Pink Sheet trading;
13.60% (middle 20 stocks) to 14.93% (smallest 27) at 60 days; spreads "tripling" and volatility
"doubling" versus NYSE.

**Derived Sharpe / t.** **None is derivable.** The paper reports a cumulative portfolio path in a
figure, no t-statistics on a return series, no Sharpe. I decline to invent one from a figure
description. This alone means the candidate cannot pass `sourcing_power_check`, whose
`--claimed-sharpe` contract is a *net* Sharpe.

**Bets per year.** The paper's own framing: "Since 1995 more than 7300 firms have delisted from U.S.
stock markets, with almost half of these being involuntary." **My calculation:** 7,300 × ~0.5 ÷ ~8.5
years (1995 → mid-2003) ≈ **430 involuntary delistings/year across all US markets** — an
order-of-magnitude figure from the paper's own two numbers, not a measurement; 2002 was a peak year
and I have not checked the rate in the 2016+ window we would actually trade. NYSE alone in 2002 was
63. At a portfolio level with a ~30-day hold this is roughly monthly rebalancing, so ~12
portfolio-level bets/year with a few dozen names each.

**Post-publication decay.** Not reported by this paper and no follow-up found. Two structural changes
since 2002 that I did **not** verify and that plausibly matter more than decay: SEC Rule 15c2-11 (as
amended Sept 2021) pushed many non-reporting OTC names to the "Expert Market" where broker-dealers
may not publish quotes, and Alpaca's tradable universe almost certainly excludes them. Logged, not
measured.

**Free data path.** Alpaca `/v2/assets` gives 19,182 *inactive* US equities and ~2,867 inactive on
listed exchanges; Alpaca SIP daily bars from 2016-01-04 cover delisted names (verified 2026-09-11,
`alpaca_delisted_coverage_2026-09-11/`). SEC EDGAR Form 25 / 25-NSE filings date the delisting.
**What is missing:** (a) Alpaca almost certainly does not carry Pink Sheet / OTC post-delisting bars
— the trade in this paper happens *after* the last listed bar, which is precisely where our data
ends; (b) no OTC quote/spread data at all, so the 13-25% spread that the authors say kills it cannot
even be modelled; (c) EDGAR is ingested for ~503 large caps only, so Form 25 dating would need a new
roster build.

**(i)** YES — stated as a legal constraint by the source, on holders who must sell into an
unlisted market. **(ii)** YES — the security leaves the listed venue, which is exactly the exclusion
that keeps large regulated capital out.

**Verdict: HOLD, do not build.** Both criteria pass, which no other candidate manages, and that is
why it is rank 1. But it fails on three independent grounds that a pre-check would catch: no
derivable net Sharpe (so no admissible `--claimed-sharpe`), a one-year N=57 sample, and — decisively
— the trade lives on Pink Sheet bars that our only delisted-coverage data source does not provide.
**The cheapest next step is not a build, it is a 30-minute data probe**: pull 20 known post-2016
involuntary NYSE/Nasdaq delistings and check whether Alpaca returns any bars after the delisting
date. If it returns nothing, this candidate is closed on data and should be written into
`DECLINED_AT_SOURCING.md` as such.

### 3.2 `microcap_fund_forced_sale_thin_capacity` — rank 2, DECLINE

**Mechanism.** Open-end funds hit by investor redemptions must sell their predetermined holdings.
Someone must warehouse the inventory; that someone requires a return. The premium should be largest
where trading capacity is thinnest.

**Source.** Ziyao Wang, "Residual Supply and the Price of Risk Absorption", arXiv:2605.30672v1,
29 May 2026. **This is an unrefereed preprint by a single author in a mathematics and statistics
department**, and I weight it accordingly. Sample: US common stocks, **January 2003 – 2024**
(490,162 no-microcap stock-months, 5,559 PERMNOs).

**Measure** (§3.2, verbatim, Eq. 34-36): flow is `Flow_{f,t} = (TNA_{f,t} − TNA_{f,t−1}(1+R_{f,t})) /
TNA_{f,t−1}`; `FIT_{i,t} = Σ_f w_{f,i,t−1} Flow_{f,t} TNA_{f,t−1}`;
`ForcedSale_{i,t} = −min(FIT_{i,t}/ME_{i,t−1}, 0)`. This is the Edmans-Goldstein-Jiang FIT family —
the one Wardlaw attacks — not Coval-Stafford's unweighted count.

**Claimed effect** (Table 8, verbatim numbers): restricting to above-median fund exposure and
splitting by dollar volume, `AbsInv` Fama-MacBeth slopes are **4.54 / 39.03 / 91.77 bp** at 1/3/6m
(t = 0.22 / 0.74 / 0.93) for high dollar volume, and **96.60 / 375.46 / 729.63 bp** (t = 2.06 / 3.79 /
5.14) for low dollar volume. Portfolio sorts (Table 9): no-microcap equal-weighted H−L **44.09 bp/mo,
t = 2.85**; **value-weighted 20.92 bp/mo, t = 1.29** — i.e. the effect is an equal-weighting effect.

**Derived Sharpe — my calculation.** For a monthly series, annualized SR = t/√(years). Table 9's
EW H−L: `2.85 / √22 = 0.6076`. Cross-check by the other route: 264 months, monthly SR = 2.85/√264 =
0.17541, ×√12 = 0.6076 — same to 4 dp. For the Table 8 low-dollar-volume 1m slope, `2.06/√22 =
0.4392`, but **that is a Fama-MacBeth rank-spread coefficient, not a tradable portfolio return**, so
I do not treat it as a Sharpe claim. The 3m and 6m slopes use overlapping horizons and their
t-statistics are not convertible at all.

**Net of costs?** **No.** The paper models trading costs *theoretically* (they appear in the pricing
restriction, §2) but reports no net-of-cost return and no spread assumption. 0.6076 is **gross**.

**Bets per year.** Monthly rebalance of a cross-sectional sort = **12 portfolio-level bets/year**.

**Decay evidence.** None reported. The paper does not cite Wardlaw at all — I checked:
`grep -c -i wardlaw` on the extracted text returns **0** — despite building on the exact measure
Wardlaw's JF 2020 paper says is partly a realized return. That is a serious omission in a 2026
preprint and is my main reason for ranking it below candidate 1 on quality.

**The fatal structural point for us.** §3.1, verbatim: "no-microcap sample keeps stocks with market
equity above the **20th percentile of New York** [Stock Exchange]". The headline tables — 8 and 9 —
are all "No microcap". **The paper deliberately excludes exactly the corner criterion (ii)
requires.** Its "thin capacity" split is low-dollar-volume *within the non-microcap universe*. §4.4
even explains why, verbatim: "Very small stocks can be noisy and may have little mutual fund
ownership". That last clause is the same wall this project already hit: `coval_stafford_firesale`
was untestable because ownership breadth in the S&P 500/600 was 643/246 owners per stock against the
paper's 47 — and going *down* in size makes fund ownership sparser still, which helps breadth-based
identification and hurts the *existence* of a forced fund seller. Both directions cannot be satisfied
at once, and no source I read resolves it.

**(i)** YES. **(ii)** NO as published — the source's own sample excludes the corner.

**Verdict: DECLINE_AT_SOURCING.** On power: 0.6076 **gross** against a 2.416 **net** admissibility
threshold on the 10.683-year Alpaca window — a factor of 4 short before any cost is charged. On
economics: the only published claim covers the non-microcap universe. On evidence quality: an
unrefereed preprint that does not engage the field's standing methodological critique.

**Free data path, for the record.** SEC N-PORT bulk quarterly holdings 2019q4-2026q2 already
downloaded (currently filtered to S&P 500/600 CUSIPs; the full zips are ~440 MB/quarter and can be
re-pulled). **Missing:** a CUSIP→ticker map for micro-caps (the single hardest gap — N-PORT reports
CUSIP/ISIN/LEI, Alpaca reports tickers, and no free crosswalk covers delisted microcaps);
point-in-time market-cap history below the S&P 600 (needs a point-in-time share count we do not
have); and the 2019q4 start gives **6.8 years**, on which the admissibility threshold is worse still.

### 3.3 `russell_reconstitution_microcap` — rank 3, DECLINE

**Mechanism.** Russell reconstitutes annually on end-of-May market caps; funds tracking the index
must buy additions and sell deletions.

**Source.** Chang, Hong & Liskovich, NBER WP 19290 (Aug 2013; RFS 28(1) 212-246, 2015). Abstract
verbatim: "Stocks are assigned to indices based on their end-of-May market capitalizations. Stocks
ranked just below 1000 are in the Russell 2000. The indices are value-weighted so these stocks
receive index buying whereas those just above 1000 have close to none. Using this random assignment,
we find price effects for both additions and deletions."

**Claimed effect.** At the **1000 cut-off** (1996-2012), Table 4, bandwidth 100, p=1: June addition
effect **0.050, t = 2.65** (p<0.01); Table 5, same spec, deletion **0.054, t = 3.00** (p<0.01). The
authors' own baseline: "This 5% figure is our baseline estimate." No significant effect in May
(a valid-design check) and none in July-September, so "there are no significant reversals."

**At the 3000 cut-off — the actual microcap boundary and the only part of this paper that speaks to
criterion (ii)** — Table 8 (sample restricted to **2005-2012** because Russell 3000E does not exist
before 2005), bandwidth 100, local linear: **addition June 0.036, t = 1.45; deletion June 0.033,
t = 1.25 — neither significant.** The authors' own reading, verbatim: "This is not economically
small. Our interpretation is that we do not have enough observations in the bottom cut-off given our
data limitations… We attribute this bouncing around of estimates to a lack of data. It might also be
due to illiquidity in the bottom end of the index and the rebalancing delay of indexers."

**Derived Sharpe.** Not derivable — an RD coefficient on a June cross-section is not a return series.
For scale only, **my calculation**: 2.65/√17 = 0.643 at the 1000 cut-off and 1.45/√8 = 0.513 at the
3000 cut-off; **both are meaningless as Sharpes** (one observation per name per year, no portfolio
return series) and are shown only to make clear that even the generous conversion lands far below
2.416.

**Net of costs?** No — raw monthly returns throughout.

**Bets per year.** **One reconstitution per year.** At the 3000 cut-off the estimation samples are
822-835 name-years over 8 years, so ~100 names/year on one date. One portfolio-level bet per year is
the worst bet count of any candidate in this project's history.

**Decay / structural change.** Russell's **banding policy from the 2007 reconstitution** cut index
switching from ~10% of Russell 1000 firms per year to ~3% (CHL §2, and AGK §2.2), which is a ~70%
reduction in the number of forced trades. There is **no banding at the 3000 cut-off** (CHL, line:
"There is no banding for the 3000 cut-off") — which is the one thing favouring the microcap version.

**Free data path.** **There isn't one.** Per AGK §3.1 (quoted in §2.3 above) the assignment variable
is proprietary and unobservable; 32% of names near the 2006 cut-off are misassigned relative to CRSP;
Russell will not release the historical caps. This project has neither CRSP nor Russell constituent
history, and no point-in-time share count to rebuild market caps from Alpaca prices.

**(i)** YES — index funds are mandated. **(ii)** NO — the reconstitution is the most heavily traded
scheduled liquidity event in US equities, and CHL themselves note that predicting switches "represents
a profitable trading opportunity" that Russell may be actively obscuring.

**Verdict: DECLINE.** Insignificant precisely at the microcap boundary, one bet per year, and not
implementable on free data.

### 3.4 `microcap_tax_loss_selling` — rank 4, DECLINE (already falsified here)

Not re-sourced from the literature, because this project has already run it and the result is
decisive against it. `dormant_pool_2026-09-09/POPULATE_REPORT.md`: the **June placebo** specs scored
**+0.5259** (`tax_loss_selling_turn_of_year/tls_jun_placebo_signed_h21`, n=2932) and **+0.5343**
(`small_cap_tax_loss_selling_turn_of_year/tls_jun_placebo_signed_h21`, n=1677) — both *higher* than
the December specs (+0.4965 and +0.4152). A placebo that matches or beats the real season means the
Sharpe is not coming from the December tax mechanism. Both families "remain NOT PARKED on attribution
grounds". Going further down in size does not fix an attribution failure; it changes the universe
while leaving the placebo logic identical.

The literature side is in the same place: the mechanism is well established for small caps
(Sias & Starks 1997 and the Roll/Reinganum line), but I did not fetch any of it, because no
literature claim can overturn this project's own placebo result on its own data. Recorded as a
deliberate scope decision in COULD_NOT_VERIFY §A.3.

**(i)** partly — the tax code creates the incentive but compels nobody to trade on a date.
**(ii)** partly. **Verdict: DECLINE, on this project's own evidence.**

### 3.5 `spac_trust_redemption_floor` — rank 5, already reviewed

The SPAC trust-redemption floor is a genuine mandated-flow mechanism (the trust must pay pro-rata
NAV on redemption) and it was reviewed in full on 2026-09-11
(`hunting_ground_review_2026-09-11/`, ranked **4th** of the hunting grounds, T1+T2). Gahng, Ritter &
Zhang (RFS 2023), 458 SPAC IPOs Jan 2010 - Dec 2020: equal-weighted annualised SPAC-period return
23.9% over an average 16-month hold; even liquidated SPACs +2.0%; the worst SPAC in the sample
+0.51% annualised. The authors' own warning, quoted in that review, is that the excluded 2021 cohort
(613 IPOs) "appear to be producing annualized SPAC period returns in the low single digits".
**Bet count: 458/11 ≈ 42 SPACs per year (my calculation), and issuance collapsed after 2022.**
Not re-sourced today; listed here only so the census of mandated-flow mechanisms is complete.

### 3.6 `cef_openending_liquidation` — rank 6, NOT SOURCED

Closed-end fund open-ending, tender offers and liquidations force a fund to sell its entire book, and
CEFs hold illiquid small names. I searched for a primary academic source measuring a *tradable
effect on the underlying stocks* and found none — only practitioner material on the CEF discount and
on interval/tender-offer fund structures. **Declined for want of a source, not on evidence against
it.** Details in COULD_NOT_VERIFY §B.2.

---

## 4. What I would take to a pre-check, and why

**Nothing should be built.** Two things are worth the small amount of work they cost:

1. **`microcap_delisting_forced_exit` → a data probe, not a pre-check** (~30 min). It is the only
   candidate where (i) and (ii) both genuinely hold, and the reason is structural rather than
   statistical: the security leaves the venue where large regulated capital is allowed to operate.
   But the entire trade happens on Pink Sheet bars *after* the last listed bar, and we have never
   checked whether Alpaca returns anything there. Probe first; if the bars do not exist, close it and
   write it into `DECLINED_AT_SOURCING.md` on data grounds.
2. **Resolve the Wardlaw-vs-Coval-Stafford question** (~1 h, needs the JF full text). This project
   implemented Coval-Stafford's unweighted count, which may be immune to the critique that killed the
   share-weighted measure. If it is immune, the existing `coval_stafford_firesale` work is worth more
   than its own power failure suggested; if it is not, candidate 2 and everything descended from FIT
   is closed for good. Either answer is cheap and permanent. It needs access to the paper.

**I would not take candidate 2 to a pre-check.** 0.6076 gross against a 2.416 net threshold is not a
borderline call, and the source excludes our corner by construction.

## 5. The strongest anti-evidence, in one place

1. **Wardlaw (JF 2020)**, abstract: removing the embedded realized return leaves "a fairly negligible
   quarterly decline in returns, **with no subsequent reversal**, and many established results in this
   literature no longer hold." The reversal is the trade.
2. **Hou, Xue & Zhang**: "Because of high costs in trading these stocks, anomalies in microcaps are
   more apparent than real"; 64% of anomalies vanish under NYSE breakpoints and value weighting.
   Criterion (ii) and tradability are in structural tension.
3. **Chang, Hong & Liskovich's own Table 8**: at the 3000 cut-off the addition and deletion effects
   are t = 1.45 and t = 1.25 — *insignificant exactly where we need them*, while the 5% effect they
   are famous for lives at the 1000 cut-off, in $1bn+ names.
4. **Appel, Gormley & Keim**: the Russell assignment variable is proprietary and 32% of near-cut-off
   names are misassigned even with CRSP. Not implementable on free data.
5. **Macey, O'Hara & Pompilio on their own result**: "it is implausible that returns remain positive
   when overall trading costs are properly included", with median first-day spreads of 25%.
6. **This project's own June placebo** beating the December tax-loss spec (+0.5259/+0.5343 vs
   +0.4965/+0.4152).
7. **The arithmetic**: `sigma_SR = sqrt(1/years)` means the best thing sourced today (0.6076 gross)
   is a factor of 4 below the 2.416 net Sharpe needed to PROCEED at `n_local=8` on 10.683 years.

## 6. Honest summary

Six mechanisms were examined; **zero are PROCEED-eligible**. One (`microcap_delisting_forced_exit`)
satisfies both criteria on a source I read and fails on data availability and on the absence of any
derivable net Sharpe — it deserves a cheap data probe, not a build. The general finding repeats the
2026-09-11 one from a new direction: the corner where a forced counterparty exists *and* large
capital is excluded is the corner where costs are 13-25% of the trade, where no published paper
reports a net-of-cost return, and where the papers that do measure the mechanism explicitly exclude
the corner. That is not a failure to look hard enough; it is the same wall, seen from the
forced-flow side.
