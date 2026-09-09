# Root cause of the two "reproducibility gaps" recorded 2026-09-09 morning

**Verdict: the data path IS point-in-time. Neither gap was a data revision. Both were
the re-scorer capturing the wrong replay — the LAST sensitivity arm instead of the
main (persisted) replay — plus a second, smaller process-environment effect
(section 4).**

## 1. What was recorded that morning (dormant_rescore.py, KNOWN_REPRODUCIBILITY_GAPS)

| family / spec | persisted | re-run (demo) | drift |
|---|---|---|---|
| quarter_end_marking / qem_month_placebo_day0_perf_h126 | -0.2151 | -0.5084 | -0.293 (flagged) |
| tax_loss_selling_turn_of_year / tls_dec_full_year_lossonly_h21 | +0.0905 | +0.0338 | -0.057 |

Both at n=2932 on the identical sp500 window (2015-01-07 .. 2026-09-05). The
suspected causes written down then — price-store revisions, a refreshed
membership snapshot — were guesses, and they were wrong.

## 2. Measurement (scratch script, no re-scorer code involved; main checkout, 2026-09-09 evening)

Each family run sp500-only through its own entry point with a thin wrapper on
`run_cross_sectional_backtest` that records EVERY replay in call order (the
re-scorer's hook keeps only the last one per pattern_id).

Original window end 2026-09-05:

| | qem placebo h126 | tls full_year h21 |
|---|---|---|
| replays per spec | 5 | 5 |
| max abs diff, re-run baseline vs committed JSON, ALL specs | 2.2e-16 | 5.6e-17 |
| committed sensitivity arms vs re-run arms | identical (x0/x1/x2) | identical (0/34/430bp) |
| captured series, in order (pre-cut Sharpe) | -0.2151, -0.2151, +0.0796, -0.2151, **-0.5104** | +0.0905, +0.0905, +0.0953, +0.0905, **+0.0349** |
| committed LAST arm | cost_x2 = -0.51042 | borrow_430bp = +0.03492 |

The captured last series IS the committed last arm, to 1e-16. The families
replay every spec five times: the screen, `_replay_all`, then one pass per
sensitivity arm (qem `_cost_arm(multiplier=0,1,2)`; tls `_sensitivity_arm`
borrow 0/34/430bp). The hub hook's "last write wins" therefore kept the
x2-cost / 430bp-borrow series, which is what the drift check compared with the
persisted BASELINE row. Same defect class as the bespoke-engine cost-arm trap
already gated in `_EXTRA_BESPOKE`; the shared-harness families were not gated.

Window end 2026-09-09 (one more trading day in the panel), cut at 2026-09-05:
pre-cut captured Sharpes move by <= 1e-8 (qem -0.51041983 vs -0.51041984; tls
+0.03491981 vs +0.03491981). The extra day does not explain anything.

Also checked and excluded: the price store had NO file modified between the
morning demos (16:08 +07) and these runs; the 143 sp500 tickers with no price
data are the same 143 (delisted names Yahoo no longer serves — consistent, not
transient); the point-in-time membership (768 tickers, per-date state) hashes
identically in a fresh process and inside the re-scorer's process; the
OHLCV panel for a 10-ticker probe hashes identically in both.

## 3. Fix

`_HUB_ARM_GATES` in dormant_rescore.py: while `qem._cost_arm` or
`tls._sensitivity_arm` executes, the family module's `run_cross_sectional_backtest`
binding is swapped back to the UNHOOKED harness, so only the main replay is
recorded. Unit-tested on a synthetic module (records main, not arms, restores
on exception). KNOWN_REPRODUCIBILITY_GAPS is now empty; the mechanism stays.

## 4. The residual (~0.003): found, and it was a real data defect

Bisecting the re-scorer's process (imports only / capture hooks / both) pointed
at "imports", but hashing the harness INPUTS for the focal spec — the OHLCV
panel, the calibrated half-spread frame, the config, the membership — showed
them identical fresh vs imports. What differed was the CHECKOUT: the scratch
measurements ran in the main checkout, every re-scorer run (the morning demos,
the populate run, the bisect) ran in a git worktree.

**4a. The price store was per-checkout.** `price_store.DEFAULT_STORE_DIR` was
anchored to the importing file's own `backend/`, unlike the SQLite default
(which app/config.py routes to the MAIN checkout through git's common dir).
Every worktree therefore fetched a PRIVATE store from the vendor on the day it
ran; four such stores were found under .claude/worktrees/. Overlapping rows
agreed exactly for ordinary tickers (the as-traded design works) — but not
for every ticker, which is 4b.

**4b. Three tickers in the MAIN store were frozen at the wrong share basis.**
Comparing the main store row-by-row with a fresh as-traded reconstruction
(store bypassed):

| ticker | stored / vendor ratio | rows off | correct-basis rows stored later | fake daily returns inside research windows |
|---|---|---|---|---|
| APH  | 0.5   | 8228 / 8231 | from 2026-09-02 | 2026-09-02 **+96.2%** |
| MNST | 2.0   | 8206 / 8231 | 25 rows, 2026-07/08 | 07-20 −51%, 07-23 +96%, 07-31 −51%, 08-03 +94%, 08-06 −50%, 08-07 +92%, 08-10 −49% |
| RUSHA | 0.6667 | 2928 / 2933 | 5 rows from 2026-08-31 | 2026-08-31 **+51.1%** |

Mechanism (price_store.py section 4b): around a split the vendor re-bases the
price history and posts the split EVENT at different times; a fetch landing
between the two reconstructs "as-traded" prices with the wrong cumulative
split factor (APH: prices halved, no event yet → stored at 0.5×; MNST: event
present, prices not yet re-based → stored at 2×). A later, consistent fetch
appends only the NEW dates, at the other basis, and first-write-wins freezes
the join. The 3,205 disagreeing overlap rows WERE reported as
"revisions held back" at WARNING level — indistinguishable from the policy
working. APH and MNST are S&P 500 members; every S&P 500 family whose window
crosses 2026-07-20 .. 2026-09-02 (all of the 2026-09-04..06 production runs)
carried these fabricated days. That is the ~0.003 (qem, tls), and very likely
the 0.014 / −0.016 / 0.049 drifts recorded for asset_growth, pead_ear and
dividend_pressure on the same morning.

Four other tickers the audit flagged (NKTR, PARA, POM, SSP) were confirmed
CONSISTENT with the vendor row-by-row: real moves around reverse splits, not
defects. The audit is a screen; the vendor comparison is the confirmation.

## 5. Fixes (this branch)

1. `_HUB_ARM_GATES` in dormant_rescore.py (section 3) — the flagged gaps.
2. `price_store.DEFAULT_STORE_DIR` now routes to the MAIN checkout's store
   from every worktree (`SHARED_STORE_ROOT`, same resolver as the database).
3. `basis_mismatch()` + a guard in `PriceStore.merge_ticker`: an overlap that
   disagrees by one near-constant ratio on most rows is a SHARE-BASIS
   MISMATCH, reported on `PriceStoreReport.basis_mismatches`, logged at ERROR
   by the provider, and the append is HELD BACK (a missing bar is honest; a
   fabricated +96% day is not). Nothing automatic rewrites a stored row.
4. `audit_frame` / `audit_store` / `PriceStore.quarantine_ticker` and
   data/research_runs/price_store_basis_audit.py (`--since`, `--confirm`,
   `--repair`). Output committed: price_store_basis_audit_2026-09-09.json.
5. APH, MNST, RUSHA repaired in the shared store: defective files copied to
   data/price_store/quarantine/2026-09-09/, resynced, re-fetched, re-audited
   clean and re-confirmed 0 rows off against the vendor.
6. Tests: 3 on the re-scorer gate, 6 on the store (routing, mismatch held
   back, ordinary revision unaffected, detector thresholds, audit, quarantine).

## 6. What the repaired, shared store changes downstream

Persisted results computed 2026-09-04..06 from the defective store are NOT
re-persisted here (the verdicts are definite negatives; a 0.003–0.05 Sharpe
shift flips none of them) but they are now known to carry the fabricated
APH/MNST/RUSHA days; the re-scorer's pre-entry drift will show the size of
that contamination family by family (section 7). Any future production run
reads the shared, repaired store.

## 7. Re-measurement on the shared, repaired store (same 16 families, same frozen specs)

Pre-entry drift = re-run Sharpe on the original window minus the persisted Sharpe.

| family | morning (private store, last-arm capture) | evening (shared repaired store, gated) | bucket |
|---|---|---|---|
| quarter_end_marking (demo, excluded family) | −0.293 FLAGGED | −0.0005 | — |
| tax_loss_selling_turn_of_year (demo) | −0.057 | +0.00003 | — |
| round_c | −0.0038 | 0.0 | LOW |
| small_cap_disposition | +0.0077 | 0.0 | LOW |
| eigenportfolio_statarb | +0.0022 | 0.0 | HIGH (φ̂ 0.115 → 0.113) |
| best_ideas_13f | +0.0008 | −0.0001 | LOW |
| asset_growth | +0.0142 | +0.0142 (unchanged; not the store) | LOW |
| pead_ear | −0.0155 | −0.0155 (unchanged; not the store) | LOW |
| dividend_payment_pressure | +0.0489 | +0.0489 (unchanged; calendar rebuilt after the run, unproven) | LOW |
| the other 9 | ≤ 1e-4 | ≤ 1e-4 | unchanged |

No entry changed bucket or pit_ok; the manifest was rebuilt from the evening
staging with the same three attribution exclusions carried over. The quarter_end
−0.0005 and tax_loss +0.00003 residuals are the size of the APH/MNST repair's
effect on numbers that were persisted from the defective store.

Remaining, honestly open: asset_growth (+0.014) and pead_ear (−0.016) do not
reproduce their persisted Sharpe and the price store is now excluded as the
cause; their EDGAR fundamentals / earnings-date inputs are the next suspects.
Both are under the 0.10 flag and carry pit_ok = True by the pre-registered
rule, with the drift recorded in their entries.

## 8. Housekeeping the fix leaves behind

Four private stores exist under .claude/worktrees/*/backend/data/price_store
(coval-stafford-firesales, frazzini-lamont-dumbmoney, gabaix-koijen-inelastic,
rescore-arm-gate). With the routing fix nothing reads them; they go away with
their worktrees. The 2026-09-08 candidates (#14–16) were computed from those
private stores — their windows and universes should be checked against the
audit before any of them is ever re-opened.
