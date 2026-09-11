# DECLINED_AT_SOURCING ledger

Every family whose claimed effect fails `app.services.research_lab.
sourcing_power_check.sourcing_power_check`'s pre-build power pre-check (power
at the most conservative declared fraction of the claim, at n_local, below
`dsr_power.POWER_FLOOR` = 0.80) is recorded here BEFORE the family is built.
CLAUDE.md section 4 requires this check going forward; see that file for the
rule text.

Fields: family key, the inputs the check was run with, the resulting power at
the deciding tier, and whether the entry is retrospective (the family was
already built before this module existed) or prospective (checked before any
build).

---

## 1. `letf_rebalancing_eod` -- RETROSPECTIVE

This family was built and DECLINED on 2026-09-11 (module-level mechanism gate
failure, per its scorecard); this pre-check module (`sourcing_power_check.py`)
did not exist until this task. It is entered here to show what the check
would have said, using the family's OWN pre-registered power block
(`data/research_runs/letf_rebalancing_2026-09-11/power_block.json`), which had
already done this exact calculation by hand before any strategy return was
computed (POWER_BLOCK.md, PREREGISTRATION section 4.3).

- Inputs: `claimed_sharpe_annualized=0.41468259575966804` (the 50%-of-Tuzun
  arm -- Ivanov & Lenkey's own measured flow-offset strength, the deciding
  arm the pre-registration named in advance), `periods_per_year=
  248.75109762396693`, `years_of_data=2637/248.75109762396693=10.601008...`,
  `n_local=20`, `bar=0.95`, `offset_fractions=(1.0,)`.
- Ladder read live: `[20, 43, 397, 1131]`.
- `sigma_sr_annualized` (this module's formula, `sqrt(periods_per_year /
  n_observations)`): `0.30713367617589954` -- IDENTICAL to the family's own
  declared value, because both use the same precedent formula.
- **power at n_local = 20: 0.014014885044634329** -- an EXACT bit-for-bit
  match to the family's own recorded `power_at_claimed_sharpe` for this arm
  (power_block.json, `arms.half_tuzun.sigma_sr_declared__bar_0.95`).
- Verdict: `DECLINE_AT_SOURCING` (0.014 << 0.80).
- Independently re-run via the CLI for this ledger:
  `python data/research_runs/sourcing_power_check.py --claimed-sharpe
  0.41468259575966804 --periods-per-year 248.75109762396693 --years-of-data
  10.601008872025316 --n-local 20 --bar 0.95 --offset-fractions 1.0`

## 2. `intraday_momentum_spy` -- RETROSPECTIVE

Built and DECLINED on 2026-09-09 for a different reason (the paper's r1
predictor has the wrong sign out of sample -- see project memory
`project_intraday_momentum_spy_2026-09-09.md`), so this check's verdict does
not change any outcome. Entered here because the task asked for the retro
check to be run and recorded.

- Inputs: `claimed_sharpe_annualized=1.08` (Gao, Han, Li & Zhou's own claim,
  as recorded in the family's `run_output.json` `power["0.95"].
  claimed_sharpe_annualized`), `periods_per_year=252` (the family's own
  preservation-block convention), `years_of_data=2660/252=10.555555...`
  (`sample.n_trading_days` from `run_output.json`), `n_local=8`, `bar=0.95`,
  `offset_fractions=(1.0, 0.5)`.
- Ladder read live TODAY: `[8, 43, 397, 1131]`. The family's OWN
  `run_output.json` (written 2026-09-09) recorded `[8, 37, 362, 1031]` --
  the pooled rungs (37/362/1031 -> 43/397/1131) moved between then and now.
  This module always reads the current ladder, so this entry uses the
  current one; it is not a discrepancy in this module.
- `sigma_sr_annualized` (this module's pre-build formula): `0.30779350562554625`.
  **This is NOT the family's realized sigma_SR** (`0.5740485047348345`,
  `RUN_REPORT.txt` line 212, computed AFTER the 8 specs were built and
  scored) -- sourcing time has no realized moments to use, so this module's
  proxy and the family's post-hoc realized value are expected to differ, and
  do (documented in `tests/test_sourcing_power_check.py`'s intraday
  regression test).
- Power at n_local=8: 0.6564 at fraction 1.0 (claimed 1.08), 0.0884 at
  fraction 0.5 (claimed 0.54). For comparison, the family's own realized-
  sigma_SR run reported power 0.1951 at bar 0.95 for the full claim
  (`run_output.json` `power["0.95"].power_at_claimed_sharpe`) -- a different
  number from this module's 0.6564 at the same fraction, precisely because
  the sigma_SR inputs differ as described above.
- **Deciding tier: smallest fraction (0.5) at n_local (8) = 0.08841180215148192.**
- Verdict: `DECLINE_AT_SOURCING` (0.0884 << 0.80).
- Independently re-run via the CLI for this ledger:
  `python data/research_runs/sourcing_power_check.py --claimed-sharpe 1.08
  --periods-per-year 252 --years-of-data 10.555555555555555 --n-local 8
  --bar 0.95 --offset-fractions 1.0 0.5`
