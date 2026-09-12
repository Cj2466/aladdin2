# M3 result -- Thai (SET/mai) free-data survivorship and daily-files gap

Measured 2026-09-12. Everything below is either (a) a script's committed output
(`m3_delisted_survivorship.py` -> `m3_survivorship_output.json`/`.txt`) or
(b) a fetched page/PDF committed under `m3_sources/` with SHA-256 in
`m3_SOURCES.md`. Nothing was built, no strategy formed, no DB row written.

## M3a -- survivorship, measured not hand-picked

Source: SET's own delisted-securities page
(`https://www.set.or.th/en/market/information/securities-list/delisted-list`),
scraped in full via a headless browser (346 rows, 18 pages) since the page is
Nuxt SSR/client-hydrated and this agent could not find its JSON API in the
static bundle -- consistent with the review's finding that SET's JSON
endpoints 403 a plain script. 256 of the 346 delisted symbols have a
delisting date in 2000-2026; each was probed on Yahoo (`yfinance`,
`<SYM>.BK`, `period=max`).

| | count | fraction |
|---|---|---|
| zero bars returned | 230 / 256 | **89.8%** |
| retained (last bar within 30 days of the real SET delisting date) | 11 / 256 | 4.3% |
| other (bars exist, but end well before/after the delisting date) | 15 / 256 | 5.9% |

By delisting year (full table in `m3_survivorship_output.txt`): every year
2000-2020 is 100% zero-bars except 2018 (2 of 4 retained). The zero-bars
fraction only meaningfully drops in 2024-2026 (very recent delistings, where
Yahoo has not yet purged the symbol) -- 2024: 15/29 zero, 2025: 9/13 zero,
2026: 3/7 zero.

**Reading it honestly**: the review's hand-picked sample of 12 dead names
(8/12 = 66.7% zero-bars) *understated* the problem. Measured across the full
population of symbols delisted 2000-2026, Yahoo's free `.BK` feed is
**89.8% survivor-biased** -- effectively unusable for any long-horizon
cross-sectional Thai study without a separate, non-Yahoo source of prices for
delisted names. The "retained" 4.3% is almost entirely very-recent (2024-26)
delistings that Yahoo has not yet dropped, not a real historical archive.

## M3b -- SET's daily files, free vs. paid

Full table in `m3_set_daily_files.md`. Summary:

| item | free without SETSMART? | granularity | history |
|---|---|---|---|
| Daily investor-type breakdown (local/foreign/institution/proprietary) | Yes (page renders via JS, no key) | Market-wide only, not per-stock | Only 3 fixed windows shown (today / MTD / YTD); **no date picker, no way to pull an arbitrary past day** |
| Daily NVDR trading by stock | Yes | Per-stock | Single-day picker; **could not navigate the calendar past the current month** (no nav-arrow controls found in the DOM; input is read-only) -- effectively ~10 recent trading days confirmed, older days NOT VERIFIED as reachable |
| Daily short-selling by stock | Yes | Per-stock | Date-RANGE picker; page itself is labeled **"Back to 6 months"**, but this agent could not operate the calendar navigation to confirm it -- treat "6 months" as SET's own claim, not independently verified |
| Program trading value | Yes | Market-wide only | Same "Back to 6 months" label, same unconfirmed-navigation caveat |

**Candidate paid-data gap P10** (for the orchestrator to log, not acted on
here): a genuine multi-year, per-stock-and-per-day investor-type / NVDR-flow /
short-interest panel for Thailand is not confirmed obtainable free at the
depth a cross-sectional backtest would need -- it is a SETSMART or SET
vendor-feed product (`m3_sources/end_of_day_service.html`). Nothing was
priced or purchased.

**Policy finding**: SET's Non-Display Usage Policy
(`m3_sources/non_display_usage.pdf`) requires a paid subscriber contract for
machine/algorithmic use of its data, but on its face addresses subscribers to
SET's own FEED product, not the public website. Separately, SET's website
Terms and Conditions (`m3_sources/terms.html`, section 1.3) restrict use of
website content to "personal and non-commercial use" and prohibit copying,
storing, or redistributing content without written permission. This agent
surfaces this as a fact found while fetching pages -- it did not interpret
whether this project's research use is inside or outside that restriction;
that is a judgment call for the project owner, not something decided or
acted on here.

## Caveats / what could NOT be verified

1. **Calendar-navigation limitation may be a scraping-tool artifact, not a true 10-day/limit.** This agent found zero navigation-arrow elements in the DOM of the NVDR, short-sales, and program-trading date pickers (confirmed by DOM dump and a screenshot), and keyboard shortcuts named in the widget's own `data-helptext` had no effect within the time tried. It is possible a real (non-headless, human-driven) browser session, or a different interaction sequence, would reveal a working control this agent missed. This is reported as NOT VERIFIED, not as a proven hard limit.
2. **The delisted list itself may be incomplete.** SET's page states "346 Search Results" as of 2026-09-12 and covers 1975-2026; this agent did not cross-check that number against any second source (e.g. an annual SET statistics PDF), so 346 is SET's own count, taken at face value.
3. **Yahoo ticker mapping is naive.** Every symbol was probed as `<SYM>.BK` exactly as SET spells it; several delisted symbols contain hyphens (e.g. `3K-BAT`, `AF-O`) that may not be Yahoo's actual historical ticker for that name (Yahoo sometimes uses a different root for amalgamated/renamed entities) -- these are folded into "zero bars" without individually confirming Yahoo never had *any* ticker for that company under *any* symbol.
4. **SET FEED / SETSMART depth and price were not investigated.** This agent did not attempt to determine what SETSMART or the SET FEED vendor product actually contains, how far back it goes, or what it costs -- only that the free public pages could not be confirmed to provide multi-month per-stock history.
5. **NVDR-by-stock and short-sales-by-stock "Export Excel" buttons were not exercised.** The browser sandbox used for this measurement blocks script-driven file downloads, so whether "Export Excel" produces a longer or differently-scoped dataset than the on-screen table was not tested.
