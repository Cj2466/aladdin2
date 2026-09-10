# The 55-of-57 scorecard gap: what it costs to close, and a recommendation (2026-09-10)

`tests/test_registration_scorecards.py::test_every_family_has_a_scorecard` is red on purpose:
55 of the 57 families with persisted trial results or a live registration have no
scorecard under `data/research_runs/scorecards/`. Its docstring says the fix is writing the
scorecards and forbids writing them from code. This memo is the decision analysis the owner
asked for. **Nothing here is executed; the test is unchanged.**

## 1. Where the 57 actually stand (verified 2026-09-10)

| group | count | evidence |
|---|---|---|
| scored | 2 | `scorecards/`: `intraday_momentum_spy`, `low_frequency_patterns` |
| live forward registrations | 4 | `quality_cbop`, `short_interest_ratio`, `lazy_prices_jaccard_full`, `cross_sectional_crypto` — layers 1–3 now drafted, layer 4 / power / decision open |
| parked in the Dormant pool | 16 | `dormant_pool_2026-09-09/dormant_pool_manifest.json`; **no overlap with the live four** (checked) |
| everything else — closed honest negatives and exclusions | 35 | by subtraction: 57 − 2 − 4 − 16 |

## 2. What one honest card costs

This pass produced layers 2 and 3 for four families in one Fable session: fetching and
text-extracting four papers, re-reading every builder-cited locus, and writing the cards. A
*complete* card additionally needs layer 1 (mechanical — the draft generator already does it),
layer 4 (cost scenarios from the borrow-cost runs, a capacity method, a regime-coverage
statement) and the power block (the pre-registration's claimed Sharpe, interpreted). Honest
estimate: **1–1.5 hours of Fable-class time per family** at the rigour this project demands,
*when the paper can be obtained*. For 55 families that is roughly 60–80 hours — and for some
of them the paper cannot be obtained at all (BHJ is one already).

## 3. Why the value is not uniform across the 55

A scorecard's layer 2 answers one question: *is this family's verdict a verdict about the
paper's construction, or about a deviation from it?* That question matters in proportion to
how likely the family is to be looked at again:

* **Live (4):** matters most — a forward result will be read against the paper. Done through
  layer 3; finish layer 4 next.
* **Parked (16):** matters — the Dormant pool re-looks yearly by design, and a look without a
  layer 2 repeats today's problem at every look.
* **Closed (35):** archival. Each already carries its own verification record in its module
  docstring (this project's convention is unusually thorough about that). A card would add
  a citation audit to a decision that is not going to be revisited without new data — the
  modules themselves say "do not re-test without new data".

## 4. Options

**A. Keep the test as it is and work through all 55.** Honest, complete, ~60–80 hours, and
the test stays red for months. The docstring itself names the cost: "a permanently red test
is the classic way a signal stops being read." Also impossible to finish for any family whose
paper cannot be obtained.

**B. Redefine green as "every family is either scored or explicitly waived with a reason",
with waivers barred for live and parked families.** Concretely:

* a committed `scorecard_waivers.json`, one entry per waived family: the reason, and a pointer
  to the module docstring section that carries that family's own verification record — a
  *pointer*, not an exemption;
* the test fails if any family is neither scored nor waived, **and** fails if a waived family
  is live or in the Dormant manifest, so the waiver can never cover the two groups where the
  card matters;
* order of work: the 4 live (layer 4 + power + decision), then the 16 parked, then the 35
  waivers.

Cost: ~20 cards (≈ 25–30 hours) plus a waiver file, and the test goes green when the pointers
are in — while still refusing to let a live or parked family hide behind one.

**C. Skip or delete the test.** No. It is the only place this gap is visible.

## 5. Recommendation

**B.** It keeps the test's purpose (the gap is visible, per family, with a reason), removes
the permanently-red failure mode the test's own author warned about, spends the expensive
work where a card will actually be read, and cannot be gamed for the families that matter.

**Why this is the owner's call and not mine:** B changes what "green" means for a governance
test. A reviewer redefining the bar it is being measured against is the pattern this project
rejects everywhere else (denominators, thresholds, status words). So: recommended, with the
mechanism specified precisely enough to build in one small branch, and left unbuilt.

If the owner ratifies B, the build is: one JSON file, one test change, and the four live
cards completed first. If the owner prefers A, the next step is the same first step — finish
the four live cards — and the difference only appears after the 16 parked.

---

**IMPLEMENTED 2026-09-10 (owner ratified B):** `registration_scorecard.load_scorecard_waivers` /
`unwaivable_family_keys`, `data/research_runs/scorecards/SCORECARD_WAIVERS.json` (31 closed
families, each pointing at an existing record), and the re-expressed completeness test plus four
waiver guards in `tests/test_registration_scorecards.py`. The four live cards were completed the
same day. The test's remaining list is now exactly the families a waiver is barred for: the 16
Dormant-pool members and the retired `quality_noa_industry_neutral` registration.

