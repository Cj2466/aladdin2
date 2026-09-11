# ADDENDUM 01 — placebo application target, and the under-specified points the build had to fix

Dated 2026-09-11, written by the builder (Fable 5.1) **before any real-arm number existed**
(the module, the run script and every output file postdate this commit). PREREGISTRATION.md is
not rewritten; this file is the amendment record required by its §8.

Nothing here changes a bin threshold, a k, a window, the measurability floors, the number of
draws, the top-20 count or a gate threshold. Item A is a genuine fork in the pre-registration's
own wording and is resolved here with its reasoning. Items B–I are points the pre-registration
simply does not fix; each is declared now so that no choice is made after seeing a number.

---

## A. THE ONE REAL FORK — what the placebo transform is applied to

**The problem.** §5 opens "Both placebos are applied to the demeaned return matrix and then run
through the IDENTICAL scanner (same code path, same alphabet, ...)", while §3 defines the
alphabet on the RAW return r_{i,t} = close_t/close_{t-1} − 1 and defines the demeaned series
y_{i,t+1} only as the OUTCOME. Those two sentences cannot both be taken literally:

* If the placebo is applied to the demeaned matrix y and the real arm is fed the raw matrix r,
  then the placebo arm's bins are built from y and the real arm's bins from r. The two arms then
  run **different alphabets**, which §5's own "same alphabet" clause forbids, and the comparison
  stops being a control (the arms would differ by two things, not one).
* If instead BOTH arms are fed the demeaned matrix, then §3's alphabet is no longer the one
  described in §3 (bins would come from y, not r), and the scanner's own demeaning step becomes a
  no-op on the real arm — a silent redefinition of §3.

**Resolution adopted.** The scanner takes exactly one input, a per-name return matrix X, and does
everything downstream of it: σ (20-bar, strictly prior), z, bins, and the cross-sectionally
demeaned outcome. The real arm passes X = r (raw). Each placebo draw passes X = transform(r).
The demeaning stays *inside* the scanner, where §3 puts it, and is applied identically in every
arm. The real and placebo arms therefore differ by exactly the placebo transform and nothing
else, which is the property a control has to have.

**Disclosed consequence, not glossed over.** Because P1 flips the sign of every raw return
independently, the placebo arm's cross-sectional mean is near zero while the real arm's carries
the market move; the real arm's demeaning therefore removes a common factor that the placebo arm
does not have to remove. This is inherent to sign-flipping raw returns and is reported as a limit
in the run report, not hidden. Likewise, §5's claim that P1 preserves volatility clustering
"exactly" is true of the return magnitudes but not bit-exactly of σ: the 20-bar sample standard
deviation is taken about the window mean, and flipping signs moves that mean. The effect is
second-order (σ changes by O(1/20) of the mean's square) and is stated in the report rather than
asserted away.

---

## B. Newey-West on a series with gaps

A pattern portfolio R_p exists only on the bars where the pattern is present with enough names,
so R_p is a series with holes. "NeweyWest-SE(R_p, lag = h)" does not say what "lag 1" means
across a hole. **Declared:** R_p is the ordered sequence of its realized bars (holes compressed
out); the Bartlett-kernel autocovariances are taken over consecutive *realizations*, which is what
handing the gap-free series to a standard HAC routine would do. The estimator is the ordinary
Newey-West (1987) Bartlett-kernel HAC variance of a sample mean, and the build validates it
against `statsmodels`' own HAC implementation in a test rather than trusting the transcription.

## C. Reading of the measurability rule

"≥ 10 names on ≥ 250 bars (Panel E) / ≥ 5 names on ≥ 2,000 bars (Panel C)" is read as: a bar
counts for a pattern only if the pattern has at least the name floor on that bar, and the pattern
is measurable iff it has at least the bar floor of such bars **in the discovery window**. R_p is
defined only on the bars that meet the name floor. Patterns failing this are counted and excluded
from every statistic, per §3.

## D. Horizon-window containment (no leakage across the discovery/holdout boundary)

A formation bar t is used in a window only if its whole outcome window (t+1 … t+h) also lies in
that window. Without this the last discovery bar's h = 1 outcome would be the first holdout bar's
return, and the h = 5 statistic would reach five bars into the holdout.

## E. Burn-in is taken inside the declared sample

§2 fixes the sample start (E: 2016-01-04, C: 2019-09-08) and separately says the first 20 bars are
σ burn-in. **Declared:** returns are computed only inside the declared sample and the burn-in is
consumed from inside it — no pre-sample bar is read. This is the conservative reading (it costs
~21 formation bars at the start of each panel) and it keeps the sample boundary literal.

## F. σ convention and missing predecessors

σ is the sample standard deviation (ddof = 1) of the 20 returns strictly before t, requiring all 20
to exist; z = r/σ is undefined otherwise. r_{i,t} requires a close at t and at the immediately
preceding panel bar — "bars with a missing predecessor are dropped" (§2) is implemented as
requiring the previous *panel date* to carry a close for that name, not merely the previous
available observation.

## G. Holdout membership floor

In the holdout, a top-20 pattern contributes on a bar only if it meets the same per-bar name floor
(10 for E, 5 for C). The ≥ 250 / ≥ 2,000-bar floor is a discovery-window *selection* rule and is
not re-applied in the holdout. H is the equal-weight average over whichever of the 20 patterns is
present on that bar; a bar with none present is dropped.

## H. Cost-arm turnover

§6 fixes the rates (5 bp E, 10 bp C, one-way) and calls the arm naive, but does not define
turnover. **Declared:** each bar's implied name weights are
w_{i,t} = (1/P_t) · Σ_p sign_p · 1[i ∈ p at t] / n_{p,t} over the top-20 patterns present at t, and
turnover_t = Σ_i |w_{i,t} − w_{i,t−1}|, charged at the one-way rate. The short leg implied by
cross-sectional demeaning (a short in the equal-weight universe) is near-constant and is NOT
charged; that understates the cost and is stated as such in the report.

## I. Synthetic-validation details left open by §7

§7 fixes the panel (500 × 2,000, Student-t(4), +0.30σ after U,U,U) but not the split, the σ the
shift is measured in, or the panel's measurability floors. **Declared in the test:** first 1,400
bars discovery / last 600 holdout; the shift is 0.30 × the same 20-bar σ_{i,t+1} the scanner uses;
name/bar floors 10 / 250, i.e. Panel E's. The planted rule is applied to the return that follows a
(U,U,U) computed on the unplanted series, and the scanner then recomputes its bins from the
planted series — so the recovery test is harder than a self-consistent plant, not easier. The
false-positive count under a P1 draw is asserted against a band around 0.0027 × the number of
**measurable** patterns in that synthetic panel (not 6,831 — a 500-name panel cannot make most
k = 8 patterns measurable), and both the expectation and the observed count are reported.

---

Builder: Claude Fable 5.1, 2026-09-11. Committed before `pattern_scan_placebo.py` existed.
