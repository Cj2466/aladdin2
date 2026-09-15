# Audit part 2 — the data and the tool A2 will actually run on (2026-09-15)

Part 1 (`NUMBER_AUDIT_2026-09-15.md`) audited the numbers. Owner then said: check everything
as correct as possible before starting. This part audits what A2 consumes — the whole-market
price panel — and what A2 uses to do its job — the EDGE spread estimator. Scripts committed
beside this file; all four were written for this audit and share no helper with the code under test.

---

## PART A — the whole-market price panel

Full scan of all 14,451 files, every row.

### Clean (no defect found)

| check | result |
|---|---|
| symbol files | **14,451** — matches the reported count |
| total data rows | **20,345,521** — matches exactly |
| date range | 2016-01-04 → 2026-09-11 (10.69y; the 10.683y in `PROJECT_WORKLIST.md` reconciles) |
| duplicate dates within a symbol | **0** |
| rows out of date order | **0** |
| rows dated after today | **0** |
| non-positive open/high/low/close | **0** |
| high < low | **0** |
| open or close outside [low, high] | **0** |
| negative volume | **0** |
| empty or unreadable files | **0** |

This is a cleaner panel than the project has had before. The three defects below are about
what the panel *claims* and what it *contains*, not about corrupted bars.

### D1 — `_coverage.json` is a REQUEST log, not a coverage ledger — SERIOUS

Every entry claims `[['2016-01-04', '2026-09-11']]`, including for names that stopped trading
years ago.

| | count | share |
|---|---|---|
| claim matches the delivered data exactly | 4,162 | 28.8% |
| claimed START differs from the data | 9,403 | 65.1% |
| **claimed END runs past the last real bar** | **1,821** | **12.6%** |

Worked example: `AABA` (Altaba) claims coverage through 2026-09-11; its last real bar is
**2019-10-02**, 577 rows. Also ABDC (2020-01-31), ACBI (2022-02-28), ACAMU (2021-01-21).

This is the same defect class as the 2026-09-10 live-panel incident (a ledger asserting coverage
it did not have). Consequence for A2: any consumer that asks `_coverage.json` "is this name alive
and how recent is it?" gets a wrong answer for 1,821 symbols, and would compute a "current spread"
for stocks that have not traded in years. **A2 must read liveness from the last row of each file,
never from `_coverage.json`.**

### D2 — roughly 1,966 likely UNFLAGGED splits

Split flags, where present, are correct and usable: over the 2,531 big single-day moves that
carry a flag, `observed_ratio × split_flag` reconciles to 1 with median error **0.049**, and
**92% land within 25%**. The flag semantics are sound.

But 8,368 big moves (>45% in a day) carry **no** flag, and **1,966 of those have a round ratio**
(2×, 3×, 5×, 10×, 20×, 50×, or their reciprocals) — the signature of a reverse split that was
never flagged. The worst names are known serial reverse-splitters (XTIA, SMX, HIND, PSHG, SUNE,
TOPS, ENVB).

Why this matters more for A2 than for a return backtest: EDGE reads **high/low/close**. An
unflagged split turns one day's range into a fake several-hundred-percent bar, which the estimator
reads as an enormous spread — concentrated in exactly the illiquid micro-caps where the spread
number actually decides whether a strategy is tradable.

### D3 — the panel is not all common stock

By ticker pattern, about **1,264 of 14,451 symbols (8.7%)** are not ordinary shares:

| kind | count |
|---|---|
| units (5-letter -U) | 462 |
| warrants (5-letter -W, plus -WW) | 375 |
| rights (5-letter -R) | 133 |
| preferred-ish (5-letter -P/-Q) | 65 |
| other 5-letter | 229 |

The extreme-move list is dominated by warrants (OXBRW 70 jumps, EDBLW 59, HUBCZ 56 …), which is
not a data error — warrants genuinely move like that. A2 must classify and exclude them, or report
them separately; treating the panel as "the US stock market" overstates both spread and volatility.
(The ticker-pattern rule is a heuristic and has false positives — EWW, GWW and POWW are ordinary
listings caught by the `-WW` rule — so the classification must be checked against an instrument
type field, not this pattern, before it gates anything.)

---

## PART B — the EDGE spread estimator

Validated against **synthetic data with a known true spread**, per CLAUDE.md's rule that a
published formula is never trusted on real data before it reproduces a known answer. Model is
the one EDGE is derived under (Ardia, Guidotti & Kroencke, JFE 2024): random-walk efficient
price, trades at ±S/2, daily OHLC taken from the simulated trade prices. 12 replications of
500 days × 390 trades per point.

### The estimator is sound where it matters

| true spread | `sign=False` (package default) | `sign=True` |
|---|---|---|
| 50 bp | 50.88 (+0.88) | 51.00 (+1.00) |
| 100 bp | 99.34 (−0.66) | 99.40 (−0.60) |
| 200 bp | 200.39 (+0.39) | 202.96 (+2.96) |
| 500 bp | 503.33 (+3.33) | 502.24 (+2.24) |

At 25 bp and above, both modes are within ~3 bp of truth. **The formula works.**

### D4 — below ~25 bp the default mode MANUFACTURES spread out of volatility

Feeding the estimator data with a **true spread of exactly zero**:

| daily volatility | `sign=False` returns | `sign=True` returns |
|---|---|---|
| 50 bp | **+2.65 bp** | −0.16 bp |
| 150 bp | **+7.27 bp** | −2.28 bp |
| 400 bp | **+20.43 bp** | −0.89 bp |

`sign=False` is one-sided — it cannot return a negative number — so estimation noise is folded
into a positive "spread" that is not there. `sign=True` is centred on zero, though still noisy
(sd 2–24 bp), which is why it must be paired with truncation and a floor rather than used raw.

**The noise floor scales with the stock's own volatility** (≈5% of daily vol here), confirming
the 2026-09-12 audit's rule that the usable threshold is per-stock, not market-wide.

### D5 — two of the three entry points still use the uncalibrated mode

| function | line | mode |
|---|---|---|
| `estimate_effective_spread` | 129 | `edge_rolling(frame, window=…)` → **sign=False** |
| `build_edge_half_spread_frame` | 201 | `edge_rolling(ohlc, window=…)` → **sign=False** |
| `build_calibrated_half_spread_frame` | 413 | `sign=CALIBRATED_SIGN_MODE` (**True**) + truncate + tick floor |

`ipo_lockup_expiration.py:1866` still consumes the uncalibrated builder. The project has already
MEASURED what the difference is worth, on lazy_prices (`live_registration_dependencies.json:293`):
switching builders moved best-spec net Sharpe **0.5946 → 0.7456** and turnover cost drag
**0.0827 → 0.0084**. That is the uncalibrated path overstating cost by roughly an order of
magnitude for that family — the same direction and rough size my synthetic test predicts.

**A2 must call `build_calibrated_half_spread_frame` and nothing else.**

---

## PART C — the other quoted counts

Re-derived from the committed CSVs:

| claim | verified |
|---|---|
| 1,817 dead names | **1,817** ✓ |
| 480 acquisitions | **480** ✓ (271 cash + 175 stock + 34 stock-and-cash) |
| 184,048 announcement events | **184,048** ✓ |
| 4,799 tickers with announcements | **4,799** ✓ |

### D6 — the delisting outcome is UNKNOWN for 68% of dead names

`outcome` breakdown: **no_action_found 1,235**, cash_merger 271, stock_merger 175,
other_action 102, stock_and_cash_merger 34.

The median implied final return of **+0.03%** was measured on the 480 names with a matched
corporate action, not on all 1,817. For the other 1,235 the terminal value is unknown, so the
survivorship correction this panel provides is **partial, not complete**. That must be stated
wherever the panel is described as "including delisted names".

---

## The finding that matters most

D4 and D5 interact with Part 1's P1 in a way worth stating plainly.

Had A2 been run on the default estimator, it would have "measured" roughly **8 bp** for a
mega-cap whose true spread is 1–2 bp. We would then have concluded that the unsourced 5 bp
default was too LOW, raised it, and watched the book's Sharpe fall from 0.599 toward the 0.412
that fails the pass line.

**We would have reached a confident, pessimistic, wrong answer, and had a measurement to back it
up.** That is the failure mode this project's rules exist to prevent, and it was two days away.

## Rules A2 must now follow (was four, now nine)

1. `sign=True` truncation — via `build_calibrated_half_spread_frame` only (D5).
2. Per-stock noise floor from the stock's own volatility, never a market-wide threshold (D4).
3. Sourced fallback by liquidity bucket, never a market-wide constant (part 1, P1).
4. Report the share measured vs assumed.
5. **Read liveness from the last row of each file, never from `_coverage.json`** (D1).
6. **Detect and exclude unflagged split days before estimating** — a round-ratio jump with no
   flag must break the window, not enter it (D2).
7. **Classify and separate units / warrants / rights / preferreds**, against an instrument-type
   field rather than the ticker-pattern heuristic used here (D3).
8. Report both the conservative and the permissive cost view; the conservative one decides.
9. Report each strategy's break-even cost, so a future correction to (3) can be applied without
   re-running anything.
