# A seven-day asset in a five-day ledger (2026-09-10)

Found while checking live-panel reproducibility
(`reproducibility_check_2026-09-10/`). The check itself passed 4 of 4; this is what
reading its output showed, and it is the more useful of the two results.

## 1. The defect

| | |
|---|---|
| crypto tickers in the shared store holding no row after 2026-09-07 | **68** of 73 |
| what the coverage ledger recorded for all 68 | covered through **2026-09-09** |
| vendor's BTC-USD 2026-09-08 close, fetched read-only to confirm | **78438.578125**, final |
| consequence | `is_covered` → True, so that bar is **never re-asked** |

`cross_sectional_crypto` holds a **live forward registration**. It built its 2026-09-09
panel with data ending 2026-09-07 — one whole trading day stale in an asset class that
has no non-trading days.

## 2. Cause, reproduced exactly

```python
bounded_coverage_end(date(2026,9,9), newest_row=date(2026,9,7), as_of=date(2026,9,9))
# -> 2026-09-09 : newest_row + ROLLING_WINDOW_TOLERANCE_DAYS(4) = 09-11 runs past the
#                 requested end, so the bound shrinks nothing at all
```

`ROLLING_WINDOW_TOLERANCE_DAYS = 4` exists for weekends and holidays — that is the whole
of its own comment in `price_store.py`. On an asset that trades every calendar day the
slack is unearned, and it silently defeats the 2026-09-10 ledger fix whose entire purpose
was that "a short or empty vendor response is re-asked on the next call instead of being
frozen as asked, none".

The same module's own docstring had already stated the premise, three weeks earlier:

> "Crypto trades 24 hours a day, 7 days a week, with no exchange holidays. That is not a
> footnote; it is the single largest source of silently wrong numbers in reusing this
> project's equity machinery on this data."

The rule was written down and the ledger still assumed five days. That is the lesson worth
keeping: a documented premise is not an enforced one.

## 3. The fix

`CONTINUOUS_CALENDAR_TOLERANCE_DAYS = 1`, chosen per ticker by `coverage_tolerance_days()`.

**One day and not zero**, for a stated reason: `requested_end` is already capped at
`as_of`, and section 4c guarantees no row is ever stored for `as_of` itself, so a symbol
whose newest row is yesterday must still count as covered through today — otherwise every
call refetches forever. One day does exactly that and nothing more.

`bounded_coverage_end` takes the tolerance as a parameter defaulting to the old value, so
**the equity path is unchanged**; the two call sites that know a ticker pass the per-ticker
value: `yfinance_provider`'s write path and `PriceStore.rebound_coverage`'s repair path.

**Identification.** `trades_every_calendar_day()` keys on yfinance's own `<COIN>-USD`
spot-pair naming, which does not collide with its FX (`=X`), futures (`=F`) or index (`^`)
suffixes. Verified against this project's real data: exactly **73 of the 1,940** tickers in
the shared store carry the suffix, all 73 are `CRYPTO_UNIVERSE` members, and all 73
`CRYPTO_UNIVERSE` members carry it — correspondence in **both** directions. `price_store`
deliberately does not import the research layer, so a test ties the two together instead.

## 4. The repair, and what it actually did

`repair_crypto_coverage.py`, run 2026-09-09 21:18 UTC. Artifact:
`crypto_coverage_repair_2026-09-09T2118Z.json`.

| | |
|---|---|
| ledger windows shrunk | **68**, every one of them crypto (no equity window moved) |
| tickers whose newest stored row advanced 09-07 → 09-08 | **68** |
| crypto tickers now current to 2026-09-08 | 68 of 73 |
| still older | 5 |

The 5 are `FTM-USD` (2025-01-13), `RNDR-USD` (2024-07-21), `MATIC-USD` (2025-03-24),
`GALA-USD` (2026-07-18), `LUNA1-USD` (2022-10-09) — **exactly** the five feed-ends the
module pre-declares in its own exclusion list, with the same dates. Independent
corroboration that the repair reached everything alive and nothing that is not.

## 5. A side effect of the repair, measured rather than glossed

The first run asked the vendor from 2013-01-01. The store is append-only, so it also took
in whatever earlier history Yahoo happens to hold. Measured across the whole universe
afterwards: **exactly 2 of the 73 coins gained pre-2017-11-01 rows — BTC-USD and LTC-USD,
both now beginning 2014-09-17, +1,141 rows each.** This is real vendor data and no
stored row changed — but widening a live family's inputs as a by-product of a repair is
not something to leave undisclosed.

**Measured consequence: none.** `CRYPTO_PRICE_HISTORY_START = date(2017, 11, 1)` is a fixed
module constant, and the rebuilt panel still begins 2017-11-01 with 3,234 rows and 73
columns. The extra history cannot enter the panel.

The script now pins its request to that same constant, so this is a guarantee rather than
a fact about today's module.

One further consequence of that first run, recorded because it is visible in the ledger:
all 73 crypto windows now begin **2013-01-01** rather than 2017-11-01. That is the
ledger's ordinary "asked, and there is none" semantics — the vendor genuinely was asked
from 2013 and genuinely held nothing earlier for 71 of them — and it is why the same
question will not be re-asked. Correct, but it is a wider claim than the store had
before, so it is stated here rather than left to be discovered.

## 6. Panel effect

| | before repair | after repair |
|---|---|---|
| `last_row_date` | 2026-09-07 | **2026-09-08** |
| `n_tickers` | 73 | 73 |
| `data.close` digest | `b6222bea529cfc69…` | `4fe2d01dcb9d62ef…` |
| `data.leg_weight_basis` digest | `2b5b4ea15d240a94…` | `097eb71fbfc737e9…` |

The digests change because the data changed — that is the repair working, not a
reproducibility failure. Both digests are recorded on both sides so the change is auditable.

## 7. Scope, stated so it is not assumed wider

* `price_cache.py`'s separate `PriceBar` layer carries the same four-day tolerance and
  serves the risk/stress/optimizer routers, **not** the research live path. Left alone
  here rather than changed without measurement. (Noted alongside: its
  `is_rolling_window` test uses `date.today()`, the local date, where the market-data
  convention established 2026-09-10 is UTC. Same layer, same decision — logged, not
  touched.)
* **Nothing here reads or writes a database row of any kind** (CLAUDE.md rule 6). No
  registration's status, formation or realized result is changed. The crypto
  registration's already-recorded days are left exactly as they stand.
* What this does **not** do: it does not re-run any tick. The registration will pick up
  2026-09-08 through its own normal path.
