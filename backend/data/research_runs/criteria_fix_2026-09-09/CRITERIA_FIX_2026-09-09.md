# Criteria fix — 2026-09-09

**Owner's instruction (Thai, paraphrased):** "Use every means to make sure the
rules we use now will not throw away good things, or things that would have
worked." Follow-up to the criteria audit
(`../criteria_audit_2026-09-09/CRITERIA_AUDIT_2026-09-09.md`, merged `a3375db`),
whose two findings were that (F1) the 0.95 DSR bar cannot see small edges at
this project's sample lengths yet labels them DEFINITE_NEGATIVE, and (F2) the
forward-validation kill-switch is near-random and about to start firing.

**Design principle for everything below:** the system may never *permanently
discard* a candidate on evidence that cannot distinguish a real edge from
noise — and nothing may become *easier to pass*. False positives remain the
worst outcome (CLAUDE.md §1); this change only stops false *permanent
negatives* being manufactured by automation.

Branch `criteria-fix-2026-09-09`, worktree `.claude/worktrees/criteria-fix`.

---

## 1. What was uncertain in the audit, and is now closed

The audit named three residual uncertainties. Each was tested before building on it.

| # | audit's stated uncertainty | what was done | result |
|---|---|---|---|
| U1 | F2's Monte Carlo assumed i.i.d. returns (normal, Student-t) — real strategy returns may be autocorrelated | `underperf_mc_ar1.py`: the as-coded rule (trailing 60 realized days, annualized Sharpe ≤ −0.5, evaluated daily, first trip permanent) on AR(1) daily returns with the **true** annualized Sharpe held fixed, φ ∈ {−0.2, 0, 0.2, 0.4}, 4 000 paths each | **Robust, and in the worse direction.** P(kill a true-Sharpe-1.0 strategy within 126 d): 0.61 / 0.65 / 0.70 / 0.74 as φ rises; within 252 d: 0.88 / 0.92 / 0.94 / 0.96. Null strategy: 0.83–0.85 / 0.99 at every φ. Positive autocorrelation shrinks the effective sample inside the window and *raises* the false-kill rate. At no φ does the rule separate S = 1.0 from S = 0 by more than ~20 points at 126 d or ~8 at 252 d. |
| U2 | F1's power numbers were computed by ad-hoc scripts, not validated code | `app/services/research_lab/dsr_power.py` + 20 000-path synthetic validation (`validate_dsr_power_output.txt`) against the project's own `probabilistic_sharpe_ratio` / `expected_max_sharpe_under_noise` with sample skew/kurtosis, 8 cases incl. the null | Analytic power matches Monte Carlo in every case, worst \|z\| = 1.70; null pass rate 0.31% vs 0.32%. **Correction to the audit:** the audit's "0.65–1.2 required Sharpe" is the *observed* Sharpe at which power is 50%. At the standard **80% floor** the minimum detectable true Sharpe for a typical equity family (n = 2 926, N = 12, σ_SR = 0.19) is **1.05**, and a true 0.5 has **15%** power (needs ~183 years of daily data). The problem is larger than stated, not smaller. |
| U3 | `dsr_policy_n.json`'s rungs were used as given | re-counted the raw pool from the live DB | `cross_sectional_trial_results` now holds **1 131** distinct (family_key, trial_id) pairs vs the ladder's n_raw = 1 031 — exactly `STALENESS_THRESHOLD_NEW_TRIALS` (100) beyond it, so `DsrPolicyLadder.is_stale_against(1131)` is **True** as of today. Direction: a stale n_raw *under*-deflates at the top rung, i.e. the false-*positive* direction, not the one this fix is about. Re-measuring the ladder is its own run (`run_dsr_policy_n.py --stage all`) and would change the required rungs on every scorecard, so it is **flagged for the owner, not done here** (§6). |

A fourth check the audit did not list: the per-family sensitivity table was
regenerated from the live DB through the new validated module
(`family_min_detectable.py` → `family_min_detectable.csv`):

* 50 of 52 persisted families are scorable at the 0.95 bar (2 fall below `MIN_TRIALS_FOR_DSR`).
* Median minimum detectable true Sharpe at 80% power: **1.20**.
* Median power at a true Sharpe of 0.5: **0.10**.
* Families in which a true 0.5 had ≥ 80% power at 0.95: **0 of 50**.
* At the 0.50 screening floor: median minimum detectable 0.64, median power at 0.5 = 0.64.

So the honest answer to the owner's question is **yes**: at the 0.95 bar, every
negative verdict this project has recorded is, for an edge of the size its own
goal statement describes ("many small micro-edges"), a statement about sample
length rather than about the mechanism. Which of them hid a real edge cannot be
known from the data; that is exactly what "underpowered" means.

---

## 2. What was changed (code)

### 2a. The forward kill-switch is advisory — R1, the time-critical item

`check_underperformance` and its two constants are **unchanged** (pinned by the
existing regression tests). What changed is that **nothing acts on it**:

| file | change |
|---|---|
| `app/services/forward_validation_service.py` | new `UnderperformanceAdvisory` dataclass + `underperformance_advisory()`; a module block records the measured false-kill rates and why the rule is advisory; `check_underperformance` docstring updated, body untouched |
| `app/services/research_lab/forward_validation_runner.py` | the `status = "underperforming"; break` transition in `apply_forward_steps` removed; unused import removed; comments updated |
| `app/services/research_lab/cross_sectional_forward_validation_runner.py` | the same transition in `_process_registration` removed; unused import removed; comments updated |
| `app/services/research_lab/forward_validation_backfill.py` | the "replay stopped at the flag" note branch removed (dead) |
| `app/services/research_lab/engine.py`, `autonomous_research_runner.py`, `autonomous_tuning.py` | docstrings/comments that described the automatic park brought up to date |
| `app/schemas/forward_validation.py`, `app/schemas/cross_sectional_forward_validation.py` | `UnderperformanceAdvisoryOut`; `underperformance_advisory` field on both registration read models |
| `app/routers/forward_validation.py`, `app/routers/cross_sectional_forward_validation.py` | advisory computed at read time from the stored day results (realized days only and the family's own calendar on the cross-sectional path) |
| `frontend/src/api/client.ts`, `components/UnderperformanceAdvisoryBadge.tsx`, `ForwardValidationPanel.tsx`, `CrossSectionalForwardValidationPanel.tsx` | a small badge next to the status: "P(edge>0) NN% over Nd", prefixed "trailing window weak" when the retired rule would have fired |

The advisory carries two things: the old rule's own verdict (`trailing_flag`,
so a reader can see exactly when it *would* have fired) and a calibrated
companion, `whole_record_psr_vs_zero` — `probabilistic_sharpe_ratio` of the
entire realized record against a zero benchmark, per-period scale, with the
record's own skew/kurtosis, **no deflation** (a forward record is one
pre-registered test, not the best of a grid). It is a probability for a human
to read, deliberately not a rule.

The `"underperforming"` status value **stays in every vocabulary** (models,
schemas, frontend, `ACTIVE_STATUSES` exclusions, the research runner's
known-underperforming skip, the portfolio runner's pruning, the execution
allocation resolver's exclusion). All of that still works; it now fires only
when a human puts a row into that state — which is what CLAUDE.md rule 6
already required of every operational status change.

**Not touched, on purpose:** `app/services/execution/strategy_breaker.py`.
That is the *live-money* breaker (20-day window, −1.0, stops new orders only,
human-liftable in one click). It is reversible and bounds real losses; the
research kill-switch was irreversible and bounded nothing. Different job.

### 2b. An `underpowered` verdict tier — R2 + R3

| file | change |
|---|---|
| `app/services/research_lab/dsr_power.py` (new) | `required_observed_sharpe`, `power_to_pass`, `min_detectable_sharpe`, `years_to_detect`, `dsr_power_report`; `POWER_FLOOR = 0.80`. Inverts the project's PSR/SR0 functions numerically — **no expression retyped**; the SR_hat standard error is the same variance term `probabilistic_sharpe_ratio` already implements, evaluated at the hypothesised Sharpe. Validated against synthetic data with a known true Sharpe (§1 U2). |
| `app/services/research_lab/registration_scorecard.py` | `VERDICT_UNDERPOWERED`; `policy_d_verdict(..., power_at_claimed_sharpe=None)` returns it **only** when the local tier fails *and* power < 0.80 — it never upgrades a failure and never touches the `unresolved`/`pass` tiers; optional `power` block on Layer 1 whose four outputs are **recomputed on load** from its inputs and refused on disagreement (same discipline as the verdict); module docstring records the revision |
| `templates/REGISTRATION_SCORECARD_TEMPLATE.md` | verdict table row, a "Power" section, the `power` block in the JSON skeleton |
| `tests/test_dsr_power.py` (12), `tests/test_registration_scorecard_power.py` (11) | new; every pre-existing Policy D test in `test_registration_scorecards.py` is byte-for-byte unchanged and still passes |

Pre-2026-09-09 scorecards (one exists: `low_frequency_patterns`) have no
`power` block and parse exactly as before. **No closed family was relabelled**
— a retroactive relabel is the owner's call (§6).

---

## 3. Tests that were changed, each with the reason (nothing weakened silently)

| test | before | after | why |
|---|---|---|---|
| `test_forward_validation.py::test_flags_underperforming_after_bad_trailing_window` | asserted `status == "underperforming"` | asserts `status == "in_progress"`, one more day applied, and `underperformance_advisory(...).trailing_flag is True` with whole-record PSR < 0.5 | the transition is gone by design; the signal must still be visible |
| `test_cross_sectional_forward_validation.py::test_runner_flags_underperformance_on_the_familys_own_calendar` | asserted `status == "underperforming"` | asserts `status == "in_progress"` and the advisory flags on realized days with the family's calendar | same |
| `test_forward_validation_backfill.py::test_a_mid_gap_underperformance_flag_stops_the_replay` → `..._no_longer_stops_the_replay` | asserted 1 of 5 missed days recovered and the row parked | asserts all 5 recovered, row active, and a second tick applies nothing more | the replay-truncation only existed to mirror the park |
| `test_forward_validation_service.py` | — | +4 tests: advisory carries the old verdict unchanged; below-floor nulls; PSR is per-period (feeding the annualized Sharpe gives a different, wrong number); calendar handling | new behaviour |

Untouched and still passing: `test_underperforming_registration_stops_ticking`,
`test_backfill_skips_a_parked_underperforming_registration`,
`test_known_underperforming_candidate_is_skipped_and_backfilled`, the three
portfolio-runner pruning tests, `test_an_underperforming_registration_is_not_traded`,
`test_check_underperformance_*` (6), `test_check_underperformance_default_is_still_the_252_day_exchange_year`,
`test_strategy_breaker.py` — i.e. every consumer of a *human-set*
`"underperforming"` behaves as before.

Suite result on the final branch state: see §7.

---

## 4. Second adversarial pass — against this fix

| # | attack | verdict |
|---|---|---|
| A1 | *"You removed the only automatic protection; a broken registration now runs forever."* | Under paper tracking a running slot costs nothing and no capital is exposed; the pairs pool was never bounded by the kill-switch (registrations are created daily for the top-K regardless — 20 rows today, all in\_progress). The live-money breaker (`strategy_breaker.py`) is untouched. **Holds, with one honest gap:** R1 had two halves — "make advisory" *or* "replace with a calibrated whole-record test". Only the first is built. Before any capital is allocated on forward status, a retirement rule with a **pre-declared false-kill rate** must exist; today there is none, and that is deliberate — it should be designed with the owner, not improvised here. |
| A2 | *"Advisory means nobody reads it."* | The badge is on both dashboard panels and the number is on the API. Whether a human acts is a process question this code cannot answer; what the code guarantees is that the *wrong* actor (a 60-day coin flip) no longer acts. **Holds.** |
| A3 | *"The whole-record PSR is itself weak at 60–126 days and a human reading it daily has the same multiple-looks problem."* | True, and it is presented as a probability, not a verdict. A PSR of 0.30 says "30% that the true Sharpe is positive", which is the honest state of knowledge at that length; the old rule turned the same evidence into a permanent kill. **Holds; the residual is stated in the dataclass docstring.** |
| A4 | *"UNDERPOWERED is a loophole: pick a low claimed Sharpe and every failure becomes 'inconclusive'."* | The validator recomputes the power from the block's inputs, so the *arithmetic* cannot be fudged — but it **cannot verify that the claimed Sharpe came from the pre-registration** rather than being chosen after the result. That is a provenance check for the mechanism-fidelity reviewer, and the template says so in bold. **Partly holds; residual named.** Note the asymmetry: even a fudged claim only ever changes `definite_negative` → `underpowered`; it cannot manufacture a pass or a forward slot. |
| A5 | *"UNDERPOWERED changes nothing operationally — cosmetic."* | It changes one thing: the "never retry a DEFINITE\_NEGATIVE" convention does not apply. But the natural follow-up — re-run with a smaller grid to gain power — is p-hacking unless the smaller grid is pre-registered afresh and the earlier result is disclosed. The template does not yet say this; **added to §6 as a rule the owner should ratify.** |
| A6 | *"Power under normal returns flatters the test."* | Yes — fat tails widen the SR\_hat standard error and lower power; `test_fat_tails_lower_power_so_the_normal_case_is_an_upper_bound` pins the direction. A normal-case power is an *upper* bound, so "underpowered" under normal moments is underpowered a fortiori. **Holds in the safe direction.** |
| A7 | *"The rule change is retroactive."* | It is applied to live rows going forward only: no row's status, day results or fingerprint changed; `config_identity` hashes only config fields, so nothing here can drift a live registration (verified by reading `cross_sectional_forward_registry.config_identity`). CLAUDE.md's retro rule forbids re-applying a *stricter* rule to declined candidates; this is the opposite direction and was still not applied retroactively (§2b). **Holds.** |
| A8 | *"Zero of 50 families with 80% power at a true 0.5 — is that an artefact of the sigma\_SR estimate?"* | σ\_SR is the cross-spec dispersion the DSR machinery itself used; a smaller σ\_SR lowers SR0 and raises power, but even `quality_noa` (σ\_SR = 0.077, the smallest) needs an observed Sharpe of 0.60 and gives a true 0.5 only ~36% power (`family_min_detectable.csv`). The result is driven by **n** (≈ 11.6 years) far more than by σ\_SR. **Holds.** |
| A9 | *"You checked the UI only by type-check and build, not in a browser."* | Correct. `oxlint`, `tsc -b` and `vite build` pass; the response-model tests exercise the JSON shape; **the badge has not been looked at in a browser in this session**, and that is stated rather than claimed. |

---

## 5. What this does NOT do (stated, not glossed)

* It does **not** lower any bar. Nothing passes that did not pass before.
* It does **not** relabel any closed family (§6, owner's call).
* It does **not** build a calibrated forward retirement rule (A1).
* It does **not** implement R5 (treat forward days as a continuation of the
  pre-registered series with the same PSR and unchanged N) — a larger design
  that changes what "graduation" means and should be its own change.
* It does **not** implement R4 (exclude declared control/placebo arms from N and
  σ\_SR) — a per-family pre-registration convention; over-counting is in the
  conservative direction and can be adopted family-by-family going forward.
* It does **not** re-measure the DSR ladder (U3).

---

## 6. Decisions the owner is asked to make

1. **Ratify the advisory kill-switch** (this branch) — the one item with a
   clock on it. The closest registrations are at 11 realized days; the old rule
   could have fired from day 60.
2. **Retroactive relabel of closed families?** `family_min_detectable.csv` says
   a true Sharpe of 0.5 had < 80% power in **every** family at the 0.95 bar.
   Options: (a) leave history as is and apply `underpowered` only going
   forward; (b) add a `power` block to the one existing scorecard and to each
   future card for closed families as they are written. Recommendation: (a) now,
   (b) opportunistically — the labels are a record of what was decided at the
   time, and the CSV already tells the truth about sensitivity.
3. **A re-test rule for `underpowered` families:** any re-run with a smaller
   grid or longer sample must be pre-registered afresh and cite the earlier
   underpowered result. Recommendation: adopt, add to the template.
4. **Re-measure the DSR ladder** (`run_dsr_policy_n.py --stage all`): the raw
   pool is 1 131 vs 1 031, at the staleness threshold. Changes the rungs on
   every scorecard; conservative direction. Recommendation: schedule as its own
   verified change, not bundled.
5. **Design a calibrated forward retirement rule before any capital
   decision** (A1) — pre-declared false-kill rate on a true-Sharpe-1.0
   strategy, whole-record not trailing, with a minimum record length.

---

## 7. Verification record

* `tests/test_dsr_power.py` 12/12; `tests/test_registration_scorecard_power.py` 11/11;
  `tests/test_registration_scorecards.py` all pass except
  `test_every_family_has_a_scorecard`, which **fails identically on `main`**
  (the long-standing known failure: 52 families, 1 scorecard) — confirmed by
  running that single test in the main checkout before any change.
* Kill-switch consumers: `test_forward_validation_service.py`,
  `test_forward_validation.py`, `test_forward_validation_backfill.py`,
  `test_pairs_forward_validation_regression.py` → 53/53;
  `test_cross_sectional_forward_validation.py`, `test_autonomous_research_runner.py`,
  `test_autonomous_portfolio_runner.py`, `test_execution_runner.py`,
  `test_strategy_breaker.py` → 225/225.
* `ruff check` clean on every file this branch touches (the six `B008 Depends`
  hits in `routers/forward_validation.py` are pre-existing lines).
* Frontend: `oxlint` (3 pre-existing warnings in `LeaderboardTable.tsx`), `tsc -b`, `vite build` — all pass.
* `deflated_sharpe.py`, `preservation_score.py`, `metrics.py`, `dsr_policy_n.py` /
  `.json`: **unchanged** on this branch (`git diff main -- <file>` empty).
* Full suite on the branch (`pytest -q`, 11 min 54 s): **4 446 passed, 3 skipped, 2 failed.**
  The two failures: (1) `test_every_family_has_a_scorecard` — the pre-existing
  known failure, identical on `main`; (2) `test_live_registration_dependencies.py::test_no_live_registration_dependency_has_changed_unacknowledged`
  — the drift guard **correctly caught** that two shared-tick-path files
  (`cross_sectional_forward_validation_runner.py`, `engine.py`) changed under
  the live registrations. Handled in the order the guard prescribes:
  re-verified (runner: the only executable change is the removed status
  transition, which could not have fired — every live cross-sectional row has
  ≤ 1 realized day; engine: docstring-only, zero executable lines differ),
  appended two acknowledgement entries to
  `live_registration_dependencies.json` (old/new sha256, commit, what was
  re-run, what it showed), then re-pinned with
  `refresh_live_registration_dependencies.py`. That test file now passes 21/21.
  Net: the only failure remaining on the branch is the one that was already
  failing on `main` before this work began.
