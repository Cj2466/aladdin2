# M1 — Thai foreign-board (`-F.BK`) premium: tradable spread or stale print?

Descriptive measurement only. No strategy, no return/Sharpe of any rule, no DB row.
Script: `m1_thai_foreign_board.py`. Raw output: `m1_output.json` (full per-symbol
detail, per-year breakdown) and `m1_output.txt` (human table). All numbers below
are read from those two committed files, produced by an independent re-fetch of
yfinance today (2026-09-12), not by reusing any cached review number.

**Symbol source note.** The task brief offered a 15-symbol fallback list, but that
list does not match what the review (`REVIEW_FOR_BRIEF.md` §2.5) actually measured
— it repeats BBL and swaps in TCAP/KKP/INTUCH for names the review's own table
names. The review's probe script was not present in this worktree to re-run
verbatim, so this script uses the review's own 15 named symbols instead, since
those are the ones with an existing citable number to cross-check against: BBL,
KBANK, SCC, BAY, SCCC, BANPU, ADVANC, PTT, SCB, CPALL, AOT, TU, KTB, TISCO, EGCO.
BBL's re-measured mean premium (6.775%) matches the review's cited figure exactly,
and KBANK's (3.417% vs 3.417%) does too — the re-fetch reproduces the prior claim.

## Table

| symbol | days in common | window | 2-sided frac (all) | 2-sided frac (last 3y) | mean premium (all days) | mean premium (2-sided days) | median depth THB (2-sided) | median depth THB (last 3y) |
|---|---|---|---|---|---|---|---|---|
| BBL | 6,616 | 2000-01-04→2026-09-11 | 89.01% | 46.05% | 6.775% | 7.186% | 177,187,000 | 835,000 |
| KBANK | 6,616 | 2000-01-04→2026-09-11 | 92.70% | 57.90% | 3.417% | 3.496% | 195,766,600 | 2,044,700 |
| SCC | 5,754 | 2003-04-24→2026-09-11 | 73.11% | 14.44% | 2.878% | 3.997% | 86,732,800 | 87,500 |
| BAY | 6,616 | 2000-01-04→2026-09-11 | 45.72% | 0.14% | 7.275% | 0.712% | 4,508,000 | 830,000 |
| SCCC | 6,616 | 2000-01-04→2026-09-11 | 8.65% | 0.41% | 16.703% | 56.991% | 4,165,317 | 176,400 |
| BANPU | 2,381 | 2016-10-28→2026-08-11 | 0.59% | 0.42% | 35.228% | -1.503% | 47,250 | 2,560 |
| ADVANC | 4,539 | — | 27.78% | 41.69% | 0.084% | -0.020% | 1,386,000 | 3,622,200 |
| PTT | 4,564 | — | 37.47% | 44.82% | 0.111% | -0.015% | 1,831,825 | 1,555,200 |
| SCB | 1,068 | — | 47.28% | 51.63% | -0.008% | -0.009% | 1,153,600 | 2,159,000 |
| CPALL | 4,605 | — | 26.43% | 43.73% | -2.944% | -0.870% | 1,682,100 | 2,411,500 |
| AOT | 5,524 | — | 12.06% | 21.53% | -2.724% | -0.892% | 830,462 | 669,338 |
| TU | 6,126 | — | 23.07% | 7.77% | 1.846% | 2.226% | 3,708,796 | 187,680 |
| KTB | 4,570 | — | 20.83% | 45.57% | 1.558% | 1.570% | 738,655 | 1,489,050 |
| TISCO | 4,543 | — | 20.49% | 15.94% | 1.019% | 0.407% | 1,013,650 | 1,100,900 |
| EGCO | 6,616 | — | 36.83% | 0.95% | 1.766% | 5.940% | 3,901,650 | 21,600 |

Full per-symbol window dates, per-year two-sided fractions, p10/p90 premium,
p25/p75 depth, and the (d) forward-change table are in `m1_output.json`.

## The three findings that matter

1. **Two-sided liquidity has decayed hard on all three "live" names, and BBL/KBANK
   are now roughly coin-flip-tradable, not routinely tradable.** Year-by-year
   two-sided fraction (from `m1_output.json`):
   - BBL: 2019–2020 100% → 2022 52.3% → 2024 38.3% → 2025 52.1% → 2026 (partial) 41.7%
   - KBANK: 2019–2020 100% → 2023 83.5% → 2024 51.9% → 2025 60.7% → 2026 (partial) 52.0%
   - SCC: 2019 43.9% → 2022 16.6% → 2025 14.5% → 2026 (partial) 12.0%
   Over the full history BBL and KBANK look tradable (89%/93% of all days two-sided).
   Over the last 3 years they are barely above a coin flip (46%/58%), and SCC has
   fallen to essentially illiquid (14.4%). The premium itself is real and persistent
   where it exists (mean ≈ median ≈ the two-sided-day mean, i.e. not driven by
   outliers), but the *opportunity to trade it* is shrinking every year measured.

2. **Depth has collapsed by roughly two orders of magnitude in the same window.**
   Full-history median depth (F-board volume × F-board close, THB, on two-sided
   days) is 177.2M (BBL) and 195.8M (KBANK) — genuinely large. Restricted to the
   last 3 years those medians fall to 835,000 (BBL) and 2.04M (KBANK) — a
   ~200x and ~96x drop respectively. SCC's median depth falls from 86.7M
   (full history) to 87,500 (last 3 years), a ~1,000x drop. **The full-history
   averages are dominated by an earlier, much more liquid regime that no longer
   exists**; using them to judge current tradability would be exactly the "stale
   print" failure mode this measurement was meant to catch. At ~THB 0.8–2M median
   depth today, BBL/KBANK are retail-position-sized, not institution-sized, and SCC
   is barely a few tens of thousands of baht.

3. **The premium does not obviously mean-revert over 1/5/20 trading days after a
   two-sided day, on the three liquid names — it is highly autocorrelated instead.**
   Lag-1 autocorrelation of the premium across consecutive two-sided days: BBL
   0.9928, KBANK 0.9559, SCC 0.9604 (diagnostic only, not evidence of a strategy).
   The forward premium-change means at t+1/t+5/t+20 for BBL/KBANK/SCC are all small
   (roughly -0.003% to -0.16%) relative to the premium level itself (2.9%–7.2%),
   consistent with a slow-moving, near-random-walk premium rather than one that
   snaps back predictably after two-sided prints. This measurement does not test
   whether the premium reverts around some other trigger (e.g. a specific
   ownership-limit event) — only whether it reverts mechanically after any
   two-sided day, which it does not appear to.

The remaining 9 names (BAY, SCCC, BANPU, ADVANC, PTT, SCB, CPALL, AOT, TU, KTB,
TISCO, EGCO — 12 total once BBL/KBANK/SCC are excluded) show two-sided fractions
from 0.6% (BANPU) to 47% (SCB), with several producing large or wild-looking
"mean premium" numbers (BANPU +35.2%, SCCC +16.7%) that are visibly not
tradable-spread numbers — they are ratios of a live price to a print that is
stale by construction, exactly as the review already flagged. SCC, though one of
the "three liquid names," is trending toward this same failure mode: its 2026
two-sided fraction (12.0%) is now close to AOT's or TISCO's, not close to BBL's or
KBANK's.

## What is tradable-looking vs stale

- **Tradable-looking, with a real caveat on trend:** BBL, KBANK. Full-history
  two-sided fraction and depth are large; but both metrics are declining sharply
  and recently, and the last-3-year picture (46–58% two-sided, THB 0.8–2M median
  depth) is a materially weaker claim than the full-history one. Any further work
  on these two should use the last-3-year numbers, not the full-history ones, as
  the operative baseline.
- **Marginal, trending toward stale:** SCC. Was plausibly tradable through ~2020
  (two-sided fraction in the 30–45% range); has fallen to 12–17% in the last three
  years with median depth near THB 87,500 — likely too thin now to act on, though
  it still trades occasionally (unlike BANPU/SCCC below).
- **Stale prints, not tradable spreads:** BAY, SCCC, BANPU, ADVANC, PTT, SCB,
  CPALL, AOT, TU, KTB, TISCO, EGCO. Two-sided fractions from under 1% (BANPU,
  0.59%) to under 47% with several producing premium statistics that are visibly
  artefactual (SCCC +56.99% mean premium on two-sided days, BANPU +35.2% on all
  days) — consistent with the review's original diagnosis that these `-F` lines
  are largely not on the same live-quote basis as the main board.

## Caveats (stated plainly, not glossed over)

- **Yahoo Finance data quality is unverified beyond internal consistency.** This
  script trusts yfinance's own OHLCV and volume fields; no independent source
  (e.g. SET's own end-of-day file) was cross-checked, because SET's machine
  APIs are blocked (403, per the review's §2.1 finding) and its HTML pages do not
  expose historical data in a scriptable form.
- **No intraday data.** "Two-sided" here means both legs printed a non-zero daily
  volume, not that they were simultaneously quotable at any moment intraday. A
  day counted as two-sided could still have had the two legs trade hours apart.
- **No bid/ask, no order-book depth, no realized spread.** The depth proxy (F
  volume × F close) measures traded value, not available liquidity at a
  particular premium level; a real execution could move the premium by an
  unmeasured amount before filling.
- **Currency is THB throughout**; no FX conversion was applied (the review's own
  §2.1 implied FX rate, 33.2 THB/USD, is not re-derived here and not needed for
  this measurement).
- **The autocorrelation and forward-change numbers are purely descriptive
  diagnostics** on daily closes; they say nothing about whether a position could
  actually be entered/exited at those closes, and are explicitly not a backtest.
- **Sample size caveat for BANPU**: only 2,381 overlapping days and 0.59% two-sided
  (14 days), so its "n_pairs" for forward-change is 0–2 — not a reliable estimate
  of anything, shown only for completeness.
- This measurement does **not** answer the review's own next question (§5, M1
  second half): whether a Thai-resident retail account can actually sell
  local-registered shares onto the foreign board, and at what fee. That is an
  operational/legal question, not a data question, and remains open.

## Bottom line for the sourcing question (R3 in the review's Step-0 table)

The foreign-board premium on BBL and KBANK is not a pure Yahoo staleness artefact
— it prints on a large majority of days across their full history and reproduces
the review's exact prior numbers on independent re-fetch. But the *current*
tradability picture (last 3 years) is materially thinner than the full-history
numbers suggest: roughly coin-flip two-sided days and THB ~1–2M median depth,
not the ~THB 180–200M the full-history average implies. SCC has decayed further
and is now closer to the stale group than to BBL/KBANK. Whether ~THB 1–2M median
depth clears this project's R3 size bar depends on the position sizing the
project would actually use — that comparison was not made here, and no return or
Sharpe was computed, per the task scope.
