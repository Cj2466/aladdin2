# M2 — US odd-lot issuer self-tenders: real bets per year and the gross premium (2026-09-12)

Answers measurement M2 of `small_participant_edges_2026-09-12/SMALL_PARTICIPANT_EDGES_2026-09-12.md`
§5, which asked for two numbers that section 3.1 counted filings instead of: **real bets per year**
and **the gross premium distribution**.

Window **2019-01-01 → 2026-09-11**. Method, re-runnable, in `m2_odd_lot_offers.py`; one row per
offer in `m2_offers.csv` with the odd-lot clause quoted verbatim; every quoted document hashed in
`m2_SOURCES.md`. **This is a measurement only — nothing was built, no DB row was written, no
strategy was backtested, and no Sharpe is claimed anywhere below.**

## 0. Census, not a sample

EDGAR full-text search returned **1,175 SC TO-I filings** containing the phrase "odd lot"
(per-year counts reproduce the review's table exactly: 190/197/193/151/145/127/84/88). Those
collapse to **348 distinct offers across 176 CIKs**. All 348 were examined — the brief's
60-offer fallback (seed 20260912) is implemented in the script but did not fire.

## 1. Bets per year

An offer is a **bet** only if all three hold: the security is exchange-listed, the document
actually **grants** odd-lot priority (not merely mentions the phrase), and the security tendered
is common stock (not preferred, warrants or notes).

| year | "odd lot" filings (review's number) | distinct offers | exchange-listed | listed **and** granting priority | **real bets (listed, priority, common)** |
|---|---|---|---|---|---|
| 2019 | 190 | 45 | 18 | 17 | **17** |
| 2020 | 197 | 51 | 23 | 18 | **17** |
| 2021 | 193 | 53 | 23 | 20 | **19** |
| 2022 | 151 | 45 | 16 | 16 | **16** |
| 2023 | 145 | 41 | 15 | 15 | **15** |
| 2024 | 127 | 47 | 23 | 9 | **8** |
| 2025 | 84 | 31 | 12 | 5 | **5** |
| 2026 (to 09-11) | 88 | 32 | 12 | 8 | **6** |

Totals over the window: **103 bets, 79 distinct issuers**. Three further facts about the other 245:
**130 offers are non-traded** (REITs, BDCs, interval and private-credit funds — Lightstone, Hancock
Park, Priority Income, Yieldstreet, Ares, Clarion, Crescent; a retail participant cannot buy these
on an exchange beforehand), **76 could not be classified** either way from the document plus the
submissions index, and **202 of 348 are NAV-based fund repurchases** rather than a market-price
tender. **7 offers explicitly DENY odd-lot priority** in as many words — the review's caveat that
the phrase does not prove the provision is confirmed. All seven are closed-end fund tenders
(three Virtus Total Return, Virtus Dividend Interest & Premium, Japan Smaller Capitalization,
Lazard World Dividend & Income, Total Return Securities Fund), and six of the seven are dated
2024 or later. Virtus Total Return, verbatim: "This tender offer will not have any special pro
ration provision for odd-lot tenders, which means that all odd-lot tenders (including
Stockholders who own fewer than 100 Shares) are subject to proration."

**The decline 2024→2026 is the sharpest thing in this table** (15–19/yr in 2019–2023 → 5–8/yr).
It is a real decline in listed common-stock offers granting the provision, not a decline in the
filing count, which fell far less.

## 2. Gross premium

Gross premium = offer price ÷ **the pre-announcement price the offer document itself states**
− 1. The document's own print is the denominator because a free feed is wrong three ways in this
sample (currency for Imperial Oil's CAD bid, a phantom 4-for-1 split for Covenant Logistics, and
the wrong share class for Wheeler REIT). yfinance agrees with the document print within 2 % on
**69 of 86** offers where both exist; the 17 disagreements are on the CSV as `yf_doc_price_ratio`.

| statistic | value | N |
|---|---|---|
| p10 | **−2.71 %** | 78 |
| p25 | **+0.91 %** | 78 |
| **median** | **+4.21 %** | 78 |
| p75 | **+10.71 %** | 78 |
| p90 | **+24.42 %** | 78 |
| min / max | −39.52 % (Rumble 2025) / +284.6 % (Optimum 2026) | 78 |
| fraction positive | 64 / 78 = **82.1 %** | 78 |
| mean | +11.48 % | 78 |

Per-year medians: 2019 +3.45 % (N 9), 2020 +5.97 % (13), 2021 +1.96 % (17), 2022 +9.24 % (14),
2023 +4.02 % (11), 2024 +4.44 % (4), 2025 −0.22 % (4), 2026 +13.44 % (6) — no trend that survives
N of 4–17 a year.

Caveats, stated rather than buried: **48 of the 78 are Dutch auctions where no final price was
found and the range midpoint was used** (flagged `range_midpoint` on the CSV). Their median
(+4.21 %) is within 21 bp of the 30 with a real fixed or final price (+4.00 %), so the proxy does
not appear to be driving the answer. 23 of the 103 bets have no stated reference price in the
selected document and carry no premium at all.

**Completion**: 98 of 103 bets have a final SC TO-I/A reporting completion (95.1 %); the other 5
have no amendment on file. **Holding period**: launch to expiration median **29 days** (p25 28,
p75 38), N = 57 offers whose expiration date parsed.

## 3. The round-trip a 99-share holder faces — descriptive dollars only

Computed as gross premium × 99 × the document's stated pre-announcement price. **This is a gross
dollar figure on one bet, not a return, not a Sharpe, and not net of spread, slippage, the odd-lot
execution penalty, or tax.**

| statistic | 99-share stake | gross dollar gain | after $1 commission each way |
|---|---|---|---|
| p25 | — | **$12.99** | $10.99 |
| median | **$2,381.94** | **$63.11** | $61.11 |
| p75 | — | **$207.03** | $205.03 |

**14 of the 78 lose money after a $2 round-trip commission** (they are the negative-premium
offers). At a $0 commission 13 of 78 lose money. The binding constraint is not the commission —
it is that the whole mechanism pays a median of about **$63 per bet**, with **at most ~19 bets a
year in the good years and 5–8 in the recent ones**, and each bet requires holding the name
beforehand (the provision is worthless to someone who buys after the announcement — it accepts
"all their securities" from a holder of fewer than 100 shares, and buying 99 shares at the
post-announcement price captures the remaining spread, not the premium).

## 4. Where the provision is actually worth the most — split-off exchange offers

Seven of the 103 bets are **split-off exchange offers** (parent shares exchanged for a
subsidiary's), and they are where the final filings show the provision operating most starkly.
In every one the issuer states that odd-lot holders were taken in full while everyone else was
cut, verbatim (hashes in `m2_SOURCES.md` §C):

| issuer | launch | final proration factor applied to everyone else |
|---|---|---|
| Cummins (Atmus) | 2024-02-14 | **6.99255200 %** |
| Danaher (Envista) | 2019-11-15 | **7.2433 %** |
| 3M (Solventum) | 2022-08-04 | **approximately 7.346065 %** |
| Lennar (Millrose) | 2025-10-10 | **8.604228 %** |
| Eli Lilly (Elanco) | 2019-02-08 | **13.5970839 %** |
| McKesson (Change Healthcare) | 2020-02-10 | **approximately 14.82 %** |
| Johnson & Johnson (Kenvue) | 2023-07-24 | **23.231832 %** |

Cummins' own PRELIMINARY count (Amendment No. 3, 2024-03-13; the final amendment restates the
proration factor but not this split): **1,006,609 shares tendered by "odd-lot" shareholders not
subject to proration, of 69,142,112 shares validly tendered in total** — the odd-lot channel is
about 1.5 % of the tender. So the mechanism is real, it operates
every time, and a sub-100-share holder gets 100 % fill where a large holder gets 7 %. I did **not**
verify the exchange-offer discount (the ~7 % figure lives in the S-4 prospectus, which is not in
the SC TO-I accession and which I did not read), so **no premium is claimed for these seven** —
they carry no `gross_premium` on the CSV.

Cash tenders show the same thing where the final amendment happens to spell it out, e.g. Summit
Midstream Partners 2020-11-10 ("proration factor for the Tender Offer, after giving effect to the
priority for odd-lot holders") and National Healthcare Properties 2020-01-09 ("after giving effect
to the priority of odd lots, is approximately 52…"). My regex found an explicit proration figure in
only 10 of the 103 bets, so **the 10 is a floor on how often the provision bound, not a rate** —
most final amendments simply do not restate it.

## 5. Anti-evidence — does anything here contradict Kadapakkam 2021?

**No, and the numbers point the same way.** Kadapakkam/Zhang/Yildirim (RQFA 56(4) 2021, abstract
re-fetched and re-hashed here) find that 2000–2015 "abnormal profits from tendering have
disappeared", and that closed-end-fund tender profits of ~0.5 % are "no longer significant after
adjustments for transaction costs".

What this measurement adds, with numbers:

1. **It does not contradict the "disappeared" finding, because it measures a different quantity.**
   A gross premium of +4.02 % to the pre-announcement close is **not** a tendering profit — the
   tendering trade Kadapakkam studies buys *after* announcement and captures offer-price-minus-
   market, which is a small fraction of the 4 %. My measurement is silent on that spread; I did
   not compute it, and any claim that "+4 % > 0.5 %, so the anomaly lives" would be wrong.
2. **The bet count is the harder constraint, and it got worse over the period Kadapakkam could not
   see.** 15→5 bets a year 2023→2025. At ~15 bets a year and a median $63 a bet, the mechanism's
   whole annual gross is on the order of **$950** on stakes of ~$2,400 each, before any cost.
3. **The closed-end-fund arm Kadapakkam examined is where the provision is most often DENIED.**
   All 7 explicit denials in my census are fund tenders (three Virtus Total Return, Virtus
   Dividend Interest & Premium, Japan Smaller Capitalization, Lazard World Dividend & Income,
   Total Return Securities Fund), so the corner of the market where he measured 0.5 % is partly a
   corner where a 99-share holder gets no priority at all.

One piece of evidence that cuts the *other* way and should be recorded honestly: **the provision is
not decorative**. The seven proration factors above are direct evidence that in oversubscribed
offers the odd-lot holder is filled in full while a large holder is cut to 7–23 %. Whatever is
true about the size of the profit, the exclusion of large capital is real and currently operating.

## 6. A correction to the review's legal-basis claim

§3.1 recorded that it "could not find the odd-lot preference in the rules where I looked" because
the eCFR text of 17 CFR 240.13e-4 contains the string "odd" zero times, and concluded the
"regulation deliberately created this gap" claim was unverified.

**The carve-out is in the rule.** 17 CFR **240.13e-4(f)(3)(i)**, current eCFR text, hashed in
`m2_SOURCES.md`: the pro-rata requirement "shall not prohibit the issuer or affiliate making the
issuer tender offer from: (i) Accepting all securities tendered by persons who own, beneficially
or of record, an aggregate of not more than a specified number which is less than one hundred
shares of such security and who tender all their securities, before prorating securities tendered
by others". The section never says "odd lot" — it says "less than one hundred shares", which is
why a string search for "odd" missed it. **The wording is permissive, not mandatory** ("shall not
prohibit"), which matches what the census found: 257 of 348 offers grant it, 7 deny it outright, and the
remaining 84 mention the phrase without either granting or denying in language this census could
match.

## 7. Could not verify

1. **The tendering spread itself** (post-announcement price → offer price), which is the quantity
   Kadapakkam measures. Not computed here; M2 asked for the gross premium to the pre-announcement
   close and that is what is reported.
2. **The split-off exchange-offer discount** (~7 % is the number usually quoted). It lives in the
   S-4 prospectus, not in the SC TO-I accession; not read, not claimed.
3. **23 of 103 bets have no premium** because the selected document states no reference price.
4. **76 of 348 offers could not be classified listed vs non-traded.** They are mostly small funds
   with no ticker in the submissions index and no explicit "no public market" sentence.
5. **The submissions index carries today's tickers, not the offer-date tickers.** Ten listed names
   returned no bars at all from yfinance (Cumulus Media, Bally's, MSC Income Fund, Pioneer Floating
   Rate, Priority Income) — the known delisted/renamed-securities gap, already on the paid-data
   list. This affects the yfinance cross-check only, never the premium, which uses the document.
6. **Whether an odd-lot tender is actually executable by a Thai-resident retail account** at a
   broker that will process a US tender instruction on a 99-share position, and at what fee. Not
   investigated; it is an access question, not a data question.
7. **The `vehicle` column (REIT / BDC / fund / operating company) is a keyword guess** and is
   wrong on at least two rows — Japan Smaller Capitalization Fund and Lazard World Dividend are
   labelled REIT because the phrase appears somewhere in their documents. Nothing in this result
   depends on that column; it is in the CSV for orientation only.
8. **The 2024–2026 decline was not explained.** It could be fewer large listed self-tenders overall,
   a drafting shift, or full-text-index coverage. Not diagnosed.

## 8. Step-0 admission rule (`micro_cap_corner_2026-09-12/STEP0_ADMISSION_RULE_2026-09-12.md`)

| rule | verdict |
|---|---|
| **R1 forced loser** | **PASS.** The issuer is bound by its own offer terms — the seven proration factors are the rule operating: everyone else cut to 7–23 %, odd-lot holders taken in full. The source is the filing itself, quoted, not an inference. |
| **R2 closed corner** | **PASS, by construction.** An institution cannot be a sub-100-share holder of anything it cares about. 17 CFR 240.13e-4(f)(3)(i) caps the exemption at "less than one hundred shares". |
| **R3 size** | **FAIL, and this is the binding one.** 15–19 bets/yr in the good years, 5–8 recently, median gross **+4.21 %** on a **~$2,382** stake = **~$63 gross a bet**, 18 % of bets negative, ~29 days held. Even ignoring costs entirely and assuming every bet is independent, a book of 4–17 bets a year at these sizes cannot reach the BOOK's 0.30-Sharpe member assumption; and the source literature's own claim for the parent trade is insignificant after costs. |
| **R6 free data** | PASS. EDGAR full-text search + submissions + Archives, all free, no key. |

**Recommendation: DECLINE at sourcing on R3** — and note this is a *different* verdict from the
review's, which declined on R3 by inheriting Kadapakkam's after-cost result. It is now declined on
a measured bet count and a measured dollar size of its own. R1 and R2 both pass on primary
evidence, which is worth keeping: this is the cleanest documented forced-flow-with-closed-corner
mechanism found so far, and it fails on economic size alone. Owner decides; nothing was registered.
