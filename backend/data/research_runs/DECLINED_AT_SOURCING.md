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

## 3. crypto perpetual-futures basis (He, Manela, Ross & von Wachter, arXiv:2212.06888v6) -- PROSPECTIVE

Checked 2026-09-11 by the orchestrator BEFORE any build, as the rule requires; the first
prospective entry. Full record: `data/research_runs/perp_basis_sourcing_2026-09-11/`
(`FEASIBILITY_AND_SOURCING_2026-09-11.md`, `sourcing_power_perp_basis.py`, JSON output).

- Claimed effects: the paper's own Table 6 High-tier ("typically an individual trader", MAKER
  fees) annualized Sharpe ratios BTC 1.80 / ETH 2.55 / BNB 4.84 / DOGE 3.58 / ADA 2.68, used as-is
  (the paper's Lucca-Moench annualization equals the calendar-time Sharpe with zeros when flat --
  derivation in the memo). Conservative declared claim: the paper's own Table 7 per-year Sharpe
  for 2022-2023, the regime the authors call a structural break (BTC 0.69, ETH 0.98, BNB 0.74,
  DOGE 0.76, ADA 0.88).
- Inputs: `periods_per_year=365`, `n_local=16` (declared), `bar=0.95`, `sigma_SR=sqrt(365/n)`,
  windows 7.0 y (2019-09 -> 2026-09) and 2.5 y out-of-sample only (2024-03 -> 2026-09).
- Power at the conservative claim, n_local: 7.0 y -> BTC 0.052, ETH 0.200, BNB 0.070, DOGE 0.076,
  ADA 0.132; 2.5 y OOS -> 0.009-0.029. Power at the full in-sample claim on the OOS window alone:
  BTC 0.273, ETH 0.718, ADA 0.782 (BNB/DOGE > 0.95).
- Verdict: **DECLINE_AT_SOURCING** as a signal test. A build could only replicate the paper's
  published in-sample years; the edge itself (post-break) is not certifiable at this project's bar.
- Reopen condition: a descriptive measurement of the hourly deviation series showing the
  post-2024 opportunity is back at a magnitude whose implied Sharpe clears the pre-check.

### Entry 3 — CORRECTION (appended 2026-09-11, after the Fable adversarial review)

The "conservative claim" numbers in entry 3 were Table 8 (long-spot-only), mislabeled as
Table 7; see `perp_basis_sourcing_2026-09-11/FEASIBILITY_AND_SOURCING_2026-09-11.md`
CORRECTION 01 and `ADVERSARIAL_REVIEW_2026-09-11.md`. Corrected Table 7 2022–23 mean Sharpe:
BTC 1.01, ETH 1.46, BNB 2.90, DOGE 1.17, ADA 1.73. Corrected power at that claim — 7.0 y:
0.219 / 0.666 / 1.000 / 0.363 / 0.867, pool 0.936; 2.5 y out-of-sample only: 0.032 / 0.128 /
0.868 / 0.055 / 0.235, pool 0.315. **Verdict unchanged: DECLINE_AT_SOURCING**, decided on the
out-of-sample window (only BNB clears; the pool does not) and on Table 7's implied 2–10 trades
per year per coin. The reopen condition stands.
