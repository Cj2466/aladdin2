# REGISTRATION SCORECARD — the required record behind every family decision

One scorecard per family, committed to
`backend/data/research_runs/scorecards/<family_key>_SCORECARD.json`, validated
by `app/services/research_lab/registration_scorecard.py`, and enforced by
`backend/tests/test_registration_scorecards.py`, which FAILS when a family
that has persisted trial results — or holds a live forward registration — has
no scorecard.

This template is the human-facing spec. The JSON skeleton at the bottom is
the thing you copy.

---

## What this is, and what it is not

A `*_PREREGISTRATION.txt` is **binding prose written before a result exists**:
the hypothesis, the prior, the grid, the pass rule, and the reasoning behind
each. Nothing about it should become machine-readable — its value is that a
human argued the case in advance.

A scorecard is the opposite artifact. It is written **after** results exist and
it records **what the decision was actually made on**, in a fixed set of
fields, so that:

* absence is detectable (`which families have never had a capacity estimate?`
  is one grep, not thirty documents), and
* a field cannot be skipped because nobody remembered it.

A scorecard does not replace a pre-registration and cannot. If the family has
one, name it in `preregistration_path`; if it does not, say so there in words.

### Why this file exists at all

Two real failures, neither hypothetical:

1. `preservation_score.py` shipped 2026-09-03 and was then **skipped** for the
   two registration decisions that followed it (`asset_growth` and
   `residual_momentum`, both DECLINED on DSR and prose alone). It was applied
   only because the repo owner asked directly whether it had been. A metric
   applied when someone remembers is a decoration, not a gate. Layer 1 makes
   it a required field with no exception path.
2. No two families state the same *set* of things. Layers 2-4 fix the set.

---

## Layer 1 — the statistical layer

### Policy D: report DSR at several N, and read it in two tiers

Commit `f385fc5` wired `global_effective_n.dsr_n_trials()` into every family.
It returns `max(local grid size, pooled effective N)`, and the pooled estimate
currently returns ONC's own structural floor of **2** — `effective_n_clustering`
found no real cluster structure in the data (25 of 25 seeds returned k=2, mean
silhouette 0.235). So the wiring is **presently a no-op**: every family still
deflates against its own grid size.

Pretending the project knows one precise N would be false in either direction.
Policy D refuses to pick one and reports a ladder:

| N | what it is | where it comes from |
|---|---|---|
| `n_local` | the family's own pre-declared grid size | the family's `*_N_TRIALS` / `len(FAMILY)` |
| `37` | distinct economic mechanisms searched project-wide — a **robustness tier**, not an estimate of independent trials | `dsr_policy_n.json` → `ladder.n_mechanisms` |
| `362` | effective independent trials (Li & Ji 2005, extrapolated to the full pool) — **anti-conservative**, a lower bound | `dsr_policy_n.json` → `ladder.n_effective` |
| `1031` | every distinct `(family_key, trial_id)` pair persisted | `dsr_policy_n.json` → `ladder.n_raw` |

**Changed 2026-09-06.** The pooled rungs used to be `481` and `857`, read off
`global_effective_n.json`'s `n_specs_clustered` and `raw_pooled_distinct_trials`
— two PROVENANCE fields on a MEASUREMENT artifact that were never chosen as
denominators. See `dsr_policy_n.py` for what each rung is now measured from and
why ONC's `E[K]=2` degenerated.

The pooled numbers are **read from the artifact, never retyped** —
`registration_scorecard.required_pooled_denominators()` loads them, and the
validator refuses a scorecard missing any of them.

Because `dsr_n_trials` takes a `max()`, the DSR "at 362" for a family with
`n_local = 36` means `n_trials = 362`; for a family with `n_local = 900` it
would mean `n_trials = 900`, so the validator does not require a separate
entry when a pooled rung is at or below the local one.

**The two-tier rule:**

| verdict | condition | meaning |
|---|---|---|
| `definite_negative` | fails the bar at `n_local`, and the `power` block shows the test had ≥ 80% power at the claimed Sharpe | closed. Nothing above can rescue it. The test could have seen the claimed effect and did not. |
| `underpowered` | fails the bar at `n_local`, and the `power` block shows the test had < 80% power at the claimed Sharpe (`dsr_power.POWER_FLOOR`) | **inconclusive, not negative.** Not a pass, no forward slot by this label alone — but the "never retry a definite_negative" convention does not apply: a longer sample or a smaller grid may resolve it. Added 2026-09-09 after the criteria audit found the 0.95 bar cannot see a true Sharpe of 0.5 at this project's sample lengths (~15% power). |
| `unresolved` | passes at `n_local`, fails at a higher measured N | **not a pass.** Explicitly not eligible for live or capital-relevant status without more forward-validation evidence. |
| `pass` | clears the bar even at the highest measured N | a real pass. |

A scorecard **without** a `power` block can only be `definite_negative` in the
failing tier (pre-2026-09-09 cards). Every card written from 2026-09-09 on is
expected to carry one — see "Power" below.

**Why a handful of points is enough, not a sampled curve:** DSR = PSR(SR0(N)); SR0
is strictly increasing in N (`deflated_sharpe.expected_max_sharpe_under_noise`)
and PSR is strictly decreasing in its benchmark, so DSR is strictly decreasing
in N. The rungs bracket every N between them. There is no N in
`[n_local, 1031]` at which a `definite_negative` passes.

A DSR of `null` (the machinery could not produce one — below
`MIN_TRIALS_FOR_DSR`, or a degenerate return series) counts as **not clearing**
the bar. An unmeasurable deflation is not a passing one.

### The threshold is per-family and must be stated

This project has two standing bars and they are **not** interchangeable:

* **0.95** — the "VALIDATED EDGE" bar
  (`short_interest_PREREGISTRATION.txt` §5: *"the best spec's deflated Sharpe
  (DSR, n_trials = 12) clears 0.95"*).
* **0.50** — the forward-registration **screening floor, never proof**
  (same document, §8: *"DSR >= 0.5 as a screening floor, never as proof"*).

Put in `dsr_pass_threshold` the bar the family's own pre-registration
declared. The validator computes the verdict from your numbers and **refuses a
scorecard whose stated `verdict` disagrees with its own numbers.**

### Power — could this test have seen the effect it was looking for?

`dsr_power.py` (added 2026-09-09). Fill the `power` block from the
**pre-registration**, not from the result:

| field | what it is | where it comes from |
|---|---|---|
| `claimed_sharpe_annualized` | the effect size the source literature claims, **net of this project's cost model** where the paper reports gross | the pre-registration, written before the family ran |
| `claimed_sharpe_source` | where that number was read from | paper, table/section, and how it was converted to net |
| `sigma_sr_annualized` | the grid's cross-spec Sharpe dispersion the DSR machinery used | the run's `sigma_sr_annualized` (same value that fed SR0) |
| `periods_per_year` | the family's own calendar | 252, or 365 for crypto |
| `required_observed_sharpe` | the observed Sharpe the bar demands at `n_local` | `dsr_power.dsr_power_report(...)` |
| `power_at_claimed_sharpe` | P(clearing the bar \| the claim is exactly true) | same |
| `min_detectable_sharpe` | smallest true Sharpe detected with 80% probability | same |
| `years_to_detect_claimed` | years of data the same grid would need to reach 80% power at the claim | same (null if > 500) |

The four output fields are **recomputed on load** from the four input fields
plus the layer's `dsr_pass_threshold` / `n_local` / `n_observations`, and the
card is refused if they disagree — you cannot state a sensitivity without
stating the inputs that determine it. The block only ever changes a
`definite_negative` into `underpowered`; it never upgrades a failure to a pass
and never touches the `unresolved`/`pass` tiers.

**A claimed Sharpe chosen after the result is post hoc.** If the
pre-registration named none, say so in `claimed_sharpe_source` and use the
most conservative number the source supports; do not pick the one that makes
the verdict read the way you want.

### preservation_score — mandatory, no exceptions

`preservation_score.py`, unchanged, on the **best spec's own realized daily
net-return series**:

```
S   = sharpe_ratio(r)                     annualized net Sharpe
AR  = mean(r) * periods_per_year          annualized arithmetic net return
MDD = max_drawdown(cumprod(1 + r))        <= 0
C   = AR / max(|MDD|, 0.01)               Calmar, floored
RQ  = sign(S) * sqrt(|S| * |C|)           risk quality
stab= clip(min(S_h1, S_h2) / |S|, 0, 1)   stability
cred= clip(dsr, 0, 1)                     credibility
preservation_score         = 0.42 * cred * RQ * stab
preservation_score_no_stab = 0.42 * cred * RQ
```

`0.42 = 1 - 0.58` is McLean & Pontiff (2016) **post-publication** decay
(J. Finance 71(1), pp. 5-32, doi:10.1111/jofi.12365), not the 26%
pre-publication figure — see the module docstring for why.

Report **both** the full score and `_no_stab`, and say in
`preservation_inputs_note` **which `dsr` you fed as `cred`** (which N, from
which run tag) and `periods_per_year` (252 equities / 365 crypto). Feeding a
different N silently changes the score, so the input is part of the number.

---

## Layer 2 — mechanism fidelity

Every non-trivial construction choice gets an **exact locus in the source**:
paper, section, and equation or table number. `"Cohen & Frazzini (2008)"` is
not a locus; `"Cohen & Frazzini (2008) JF 63(4), §II.B, Eq. (2)"` is.

* `construction_choices` — one entry per choice, each with its `source_locus`.
  Non-trivial means: anything a reader could have done differently and gotten
  a different number.
* `deviations` — everything you did **differently from the source**, each with
  `reason`. An empty list is a legitimate and meaningful claim; it is not a
  free pass, and the independent reviewer is expected to check it.
* `source_text_obtained` — `true` only if the **full text** was actually in
  hand. `false` when only an abstract/second-hand replication was available
  (as in `short_interest_PREREGISTRATION.txt` §1, which could not obtain the
  JFE full text and labelled every methodological detail by strength of
  support). A `false` here is not a failure; an undisclosed `true` is.
* `independent_reviewer` + `..._signed_off_at` + `..._findings` — the sign-off
  is not "looks fine". Record **what the reviewer actually re-derived and what
  they found**, including nothing. `VERIFICATION_CHECKLIST.md` in this
  directory is the pass they should have run.

---

## Layer 3 — the regime-conditional claim

Does the **source literature** claim an unconditional effect, or one
conditional on a regime?

* `source_claim_type: "unconditional"` — then `not_applicable_reason` is
  required and the three conditional fields must be absent/null. The validator
  **refuses** an unconditional scorecard that also carries in-regime and
  out-of-regime DSRs: splitting an unconditional claim by regime after the
  fact is a post-hoc conditioning, which is exactly what this layer exists to
  make visible.
* `source_claim_type: "conditional"` — then you must give the
  `regime_definition_rule` in words, the date it was **pre-declared**
  (`regime_rule_pre_declared_at`, which must be a real date on which the rule
  was committed, not the date you wrote the scorecard), and DSR computed
  **separately** in-regime and out-of-regime.

`claim_evidence` carries the quote or citation establishing which of the two
the source actually claims. This is the field that stops "the paper says it's
conditional" being asserted after a conditional split happened to look better.

---

## Layer 4 — the economics

### `cost_scenarios` — a range, minimum two

A single cost number is an assumption. Each scenario needs a `name`, its
`one_way_bps`, its `source`, and the **best spec's net Sharpe under it**.

Sourced levels this repo already has, verified and usable (see
`data/research_runs/edge_cost_reaudit_corrected_PREREGISTRATION.txt` §2):

| level | one-way | source |
|---|---|---|
| S&P 500 equal-weighted best estimate | ~2.0 bp | Hagströmer, *Bias in the effective bid-ask spread*, JFE 2021, Table 1 |
| S&P 500 tight/optimistic | ~1.0 bp | Hagströmer 2021 Table 1 median stock; Nasdaq/Mackintosh 2024 cap-weighted |
| S&P 500 conservative | ~3.5 bp | above Hagströmer's 2015 p95 stock, covering vol-spike regimes |
| project-standard control | 5.0 bp | `DEFAULT_XS_COST_BPS`, kept so Sharpes stay comparable |
| tick floor (exact, not an estimate) | `50 / price_$` bp | $0.01 minimum tick |

If the family shorts, its short-borrow assumption belongs in a scenario too —
see `borrow_cost.py`. `financing_bps_per_year = 0.0` is a **disclosed
optimism**, not an estimate, and a scorecard that uses it must say so in the
scenario's `source`.

### `capacity`

Average-daily-dollar-volume based, stated as arithmetic a reader can redo:

```
capacity_usd ≈ avg_daily_dollar_volume_usd
               * participation_cap_fraction
               * n_names_per_leg
```

`method` must say where the ADV came from, over what window, and what the
participation cap assumes (and that a cap is a judgment call, not a
measurement).

### `regime_coverage` — computed, never asserted

Give `window_start` and `window_end`. The validator **computes** which of the
four known regimes the window covers and **rejects** a scorecard whose
declared present/absent lists disagree:

| key | episode | bracket |
|---|---|---|
| `dotcom_2000` | dot-com bust | 2000-03-24 .. 2002-10-09 |
| `gfc_2008` | global financial crisis | 2007-10-09 .. 2009-03-09 |
| `covid_2020` | COVID crash and recovery | 2020-02-19 .. 2020-12-31 |
| `rate_hike_2022` | 2022 rate-hike bear market | 2022-01-03 .. 2022-10-12 |

A regime counts as present only if the window covers **at least half** of it:
a window ending 2008-01-02 has technically touched the GFC and learned nothing
from it.

`statement` is the sentence a reader gets: what the window did and did not see,
in plain words.

---

## The JSON skeleton

Copy to `backend/data/research_runs/scorecards/<family_key>_SCORECARD.json`.
Every `<...>` is a placeholder and the validator **rejects** any string still
containing one (as it does `TODO`, `TBD`, `FIXME`, `XXX`, and empty strings).

```json
{
  "schema": "registration_scorecard/v1",
  "family_key": "<family_key exactly as persisted in cross_sectional_trial_results>",
  "pattern_id": "<the spec this scorecard is about>",
  "written_at": "<YYYY-MM-DD>",
  "author": "<who wrote it>",
  "decision": "<REGISTERED | DECLINED | WITHDRAWN | NOT_YET_DECIDED>",
  "decision_rationale": "<why, in prose, in one paragraph>",
  "preregistration_path": "<data/research_runs/..._PREREGISTRATION.txt, or a sentence saying there is none and why>",

  "layer_1_statistical": {
    "best_spec_pattern_id": "<pattern_id of the best spec>",
    "n_local": 0,
    "dsr_pass_threshold": 0.95,
    "dsr_by_n": { "0": 0.0, "37": 0.0, "362": 0.0, "1031": 0.0 },
    "verdict": "<definite_negative | underpowered | unresolved | pass>",
    "sharpe_net_annualized": 0.0,
    "n_observations": 0,
    "preservation_score": 0.0,
    "preservation_score_no_stab": 0.0,
    "preservation_inputs_note": "<which dsr (which N, which run_tag) was fed as cred, and periods_per_year>",
    "power": {
      "claimed_sharpe_annualized": 0.0,
      "claimed_sharpe_source": "<paper, table/section; how gross was converted to net>",
      "sigma_sr_annualized": 0.0,
      "periods_per_year": 252,
      "required_observed_sharpe": 0.0,
      "power_at_claimed_sharpe": 0.0,
      "min_detectable_sharpe": 0.0,
      "years_to_detect_claimed": 0.0
    }
  },

  "layer_2_mechanism_fidelity": {
    "source_citation": "<author, title, journal, volume(issue), year, pages, doi>",
    "source_text_obtained": false,
    "construction_choices": [
      { "choice": "<what was built>", "source_locus": "<paper, section, equation/table>" }
    ],
    "deviations": [
      { "deviation": "<what differs from the source>", "reason": "<why>" }
    ],
    "independent_reviewer": "<who>",
    "independent_reviewer_signed_off_at": "<YYYY-MM-DD>",
    "independent_reviewer_findings": "<what they re-derived and what they found, including nothing>"
  },

  "layer_3_regime_conditional": {
    "source_claim_type": "<unconditional | conditional>",
    "claim_evidence": "<quote or citation establishing which>",
    "not_applicable_reason": "<required when unconditional; omit when conditional>",
    "regime_definition_rule": null,
    "regime_rule_pre_declared_at": null,
    "dsr_in_regime": null,
    "dsr_out_of_regime": null
  },

  "layer_4_economics": {
    "cost_scenarios": [
      { "name": "<name>", "one_way_bps": 0.0, "source": "<source>", "best_spec_net_sharpe": 0.0 },
      { "name": "<name>", "one_way_bps": 0.0, "source": "<source>", "best_spec_net_sharpe": 0.0 }
    ],
    "capacity": {
      "avg_daily_dollar_volume_usd": 0.0,
      "participation_cap_fraction": 0.0,
      "n_names_per_leg": 0,
      "capacity_usd": 0.0,
      "method": "<where the ADV came from, over what window, what the cap assumes>"
    },
    "regime_coverage": {
      "window_start": "<YYYY-MM-DD>",
      "window_end": "<YYYY-MM-DD>",
      "regimes_present": [],
      "regimes_absent": [],
      "statement": "<what the window did and did not see>"
    }
  }
}
```

---

## Backfilling old families — read this before you do it

`test_registration_scorecards.py` currently fails, listing every family with
persisted trial results and no scorecard. **That failure is the correct
state**, not a bug to be silenced.

Do **not** backfill by reconstructing Layer 2 from the code. An honest
`source_locus` requires the construction context the original author had —
which paper section they were reading when they chose a breakpoint — and
inventing one produces a citation that looks verified and is not. This project
has already been burned once by a formula written from memory
(the discarded Corwin-Schultz implementation, see `spread_estimator.py`).

Backfill a family only when someone with the original context writes it, or
when the original context is recoverable from a committed pre-registration or
run report. Otherwise leave it failing: a listed gap is worth more than a
fabricated scorecard.
