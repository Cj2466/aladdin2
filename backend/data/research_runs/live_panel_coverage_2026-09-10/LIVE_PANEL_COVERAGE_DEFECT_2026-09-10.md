# Live panel coverage defect (found 2026-09-10 while re-verifying the live registrations)

## 1. What was found

While replaying the three equity live registrations (quality_cbop, short_interest_ratio,
lazy_prices_jaccard_full) from a fresh state to check the price-store repair, the replayed
2026-09-08 day results did not match the stored ones — and the STORED ones were the wrong
side:

| registration | stored 2026-09-08 gross | what the row held at tick time |
|---|---|---|
| quality_cbop / cbop_ls_h63 | **0.0 exactly** | none of its 14 names had a 09-08 close |
| lazy_prices_jaccard_full / lazy_jaccard_full_h126_ivol | **0.0 exactly** | none of its 198 names had one |
| short_interest_ratio / si_ratio_hedged_h21 | −0.0087 | index leg realized, stock leg missing |

Cause, in the shared price store: **712 tickers carried coverage through 2026-09-09 while
their newest stored row was 2026-09-04** (UNH, VRSN, AAPL, ... — most of the S&P 500), and
the vendor had 09-08 and 09-09 bars for every one of them (checked live, store bypassed).
The ledger records "asked about [start, end)" for every ticker in a fetch batch, including
the ones that resolved nothing, because a dead symbol must not be re-asked forever. A
batch download that came back empty or short for live symbols (an outage or rate limit at
the 2026-09-09 00:09 UTC tick) was therefore frozen as answered, every later request fell
inside the recorded window, and the missing bars were never fetched again. The panel's
newest row existed only because a handful of names (SPY, the tickers repaired earlier that
evening) had a 09-08 bar; the harness treats a name with no return as cash, so a book whose
every name is missing books exactly 0.0.

## 2. Fixes (this branch)

1. `price_store.bounded_coverage_end`: a fetch records coverage no further than the newest
   row it or the store knows for a LIVE ticker, plus the rolling tolerance; a ticker with no
   row at all, or nothing newer than STALE_TICKER_CALENDAR_DAYS (30) before the requested
   end, keeps the old rule (dead symbols are still not re-asked). Applied in the provider's
   store-serving path, grouped by resulting end.
2. `PriceStore.rebound_coverage` + `price_store_basis_audit.py --rebound-coverage`: the
   ledger repair. Run on the shared store 2026-09-10: 623 windows shrunk from 2026-09-09 to
   2026-09-08 (price_store_basis_audit_2026-09-10.json).
3. Backfill: one fetch of the 768-ticker S&P 500 pool wrote 1,216 rows (09-08 and 09-09 for
   ~608 names); 613 names priced on 09-08, the same count as on 09-04; no basis mismatch.
4. Runner: `live_panel_newest_row_incomplete` — a tick whose newest close row prices fewer
   than half the names the previous row priced is skipped with a warning; the row stays
   unprocessed and is caught up by rows_to_process once complete.
5. Tests: bounded end cases; ledger repair; short vendor response is re-asked / dead ticker is
   not (provider, end to end); runner skips the mostly-empty row.

## 3. What this leaves for the owner (CLAUDE.md rule 6 — not executed)

The three registrations' stored 2026-09-08 day results are fabricated (section 1). Their
formation weights of 2026-09-04 reproduce exactly from the repaired store (cbop 7/7 and 7/7
identical, short_interest 22/22 and 500/500; lazy_prices' 99 short weights identical, its 99
long weights differ by at most 5e-3 — see section 4). Section 4 gives what 09-08 should have
been. Options: (a) reset the three carry states and day results to the 2026-09-04 formation
so the runner re-realizes 09-08 onward from the complete panel; (b) re-register. Either is a
change to a live record and needs the owner's sign-off.

## 4. Replay on the repaired, backfilled store (2026-09-10, read-only, from a fresh state)

Formation on the 2026-09-04 row, then the following rows, exactly as the first tick did.

| registration | 2026-09-04 formation vs stored | 2026-09-08 gross: stored → true | 2026-09-08 net: stored → true | ~~2026-09-09 net~~ (INVALID, see section 5) |
|---|---|---|---|---|
| quality_cbop / cbop_ls_h63 | identical (7+7 weights, n_eligible 136) | 0.0 → **−0.0420** | −0.0010 → −0.0430 | ~~+0.0024~~ |
| short_interest_ratio / si_ratio_hedged_h21 | identical (22+500 weights) | −0.0087 → **+0.0010** | −0.0098 → −0.0001 | ~~+0.0061~~ |
| lazy_prices_jaccard_full / lazy_jaccard_full_h126_ivol | 99 short identical; 99 long differ ≤ 5e-3 (see below) | 0.0 → **−0.0030** | −0.0006 → −0.0036 | ~~−0.0006~~ |

The 2026-09-09 column was computed on rows that turned out to be the 9th's
STILL-FORMING bar (section 5) and is struck out; the 09-04 formation and the
09-08 day are unaffected (both bars were final when fetched).

lazy_prices' long-leg weights: a replay on a copy of the store carrying the quarantined
(defective) APH/MNST/RUSHA files reproduces the STORED weights exactly, and the repaired
store moves them by ≤ 5e-3 — the live 2026-09-04 formation's ivol weighting had read APH's
fabricated +96% day. cbop and short_interest do not weight by trailing volatility and are
unaffected. The stored 2026-09-08 results are wrong for all three (section 1); the true
values above are what a complete panel gives on the repaired store.

Recommendation (owner's call, rule 6): reset all three carry states / day results /
formations to just before the 2026-09-08 tick — for lazy_prices to before the 2026-09-04
formation, so the weights are re-formed from the repaired store — and let the runner catch
up 09-08 and 09-09 from the complete panel. The crypto registration is unaffected (its
2026-09-07 row was complete).

## 5. Second defect, found 2026-09-10 while preparing the reset: a not-yet-final bar was stored

Checked before touching any live row. The "backfill" of section 2 (one fetch at
2026-09-09 17:14 UTC = 13:14 New York, mid-session) had been issued by the replay
script with `end = date.today()` on the LOCAL calendar (Bangkok, already the 10th), and
the provider's own rolling-window clock was the local date too. The vendor answered
with the 9th's bar as it stood at that minute, and first-write-wins froze it:

| | |
|---|---|
| tickers with a 2026-09-09 row | 611 (all written 17:14–17:15 UTC) |
| AAPL 2026-09-09 stored | close 312.77, volume 22.59M (a full day is ~35M) |
| UNH 2026-09-09 stored | low 378.08, close 394.92, volume 4.69M |
| ledger | 768 tickers recorded as covered through 2026-09-10 |

Had a tick run on the 10th it would have realized 09-09 on those intraday snapshots
and never revisited them. Fix (branch live-reset-2026-09-10, `934e716`):

1. `price_store` section 4c: `merge_ticker` refuses any row dated on or after the
   current UTC date (a bar dated D is final only after D's New York close, so UTC day
   D+1 is the earliest it may be stored); counted on `PriceStoreReport.rows_unfinal_dropped`.
   The provider's rolling-window clock is `utc_today()`. Tests: store 4, provider 1
   end-to-end (today's forming bar is not stored, is not covered, and is re-asked on
   the next UTC day); the two 2026-09-10 provider tests now pin `utc_today` instead of
   the datetime class; the rolling-window test's rows end yesterday.
2. Repair, run on the shared store at 18:08 UTC: `price_store_basis_audit.py
   --drop-unfinal` removed the 611 rows (kept verbatim as evidence in
   `price_store_basis_audit_2026-09-09T1808Z.json`) and rebounded the ledger to
   2026-09-09. Verified independently afterwards: 0 tickers with a row ≥ 2026-09-09;
   newest row 2026-09-08 for 1,441 tickers; no ledger window past 2026-09-09.
   The 9th is fetched again, final, by the first request on UTC 2026-09-10.
3. `--confirm-recent N`: a whole-store check of the last N business days against a
   fresh vendor batch, to be run after the New York close (not yet run at the time of
   writing; its result is appended below when it exists).

The full-history basis audit that ran with the repair lists 42 tickers (the
2026-09-09 audit had used `--since 2025-06-01` and listed 4; the same 4 are the only
ones with an event after that date). All 42 were sent to `--confirm` (read-only,
vendor row-by-row, store bypassed): **42/42 consistent with the vendor, 0 rows off on
every one** (ratio 1.0 on 230–8,232 overlapping rows each) — the audit's ex-date and
neighbourhood heuristics flag reverse splits and genuine large moves, not a basis
join. Record: the `--confirm` JSON written alongside this memo's repair record.

## 6. Where the 2026-09-09 00:09 UTC tick came from, and what "live" means here

Established from this session's own transcript: a `uvicorn app.main:app` was started
on the MAIN checkout at 2026-09-08 15:25:56 UTC (to register the three equity
registrations on startup). Its runner ticked every 1,800 s; the 00:09 UTC tick was
simply the first tick after UTC midnight, when `today` rolled to the 9th and the panel
gained the (incomplete) 09-08 row. That process is no longer running. Consequences,
stated plainly:

* The registrations in the local SQLite DB advance ONLY while a local server is
  running. Nothing on this machine schedules one (no crontab, no LaunchAgent for it).
* Production (Render + Neon Postgres) holds its OWN registration rows, created by the
  same startup step on deploy, and ticks on its own ephemeral price store. Whether its
  2026-09-08 day was fabricated the same way cannot be checked from here (the status
  endpoints are user-scoped; there is no Render shell on the free plan). The owner can
  read it off the dashboard's cross-sectional panel: a 09-08 gross of exactly 0.0 for
  cbop or lazy_prices is the signature. The ledger bound (`7002a41`) and the UTC-clock
  guard (this branch) reach production on the next deploy.

## 7. Reset status (owner approved 2026-09-10, "ตามนี้")

* Pre-reset copy of rows 2/4/5 committed verbatim:
  `live_registrations_pre_reset_2026-09-10.json` (sha256 835823a0…52ccb7f).
* The reset (fresh carry state, empty day/formation lists, `last_processed_date =
  2026-09-03` so the runner's own catch-up re-forms on the 09-04 row and realizes
  09-08 onward from the complete panel) was NOT executed by the assistant: the Claude
  Code permission classifier refused the DB write twice, once from each checkout. The
  scripts are committed next to this memo: `reset_live_registrations.py` (refuses to
  run unless the rows still match the backup) and `tick_live_registrations.py` (ticks
  registrations 2/4/5 only, through the runner's own `_process_family`, and proves no
  store file changed during the tick). Both are run from the MAIN checkout. Results to
  be recorded here when they exist.
