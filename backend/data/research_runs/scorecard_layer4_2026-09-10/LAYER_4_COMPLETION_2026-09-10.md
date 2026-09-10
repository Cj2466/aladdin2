# The four live scorecards completed — layer 4, power, verdict, decision (2026-09-10)

Follows `scorecard_drafts_2026-09-10/LAYER_2_REVIEW_2026-09-10.md`. The four cards now
sit in `data/research_runs/scorecards/` and pass the validator; the completeness test's
list drops from 55 to **48** — four cards, but three of them cover two family keys each (`covers_family_keys`: the trial-results key and the registration key), so seven keys close. Every number on them is measured and persisted; this memo records
where, and the one thing the measuring found.

## 1. Verdicts, against the validated-edge bar (0.95)

| family | DSR at n_local | power at the paper's own effect | verdict | decision |
|---|---|---|---|---|
| quality_cbop | 0.8174 (n=9) | 0.962 (BGLN Table 4 decile, t = 8.5 → SR 1.20) | **definite_negative** | REGISTERED (observational) |
| short_interest_ratio | 0.7962 (n=12) | not stated — no honest claimed effect exists | **definite_negative** | REGISTERED (observational) |
| lazy_prices_jaccard_full | 0.7540 (n=36) | 0.39 (CMN value-weighted, t = 3.59 → SR 0.80) | **underpowered** | REGISTERED (observational) |
| cross_sectional_crypto | 0.3553 (n=28) | 0.011 (FP U.S. BAB Sharpe 0.78) | **underpowered** | REGISTERED (observational) |

Two families (cbop, crypto) never pre-declared a numeric bar; their registration files use the
0.50 screening floor as a *selection* criterion. Judging against 0.50 would read as passing a
floor, so all four cards judge against 0.95 and record the 0.50 standing in the rationale
(cbop clears it at every rung; crypto fails it at every rung).

The power block is scored exactly as the validator recomputes it — `dsr_power_report` with its
default skewness 0 / kurtosis 3 — and says so on each card. The claimed effects are the papers'
own reported statistics, gross and on their own universes, used deliberately as generous upper
bounds; none comes from a pre-registration, because none of the four pre-registrations states
an expected Sharpe.

## 2. Cost scenarios — where each number comes from

* **lazy_prices**: the nine-run ladder already persisted on 2026-09-05 (`edge_cost_correction_*`,
  `cost_basis_switch_*`): 0.7456 with the calibrated spread and no borrow → 0.5251 with the
  measured borrow that is the live config → −0.2376 at the hard-to-borrow ceiling.
* **short_interest**: the financing ladder of `short_interest_borrow_composition_2026-09-05.txt`
  on the pinned snapshot: 0.4161 → 0.3233 at the measured 44.77 bp/yr (live config) → −0.0298 at
  the long_short-book rate, which is the wrong book and shown as the ceiling.
* **quality_cbop** and **crypto**: measured today by `run_cost_scenarios.py` — the whole grid
  re-screened per arm with one config field changed, rows persisted under
  `scorecard_cost_scenarios_2026-09-10_*`. Crypto's same-day baseline reproduces the canonical
  row exactly; its range is 0.9540 (15 bp) / 0.9438 (30 bp) / 0.9232 (60 bp) / 1.0544 (no borrow).
  cbop's is read against a same-day baseline of 0.4538 — see §4.

## 3. Capacity and regime coverage

Capacity = median trailing daily dollar volume × 1% participation × names per leg, from the
shared price store to 2026-09-08: cbop $23.1M (its own 164-name sample), short_interest $73.0M,
lazy_prices $306.0M, crypto **$2.0M** (alts ex-BTC/ETH, the coins a quintile leg is actually made
of). All informational; no capital is deployed. Regime coverage by the validator's own rule: the
three equity families see COVID and the 2022 rate-hike bear and miss the GFC and dot-com; crypto's
window starts after COVID and sees only 2022.

## 4. What the measuring found: quality_cbop's backward numbers no longer reproduce

Re-screening the family today with the canonical config gives cbop_ls_h63 **+0.4538** against the
registered **+0.4565** (−0.0027) — and siblings move far more: cbop_ls_h126 −0.063, cbop_ls_h252
−0.075, the quintile variants to −0.090. The 2026-09-04 rerun still matched the canonical to
3e-4, so the inputs moved after 09-04.

Excluded first: the seeded 200-ticker sample is identical (union still 768); the APH/MNST/RUSHA
repair is not it (their adjusted series carry no fabricated day, and the canonical run predates
the store and used correct prices).

Then two controlled replays, both persisted (`run_dated_fundamentals_replay.py`,
`run_price_path_replay.py`):

| arm | vs canonical (max \|Δ\|) | what it shows |
|---|---|---|
| fundamentals as-of 2026-09-10 (fact store rebuild) | 0.0900 | = today's baseline to 0.000000: the rebuilt document shape is neutral |
| fundamentals as-of 2026-08-28 | **0.0490** | restores cbop_ls_h252 **exactly** and most of the long-hold movement — the 2026-09-09 document refresh is that part |
| as-of 08-28 + YAHOO convention | 0.0491 | the dividend-convention change is 0.0003 — not it |
| as-of 08-28 + throw-away store fetched fresh from the vendor | 0.0498 | = shared store to 0.0009 — the store equals the vendor today |

What remains — −0.027 / −0.040 on the three hedged specs, −0.017 on the registered spec — lies in
inputs for which **no 2026-08-28 snapshot exists anywhere** (both older worktree caches carry the
09-10 refresh): vendor data between 08-28 and the 09-04 store freeze, or companyfacts content that
left the documents before their 09-09 version. It cannot be separated further. That is precisely
the defect class the point-in-time stores now prevent going forward and could not undo backward.

Consequence, on the card and in the module's new section 7: the registered spec is barely
affected and the registration is untouched (a formation re-run remains the owner's call, rule 6);
every cost comparison for this family must be read against a same-day baseline, never against the
canonical row.

## 5. Also in this branch

* Five dated, pure-append corrections in the modules the layer-2 review found wanting
  (`bab_forward_registration.py` docstring **and** its persisted-rationale constant — the live row
  is not rewritten; `cross_sectional_crypto.py`; `quality_forward_registration.py` section K;
  `cross_sectional_lazy_prices.py`; `cross_sectional_quality.py` section 7). Proven comment-only
  by comparing docstring-stripped ASTs against main; the three pinned modules acknowledged in the
  dependency manifest in full form and re-pinned.
* `preservation_score` for crypto, measured from a replay that reproduces the persisted row to
  0.0 (`run_crypto_preservation_score.py`): 0.1505 / 0.1661.

## 6. Not done here

The waiver mechanism for the remaining 48 (option B of `SCORECARD_GAP_DECISION_2026-09-10.md`)
is a separate branch. No live registration's status, formation or realized result changed.
