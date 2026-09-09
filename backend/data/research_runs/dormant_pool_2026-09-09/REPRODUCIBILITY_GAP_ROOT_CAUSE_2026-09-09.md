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

## 4. The residual: a process-environment effect of ~0.003 (open, measured)

With the gate in place the re-scorer's own demo on qem gives -0.21225 against
the persisted -0.21507 (drift +0.0028); the tls populate-run reruns sat
0.0008–0.0076 BELOW their 430bp arms. The scratch runs above (family called
directly, no re-scorer imports, no capture hooks) reproduce to 1e-16. So
~0.003 of shift is introduced by something in the re-scorer PROCESS itself,
not by data, membership or window. The same order of drift shows on other
shared-harness families' committed looks (quality_cbop -0.0034, round_c
-0.0038, eigenportfolio +0.0022) while flat-cost/ETF families reproduce to
1e-15. See section 5 for the bisect result.
