# Bet-level test (option C) — REJECTED at its own Phase 1 gate, 2026-09-09

**Question the owner asked:** would an "adaptive by mechanism shape" test —
scoring each family on the return of its declared bet unit (an event window,
a formation) instead of the daily Sharpe of the whole series — detect small
real edges better without admitting fake ones?

**Pre-committed gate (stated before running):** on a synthetic null with
clustered events, overlapping bets and crisis-heteroskedastic noise, the
bet-level PSR with an overlap/cluster-robust effective n must keep its
false-positive rate at or below nominal. "If it does not, C is dead — no SE
tuning until it passes."

**Result (`bet_level_fp_gate_output.txt`, 2 000 replications, seed 20260909):**

| statistic | false-positive rate at the 0.95 bar (null) | power, true active-day Sharpe 1.0 |
|---|---|---|
| A — daily PSR, idle days as zeros (**the project's current test**) | **0.047** (nominal 0.05) | 0.257 |
| B — naive bet PSR, i.i.d. n | 0.138 (2.7× nominal) | 0.378 (bought with false positives) |
| C — bet PSR, Newey-West HAC effective n (maxlags = window, pre-declared) | **0.086 — FAIL** | 0.268 |
| C′ — bet PSR, cluster-by-month effective n | 0.074 — FAIL | 0.241 |
| continuous monthly mechanism, i.i.d. daily noise | — | daily 0.507 / 0.857 vs monthly bets 0.505 / 0.860 at true Sharpe 0.5 / 0.8 — **exactly neutral** |

**Two findings, both against the proposal:**

1. **The robust-n correction under-corrects.** With ~110 bets, HAC/cluster
   standard errors are biased downward in finite samples (a known property,
   not a bug in the script — the design effects of 1.8–1.9 are real and are
   still not enough). The false-positive rate is 1.5–1.7× nominal. Under this
   project's rule that a false positive is the worst outcome, that ends C as a
   primary statistic.

2. **The √f "dilution" argument was wrong.** I claimed a mechanism active on a
   fraction f of days has its daily Sharpe shrunk by √f, so the daily test
   was throwing away power. The shrinkage is real, but the observation count
   grows by exactly 1/f at the same time, and the PSR z-statistic is
   Sharpe × √n — the two cancel. The simulation confirms it: power 0.257
   (daily) vs 0.268 (bet-level, and that with an inflated size). **Idle days
   recorded as zeros cost the daily test nothing.** The same holds for the
   continuous monthly case (0.507 vs 0.505): aggregation to the decision
   frequency neither helps nor hurts an i.i.d. series.

**What this means:**

* The project's existing measurement — daily Sharpe of the full series →
  PSR/DSR — is **not** the source of lost power, and it held its nominal
  false-positive rate under event clustering and regime heteroskedasticity
  without any adjustment. It stays the primary statistic.
* The lost-power problem is entirely sample length (`criteria_fix_2026-09-09`:
  0/50 families with 80% power at a true Sharpe 0.5). No re-statistic fixes
  that. The only honest levers are (E) forward continuation with a
  pre-declared look schedule, and more data.
* Options B (per-type taxonomy) and D (pooling) were already rejected in
  discussion; C is now rejected by measurement. **Nothing from the "adaptive
  by mechanism shape" idea should be built.**

**Residuals, stated:** one synthetic world (T = 2 926, H = 10, hazards
0.01/0.15, crisis vol ×2). A world with far fewer, longer bets could behave
differently — but in the direction of *fewer* effective observations, which
makes HAC worse, not better. The alternative used a fixed per-day effect;
concentrating the effect in crises would raise both tests' power together
and not change the comparison. Not tested: a bet-level statistic with a
small-sample HAC correction (Kiefer-Vogelsang fixed-b); it would need its
own validation and would still not add power, so it is not worth building.

This is an honest negative on a methodology proposal I made myself, caught
by the validation gate I insisted on before building. Recorded so the idea is
not re-proposed without this evidence.
