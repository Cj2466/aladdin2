"""THE FOURTH DELIBERATE, DISCLOSED FORWARD-VALIDATION REGISTRATION
(2026-09-03): lazy_prices_jaccard_full / lazy_jaccard_full_h126_ivol.

READ THIS BEFORE TREATING THIS REGISTRATION AS ANYTHING. It is not a
promotion and it does not claim a validated edge. cross_sectional_lazy_
prices.py's own module docstring calls its result an "HONEST NEGATIVE ... a
NUANCED one that must not be rounded off in either direction" against its
own pre-registered pass/fail rule. That verdict stands and is not disputed
here. What this row is is a decision to spend real calendar time collecting
real future data on one pre-committed hypothesis, recorded here so it can be
audited, argued with, or reversed.

This mirrors short_interest_forward_registration.py — the same mechanism,
the same startup path, the same reasoning register, the same refusal to let
a status word stand in for evidence — with the differences stated below.

--------------------------------------------------------------------------
WHAT THE BACKWARD EVIDENCE SAID, AND WHAT IT DID NOT
--------------------------------------------------------------------------
cross_sectional_lazy_prices.py screened 36 pre-declared specs (2 similarity
metrics x 3 document scopes x 3 holding periods x 2 leg weightings) against
the family's own 36-trial DSR denominator, on 7,798 REAL 10-K documents
fetched live from SEC EDGAR for the point-in-time S&P 500 union over
2015-01-07..2026-08-31 (2,926 realized days per spec, run tag
"lazy_prices_2026-09-01"). Its pre-registered bar required a spec with
sharpe > 0 AND dsr >= 0.95; the best spec reached DSR 0.7540, and the
verdict is therefore a fail. Re-derived directly from the persisted
cross_sectional_trial_results rows during this registration (36 of 36 rows
present, bit-for-bit matching the committed run report):

    lazy_jaccard_full_h126_ivol: Sharpe +0.6035, PSR(0) 0.9801, DSR 0.7540,
    n_trials 36, 2,926 realized days, 24 formations, ~87.7 names per leg.

DSR >= 0.5 is a BACKTEST-LEVEL statistical signal, not proof of anything —
the same level that selected cbop (0.8174), noa_neutral (0.5631) and
si_ratio_hedged_h21 (0.7962) for this project's three earlier registrations.
0.7540 sits between si_ratio_hedged_h21 and cbop, ahead of noa_neutral. It
says a spec beat the expected maximum of its own family's correlated noise
trials more often than not. It cannot see a data bug, a universe artifact, a
cost misestimate, or a sequential search across families, and this project
has been burned by exactly that before (the raw-NOA family carried DSR up to
0.968 and was then shown to be a sector-composition artifact).

--------------------------------------------------------------------------
WHY THIS SPEC, AND WHY NO DEVIATION FROM THE TOP-DSR SPEC WAS MADE — the
question the short-interest registration's own precedent requires asking
--------------------------------------------------------------------------
si_ratio_hedged_h21 was registered instead of its family's higher-scoring
days-to-cover specs because those specs measure a DIFFERENT CONSTRUCT than
the paper studies: a post-hoc diagnostic found the days-to-cover long leg
sits at the 72.7th percentile of trading VOLUME and only the 33.2nd
percentile of the short-interest ratio itself — sorting on it is
substantially sorting on volume, not on short interest. That precedent
requires the same question here: does lazy_jaccard_full_h126_ivol measure
what Cohen, Malloy & Nguyen [CMN20] actually studied, or does it measure
something else that happens to correlate with it?

THE ANSWER, CHECKED RATHER THAN ASSUMED: no comparable confound was found,
and no deviation is made.
 * Jaccard is not a proxy standing in for [CMN20]'s measure — it IS one of
   [CMN20]'s own four declared similarity metrics (Sim_Jaccard), implemented
   here exactly as the paper defines it (module docstring section on
   TOKENIZATION).
 * "full" (the whole 10-K, not an extracted section) is [CMN20]'s own
   BASE-CASE scope — its headline 34-58bp/month figure is a whole-document
   number, not a section-level one. This is the opposite of the
   days-to-cover situation, where the winning measure was not in the paper
   at all.
 * "full" scope ALSO had ZERO section-extraction loss in the production run
   (100.0% of same-type pairs scored, against risk_factors' 90.0% and mda's
   87.4%), so unlike the two section-scope panels this one is not
   differentially composed by which filers' section headings happen to
   parse — a cleaner cross-section than either alternative, not a dirtier
   one.
 * A NEW, BOUNDED, ADVERSARIAL SPOT-CHECK was run for this registration
   specifically. >>> THIS BULLET IS CORRECTED, IN PART, BY THE "CORRECTION,
   APPENDED 2026-09-03" SECTION AT THE END OF THIS DOCSTRING: the check
   below was statistically underpowered and measured the wrong length
   variable. Its text is preserved verbatim rather than rewritten, so the
   claim as originally made stays auditable; read the correction before
   relying on any sentence in it. <<<
   The check tested the one confound this project's own history would
   most expect: that whole-document Jaccard, which shrinks whenever a
   filing's vocabulary changes, might mostly be tracking DOCUMENT LENGTH
   GROWTH (a 10-K that only ever adds boilerplate, never removes any) rather
   than genuine language change. 18 real, freshly-fetched consecutive 10-K
   pairs across 9 large-cap tickers (AAPL, MSFT, JNJ, KO, BA, CAT, PG, JPM,
   WMT) were measured: corr(jaccard, length ratio) = 0.197, corr(jaccard,
   length delta) = 0.119 — both weak. Several pairs whose document SHRANK
   year over year (MSFT 0.877x, JPM 0.973x/0.975x, WMT 0.988x/0.971x) still
   showed Jaccard well below 1 (0.85-0.93), which a pure-growth-only model
   cannot produce at all (a shrinking document can only score below 1 if
   real vocabulary was removed, not merely diluted by addition) — direct
   evidence of real term-level turnover, not mechanical growth. THIS CHECK
   IS SMALL AND AD HOC — 18 pairs of large, well-known filers, not the
   full-scale, committed, re-checkable diagnostic short-interest's
   measure_normalizer_divergence() is. It is disclosed as exactly that: a
   spot-check that found no evidence of the suspected confound, not a proof
   that none exists.

Given both of these, the DECISION here is the opposite of short-interest's:
the family's own top-DSR spec is registered AS IS, because — unlike
days-to-cover — nothing was found suggesting it measures a different thing
than the hypothesis under test.

--------------------------------------------------------------------------
THE HONEST CASE AGAINST THIS SPEC, STATED BEFORE ANY FORWARD DATA EXISTS
--------------------------------------------------------------------------
 * ITS OWN FAMILY'S VERDICT IS A NEGATIVE. 0.7540 is not a pass of anything;
   the bar this family set itself was sharpe > 0 AND dsr >= 0.95, and no
   spec reaches it.
 * THE BEST RESULT SITS ON THE THINNEST AXIS, in the family's own stated
   words: the top four of 36 specs are all h126 (24 formations each), the
   cell with the least independent information in the whole grid. The
   honest t-statistic behind Sharpe +0.6035 is roughly +2.06 across an
   11.6-year span BEFORE any multiplicity correction — exactly the size of
   number 36 correlated trials produce by chance.
 * IT IS AN INATTENTION ANOMALY TESTED ON THE LEAST INATTENTIVE UNIVERSE IN
   EXISTENCE. [CMN20] runs the complete U.S. filer universe through 2014;
   this family runs S&P 500 large caps, each covered by dozens of analysts,
   over 2015-2026 — almost entirely after the paper was circulated (2018)
   and published (2020), when filing-diff products are commercially sold.
 * ANNUAL, NOT QUARTERLY. [CMN20] uses 10-K AND 10-Q; this family uses 10-K
   only — strictly less information than the paper's own construction.
 * A KNOWN, UNFIXED DATA GAP. XOM is likely silently excluded from this
   panel today (edgar_filing_text_provider.py shares the root cause fixed
   in edgar_xbrl_provider.py on 2026-09-02 for a different family, and was
   deliberately not itself patched — see LAZY_PRICES_UNIVERSE_RULE and
   data/research_runs/lazy_prices_2026-09-01.txt section 9). One name out of
   roughly 700 is not expected to move this registration's outcome, but the
   size of the effect is unmeasured.
 * COSTS ARE UNDERSTATED. financing_bps_per_year = 0.0, the project's
   standing disclosed short-borrow optimism, not an estimate. This family's
   turnover is genuinely low (an annual signal held 3-6 months), which
   matters less here than in any event-driven family in this project, but it
   only moves the numbers down.
 * SURVIVORSHIP CUTS AGAINST THE HYPOTHESIS, WHICH MAKES THE POSITIVE SIGN
   SLIGHTLY MORE INTERESTING AND STILL NOT SUFFICIENT. The names yfinance
   cannot price are overwhelmingly the acquired and failed ones — exactly
   the firms expected to rewrite risk-factor and litigation language, i.e.
   "changers" belonging in the SHORT leg. Their absence should weaken the
   measured short side; the direction is disclosed, the size is not
   knowable with free data.
 * THE LIVE PANEL THIS REGISTRATION TICKS ON IS THIS PROJECT'S SINGLE MOST
   EXPENSIVE, by a wide margin: rebuilding it means re-listing and
   re-fetching (or, once cached, re-reading) every same-type 10-K pair of
   every point-in-time S&P 500 union member back to 2015. A slow or failed
   build only delays this registration's clock — never any other family's,
   and never any part of order execution — but it is the most likely of the
   four registrations to occasionally sit a tick or several behind the
   others. See cross_sectional_forward_registry's lazy_prices section for
   the full disclosure.

--------------------------------------------------------------------------
WHY FORWARD VALIDATION IS THE ONLY LEGITIMATE REMAINING TEST
--------------------------------------------------------------------------
Every objection above is an objection about a SAMPLE that has been fully
used. The 2015-2026 backward window can answer nothing further about this
hypothesis, and any further slicing of it can only re-describe it under a
friendlier denominator — the move this project has caught and rejected
before. The family's own closing line is that a well-documented honest
negative "leaves the family where it is" — it does not forbid a forward
test, and does not need to: a forward record IS genuinely new data,
accumulating out of observations that did not exist at registration time, so
no amount of searching, tuning or spot-checking done before today can have
seen it. That is a structural property, not a statistical technique.

--------------------------------------------------------------------------
HOW TO READ THIS ROW, AND WHAT WOULD COUNT
--------------------------------------------------------------------------
 * Graduation (status "forward_validated") means ONLY that enough real
   out-of-sample data has accumulated to be worth looking at. It is never a
   verdict. See cross_sectional_forward_validation_service.
   MIN_FORWARD_COMPLETE_HOLDS.
 * The threshold is 252 realized trading days = max(126, 2 x
   holding_days=126) — the SAME two-complete-holds shape as
   noa_neutral_ls_h126_median (~1 year for two annual-scale formations),
   and thinner than it sounds: two independent formations cannot resolve a
   signal, and this is a 126-day-hold family, so "two formations" really is
   the whole clock.
 * This is an equity family on a 252-day calendar (config.periods_per_year =
   252), like every other registration here except the crypto one.
 * The honest evidence is the realized daily series and its Sharpe with the
   formation count printed beside it — never the status word alone.
 * A negative forward result is a real result and must be reported as one.
   The trailing-window underperformance rule flags this registration
   permanently and non-reversibly if it earns that, so the outcome cannot be
   quietly waited out.
 * THERE ARE NOW FOUR LIVE REGISTRATIONS (quality_cbop / cbop_ls_h63,
   quality_noa_industry_neutral / noa_neutral_ls_h126_median,
   short_interest_ratio / si_ratio_hedged_h21, and this one). "The best of
   the four" is a selection over four, and a reader who looks only at
   whichever survives is reading a biased point estimate. All four must
   always be reported, including the losers, and none may be quietly
   dropped.

--------------------------------------------------------------------------
WHAT THE FORWARD PATH CANNOT PROTECT AGAINST HERE
--------------------------------------------------------------------------
The drift machinery fingerprints the SPEC and the CONFIG. It cannot
fingerprint DATA. Residuals specific to this family, all disclosed:

 1. THE (METRIC, SCOPE) PANEL IS DATA, NOT SPEC. All 36 of this family's
    signal functions read CrossSectionalData.fundamental_signal, so which of
    the six similarity panels that slot holds is invisible to the drift
    check. That is why this registration is made under family_key
    "lazy_prices_jaccard_full", exposing only the six jaccard/full specs —
    see cross_sectional_forward_registry's lazy_prices section. A
    risk_factors, mda or cosine spec cannot be registered against this key
    at all.
 2. THE UNIVERSE CAN GROW. The candidate pool is the point-in-time S&P 500
    UNION, and a live membership refresh extends it. A union is additive — a
    name is added only when it really joined the index, and was_member still
    gates it per formation — so the pool is deliberately NOT pinned here,
    exactly like the short-interest registration and unlike the two
    seeded-sample quality registrations.
 3. THE UNFIXED XOM GAP CAN MOVE. If edgar_filing_text_provider.py's CIK
    resolution is fixed later (mirroring the 2026-09-02 fix to the XBRL
    provider), the eligible cross-section gains one name mid-flight. That is
    a data change no spec/config fingerprint can see, exactly like the
    residual described for the quality families' companyfacts cache.
 4. THE FILING-TEXT CACHE CAN BE COLD ON ANY GIVEN DAY. Unlike every sibling
    family's live inputs, this one's dominant cost (7,798+ real document
    fetches to rebuild history) can genuinely fail to complete within a
    single tick on a slow or rate-limited day. A build that does not finish
    simply leaves the registration untouched for the runner to retry — see
    cross_sectional_forward_registry's lazy_prices section for why that
    cannot corrupt the track record or block any other registration.

--------------------------------------------------------------------------
CORRECTION, APPENDED 2026-09-03 — THE ADVERSARIAL CHECK ABOVE WAS
UNDERPOWERED AND MEASURED THE WRONG LENGTH VARIABLE
--------------------------------------------------------------------------
PURE APPEND. Nothing above this section has been rewritten except the
insertion of a pointer to here at the head of the bullet it corrects, so
the claim as originally made stays readable and auditable — the same
convention data/research_runs/lazy_prices_2026-09-01.txt section 9 used
for the XOM gap.

WHAT WAS CLAIMED. The bullet beginning "A NEW, BOUNDED, ADVERSARIAL
SPOT-CHECK" reported corr(jaccard, length ratio) = 0.197 and
corr(jaccard, length delta) = 0.119 over 18 real filing pairs and
concluded that there was no evidence of a document-length-growth
confound. Commit 0c576bb's own message put it more strongly still: the
check "found no evidence that whole-document Jaccard is a
document-length-growth confound". Three things are wrong with that, in
increasing order of importance.

 1. THE CHECK COULD NOT HAVE DETECTED WHAT IT LOOKED FOR. At n = 18, a
    two-sided Fisher-z test at alpha = 0.05 has power 0.12 against a
    true correlation of 0.20 and 0.22 against 0.30. The reported
    r = 0.197 carries a 95% confidence interval of [-0.297, +0.608]:
    that sample cannot tell "no relationship" apart from "a strong
    one". "Weak correlation" described the point estimate, not the
    evidence, and the conclusion drawn from it — "no evidence of a
    confound" — was really "no power to see one".
 2. IT DID NOT REPLICATE, AND THE SIGN REVERSED. Re-measured with this
    project's own tokenizer and provider on 180 real consecutive 10-K
    pairs across 30 different S&P 500 filers (the 9 mega-caps of the
    original check deliberately excluded, so this is out-of-sample),
    corr(jaccard, length ratio) is -0.566 with p = 1.2e-16 — not
    +0.197. The original sign was noise.
 3. IT MEASURED THE WRONG VARIABLE, and this is the substantive error.
    Jaccard is not bounded by raw document length; it is bounded by the
    UNIQUE-VOCABULARY size ratio. Writing |A| for the count of DISTINCT
    surviving tokens in a filing,

        J(A,B) = |A n B| / |A u B|  <=  min(|A|,|B|) / max(|A|,|B|)

    because |A n B| <= min(|A|,|B|) and |A u B| >= max(|A|,|B|). Call
    the right-hand side the VOCABULARY-SIZE CEILING. It knows nothing
    about WHICH words changed — only how much the distinct-word count
    grew or shrank. On the same 180 pairs the ceiling alone explains
    R^2 = 0.524 of Jaccard's variance (Pearson +0.724, Spearman +0.410),
    and its own bottom quintile recovers 19 of the 36 names in Jaccard's
    bottom quintile — 52.8% against a 20% chance baseline. The original
    check never computed it. Its raw-length variables are only loose
    proxies for it: a filing can double in length without adding a
    single new distinct word.

WHAT WAS THEN MEASURED, ON THE REAL PRODUCTION PANEL. The question the
original check should have asked was answered directly rather than by
proxy: does a cross-sectional sort on the vocabulary ceiling ALONE
reproduce this spec's Sharpe? See
data/research_runs/lazy_prices_vocab_ceiling_confound_2026-09-03.txt for
the full run (rebuilt 2015-2026 panel, real EDGAR text, the family's own
backtest path, the same 36-trial DSR denominator) and
data/research_runs/run_lazy_prices_ceiling_confound.py for the exact
invocation. THE RESULT, in two halves that must be read together:

 A. THE CONFOUND READING IS REFUTED. Sorting on the ceiling ALONE, on the
    same rebuilt 2015-2026 panel, with the same quintile / h126 /
    inverse-vol / long_short parameters and the same 36-trial denominator,
    earns Sharpe +0.1875 and DSR 0.2386 — against +0.5741 / 0.7278 for the
    registered spec on that same panel (the rebuilt panel reproduces the
    committed +0.6035 / 0.7540 to within 0.030 Sharpe and 0.027 DSR; all 36
    pattern_ids matched, largest |delta Sharpe| 0.043). That is 33% of the
    Sharpe and a DSR nowhere near either the registered spec's or the
    family's own 0.95 bar. Two of the six ceiling-only specs are outright
    negative. This is NOT the si_dtc situation, and no demotion is
    recommended.
 B. BUT THE CEILING MATTERS MORE THAN THE 18-PAIR CHECK IMPLIED, AND THAT IS
    NOW ON THE RECORD. Three numbers. (1) Removing the ceiling's linear
    cross-sectional projection from Jaccard within each formation costs the
    spec 22% of its Sharpe (+0.5741 -> +0.4483) and drops its DSR from
    0.7278 to 0.5703 — below lazy_cosine_rf_h126_ivol's own 0.6377 on the
    same panel. (2) The ceiling's own short quintile shares 49.0% of its
    names with this spec's short leg, averaged over all 24 real formations,
    against a 20% chance baseline (long leg: 30.1%; the two strategies'
    daily net returns correlate only +0.283). (3) The ceiling explains
    R^2 = 0.489 of Jaccard's variance over 1.6M real panel cells.
    Jaccard also factors EXACTLY into the ceiling and a CONTAINMENT ratio
    o = J(1+1/c)/(1+J) = |A n B|/min(|A|,|B|), verified to 4.4e-16 per cell;
    containment alone earns +0.3766 / DSR 0.4735. Neither half reproduces
    the whole, and the two are near-orthogonal in the cross-section
    (Spearman -0.033), so this spec scores on the INTERACTION of "the
    vocabulary changed size" with "the vocabulary was replaced" — which is a
    more specific and more fragile claim than the registration originally
    made.

 The pre-committed reading rule (written before any full-panel number
 existed, reproduced verbatim in section 7 of the run report) scores this as
 formally MIXED: no confound condition fired, and only one of its three
 acquittal conditions did — the two that failed are exactly the 49.0%
 short-leg overlap and the 0.5703 post-orthogonalization DSR. So: the
 registration stands, unchanged and unenacted-upon by this pass, and a human
 who chooses to demote on those two numbers is not being unreasonable.
 A DEMOTION WAS DELIBERATELY NOT ENACTED HERE — it would reset the forward
 clock, and it needs sign-off, not a verifier's judgement call.
 ONE MORE FINDING THAT ARGUES AGAINST DEMOTING, not for it: the obvious
 fallback lazy_cosine_rf_h126_ivol has no analytic set-size bound (cosine
 reads raw counts and is magnitude-invariant) but is MORE rank-associated
 with its own scope's ceiling than the incumbent is with its own — Spearman
 +0.539 against +0.425 — and rank is what a quintile sort consumes.

TWO LIMITS OF THIS CORRECTION, STATED RATHER THAN LEFT TO BE FOUND.
 * THE PERSISTED RATIONALE ON THE ALREADY-LIVE ROW IS NOT REWRITTEN BY
   THIS CHANGE. register_or_get_cross_sectional_forward_validation
   matches on config_hash — built from family_key, pattern_id and the
   spec/config fingerprints, and deliberately NOT from the rationale
   text — and returns an existing row untouched. So the corrected
   LAZY_PRICES_REGISTRATION_RATIONALE below reaches only a row created
   after this commit; the row created on 2026-09-03 still carries the
   uncorrected wording in its registration_rationale column. That is
   the deliberate choice, not an oversight: rewriting it in place would
   be an undisclosed mutation of a running track record, and forcing a
   new row would reset the forward clock to zero. Anyone reading the
   live row, or the /families listing that surfaces it, must read this
   file alongside it.
 * THE GIT HISTORY OF 0c576bb IS NOT REWRITTEN. Its message still
   carries the overstated sentence, by design. This file is the
   correction of record.

--------------------------------------------------------------------------
CORRECTION, APPENDED 2026-09-04 -- THE XOM CIK-FIX HYPOTHESIS FOR THE
82b69fa REPRODUCTION DRIFT IS TESTED AND REFUTED (a DIFFERENT question from
the 2026-09-03 correction above, which was about the vocabulary-ceiling
confound, not about reproduction drift or XOM)
--------------------------------------------------------------------------
PURE APPEND, same convention as the 2026-09-03 section above and
data/research_runs/lazy_prices_2026-09-01.txt section 9.

WHAT PROMPTED THIS. Commit 82b69fa (run_preservation_score.py, 2026-09-04
00:51 +07) rebuilt this family's own production panel on the SAME window as
the registration (MEMBERSHIP_DATA_START..2026-09-01) and found
lazy_jaccard_full_h126_ivol reproduces at Sharpe +0.5498 against the
committed +0.6035 -- delta -0.0537 -- with 7 further lazy_prices `full`-arm
specs down 0.05-0.10 the same direction, while every `rf`/`mda`-arm spec
reproduced inside tolerance. That commit named the 2026-09-02 XOM CIK-mapping
fix (dcdf864 / 401d98d, "resolve successor-shell CIKs to their predecessor",
deployed for the sibling quality/asset_growth families) as the "leading
candidate explanation" and labelled it explicitly UNVERIFIED.

THE FINDING: REFUTED, on four independent lines of evidence, not one.
 1. THE FIX NEVER TOUCHED THIS FAMILY'S CODE. Reading dcdf864/401d98d shows
    the change lives entirely in edgar_xbrl_provider.py plus cross_sectional_
    quality.py, cross_sectional_quality_neutral.py and cross_sectional_
    asset_growth.py. edgar_filing_text_provider.py -- the provider THIS
    family uses -- has no successor-CIK resolution logic of any kind; its
    get_ticker_cik_map/build_filing_index is a straight ticker->CIK
    passthrough against SEC's live company_tickers.json, exactly as already
    disclosed above and in lazy_prices_2026-09-01.txt section 9.
 2. NO CODE IN THIS FAMILY'S ENTIRE DEPENDENCY CHAIN CHANGED, AT ALL, IN THE
    RELEVANT WINDOW. `git diff --stat 0c576bb 82b69fa -- backend/app` shows
    exactly two files touched anywhere under backend/app between the
    registration and 82b69fa: this file (the 2026-09-03 correction above,
    a docstring-only change) and a brand-new, unrelated module
    (preservation_score.py). sp500_membership_history.py,
    edgar_filing_text_provider.py, cross_sectional_lazy_prices.py and
    cross_sectional.py (the backtest engine) carry zero commits over that
    entire span. A change with no code behind it cannot be a code fix.
 3. XOM IS STILL, TODAY, FULLY EXCLUDED -- RECONFIRMED LIVE, NOT QUOTED FROM
    AN OLD DOCSTRING. A fresh call to EdgarFilingTextProvider().
    get_ticker_cik_map() on 2026-09-04 resolves XOM to CIK 2115436
    ("ExxonMobil Holdings Corp", entityName confirmed via the live
    submissions endpoint) with 29 total filings and ZERO of them 10-K/10-Q
    -- the identical successor-shell state 401d98d's own message describes,
    unaffected by that fix because it was never ported here. A second,
    independent witness agrees: a filing index a7957eb saved 10.5 hours
    earlier (2026-09-03T15:29:18Z) already shows XOM as CIK-resolved and
    indexed with an empty filings list. Two witnesses, ~10.5 hours apart,
    same answer: zero.
 4. THE DECISIVE ABLATION TEST, run rather than argued. The family's own
    unmodified production entry point (run_lazy_prices_screening ->
    screen_lazy_prices_family -> run_cross_sectional_backtest -- no replay
    logic reimplemented) was run twice on the IDENTICAL window used by both
    the original registration and the 2026-09-03 correction above
    (2015-01-07..2026-08-31, NOT 82b69fa's own 2026-09-01 -- see the note on
    that difference below), reusing a7957eb's saved filing index so both
    runs see byte-identical EDGAR data and differ in exactly one input: the
    full point-in-time universe (768 tickers, XOM included) versus that same
    universe with "XOM" -- and only XOM -- removed before pricing and
    filing-index construction (767 tickers). Script:
    data/research_runs/run_xom_hypothesis_test_fast.py (a companion live-
    fetch version, run_xom_hypothesis_test.py, exists for a from-scratch
    re-verification that does not depend on any prior run's cache). All 72
    replays (the family's full 36-spec grid, once with XOM and once
    without) persisted to cross_sectional_trial_results under run_tags
    lazy_prices_xom_included_fast_2026-09-04 and
    lazy_prices_xom_excluded_fast_2026-09-04, not left in a text file alone.

      lazy_jaccard_full_h126_ivol, WITH XOM (768 tickers):    Sharpe 0.5945671  DSR 0.7532862
      lazy_jaccard_full_h126_ivol, WITHOUT XOM (767 tickers): Sharpe 0.5945655  DSR 0.7532857
      delta from removing XOM (the ablation's ENTIRE effect):  Sharpe -0.0000015  DSR -0.0000005

    That delta is floating-point-scale noise -- about 1/35,000th the size of
    the 0.0537 drift under investigation -- and it is not special to the
    registered spec: MAX |delta Sharpe| across ALL 36 pre-declared specs in
    the family, from removing XOM and nothing else, is 0.0000. XOM's
    presence or absence in this family's universe is, to measurement
    precision, INVISIBLE to every spec this family screens.

VERDICT: REFUTED, cleanly, not partially and not ambiguously. The XOM
CIK-mapping fix explains none of the 82b69fa reproduction drift, because the
fix was never wired into any code this family calls and XOM contributes
nothing to this family's panel before, during or after that fix existed.

WHAT THE DRIFT ACTUALLY LOOKS LIKE, HONESTLY REPORTED RATHER THAN EXPLAINED
AWAY. This correction does NOT claim to have found the complete mechanism --
saying so would be exactly the fabricated-confidence this project has a
standing rule against. What is established:
 * The registered spec's Sharpe on a rebuild of the IDENTICAL declared
   window has now been measured FOUR times, by three different runs on three
   different days, and never landed on the same number twice: +0.6035
   (committed, 2026-09-01) -> +0.5741 (this file's 2026-09-03 correction,
   23:11) -> +0.5498 (82b69fa, 2026-09-04 00:51 -- but see the end-date note
   below) -> +0.5946 (this correction's own ablation run A, 2026-09-04
   02:15). That sequence is NOT monotonically decaying, which a persistent,
   one-directional code regression would produce; it moves up, down, and up
   again. Non-monotonic bouncing across nominally-identical reruns is the
   signature of measurement noise from a LIVE input, not a standing defect.
 * NO CODE CHANGED (point 2 above), so the only remaining candidate class is
   the family's own already-disclosed live, non-point-in-time dependencies:
   SEC's ticker->CIK map (a CURRENT-state file, refetched fresh on every
   run, not point-in-time -- the same file whose churn 401d98d's own
   companyfacts-cache fix exists to survive for the sibling families) and
   EDGAR's own filing listings, which grow with every passing day regardless
   of any code path in this project. This file's own 2026-09-03 correction
   already measured this map moving for reasons having nothing to do with
   XOM (604 vs 606 CIKs resolved between 2026-09-01 and 2026-09-03); this
   correction's own live check (point 3 above) used a THIRD snapshot on
   2026-09-04 and did not re-measure the resolved-CIK count, so whether it
   moved a third time is not established here.
 * A SEPARATE, MUNDANE, NON-XOM METHODOLOGICAL DIFFERENCE ALSO APPLIES TO
   82b69fa'S OWN NUMBER SPECIFICALLY, disclosed so it is not mistaken for
   part of the live-data-churn story: 82b69fa's own script invoked
   run_lazy_prices_screening with end=date(2026, 9, 1), one calendar day
   later than the original registration's own window
   (2015-01-07..2026-08-31) and than this correction's own ablation
   (matched to the registration on purpose). One extra trading/filing day is
   consistent with 82b69fa's own reported n_observations=2927 against the
   committed 2926. This does not explain a 0.05 Sharpe move by itself, but
   it means 82b69fa's +0.5498 and this correction's +0.5946 are not directly
   comparable to each other on a like-for-like window -- only each is
   directly comparable to the committed +0.6035, which used the shorter
   window.
 * WHICH SPECIFIC EXTERNAL FACT (which ticker's CIK moved, which filing
   entered or left the panel, or something else in the point-in-time
   pipeline) drives the remaining variation is NOT IDENTIFIED by this
   correction. That is left as an open, disclosed gap rather than asserted
   away -- consistent with this project's standing rule against fabricated
   confidence. What IS established with high confidence is the negative
   result: it is not the XOM fix, and it is not any other code change,
   because no other code changed either.
 * THE HONEST READING TO CARRY FORWARD: this spec's backward Sharpe/DSR is
   not a fixed constant that a "correct" rebuild should reproduce exactly --
   it is a live-data-dependent quantity that has now been measured in the
   0.55-0.60 Sharpe / 0.73-0.75 DSR range across four independent snapshots,
   all well short of the family's own 0.95 DSR bar in every single instance.
   The committed +0.6035/0.7540 was never wrong; it was one honest
   measurement of a quantity that is not perfectly point-in-time-pinned in
   every one of its inputs, a residual this file's own module docstring
   already flagged (see "THE UNIVERSE CAN GROW" and "THE UNFIXED XOM GAP CAN
   MOVE" above) without at the time having a name for the broader mechanism
   -- live CIK-map churn generally, not only via XOM -- that this correction
   now attaches to it.

DOES THIS REQUIRE RE-REGISTERING OR RESETTING THE FORWARD CLOCK? NO, AND
DELIBERATELY NOT. Nothing about the live row's config_hash, spec, holding
period, portfolio construction or DSR denominator changed -- this correction
touches no registration, adapter or spec, exactly like the 2026-09-03
correction before it. The forward-validation clock tracks REAL subsequent
market data against a fixed spec definition; it does not re-derive from
whatever the backward reference backtest says on any given day, and a
backward number bouncing between 0.55 and 0.60 changes nothing about what
the live row has actually earned since 2026-09-03. Re-registering would only
reset an accumulating track record to zero for no benefit.

CBOP AND NOA_NEUTRAL -- FLAGGED, NOT RE-VERIFIED HERE. The other two
EDGAR-XBRL-based live registrations (quality_cbop / cbop_ls_h63,
quality_noa_industry_neutral / noa_neutral_ls_h126_median) sit on
edgar_xbrl_provider.py, which WAS hardened against successor-CIK churn on
2026-09-02 (dcdf864) and was separately re-verified with XOM correctly
included the same day (279641c: MAX|dSharpe|=0.0000 for cbop, 0.0335 for
noa_neutral, neither family's standing moved). In the SAME 82b69fa rebuild
that caught this family's drift, both cbop_ls_h63 and
noa_neutral_ls_h126_median reproduced their OWN persisted Sharpe and DSR
with delta = 0.0000 -- exact reproduction, not merely within tolerance. That
is evidence AGAINST the two of them sharing this family's staleness problem,
not evidence they are immune to all future live-data churn; it is reported
here as a flag for whoever next touches those two registrations, not as a
completed re-verification of them, which is out of this correction's scope.

Reproducibility of this correction itself: data/research_runs/
lazy_prices_xom_hypothesis_test_fast_2026-09-04.txt (the full 36-spec grid)
and run_xom_hypothesis_test_fast.py / run_xom_hypothesis_test.py (the two
scripts, cached-index and live-fetch respectively) are committed alongside
this docstring change.

--------------------------------------------------------------------------
CORRECTION APPENDED 2026-09-04 (SECOND, SAME DAY) -- THE ACTUAL ROOT CAUSE
OF THE REPRODUCTION DRIFT IS FOUND, PROVEN, AND FIXED. IT IS NOT SEC's
TICKER->CIK MAP.
--------------------------------------------------------------------------
PURE APPEND, same convention as both corrections above.

The correction immediately above left the drift (+0.6035 -> +0.5741 ->
+0.5946 -> +0.5498 across four same-window reruns) attributed to "this
family's own already-disclosed live, non-point-in-time dependencies (SEC's
ticker->CIK map, EDGAR's growing filing listings)" without identifying
which one, or proving either was the actual mechanism. Both claims are now
tested directly, and the SEC/EDGAR side is REFUTED while a different,
previously-undiscussed dependency is PROVEN.

TEST 1 -- SEC's ticker->CIK map, re-tested directly. A live call to
EdgarFilingTextProvider().get_ticker_cik_map() on 2026-09-04 was diffed
against a7957eb's own saved filing index (2026-09-03T15:29:18Z, ~13 hours
earlier) for every ticker in the family's point-in-time universe: 0 CIK
values changed, 0 tickers newly resolved, 0 tickers newly unresolved.
SEC's ticker->CIK map is real and disclosed as non-point-in-time in
principle, but it did NOT move over a window comparable to the reruns under
investigation. It is not the mechanism.

TEST 2 -- YFinanceProvider's price data, tested directly and found to be
the actual driver. get_daily_ohlcv (and the sibling get_price_history) call
yf.download(..., auto_adjust=True) with NO caching layer, by explicit
design (see that method's own docstring). auto_adjust=True does not return
a fixed historical record: it back-adjusts the ENTIRE returned series for
every split and cash dividend Yahoo currently knows about, and that
knowledge keeps changing as Yahoo processes new corporate actions.
MEASURED: fetching the identical 625 tickers over the identical
2015-01-07..2026-08-31 window twice, ~5.5 hours apart (2026-09-03 22:54 vs
2026-09-04 04:24), with ZERO code changes, moved 966,719 of 1,700,804
comparable (date, ticker) Close cells at all and 48,968 (2.9%) by more than
1bp, max relative difference 1.15%. Whole multi-year Close series for names
including AIZ, ALL, CBOE, CSX, DD, DOV, EFX, EL, FDS, GLW, NOC, NWL, O, PH
and UNP were uniformly rescaled by a small constant factor across their
ENTIRE history in-sample (a pure back-adjustment-factor shift, which
leaves pct_change()-based returns unaffected because a uniform rescale
cancels in a ratio) -- but for DOW, PCL, Q and FCPT the rescale boundary
fell INSIDE the backtest window (2019-03-20, 2025-08-05, 2025-10-27 and an
unidentified date respectively), which fabricates or erases that one day's
return for that one ticker purely as a side effect of when the fetch
happened to run, an artifact this family's own daily_returns computation
(data.close.pct_change() in cross_sectional.py) has no way to detect or
correct.

THE DECISIVE ISOLATION TEST. Holding EVERY other input byte-identical --
the same six similarity panels (jaccard/cosine x full/risk_factors/mda)
saved by an earlier confound run, the same code, run through the family's
own unmodified screen_lazy_prices_family -- and varying ONLY the
close/half_spread/leg_weight_basis inputs (RUN A: the 2026-09-03 22:54
price snapshot; RUN B: a live fetch 2026-09-04 04:24, ~5.5h later) moved
the registered spec lazy_jaccard_full_h126_ivol's Sharpe from +0.5741 to
+0.5946 (delta +0.0205) and moved OTHER specs in the same family by up to
0.0433 -- with the panels, the code and the universe all held fixed. That
is the same order of magnitude as the +0.6035/+0.5741/+0.5946/+0.5498
drift this correction set out to explain, produced by re-running ONE input
(the live price fetch) a few hours apart. This is not a hypothesis argued
from a docstring; it is a measured causal effect from a controlled
before/after comparison.

VERDICT: PROVEN. YFinanceProvider.get_daily_ohlcv's live, uncached,
auto_adjust=True price series -- not SEC's ticker->CIK map, not EDGAR's
filing listings, not any code defect -- is the dominant driver of this
family's reproduction drift. The two corrections above were honest about
not knowing the mechanism; this one identifies it with a real controlled
experiment rather than continuing to guess between the two disclosed
candidates.

THE FIX, IMPLEMENTED AND VERIFIED IN THIS SAME COMMIT. A free vendor's
continuously-revised adjusted-close series cannot be made retroactively
immutable by anything this project controls, so the fix freezes the
external answer once rather than trying to make Yahoo's data point-in-time:
 * yfinance_provider.save_ohlcv_snapshot / load_ohlcv_snapshot (new):
   persist a get_daily_ohlcv result to disk (gzipped CSV per field, a small
   JSON manifest) and reload it later, mirroring save_filing_index /
   load_filing_index's existing role for the EDGAR side exactly.
 * cross_sectional_lazy_prices.run_lazy_prices_screening gained a new
   `price_frames` parameter (opt-in, exactly like the pre-existing
   `filing_index` parameter): when supplied, the live get_daily_ohlcv call
   never happens and the frozen frames are used instead. Nothing loads
   automatically -- a caller that wants live data (the forward-validation
   tick, build_lazy_prices_live_panel, which correctly must keep tracking
   real new trading days) is completely unaffected and unchanged.
 * DEFAULT_PRICE_SNAPSHOT_DIR (new) and DEFAULT_FILING_INDEX_PATH (pre-
   existing, but never actually populated by any prior commit until now)
   are this family's own frozen reproducibility snapshots for its
   registered window (2015-01-07..2026-08-31, 625 priced tickers, 604
   CIK-resolved, 12,828 filings listed), committed to the repository as
   real artifacts rather than left as unused constants.

PROOF THE FIX WORKS, not just "the code looks more correct now". Both
frozen snapshots were loaded FRESH FROM DISK (not reused in-memory objects)
and run_lazy_prices_screening was called twice in independent invocations.
Result, all 36 pre-declared specs, RUN A vs RUN B:

    registered spec lazy_jaccard_full_h126_ivol:
      RUN A: Sharpe +0.5945672287  DSR 0.7532869753
      RUN B: Sharpe +0.5945672287  DSR 0.7532869753
      delta: 0.0 (exact, to the full double-precision digits printed)

    ALL 36/36 SPECS: delta_sharpe == 0.0 and delta_dsr == 0.0, EXACTLY, for
    every single spec -- not "within tolerance", bit-for-bit identical.
    MAX |delta Sharpe| across the whole grid: 0.00e+00.

Full grid and both runs: data/research_runs/
lazy_prices_ptit_fix_verification_2026-09-04.txt. Both runs' 36-row results
are also persisted to cross_sectional_trial_results under run_tags
lazy_prices_ptit_fix_verification_A_2026-09-04 and
..._B_2026-09-04, per this project's standing "persist real results, not
just a text file" rule. Reproducibility script: data/research_runs/
run_lazy_prices_ptit_fix_verification.py.

ONE HONEST CAVEAT ON WHAT "FIXED" MEANS HERE. This makes THIS family's
backward number reproducible GOING FORWARD, from the frozen 2026-09-04
snapshot onward. It does NOT retroactively explain which exact ticker/date
caused each of the four already-observed historical numbers (+0.6035,
+0.5741, +0.5946, +0.5498) -- those predate any snapshot being frozen, so
their specific per-cell diffs cannot be reconstructed after the fact. What
is established is the MECHANISM (proven, on live data, via a controlled
isolation test) and a working FIX for all future reruns of this window.

DOES THIS REQUIRE RE-REGISTERING, RESETTING THE FORWARD CLOCK, OR TOUCHING
EXECUTION/CAPITAL? NO. Nothing about the live row's config_hash, spec,
holding period, portfolio construction or DSR denominator changed. The live
forward-validation tick (build_lazy_prices_live_panel) is untouched --
it still calls get_daily_ohlcv live, as it must, since forward validation
has to track real new trading days, not a frozen backward snapshot. This
family remains observation-only; ExecutionControl.trading_halted is
untouched by this change and stays True. No capital is at risk from this
correction in any way.

THIS IS NOT SPECIFIC TO LAZY_PRICES, AND IS NOT FIXED PROJECT-WIDE HERE --
DISCLOSED AS AN OPEN RISK. get_daily_ohlcv and get_price_history are the
live, uncached, auto_adjust=True price primitives nearly every
cross-sectional family in this codebase calls to build its own `close` /
returns / vol-basis inputs. quality_cbop (cbop_ls_h63) and
quality_noa_industry_neutral (noa_neutral_ls_h126_median) call
get_price_history, which shares the IDENTICAL auto_adjust=True/no-cache
characteristic get_daily_ohlcv has -- verified by reading yfinance_
provider.py directly, not assumed. Both reproduced their own persisted
Sharpe/DSR EXACTLY (delta 0.0000) in the 82b69fa rebuild that first caught
this family's drift; given TEST 2 above, the most defensible reading is
that no dividend-reprocessing event happened to touch a name actively held
in their specific universe/window at that specific comparison instant --
NOT that those two families are structurally immune to this same
mechanism. Building an equivalent frozen-snapshot fix for every other
family on these two methods is out of scope for this correction (which is
about lazy_prices specifically) and is left here as an explicit, disclosed,
project-wide reproducibility risk for whoever next needs a byte-reproducible
backward number from any family built on get_daily_ohlcv or
get_price_history.

--------------------------------------------------------------------------
CORRECTION APPENDED 2026-09-04 (THIRD, SAME DAY) -- THIS REGISTRATION'S
BACKTESTED NUMBERS MOVE, BECAUSE THE DIVIDEND-ADJUSTMENT CONVENTION
UNDERNEATH THEM WAS WRONG AND HAS BEEN FIXED. THE MOVE IS ABOUT A THIRD OF
WHAT WAS PREVIOUSLY DISCLOSED, AND THAT DIFFERENCE IS ITSELF THE FINDING.
--------------------------------------------------------------------------
PURE APPEND, same convention as the three corrections above. Nothing before
this line is edited.

WHAT CHANGED. The point-in-time price store (77e77d7..61bd307) computes every
adjusted series from stored raw rows under a selectable convention, and
shipped with it deliberately left at YAHOO -- r(t) = P(t)/(P(t-1)-D(t)) - 1,
a faithful reproduction of yfinance's auto_adjust=True -- so that introducing
the store was provably numerics-neutral. That same commit disclosed in code
that the convention is measurably wrong and recommended flipping it in its
own reviewed change. This is that change. The default is now
AdjustmentConvention.CRSP, r(t) = (P(t)+D(t))/P(t-1) - 1.

Yahoo's form is not a level error a cross-sectional ranking could absorb. It
is exactly r_YAHOO = r_CRSP / (1 - D/P(t-1)) -- the true total return
multiplied by a gain that grows with the distribution. Measured on all 144
ordinary distributions above 5% of price in this project's two point-in-time
universes, the sign of the error equals the sign of the true return on every
one of the 143 that has a sign. On KDP's 2018-07-10 special distribution it
reports +11.45% for a day that returned +1.84%.

THE EFFECT ON THIS REGISTRATION, MEASURED THREE WAYS RATHER THAN ONE.
Window 2015-01-07..2026-08-31, everything else held byte-identical -- same
store, same EDGAR filing cache, same universe, same code, one process per arm:

    lazy_jaccard_full_h126_ivol
      YAHOO      (as registered)   Sharpe +0.59456852  DSR 0.75328860
      CRSP       (NEW DEFAULT)     Sharpe +0.58869145  DSR 0.74738924
        delta                             -0.00587708       -0.00589936
      CRSP + the same-day DROP rule Sharpe +0.57771213  DSR 0.73759955
        delta                             -0.01685639       -0.01568905

THE -0.0169/-0.0157 FIGURE PREVIOUSLY DISCLOSED FOR "FLIPPING THE
CONVENTION" IS THE THIRD ROW, NOT THE SECOND. It reproduces here to within
1.6e-07 (the earlier rollout recorded dSharpe -0.016856551786), which is a
good independent check of that measurement on a separately-built store --
but the flag it was measured under bundled TWO changes, and only one of them
is shipped. Roughly
65% of that disclosed impact was the same-day drop rule, which is NOT
enabled; the convention alone costs this registration -0.0059 Sharpe and
-0.0059 DSR.

This is still a real degradation of this registration's backward number and
is recorded as such. It crosses nothing: not this family's own pre-registered
bar (sharpe > 0 AND dsr >= 0.95, which the spec failed at registration and
still fails), and not the 0.50 or 0.6275 thresholds used elsewhere in this
project. It is disclosed because the number a reader of this file would
otherwise carry forward is now stale, not because a verdict moved.

WHY THIS FAMILY MOVES MORE THAN THE OTHER THREE LIVE REGISTRATIONS. Its
holdings are ranked on filing-language similarity, which is uncorrelated with
dividend policy, so it holds large-distribution names as often as chance
allows and never hedges the exposure. Measured on the same three arms:
cbop_ls_h63 moves +0.00023112 Sharpe / +0.00029812 DSR, si_ratio_hedged_h21
-0.00196449 / -0.00121998, and xc_btcbeta_l180_h180 EXACTLY 0.00000000 on
both (crypto's feed carries no distributions at all, so the convention is
structurally inert there).

WHAT WAS *NOT* DONE, AND WHY. The same flag that selected the convention also
silently switched on `drop_same_day_split_distributions`, on the recorded
basis that Yahoo double-encodes spin-offs and that "only 3 such events exist
in this project's universe... and all three are real spin-offs". A full scan
for this review found FIFTEEN such events across SIX tickers, and the rule is
correct for only TWO of them. Tootsie Roll pays a regular quarterly CASH
dividend AND, separately, an annual 3% STOCK dividend on the same ex-date
every March; DXC's 2015 CSRA separation paid one CSRA share AND a separate
$10.50/share of cash; Scripps paid $1.0297 of cash alongside 0.25 of a
Journal Media Group share; B. Riley paid $0.08 + $0.17 of cash. In all
thirteen the split ratio and the recorded cash are two DIFFERENT real
distributions and dropping the cash discards a payment that was made. That
rule therefore now defaults to False under both conventions. Full evidence,
per-event arithmetic and primary sources: data/research_runs/
dividend_convention_2026-09-04.txt, reproducible via
data/research_runs/run_dividend_convention.py.

DOES THIS REQUIRE RE-REGISTERING OR RESETTING THE FORWARD CLOCK? NO. The
spec, config_hash, spec_fingerprint, holding period, portfolio construction
and DSR denominator are all unchanged; only the return definition the prices
are expressed in changed, and it changed for the live tick as well as the
backtest, in the same direction, computed the same way.
build_lazy_prices_live_panel rebuilds the WHOLE history on every tick rather
than appending to a stored series (see its own docstring), so the live series
is recomputed consistently under the new convention rather than spliced onto
observations taken under the old one. Verified after the change by running
app/main.py's own lifespan registration sequence twice against a real
database: five rows, byte-identical across both startups, this one still
in_progress. This family remains observation-only; nothing in
app/services/execution/ is touched and ExecutionControl.trading_halted stays
True. No capital is at risk from this correction in any way.

ONE THING THIS CORRECTION DOES NOT REACH, restated because it is now three
corrections deep. LAZY_PRICES_REGISTRATION_RATIONALE — the condensed copy
persisted ONTO the database row — is not edited here, and an already-created
row would not pick up an edit anyway, because register_or_get dedups on
config_hash and config_hash does not include the rationale field. So a reader
of the DB row or of the API listing still sees the 2026-09-03 text. That is
pre-existing, documentation-only staleness affecting all four corrections on
this file, not something this one introduces; the file is the full statement
of record.

CORRECTING THE RECORD THIS CORRECTION INHERITED. price_store.py's section 5
and data/research_runs/price_store_pit_2026-09-04.txt's section 3 presented
DHR (-35.7%), DXC (-27.1%) and XRX (-12.8%) as cumulative evidence that the
dividend CONVENTION is wrong. All three reproduce exactly, but decomposed
they are the same-day drop rule, not the convention: the convention alone
accounts for -13.57%, -2.62% and -3.40% of them. The convention's own
headline cases are KDP (-8.69%) and AIV (-4.03%). A dated correction is
appended to that report rather than editing its section 3 in place.
"""

import asyncio
import logging
from datetime import date

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.cross_sectional_forward_validation import (
    CrossSectionalForwardValidationRegistration,
)
from app.services.cross_sectional_forward_validation_service import (
    register_or_get_cross_sectional_forward_validation,
)
from app.services.research_lab.cross_sectional_forward_registry import (
    LAZY_PRICES_JACCARD_FULL_FAMILY_KEY,
)
from app.services.research_lab.system_account import get_or_create_system_user

logger = logging.getLogger(__name__)

LAZY_PRICES_PATTERN_ID = "lazy_jaccard_full_h126_ivol"

# The rationale persisted onto the row itself (not just in this docstring),
# so a reader of the database — or of the API listing — sees WHY this
# registration exists without having to find this file. A condensed form of
# the module docstring above, which remains the full statement.
LAZY_PRICES_REGISTRATION_RATIONALE = (
    "DELIBERATE, DISCLOSED REGISTRATION — NOT AN AUTOMATIC ONE, AND NOT A CLAIM OF VALIDATED EDGE. "
    "lazy_jaccard_full_h126_ivol comes from the 36-spec pre-declared lazy_prices filing-language "
    "family (Cohen, Malloy & Nguyen 2020, replicated on 7,798 real 10-K documents fetched live from "
    "SEC EDGAR for the point-in-time S&P 500 union, 2015-2026), whose own pre-registered bar required "
    "a spec with sharpe > 0 AND dsr >= 0.95, whose best spec reached DSR 0.7540, and whose VERDICT IS "
    "THEREFORE AN HONEST NEGATIVE — a verdict that stands and is not disputed by this row. This "
    "spec's own numbers, re-derived directly from the persisted cross_sectional_trial_results rows "
    "during this registration (run tag lazy_prices_2026-09-01): Sharpe +0.6035, PSR(0) 0.9801, DSR "
    "0.7540 against the family's own 36-trial denominator over 2,926 realized days, 24 formations, "
    "~87.7 names per leg. DSR >= 0.5 is a BACKTEST-LEVEL statistical signal and never proof; 0.7540 "
    "sits between the three rows already registered (cbop 0.8174, si_ratio_hedged_h21 0.7962, "
    "noa_neutral 0.5631). "
    "WHY THIS SPEC AND NOT A DEVIATION, unlike the short-interest precedent: that registration chose "
    "a LOWER-scoring spec because the family's top specs (days-to-cover) measure a different "
    "construct than the paper studies (substantially sorting on trading volume, not short interest). "
    "The identical question was asked here and answered the other way. Jaccard IS one of "
    "[CMN20]'s own four declared similarity metrics, not a proxy for one; 'full' (the whole 10-K) IS "
    "the paper's own base-case scope (its 34-58bp/month headline is whole-document); and 'full' had "
    "ZERO section-extraction loss in the production run (100.0% of pairs scored, vs 90.0%/87.4% for "
    "the two section scopes), so it is not differentially composed the way those two are. A NEW "
    "bounded adversarial check was run for this registration specifically, on 18 real, freshly-"
    "fetched consecutive 10-K pairs across 9 large-cap tickers, to test the specific confound this "
    "project's history would most expect — that whole-document Jaccard mostly tracks DOCUMENT LENGTH "
    "GROWTH rather than genuine language change. It found weak correlation (jaccard vs length ratio "
    "0.197, vs length delta 0.119) and several filings that SHRANK year over year yet still scored "
    "well below 1.0 — impossible under a pure-growth-only model, and direct evidence of real "
    "vocabulary turnover. That check is small and ad hoc, not a full-scale, re-checkable diagnostic "
    "the way short-interest's measure_normalizer_divergence is, and is disclosed as exactly that. No "
    "comparable confound was found by it, so the family's own top-DSR spec is registered as is — "
    "A CONCLUSION SINCE CORRECTED IN PART; read the CORRECTION APPENDED 2026-09-03 at the end of "
    "this rationale before relying on any sentence of this paragraph. "
    "THE HONEST CASE AGAINST IT, STATED BEFORE ANY FORWARD DATA EXISTS: its own family's verdict is a "
    "negative; the best result sits on the family's thinnest axis (the top four of 36 specs are all "
    "h126, 24 formations, honest pre-multiplicity t-statistic roughly +2.06); it is an inattention "
    "anomaly tested on the least inattentive universe in existence (S&P 500 large caps), in a sample "
    "that post-dates the paper's own publication; it uses an annual 10-K-only signal where the paper "
    "used 10-K AND 10-Q; XOM is likely silently excluded from this panel today via a known, unfixed "
    "CIK-resolution gap in this family's own EDGAR provider (edgar_filing_text_provider.py), the same "
    "root cause fixed elsewhere on 2026-09-02 but deliberately not ported here; survivorship removes "
    "overwhelmingly the acquired/failed 'changer' names that belong in the short leg, working against "
    "the hypothesis; costs assume financing_bps_per_year=0.0, this project's standing disclosed "
    "short-borrow optimism; and this family's live panel is this project's single most expensive by a "
    "wide margin (re-fetching or re-reading thousands of real 10-K documents to rebuild history), so "
    "this registration's clock is the most likely of the four to occasionally lag the others on a "
    "slow tick, though never at any capital or execution risk. "
    "READING THE RESULT: graduation means ONLY that enough real out-of-sample data has accumulated "
    "to be worth looking at, never that the signal works. The threshold is 252 realized trading days "
    "= max(126, 2 x holding_days=126), i.e. TWO completed formations (~1 year), which is thin and "
    "must be stated wherever this is surfaced; the evidence is the realized daily series on this "
    "family's 252-day equity calendar with the formation count beside it, not the status word. A "
    "negative forward result is a real result: the trailing-window underperformance rule flags this "
    "registration permanently and non-reversibly if it earns one. "
    "ONE spec of this family is registered, deliberately, under family_key lazy_prices_jaccard_full, "
    "which exposes only the six jaccard/full specs — because all 36 of this family's signal functions "
    "read the same fundamental_signal slot, and a risk_factors, mda or cosine registration would "
    "otherwise be able to tick on the wrong panel undetected. THERE ARE NOW FOUR LIVE REGISTRATIONS "
    "(this one, quality_cbop / cbop_ls_h63, quality_noa_industry_neutral / noa_neutral_ls_h126_median, "
    "short_interest_ratio / si_ratio_hedged_h21), so 'the best of the four' is a selection over four "
    "and ALL FOUR must always be reported, including the losers. "
    "CORRECTION APPENDED 2026-09-03 (independent verification pass) — THE ADVERSARIAL CHECK ABOVE WAS "
    "UNDERPOWERED AND MEASURED THE WRONG LENGTH VARIABLE. (i) At n=18 that check had power 0.12 to "
    "detect a true correlation of 0.20 and 0.22 to detect 0.30; the r=0.197 it reported carries a 95% "
    "CI of [-0.297,+0.608], so it could not distinguish 'no relationship' from 'a strong one'. 'Weak "
    "correlation' described its point estimate, not its evidence. (ii) It did not replicate: on 180 "
    "real consecutive 10-K pairs across 30 OTHER S&P 500 filers, corr(jaccard, length ratio) is -0.566 "
    "(p=1.2e-16), the opposite sign. (iii) It measured the wrong variable. Jaccard is bounded not by "
    "raw document length but by the UNIQUE-VOCABULARY size ratio min(|A|,|B|)/max(|A|,|B|) — the "
    "'vocabulary-size ceiling', since |A n B| <= min and |A u B| >= max — which carries no information "
    "about WHICH words changed. On those 180 pairs the ceiling alone explains R^2=0.524 of Jaccard's "
    "variance and its own bottom quintile recovers 52.8% of Jaccard's bottom (short-leg) quintile "
    "against a 20% chance baseline. The original check never computed it. THE DECISIVE TEST WAS THEN "
    "RUN ON THE REAL 2015-2026 PRODUCTION PANEL — same universe, same spec parameters, same backtest "
    "path, same 36-trial denominator, ranking on the CEILING ALONE. THE CONFOUND READING IS "
    "REFUTED: ceiling-only earns Sharpe +0.1875 / DSR 0.2386, against +0.5741 / 0.7278 for this "
    "spec on the same rebuilt panel (which reproduces the committed +0.6035 / 0.7540 to within "
    "0.030 Sharpe; 36/36 pattern_ids matched) — 33% of the Sharpe, and two of the six "
    "ceiling-only specs are negative. This is NOT the si_dtc situation and NO DEMOTION IS "
    "RECOMMENDED. BUT THE CEILING MATTERS MORE THAN THE 18-PAIR CHECK IMPLIED: removing its "
    "linear cross-sectional projection from Jaccard costs this spec 22% of its Sharpe (+0.5741 -> "
    "+0.4483) and drops its DSR to 0.5703 — below lazy_cosine_rf_h126_ivol's 0.6377 on the same "
    "panel; the ceiling's own short quintile shares 49.0% of its names with this spec's SHORT leg "
    "over all 24 real formations against a 20% chance baseline (long leg 30.1%, strategy return "
    "correlation +0.283); and the ceiling explains R^2=0.489 of Jaccard's variance over 1.6M real "
    "panel cells. Jaccard factors EXACTLY into the ceiling and a containment ratio "
    "|A n B|/min(|A|,|B|) (verified to 4.4e-16 per cell), of which containment alone earns +0.3766 "
    "/ DSR 0.4735; neither half reproduces the whole and the two are near-orthogonal, so this spec "
    "scores on the INTERACTION of vocabulary-size change with vocabulary replacement — a more "
    "specific and more fragile claim than this rationale originally made. The pre-committed "
    "reading rule scores the result as formally MIXED (no confound condition fired; only one of "
    "three acquittal conditions did), so the registration STANDS UNCHANGED and a human who chooses "
    "to demote on the 49.0% short-leg overlap and the 0.5703 residual DSR is not being "
    "unreasonable — that call was deliberately NOT made here, because enacting it would reset this "
    "forward clock. One finding argues AGAINST demoting: the obvious fallback "
    "lazy_cosine_rf_h126_ivol has no analytic set-size bound but is MORE rank-associated with its "
    "own scope's ceiling than this spec is with its own (Spearman +0.539 vs +0.425), and rank is "
    "what a quintile sort consumes. See "
    "lazy_prices_forward_registration.py's docstring and "
    "data/research_runs/lazy_prices_vocab_ceiling_confound_2026-09-03.txt for the full run. NOTE, "
    "because it is a real limitation: this corrected text reaches only a registration row created "
    "AFTER 2026-09-03. The row created that day still carries the uncorrected wording, because "
    "config_hash excludes the rationale and re-registering would reset the forward clock to zero. "
    "CORRECTION APPENDED 2026-09-04 -- THE XOM CIK-FIX HYPOTHESIS FOR A SEPARATE REPRODUCTION-DRIFT "
    "FINDING IS TESTED AND REFUTED. Commit 82b69fa (2026-09-04) rebuilt this spec on the registration's "
    "own window and got Sharpe +0.5498 vs the committed +0.6035 (delta -0.0537), and flagged the "
    "2026-09-02 XOM CIK-mapping fix (dcdf864/401d98d, deployed for the sibling quality/asset_growth "
    "families) as the UNVERIFIED leading suspect. REFUTED, on four lines of evidence: (i) that fix "
    "touched only edgar_xbrl_provider.py and the quality/asset_growth family modules, never "
    "edgar_filing_text_provider.py (this family's own provider, which has no successor-CIK resolution "
    "logic at all); (ii) git diff across the whole registration-to-rebuild window shows ZERO lines "
    "changed anywhere in this family's dependency chain (universe, provider, family module, backtest "
    "engine); (iii) a live check on 2026-09-04 reconfirms XOM still resolves to the pre-fix successor "
    "shell (CIK 2115436, 0 periodic filings), unchanged; (iv) THE DECISIVE ABLATION TEST -- the "
    "family's own unmodified run_lazy_prices_screening run twice on the identical registration window, "
    "once with XOM in the universe and once with only XOM removed -- moved the registered spec's "
    "Sharpe/DSR by -0.0000015/-0.0000005, floating-point noise about 1/35,000th the size of the drift "
    "under investigation, and MAX|delta Sharpe| across all 36 specs in the family was 0.0000. XOM's "
    "presence or absence is invisible to this family, before and after the fix alike. The drift itself "
    "is real and not fully explained here (four independent same-window rebuilds gave four different, "
    "NON-MONOTONIC numbers: +0.6035, +0.5741, +0.5946, +0.5498, the last on a one-day-later end-date "
    "that is a separate disclosed methodological difference) -- consistent with this family's own "
    "already-disclosed live, non-point-in-time dependencies (SEC's current-state ticker->CIK map, "
    "EDGAR's growing filing listings) rather than any code defect, since no code changed. This does "
    "NOT reset the forward-validation clock or touch the live registration in any way -- the live row "
    "tracks real subsequent market data, not the backward reference number. cbop_ls_h63 and "
    "noa_neutral_ls_h126_median were checked (flag only, not re-verified) in the same 82b69fa rebuild "
    "and both reproduced their persisted Sharpe/DSR EXACTLY (delta 0.0000), showing no sign of the same "
    "problem. See lazy_prices_forward_registration.py's docstring and "
    "data/research_runs/lazy_prices_xom_hypothesis_test_fast_2026-09-04.txt for the full run. "
    "CORRECTION APPENDED 2026-09-04 (SECOND, SAME DAY) -- THE ACTUAL ROOT CAUSE IS FOUND, PROVEN AND "
    "FIXED, AND IT IS NOT SEC's TICKER->CIK MAP. SEC's map was re-tested directly (live fetch vs a "
    "13-hour-earlier saved snapshot, same 625-ticker universe): 0 CIK values changed -- real in "
    "principle, but not the mechanism here. The actual driver: YFinanceProvider.get_daily_ohlcv calls "
    "yf.download(auto_adjust=True) with NO caching, and Yahoo continuously reprocesses dividends/splits, "
    "retroactively re-adjusting its ENTIRE historical Close series. MEASURED: fetching the same 625 "
    "tickers over the same 2015-01-07..2026-08-31 window twice, ~5.5 hours apart, with zero code "
    "changes, changed 2.9% of all (date, ticker) cells by more than 1bp (max 1.15%); names like DOW/PCL/"
    "Q/FCPT had their rescale boundary fall INSIDE the window, fabricating a single day's return as a "
    "side effect of fetch timing. THE DECISIVE ISOLATION TEST: holding the similarity panels and all "
    "code byte-identical and varying ONLY the price fetch (old vs new, ~5.5h apart) moved the registered "
    "spec's Sharpe from +0.5741 to +0.5946 (delta +0.0205) and other specs by up to 0.0433 -- the same "
    "order of magnitude as the drift under investigation, produced by a controlled experiment, not "
    "argued from a docstring. THE FIX: yfinance_provider.save_ohlcv_snapshot/load_ohlcv_snapshot (new) "
    "freeze a price fetch to disk; run_lazy_prices_screening's new `price_frames` parameter (opt-in, "
    "like the pre-existing `filing_index`) replays the frozen snapshot instead of re-fetching live. "
    "DEFAULT_PRICE_SNAPSHOT_DIR (new) and DEFAULT_FILING_INDEX_PATH (pre-existing but never before "
    "populated) are this family's own committed frozen snapshots for its registered window. PROOF: both "
    "snapshots loaded FRESH FROM DISK twice, independently, and run_lazy_prices_screening called twice "
    "-- ALL 36 specs reproduced with delta EXACTLY 0.0 (registered spec: Sharpe +0.5945672287 / DSR "
    "0.7532869753, both runs, bit-for-bit). See data/research_runs/lazy_prices_ptit_fix_verification_"
    "2026-09-04.txt and run_lazy_prices_ptit_fix_verification.py. This does not retroactively explain "
    "each of the four already-observed historical numbers (no snapshot existed to diff before now), "
    "does not reset the forward-validation clock, does not touch build_lazy_prices_live_panel (which "
    "must keep fetching live data for real forward ticks) or ExecutionControl.trading_halted (stays "
    "True), and does not affect execution or capital in any way. THIS IS NOT LAZY_PRICES-SPECIFIC: "
    "get_daily_ohlcv/get_price_history are live, uncached, auto_adjust=True primitives nearly every "
    "cross-sectional family calls, including quality_cbop and quality_noa_industry_neutral via "
    "get_price_history (verified to share the identical characteristic); their exact reproduction in "
    "82b69fa most plausibly means no relevant dividend event touched an actively-held name at that "
    "specific instant, not structural immunity. A project-wide fix is out of scope here and is left as "
    "an explicit, disclosed, open risk."
)


def register_lazy_prices_forward_validation(
    db: Session, user_id: int, *, started_at: date | None = None
) -> tuple[CrossSectionalForwardValidationRegistration, bool]:
    """Create (or return, idempotently) the one lazy_prices forward-validation
    registration. Returns (registration, created).

    Idempotent by the same (user_id, config_hash) rule the other three
    registrations use, so re-running this never resets an accumulated track
    record — which matters more here than anywhere else in the codebase,
    since the whole value of the row is the clock it has been running and
    this family's live panel is the most expensive to rebuild.

    `started_at` exists only so tests can be deterministic; production
    callers pass nothing, and a forward clock therefore cannot be backdated
    into the backward data it was decided on."""
    return register_or_get_cross_sectional_forward_validation(
        db,
        user_id=user_id,
        family_key=LAZY_PRICES_JACCARD_FULL_FAMILY_KEY,
        pattern_id=LAZY_PRICES_PATTERN_ID,
        rationale=LAZY_PRICES_REGISTRATION_RATIONALE,
        started_at=started_at,
    )


# --- the production entry point: app startup ---------------------------------
#
# WHY STARTUP AND NOT A SCRIPT — identical to short_interest_forward_
# registration.py, whose comment block states it in full. In short: this row
# has to exist in the PRODUCTION database, this project's host (Render, free
# plan) has no Shell to run a one-off script from, and a deploy already
# happens automatically — so the deploy carries the registration.
#
# WHY THAT IS SAFE TO RUN ON EVERY PROCESS START (and there are many — every
# deploy, and every free-tier wake-from-sleep):
#  * register_lazy_prices_forward_validation is idempotent on (user_id,
#    config_hash), so a second start returns the SAME row and never resets the
#    accumulated forward clock, which is the entire value of the row.
#  * It touches no market data. The call resolves the family's own specs and
#    config in memory (build_specs/build_config — cross_sectional_lazy_
#    prices.LAZY_PRICES_FAMILY is built once at import, from no live data),
#    fingerprints them and writes at most one indexed row. build_lazy_prices_
#    live_panel — this project's single most expensive live path, by a wide
#    margin — is only ever called by the runner's tick, never here, so
#    startup cannot block on a network fetch and cannot look like a hung
#    deploy to Render's health check. A test pins this by detonating every
#    registered family's live-panel builder, this one included.
#  * It cannot take the API down: every failure is caught and logged, and the
#    next process start simply retries.

STARTUP_FAILURE_LOG_MESSAGE = (
    "Lazy-prices forward-validation registration failed on startup. The API is starting anyway "
    "(this is a one-shot setup step, never a startup gate) and the next process start will "
    "retry it idempotently — an existing registration's accumulated clock is unaffected."
)


def _format_registration_outcome(
    registration: CrossSectionalForwardValidationRegistration, created: bool, user_id: int
) -> str:
    """One log line, formatted while the session that loaded the row is still
    open — every field below is a lazy/expirable ORM column, and reading one
    off a detached instance raises instead of returning a value."""
    return (
        f"lazy-prices forward-validation registration "
        f"{'CREATED' if created else 'ALREADY EXISTS'}: id={registration.id} "
        f"family_key={registration.family_key} pattern_id={registration.pattern_id} "
        f"status={registration.status} user_id={user_id} "
        f"started_at={registration.started_at} "
        f"n_forward_trading_days={registration.n_forward_trading_days} "
        f"threshold={registration.min_trading_days_threshold} "
        f"config_hash={registration.config_hash}"
    )


def register_lazy_prices_forward_validation_once() -> list[str]:
    """The SYNCHRONOUS unit of work behind the startup step. Returns one
    human-readable outcome line (a list of one, so the async wrapper's
    logging loop is identical to its siblings'); raises on any failure, which
    the async wrapper turns into a log line.

    Owns its own session and closes it in a finally, sharing nothing with the
    request-scoped get_db sessions or with any runner. Ownership is the system
    account, the same convention every other autonomously created row in this
    project uses — a row owned by whichever human happened to run a script
    would be the wrong answer for a registration the project as a whole is
    making.

    SessionLocal is looked up on the module at call time, not bound at import,
    so tests can monkeypatch it exactly the way the runner tests already do."""
    db = SessionLocal()
    try:
        system_user = get_or_create_system_user(db)
        registration, created = register_lazy_prices_forward_validation(db, system_user.id)
        return [_format_registration_outcome(registration, created, system_user.id)]
    finally:
        db.close()


async def register_lazy_prices_forward_validation_on_startup() -> None:
    """Create-or-confirm the lazy-prices forward-validation registration,
    once, during app startup. NEVER RAISES.

    Dispatched through asyncio.to_thread because the work below is synchronous
    SQLAlchemy and lifespan() is async — the same thread-boundary discipline
    every background runner already follows for its own DB work.

    `except Exception` deliberately, not BaseException: asyncio.CancelledError
    derives from BaseException, so a shutdown that interrupts this still
    cancels rather than being swallowed and logged as a failure."""
    try:
        outcomes = await asyncio.to_thread(register_lazy_prices_forward_validation_once)
    except Exception:
        logger.exception(STARTUP_FAILURE_LOG_MESSAGE)
        return
    for outcome in outcomes:
        # "%s", not an f-string into the message: an outcome line carries a
        # config_hash and could in principle contain a % that logging would
        # then try to interpret as a format spec.
        logger.info("%s", outcome)


__all__ = [
    "LAZY_PRICES_PATTERN_ID",
    "LAZY_PRICES_REGISTRATION_RATIONALE",
    "register_lazy_prices_forward_validation",
    "register_lazy_prices_forward_validation_on_startup",
    "register_lazy_prices_forward_validation_once",
]
