# Whole-store verification after the 2026-09-09/10 price-store repairs

Run after the New York close (the first run started 20:15 UTC, i.e. after the 20:00 UTC
close, deliberately — fetching earlier is what caused the not-yet-final-bar defect this
verification exists to check for). Closes section 5 item 3 of
`LIVE_PANEL_COVERAGE_DEFECT_2026-09-10.md`.

## 1. A false positive in this project's own audit script, found and fixed first

The first run reported that **all 1,592 tickers were missing 2026-09-05, 09-06 and
09-07**. That is Saturday, Sunday and US Labor Day. The number was implausible on its
face, which is the only reason it was chased.

Cause, measured rather than guessed: yfinance aligns a multi-ticker batch onto the
**union** of its members' trading calendars, and this store's universe contains crypto
(BCH-USD, LINK-USD, ...) which trades every day. An equity in the same batch therefore
comes back with NaN-close rows on weekends and market holidays.

| fetch | rows returned for AAPL, 2026-09-02 .. 09-09 |
|---|---|
| AAPL alone | 4 (09-02, 09-03, 09-04, 09-08) |
| AAPL batched with BTC-USD | 7 — the extra three are Sat 09-05, Sun 09-06 and Labor Day 09-07, each with a NaN close |

`confirm_recent` compared the vendor's padded index against the store's real rows and
called the padding a gap. **The defect was in the audit script, not in the store.**
Confirmed independently before changing anything: the store holds **0 NaN-close rows
across 6,852,849 rows in 1,592 tickers**, and weekend rows only for crypto tickers,
which is correct.

Fixed by dropping NaN-close rows from the vendor frame before any comparison. The
comment at that line records the measurement so the next reader does not re-derive it.

This is worth recording for its own sake: nothing crashed, no test went red, and the
script printed a confident wrong number. The only signal was that the number did not
match what a person knows about calendars.

## 2. The corrected result

```
window 2026-09-02 .. 2026-09-09, 1,592 tickers
rows compared            6,338
rows differing from the vendor    0
tickers the vendor returned nothing for   0
```

Every stored close in the last five business days agrees with a fresh vendor
reconstruction, to within 0.1%. Record: `price_store_basis_audit_2026-09-09T2018Z.json`
(the earlier `...T2015Z.json` is the pre-fix run, kept as the evidence for section 1).

## 3. The 122 genuine missing days, and why they are benign

After the fix, 122 tickers lack at least one day the vendor really has:

| group | count | what they are |
|---|---|---|
| crypto (`*-USD`) | 68 | missing 2026-09-08 only |
| ETFs, FX pairs, a few equities | 54 | mostly missing 2026-09-08; a handful missing more |

None is an S&P 500 name. The 2026-09-10 backfill covered the 768-ticker S&P pool, and
these instruments belong to other families' universes (crypto, bonds, commodities, fx),
so they were simply not in it. They self-heal: their coverage ledger does not claim the
missing day, so the next request that reaches it refetches. Examples:

| ticker | newest stored row | coverage ends | missing |
|---|---|---|---|
| AAVE-USD | 2026-09-07 | 2026-09-09 | 09-08 (inside the 4-day tolerance; refetched tomorrow) |
| BWX | 2026-09-04 | 2026-09-05 | 09-08 (not covered; refetched on the next request) |
| DX-Y.NYB | 2026-09-01 | 2026-09-02 | 09-02 .. 09-08 (not covered; refetched) |

## 4. The check that actually matters: is the ledger honest?

The 2026-09-10 defect was a coverage ledger claiming to have answered a question it had
not. The direct test of whether that is gone is whether any window now runs past what
`bounded_coverage_end` permits given the ticker's newest stored row.

```
tickers checked                       1,592
coverage windows exceeding the bound      0
```

Zero, across the whole store. Every ticker's newest row is 2026-09-08 with coverage to
2026-09-09, which is the bound working as designed: the store asked about the 9th, the
9th's bar was not final, and nothing was invented.

## 5. What this does not cover

The five business days checked are the window the not-yet-final-bar defect could have
touched. It is not a full-history re-audit; the share-basis audit
(`price_store_basis_audit.py` with no arguments) remains the tool for that, and its last
full run on 2026-09-09 confirmed all 42 flagged tickers against the vendor row by row.
