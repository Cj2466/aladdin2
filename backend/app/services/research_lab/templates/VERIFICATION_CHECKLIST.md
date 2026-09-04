# INDEPENDENT VERIFICATION CHECKLIST

The pass that has to happen before anything in this project is called done.

Not invented for this file. Every step below is something a verification pass
in *this repository* has already done and that already caught something. Where
a step exists because of a specific incident, the incident is named — a rule
whose cost you cannot see is a rule that gets skipped under time pressure.

---

## 0. Before you start

**Verify from primitives, not from the report.** The output being checked is
the thing under suspicion. If your only evidence is a number the pipeline
printed, you have re-read the claim, not verified it.

**Be adversarial about the claims that are cheapest to make.** In this
project's history the highest-risk category has been *"X is not available /
needs payment"* and *"I checked and it's fine"* — assertions that cost nothing
to write and are expensive to falsify. Falsify them anyway.

**Try to break it, not to confirm it.** `dd34094`'s verifier put it as
"fully adversarial", and it found a prose overstatement ("7 of 9" clearers
that were actually 6) that a confirming read would have sailed past.

---

## 1. Re-derive N key numbers by hand from primitives

At least **three**, including the single number the conclusion rests on.
By hand means: from raw inputs, through arithmetic you wrote, without calling
the function under test.

- [ ] The headline statistic, recomputed from the raw series (not from the
      persisted summary row).
- [ ] One number the conclusion is *sensitive* to — the one that, if wrong,
      flips the verdict.
- [ ] One number from the *middle* of the pipeline, where an error would not
      be visible at either end.
- [ ] Where a fixed point exists, hit it exactly rather than approximately.
      `77e77d7` pinned its price reconstruction against a known fact — AAPL
      closed at 499.23 on 2020-08-28 before its 4-for-1 split — and required
      exact reconstruction from Yahoo's 124.8075. An externally-known answer
      beats any internal consistency check.
- [ ] Reproduce from a **fresh data fetch or a fresh process**, not from the
      run's own cached objects. `dd34094` reproduced 6 of 9 scenario passes
      from a fresh fetch and required **exact clearing-SET matches, not just
      matching counts** — the same count with a different set is a different
      result wearing the same number.

Record what you re-derived and to what tolerance. "Matches" without a
tolerance is not a measurement.

---

## 2. Diff every file that is claimed to be unchanged

- [ ] For each file the change claims not to touch, confirm it is
      **byte-identical**: `git diff <base>..HEAD -- <path>` empty, or compare
      `sha256`. Reading the diff summary is not this step.
- [ ] For a formula or constant claimed to be untouched, check the **value**,
      not just the file: `f385fc5`'s verification confirmed
      `PSR_SELECTION_THRESHOLD` was still *imported* from
      `multi_signal_combination.py` rather than having become a hardcoded copy
      with the same value — the file diff would not have shown that.
- [ ] If the claim is "byte-for-byte unaffected", prove it by running the old
      path and the new one and comparing outputs, not by reading the code.
      `61bd307` did this across 26 families and 420 specs.

---

## 3. Run the full relevant test suite and confirm zero NEW failures

- [ ] Full suite, not the changed file's tests. Record the counts:
      `f385fc5` reported "3573 passed, 3 skipped"; `dd34094` reported
      "2545 passed / 1 skipped, ruff clean".
- [ ] Compare against the **baseline on the merge base**, not against zero. A
      suite with pre-existing failures needs the before-count, or "no new
      failures" is unverifiable.
- [ ] Lint clean, by the same command the project uses.
- [ ] Confirm no test was **skipped or xfailed** in this change. A newly
      skipped test is a silently deleted assertion.

---

## 4. Check whether a test was weakened instead of the code being fixed

This is the step most easily skipped and the one with the worst failure mode.

- [ ] `git diff <base>..HEAD -- '*test*'` and read **every** change to an
      existing test. New tests are cheap to add; changed ones deserve the
      scrutiny.
- [ ] For each modified assertion, ask which is true: *the expectation was
      wrong* (fine, and it must be explained), or *the behaviour changed and
      the test was bent to fit* (not fine).
- [ ] Watch specifically for: a tolerance widened, an exact equality turned
      into `approx`, an assertion turned into a log line, a loop bound
      shortened, a fixture made smaller until an edge case stopped occurring,
      `pytest.raises` broadened to a base class.
- [ ] A test that now passes on **strictly less** input than before is a
      weakened test even if its assertions are unchanged.

---

## 5. Confirm no live registration was silently changed

`cross_sectional_forward_validation_registrations` rows are only ever changed
by an explicit, signed-off human decision. Never as a side effect.

- [ ] No `status` transition in this change. `f385fc5` stated it plainly:
      "All four live registrations therefore keep the numbers they had; none
      has its status changed here."
- [ ] `spec_fingerprint` / `config_fingerprint` unchanged for every live
      registration — or, if changed, that is the *point* of the change and it
      is signed off.
- [ ] **The fingerprints are not enough.** They do not cover the code and data
      underneath the spec — price adjustment, universe construction, the DSR
      denominator, the cost model. Run
      `tests/test_live_registration_dependencies.py` and, if it is red,
      re-verify and record an acknowledgement before re-pinning. Three real
      incidents moved exactly that layer with both fingerprints unchanged:
      the price-store rewrite (`77e77d7..61bd307`), the CRSP dividend
      convention (`a3ba0bc`), and short_interest's mid-split price freeze
      (`fa614ac`).
- [ ] A change that alters what a live registration *trades* — a different
      cost frame, a different universe rule — is a repo-owner decision even
      when no fingerprint moves.

---

## 6. Check the sources, not the citations

- [ ] **Fetch every cited source and confirm the quoted text is really there.**
      `dd34094`'s verifier "fetched and confirmed every cited source verbatim".
      This project has shipped one formula written from memory — a
      Corwin-Schultz implementation that recovered a true 10bp spread as
      **-12.8bp** — and the standing rule since is: the paper in context,
      equation by equation, equation numbers cited in code.
- [ ] Distinguish *the source says X* from *a paper citing the source says X*.
      `short_interest_PREREGISTRATION.txt` §1 records two near-misses: a
      search engine's synthesized answer attributing a different paper's
      design to the source, and citing papers whose "Consistent with Boehmer
      et al. (2010), Table 9 shows…" refers to their **own** table.
- [ ] Where the full text could not be obtained, that must be **stated**, and
      every detail derived from second-hand sources labelled by strength of
      support.
- [ ] Any number with no credible free source uses the **most conservative
      defensible** value, and says so.

---

## 7. Explicit p-hacking / selection check

- [ ] Every scenario, threshold, cutoff and constant traces to a
      **pre-registration or a cited external source** — not to something tried
      against the data. `dd34094` ran exactly this check and said so:
      "no scenario or calibration choice traces to anything but the cited
      primary sources".
- [ ] The grid did not grow after results existed. Compare against the
      pre-registration's own declared grid.
- [ ] The pass rule was not softened. Compare against the pre-registration's
      own declared rule; if it changed, that is a finding to report, not an
      edit to make.
- [ ] Where results were known in advance and could not be un-known, that
      prior knowledge is **disclosed** rather than pretended away (the
      "DISCLOSED PRIOR KNOWLEDGE" section in
      `edge_cost_reaudit_corrected_PREREGISTRATION.txt` §0 is the model).
- [ ] Freeze the design before running: a `sha256` of the pre-registration,
      recorded before the first number exists, is what makes "this was
      pre-declared" checkable rather than asserted.

---

## 8. Check the write-up against the numbers

- [ ] Every number in the prose appears in the persisted output. `dd34094`
      found and fixed a prose overstatement this way.
- [ ] Superlatives and counts ("all", "every", "none", "7 of 9") are
      recounted from the data.
- [ ] Results are **persisted to a real committed file or DB table**, not left
      in a scratchpad or a docstring. Two real incidents came from that: a
      local DB wipe destroyed 249 rows, and a synthetic RNG fixture was later
      mistaken for real archived results and produced a fabricated finding
      (see `cross_sectional_persistence.py`'s header).
- [ ] Originals stay visible beside corrected values. A revised number with
      the old one deleted is unauditable.
- [ ] An honest negative is reported as an honest negative, with no hedging
      language that leaves room to reread it as a positive later.

---

## 9. What to do when a step fails

Report it. Do not fix it quietly and re-run the checklist as though it had
passed the first time — the fact that it failed is itself a result, and the
next reader needs it.

If you cannot complete a step (missing API key, missing cache, a source behind
a paywall), say **which** step and **why**, rather than marking it done.
`61bd307` did exactly this: two families could not be compared because the
environment lacked `FRED_API_KEY` and a calendar cache, and it said so instead
of quietly reporting 24 of 26.

---

## The one-line version

> Re-derive the numbers yourself, diff what is claimed unchanged, run
> everything, read the test diff for weakened assertions, confirm no live
> registration moved, and fetch every source you cite.
