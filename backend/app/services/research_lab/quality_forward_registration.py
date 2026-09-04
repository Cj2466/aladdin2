"""THE TWO DELIBERATE, DISCLOSED FORWARD-VALIDATION REGISTRATIONS OF
2026-08-30: quality_cbop / cbop_ls_h63 and quality_noa_industry_neutral /
noa_neutral_ls_h126_median.

READ THIS BEFORE TREATING EITHER REGISTRATION AS ANYTHING. Neither is a
promotion, and neither claims a validated edge. Both families' own module
docstrings say, in their own words, that they did not clear this project's
bar — cross_sectional_quality.py section 5 calls CbOP "no validated edge"
and "a null result", and cross_sectional_quality_neutral.py section 5 calls
the industry-neutral NOA family an "HONEST NEGATIVE". Those verdicts stand
and are not disputed here. What these rows are is a decision to spend real
calendar time collecting real future data on two pre-committed hypotheses,
recorded here so it can be audited, argued with, or reversed.

This mirrors bab_forward_registration.py — the same mechanism, the same
reasoning register, and the same refusal to let a status word stand in for
evidence — with the differences stated below.

--------------------------------------------------------------------------
WHY THESE TWO, AND WHAT "STRONGEST" ACTUALLY MEANS HERE
--------------------------------------------------------------------------
Both are the best spec of their own pre-declared family by deflated Sharpe,
and both clear DSR >= 0.5 — the level this codebase treats everywhere else
as the line below which a result is an honest negative. From the persisted
cross_sectional_trial_results rows (run tags "quality_build_2026-08-28" and
"noa_neutral_build_2026-08-28", 2,926 realized days each):

  * cbop_ls_h63            Sharpe +0.4565, PSR(0) 0.9397, DSR 0.8174 (n=9)
  * noa_neutral_ls_h126_median  +0.3003, PSR(0) 0.8470, DSR 0.5631 (n=18)

DSR >= 0.5 is a BACKTEST-LEVEL statistical signal, not proof of anything.
It says the spec beat the expected maximum of its own family's correlated
noise trials more often than not. It cannot see a data bug, a sector tilt,
a cost misestimate, or a sequential search across families — and this
project has been burned by exactly that: the RAW NOA family carried DSR up
to 0.968, higher than either number above, and its own verification pass
then showed a static long-financials/tech short-REIT portfolio out-earned
every NOA spec on the same dates. A high DSR was not enough there and is
not enough here.

--------------------------------------------------------------------------
THE HONEST CASE AGAINST EACH, STATED BEFORE ANY FORWARD DATA EXISTS
--------------------------------------------------------------------------
cbop_ls_h63. Sharpe +0.46 on a financials-free cross-section averaging ~68
ranked names (decile legs of ~7), which is a small, noisy cross-section by
the standards of the Ball et al. (2016) result it replicates, and that paper
itself reports post-publication attenuation. Its own family's docstring
concluded no spec "clears an 82% probability of beating its own family's
9-trial noise benchmark, well short of this project's bar". Costs assume
financing_bps_per_year = 0.0 — the standing, disclosed short-borrow
optimism, not an estimate.

noa_neutral_ls_h126_median. Its own family's verdict is that the edge does
NOT survive industry neutralization: the family's best spec (this one) sits
barely above the expected maximum of 18 correlated noise trials (0.254 vs
+0.300), four of nine specs are at or below +0.02, and the paper's own
annual rebalance (h252) is ~zero across all three variants. DSR 0.563 is a
coin flip, and it is the MAXIMUM of the family. That module's closing line
is "do not re-test it here without new data or a genuinely different
hypothesis".
  >>> "THE PAPER'S OWN ANNUAL REBALANCE (h252)" IS FACTUALLY WRONG AND IS
  CORRECTED BY THE "CORRECTION, APPENDED 2026-09-04" SECTION AT THE END OF
  THIS DOCSTRING (section B.2): HHTZ form portfolios MONTHLY; what updates
  annually is the ranking variable, not the portfolio. That correction also
  RECOMMENDS THIS REGISTRATION BE REMOVED. Read it before citing this
  paragraph or this registration as precedent.

FORWARD VALIDATION IS NEW DATA, WHICH IS PRECISELY WHY IT IS THE ONE
LEGITIMATE NEXT TEST AND NOT THE RE-TEST THAT LINE FORBIDS. Every objection
above is an objection about a SAMPLE that has been fully used: the 2015-2026
backward window can answer nothing further about either hypothesis, and any
further slicing of it can only re-describe it under a friendlier
denominator. A forward record accumulates out of data that did not exist at
registration time, so no amount of searching, tuning or subset-redrawing
done before today can have seen it. That is a structural property, not a
statistical technique, and it is what makes this the only remaining test.

--------------------------------------------------------------------------
TWO REGISTRATIONS, NOT ONE — a deliberate departure, disclosed
--------------------------------------------------------------------------
bab_forward_registration.py registers exactly ONE spec and explains why:
registering several of A FAMILY's specs "to see which works" re-imports the
multiple-comparisons problem into the forward test. That reasoning is
honored, not evaded, here — these are ONE spec from each of TWO SEPARATE
pre-declared families testing two unrelated mechanisms (cash-based operating
profitability; within-industry balance-sheet bloat), each pinned by
pattern_id before any forward data exists.

It is still a departure and it still costs something, which must be said
plainly: with two live registrations, "the better of the two" is a selection
over two, and a reader who looks only at whichever one survives is reading a
biased point estimate. Both must be reported, always, including the loser,
and neither may be quietly dropped.

WHY THE BEST BACKWARD SPEC OF EACH FAMILY, and not another variant or a
blend: it is the hypothesis that was actually formed and looked at. Choosing
a different sibling now, or averaging them, would be a fresh selection made
on the same exhausted backward data. Pre-committing to the one that was
actually seen is the honest version of this decision, even though "best of 9
by backward Sharpe" is exactly the kind of selection that biases the point
estimate — which is the whole reason a clean forward sample is what is being
collected.

--------------------------------------------------------------------------
HOW TO READ THESE ROWS, AND WHAT WOULD COUNT
--------------------------------------------------------------------------
 * Graduation (status "forward_validated") means ONLY that enough real
   out-of-sample data has accumulated to be worth looking at. It is never a
   verdict. See cross_sectional_forward_validation_service.
   MIN_FORWARD_COMPLETE_HOLDS.
 * The thresholds differ because the holds do: cbop_ls_h63 graduates at 126
   realized trading days (max(126, 2 x 63) — the pairs floor, reached
   exactly at two complete holds, ~6 months), noa_neutral_ls_h126_median at
   252 (max(126, 2 x 126), ~1 year). Both are TWO completed formations,
   which is thin, and must be stated wherever either is surfaced: two
   independent formations cannot resolve a signal.
 * These are equity families on a 252-day calendar (config.periods_per_year
   = 252), unlike the crypto registration's 365.
 * The honest evidence is the realized daily series and its Sharpe with the
   formation count printed beside it — never the status word alone.
 * A negative forward result is a real result and must be reported as one.
   The trailing-window underperformance rule flags either registration
   permanently and non-reversibly if it earns that, so the outcome cannot
   be quietly waited out.

--------------------------------------------------------------------------
WHAT THE FORWARD PATH CANNOT PROTECT AGAINST HERE — read before trusting it
--------------------------------------------------------------------------
The drift machinery fingerprints the SPEC and the CONFIG. It cannot
fingerprint DATA, and both of these families are data-heavy in ways the
Crypto family is not. See cross_sectional_forward_registry's quality section
for what is closed (the seeded candidate sample is pinned against a live
membership refresh re-drawing it; the companyfacts cache is bounded so
fundamentals cannot freeze; a panel that can rank nothing raises rather than
recording an empty book's exact 0.0 as flat performance) and for the
residuals that are NOT closed (a membership refresh's earliest_overrides, or
a re-vendoring of the membership literals, can still move the candidate
pool; EDGAR restatement and entity-linking hazards are the same ones the
backward run documents).

==========================================================================
CORRECTION, APPENDED 2026-09-04 — THE noa_neutral REGISTRATION IS
RE-REVIEWED AGAINST THE PRIMARY SOURCE AND ITS **REPLACEMENT IS
RECOMMENDED**. THIS IS A RECOMMENDATION AWAITING HUMAN SIGN-OFF, NOT AN
ACTION TAKEN. THE LIVE DATABASE ROW IS DELIBERATELY UNTOUCHED.
==========================================================================
PURE APPEND, same convention as lazy_prices_forward_registration.py's two
correction sections and cross_sectional_quality_neutral.py's addenda:
nothing above is edited, so what was claimed stays visible next to what is
true. THIS CORRECTION CONCERNS noa_neutral_ls_h126_median ONLY. It does
not dispute, revisit or weaken the cbop_ls_h63 registration made in the
same file on the same day; see C.5 for why cbop passes the same test.

--------------------------------------------------------------------------
A. WHAT PROMPTED THIS, AND WHAT WAS RE-DERIVED RATHER THAN INHERITED
--------------------------------------------------------------------------
Commit dd288f9 (2026-09-04) declined five forward-validation candidates,
two of them (asset_growth, residual_momentum) on MECHANISM FIDELITY — the
si_dtc standard: a spec must measure what its source paper actually
measures, not merely clear the informal DSR >= 0.5 screening floor. While
doing that, its own decision record (data/research_runs/asset_growth_
2026-09-01.txt, section D.4) recorded an honest counter-precedent: this
registration has the same shape at a LOWER DSR, and recommended it "deserves
a cadence-fidelity re-review on the same standard". This is that re-review.

It was done from scratch and deliberately does NOT rely on dd288f9's
summary. Every statistic below was re-queried directly from
cross_sectional_trial_results (family_key "quality_noa_industry_neutral",
run_tag "noa_neutral_build_2026-08-28", 9 rows, n_trials=18 on every row,
2,926 realized days each), and every claim about the source paper was
re-read from a freshly retrieved copy of the paper itself. Two of dd288f9's
premises did not survive that; see C.1 and D.

--------------------------------------------------------------------------
B. THE PRIMARY SOURCE, READ RATHER THAN RECALLED
--------------------------------------------------------------------------
Hirshleifer, Hou, Teoh & Zhang, "Do investors overvalue firms with bloated
balance sheets?", Journal of Accounting and Economics 38(1), December 2004,
pp. 297-331. The JAE-accepted manuscript (title page "This Draft: March 29,
2004") was fetched 2026-09-04 from the authors' own posting at
https://haas.berkeley.edu/wp-content/uploads/HHTZ-032904-jae.pdf and
text-extracted with pdftotext. Four findings, each a verbatim quotation:

 B.1  THE INDUSTRY-DEMEANING SANCTION IS REAL — CONFIRMED. Section 3.4:
      "Given the industry variation in NOA noted here, we have verified
      that our main findings remain strong when we industry-demean our net
      operating assets measure (results not reported; see Zhang (2004) for
      an industry study on NOA)."
      This vindicates the citation string on the live row and on this
      family's specs. The industry-neutral AXIS is NOT a deviation, and
      this registration is therefore NOT the residual_momentum failure
      (where BHM do not industry-neutralize and neutralization supplied
      82.7% of the candidate's Sharpe). Stated plainly because it is the
      strongest thing that can be said in this registration's favour.
      ONE QUALIFICATION, not a retraction: the sanction is an unreported
      assertion — "results not reported" — deferring to a separate paper.
      It authorises the construction; it supplies no effect size.

 B.2  THE PORTFOLIOS ARE FORMED **MONTHLY**, NOT ANNUALLY. Section 4.1.1:
      "Every month, stocks are ranked by NOA, placed into deciles, and the
      equal-weighted and value-weighted monthly raw and characteristic
      adjusted returns are computed. We require at least a four-month gap
      between the portfolio formation month and the fiscal year end..."
      Table 4 notes, independently: "Every month between July, 1964 and
      December, 2002, portfolios are formed monthly by assigning firms to
      deciles based on the magnitude of NOA in year t."
      THIS CONTRADICTS THIS FILE'S OWN TEXT ABOVE AND THE RATIONALE ON THE
      LIVE ROW, both of which call h252 "the paper's own annual rebalance".
      What is annual is the VARIABLE — section 3.2: "The NOA, Accruals,
      Size and Book-to-market variables, however, are only updated every
      12 months" — not the portfolio. See D for why this makes the case
      against the registration stronger rather than weaker.

 B.3  DECILES, AND AN EQUAL-WEIGHTED LOW-MINUS-HIGH HEDGE. Table 4's hedge
      row is "a long position in the lowest ranked NOA portfolio and an
      offsetting short position in the highest ranked NOA portfolio". The
      harness's decile long_short at QUALITY_RANK_FRACTION = 0.1 matches
      this. NOT a deviation.

 B.4  THE EFFECT IS LONG-LIVED AND DECAYS SLOWLY. Table 4, equal-weighted
      characteristic-adjusted hedge return: 0.0124/month in year t+1
      (t = 10.31), 0.0083 in t+2 (t = 7.66), 0.0057 in t+3 (t = 5.44);
      the text states "the hedge returns decline by about one-third in
      each successive year". A construction in which a 6-month hold earns
      and a 12-month hold earns nothing is not this profile. See D.3.

 B.5  FINANCIALS ARE IN THE SAMPLE. Table 3 reports "Financials" as one of
      the fourteen Fama-French industry groups and notes NOA decile 1's
      "relatively high presence in the Pharmaceuticals and Financials
      groups". This family's inclusion of financials is FAITHFUL — unlike
      asset_growth, where financials inclusion was counted as a third
      deviation. Recorded so the two decisions are not read as symmetric.

--------------------------------------------------------------------------
C. THE GRID, RE-QUERIED. AND THE DEVIATION THAT ACTUALLY MATTERS
--------------------------------------------------------------------------
All nine persisted rows, re-queried 2026-09-04 and matching this family's
committed docstring table exactly. "centre" is the demeaning statistic;
"naive t" is Sharpe x sqrt(2926/252), the pre-multiplicity t-statistic on
11.61 years, the same convention lazy_prices_2026-09-01 uses:

  spec                          centre  frac   Sharpe    DSR   naive t  legs
  ------------------------------------------------------------------------
  noa_neutral_ls_h126_median *  median  0.1   +0.3003  0.5631   +1.02   9.62
  noa_neutral_ls_h63_median     median  0.1   +0.2596  0.5081   +0.88   9.85
  noa_neutral_ls_h126_quintile  mean    0.2   +0.1156  0.3191   +0.39  19.67
  noa_neutral_ls_h126_mean      mean    0.1   +0.0945  0.2938   +0.32   9.62
  noa_neutral_ls_h252_median    median  0.1   +0.0221  0.2151   +0.08   9.50
  noa_neutral_ls_h252_mean      mean    0.1   +0.0080  0.2013   +0.03   9.50
  noa_neutral_ls_h63_mean       mean    0.1   -0.0535  0.1476   -0.18   9.85
  noa_neutral_ls_h63_quintile   mean    0.2   -0.0641  0.1395   -0.22  20.09
  noa_neutral_ls_h252_quintile  mean    0.2   -0.0670  0.1374   -0.23  19.50
  ------------------------------------------------------------------------
  * = THE REGISTERED SPEC.  All rows: 2,926 days, n_trials 18,
  sigma_sr 0.1368, expected max noise Sharpe 0.2536.

 C.1  dd288f9 NAMED THE WRONG COMPARISON SPEC. Its record cites the
      "literature cadence" sibling as DSR 0.215 — that is
      noa_neutral_ls_h252_MEDIAN, which shares the registered spec's
      NON-paper centring statistic and differs from it only in horizon.
      The genuinely literature-shaped cells are the MEAN-centred ones.
      Correcting this moves the comparison DOWN, not up (0.2013 or 0.1476,
      not 0.2151). The re-review reaches dd288f9's conclusion by a
      different and stronger route, not by accepting its arithmetic.

 C.2  THE DECISIVE DEVIATION IS THE CENTRING STATISTIC, AND IT NEEDS NO
      VIEW ON CADENCE AT ALL. The paper's word is "industry-demean".
      Demeaning is subtraction of the MEAN. This family's own section 2
      says so in its own pre-registration: the bucket mean is the "core
      spec" and the median a "sibling spec" whose stated job is to "check
      the result is not an artifact of bucket-mean outlier sensitivity" —
      i.e. a ROBUSTNESS CHECK on the hypothesis, not the hypothesis.
      Holding the horizon fixed at the registered h126 and changing only
      that one axis:
          noa_neutral_ls_h126_mean    +0.0945   DSR 0.2938
          noa_neutral_ls_h126_median  +0.3003   DSR 0.5631   <- registered
      The centring choice alone supplies +0.2058 of Sharpe, 68.5% of the
      registered spec's total, and it is the ONLY reason any cell of this
      family clears the 0.5 floor. On the paper's own centring statistic
      the family's maximum DSR is 0.3191 and its maximum Sharpe +0.1156.

 C.3  THE JOINT DEVIATION. Against the cell that deviates on neither axis
      under the erroneous annual reading (h252_mean, +0.0080), the
      registered spec's Sharpe is 97.4% attributable to the two deviations
      together. Under the corrected monthly reading the faithful cell is
      h63_mean at -0.0535 and the attribution exceeds 100%.

 C.4  THE MEAN-CENTRED AXIS IS FLAT-TO-NEGATIVE AT EVERY HORIZON:
      -0.0535 (h63) / +0.0945 (h126) / +0.0080 (h252), arithmetic mean
      +0.0163, max naive t +0.32. There is no horizon at which the paper's
      own construction produces a result on this universe.
      THE HONEST COUNTER-READING, stated because it is real: the
      median-minus-mean uplift is +0.3131 / +0.2058 / +0.0141 at h63 /
      h126 / h252, and one can argue the h252 cells are simply the
      noisiest (12 formations, against 24 and 47). True. But that argument
      cuts both ways — it says the family cannot distinguish ANY of these
      cells from each other or from zero, which is this family's own
      stated verdict, and it does not explain why a purely outlier-robust
      re-centring of a signal that updates once a year per firm should
      change the answer by 0.31 of Sharpe at one horizon and 0.01 at
      another. Neither pattern is a mechanism. Both are noise.

 C.5  THE SIBLING REGISTRATION IN THIS FILE PASSES THE SAME TEST, which is
      why this correction is narrow. cbop_ls_h63's family is positive at
      every cadence (+0.457 / +0.438 / +0.333, DSR 0.817 / 0.801 / 0.687)
      with no non-literature axis carrying the result. Registering its
      best point picked from a curve that is above the floor everywhere.
      That is not this situation.

--------------------------------------------------------------------------
D. WHY THE CADENCE CORRECTION MAKES THE CASE WORSE, NOT BETTER
--------------------------------------------------------------------------
 D.1  A defender could reasonably say the harness's `holding` axis fuses
      formation frequency with holding length, so HHTZ's construction
      (monthly formation, returns measured 5-16 months out, overlapping)
      has NO exact analogue in {63, 126, 252} and h126 is a defensible
      compromise. That is a fair steelman and it is accepted as far as it
      goes. It does not touch C.2, which is horizon-free.
 D.2  It also does not survive being applied consistently. If h126 is
      defensible as a compromise, then so is h63, and h63's mean-centred
      cell is NEGATIVE. The compromise argument selects the surviving cell
      after seeing which one survived.
 D.3  B.4 is the substantive point. HHTZ document a hedge return that is
      strongly positive in year t+1 and still significant in t+3, decaying
      about a third per year. The registered spec's profile is the
      opposite: +0.300 at a 6-month hold, +0.022 at a 12-month hold. On
      the paper's own decay profile a 12-month hold should retain most of
      a 6-month hold's edge, not 7% of it. Whatever the h126_median cell
      is capturing, its term structure is not NOA's.
 D.4  The one place the raw sibling family agrees with HHTZ's term
      structure is instructive: quality_noa's h252 cells reach +0.4613 and
      +0.4994 (DSR 0.880, 0.904), i.e. the RAW effect does persist at the
      annual horizon exactly as the paper says it should. That effect was
      already demonstrated to be sector composition. So the only part of
      this family's evidence that matches the paper's temporal signature
      is the part known to be a confound, and the part that survives the
      confound test does not match the signature.

--------------------------------------------------------------------------
E. THE OTHER NUMBERS THAT BEAR ON A CAPITAL-PRESERVATION READING
--------------------------------------------------------------------------
 * NAIVE t = +1.02. Before any multiplicity adjustment at all, over 11.61
   years, the registered spec is a one-sigma result. For scale, the
   lazy_prices registration disclosed its own equivalent as "roughly
   +2.06" and treated that as thin.
 * DECILE LEGS OF 9.6 NAMES, from a 200-ticker seeded sample. This is the
   thinnest cross-section of any live cross-sectional registration.
 * DSR 0.5631 means an estimated 56% probability the true Sharpe exceeds
   0.2536 — the expected best-of-18-noise-trials level. It is the MAXIMUM
   of its family and it is a coin flip. All of this was disclosed at
   registration time and none of it is new; it is restated because the
   registration's defence rested on the forward test resolving it, and E
   plus C.2 together say what the forward test can and cannot resolve.
 * preservation_score = 0.00000. This family WAS scored by the
   2026-09-03 run (data/research_runs/preservation_score_2026-09-03.json,
   generated 2026-09-04T00:44:17, reproduced=True against the persisted
   Sharpe), and the registered spec's path numbers are the worst thing in
   this correction that is not a fidelity argument:
       full-sample Sharpe  +0.3043   (rebuild; persisted +0.3003)
       FIRST-half Sharpe   +0.6581
       SECOND-half Sharpe  -0.0064   <- the edge is gone in half two
       sharpe_decay        -0.6645
       max drawdown        -44.66%
       Calmar              +0.1012
       stability            0.0000   -> preservation_score 0.00000
   The whole of the registered spec's backtested edge sits in the first
   half of the 11.6-year sample and the second half is flat-to-negative.
   That is an entirely independent line of evidence pointing the same way
   as C.2: a real within-industry NOA effect should not switch off
   halfway through the only sample in which it was ever detected.
   THE HONEST QUALIFICATION, because this number is easy to over-read:
   stability = 0 is NOT unique to this row. cbop_ls_h63 (S1 +1.1036,
   S2 -0.0975) and si_ratio_hedged_h21 (S1 -0.1192, S2 +1.0743) also
   score stability 0 and preservation_score 0; only lazy_jaccard_full_
   h126_ivol (stab 0.809, presv +0.0852) does not. Splitting a sample in
   half doubles each half's standard error, and preservation_score.py's
   own caveat 3 calls stability "a coarse screen, not a test". What does
   separate this row is the stability-free variant, where the ranking is
   unambiguous and this registration is LAST of the four:
       lazy_prices  0.1054 | cbop 0.1073 | si_ratio 0.0887 | THIS 0.0421
   preservation_score does not drive this recommendation — a mechanism
   failure is a hard gate no path statistic can lift or impose — but it
   is recorded here because it was built to be applied, and applied it
   agrees with C.2. (A note for whoever checks this next:
   run_preservation_score.py's exclusion list names best_ideas_13f,
   eigenportfolio_statarb, dividend_month_premium, phase_a_intraday_
   expanded and multi_signal_combination — it does NOT exclude this
   family. Read the JSON, not the exclusion list.)

--------------------------------------------------------------------------
F. THE HONEST CASE FOR LEAVING THE ROW ALONE — stated in full, because it
   is not weak and the recommendation below has to beat it
--------------------------------------------------------------------------
 F.1  NOTHING IS AT RISK. This is an observational row. No capital, no
      order path, no execution reference. The direct cost of being wrong
      about it is zero dollars.
 F.2  IT WAS REGISTERED WITH ITS EYES OPEN. The rationale on the live row
      says the family's verdict is an honest negative, that DSR 0.563 is a
      coin flip, and — verbatim — "a negative forward result is the
      EXPECTED outcome here". This is not a registration that overclaimed.
 F.3  PRE-COMMITMENT IS REAL. The spec was pinned by pattern_id before any
      forward data existed, so the forward record is statistically clean
      whatever the spec's provenance. Deregistering after seven days of
      accumulated clock and re-registering something else is itself a
      selection event, and a bad habit to start.
 F.4  ONLY REGISTERING STRONG PRIORS IS ITSELF A BIAS. A forward-validation
      programme that admits only what already looks good will confirm
      itself. Spending cheap calendar time on a weak prior is defensible.

--------------------------------------------------------------------------
G. THE RECOMMENDATION — awaiting human sign-off, NOT actioned
--------------------------------------------------------------------------
RECOMMEND REMOVING THIS REGISTRATION, WITH NO REPLACEMENT SPEC FROM THIS
FAMILY. Ranked reasons:

 G.1  THE si_dtc / asset_growth SHAPE IS PRESENT IN ITS PUREST FORM. The
      spec that clears the floor is not the paper's construction, and
      every spec that is the paper's construction is flat or negative
      (C.2, C.4). asset_growth was declined on exactly this at DSR 0.670
      and residual_momentum at 0.630. This row is 0.563. Keeping it means
      the live set is held to a LOOSER standard than the declined set, and
      the gap runs the wrong way: the weakest evidence gets the calendar
      time. Under a capital-preservation-first objective the asymmetry
      matters more than the row does, because the registered set is the
      pipeline anything would eventually be promoted from.
 G.2  THE FORWARD RECORD WILL NOT ANSWER THE QUESTION IT IS BEING SPENT
      ON. F.3 is right that the test is statistically clean, but a clean
      test of the wrong hypothesis still tests the wrong hypothesis. A
      forward WIN for h126_median would not validate HHTZ 2004, because
      h126_median is not HHTZ's construction; it would validate
      median-centred semiannual industry-neutral NOA, a thing no
      literature predicts and this project would then have to decide what
      to do with. A forward LOSS teaches nothing that C.4 does not
      already say. An experiment with no informative outcome is not worth
      252 trading days of clock, cheap or not.
 G.3  NO REPLACEMENT IS AVAILABLE. Unlike short_interest — where
      si_ratio_hedged_h21 existed as a mechanism-faithful spec above the
      floor and was registered in place of the higher-scoring days-to-
      cover specs — the mechanism-faithful cells here top out at DSR
      0.3191. There is nothing to swap in. Registering h126_mean at
      DSR 0.294 "for fidelity" would be worse: it is below the floor on
      both axes and would spend the same clock on a cell nobody believes.
 G.4  THE FAMILY'S OWN CLOSING INSTRUCTION SHOULD BE HONOURED AS WRITTEN.
      "Do not trade NOA in any form on this universe; do not re-test it
      here without new data or a genuinely different hypothesis." The
      registration argued forward data IS new data, which is true of the
      DATA and not of the HYPOTHESIS: the hypothesis being carried forward
      was selected from the exhausted backward grid, on the axis that
      grid designated a robustness check.

THE ALTERNATIVE, IF CONTINUITY IS PREFERRED. If the reviewer would rather
not stop a running clock, the minimum acceptable action is to RE-LABEL the
row's hypothesis honestly — it is a test of median-centred, semiannually
rebalanced, industry-demeaned NOA, and it is NOT a test of Hirshleifer,
Hou, Teoh & Zhang (2004) — and to record that a forward positive would not
be evidence for the NOA anomaly. That is strictly worse than removal on
G.2, but it is honest, and it is better than leaving the current framing in
place. Either way the "annual rebalance" error in B.2 must be corrected
wherever it is surfaced.

WHAT WOULD REVERSE THIS RECOMMENDATION: a mean-demeaned spec clearing the
floor on a materially wider cross-section than 9.6 names per leg (a NEW
pre-registered run carrying these 18 trials into its denominator), or an
explicit argued human decision to drop the mechanism-fidelity gate — which
would also require revisiting si_dtc (DSR 0.948), asset_growth (0.670) and
residual_momentum (0.630), all of which would then qualify ahead of this.

--------------------------------------------------------------------------
H. WHAT WAS AND WAS NOT TOUCHED — the scope boundary, stated exactly
--------------------------------------------------------------------------
NO DATABASE ROW WAS MODIFIED, DEACTIVATED OR DELETED. The live
cross_sectional_forward_validation_registrations row for
quality_noa_industry_neutral / noa_neutral_ls_h126_median is untouched, its
clock is still running, and its status is unchanged. This re-review was
authorised; the deregistration was not, and stopping a clock that has
accumulated real evidence since 2026-08-28 is the reviewer's call.

NOR CAN THIS FILE'S EDITS REACH THAT ROW. register_or_get_cross_sectional_
forward_validation matches on (user_id, config_hash) and returns any
existing row with `return existing, False` before touching a single field.
The rationale text is written ONLY at creation. So the sentence appended to
NOA_NEUTRAL_REGISTRATION_RATIONALE below cannot and does not alter the
stored rationale on the live row; it applies to a fresh registration only.
That is the same append convention lazy_prices_forward_registration.py uses
and it is stated here so nobody mistakes it for an in-place edit.

No adapter was changed. No entry was added to or removed from main.py's
lifespan(). app/services/execution/ contains ZERO occurrences of
"cross_sectional"/"CrossSectional" and zero occurrences of any
cross-sectional family name (noa, quality_cbop, lazy_prices,
short_interest, best_idea, 13f) — both verified by grep at correction
time. Stated precisely because a loose grep is misleading here: that
package DOES import ForwardValidationRegistration, but that is the
SEPARATE pairs-path table (app/models/forward_validation.py /
forward_validation_registrations), not
cross_sectional_forward_validation_registrations, which nothing under
app/services/execution/ reads. ExecutionControl.trading_halted is
untouched and its model default remains True.

==========================================================================
I. THE RECOMMENDATION IN G IS NOW SIGNED OFF AND **ENACTED**, 2026-09-04.
noa_neutral_ls_h126_median IS RETIRED. THE ROW IS WITHDRAWN, NOT DELETED.
==========================================================================
PURE APPEND again: sections A-H are untouched, including H's statement that
no row was modified, which was true of H and is no longer true of the file
as a whole. THIS SECTION CONCERNS noa_neutral_ls_h126_median ONLY. The
cbop_ls_h63 registration made in this file on the same day is untouched,
still active, and still ticking; C.5 says why it passes the same test.

--------------------------------------------------------------------------
I.1  WHAT AUTHORISED THIS, AND WHAT WAS RE-DERIVED BEFORE ACTING
--------------------------------------------------------------------------
The human owner of this project read G, and asked for one more pass before
anything was touched: verbatim, "check for certain there is no way this
could actually be viable", and if confirmed, to ACT rather than record a
third recommendation. So every load-bearing claim in A-H was re-derived
from scratch rather than inherited:

 * The nine persisted rows were re-queried from cross_sectional_trial_
   results (family_key quality_noa_industry_neutral, run_tag
   noa_neutral_build_2026-08-28, n_trials 18, 2,926 days). Every Sharpe and
   DSR in C matches to four decimals. 68.5% re-computed as
   (0.3003 - 0.0945) / 0.3003 = 0.6853. Naive t re-computed as
   0.3003 x sqrt(2926/252) = +1.02.
 * The HHTZ manuscript was re-fetched INDEPENDENTLY (same URL, fresh
   download, pdftotext) and all four B-quotations were re-found verbatim,
   including the two the correction turns on: "we industry-demean our net
   operating assets measure (results not reported; see Zhang (2004) for an
   industry study on NOA)" and "Every month, stocks are ranked by NOA,
   placed into deciles". Also re-confirmed: the word "median" appears in
   that paper ONLY in descriptive-statistics tables, never once as a
   portfolio-construction or industry-adjustment statistic.
 * preservation_score_2026-09-03.json was re-read directly. Every number in
   E matches, including the qualification that cbop and si_ratio_hedged
   also score 0.
 * The effective_n clustering result was re-derived from its own persisted
   return matrix rather than read off its report.

Nothing weakened. One thing got materially stronger — I.2.

--------------------------------------------------------------------------
I.2  THE NEW FINDING, AND THE REASON THIS IS NOW A MECHANISM FAILURE
     RATHER THAN A FIDELITY ARGUMENT
--------------------------------------------------------------------------
C.2 established that the centring statistic supplies 68.5% of the
registered Sharpe. It did not say WHAT that axis is. It is this:

    signal_median_i - signal_mean_i
        = (median_b - NOA_i) - (mean_b - NOA_i)
        = median_b - mean_b

a CONSTANT for every member of bucket b. NOA_i cancels. Verified directly
against the real signal function rather than left as algebra: feeding
signal_industry_demeaned_noa a right-skewed panel over six buckets, the
median-minus-mean difference has exactly ONE distinct value per bucket and
its within-bucket max-minus-min is 0.0 in all six.

So the axis carrying 68.5% of this registration's Sharpe contains ZERO
within-industry information. It is a per-industry offset, and since
mean_b - median_b is a skewness measure, it is a bet on how right-skewed
each industry's NOA distribution is: short the skewed industries, long the
symmetric ones. That is a BETWEEN-industry tilt — the single thing this
family was created to remove. cross_sectional_quality_neutral.py section 1
exists because the raw NOA family reached DSR 0.968 and was then shown to
be sector composition (a static long-financials/tech, short-REIT portfolio
out-earned every one of its specs on the same dates).

Its size, measured rather than asserted, on the rebuilt daily series behind
data/research_runs/effective_n_return_matrix_2026-09-04.csv.gz (2,926
common days): the difference series (median-centred portfolio returns minus
mean-centred portfolio returns) has an annualized Sharpe of +0.427 at 7.07%
annualized volatility — a HIGHER Sharpe than the +0.304 of the registered
spec it is a component of, on 48% of its volatility. The registered spec is
best described as the paper's construction (Sharpe +0.095) plus an
industry-skewness overlay (Sharpe +0.427) that no literature predicts and
that this project has never hypothesised.

HONEST LIMIT ON THIS FINDING, because it can be over-read: the median-
centred specs' correlation with the raw confounded noa_low family is only
slightly higher than the mean-centred specs' (mean rho 0.523 vs 0.492 over
the nine raw specs; higher for the median cell at all three horizons, and
on the max as well, so the direction is consistent 3/3 — but ~0.03 is a
small difference). The re-introduced tilt is real and it is not the WHOLE
of the old sector bet. The algebra is exact; the "how much of the old
confound came back" question is directionally answered and no more.

--------------------------------------------------------------------------
I.3  THE STEELMAN, BUILT AS WELL AS IT CAN BE BUILT, AND WHY IT LOSES
--------------------------------------------------------------------------
F already stated four defences. The 2026-09-04 pass was specifically asked
to find better ones. It found two that F did not have, and both are real:

 S.1  INDUSTRY-**MEDIAN** ADJUSTMENT IS A GENUINE, MAINSTREAM CONVENTION,
      not merely this project's own robustness sibling. Barber & Lyon,
      "Detecting abnormal operating performance: the empirical power and
      specification of test statistics", Journal of Financial Economics
      41(3), 1996, pp. 359-399, use it as their DEFAULT benchmark —
      verbatim from the paper, retrieved 2026-09-04: "median performance of
      the industry comparison group as our industry performance measure,
      PI_it", with variants defined as "the median performance of firms in
      the same two-digit SIC code" and "the same four-digit SIC code". The
      reason is exactly the reason this family's own section 2 gives for
      including a median sibling: accounting ratios are skewed and
      outlier-prone. So "median centring is arbitrary" would be FALSE, and
      the earlier framing of median as merely "a robustness check" understates
      how defensible the choice would have been ex ante.
 S.2  THE WITHIN-INDUSTRY NOA HYPOTHESIS IS NOT A STRAW MAN. Zhang's
      industry study — the one HHTZ defer to in the demeaning sentence
      itself — reports (abstract, SSRN 900264, "Net Operating Assets as a
      Predictor of Industry Stock Returns") that BOTH the cross-industry
      and the within-industry components of NOA predict returns. So this
      family tests a hypothesis the literature actually asserts, and its
      honest negative is a real failure-to-replicate rather than a badly
      posed question. (NOT VERIFIED, and flagged as such: whether Zhang
      decomposes on means or medians. The full text is paywalled; only the
      abstract-level claim above could be confirmed. If Zhang turned out to
      decompose on medians, S.1 would get stronger — and would still not
      reach I.2, per R.2 below.)

 Plus F.1-F.4 restated in their strongest form: nothing is at risk (no
 capital, no order path); the row was registered with its eyes open and its
 rationale predicts its own negative; pre-commitment by pattern_id makes
 the forward record statistically clean whatever the spec's provenance;
 and only ever registering strong priors is itself a bias.

 And one more the reviewer raised directly: preservation_score = 0.00000 is
 a WEAK discriminator, because cbop_ls_h63 and si_ratio_hedged_h21 score 0
 on it too. That is correct, it is conceded, and E already said it — a 0
 there separates this row from nothing.

WHY THE STEELMAN LOSES ANYWAY. Four independent answers, any one of which
would be sufficient:

 R.1  S.1 IS AN ARGUMENT ABOUT WHAT COULD HAVE BEEN PRE-DECLARED, NOT ABOUT
      WHAT WAS. This family wrote down, before any backtest ran, that the
      bucket mean is the core spec and the median a sibling that exists to
      "check the result is not an artifact of bucket-mean outlier
      sensitivity". Both were then run, and the sibling was registered
      because it scored better. A general literature blessing for medians
      cannot retroactively convert a post-hoc pick of the robustness axis
      into an ex-ante core choice; if it could, every pre-declaration in
      this project would be worth nothing, since some paper somewhere
      sanctions almost any single variant.
 R.2  S.1 SANCTIONS MEDIAN CENTRING AS A **ROBUSTNESS** CHOICE — i.e. as a
      thing that should not change the answer much. Here it changes 68.5%
      of the answer, and I.2 says why: it is not doing outlier-robustness
      work, it is adding a between-industry offset. Barber & Lyon's
      motivation for the median is skew-robustness in a BENCHMARK; nothing
      in that literature predicts a return premium for industry-level NOA
      skewness. A robustness variant that supplies two-thirds of the result
      through an axis the source construct does not contain has stopped
      being a robustness variant.
 R.3  S.2 CUTS AGAINST KEEPING THE ROW ONCE I.2 IS IN HAND. Zhang's
      cross-industry NOA component is about the LEVEL of NOA in an
      industry. I.2's overlay is about the SHAPE of NOA's distribution
      within an industry. They are not the same quantity, so Zhang cannot
      be used to license the overlay — and on THIS universe the
      cross-industry NOA component has anyway already been tested directly
      and found to be a static sector bet.
 R.4  F.1 (nothing is at risk) IS TRUE OF THE DOLLARS AND FALSE OF THE
      PIPELINE. The registered set is the only thing anything is ever
      promoted FROM, and asset_growth (DSR 0.670) and residual_momentum
      (0.630) were both declined on 2026-09-04 for precisely the shape this
      row has, at HIGHER DSRs. Leaving it running means the live set is
      held to a looser standard than the declined set, with the weakest
      evidence getting the calendar time. Under a stated
      capital-preservation-first objective, that asymmetry is the risk, and
      it is not zero just because this particular row is observational.

--------------------------------------------------------------------------
I.4  WHAT RETIREMENT COSTS, PRICED HONESTLY
--------------------------------------------------------------------------
 * FORWARD EVIDENCE DESTROYED: none. Nothing is deleted. Every realized
   day, formation, carry-state value and the full original rationale stay
   on the row exactly as they were; retirement only stops the row being
   loaded for further ticks.
 * FORWARD EVIDENCE FOREGONE: small, and much smaller than "since
   2026-08-28" suggests. The startup wiring that actually creates these
   rows in production landed in commit b19bb3d on 2026-08-31, so the
   production clock cannot predate that — roughly four calendar days
   against a graduation threshold of 252 REALIZED trading days. Under 2% of
   one threshold, and the threshold is itself only two formations, which
   this file already says cannot resolve a signal.
 * DIVERSIFICATION: a real cost, recorded rather than argued away. The
   2026-09-04 clustering run measured the live set's variance-based
   effective N at 3.866 of 5 with this row and 3.077 of 4 without it — so
   removing it costs about 0.79 of an effective bet, and it is the live
   registration least correlated with the other four. Two things bound
   that: the same run reports the population is below its own reliability
   floor (N=5 < 10) and that at this sample size any |rho| below ~0.53 is
   indistinguishable from zero, so the apparent orthogonality is a failure
   to reject independence rather than a measurement of it; and effective-N
   is a reason to add genuinely different bets, never a reason to keep a
   bet whose own mechanism does not hold up.
 * PRECEDENT: F.3's point that deregistering is itself a selection event is
   accepted. It is answered by WHAT was selected on: not the forward
   returns (which nobody has looked at, and which are far too short to look
   at), but the backward construction's fidelity to its own source. That is
   a re-audit of the registration decision, not a peek at its outcome, and
   it is the only kind of withdrawal that does not bias the forward record.

--------------------------------------------------------------------------
I.5  THE VERDICT, AND EXACTLY WHAT WAS DONE
--------------------------------------------------------------------------
RETIRED. G's recommendation stands after a genuine attempt to defeat it,
and I.2 upgrades it from a fidelity argument to a mechanism failure: the
axis carrying two-thirds of the result provably carries no within-industry
information at all, on a family whose entire purpose is within-industry
prediction. No replacement spec is registered, for G.3's reason — the
mechanism-faithful cells top out at DSR 0.3191.

The mechanism is retire_noa_neutral_forward_validation below: a status
transition to RETIRED_STATUS plus a dated closing entry APPENDED to the
row's own registration_rationale, run as an idempotent one-shot startup
step exactly like the registrations above it. Deliberately NOT a DELETE
(the history and the record of the decision are the point), NOT a schema
migration (status is a plain VARCHAR(30) with no CHECK and no enum, so
adding a value costs nothing), and NOT an edit of any existing text (the
closing entry is an append, so the two claims the re-review found wrong
stay visible beside their correction).

It also does the one thing H said could not be done: because this is a
deliberate UPDATE rather than register_or_get's return-existing-untouched,
the "the paper's own annual rebalance (h252)" error is now corrected ON THE
LIVE ROW rather than only in this file. That was the "either way" clause of
G's alternative, and it is honoured here even though removal, not
relabelling, is what was chosen.

WHAT WOULD REOPEN THE QUESTION — unchanged from G, and restated because a
retirement should say what would undo it: a mean-demeaned spec clearing the
floor on a materially wider cross-section than 9.6 names per leg, carried
in a NEW pre-registration whose denominator includes these 18 trials; or an
explicit argued human decision to drop the mechanism-fidelity gate, which
would also have to revisit si_dtc (0.948), asset_growth (0.670) and
residual_momentum (0.630), all of which would then qualify ahead of this.
Either would be a fresh registration with a fresh clock, never an
un-retirement of this row.

--------------------------------------------------------------------------
I.6  SCOPE BOUNDARY FOR THIS CHANGE — re-verified, not inherited from H
--------------------------------------------------------------------------
NOTHING ABOUT CAPITAL CHANGES, AND NOTHING COULD: this was never a
capital-bearing row. Re-checked at retirement time rather than assumed —
app/services/execution/ contains ZERO occurrences of "cross_sectional" or
"CrossSectional" (grep, 2026-09-04), and the only registration table it
reads is the SEPARATE pairs-path forward_validation_registrations via
allocation_resolver, whose TRADEABLE_REGISTRATION_STATUS is
"forward_validated" on that other table. Nothing anywhere reads
cross_sectional_forward_validation_registrations except this family's own
registration modules, the cross-sectional runner and the read-only router.
ExecutionControl.trading_halted is untouched and its model default remains
True. AutonomousPortfolioRunner does not reference this table at all.

The cbop_ls_h63 row is untouched. No other family's registration is
touched. No adapter, no spec, no config, no DSR denominator and no persisted
trial row is touched: cross_sectional_quality_neutral.py's nine specs still
exist and still say exactly what they said, because retiring a forward
registration is not the same as deleting a family, and the backward record
has to stay reproducible.

--------------------------------------------------------------------------
J.  CORRECTION APPENDED 2026-09-04 (LATER THE SAME DAY) — THE RETURN
    DEFINITION UNDER cbop_ls_h63 CHANGED, SO ITS BACKTESTED NUMBER MOVED
--------------------------------------------------------------------------
PURE APPEND. Nothing above this line is edited.

The point-in-time price store (77e77d7..61bd307) shipped with its
total-return convention deliberately left at YAHOO,
r(t) = P(t)/(P(t-1) - D(t)) - 1, so that introducing the store was provably
numerics-neutral, and disclosed in code that the convention is wrong. It is:
it equals the true total return multiplied by 1/(1 - D/P(t-1)), a leverage
applied on ex-dates in proportion to the distribution's size, which on KDP's
2018-07-10 special distribution reports +11.45% for a +1.84% day. The default
is now AdjustmentConvention.CRSP, r(t) = (P(t) + D(t))/P(t-1) - 1. Full
decision record, primary sources and the universe-wide measurement:
data/research_runs/dividend_convention_2026-09-04.txt.

MEASURED EFFECT ON THIS REGISTRATION, everything else held byte-identical
(same store, same EDGAR cache, same universe, same 2026-08-28 window):

    cbop_ls_h63   YAHOO  Sharpe +0.45652857  DSR 0.81736998
                  CRSP   Sharpe +0.45675969  DSR 0.81766810
                  delta         +0.00023112       +0.00029812

It moves UP, by 2 parts in ten thousand, and crosses nothing. The direction
is not evidence for or against the change: the convention's error takes the
sign of the day's own return, so a family's aggregate can land either way.
Also measured: the same numbers hold with `drop_same_day_split_distributions`
on or off, i.e. none of the six same-day split+distribution names in this
project's universes is materially held by this spec.

Section I's own headline figures (Sharpe +0.4565, PSR(0) 0.9397, DSR 0.8174)
were computed under the old convention and are left exactly as written,
because they are the numbers the registration decision was actually made on.
This entry is the correction of record for reading them today.

Nothing about the spec, config_hash, spec_fingerprint, holding period,
portfolio construction or DSR denominator changed. Verified after the change
by running app/main.py's own lifespan sequence twice against a real database:
five rows, byte-identical across both startups, cbop_ls_h63 still in_progress
and noa_neutral_ls_h126_median still retired. ExecutionControl.trading_halted
is untouched and stays True.
"""

import asyncio
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.cross_sectional_forward_validation import (
    CrossSectionalForwardValidationRegistration,
)
from app.services.cross_sectional_forward_validation_service import (
    RETIRED_STATUS,
    register_or_get_cross_sectional_forward_validation,
)
from app.services.research_lab.cross_sectional_forward_registry import (
    QUALITY_CBOP_FAMILY_KEY,
    QUALITY_NOA_NEUTRAL_FAMILY_KEY,
)
from app.services.research_lab.system_account import get_or_create_system_user

logger = logging.getLogger(__name__)

CBOP_PATTERN_ID = "cbop_ls_h63"
NOA_NEUTRAL_PATTERN_ID = "noa_neutral_ls_h126_median"

# The rationales persisted onto the rows themselves (not just in this
# docstring), so a reader of the database — or of the API listing — sees WHY
# each registration exists without having to find this file. Condensed forms
# of the module docstring above, which remains the full statement.

CBOP_REGISTRATION_RATIONALE = (
    "DELIBERATE, DISCLOSED REGISTRATION — NOT AN AUTOMATIC ONE, AND NOT A CLAIM OF VALIDATED EDGE. "
    "cbop_ls_h63 is the best of the 9 pre-declared specs of the cash-based operating profitability "
    "family (Ball, Gerakos, Linnainmaa & Nikolaev 2016, replicated from SEC EDGAR XBRL annual "
    "fundamentals): Sharpe +0.4565, PSR(0) 0.9397, DSR 0.8174 against its own family's 9-trial "
    "denominator over 2,926 realized days (run tag quality_build_2026-08-28). DSR >= 0.5 is a "
    "BACKTEST-LEVEL statistical signal, never proof: this family's own module docstring calls the "
    "result 'no validated edge' and 'a null result', because 0.82 falls well short of this "
    "project's bar. It is also a small cross-section — ~68 ranked names, decile legs of ~7, "
    "financials structurally excluded for lack of COGS-shaped XBRL tags — and Ball et al. "
    "themselves report post-publication attenuation. Costs assume financing_bps_per_year=0.0, the "
    "standing disclosed short-borrow optimism rather than an estimate. "
    "THE WARNING FROM THIS PROJECT'S OWN HISTORY: the sibling raw-NOA family carried a HIGHER DSR "
    "(up to 0.968) and was then shown to be a sector-composition artifact — a static "
    "long-financials/tech short-REIT portfolio out-earned every one of its specs on the same "
    "dates. A high DSR did not survive scrutiny there and is not being treated as sufficient here. "
    "The backward 2015-2026 sample has been fully used and can answer nothing further; forward "
    "validation on data that did not exist at registration time is the only statistically "
    "legitimate remaining test, structurally immune to both look-ahead and data-snooping in a way "
    "no backtest re-slice can be. "
    "READING THE RESULT: graduation means ONLY that enough real out-of-sample data has accumulated "
    "to be worth looking at, never that the signal works. The threshold is 126 realized trading "
    "days = max(the pairs floor of 126, 2 x holding_days=63), i.e. exactly TWO completed "
    "formations, which is thin and must be stated wherever this is surfaced; the evidence is the "
    "realized daily series on this family's 252-day equity calendar with the formation count beside "
    "it, not the status word. A negative forward result is a real result: the trailing-window "
    "underperformance rule flags this registration permanently and non-reversibly if it earns that. "
    "ONE spec of this family is registered, deliberately — registering several would re-import the "
    "multiple-comparisons problem into the forward test — but a SECOND registration from a "
    "different family (quality_noa_industry_neutral / noa_neutral_ls_h126_median) was made the same "
    "day, so 'the better of the two' is a selection over two and BOTH must always be reported, "
    "including the loser."
)

NOA_NEUTRAL_REGISTRATION_RATIONALE = (
    "DELIBERATE, DISCLOSED REGISTRATION — NOT AN AUTOMATIC ONE, AND MADE AGAINST ITS OWN FAMILY'S "
    "STATED NEGATIVE VERDICT, which is not disputed here. noa_neutral_ls_h126_median is the best of "
    "the 9 pre-declared specs of the industry-neutral net-operating-assets family (Hirshleifer, "
    "Hou, Teoh & Zhang 2004, run as the paper's own industry-demeaned robustness construction on "
    "point-in-time SIC buckets read from archived 10-K SGML headers): Sharpe +0.3003, PSR(0) "
    "0.8470, DSR 0.5631 against an 18-trial denominator — this family's own 9 plus the raw NOA "
    "family's 9, carried per that module's standing written pre-declaration so the sequential "
    "search that produced this hypothesis is counted rather than forgotten (run tag "
    "noa_neutral_build_2026-08-28, 2,926 realized days). "
    "THE CASE AGAINST IT, IN ITS OWN FAMILY'S WORDS: the edge does NOT survive industry "
    "neutralization. This spec sits barely above the expected maximum of 18 correlated noise trials "
    "(0.254), four of the nine specs are at or below +0.02, the paper's own annual rebalance (h252) "
    "is ~zero in all three variants, and DSR 0.563 is a coin flip that is also the MAXIMUM of the "
    "family. That module's verdict is an HONEST NEGATIVE and its closing line is 'do not re-test it "
    "here without new data or a genuinely different hypothesis'. "
    "THIS REGISTRATION IS NOT THAT FORBIDDEN RE-TEST: every objection above is an objection about a "
    "SAMPLE that has been fully used, and forward validation accumulates a record out of data that "
    "DID NOT EXIST at registration time — the new data that line asks for, not another slice of the "
    "old. Registering it is a decision to let the one spec that cleared DSR 0.5 be resolved by real "
    "future returns instead of by argument. "
    "READING THE RESULT: graduation means ONLY that enough real out-of-sample data has accumulated "
    "to be worth looking at, never that the signal works. The threshold is 252 realized trading "
    "days = max(126, 2 x holding_days=126), i.e. TWO completed formations (~1 year), which is thin "
    "and must be stated wherever this is surfaced; the evidence is the realized daily series on "
    "this family's 252-day equity calendar with the formation count beside it, not the status word. "
    "Given the backward evidence, a negative forward result is the EXPECTED outcome here and would "
    "be a complete, valued answer — it is a real result and the trailing-window underperformance "
    "rule flags this registration permanently and non-reversibly if it earns one. "
    "ONE spec of this family is registered, deliberately; a SECOND registration from a different "
    "family (quality_cbop / cbop_ls_h63) was made the same day, so 'the better of the two' is a "
    "selection over two and BOTH must always be reported, including the loser. "
    "CORRECTION APPENDED 2026-09-04 (independent re-review from the primary source) — TWO THINGS "
    "ABOVE ARE WRONG AND THIS REGISTRATION'S REMOVAL IS RECOMMENDED. (1) 'The paper's own annual "
    "rebalance (h252)' is factually incorrect: HHTZ form portfolios MONTHLY ('Every month, stocks "
    "are ranked by NOA, placed into deciles', section 4.1.1; 'portfolios are formed monthly', "
    "Table 4 notes, both verbatim from the JAE-accepted manuscript retrieved 2026-09-04). What is "
    "annual is the ranking VARIABLE, not the portfolio, so h252 is the FURTHEST of the three "
    "horizons from the paper's cadence and h63 is the closest. (2) The decisive deviation is not "
    "the horizon at all but the DEMEANING STATISTIC: the paper's word is 'industry-demean', which "
    "is mean-centring, and this family's own pre-declaration designates mean the CORE spec and "
    "median a robustness SIBLING. Holding the horizon fixed, noa_neutral_ls_h126_mean scores "
    "Sharpe +0.0945 / DSR 0.2938 against this spec's +0.3003 / 0.5631 — the non-paper centring "
    "statistic supplies 68.5% of the registered Sharpe and is the ONLY reason any cell of this "
    "family clears the 0.5 floor. On the paper's own centring the family maxes out at DSR 0.3191, "
    "and its mean-centred cells are -0.0535 / +0.0945 / +0.0080 at h63/h126/h252. This is the "
    "si_dtc shape that dd288f9 used to decline asset_growth (DSR 0.670) and residual_momentum "
    "(0.630), present here at a LOWER DSR, with no mechanism-faithful spec available to register "
    "instead. WHAT IS NOT WRONG: the industry-demeaning axis IS the paper's own robustness "
    "construction (section 3.4, verbatim, re-verified), so this is NOT the residual_momentum "
    "failure. The recommendation is recorded in this module's docstring and is AWAITING HUMAN "
    "SIGN-OFF; no row was modified, and this text cannot alter the live row's stored rationale "
    "because register_or_get returns an existing row untouched."
)


def register_quality_forward_validations(
    db: Session, user_id: int, *, started_at: date | None = None
) -> list[tuple[CrossSectionalForwardValidationRegistration, bool]]:
    """Create (or return, idempotently) both quality forward-validation
    registrations, in a fixed order. Returns [(registration, created), ...].

    Idempotent by the same (user_id, config_hash) rule the pairs path uses,
    so re-running this never resets an accumulated track record — which
    matters more here than anywhere else in the codebase, since the whole
    value of a row is the clock it has been running.

    `started_at` exists only so tests can be deterministic; production
    callers pass nothing, and a forward clock therefore cannot be
    backdated into the backward data it was decided on."""
    return [
        register_or_get_cross_sectional_forward_validation(
            db,
            user_id=user_id,
            family_key=family_key,
            pattern_id=pattern_id,
            rationale=rationale,
            started_at=started_at,
        )
        for family_key, pattern_id, rationale in (
            (QUALITY_CBOP_FAMILY_KEY, CBOP_PATTERN_ID, CBOP_REGISTRATION_RATIONALE),
            (
                QUALITY_NOA_NEUTRAL_FAMILY_KEY,
                NOA_NEUTRAL_PATTERN_ID,
                NOA_NEUTRAL_REGISTRATION_RATIONALE,
            ),
        )
    ]


# --- the production entry point: app startup ---------------------------------
#
# WHY STARTUP AND NOT A SCRIPT. These two rows have to exist in the PRODUCTION
# database, and this project's production host (Render, free plan) has no Shell
# — running a one-off script there is a paid feature. A deploy, on the other
# hand, already happens automatically. So the deploy itself carries the
# registration: main.py's lifespan awaits register_quality_forward_validations_
# on_startup() once per process start, before the background runners launch.
#
# WHY THAT IS SAFE TO RUN ON EVERY PROCESS START (and there are many — every
# deploy, and every Render free-tier wake-from-sleep):
#  * register_quality_forward_validations is idempotent on (user_id,
#    config_hash), so a second start returns the SAME row and never resets the
#    accumulated forward clock, which is the entire value of these rows.
#  * It touches no market data. The call resolves the family's own specs and
#    config in memory (build_specs/build_config), fingerprints them and writes
#    at most one indexed row per family. build_live_panel — the EDGAR/yfinance
#    path — is only ever called by the runner's tick, never here, so startup
#    cannot block on a network fetch and cannot look like a hung deploy to
#    Render's health check.
#  * It cannot take the API down: every failure is caught and logged, and the
#    next process start simply retries.

STARTUP_FAILURE_LOG_MESSAGE = (
    "Quality forward-validation registration failed on startup. The API is starting anyway "
    "(this is a one-shot setup step, never a startup gate) and the next process start will "
    "retry it idempotently — an existing registration's accumulated clock is unaffected."
)


def _format_registration_outcome(
    registration: CrossSectionalForwardValidationRegistration, created: bool, user_id: int
) -> str:
    """One log line per registration, formatted while the session that loaded
    it is still open — every field below is a lazy/expirable ORM column, and
    reading one off a detached instance raises instead of returning a value."""
    return (
        f"quality forward-validation registration "
        f"{'CREATED' if created else 'ALREADY EXISTS'}: id={registration.id} "
        f"family_key={registration.family_key} pattern_id={registration.pattern_id} "
        f"status={registration.status} user_id={user_id} "
        f"started_at={registration.started_at} "
        f"n_forward_trading_days={registration.n_forward_trading_days} "
        f"threshold={registration.min_trading_days_threshold} "
        f"config_hash={registration.config_hash}"
    )


def register_quality_forward_validations_once() -> list[str]:
    """The SYNCHRONOUS unit of work behind the startup step. Returns one
    human-readable outcome line per registration; raises on any failure (the
    async wrapper is what turns a failure into a log line).

    Owns its own session and closes it in a finally, sharing nothing with the
    request-scoped get_db sessions or with any runner. Ownership is the system
    account, the same convention run_register_quality_forward_validation.py
    and every other autonomously created row in this project uses — a row
    owned by whichever human happened to run a script would be the wrong
    answer for a registration the project as a whole is making.

    SessionLocal is looked up on the module at call time, not bound at import,
    so tests can monkeypatch it exactly the way the runner tests already do."""
    db = SessionLocal()
    try:
        system_user = get_or_create_system_user(db)
        return [
            _format_registration_outcome(registration, created, system_user.id)
            for registration, created in register_quality_forward_validations(db, system_user.id)
        ]
    finally:
        db.close()


async def register_quality_forward_validations_on_startup() -> None:
    """Create-or-confirm both quality forward-validation registrations, once,
    during app startup. NEVER RAISES.

    Dispatched through asyncio.to_thread because the work below is synchronous
    SQLAlchemy and lifespan() is async — the same thread-boundary discipline
    every background runner already follows for its own DB work (see
    AutonomousResearchRunner._tick).

    `except Exception` deliberately, not BaseException: asyncio.CancelledError
    derives from BaseException, so a shutdown that interrupts this still
    cancels rather than being swallowed and logged as a failure."""
    try:
        outcomes = await asyncio.to_thread(register_quality_forward_validations_once)
    except Exception:
        logger.exception(STARTUP_FAILURE_LOG_MESSAGE)
        return
    for outcome in outcomes:
        # "%s", not an f-string into the message: an outcome line carries a
        # config_hash and could in principle contain a % that logging would
        # then try to interpret as a format spec.
        logger.info("%s", outcome)


# --- the retirement of noa_neutral_ls_h126_median (2026-09-04) ---------------
#
# See section I of this module's docstring for the decision and its reasoning.
# What follows is the mechanism only.

# The sentinel that makes the append idempotent independently of the status
# column, so a row cannot end up carrying the closing entry twice even if its
# status were changed by hand between runs. It must appear verbatim inside
# NOA_NEUTRAL_RETIREMENT_NOTE.
NOA_NEUTRAL_RETIREMENT_MARKER = "REGISTRATION RETIRED 2026-09-04"

# APPENDED to the row's existing registration_rationale — never replacing it.
# The original text stays visible, including the two claims the re-review
# found to be wrong, because a record that edits away what it used to say is
# not a record. This is the ONLY channel by which a reader of the database or
# of the API listing (which surfaces registration_rationale verbatim) learns
# that the row is closed and why, so it has to be able to stand alone.
NOA_NEUTRAL_RETIREMENT_NOTE = (
    "\n\n=== " + NOA_NEUTRAL_RETIREMENT_MARKER + " — WITHDRAWN, NOT DELETED. ===\n"
    "This registration is closed and will not accumulate another forward day. Nothing was "
    "deleted: every realized day, formation, carry-state value and counter this row had "
    "already accumulated is preserved on it unchanged, and every word of the rationale above "
    "is preserved verbatim — including the two claims the re-review found to be wrong, which "
    "are corrected below rather than edited out. Only the status changed (to 'retired', which "
    "the forward runner's ACTIVE_STATUSES deliberately excludes) and this entry was appended. "
    "AUTHORITY: an explicit decision by this project's owner on 2026-09-04, taken after asking "
    "for one further maximally-skeptical re-verification of the removal recommendation that had "
    "been appended to this rationale earlier the same day and left deliberately un-enacted. That "
    "re-verification re-derived every claim from the persisted trial rows and from an "
    "independently re-fetched copy of the source paper, and deliberately tried to build the "
    "strongest available case for KEEPING the row first. The case for removal survived it and "
    "one reason got stronger. "
    "REASON 1 — THE SPEC IS NOT THE PAPER'S CONSTRUCTION. Hirshleifer, Hou, Teoh & Zhang (2004, "
    "Journal of Accounting and Economics 38(1), 297-331) write, verbatim, 'we industry-demean "
    "our net operating assets measure'. Demeaning subtracts the MEAN. This family's own written "
    "pre-declaration, fixed before any backtest ran, designates the bucket mean the CORE spec "
    "and the median a robustness SIBLING whose stated job is to check the result is not an "
    "artifact of bucket-mean outlier sensitivity. This row registered the sibling. Holding the "
    "horizon fixed at h126 and changing only that axis: mean-centred Sharpe +0.0945 / DSR "
    "0.2938 against this spec's +0.3003 / 0.5631. The centring statistic supplies 68.5% of the "
    "registered Sharpe and is the only reason any cell of this nine-spec family clears the 0.5 "
    "screening floor; on the paper's own centring the family's maximum DSR is 0.3191. "
    "REASON 2 — THAT AXIS CARRIES NO WITHIN-INDUSTRY INFORMATION AT ALL, which is what turns a "
    "fidelity argument into a mechanism failure and is the finding that was new on 2026-09-04. "
    "The two signals differ by exactly (median_b - NOA_i) - (mean_b - NOA_i) = median_b - "
    "mean_b: a constant within each industry bucket, with the firm's own NOA cancelling out. "
    "Verified directly against the signal function, not left as algebra — the median-minus-mean "
    "difference takes exactly one distinct value per bucket and its within-bucket spread is "
    "0.0. So 68.5% of this registration's Sharpe comes from a per-industry offset, i.e. a bet "
    "on how right-skewed each industry's NOA distribution is (mean minus median IS a skewness "
    "measure) — a purely BETWEEN-industry tilt, which is the exact confound this family was "
    "created to remove after the raw NOA family reached DSR 0.968 and was shown to be sector "
    "composition. Measured on the rebuilt daily series (2,926 common days): the median-minus-"
    "mean difference series has an annualized Sharpe of +0.427 at 7.07% volatility, a higher "
    "Sharpe than the +0.304 of the spec it is a component of. No literature predicts a return "
    "premium for industry-level NOA skewness and this project has never hypothesised one. "
    "REASON 3 — A FACTUAL ERROR IN THE TEXT ABOVE, CORRECTED HERE ON THE ROW. 'The paper's own "
    "annual rebalance (h252)' is wrong. HHTZ form portfolios MONTHLY ('Every month, stocks are "
    "ranked by NOA, placed into deciles', section 4.1.1; 'portfolios are formed monthly', Table "
    "4 notes — both re-verified verbatim from an independently re-fetched copy of the JAE-"
    "accepted manuscript on 2026-09-04). What updates annually is the ranking VARIABLE, not the "
    "portfolio. This correction is NOT the reason for retirement — reason 1 is horizon-free and "
    "the mean-centred cells are flat to negative at every horizon (-0.0535 / +0.0945 / +0.0080 "
    "at h63 / h126 / h252) — but it was load-bearing in the text above, it could not be reached "
    "by any earlier append (register_or_get returns an existing row untouched, so only a "
    "deliberate update like this one can write to it), and it must not be left standing. "
    "REASON 4 — THE PATH STATISTICS AGREE, read with their own caveat. preservation_score is "
    "0.00000: first-half Sharpe +0.6581 collapsing to second-half -0.0064, max drawdown "
    "-44.66%, Calmar +0.1012. A zero there does NOT by itself distinguish this row, because "
    "cbop_ls_h63 and si_ratio_hedged_h21 also score zero on the stability term — that is "
    "conceded, not glossed. What distinguishes it is the stability-free variant, where it ranks "
    "LAST of the four scored live registrations: cbop 0.1073, lazy_prices 0.1054, "
    "si_ratio_hedged 0.0887, this row 0.0421. Its naive pre-multiplicity t-statistic over 11.6 "
    "years is +1.02 and its decile legs average 9.6 names. "
    "THE BEST CASE FOR KEEPING IT, RECORDED BECAUSE IT IS REAL: (a) industry-MEDIAN adjustment "
    "is a mainstream convention, not this project's invention — Barber & Lyon (1996, Journal of "
    "Financial Economics 41(3), 359-399) use 'median performance of the industry comparison "
    "group as our industry performance measure' as their default, precisely because accounting "
    "ratios are skewed; (b) the within-industry NOA hypothesis is one the literature actually "
    "asserts (Zhang, 'Net Operating Assets as a Predictor of Industry Stock Returns', reports "
    "both cross-industry and within-industry components predicting returns), so this family's "
    "negative is a real failure-to-replicate, not a badly posed question; (c) nothing was at "
    "risk here — no capital, no order path; (d) the row was registered with its eyes open and "
    "its own rationale predicts a negative as the expected outcome; (e) de-registering is "
    "itself a selection event and a bad habit to start. These lose on four counts: a general "
    "literature blessing for medians cannot retroactively turn a post-hoc pick of THIS "
    "family's pre-declared robustness axis into an ex-ante core choice; that blessing is for "
    "median as a SKEW-ROBUST benchmark, whereas here the median supplies two-thirds of the "
    "answer through a between-industry offset the source construct does not contain; Zhang's "
    "cross-industry component is about the LEVEL of industry NOA, not the SHAPE of its "
    "distribution, so it cannot license the overlay; and the selection this withdrawal is based "
    "on is the backward construction's fidelity to its own source, NOT the forward returns, "
    "which nobody has looked at and which are far too short to look at — a re-audit of the "
    "registration decision, not a peek at its outcome. "
    "WHAT THIS COSTS: forward evidence destroyed, none. Forward evidence foregone, little — the "
    "startup wiring that creates these rows in production landed 2026-08-31, so this clock is "
    "roughly four calendar days old against a 252-realized-day graduation threshold. "
    "Diversification, about 0.79 of an effective bet by the 2026-09-04 clustering run "
    "(variance-based effective N 3.866 of 5 with this row, 3.077 of 4 without) — a real cost, "
    "bounded by that run's own finding that a 5-strategy population is below its reliability "
    "floor and that any correlation below about 0.53 is indistinguishable from zero at this "
    "sample size. "
    "NO REPLACEMENT SPEC IS REGISTERED FROM THIS FAMILY: the mechanism-faithful cells top out at "
    "DSR 0.3191, so unlike short_interest there is nothing faithful above the floor to swap in. "
    "WHAT WOULD REOPEN THE QUESTION: a mean-demeaned spec clearing the floor on a materially "
    "wider cross-section than 9.6 names per leg, pre-registered afresh with these 18 trials in "
    "its denominator; or an explicit argued decision to drop the mechanism-fidelity gate, which "
    "would also have to revisit si_dtc (DSR 0.948), asset_growth (0.670) and residual_momentum "
    "(0.630), all of which would then qualify ahead of this. Either would be a NEW registration "
    "with a new clock, never an un-retirement of this row. "
    "SCOPE: the sibling cbop_ls_h63 registration is untouched and still active. No other "
    "registration, adapter, spec, config, DSR denominator or persisted trial row is affected. "
    "Nothing under app/services/execution/ reads this table (re-verified by grep at retirement "
    "time) and ExecutionControl.trading_halted remains True. Full reasoning: "
    "quality_forward_registration.py, module docstring, section I."
)


def retire_noa_neutral_forward_validation(
    db: Session, user_id: int
) -> list[tuple[CrossSectionalForwardValidationRegistration, bool]]:
    """Withdraw the noa_neutral_ls_h126_median forward-validation
    registration. Returns [(registration, retired_now), ...] — empty when
    there is no such row.

    IDEMPOTENT, and in the direction that matters: a row already carrying
    RETIRED_STATUS is returned with retired_now=False and is not written to
    at all, so the closing entry cannot be appended twice and the retirement
    cannot be "re-applied" on top of itself. This runs on EVERY process start
    (see the startup wrapper below), which on this project's host means every
    deploy and every free-tier wake-from-sleep.

    NEVER CREATES ANYTHING. If the registration is absent this is a silent
    no-op returning []. That case is not hypothetical — a fresh developer
    database has no such row — and creating one in order to retire it would
    be inventing a decision record that never existed on that database.

    MATCHED ON (user_id, family_key, pattern_id), deliberately NOT on
    config_hash. config_hash is the right key for register_or_get, whose job
    is to avoid duplicating an identical registration; it is the wrong key
    here, because a family whose config has moved since 2026-08-30 would
    hash differently now and the lookup would silently miss the very row it
    exists to close. Withdrawing a hypothesis means withdrawing every row
    that is tracking it, under whatever config it was pinned to — hence a
    list, even though production holds exactly one.

    SCOPED TO ONE user_id, the system account the startup path passes. A row
    some human registered for themselves through the API is that human's to
    close; a startup step reaching across users would be overreach.

    Does NOT touch carry_state_json, day_results_json, formations_json,
    n_forward_trading_days, n_formations, started_at or the existing
    rationale text. The whole point of retiring rather than deleting is that
    the accumulated record survives intact and legible."""
    rows = (
        db.execute(
            select(CrossSectionalForwardValidationRegistration)
            .where(
                CrossSectionalForwardValidationRegistration.user_id == user_id,
                CrossSectionalForwardValidationRegistration.family_key
                == QUALITY_NOA_NEUTRAL_FAMILY_KEY,
                CrossSectionalForwardValidationRegistration.pattern_id
                == NOA_NEUTRAL_PATTERN_ID,
            )
            .order_by(CrossSectionalForwardValidationRegistration.id)
        )
        .scalars()
        .all()
    )

    outcomes: list[tuple[CrossSectionalForwardValidationRegistration, bool]] = []
    changed = False
    for row in rows:
        if row.status == RETIRED_STATUS:
            outcomes.append((row, False))
            continue
        row.status = RETIRED_STATUS
        # Belt and braces against a hand-edited status: the note is appended
        # only if it is not already there, so the text can never double up.
        if NOA_NEUTRAL_RETIREMENT_MARKER not in row.registration_rationale:
            row.registration_rationale = (
                row.registration_rationale + NOA_NEUTRAL_RETIREMENT_NOTE
            )
        changed = True
        outcomes.append((row, True))

    if changed:
        db.commit()
        for row, _ in outcomes:
            db.refresh(row)
    return outcomes


def _format_retirement_outcome(
    registration: CrossSectionalForwardValidationRegistration, retired_now: bool, user_id: int
) -> str:
    """One log line per affected row, formatted while the loading session is
    still open — same reason as _format_registration_outcome: every field
    below is a lazy/expirable ORM column.

    The accumulated counters are printed deliberately. They are the thing a
    reader most needs to see is UNCHANGED across the transition, and printing
    them on the retirement line makes that checkable from Render's log viewer
    alone, without database access this environment does not have."""
    return (
        f"noa_neutral forward-validation registration "
        f"{'RETIRED' if retired_now else 'ALREADY RETIRED'}: id={registration.id} "
        f"family_key={registration.family_key} pattern_id={registration.pattern_id} "
        f"status={registration.status} user_id={user_id} "
        f"started_at={registration.started_at} "
        f"n_forward_trading_days={registration.n_forward_trading_days} "
        f"n_formations={registration.n_formations} "
        f"threshold={registration.min_trading_days_threshold} "
        f"(history preserved; row not deleted — see quality_forward_registration "
        f"docstring section I)"
    )


RETIREMENT_ABSENT_LOG_MESSAGE = (
    "noa_neutral forward-validation registration NOT PRESENT for the system account; nothing to "
    "retire. This is the expected outcome on any database where the registration was never "
    "created, and the step deliberately does not create one in order to close it."
)

RETIREMENT_FAILURE_LOG_MESSAGE = (
    "noa_neutral forward-validation retirement failed on startup. The API is starting anyway "
    "(this is a one-shot step, never a startup gate) and the next process start will retry it "
    "idempotently. Until it succeeds the row keeps its previous status, which means it may tick "
    "on — a stale observational row, with no capital consequence."
)


def retire_noa_neutral_forward_validation_once() -> list[str]:
    """The SYNCHRONOUS unit of work behind the startup step. Returns one
    human-readable outcome line per affected row (empty list when the
    registration is absent); raises on any failure, which the async wrapper
    turns into a log line.

    Owns its own session and closes it in a finally, and looks SessionLocal
    up on the module at call time rather than binding it at import, so tests
    can monkeypatch it exactly as they already do for the registration
    step."""
    db = SessionLocal()
    try:
        system_user = get_or_create_system_user(db)
        return [
            _format_retirement_outcome(registration, retired_now, system_user.id)
            for registration, retired_now in retire_noa_neutral_forward_validation(
                db, system_user.id
            )
        ]
    finally:
        db.close()


async def retire_noa_neutral_forward_validation_on_startup() -> None:
    """Withdraw the noa_neutral registration, once, during app startup.
    NEVER RAISES.

    WHY STARTUP, exactly as for the registrations above: this project's
    production database is a managed Postgres that no development environment
    can reach, and its host's free plan has no Shell, so a one-off script
    cannot be run against it. A deploy is the only automatic, free channel
    into that database — the same channel that CREATED this row — so the
    deploy has to carry the withdrawal too. main.py's lifespan awaits this
    after the registration steps, so on a database where the row does not yet
    exist it is created and then closed in the same process start rather than
    left open until the next one.

    Safe on every process start (there are many — every deploy and every
    wake-from-sleep): it is idempotent, it touches no market data, it writes
    at most one indexed row, and a failure logs rather than aborting startup.

    `except Exception` deliberately, not BaseException, so a shutdown that
    interrupts this still cancels instead of being swallowed as a failure."""
    try:
        outcomes = await asyncio.to_thread(retire_noa_neutral_forward_validation_once)
    except Exception:
        logger.exception(RETIREMENT_FAILURE_LOG_MESSAGE)
        return
    if not outcomes:
        logger.info(RETIREMENT_ABSENT_LOG_MESSAGE)
        return
    for outcome in outcomes:
        logger.info("%s", outcome)


__all__ = [
    "CBOP_PATTERN_ID",
    "CBOP_REGISTRATION_RATIONALE",
    "NOA_NEUTRAL_PATTERN_ID",
    "NOA_NEUTRAL_REGISTRATION_RATIONALE",
    "NOA_NEUTRAL_RETIREMENT_MARKER",
    "NOA_NEUTRAL_RETIREMENT_NOTE",
    "register_quality_forward_validations",
    "register_quality_forward_validations_on_startup",
    "register_quality_forward_validations_once",
    "retire_noa_neutral_forward_validation",
    "retire_noa_neutral_forward_validation_on_startup",
    "retire_noa_neutral_forward_validation_once",
]
