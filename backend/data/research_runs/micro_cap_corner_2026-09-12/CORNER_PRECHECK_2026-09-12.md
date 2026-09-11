# Step 0 Days 2–3 — the micro-cap corner: what exists on free data, and what passes the admission rule (2026-09-12, 01:30 → ~04:30 Bangkok)

Orchestrator: Fable 5.1. One sub-agent (Opus) for literature sourcing, sequential; every
quotation it relied on was re-read by the orchestrator in the extracted source files, and the
three source PDF hashes were re-computed and matched `sources/SOURCES.md`. Rule used: the
admission rule declared BEFORE any of this was measured (`STEP0_ADMISSION_RULE_2026-09-12.md`).

## 1. Result in one line

**Admissible at sourcing: 0. Produced: 0.** One candidate (fund-redemption fire sales measured by
Coval-Stafford's unweighted count on a sparse-ownership listed universe) satisfies every rule
except R3 (claim size), and R3 fails only on the conservative reading — recorded so the owner can
waive it knowingly rather than have it waived for them.

## 2. What was measured (all scripts and outputs in this folder; nothing invented)

### 2.1 The universe with delisted names — `probe_alpaca_universe.py`, `alpaca_universe_probe.json`
Alpaca `/v2/assets`: 14,315 active and 19,182 inactive US equities; 2,867 inactive on listed
exchanges, of which 2,100 are plain tickers (767 CUSIP-like or unit strings, which 400 a whole
request). A seeded sample of 300 inactive plain tickers: 293 return SIP daily bars (0 errors),
first bars from 2016-01-04, last bars 2018-06-25 → 2026-09-10 (median 2021-04-30). **Coverage of
delistings therefore starts ~mid-2018 in the assets list** (LNKD 2016 and TCS are absent from it).
34 of 293 still trade to the window end = symbol re-use, to be cut by delisting date as the
2026-09-11 memo said. Median daily dollar volume of the delisted sample: **$137k** (p25 $16k,
p75 $2.0M) — the corner is genuinely tiny.

### 2.2 Fund-ownership breadth of every equity CUSIP — `measure_nport_ownership_breadth.py`, `nport_breadth/`
Streams SEC N-PORT FUND_REPORTED_HOLDING per quarter (2019q4 → 2026q2) through the existing
provider's range-request reader; ASSET_CAT = EC, real CUSIPs. Per quarter ~21–27k equity CUSIPs;
**median 4 fund owners; 6.3k–8.5k CUSIPs with 5–47 owners** (the breadth regime of
Coval-Stafford's worked example, 47) — versus 643 (S&P 500) and 246 (S&P 600) in the 2026-09-08
test. Full table in `nport_breadth/summary.json` (appended below when the run completes).

### 2.3 Joining the two — `intersect_breadth_universe.py`, `breadth_universe_intersection.json`
CUSIP → ticker through SEC fails-to-deliver archives (29 cached in the main checkout, 33,584 CUSIPs,
31,296 symbols), then symbol ∈ Alpaca listed plain tickers (active ∪ inactive):
**1,070–1,468 listed names per quarter with 5–47 fund owners**, 112–158 of them now delisted
(2019q4–2021q4; later quarters appended below). Limits, stated: the FTD map covers 6.7–8.8k of
the 21–27k CUSIPs (foreign, unlisted, and names with no fails in the 29 half-month files are
unmapped — more archives are free and would raise it); Alpaca's inactive list starts ~2018-06.

### 2.4 Post-delisting bars — inline probe, recorded in `DECLINED_AT_SOURCING.md` #15
`feed=otc` → HTTP 403 on the free tier; `feed=sip` → 0 bars after the last listed bar for all 12
sampled delisted names. Logged as **P9**; no purchase recommended.

## 3. Sourcing (Opus agent; `FORCED_FLOW_SOURCING_2026-09-12.md`, `candidates_ranked.csv`, `sources/`)

| candidate | R1 forced | R2 corner | R3 size | R6 data | verdict |
|---|---|---|---|---|---|
| delisting forced exit (Macey-O'Hara-Pompilio) | yes — SEC rules force institutions out of unlisted shares (fn. 45, re-read) | yes — legal exclusion | not derivable; authors doubt it survives a 25% first-day spread | **no — OTC bars 403** | DECLINED #15 |
| fund-redemption fire sales, count measure, sparse-ownership universe (Coval-Stafford Eq. 4) | yes (Wardlaw 2020 critique unresolved: abstract only) | yes — 1,070–1,468 names/quarter | **0.44–0.70 gross → 0.22–0.35 at fraction 0.5; rule needs ≥ 0.30 net** | yes — all three free sources exist | DECLINED #16 on R3 (conservative) |
| Russell reconstitution at the micro-cap boundary (Chang-Hong-Liskovich) | yes | no — significant only at the 1000 cut-off | t = 1.45 / 1.25 at the 3000 cut-off | no free Russell history | DECLINED #17 |
| micro-cap tax-loss | incentive, not mandate | partly | — | — | already falsified in-house (June placebo) |
| SPAC trust redemption | yes | partly | 23.9% EW annualised | — | reviewed 2026-09-11, ~40 bets/yr |
| closed-end fund liquidation | yes | ? | — | — | no primary source found |

Strongest anti-evidence, re-read by the orchestrator: Wardlaw (abstract): outflows leave "a fairly
negligible quarterly decline in returns, with no subsequent reversal"; HXZ: micro-cap anomalies
"more apparent than real" because of trading costs; Macey et al. on their own effect (above).

## 4. What this means for Step 0 and for the owner's decision

1. **The corner exists on free data.** That is new: the 2026-09-08 fire-sale test could not reach
   sparse ownership; today's join shows ~1.1–1.5k listed names per quarter where it holds. It is
   the first universe in this project where "big money cannot collect it" is true by measurement.
2. **The forced-flow claims in that corner are small.** The only buildable one is 0.44–0.70 GROSS
   by the paper's own t-statistics over 25 years. Under the rule written before measuring, that is a
   decline. Under a waiver it would be a build with a 6.8-year N-PORT window whose in-sample
   number would still need the 3-year wait to mean anything.
3. **Day 6's number is 0 unless the owner waives R3 for #16.** The honest expectation recorded in
   the rule (1–3 admissible, 0–2 produced) was optimistic by one: 0 admissible.
4. Cost of a waiver, stated: an Opus build of a new universe path (N-PORT full-holdings
   re-extraction for ~5k CUSIPs × 27 quarters, flows from FUND_REPORTED_INFO, Alpaca panel with
   delisting cuts, FTD map routed to the worktree) — roughly a day's sequential work plus
   verification; nothing in it is blocked.

## 5. Not verified / left open
Wardlaw 2020 full text (SSRN 403, Wiley gated, author's site links only to those two);
whether Alpaca's paid tiers include OTC bars; the involuntary-delisting rate 2016+; whether the
FTD-mapped 6.7–8.8k CUSIPs are representative of the 21–27k (US-listed names should map well —
the unmapped are mostly foreign — but this was not measured).

## 6. Appended after the breadth run completed (27/27 quarters, 0 errors, ~1 min each)

Sparse-ownership LISTED universe per quarter: **1,070 → 1,810** names (rising over time; the
"now delisted" column collapses in recent quarters simply because those names have not had time
to die). §1–§4 above quoted 1,070–1,468 from the first nine quarters; the full range is 1,070–1,810.

| quarter | equity CUSIPs | median owners | p90 | 5–47 owners | mapped to listed Alpaca | 5–47 AND listed | of which now delisted |
|---|---|---|---|---|---|---|---|
| 2019q4 | 21,047 | 4 | 142 | 6,291 | 4,575 | **1,070** | 146 |
| 2020q1 | 25,148 | 3 | 131 | 7,199 | 4,678 | **1,126** | 158 |
| 2020q2 | 25,680 | 3 | 123 | 7,511 | 4,847 | **1,173** | 138 |
| 2020q3 | 26,311 | 3 | 116 | 7,741 | 4,968 | **1,221** | 139 |
| 2020q4 | 26,046 | 3 | 121 | 7,692 | 5,056 | **1,248** | 157 |
| 2021q1 | 25,858 | 3 | 121 | 7,382 | 5,123 | **1,276** | 142 |
| 2021q2 | 26,529 | 3 | 122 | 7,805 | 5,259 | **1,348** | 149 |
| 2021q3 | 26,891 | 3 | 119 | 7,935 | 5,336 | **1,385** | 127 |
| 2021q4 | 26,889 | 4 | 120 | 8,501 | 5,490 | **1,468** | 112 |
| 2022q1 | 27,464 | 3 | 121 | 7,956 | 5,631 | **1,509** | 100 |
| 2022q2 | 27,327 | 3 | 124 | 8,082 | 5,555 | **1,503** | 77 |
| 2022q3 | 27,571 | 3 | 114 | 8,097 | 5,521 | **1,465** | 43 |
| 2022q4 | 26,907 | 3 | 120 | 7,841 | 5,479 | **1,453** | 13 |
| 2023q1 | 26,386 | 3 | 121 | 7,303 | 5,496 | **1,433** | 6 |
| 2023q2 | 26,571 | 3 | 126 | 7,710 | 5,574 | **1,454** | 8 |
| 2023q3 | 26,369 | 3 | 121 | 7,378 | 5,560 | **1,439** | 7 |
| 2023q4 | 25,152 | 4 | 132 | 7,573 | 5,622 | **1,458** | 11 |
| 2024q1 | 24,991 | 3 | 131 | 6,961 | 5,659 | **1,506** | 6 |
| 2024q2 | 25,882 | 3 | 129 | 7,550 | 6,233 | **1,759** | 162 |
| 2024q3 | 23,649 | 4 | 150 | 7,802 | 5,894 | **1,614** | 8 |
| 2024q4 | 23,124 | 4 | 148 | 7,192 | 5,893 | **1,520** | 7 |
| 2025q1 | 22,814 | 4 | 153 | 6,998 | 6,030 | **1,506** | 5 |
| 2025q2 | 22,863 | 4 | 157 | 7,082 | 6,231 | **1,590** | 8 |
| 2025q3 | 23,477 | 4 | 148 | 6,893 | 6,411 | **1,599** | 7 |
| 2025q4 | 23,683 | 3 | 145 | 6,941 | 6,620 | **1,673** | 6 |
| 2026q1 | 24,013 | 3 | 137 | 6,911 | 6,803 | **1,725** | 6 |
| 2026q2 | 24,946 | 4 | 144 | 7,576 | 7,114 | **1,810** | 7 |

Independent re-derivation (orchestrator, pandas groupby path instead of the script's dict/set loop),
2026q2: 24,945 CUSIPs vs 24,946 (one CUSIP apart — pandas' bad-line skip on one row; that CUSIP has
> 47 owners), median 4 = 4, 5–47 owners 7,576 = 7,576, ≤ 47 owners 21,476 = 21,476.
