# Audit of this project's candidate-selection criteria — 2026-09-09

**Question asked by the project owner**: are the rules we use to accept/reject
candidates actually appropriate? Could they be discarding real, profitable
edges? Could a small mechanical detail in any one rule be producing wrong
decisions? Then: attack the conclusions adversarially and confirm what survives.

**Method**: every gate was read from the code that enforces it (not from memory
or docs), and every quantitative claim below was produced by running the
project's OWN functions (`deflated_sharpe.probabilistic_sharpe_ratio`,
`expected_max_sharpe_under_noise`) or a Monte Carlo of the rule exactly as
coded. Scripts and the CSV are in this directory. No formula was re-typed.
Normal returns are assumed where an inversion needed a distribution; the
fat-tail check in `underperf_mc_fattail.py` shows the headline finding does
not depend on that.

Files read: `deflated_sharpe.py`, `dsr_policy_n.py` (+ `.json`),
`preservation_score.py`, `metrics.py`, `forward_validation_service.py`,
`registration_scorecard.py` (policy_d_verdict, Layer 1-4),
`cross_sectional.py` (sigma_sr, DEFAULT_XS_COST_BPS),
`cross_sectional_forward_validation_runner.py` (drift + underperformance),
`forward_validation_runner.py`, `borrow_cost.py`, `autonomous_research_runner.py`,
`templates/REGISTRATION_SCORECARD_TEMPLATE.md`. DB: 3,017 rows of
`cross_sectional_trial_results` across 52 family keys.

---

## 0. Executive summary

1. **The 0.95 DSR bar is not wrong — but with ~11.6 years of daily data it can
   only detect true annual Sharpe ratios of roughly 0.65–1.2 (equity families)
   and 0.9–1.7 (short-sample / high-dispersion families).** Post-publication
   anomalies in the literature (McLean & Pontiff 2016: −58%) sit around
   0.3–0.5. So the class of edge this project says it is hunting ("many small,
   independent micro-edges") is **undetectable by construction** at this bar
   with this sample — by our gate AND by the literature's own hurdle (Harvey,
   Liu & Zhu 2016's t>3.0 implies Sharpe ≈ 0.88 at 11.6 years). The error is
   not the bar; it is calling a sub-threshold result **DEFINITE_NEGATIVE** and
   forbidding re-attempts. That label is where real edges get thrown away.

2. **The forward-validation "underperforming" kill-switch is a latent,
   near-random destroyer of registrations.** As coded (trailing 60 realized
   days, annualized Sharpe ≤ −0.5, permanent, stops ticking), a strategy with
   TRUE Sharpe 1.0 is permanently killed with probability 0.66 inside its own
   126-day graduation window and 0.92 within a year; a true-Sharpe-0.5
   strategy: 0.76 / 0.97. A ZERO-edge strategy: 0.84 / 0.99. The rule has
   essentially no discriminating power (0.966 vs 0.988 at one year), and no
   threshold fixes it — at −4.0 it still kills 24% of real SR-0.5 strategies
   while passing 63% of null ones. **It has never fired only because no
   registration has reached 60 realized days yet** (BNY/ROL/STT/PRU are at 9,
   MET at 7, all cross-sectional rows at 0). This must be changed before any
   row reaches day 60 (~10 trading weeks for the momentum rows).

3. Everything else is either sound, secondary/informational, or a
   labelling/consistency issue rather than a mechanical error (details §2).

---

## 1. What the gate actually is (as coded)

| Stage | Rule (as coded) | Where |
|---|---|---|
| Pre-registration bar | best spec: `sharpe > 0 AND DSR >= 0.95` at `n_local` | family `*_PREREGISTRATION.txt`; `policy_d_verdict` |
| DSR | `PSR(SR_hat, SR0)`; `SR0 = sigma_SR·[(1−γ)Φ⁻¹(1−1/N) + γΦ⁻¹(1−1/(Ne))]`; PSR uses `sqrt(n_obs−1)`, sample skew/kurt | `deflated_sharpe.py` (Bailey & López de Prado 2014) |
| sigma_SR | `std(ddof=1)` of the family's own specs' annualized Sharpes | `cross_sectional.py:1979` |
| N ladder | `{n_local, 37, 362, 1031}`; DEFINITE_NEGATIVE if fails at `n_local`; PASS only at 1031; else UNRESOLVED | `dsr_policy_n.py`, `policy_d_verdict` |
| DSR unmeasurable | `n_trials < 5` or degenerate series → `None` → counts as failing | `MIN_TRIALS_FOR_DSR`, `policy_d_verdict` |
| Screening floor | `DSR >= 0.50` at `n_local` = "worth a forward slot, never proof" | `short_interest_forward_registration.py` etc. |
| preservation_score | mandatory to REPORT; not used in `computed_verdict` | `registration_scorecard.py` |
| Costs | 5 bps one-way per unit notional traded (flat) or EDGE spread; borrow 0 for most equity families, 44.77/48.16 bps for short_interest/lazy_prices | `DEFAULT_XS_COST_BPS`, `borrow_cost.py` |
| Forward graduation | `max(126 days, 2 complete holds)` realized days → "forward_validated" (data-sufficiency, not a pass) | `cross_sectional_forward_validation_service.py` |
| Forward kill-switch | trailing 60 realized days, annualized Sharpe ≤ −0.5 → "underperforming", permanent, stops ticking | `forward_validation_service.check_underperformance`; both runners |
| Spec drift | any change to spec/config fingerprint parks the row and a new row starts at 0 | both services |
| Momentum/pairs auto-registrations | NO gate at all ("forward-validation itself is the honest test") | `autonomous_research_runner.py:296-330` |

---

## 2. Findings

### F1 — Minimum detectable Sharpe at the 0.95 bar (the central number)

Inverting the project's own PSR/SR0 with each family's actual `n_obs`,
`n_trials` and `sigma_SR` (`family_power.py`, `family_power.csv`; normal
returns; monthly families in `monthly_req.py`):

| family (long daily sample) | n_obs | N | σ_SR | best Sharpe | best DSR | **min Sharpe @0.95** | min Sharpe @0.50 |
|---|---|---|---|---|---|---|---|
| quality_cbop | 2926 | 9 | 0.125 | 0.457 | 0.817 | **0.673** | 0.190 |
| quality_noa (passed) | 2926 | 9 | 0.077 | 0.659 | 0.968 | 0.600 | 0.117 |
| short_interest | 2169 | 12 | 0.197 | 0.774 | 0.948 | **0.889** | 0.328 |
| lazy_prices | 2926 | 36 | 0.187 | 0.603 | 0.754 | **0.885** | 0.402 |
| best_ideas_13f | 2890 | 36 | 0.172 | 0.672 | 0.845 | 0.855 | 0.368 |
| rebalancing_pressure | 5810 | 24 | 0.210 | 0.566 | 0.801 | 0.759 | 0.417 |
| funding_carry | 2157 | 12 | 0.298 | 0.872 | 0.827 | 1.059 | 0.496 |
| commodities | 2456 | 24 | 0.332 | 0.905 | 0.773 | 1.184 | 0.657 |
| crypto | 2128 | 28 | 0.515 | 0.944 | 0.355 | **1.736** | 1.053 |
| asset_growth | 2928 | 12 | 0.093 | 0.293 | 0.680 | 0.638 | 0.156 |
| residual_momentum | 2929 | 18 | 0.123 | 0.326 | 0.630 | 0.711 | 0.228 |
| tax_loss_selling | 2932 | 32 | 0.233 | 0.526 | 0.554 | 0.971 | 0.489 |
| quarter_end_marking | 2932 | 36 | 0.462 | 0.437 | 0.010 | 1.476 | 0.993 |
| **monthly-observation families** | | | | | | | |
| dumb_money (70 mo) | 70 | 24 | 0.479 | 0.482 | 0.227 | 1.67 | 0.95 |
| margin_credit (201 mo) | 201 | 24 | 0.520 | 0.977 | 0.451 | 1.45 | 1.03 |
| inelastic_markets (92 mo) | 92 | 24 | 0.126 | −0.076 | 0.064 | 0.86 | 0.25 |

Years of daily data a TRUE-Sharpe-S strategy needs to pass 0.95 **in
expectation** (`years_needed.py`, σ_SR = 0.20):

| true Sharpe | N=12 | N=36 | N=1031 |
|---|---|---|---|
| 0.5 | 98 y | never (<200 y) | never |
| 0.6 | 38 y | 94 y | never |
| 0.8 | 13 y | 20 y | 125 y |
| 1.0 | 7 y | 9 y | 23 y |
| 1.5 | 2 y | 3 y | 4 y |

At the 0.50 floor every S ≥ 0.4 passes within 1 year at N=12.

**Reading**: with the sample lengths this project has, a DEFINITE_NEGATIVE at
0.95 says "true Sharpe is probably below ~0.7–0.9", not "there is no edge". A
true 0.5-Sharpe edge — exactly the size the goal statement targets — would be
labelled DEFINITE_NEGATIVE with near certainty. Ten families sit in the
`0.50 ≤ DSR < 0.95` band (asset_growth 0.680, residual_momentum 0.630,
best_ideas_13f 0.845, funding_carry 0.827, commodities 0.773,
rebalancing_pressure 0.801, buyback 0.587, tax_loss_selling 0.554/0.555,
lazy_prices 0.754, quality_cbop 0.817, short_interest 0.948); only four of
them hold forward slots. The floor is applied inconsistently.

### F2 — The forward "underperforming" kill-switch (`underperf_mc.py`)

P(at least one permanent flag) for the rule exactly as coded:

| true Sharpe | within 126 d | within 252 d | within 504 d |
|---|---|---|---|
| 0.0 | 0.840 | 0.986 | 1.000 |
| 0.5 | 0.758 | 0.966 | 0.999 |
| 1.0 | 0.658 | 0.920 | 0.996 |
| 2.0 | 0.426 | 0.738 | 0.947 |

Student-t(4) returns: 0.749/0.964 (S=0.5), 0.645/0.912 (S=1.0) — same picture.
Lowering the threshold does not rescue it: at −4.0, P(kill | S=0.5, 1 y) =
0.24 and P(kill | S=0, 1 y) = 0.37 — the rule still cannot tell a real edge
from noise, because a 60-day annualized Sharpe has a standard error of ≈2.0.
The service's own docstring says the threshold is "NOT independently
empirically calibrated against a null distribution" — this is that
calibration, and it fails. The flag is permanent by design ("never
auto-reversible") and removes the row from `ACTIVE_STATUSES`, so evidence
stops accumulating at the exact moment a noisy window happens.

### F3 — sigma_SR is a hidden lever set by grid design

`SR0 ∝ sigma_SR`, and sigma_SR is the dispersion of the family's OWN specs.
A grid that deliberately includes weak/placebo/control variants or pools two
universes inflates sigma_SR and therefore SR0. Crypto: σ=0.515 → SR0(N=28)
≈ 1.0 annualized, so a 0.944 Sharpe scores DSR 0.355; small-cap quarter-end
σ=0.761 → min Sharpe 2.28. margin_credit's best DSR belonged to a CONTROL
spec — controls are inside N and inside sigma. Per Bailey & López de Prado the
variance across *trials* is the right input, but a control arm is not a
candidate strategy. Direction: false negatives for families with
heterogeneous grids; a family that pre-registers 5 near-identical variants gets
an easier bar than one that pre-registers 36 diverse ones.

### F4 — Pooled rungs mix the family's sigma with a pooled N

`dsr_across_denominators` passes the family's own σ_SR with N=37/362/1031.
Bailey & López de Prado's SR0 uses the variance across THOSE N trials; the
pooled dispersion is larger than a single family's, so SR0 at the top rungs
is understated. Direction: **lenient** at the PASS tier only (never affects
DEFINITE_NEGATIVE, which is decided at n_local with a consistent pair). Low
priority, but a genuine inconsistency to fix or document.

### F5 — Short-sample families are structurally untestable at 0.95

Timing overlays and monthly-flow families have 65–201 observations. Their
minimum detectable Sharpe at 0.95 is 0.86–1.67. A negative there is "sample
too short", never "mechanism refuted". The verdict vocabulary cannot say that.

### F6 — Verdict semantics and the "do not re-attempt" rule

CLAUDE.md §4: "Don't retroactively re-apply a newly-stricter rule to
already-declined candidates". Combined with the DEFINITE_NEGATIVE label, this
freezes F1's undetectable edges out forever. The label is doing work the
statistics do not support.

### F7 — Forward validation at 126 days is weak evidence on its own

A 126-day Sharpe has SE ≈ 1.41; it cannot separate 0.5 from 0. The forward
record is only informative if it is treated as *more observations of the
same pre-registered strategy* (appended to the backtest series in the same
PSR, with N unchanged because the strategy was fixed in advance) — not as a
separate 126-day pass/fail.

### F8 — Costs are not a false-negative driver

5 bps one-way flat is realistic-to-slightly-conservative for S&P 500 names;
borrow is 0 for every equity family except two (lenient, and already logged
as an open paid-data gap). Several memos already report zero-cost DSR
(quarter_end_marking fails even at zero cost). No change recommended.

### F9 — preservation_score

Mandatory to report, not part of the verdict. Its stability term zeros any
spec that lost money in either half — harsh, but as an informational
secondary it is fine. Keep informational; never promote to a gate.

### F10 — `n_trials < 5` → DSR None → "fails"

`ofi_crypto` and `patterns_d2` (4 specs) got no DSR and are treated as not
clearing. "Unmeasurable" and "negative" are different states.

### F11 — Momentum/pairs auto-registrations have no entry gate at all

By design. Combined with F2 they will be killed at random after day 60.

---

## 3. Recommendations (nothing here changes any live row; all need owner sign-off)

**R1 (urgent, before any row reaches 60 realized days). Replace the
underperformance kill-switch.** Options, in order of preference:
(a) make it advisory — set a flag/annotation, keep ticking, never change
status; (b) if an automatic stop is wanted, use a rule with a stated
false-kill rate calibrated by simulation on the *full* record (e.g. cumulative
PSR-vs-zero of the whole forward series below X after at least Y days), not a
60-day window. Either way, remove the permanence: a status the data can only
move one way is not a measurement.

**R2. Rename the verdict tiers to what the numbers mean.** Keep the 0.95 and
0.50 bars unchanged, but:
- `DEFINITE_NEGATIVE` only when best DSR < 0.50 at n_local, or Sharpe ≤ 0, or a
  pre-registered mechanism/placebo check fails;
- `UNDERPOWERED` (new) when 0.50 ≤ DSR < 0.95 at n_local — eligible for a
  forward slot by rule, not by ad-hoc choice;
- `UNRESOLVED_AT_POOLED_N` and `PASS` as today.
The "do not re-attempt" rule then applies to DEFINITE_NEGATIVE only.

**R3. Report power, always.** Every scorecard gets two new numbers computed
from its own n_obs/N/σ_SR: minimum detectable Sharpe at 0.95 and at 0.50, and
years-to-pass at the realized Sharpe. This is what turns "0.948 vs 0.95" and
"0.010 vs 0.95" into different statements.

**R4. Exclude declared control/placebo arms from N and σ_SR.** They are not
candidate strategies. Pre-registrations must label them; the family loader
counts only candidates. (Direction: slightly easier bar, principled.)

**R5. Treat forward days as continuation of the pre-registered series.** DSR
recomputed on backtest + forward realized returns, N unchanged. Graduation at
126 days stays a data-sufficiency milestone.

**R6 (document, don't build). Portfolio-level admission** is NOT
recommended: adding low-correlation noise raises in-sample portfolio Sharpe
mechanically (variance reduction around a zero mean) and there is no
portfolio-level multiple-testing correction in this codebase. Revisit only
with such a correction.

**R7. Fix or document F4** (pooled σ_SR for pooled N). Low priority.

**The decision the owner has to make, stated plainly**: with ~11.6 years of
data, no honest single-strategy test — ours or the literature's — can certify
a 0.4–0.6 Sharpe edge at 95%. Either (i) the project accepts that only
Sharpe ≳ 0.8 edges are individually certifiable and lets the 0.50 tier be the
working set it tracks (R2/R5), or (ii) it needs a different decision framework
for small edges, which does not yet exist here and carries its own
false-positive trap (R6). This audit recommends (i) now.

---

## 4. Adversarial pass on the findings above

**A1. "The 0.95 bar is too strict — lower it."** Rejected. HLZ (2016) t>3.0 at
11.6 years ⇒ Sharpe ≈ 0.88, the same neighbourhood as our minimum detectable
Sharpe. The bar is literature-standard. Lowering it would manufacture
positives; the fix is the *label* (R2), not the number.

**A2. "F2 is an artefact of iid-normal returns."** Tested: Student-t(4) gives
the same probabilities. Vol clustering in real returns produces longer runs of
bad 60-day windows, which makes the flag *more* likely, not less. The
one-window analytic (P ≈ 0.31 for S=0.5) agrees with the simulation's
magnitude. Survives.

**A3. "F2 never fired, so it is harmless."** It never fired because no row has
60 realized days. Rows are at 0–10. That is a countdown, not evidence.

**A4. "The 0.50 floor already handles F1/F6, so nothing is broken."** Partly.
The floor exists and was applied to 4 families; at least 7 others in the same
band were declined. A rule applied by recollection is the exact failure
`REGISTRATION_SCORECARD_TEMPLATE.md` was written to stop. R2 makes it a rule.

**A5. "F3 (σ_SR) is the paper's own definition; leave it."** Agreed for
genuine search variants. Not agreed for arms pre-registered as controls or
placebos: those are pinned negatives by design and the paper's N is a count
of strategy trials. R4 is narrow on purpose.

**A6. "R5 (append forward days) is a look-ahead / selection risk."** Only if
the strategy or its parameters could change after seeing forward data. They
cannot: spec drift parks the row. N stays fixed because no new search
occurred. This is the textbook out-of-sample extension, and it is *weaker*
than a fresh test, not stronger — which is why R2 keeps forward-tracked rows
as UNDERPOWERED until the combined PSR clears the bar.

**A7. "Maybe the owner only wants big edges, so F1 is not a problem."**
Possible, and stated as the explicit decision in §3. If so, R2/R3 still
apply: a DEFINITE_NEGATIVE label on an undetectable edge is still wrong.

**A8. "Costs could be the real killer, not statistics."** Checked: borrow is
zero for most families (lenient) and flat 5 bps is realistic. Where a family
died at zero cost the memo says so. Not the driver.

**A9. "The audit re-derived nothing; it trusted the module."** The inversions
call the module's functions, but the module was itself verified against
Mertens (2002) at import-time constants and the rule Monte Carlos are
independent of it. The one number the conclusion rests on (F2) was
cross-checked analytically and under a second distribution.

**Residual uncertainty, stated**: (a) F1 tables assume normal returns; with the
negative skew typical of short legs the minimum detectable Sharpe is slightly
higher, not lower. (b) `n_obs` uses daily realized returns for strategies that
decide monthly/quarterly; the Sharpe standard error is still governed by daily
observations, so this is not a flaw, but effective information per decision is
low and the forward record will be slow. (c) I did not re-verify the
`dsr_policy_n.json` rungs themselves; they are outside this audit's question.

---

## 5. What was NOT done here
No registration's status was changed. No threshold was changed. No code path
was modified. Scripts in this directory are reproducible from the shared dev
DB and the module as of commit d1b7198.
