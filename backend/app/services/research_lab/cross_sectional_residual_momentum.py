"""RESIDUAL (IDIOSYNCRATIC) MOMENTUM — candidate #6 of this project's
literature-grounded "Seven Candidates" review.

PRE-REGISTRATION: backend/data/research_runs/residual_momentum_PREREGISTRATION.txt,
committed BEFORE this module's family was ever run. The hypothesis, the 18-spec
grid, n_trials = 18, the 0.95 DSR bar and the industry-neutral confirmation
condition are all fixed there and are not restated here as though they were
decided afterwards.

--------------------------------------------------------------------------------
1. THE SOURCE, AND THE ONE THING THE BUILD BRIEF GOT WRONG
--------------------------------------------------------------------------------

Blitz, David, Joop Huij & Martin Martens, "Residual momentum", Journal of
Empirical Finance 18(3), June 2011, pp. 506-521,
doi:10.1016/j.jempfin.2011.01.003. Verified against TWO independent records
(Crossref REST API and RePEc/EconPapers) returning identical fields. Verbatim
from the abstract:

    "Conventional momentum strategies exhibit substantial time-varying
     exposures to the Fama and French factors. We show that these exposures can
     be reduced by ranking stocks on residual stock returns instead of total
     returns. As a consequence, residual momentum earns risk-adjusted profits
     that are about twice as large as those associated with total return
     momentum; is more consistent over time; and less concentrated in the
     extremes of the cross-section of stocks."

The paper's body is paywalled (SSRN, ScienceDirect and ResearchGate all
returned HTTP 403 to this build), so NO NUMBER FROM IT IS QUOTED ANYWHERE HERE.
The only magnitude attributed to BHM is the abstract's own "about twice as
large", which is an exact quote.

THE BUILD BRIEF SAID BHM USE "A CARHART-STYLE MULTI-FACTOR REGRESSION". THEY DO
NOT. It is the Fama-French THREE-factor model — market, SMB, HML — with no
momentum (UMD) factor. BHM's own abstract says "the Fama and French factors";
Hanauer & Windmüller write the regression out as three factors and cite BHM for
it; Prunier's independent replication says the same. Including UMD would
regress the momentum factor out of a momentum signal, which is close to
circular. This family is built on FF3.

The brief was RIGHT about the part it flagged as load-bearing: the exposures are
TIME-VARYING, estimated by ROLLING regression, not one static beta.

--------------------------------------------------------------------------------
2. THE EXACT CONSTRUCTION, AND WHERE IT COMES FROM
--------------------------------------------------------------------------------

Taken verbatim from Hanauer, Matthias X. & Steffen Windmüller, "Enhanced
Momentum Strategies" (working paper, draft 2019-08-14, wp.lancs.ac.uk), whose
text states it follows Gutierrez and Prinsky (2007), Blitz et al. (2011) and
Blitz et al. (2018). Their Eq. 8 and Eq. 9, as fetched and text-extracted by
this build:

    "Instead of using the individual stocks' raw returns from t - 12 to t - 2,
     we orthogonalize them with respect to a Fama-French three-factor model.
     [...] we [...] regress the past 36 months' returns of all valid stocks
     within the investment universe on country-specific factors of the
     Fama-French three-factor model. Thus, the following time-series model is
     estimated for every stock i and month t using a rolling-window approach:"

    (8)  R_i,t - R_f,t = a_i + b_RMRF,i*RMRF_t + b_SMB,i*SMB_t
                                              + b_HML,i*HML_t + e_i,t

    (9)  score_i,t = SUM_{j=2..12} e_i,t-j
                     / sqrt( SUM_{j=2..12} (e_i,t-j - mean(e_i))^2 )

Corroborated independently by Prunier, Laurent, "Robustness tests of residual
momentum strategies" (master's thesis, Université de Liège, open access), which
supplied two details this build would otherwise have gotten wrong. Verbatim:

    "only Blitz et al. (2011) do not include it [the alpha] in their
     calculation of the residual. Next, they rank the stocks on the sum of
     their twelve last months' residual, adjusted by its standard deviation
     over the same period and excluding the most recent one. The zero-cost
     portfolio is long the top decile and shorts the bottom one, using an
     equally weighted scheme in each decile."

So: ALPHA IS NOT ADDED BACK (the score is the plain OLS residual, the intercept
absorbed by the fit), and DECILE legs are BHM's own choice.

EQ. 9's DENOMINATOR VS. THE SAMPLE STANDARD DEVIATION. Hanauer's denominator is
sqrt(sum of squared deviations); the sample standard deviation is that divided
by sqrt(n-1). This module uses the standard deviation. The two are IDENTICAL
SORTS here because n is fixed at exactly RESIDUAL_MOM_FORMATION_MONTHS for every
scored name — a stock missing any month of the window is refused outright rather
than scored on a short window — so the ratio between them is a constant common
to the whole cross-section, and a common positive constant cannot reorder a
ranking. The refusal is what makes that argument true, so it is a construction
requirement rather than a data-hygiene nicety, and it is unit-tested.

WHY THE SCORE IS NOT DEGENERATE, checked and pinned by a test rather than
assumed. OLS residuals sum to EXACTLY ZERO over the estimation window. If the
scoring window equalled the estimation window the numerator of Eq. 9 would be
zero for every stock and the "signal" would be pure floating-point noise. It is
non-degenerate only because the scoring window (11 months) is a STRICT SUBSET of
the estimation window (36 months). This is the single easiest way to silently
destroy this family, so `residual_scores_for_window` refuses formation_months >=
regression_months outright.

--------------------------------------------------------------------------------
3. POINT-IN-TIME DISCIPLINE — THE ONE PLACE THIS FAMILY COULD CHEAT
--------------------------------------------------------------------------------

Ken French publishes the FF3 factors with a REAL lag. The vintage cached in this
repo carries data through 2026-06-30 and its archive timestamp is 2026-08-03 — a
MEASURED lag of 34 days. A backtest forming at month-end M on factor data for
month M-1 would be trading numbers that had not been published.

Four defences, all structural rather than asserted:

 * Every monthly score carries an availability date of
   (its last data month's end + FF3_PUBLICATION_LAG_DAYS = 45 days),
   conservative against the measured 34.
 * `build_point_in_time_factor_frame` (the sibling quality families' helper)
   forward-fills from availability dates ONLY — never backfills, never
   interpolates — and refuses a value carried past RESIDUAL_MOM_MAX_STALENESS_
   DAYS = 75. That bound is deliberately TIGHT: this signal refreshes monthly,
   unlike the 455-day bound the annual-filing families use.
 * The frame rides CrossSectionalData.fundamental_signal, which the harness
   slices to rows <= the formation date, so look-ahead at formation is
   structurally impossible whatever this module computes.
 * `build_residual_momentum_observations` ASSERTS that no observation's
   availability precedes its own data end.

CONSEQUENCE, DISCLOSED RATHER THAN HIDDEN: the 45-day lag means the score in
force at a formation date generally stops two calendar months earlier, so this
family skips MORE than BHM do, never less. The realized gap is MEASURED per run
(`median_signal_age_days`) rather than assumed, and comes out at 60 days.

HOW MUCH MORE, corrected by independent verification — an earlier draft put
BHM's own skip at "~2 months", which understates the gap. BHM rank on t-12..t-2
and form at t, so THEIR skip is ONE month. This family's measured 60-day median
data age is therefore about TWICE their skip, not marginally more. Mechanically:
the scoring window here is the last 11 months of the 36-month estimation window,
so the estimation window's own most recent month is INCLUDED and the skip comes
entirely from the publication lag. When the lag lands the usable score on month
t-2 the scoring window is EXACTLY BHM's t-12..t-2; when it lands on t-3 the
window is one month staler than theirs. The direction of the disclosure was
always right — more conservative than the source paper — but the size was not.

THE SAME LAG APPLIES TO ALL THREE ARMS INCLUDING THE RAW CONTROL, and all three
arms are scored on the SAME set of qualifying months. The control needs no
factor data and could in principle be scored more recently; letting it would
hand the benchmark a timing advantage and quietly rig the comparison the whole
family exists to make. `compute_residual_momentum_scores` therefore computes all
three arms in one pass over one month set.

THE ONE POINT-IN-TIME IMPERFECTION THAT REMAINS, added by independent
verification because the section above disclosed the publication LAG and was
silent on the publication REVISION. French rebuilds the ENTIRE history when CRSP
is refreshed — the provider module says so, but as a reproducibility argument
rather than as a look-ahead one. The vintage committed here was built from the
202606 CRSP database, so a 2015 formation in this backtest is ranked on the
2026-revised values of the 2012-2015 factor months, not on the values French
actually published at the time. The 45-day lag makes the RELEASE DATE honest; it
does nothing about the REVISION. This is small (FF3 revisions are typically in
the third decimal of a monthly percent, well under the ~1e-6 price-vendor noise
that already moves this family's Sharpes in section 6) and it is not fixable
without a vintage archive nobody keeps, but it is a real deviation from strict
point-in-time and it should be stated rather than implied away. Every other
input — prices, membership, SIC — is genuinely as-of-formation.

--------------------------------------------------------------------------------
4. WHY A MARKET-ONLY ARM IS IN THE GRID
--------------------------------------------------------------------------------

Not as a convenience fallback. It is a specific published claim, and the grid is
built so this run measures it. Hanauer & Windmüller footnote 7, verbatim:

    "Chaves (2016) in this regard shows that also a simplified version of
     idiosyncratic momentum that is based on one-factor (market) unscaled
     residuals works. Blitz et al. (2018) confirm that most of the performance
     improvement comes from orthogonalizing returns with the market factor and
     that the inclusion of additional Fama-French factors leads to small further
     improvements as more of the stock specific momentum is isolated."

The CAPM arm uses French's OWN Mkt-RF rather than an SPY proxy, so the
CAPM-vs-FF3 comparison differs in the factor SET alone and not also in the data
source or the publication lag.

--------------------------------------------------------------------------------
5. WHAT THIS FAMILY DOES NOT REUSE, AND WHY
--------------------------------------------------------------------------------

There is no general residualizer in this codebase to reuse — checked before
writing one. The three existing regression sites are each welded to a different
purpose: `cross_sectional_ivol.signal_idiosyncratic_volatility` fits a
market-model regression but keeps only the residual STANDARD DEVIATION and
throws the residual series away; `cross_sectional_eigenportfolio.build_cross_
section_signal` returns residual returns but couples them to PCA eigenportfolios
and an OU/s-score fit; `macro_beta._ols_with_intercept` is univariate and
discards residuals. `cross_sectional_ofi.expanding_orthogonalize` is the closest
thing to a general residualizer but is expanding-window and single-regressor,
where BHM require rolling and multi-factor.

What IS reused, unchanged: the point-in-time step-panel builder and seeded
sample (`cross_sectional_quality`), the industry-bucket panel and MIN_BUCKET_SIZE
(`cross_sectional_quality_neutral`), the membership gate
(`sp500_membership_history.was_member`), and the whole backtest/DSR harness
(`cross_sectional.screen_cross_sectional_universe`).

ONE TRAP THIS PROJECT HAS ALREADY FALLEN INTO, avoided deliberately.
`vol_regime_timing`'s ConfoundDiagnostic documents a production bug where a
RETURN STREAM was replaced by its OLS residual `y - alpha - beta*x`, whose mean
is exactly zero by construction, so its Sharpe was ~0 for every strategy. That
bug does not apply here and the reason matters: this family residualizes a
RANKING VARIABLE, not a traded return stream, and it ranks a PARTIAL sum over a
strict sub-window whose mean is not pinned to zero (section 2). The traded
returns are the harness's ordinary long-short leg returns.

--------------------------------------------------------------------------------
6. RESULTS — HONEST NEGATIVE
--------------------------------------------------------------------------------

Run 2026-09-02, run_tag residual_momentum_build_2026-09-02, full mechanical
report at data/research_runs/residual_momentum_2026-09-02.txt. 200-ticker seeded
point-in-time S&P 500 sample (768-ticker union pool), 2929 trading days per
spec, decile legs averaging 11.8-12.5 names. sigma_SR 0.1232 pooled over all 18;
expected max Sharpe of 18 pure-noise trials 0.228.

    rm_ff3_residual_neutral_ls_h21        +0.326  DSR 0.630
    rm_capm_residual_neutral_ls_h21       +0.298  DSR 0.593
    rm_capm_residual_neutral_ls_h63       +0.218  DSR 0.486
    rm_ff3_residual_neutral_ls_h63        +0.212  DSR 0.478
    rm_capm_residual_ls_h63               +0.178  DSR 0.432
    rm_total_return_control_neutral_h63   +0.162  DSR 0.411
    rm_total_return_control_ls_h63        +0.134  DSR 0.375
    rm_total_return_control_neutral_h126  +0.109  DSR 0.342
    rm_ff3_residual_ls_h63                +0.104  DSR 0.335
    rm_capm_residual_neutral_ls_h126      +0.067  DSR 0.291
    rm_ff3_residual_ls_h21                +0.057  DSR 0.279
    rm_capm_residual_ls_h21               +0.056  DSR 0.278
    rm_total_return_control_neutral_h21   +0.048  DSR 0.269
    rm_total_return_control_ls_h126       +0.036  DSR 0.256
    rm_total_return_control_ls_h21        -0.021  DSR 0.198
    rm_ff3_residual_neutral_ls_h126       -0.030  DSR 0.189
    rm_capm_residual_ls_h126              -0.088  DSR 0.140
    rm_ff3_residual_ls_h126               -0.126  DSR 0.114

THE PRE-REGISTERED BAR IS NOT MET. Condition (i) required the best RESIDUAL
spec's DSR to exceed 0.95; rm_ff3_residual_neutral_ls_h21 reaches 0.630, so
condition (ii) is never reached. Not one of the 18 specs clears the bar.

FOUR THINGS THE GRID'S STRUCTURE SAYS:

 * BHM'S COMPARATIVE DIRECTION IS WEAKLY CORROBORATED, AND THAT IS ALL. Across
   the 6 matched (conditioning, holding) cells the CAPM residual beat the
   total-return control in 4 and the FF3 residual in 3. The pattern is orderly:
   both residual arms beat the control in both h21 cells and in the
   industry-neutral h63 cell, both LOSE to it in both h126 cells, and the single
   split is raw h63 (CAPM +0.178 beats control +0.135, FF3 +0.104 does not). So
   residualizing did something in the paper's direction over most of the grid —
   but the 18 specs are correlated variants of one idea, so that count carries
   roughly the information of a single positive draw, which is exactly what
   sigma_SR already prices in. No "twice as large" ratio is computed or claimed:
   this sample cannot resolve one, as the pre-registration committed to saying.

 * INDUSTRY NEUTRALIZATION HELPS EVERY SINGLE PAIR — 9 of 9, deltas +0.028 to
   +0.270, and it helps the RESIDUAL arms roughly three times as much as the
   control (mean delta +0.152 for the residual arms vs +0.057 for the control).
   This is the most informative structure in the run and it points the OPPOSITE
   way to the sibling NOA family, where neutralizing DESTROYED an apparent
   positive. Here the raw sort is the weaker one, so residual momentum on this
   universe is not a disguised industry bet — if anything the industry component
   is noise the sort is better off without. Honest reading: FF3 orthogonalization
   removes market, size and value but leaves industry co-movement in the
   residual, and on a 200-name large-cap cross-section that leftover is a drag
   rather than an edge. This does NOT rescue the result — +0.326 at DSR 0.630 is
   still a negative — but it does mean the negative is a genuine statement about
   residual momentum rather than a confound diagnosis.

 * THE LITERATURE'S OWN REBALANCE GIVES THE GRID'S TWO BEST SPECS, which is the
   opposite of what the sibling asset-growth family found. h21 is BHM's own
   monthly rebalance, and rm_ff3_residual_neutral_ls_h21 and
   rm_capm_residual_neutral_ls_h21 top the grid despite paying its heaviest
   turnover cost (cost drag 0.12 versus 0.04 at h126, since a monthly-
   refreshing signal at a monthly hold trades ~12x a year). A signal whose best
   expression IS the source paper's own cuts mildly in the hypothesis's favour
   and is recorded for that reason.

   TWO OVERSTATEMENTS IN AN EARLIER DRAFT OF THIS BULLET, corrected by
   independent verification against the grid's own 18 numbers. It said "h126 is
   the worst hold under every arm": true of all four RESIDUAL arm-conditionings,
   FALSE of the total-return control, where h21 is the worst hold in both
   conditionings (raw -0.021 vs +0.036 at h126; neutral +0.048 vs +0.109). And
   "best at h21" holds only for the two INDUSTRY-NEUTRAL residual arms; for both
   RAW residual arms the best hold is h63 (capm +0.178, ff3 +0.104, against
   +0.056 and +0.057 at h21). The honest statement is narrower than the earlier
   one: the h21 result is a property of the industry-neutral residual sorts, not
   of the grid as a whole.

 * THE 45-DAY PUBLICATION LAG REALLY BIT, and this is the run's biggest
   self-imposed handicap. The MEASURED median age of the data ranked on is 60
   calendar days, so the effective skip is ~2 months rather than BHM's ~1-2 —
   deliberately conservative, applied identically to all three arms, and
   disclosed in advance. A share of the shortfall against the paper is plausibly
   this lag eating momentum decay; this dataset CANNOT separate that from
   ordinary post-publication decay, and no attempt is made to.

DATA GUARDS, MEASURED RATHER THAN ASSUMED: the _MIN_RESIDUAL_STD degeneracy
guard NEVER FIRED (0 refusals across 23,103 scored ticker-months per arm) —
exactly as predicted, and reported so a guard that had nothing to do is not
mistaken for one that was never checked. 2,601 ticker-months were refused for an
incomplete 36-month estimation window (~10%), and 2 of 155 monthly windows were
refused outright for incomplete Fama-French coverage (July and August 2026, past
the committed vintage's 2026-06-30 end) — refused for ALL THREE ARMS including
the control, which is the anti-rigging property section 3 describes.

DETERMINISM, stated precisely rather than flatteringly: the whole screen was run
FOUR times from scratch. All 18 per-spec Sharpes and DSRs, the 23,103 scored
ticker-months and the 2,601 refusals were IDENTICAL every time. One diagnostic
was not: the printed maximum of the ff3 score panel flickered between +15.964
and +15.965 — its fifth significant figure — across runs that were otherwise
identical, INCLUDING TWO RUNS OF THE SAME CODE.

THE CAUSE IS NOW ISOLATED, BY INDEPENDENT VERIFICATION, and it is candidate (b).
An earlier draft of this docstring confidently attributed the flicker to LAPACK
summation order in np.linalg.lstsq; that was a guess dressed as a finding and was
retracted. A later draft left two candidates open — (a) that float
non-determinism and (b) yfinance re-serving different adjusted closes between
fetches — and said the evidence could not separate them. It can, and the test is
one line of provider code rather than an inference: fetching the SAME 168-ticker,
3963-day panel twice in a row returns 357,543 differing cells out of 612,016
(58%), with a maximum RELATIVE difference of 1.3e-6. That is six to seven orders
of magnitude larger than double-precision lstsq reordering noise (~1e-15
relative) and is exactly the size needed to explain a 1e-5 relative wobble in a
score panel maximum. yfinance's adjusted closes are not stable across calls, so
neither is anything computed from them.

WHAT THIS MEANS FOR "IDENTICAL", stated more precisely than before. The earlier
claim that "'byte-identical' is true of every number this family reports" is too
strong and is corrected here. Across two full independent re-runs the per-spec
Sharpes, DSRs, PSRs, skewness and kurtosis ALL move — by up to ~2e-6 absolute on
a Sharpe (e.g. rm_ff3_residual_neutral_ls_h126 at -0.030374 vs -0.030372). The
defensible claim is the one that survives: every number this family REPORTS is
identical at the 3-4 decimal places it is printed to, the rank ordering of all
18 specs is identical, and the scored counts (23,103), refusal counts (2,601),
universe accounting and verdict are identical. The instability is in the price
vendor, is ~1e-6 relative, and cannot reach any reported digit.

CONSEQUENCE WORTH RECORDING: this family is reproducible to reported precision
but NOT bit-reproducible, and it cannot be made bit-reproducible without pinning
a price vintage the way the Fama-French file is pinned. The factor half of the
inputs is versioned in git; the price half is not.

THE POOLED sigma_SR HELPED THE HEADLINE, AND THAT IS DISCLOSED RATHER THAN LEFT
FOR SOMEONE TO FIND. Pooling sigma_SR over all 18 specs (0.1232) instead of over
the ff3 arm's own 6 (0.1631) LOWERS the noise benchmark SR0 from 0.302 to 0.228
and so RAISES the headline DSR from 0.532 to 0.630 — a gift of +0.098 to the
number this family is judged on. Three things make that defensible, and they are
stated together so a reader can judge for themselves:
  * the decision was made and committed BEFORE the run, for a stated reason that
    has nothing to do with the outcome (the search spanned 18 specs, so the
    dispersion benchmark should describe 18);
  * the direction was not knowable in advance — pooling raises DSR for an arm
    whose internal spread is wide and lowers it for a narrow one, and the
    control arm's own DSRs were pushed the other way (its sigma is 0.0689);
  * IT CHANGES NO VERDICT. At the un-pooled ff3-arm sigma the headline is still
    0.532, and at Round C's n_trials = 30 it is 0.595. Every route lands far
    below the pre-registered 0.95 bar.

TWO CONSTRUCTION DETAILS WERE DECIDED AFTER THE PRE-REGISTRATION WAS FROZEN, and
neither is load-bearing, but both are recorded because a pre-registration is
only worth something if departures from it are listed rather than absorbed:
  * _MIN_RESIDUAL_STD (the exact-collinearity degeneracy floor) is not in the
    pre-registration. It was added while unit-testing the pure-factor case,
    before the production run, and it NEVER FIRED on real data (0 refusals in
    23,103 scored ticker-months per arm). It cannot have shaped this result.
  * The in-progress-final-month guard in monthly_returns_from_daily_close was
    added AFTER the first production run, and is a verified no-op against it:
    re-running with the guard reproduced all 18 per-spec Sharpes and DSRs
    exactly (only the window bookkeeping moved, 156/3 to 155/2).
  * The raw-vs-excess control arm was a genuine DEVIATION from the frozen
    pre-registration, which specified "the cumulative EXCESS return", while the
    first implementation used raw returns on a justification that was
    mathematically wrong for a compounded product. Corrected to excess and
    re-run: two control Sharpes moved by 0.001 (+0.163 to +0.162, +0.135 to
    +0.134), no ordering changed, and the headline is untouched. The numbers
    above are the corrected run.

--------------------------------------------------------------------------------
7. IS THIS "THE SAME NEGATIVE IN DIFFERENT CLOTHES"? NO — AND HERE IS THE
   EVIDENCE, INCLUDING THE REASON IT STILL DOES NOT MATTER
--------------------------------------------------------------------------------

The pre-registration committed this family to answering that question plainly
rather than dodging it. This project has already returned clean honest negatives
on two close behavioral relatives, both on this same universe, both in the Round
C family (n_trials = 30, 63 persisted rows each across run tags):

THE COMPARISON TABLE IN AN EARLIER DRAFT OF THIS SECTION WAS WRONG IN THREE
WAYS, all found by independent verification querying the siblings' own persisted
rows rather than trusting the table. The corrected version is below; the three
errors are named after it because a comparison that gets quietly fixed teaches
nobody anything.

Round C was re-run at five cost assumptions. The pass that matches THIS family's
5 bps one-way is `flat_control`, and it is the only one the numbers below use:

    52-week-high anchoring (gh52)     best Sharpe +0.043   best DSR 0.051
    capital-gains overhang (cgo)      best Sharpe +0.179   best DSR 0.122
    Lou-Polk-Skouras persistence (lps) best Sharpe +0.277  best DSR 0.204
    residual momentum (this family)   best Sharpe +0.326   best DSR 0.630

  ERROR 1 — MISMATCHED COST BASIS. The earlier numbers (gh52 +0.058/0.067, cgo
  +0.188/0.146) are Round C's 1 bp pass, not its 5 bp pass. The mismatch
  flattered the SIBLINGS, so it worked against this family's own claim; it is
  corrected anyway.

  ERROR 2 — THE THIRD SUB-FAMILY WAS MISSING. Round C is 30 specs in THREE
  sub-families, not two. Lou, Polk & Skouras component persistence (lps) is also
  a price-path sort on this same universe and reaches +0.277 / DSR 0.204 — much
  closer to this family than either of the two that were cited. Residual
  momentum is still the best of the four, by 1.18x on Sharpe rather than the
  1.7x-5.6x the earlier draft claimed against its chosen two.

  ERROR 3 — "FOUR TO NINE TIMES EITHER SIBLING'S" DSR IS NOT A SUPPORTABLE
  COMPARISON, and this is the one that mattered. Recomputing this family's
  headline at Round C's n_trials = 30 changes only the TRIAL COUNT; it leaves
  this family's own sigma_SR (0.1232) and noise benchmark SR0 (0.228) in place,
  while Round C's DSRs are deflated against sigma_SR 0.2404 and SR0 0.4985 —
  more than twice as demanding. Deflated against ROUND C'S OWN benchmark this
  family's headline Sharpe of +0.326 gives DSR 0.279, not 0.595. The ratios then
  fall to ~5.5x gh52, ~2.3x cgo and ~1.4x lps. The DSR ratio was measuring a
  difference in sibling-Sharpe dispersion, not a difference in signal quality.
  THE SHARPE COMPARISON IS THE HONEST APPLES-TO-APPLES ONE and it is the weaker
  claim: +0.326 against +0.277, +0.179 and +0.043.

The structure does differ, and that part survives. Under the matched 5 bp pass
gh52 and cgo are at their WORST at a 21-day hold (gh52 -0.26 to -0.41 there, cgo
-0.03 to -0.07) and their BEST at h126, in every one of Round C's five cost
passes. This family's two best specs are h21 and its residual arms are worst at
h126. (The earlier draft's quoted ranges, "-0.23 to -0.70" and "-0.23 to -0.00",
were minima and maxima taken across DIFFERENT cost passes; the qualitative claim
they were supporting holds under each pass taken on its own.)

AND YET THE VERDICT IS THE SAME, which is the point — and after the corrections
above it is the point more than ever. 0.630 is a long way from 0.95; at Round
C's own benchmark it is 0.279. "The best of four negatives, by a smaller margin
than first claimed" is still a negative. Residual momentum is the most promising
behavioral price-path sort this project has tested on this universe, and is
nonetheless not tradeable by us, on our universe, now.

NOTHING FROM THIS FAMILY IS REGISTERED FOR FORWARD VALIDATION. Noted because it
would otherwise look like an omission: exactly TWO specs (DSR 0.630 and 0.593,
both industry-neutral h21) clear the >= 0.5 screening floor this project has
previously used to pick forward-validation candidates, and both fall far short
of this family's own pre-registered 0.95 bar. (The next two, 0.487 and 0.479,
sit just under 0.5.) 0.5 is a screening floor, not a significance bar, so this
changes no verdict. Registration is a separate, later, human decision and this
module deliberately makes no recommendation either way.

WHAT THIS DOES NOT CLAIM, as the pre-registration committed in advance to
saying: it does NOT refute Blitz/Huij/Martens. Their sort is a broad CRSP-
universe sort with hundreds of names per decile over a multi-decade, largely
pre-publication sample. This is 168 priced large-cap names (200 sampled, 32 with
no yfinance history, a further 5 never scoring) over 11.6 years with decile legs
averaging ~12, entirely post-publication, on the most arbitraged segment of
the market, under a deliberately conservative extra publication lag. Anomaly
decay, absence in the large-cap segment specifically, the extra lag, and simple
lack of power are ALL consistent with these numbers and this dataset cannot
distinguish between them. Nor does it say anything about residual momentum as a
RISK-MANAGEMENT OVERLAY on an existing momentum book, which is what much of the
citing literature actually studies — this family tests a standalone long-short
sort.

DO NOT re-test residual momentum on this universe without genuinely new data (a
materially wider cross-section, or a longer pre-publication history) or a
genuinely different hypothesis — and carry these 18 trials into the denominator
of anything that does.
"""

import logging
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from functools import partial

import numpy as np
import pandas as pd

from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider, SicHistory
from app.services.market_data.fama_french_provider import (
    FamaFrenchMonthly,
    load_fama_french_monthly,
)
from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalScreeningResult,
    CrossSectionalSpec,
    screen_cross_sectional_universe,
)
from app.services.research_lab.cross_sectional_quality import (
    QUALITY_COST_BPS,
    QUALITY_FINANCING_BPS_PER_YEAR,
    QUALITY_RANK_FRACTION,
    QUALITY_SAMPLE_SEED,
    QUALITY_SIGNAL_LOOKBACK_ROWS,
    FactorObservation,
    build_point_in_time_factor_frame,
    build_quality_sample,
    default_quality_config,
)
from app.services.research_lab.cross_sectional_quality_neutral import (
    MIN_BUCKET_SIZE,
    build_point_in_time_bucket_frame,
)
from app.services.research_lab.deflated_sharpe import (
    MIN_TRIALS_FOR_DSR,
    expected_max_sharpe_under_noise,
    probabilistic_sharpe_ratio,
)
from app.services.research_lab.global_effective_n import dsr_n_trials
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    was_member,
)

logger = logging.getLogger(__name__)

RESIDUAL_MOMENTUM_CITATION = (
    "Blitz, Huij & Martens, 'Residual momentum' (Journal of Empirical Finance 18(3), 2011, "
    "pp. 506-521, doi:10.1016/j.jempfin.2011.01.003) — ranking on FF3-orthogonalized trailing "
    "returns rather than total returns, whose abstract claims risk-adjusted profits 'about "
    "twice as large as those associated with total return momentum'; construction taken from "
    "Hanauer & Windmuller's 'Enhanced Momentum Strategies' Eqs. 8-9 and corroborated by "
    "Prunier's independent replication"
)

# --- BHM's own construction constants ---------------------------------------

# The rolling estimation window, in MONTHS. BHM's own 36, verified twice (see
# module docstring section 1). DELIBERATELY NOT A GRID AXIS: Prunier's
# sensitivity work already reports 36 the best of {12, 24, 36, 48}, so searching
# over it here would be selecting on a dimension the literature has published
# on. One value, pre-committed, no search.
RESIDUAL_MOM_REGRESSION_MONTHS = 36

# The scoring window, in MONTHS: Eq. 9's j = 2..12, i.e. eleven months, the
# most recent month skipped. MUST stay a strict subset of the estimation window
# or the score collapses to zero for every stock (section 2).
RESIDUAL_MOM_FORMATION_MONTHS = 11

# Ken French's measured publication lag on the vintage cached here is 34 days
# (data through 2026-06-30, archive timestamp 2026-08-03). 45 is deliberately
# conservative against that. See module docstring section 3.
FF3_PUBLICATION_LAG_DAYS = 45

# A monthly-refreshing score more than ~2.5 months old means months are missing.
# Tight ON PURPOSE — the annual-filing families' 455-day bound would let a score
# from last spring rank today's cross-section.
RESIDUAL_MOM_MAX_STALENESS_DAYS = 75

# Eq. 9 is a RATIO of residual quantities, so it is scale-invariant: a stock
# with a tiny idiosyncratic component gets the same score magnitude as a
# volatile one with the same residual SHAPE. That is BHM's intent. But it has a
# degenerate limit — a stock whose returns are an exact linear combination of
# the factors has residuals of pure floating-point dust (~1e-16), and dividing
# dust by dust yields an ARBITRARY O(1) score that is indistinguishable from a
# strong genuine signal. Found while unit-testing the pure-factor case, not
# theorised. A monthly residual standard deviation below one part in a hundred
# million is not a real stock, so below this floor the name is refused rather
# than scored. Expected NEVER to fire on real data (36 monthly returns against
# at most 4 parameters leave real residual variance); the run reports it if it
# does, per this project's rule that a guard which stops firing must not look
# like one that had nothing to do.
_MIN_RESIDUAL_STD = 1e-8

# Calendar padding of price history before the first formation. The score at a
# formation needs RESIDUAL_MOM_REGRESSION_MONTHS of monthly returns ending two
# months earlier, plus one further month to form the first return, plus the
# publication lag: ~39 months. 1500 days (~49 months) leaves real margin, and
# over-fetching free daily closes costs nothing.
RESIDUAL_MOM_PRICE_PADDING_CALENDAR_DAYS = 1500

RESIDUAL_MOM_FAMILY = "residual_momentum"
RESIDUAL_MOM_FAMILY_KEY = "residual_momentum"

# --- the pre-declared grid (see the pre-registration, section 5) -------------

# Arm -> the factor columns regressed out. The control regresses nothing out and
# is BHM's own comparison baseline, "total return momentum".
RESIDUAL_MOM_ARMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("total_return_control", ()),
    ("capm_residual", ("mkt_rf",)),
    ("ff3_residual", ("mkt_rf", "smb", "hml")),
)
RESIDUAL_MOM_CONDITIONINGS: tuple[str, ...] = ("raw", "industry_neutral")
# 21 is INCLUDED here (unlike the asset-growth family, which excluded it)
# because this ranking variable refreshes MONTHLY, so a monthly hold re-ranks on
# genuinely new information rather than re-paying turnover on an unchanged sort.
# 21 is also BHM's own rebalance frequency.
RESIDUAL_MOM_HOLDING_DAYS: tuple[int, ...] = (21, 63, 126)

# 3 arms x 2 conditionings x 3 holds = 18, deciles and long_short throughout,
# ALL fixed before any backtest ran.
RESIDUAL_MOM_N_TRIALS = (
    len(RESIDUAL_MOM_ARMS) * len(RESIDUAL_MOM_CONDITIONINGS) * len(RESIDUAL_MOM_HOLDING_DAYS)
)


# --- monthly panel ----------------------------------------------------------


def monthly_returns_from_daily_close(close: pd.DataFrame) -> pd.DataFrame:
    """Calendar-month-end simple returns from a daily adjusted-close panel.

    The last observed close in each calendar month is that month's mark, and the
    month's return is its change from the previous month's mark. A month in
    which a ticker never traded has no mark, so the NEXT month's return is NaN
    rather than silently spanning a two-month gap — which is what makes the
    "every month of the window must be present" refusal below meaningful.

    THE FINAL MONTH IS DROPPED WHEN IT IS STILL IN PROGRESS. `resample("ME")`
    happily labels a two-day stub "2026-09-30" and hands back a one-day figure
    that looks exactly like a monthly return; feeding that into a 36-month
    regression would contaminate both the betas and, if it landed in the scoring
    window, the score. On the 2026-09-02 production run this was masked by the
    Fama-French coverage gate (French's committed vintage ends 2026-06-30, so
    every window touching the stub was already refused for ALL arms) — but that
    was a coincidence of the factor vintage, not a property of this function,
    and it would stop protecting the moment French published another month.
    Verified no-op against that run: re-running with this guard reproduced
    byte-identical per-spec output.

    The rule is deliberately conservative rather than calendar-clever: the last
    month survives only if the panel reaches its final CALENDAR day. A month
    whose last trading day falls on a Friday the 29th is therefore dropped too.
    That costs at most the newest month of signal, which the 45-day publication
    lag makes unusable anyway, and it avoids this function needing a trading
    calendar to be correct."""
    marks = close.resample("ME").last()
    if len(marks) and len(close.index):
        last_price_day = close.index[-1]
        final_month_end = marks.index[-1]
        if last_price_day < final_month_end:
            marks = marks.iloc[:-1]
    return marks.pct_change(fill_method=None)


def align_factors_to_months(
    monthly: pd.DataFrame, factors: pd.DataFrame, columns: tuple[str, ...]
) -> pd.DataFrame:
    """The factor columns reindexed onto the monthly return panel's own index.

    Months the factor file does not cover become NaN, which the window
    completeness check below turns into a refusal — never a zero, and never a
    forward-filled stale factor value."""
    missing = [c for c in (*columns, "rf") if c not in factors.columns]
    if missing:
        raise ValueError(f"Fama-French frame is missing required columns: {missing}")
    return factors.reindex(monthly.index)[[*columns, "rf"]]


@dataclass
class ResidualMomentumDiagnostics:
    """What the score computation produced and refused, measured rather than
    assumed — this project's standing discipline that a guard which silently
    stops firing must not look like one that had nothing to do."""

    n_scored: int = 0
    n_refused: Counter = field(default_factory=Counter)
    n_month_windows: int = 0
    n_months_without_factor_coverage: int = 0

    def merge(self, other: "ResidualMomentumDiagnostics") -> None:
        self.n_scored += other.n_scored
        self.n_refused.update(other.n_refused)
        self.n_month_windows += other.n_month_windows
        self.n_months_without_factor_coverage += other.n_months_without_factor_coverage


def residual_scores_for_window(
    excess_window: np.ndarray,
    factor_window: np.ndarray,
    *,
    formation_months: int,
) -> np.ndarray:
    """Eq. 8 + Eq. 9 for ONE score month, for every ticker at once.

    `excess_window` is (W, N) excess returns — W months of history ending at the
    score month, N tickers, ALL FINITE (callers refuse incomplete columns before
    getting here). `factor_window` is (W, k) factor returns for the same months,
    WITHOUT an intercept column; k == 0 is the control arm and means "regress
    nothing out", in which case the residual is the excess return demeaned by
    the window mean — which is exactly what OLS on an intercept alone gives, so
    the control travels the same code path rather than a parallel one.

    Returns an (N,) array of scores.

    THE DESIGN MATRIX IS THE SAME FOR EVERY TICKER (factors do not vary by
    stock), so this is ONE least-squares solve for the whole cross-section
    rather than N of them.

    Refuses formation_months >= W outright: OLS residuals sum to exactly zero
    over the estimation window, so a scoring window equal to the estimation
    window would score every stock at ~0 and the family would be measuring
    floating-point noise while looking perfectly healthy (module docstring
    section 2)."""
    n_window = excess_window.shape[0]
    if formation_months >= n_window:
        raise ValueError(
            f"formation_months={formation_months} must be strictly less than the "
            f"{n_window}-month estimation window: OLS residuals sum to exactly zero over the "
            "estimation window, so an equal scoring window scores every stock at zero."
        )
    if factor_window.shape[0] != n_window:
        raise ValueError(
            f"factor window has {factor_window.shape[0]} rows, excess window has {n_window}."
        )

    design = np.column_stack([np.ones(n_window), factor_window]) if factor_window.size else np.ones(
        (n_window, 1)
    )
    coefficients, *_ = np.linalg.lstsq(design, excess_window, rcond=None)
    residuals = excess_window - design @ coefficients

    scoring = residuals[-formation_months:, :]
    numerator = scoring.sum(axis=0)
    denominator = scoring.std(axis=0, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        scores = np.where(denominator > _MIN_RESIDUAL_STD, numerator / denominator, np.nan)
    return scores


def _control_scores_for_window(excess_window: np.ndarray, *, formation_months: int) -> np.ndarray:
    """BHM's comparison baseline: conventional total-return momentum, the
    CUMULATIVE COMPOUNDED return over the same scoring window, neither
    orthogonalized nor volatility-standardized.

    That is what the literature means by "total return momentum", and it is
    therefore what BHM's headline comparison is against. DISCLOSED in the
    pre-registration and repeated here so a reader of the code sees it too: the
    control differs from the residual arms in TWO respects at once (no
    orthogonalization AND no standardization), so this family tests BHM's
    published comparison and NOT a clean one-factor-at-a-time ablation of
    orthogonalization alone.

    EXCESS, NOT RAW, RETURNS — matching the pre-registration ("the cumulative
    EXCESS return over the same 11 months") and matching Eq. 8's left-hand side,
    so the control and the residual arms are fed the identical quantity and
    differ only in what is done to it.

    THIS WAS BUILT RAW FIRST, AND THE STATED REASON WAS WRONG. The original
    justification was that subtracting the risk-free rate shifts every name by
    the same amount and a common shift cannot reorder a ranking. That is true of
    a SUM and false of the COMPOUNDED PRODUCT computed here: with
    r_A = (1.0, 0.0), r_B = (0.0, 1.0) and rf = (0, 0.5), the raw products tie
    at 1.000 while the excess products are 0.000 and 0.500. Caught by
    independent verification, corrected here, and pinned by a test.

    HOW MUCH IT BIT, RE-MEASURED. An earlier draft of this docstring claimed
    raw and excess "ranked identically in all 152 real monthly cross-sections
    of the production run". That is FALSE and is corrected here rather than
    quietly dropped: the full ordering differs in 81 of those 152
    cross-sections. What is true is the part that matters — the TRADED decile
    membership differs in 1 of 152 top deciles and 0 of 152 bottom deciles,
    which is why the six control Sharpes moved by at most 0.0002 and no
    ordering in the grid changed. Monthly RF is ~1e-3, so it reshuffles
    near-ties in the middle of the cross-section and almost never reaches the
    tails that are actually traded. The code now does what was pre-registered
    rather than something that happened to agree with it."""
    scoring = excess_window[-formation_months:, :]
    return np.prod(1.0 + scoring, axis=0) - 1.0


def compute_residual_momentum_scores(
    monthly_returns: pd.DataFrame,
    factors: pd.DataFrame,
    *,
    regression_months: int = RESIDUAL_MOM_REGRESSION_MONTHS,
    formation_months: int = RESIDUAL_MOM_FORMATION_MONTHS,
) -> tuple[dict[str, pd.DataFrame], ResidualMomentumDiagnostics]:
    """Every arm's monthly score panel, computed in ONE pass over ONE set of
    qualifying months.

    Returns (arm name -> (months x tickers) score frame, diagnostics).

    THE SINGLE MOST IMPORTANT PROPERTY HERE, and the reason the control is not
    computed in its own convenient loop: a month is scored for ALL arms or for
    NONE. The control arm needs no factor data at all and could therefore be
    scored for months where FF3 coverage has run out — which would hand the
    benchmark a timing advantage over the very arms it is the benchmark for, and
    quietly rig the comparison this family exists to make. The qualifying-month
    gate below is computed once, from the FF3 columns, and applied to all three.

    A ticker is scored at a month only if EVERY month of the estimation window
    is present for it. Partial windows are refused, never fitted on what is
    there: BHM require 36 months of history to be eligible, and a fixed n is
    also what makes the standard-deviation-vs-Eq.-9 equivalence exact (module
    docstring section 2)."""
    if formation_months >= regression_months:
        raise ValueError(
            f"formation_months={formation_months} must be strictly less than "
            f"regression_months={regression_months} — see residual_scores_for_window."
        )

    arm_columns = {name: cols for name, cols in RESIDUAL_MOM_ARMS}
    all_factor_columns = tuple(
        dict.fromkeys(c for cols in arm_columns.values() for c in cols)
    )
    aligned = align_factors_to_months(monthly_returns, factors, all_factor_columns)

    diagnostics = ResidualMomentumDiagnostics()
    tickers = list(monthly_returns.columns)
    index = monthly_returns.index
    returns_matrix = monthly_returns.to_numpy(dtype=float)
    rf_vector = aligned["rf"].to_numpy(dtype=float)
    excess_matrix = returns_matrix - rf_vector[:, None]

    scores: dict[str, np.ndarray] = {
        name: np.full((len(index), len(tickers)), np.nan) for name in arm_columns
    }

    for end in range(regression_months - 1, len(index)):
        start = end - regression_months + 1
        # THE QUALIFYING-MONTH GATE. Every factor this family regresses out,
        # plus RF, must be present for every month of the window. Applied once,
        # to all arms, including the control that does not need it.
        factor_window_all = aligned.iloc[start : end + 1].to_numpy(dtype=float)
        diagnostics.n_month_windows += 1
        if not np.isfinite(factor_window_all).all():
            diagnostics.n_months_without_factor_coverage += 1
            continue

        window_excess = excess_matrix[start : end + 1, :]
        complete = np.isfinite(window_excess).all(axis=0)
        n_incomplete = int((~complete).sum())
        if n_incomplete:
            diagnostics.n_refused["incomplete_estimation_window"] += n_incomplete
        if not complete.any():
            continue

        excess_complete = window_excess[:, complete]

        for name, columns in arm_columns.items():
            if not columns:
                arm_scores = _control_scores_for_window(
                    excess_complete, formation_months=formation_months
                )
            else:
                factor_window = aligned.iloc[start : end + 1][list(columns)].to_numpy(dtype=float)
                arm_scores = residual_scores_for_window(
                    excess_complete, factor_window, formation_months=formation_months
                )
                # The _MIN_RESIDUAL_STD degeneracy refusal, counted per arm so
                # a guard that never fires is visibly a guard that never fired
                # rather than one nobody measured.
                n_degenerate = int((~np.isfinite(arm_scores)).sum())
                if n_degenerate:
                    diagnostics.n_refused[f"degenerate_residual_std_{name}"] += n_degenerate
            scores[name][end, complete] = arm_scores

        diagnostics.n_scored += int(complete.sum())

    frames = {
        name: pd.DataFrame(matrix, index=index, columns=tickers)
        for name, matrix in scores.items()
    }
    return frames, diagnostics


def build_residual_momentum_observations(
    score_frame: pd.DataFrame,
    *,
    publication_lag_days: int = FF3_PUBLICATION_LAG_DAYS,
) -> dict[str, list[FactorObservation]]:
    """Turn a monthly score panel into the sibling quality families'
    availability-dated observation lists.

    `end` is the score's LAST DATA MONTH-END; `available` is that plus the
    factor publication lag. The step-panel builder forward-fills from
    `available` only, so a score cannot be used before its inputs were
    published (module docstring section 3).

    The availability >= data-end invariant is ASSERTED rather than trusted,
    because a negative lag would be the one bug in this family that produces a
    better-looking result while remaining completely invisible in the output."""
    if publication_lag_days < 0:
        raise ValueError(
            f"publication_lag_days={publication_lag_days} is negative — that would make a "
            "score visible BEFORE the factor data it is computed from was published."
        )
    observations: dict[str, list[FactorObservation]] = {}
    for ticker in score_frame.columns:
        column = score_frame[ticker]
        events: list[FactorObservation] = []
        for timestamp, value in column.items():
            if not np.isfinite(value):
                continue
            data_end: date = timestamp.date()
            available = data_end + timedelta(days=publication_lag_days)
            assert available >= data_end, "score availability must not precede its data end"
            events.append(FactorObservation(end=data_end, value=float(value), available=available))
        observations[ticker] = events
    return observations


# --- the two pre-declared conditionings --------------------------------------


def signal_residual_momentum(history: CrossSectionalData) -> pd.Series:
    """RAW conditioning: the residual-momentum score at the formation date,
    top-is-long (standard momentum sign — high residual momentum is the winner
    leg, low the loser leg).

    All the real work — the rolling regressions, Eq. 9, the publication lag —
    is already in the panel this reads. This function takes the last row of a
    history view the harness has already truncated to rows <= the formation
    date, which is the structural look-ahead guarantee. NaN refuses the ticker
    from ranking, the correct answer for "this name's residual momentum is
    unobservable or stale here"."""
    frame = history.fundamental_signal
    if frame is None:
        raise ValueError(
            "signal_residual_momentum requires CrossSectionalData.fundamental_signal; the spec "
            "must set requires_fundamental_signal=True and the caller must supply the frame."
        )
    row = frame.iloc[-1].astype(float)
    return row.where(np.isfinite(row))


def signal_residual_momentum_industry_neutral(
    history: CrossSectionalData,
    *,
    bucket_frame: pd.DataFrame,
    min_bucket_size: int = MIN_BUCKET_SIZE,
) -> pd.Series:
    """INDUSTRY-NEUTRAL conditioning: the deviation of a name's residual-
    momentum score from its own industry bucket's MEDIAN, computed
    cross-sectionally over THIS formation's eligible ranked names only.

        signal_i = score_i(t) - median_{b(i)}(t)

    WHY THIS AXIS EXISTS AT ALL, given that the score is already
    factor-orthogonalized: residualizing against FF3 removes market, size and
    value exposure. IT DOES NOT REMOVE INDUSTRY. Energy names can share a large
    common residual in an oil rally, so a residual-momentum sort can still be an
    industry bet — the exact failure mode that killed the sibling NOA family's
    apparent positive. Both conditionings are pre-declared in ONE grid under ONE
    denominator so the confound test is half the grid rather than a follow-up
    designed after seeing a confounded result.

    THE MEDIAN, NOT THE MEAN, is the pre-declared center: the score is a ratio
    whose denominator can be small for a quiet stock, so its tails are heavy and
    a bucket mean is dragged by a single outlier. Mean centering is NOT in this
    grid and so cannot be selected post-hoc.

    Conditioning on the ELIGIBLE cross-section is deliberate and inherited from
    the sibling neutral family: the harness hands this function a view whose
    columns are already restricted to the formation date's point-in-time
    members, so bucket medians are computed among the names actually being
    ranked — never over departed members or unpriced names. A name with no
    bucket, or whose bucket has fewer than min_bucket_size ranked members at
    this formation, is refused (NaN)."""
    frame = history.fundamental_signal
    if frame is None:
        raise ValueError(
            "signal_residual_momentum_industry_neutral requires CrossSectionalData."
            "fundamental_signal; the spec must set requires_fundamental_signal=True and the "
            "caller must supply the frame."
        )
    row = frame.iloc[-1].astype(float)
    formation_ts = frame.index[-1]
    buckets = bucket_frame.loc[formation_ts].reindex(row.index)

    valid = np.isfinite(row.to_numpy()) & buckets.notna().to_numpy()
    values = row[valid]
    if values.empty:
        return pd.Series(np.nan, index=row.index, dtype=float)
    labels = buckets[valid]
    grouped = values.groupby(labels)
    center = grouped.transform("median")
    sizes = grouped.transform("size")
    demeaned = (values - center).where(sizes >= min_bucket_size)
    return demeaned.reindex(row.index).astype(float)


# --- the pre-declared family -------------------------------------------------


def build_residual_momentum_family(bucket_frame: pd.DataFrame) -> list[CrossSectionalSpec]:
    """The 18 pre-declared specs.

    The GRID (arms x conditionings x holds, and the count of 18) is fixed in the
    module constants above and in the pre-registration; the bucket frame is
    runtime DATA injected into the neutral specs' signal closures, never a
    searched-over axis.

    NOTE ON THE SIGNAL FRAME: all three arms share ONE signal function and are
    distinguished by WHICH score panel is handed to the harness, so a spec's
    pattern_id names its arm but its signal_fn does not know which arm it is.
    That is why `run_residual_momentum_screening` screens one arm at a time and
    passes n_trials_override — see there."""
    specs: list[CrossSectionalSpec] = []
    for arm, _columns in RESIDUAL_MOM_ARMS:
        for conditioning in RESIDUAL_MOM_CONDITIONINGS:
            if conditioning == "raw":
                signal_fn = signal_residual_momentum
                suffix = ""
            else:
                signal_fn = partial(
                    signal_residual_momentum_industry_neutral, bucket_frame=bucket_frame
                )
                suffix = "_neutral"
            for holding in RESIDUAL_MOM_HOLDING_DAYS:
                specs.append(
                    CrossSectionalSpec(
                        pattern_id=f"rm_{arm}{suffix}_ls_h{holding}",
                        family=RESIDUAL_MOM_FAMILY,
                        citation=RESIDUAL_MOMENTUM_CITATION,
                        signal_fn=signal_fn,
                        lookback_days=QUALITY_SIGNAL_LOOKBACK_ROWS,
                        holding_days=holding,
                        portfolio="long_short",
                        rank_fraction=QUALITY_RANK_FRACTION,
                        requires_fundamental_signal=True,
                    )
                )

    assert len(specs) == RESIDUAL_MOM_N_TRIALS == 18, (
        f"residual momentum built {len(specs)} definitions; the declared grid implies "
        f"{RESIDUAL_MOM_N_TRIALS} and the pre-registration froze exactly 18. All three must "
        "agree — a drift silently changes this family's DSR denominator."
    )
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    assert all(s.requires_fundamental_signal for s in specs)
    assert all(s.portfolio == "long_short" for s in specs)
    assert all(s.rank_fraction == QUALITY_RANK_FRACTION for s in specs), (
        "deciles throughout — BHM's own sort. The rank fraction is NOT a grid axis here."
    )
    assert all(s.holding_days in RESIDUAL_MOM_HOLDING_DAYS for s in specs)
    return specs


def repool_deflated_sharpe(
    results: list[CrossSectionalScreeningResult],
    *,
    n_trials: int = RESIDUAL_MOM_N_TRIALS,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
) -> list[CrossSectionalScreeningResult]:
    """Recompute every result's DSR against a sigma_SR pooled over ALL of them.

    WHY THIS IS NEEDED. This family screens in three passes (one per arm,
    because each arm ranks a different score panel). `n_trials_override` already
    fixes the DSR denominator at 18 in every pass, but sigma_SR is computed
    inside each call from that call's own siblings — so without this, each arm's
    DSR would be deflated against the dispersion of its own 6 Sharpes rather
    than the 18 the search actually spanned. sigma_SR is meant to describe the
    whole searched family.

    This is a STRICT RE-DERIVATION from numbers already computed, not a second
    backtest: the per-observation Sharpe, sample size, skewness and kurtosis all
    come from each result's existing DeflatedSharpeResult. Only sigma_SR — and
    therefore SR0 and the DSR — change.

    Note the direction of the effect is NOT chosen: pooling can raise or lower
    any individual DSR depending on whether the pooled dispersion is wider or
    narrower than that arm's own. It is applied unconditionally, before any
    number is looked at, because it is the correct denominator — not because of
    what it does to the answer.
    """
    if len(results) < 2:
        return results

    # POOLED DENOMINATOR (2026-09-04). This function REPLACES the DSR that
    # screen_cross_sectional_universe already computed, so without this line
    # it would silently undo that function's own pooled correction and hand
    # this family back its old 18-trial denominator.
    n_trials = dsr_n_trials(n_trials)

    sharpes = [r.sharpe_annualized for r in results]
    sigma_sr = float(np.std(sharpes, ddof=1))
    sigma_sr_daily = sigma_sr / np.sqrt(periods_per_year)
    sr0_daily = expected_max_sharpe_under_noise(sigma_sr_daily, n_trials)
    floor_met = n_trials >= MIN_TRIALS_FOR_DSR

    repooled: list[CrossSectionalScreeningResult] = []
    for result in results:
        previous = result.deflated_sharpe
        sr0_annualized: float | None = None
        dsr: float | None = None
        if floor_met and sr0_daily is not None:
            sr0_annualized = sr0_daily * np.sqrt(periods_per_year)
            dsr = probabilistic_sharpe_ratio(
                previous.sharpe_net_daily,
                sr0_daily,
                previous.n_observations,
                previous.skewness,
                previous.kurtosis,
            )
        interpretation = (
            f"This is 1 of N={n_trials} pre-declared configurations in the residual-momentum "
            f"family. sigma_SR is POOLED across all {len(results)} screened specs (not just the "
            "arm this spec was screened in) because the search spanned the whole family — see "
            "repool_deflated_sharpe. "
            + (
                f"Adjusting for that search and for this run's own sample size "
                f"({previous.n_observations} days), skew and kurtosis, there is an estimated "
                f"{dsr:.0%} probability that this strategy's true long-run Sharpe exceeds "
                f"{sr0_annualized:.2f}, the Sharpe expected from the best of {n_trials} "
                "equally-skilled, zero-edge trials by chance alone."
                if dsr is not None and sr0_annualized is not None
                else "The multiple-comparisons benchmark could not be computed."
            )
        )
        result.deflated_sharpe = replace(
            previous,
            n_trials=n_trials,
            sigma_sr_annualized=sigma_sr,
            expected_max_sharpe_noise_annualized=sr0_annualized,
            dsr=dsr,
            dsr_floor_met=floor_met,
            interpretation=interpretation,
        )
        repooled.append(result)
    return repooled


def specs_for_arm(all_specs: list[CrossSectionalSpec], arm: str) -> list[CrossSectionalSpec]:
    """The subset of the family belonging to one arm. Each arm ranks a DIFFERENT
    score panel, and the harness takes one fundamental_signal frame per call, so
    the 18 specs are screened in three passes of 6."""
    return [s for s in all_specs if s.pattern_id.startswith(f"rm_{arm}")]


# --- production entry point --------------------------------------------------


@dataclass
class ResidualMomentumScreeningSummary:
    """run_residual_momentum_screening's full result: the screening output plus
    every measured coverage number a reader needs to interpret it. Typed fields,
    not docstring paragraphs — the discipline the sibling summaries state. A
    result read without these is not interpretable."""

    results: list[CrossSectionalScreeningResult]
    n_trials: int
    universe_size: int
    sample_size: int
    sample_seed: int
    missing_price_data: list[str]
    tickers_without_score: list[str]
    panel_start: date | None
    panel_end: date | None
    formation_start: date
    # Factor-data provenance: which French vintage this run actually ranked on.
    factor_vintage: str = ""
    factor_first_month: date | None = None
    factor_last_month: date | None = None
    factor_sentinel_cells: int = 0
    # Construction constants, echoed so a persisted run records what it used.
    regression_months: int = RESIDUAL_MOM_REGRESSION_MONTHS
    formation_months: int = RESIDUAL_MOM_FORMATION_MONTHS
    publication_lag_days: int = FF3_PUBLICATION_LAG_DAYS
    max_staleness_days: int = RESIDUAL_MOM_MAX_STALENESS_DAYS
    diagnostics: ResidualMomentumDiagnostics = field(
        default_factory=ResidualMomentumDiagnostics
    )
    # THE number that shows the publication lag really bit: the median calendar
    # age of the score in force at the formations actually ranked. Measured, not
    # assumed (module docstring section 3).
    median_signal_age_days: float = float("nan")
    score_range: dict[str, tuple[float, float]] = field(default_factory=dict)
    # Industry-bucket accounting for the neutral half of the grid.
    tickers_without_bucket: list[str] = field(default_factory=list)
    current_sic_fallback_tickers: list[str] = field(default_factory=list)
    bucket_slot_counts: dict[str, int] = field(default_factory=dict)
    n_min_bucket_refusals: int = 0
    cost_bps: float = QUALITY_COST_BPS
    financing_bps_per_year: float = QUALITY_FINANCING_BPS_PER_YEAR
    warnings: list[str] = field(default_factory=list)


def _median_signal_age(
    age_frame: pd.DataFrame,
    formation_start: date,
    *,
    publication_lag_days: int = FF3_PUBLICATION_LAG_DAYS,
) -> float:
    """Median calendar age, in days, of the information the scores in force are
    computed FROM — i.e. days since the score's last DATA MONTH-END, not days
    since it became available.

    THE PUBLICATION LAG IS ADDED BACK ON PURPOSE. build_point_in_time_factor_
    frame measures age from a value's AVAILABILITY date, which for this family
    already has the 45-day lag folded in; reporting that number raw would say
    "the signal is a few days old" about a signal whose newest input is a
    two-month-old factor return. The number that matters for judging how much
    momentum decay this family eats is the age of the DATA, so that is what is
    reported."""
    if age_frame.empty:
        return float("nan")
    window = age_frame[age_frame.index.date >= formation_start]  # type: ignore[attr-defined]
    values = window.to_numpy(dtype=float)
    values = values[np.isfinite(values)]
    return float(np.median(values) + publication_lag_days) if values.size else float("nan")


def _measure_bucket_composition(
    close: pd.DataFrame,
    score_frame: pd.DataFrame,
    bucket_frame: pd.DataFrame,
    formation_start: date,
    holding_days: int,
) -> tuple[dict[str, int], int]:
    """(bucket -> ranked ticker-formation slots, slots refused by
    MIN_BUCKET_SIZE) on the given cadence's formation dates, re-derived exactly
    as the harness derives them, under the same eligibility gate. Measurement
    only — the backtests never read this."""
    positions = np.flatnonzero(close.index.date >= formation_start)  # type: ignore[attr-defined]
    if len(positions) == 0:
        return {}, 0
    slot_counts: Counter = Counter()
    n_refused = 0
    for i in range(int(positions[0]), len(close.index) - 1, holding_days):
        formation_day = close.index[i].date()
        prices = close.iloc[i]
        eligible = [
            t for t in close.columns if was_member(t, formation_day) and np.isfinite(prices[t])
        ]
        values = score_frame.iloc[i][eligible]
        has_value = values[np.isfinite(values.to_numpy())]
        labeled = bucket_frame.iloc[i][has_value.index].dropna()
        sizes = labeled.groupby(labeled).transform("size")
        for bucket, size in zip(labeled, sizes):
            if size >= MIN_BUCKET_SIZE:
                slot_counts[str(bucket)] += 1
            else:
                n_refused += 1
    return dict(slot_counts), n_refused


def run_residual_momentum_screening(
    start: date = MEMBERSHIP_DATA_START,
    end: date | None = None,
    provider: YFinanceProvider | None = None,
    edgar: EdgarXbrlProvider | None = None,
    config: CrossSectionalConfig | None = None,
    factors: FamaFrenchMonthly | None = None,
) -> ResidualMomentumScreeningSummary:
    """THE production entry point: one price fetch, one SIC-history fetch, one
    cached factor file, three arms x 6 specs screened under ONE 18-trial DSR
    denominator.

    WHY THREE SCREENING PASSES AND n_trials_override=18. The harness takes one
    `fundamental_signal` frame per call, and this family's three arms rank three
    DIFFERENT score panels, so they cannot share a call. Screening them
    separately would otherwise give each arm its own 6-trial denominator, which
    would be trial-count laundering: the family really did search 18
    pre-declared definitions and the max is taken over all 18. Passing
    n_trials_override=18 to each pass restores the honest denominator. The
    harness itself refuses an override SMALLER than the specs screened, so this
    can only ever enlarge, never shrink.

    THE SECOND HALF OF THAT PROBLEM, and why `repool_deflated_sharpe` exists:
    n_trials_override fixes the DENOMINATOR but not sigma_SR, which the harness
    computes per call — so each pass would estimate the dispersion of sibling
    Sharpes from its own 6 rather than from all 18. sigma_SR is meant to
    describe the spread of the whole searched family, so this function repools
    it across all 18 results before returning them. Every persisted row
    therefore carries ONE consistent DSR, computed at n_trials = 18 against a
    sigma_SR estimated from 18 siblings — rather than a per-arm number and a
    pooled number competing in the report."""
    if start < MEMBERSHIP_DATA_START:
        raise ValueError(
            f"Residual-momentum screening start {start.isoformat()} predates point-in-time "
            f"membership coverage ({MEMBERSHIP_DATA_START.isoformat()}) — a formation before "
            "that date would silently see an empty universe."
        )
    end = end if end is not None else date.today()  # noqa: DTZ011 — price-fetch end bound only
    provider = provider if provider is not None else YFinanceProvider()
    edgar = edgar if edgar is not None else EdgarXbrlProvider()
    config = config if config is not None else default_quality_config()
    config.formation_start = start
    factors = factors if factors is not None else load_fama_french_monthly()

    warnings: list[str] = []
    sample, universe_size = build_quality_sample(start, end)

    padded_start = start - timedelta(days=RESIDUAL_MOM_PRICE_PADDING_CALENDAR_DAYS)
    close, missing_price = provider.get_price_history(sample, padded_start, end)
    if close.empty:
        return ResidualMomentumScreeningSummary(
            results=[],
            n_trials=RESIDUAL_MOM_N_TRIALS,
            universe_size=universe_size,
            sample_size=len(sample),
            sample_seed=QUALITY_SAMPLE_SEED,
            missing_price_data=missing_price,
            tickers_without_score=[],
            panel_start=None,
            panel_end=None,
            formation_start=start,
            warnings=[*warnings, "No price data resolved for any sampled ticker."],
        )
    if missing_price:
        warnings.append(
            f"{len(missing_price)} of {len(sample)} sampled tickers resolved no price data "
            "(the standing departed-member yfinance gap — see cross_sectional.py)."
        )

    monthly = monthly_returns_from_daily_close(close)
    score_frames, diagnostics = compute_residual_momentum_scores(monthly, factors.frame)
    if diagnostics.n_months_without_factor_coverage:
        warnings.append(
            f"{diagnostics.n_months_without_factor_coverage} of {diagnostics.n_month_windows} "
            "monthly windows had incomplete Fama-French coverage and were scored for NO arm "
            "(including the control, deliberately — see compute_residual_momentum_scores)."
        )

    sic_histories: dict[str, SicHistory]
    sic_histories, _, sic_failed = edgar.fetch_sic_history_for_tickers(list(close.columns))
    if sic_failed:
        warnings.append(f"{len(sic_failed)} tickers produced no SIC history (fetch failures).")
    bucket_frame, no_bucket, sic_fallback = build_point_in_time_bucket_frame(close, sic_histories)
    if sic_fallback:
        warnings.append(
            f"{len(sic_fallback)} tickers bucketed from CURRENT SIC only (no filing header ever "
            f"carried one): {sic_fallback} — a disclosed point-in-time approximation."
        )

    all_specs = build_residual_momentum_family(bucket_frame)
    results: list[CrossSectionalScreeningResult] = []
    unusable_all: set[str] = set()
    score_range: dict[str, tuple[float, float]] = {}
    age_frames: list[pd.DataFrame] = []
    representative_frame: pd.DataFrame | None = None

    for arm, _columns in RESIDUAL_MOM_ARMS:
        observations = build_residual_momentum_observations(score_frames[arm])
        panel, ages, unusable = build_point_in_time_factor_frame(
            close, observations, max_staleness_days=RESIDUAL_MOM_MAX_STALENESS_DAYS
        )
        unusable_all.update(unusable)
        age_frames.append(ages)
        if representative_frame is None:
            representative_frame = panel
        finite = panel.to_numpy(dtype=float)
        finite = finite[np.isfinite(finite)]
        score_range[arm] = (
            (float(finite.min()), float(finite.max())) if finite.size else (float("nan"),) * 2
        )
        arm_specs = specs_for_arm(all_specs, arm)
        results.extend(
            screen_cross_sectional_universe(
                CrossSectionalData(close=close, fundamental_signal=panel),
                arm_specs,
                config,
                n_trials_override=RESIDUAL_MOM_N_TRIALS,
            )
        )

    # POOLED sigma_SR across all 18, applied unconditionally before any number
    # is inspected — see repool_deflated_sharpe.
    results = repool_deflated_sharpe(results)

    slot_counts: dict[str, int] = {}
    n_refused = 0
    if representative_frame is not None:
        slot_counts, n_refused = _measure_bucket_composition(
            close, representative_frame, bucket_frame, start, holding_days=63
        )

    return ResidualMomentumScreeningSummary(
        results=results,
        n_trials=RESIDUAL_MOM_N_TRIALS,
        universe_size=universe_size,
        sample_size=len(sample),
        sample_seed=QUALITY_SAMPLE_SEED,
        missing_price_data=missing_price,
        tickers_without_score=sorted(unusable_all),
        panel_start=close.index[0].date(),
        panel_end=close.index[-1].date(),
        formation_start=start,
        factor_vintage=factors.vintage_line,
        factor_first_month=factors.first_month_end.date(),
        factor_last_month=factors.last_month_end.date(),
        factor_sentinel_cells=factors.n_sentinel_cells,
        diagnostics=diagnostics,
        median_signal_age_days=(
            _median_signal_age(age_frames[0], start) if age_frames else float("nan")
        ),
        score_range=score_range,
        tickers_without_bucket=no_bucket,
        current_sic_fallback_tickers=sic_fallback,
        bucket_slot_counts=slot_counts,
        n_min_bucket_refusals=n_refused,
        cost_bps=config.cost_bps,
        financing_bps_per_year=config.financing_bps_per_year,
        warnings=warnings,
    )
