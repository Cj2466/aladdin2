# Point-in-time EDGAR submissions store (built 2026-09-10)

Closes gap 1 of the three named in `edgar_facts_store_2026-09-10/`'s §6. It turned out
to be a worse defect than the one that motivated it.

## 1. The endpoint loses data, permanently

`cross_sectional_pead` reads earnings-announcement dates from
`https://data.sec.gov/submissions/CIK##########.json`. That document's `filings.recent`
block is **bounded**; everything older moves into separate `filings.files` archives this
project does not fetch. For an active filer the covered window therefore **slides
forward**: an 8-K visible in one fetch is absent from a later one, and no amount of
refetching brings it back.

The bound, measured across all 503 universe tickers on 2026-09-09 rather than recalled:

| | |
|---|---|
| rows per ticker | 29 .. 26,014, median 1,001 |
| tickers holding 995–1,010 rows | 435 of 503 |
| tickers holding more than 1,100 | 6 — JPM 26,014, MS 19,798, GS 16,110, C 13,383, BAC 11,373, BLK 1,762 |
| of those 6, earliest filing within the last year | 5 (the five banks all bottom out at exactly one year) |

Consistent with `recent` holding the greater of about 1,000 filings or one year of them.
That rule is **inferred from this project's own measurement, not verified against SEC's
documentation** — but the consequence does not depend on its exact form: JPM's earnings
8-Ks older than one year are not in the endpoint today, and next month another month of
them will be gone.

This is not a hypothesis about the future either. The family's own 2026-08-28 production
run measured the loss and disclosed it: of 503 tickers, **181 had truncated `recent`
coverage** — their 8-Ks before the 2018-04-07 fetch floor were already unreachable. The
identical measurement (≥1,000 rows AND earliest filing after the floor) on **2026-09-09
gives 185**. Four more tickers lost their early coverage in twelve days, while nobody was
looking.

Combined with how the family is actually invoked, that is a standing drift generator:

| | |
|---|---|
| callers passing `events=` (a cached list) | **none** — `run_dividend_convention.py`, `run_preservation_score.py`, `run_global_effective_n.py` and `dormant_rescore.py` all call `run_pead_screening(start, end)` |
| the event-cache file the module supports | `data/pead_edgar_item202_events.json` — **has never existed on disk** |

So every run fetches live, and re-running `pead_ear` on the *same frozen window* months
later necessarily scores a **smaller** sample than the run before it. That is consistent
with the −0.016 drift recorded against pead_ear in the Dormant pool. Consistent with,
not proven to be the whole of it: the loss is mechanical and certain, its exact
contribution to that number is not recoverable, because no earlier copy of the endpoint's
response exists.

An earlier note in the fact-store memo said pead had "no cache at all". That was
imprecise and has been corrected: the *mechanism* exists, the *file* never did, and no
caller uses it.

## 2. What was built

`app/services/market_data/edgar_submissions_store.py` (20 tests), the sibling of
`edgar_facts_store.py` and routed the same way, to the main checkout.

- **Append-only retention is the point.** A filing row is keyed by its accession
  number, which is globally unique and immutable. Once stored it never leaves, so the
  truncation floor stops moving forward from the day the store starts. `submissions_as_of`
  serves the **union** of everything ever seen, which is always a superset of what the
  endpoint returns today.
- **A drop-in.** It rebuilds SEC's exact nested `filings.recent` parallel-array shape,
  so `cross_sectional_pead._parse_item_202_rows` consumes it with no change. A store
  that needed its consumer rewritten would be a second implementation of the parse.
- **Faithful.** All 15 `filings.recent` fields are stored, not the four pead reads today.
- **First-write-wins.** A row whose content changed under an accession already stored is
  refused and recorded on `report.revisions`.
- **Two dates, never conflated**, as in the fact store: `filingDate` is SEC's own and the
  economic point-in-time key; `first_seen` is the store's and the reproducibility key.
- **Ragged and malformed responses degrade** rather than failing a research run; rows
  without an accession or a filing date cannot be dated and are dropped.

**Wiring.** `fetch_item_202_events` merges each fetched document into the store and then
parses the union. What the store contributed beyond the live response is **counted and
disclosed** on `EdgarFetchReport.n_tickers_recovered_from_store` and
`.n_events_recovered_from_store` — a sample that grew for a data-retention reason is a
sample-construction fact, and this project reports those rather than absorbing them.
`submissions_store=EdgarSubmissionsStore(None)` restores the exact pre-2026-09-10
behaviour.

## 3. The ingest

```
503 tickers requested, 0 unresolved, 0 fetch failures
500 CIKs stored (3 pairs of dual-class tickers share a CIK), 566,131 filing rows, 16.6 MB
filing dates 2005-03-22 .. 2026-09-09;  first_seen 2026-09-09 (UTC)
filing revisions held back: 0
```

Every form type is stored, not only 8-Ks, so the next consumer that needs 10-K filing
dates does not have to go back to an endpoint that has meanwhile dropped them.

**What is retained versus what the endpoint still offers**, by the family's own
truncation definition: 185 of 503 tickers are truncated today. For the five heaviest
filers the store now holds exactly what the endpoint had on 2026-09-09 and will hold it
permanently, while the endpoint's own floor keeps advancing.

**Run it regularly.** Every day the store is not running is a day of filings that could
still have been captured and, once they leave `filings.recent`, cannot be. The store is
append-only, so a re-run can only ever add.

## 4. What this changes, and what it does not

**It does not change any live registration.** pead_ear is a Dormant-pool entry, not a
live forward registration; nothing on the live tick path reads this store.

**It will change pead_ear's next look**, upward in sample size, for the 181-odd tickers
whose early events the endpoint had dropped. That is a data correction, not a spec
change — the frozen spec is untouched — but it must be recorded in the entry when the
look is taken, and the recovered-event counts on `EdgarFetchReport` are what to record.
The look is **not** taken here.

**It cannot recover what is already gone.** Filings that left `filings.recent` before
2026-09-09 are not in this store and are not retrievable from this endpoint. The store's
retention begins now. For the five bank tickers that means one year of history and no
more — pead's events for them before 2025-09-09 are permanently unavailable through this
route, and any future pead result must disclose that rather than treat their sample as
comparable to a full-history name's. Recovering the pre-2018 history would need SEC's `filings.files`
archives, which this project does not fetch — logged as a follow-up, not built.

## 5. A separate pead defect found while measuring (recorded, not fixed)

**XOM's earliest retained filing is 2026-07-01.** `cross_sectional_pead.load_cik_map`
resolves tickers through SEC's current ticker→CIK map with **no successor-shell
resolution**, so XOM maps to CIK 2115436 ("ExxonMobil Holdings Corp", registered
2026-07-01) rather than CIK 34088, which holds the operating history.
`edgar_xbrl_provider` got exactly this fix on 2026-09-02 (`dcdf864`); the pead path never
did, so XOM contributes about two months of filings to the sample instead of two decades.
Not fixed here: the fact provider's trigger ("the successor has zero annual facts") does
not transfer to submissions, and picking a different trigger is a construction decision
that needs its own measurement. Logged as a follow-up.

## 6. Still open, same defect class

* **`sec_shares_outstanding_provider`'s cache** (37 files) feeds the dividend calendar's
  share counts. Gap 2 of the fact-store memo's §6; unaddressed.
* **SIC histories** (`filing_sic/`, `submissions_sic/`) — `filing_sic` is keyed on
  immutable accessions and so is safe; `submissions_sic` is a current-day fallback read.
