# Amendment 1 — R5's expectation was mis-stated; the harness reproduces the audit (2026-09-09)

Written after run 1 (`retirement_rule_gates_output.txt`, commit f75b9bc),
before run 2.

## What run 1 showed

R5 was declared as: "expected: kills true 1.0 in roughly two of three paths
within 3 y; if this does not reproduce, the harness is wrong and nothing
above counts". Run 1 measured the old rule killing a true-1.0 strategy in
0.922 of paths by 1 y and 1.000 by 3 y, and the script's check
(0.55 ≤ rate ≤ 0.80 at 3 y) failed.

## Why the expectation, not the harness, was wrong

The "two in three" figure in the criteria fix (`underperf_mc_ar1_output.txt`,
`CRITERIA_FIX_2026-09-09.md` row U1) is **P(kill within 126 trading days)
= 0.654** at φ = 0; the same table gives **0.922 within 252 days**. I quoted
the number from memory without its horizon. Run 1's harness gives 0.922 at
252 days — the audit's own figure to three decimals — so the harness
reproduces the audit exactly and the R5 criterion is restated to the
audit's actual horizons:

    P(kill true 1.0 within 126 d) within 0.65 ± 0.05,
    P(kill true 1.0 within 252 d) within 0.92 ± 0.03.

No other criterion, boundary, seed or statistic is changed. R1–R4 results of
run 1 stand and are expected to reproduce identically in run 2 (same seeds).

## Disclosure on the selection metric (not a change)

R3's "median delay after change" is computed among paths that were caught,
so a statistic that catches few decays can show a short median. In run 1
S-B SPRT caught 14.5 % of decays within 5 y at median 2.24 y, while S-C CUSUM
caught 48.7 % at median 2.06 y. The pre-declared selection rule is applied as
written (S-B was the only statistic passing R1 and R2 at s0 = 0.5, so the
metric did not decide anything), and the results memo reports P(caught) next
to the median so the weakness is visible. A future revision should select on
P(caught within H) — noted here, not adopted here.
