# Small-participant edges — an evidence-tiered review (2026-09-12)

Agent: research sub-agent (Opus), worktree `.claude/worktrees/small-participant-edges-2026-09-12`.
Wall clock: work started 10:10 Bangkok, this file first written 10:35 Bangkok (`date` read, not estimated).
Nothing was built, no backtest was run, no DB row was written. Everything below is either
(a) **measured by me today** with a committed script and its committed output, or
(b) **quoted from a source file committed under `sources/`** with a SHA-256 in `SOURCES.md`, or
(c) explicitly listed in `COULD_NOT_VERIFY.md`.

## 0. Scope, and what this does NOT redo

This extends, and does not repeat, `hunting_ground_review_2026-09-11/` (crypto perp basis,
Polymarket, US micro-cap corner, SPAC, market making, MEV, retail order-flow, equity HFT) and
`micro_cap_corner_2026-09-12/` (the sparse-ownership US listed corner, ledger entries #15–17).
The question asked here is narrower and different:

> which edges exist **only** for a small participant — because someone is FORCED to trade
> against them, or because the return is structurally reserved for small holders — **and** large
> capital cannot profitably or legally collect them?

Two parts: **A** the owner's home market (SET/mai, Thailand), **B** mechanisms reserved for small
participants globally.

**Evidence tiers** (identical to 2026-09-11, one addition):
**T1** peer-reviewed / regulatory / audited document, read by me ·
**T2** working paper or reputable institutional report, read by me ·
**T3** credible secondary source read by me, with a stated reason it is credible ·
**T4** recalled, not verified · **H** hypothesis, no evidence claimed ·
**M** *measured by me today* in this project, script and output committed (new tier — it is
neither a literature claim nor a hypothesis, and it should not be dressed as either).

---

## 1. Ranked summary

Ranking criterion, applied in this order: (i) is there an identifiable FORCED loser or a return
legally/structurally reserved for small holders; (ii) is large capital genuinely excluded;
(iii) does free data exist to measure it; (iv) how big and how frequent is the claim; (v) what is
the anti-evidence. Full detail per row in §3 and §4. `candidates_ranked.csv` carries the same
table in machine-readable form.

| # | candidate | who is FORCED / why capital is excluded | best supporting evidence | tier | best anti-evidence | tier | free data? | bets/yr | verdict now |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **Thai foreign-board (`-F`) premium on foreign-limit-full names** | A foreigner who needs *registered, voting* shares of a FOL-full company can only buy on the foreign board; only a holder of LOCAL-registered shares can supply them. A foreign fund cannot be on the cheap side of that trade — it is on the expensive side by construction | M: `-F` lines exist free on Yahoo back to 2000-01-04; mean `-F`/main−1 over the full history: BBL **+6.775%**, BAY +7.275%, SCCC +16.703%, KBANK +3.417% | M | M: 12 of the 15 `-F` lines probed have **median daily volume 0** — most of that "premium" is a stale print, not a tradable spread. BBL/KBANK/SCC are the only three that trade regularly. And the NVDR scheme exists explicitly to remove the need for the foreign board (NVDR prospectus, T1) | M+T1 | **yes**, 2000→ | unknown (must be measured) | **measure first** (§5 M1) |
| 2 | **Odd-lot provisions in US issuer self-tenders** | A tender-offer odd-lot provision takes the whole holding of a sub-100-share holder without proration — an institution cannot be a sub-100-share holder | M: EDGAR full-text search — "odd lot" appears in **84–224 SC TO-I filings per year, every year 2011→2026**; the provision is not extinct | M | T1: Kadapakkam/Zhang/Yildirim (RQFA 2021) — the parent tendering-profit anomaly (L&V's 9%) is **gone in 2000–2015**, and CEF tender profits of ~0.5% "are no longer significant after adjustments for transaction costs" | T1 | **yes** (EDGAR) | M: 16–26 distinct issuers per 100 hits/yr; most are **non-traded** REIT/BDC/interval funds | **low ceiling; measurable** (§5 M2) |
| 3 | **Japanese shareholder perks at the minimum lot** | The perk is a per-shareholder, not per-share, payout: "the yield on shareholder perks tends to be highest at a minimum lot of 100 shares". A large holder receives the same box of noodles as a 100-share holder, so the yield → 0 with size | T1: Gao & Nose, PLOS ONE 2024 — "Because they are often not proportional to the number of shares held, shareholder perks are considered to be attractive to small shareholders" | T1 | no net-of-cost Sharpe exists in anything I read; the payout is consumption in Japan (vouchers, food), not cash, so a Thailand-resident holder may not be able to realise it at all | — | unknown | unknown | **unresolved; access is the gate** |
| 4 | **Thai small-cap / mai corner (analogue of the US micro-cap corner)** | Capacity only. M: median Thai ordinary stock trades **THB 1.52m/day ≈ USD 46k** (p25 THB 0.46m ≈ USD 14k) — a foreign institution cannot hold a position there | M (turnover) + T3 (SET monthly report via reprint: foreign investors are 55.3% of turnover, i.e. concentrated in the large names) | M | **No forced flow identified yet** — this is a corner, not an edge; and the free universe is survivor-only (M: 8 of 12 named dead/suspended symbols return **zero** bars) | M | yes, with survivorship bias | — | **corner exists, mechanism missing** |
| 5 | **SET50/SET100 semi-annual rebalancing** | Index funds tracking the SET50/SET100 must trade the adds/drops on the effective date | (none read for Thailand) | — | T2: Greenwood & Sammon (NBER w30748) — the S&P 500 index effect fell from 3.4% (1980s) / 7.6% (1990s) to **0.8%** in the last decade; deletions to −0.6% | T2 | constituent history not sourced | ~2 reviews/yr | **not admissible without a Thai-specific source** |
| — | Closed-end fund discount / open-ending | **RANKED OUT for a small participant.** The return in the literature is earned by an ACTIVIST: Bradley/Brav/Goldstein/Jiang's own worked example is a 14.5% combined stake; open-ending attempts halve the discount but the attempt requires the stake | T1 | same paper | T1 | — | — | **excluded: needs size, the opposite of this brief** |
| — | Repurchase tender-offer arbitrage generally | **RANKED OUT.** L&V's 9% (1962–1986) is real and I read the working paper; Kadapakkam et al. show it is gone by 2000–2015 | T1+T2 | T1 | — | — | — | **excluded: dead** |
| — | IPO retail allocation, rights-offering oversubscription, Dutch-auction tenders, small-cap merger arb, share-class arb, OTC/small-exchange liquidity provision, Thai shareholder perks | — | **no primary source read within this budget** | — | — | — | — | — | **UNRANKED FOR WANT OF EVIDENCE — absence of a ranking is absence of evidence, not evidence of absence** |

### The single most useful number found today

Thailand's free daily history is **26.69 years** (Yahoo `.BK`, mass start 2000-01-04, measured
today) against the US window's 10.683 years. Run through this project's own
`sourcing_power_check` — no new formula, same ladder — the minimum **claimed net annualized
Sharpe** that returns PROCEED falls from **2.416** (US, n_local=8) to **1.528** (Thailand,
n_local=8); 1.425 at n_local=5, 1.660 at n_local=16
(`thai_window_power_threshold.py`, `thai_window_power_threshold_output.txt`; the script's US
control reproduces 2.416 exactly, which is the number already in `DECLINED_AT_SOURCING.md`).

That is a **37% cut in the admissibility bar**, obtained from calendar time alone — the one lever
the project's own power finding says actually moves (`feedback_sampling_frequency_does_not_shorten_detection`).
It does not make any candidate admissible by itself. It does mean the Thai market is the cheapest
place this project currently has to test a claim, and that is a fact about the data window, not
about Thai stocks being inefficient.

---

## 2. PART A — the home market: what is actually free, and what is actually closed

### 2.1 Free data — measured, not assumed (`THAI_MARKET_DATA_PROBE.md` has the scripts and raw output)

Yahoo Finance, enumerated through yfinance's screener endpoint (`region = th`), 2026-09-12:

| measured | value |
|---|---|
| symbols in the Yahoo Thai universe | **2,281**, every one tagged `exchange = SET`, `quoteType = EQUITY` |
| of which ordinary lines | **884** |
| of which NVDR lines (`-R`) | **836** |
| of which digit-suffix DW/DR lines | **561** |
| ordinary symbols returning daily bars (seeded sample n=200) | **200 / 200, zero errors** |
| history start | min **1983-08-26**; a mass floor at **2000-01-04** (190 of 884 ordinary names start exactly there); median first bar 2011-07-28 |
| bars per symbol | median **3,732** |
| last bar | 2026-09-11 for the whole sample; **0 of 200 stale** |
| median daily turnover (close × volume), THB | p10 **179,733** · p25 **461,968** · median **1,519,123** · p75 **8,141,739** · p90 **43,368,031** |

At the FX implied by SET's own August 2026 report (THB 75.05bn ≈ USD 2.26bn ⇒ 33.2 THB/USD),
the median Thai ordinary stock turns over about **USD 46,000 a day**, the 25th percentile about
**USD 14,000**. For comparison, the US delisted micro-cap sample measured on 2026-09-12 had a
median of USD 137k/day. The Thai listed market is, at the median, *thinner than the US delisted
corner*.

**Three defects of the free feed, measured today, that constrain everything in Part A:**

1. **Survivorship.** Of 12 symbols I selected as candidate dead/suspended SET names, **8 return
   zero bars** (SSI, MAX, EARTH, PACE, NMG, STARK, IFEC, DTAC) and **9 of 12 are absent from the
   live screener universe**. One (POLAR) does retain 4,020 bars ending 2025-01-27. The Yahoo Thai
   universe is therefore essentially a **survivor list**; any long-horizon Thai study on it is
   biased upward by an unmeasured amount. (I did not verify each of those 12 names' actual SET
   status — what is measured is the *bar availability*, not the delisting.)
2. **The NVDR (`-R`) lines are not usable as a price series.** All five probed (`ADVANC-R`,
   `BBL-R`, `KBANK-R`, `PTT-R`, `SCB-R`) have **median volume 0**; `PTT-R` vs `PTT` shows a mean
   close ratio of **+265%** with a max of +1010% over the common window — i.e. the historical
   `-R` series is not on the same corporate-action basis as the main line. Any NVDR
   premium/discount computed from this feed today would be an artefact.
3. **SET's own APIs are blocked to a script.** `https://www.set.or.th/api/set/stock/list` returns
   **HTTP 403** (Imperva/Incapsula interstitial) with browser headers and a referer;
   `https://www.settrade.com/api/...` likewise. SET's HTML pages fetch fine but render their
   numbers client-side, so the investor-type and short-selling tables on
   `set.or.th/en/market/statistics/*` are **not** scriptable through a plain HTTP client as of
   today. This is a real engineering gate on using SET's free data at all, and it is why §2.3's
   investor-type numbers are cited to a T3 reprint of SET's own monthly report rather than to SET.

### 2.2 What SET publishes free (page-level, verified by fetching the pages)

Verified to exist as public pages (HTML fetched, committed): end-of-day data service description,
investor-type statistics, program-trading value, five-day market summary, short-selling eligible
list, trading-units/tick-size/price-limit reference, tax reference, SET50 overview. What is
**paid** (SETSMART and the institutional data feeds) was **not** priced or purchased and is listed
in `COULD_NOT_VERIFY.md`.

### 2.3 Structural constraints — who is kept out, and where

| constraint | what it says | source | tier |
|---|---|---|---|
| Foreign ownership limit + NVDR | "Under Thai law, the percentage of shares that can be held by non-Thai individuals or entities in a company listed … may be limited. Foreigners who are interested in making investments in these companies are often prevented from doing so because of these foreign ownership restrictions. The NVDR represents an investment alternative that allows foreign investors to receive the Financial Benefits … without being concerned about the foreign shareholding limitations." | Thai NVDR prospectus 30-01-2020, p.1 | T1 |
| NVDR carries no vote | "each Non-Voting Depositary Receipt represents certain Financial Benefits (but not voting rights) … The Investor will not be entitled to exercise any voting rights with respect to the Shares, except in the situation where it is proposed that the Shares be delisted" | same, p.1 | T1 |
| Short selling restricted to SET100 | Eligible list revised so that only **SET100** common stocks (plus underlying DW/ETF/SSF, DR, ETF) remain; "Large Market Capitalization with Liquidity as specified by SET (non-SET100)" **cancelled**; "effective from April 16, 2025" | SET circular KorSor.(Wor) 004/2025, 11 Apr 2025 | T1 |
| Board lot | 100 shares generally; SET consulted (June 2025) on cutting it to 10 shares for stocks ≥ THB 50 "in order to align with the ticket size of retail investors" | SET Market Consultation No.15, May 2025 | T1 |
| New-listing price band | "The floor level for newly listed securities will be reduce to 0.5 times the IPO price, while the Ceiling will remain unchanged at no more than 3 times the IPO price" | same | T1 |
| Ceiling/floor, normal | Shares: "Not exceeding **3 times the IPO price**" on the first day of trading; "Not exceeding **30%** of the closing price of the Securities on the preceding Trading day" thereafter. The same table carries a separate securities type, "**Securities Held by Foreign Nationals**" — i.e. the foreign board is a distinct instrument in SET's own rulebook | SET *Trading units – Tick sizes – Price limits* page, text located in the fetched HTML | T1 |
| Investor-type mix, Aug 2026 | "Foreign investors led trading activity at **55.3 percent** of total trading value, followed by retail investors at **30.8 percent**, while local institutional investors and proprietary trading by securities companies were on par at **6.9 percent** each"; SET+mai average daily trading value THB 75.05bn (≈ USD 2.26bn) | Kaohoon International reprint of SET's monthly report, quoting SET's Head of Research by name | T3 |

**The single most important structural fact, and it cuts against the folklore:** the Thai market is
**not** a retail-dominated backwater that foreign institutions have left. Foreign investors are
**55.3%** of turnover and retail **30.8%**. Whatever edge exists here, "big money is absent" is not
the reason, except in the small-cap tail where the turnover numbers in §2.1 make institutional
participation arithmetically impossible.

### 2.4 Legal / operational access for a Thai resident

| item | finding | source | tier |
|---|---|---|---|
| Capital gains, individual | "Capital Gains … Individual Investor … **Tax exempt**" for direct investment in SET/TFEX | SET tax page | T1 |
| Dividends, individual | "**10% withholding tax** on any dividend income from listed or limited companies"; may elect to exclude from the year-end computation | SET tax page | T1 |
| Foreign investors | 30 treaty countries exempt from Thai capital gains, 27 not (SET's table is dated "as of September 2014") | SET tax page | T1 (stale) |
| Brokerage access, short-sale access for retail, ability to sell on the foreign board | **NOT VERIFIED** — no broker document read | — | see `COULD_NOT_VERIFY.md` |

The tax point is structural and in the owner's favour: a Thai-resident individual pays **zero** tax
on SET trading gains, while a foreign fund's treatment depends on its treaty. That is a real
after-tax edge of a size no signal in this project has ever claimed — but it is an edge over
foreign *investors*, not a source of return on its own.

### 2.5 The Thai candidates, with their anti-evidence

**A1. Foreign-board (`-F`) premium — the only Part A candidate with a forced loser AND free data.**

Mechanism: when a company's foreign-ownership limit is exhausted, a foreigner who wants registered
(voting) shares must buy on the foreign board from a holder of local-registered shares. The buyer
is constrained by law; the seller is any local holder. A foreign institution is structurally on the
**buy** side — it cannot collect this premium, it pays it. NVDR exists precisely to let foreigners
avoid paying it (prospectus, T1), which is simultaneously the mechanism's main anti-evidence.

Measured today (`probe_thai_foreign_board.py`, full output committed), mean of `-F` close / main
close − 1 over each pair's whole common history:

| symbol | overlap days | window | mean | sd | p95 | median `-F` volume | days with `-F` volume = 0 |
|---|---|---|---|---|---|---|---|
| BBL | 6,616 | 2000-01-04 → 2026-09-11 | **+6.775%** | 12.956% | +34.916% | 1,174,500 | 723 |
| KBANK | 6,616 | 2000-01-04 → 2026-09-11 | **+3.417%** | 5.644% | +15.741% | 1,760,900 | 476 |
| SCC | 5,754 | 2003-04-24 → 2026-09-11 | +2.878% | 5.451% | +14.021% | 135,250 | 1,544 |
| BAY | 6,616 | 2000-01-04 → 2026-09-11 | +7.275% | 19.551% | +47.059% | **0** | 3,590 |
| SCCC | 6,616 | 2000-01-04 → 2026-09-11 | +16.703% | 34.895% | +82.952% | **0** | 6,042 |
| BANPU | 2,380 | 2016-10-28 → 2026-08-11 | +35.228% | 41.264% | +137.805% | **0** | 2,366 |
| ADVANC / PTT / SCB / CPALL / AOT / TU / KTB / TISCO / EGCO | — | — | −2.9% … +1.8% | 2.0–16.5% | — | **0** | 2,400–4,900 |

Read honestly: **only BBL, KBANK and (partly) SCC have a foreign board that actually trades.**
For the rest the "premium" is the ratio of a live price to a stale one and means nothing. The two
tradable names are exactly the two where the story is most plausible (Thai banks have the tightest
foreign limits), which is encouraging and also exactly the shape a selection artefact would take.
Nothing here is a return estimate; no strategy was formed.

Literature: Bailey & Jagtiani, *Foreign ownership restrictions and stock prices in the Thai capital
market*, JFE 36(1), 1994, 57–87 — **citation verified, content NOT read**: RePEc states "No
abstract is available for this item" and the publisher copy is gated. Listed in
`COULD_NOT_VERIFY.md`. I make no claim about what that paper found.

**A2. Thai small-cap / mai corner.** The corner exists (§2.1 turnover). No forced flow has been
identified in it, and the free universe is survivor-only. Under the Step-0 admission rule this is
R1-fail: a corner is not a mechanism.

**A3. SET50/SET100 rebalancing.** Semi-annual, rule-based, announced in advance — a textbook forced
flow. Two problems: no Thai-specific study was found, and the global prior is now strongly negative
(Greenwood & Sammon: 7.6% in the 1990s → **0.8%** in the last decade). Not admissible without a
Thai-specific measurement, and the global trend says the expected answer is "small".

**A4. IPO first-day / new-listing band.** The rule is real and asymmetric (floor 0.5×, ceiling 3×
the IPO price, T1). No Thai IPO underpricing source was read, and IPO *allocation* — the part that
would actually be reserved for small participants — was not sourced at all.

---

## 3. PART B — mechanisms reserved for small participants, globally

### 3.1 Odd-lot provisions in issuer tender offers — **the cleanest "reserved by construction" mechanism found, with the weakest economics**

*Who is forced / why capital is excluded.* A tender-offer odd-lot provision buys the **entire**
holding of a holder of fewer than 100 shares without proration. An institution cannot be a
sub-100-share holder of anything it cares about, so the provision is unreachable at size — the
exclusion is definitional rather than economic.

*Does it still exist?* **Measured (M), not recalled.** EDGAR full-text search for the exact phrase
"odd lot" in form **SC TO-I** (issuer self-tender), one query per year:

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026* |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| filings | 122 | 219 | 108 | 171 | 224 | 151 | 157 | 184 | 190 | 197 | 193 | 151 | 145 | 127 | 84 | 88 |

(*2026 is year-to-date. Control: total SC TO-I filings/yr ran 2,835–5,281 over the same period.)
Distinct entities among the first 100 hits per year: **21 (2023), 16 (2024), 19 (2025), 26 (2026)** —
and inspection of the names shows a majority are **non-traded** vehicles (Lightstone Value Plus
REIT, Hancock Park Corporate Income, Priority Income Fund, Ares/Fortress/Crescent private credit
funds, Yieldstreet), whose shares a retail participant cannot buy on an exchange at a discount
beforehand. The exchange-listed ones in the sample are real (JNJ, Cummins, Incyte, Valvoline,
Lennar, WEX, Scholastic, InterDigital, Rumble, Presidio, Virtus Total Return).

*Caveats on that measurement, stated:* EDGAR counts **filings, not offers** (amendments inflate the
count), and the phrase "odd lot" appearing in a document does **not** prove the offer grants
odd-lot priority. Both are exactly what measurement M2 in §5 would resolve.

*Legal basis.* I could **not** find the odd-lot preference in the rules where I looked: the current
eCFR text of **17 CFR 240.13e-4** and **240.14d-8** contains the string "odd" **zero times**
(both fetched and committed). So the widely repeated "regulation deliberately created this gap" claim
is, on what I read, **unverified** — the provision appears to be a *contractual* feature of offers,
not a mandate. Recorded in `COULD_NOT_VERIFY.md`.

*A citation correction.* Secondary sources (blogs, and a search engine's own summary) attribute
"9–12% abnormal returns … with odd-lot provisions" to **Lakonishok & Vermaelen (1990)**. I read the
full 46-page working-paper version (INSEAD WP 88-40, committed): the word "odd" appears **zero
times** in it. What the paper actually shows is the *prorated* tender arbitrage — "buying shares
before the expiration date and tendering to the company … generates economically and statistically
significant abnormal returns of **9%** on average" (1962–1986), plus a second rule that "beat[s] the
value-weighted index by **12% per year** in the two years after the repurchase". That is a different
trade, with proration risk, and it is **not** evidence about odd-lot provisions. (I read the
working paper, not the published 1990 JF version; the published version could differ.)

*Anti-evidence, T1 and decisive for the economics.* Kadapakkam, Zhang & Yildirim, *A reexamination
of the tendering profit anomaly*, Review of Quantitative Finance and Accounting 56(4) 2021,
1475–1501, abstract read verbatim: "Given the rise of event-driven hedge funds, we reexamine this
strategy in recent years (2000–2015) and find that **abnormal profits from tendering have
disappeared**. Examining a sample of closed-end fund repurchase tender offers during the same
period, we find abnormal tendering profits of around **0.5%**. However, these profits are **no
longer significant after adjustments for transaction costs**."

*Verdict.* The mechanism is genuinely reserved and demonstrably still in use, and its measured bet
count (order 20–40 US issuers a year, a minority exchange-listed) combined with a parent-anomaly
return that is dead after costs means it cannot, on present evidence, clear this project's power
bar. It is worth **measuring** (§5 M2) because the measurement is cheap and the answer is a number,
not an opinion.

### 3.2 Shareholder perks (Japan) — reserved *per shareholder*, which is the purest form of the idea

Gao & Nose, *Long-term shareholder perks and stock price reaction*, PLOS ONE 19(4) 2024 (open
access, read): "Because they are often not proportional to the number of shares held, shareholder
perks are considered to be attractive to small shareholders"; and, on the size gradient, "the yield
on shareholder perks tends to be **highest at a minimum lot of 100 shares**". Their worked example:
Nissin Foods sends product "once a year to all shareholders who hold at least 100 shares, which is
the minimum trading unit."

That is the exact shape this brief asks for: a payout whose *yield falls monotonically with
position size*, making it worthless to any institution. What is missing is everything economic —
no net-of-cost return, no ex-day capture study read by me (a related SSRN paper by Huang/Rhee/
Suzuki/Yasutake on ex-benefit-day price movement was found but not read), and no answer to whether
a Thailand-resident holder can realise a Japanese food voucher at all. Unresolved, and the gate is
access, not statistics.

### 3.3 Closed-end fund discounts / open-ending — ranked OUT, for a reason worth recording

Bradley, Brav, Goldstein & Jiang, *Activist Arbitrage: A Study of Open-Ending Attempts of Closed-End
Funds* (JFE 95(1) 2010; the December 2008 full text read and committed): "Open-ending attempts have
a substantial effect on discounts, reducing them, on average, to half of their original level";
"open-ending attempts reduce the discount of the targeted funds by more than 10 percentage points on
average … given that discounts of targeted CEFs are around 20% of NAV". The paper's own worked
example is an activist whose "combined beneficial holdings … represented approximately 14.5% of the
fund's outstanding shares."

The return is compensation for **doing the activism**, which needs a stake a small participant
cannot take. This is the mirror image of the brief: a mechanism where large capital is the only
party that *can* collect. It is listed here so the project does not rediscover it as a candidate.

### 3.4 Everything else in the brief — honestly, not researched

IPO retail allocations (US / Thai / HK lotteries and clawbacks), rights offerings and
oversubscription privileges, Dutch-auction tender premiums, small-cap merger arbitrage below fund
size, share-class arbitrage, OTC/small-exchange liquidity provision, and Thai shareholder perks
were **not sourced within this budget**. I read no primary document on any of them, so I rank none
of them and claim nothing about them. They are listed in `COULD_NOT_VERIFY.md` §C as open, with the
search that would settle each.

---

## 4. How the ranked candidates score against the Step-0 admission rule (R1–R6)

Applying `micro_cap_corner_2026-09-12/STEP0_ADMISSION_RULE_2026-09-12.md` as written. None of these
is proposed for a build; this is the same ledger discipline applied to new candidates.

| candidate | R1 forced loser | R2 closed corner | R3 size (≥0.30 net at fraction 0.5) | R6 free data | status |
|---|---|---|---|---|---|
| Thai `-F` premium | **yes** — FOL-constrained foreign buyers, by law | **yes** — only local-registered holders can supply | **unknown** — no source claim exists and no return was computed | **yes** (2000→), with the staleness defect measured | **not yet checkable**: R3 needs M1 |
| US odd-lot tenders | **yes** — the issuer must take the whole odd lot | **yes** — definitional | **fails on present evidence** (T1: parent anomaly insignificant after costs 2000–2015) | yes (EDGAR) | would DECLINE at sourcing on R3 |
| Japanese perks | yes — the payout is per holder | yes — yield → 0 with size | unknown | unknown | R6 unresolved (access) |
| Thai small-cap corner | **no** — no mechanism | yes | — | yes, survivor-biased | R1 fail |
| SET50/100 rebalancing | yes | no — the effect lives in the large names by construction | no Thai source; global prior 0.8% | constituent history not sourced | R2/R3/R6 fail |

I did **not** add any of these to `DECLINED_AT_SOURCING.md`: that ledger is the orchestrator's, the
entries above are candidate-stage, and two of them are one measurement away from a real verdict.
Recommended, not executed.

---

## 5. What to do first — three concrete measurements (not builds)

**M1. Is the Thai foreign-board premium a tradable spread or a stale print?**
On BBL, KBANK and SCC only (the three with a live `-F` book), measure from the free data already
proven to exist: (a) the fraction of days on which **both** legs print with non-zero volume;
(b) the premium distribution conditional on that; (c) what the premium does over the following
1/5/20 days after a two-sided day; (d) the THB depth implied by `-F` volume × price at the p25 day.
Then, and separately from any data work, establish the **operational** question that decides
everything: can a Thai-resident retail account sell local-registered shares onto the foreign board,
and at what fee? If (a) is small or (d) is below a few hundred thousand baht, the candidate dies
there and the answer is an honest negative that costs one day.

**M2. Turn the EDGAR odd-lot count into a bet count and a gross premium.**
Pull the ~20–40 distinct SC TO-I issuers per year that mention "odd lot" (2019→2026), and classify
each: exchange-listed or non-traded; does the document actually grant odd-lot **priority** (quote
the clause); offer price vs the pre-announcement close; completion. Output is two numbers this
project needs and does not have: real bets/year for a retail-only mechanism, and the gross premium
distribution to set against Kadapakkam's "insignificant after transaction costs".

**M3. Measure the Thai free feed's survivorship and close the SET-API gap.**
Obtain a list of SET/mai delistings 2000→2026 from SET's own published notices (the HTML pages
fetch fine; only the JSON APIs are blocked) and measure what fraction have **zero** bars on the free
feed — today's 8-of-12 is a hand-picked sample, not an estimate. In the same pass, determine whether
SET's investor-type, NVDR-flow and short-selling daily files can be downloaded at all without
SETSMART; if they cannot, that is a **paid-data gap to log (candidate P10)**, not a purchase.

Each of these three ends in a number, and any one of them can kill its candidate cheaply. That is
the intended order.

---

## 6. Strongest anti-evidence in this review, collected

1. **T1 — the tendering-profit family is dead after costs.** Kadapakkam/Zhang/Yildirim: profits
   "have disappeared" 2000–2015; CEF tender profits ~0.5%, "no longer significant after adjustments
   for transaction costs."
2. **T2 — forced index flows have collapsed as a source of return.** Greenwood & Sammon: S&P 500
   addition effect 3.4% (1980s) → 7.6% (1990s) → **0.8%** (last decade), deletions −0.6%, *despite*
   more indexed assets. Any "index funds are forced to trade" candidate now starts from this prior.
3. **T3 — the Thai market is foreign-institution-dominated, not retail-abandoned.** 55.3% of
   turnover is foreign vs 30.8% retail (SET's own August 2026 report, via reprint).
4. **M — the free Thai feed is survivor-only and partly synthetic.** 8 of 12 named dead/suspended
   symbols return zero bars; every NVDR `-R` line probed has median volume 0 and `PTT-R` is off
   `PTT` by a mean of +265%; 12 of 15 foreign-board lines have median volume 0.
5. **T1 — Thailand's rules are narrowing, not widening, the retail playing field.** Short-selling
   eligibility was cut to SET100 only, effective 16 April 2025.
6. **T1 — the CEF discount return belongs to the large holder**, not the small one (14.5% stake in
   the paper's own example).

---

## 7. Files in this folder

| file | what it is |
|---|---|
| `SMALL_PARTICIPANT_EDGES_2026-09-12.md` | this review |
| `candidates_ranked.csv` | the §1 table, machine-readable |
| `THAI_MARKET_DATA_PROBE.md` | the probe methodology, scripts and committed outputs |
| `probe_thai_yfinance.py` / `thai_probe_output.txt` / `thai_yfinance_probe.json` | universe + bar-availability probe |
| `probe_thai_boards.py` / `thai_boards_output.txt` | `-F` existence, `-R` quality, screener membership |
| `probe_thai_foreign_board.py` / `thai_foreign_board_output.txt` | foreign-board premium table |
| `probe_edgar_odd_lot.py` / `edgar_odd_lot_output.txt` | EDGAR odd-lot frequency + distinct issuers |
| `thai_window_power_threshold.py` / `thai_window_power_threshold_output.txt` | admissibility threshold on the 26.69-year Thai window (US control reproduces 2.416) |
| `COULD_NOT_VERIFY.md` | every claim I could not establish |
| `sources/` + `SOURCES.md` | every fetched document with its SHA-256 |
