# Forward-retirement rule, version 2 — protect level 1.0, CUSUM (2026-09-09)

## 0. Provenance, stated before anything else

Version 1 (`RETIREMENT_RULE_PREREGISTRATION.md`) named protect level
s0 = 0.5 as primary and, under its pre-declared selection rule, adopted the
SPRT. The same pre-registration declared s0 = 1.0 as an alternative "the
owner may choose" and the gate script computed both in one run (run 2,
`retirement_rule_gates_output.txt`, 9484ab1). On 2026-09-09 the owner,
shown both, chose s0 = 1.0.

This is therefore **a choice among two pre-declared alternatives whose
numbers were computed in the same pre-registered run — not a boundary or
criterion edited after seeing results.** It is still a choice made after
seeing the numbers, and that is disclosed here rather than dressed up. The
honest consequence: the false-recommend rate at true 0.5 (11 % within 5 y)
was known when the choice was made and is accepted, not discovered.

Nothing in the gate script, the seeds, the models, R1–R5 or the statistic
definitions changes. No new simulation is run for this version; the
numbers below are copied from run 2's "PROTECT s0 = 1.0" section.

## 1. The rule

Statistic S-C CUSUM (Page): C_t = max(0, C_{t−1} + ℓ_t), C_0 = 0, with
ℓ_t = d (z_t − m), d = (s1 − s0)/√252, m = (s1 + s0)/(2√252), s0 = 1.0,
s1 = −1.0, z_t the daily net return standardized by the expanding-sample sd
(ddof = 1). Monitored daily from day 60. Recommend retirement at the first
day C_t ≥ h, with h the simulated 0.95 quantile of max_t C_t over 5 y under
true Sharpe 1.0, worst case over the bucket's contract models:

| bucket | h |
|---|---|
| LOW (φ̂ ≤ 0.10) | 5.8180 |
| HIGH (φ̂ > 0.10) | 7.9806 |

Bucket = `dormant_pool.assign_bucket` on the registration's ORIGINAL-window
series, fixed at registration. **When φ̂ has not been measured for a
registration, the HIGH boundary is used** (the higher boundary recommends
less often — the conservative direction for a rule that can only ever
recommend). The four live registrations' φ̂ values are recorded in
`RETIREMENT_RULE_V2_RESULT.md` as they are measured.

## 2. Measured operating characteristic (run 2, s0 = 1.0, CUSUM)

| | LOW | HIGH |
|---|---|---|
| R1 false-recommend within 5 y at true 1.0 | 0.025 normal / 0.023 t4 / 0.054 AR(1) 0.1 | 0.049 AR(1) 0.3 |
| R2 catch true −1.0 within 5 y | 0.95 (median 2.06 y, DD at trigger 2.9 vol-units) | 0.83 (median 2.85 y) |
| R3 decay: 1.0 for 2 y then −1.0, caught within 5 y | 0.76 (median delay 1.67 y, 80th pct 2.34 y) | not measured (R3 ran in LOW only) |
| true 0.5 recommended within 5 y (the accepted cost) | 0.11 | — |
| true 0.3 | 0.19 | — |
| true 0.0 | 0.37 | — |

## 3. What adoption means (unchanged from v1 §5)

`retirement_rule.py` exposes the CUSUM statistic and these boundaries as the
adopted rule (v1's SPRT stays available, marked superseded); the advisory
bundle every forward registration already carries gains a
`retirement` block (rule id, bucket, statistic, boundary, recommended flag,
first-trigger day). Nothing flips a status: the dashboard shows the
recommendation and the owner decides (CLAUDE.md rule 6). A capital stop
wired to this rule would need its own pre-registration.
