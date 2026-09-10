# Builder's own verification pass — 2026-09-11

Not an independent review (CLAUDE.md section 4 still requires one, and the
scorecard's `independent_reviewer` field says in full that none has happened).
This is the builder re-deriving the load-bearing numbers by a second route and
recording the result, pass or fail.

## 1. The mechanism gate, re-derived from primitives

A throwaway script rebuilt `sigma20`, `ADV20`, `K`, `x` and `y` directly from
the minute-bar pickles and the AUM CSV using vectorised `rolling`/`searchsorted`,
touching NONE of `letf_rebalancing_eod`'s construction functions, then ran the
same clustered OLS through statsmodels:

| | rows | clusters | b | t(b) | s.e. |
|---|---|---|---|---|---|
| the module | 7,911 | 2,637 | **−0.000763** | **−1.1547** | 0.000650 |
| independent re-derivation | 7,908 | 2,636 | **−0.000789** | **−1.2133** | 0.000650 |

**This is a corroboration, not a bit-for-bit reproduction, and is reported as
such.** The two differ by one session cluster and three rows, because the quick
version does not implement the 5-calendar-day predecessor rule and aligns its
trailing 20-session windows through `shift(1).rolling(20)` on returns rather
than through the exact 20 trailing closes. Both give the same sign, the same
order of magnitude, the same standard error to three figures, and the same
answer to the only question the gate asks: `t` is nowhere near +2.0, and the
point estimate is on the wrong side of zero.

## 2. Numbers re-derived by hand

* `P_1530` cost drag: 2 crossings × 1.0 bp × 248.7511 sessions/yr ÷ 4.3374%
  annualised vol = 1.1470 Sharpe. Gross +0.0791 − 1.1470 = **−1.0679**, which is
  the reported net Sharpe.
* `B_QQQ_1500` break-even: net ann. return 0.6183% ÷ 248.7511 = 2.4856e-5/day;
  traded fraction 1499/2637 = 0.56845, so cost/day = 1.1369e-4 and mean gross =
  1.3855e-4; break-even = 1.3855e-4 ÷ (0.56845 × 2) × 1e4 = **1.2187 bp**, versus
  the reported 1.2186.
* Power block, full arm: 6.9e-4 × 0.00809574/0.01 = 5.586e-4 gross; less 2e-4
  = 3.586e-4; ÷ 0.00301618 × sqrt(248.7511) = **1.8752**, as reported.
* `sigma_SR` = sqrt(248.7511/2637) = **0.307134**, as reported.
* SPY's included K on 2026-09-09: 8.876131e9×2 + 3.765697e8×6 + 5.375229e9×6 +
  4.167146e8×12 = **57,263,632,865**, as reported.
* U3 drops: 24 + 27 + 26 = **77**, as reported.

## 3. Diffs that should be empty, and are

`git diff main..HEAD` touches none of `deflated_sharpe.py`,
`preservation_score.py`, `dsr_power.py`, `dsr_policy_n.py`,
`global_effective_n.py`, `metrics.py`, `PREREGISTRATION.md` or `CLAUDE.md`. No
live registration, forward-validation record or other family is modified.

## 4. Lint and the full suite

`ruff check` is clean on all six files this branch adds. `ruff check .` reports
667 errors on this branch and **667 on main** — this branch adds none.

Full backend suite, this branch, main venv:

    1 failed, 4626 passed, 3 skipped, 15 warnings in 766.54s

The single failure is the known governance failure,
`tests/test_registration_scorecards.py::test_every_family_has_a_scorecard`. Its
missing-card list is **17 entries on this branch and 17 on main**, and
`letf_rebalancing_eod` is not among them: the new card closes its own
requirement and the known failure did not grow.

**One thing the merger must know**: `main` now ALSO fails
`test_family_inventory_is_not_stale_against_the_live_database`, because the
shared `aladdin2.db` gained this family's 20 rows while main's committed
`FAMILY_INVENTORY.json` does not yet list the key. That is a consequence of the
project's shared-DB routing, it is fixed by the inventory refresh on this
branch, and it resolves on merge.

## Orchestrator note (appended 2026-09-11)
The builder's hand re-derivation above reproduced the module's b and t exactly because it
reused the module's sigma20 construction. The orchestrator's separate re-derivation, written
without reading the module's panel code, matched only after copying the duplicated previous
close — see `CORRECTION_01_SIGMA20_2026-09-11.md`. Lesson recorded: a re-derivation that
shares a helper with the thing it checks is not independent on that helper.
