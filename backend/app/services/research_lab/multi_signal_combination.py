"""THE PROJECT'S CORE THESIS, TESTED: can several individually-weak,
sub-significance signals be combined into a genuinely significant book?

This is the "law of large numbers of micro-edges" test. Every family this
project has built is an honest negative on its own. The thesis under test
is that this does not matter — that a dozen tiny, mutually-uncorrelated
edges add up to one real one, which is the Medallion story as it is usually
told. This module tries to falsify that on this project's own measured
results rather than argue about it.

THIS FILE IS WRITTEN IN THE ORDER THE WORK WAS ACTUALLY DONE. Sections 1-3
(the selection rule, the threshold, the combination methodology and the
null control) were written, committed to this file, and frozen BEFORE any
combined number existed. Section 6 (results) was appended afterwards.
Nothing in sections 1-5 was edited after section 6 was written. That
ordering is the entire methodological content of this module: the failure
mode it exists to prevent is choosing WHICH signals to combine after seeing
how good the combination looks, which is a form of p-hacking that no amount
of downstream statistical machinery can undo.

===========================================================================
1. STEP 1(a) — THE HARD-EXCLUDE RULE, AND WHY IT IS NOT "EXCLUDE EVERY
   HONEST NEGATIVE"
===========================================================================
Every candidate here is drawn from cross_sectional_trial_results, which is
the project's authoritative record of per-spec screening output (see
cross_sectional_persistence.py). Each contributing family module also
carries its own final, independently-verified VERDICT in its docstring.
Those verdicts are respected, not just the raw numbers.

The distinction that does the work — declared before any list was drawn up:

  HARD EXCLUDE a family or a specific spec when its own documentation
  carries an explicit, final DISQUALIFYING verdict of one of three kinds:
    (i)   CONFIRMED ARTIFACT — the return stream was shown to measure
          something other than the claimed signal;
    (ii)  CONFIRMED UNTRADEABLE / COST-DOMINATED — the stream cannot be
          realized going forward (universe decay) or does not survive a
          realistic cost model;
    (iii) AN EXPLICIT IMPERATIVE — "DO NOT TREAT AS VALIDATED EDGE",
          "Do not trade X in any form on this universe".

  DO NOT hard-exclude for: "honest negative", "no validated edge", "does
  not clear this project's bar", "null result". That language is on almost
  every family in the project and it describes exactly the population this
  experiment is about — individually weak, honestly measured, sub-
  significance signals. Excluding them would make the thesis untestable by
  construction, which is the opposite of a test.

The difference in one sentence: (i)/(ii)/(iii) mean the NUMBER IS NOT WHAT
IT LOOKS LIKE; "honest negative" means the number is real and small.

===========================================================================
2. STEP 1(b) — THE ONE NUMERIC THRESHOLD, CHOSEN BEFORE THE SELECTION QUERY
   WAS RUN
===========================================================================
THRESHOLD: psr_vs_zero >= 0.50, applied uniformly to every non-hard-excluded
persisted spec. Chosen over the alternative (a DSR threshold) for three
reasons, all of which are about comparability across families rather than
about which signals it happens to admit:

  1. PSR-vs-zero is populated for every row in the table. DSR is None
     whenever a family declared fewer than deflated_sharpe.MIN_TRIALS_FOR_DSR
     = 5 sibling specs — which is true of the whole ofi_crypto family BY
     DESIGN (4 pre-declared specs; that module's docstring says so and says
     why padding the family to 5 to make the tooling emit a number would be
     choosing the hypothesis to fit the instrument). A DSR threshold would
     silently delete an entire family for a reason that has nothing to do
     with its signal.
  2. DSR is not comparable across these families. n_trials in the table
     ranges from 4 to 212. The identical return series would get a very
     different DSR as a member of a 4-spec family than as a member of an
     18-spec family, because SR0 grows with the family's own declared size.
     A CROSS-family threshold must not depend on how many siblings each
     builder happened to pre-declare.
  3. It is deliberately the WEAKEST coherent bar. PREDECLARATION.txt (this
     project's own decision rule, archived at
     research_archive/session_2026-08-22_to_27/PREDECLARATION.txt) reads:
     "DSR > 0.50 = 'possibly interesting', nothing more / DSR 0.90-0.95 =
     this project's real significance standard / Anything below 0.90 is
     reported as an HONEST NEGATIVE". Selecting at the "possibly
     interesting" tier would pre-select for NEARLY-significant signals and
     turn this into "do two or three almost-good signals add up", which is
     a different and much less interesting question than the one asked.

  THE HONEST COST OF THIS THRESHOLD, STATED BEFORE THE SELECTION WAS RUN.
  probabilistic_sharpe_ratio(sr_hat, 0, n, skew, kurt) = Phi(sr_hat *
  sqrt(n-1) / sqrt(denom)) with denom > 0, so PSR-vs-zero >= 0.50 is
  ALGEBRAICALLY IDENTICAL to "in-sample annualized Sharpe > 0". This
  selection is therefore selection-on-in-sample-sign, and the combined
  portfolio is then measured on the SAME sample. The combined Sharpe is
  upward-biased by construction. That bias is not hidden or argued away
  here — section 4 pre-declares a Monte Carlo null that prices it directly,
  and the headline verdict is taken from that null, not from the raw
  combined Sharpe.

STEP 1(c) — ONE SPEC PER FAMILY: where several specs of the same family
clear the threshold, only that family's single best spec is kept, ranked by
the SAME criterion used to threshold (highest psr_vs_zero). Sibling specs of
one family share a universe, a signal and mostly a formation grid; combining
them would count one edge several times, understate the correlation the RMT
and HRP steps are supposed to be measuring, and inflate exactly the
"several independent edges" claim under test.

STEP 1 TIE-BREAK, declared for completeness: ties on psr_vs_zero are broken
by higher sharpe_annualized, then by trial_id ascending, so the rule is
deterministic.

RUN-TAG RULE, declared before the query: where a family has several
run_tags, the tag whose rows the family's own docstring names as the
canonical / post-verification record is used. Where a family has exactly
one tag, that tag is used. This is a data-provenance rule, not a selection
knob: it never picks BETWEEN specs, only between two recordings of the same
screening pass.

===========================================================================
3. STEP 2 — THE COMBINATION METHODOLOGY, FROZEN BEFORE ANY OF IT RAN
===========================================================================
RETURN SERIES. The persisted full_result_json holds summary statistics
only — no return stream (verified by inspection of one row per family).
Each selected spec's DAILY NET return series is therefore regenerated by
re-running that family's own code with its own config, and is net of
whatever turnover and financing charges that family models. No series is
re-derived, re-costed or re-scaled here.

CALENDAR ALIGNMENT. The equity families share the NYSE session calendar;
the crypto family trades 24/7/365 (metrics.CALENDAR_DAYS_PER_YEAR, and see
cross_sectional_ofi.py's CALENDAR note). The common calendar is the
INTERSECTION of the equity-family dates. A signal with a finer native
calendar is COMPOUNDED onto it: each common date carries
prod(1 + r_native) - 1 over that signal's native dates falling after the
previous common date, up to and including this one. No observation is
dropped and none is fabricated — dropping crypto weekends would silently
delete ~2/7 of that sleeve's P&L, and forward-filling equities across
weekends would invent equity returns that never happened. A common date on
which a signal has no native observation at all contributes 0.0, which is
already every family's own encoding of a flat / uninvested day.

WINDOW. The strict intersection of all selected candidates' dates. This is
short — it is bounded below by the latest-starting candidate — and that
truncation is reported, not worked around. Running the combination on a
longer window by dropping the late-starting candidate would be choosing the
candidate set from the window, i.e. exactly the move this module exists to
prevent.

PIPELINE, in order:
  1. RMT denoising of the candidates' correlation matrix
     (risk/rmt_denoising.denoise_covariance_matrix, q = T/N, sigma^2 fitted
     — the module's own default).
  2. HRP on the denoised matrix
     (risk/hrp_optimizer.compute_hrp_weights_from_returns(..., denoise=True),
     which is that module's own composed RMT+HRP path). Weights are
     long-only and sum to 1.
  3. Combined series r_c[t] = sum_i w_i r_i[t]. Every sleeve is a
     self-financing overlay (dollar-neutral long/short, or a timing overlay
     with financing charged inside), so a weighted sum is the return of a
     book putting w_i of one unit of notional behind sleeve i.
  4. Kelly/HJB sizing
     (risk/kelly_sizing.compute_kelly_leverage_from_returns) on the HRP
     direction, risk_free_rate = 0.0. THAT ZERO IS A DELIBERATE MODELLING
     CHOICE, not a placeholder: each sleeve's series is already an
     excess-return-like overlay with its own financing charged inside it, so
     subtracting a second risk-free rate would double-count. Reported at
     full Kelly, at the module's DEFAULT_KELLY_FRACTION = 0.5, and at
     growth_optimal_kelly_fraction with the sample theta^2 debiased as that
     function's own docstring instructs (max(theta_hat^2 - N/T_years, 0)),
     because feeding it the raw sample value biases the fraction UP.

  DECLARED CAVEAT ON STEP 1, WRITTEN BEFORE IT RAN: Marchenko-Pastur is an
  asymptotic result (N -> inf, T -> inf, T/N fixed). At the N this
  experiment has, it is far outside that regime, and its sigma^2 is fitted
  by a kernel density estimate over a handful of eigenvalues. Whatever the
  denoising does or does not change here is REPORTED, and is NOT treated as
  evidence for or against RMT denoising as a method.

===========================================================================
4. STEP 2(5) — WHAT n_trials MEANS FOR A COMBINED BOOK, AND WHY A DSR IS
   NOT REPORTED AS THE HEADLINE
===========================================================================
The DSR (Bailey & Lopez de Prado 2014, as implemented in
deflated_sharpe.py) answers one specific question: given that the reported
Sharpe is the MAXIMUM over N equally-skilled zero-edge trials whose Sharpes
have cross-sectional dispersion sigma_SR, how likely is the true Sharpe to
beat the best-of-N-noise benchmark SR0? Its generative model is a maximum
over N draws of the same statistical object.

A combined portfolio is not that object. It is one deterministic function
(a fixed weighted sum) of N series that were themselves selected. Three
candidate answers, assessed before any number was computed:

  (1) n_trials = number of signals combined. REJECTED. It encodes "I ran
      this many combinations and reported the best". One combination was
      run. There is also no set of sibling combinations from which to
      estimate sigma_SR, so the number that came out would be a
      dispersion of the wrong things.
  (2) n_trials = every spec scanned by the selection rule. Directionally
      right — the combination does inherit the whole search that produced
      its inputs — but still not the DSR's model, because the reported
      statistic is not the maximum of those specs.
  (3) Report PSR-vs-zero for the combined series (exactly defined for one
      series, needs no trial count at all), and separately report a
      clearly-labelled DEFLATION-STYLE SENSITIVITY using (2)'s trial count
      with sigma_SR taken from the actual cross-sectional dispersion of the
      scanned specs' annualized Sharpes.

  CHOSEN: (3). The sensitivity number is persisted in the `dsr` column
  because that is the column that exists, and the persisted JSON carries an
  explicit flag saying it is NOT a Bailey-Lopez de Prado DSR. A number that
  looks precise on a shaky foundation is worse than saying so.

  THE PRE-DECLARED DECISION RULE FOR THE COMBINED BOOK. PSR alone is not
  enough: PSR prices sample size, skew and kurtosis, and prices selection
  at exactly zero. The combination is called a real edge only if BOTH:
    * the deflation-style sensitivity of section 4(3) is >= 0.90 (the bar
      PREDECLARATION.txt sets for this project), AND
    * the selection-mirroring Monte Carlo null below returns an empirical
      p-value <= 0.05.
  Anything else is an honest negative and is reported as one.

THE SELECTION-MIRRORING MONTE CARLO NULL, declared here in full before it
ran. The threshold of section 2 guarantees every input has a positive
in-sample Sharpe, so a combination of pure noise selected the same way would
ALSO look positive. To price that:
  * For each selected family f, which had k_f persisted specs, draw k_f
    independent zero-mean Gaussian daily series of length T (the common
    window) with the daily volatility of the spec actually selected from f.
  * Keep that family's best-of-k_f by in-sample Sharpe — mirroring
    step 1(c) exactly.
  * Run the identical pipeline (RMT+HRP, and separately equal-weight) on
    the surviving N sleeves and record the combined annualized Sharpe.
  * B = 2000 draws, seed 20260829, both fixed here.
  * p-value = fraction of draws whose combined Sharpe >= the real one.
  Two approximations, both stated in advance and both CONSERVATIVE (they
  make the null's best-of-k too good, so a real result has to clear MORE):
  sibling specs within a family are drawn independent when in reality they
  are highly correlated, which over-disperses the best-of-k; and the
  families are drawn independent of each other, which is close to the truth
  here (different asset classes and mechanisms) and whose real measured
  cross-correlations are reported alongside so a reader can check.

---------------------------------------------------------------------------
4A. ADDENDUM, WRITTEN AFTER RUNNING STEP 1 AND BEFORE COMPUTING ANY
    COMBINED NUMBER. The sequence matters, so it is recorded rather than
    folded into section 4 as if it had always been there.
---------------------------------------------------------------------------
Running the frozen selection produced n_scanned = 332 and, from section
4(3)'s formula, sigma_SR = 10.63 annualized. That number is an artifact and
this project has already documented the mechanism: intraday_patterns.py's
own docstring says "deeply-negative cost-dominated siblings inflate
sigma_SR to ~2.9 annualized, making the SR0 noise benchmark a severe 8.1".
Here it is worse — the 212 hard-excluded phase_a specs, re-priced under the
EDGE cost model, run down to an annualized Sharpe of -56.8 on patterns with
a few dozen trades, and they alone carry sigma_SR = 9.65. Across the 59
specs that are NOT hard-excluded, sigma_SR is 0.32.

An SR0 built on sigma_SR = 10.63 is roughly 30 annualized. No combined book
of this project's signals can clear that, so the pre-declared statistic
would return ~0 for ANY input — which makes it uninformative rather than
strict.

WHAT IS DONE ABOUT IT, decided here and now, before any combined Sharpe
exists:
  * THE PRE-DECLARATION IS NOT CHANGED. The primary deflation-style
    sensitivity is computed exactly as section 4(3) says, over all 332
    scanned specs, and the section 4 decision rule reads THAT number. A
    pre-declaration that is revised the moment it becomes inconvenient is
    not a pre-declaration.
  * A SECOND, CLEARLY-LABELLED DIAGNOSTIC is computed alongside it with
    sigma_SR taken over the 59 non-hard-excluded specs only. It is NOT
    pre-declared, it was added at this point in the sequence for the reason
    above, and it does NOT feed the verdict. It exists so a reader can see
    how much of the primary's answer is the artifact and how much is the
    data.
  * Both numbers are persisted and both are reported, whichever way they
    come out.

===========================================================================
5. STEP 3 — THE BASELINES, ALL FOUR DECLARED BEFORE ANY OF THEM RAN
===========================================================================
Reported side by side with the RMT+HRP+Kelly result whatever comes out:
  * EQUAL WEIGHT (1/N) on the same candidates — the simplest possible
    combination. If this matches, the diversification did the work and the
    machinery did not.
  * INVERSE VOLATILITY (1/sigma_i, normalized) — the simplest risk-aware
    combination, and what HRP degenerates towards when the correlation
    matrix carries no usable structure. Isolates whether the clustering
    machinery adds anything beyond volatility scaling.
  * HRP WITHOUT RMT DENOISING — isolates the RMT step's own contribution.
  * BEST SINGLE CANDIDATE over the same common window — the "did combining
    help at all" reference. Note this is measured over the intersection
    window, so it will not equal that spec's own persisted family Sharpe.

===========================================================================
6. RESULTS — APPENDED AFTER SECTIONS 1-5 WERE FROZEN
===========================================================================
Run 2026-08-29. Persisted to cross_sectional_trial_results under
family_key "multi_signal_combination", run_tags
"multi_signal_build_2026-08-29" (primary, 4 rows — one per weighting
scheme) and "multi_signal_sensitivity_add_noa_neutral_2026-08-29" (the
section 1 sensitivity, 4 rows). Each row carries its own combined daily
return series, the aligned candidate matrix, the full selection record and
the null-control output, so the whole experiment is replayable from the
table without re-fetching SEC, Yahoo or Binance.

WHAT STEP 1 SELECTED. 332 persisted specs scanned; 273 hard-excluded on
section 1(a)'s documented verdicts; 39 failed the PSR >= 0.50 threshold;
16 cleared it but were not their family's best; 4 selected:

  correlation_risk_premium / crp_realized_21d_h63   +0.2599  PSR 0.8742
  insider_opportunistic / insider_opp_buy_h21_c2_equal +0.0699  PSR 0.5937
  ofi_crypto / ofi_raw_h7                            +0.4617  PSR 0.8684
  quality_cbop / cbop_ls_h63                         +0.4565  PSR 0.9397

Four genuinely different mechanisms and three asset classes: an equity-
index correlation-timing overlay, an SEC Form 4 insider-event book, a
crypto perpetual-futures order-flow cross-section, and a US large-cap
accounting-quality long-short. All four return series were regenerated
from their own families' code and reproduce the persisted rows: OFI
bit-exact, and the three yfinance-dependent ones to 4e-7 .. 7e-6 relative
(Yahoo restates adjusted closes; there is no price cache on those paths).
n_trading_days matched exactly on all four.

THE PREMISE HOLDS ON THE CORRELATION SIDE, AND ONLY THERE. Over the
1480-day common window (2020-10-05 .. 2026-08-26) every pairwise
correlation is within +/-0.067, and RMT put ZERO eigenvalues outside the
Marchenko-Pastur band — the correlation matrix is statistically
indistinguishable from the identity. These really are four near-
independent bets. That is the part of the thesis that survived.

THE COMBINATION IS WORSE THAN ITS OWN BEST INPUT. Annualized Sharpe over
the common window:

  equal_weight        +0.3015    PSR(0) 0.767
  inverse_volatility  +0.1765    PSR(0) 0.665
  hrp_no_denoise      +0.0657    PSR(0) 0.563
  rmt_denoised_hrp    +0.0522    PSR(0) 0.550     <- the "sophisticated" one
  best single input (ofi_raw_h7)  +0.4600

TWO THINGS EXPLAIN THAT, and they are separate.

(a) THE SELECTION DOES NOT SURVIVE THE WINDOW. The candidates were chosen
on full-sample evidence over their own family windows (2154 to 4934 days)
and are necessarily scored on the 1480-day intersection. Over that
intersection, crp_realized_21d_h63 runs -0.4040 and cbop_ls_h63 -0.0654 —
two of the four are NEGATIVE in the window where the book actually
trades. No weighting scheme can fix inputs that are not positive in the
period being measured. This is a property of the data, not of any method
here, and it is the single most consequential fact in this result.

(b) HRP IS A RISK ALLOCATOR AND IS BLIND TO EXPECTED RETURN. Its inverse-
variance recursion put 89% of the book on the two LOWEST-volatility
sleeves (crp 0.437 + insider 0.453) and 3.8% on ofi_raw_h7 — the highest-
Sharpe input — purely because crypto is the most volatile. Equal weight,
which does not know about volatility either, happens to keep a full 25%
on that sleeve and therefore wins. So the honest Step 3 answer is not
"the sophistication added nothing": it is that ON THIS PROBLEM THE
SOPHISTICATION ACTIVELY HURT, and monotonically — equal weight beats
inverse-vol beats HRP beats RMT+HRP. RMT vs no-RMT is a rounding
difference (+0.052 vs +0.066), exactly as its zero-signal-eigenvalue
finding implies. Nothing here impugns HRP or RMT as methods; it says that
allocating BY RISK across signals of very unequal Sharpe throws away the
Sharpe, which is what those methods are built to do.

KELLY SAYS HOLD CASH. On the RMT+HRP direction with r_f = 0: full-Kelly
leverage 0.7032x, half-Kelly 0.3516x, zero-growth leverage 1.4063x. But
the growth-optimal fraction, once estimation error is priced with
kelly_sizing's own debiasing, is EXACTLY 0.0 — theta_hat^2 = 0.00272
against N/T_years = 4/5.873 = 0.681, so the debiased theta^2 floors at
zero and c* = 0. The recommendation is zero leverage: do not hold this
book. That is an informative answer, not a failure to produce one.

THE PRE-DECLARED DECISION RULE, APPLIED. Deflation-style sensitivity 0.000
(needed >= 0.90) and null p-value 1.0000 (needed <= 0.05). HONEST
NEGATIVE. Both halves are reported with their own caveats: the pre-
declared sensitivity is dominated by the sigma_SR artifact of section 4A
(the section 4A diagnostic, over the 59 non-hard-excluded specs, gives
0.0458 — still nowhere near 0.90), and the null turned out far more
conservative than section 4 anticipated for a third reason only visible
once it ran (it selects best-of-k on the same window it scores, so its
zero-edge median combined Sharpe is +1.10). Neither caveat is load-
bearing: at +0.05 to +0.30 against a best single input of +0.46, there is
nothing for a strict test to reject that a loose one would not.

THE SENSITIVITY OF SECTION 1 CHANGES NOTHING. Adding
quality_noa_industry_neutral / noa_neutral_ls_h126_median back (the one
genuine judgement call in the hard-exclude list) gives RMT+HRP +0.0658 and
equal weight +0.2814, same ordering, same verdict — and that candidate is
itself -0.0025 over the common window. The exclusion is not load-bearing.

WHAT THIS DOES AND DOES NOT SAY ABOUT THE THESIS. It is evidence against
the strong form — "enough individually-weak edges automatically add up" —
on THIS project's current inventory: four near-orthogonal signals, honestly
measured, combined every way tonight's tools allow, produce a book weaker
than its best constituent. It is NOT a refutation of the general
law-of-large-numbers argument, for a reason that is measurable rather than
rhetorical: the argument needs edges that are positive in the SAME period,
and half of these are not. Four is also a very small N for a law of large
numbers. The concrete implication for the project is a sequencing one —
combination cannot be the thing that rescues a set of individually
sub-significance signals, so the effort belongs upstream, in finding
signals that hold up out of sample, not downstream in the allocator.

===========================================================================
7. INDEPENDENT VERIFICATION PASS (2026-08-29) — written by the verifier,
   not the builder. Sections 1-6 above are untouched.
===========================================================================
Everything below was re-derived from the raw table, the family modules'
own code and the risk modules called directly — not from this module's
wrapper functions or its persisted JSON.

REPRODUCED EXACTLY (independent code, same numbers):
 * Selection: 332 scanned under the canonical-tag rule / 273 hard-excluded
   / 39 threshold failures / 16 not-family-best / the same 4 candidates,
   from an independent SQL + re-implementation of steps 1(a)-(c).
 * sigma_SR 10.6262 over the 332 scanned specs and 0.3200 over the 59
   survivors, recomputed from raw rows (phase_a's 212 specs alone carry
   9.65, min Sharpe -56.76 — the section 4A artifact mechanism confirmed).
 * PSR-vs-zero >= 0.50 <=> in-sample Sharpe >= 0: confirmed against
   deflated_sharpe.py's actual formula (Phi(sr_hat*sqrt(n-1)/sqrt(denom)),
   denom > 0 enforced) and empirically against all 332 rows (zero
   sign/threshold mismatches).
 * All four return series regenerated via each family's own backtest code:
   family-row Sharpes and n_observations match exactly (crp +0.2599/4934,
   cbop +0.4565/2926, insider +0.0699/2893, ofi +0.4617/2154); an
   independently written alignment produced the identical 1480-day window
   and matched the persisted matrix (OFI bit-exact; the yfinance-dependent
   three to <=1.25e-6 absolute, restatement drift).
 * The crux numbers: crp -0.4040 and cbop -0.0654 on the common window.
 * RMT (called directly): correlation eigenvalues 0.9084..1.1047, all
   inside lambda_plus = 1.1067 — zero signal eigenvalues, as reported.
 * HRP weights (crp 0.4367 + insider 0.4528 = 88.95% on the two lowest-vol
   sleeves, ofi 0.0384), all four combined Sharpes, PSRs, the 0.000
   pre-declared sensitivity and the 0.0458 diagnostic.
 * Kelly: theta_hat^2 = 0.00272 < N/T_years = 0.6811, debiased theta^2 = 0,
   growth-optimal fraction exactly 0.0 — hold cash, reproduced.
 * The null control, RE-IMPLEMENTED from section 4's declared text alone
   with the declared seed: median +1.1037 / p95 +1.5427 / p = 1.0000
   (RMT+HRP) and +0.9456 / p = 0.9965 (equal weight) — bit-identical, so
   the shipped null does exactly what its declaration says. The +1.10
   median is real and analytically right: best-of-k selection on the
   scoring window inflates each sleeve to E[max of k] ~ 0.4-0.7
   annualized, and four near-independent sleeves halve the combined vol.
 * The add-back sensitivity run and both hard-exclusion "does real work"
   claims (noa_neutral's best PSR 0.8470 would clear; round_c flat_control
   has 14 clearing specs).

TWO FINDINGS THE BUILDER'S ACCOUNT DID NOT SURFACE, neither changing the
verdict:
 * round_c would be load-bearing even under the canonical edge_spread tag:
   4 of its 30 specs clear PSR >= 0.50 there (positive but cost-degraded,
   best edge DSR 0.03 per commit 214a58c). Without the hard exclusion the
   book would have taken a fifth, cost-dominated candidate.
 * ofi_raw_h7 — the selected best-performing input — carries its own
   module's caution: "the weekly RAW secondary is far more window-sensitive
   (+0.462 at 30 weeks, +0.930 at 4 weeks) ... a reason to distrust the
   raw spec's apparently better number". That is a disclosed sensitivity
   note, not one of section 1(a)'s three disqualifying categories (the
   module keeps the spec as the thesis's own pre-declared control), so its
   eligibility is correct under the frozen rule — but a reader should know
   the combination's single best input is also its most window-fragile.
   Removing it could only make the combination worse, so the honest
   negative does not rest on it.

ON THE ORDERING CLAIM ITSELF (the "frozen before any combined number
existed" narrative): it could NOT be independently confirmed. The file was
never git-committed or staged before results — the phrase "committed to
this file" in the preamble means "written into this file", not a git
commit — and the entire build ran inside one ~30-minute window (worktree
created ~07:24 local, rows persisted 07:49:39 and 07:49:59, tests saved
07:52, module saved 07:54), leaving no artifact that separates the
writing of sections 1-5 from the computing of section 6. What IS
structurally verifiable, and was verified: the verdict path in the code
reads only the pre-declared 332-spec sensitivity; the 59-spec number
lives in separately-labelled diagnostic fields and feeds nothing; and the
pre-declared calculation was kept even though it returned the maximally
inconvenient 0.000 — the direction of any self-serving revision would
have been the swap that visibly did not happen. Both numbers were
recomputed from raw data by this pass. Future pre-declarations should be
committed (in git, with a hash) before the first result is computed, so
this caveat does not have to be written again.

ONE TEST-SUITE GAP, FOUND BY MUTATION AND FIXED: deleting a hard-exclusion
failed a test (good), but mutating PSR_SELECTION_THRESHOLD from 0.50 to
0.40 passed all 32 tests — every threshold test referenced the constant
instead of the declared value. A pinned-constants test was added so a
revision of any pre-declared value now fails loudly.

===========================================================================
8. THE 2026-08-30 CHANGE TO THE SELECTION FRAMEWORK — WRITTEN AFTER
   RUNNING STEP 1 ON THE CORRECTED TABLE AND BEFORE COMPUTING ANY NEW
   COMBINED NUMBER (the section 4A convention: the sequence is recorded,
   not smoothed over). Sections 1-7 above are untouched.
===========================================================================
Between the section 6 run and this section, three commits changed what is
known about the cost evidence behind two of section 1's hard-exclusions:

 * df8a933 — the shared EDGE spread estimator overstates mega/large-cap
   half-spreads ~10-40x at this project's settings (the source paper's own
   disclosed limitation, not an implementation bug).
 * acc3ac8 — an independent build sharpened that to "blind, not biased":
   a ZERO-true-spread placebo reproduces the real-data outputs, and the
   estimate regresses on volatility at R^2 = 0.96, not on true spread.
 * dd34094 — both edge_spread-based exclusions re-audited under a
   pre-registered (sha256-frozen BEFORE any result existed),
   independently-sourced realistic cost calibration, itself adversarially
   verified with exact clearing-set matches:
     - round_c: the IDENTICAL 14/30 specs clear psr_vs_zero >= 0.50 under
       ALL FIVE scenarios (flat 1.0/2.0/3.5bp, the 5bp control, and
       EDGE-as-ranker rescaled to a realistic level). Cost is not a
       binding constraint for these 21-126-day-hold books at any
       defensible level. The recorded category-(ii) evidence for its
       exclusion IS INVALIDATED.
     - phase_a_intraday_expanded: the recorded "zero specs clear" leg is
       also wrong (9/212 clear at the best-estimate calibration), but the
       exclusion's noise half survives IN FULL: DSR ~ 0 under every
       scenario (best 0.004), 197/212 negative everywhere, and the
       clearing set is cost-fragile within the plausible bracket
       (15 -> 9 -> 2 across low/mid/high).

DECISIONS, made with the project owner's explicit sign-off and recorded
here before the re-run:
 (a) round_c's hard-exclusion is REMOVED from HARD_EXCLUSIONS. Its
     recorded disqualifying evidence no longer exists; what remains is an
     honest negative (best standalone DSR 0.24 against the 0.90
     standard), and section 1 declares honest negatives ELIGIBLE — they
     are exactly the population this experiment is about.
 (b) phase_a_intraday_expanded's hard-exclusion STANDS. Re-admitting it
     was not put to the owner, deliberately: its re-audit outcome is
     genuinely fragile, unlike round_c's clean reversal. Only its
     recorded REASON is corrected, to the evidence that actually survives
     (the noise/fragility characterization), so the record no longer
     cites the invalidated "zero specs clear" claim.
 (c) CANONICAL_RUN_TAGS moves BOTH families off the discredited
     edge_spread tag onto the corrected calibration's own declared
     best-estimate scenarios (mid_2bp for round_c, mid_tier for phase_a).
     For round_c this now matters for the combination math, not just the
     record: the mid_2bp rows are what its candidate spec is selected
     from and reproduced against.

KNOWN SELECTION-LEVEL CONSEQUENCES, computed from the table before any
combined number (the same position in the sequence section 4A occupied):
 * n_scanned stays 332 — the corrected tags carry the same spec counts
   (30 round_c, 212 phase_a) as the tags they replace.
 * Step 1 now selects FIVE candidates: the four of section 6 unchanged,
   plus round_c/lps_intraday_l252_h63 (Sharpe +0.2862, PSR(0) 0.8328
   under mid_2bp — round_c's best spec under every scenario).
 * The pre-declared 332-spec sigma_SR falls from 10.63 to 2.08
   annualized. The section 4A artifact is REDUCED, not gone: phase_a's
   deeply-negative siblings still dominate the dispersion even at
   realistic costs (its mid_tier Sharpes run to -10.9 on thin patterns).
   The pre-declared sensitivity therefore still faces an SR0 of several
   annualized Sharpe units and will read ~0 for any plausible combined
   book; the 4A diagnostic (now 89 non-hard-excluded specs, sigma_SR
   0.296) remains the informative companion number. Both are computed
   and reported exactly as before; the decision rule still reads the
   pre-declared one.
 * The null control's round_c sleeve mirrors best-of-30 selection, the
   largest k_f in the book — the null gets HARDER to beat, not easier.

Nothing else changes: same threshold, same one-spec-per-family rule, same
pipeline, same baselines, same null design and seed, same decision rule,
same add-back sensitivity. Section 9 below was appended only after the
re-run completed; nothing above it was edited afterwards.

===========================================================================
9. RECOMBINATION RESULTS (2026-08-30) — APPENDED AFTER SECTION 8 AND THE
   COMPLETED RE-RUN
===========================================================================
Run 2026-08-30 via run_multi_signal_recombination.py (backend/ root —
committed this time, per section 7's durable-artifact ask). Persisted under
family_key "multi_signal_combination", run_tags
"multi_signal_recombination_2026-08-30" (primary, 4 rows) and
"multi_signal_recomb_sensitivity_add_noa_neutral_2026-08-30" (the section 1
add-back, 4 rows), each row carrying its combined daily series and the
primary rmt row the aligned 5-candidate matrix. Full record:
data/research_runs/multi_signal_recombination_2026-08-30.txt.

WHAT STEP 1 SELECTED: 332 scanned / 243 hard-excluded / 55 threshold
failures / 29 not-family-best / 5 selected — the section 6 four unchanged
plus round_c/lps_intraday_l252_h63 (+0.2862, PSR(0) 0.8328), exactly as
section 8 derived. All five series were regenerated from their families'
own code and reproduce the persisted rows: the four session-calendar
sleeves to +/-0.00000 Sharpe at the log's five decimals, OFI to 3.9e-16
once compared on its own 365-day calendar. (The run log's OFI line shows
"drift -0.078": the diagnostic print annualized the native 24/7 series at
252 days — 0.4617 x sqrt(252/365) = 0.3836, the exact printed value. An
annualization-basis artifact in the CHECK only, fixed in the runner; the
pipeline itself compounds onto the session calendar and was unaffected.)

THE WINDOW MOVED BY ONE DAY: 2020-10-05 .. 2026-08-25, 1479 common days
(section 6: .. 2026-08-26, 1480). round_c's archived panel ends
2026-08-25 — its pinned END of 2026-08-26 is yfinance-exclusive — so the
intersection loses the final session. Every comparison to section 6 below
is across windows differing by that one day.

THE COMBINATION IMPROVED ACROSS THE BOARD — AND STILL TRAILS ITS OWN BEST
INPUT. Annualized Sharpe over the common window (section 6 in brackets):

    equal_weight        +0.4347  PSR(0) 0.852   [+0.3015]
    inverse_volatility  +0.3263  PSR(0) 0.784   [+0.1765]
    rmt_denoised_hrp    +0.1484  PSR(0) 0.640   [+0.0522]
    hrp_no_denoise      +0.1414  PSR(0) 0.634   [+0.0657]
    best single input   +0.4589  (ofi_raw_h7)   [+0.4600]

The new sleeve is additive everywhere: lps_intraday_l252_h63 runs +0.3617
INSIDE the window, so every scheme gains 0.08-0.15 of Sharpe, while the
section 6 drags are unchanged (crp -0.4038 and cbop -0.0610 in-window).
The equal-weight gap to the best single input narrows from -0.158 to
-0.024 — but it does not close, and the section 6(a) diagnosis stands:
two of the five sleeves are negative in the period actually traded.

THE CORRELATION PREMISE WEAKENED, MEASURABLY. The new sleeve is the first
candidate with visible cross-correlations: lps vs crp -0.197 and lps vs
cbop +0.201 (every other pair stays within +/-0.067), and RMT now finds
ONE signal eigenvalue (lambda_plus 1.1197) where section 6 found zero.
Five bets, no longer statistically indistinguishable from independent —
unsurprising, since round_c and cbop share the S&P 500 universe. HRP
still allocates by risk: 83.7% on the two lowest-vol sleeves
(crp 0.4110 + insider 0.4263) and 6.1% on the new one, which is why the
HRP variants again trail equal weight, now by ~0.29 of Sharpe.

KELLY STILL SAYS HOLD CASH: full-Kelly leverage 2.139x on the RMT+HRP
direction, but theta_hat^2 = 0.0220 against N/T_years = 5/5.869 = 0.852,
so the debiased theta^2 floors at zero and the growth-optimal fraction is
exactly 0.0. Five sleeves over 5.9 years is still far too little sample
for the measured edge to survive its own estimation risk.

THE PRE-DECLARED RULE, APPLIED: deflation-style sensitivity 0.000 (needed
>= 0.90; sigma_SR 2.0774 over the 332 scanned specs puts the best-of-332
noise benchmark at 6.08 annualized by section 4A's own arithmetic
(deflated_sharpe.expected_max_sharpe_under_noise(2.0774, 332); the
figure first written here, "near 5.9", was corrected to the helper's
actual output by the section 10 verification pass) — reduced ~5x from
the artifact-driven 31.11, still unclearable, and now
dominated by phase_a's REAL sibling dispersion under realistic costs
rather than by an estimator artifact) and selection-mirroring null
p = 1.0000 on both weightings (needed <= 0.05; the null's best-of-30
round_c sleeve raised its zero-edge median combined Sharpe to +1.2876
from section 6's +1.1037 — harder, exactly as section 8 predicted).
HONEST NEGATIVE, by the same rule as section 6. The 4A diagnostic reads
0.0767 on RMT+HRP (section 6: 0.0458) and 0.2335 on equal weight — still
nowhere near 0.90.

SENSITIVITY (noa_neutral added back, six sleeves, pre-declared):
equal_weight +0.4168, inverse_volatility +0.2931, rmt_denoised_hrp
+0.1314, hrp_no_denoise +0.1232; the added sleeve is itself -0.0002 over
the window. Same ordering, same HONEST NEGATIVE. Still not load-bearing.

WHAT THE RE-ADMISSION DID AND DID NOT CHANGE. It made every combination
meaningfully better, which is what re-admitting a sleeve that is positive
in the window had to do — the correction was real and its effect is
visible in every row. It did NOT produce a combined edge this project can
certify: the book still trails its best constituent, both halves of the
pre-declared significance rule fail as decisively as before, and the
estimation-risk-debiased Kelly fraction is still zero. The binding
constraint remains exactly where section 6 located it — upstream, in
signals that stay positive in the same period — and adding one more
honest sleeve moved the book closer to, not past, that ceiling.

===========================================================================
10. INDEPENDENT VERIFICATION PASS (2026-08-30) — written by the verifier,
    not the builder. Sections 1-9 above are untouched except for the one
    numeric correction named in (f) below, which is flagged in place.
===========================================================================
Everything in sections 8-9 was re-derived from the code and the persisted
rows without trusting the builder's run log. What was checked and found:

(a) NO THUMB ON THE SCALE. The code body was diffed against dbb1edb's
    frozen version, not merely against this branch's parent. The ONLY
    changes are: round_c's HardExclusion removed (replaced by a dated,
    cited comment), phase_a's reason text rewritten, the two
    CANONICAL_RUN_TAGS entries retagged, and the round_c sleeve added to
    regenerate_candidate_series with ROUND_C_REPRO_END/ROUND_C_MID_COST_BPS
    and its EXPECTED_OBSERVATIONS entry. Docstring sections 1-7 are
    BYTE-IDENTICAL to dbb1edb. PSR_SELECTION_THRESHOLD (0.50),
    COMBINED_SIGNIFICANCE_BAR (0.90), COMBINED_NULL_P_VALUE_BAR (0.05),
    NULL_CONTROL_DRAWS (2000), NULL_CONTROL_SEED (20260829),
    SENSITIVITY_ADD_BACK, NON_EQUITY_CALENDAR_SPECS, the four weighting
    schemes, the alignment rule and the decision rule are all unchanged.
    phase_a_intraday_expanded IS still in HARD_EXCLUSIONS (5 entries; only
    round_c left), as section 8(b) says.

(b) THE NUMBERS REPRODUCE. Recomputed from the persisted candidate matrix
    with plain numpy — not through this module's own metric helpers — all
    five single-sleeve in-window Sharpes, all ten pairwise correlations,
    all four combined Sharpes, and the equal-weight and inverse-vol
    weights from scratch: every one matches to <= 1e-6, and each row's
    stored combined series equals weights @ matrix to 0.0 exactly. Kelly
    reproduces (mu_ann/vol_ann^2 = 2.1391). Both persisted run_tags exist
    with 4 rows each and agree with the run log.

(c) THE NEGATIVE-IN-WINDOW CLAIM IS A DATA PROPERTY, NOT A BUG. This was
    the highest-risk claim and got the hardest look. All five raw series
    were regenerated and their FULL-window Sharpes reproduce the persisted
    family rows (crp +0.2599, cbop +0.4565, insider +0.0699, ofi +0.4617
    at 365/yr, round_c +0.2862). Every index is tz-naive, midnight-
    normalized, monotonic and unique — no local-vs-UTC exposure. The
    1479-day intersection was then recomputed HERE, twice: once with
    DatetimeIndex.intersection and once via a wholly separate naive
    date-STRING path. Both give the identical date set to the persisted
    matrix, and both give crp -0.4038 and cbop -0.0610. The sign flip is
    real: these sleeves earn their full-sample Sharpe outside 2020-2026.

(d) THE ONE-DAY WINDOW LOSS IS EXPLAINED AND BENIGN. round_c's panel ends
    2026-08-25 while crp ends 08-26 and cbop/insider 08-27, so round_c
    binds the right edge — the yfinance-exclusive-end account in section 9
    is correct, and the same END convention holds for every other sleeve.
    Confirmed the section 6 -> section 9 Sharpe moves (crp -0.4040 ->
    -0.4038, cbop -0.0654 -> -0.0610, ofi +0.4600 -> +0.4589) are fully
    accounted for by dropping 2026-08-26 plus <= 1.5e-6 of Yahoo
    adjusted-close restatement; OFI is bit-identical on the shared dates.

(e) THE SELECTION AND RETAG ARE JUSTIFIED, NOT ARBITRARY. Under mid_2bp
    exactly 14/30 round_c specs clear PSR >= 0.50, and the clearing SET is
    identical under all five corrected scenarios; lps_intraday_l252_h63 is
    round_c's best by both PSR and Sharpe in every one, spanning
    0.277-0.289 — so the mid_2bp choice cannot have picked the candidate.
    n_scanned is 332 under both old and new tags; sigma_SR is 10.6262 old
    vs 2.0774 new, and the stage counts 332/243/55/29/5 reproduce exactly.
    phase_a's corrected reason text checks out on the rows: 9/212 clear at
    mid_tier, 15 -> 9 -> 2 across low/mid/high, best DSR 0.0043, and 197
    specs negative in every scenario.

(f) ONE CORRECTION MADE. Section 9 and the run report first put the
    best-of-332 noise benchmark "near 5.9 annualized". The module's own
    expected_max_sharpe_under_noise(2.0774, 332) returns 6.0810 (and
    31.1053 at the old sigma_SR, not "~30"). Corrected in both places.
    Nothing downstream moves: the sensitivity is 0.000 either way.

(g) TESTS AND LINT RUN INDEPENDENTLY. Full suite 2592 passed / 1 skipped
    (7m32s); this module's file 34/34. The two new tests genuinely pin the
    new behaviour — one asserts round_c is absent from HARD_EXCLUSIONS and
    that a sub-threshold sibling now fails on the THRESHOLD stage rather
    than on an exclusion, the other pins both corrected run_tags and
    asserts no "edge_spread" tag survives anywhere in CANONICAL_RUN_TAGS.
    The pinned-constants test from section 7 is intact. ruff clean.

(h) PROVENANCE HOLDS. The run report's three sha256 hashes were checked,
    including by reconstructing the pre-results module (this file minus
    section 9) — it hashes to the recorded
    599839e76648da0c4463a415623ddb344103e0220876aaaf0c8194844f14194c.
    Section 9 really was appended after the run, with sections 1-8 frozen.

VERDICT ON THE VERDICT: the re-admission is correctly executed and the
HONEST NEGATIVE stands. The combined book (best +0.4347 equal-weight)
remains below its own best input (+0.4589), both halves of the
pre-declared rule fail, and the debiased Kelly fraction is 0.0. The
reason for the negative has genuinely changed — it is now the
shared-window problem in (c), not the discredited cost model — and the
record says so without overclaiming the re-admission as progress.
NOT INDEPENDENTLY CHECKED, and inherited rather than introduced here: the
delisted-ticker coverage gap that flatters every equity sleeve
(round_c resolves 625/768 point-in-time members), and the upstream
correctness of the dd34094 cost calibration itself, which this pass took
as given from its own verified re-audit.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.models.cross_sectional_trial_result import CrossSectionalTrialResult
from app.services.research_lab.deflated_sharpe import (
    DeflatedSharpeResult,
    compute_deflated_sharpe,
)
from app.services.research_lab.global_effective_n import dsr_n_trials
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR, sharpe_ratio
from app.services.risk.hrp_optimizer import compute_hrp_weights_from_returns
from app.services.risk.kelly_sizing import (
    DEFAULT_KELLY_FRACTION,
    KellyLeverageResult,
    compute_kelly_leverage_from_returns,
    growth_optimal_kelly_fraction,
)

MULTI_SIGNAL_FAMILY = "multi_signal_combination"

# Section 2's threshold. One number, one comparison, applied to every
# non-hard-excluded persisted spec.
PSR_SELECTION_THRESHOLD = 0.50

# Section 4's null control. Both frozen before it ran.
NULL_CONTROL_DRAWS = 2000
NULL_CONTROL_SEED = 20260829

# Section 4's decision rule.
COMBINED_SIGNIFICANCE_BAR = 0.90
COMBINED_NULL_P_VALUE_BAR = 0.05


@dataclass(frozen=True)
class HardExclusion:
    """One hard-exclude decision from section 1, with the evidence that
    justifies it recorded at the point of decision rather than in prose
    somewhere else.

    `spec_ids` empty means the whole family is excluded; a non-empty tuple
    excludes only those specs and leaves the family's other specs eligible
    (which is how the seasonality placebo is handled)."""

    family_key: str
    spec_ids: tuple[str, ...]
    category: str  # "artifact" | "untradeable" | "imperative"
    source_file: str
    reason: str


# ---------------------------------------------------------------------------
# Section 1(a) applied. Every entry below was confirmed by reading the named
# file in this worktree, not taken from a brief. Line references are to the
# module docstrings as of commit 524a8db.
# ---------------------------------------------------------------------------

HARD_EXCLUSIONS: tuple[HardExclusion, ...] = (
    HardExclusion(
        family_key="quality_noa",
        spec_ids=(),
        category="artifact",
        source_file="app/services/research_lab/cross_sectional_quality.py",
        reason=(
            "Its own docstring: 'VERDICT — DO NOT TREAT AS VALIDATED EDGE: likely "
            "sector-tilt artifact'. The independent verification pass confirmed the "
            "sector-composition diagnosis quantitatively (a static long-financials/"
            "tech, short-REIT portfolio out-earned every raw NOA spec). Categories "
            "(i) and (iii)."
        ),
    ),
    HardExclusion(
        family_key="quality_noa_industry_neutral",
        spec_ids=(),
        category="imperative",
        source_file="app/services/research_lab/cross_sectional_quality_neutral.py",
        reason=(
            "This family is NOT excluded because the raw NOA family is an artifact — "
            "it is a separate, legitimately pre-declared family and that would be the "
            "wrong reason. It is excluded on its OWN final verdict: 'VERDICT — HONEST "
            "NEGATIVE, and the final answer to the NOA question on this universe ... "
            "Do not trade NOA in any form on this universe; do not re-test it here "
            "without new data or a genuinely different hypothesis.' That is an "
            "explicit imperative, category (iii), and it is the reason recorded here. "
            "Because this exclusion is the one genuine judgement call in section 1 "
            "(its best spec would otherwise clear the threshold), a pre-declared "
            "sensitivity that ADDS it back is run and reported regardless of outcome "
            "— see SENSITIVITY_ADD_BACK."
        ),
    ),
    HardExclusion(
        family_key="funding_carry",
        spec_ids=(),
        category="untradeable",
        source_file="app/services/research_lab/cross_sectional_funding_carry.py",
        reason=(
            "Its own same-day adversarial verification: 'CORRECTED VERDICT: ... NOT a "
            "validated deployable edge', 'THE BEST SPEC CANNOT TRADE TODAY' (100% in "
            "cash since 2025-03; eligible names decayed 66 -> 27), 'ALL four f10 specs "
            "are untradeable at today's breadth', and 2026 YTD every spec that could "
            "still form a book lost 34-47%. Categories (ii) and (iii)."
        ),
    ),
    HardExclusion(
        family_key="same_calendar_month_seasonality",
        spec_ids=("seasonality_other_month_placebo_20y_ls",),
        category="artifact",
        source_file="app/services/research_lab/cross_sectional_seasonality.py",
        reason=(
            "This ONE spec only. It is the family's pre-declared negative control "
            "('the arm that was pre-declared as the thing that must NOT work'), it is "
            "the family's single best number, and its own module concludes the "
            "positive is 'much better explained by \"this cross-section is exhibiting "
            "plain long-horizon mean reversion, which the other-month average happens "
            "to proxy\" than by anything seasonal'. Category (i). The family's seven "
            "same-month specs are NOT hard-excluded — they are all negative and fail "
            "section 2's threshold on their own."
        ),
    ),
    HardExclusion(
        family_key="phase_a_intraday_expanded",
        spec_ids=(),
        category="untradeable",
        source_file="app/services/research_lab/intraday_patterns.py",
        reason=(
            "Cost-fragile noise — REASON TEXT CORRECTED 2026-08-30 (see docstring "
            "section 8; the exclusion DECISION is unchanged). The originally recorded "
            "EDGE-model leg ('212/212 worse ... under the edge_spread run_tag, zero "
            "specs clear psr_vs_zero >= 0.50', commit 214a58c) is INVALIDATED: commit "
            "dd34094's independently verified corrected-cost re-audit shows 9/212 "
            "specs clear at the sourced best-estimate calibration. What the re-audit "
            "CONFIRMS, and what this exclusion now rests on: the module's own "
            "characterization ('204/212 patterns had a negative pooled raw Sharpe ... "
            "Same cost-dominated-noise signature as the pilot') survives in full — "
            "DSR ~ 0 under every corrected scenario (best 0.004), 197/212 patterns "
            "negative at every defensible cost level, and the clearing set is fragile "
            "within the plausible cost bracket (15 -> 9 -> 2 across low/mid/high) and "
            "concentrated in one volume_climax/day-of-week pocket. With n_trials=212 "
            "and this family's sibling dispersion, a +0.8 in-sample Sharpe is exactly "
            "what the best of 212 zero-edge trials looks like. Category (ii)."
        ),
    ),
    # round_c is DELIBERATELY ABSENT from this tuple as of 2026-08-30. It was
    # hard-excluded here from this module's creation (category (ii),
    # "cost-dominated under realistic per-ticker costs", citing the 2026-08-28
    # EDGE re-audit of commit 214a58c: 30/30 worse, ~36bp realized charge).
    # Commits df8a933 and acc3ac8 then established that the EDGE estimator is
    # BLIND at this universe's spread regime (its output regresses on
    # volatility at R^2 = 0.96, and a zero-true-spread placebo reproduces it),
    # and commit dd34094's pre-registered, independently verified re-audit
    # showed the IDENTICAL 14/30 specs clear psr_vs_zero >= 0.50 under every
    # defensible cost scenario (flat 1.0/2.0/3.5bp, the 5bp control, and
    # EDGE-as-ranker rescaled to a realistic level) — the recorded exclusion
    # evidence measured the estimator's noise floor, not real trading cost,
    # and is invalidated. With the disqualifying verdict gone, round_c is an
    # ordinary honest negative (best standalone DSR 0.24 against the 0.90
    # standard), and section 1's own rule says honest negatives are ELIGIBLE.
    # Removed with the project owner's explicit sign-off; see docstring
    # section 8 and data/research_runs/edge_cost_reaudit_corrected_2026-08-30
    # .txt for the full evidence chain.
)

# The one pre-declared sensitivity of section 1: re-run everything with this
# family added back, and report both, whatever comes out. Declared with the
# exclusions, before any combined number existed.
SENSITIVITY_ADD_BACK = "quality_noa_industry_neutral"

# Section 2's run-tag provenance rule, applied. Only families with more than
# one run_tag need an entry; everything else has exactly one.
CANONICAL_RUN_TAGS: dict[str, str] = {
    # cross_sectional_funding_carry.py's docstring: the *_verified_* tags are
    # the corrected numbers, persisted "alongside the originals". Recorded for
    # completeness; the family is hard-excluded anyway.
    "funding_carry": "funding_carry_verified_excl_collapse3_2026-08-29",
    # BOTH TAGS CORRECTED 2026-08-30 (see docstring section 8). These two
    # families previously pointed at "edge_cost_reaudit_2026-08-28_edge_spread"
    # on the claim (commit 214a58c) that edge_spread was "the realistic
    # per-ticker cost model". That claim is now known to be WRONG: commits
    # df8a933/acc3ac8 established the EDGE estimator is blind at this
    # universe's spread regime (~10-40x overstatement; output regresses on
    # volatility, not spread), so the edge_spread rows record the estimator's
    # noise floor, not realistic trading costs. The canonical tags now name
    # commit dd34094's corrected-cost re-audit at its own pre-registered
    # BEST-ESTIMATE calibration (externally sourced: Hagstromer JFE 2021,
    # Nasdaq/Mackintosh 2024, tick-floor arithmetic):
    #   * round_c -> mid_2bp (flat 2.0bp one-way). Not merely a record-keeping
    #     choice anymore: round_c is no longer hard-excluded, so this tag's
    #     rows are what its candidate spec is selected from and reproduced
    #     against. The choice is immaterial to WHICH specs clear (the same 14
    #     clear under all five scenarios, verified set-identical) and nearly
    #     immaterial to the numbers (best-spec Sharpe spans 0.277-0.289
    #     across scenarios); mid_2bp is simply the calibration's declared
    #     best estimate.
    #   * phase_a_intraday_expanded -> mid_tier (large 1.5bp / mid-small
    #     10.0bp, tick-floored). The family stays hard-excluded, but the
    #     record — including the sigma_SR that sections 4(3)/4A compute over
    #     ALL scanned specs — should rest on realistic costs, not on the
    #     discredited estimator. NOTE the consequence, disclosed in section 8:
    #     this retag moves the pre-declared 332-spec sigma_SR from 10.63 to
    #     2.08 annualized, because the edge_spread rows' -56.8-Sharpe
    #     artifacts leave the scan.
    "phase_a_intraday_expanded": "edge_cost_reaudit_corrected_2026-08-30_mid_tier",
    "round_c": "edge_cost_reaudit_corrected_2026-08-30_mid_2bp",
}


@dataclass(frozen=True)
class ScannedSpec:
    """One persisted spec as the selection rule sees it."""

    family_key: str
    run_tag: str
    trial_id: str
    sharpe_annualized: float
    dsr: float | None
    psr_vs_zero: float | None
    n_observations: int
    n_trials: int


@dataclass(frozen=True)
class SelectionDecision:
    """Why one spec is in or out. Every scanned spec gets one of these, so
    the record is complete rather than a list of winners."""

    spec: ScannedSpec
    selected: bool
    stage: str  # "hard_exclude" | "threshold" | "not_family_best" | "selected"
    reason: str


@dataclass(frozen=True)
class CandidateSelection:
    """The frozen output of Step 1."""

    selected: tuple[ScannedSpec, ...]
    decisions: tuple[SelectionDecision, ...]
    n_scanned: int
    # Section 4(2)'s trial count and its sigma_SR: every spec the rule
    # scanned, i.e. the size of the search these candidates came out of.
    scanned_sharpes: tuple[float, ...]
    # Section 4A's diagnostic, NOT pre-declared: the same quantities over
    # only the specs that survived section 1(a).
    surviving_sharpes: tuple[float, ...] = ()

    @property
    def n_trials_for_deflation(self) -> int:
        return self.n_scanned

    @property
    def sigma_sr_annualized(self) -> float:
        return float(np.std(np.asarray(self.scanned_sharpes, dtype=float), ddof=1))

    @property
    def n_trials_diagnostic(self) -> int:
        return len(self.surviving_sharpes)

    @property
    def sigma_sr_diagnostic(self) -> float:
        return float(np.std(np.asarray(self.surviving_sharpes, dtype=float), ddof=1))


def _hard_exclusion_for(family_key: str, trial_id: str) -> HardExclusion | None:
    for rule in HARD_EXCLUSIONS:
        if rule.family_key != family_key:
            continue
        if not rule.spec_ids or trial_id in rule.spec_ids:
            return rule
    return None


def load_scanned_specs(db: Session, *, exclude_families: tuple[str, ...] = ()) -> list[ScannedSpec]:
    """Every persisted spec, reduced to one row per (family, trial) via the
    canonical run-tag rule of section 2.

    `exclude_families` exists ONLY for the pre-declared sensitivity of
    section 1 (running the pipeline with SENSITIVITY_ADD_BACK put back), and
    is never used to drop a family on the basis of its numbers."""
    # THIS MODULE'S OWN PERSISTED ROWS ARE NOT CANDIDATES. Found the first
    # time the pipeline was re-run after persisting: the combined books land
    # in the same table under MULTI_SIGNAL_FAMILY, so without this filter a
    # second run would feed its own output back in as a fifth "signal" and
    # its n_scanned would grow every run. Not a selection judgement — a
    # combination of signals cannot be one of its own inputs.
    rows = [
        r
        for r in db.query(CrossSectionalTrialResult).all()
        if r.family_key != MULTI_SIGNAL_FAMILY
    ]
    by_family_tags: dict[str, set[str]] = {}
    for row in rows:
        by_family_tags.setdefault(row.family_key, set()).add(row.run_tag)

    chosen_tag: dict[str, str] = {}
    for family, tags in by_family_tags.items():
        if len(tags) == 1:
            chosen_tag[family] = next(iter(tags))
            continue
        declared = CANONICAL_RUN_TAGS.get(family)
        if declared is None or declared not in tags:
            raise ValueError(
                f"family {family!r} has {len(tags)} run_tags {sorted(tags)} and no "
                "entry in CANONICAL_RUN_TAGS naming the canonical one — refusing to "
                "guess, because guessing here would silently pick between two "
                "recordings of different numbers."
            )
        chosen_tag[family] = declared

    specs: list[ScannedSpec] = []
    for row in rows:
        if row.family_key in exclude_families:
            continue
        if row.run_tag != chosen_tag[row.family_key]:
            continue
        specs.append(
            ScannedSpec(
                family_key=row.family_key,
                run_tag=row.run_tag,
                trial_id=row.trial_id,
                sharpe_annualized=float(row.sharpe_annualized),
                dsr=row.dsr,
                psr_vs_zero=row.psr_vs_zero,
                n_observations=int(row.n_observations),
                n_trials=int(row.n_trials),
            )
        )
    specs.sort(key=lambda s: (s.family_key, s.trial_id))
    return specs


def select_candidates(specs: list[ScannedSpec]) -> CandidateSelection:
    """Steps 1(a), 1(b) and 1(c), in that order, with a decision recorded for
    every scanned spec.

    Pure and deterministic: same table, same list, every time."""
    decisions: list[SelectionDecision] = []
    survivors: list[ScannedSpec] = []

    for spec in specs:
        rule = _hard_exclusion_for(spec.family_key, spec.trial_id)
        if rule is not None:
            decisions.append(
                SelectionDecision(
                    spec=spec,
                    selected=False,
                    stage="hard_exclude",
                    reason=f"[{rule.category}] {rule.source_file}: {rule.reason}",
                )
            )
            continue
        psr = spec.psr_vs_zero
        if psr is None or psr < PSR_SELECTION_THRESHOLD:
            decisions.append(
                SelectionDecision(
                    spec=spec,
                    selected=False,
                    stage="threshold",
                    reason=(
                        f"psr_vs_zero={psr!r} < {PSR_SELECTION_THRESHOLD} "
                        "(section 2's single pre-declared threshold)"
                    ),
                )
            )
            continue
        survivors.append(spec)

    # Step 1(c): one spec per family, by the same criterion, deterministic
    # tie-break.
    best_by_family: dict[str, ScannedSpec] = {}
    for spec in survivors:
        current = best_by_family.get(spec.family_key)
        key = (spec.psr_vs_zero or 0.0, spec.sharpe_annualized, [-ord(c) for c in spec.trial_id])
        if current is None:
            best_by_family[spec.family_key] = spec
            continue
        current_key = (
            current.psr_vs_zero or 0.0,
            current.sharpe_annualized,
            [-ord(c) for c in current.trial_id],
        )
        if key > current_key:
            best_by_family[spec.family_key] = spec

    for spec in survivors:
        winner = best_by_family[spec.family_key]
        if spec is winner:
            decisions.append(
                SelectionDecision(
                    spec=spec,
                    selected=True,
                    stage="selected",
                    reason=(
                        f"cleared psr_vs_zero >= {PSR_SELECTION_THRESHOLD} "
                        f"({spec.psr_vs_zero:.4f}) and is family {spec.family_key}'s "
                        "best surviving spec by that same criterion"
                    ),
                )
            )
        else:
            decisions.append(
                SelectionDecision(
                    spec=spec,
                    selected=False,
                    stage="not_family_best",
                    reason=(
                        f"cleared the threshold ({spec.psr_vs_zero:.4f}) but "
                        f"{winner.trial_id} is family {spec.family_key}'s best "
                        f"({winner.psr_vs_zero:.4f}) — step 1(c), one spec per family"
                    ),
                )
            )

    selected = sorted(best_by_family.values(), key=lambda s: s.family_key)
    decisions.sort(key=lambda d: (d.spec.family_key, d.spec.trial_id))
    return CandidateSelection(
        selected=tuple(selected),
        decisions=tuple(decisions),
        n_scanned=len(specs),
        scanned_sharpes=tuple(s.sharpe_annualized for s in specs),
        surviving_sharpes=tuple(
            d.spec.sharpe_annualized for d in decisions if d.stage != "hard_exclude"
        ),
    )


# ---------------------------------------------------------------------------
# Regenerating the selected specs' return series.
#
# The persisted full_result_json holds summary statistics only — no return
# stream — so each selected spec's daily net series has to be recomputed by
# its own family's code. Each family's screening ENTRYPOINT throws the
# backtest object away (verified: QualityScreeningSummary,
# InsiderScreeningSummary, CrpScreeningSummary and OfiScreeningSummary all
# carry scalar result rows only, and the CrossSectionalBacktestResult /
# InsiderBacktestResult / CrpBacktestResult / OfiBacktest objects are
# locals inside the screen_* functions), so each series is regenerated by
# calling that family's own lower-level backtest function with the same
# config the entrypoint would have built.
#
# EVERY `end` DATE BELOW IS PINNED, not date.today(). Each family's
# entrypoint defaults `end` to today, and yfinance/Binance `end` is
# exclusive, so a re-run on a later day silently lengthens the panel and
# moves the Sharpe. The pinned values are the ones that reproduce the
# persisted rows' n_trading_days exactly, and each is asserted below.
# ---------------------------------------------------------------------------

# The dates the persisted runs used, recovered from each row's own
# n_trading_days and computed_at and confirmed by reproduction.
CRP_REPRO_END = date(2026, 8, 27)
QUALITY_REPRO_END = date(2026, 8, 28)
INSIDER_REPRO_END = date(2026, 8, 28)
OFI_REPRO_END = date(2026, 8, 29)
# round_c (re-admitted 2026-08-30, docstring section 8): the corrected
# re-audit's window end, pinned in run_edge_cost_reaudit_round_c.py and
# identical to the archived original run's. Its cost rate MUST match the
# canonical mid_2bp run_tag's configuration (flat 2.0bp one-way), or the
# regenerated series would not be the series the candidate was selected on.
ROUND_C_REPRO_END = date(2026, 8, 26)
ROUND_C_MID_COST_BPS = 2.0

# n_trading_days each regenerated series MUST have, from the persisted rows.
# Asserted rather than logged: a silently shorter or longer series would
# change the alignment window and every number downstream.
EXPECTED_OBSERVATIONS = {
    "crp_realized_21d_h63": 4934,
    "cbop_ls_h63": 2926,
    "insider_opp_buy_h21_c2_equal": 2893,
    "ofi_raw_h7": 2154,
    "lps_intraday_l252_h63": 2924,
}

# The crypto family is the only selected candidate whose native calendar is
# not the equity session calendar (24/7/365 — see metrics.CALENDAR_DAYS_PER_
# YEAR). Section 3's compounding rule applies to exactly this one.
NON_EQUITY_CALENDAR_SPECS = ("ofi_raw_h7",)


def regenerate_candidate_series(
    *,
    edgar_cache_dir: Path,
    insider_trades_cache: Path,
    binance_cache_dir: Path,
) -> dict[str, pd.Series]:
    """Recompute the five selected specs' daily net return series (four
    until 2026-08-30; round_c's best spec joined when its hard-exclusion
    was removed — docstring section 8).

    The three cache paths are REQUIRED arguments with no defaults on
    purpose. Every one of those providers defaults its cache to a path
    resolved relative to this file's own repo root, which inside a git
    worktree points at a directory that does not exist — silently turning a
    cached run into a fresh multi-hundred-megabyte refetch against SEC,
    Yahoo and Binance, and (for Binance) overwriting the main repo's cache.
    Making the caller state them means that cannot happen by accident."""
    from app.services.market_data.binance_futures_provider import BinanceFuturesProvider
    from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider
    from app.services.market_data.yfinance_provider import YFinanceProvider
    from app.services.research_lab import (
        cross_sectional_correlation_risk_premium as crp,
    )
    from app.services.research_lab import cross_sectional_ofi as ofi
    from app.services.research_lab.cross_sectional import (
        CrossSectionalConfig,
        CrossSectionalData,
        run_cross_sectional_backtest,
    )
    from app.services.research_lab.cross_sectional_insider import (
        INSIDER_BENCHMARK_TICKER,
        INSIDER_FAMILY,
        INSIDER_WARMUP_PADDING_CALENDAR_DAYS,
        InsiderConfig,
        build_buy_events,
        build_owner_labels,
        load_trades_cache,
        run_insider_backtest,
    )
    from app.services.research_lab.cross_sectional_patterns import (
        PRICE_HISTORY_PADDING_CALENDAR_DAYS,
        ROUND_C_FAMILY,
    )
    from app.services.research_lab.cross_sectional_quality import (
        CBOP_FAMILY,
        QUALITY_PRICE_HISTORY_PADDING_CALENDAR_DAYS,
        build_point_in_time_factor_frame,
        build_quality_sample,
        compute_cbop_observations,
        default_quality_config,
    )
    from app.services.research_lab.sp500_membership_history import (
        MEMBERSHIP_DATA_START,
        get_universe_over,
    )

    out: dict[str, pd.Series] = {}

    # --- correlation_risk_premium / crp_realized_21d_h63 -------------------
    # This spec's state function reads only data.realized, never
    # data.implied, so the CBOE implied-correlation fetch is not on its
    # path at all; an all-NaN implied frame satisfies CrpData's index check
    # and changes nothing. run_crp_screening's point-in-time crosscheck (768
    # tickers, 573 correlation matrices) is likewise not needed for one spec.
    crp_start = crp.CRP_FORMATION_START
    crp_padded = crp_start - timedelta(days=crp.CRP_HISTORY_PADDING_CALENDAR_DAYS)
    crp_tickers = [*crp.SECTOR_ETF_UNIVERSE, crp.TRADED_TICKER, crp.VIX]
    crp_closes, _ = YFinanceProvider().get_price_history(crp_tickers, crp_padded, CRP_REPRO_END)
    sector_cols = [t for t in crp.SECTOR_ETF_UNIVERSE if t in crp_closes.columns]
    implied = pd.DataFrame(
        index=crp_closes.index, columns=list(crp.IMPLIED_CORRELATION_INDICES), dtype=float
    )
    crp_data = crp.align_crp_data(
        implied, crp_closes[sector_cols], crp_closes[crp.VIX], crp_closes[crp.TRADED_TICKER]
    )
    crp_config = crp.default_crp_config()
    crp_config.formation_start = crp_start
    crp_spec = next(s for s in crp.CRP_FAMILY if s.spec_id == "crp_realized_21d_h63")
    out["crp_realized_21d_h63"] = crp.run_crp_backtest(crp_data, crp_spec, crp_config).daily_returns

    # --- quality_cbop / cbop_ls_h63 ---------------------------------------
    q_start = MEMBERSHIP_DATA_START
    q_config = default_quality_config()
    # LOAD-BEARING: default_quality_config leaves formation_start None, and
    # run_quality_screening sets it. Without it, formations begin inside the
    # price padding, before point-in-time membership data exists.
    q_config.formation_start = q_start
    sample, _ = build_quality_sample(q_start, QUALITY_REPRO_END)
    edgar = EdgarXbrlProvider(cache_dir=edgar_cache_dir)
    extractions, _, _ = edgar.fetch_line_items_for_tickers(sample)
    q_padded = q_start - timedelta(days=QUALITY_PRICE_HISTORY_PADDING_CALENDAR_DAYS)
    q_close, _ = YFinanceProvider().get_price_history(sample, q_padded, QUALITY_REPRO_END)
    cbop_obs = {t: compute_cbop_observations(e)[0] for t, e in extractions.items()}
    cbop_frame, _, _ = build_point_in_time_factor_frame(q_close, cbop_obs)
    cbop_spec = next(s for s in CBOP_FAMILY if s.pattern_id == "cbop_ls_h63")
    out["cbop_ls_h63"] = run_cross_sectional_backtest(
        CrossSectionalData(close=q_close, fundamental_signal=cbop_frame),
        cbop_spec,
        q_config,
        None,
    ).daily_returns

    # --- insider_opportunistic / insider_opp_buy_h21_c2_equal --------------
    i_start = MEMBERSHIP_DATA_START
    i_config = InsiderConfig()
    trades, _ = load_trades_cache(insider_trades_cache)
    # formation_end is capped by the published quarterly data's own coverage,
    # not by `end` — so `end` moves the price panel and nothing else.
    last_coverage = max(t.filing_date for t in trades)
    formation_end = min(INSIDER_REPRO_END, last_coverage)
    labels = build_owner_labels(trades, list(range(i_start.year, formation_end.year + 1)))
    event_tickers = sorted(
        {t.ticker for t in trades if t.trans_code == "P" and t.acquired_disposed == "A"}
    )
    i_fetch_start = i_start - timedelta(days=INSIDER_WARMUP_PADDING_CALENDAR_DAYS)
    provider = YFinanceProvider()
    frames, _ = provider.get_daily_ohlcv(event_tickers, i_fetch_start, INSIDER_REPRO_END)
    i_close = frames["close"]
    bench_frames, _ = provider.get_daily_ohlcv(
        [INSIDER_BENCHMARK_TICKER], i_fetch_start, INSIDER_REPRO_END
    )
    benchmark = bench_frames["close"][INSIDER_BENCHMARK_TICKER]
    events, _ = build_buy_events(
        trades, labels, i_close.index, i_start, formation_end, set(i_close.columns)
    )
    i_spec = next(s for s in INSIDER_FAMILY if s.pattern_id == "insider_opp_buy_h21_c2_equal")
    entered = [e for e in events if e.cluster_filings >= i_spec.min_cluster_buys]
    # basis=None is exact for this spec: the entry-row basis is read only on
    # the inverse_vol weighting branch, and this spec is equal-weighted.
    out["insider_opp_buy_h21_c2_equal"] = run_insider_backtest(
        i_close, benchmark, entered, i_spec, i_config, None
    ).daily_returns

    # --- ofi_crypto / ofi_raw_h7 ------------------------------------------
    ofi_provider = BinanceFuturesProvider(cache_dir=str(binance_cache_dir))
    panels = ofi.build_ofi_panels(ofi_provider, end=OFI_REPRO_END, start=ofi.OFI_DATA_START)
    ofi_config = ofi.default_ofi_config()
    ofi_spec = next(s for s in ofi.build_ofi_family() if s.pattern_id == "ofi_raw_h7")
    out["ofi_raw_h7"] = ofi.run_ofi_backtest(panels, ofi_spec, ofi_config).daily_returns

    # --- round_c / lps_intraday_l252_h63 ----------------------------------
    # Exactly the canonical mid_2bp run_tag's configuration, one spec of it:
    # the corrected re-audit runner's point-in-time universe, window and
    # flat 2.0bp one-way cost (run_edge_cost_reaudit_round_c.py), replayed
    # through run_cross_sectional_backtest with the default point-in-time
    # S&P 500 membership gate — the same call
    # screen_cross_sectional_universe makes per spec.
    rc_universe = get_universe_over(MEMBERSHIP_DATA_START, ROUND_C_REPRO_END)
    rc_padded = MEMBERSHIP_DATA_START - timedelta(days=PRICE_HISTORY_PADDING_CALENDAR_DAYS)
    rc_frames, _ = YFinanceProvider().get_daily_ohlcv(rc_universe, rc_padded, ROUND_C_REPRO_END)
    rc_config = CrossSectionalConfig(cost_bps=ROUND_C_MID_COST_BPS)
    rc_config.formation_start = MEMBERSHIP_DATA_START
    rc_spec = next(s for s in ROUND_C_FAMILY if s.pattern_id == "lps_intraday_l252_h63")
    out["lps_intraday_l252_h63"] = run_cross_sectional_backtest(
        CrossSectionalData(
            close=rc_frames["close"], open=rc_frames["open"], volume=rc_frames["volume"]
        ),
        rc_spec,
        rc_config,
        None,
    ).daily_returns

    for label, series in out.items():
        expected = EXPECTED_OBSERVATIONS[label]
        if len(series) != expected:
            raise ValueError(
                f"{label}: regenerated {len(series)} observations but the persisted row "
                f"says {expected} — the reproduction does not match the record, so the "
                "combination must not be built on it. Check the pinned end date."
            )
        idx = pd.DatetimeIndex(series.index)
        if idx.tz is not None:
            series = pd.Series(series.to_numpy(dtype=float), index=idx.tz_localize(None))
            out[label] = series
    return out


# ---------------------------------------------------------------------------
# Step 2. Calendar alignment, the pipeline, and the null control.
# ---------------------------------------------------------------------------


def compound_onto_calendar(native: pd.Series, calendar: pd.DatetimeIndex) -> pd.Series:
    """Section 3's alignment rule: put a finer-calendar return series onto a
    coarser common calendar by COMPOUNDING, so no observation is dropped and
    none is fabricated.

    Each common date d_k carries prod(1 + r_t) - 1 over every native date t
    with d_{k-1} < t <= d_k. Native observations before the first common date
    are dropped (they are outside the window under test, by definition of the
    intersection). A common date with no native observation in its bucket
    gets 0.0 — every family's own encoding of a flat day.

    A series already ON the common calendar comes back unchanged (each bucket
    holds exactly one observation), which is asserted in the tests rather than
    assumed."""
    if not isinstance(native.index, pd.DatetimeIndex):
        raise TypeError("native series must be indexed by a DatetimeIndex")
    if not native.index.is_monotonic_increasing:
        native = native.sort_index()
    calendar = pd.DatetimeIndex(calendar).sort_values()
    if len(calendar) == 0:
        raise ValueError("empty common calendar")

    # searchsorted with side="left" puts a native date exactly equal to a
    # common date into that date's own bucket, which is the (d_{k-1}, d_k]
    # convention above.
    positions = calendar.searchsorted(native.index, side="left")
    values = np.ones(len(calendar), dtype=float)
    native_values = native.to_numpy(dtype=float)
    for pos, r in zip(positions, native_values):
        if pos >= len(calendar):
            continue  # after the window
        values[pos] *= 1.0 + r
    return pd.Series(values - 1.0, index=calendar)


def build_returns_matrix(
    series_by_spec: dict[str, pd.Series],
    *,
    daily_calendar_specs: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Section 3's window and alignment rules, applied.

    `series_by_spec` maps spec label -> that spec's own native daily net
    return series. `daily_calendar_specs` names the specs whose native
    calendar is NOT the common (equity session) calendar — those are
    compounded onto it; the rest are intersected.

    The common calendar is the intersection of the dates of the specs NOT
    named in `daily_calendar_specs`, further intersected with the span of
    every named one so that no leading period is carried in which a
    finer-calendar sleeve did not exist."""
    if not series_by_spec:
        raise ValueError("no series supplied")
    base_labels = [k for k in series_by_spec if k not in daily_calendar_specs]
    if not base_labels:
        raise ValueError(
            "every supplied series was declared as a non-common-calendar series — "
            "there is no common calendar left to compound onto"
        )
    common: pd.DatetimeIndex | None = None
    for label in base_labels:
        idx = pd.DatetimeIndex(series_by_spec[label].index).sort_values()
        common = idx if common is None else common.intersection(idx)
    assert common is not None
    for label in daily_calendar_specs:
        idx = pd.DatetimeIndex(series_by_spec[label].index)
        common = common[(common >= idx.min()) & (common <= idx.max())]
    if len(common) == 0:
        raise ValueError("the selected candidates share no overlapping window")

    columns: dict[str, pd.Series] = {}
    for label, series in series_by_spec.items():
        s = series.copy()
        s.index = pd.DatetimeIndex(s.index)
        if label in daily_calendar_specs:
            columns[label] = compound_onto_calendar(s, common)
        else:
            columns[label] = s.reindex(common).fillna(0.0)
    frame = pd.DataFrame(columns).loc[common]
    frame = frame[list(series_by_spec.keys())]
    if not np.isfinite(frame.to_numpy(dtype=float)).all():
        raise ValueError("aligned returns matrix contains NaN/inf")
    return frame


def inverse_volatility_weights(returns: pd.DataFrame) -> dict[str, float]:
    """Baseline 2 of section 5. 1/sigma_i normalized to sum to 1."""
    vols = returns.std(ddof=1)
    if (vols <= 0).any() or not np.isfinite(vols).all():
        raise ValueError("a candidate has zero or non-finite volatility")
    inv = 1.0 / vols
    return {str(k): float(v) for k, v in (inv / inv.sum()).items()}


def equal_weights(returns: pd.DataFrame) -> dict[str, float]:
    """Baseline 1 of section 5."""
    n = returns.shape[1]
    return {str(c): 1.0 / n for c in returns.columns}


def combined_series(returns: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    w = pd.Series(weights).reindex(returns.columns)
    if w.isna().any():
        raise ValueError("weights do not cover every column of the returns matrix")
    return returns.mul(w, axis=1).sum(axis=1)


@dataclass
class CombinationResult:
    """One weighting scheme's combined book. Deliberately carries the
    weights that produced it — a return stream carries no evidence of its
    own construction, the same reasoning HRPResult.denoise exists for."""

    method: str
    weights: dict[str, float]
    sharpe_annualized: float
    n_trading_days: int
    psr_vs_zero: float | None
    # Section 4(3): NOT a Bailey-Lopez de Prado DSR. See the field name.
    deflation_style_sensitivity: float | None
    deflation_n_trials: int
    deflation_sigma_sr_annualized: float
    # Section 4A. NOT pre-declared, does NOT feed the verdict.
    deflation_diagnostic: float | None
    deflation_diagnostic_n_trials: int
    deflation_diagnostic_sigma_sr: float
    mean_annualized_return: float
    annualized_volatility: float
    # Set only for the RMT+HRP method.
    rmt_n_signal: int | None = None
    rmt_n_noise: int | None = None
    rmt_sigma2: float | None = None
    rmt_lambda_plus: float | None = None
    hrp_quasi_diag_order: tuple[str, ...] = ()
    # The combined book's own daily net return stream, ISO date -> return.
    # Carried and persisted deliberately: cross_sectional_persistence.py's
    # docstring records that no family had anywhere to persist its numbers,
    # and none of the persisted per-spec rows carries a return series — which
    # is exactly why every candidate here had to be regenerated from scratch.
    # A future reader of this row does not have to.
    daily_returns: dict[str, float] = field(default_factory=dict)


def _score_combination(
    method: str,
    returns: pd.DataFrame,
    weights: dict[str, float],
    selection: CandidateSelection,
) -> tuple[CombinationResult, pd.Series, DeflatedSharpeResult]:
    series = combined_series(returns, weights)
    sharpe = sharpe_ratio(series, periods_per_year=TRADING_DAYS_PER_YEAR)
    # POOLED DENOMINATOR (2026-09-04): both the headline and the diagnostic
    # denominator are raised to the project-wide effectively-independent trial
    # count when that is larger. The candidates being combined were themselves
    # drawn from that project-wide search, so counting only the combination
    # trials understates it twice over. See global_effective_n.py.
    deflated = compute_deflated_sharpe(
        sharpe_net_annualized=sharpe,
        returns=series,
        n_trials=dsr_n_trials(selection.n_trials_for_deflation),
        sigma_sr_annualized=selection.sigma_sr_annualized,
        periods_per_year=TRADING_DAYS_PER_YEAR,
    )
    diagnostic = compute_deflated_sharpe(
        sharpe_net_annualized=sharpe,
        returns=series,
        n_trials=dsr_n_trials(selection.n_trials_diagnostic),
        sigma_sr_annualized=selection.sigma_sr_diagnostic,
        periods_per_year=TRADING_DAYS_PER_YEAR,
    )
    result = CombinationResult(
        method=method,
        weights={str(k): float(v) for k, v in weights.items()},
        sharpe_annualized=sharpe,
        n_trading_days=len(series),
        psr_vs_zero=deflated.psr_vs_zero,
        deflation_style_sensitivity=deflated.dsr,
        deflation_n_trials=selection.n_trials_for_deflation,
        deflation_sigma_sr_annualized=selection.sigma_sr_annualized,
        deflation_diagnostic=diagnostic.dsr,
        deflation_diagnostic_n_trials=selection.n_trials_diagnostic,
        deflation_diagnostic_sigma_sr=selection.sigma_sr_diagnostic,
        mean_annualized_return=float(series.mean() * TRADING_DAYS_PER_YEAR),
        annualized_volatility=float(series.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)),
        daily_returns={str(d.date()): float(v) for d, v in series.items()},
    )
    return result, series, deflated


@dataclass
class NullControlResult:
    """Section 4's selection-mirroring Monte Carlo."""

    n_draws: int
    seed: int
    family_spec_counts: dict[str, int]
    real_sharpe_rmt_hrp: float
    real_sharpe_equal_weight: float
    p_value_rmt_hrp: float
    p_value_equal_weight: float
    null_median_sharpe_rmt_hrp: float
    null_p95_sharpe_rmt_hrp: float
    null_median_sharpe_equal_weight: float
    null_p95_sharpe_equal_weight: float


def run_null_control(
    returns: pd.DataFrame,
    family_spec_counts: dict[str, int],
    real_sharpe_rmt_hrp: float,
    real_sharpe_equal_weight: float,
    *,
    n_draws: int = NULL_CONTROL_DRAWS,
    seed: int = NULL_CONTROL_SEED,
) -> NullControlResult:
    """Section 4's null, exactly as declared: per family draw k_f zero-edge
    series at the selected sleeve's own daily volatility, keep the best by
    in-sample Sharpe, then run the same two combinations.

    The columns of `returns` must be in the same order as
    `family_spec_counts`, which is how each sleeve's volatility is matched to
    its family's k_f."""
    labels = list(returns.columns)
    if list(family_spec_counts.keys()) != labels:
        raise ValueError(
            "family_spec_counts must be keyed by the returns matrix's columns, in "
            f"order; got {list(family_spec_counts.keys())} vs {labels}"
        )
    t = len(returns)
    sigmas = returns.std(ddof=1).to_numpy(dtype=float)
    ks = np.asarray([family_spec_counts[c] for c in labels], dtype=int)
    rng = np.random.default_rng(seed)

    null_rmt = np.empty(n_draws, dtype=float)
    null_eq = np.empty(n_draws, dtype=float)
    for b in range(n_draws):
        sleeves = np.empty((t, len(labels)), dtype=float)
        for j, (sigma, k) in enumerate(zip(sigmas, ks)):
            draws = rng.normal(0.0, sigma, size=(t, k))
            # Best-of-k by in-sample Sharpe — mirroring step 1(c). Constant
            # sigma across siblings, so argmax on the mean is argmax on the
            # Sharpe up to the sample std, which is recomputed per column
            # anyway to keep the mirror exact.
            stds = draws.std(axis=0, ddof=1)
            sleeves[:, j] = draws[:, int(np.argmax(draws.mean(axis=0) / stds))]
        frame = pd.DataFrame(sleeves, columns=labels, index=returns.index)
        hrp = compute_hrp_weights_from_returns(frame, denoise=True)
        null_rmt[b] = sharpe_ratio(
            combined_series(frame, hrp.weights), periods_per_year=TRADING_DAYS_PER_YEAR
        )
        null_eq[b] = sharpe_ratio(
            combined_series(frame, equal_weights(frame)),
            periods_per_year=TRADING_DAYS_PER_YEAR,
        )

    return NullControlResult(
        n_draws=n_draws,
        seed=seed,
        family_spec_counts=dict(family_spec_counts),
        real_sharpe_rmt_hrp=real_sharpe_rmt_hrp,
        real_sharpe_equal_weight=real_sharpe_equal_weight,
        p_value_rmt_hrp=float(np.mean(null_rmt >= real_sharpe_rmt_hrp)),
        p_value_equal_weight=float(np.mean(null_eq >= real_sharpe_equal_weight)),
        null_median_sharpe_rmt_hrp=float(np.median(null_rmt)),
        null_p95_sharpe_rmt_hrp=float(np.quantile(null_rmt, 0.95)),
        null_median_sharpe_equal_weight=float(np.median(null_eq)),
        null_p95_sharpe_equal_weight=float(np.quantile(null_eq, 0.95)),
    )


@dataclass
class MultiSignalSummary:
    """Everything Step 2 and Step 3 produced, in one object."""

    selection: CandidateSelection
    window_start: str
    window_end: str
    n_trading_days: int
    correlation_matrix: dict[str, dict[str, float]]
    results: tuple[CombinationResult, ...]
    kelly: dict[str, float]
    null_control: NullControlResult | None
    best_single_candidate: str
    best_single_sharpe: float
    verdict: str
    notes: tuple[str, ...] = ()
    # The aligned per-candidate return matrix, so the whole experiment is
    # replayable from the persisted row without re-fetching SEC, Yahoo and
    # Binance. Column label -> ISO date -> return.
    aligned_returns: dict[str, dict[str, float]] = field(default_factory=dict)
    single_candidate_sharpes: dict[str, float] = field(default_factory=dict)


def run_combination(
    selection: CandidateSelection,
    series_by_spec: dict[str, pd.Series],
    *,
    daily_calendar_specs: tuple[str, ...] = (),
    family_spec_counts: dict[str, int] | None = None,
    run_null: bool = True,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
) -> MultiSignalSummary:
    """Steps 2 and 3, on an already-frozen selection and already-regenerated
    return series. Takes the series as an argument rather than fetching them
    so this whole pipeline is testable without a network."""
    returns = build_returns_matrix(series_by_spec, daily_calendar_specs=daily_calendar_specs)

    hrp_denoised = compute_hrp_weights_from_returns(returns, denoise=True)
    hrp_raw = compute_hrp_weights_from_returns(returns, denoise=False)

    rmt_hrp, _, _ = _score_combination(
        "rmt_denoised_hrp", returns, hrp_denoised.weights, selection
    )
    assert hrp_denoised.denoise is not None
    rmt_hrp.rmt_n_signal = hrp_denoised.denoise.n_signal
    rmt_hrp.rmt_n_noise = hrp_denoised.denoise.n_noise
    rmt_hrp.rmt_sigma2 = hrp_denoised.denoise.fit.sigma2
    rmt_hrp.rmt_lambda_plus = hrp_denoised.denoise.fit.lambda_plus
    rmt_hrp.hrp_quasi_diag_order = tuple(hrp_denoised.quasi_diag_order)

    hrp_only, _, _ = _score_combination("hrp_no_denoise", returns, hrp_raw.weights, selection)
    hrp_only.hrp_quasi_diag_order = tuple(hrp_raw.quasi_diag_order)
    eq, _, _ = _score_combination("equal_weight", returns, equal_weights(returns), selection)
    iv, _, _ = _score_combination(
        "inverse_volatility", returns, inverse_volatility_weights(returns), selection
    )

    singles = {
        str(c): sharpe_ratio(returns[c], periods_per_year=TRADING_DAYS_PER_YEAR)
        for c in returns.columns
    }
    best_single = max(singles, key=lambda k: singles[k])

    kelly_result: KellyLeverageResult = compute_kelly_leverage_from_returns(
        returns,
        hrp_denoised.weights,
        risk_free_rate=0.0,
        kelly_fraction=kelly_fraction,
        insufficient_history_label="multi-signal candidates",
    )
    theta_hat_sq = kelly_result.portfolio_sharpe**2
    n_years = len(returns) / TRADING_DAYS_PER_YEAR
    debiased_theta_sq = max(theta_hat_sq - returns.shape[1] / n_years, 0.0)
    growth_optimal = growth_optimal_kelly_fraction(
        debiased_theta_sq, returns.shape[1], n_years, n_obs=len(returns)
    )
    kelly = {
        "risk_free_rate": 0.0,
        "kelly_fraction": kelly_result.kelly_fraction,
        "full_kelly_leverage": kelly_result.full_kelly_leverage,
        "leverage_at_kelly_fraction": kelly_result.leverage,
        "portfolio_excess_return_annualized": kelly_result.portfolio_excess_return,
        "portfolio_volatility_annualized": kelly_result.portfolio_volatility,
        "portfolio_sharpe": kelly_result.portfolio_sharpe,
        "growth_rate_at_kelly_fraction": kelly_result.growth_rate,
        "full_kelly_growth_rate": kelly_result.full_kelly_growth_rate,
        "zero_growth_leverage": kelly_result.zero_growth_leverage,
        "sample_theta_squared": theta_hat_sq,
        "debiased_theta_squared": debiased_theta_sq,
        "growth_optimal_kelly_fraction": growth_optimal,
        "leverage_at_growth_optimal_fraction": growth_optimal
        * kelly_result.full_kelly_leverage,
    }

    results_for_ranking = (rmt_hrp, hrp_only, eq, iv)

    null: NullControlResult | None = None
    if run_null:
        if family_spec_counts is None:
            raise ValueError("family_spec_counts is required to run the null control")
        missing = [str(c) for c in returns.columns if str(c) not in family_spec_counts]
        if missing:
            raise ValueError(
                f"family_spec_counts is missing k_f for {missing} — the null cannot "
                "mirror step 1(c)'s best-of-k selection for a sleeve whose family size "
                "it does not know, and defaulting it to 1 would silently remove the "
                "selection bias the control exists to price."
            )
        null = run_null_control(
            returns,
            {str(c): family_spec_counts[str(c)] for c in returns.columns},
            rmt_hrp.sharpe_annualized,
            eq.sharpe_annualized,
        )

    verdict = _verdict(rmt_hrp, null)
    corr = returns.corr()

    # Notes are computed from the run, not written by hand, so they cannot
    # drift from it. Every one of these was FOUND by running the pipeline;
    # none of them changes any pre-declared step.
    notes: list[str] = []
    negative_in_window = sorted(k for k, v in singles.items() if v < 0)
    if negative_in_window:
        notes.append(
            "SELECTION DOES NOT SURVIVE THE WINDOW. "
            + ", ".join(f"{k} ({singles[k]:+.4f})" for k in negative_in_window)
            + " have NEGATIVE Sharpes over the common window, despite having been "
            "selected on a positive PSR-vs-zero over their own (longer) family "
            "windows. The candidates were chosen on full-sample evidence and are "
            "scored here on the intersection window, and for these the two do not "
            "agree. This is the single most consequential fact about the result and "
            "it is a property of the data, not of the combination method."
        )
    if rmt_hrp.rmt_n_signal == 0:
        notes.append(
            f"RMT found ZERO signal eigenvalues: all {rmt_hrp.rmt_n_noise} sit inside "
            f"the Marchenko-Pastur band (lambda_plus {rmt_hrp.rmt_lambda_plus:.4f}, "
            f"fitted sigma^2 {rmt_hrp.rmt_sigma2:.5f}). Read literally, the candidates' "
            "correlation matrix is indistinguishable from the identity — which is what "
            "the 'many independent edges' thesis assumes, and is corroborated by the "
            "raw pairwise correlations. Denoising therefore flattens the matrix to "
            "(near) identity, which is why the denoised and un-denoised HRP weights "
            "barely differ. As section 3 declared in advance, this is REPORTED and not "
            "read as evidence about RMT as a method: at this N the estimator is far "
            "outside its asymptotic regime."
        )
    if null is not None:
        notes.append(
            "THE NULL CONTROL IS MORE CONSERVATIVE THAN SECTION 4 ANTICIPATED, and the "
            "third reason was only visible once it ran: the null selects each sleeve's "
            "best-of-k on the SAME window the combination is scored on, whereas the "
            "real candidates were selected on their own longer family windows. Its "
            f"median zero-edge combined Sharpe is therefore {null.null_median_sharpe_rmt_hrp:+.4f}, "
            "far above anything the real data produced, so its p-value is an upper "
            "bound rather than a tight test. Recorded rather than replaced: the "
            "headline conclusion does not rest on it, because the combination's Sharpe "
            "is below the best single input's over the same window and there is "
            "nothing for a null to defend."
        )
    ranked = sorted(results_for_ranking, key=lambda r: r.sharpe_annualized, reverse=True)
    notes.append(
        "SOPHISTICATION ORDERING (Step 3), best to worst by combined Sharpe: "
        + ", ".join(f"{r.method} {r.sharpe_annualized:+.4f}" for r in ranked)
        + f"; best single candidate {best_single} {singles[best_single]:+.4f}."
    )
    return MultiSignalSummary(
        selection=selection,
        window_start=str(returns.index[0].date()),
        window_end=str(returns.index[-1].date()),
        n_trading_days=len(returns),
        correlation_matrix={
            str(i): {str(j): float(corr.loc[i, j]) for j in corr.columns} for i in corr.index
        },
        results=results_for_ranking,
        kelly=kelly,
        notes=tuple(notes),
        null_control=null,
        best_single_candidate=best_single,
        best_single_sharpe=singles[best_single],
        verdict=verdict,
        aligned_returns={
            str(c): {str(d.date()): float(v) for d, v in returns[c].items()}
            for c in returns.columns
        },
        single_candidate_sharpes=singles,
    )


def _verdict(primary: CombinationResult, null: NullControlResult | None) -> str:
    """Section 4's pre-declared decision rule, applied mechanically."""
    sens = primary.deflation_style_sensitivity
    clears_bar = sens is not None and sens >= COMBINED_SIGNIFICANCE_BAR
    if null is None:
        return (
            "NO VERDICT — the null control did not run, and section 4's decision rule "
            "requires both halves."
        )
    clears_null = null.p_value_rmt_hrp <= COMBINED_NULL_P_VALUE_BAR
    if clears_bar and clears_null:
        return (
            f"CLEARS THE PRE-DECLARED BAR: deflation-style sensitivity "
            f"{sens:.3f} >= {COMBINED_SIGNIFICANCE_BAR} AND selection-mirroring null "
            f"p-value {null.p_value_rmt_hrp:.4f} <= {COMBINED_NULL_P_VALUE_BAR}."
        )
    return (
        "HONEST NEGATIVE by section 4's pre-declared rule: deflation-style sensitivity "
        f"{'None' if sens is None else format(sens, '.3f')} "
        f"({'>=' if clears_bar else '<'} {COMBINED_SIGNIFICANCE_BAR}) and "
        f"selection-mirroring null p-value {null.p_value_rmt_hrp:.4f} "
        f"({'<=' if clears_null else '>'} {COMBINED_NULL_P_VALUE_BAR}). Both were "
        "required; the combination does not clear a real significance bar."
    )


# ---------------------------------------------------------------------------
# Persistence. cross_sectional_persistence's writer needs .spec_id,
# .sharpe_annualized, .n_trading_days and .deflated_sharpe, so the combined
# results are shaped into exactly that rather than getting a parallel writer.
# ---------------------------------------------------------------------------


@dataclass
class PersistableCombination:
    """Adapter onto persist_cross_sectional_trial_results' contract.

    `deflated_sharpe.dsr` here is section 4(3)'s DEFLATION-STYLE SENSITIVITY,
    not a Bailey-Lopez de Prado DSR — the combined portfolio is not the
    maximum of n_trials sibling trials, which is that statistic's generative
    model. The flag below travels with every persisted row so a future reader
    of the `dsr` column cannot mistake it for one."""

    spec_id: str
    sharpe_annualized: float
    n_trading_days: int
    deflated_sharpe: DeflatedSharpeResult
    dsr_is_not_a_bailey_lopez_de_prado_dsr: bool = True
    dsr_caveat: str = (
        "The `dsr` column for this family is a deflation-style SENSITIVITY, not a "
        "DSR: n_trials is the size of the search that produced the combined book's "
        "inputs and sigma_SR is the dispersion of those scanned specs' Sharpes, but "
        "the reported statistic is a fixed weighted sum of selected series, not the "
        "maximum over n_trials sibling trials. See multi_signal_combination.py "
        "section 4."
    )
    # Section 4A's diagnostic, carried explicitly so the persisted row shows
    # both numbers and which one the verdict used.
    deflation_diagnostic: float | None = None
    deflation_diagnostic_n_trials: int = 0
    deflation_diagnostic_sigma_sr: float = 0.0
    weights: dict[str, float] = field(default_factory=dict)
    window_start: str = ""
    window_end: str = ""
    correlation_matrix: dict[str, dict[str, float]] = field(default_factory=dict)
    kelly: dict[str, float] = field(default_factory=dict)
    null_control: dict[str, object] = field(default_factory=dict)
    selection_reasoning: list[dict[str, object]] = field(default_factory=list)
    verdict: str = ""
    notes: list[str] = field(default_factory=list)
    single_candidate_sharpes: dict[str, float] = field(default_factory=dict)
    daily_returns: dict[str, float] = field(default_factory=dict)
    candidate_daily_returns: dict[str, dict[str, float]] = field(default_factory=dict)


def build_persistable(summary: MultiSignalSummary) -> list[PersistableCombination]:
    """One row per weighting scheme, each carrying the full selection record
    so the persisted rows are self-contained."""
    reasoning = [
        {
            "family_key": d.spec.family_key,
            "trial_id": d.spec.trial_id,
            "run_tag": d.spec.run_tag,
            "sharpe_annualized": d.spec.sharpe_annualized,
            "psr_vs_zero": d.spec.psr_vs_zero,
            "dsr": d.spec.dsr,
            "selected": d.selected,
            "stage": d.stage,
            "reason": d.reason,
        }
        for d in summary.selection.decisions
    ]
    rows: list[PersistableCombination] = []
    for result in summary.results:
        deflated = DeflatedSharpeResult(
            sharpe_net_annualized=result.sharpe_annualized,
            sharpe_net_daily=result.sharpe_annualized / np.sqrt(TRADING_DAYS_PER_YEAR),
            n_observations=result.n_trading_days,
            skewness=float("nan"),
            kurtosis=float("nan"),
            psr_vs_zero=result.psr_vs_zero,
            n_trials=result.deflation_n_trials,
            sigma_sr_annualized=result.deflation_sigma_sr_annualized,
            expected_max_sharpe_noise_annualized=None,
            dsr=result.deflation_style_sensitivity,
            dsr_floor_met=True,
            interpretation="see dsr_caveat — this is not a DSR",
        )
        rows.append(
            PersistableCombination(
                spec_id=result.method,
                sharpe_annualized=result.sharpe_annualized,
                n_trading_days=result.n_trading_days,
                deflated_sharpe=deflated,
                deflation_diagnostic=result.deflation_diagnostic,
                deflation_diagnostic_n_trials=result.deflation_diagnostic_n_trials,
                deflation_diagnostic_sigma_sr=result.deflation_diagnostic_sigma_sr,
                weights=result.weights,
                window_start=summary.window_start,
                window_end=summary.window_end,
                correlation_matrix=summary.correlation_matrix,
                kelly=summary.kelly if result.method == "rmt_denoised_hrp" else {},
                null_control=(
                    asdict(summary.null_control) if summary.null_control is not None else {}
                ),
                selection_reasoning=reasoning,
                verdict=summary.verdict,
                notes=list(summary.notes),
                single_candidate_sharpes=summary.single_candidate_sharpes,
                daily_returns=result.daily_returns,
                # Only on the primary row: four copies of the same matrix
                # would quadruple the table's size for nothing.
                candidate_daily_returns=(
                    summary.aligned_returns if result.method == "rmt_denoised_hrp" else {}
                ),
            )
        )
    return rows


def summary_lines(summary: MultiSignalSummary) -> list[str]:
    """The human-readable record. Deliberately reports the baselines and the
    null before the headline number, so nobody can read the headline without
    them."""
    lines: list[str] = []
    lines.append(
        f"MULTI-SIGNAL COMBINATION — {len(summary.selection.selected)} candidates, "
        f"{summary.window_start} .. {summary.window_end}, "
        f"{summary.n_trading_days} common trading days."
    )
    lines.append(
        f"Scanned {summary.selection.n_scanned} persisted specs; sigma_SR across them "
        f"{summary.selection.sigma_sr_annualized:.4f} (section 4(3), pre-declared). "
        f"Section 4A diagnostic, NOT pre-declared and NOT used for the verdict: over "
        f"the {summary.selection.n_trials_diagnostic} non-hard-excluded specs sigma_SR "
        f"is {summary.selection.sigma_sr_diagnostic:.4f}."
    )
    lines.append("SELECTED (frozen before any combined number existed):")
    for spec in summary.selection.selected:
        lines.append(
            f"  {spec.family_key}/{spec.trial_id}: Sharpe {spec.sharpe_annualized:+.4f}, "
            f"PSR(0) {spec.psr_vs_zero:.4f}, DSR "
            f"{'None' if spec.dsr is None else format(spec.dsr, '.4f')}, "
            f"n={spec.n_observations}"
        )
    lines.append("PAIRWISE CORRELATIONS over the common window:")
    for i, row in summary.correlation_matrix.items():
        for j, v in row.items():
            if i < j:
                lines.append(f"  {i} vs {j}: {v:+.4f}")
    lines.append("COMBINATIONS (all four pre-declared in section 5):")
    for result in summary.results:
        primary = result.deflation_style_sensitivity
        diag = result.deflation_diagnostic
        lines.append(
            f"  {result.method:<20} Sharpe {result.sharpe_annualized:+.4f}  "
            f"PSR(0) {result.psr_vs_zero:.4f}  deflation-sensitivity "
            f"{'None' if primary is None else format(primary, '.4f')}  "
            f"[4A diagnostic {'None' if diag is None else format(diag, '.4f')}]"
        )
        lines.append(
            "      weights " + ", ".join(f"{k}={v:.4f}" for k, v in result.weights.items())
        )
    lines.append(
        f"  best single candidate over the SAME window: {summary.best_single_candidate} "
        f"at {summary.best_single_sharpe:+.4f}"
    )
    if summary.null_control is not None:
        n = summary.null_control
        lines.append(
            f"SELECTION-MIRRORING NULL ({n.n_draws} draws, seed {n.seed}): RMT+HRP "
            f"p={n.p_value_rmt_hrp:.4f} (null median {n.null_median_sharpe_rmt_hrp:+.4f}, "
            f"p95 {n.null_p95_sharpe_rmt_hrp:+.4f}); equal-weight "
            f"p={n.p_value_equal_weight:.4f} (null median "
            f"{n.null_median_sharpe_equal_weight:+.4f}, p95 "
            f"{n.null_p95_sharpe_equal_weight:+.4f})."
        )
    k = summary.kelly
    lines.append(
        f"KELLY on the RMT+HRP direction (r_f = 0, see section 3): full-Kelly leverage "
        f"{k['full_kelly_leverage']:.4f}x, at fraction {k['kelly_fraction']} "
        f"{k['leverage_at_kelly_fraction']:.4f}x, growth-optimal fraction "
        f"{k['growth_optimal_kelly_fraction']:.4f} -> "
        f"{k['leverage_at_growth_optimal_fraction']:.4f}x. Portfolio Sharpe "
        f"{k['portfolio_sharpe']:+.4f}, vol {k['portfolio_volatility_annualized']:.4f}, "
        f"zero-growth leverage {k['zero_growth_leverage']:.4f}x."
    )
    lines.append(f"VERDICT: {summary.verdict}")
    for note in summary.notes:
        lines.append(f"NOTE: {note}")
    return lines


def persist_combination(
    db: Session, summary: MultiSignalSummary, run_tag: str
) -> int:
    """Writes one row per weighting scheme to cross_sectional_trial_results
    under family_key MULTI_SIGNAL_FAMILY.

    Uses the shared writer's contract via build_persistable rather than a
    parallel writer, so the combined-book results live in the same table
    every family's per-spec results live in."""
    from app.services.research_lab.cross_sectional_persistence import (
        persist_cross_sectional_trial_results,
    )

    return persist_cross_sectional_trial_results(
        db, MULTI_SIGNAL_FAMILY, build_persistable(summary), run_tag=run_tag
    )


def selection_report(selection: CandidateSelection) -> str:
    """The complete Step 1 record — every scanned spec, in or out, with its
    reason. Emitted as JSON so it can be archived next to the run."""
    return json.dumps(
        {
            "threshold": PSR_SELECTION_THRESHOLD,
            "n_scanned": selection.n_scanned,
            "n_selected": len(selection.selected),
            "sigma_sr_annualized": selection.sigma_sr_annualized,
            "decisions": [
                {
                    "family_key": d.spec.family_key,
                    "trial_id": d.spec.trial_id,
                    "run_tag": d.spec.run_tag,
                    "sharpe_annualized": d.spec.sharpe_annualized,
                    "psr_vs_zero": d.spec.psr_vs_zero,
                    "dsr": d.spec.dsr,
                    "selected": d.selected,
                    "stage": d.stage,
                    "reason": d.reason,
                }
                for d in selection.decisions
            ],
        },
        indent=2,
    )
