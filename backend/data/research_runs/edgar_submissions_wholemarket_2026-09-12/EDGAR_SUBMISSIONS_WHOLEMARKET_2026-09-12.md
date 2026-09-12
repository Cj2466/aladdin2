# EDGAR submissions store: whole-market extension + announcement-date table (2026-09-12)

**Step A4.** Extends `edgar_submissions_store` from the 503-ticker PEAD screening
universe to the whole-market price panel (`whole_market_panel_2026-09-12/universe.csv`,
14,509 distinct symbols) and builds the Item 2.02 (earnings 8-K) announcement-date
table a later family will read.

## 1. Universe -> CIK resolution

Fresh fetch of `https://www.sec.gov/files/company_tickers.json` (797,931 bytes,
sha256 `26602b2f...`, committed alongside this report). Resolves **7,143 of 14,509**
distinct symbols (exactly matches the count `universe.csv`'s own
`in_sec_company_tickers` column had already flagged -- 0 discrepancies), collapsing
to **6,038 distinct CIKs** via share-class/dual-ticker overlap.
See `build_universe_ciks.py`, `universe_ciks.csv`, `universe_cik_resolution_report.json`.

## 2. Ingest

`ingest_wholemarket.py` ran the full 6,038-CIK pass in the background
(~43 minutes, 0.15s/request, SEC's declared user agent, resumable via the store's
own coverage ledger).

| | before | after |
|---|---|---|
| CIKs in store | 500 | 6,040 |
| filing rows | 566,131 | 3,702,630 |

- 6,038/6,038 CIKs fetched OK, **0 failures**.
- 3,136,499 new rows written; 562,970 already present (overlap with the prior
  503-ticker store).
- **2,322 filing revisions held back** (first-write-wins refused them, as
  designed) -- all are `acceptanceDateTime`-only shifts of +/-4h or +/-5h under an
  unchanged accession and `filingDate`, consistent with an EST/EDT UTC-offset
  artifact on SEC's side, not a real content change. `filingDate` (the field this
  family actually reads) is identical in all 2,322.

## 3. Announcement dates

Built via `submissions_as_of()` read directly from the store plus
`cross_sectional_pead._parse_item_202_rows` (reused unchanged) -- **not**
`fetch_item_202_events`, to avoid a second ~18-minute live re-fetch pass over data
this run had just ingested into the same store. See `build_announcement_dates.py`.

**167,993 announcement rows, 4,320 distinct tickers with >=1 event.**

| year | events | distinct tickers | | year | events | distinct tickers |
|---|---|---|---|---|---|---|
| 2004 | 225 | 167 | | 2016 | 7,539 | 1,854 |
| 2005 | 869 | 226 | | 2017 | 8,601 | 2,128 |
| 2006 | 976 | 260 | | 2018 | 9,801 | 2,394 |
| 2007 | 1,255 | 335 | | 2019 | 10,708 | 2,627 |
| 2008 | 1,577 | 407 | | 2020 | 12,161 | 2,868 |
| 2009 | 1,747 | 467 | | 2021 | 13,461 | 3,289 |
| 2010 | 2,141 | 585 | | 2022 | 14,621 | 3,491 |
| 2011 | 2,760 | 730 | | 2023 | 15,257 | 3,650 |
| 2012 | 3,301 | 865 | | 2024 | 15,846 | 3,813 |
| 2013 | 4,166 | 1,075 | | 2025 | 16,403 | 3,977 |
| 2014 | 5,327 | 1,366 | | 2026 (partial, through 09-12) | 12,682 | 4,086 |
| 2015 | 6,569 | 1,644 | | | | |

Breadth rises monotonically -- expected, since it reflects both real listing
growth and the truncation described below.

## 4. Truncation

**3,178 of 6,038 CIKs (52.6%) have an earliest stored filing after 2016-01-01.**
Distribution by year of that earliest-filing date:

| 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|
| 279 | 328 | 297 | 290 | 384 | 436 | 226 | 212 | 266 | 351 | 109 |

**Caveat, stated plainly:** this number does NOT separate genuine
`filings.recent` truncation from a company that simply never existed before
2016 (a large share of the whole-market universe are post-2016 IPOs/SPACs whose
true first filing legitimately falls after that date). It is an upper bound on
possible loss, not a measured loss against each company's true history --
that needs an independent incorporation/registration-date source this run did
not fetch.

## 5. Delisted-ticker gap -- LIVING-COMPANY ONLY, per the orchestrator's correction

**The announcement-dates table above covers only companies resolvable through
SEC's CURRENT-ticker `company_tickers.json` mapping.** Measured directly here:
of the panel's 2,092 `status == inactive` symbols, 127 (6.1%) resolve that way.
This is a materially different number than the orchestrator's stated 5/1,817
(0.3%) -- **not reconciled**, and flagged rather than silently overridden.
Spot-checking 15 of the 127 shows genuine name matches (Alpaca's `name` and
SEC's `entity_name` agree, e.g. AMBR/"Amber International Holding" ->
CIK entity "Amber International Holding Ltd", ARRY/"Array Technologies" ->
same), so these are not ticker-recycling false positives on their face -- but
Alpaca's `inactive` status covers several different real-world reasons (fully
delisted and defunct, ticker/exchange changed, temporarily suspended, merged
with the surviving entity keeping the CIK, ...) and this run did not verify
which of the 127 are actually still-CIK-findable-but-truly-gone vs. some other
inactive reason. Whichever the correct denominator, **the qualitative
conclusion is unchanged: this table is LIVING-COMPANY-ONLY (at best a small
single-digit-percent slice of the delisted population is covered) and must not
be used as a survivorship-bias-free panel.**

A probe (`probe_delisted_cik_resolution.py`, 20-ticker deterministic sample:
ACIA, CLDR, FIT, ZNGA, AABA, ALOG, ARMO + 13 more alphabetically) tested three
free routes before any full delisted-name ingest:

1. **SEC browse-edgar company-name search** (`getcompany&company=<name>`) --
   covers every CIK ever registered, not just current tickers. Using
   `universe.csv`'s own `name` column with a period-strip + corporate-suffix-
   strip fallback ladder, resolves **11/15 attempted 1:1 (73%)**. Behavior is a
   fuzzy, not strict, prefix match: measured live that a trailing period breaks
   an otherwise-good query ("Zynga Inc." -> 0 matches, "Zynga Inc" -> 1) and a
   trailing corporate-form word can too ("Artius Acquisition Inc" -> 0,
   "Artius Acquisition" -> 1). **5/20 sample tickers (25%) have an EMPTY `name`
   in universe.csv and this route cannot even be attempted for them from data
   already held.**
2. **EDGAR full text search** (`efts.sec.gov`, 2001-present) -- finds the
   right CIK among candidates for distinctively-named companies (Cloudera,
   Acacia, Zynga) but its highest-hit-count CIK is **wrong** for generic-string
   collisions (FIT -> "Fortress Investment Trust II" not Fitbit; ABDC ->
   "AmeriSourceBergen" not Alcentra Capital). Corroborating signal only, not a
   standalone resolver.
3. **Store's own `tickers` field** on already-held CIKs -- 0 hits (expected;
   none of the 6,038 currently-listed CIKs share a former ticker with the dead
   sample).

**No full delisted-name ingest was started.** Recommend it as its own,
separately-scoped follow-up (with its own go/no-go) given routes 1+2 leave a
non-trivial uncovered/ambiguous remainder even on this small sample.

## 6. Spot-check

Rule: first 10 tickers, sorted alphabetically, among the 3,312 tickers with
>=20 events in the table. Sample: A, AA, AAL, AAME, AAMI, AAOI, AAON, AAP, AAPL,
AAT. All 10 show a median inter-filing gap of 91-92 days (~4/year) -- a real
quarterly cadence. A few individual outlier gaps exist (e.g. AAON max 364 days,
AAME max 234 days) but were not individually traced to a cause; none dropped.

## 7. Verification

- `backend/data/price_store/` and `backend/data/price_store_alpaca/`: **not
  modified** (confirmed via `git status`/mtime -- this step never touches
  price data).
- `ruff check` on every new file in this directory: **all pass**.
- `pytest -q tests/test_edgar_submissions_store.py tests/test_shared_cache_routing.py tests/test_worktree_database_routing.py`:
  see commit message / orchestrator report for the exact pass count.

## Files

`build_universe_ciks.py`, `universe_ciks.csv`, `universe_cik_resolution_report.json`,
`company_tickers_2026-09-12.json` (+`.sha256`), `ingest_wholemarket.py`,
`ingest_manifest_2026-09-12T1247Z.json`, `ingest_progress.jsonl`, `ingest_stdout.log`,
`build_announcement_dates.py`, `announcement_dates.csv`,
`announcement_dates_report.json`, `probe_delisted_cik_resolution.py`,
`delisted_cik_resolution_probe_report.json`, `measure_wholemarket_report.py`,
`edgar_submissions_wholemarket_report.json`, this file.
