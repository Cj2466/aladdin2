# Point-in-time EDGAR fact store (built 2026-09-10)

Closes the third and last of the input-mutation defects found while chasing the
Dormant pool's reproducibility gaps. The first two were the price store's share-basis
corruption (`c298dd3`) and its coverage ledger (`7002a41`, `1f8307f`). This one is
fundamentals.

## 1. The defect

Three families re-scored on frozen windows and did not reproduce: asset_growth
(+0.014), pead_ear (−0.016), dividend_payment_pressure (+0.049). The price store was
excluded by re-running them on the repaired shared store. Every remaining input they
have in common is EDGAR-derived and mutates in place:

| input | how it mutates |
|---|---|
| `data/edgar_companyfacts/CIK*.json` | rewritten whenever a consumer with `max_cache_age_days` set reads it. Since quality_cbop went live on 2026-09-08 its live panel (max age 1 day) rewrites all ~165 files every UTC day; 163 of 166 were rewritten on 2026-09-09. |
| `company_tickers.json` | rewritten the same way, and by SEC's construction maps **current** tickers only — so the universe a family resolves is itself a moving input. |

**The cost, demonstrated rather than argued.** On 2026-09-10 an attempt to attribute
asset_growth's drift looked for any copy of the 2026-09-04 cache. There is none: the
three apparent copies (the session scratchpad's `edgar_0908/` and two worktrees')
all resolve to **the same inode** as the live files, so they were never independent
copies. The question cannot be answered at all. A store that had existed on 09-04
would have answered it in seconds. That is the whole argument for this module.

## 2. What was measured first

Two things were checked before anything was built, because both could have changed
the design. Both are re-runnable: `measure_pit_contamination.py` next to this memo
reproduces every number below and writes them to a dated JSON.

**(a) Can new filings alone explain the drift? No.** Every annual-form entry in all
163 cached documents, across every taxonomy, was scanned for a `filed` date after
2026-09-04: **0 of 1,510,476**. So the fact content did not gain anything between the 09-04 run and
today, and the drift's cause is elsewhere — the ticker→CIK map and the SIC histories
are the remaining unversioned suspects, both now partly addressed (§4) and neither
provable retroactively.

**(b) Does the whole-document scan leak the future? Yes, and it is small.**
`extract_line_items` runs `_find_cross_filing_scale_conflicts` over the entire
document and drops every conflicted (tag, period), so a filing made in 2026 can
remove or re-resolve a period a 2015 backtest would have used. Measured across all
163 documents by comparing the full document against one truncated to `filed <= D`:

| | end-2018 | end-2021 | end-2024 |
|---|---|---|---|
| observations visible in the point-in-time view | 15,851 | 21,466 | 26,951 |
| **dropped** by the whole-document scan | 3 | 1 | 0 |
| **resolved differently at the same filed date** | 2 | 0 | 0 |
| differing value arriving with a *later* filed date | 98 | 10 | 7 |

The first two rows are the contamination: 0.03% of end-2018 observations, zero by
end-2024. Real, worth closing, and **not an explanation for any of the three
drifts** — recorded that way so the honest size survives. The third row is the
consuming family working correctly: a restated figure carries a later `filed` and
`build_point_in_time_factor_frame` delays it, which is exactly the intended
behaviour. Serving a dated document closes the first two rows for free.

## 3. What was built

`app/services/market_data/edgar_facts_store.py`, the fundamentals analogue of
`price_store.py`, plus 29 tests.

- **Storage.** Not N dated copies of a 4 MB document. Every SEC fact already carries
  `filed` and its accession `accn`, so a document is a set of immutable facts that
  only grows. The store keeps that set once per CIK, flattened, append-only, gzipped,
  and rebuilds any dated view on demand. Measured: 903 MB of raw copies → **47.5 MB**.
- **Two dates, never conflated.** `filed` is SEC's own publication date and the
  economic point-in-time key (`document_as_of(cik, as_of=D)`). `first_seen` is when
  *this store* first saw the fact and is the reproducibility key
  (`knowledge_cutoff=K` reconstructs what a run made on K actually read, including
  facts SEC had published but the store had not yet fetched).
- **First-write-wins**, as price_store §4. A fact's identity is
  (taxonomy, tag, unit, start, end, accn). A restatement arrives under a *new*
  accession and is simply a new fact, so `extract_annual_tag_series`' earliest-filed-wins
  still returns the originally published figure. A changed value under an accession
  already stored is refused and recorded on `report.revisions`.
- **Faithful, not consumer-shaped.** Every taxonomy, unit and form is kept, not just
  the 10-K/USD subset today's families read — a store filtered to one family's needs
  would send the next family back to the network, which is how the mutable cache
  became the problem.
- **Routed to the main checkout**, like the database and the price store.
- **The ticker→CIK map** is snapshotted by date, and only when it actually changed.
  `cik_map_as_of` never returns a later snapshot.

Wiring (`edgar_xbrl_provider.py`): every document the provider obtains, from cache or
network, is merged into the store once per UTC day per CIK (measured cost 0.05 s for a
median document, 0.15 s for the largest; the day gate exists because the live runner
ticks every 1,800 s over ~165 CIKs). `get_company_facts` **returns the document
verbatim, exactly as before** — the dated views live on their own opt-in methods.

## 4. A second defect found while running it

The first ingest, run from a worktree, found **zero documents**:
`EdgarXbrlProvider.DEFAULT_CACHE_DIR` resolved to the worktree's own empty
`data/edgar_companyfacts`. A worktree therefore refetched all ~165 documents fresh
from SEC and ran the same code against **different fundamentals than main** — the
identical defect the price store had on 2026-09-09, one level over. Worse, some
worktrees had been hand-symlinked to main's cache and some had not, so whether a run
was reproducible depended on an invisible per-worktree accident. Fixed by routing
`DEFAULT_CACHE_DIR` to `MAIN_CHECKOUT_BACKEND_DIR`. In the main checkout the path is
byte-identical to what it was, so no live tick reads anything different.

## 5. The ingest

```
163 CIKs, 4,213,712 facts, 47.5 MB on disk
ticker->CIK map: 10,407 tickers, snapshot 2026-09-09 (UTC)
value revisions held back: 0
```

Ingested at 2026-09-09 18:54 UTC (2026-09-10 01:54 Bangkok, which is where this
memo's folder name comes from). Idempotent, proven by running it twice: the second run
wrote 0 facts and re-dated nothing (4,213,712 already present). Manifests are committed next to this memo; the
store's own bytes are gitignored, like the price store's.

**Independent verification** (a separate script, comparing the two paths rather than
trusting the ingest's report): the store's served documents were run through
`extract_line_items` alongside the raw cache files for all 163 documents and 30,590
line-item observations — **0 mismatches** in value, filed date or resolved tag. The
dated read was checked to actually hide the future (CIK 1800: 19 asset periods today,
7 as of 2015-01-01, newest filed date in that view 2014-02-21).

## 6. What this does NOT cover

Stated so it is not mistaken for done. All three are the same defect class:

1. **pead_ear's earnings dates** come from SEC's *submissions* endpoint, fetched live
   on every run with no cache at all. Not reproducible by construction, and not served
   from here.
2. **The dividend calendar's share counts** come from `sec_shares_outstanding_provider`'s
   own mutable cache (`data/sec_shares_outstanding/`, 37 files).
3. **The SIC histories** (`filing_sic/`, `submissions_sic/`) are keyed on immutable
   accessions and a current-day fallback respectively, so they are less exposed — but
   the fallback is a live read.

## 7. Left for the owner (CLAUDE.md rule 6)

**No family reads the dated methods yet, deliberately.** Switching one would change
its numbers — measured at 3 observations of 15,851 at end-2018 and 0 of 26,951 at
end-2024 — and quality_cbop is a live registration. The recommendation is to switch
the research path first and leave the live path alone until a formation boundary,
but that is a decision, not a default, and it is not taken here.

**Honest limitation.** `first_seen` on this first ingest is **2026-09-09** — the UTC
date, which is what the store's clock runs on; the local Bangkok date was already the
10th — for every fact, including ones SEC published in 1994. It records when the store
first saw them, not when they became public. A `knowledge_cutoff` query for any
earlier date correctly returns nothing: **the store's knowledge begins there.** It cannot recover
what the 09-04 cache said. It exists so that the next time this question is asked,
it has an answer.
