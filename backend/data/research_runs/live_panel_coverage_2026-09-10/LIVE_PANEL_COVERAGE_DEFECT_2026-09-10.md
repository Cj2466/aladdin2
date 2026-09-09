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

| registration | 2026-09-04 formation vs stored | 2026-09-08 gross: stored → true | 2026-09-08 net: stored → true | 2026-09-09 net (never ticked) |
|---|---|---|---|---|
| quality_cbop / cbop_ls_h63 | identical (7+7 weights, n_eligible 136) | 0.0 → **−0.0420** | −0.0010 → −0.0430 | +0.0024 |
| short_interest_ratio / si_ratio_hedged_h21 | identical (22+500 weights) | −0.0087 → **+0.0010** | −0.0098 → −0.0001 | +0.0061 |
| lazy_prices_jaccard_full / lazy_jaccard_full_h126_ivol | 99 short identical; 99 long differ ≤ 5e-3 (see below) | 0.0 → **−0.0030** | −0.0006 → −0.0036 | −0.0006 |

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
