# Does the point-in-time work actually reproduce? (2026-09-10)

Three nights of work — the price store's share-basis guard and coverage ledger
(`c298dd3`, `7002a41`), the not-yet-final-bar rule (`1f8307f`), the EDGAR fact store
(`ef6584a`), the submissions store (`dfeb161`) — were each justified by a measured
defect. None had ever been checked against the property they exist to produce: **the
same request, made twice, returns the same panel.**

Run: `check_live_panel_reproducibility.py`, 2026-09-09 20:30 UTC, as-of 2026-09-09 (UTC).
Artifact: `live_panel_reproducibility_2026-09-09T2030Z.json`.

## 1. Result: 4 of 4 identical

Each live family's panel was built twice in one process and every frame it carries was
compared by SHA-256 over a deterministically serialised copy (sorted both axes, `%.17g`).

| family | last row | tickers | frames hashed | rebuild |
|---|---|---|---|---|
| `quality_cbop` | 2026-09-08 | 168 | close, fundamental_signal | IDENTICAL |
| `short_interest_ratio` | 2026-09-08 | 597 | close, fundamental_signal | IDENTICAL |
| `lazy_prices_jaccard_full` | 2026-09-08 | 625 | close, fundamental_signal, half_spread, leg_weight_basis | IDENTICAL |
| `cross_sectional_crypto` | 2026-09-07 | 73 | close, leg_weight_basis | IDENTICAL |

No family failed to build; no frame differed.

## 2. What this does NOT establish

Stated before the result, and unchanged by it: **two builds in ONE process cannot
separate a store hit from an in-process cache hit.** This is a necessary condition for
reproducibility, not a sufficient one. The sufficient check compares across processes and
across days; that is what the stores' `first_seen` column exists for and it needs a
second day to run.

And the sharper limit, which this run demonstrated by accident — see §3:

> **A frozen wrong answer is perfectly reproducible.** Identical digests prove the
> inputs are immutable. They say nothing about whether the inputs are complete.

## 3. A real defect the check surfaced, which the check itself would never have failed on

`cross_sectional_crypto`'s panel ends 2026-09-08 for the equity families but **2026-09-07
for crypto**, in an asset class that trades every calendar day. Traced to the ledger:

| | |
|---|---|
| crypto tickers whose newest stored row is 2026-09-07 | **68** (of 73 with rows; the other 5 are long-dead coins) |
| what the coverage ledger records for all 68 | `[..., "2026-09-09"]` |
| vendor's BTC-USD bars, fetched read-only to confirm | 09-08 **78438.578125** (final), 09-09 78243.867188 (forming) |

The 09-08 bar exists, is final, and is missing from the store — and because the ledger
records the window as already covered, `is_covered` returns True and **it will never be
re-asked.**

**Mechanism, reproduced exactly:**

```
bounded_coverage_end(date(2026,9,9), newest_row=date(2026,9,7), as_of=date(2026,9,9))
  -> 2026-09-09          # newest_row + ROLLING_WINDOW_TOLERANCE_DAYS(4) = 09-11, so the
                         # requested end is NOT shrunk at all
```

`ROLLING_WINDOW_TOLERANCE_DAYS = 4` is calibrated for a five-day calendar — the constant's
own comment in `price_store.py` gives weekends and holidays as its whole reason. Applied to
a seven-day asset it is pure slack: a genuine 1-to-4-day hole in crypto data is recorded as
covered and frozen.

This is the same defect class as the 2026-09-10 ledger fix, which that fix's own tolerance
partially defeats. Recorded here; **fixed separately**, not inside a verification artifact.

## 4. Provenance

Panels built through each family's own `adapter.build_live_panel(today)`. Read-only with
respect to the database: no registration row was read for its state and nothing was
written. The vendor was queried once, read-only, to confirm the 09-08 crypto bar exists.
