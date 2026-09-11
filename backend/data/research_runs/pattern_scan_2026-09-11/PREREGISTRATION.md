# PRE-REGISTRATION — rule-free pattern scan vs. placebo (`pattern_scan_placebo`)

Written 2026-09-11 ~23:00 Bangkok by the orchestrator (Fable 5.1) at the owner's request, BEFORE
any scan was run. The owner's hypothesis, in their words: the price chart is the honest record of
everything that happened; scanning it for recurring patterns without imposing a theory should find
what is really there. This experiment tests that hypothesis directly against the one alternative it
must beat — that the patterns a scanner finds live in the scanner (and in noise), not in the market.
Nothing here is a theory about markets. Committed and merged to `main` before the build; amendments
are dated ADDENDUM files; this file is never rewritten.

## 0. Scope
Observational. No registration, no live-status change, no capital, no paid data, no DB writes
except the persisted summary rows the run script writes under its own run tag. The result feeds the
BOOK-membership discussion at most; nothing here certifies a single family (the certifiability
ceiling of 2026-09-11 applies to any individual pattern exactly as to any family).

## 1. The question, stated so that both answers are possible
**Q:** Does a fully generic pattern alphabet, applied to every price series this project holds,
find more and stronger recurring "shape → next move" regularities in the REAL series than the same
scanner finds in placebo series that preserve everything about the data except time-ordered
information? And do the strongest real patterns survive a held-out period the scanner never saw?
**Yes** = the owner's hypothesis is supported on this data at this resolution. **No** = the
patterns are scanner artifacts on this data at this resolution — not a statement about other
resolutions, universes or alphabets.

## 2. Data (all already held; nothing fetched)
- **Panel E (US equities, daily):** every ticker in the shared point-in-time price store
  (`data/price_store/v1`, 1,593 files on 2026-09-11) with ≥ 1,000 daily rows, read through
  `PriceStore.read_ticker` and split/dividend-adjusted through the store's own `adjusted_frames`
  path (the same path every family uses). Sample 2016-01-04 → 2026-09-08 (the last store date).
  Survivorship: the store holds what the families needed; whatever bias that carries is IDENTICAL
  in the real and placebo arms because the placebo is built from the same series, and the outcome
  is cross-sectionally demeaned (§3), which removes common drift.
- **Panel C (crypto, hourly):** the 25 Binance symbols in `data/binance_hourly/` (spot close;
  perp close as a robustness re-run), 2019-09-08 → 2026-09-11.
- Bars with a missing predecessor are dropped; a series' first 20 bars are burn-in for σ.

## 3. The alphabet (generic; declared once; not tuned)
For each series i and bar t: r_{i,t} = close_t / close_{t−1} − 1; σ_{i,t} = standard deviation of
r over the 20 bars strictly before t; z_{i,t} = r_{i,t} / σ_{i,t}. Bin b_{i,t} = D if z < −0.5,
F if −0.5 ≤ z ≤ 0.5, U if z > 0.5. A **pattern** is the ordered tuple of the last k bins
(b_{t−k+1}, …, b_t), k ∈ {3, 5, 8}: 27 + 243 + 6,561 = **6,831 patterns per panel**, encoded as
base-3 integers. No other feature (volume, level, trend, calendar) enters. This alphabet is one
choice; it is the most theory-free one the orchestrator could state in two lines, and its
limitations are §9's first item.

**Outcome:** y_{i,t+1} = r_{i,t+1} − mean_j r_{j,t+1} over the panel's names alive at t+1
(cross-sectional demeaning: a pattern must predict RELATIVE next-bar movement; this removes market
drift and survivorship-induced drift from both arms alike). Primary horizon h = 1 bar. Secondary
h = 5 bars (sum of the next five demeaned returns), reported, not gating.

**Pattern portfolio:** on each bar t, the equal-weight average of y_{i,t+1} over every name whose
last-k bins equal p gives the pattern's return series R_{p,t}. A pattern is **measurable** only if
it has ≥ 10 names on ≥ 250 bars (Panel E) / ≥ 5 names on ≥ 2,000 bars (Panel C) in the discovery
window; unmeasurable patterns are counted and excluded from every statistic.

**Statistic:** t_p = mean(R_p) / NeweyWest-SE(R_p, lag = h) over the discovery window;
SR_p = annualized Sharpe of R_p (252 for E, 8,760 for C — reported only; the gate uses t).

## 4. Windows (fixed)
| panel | discovery | holdout |
|---|---|---|
| E | 2016-01-04 → 2022-12-31 | 2023-01-03 → 2026-09-08 |
| C | 2019-09-08 → 2023-12-31 | 2024-01-01 → 2026-09-11 |
The holdout is touched exactly once, in §6, after §5 is complete and committed.

## 5. Placebos (the control the owner's hypothesis must beat)
Both placebos are applied to the demeaned return matrix and then run through the IDENTICAL
scanner (same code path, same alphabet, same measurability rule, same statistic):
- **P1 sign-flip:** every r_{i,t} is multiplied by an independent ±1 (seeded). Magnitudes, volatility
  clustering, cross-sectional dispersion and each name's history length are preserved exactly; every
  form of sign predictability is destroyed. This is the null "the past shape carries no information
  about the direction of the next move".
- **P2 time-shuffle:** each name's return series is independently permuted in time (seeded).
  Preserves each name's return distribution; destroys all temporal structure including volatility
  clustering. This is the cruder null; if P1 and P2 disagree, P1 decides and P2 is reported.
- **Draws:** 20 seeded draws of each (seeds 1…20). Every placebo statistic below is the
  distribution over draws; "beyond the envelope" means above the maximum of the 20 draws
  (empirical p < 1/21 ≈ 0.048 under exchangeability).

**Control non-degeneracy (CLAUDE.md §4):** P1 changes the bin sequence of every name with
probability 1 − 3^{−k} per pattern position and changes the outcome sign with probability ½, so no
pattern's real and placebo portfolios can coincide except by chance on a measure-zero set; the
builder's test must show, on the real panel, that the fraction of (pattern, date) cells whose
membership is identical between the real and a P1 draw is below 5%.

## 6. Decision rules (declared now; read off mechanically)
Discovery window, per panel, computed for the real arm and each placebo draw:
- N3 = number of measurable patterns with |t_p| ≥ 3; N4 = same at 4; Tmax = max |t_p|.
- **GATE 1 (existence):** PASS iff N3_real > max_{draws} N3_P1 AND Tmax_real > max_{draws} Tmax_P1.
Holdout window (touched once):
- Take the 20 measurable patterns with the largest |t_p| in discovery (real arm), orient each by
  the sign of its discovery mean, and form the equal-weight daily average of the 20 oriented
  R_{p,t} series over the holdout → one series H_real. Do the same for each P1 draw (its own
  top-20, its own orientation) → H_{P1,d}.
- **GATE 2 (survival):** PASS iff t(H_real) ≥ 2.0 AND t(H_real) > max_d t(H_{P1,d}).
- **Overall:** "patterns beyond noise on this data" iff GATE 1 and GATE 2 both PASS on a panel.
  Reported per panel; the two panels do not rescue each other.
- Secondary, reported, not gating: the same with |t| ≥ 4; the h = 5 horizon; a cost arm — 5 bp
  one-way on E and 10 bp on C applied to the daily turnover of H_real (a pattern portfolio
  rebalances every bar, so this will be large; it is what a naive follow-up would pay).
- Multiple comparisons are handled by the placebo envelope, not by DSR; the count of patterns
  scanned (6,831 × 2 horizons × 2 panels = 27,324) is recorded so nothing is hidden.

## 7. Validation on a known answer (before the real scan)
Synthetic panel: 500 names × 2,000 bars of i.i.d. Student-t(4) returns with a planted rule — after
the bin sequence (U, U, U) the next demeaned return is shifted by +0.30σ. The scanner must recover
that pattern with t ≥ 3 and place it in the top-3 by |t| in discovery, must find no pattern with
|t| ≥ 3 in a P1 draw of the same synthetic panel beyond what 6,831 draws of a null t-statistic
produce (report the count against the analytic expectation ≈ 6,831 × 0.0027 ≈ 18), and the planted
pattern's holdout t must exceed 2. Committed as a test.

## 8. What is NOT allowed
No change to bins, thresholds, k, windows, measurability rule, number of draws, top-20 count, or
gate thresholds after any real-arm number exists. No second alphabet in this run. No dropping a
panel. Any deviation is a dated ADDENDUM committed before the affected result.

## 9. Known limits, stated before the result
1. One alphabet (sign/size bins of the last 3–8 bars). A negative says nothing about volume-based,
   multi-scale, cross-asset or level-based shapes. A follow-up may declare a second alphabet in a
   new pre-registration; it may not be added here.
2. Daily equities and hourly crypto only; no tick data.
3. The demeaned outcome tests RELATIVE predictability; a pattern that predicts the whole market's
   next move is invisible here by design (it would be a market-timing claim, a different test).
4. The universe is the store's, not a clean point-in-time index; both arms share it.
5. The cost arm is naive (bar-by-bar rebalancing); a real implementation would net positions.

## 10. Deliverables
`app/services/research_lab/pattern_scan_placebo.py` (alphabet, scanner, placebos, gates),
`tests/test_pattern_scan_placebo.py` (§7 + non-degeneracy + determinism), run script
`data/research_runs/run_pattern_scan_placebo.py`, outputs under
`data/research_runs/pattern_scan_2026-09-11/`: `RUN_REPORT.txt`, `run_output.json`,
`patterns_discovery_E.csv` / `_C.csv` (every measurable pattern's t, SR, n_bars, mean names),
`placebo_envelope.json`, `holdout_top20_E.csv` / `_C.csv`, and the persisted summary rows
(one per panel per arm) under run tag `pattern_scan_placebo_2026-09-11`.
