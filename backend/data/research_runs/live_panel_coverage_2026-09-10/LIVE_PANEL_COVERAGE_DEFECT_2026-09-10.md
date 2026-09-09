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

## 4. Replay on the repaired, backfilled store
(filled in below once the replay finishes)
