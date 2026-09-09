# Amendment 1 to the Dormant pool pre-registration — autocorrelation buckets

Written after gate run 1 and run 2 (both committed, `4ad7c63`), before run 3.
The original pre-registration is unchanged; this document supersedes its §4
boundary rule only in the way stated here.

## What happened

Run 1 (boundary calibrated under i.i.d. normal, C_K = 0.98865): G1 and G2a
passed; **G2b (AR(1) φ = 0.3) failed** at 0.1661 false promotion. Per §5 the
boundary was recalibrated under the worst model (C_K = 0.99902) and run 2
passed every gate — at a power cost the pre-registration required to be
stated: a true-Sharpe-0.5 family is promoted within 10 years with probability
0.10 (was 0.35), a true-1.0 family 0.59 (was 0.86).

## Why φ = 0.3 was the wrong stress

Measured on the project's own committed return matrix
(`global_effective_n_return_matrix_2026-09-05.csv.gz`, 481 spec-level daily
net-return series, ≥ 500 observations each), lag-1 autocorrelation is:

    5% / 25% / 50% / 75% / 95%  =  −0.096 / −0.033 / −0.001 / 0.029 / 0.070
    max = 0.247;  share > 0.1 = 1.9%;  share > 0.2 = 0.8%;  share > 0.3 = 0.0%

A boundary calibrated for φ = 0.3 protects against a return process no
persisted spec exhibits, and pays for it in exactly the currency this whole
exercise exists to conserve.

## The amended rule (pre-declared, applied at ENTRY, never re-chosen)

At entry into Dormant the family's lag-1 autocorrelation φ̂_entry is measured
on the frozen spec's daily net returns over the **original** window (data
that exists before any extension — so this choice cannot peek at the
extension) and recorded on the entry.

| bucket | condition | boundary C_K calibrated as the max over |
|---|---|---|
| LOW  | φ̂_entry ≤ 0.10 | i.i.d. normal, Student-t(4), AR(1) φ = 0.10 |
| HIGH | φ̂_entry > 0.10 | AR(1) φ = 0.30 (run 2's boundary, 0.99902) |

The LOW bucket covers 98% of persisted specs with a margin above their 95th
percentile (0.07 → 0.10). A family in HIGH keeps the conservative boundary.
The bucket is written into the entry record and is never changed afterwards.

## Gates for run 3 (criteria unchanged from §5, applied per bucket)

* LOW bucket: G1 (normal) ≤ 0.05 + 2se; G2a (t4) ≤ 0.07; G2b at **φ = 0.10**
  ≤ 0.07; and, as a disclosed stress beyond the bucket's contract, the
  false-promotion rate at φ = 0.30 is reported (expected to exceed 0.07 —
  that is what the HIGH bucket exists for).
* HIGH bucket: G2b at φ = 0.30 ≤ 0.07 (run 2 already showed 0.0504).
* G3 power reported for both buckets.

Attack considered before adopting: "φ̂_entry is estimated on the same window
the spec was selected on — does selection bias it?" Selection is on Sharpe,
not on autocorrelation; a selected spec's φ̂ is not systematically inflated
by being the best-Sharpe spec. Residual: φ̂_entry from ~2 900 observations
has a standard error of ≈ 0.02, so a family at true φ = 0.11 can land in LOW.
The LOW boundary's φ = 0.10 calibration plus the 0.07 tolerance in G2b absorb
that; a family at true φ ≥ 0.2 mis-bucketed into LOW is a 0.8%-of-specs case
and is the reason G2b at φ = 0.30 is still reported for LOW rather than
hidden.
