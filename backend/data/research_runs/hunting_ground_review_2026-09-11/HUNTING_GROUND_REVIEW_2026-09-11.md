# Hunting-Ground Review — where can a small participant structurally earn?
**Date**: 2026-09-11 · **Type**: literature/evidence review, not a signal test. No DSR,
pre-registration, scorecard or preservation_score machinery applies here; nothing here is a
registration or a claim of an edge.

**The one rule in force**: every factual claim below is either (a) backed by a document I actually
fetched and read — listed in `sources/SOURCES.md` with URL, fetch date and SHA-256 — or (b) explicitly
tiered **T4 (RECALLED-NOT-VERIFIED)**, **COULD-NOT-ACCESS**, or **H (hypothesis)**. Hypotheses are
segregated in `HYPOTHESES.md`. Everything I tried and failed to source is in `COULD_NOT_VERIFY.md`.

**Evidence tiers**: **T1** peer-reviewed / regulatory / audited document, read by me · **T2** working
paper or reputable institutional report, read by me · **T3** credible secondary source read by me
(with a stated reason it is credible) · **T4** recalled, not verified · **H** hypothesis, no evidence claimed.

**Sources actually read**: 16. Sources attempted and blocked: 7 (see `COULD_NOT_VERIFY.md`).

---

## 0. The short answer

The public record contains **very little** direct evidence of a persistently profitable small
participant, and a great deal of evidence that the obvious places to look are already taken. But the
record is not uniformly negative, and it is negative for a *specific, legible reason* that is itself
the most useful output of this review:

> Every documented persistent profit-earner I could source earns it from a **structural position**
> — a venue seat, an order-flow relationship, a leverage/tax structure, a latency rank, an IPO
> allocation — and **not** from a superior forecast of a public data series. Where profit *is*
> available without a structural position, it is available because the capital required is too small,
> the venue too new, or the legal/operational friction too irritating for a large firm to bother.

That reframes the hunting question. The grounds worth ranking are not "which anomaly still works"
but "which frictions are too small to be worth an institution's time and are legally/operationally
reachable by one person". Sections 1–5 assemble the evidence; Section 6 ranks.

---

## 1. Academic evidence on who actually profits

### 1.1 Retail day traders: comprehensively, catastrophically negative — **T2**

Chague, De-Losso & Giovannetti, *Day trading for a living?* (13 June 2020) observe **every**
individual who began day-trading mini-Ibovespa futures in Brazil 2013–2015 — 19,646 people, the
whole population from the CVM regulator, not a survey sample. Of the 1,551 who persisted **more than
300 trading days**:

- **97% lost money** (net of exchange and brokerage fees).
- **17 people (1.1%)** earned more than the Brazilian minimum wage (US$16/day).
- **8 people (0.5%)** earned more than a starting bank teller's salary (US$54/day).
- The single best trader in the whole population earned **US$310/day with a daily standard deviation
  of US$2,560** — a daily Sharpe of about 0.12, i.e. an annualised Sharpe of roughly 1.9 *for the
  single luckiest-or-best participant out of 19,646*, which is exactly the number you would expect
  from selection alone. (The Sharpe arithmetic is mine, from their reported mean and s.d.; the
  0.12 = 310/2560 and 1.9 ≈ 0.12·√252 are my calculation, not theirs.)
- The eight successful traders' daily s.d. ranges US$632–3,308 — all "with great volatility".
- The probability of positive profit **decreases monotonically** with the number of days traded
  (5.7% traded 1 day; 7.9% traded >300). The authors say this pattern is what you see in casino
  roulette, and is the opposite of what self-selection or learning would produce.
- Panel regressions on the 1,551 persisters, with trader fixed effects, find **no learning** — neither
  on a sequential day counter nor on first-third/last-third dummies, gross or net.
- Their profit measure **overestimates** performance: it excludes income taxes, platform costs and course fees.

The authors' own explanation for why their top traders do worse than Barber, Lee, Liu & Odean's
(1992–2006 Taiwan) is directly relevant to this project: *"during their sample, retail day traders
did not have to compete for profits with institutional high-frequency trading (HFTs) algorithms,
which are increasingly active in today's market."* **[T2, source #1]**

**Note (T4)**: Chague et al. *cite* Barber, Lee, Liu & Odean (2014) and Barber et al. (2019) as
finding "less than 3% of the *frequent* day traders present consistent profit". I did not read those
papers. That number is **T4** and should not be used as if sourced. I have no verified Barber & Odean
number of my own (see `COULD_NOT_VERIFY.md` §B.1).

### 1.2 HFT / liquidity provision: profitable, persistent, and explicitly a function of latency rank — **T1**

Baron, Brogaard, Hagströmer & Kirilenko, *Risk and Return in High-Frequency Trading* (2017 working
version of the JFQA 2019 paper), on Swedish equity-market regulatory data:

- **Median HFT firm**: annualised **Sharpe 1.61**, four-factor annualised alpha **9%**, daily
  revenues 6,990 SEK on 64 MSEK daily volume (56.5 SEK per MSEK traded).
- **90th-percentile HFT firm**: annualised **Sharpe 11.1**, four-factor alpha **89%**, 472.2 SEK per
  MSEK traded — i.e. the top decile earns ~8× the median *per unit traded* and ~7× the risk-adjusted return.
- Performance is **persistent**: daily persistence coefficients 0.235 (revenues) and 0.387 (returns),
  statistically significant, higher at monthly frequency. The authors state plainly that persistence
  means "something other than luck drives a firm's performance".
- The driver is **relative latency rank**, not absolute speed: firms that improve their latency rank
  through colocation upgrades see improved performance; the authors treat this as causal via the
  2012 colocation event.
- From five firms' regulatory filings (Virtu 2011-15, KCG 2013-15, GETCO 2009-12, Flow Traders
  2012-15, Jump 2010): **trading profit margins 27.4%–64.5% of trading revenue**; 40–80% of HFT costs
  are *per-trade* fees (brokerage, exchange, clearing, financing); fixed costs (communications, data
  processing, equipment, technology, admin) are only **15–30% of total costs**, and 17.7–27.2% of
  trading revenue across the three 2014 firms. Fixed costs do not scale with revenue. **[T1, source #3]**

The structural reading: HFT profit is a *rent on latency rank*, and the fixed cost of holding that
rank is small relative to revenue — which is precisely why it stays concentrated. A participant with
no colocation has latency rank ≈ last, and this literature says that determines the outcome.

### 1.3 Post-publication anomaly decay: real, measured, and worse where arbitrage is cheap — **T1**

McLean & Pontiff (JF 2016), on 97 published cross-sectional predictors:

- Portfolio returns are **26% lower out-of-sample** and **58% lower post-publication**; the implied
  publication-informed-trading effect is **32% (58 − 26)**.
- Post-publication declines are **greater** for predictors with higher in-sample returns.
- Costly-arbitrage cross-section, in-sample (their β₂ terms): five of six costly-arbitrage variables
  (small size, wide spreads, high idiosyncratic risk, low dividends, and the composite index) have the
  expected sign and are all statistically significant — harder-to-arbitrage portfolios earn more.
  Dollar volume goes the other way and is insignificant.
- **Post-publication, the level effect survives**: the β₂+β₃ sums are correctly signed for all six
  costly-arbitrage variables, and five of six are significant. Predictors concentrated in
  costly-to-arbitrage stocks *retain* more of their return after publication.
- **But the interaction cuts the other way for idiosyncratic risk specifically**: post-publication
  returns are *lower* for portfolios of high-idiosyncratic-risk stocks, p = 0.000. Idiosyncratic risk
  is the only costly-arbitrage variable with a significant correctly-signed in-sample slope, and
  Pontiff (2006) is quoted: *"idiosyncratic risk is the single largest cost faced by arbitrageurs."*
- Post-publication, predictor-portfolio **trading volume and dollar volume rise ~18.7%** and short
  interest on the short-minus-long leg rises significantly — direct evidence that sophisticated
  capital arrives after publication. **[T1, source #2]**

**Implication for this project's 58 negatives**: testing published anomalies post-publication on
large-cap US equities is testing in exactly the corner where McLean & Pontiff measure the largest
decay and the most arriving capital. Fifty-eight honest negatives there is the *predicted* result,
not a surprise or a methodological failure.

### 1.4 Anomalies mostly live in microcaps — and that is a two-edged fact — **T2**

Hou, Xue & Zhang, *Replicating Anomalies* (NBER WP 23394, 2017), replicating 447 anomaly variables:

- With microcaps controlled via NYSE breakpoints and value-weighted returns, **286 (64%) are
  insignificant at 5%**; at t > 3, **380 (85%)** are insignificant; 95 of 102 liquidity variables
  (93%) are insignificant. Of the 161 that survive, the q-factor model leaves 115 alphas insignificant.
- Their stated reason: *"The key word is microcaps."* They report Fama & French (2008) as finding
  microcaps are **3% of total market capitalisation but 60% of the number of stocks**, have the
  highest equal-weighted returns and the largest cross-sectional dispersion in both returns and
  anomaly variables.
- Their verdict on the microcap corner: *"because of high costs in trading these stocks, anomalies in
  microcaps are more apparent than real."* **[T2, source #16]**

This is the central tension of the whole review. The published-anomaly signal is concentrated exactly
where a sub-$1M participant is uniquely unconstrained by capacity — and the authors' own explanation
for why it is not real is a **cost** claim, which is participant-specific, not a claim that the
underlying return does not exist. Whether a specific microcap anomaly survives *this project's*
actual cost structure is an empirical question this review cannot settle, and neither HXZ nor anyone
else I read measures costs for a $100k book.

### 1.5 Anomaly trading costs: the frequency ceiling is measured — **T2**

Novy-Marx & Velikov (NBER WP 20721, 2014), on 23 anomalies:

- Most anomalies with **one-sided monthly turnover under 50%** still generate statistically
  significant net spreads when designed to mitigate costs. **Few with higher turnover do.**
- The **buy/hold spread** (looser exit than entry, i.e. trading hysteresis) is the single most
  effective simple cost-mitigation technique.
- Trading the **high-turnover** strategies "designed with complete disregard for trading costs"
  costs **always more than 1% per month**; transaction costs exceed the gross spread for all but two
  of the high-turnover anomalies; **the effective bid-ask spread alone eradicates the profits of all
  but two**. Only 2 of the high-turnover anomalies get positive weight in the ex-post MVE portfolio,
  raising the max Sharpe by 1 percentage point to 0.76.
- In all cases costs reduce statistical significance, "increasing concerns related to data snooping." **[T2, source #11]**

Read against this project's own power finding (a true Sharpe of 0.5 cannot be certified in ~10 years
of daily data), this is a pincer: the strategies with enough bets per unit time to be *certifiable*
are exactly the ones whose costs exceed their gross spread.

### 1.6 Crypto: arbitrage was real, large, and gated by capital controls — not by speed or capital — **T1**

Makarov & Schoar (JFE 2020), tick data from 34 exchanges across 19 countries:

- Bitcoin price deviations across exchanges **persist for several hours, and in some instances days
  and weeks**.
- Cross-country: US–Korea daily average price ratio **>15%** from Dec 2017 to early Feb 2018, reaching
  **40% on several days** (the "kimchi premium"); Japan–US ~**10%**; US–Europe ~**3%**.
- **Within** the same country, deviations "typically do not exceed 1%, on average."
- Potential arbitrage profit was **often more than $75 million per day**, and they estimate a
  **minimum of $2 billion total** from Dec 2017 to Feb 2018.
- Round-trip transaction costs: blockchain fees peaked ~$40 (fixed, negligible at size); exchange
  fees 0.10–0.25%, with **zero maker fees on most exchanges**; bid-ask spreads 1–10 bp; withdrawal
  fees 10–50 bp. They conclude **round-trip cost ~50–75 bp for large players** — "very low compared
  to the arbitrage spreads we show, and therefore cannot explain the arbitrage spreads we find".
- They also reject governance/hack risk as the explanation (the highest-spread exchanges, Bithumb and
  Korbit, had large volume).
- Their explanation is **capital controls and slow-moving capital**: the trade needs USD in the US
  and generates KRW in Korea, and "if this profit cannot be repatriated seamlessly, arbitrage capital
  can become 'stuck' within a country and thus become scarce." **[T1, source #5]**

This is the single clearest documented case in the whole review of an edge that was **not** protected
by speed or capital, but by a legal/banking friction. It is also the clearest case of an edge that a
solo participant is, if anything, *worse* placed to capture than an institution, because the binding
constraint is cross-border fiat rails and KYC — where institutions have relationships and a retail
person has limits.

### 1.7 Crypto perpetual-futures basis: an explicitly retail-tiered, high-Sharpe result — **T2**

He, Manela, Ross & von Wachter, *Fundamentals of Perpetual Futures* (arXiv v6, July 2024), sample
running from Jan 2020 (BTC/ADA) / Jul 2020 (DOGE) to **11 March 2024**:

- They derive no-arbitrage prices for perpetuals and bounds under trading costs, then trade the
  deviation: open when the futures-spot spread exceeds the cost-tier bound, close on convergence.
- **Bitcoin, "high" fee tier — which their Table 3 explicitly labels "typically an individual
  trader" (30-day volume >$1mn spot, >$15mn perps; spot 0.0675%, futures 0.0144%) — annualised
  Sharpe 1.8 in the introduction, reported as 2.00 in the results section.** Up to **3.5** at the
  zero-fee market-maker tier. Higher for Ether and other cryptos. Significant alphas vs. the Liu-
  Tsyvinski-Wu 3-factor and Cong-Karolyi-Tang-Zhao 5-factor crypto models.
- The **mean absolute deviation** from their no-arbitrage price is **60–90% per year** across tokens,
  while the *mean signed* deviation is statistically indistinguishable from zero — i.e. the anchor
  holds on average and the trade is in the dispersion around it.
- **They report the decay themselves**: "Since the year 2022, the deviation between the futures and
  the spot has become smaller and less volatile. There seems to be a structural break." The strategy
  takes fewer positions and has "significantly lower annualized returns" after that break, though
  Sharpe stays sizeable conditional on a large deviation.
- They also test a **"long-spot only"** variant precisely because "the infrastructure for shorting
  the spot is not well-developed" — i.e. they anticipated the constraint a small participant faces.
- Wider context they give: the narrowing gap is attributed to arbitrage capital and competition, and
  they connect the 2022 break to the downfall of Alameda Research and Three Arrows Capital — that is,
  a *reduction* in competing arbitrage capital coincided with a *narrowing*, which is the opposite
  of what a pure crowding story predicts and is worth noting as an unexplained wrinkle. **[T2, source #9]**

This is the only high-Sharpe, retail-fee-tier, explicitly-cost-inclusive result in the review.

### 1.8 Retail order-flow signals: existed, decayed, and were never cost-tested — **T2**

Ardia, Aymard & Cenesizoglu (arXiv:2403.17095, Mar 2024) re-run Boehmer, Jones, Zhang & Zhang
(JF 2021) — the retail-order-imbalance predictor — on 2016–2021 instead of 2010–2015:

- Predictive power **weakens significantly**. Cross-sectional predictability falls from **11.16 bps
  to 6.02 bps per week**; for small caps, from **20.5 bps to 9.8 bps** per week.
- Predictability for **large-cap and high-price stocks vanishes**; small-cap and low-price weakens.
- The horizon shortens from six-to-eight weeks down to about four.
- **The long-short strategy is no longer profitable at all on the full universe** — alphas are
  insignificant at every horizon and under both trade-signing methods. On **small caps only**, alphas
  remain positive but fall by more than 65% (one-week 0.437% → 0.143%; two-week 0.613% → 0.177%), and
  become insignificant at horizons of eight weeks and beyond.
- Results are also **sensitive to the trade-signing method** (BJZZ's subpenny algorithm vs. the
  quote-midpoint method), which agreed in 2010–2015 and disagreed in 2016–2021.
- Crucially, the replication quotes BJZZ's own disclaimer verbatim: *"We ignore trade frictions and
  transaction costs here, and thus, the results do not have implications for whether outsiders can
  profit from these signals."* **[T2, source #7]**

**Note**: I did not read BJZZ itself (`COULD_NOT_VERIFY.md` §A). All BJZZ numbers here are as
reported by the replication.

---

## 2. Structural record of firms that demonstrably do earn — and what a solo participant cannot copy

### 2.1 Virtu Financial S-1 (2014) — **T1**

Verified verbatim from the SEC filing:

> "As a result of our real-time risk management strategy and technology, we had only one losing
> trading day during the period depicted, a total of 1,238 trading days."

The chart period is **1 January 2009 through 31 December 2013**, and elsewhere in the same filing:
"we have had only one losing trading day since January 1, 2008." **Two material qualifications the
popular retelling drops**: (i) the measure is **Adjusted Net Trading Income**, a **non-GAAP** measure
defined in the filing as market-making revenue plus net interest and dividends **less direct costs**
(brokerage, exchange, clearance) — it is *not* net income and excludes fixed operating costs; and
(ii) the series **includes Madison Tyler Holdings' Adjusted Net Trading Income prior to the July 2011
transaction**, so it is a merged, partly-backward-constructed series.

The structural reason, in Virtu's own words: they make markets "in more than 10,000 securities and
other financial instruments on more than 210 unique exchanges, markets and liquidity pools in 30
countries", generating revenue "by buying and selling large volumes … and earning small amounts of
money based on the difference between what buyers are willing to pay and what sellers are willing to
accept". No one geography or asset class was more than 30% of 2013 Adjusted Net Trading Income. **[T1, source #4]**

**What a solo participant cannot replicate**: 210 venue connections, 30 jurisdictions, market-maker
registrations, clearing memberships, and the volume that makes a sub-basis-point capture economic.
The 1,238-day record is a *diversification* result — the law of large numbers over ~10,000
instruments — not a forecasting result. That is the same mechanism this project's goal statement
aspires to, at a scale of instrument access this project does not have.

### 2.2 Renaissance / Medallion, Senate PSI hearing record (22 July 2014) — **T1**

From the hearing record (opening statements and sworn testimony; the staff report PDF was 403 —
see `COULD_NOT_VERIFY.md`):

- Deutsche Bank and Barclays sold **199 basket options** to more than a dozen hedge funds, used to
  make **over $100 billion in trades** (Levin).
- **"Instead of complying with the 2:1 leverage ratio, the banks offered their hedge fund clients
  leverage as high as 20:1"** (Levin). The option structure also capped Medallion's downside at the
  premium paid — Renaissance's own witness confirmed "RenTec had the risk up to the premium that they
  paid for the option".
- **RenTec's Medallion produced profits of more than $30 billion 1999–2013** through the structure
  (Levin); McCain put it at "in the neighborhood of $34 billion in pre-tax profits" from 60 exercised
  long-term basket options 2000–2014, "potentially avoiding over $6 billion in taxes"; the Treasury
  cost was put at approximately **$6.8 billion**.
- **Order volume and latency**: Levin put it at "30 million a year between the two banks, about 15
  million per bank". Deutsche Bank's witness corrected the latency figure — the orders "were sent
  through our slower system initially, which was in the range of a few **milliseconds**", not
  microseconds. So: **~30 million orders/year, millisecond-scale, computer-placed by RenTec in the
  banks' names.**
- Renaissance's own witness (Silber) stated the **average holding period of the Deutsche Bank options
  was around 450 days, Barclays around 400 days**, and that the purpose was "a combination of
  **leverage and loss protection** that we have been unable to obtain through any other means",
  accepting general-creditor counterparty risk in exchange. **[T1, source #6]**

**What a solo participant cannot replicate**: 20:1 leverage with a capped downside, bank-intermediated
structures unavailable to retail (McCain: "an artificial structure, **not available to ordinary
consumers**"), and the resulting tax treatment. Note what is *not* in evidence here: nothing in this
record says Medallion's edge is a better forecast. What is documented is **leverage, loss protection,
bet count and tax structure** — three of which are structural and one of which (bet count: ~30 million
orders/year) is the same law-of-large-numbers mechanism as Virtu.

### 2.3 The generalisation

Across §2.1, §2.2 and §1.2, the documented earners share a pattern: **thousands-to-millions of small
bets per year**, and a **structural asymmetry** (latency rank / venue seats / leverage-with-downside-
protection / order-flow access) that is bought, licensed or negotiated rather than discovered. None of
the three primary documents attributes the profit to a proprietary forecast of public data.

A solo participant can replicate **the bet-count principle** and **none of the structural asymmetries**.
That is the honest bottom line of Section 2, and it says the hunting ground must be somewhere the
structural asymmetry is *absent for everyone*, not somewhere it can be out-competed.

---

## 3. Small-capacity venues where large players may be structurally absent

### 3.1 Prediction markets (Polymarket) — the strongest *positive* small-player evidence found — **T1**

Saguillo, Ghafouri, Kiffer & Suarez-Tangil, AFT 2025 (peer-reviewed, LIPIcs), on on-chain
Polymarket order-book data, **1 April 2024 – 1 April 2025**, 86 million bids:

- Two arbitrage families: **market-rebalancing** (within one market/condition — the complementary
  outcomes fail to sum to $1) and **combinatorial** (across logically related markets).
- **Realised, executed profit of ≈ $39.6 million** ($39,587,585.02) over the year, on trades they
  identify from on-chain data.
- **Polymarket charged no per-trade fee during the measurement period** — the authors state this
  explicitly as the reason they do not net fees out.
- Concentration and scale, from their Table 1 (top 10 accounts): top account **$2,009,631.76 over
  4,049 opportunities** (≈$496 each); #4 **$768,565.50 over just 211 opportunities** (≈$3,643 each);
  #10 **$383,569.94 over 2,720**. The authors describe "very big players with bot-like behaviour".
- The authors' own framing is modest: arbitrage volume is "relatively modest compared to other markets
  like decentralized exchanges, where transactions are atomic and risk-free", and they found "a
  limited number of dependent markets". **[T1, source #8]**

**Why this is the standout**: the top participants operate at **$0.4–2.0 million of annual profit
each**. That is a scale at which Citadel or Jane Street would not staff a desk, and it is a scale a
solo participant could in principle occupy. The activity is bot-like and high-bet-count (hundreds to
thousands of opportunities per account per year) — which, per this project's own power finding, makes
it one of the few grounds that is **statistically certifiable in a human lifetime**.

**Anti-evidence, equal weight**: profit is heavily concentrated in a handful of automated wallets;
the paper does not report opportunity *duration*, so I cannot say whether these are latency races
(a related paper on high-frequency Polymarket order-book snapshots exists — arXiv 2605.00864 — which
I did **not** read); the no-fee condition may no longer hold (unverified, §B.10); and legal access
for a Thailand-resident participant is entirely unverified (§B.11).

### 3.2 Crypto market making on major pairs — evidenced **negative** for a small participant — **T2**

Albers, Cucuringu, Howison & Shestopaloff (arXiv:2502.18625v2), from a **live trading experiment** on
the Binance USDT-margined Bitcoin perpetual — the most liquid crypto market — **232,897 minimum-sized
maker orders** submitted 12–19 February 2024, of which 127,051 filled:

- They document a **fundamental negative correlation between maker fill likelihood and post-fill
  returns**: the orders that fill are the ones you did not want filled.
- The consequence is that "viable maker strategies often require a **contrarian** approach,
  counter-trading the prevailing order book imbalance" — and that "commonly-cited strategies" are
  "**highly unprofitable**".
- **The spread is virtually always one tick wide**, and the tick is 0.1 USD ≈ **0.03 bp**, "negligible
  compared to fees". There is effectively **no spread to capture** on BTC perp.
- Their fee assumption is Binance's **most favourable tier: taker 1.5 bp, maker −0.5 bp (a rebate)**
  — and they state "any strategy results analyzed below would only deteriorate with less favorable
  fees". A solo participant does not get the top tier.
- Getting a good queue position on the profitable side "is extremely competitive and typically
  involves **latency optimization and/or special order types**".
- They summarise the whole thing as an "Unprofitability Principle": *ease of prediction × ease of
  exploitation < c*. **[T2, source #14]**

This is a clean, well-designed negative and I weight it heavily. Major-pair crypto market making is
the same latency-rank game as §1.2, in a venue where the spread is one negligible tick.

### 3.3 CEX-DEX arbitrage / MEV — documented profit, documented barriers — **T2**

Wu, Sui, Thiery & Pai (arXiv:2507.13023v3), Aug 2023 – Mar 2025 on Ethereum:

- **$233.8 million** extracted by **19 major searchers** across **7,203,560 identified CEX-DEX
  arbitrages**.
- **Three searchers captured three-quarters** of both volume and extracted value; concentration is increasing.
- Explicit entry barriers named: "**capital requirements, low-latency infrastructure, inventory risk,
  and uncertainty of block inclusion**".
- Profitability is "tied to their **integration level with block builders**"; exclusive
  searcher–builder relationships exist and vertically-integrated builders' profitability had been
  underestimated. Three builders dominate; two vertically integrate their own searchers.
- These trades take <2% of block space but contribute >15% of total block value, which is exactly why
  builders fight for the flow. **[T2, source #15]**

Note the source's own interests: authors are affiliated with Flashbots and Paradigm, both participants
in this market. The finding (concentration, vertical integration) does not obviously serve those
interests, which slightly raises my confidence in it.

**Verdict**: MEV is a documented, auditable, on-chain profit pool of the right order of magnitude —
and it is a latency-plus-integration game with an explicit oligopoly. This is *not* a small-player
ground on the evidence I read.

### 3.4 SPAC arbitrage — a real, near-riskless historical return with a capacity and cohort problem — **T1 + T2**

Gahng, Ritter & Zhang, *SPACs* (RFS 2023), on **458 exchange-listed SPAC IPOs, Jan 2010 – Dec 2020**,
measured through Dec 2021, using an "optimal redemption strategy" (sell each unit component if market
price exceeds redemption value, else redeem, five trading days before the merger or liquidation):

- **Equal-weighted annualised SPAC-period return: 23.9%** over an average 16-month holding period.
- For an investor who buys at the **first-day close** rather than the IPO offer price — i.e. **no IPO
  allocation required** — the return is **0.3 percentage points lower: 23.6%**.
- **Even liquidated SPACs returned +2.0% annualised**, because sponsors' warrant/unit purchases cover
  the underwriting fee so the trust holds ≥100% of IPO proceeds and accrues interest.
- **The worst SPAC IPO in the entire 2010–2020 sample returned +0.51% annualised.** The authors
  describe the instrument as "equivalent to a **default-free convertible bond with extra warrants**".
- The authors' own warning, twice: "we caution that the high average annualized returns for SPAC IPO
  investors and deal sponsors" are unlikely to repeat, and (footnote 19) as of January 2023 the **613
  SPAC IPOs from 2021 — excluded from their sample — "appear to be producing annualized SPAC period
  returns in the low single digits."** They also note Klausner et al. (2022) report 11.6% on a
  narrower 2019–20 sample. **[T1, source #13]**

AQR's own SPAC white paper (Oct 2024) is a self-interested marketing document and I use it only for
what it says about **its own access**: AQR states it earns "a liquidity premium", buys "equity in the
secondary market when the price is below the trust value", holds a "highly diversified portfolio of
warrants **acquired in IPOs**", and has spent years "forming relationships with serial sponsors and
underwriters that have helped facilitate their transactions and **improve our IPO allocations**".
It also names a structural feature that a small player is on the *right* side of: the "Bulldog"
provision caps any single investor or concerted group at redeeming e.g. 15% of shares — a constraint
that binds a large fund and not a small one. And it notes SPACs allow management to buy back their own
shares from the trust "at attractive 'spread-to-trust' levels", putting a **soft floor** under
secondary prices. **[T2/T3, source #12]**

**Structural reading**: the *IPO-allocation and warrant* leg is closed to a solo participant. The
**secondary-market buy-below-trust-and-redeem leg is not** — it needs no allocation, no relationship,
and Gahng-Ritter-Zhang show buying at the first-day close costs only 30 bp of annualised return.
The binding constraints are (a) issuance volume post-2022, which the AQR paper describes as "muted
since early 2022" with only a "mild resurgence", and (b) **bet count**: 458 SPACs over 11 years is
~40 independent bets a year, which is a *low-frequency* ground and therefore hard to certify under
this project's power finding — though the near-riskless floor (worst = +0.51%) means the true Sharpe
may be high enough to compensate. That trade-off has to be measured, not assumed.

### 3.5 Small/micro-cap US equities — the strongest *hypothesis*, weakest *evidence*

The positive case rests on §1.3 (costly-to-arbitrage portfolios retain more return post-publication;
β₂+β₃ correctly signed and significant for five of six variables) and §1.4 (published anomalies live
in microcaps: 3% of market cap, 60% of stock count). The negative case rests on the same two sources:
Hou-Xue-Zhang's "anomalies in microcaps are more apparent than real" is a **cost** verdict, and
McLean & Pontiff find the *idiosyncratic-risk* interaction is significantly negative (p=0.000) —
high-idio portfolios decay **more**, not less, post-publication.

I found **no** source measuring whether microcap anomaly spreads survive a **$100k–$1M** book's actual
cost structure — which is a different question from whether they survive an institutional book's.
That gap is the single most valuable unresolved question in this review, and it is answerable with
free data this project already routes (Alpaca + the point-in-time price store), which is why it ranks
high despite the evidence being genuinely two-sided.

### 3.6 Retail order-flow mechanics / odd lots
Covered at §1.8. Evidence: decayed to insignificance on the full universe, survives weakly in small
caps, never cost-tested by its own authors, and sensitive to the trade-signing method. Beyond the BJZZ
replication I read **no** primary source on odd-lot or PFOF economics (§B.4).

### 3.7 Closed-end fund discounts
**No source read.** I make no claim. Not ranked. (§B.5)

### 3.8 Kalshi
**No source read.** I make no claim. Not ranked. (§B.3)

---

## 4. Track-record databases

The brief asks what audited public track records of small systematic traders exist and what they show
once survivorship is accounted for. **I could not answer this for retail platforms** (Collective2,
Darwinex, Numerai, eToro) — I searched, found no study measuring survivorship-corrected realised
performance of small systematic traders on such platforms, and read none. One arXiv paper on eToro
that surfaced turned out to be about popularity dynamics rather than profitability; I fetched it,
read enough to establish that, and discarded it rather than cite it. See `COULD_NOT_VERIFY.md` §B.9.

What I *can* answer is the professional analogue, and it is brutal — **T1**:

Bhardwaj, Gorton & Rouwenhorst, *Fooling Some of the People All of the Time* (RFS 2014), on all CTAs
voluntarily reporting to Lipper-TASS, 1994–2012:

- To get an unbiased estimate they say they **exclude more than 75% of the vendor-reported
  observations**; their own footnote 4 gives the counts as **53,826 of 72,132** monthly observations,
  which is 74.6% — the paper's prose and its footnote are slightly inconsistent and I report both
  rather than pick one. In the final 962-fund database of 65,091 monthly returns, **46,785
  observations (71.9%, my arithmetic from their counts) are backfilled** — returns from *before* the
  fund's date of entry into the database.
- They document a previously unreported **"graveyard bias"**: the *entire track record* of some funds
  has been deleted from the vendor dataset.
- **Bias-adjusted CTA returns after fees, 1994–2012, are statistically indistinguishable from
  US Treasury bills.** Gross of fees the excess return is 6.1%; managers captured it in fees
  (about 4% of AUM in fee income), which the authors note "explains the high rates of entry into a
  market with high attrition rates".
- CTAs show **no alpha relative to simple futures strategies in the public domain**; exposure to
  simple trend-following explains most of the gross outperformance; for 7 of 10 funds an R² below 32%.
- Their explicit generalisation: "**Our results have implications for all hedge fund studies in that
  we find the typical adjustments for biases in the hedge fund databases still leave upward bias in
  fund performance.**" **[T1, source #10]**

**The transferable lesson**: in the one voluntary-reporting performance database that has been
audited this carefully, ~72% of the reported history is backfilled (46,785 of 65,091 observations), whole track records vanish, and
the standard bias corrections are still not enough. Any Collective2/Darwinex/Numerai-style leaderboard
should be assumed to have at least these three defects until someone demonstrates otherwise — and
nobody has, that I could find. **Treat every public small-trader track record as unevidenced.**

---

## 5. Anti-evidence, given equal weight

Ranked by how much it should move this project's plans.

1. **Chague et al.** — 97% of persistent retail day traders lose; the best of 19,646 earns a ~1.9
   annualised Sharpe that is fully explicable by selection; *no learning* over 300+ days. **[T2]**
2. **Bhardwaj-Gorton-Rouwenhorst** — 72% of a professional performance database is backfilled;
   bias-adjusted net returns = T-bills; standard corrections insufficient. **[T1]**
3. **Albers et al.** — a live 232,897-order experiment shows the fill/post-fill-return trade-off makes
   naive maker strategies "highly unprofitable" on the most liquid crypto market, *assuming the best
   fee tier* that a small player cannot get, on a spread that is one 0.03bp tick wide. **[T2]**
4. **Ardia et al.** — a headline retail-flow signal from a top-3 finance journal loses all
   significance on the full universe within one sample period of publication, and its authors had
   already disclaimed any implication for outsiders' profits. **[T2]**
5. **Novy-Marx & Velikov** — high-turnover anomaly costs always exceed 1%/month; the effective
   bid-ask spread alone kills all but 2 of the high-turnover set. **[T2]**
6. **Hou-Xue-Zhang** — 64% (85% at t>3) of 447 published anomalies are insignificant once microcaps
   are controlled, and the microcap-only survivors are "more apparent than real" because of costs. **[T2]**
7. **McLean & Pontiff** — 58% post-publication decay, larger for the highest-in-sample-return
   predictors; measurable capital arrival (volume +18.7%, short interest up). **[T1]**
8. **Wu et al.** — the most auditable small-player-adjacent profit pool (CEX-DEX MEV) is 75%
   controlled by three searchers and structurally tied to block-builder integration. **[T2]**
9. **Baron et al.** — HFT performance is persistent and driven by *relative latency rank*, which a
   non-colocated participant cannot obtain at any price it can pay. **[T1]**
10. **Gahng-Ritter-Zhang's own warning** — the 2021 SPAC cohort (613 IPOs, excluded from their
    sample) "appear to be producing annualized SPAC period returns in the low single digits". A 23.9%
    historical number is not a forward number. **[T1]**

**The meta-anti-evidence**: five of these ten are cases where a published, peer-reviewed, apparently
robust result decayed, reversed, or failed to replicate within a decade. This project has already
recorded 58 honest negatives of exactly that shape. The base rate for "published finding survives
into a small participant's live P&L" is, on this evidence, very low — and nothing in this review
should be read as raising it.

---

## 6. Ranked map of hunting grounds

Full attributes are in `hunting_grounds_ranked.csv`. Summary of the ranking logic and the top of the list:

**Ranking criteria**: (1) does credible evidence exist that a *small* participant can earn here, at a
tier I actually read; (2) is the structural protection real and *absent for large players too*, or
merely "they haven't got round to it"; (3) is the bet frequency high enough to be certifiable under
this project's own power finding; (4) is the data free; (5) can this project legally and
operationally reach it.

| Rank | Ground | Best evidence | Structural reason large players are absent or indifferent |
|---|---|---|---|
| 1 | **Crypto perpetual-futures basis / random-maturity arbitrage** | **T2** (He et al., Sharpe 1.8–2.0 at the fee tier the paper labels "typically an individual trader") | Nothing keeps large players out — but the paper *measures the return net of retail-tier fees*, so a small participant's cost disadvantage is already priced into the reported result. Capacity per opportunity is small. |
| 2 | **Prediction-market (Polymarket-style) internal-consistency arbitrage** | **T1** (AFT 2025: $39.6m realised in one year; top accounts $0.4–2.0m each) | Profit per participant is $0.4–2m/yr — below the threshold at which a large market-maker staffs a desk. Legally awkward venue, on-chain settlement, no institutional custody path. |
| 3 | **US micro/small-cap published-anomaly corner** | Genuinely two-sided: **T1** (McLean-Pontiff: costly-to-arbitrage portfolios retain more return post-publication) vs **T2** (Hou-Xue-Zhang: "more apparent than real" on costs) | Capacity. Microcaps are 3% of market cap and 60% of stock count; a $100k book has no capacity constraint where a $1bn book has nothing but. **This is the only ground where the project's smallness is itself the edge.** |
| 4 | **SPAC secondary buy-below-trust + optimal redemption** | **T1** (Gahng-Ritter-Zhang: 23.6% annualised buying at first-day close, worst-ever SPAC +0.51%) | The redemption floor caps downside structurally; the "Bulldog" 15% redemption cap binds large concerted holders and not a small one. But issuance is muted post-2022 and the 2021 cohort returns are low single digits. |
| 5 | **Cross-venue / cross-country crypto price dispersion** | **T1** (Makarov-Schoar: hours-to-weeks persistence, >15% US-Korea, ~50-75bp round-trip cost) | Capital controls and fiat repatriation, explicitly — *not* speed or capital. **But this friction binds a retail participant harder than an institution**, which is why it ranks 5th and not 1st despite the strongest measured spreads in the review. |

**Ranked out, with reasons**: crypto market making on major pairs (**evidenced negative**, §3.2);
CEX-DEX MEV (**evidenced oligopoly**, §3.3); retail-order-imbalance signals (**evidenced decay**,
§1.8); HFT/latency (**structurally closed**, §1.2); anything requiring IPO allocations, venue seats,
20:1 structured leverage, or colocation (§2). Closed-end funds and Kalshi are **unranked for want of
any source I read** — absence of a ranking here is absence of evidence, not evidence of absence.

### Three cross-cutting conclusions

1. **Frequency is the gate, not just the edge.** This project already measured that a true Sharpe of
   0.5 is uncertifiable in ~10 years of daily data. Grounds 1 and 2 are high-bet-count and therefore
   *testable*; ground 4 is ~40 bets/year and is *not*, unless its near-riskless floor produces a
   Sharpe high enough to compensate — which must be measured, not assumed. Ground 3's testability
   depends entirely on breadth across names, which is the one dimension where microcaps are rich.

2. **The documented winners win on structure, not forecasts** (§2.3). Every hunting ground above is
   therefore framed as "which friction is too small to be worth an institution's attention",
   and none as "which public data series can be forecast better".

3. **Cost realism is the whole ballgame, and one paper in this review did it right.** He et al. is
   the only source I read that reports its result **at an explicitly retail fee tier**. That is the
   standard to hold every future candidate to — and it happens to be exactly what this project's own
   rule already requires (cost realism feeding into the DSR calculation itself, not sitting as a side
   disclosure). Novy-Marx & Velikov and Hou-Xue-Zhang both say, in different words, that the cost
   line is where published anomalies die.

---

## 7. What this review is not

It is not a claim that any ground above contains a real edge for this project. Every ground is a
*place to look*, with the evidence for and against it tiered so the next decision can be made from
sources rather than impressions. Three of the five top-ranked grounds have an **unverified
legal-access question** (§B.11) that gates them entirely and should be settled before any work starts.
Two of the five rest on results whose own authors documented decay after their sample ended
(He et al.'s 2022 structural break; Gahng-Ritter-Zhang's 2021 cohort warning) — those decays are the
first thing any candidate built here must confront, not the last.
