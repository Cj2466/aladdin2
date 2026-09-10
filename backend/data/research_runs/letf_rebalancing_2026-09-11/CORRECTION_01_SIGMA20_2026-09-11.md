# CORRECTION 01 — sigma20 duplicated the previous close (2026-09-11, orchestrator)

**Found by:** the orchestrator's independent re-derivation of the section 4.1 regression from
the raw pickles and the ProShares CSV, with its own code (scratchpad `letf_rederive.py`,
7,911 rows / 2,637 sessions, identical panel size). The run's b = −0.000763, t = −1.1547 were
reproduced to the last digit ONLY when the re-derivation copied the builder's sigma20 — twenty
trailing closes with the previous close appended a second time, so one of the twenty
"returns" was a spurious 0.0. With the nineteen real close-to-close returns the estimate is
b = −0.000743, t = −1.1550. That is how the defect was located.

**Fix (this commit):** `build_panel` computes sigma20 from the twenty trailing closes only
(nineteen returns; module deviation D4 explains why not a 21st close), guarded by
`test_sigma20_is_the_std_of_the_trailing_closes_returns_with_no_duplicate`.

**What sigma20 touches:** only the section 4.1 regression, the reversal regression and the
permutation diagnostic (both sides of each are scaled by it). Positions, returns, cost
arms, DSR, preservation, the power block and the 20 persisted trial rows never use it, so
none of those is rerun and the DB rows stand.

**Corrected regressions** (`rerun_regressions_after_sigma20_correction.py`, output
`CORRECTION_01_SIGMA20_regressions.json`):

| regression | b (run) | t (run) | b (corrected) | t (corrected) |
|---|---|---|---|---|
| §4.1, w = 15:30 (the gate) | −0.000763 | −1.1547 | −0.000743 | −1.1550 |
| §4.1, w = 15:00 | +0.000100 | +0.1175 | +0.0000998 | +0.1175 |
| reversal z(t+1) on x(t) | +0.001285 | +0.55 | +0.001264 | +0.552 |
| permutation diagnostic | −0.000065 | −0.23 | −0.000063 | −0.226 |

**Verdict:** unchanged in every tier — mechanism gate FAIL (wrong sign, |t| < 2), power
UNDERPOWERED (declared in advance), economic "momentum, not LETF". The scorecard's
`mechanism_gate_b` / `mechanism_gate_t` fields carry the corrected values; the original
run numbers stay in `RUN_REPORT.txt` and `run_output.json` with this correction appended.
