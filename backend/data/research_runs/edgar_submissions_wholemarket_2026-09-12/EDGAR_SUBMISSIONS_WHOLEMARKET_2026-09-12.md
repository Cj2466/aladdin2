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

**Update: the orchestrator gave GO on a full delisted-name ingest, with a
hard requirement** -- see section 5b.

## 5b. Delisted-name ingest, GO decision executed (two-independent-check gate)

**Why the gate is mandatory, not optional caution:** the orchestrator measured
the panel's TRULY stopped-trading population precisely (last bar <= 2026-08-12,
`delisting_outcomes_2026-09-12/dead_names.csv`, 1,817 tickers -- a stricter,
different denominator than section 5's "Alpaca-inactive" 2,092) and found only
**5 resolve via `company_tickers.json` (0.3%)**: AYR, CONE, EMI, FBYDP, SVA.
Hand-checking those 5 found **2 are the wrong company** -- CONE's ticker had
been reassigned to "Compass Sub North, Inc." (the real CyrusOne, acquired
2022, is a different, defunct CIK) and EMI to "Encore Medical, Inc." A
ticker-string match on a dead name is, empirically, more likely wrong than
right. This reconciles section 5's 127/2,092 (6.1%) figure against the
orchestrator's 5/1,817 (0.3%): different, overlapping but not identical
denominators -- Alpaca's `inactive` flag catches many tickers that are not
"stopped trading" in the strict sense (`dead_names.csv` and the panel's
`inactive` set overlap heavily but are not the same population), which is why
the two numbers legitimately differ rather than one being wrong.

**The two required, independent checks** (`resolve_delisted_names.py`, reusing
`probe_delisted_cik_resolution.py`'s name-search/fallback ladder unchanged):

1. **Name match** -- browse-edgar company-name search on `universe.csv`'s
   `name` (1,418/1,817 have one) or, failing that, a FTD-DESCRIPTION-derived
   name (see below). Rejected as ambiguous if 0 or >1 candidates survive.
2. **Date overlap** -- the candidate CIK's real filing history (fetched live,
   merged into the shared store) must overlap `[first_bar, last_bar]` from
   `dead_names.csv`. This is exactly the check that would have caught
   CONE/EMI: verified by hand before the full run that CONE's name
   ("CyrusOne Inc Common Stock") now resolves to CIK **1553023**
   ("CyrusOne Holdco LLC" -- the real post-reorg entity), not the wrong
   2103884.

**No-name cohort (399/1,817):** the brief's suggested route (Form 13F
quarterly holdings, CUSIP -> NAMEOFISSUER) was probed first, not bulk-run
blind. Zero 13F quarter archives were cached locally (only 29 fails-to-deliver
archives were); fetching one to test (2018q3, 46.6MB, now cached in
`data/form13f_raw/`) found it recovers a name for every ticker with a cached
CUSIP -- but an EQUIVALENT name proxy was already sitting for free in the
same cached FTD archives' own DESCRIPTION field (not parsed by the shared
`form13f_provider.py`, which drops it), with IDENTICAL 14/14 recovery on the
probe sample. Used FTD DESCRIPTION instead: recovers a name for **234/399
(58.6%)**; the other 165/399 have no CUSIP in any cached FTD archive.
FTD-description-sourced names resolved through check 1 at a much lower rate
than clean Alpaca names, though (46/234 = 19.7% vs. 665/1,418 = 46.9%) --
FTD's DESCRIPTION field is truncated (~30 chars) and abbreviation-heavy
("WISDOMTREE ASIA LOCAL DEBT FUN", "GLOBAL BRASS & COPPER HLDGS,IN"), which
the current suffix-stripping ladder handles worse than Alpaca's fuller
names. Noted as a real, uncorrected limitation rather than iterated on
further under this task's time budget.

**Final counts, all 1,817 stopped-trading tickers:**

| status | count | % |
|---|---|---|
| resolved (both checks passed) | 711 | 39.1% |
| rejected_by_name_zero | 845 | 46.5% |
| rejected_by_name_ambiguous | 90 | 5.0% |
| rejected_by_date_overlap | 6 | 0.3% |
| no_name (no name from any free source) | 165 | 9.1% |

The 6 `rejected_by_date_overlap` cases are the gate's second check actually
firing -- a clean 1:1 name match whose real filing history does not cover the
ticker's trading window, exactly the CONE-shaped failure mode the gate exists
to catch.

**20-ticker sample table** (same sample as section 5's probe, minus ACETQ and
ACLL which are not in the 1,817 stopped-trading population -- replaced with
the next two dead tickers alphabetically, ACTDU and ACTTU, to keep 20):

| ticker | status | name source | query used | n_matches | CIK |
|---|---|---|---|---|---|
| ACIA | resolved | alpaca | Acacia Communications, Inc | 1 | 1651235 |
| CLDR | resolved | alpaca | Cloudera, Inc | 1 | 1535379 |
| FIT | resolved | alpaca | Fitbit, Inc | 1 | 1447599 |
| ZNGA | resolved | alpaca | Zynga Inc | 1 | 1439404 |
| AABA | rejected_by_name_zero | ftd_description | ALTABA INC COM | 0 | -- |
| ALOG | no_name | -- | -- | -- | -- |
| ARMO | no_name | -- | -- | -- | -- |
| AACQU | resolved | alpaca | Artius Acquisition | 1 | 1817888 |
| ABDC | resolved | alpaca | Alcentra Capital Corp | 1 | 1578620 |
| ACACU | resolved | alpaca | Acri Capital Acquisition | 1 | 1914023 |
| ACAMU | rejected_by_name_ambiguous | alpaca | Acamar Partners Acquisition Corp | 2 | -- |
| ACBI | resolved | alpaca | Atlantic Capital Bancshares, Inc | 1 | 1461755 |
| ACC | rejected_by_name_zero | alpaca | American Campus Communities, Inc | 0 | -- |
| ACGLP | resolved | alpaca | Arch Capital Group Ltd | 1 | 947484 |
| ACKIT | resolved | alpaca | Ackrell SPAC Partners I Co | 1 | 1790121 |
| ACKIU | resolved | alpaca | Ackrell SPAC Partners I Co | 1 | 1790121 |
| ACSF | no_name | -- | -- | -- | -- |
| ACTCU | rejected_by_name_ambiguous | alpaca | ArcLight Clean Transition Corp | 2 | -- |
| ACTDU | resolved | alpaca | ArcLight Clean Transition Corp. II | 1 | 1842279 |
| ACTTU | resolved | alpaca | Act II Global Acquisition Corp | 1 | 1753706 |

Note AABA (Altaba, the real Yahoo successor) rejected: its Alpaca `name` is
empty, so it fell to the FTD-description name "ALTABA INC COM", whose
trailing "COM" (FTD's abbreviation for "common stock", not covered by the
current suffix ladder) breaks the browse-edgar prefix match -- a concrete
instance of the FTD-description limitation above, not a data problem with
Altaba itself (full text search independently confirms CIK 1011006 is the
real Altaba). ACC and AABA both illustrate the gate correctly refusing to
guess rather than silently taking a fallback.

**Rebuild of `announcement_dates.csv`** (`rebuild_announcement_dates.py`),
adding a `population` column (living / formerly_listed):
- The 5 tickers that had slipped into the "living" table via the naive
  ticker-match path (AYR, CONE, EMI, FBYDP, SVA) are reclassified. AYR/FBYDP/
  SVA's gate-verified CIK is IDENTICAL to their original CIK -- rows unchanged,
  just relabeled. **CONE and EMI each contributed ZERO rows to the original
  table** (measured: neither the wrong nor the right CIK filed an Item 2.02
  8-K in the [2000-01-01, 2026-09-12] window) -- no fabricated events actually
  existed to delete, but that is fortunate, not a property of the gate having
  caught something, and is stated as such. After the rebuild CONE correctly
  shows 37 real CyrusOne earnings events (2013-2021) under CIK 1553023.
- 711 resolved tickers contributed **16,122 new formerly_listed announcement
  rows**. Final table: **184,048 rows total (167,926 living / 16,122
  formerly_listed)**.

**Events and distinct tickers per year, living vs. formerly_listed** (last 6
years shown; full table in `announcement_dates_report.json`):

| year | living events | living tickers | formerly_listed events | formerly_listed tickers |
|---|---|---|---|---|
| 2021 | 13,459 | 3,288 | 912 | 264 |
| 2022 | 14,619 | 3,490 | 573 | 191 |
| 2023 | 15,254 | 3,649 | 450 | 118 |
| 2024 | 15,841 | 3,811 | 408 | 108 |
| 2025 | 16,396 | 3,975 | 341 | 94 |
| 2026 (partial) | 12,676 | 4,084 | 237 | 80 |

The formerly_listed share shrinks going backward in real time from the
present (mechanically: `dead_names.csv` requires a LAST bar, so this cohort
is entirely companies that had already stopped trading by 2026-08-12 --
recent years show more of them because more delistings are recent, not
because coverage is better further back).

**Final honest coverage sentence, for the memo:** of the panel's 1,817
tickers that stopped trading, the announcement-dates table now covers 711
(39.1%) with a name-match- and date-overlap-verified CIK; the remaining 1,106
are excluded rather than guessed at (845 no single name match, 90 ambiguous
name matches, 165 no name recoverable from any free source tried, 6
name-matched but rejected on date overlap). **The table is no longer
living-company-only, but it is still far from complete for the formerly-listed
population, and every gap is an explicit exclusion, not a silent one.**

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
`build_announcement_dates.py`, `announcement_dates.csv` (now with a `population`
column), `announcement_dates_report.json`, `probe_delisted_cik_resolution.py`,
`delisted_cik_resolution_probe_report.json`, `resolve_delisted_names.py`,
`delisted_resolution.csv`, `delisted_resolution_report.json`,
`resolve_delisted_progress.jsonl`, `resolve_delisted_stdout.log`,
`rebuild_announcement_dates.py`, `delisted_gate_20sample_table.json`,
`measure_wholemarket_report.py`, `edgar_submissions_wholemarket_report.json`,
this file.

---

## Orchestrator verification, appended 2026-09-12 (Opus 5, own code, not the agent's)

**Reproduced exactly:** 184,048 rows (167,926 living / 16,122 formerly_listed), 4,799 distinct
tickers of which 481 formerly listed; 711 of 1,817 stopped-trading tickers resolved (39.1%).

**Hand-checked resolutions — all correct, events ending before the stock stopped trading:**

| ticker | events | first → last event | stock last traded |
|---|---|---|---|
| ACIA (Acacia) | 20 | 2016-08-11 → 2021-01-11 | 2021-02-26 |
| CLDR (Cloudera) | 18 | 2017-06-08 → 2021-08-30 | 2021-10-07 |
| ZNGA (Zynga) | 28 | 2015-05-06 → 2022-05-09 | 2022-05-20 |
| FIT (Fitbit) | 23 | 2015-08-05 → 2020-11-04 | 2021-01-13 |
| CONE (CyrusOne) | 37 | 2013-02-26 → 2022-02-16 | 2022-03-24 |
| ALOG, ARMO | 0 | — | rejected by the gate (no usable name), an honest exclusion |

**A gate weakness I found that the agent's own counts did not surface.** The date-overlap check
rejected only 6 tickers, but measuring the EVENTS rather than the entity shows more:
- **1,985 of the 16,122 formerly-listed events (12.3%) are dated AFTER their ticker's last trade.**
  They can never produce a return — no price exists — so they will silently drop out of any build.
  Usable formerly-listed events are therefore **14,137**, not 16,122.
- **87 tickers have ALL their events after the last trade.** 71 of the 87 are SPAC units or
  warrants (symbol ends U/W): the legal entity kept filing after the unit stopped trading, so the
  CIK is right and the TICKER is the wrong vehicle. The remaining 16 (ANDAR, ARYA, ATSPT, BRPAR,
  BRPM, CLAQR, CMSS, DWIN, FBYDP, GHIV, GPAQ, GPCOR, …) need individual review before use.
- Cause: the gate tested overlap against the CIK's WHOLE filing history, which includes non-earnings
  filings from before the ticker died, so an entity that only began reporting earnings later still
  passes. **Fix for whoever builds on this table: require each EVENT's date to fall inside the
  ticker's own trading window, not merely the entity's filing history to overlap it.** Nothing is
  deleted here; the rule belongs in the consumer, and the count above is the size of the issue.

**Not a correctness problem, stated for the record:** those 1,985 events cannot fabricate a return;
they can only be dropped. The risk they carry is a silent shrinkage of the sample, which is why the
number is recorded rather than left to be discovered later.
