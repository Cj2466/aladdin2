"""SHORT INTEREST, THE LONG-SIDE READING: one pre-declared cross-sectional
equity family testing whether heavily-traded names with LOW short interest
earn positive abnormal returns, computed from real FINRA bi-monthly short
interest and real SEC point-in-time share counts.

Structural descendant of cross_sectional_asset_growth.py: same harness, same
point-in-time step-panel discipline, same "pre-declare the competing
conditionings TOGETHER in one grid under one DSR denominator" rule that
family adopted after the NOA pair had to discover its own confound
sequentially. What is NEW here is the data — this is the first family in
this project built on FINRA short interest — and section 3 explains why that
data is unusually clean in one respect and awkward in another.

=======================================================================
1. THE SOURCE, AND EXACTLY HOW MUCH OF IT COULD BE VERIFIED
=======================================================================

PRIMARY. Boehmer, Ekkehart, Zsuzsa R. Huszar & Bradford D. Jordan, "The
good news in short interest", Journal of Financial Economics 96(1), 2010,
pp. 80-97.

BIBLIOGRAPHIC RECORD AND ABSTRACT: VERIFIED, live-fetched from RePEc/
EconPapers during this build (2026-09-02). The abstract, verbatim:

    "Stocks with relatively high short interest subsequently experience
    negative abnormal returns, but the effect can be transient and of
    debatable economic significance. In contrast, relatively heavily traded
    stocks with low short interest experience both statistically and
    economically significant positive abnormal returns. These positive
    returns are often larger (in absolute value) than the negative returns
    observed for heavily shorted stocks. Thus, the positive information
    associated with low short interest, which is publicly available, is only
    slowly incorporated into prices, which raises a broader market
    efficiency issue. Our results also cast doubt on existing theories of
    the impact of short sale constraints."

THE FULL TEXT COULD NOT BE OBTAINED. SSRN (abstract page and every
Delivery.cfm variant), ScienceDirect, ResearchGate, the SMU institutional
repository and NUS ScholarBank were all tried during this build and every
one returned HTTP 403, a CAPTCHA, or metadata without full text; the
Internet Archive holds no full-text snapshot. So EVERY methodological claim
below is SECOND-HAND, from sources describing the paper, and each is labeled
with how many independent sources support it. Nothing here is reconstructed
from memory, and where the sources are silent this module says so rather
than inventing a plausible answer.

 (a) THE MEASURE — shares sold short divided by SHARES OUTSTANDING, a
     LEVEL, not a change or a trend. Multiple independent sources, the
     strongest being a later paper by TWO OF THE THREE ORIGINAL AUTHORS
     (Boehmer, Huszar, Wang & Zhang), which groups this paper with the
     literature that uses "the aggregate number of shares shorted for each
     stock divided by shares outstanding, SIR, as their main measure of
     short selling ... Boehmer et al. (2010), among others, use SIR". A
     2022 citing paper states it concretely: BHJ "calculate monthly short
     interest ratios over 1988-2005 for stocks by dividing short interest
     by shares outstanding".

     ONE DISSENTING SOURCE exists and is recorded rather than dropped: a
     2018 paper cites BHJ for short interest "divided by the trading volume
     of the month or, alternatively, divided by the total shares
     outstanding". It is the only source implying a days-to-cover reading
     and is most likely loose citation — but see (e), which is why this
     family does not simply pick a side.

 (b) BREAKPOINTS — EXTREME PERCENTILE TAILS, not quintiles or deciles. Two
     independent replications agree: portfolios were formed from "the 99th,
     95th and 90th percentiles of the short interest level distribution ...
     whereas the lightly shorted portfolios included securities from the
     1st, 5th and 10th percentiles". See section 4 for which of those three
     this family can actually run and why.

 (c) REBALANCE — MONTHLY, two independent sources. Horizon: a one-month
     baseline, with one source reporting that the low-short-interest
     portfolio's alpha survives "up to 6 months" with no dramatic
     reduction.

 (d) UNIVERSE AND WEIGHTING — NYSE, AMEX and NASDAQ, 1988-2005, averaging
     about 4,400 stocks per month; portfolios reported both equal- and
     value-weighted; abnormal returns measured against the CARHART
     FOUR-FACTOR model (three sources agree on four-factor; none mentions
     DGTW characteristic adjustment).

 (e) WHAT COULD NOT BE VERIFIED AT ALL, and it is the single most important
     gap in this module — HOW "RELATIVELY HEAVILY TRADED" IS
     OPERATIONALIZED. The abstract's headline claim is conditioned on it,
     and no source found states BHJ's trading-activity variable, whether the
     sort is a double sort, or any breakpoint. The only related evidence is
     a 2019 citing paper reporting that BHJ's spreads "are more pronounced
     among stocks with higher turnover ratios and smaller sizes" — which
     establishes that turnover-conditioned results exist in the paper and
     nothing about how they were built.

     THIS FAMILY THEREFORE DOES NOT CLAIM TO REPLICATE THAT CONDITIONING.
     See section 4 for the substitute it uses instead and why that
     substitute is a disclosed approximation rather than a reconstruction.

=======================================================================
2. THE PRIOR — THREE REASONS TO EXPECT LITTLE, STATED BEFORE RESULTS
=======================================================================

 * POST-PUBLICATION WINDOW ON A PUBLISHED ANOMALY. The paper's sample ends
   in 2005 and it was published in 2010. This family tests 2018-2026, which
   begins thirteen years after the sample ends and eight years after
   publication, on the most-watched 500 stocks in the world. Short interest
   is also about as cheap and public a signal as exists — FINRA gives it
   away twice a month — so if it were tradeable at this scale it would be
   the most easily-harvested edge in this entire project.

 * THE LONG SIDE MAY BE A JANUARY AND SMALL-CAP ARTIFACT. A 2016
   dissertation (single source, but directly on point) reports that BHJ's
   lightly-shorted portfolio earns "significant average 4-factor adjusted
   return of 4.55 percent in January ... compared to average return of 0.45
   percent in non-January", and concludes the positive abnormal return "is
   mainly driven by the January effect and size effect". The same source
   states that outside January the long side is SMALLER in absolute value
   than the short side — the direct opposite of the abstract's headline
   claim, which is the specific claim this family exists to test.

   This family measures the January share as a DIAGNOSTIC and pre-commits
   to reporting it (section 5). It is NOT a spec axis: it is not searched
   over, so no January-conditioned variant can be selected post hoc.

 * A SUB-$5 PRICE SCREEN MAY MATTER. A further single source notes that a
   later paper (Guo & Wu 2019) added a $5 price screen and got different
   results, "which means that the results of Boehmer et al. (2010) could
   have been mainly influenced by stocks priced below $5". Every S&P 500
   constituent is far above $5, so if that reading is right this family's
   universe removes the effect by construction. That is a reason for a LOW
   prior here, and it is stated before any number was computed.

=======================================================================
3. THE DATA — ONE UNUSUAL STRENGTH AND ONE REAL ASYMMETRY
=======================================================================

THE STRENGTH: NO CURRENT-DAY TICKER MAP ANYWHERE IN THE NUMERATOR. FINRA
publishes one file per settlement cycle, keyed on the ticker as it existed
ON THAT DATE (finra_short_interest_provider.py section 4). A company
renamed, acquired or delisted in 2020 still appears under its real 2020
ticker in the 2020 files. The failure mode that lost XOM from the sibling
EDGAR families — a present-day CIK lookup breaking for a re-registered
entity — has no analogue in the short-interest numerator.

The cost of this data is also PER-CYCLE, not per-ticker: 208 files cover
every listed security. That is why this family screens the FULL 691-name
point-in-time S&P 500 union universe rather than the seeded 200-name sample
the EDGAR-based quality families had to draw.

THE ASYMMETRY, WHICH IS THE ONE GENUINELY AWKWARD PART OF THIS BUILD. The
paper's own measure (section 1a) divides by SHARES OUTSTANDING, and there
is no free per-date share-count source with FINRA's coverage properties.
The best available (sec_shares_outstanding_provider.py) resolves tickers
through SEC's current-day company_tickers.json, which loses 108 of the 691
universe names — departed members, exactly the population the numerator
handles perfectly.

SO THE TWO NORMALIZERS THIS FAMILY TESTS DO NOT NATURALLY SEE THE SAME
CROSS-SECTION, and a grid whose halves rank different universes cannot
attribute a difference between them to the normalizer. This family
therefore MASKS BOTH PANELS TO THEIR COMMON CROSS-SECTION: a
ticker-formation is ranked only where BOTH a short-interest ratio and a
days-to-cover are computable, in every one of the 12 specs. The cost is
paid by the days-to-cover half, which could have ranked more names; the
benefit is that the normalizer axis measures the normalizer. The realized
loss is measured per run and reported, never assumed.

RESIDUAL SURVIVORSHIP, stated not hidden: masking to the share-count panel
reimports the current-day-ticker-map bias into the whole family. The names
it drops are overwhelmingly index leavers — disproportionately the
short/hedge leg's natural candidates — so the surviving cross-section is
better than the real one was. THIS FLATTERS THE RESULTS.

POINT-IN-TIME CONSTRUCTION, both panels:
 * Short interest becomes visible at settlement + 14 calendar days, a bound
   chosen to DOMINATE every row of FINRA's own published schedule (worst
   real gap 12 days) rather than approximate its seven-business-day rule.
   See finra_short_interest_provider.py section 3, and note the design
   precedent: Bradford Jordan's own later work states that "Short interest
   data is made public eight business days after the mid-month reporting
   settlement date" and uses only mid-month values "to insure public
   availability by the start of the next month".
 * Share counts become visible at their cover-page `end` date + 90 calendar
   days, a bound set from a MEASURED distribution of 7,539 real (end,
   filed) pairs extracted from this project's own cached EDGAR
   companyfacts (p50 8 days, p95 35, p99 73). See
   sec_shares_outstanding_provider.py, which also states the ~0.5% residual
   this does not cover and why its effect is bounded.
 * Both are forward-filled STEP series, never interpolated, and refuse a
   value carried past a bounded staleness.
 * Formation-time look-ahead is structurally impossible regardless, because
   both frames ride CrossSectionalData frames the harness slices to rows
   <= the formation date.

A SPLIT GUARD, LOAD-BEARING FOR THE RATIO. FINRA reports short interest in
RAW shares as of the settlement date; SEC reports share counts in RAW
shares as of a cover date up to a quarter earlier. A split between the two
would corrupt the ratio by the split factor — and a 2:1 split HALVES the
computed ratio, pushing the name toward the LOW-short-interest long leg,
i.e. straight into the leg this family is testing. FINRA flags such cycles
itself in `stockSplitFlag` (measured: 348 flagged rows across 11 sampled
cycles of ~20,000 securities each), and this family REFUSES every flagged
observation rather than trusting it.

=======================================================================
4. THE PRE-DECLARED GRID
=======================================================================

    normalizer {short_interest_ratio, days_to_cover}     2
  x holding period {21, 63, 126} trading days            3
  x portfolio {long_universe_hedged, long_short}         2
  = 12 definitions.

n_trials = 12, this family's own honest denominator — no carried trials from
any other family. This is a fresh hypothesis from an independent literature
and all four axes were fixed together before any number was computed.

WHY THE NORMALIZER IS AN AXIS AND NOT A DECISION. Section 1(a) establishes
the paper's own measure is short interest over shares outstanding, and this
family would simply use it — except that a direct replication of this very
paper (a 2020 ZHAW bachelor thesis, the most detailed replication found)
reports that the two normalizers give DIFFERENT ANSWERS: its
percent-of-shares-outstanding sorts produced significant low-short-interest
alpha while its days-to-cover sorts did not (intercepts insignificant at
p = 0.468 and 0.221). A single thesis is weak evidence, but it is evidence
that the choice is load-bearing rather than cosmetic, and this project has
already been burned once by fixing a conditioning first and discovering the
confound afterwards (the raw-NOA family). Both are therefore pre-declared
together, under ONE denominator, and neither can be reported without the
other.

WHY BOTH PORTFOLIOS, AND WHY long_universe_hedged IS THE ONE THAT MATTERS.
This candidate is specifically the LONG-SIDE reading: the claim is not that
a low-minus-high spread is profitable (the high-short-interest side is the
long-known effect), it is that the LOW side alone earns positive abnormal
returns, "often larger" than the negative returns on the heavily shorted
side. A long_short spread cannot distinguish those two claims — a spread
driven entirely by its short leg would look identical. long_universe_hedged
(long the ranked leg, short an equal-weighted basket of the whole eligible
universe — see cross_sectional._target_weights) isolates the long leg's
abnormal return against its own universe, which IS the paper's headline
quantity. Both are in the grid so the comparison between them can be made;
the pass/fail rule below is written so the long side has to carry it.

RANK FRACTION IS FIXED AT 0.05 AND IS NOT SEARCHED OVER. Section 1(b) gives
the paper's three published low-side cutoffs: the 1st, 5th and 10th
percentiles. On a ~500-name point-in-time universe the 1st percentile is ~5
names, at this harness's DEFAULT_MIN_NAMES_PER_LEG floor, which is not a
cross-section but a handful of stock picks; the 10th is a decile, which is
not the tail the paper emphasizes. The 5th is the one of the three that is
both a genuine tail and a usable leg (~25 names), so it is fixed in advance.
Fixing it rather than searching it is deliberate: with three defensible
cutoffs available, searching all three and reporting the best would be a
selection this family's denominator would have to pay for and its thin
sample cannot afford.

HOLDING PERIODS {21, 63, 126}. 21 days is the paper's OWN monthly rebalance
and, unlike every EDGAR-based family in this project, a monthly hold is
genuinely appropriate here: the ranking variable refreshes TWICE A MONTH,
so a monthly reformation trades on real new information rather than
re-paying turnover on an unchanged ranking (contrast
cross_sectional_quality.py section 4, which excludes 21 for exactly the
opposite reason). 126 is the ~6-month horizon over which one source reports
the paper's long-side alpha persists. 63 is the house middle.

THE "HEAVILY TRADED" CONDITIONING IS NOT REPLICATED, AND THIS IS THE ONE
DESIGN CALL A HUMAN SHOULD REVIEW. Section 1(e) records that the paper's
own operationalization could not be verified from any source. Rather than
invent a double sort and attribute it to the paper, this family lets the
UNIVERSE carry that conditioning: the point-in-time S&P 500 is, by
construction, the most heavily traded segment of the US equity market. That
is an honest approximation and a weak one — it is a universe restriction,
not a within-universe sort, and it cannot reproduce a conditional result. A
reader who wants the paper's actual double sort needs the paper's
methodology section (JFE 96(1), around pp. 83-86 per one replication's page
citation), which no free source served during this build.

UNIVERSE: the FULL point-in-time S&P 500 union over the panel window, gated
per formation by the harness's default was_member, then masked to the
common cross-section of section 3. Not a seeded sample — this family's data
cost does not scale with ticker count.

COSTS: DEFAULT_XS_COST_BPS (5 bps one-way), identical to every S&P 500
equity family here so Sharpes stay comparable; financing_bps_per_year stays
0.0 — this project's standing DISCLOSED optimism about short borrow, not an
estimate. It is worth naming that this assumption bites HARDER here than
anywhere else in this project: a family whose entire subject is short
selling, and whose every spec carries a short leg, is being charged zero
borrow cost. The long_universe_hedged specs short a broad index-like
basket, which is genuinely cheap to borrow; the long_short specs short the
MOST heavily shorted names in the index, which is exactly the population
where borrow is expensive. Any positive long_short result must be read with
that in mind, and it is a further reason the long side is the one this
family's pass rule leans on.

PASS/FAIL, FIXED BEFORE RESULTS. Reported as a validated edge ONLY if:
  (i)  the best spec's deflated Sharpe (DSR, n_trials=12) clears 0.95; AND
  (ii) that spec is a long_universe_hedged spec, OR its long_universe_hedged
       counterpart at the same normalizer and holding period also clears a
       materially positive Sharpe.
Condition (ii) is what makes this the LONG-SIDE candidate it claims to be:
a long_short-only positive is consistent with the long-known heavily-shorted
effect and does not support this paper's distinctive claim. Anything else is
an honest negative and gets written up as one.

=======================================================================
5. PRODUCTION RUN 2026-09-02 — MEASURED COVERAGE AND RESULTS
=======================================================================

Sections 1-4 and the pre-registration document were committed in f091c7c
BEFORE this run existed. Everything below is what came out; the grid and the
pass/fail rule applied are that commit's, unchanged. Full detail in
data/research_runs/short_interest_2026-09-02.txt.

Run tag "short_interest_build_2026-09-02", persisted to
cross_sectional_trial_results under family_key "short_interest" (12 rows,
n_trials=12 on every row). Formations 2018-01-12..2026-09-01, 2,169 realized
trading days per spec.

DATA PROVENANCE — REAL. 208 real FINRA cycle files, real SEC XBRL frames,
real yfinance daily history. No synthetic input touched any persisted number.

COVERAGE: 208 of 209 settlement anchors resolved — the one miss is
2026-08-31, whose real publication date is 2026-09-10, i.e. it did not exist
yet, which is the publication lag doing its job rather than a gap. 115,986
FINRA rows parsed with ZERO refusals; 98,257 short-interest ratios built;
~394-404 names ranked per formation, giving 5% legs of ~20.6 names.

TWO DATA DEFECTS WERE FOUND BY THIS RUN AND FIXED AT SOURCE. Both are
recorded because each would otherwise have silently corrupted a result:

 (a) FINRA'S FILES CONTAIN LITERAL DOUBLE QUOTES in issueName — e.g.
     `ELEMENTS "Dogs of the Dow" Tot` — in 68 of the 208 cycle files. The
     files are pipe-delimited and unquoted, so csv's default QUOTE_MINIMAL
     read that quote as opening a field and swallowed delimiters and
     newlines until the next one. It surfaced as a hard `_csv.Error`, which
     is the LUCKY outcome; a file whose quotes happen to balance instead
     merges rows silently and emits plausible values for the wrong security.
     Fixed with QUOTE_NONE, pinned by two regression tests.

 (b) THE FIRST RUN EMITTED A REALIZED SHORT-INTEREST RATIO RANGE OF
     0 .. 32,050,932, for a quantity mathematically confined to ~[0, 1].
     Root cause: dei:EntityCommonStockSharesOutstanding carries two distinct
     corruption modes — shell/pre-distribution registrations (FOXA
     2019-03-18 = 1 share; CTVA, SW, VTRS = 100; PSKY = 1,000; AMCR =
     13,001; LIN = 25,000; CMG = 27,962; RMD = 145,681) and scale/units
     errors (AJG 2020 = 191,469,000,000,000 against its own median of
     210,588,000; GRMN = 198bn; CCL = 932bn; PKG = 89.9bn). Fixed with two
     guards in sec_shares_outstanding_provider — an absolute floor and a
     scale break against the ticker's own median, each catching what the
     other structurally cannot — plus an `implausible_ratio` tripwire here.
     19 records refused of 16,173; the realized range is now
     0.00000..0.99944. THE TRIPWIRE STILL FIRED 58 TIMES on 98,257
     observations (0.06%), reported rather than hidden: the upstream guards
     are very good but not complete, and the residual is caught downstream.

RESULTS — the grid, ranked by Sharpe (DSR at n_trials = 12):

    si_dtc_ls_h63       +0.774  DSR 0.948   si_ratio_hedged_h21   +0.453  0.796
    si_dtc_ls_h126      +0.741  DSR 0.939   si_ratio_hedged_h126  +0.450  0.794
    si_dtc_hedged_h63   +0.707  DSR 0.925   si_dtc_hedged_h21     +0.416  0.721
    si_dtc_hedged_h126  +0.670  DSR 0.910   si_ratio_hedged_h63   +0.386  0.736
    si_dtc_ls_h21       +0.605  DSR 0.873   si_ratio_ls_h63       +0.286  0.632
                                            si_ratio_ls_h21       +0.236  0.576
                                            si_ratio_ls_h126      +0.233  0.573

VERDICT — HONEST NEGATIVE, BY THE NARROWEST MARGIN THIS PROJECT HAS SEEN.

THE PRE-REGISTERED BAR IS NOT MET. Condition (i) required the best spec's
DSR to exceed 0.95; si_dtc_ls_h63 reaches 0.948, so condition (ii) is never
reached. The rule is applied exactly as written and the answer is a fail:
0.948 is not 0.95, and "close to a threshold" is not a pass. This is
precisely the case a pre-registered bar exists for — it was fixed in f091c7c
before any of these numbers existed, and moving it now, by any amount and
for any reason, would turn this whole exercise into the thing it was built
to prevent.

THREE THINGS THE GRID'S STRUCTURE SAYS, and the second is the important one:

 * THIS IS THE STRONGEST GRID THIS PROJECT HAS PRODUCED among its recent
   honest negatives. All 12 specs are positive, four exceed DSR 0.90, and
   every one clears the DSR 0.5 screening floor. For scale: the sibling
   asset-growth family topped out at DSR 0.670, and the two families that
   WERE registered for forward validation scored 0.817 (cbop) and 0.563
   (noa_neutral). That is a real observation, and it is why section 6 does
   not simply close the file.

 * THE STRENGTH IS IN THE WRONG NORMALIZER, AND THAT IS PROBABLY FATAL TO
   THE CANDIDATE AS STATED. Every one of the top five specs is
   days-to-cover. The paper's OWN measure — short interest over shares
   outstanding (section 1a) — tops out at DSR 0.796 and fills the bottom
   half of the grid. A candidate that works only under a normalizer its
   source paper does not use, and which the one available replication found
   explicitly did NOT work (section 4), is not evidence for that paper's
   mechanism. Pre-declaring both normalizers in one grid is what made this
   visible instead of flattering; had this family fixed the normalizer to
   days-to-cover on convenience grounds, it would have reported a DSR 0.948
   "near miss" for BHJ and been wrong.

   A POST-HOC DIAGNOSTIC — labeled post-hoc, run after the verdict was
   already a fail, and incapable of changing it — makes the reason concrete.
   Measured over 34 quarterly formations:

       long-leg overlap, ratio sort vs days-to-cover sort:  19.7%
       mean ADV percentile of the days-to-cover long leg:   72.7%
       mean ADV percentile of the ratio long leg:           64.5%
       mean short-interest-RATIO percentile of the
           days-to-cover long leg:                          33.2%
       panel-wide Spearman corr(ratio, days-to-cover):      0.613

   The two sorts pick overwhelmingly DIFFERENT names — they agree on about
   one name in five. And the days-to-cover long leg is not a
   low-short-interest portfolio at all by the paper's measure: it sits at
   the 33rd percentile of the short-interest ratio, i.e. mid-pack, while
   sitting at the 73rd percentile of trading volume. Days-to-cover is short
   interest DIVIDED BY average daily volume, so sorting on LOW days-to-cover
   is substantially sorting on HIGH VOLUME. The most likely reading of the
   best specs in this grid is a liquidity/volume effect wearing a
   short-interest label, not "the good news in short interest".

 * THE PRE-DECLARED JANUARY DIAGNOSTIC POINTS THE SAME WAY AS THE PRIOR.
   Section 2 recorded a source claiming BHJ's long side is mainly a January
   effect. The long-side (hedged) days-to-cover specs are heavily
   January-concentrated: h126 earns +0.001403 mean daily return in January
   against +0.000321 outside it (4.4x), h63 +0.001389 against +0.000431
   (3.2x). The long_short variants are far less so (~1.3x). A long-side
   result whose return concentrates in one month of the year is exactly the
   artifact section 2 warned about, pre-registered before it was measured.

WHAT THIS DOES NOT CLAIM. It does not refute Boehmer/Huszar/Jordan. Their
sort is a broad-universe, ~4,400-stock, 18-year sort across NYSE/AMEX/NASDAQ
including the micro-cap segment where one source says the effect
concentrates. This is ~400 large caps over 8.7 years with ~21-name legs, in
a post-publication window, WITHOUT the paper's own (unverifiable)
trading-activity conditioning, and with the sub-$5 population excluded by
construction. Anomaly decay, absence in the large-cap segment, the missing
conditioning, and simple lack of power are all consistent with these numbers
and this dataset cannot distinguish between them.

=======================================================================
6. FORWARD VALIDATION — THE DECISION, AND WHY IT IS LEFT TO A HUMAN
=======================================================================

The pre-registration (section 8) committed to stating this explicitly in
either direction rather than leaving a silent omission.

NOTHING FROM THIS FAMILY IS REGISTERED FOR FORWARD VALIDATION BY THIS BUILD,
AND NO REGISTRATION IS WIRED INTO APP STARTUP.

The case FOR registering something is real and is not dismissed: all 12
specs clear the DSR >= 0.5 screening floor that selected cbop and
noa_neutral, four exceed 0.90, and the best (0.948) is materially stronger
than either row now accumulating in production. The literature review that
produced this candidate flagged it as "best treated as forward-accumulating
rather than immediately backtestable", and forward validation is the one
statistically legitimate test left once a backward sample is exhausted.

The case AGAINST, which is why this build stops short:

 * A registration starts a PERMANENT, non-reversible clock on the production
   system. The two existing registrations were each made against a
   hypothesis whose MECHANISM was understood and whose best spec was the
   spec its family actually set out to test. Here the best specs measure
   something the diagnostic above suggests is mostly trading volume, not
   short interest — registering it would spend a year of real calendar time
   accumulating evidence about a signal nobody has yet identified.
 * The obvious repair — register the best LONG-SIDE spec
   (si_dtc_hedged_h63, DSR 0.925) rather than the best overall — is
   defensible, because the pre-registration privileged the long side BEFORE
   results existed, so it is not a post-hoc selection. But it is still
   days-to-cover, so it inherits the same interpretive problem, and its
   January concentration (3.2x) is among the worst in the grid.
 * The zero-borrow assumption (section 4) is least defensible for exactly
   the long_short specs that top the grid.

THE HONEST NEXT STEP, stated as a recommendation rather than taken
unilaterally: if a human wants this accumulating, the spec to register is
si_dtc_hedged_h63 — the best long-side spec, the reading this candidate
actually names — with the volume-confound diagnostic above written onto the
registration row as its standing case-against, exactly as
quality_forward_registration.py writes the case against cbop and noa_neutral
onto theirs. That is a small, reviewable change: a module mirroring
quality_forward_registration.py plus one awaited call in main.py's lifespan.
It is left undone on purpose, because switching on a permanent production
clock is a decision for someone who has read the volume confound, not for
the agent that found it.

THE GENUINELY OPEN QUESTION, for whoever picks this up: is the days-to-cover
result a real liquidity/volume premium worth its own pre-registered family,
or is it the well-documented short-term-reversal / illiquidity literature
arriving through an unusual door? This family cannot answer that — it did
not pre-register a volume sort and must not go looking for one in the same
sample now. That needs a fresh hypothesis, a fresh denominator, and its own
pre-registration.

DO NOT re-test short interest on this universe without genuinely new data or
a genuinely different hypothesis — and carry these 12 trials into the
denominator of anything that does.

=======================================================================
7. SECTION 6 ADDENDUM — A REGISTRATION WAS MADE, AND IT IS NOT THE ONE
   SECTION 6 RECOMMENDED (2026-09-02, later the same day)
=======================================================================

PURE ADDITION. Nothing above this line is edited, including section 6's
statement that nothing from this family is registered — which was true when
it was written and is the record of what THIS BUILD did. What follows is
what a human subsequently decided, recorded here so the module names its own
live consequences.

REGISTERED: si_ratio_hedged_h21 (Sharpe +0.4531, PSR(0) 0.9075, DSR 0.7962),
for observational forward validation only — no capital, real or paper, is at
risk. See short_interest_forward_registration.py for the full statement, the
case against, and the rationale persisted onto the row itself, and
cross_sectional_forward_registry.py's short-interest section for the live
panel and the family_key that carries it.

NOT si_dtc_hedged_h63, WHICH IS WHAT SECTION 6 RECOMMENDED. The departure
acts on the two reservations section 6 stated in the same breath as that
recommendation: it is still days-to-cover, so it inherits the volume-confound
interpretation, and its January concentration (3.2x) is among the worst in
the grid. si_ratio_hedged_h21 is instead the paper's own measure x the
paper's own long-side reading x the paper's own monthly rebalance — the most
pre-specified cell in the grid, with all three axes privileged in writing in
the pre-registration before any number existed — and its January ratio is
2.05x. It is still a SELECTION over twelve seen results, and its point
estimate is biased upward by that; the forward sample is what answers it.

WHAT THIS ADDENDUM DOES NOT DO: it does not move the verdict. The family's
pre-registered bar was 0.95 on its best spec, the best spec reached 0.948,
and this family's answer remains an HONEST NEGATIVE. A forward registration
is not a pass, a promotion, or a claim of edge; it is a decision to let real
future data speak instead of argument, and the graduation threshold (126
realized trading days = six completed monthly formations) means only that
enough out-of-sample data has accumulated to be worth looking at.

The remaining paragraphs of section 6 stand unchanged, including the open
question about the days-to-cover result and the prohibition on re-testing
short interest on this universe without new data.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider
from app.services.market_data.finra_short_interest_provider import (
    FinraShortInterestProvider,
    ShortInterestFetchDiagnostics,
    ShortInterestObservation,
)
from app.services.market_data.sec_shares_outstanding_provider import (
    SecSharesOutstandingProvider,
    ShareCountDiagnostics,
    build_point_in_time_share_count_frame,
)
from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    DEFAULT_XS_COST_BPS,
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalScreeningResult,
    CrossSectionalSpec,
    run_cross_sectional_backtest,
    screen_cross_sectional_universe,
)
from app.services.research_lab.cross_sectional_buyback import SHARES_MAX_STALENESS_DAYS
from app.services.research_lab.sp500_membership_history import get_universe_over, was_member

logger = logging.getLogger(__name__)

SHORT_INTEREST_CITATION = (
    "Boehmer, Huszar & Jordan, 'The good news in short interest' (Journal of Financial "
    "Economics 96(1), 2010, pp. 80-97) — whose abstract reports that 'relatively heavily traded "
    "stocks with low short interest experience both statistically and economically significant "
    "positive abnormal returns', 'often larger (in absolute value) than the negative returns "
    "observed for heavily shorted stocks'. Replicated here on real FINRA bi-monthly short "
    "interest and real SEC point-in-time share counts. The paper's full text could not be "
    "obtained during this build (SSRN/ScienceDirect/repositories all refused), so every "
    "methodological detail used is second-hand and labeled as such in the module docstring — "
    "including one detail, its 'heavily traded' conditioning, that could not be verified at all "
    "and is therefore NOT replicated"
)

# --- panel construction ------------------------------------------------------

# A short-interest value may be carried forward at most this long before it
# is refused. Cycles are ~15 calendar days apart and the publication bound is
# 14 days, so in normal operation a value is never more than ~16 days old;
# 45 days means THREE consecutive missed cycles, which for a security FINRA
# publishes twice a month is not staleness but disappearance (a delisting, a
# ticker change, a halt). Refused rather than carried, so a dead name cannot
# keep ranking on its last known reading.
SHORT_INTEREST_MAX_STALENESS_DAYS = 45

# DEFENCE IN DEPTH on the ratio itself, downstream of the two share-count
# guards in sec_shares_outstanding_provider.
#
# Short interest as a fraction of SHARES OUTSTANDING is confined to roughly
# [0, 1] by construction. Values above 100% are occasionally quoted in the
# press, but those are computed against FLOAT (shares available to trade),
# which is smaller than shares outstanding and excludes insider and strategic
# holdings; against total shares outstanding, above 1.0 is essentially unheard
# of for an S&P 500 constituent.
#
# This bound exists because the FIRST production run of this family (before the
# provider guards existed) emitted a realized ratio range of
# 0.00000 .. 32,050,932 — a number that is not a short-interest ratio at all.
# The root cause was fixed at source; this is the tripwire that would have
# caught it, and its refusal count is REPORTED every run so that "the guards
# upstream are working" is a measured claim rather than an assumption.
SHORT_INTEREST_MAX_PLAUSIBLE_RATIO = 1.0

# The panel's first formation date: the first FINRA cycle available on this
# endpoint is 2017-12-29, which under the 14-day publication bound becomes
# readable on 2018-01-12. A formation earlier than that would rank an empty
# cross-section.
SHORT_INTEREST_FORMATION_START = date(2018, 1, 12)

# The earliest settlement cycle to ask FINRA for. Deliberately a little
# before the first available one (2017-12-29) so the resolver's own
# anchor-walk decides where the data really starts, rather than this module
# asserting it — and so the very first formation reads a value that was
# already visible rather than one published that morning.
SHORT_INTEREST_CYCLE_FETCH_START = date(2017, 12, 1)

# Calendar padding before formation_start when fetching prices: the signal
# reads one row, so this is a small margin for the row-indexed formation
# floor, not a lookback warm-up. Same value and same reason as
# cross_sectional_quality.QUALITY_PRICE_HISTORY_PADDING_CALENDAR_DAYS.
SHORT_INTEREST_PRICE_HISTORY_PADDING_CALENDAR_DAYS = 30

# The signal reads only the formation row of its panel.
SHORT_INTEREST_SIGNAL_LOOKBACK_ROWS = 1


@dataclass
class ShortInterestPanelDiagnostics:
    """Measured panel coverage. Every field is counted during construction;
    none is assumed."""

    n_observations_used: int = 0
    n_refused: dict[str, int] = field(default_factory=dict)
    # Ranked ticker-day cells in each panel BEFORE the common-cross-section
    # mask, and the count the mask removed. The single most important number
    # for reading this family's universe accounting (module docstring
    # section 3).
    n_cells_ratio_only: int = 0
    n_cells_dtc_only: int = 0
    n_cells_common: int = 0
    tickers_never_ranked: list[str] = field(default_factory=list)

    def refuse(self, reason: str, count: int = 1) -> None:
        self.n_refused[reason] = self.n_refused.get(reason, 0) + count


def _step_frame(
    close: pd.DataFrame,
    points_by_ticker: dict[str, dict[pd.Timestamp, float]],
    *,
    max_staleness_days: int,
) -> pd.DataFrame:
    """Forward-fill sparse, availability-dated points onto `close`'s exact
    trading-day index as a STEP series, refusing anything carried past
    `max_staleness_days`.

    The union-reindex is deliberate: a value becoming available on a
    non-trading day must still propagate from its own date rather than being
    silently dropped, and the result is then read back on `close`'s dates
    alone. Identical in contract to
    sec_shares_outstanding_provider.build_point_in_time_share_count_frame and
    to cross_sectional_buyback.build_point_in_time_share_counts' step 4 — no
    interpolation, no back-fill, no extrapolation."""
    empty = pd.Series(np.nan, index=close.index, dtype=float)
    columns: dict[str, pd.Series] = {}
    for ticker in close.columns:
        points = points_by_ticker.get(ticker)
        if not points:
            columns[ticker] = empty.copy()
            continue
        sparse = pd.Series(points).sort_index()
        union = sparse.index.union(close.index)
        filled = sparse.reindex(union).ffill()
        last_seen = pd.Series(sparse.index, index=sparse.index).reindex(union).ffill()
        ages = pd.Series(union, index=union) - last_seen
        fresh = filled.where(ages <= pd.Timedelta(days=max_staleness_days))
        columns[ticker] = fresh.reindex(close.index).astype(float)
    return pd.DataFrame(columns, index=close.index).reindex(columns=close.columns)


def build_short_interest_panels(
    close: pd.DataFrame,
    observations: dict[str, list[ShortInterestObservation]],
    share_counts: pd.DataFrame,
    *,
    max_staleness_days: int = SHORT_INTEREST_MAX_STALENESS_DAYS,
) -> tuple[pd.DataFrame, pd.DataFrame, ShortInterestPanelDiagnostics]:
    """The two pre-declared normalizer panels, MASKED TO THEIR COMMON
    CROSS-SECTION, plus measured diagnostics.

    Returns (short_interest_ratio_frame, days_to_cover_frame, diagnostics),
    both aligned to `close`'s exact index and columns.

        short_interest_ratio = short shares / shares outstanding
        days_to_cover        = short shares / average daily volume

    Both are RAW as-of-settlement-date quantities over their own
    denominators. The ratio's denominator comes from `share_counts`, a
    point-in-time step panel read at each value's own AVAILABILITY date, so
    a value's visibility is governed by the LATER of the two inputs' public
    dates — which is what makes the ratio point-in-time rather than just its
    numerator.

    THE MASK (module docstring section 3): every cell where either panel is
    NaN is set NaN in BOTH. Without it the two halves of the grid would rank
    different universes and the normalizer axis would be measuring a
    universe difference.

    REFUSALS, all counted:
     * `stock_split_cycle` — FINRA flagged a split in this cycle
       (stockSplitFlag == 'S'). The numerator and denominator are then on
       different share bases and the ratio is corrupted by the split factor,
       in the direction that pushes the name into the long leg. Refused.
     * `no_share_count` — no point-in-time share count is visible for this
       ticker on this observation's availability date. This is the reason the
       two share-count plausibility guards show up here: a record they refuse
       leaves a hole in the step panel, and a hole is correctly "unrankable",
       never a guess.
     * `implausible_ratio` — a ratio above SHORT_INTEREST_MAX_PLAUSIBLE_RATIO,
       i.e. more shares short than exist. The tripwire for a share-count
       corruption that got past both provider guards; see that constant.
     * `non_positive_share_count` / `non_finite_ratio` — belt and braces.
    """
    diagnostics = ShortInterestPanelDiagnostics()
    ratio_points: dict[str, dict[pd.Timestamp, float]] = {}
    dtc_points: dict[str, dict[pd.Timestamp, float]] = {}

    for ticker in close.columns:
        for observation in observations.get(ticker, []):
            if observation.split_flagged:
                diagnostics.refuse("stock_split_cycle")
                continue
            available = pd.Timestamp(observation.available)
            # Read the share count on the first trading day at or after the
            # short-interest value's own availability date: that is the
            # earliest moment BOTH inputs are public.
            position = close.index.searchsorted(available, side="left")
            if position >= len(close.index):
                diagnostics.refuse("available_after_panel_end")
                continue
            read_on = close.index[position]
            shares = share_counts.at[read_on, ticker] if ticker in share_counts.columns else np.nan

            dtc_points.setdefault(ticker, {})[available] = observation.days_to_cover

            if not np.isfinite(shares):
                diagnostics.refuse("no_share_count")
                continue
            if shares <= 0.0:
                diagnostics.refuse("non_positive_share_count")
                continue
            ratio = observation.short_shares / float(shares)
            if not np.isfinite(ratio):
                diagnostics.refuse("non_finite_ratio")
                continue
            if ratio > SHORT_INTEREST_MAX_PLAUSIBLE_RATIO:
                diagnostics.refuse("implausible_ratio")
                continue
            ratio_points.setdefault(ticker, {})[available] = ratio
            diagnostics.n_observations_used += 1

    ratio_frame = _step_frame(close, ratio_points, max_staleness_days=max_staleness_days)
    dtc_frame = _step_frame(close, dtc_points, max_staleness_days=max_staleness_days)

    ratio_valid = np.isfinite(ratio_frame.to_numpy())
    dtc_valid = np.isfinite(dtc_frame.to_numpy())
    common = ratio_valid & dtc_valid
    diagnostics.n_cells_ratio_only = int((ratio_valid & ~dtc_valid).sum())
    diagnostics.n_cells_dtc_only = int((dtc_valid & ~ratio_valid).sum())
    diagnostics.n_cells_common = int(common.sum())

    ratio_frame = ratio_frame.where(common)
    dtc_frame = dtc_frame.where(common)
    diagnostics.tickers_never_ranked = sorted(
        ticker for ticker in close.columns if not np.isfinite(ratio_frame[ticker].to_numpy()).any()
    )
    return ratio_frame, dtc_frame, diagnostics


# --- the two pre-declared signals --------------------------------------------


def _low_value_signal(frame: pd.DataFrame | None, what: str) -> pd.Series:
    """Shared body of both signals: the NEGATED formation-row value, so the
    harness's top-is-long convention lands the long leg on the LOW side —
    the paper's documented direction (module docstring section 1).

    All the real work is already done in the panel this reads. This function
    only takes the last row of a history view the harness has already
    truncated to rows <= the formation date, which is the structural
    look-ahead guarantee. A NaN cell refuses the ticker from ranking, the
    correct answer for "this company's short interest is unobservable or
    stale here"."""
    if frame is None:
        raise ValueError(
            f"{what} requires CrossSectionalData.fundamental_signal; the spec must set "
            "requires_fundamental_signal=True and the caller must supply the frame."
        )
    row = frame.iloc[-1].astype(float)
    signal = -row
    return signal.where(np.isfinite(signal))


def signal_low_short_interest_ratio(history: CrossSectionalData) -> pd.Series:
    """Short interest as a fraction of shares outstanding, negated — the
    paper's own measure (module docstring section 1a)."""
    return _low_value_signal(history.fundamental_signal, "signal_low_short_interest_ratio")


def signal_low_days_to_cover(history: CrossSectionalData) -> pd.Series:
    """Short interest in days of the cycle's own average volume, negated —
    the competing normalizer, pre-declared alongside the paper's rather than
    chosen after seeing either (module docstring section 4)."""
    return _low_value_signal(history.fundamental_signal, "signal_low_days_to_cover")


# --- the pre-declared family -------------------------------------------------

SHORT_INTEREST_NORMALIZERS: tuple[str, ...] = ("short_interest_ratio", "days_to_cover")
SHORT_INTEREST_HOLDING_DAYS: tuple[int, ...] = (21, 63, 126)
SHORT_INTEREST_PORTFOLIOS: tuple[str, ...] = ("long_universe_hedged", "long_short")

# The paper's 5th-percentile low-side cutoff — fixed, NOT searched over. See
# module docstring section 4 for why the 1st and 10th are excluded up front.
SHORT_INTEREST_RANK_FRACTION = 0.05

SHORT_INTEREST_COST_BPS = DEFAULT_XS_COST_BPS
SHORT_INTEREST_FINANCING_BPS_PER_YEAR = 0.0

SHORT_INTEREST_N_TRIALS = (
    len(SHORT_INTEREST_NORMALIZERS)
    * len(SHORT_INTEREST_HOLDING_DAYS)
    * len(SHORT_INTEREST_PORTFOLIOS)
)

SHORT_INTEREST_FAMILY = "short_interest"
SHORT_INTEREST_FAMILY_KEY = "short_interest"

_ID_PREFIX = {"short_interest_ratio": "si_ratio", "days_to_cover": "si_dtc"}
_ID_PORTFOLIO = {"long_universe_hedged": "hedged", "long_short": "ls"}


def build_short_interest_family() -> list[CrossSectionalSpec]:
    """The 12 pre-declared specs.

    Deliberately takes NO arguments: unlike the industry-neutral families,
    nothing about this grid is bound to runtime data — both signals read the
    same CrossSectionalData.fundamental_signal slot, and which PANEL is
    supplied there is the caller's job (see run_short_interest_screening,
    which screens the two normalizers as two passes over one spec list
    rather than smuggling a frame into a closure). That keeps the family
    fingerprintable for forward-validation registration without a data
    dependency."""
    specs: list[CrossSectionalSpec] = []
    for normalizer in SHORT_INTEREST_NORMALIZERS:
        signal_fn = (
            signal_low_short_interest_ratio
            if normalizer == "short_interest_ratio"
            else signal_low_days_to_cover
        )
        for holding in SHORT_INTEREST_HOLDING_DAYS:
            for portfolio in SHORT_INTEREST_PORTFOLIOS:
                specs.append(
                    CrossSectionalSpec(
                        pattern_id=(
                            f"{_ID_PREFIX[normalizer]}_{_ID_PORTFOLIO[portfolio]}_h{holding}"
                        ),
                        family=SHORT_INTEREST_FAMILY,
                        citation=SHORT_INTEREST_CITATION,
                        signal_fn=signal_fn,
                        lookback_days=SHORT_INTEREST_SIGNAL_LOOKBACK_ROWS,
                        holding_days=holding,
                        portfolio=portfolio,  # type: ignore[arg-type]
                        rank_fraction=SHORT_INTEREST_RANK_FRACTION,
                        requires_fundamental_signal=True,
                    )
                )

    assert len(specs) == SHORT_INTEREST_N_TRIALS == 12, (
        f"short interest built {len(specs)} definitions; the declared grid implies "
        f"{SHORT_INTEREST_N_TRIALS} and the build pre-declared exactly 12. All three must agree "
        "— a drift silently changes this family's DSR denominator."
    )
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    assert all(s.requires_fundamental_signal for s in specs)
    assert all(s.rank_fraction == SHORT_INTEREST_RANK_FRACTION for s in specs)
    assert all(s.leg_weighting == "magnitude" for s in specs)
    assert all(s.cohort_formation_days is None for s in specs)
    assert 21 in SHORT_INTEREST_HOLDING_DAYS, (
        "a monthly hold is IN this grid on purpose, unlike every EDGAR-based family here: the "
        "ranking variable refreshes twice a month, and 21 days is the source paper's own "
        "rebalance frequency."
    )
    return specs


def specs_for_normalizer(normalizer: str) -> list[CrossSectionalSpec]:
    """The 6 specs of one normalizer half. Used by the screening entry point,
    which must screen each half against its OWN panel — but always under the
    full 12-trial denominator, never 6 (see run_short_interest_screening)."""
    if normalizer not in SHORT_INTEREST_NORMALIZERS:
        raise ValueError(f"unknown normalizer {normalizer!r}; expected one of {SHORT_INTEREST_NORMALIZERS}")
    prefix = _ID_PREFIX[normalizer]
    return [spec for spec in build_short_interest_family() if spec.pattern_id.startswith(prefix)]


def default_short_interest_config() -> CrossSectionalConfig:
    """A fresh config per call — the harness writes formation_start onto
    whatever it is given, so a shared singleton would leak between runs."""
    return CrossSectionalConfig(
        cost_bps=SHORT_INTEREST_COST_BPS,
        financing_bps_per_year=SHORT_INTEREST_FINANCING_BPS_PER_YEAR,
    )


# --- production entry point --------------------------------------------------


@dataclass
class ShortInterestScreeningSummary:
    """run_short_interest_screening's full result: the screening output plus
    every measured coverage number a reader needs to interpret it."""

    results: list[CrossSectionalScreeningResult]
    n_trials: int
    universe_size: int
    panel_start: date | None
    panel_end: date | None
    formation_start: date
    missing_price_data: list[str] = field(default_factory=list)
    finra: ShortInterestFetchDiagnostics = field(default_factory=ShortInterestFetchDiagnostics)
    shares: ShareCountDiagnostics = field(default_factory=ShareCountDiagnostics)
    panel: ShortInterestPanelDiagnostics = field(default_factory=ShortInterestPanelDiagnostics)
    # Realized ranges of both ranking variables — the cheapest sanity check a
    # reader has that neither panel is carrying an absurd value.
    ratio_range: tuple[float, float] = (float("nan"), float("nan"))
    dtc_range: tuple[float, float] = (float("nan"), float("nan"))
    n_eligible_by_formation: dict[str, float] = field(default_factory=dict)
    # The pre-declared January DIAGNOSTIC (module docstring section 2), one
    # entry per spec: (January mean daily return, non-January mean daily
    # return). Measured and reported; never used to select a spec.
    january_split: dict[str, tuple[float, float]] = field(default_factory=dict)
    cost_bps: float = SHORT_INTEREST_COST_BPS
    financing_bps_per_year: float = SHORT_INTEREST_FINANCING_BPS_PER_YEAR
    warnings: list[str] = field(default_factory=list)


def _frame_range(frame: pd.DataFrame) -> tuple[float, float]:
    values = frame.to_numpy()
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return float("nan"), float("nan")
    return float(finite.min()), float(finite.max())


def measure_january_split(daily_returns: pd.Series) -> tuple[float, float]:
    """(mean January daily return, mean non-January daily return) for one
    spec's realized series — the pre-declared diagnostic for the "BHJ's long
    side is a January artifact" claim in module docstring section 2.

    A DIAGNOSTIC, not a spec axis: it is computed after the fact from a
    series the grid already produced, so it cannot enlarge the search."""
    index = pd.DatetimeIndex(daily_returns.index)
    is_january = index.month == 1
    january = daily_returns[is_january]
    other = daily_returns[~is_january]
    return (
        float(january.mean()) if len(january) else float("nan"),
        float(other.mean()) if len(other) else float("nan"),
    )


@dataclass
class NormalizerDivergence:
    """The POST-HOC volume-confound diagnostic, section 5.

    Post-hoc and labeled as such: it was NOT pre-registered (section 6 of the
    pre-registration declares only the January split, coverage and mask cost),
    it was computed after the verdict was already a fail, and it is
    structurally incapable of changing that verdict — nothing here feeds a
    Sharpe, a DSR or a spec selection.

    It exists as CODE rather than as a paragraph because this project's
    standing rule is that a computed result lives in git or a DB table, never
    only in prose. The 2026-09-02 figures quoted in section 5 were originally
    reported from a scratchpad script that was never committed; independent
    verification re-derived them and committed this function so they can be
    re-checked."""

    n_formations: int
    mean_names_ranked: float
    mean_leg_size: float
    # |ratio leg AND dtc leg| / |one leg| -- "they agree on about one name in
    # five". Reported alongside the stricter Jaccard so the convention is not
    # ambiguous, which it was in the original prose.
    long_leg_overlap_share_of_leg: float
    long_leg_overlap_jaccard: float
    mean_adv_percentile_of_dtc_leg: float
    mean_adv_percentile_of_ratio_leg: float
    mean_ratio_percentile_of_dtc_leg: float
    spearman_ratio_vs_dtc: float


def measure_normalizer_divergence(
    close: pd.DataFrame,
    ratio_frame: pd.DataFrame,
    dtc_frame: pd.DataFrame,
    adv_frame: pd.DataFrame,
    formation_start: date,
    holding_days: int = 63,
    rank_fraction: float = SHORT_INTEREST_RANK_FRACTION,
) -> NormalizerDivergence:
    """How far apart the two normalizers' LONG legs really are, and what the
    days-to-cover leg is actually sorting on.

    Re-derives, on the same formation cadence the harness uses, the figures
    section 5 quotes. Verified 2026-09-02 to reproduce them exactly on the
    production panel at holding_days=63: 34 formations, 19.7% leg overlap,
    72.7% / 64.5% mean ADV percentile for the dtc / ratio legs, 33.2% mean
    short-interest-ratio percentile for the dtc leg, Spearman 0.613."""
    from scipy.stats import spearmanr

    from app.services.research_lab.cross_sectional import select_leg_tickers

    positions = np.flatnonzero(close.index.date >= formation_start)  # type: ignore[attr-defined]
    rows: list[dict[str, float]] = []
    for i in range(int(positions[0]) if len(positions) else 0, len(close.index) - 1, holding_days):
        if len(positions) == 0:
            break
        day = close.index[i].date()
        prices, ratios, dtcs, advs = (
            close.iloc[i],
            ratio_frame.iloc[i],
            dtc_frame.iloc[i],
            adv_frame.iloc[i],
        )
        eligible = [
            ticker
            for ticker in close.columns
            if was_member(ticker, day)
            and np.isfinite(prices[ticker])
            and np.isfinite(ratios[ticker])
            and np.isfinite(dtcs[ticker])
        ]
        if len(eligible) < 10:
            continue
        ratio_leg, _ = select_leg_tickers(-ratios[eligible].astype(float), rank_fraction)
        dtc_leg, _ = select_leg_tickers(-dtcs[eligible].astype(float), rank_fraction)
        if not ratio_leg or not dtc_leg:
            continue
        shared = set(ratio_leg) & set(dtc_leg)
        adv_percentile = advs[eligible].rank(pct=True)
        ratio_percentile = ratios[eligible].rank(pct=True)
        rows.append(
            {
                "n_ranked": float(len(eligible)),
                "leg": float(len(dtc_leg)),
                "share": len(shared) / len(dtc_leg),
                "jaccard": len(shared) / len(set(ratio_leg) | set(dtc_leg)),
                "adv_dtc": float(adv_percentile[dtc_leg].mean()) * 100.0,
                "adv_ratio": float(adv_percentile[ratio_leg].mean()) * 100.0,
                "ratio_dtc": float(ratio_percentile[dtc_leg].mean()) * 100.0,
            }
        )

    flat_ratio = ratio_frame.to_numpy().ravel()
    flat_dtc = dtc_frame.to_numpy().ravel()
    both = np.isfinite(flat_ratio) & np.isfinite(flat_dtc)
    spearman = (
        float(spearmanr(flat_ratio[both], flat_dtc[both]).statistic)
        if both.sum() > 2
        else float("nan")
    )

    def mean_of(key: str) -> float:
        return float(np.mean([row[key] for row in rows])) if rows else float("nan")

    return NormalizerDivergence(
        n_formations=len(rows),
        mean_names_ranked=mean_of("n_ranked"),
        mean_leg_size=mean_of("leg"),
        long_leg_overlap_share_of_leg=mean_of("share"),
        long_leg_overlap_jaccard=mean_of("jaccard"),
        mean_adv_percentile_of_dtc_leg=mean_of("adv_dtc"),
        mean_adv_percentile_of_ratio_leg=mean_of("adv_ratio"),
        mean_ratio_percentile_of_dtc_leg=mean_of("ratio_dtc"),
        spearman_ratio_vs_dtc=spearman,
    )


def build_average_daily_volume_panel(
    close: pd.DataFrame,
    observations: dict[str, list[ShortInterestObservation]],
    *,
    max_staleness_days: int = SHORT_INTEREST_MAX_STALENESS_DAYS,
) -> pd.DataFrame:
    """FINRA's own trailing averageDailyVolumeQuantity as a point-in-time step
    panel, on the identical availability/staleness/split contract as the two
    ranking panels.

    Used only by measure_normalizer_divergence — no spec ranks on it, and
    adding one would be a new pre-registered family, not a diagnostic (module
    docstring section 6)."""
    points: dict[str, dict[pd.Timestamp, float]] = {}
    for ticker in close.columns:
        for observation in observations.get(ticker, []):
            if observation.split_flagged:
                continue
            points.setdefault(ticker, {})[pd.Timestamp(observation.available)] = (
                observation.average_daily_volume
            )
    return _step_frame(close, points, max_staleness_days=max_staleness_days)


def _measure_eligibility(
    close: pd.DataFrame, panel: pd.DataFrame, formation_start: date, holding_days: int
) -> float:
    """Mean count of names ranked per formation on one cadence, re-derived
    exactly as the harness derives its formation dates, under the same
    eligibility gate (point-in-time member + finite price + finite signal).
    Measurement only — the backtests never read this."""
    positions = np.flatnonzero(close.index.date >= formation_start)  # type: ignore[attr-defined]
    if len(positions) == 0:
        return float("nan")
    counts: list[int] = []
    for i in range(int(positions[0]), len(close.index) - 1, holding_days):
        formation_day = close.index[i].date()
        prices = close.iloc[i]
        values = panel.iloc[i]
        counts.append(
            sum(
                1
                for t in close.columns
                if was_member(t, formation_day)
                and np.isfinite(prices[t])
                and np.isfinite(values[t])
            )
        )
    return float(np.mean(counts)) if counts else float("nan")


def run_short_interest_screening(
    start: date = SHORT_INTEREST_FORMATION_START,
    end: date | None = None,
    provider: YFinanceProvider | None = None,
    finra: FinraShortInterestProvider | None = None,
    sec_shares: SecSharesOutstandingProvider | None = None,
    edgar: EdgarXbrlProvider | None = None,
    config: CrossSectionalConfig | None = None,
    universe: list[str] | None = None,
) -> ShortInterestScreeningSummary:
    """THE production entry point: one FINRA fetch, one SEC frames fetch, one
    price fetch, one 12-spec pre-declared family screened under its own
    12-trial DSR denominator.

    THE TWO NORMALIZER HALVES ARE SCREENED AS TWO PASSES over two different
    fundamental_signal panels — the harness takes exactly one such frame per
    call — but BOTH passes are given n_trials_override=12, the family's full
    pre-declared size. Screening 6 specs and letting the harness infer
    n_trials=6 would halve the DSR denominator for a search that really did
    cover 12 definitions, which is precisely the trial-count laundering
    screen_cross_sectional_universe refuses to let a caller express
    downward. sigma_sr is necessarily estimated within each pass (the
    harness has no cross-pass view), which is a real and disclosed
    limitation: it is the std of 6 sibling Sharpes, not 12."""
    end = end if end is not None else date.today()  # noqa: DTZ011 — fetch end bound only
    provider = provider if provider is not None else YFinanceProvider()
    finra = finra if finra is not None else FinraShortInterestProvider()
    sec_shares = sec_shares if sec_shares is not None else SecSharesOutstandingProvider()
    edgar = edgar if edgar is not None else EdgarXbrlProvider()
    config = config if config is not None else default_short_interest_config()
    config.formation_start = start

    warnings: list[str] = []
    sample = universe if universe is not None else get_universe_over(start, end)
    universe_size = len(sample)

    padded_start = start - timedelta(days=SHORT_INTEREST_PRICE_HISTORY_PADDING_CALENDAR_DAYS)
    close, missing_price = provider.get_price_history(sample, padded_start, end)
    if close.empty:
        return ShortInterestScreeningSummary(
            results=[],
            n_trials=SHORT_INTEREST_N_TRIALS,
            universe_size=universe_size,
            panel_start=None,
            panel_end=None,
            formation_start=start,
            missing_price_data=missing_price,
            warnings=["No price data resolved for any universe ticker."],
        )
    if missing_price:
        warnings.append(
            f"{len(missing_price)} of {universe_size} universe tickers resolved no price data "
            "(the standing departed-member yfinance gap — see cross_sectional.py)."
        )

    priced = list(close.columns)
    observations, finra_diagnostics = finra.fetch_observations_for_tickers(
        priced, SHORT_INTEREST_CYCLE_FETCH_START, end
    )

    cik_map = edgar.get_ticker_cik_map()
    resolvable = {ticker: cik_map[ticker] for ticker in priced if ticker in cik_map}
    share_observations, share_diagnostics = sec_shares.fetch_share_counts(
        resolvable,
        padded_start,
        end,
        missing_from_map=[ticker for ticker in priced if ticker not in cik_map],
    )
    if share_diagnostics.tickers_without_cik:
        warnings.append(
            f"{len(share_diagnostics.tickers_without_cik)} priced tickers resolve no CIK in SEC's "
            "current-day ticker map and can never carry a short-interest RATIO — see module "
            "docstring section 3 on the asymmetry this creates and the mask that answers it."
        )

    share_frame, no_shares = build_point_in_time_share_count_frame(
        close, share_observations, max_staleness_days=SHARES_MAX_STALENESS_DAYS
    )
    ratio_frame, dtc_frame, panel_diagnostics = build_short_interest_panels(
        close, observations, share_frame
    )
    if no_shares:
        warnings.append(f"{len(no_shares)} priced tickers produced no usable share count.")
    if panel_diagnostics.tickers_never_ranked:
        warnings.append(
            f"{len(panel_diagnostics.tickers_never_ranked)} priced tickers are never ranked in any "
            "formation (no cycle where both a short-interest ratio and a days-to-cover exist)."
        )

    results: list[CrossSectionalScreeningResult] = []
    january: dict[str, tuple[float, float]] = {}
    for normalizer, panel in (
        ("short_interest_ratio", ratio_frame),
        ("days_to_cover", dtc_frame),
    ):
        data = CrossSectionalData(close=close, fundamental_signal=panel)
        specs = specs_for_normalizer(normalizer)
        results.extend(
            screen_cross_sectional_universe(
                data, specs, config, n_trials_override=SHORT_INTEREST_N_TRIALS
            )
        )
        # THE PRE-DECLARED JANUARY DIAGNOSTIC (module docstring section 2).
        # This costs a second replay per spec, which is real wall clock and
        # is spent deliberately: screen_cross_sectional_universe keeps its
        # replays internal and returns only summary statistics, and the
        # honest alternatives are worse. Widening that function's return
        # type would touch every family in this project for one diagnostic;
        # computing the split for only "the interesting specs" would be a
        # post-hoc selection. The replay is deterministic, so these series
        # are exactly the ones the screen above scored.
        for spec in specs:
            replay = run_cross_sectional_backtest(data, spec, config)
            if replay.status == "ok" and len(replay.daily_returns) > 0:
                january[spec.pattern_id] = measure_january_split(replay.daily_returns)

    eligible: dict[str, float] = {}
    for normalizer, panel in (("si_ratio", ratio_frame), ("si_dtc", dtc_frame)):
        for holding in SHORT_INTEREST_HOLDING_DAYS:
            eligible[f"{normalizer}_h{holding}"] = _measure_eligibility(
                close, panel, start, holding
            )

    return ShortInterestScreeningSummary(
        results=sorted(results, key=lambda r: -r.sharpe_annualized),
        n_trials=SHORT_INTEREST_N_TRIALS,
        universe_size=universe_size,
        panel_start=close.index[0].date(),
        panel_end=close.index[-1].date(),
        formation_start=start,
        missing_price_data=missing_price,
        finra=finra_diagnostics,
        shares=share_diagnostics,
        panel=panel_diagnostics,
        ratio_range=_frame_range(ratio_frame),
        dtc_range=_frame_range(dtc_frame),
        n_eligible_by_formation=eligible,
        january_split=january,
        cost_bps=config.cost_bps,
        financing_bps_per_year=config.financing_bps_per_year,
        warnings=warnings,
    )


__all__ = [
    "SHORT_INTEREST_CITATION",
    "SHORT_INTEREST_FAMILY",
    "SHORT_INTEREST_FAMILY_KEY",
    "SHORT_INTEREST_FORMATION_START",
    "SHORT_INTEREST_HOLDING_DAYS",
    "SHORT_INTEREST_MAX_STALENESS_DAYS",
    "SHORT_INTEREST_NORMALIZERS",
    "SHORT_INTEREST_N_TRIALS",
    "SHORT_INTEREST_PORTFOLIOS",
    "SHORT_INTEREST_RANK_FRACTION",
    "NormalizerDivergence",
    "ShortInterestPanelDiagnostics",
    "ShortInterestScreeningSummary",
    "build_average_daily_volume_panel",
    "build_short_interest_family",
    "build_short_interest_panels",
    "default_short_interest_config",
    "measure_january_split",
    "measure_normalizer_divergence",
    "run_short_interest_screening",
    "signal_low_days_to_cover",
    "signal_low_short_interest_ratio",
    "specs_for_normalizer",
]
