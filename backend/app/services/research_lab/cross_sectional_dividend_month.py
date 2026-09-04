"""DIVIDEND MONTH PREMIUM: a 12-definition CALENDAR-driven family -- long
every point-in-time S&P 500 member the calendar says is DUE TO GO
EX-DIVIDEND this month, before the dividend is declared and with no
knowledge of whether it will be declared or how large it will be, short a
declared comparison set of members that are not.

The pre-registration, committed in f8e5c1a BEFORE any return existed, is
data/research_runs/dividend_month_premium_PREREGISTRATION.txt. The grid, the
forecast rule, the decision rule and the diagnostics below are that
document's, unchanged. Sections 1-4 here restate what a reader of this file
needs; section 5 is filled in after the run and is the only part written
with a result in view.

=======================================================================
1. THE SOURCE, ITS TIER, AND TWO CORRECTIONS TO THIS FAMILY'S OWN BRIEF
=======================================================================
CITATION STATUS -- READ THIS BEFORE QUOTING ANY NUMBER BELOW.

 [HS13] Hartzmark, Samuel M. & Solomon, David H., "The dividend month
        premium", Journal of Financial Economics 109(3), September 2013,
        pp. 640-660, doi:10.1016/j.jfineco.2013.02.015. RECORD VERIFIED at
        Crossref. THE PUBLISHED BODY WAS NOT RETRIEVED -- OpenAlex reports
        the work closed access with no OA location and no deposited
        abstract; SSRN, ScienceDirect, ResearchGate, Springer and aaltodoc
        all returned HTTP 403.
 [HS12] The EFA 2012 conference draft of the same paper ("This Draft: May
        25th, 2012", sample January 1927 - December 2009), retrieved from
        the Internet Archive. PRIMARY -- the full body was downloaded and
        every quotation in this module was re-grepped out of that local
        copy during the build, not taken on trust. IT IS A WORKING PAPER.
        The published version's sample runs later; numbers drift between
        versions, and every figure below is the DRAFT's unless labelled.

CORRECTION TO THE BUILD BRIEF #1: the brief cited this candidate as "Slow
Moving Capital?". THE TITLE IS WRONG -- that DOI returns "The dividend
month premium", and "Slow Moving Capital" is a different paper by different
authors (Mitchell, Pedersen & Pulvino). Nothing here derives from it.

CORRECTION TO THE BUILD BRIEF #2, AND IT IS THE LOAD-BEARING ONE: the brief
described the effect as occurring in months a firm is predicted to PAY a
dividend. [HS12] states the opposite convention verbatim -- "Dividend
months refer to months with an ex-date unless otherwise noted." The premium
is keyed on the EX-DIVIDEND DATE. That is not a quibble: it is the
difference between a quantity this project's data can represent and one it
cannot (Yahoo's actions feed carries the ex-date and nothing else), and it
puts the mechanism's pivot -- where buying pressure stops and reversal
begins -- on the ex-day, which is what makes the event study in section 4
the right diagnostic.

THE MECHANISM. A PRICE-PRESSURE story, not a risk story: dividend-seeking
investors buying ahead of the ex-day. The paper's central argument against
risk is structural rather than statistical, and it is the reason the
'within' short leg exists (section 3).

  CORRECTION MADE ON INDEPENDENT VERIFICATION, 2026-09-02. An earlier
  revision of this paragraph introduced that sentence as "the mechanism, in
  the paper's own words", and the pre-registration escalated it to "and not
  paraphrased", while describing the mechanism as buying pressure "meeting
  INELASTIC SHORT-RUN SUPPLY". THAT PHRASE IS NOT IN THE PAPER. Grepped:
  "inelastic" appears 0 times in the source and "supply" 0 times. The
  paper's own framing is demand-side -- that "demand curves for stocks
  actually slope downwards" -- and the inelastic-supply gloss came from this
  family's build brief, not from [HS12]. Nothing downstream depended on it,
  but a quotation marker around text the source does not contain is exactly
  the failure this project's citation discipline exists to catch, so it is
  recorded here rather than quietly deleted.

THE REVERSAL, which is this family's mechanism test and is quoted rather
than characterized. [HS12] Table IV Panel A, mean characteristic-adjusted
returns: actual declaration day +11.7bp, predicted declaration day +3.0bp,
interim +15.8bp, ex-day +26.6bp, and the 40 days AFTER the ex-day -73.2bp,
"(all highly statistically significant)". Their own reading:

    "abnormal returns in the 40 days after the ex-dividend day are -73
     basis points. This effect is large enough to offset the gains during
     the dividend month, reinforcing the conclusion that the main effect is
     a time-series one and that the price increases are reversed by
     subsequent price decreases."

That is FULL reversal, and the same authors later describe the 2013 result
as "a temporary price impact" in Hartzmark & Solomon, "Predictable Price
Pressure" (2021), also retrieved and read.

TWO PRECISION NOTES ON THOSE FIGURES, both added on independent
verification. (a) The paper's +54.2bp is the total "from announcement to
ex-day" and 49.1% of it IS THE EX-DAY ITSELF, so it must not be described as
run-up BEFORE the ex-day -- strictly before, the paper's own decomposition
gives 11.7 + 15.8 = 27.5bp. An earlier revision of this docstring made that
mistake. (b) 54.2 is a figure from the paper's TEXT; the corresponding
Table IV Panel A "declaration to ex-day" cell reads 0.534 (t = 37.28). The
0.8bp gap is the paper's own and is not reconciled here.

  CORRECTED ON THE SECOND INDEPENDENT VERIFICATION, 2026-09-02 -- see
  ERRATA V2. That t-statistic was published here as 12.31, which is NOT
  Table IV's. 12.31 is Table III Panel A's t for the equal-weighted
  BETWEEN-COMPANIES difference portfolio, whose alpha is also 0.534 -- two
  different quantities that happen to share three digits, and the wrong one
  was picked up. Table IV Panel A reads, in full: predicted declaration day
  0.117 (23.97), declaration day 0.030 (6.78), interim 0.158 (12.10), ex-day
  0.266 (63.42), declaration-to-ex-day 0.534 (37.28), 40 days after ex-day
  -0.732 (-32.60). Nothing downstream used the t; the entry exists because a
  paragraph whose whole subject is citation precision is the last place an
  unchecked number belongs.

THE PAPER'S OWN SHARPE RATIOS, AND A RETRACTED CLAIM ABOUT THEM.

  *** RETRACTION, MADE ON INDEPENDENT VERIFICATION 2026-09-02. *** Earlier
  revisions of this module and of the pre-registration asserted that [HS12]
  CONTRADICTS ITSELF on Sharpe -- "an 'annual Sharpe Ratio of 0.194' ... 
  while Table II Panel B of the SAME draft reports 0.188, 0.097 and 0.019
  ... Those do not reconcile ... the word 'annual' appears to be wrong in
  one of them" -- and used that as the reason to quote no paper Sharpe at
  all. THE ASSERTION IS WRONG AND IS WITHDRAWN. Re-reading the source: the
  introduction's figure is an ANNUAL-FREQUENCY statistic, and the paper says
  so in the very next sentence ("positive excess returns in 71 out of 81
  years, with the largest negative annual return being only -4.6%"), while
  Table II's own note reads "All columns listing percentiles are for monthly
  returns". Two frequencies, both correctly labelled, no contradiction. No
  sqrt(12) relation should hold between them and none does. The error was
  ours, not the paper's, and it had a real cost: it suppressed the one
  external comparator a reader of THIS family most wants.

  THE COMPARATORS, now stated. [HS12]'s within-companies portfolio: annual
  Sharpe 0.194 (annual-frequency), monthly Sharpe 0.097 in Table II Panel B
  (which would be ~0.336 if naively annualized); the long-only dividend
  month portfolio 0.413. Panel B in fact lists FIVE Sharpes across five
  portfolios (0.188, 0.124, 0.083, 0.097, 0.019), so no single one of them
  is "the" paper Sharpe.

  THEY STILL ARE NOT LIKE-FOR-LIKE WITH THIS FAMILY'S NUMBERS, and that is
  the honest caveat rather than a reason for silence: this family annualizes
  from DAILY returns on a large-cap-only universe with no factor adjustment,
  the paper computes from annual or monthly returns on all of CRSP. Compare
  them as order-of-magnitude context (paper ~0.19-0.41; this family's best
  gross +0.443, best net -0.122), never as a replication check.

=======================================================================
2. THE HONEST PRIOR -- QUANTITATIVE, AND WRITTEN BEFORE ANY RESULT
=======================================================================
Two facts point the same way and neither is rhetorical.

FIRST, THE UNIVERSE IS THE WRONG ONE FOR THIS EFFECT AND THE PAPER SAYS SO
ITSELF. [HS12]'s cross-sectional evidence is that ILLIQUID stocks show both
larger run-ups and larger reversals: a one standard deviation move in their
liquidity measure changes interim returns by 7.0bp, ex-day returns by 4.8bp
and the 40-day post-period by 11.7bp. The S&P 500 is the most liquid
large-cap segment there is -- precisely where a price-pressure effect should
be SMALLEST. Their own value-weighted alphas sit below their equal-weighted
ones (+29.2bp vs +37.4bp within-companies), pointing the same way.

SECOND, THE DECAY IS MEASURED, NOT ASSUMED. Chen & Zimmermann's Open Source
Asset Pricing project publishes monthly long-short returns for their
"DivSeason" implementation of [HS12]'s exact forecast rule. That series was
downloaded and computed twice, independently, agreeing to every digit:

    through 2009-12   1004 mo  +0.324%/mo  t=13.68  ann.Sharpe +1.50
    2013-01 onward     144 mo  +0.107%/mo  t= 2.61  ann.Sharpe +0.75
    2015-01 onward     120 mo  +0.091%/mo  t= 1.97  ann.Sharpe +0.62
    2016-01 onward     108 mo  +0.081%/mo  t= 1.63  ann.Sharpe +0.54  (n.s.)

THE 2016-01 ROW IS THIS FAMILY'S OWN FORMATION WINDOW, and it sets the
expectation quantitatively: a BROAD-universe, EQUAL-weighted, GROSS-of-cost
implementation of this rule earns about 0.54 annualized -- NOT statistically
distinguishable from zero -- over 2016-2024 with thousands of names per leg.
This family runs the same rule on ~144 long names against ~119-226 short,
large-cap only, NET of 5bp. It should expect materially less than 0.54, and
0.54 is already far below this family's own 0.95 DSR bar.

  CORRECTION MADE ON INDEPENDENT VERIFICATION. The pre-registration named
  the 2015-01 row as this family's window and quoted 0.62 against "~170 long
  names against ~260 short". BOTH ARE WRONG for the run that actually
  happened. FORMATION_START is 2016-01-04 (the forecast rule needs a year of
  the firm's own ex-dates inside the priced panel before it can fire, so the
  first accepted formation is 2016-01-29), the realized leg sizes are 144
  long against 218-226 short, and the right comparator is therefore the
  0.54 row -- which is INSIGNIFICANT, making the prior even less favourable
  than the pre-registration stated. The change moves the prior in the
  direction UNFAVOURABLE to this family, which is why it is corrected here
  rather than argued about.

THE DECAY IS CONTESTED AND BOTH READINGS ARE RECORDED. The AUTHORS' OWN
2018 update (Annual Review of Financial Economics 10, pp. 499-517,
retrieved and read) re-runs the strategy value-weighted "including the most
recent data" and finds essentially no decay: raw 0.276 (t=7.25), FF4 0.282
(t=7.14), FF5 0.332 (t=7.35). Separately Ainsworth & Nicholson's 11-country
study (Datastream, 1993-2013) is a genuinely modern out-of-sample US window
and CONFIRMS at +75bp/month against other dividend payers -- larger than
[HS12]'s own 37bp -- while finding the effect significantly NEGATIVE in
Australia and insignificant in Japan, Hong Kong, Italy and New Zealand.
Equal- versus value-weighting is the most likely reconciliation and this
build could not settle it.

An honest negative is the expected outcome here and is a complete result.

=======================================================================
3. THE FORECAST RULE AND THE PRE-DECLARED GRID
=======================================================================
THE RULE IS THE PAPER'S OWN, quoted verbatim from [HS12]:

    "We forecast using the following rule: a company has a 'predicted
     dividend' in month t if it paid a quarterly dividend in months t-3,
     t-6, t-9, or t-12, a semi-annual dividend in months t-6 or t-12, an
     annual dividend in months t-12, or a dividend of unknown frequency in
     months t-3, t-6, t-9, or t-12 (excluding the unknown dividends does
     not affect the results)."

Point-in-time by construction: every input is an ex-date at least three
months old at the formation it justifies, so a prediction can never read a
distribution that had not yet happened. build_dmp_positions asserts this
rather than trusting it.

IT IS NOT THE BEST-SCORING RULE ON THIS DATA, and that is recorded here
rather than discovered later. Measured on real ex-dates over the formation
window, month level, dates only, no returns:

    HS13 rule (adopted)              precision 0.792   recall 0.956
    naive: ex-date in month t-12     precision 0.918   recall 0.909
    t-12 AND t-24                    precision 0.934   recall 0.840
    t-12 OR t-24                     precision 0.866   recall 0.927
    t-3 only                         precision 0.875   recall 0.872
    t-3 AND t-12                     precision 0.966   recall 0.820
    t-12 +/- 1 month                 precision 0.337   recall 0.974

(These are the RUN's measured numbers, over the 2016-01..2026-06 formation
window. The pre-registration's table is the same measurement over its
mistakenly-stated 2015-01 window and differs in the third decimal; see the
formation-window correction in section 2.)

FIVE of the six alternatives beat it on precision -- every one except the
+/-1-month variant. An earlier revision of this docstring and the
pre-registration both said "four", which was simply a miscount of their own
table. THE PAPER'S RULE IS ADOPTED
ANYWAY, because this family's job is to test [HS13]'s claim on this
universe, not to build the best dividend-month forecaster this project can.
Tuning a predictor against a score measured on the same sample the returns
come from is one step from tuning it against the returns. The alternatives
are measured and reported so the choice is checkable; none is ever traded.

THREE DEVIATIONS FROM [HS12], each forced by data this project does not
have, each declared rather than discovered:

 (1) UNIVERSE. [HS12] uses all CRSP NYSE/AMEX/NASDAQ common shares (share
     code 10/11, excluding ADRs, units, closed-end funds and REITs). This
     family uses the point-in-time S&P 500, a large-cap subset two orders
     of magnitude smaller and NOT share-code screened. See section 2 for
     why that is the single biggest reason to expect little here.
 (2) FREQUENCY CLASSIFICATION. [HS12] reads declared frequency from CRSP's
     distribution code. THIS PROJECT HAS NO CRSP. Frequency is INFERRED,
     point-in-time, from the count of the firm's own ex-dates in months
     t-12..t-1 (see classify_dividend_frequency). A misclassified firm is
     predicted in the wrong months, which dilutes both legs.
 (3) VALUE WEIGHTING IS NOT REPRODUCED. [HS12] reports equal- and
     value-weighted books side by side. This project has no cheap
     point-in-time market cap for this universe, so the second weighting
     axis here is DIVIDEND YIELD, not market cap. That is a deviation and
     is not presented as a replication of the paper's VW book.

THE GRID -- 12 SPECS, FROZEN BY THE PRE-REGISTRATION:

  short leg {between, within, one_after}   3   [HS12]'s OWN three
  x weighting {equal, yield}               2
  x window {month, toex}                   2
  = 12 definitions.

The short legs are not three variants invented here; they are the paper's
own three comparison portfolios from its Table III. 'within' is [HS12]'s
identification workhorse and the reason condition (ii) of the decision rule
exists: a quarterly payer is long 4 months a year and short the other 8, so
fixed factor loadings cancel -- "any fixed loadings on risk factors will
tend to cancel out, making systematic risk a less likely explanation."

The 'yield' weighting is theory-implied rather than generic. [HS12] defines
its yield as "the average from the previous 12 months of dividends payment
(in months that included a dividend), divided by" price, and reports that a
one standard deviation increase in it adds 26.2bp to the interim return and
4.5bp to the ex-day return. It is a MAGNITUDE, so no past return's sign
ever reaches the weights.

PRE-DECLARED PREDICTION ON THE WINDOW AXIS, written before any return: under
the price-pressure mechanism 'toex' should BEAT 'month', because [HS12]'s
own daily decomposition puts +54.2bp of run-up before the ex-day and
-73.2bp in the 40 days after it, part of which falls inside the same
calendar month. If 'month' beats 'toex' across the grid, whatever is being
measured is not the run-up the mechanism describes.

THE SHORT LEG IS ALWAYS EQUAL-WEIGHTED whatever the weighting axis says,
and always runs the FULL calendar month whatever the window axis says. It
is a comparison pool, not a ranked leg, and cross_sectional.py's own rule
for its universe hedge is reused rather than re-decided.

PRICE BASIS. Returns are computed from TOTAL-RETURN (dividend- and
split-adjusted) closes, the same basis every other equity family here uses.
THIS IS NOT A STYLE CHOICE: on the ex-day the price falls by roughly the
dividend, so a price-only series would hand the long leg a mechanical loss
on exactly the day this family is pointed at, and the whole result would be
an artifact of the price basis. The YIELD DENOMINATOR is the opposite --
Yahoo's split-adjusted-but-not-dividend-adjusted Close -- because the
dividend amounts are on that basis too. Mixing them would overstate
historical yields by a per-ticker factor. Both frames are carried
explicitly and a test pins the pairing.

=======================================================================
4. DIAGNOSTICS AND THE DECISION RULE
=======================================================================
NOT specs, NOT in n_trials:

 * THE EX-DAY EVENT STUDY, and the reason this family is worth running even
   if the portfolio is a null. Mean universe-hedged daily return in event
   time around every ACTUAL ex-date in the formation window, cumulated.
   PRE-DECLARED READING: price pressure predicts a positive run-up into day
   0 and a negative drift afterwards that offsets it. If there is no
   reversal here that is evidence against the mechanism as described
   operating in this sample, and it is reported as such -- INCLUDING in the
   case where the portfolio specs look positive, which would then be a
   positive whose stated mechanism is unsupported. Computed with hindsight
   on actual ex-dates; never consulted in position formation. It is
   universe-hedged, NOT DGTW characteristic-adjusted as [HS12]'s is, so its
   levels are not directly comparable to the paper's -- the SHAPE is.
 * THE PLACEBO CALENDAR -- the falsification control. Every predicted month
   shifted +1, which for a quarterly payer lands in a month it is NOT due
   to go ex. A VETO, NOT A TIEBREAK: if the placebo earns what the real
   book earns, the family is a null regardless of its headline.
 * caught_actual_fraction per spec, the cost ladder, gross-vs-net Sharpes,
   subperiod Sharpes, leg sizes, and how often the $5 screen and the
   outside-month ex-day degradation bind.

DECISION RULE, fixed before the result, on the best DSR at the 5.0bp
headline:
   (i)  DSR >= 0.95 (n_trials=12) -- the bar this project's other 12-spec
        literature-nominated family in this same wave used; AND
   (ii) that spec's 'within'-short-leg counterpart, at the same weighting
        and window, is also materially positive.
Condition (ii) is the load-bearing one. Payers differ from non-payers in
ways [HS12] documents -- "dividend-paying stocks have larger market
capitalization, and a higher book-to-market ratio" -- so a book long
payers-in-their-month and short EVERYTHING ELSE carries a permanent
payer-vs-non-payer tilt. A positive that appears only under 'between' is a
dividend-PAYER result, not a dividend-MONTH result. This is the structural
analogue of the industry-neutral half of the asset_growth grid.

NO RISK-FACTOR CONTROL EXISTS HERE. [HS12] reports four-factor ALPHAS; this
family reports raw long-short Sharpes with no factor adjustment, because
this project's harness runs no factor regressions. A positive here is NOT
an alpha and must not be described as one. Condition (ii) is a structural
substitute for factor neutrality, not an equivalent of it.

=======================================================================
5. PRODUCTION RUN 2026-09-02 -- MEASURED COVERAGE AND RESULTS
=======================================================================
Sections 1-4 and the pre-registration were committed in f8e5c1a BEFORE this
run existed. Everything below is what came out; the grid, the forecast
rule, the window prediction and the decision rule applied are that commit's,
unchanged. Full detail in data/research_runs/dividend_month_premium_
2026-09-02.txt.

Run tag "dividend_month_premium_2026-09-02", persisted to
cross_sectional_trial_results under family_key "dividend_month_premium" (12
rows, n_trials=12 on every row). Formations 2016-01-04..2026-06-30, price
panel 2013-01-02..2026-09-01, 2,662 realized trading days per spec.

DATA PROVENANCE -- REAL. Ex-dividend dates and amounts are real yfinance
corporate-actions data; prices are real yfinance daily bars. No synthetic
input touched any persisted number.

COVERAGE: 768 point-in-time candidate tickers, 496 with a dividend calendar
and a price, 24,798 ex-dates. 18,164 long firm-months per spec; long leg
mean 144 names (min 72, max 206) under 'month' and mean 79.7 under 'toex' --
where the MINIMUM IS 1, because every 'toex' position closes on or before
its predicted ex-day and the tail of a month can be down to a single name at
1.0 of notional against a 119-226 name short leg. That is the more alarming
number of the two and it belongs here rather than only in the report's
table. Short leg 119-226 depending on the axis. The $5 price screen bound 51 times and
the ex-day projection landed outside its target month 902 times out of
18,164 (5.0%, against 4.6% measured in advance).

RESULTS -- HONEST NEGATIVE ON THE PORTFOLIO, POSITIVE ON THE MECHANISM.
ALL TWELVE SPECS ARE NEGATIVE NET of the 5.0bp headline cost, spanning
-0.122 to -0.714, and the best deflated Sharpe is 0.076 against a
pre-registered 0.95 bar. Condition (i) fails by an order of magnitude, so
condition (ii) is never reached. That is the verdict.

FOUR THINGS THE STRUCTURE SAYS, and three of them are more interesting than
the verdict:

 * EVERY SPEC IS POSITIVE GROSS (+0.158 to +0.443) AND THE PLACEBO LOSES
   TO THE LIVE BOOK ON ALL TWELVE. The falsification control -- the
   identical machinery with every predicted month shifted one month, landing
   between a quarterly payer's ex-dates -- earns LESS than the live book on
   every spec, by +0.17 to +0.74 of gross Sharpe, and catches a real ex-date
   8-9% of the time against 54-80% for the live book. So the gross positive
   is not a generic long-short artifact: it IS about dividend months. What
   kills it is cost, not the absence of signal.
   PRECISION, corrected on independent verification: the placebo's own gross
   Sharpe is negative on NINE of twelve specs, not all twelve as an earlier
   revision of this bullet claimed. It is positive, slightly, on exactly the
   three EQUAL-WEIGHTED 'toex' specs -- values not quoted here because they
   sit in the digit D5 shows is vendor noise. The pre-registered test is the
   live-versus-placebo DIFFERENCE, which is positive 12/12, so the veto is
   passed either way -- but "the placebo is negative" was an overstatement
   of it and is withdrawn.

 * THE EX-DAY EVENT STUDY SHOWS THE RIGHT SHAPE, AND A POST-HOC TEST THEN
   TOOK MOST OF IT AWAY. THIS BULLET WAS REWRITTEN AFTER THE CONFOUND BELOW
   WAS FOUND; its first version claimed "THE MECHANISM IS SUPPORTED" and
   that claim was wrong. Over 14,924 real ex-dates the universe-hedged
   excess return runs UP +12.84bp into the ex-day (t = +2.15, +2.12
   clustered by ex-date month) and REVERSES -18.08bp over the following 40
   days (t = -2.34, -3.27 clustered), with a round trip of -5.24bp at
   t = -1.20 -- not distinguishable from zero. That IS the full-reversal
   signature [HS12] reports, at roughly a quarter of its magnitude.
   THOSE THREE NUMBERS NOW COME FROM ONE POPULATION, which they did not
   before independent verification: the run-up and reversal were being read
   off the per-offset curve (averaged over every event with data at that
   offset, 15,255) while the t-statistics and the round trip came from the
   complete-window subset (14,924). The published pair was +12.02 and
   -18.35, which sums to -6.33 against a stated round trip of -5.24. Fixed
   in the code, not in the prose, and pinned by a regression test.

   BUT 92.0% OF THOSE EVENT WINDOWS ALSO CONTAIN A REAL 8-K ITEM 2.02
   EARNINGS ANNOUNCEMENT (median distance from ex-date to nearest
   announcement: 17 trading days). Firms declare dividends alongside
   earnings, so the two calendars are close by construction, and this
   family's universe-hedged study CANNOT separate them -- [HS12]'s Table IV
   can, because it decomposes declaration day, interim period and ex-day,
   which needs a DECLARATION-date feed this project does not have. On the
   8.0% of ex-dates with no announcement anywhere in the window the shape
   does not survive: run-up -42.5bp (clustered t -0.06), reversal -35.5bp
   (t +0.10), round trip -78.0bp (t +0.06).

   THE HONEST CONCLUSION IS "NOT SUPPORTED", NOT "REFUTED". The clean subset
   drops 92% of events and what remains is a SELECTED population -- firms
   whose dividend calendar sits far from their earnings calendar are unusual
   by construction, and the clustered t there has few effective observations.
   So this family observed a run-up-and-reversal pattern consistent with
   [HS12]'s mechanism and CANNOT attribute it to dividend price pressure
   rather than to earnings. That is a weaker claim than the first draft of
   this bullet made, and it is the one the evidence carries.

 * THE PRE-DECLARED WINDOW PREDICTION IS CONFIRMED ON GROSS, 6/6, AND
   REVERSED ON NET. Section 3 committed in advance to expecting 'toex' to
   beat 'month' because part of the reversal falls inside the same calendar
   month. It does, in every one of the six matched pairs. But exiting
   mid-month multiplies turnover by 2.1-2.4x per matched pair (0.334-0.371
   daily L1 against 0.137-0.176), and at 5bp that costs more than the extra
   run-up is worth:
   every 'toex' spec is WORSE than its 'month' twin on net. Capturing the
   run-up before the reversal is real and is not economic here.

 * COST IS THE DECIDING ASSUMPTION AFTER ALL, which section 5 of the
   pre-registration said it should not be and pre-committed to treating as
   a finding if it were. The whole grid flips inside the cost ladder:

       0.0bp  12/12 positive, best dmp_one_after_yield_toex  +0.443
       1.0bp  12/12 positive, best dmp_one_after_yield_toex  +0.298
       2.0bp   7/12 positive, best dmp_one_after_yield_toex  +0.154
       3.5bp   1/12 positive, best dmp_one_after_yield_month +0.001
       5.0bp   0/12 positive, best dmp_one_after_yield_month -0.122

   2.0bp is this project's own sourced best estimate for an equal-weighted
   S&P 500 book, and even there the best spec is +0.154 -- a number no bar
   in this project would pass. So the honest statement is narrower than
   "there is nothing here": there is a small gross effect of about the size
   the decayed public replication predicts, and it sits inside the spread.

THE PRIOR WAS RIGHT, AND THAT IS WORTH SAYING PLAINLY. Section 2 predicted,
before any number existed, that this family should expect materially less
than the 0.62 annualized Sharpe that a broad-universe, equal-weighted,
gross-of-cost implementation of the same rule earns over 2015-2024 on
Chen & Zimmermann's public series. The best gross Sharpe here is +0.443 and
the best net is -0.122. The large-cap restriction and the cost both bit in
the predicted direction and by roughly the predicted amount.

THIS FAMILY'S PRINCIPAL DESIGN DEFECT, FOUND AFTER THE RUN AND DELIBERATELY
NOT FIXED IN IT. The 'between' short leg is NOT [HS12]'s 'between
companies' portfolio: the paper shorts all companies not predicted to pay,
INCLUDING never-payers, while this implementation's short pool holds only
dividend payers -- because the entrypoint prices only tickers with a
dividend calendar (129 priced never-payers, a fifth of the priced universe,
are absent from the panel), and because the uniform 4-prior-ex-date gate
excludes a never-payer by construction. THE PRE-REGISTRATION CONTRADICTED
ITSELF: it described 'between' as "INCLUDING firms that never pay" while
freezing a gate that makes that impossible, and the code followed the gate.
The measurable consequence is that 'between' and 'within' differ only by a
trailing-12-month recency test -- 28,402 against 27,505 short slots, 3.3%
apart -- so decision-rule condition (ii) has far less discriminating power
than intended and is not the paper's payer-versus-non-payer contrast.
(CORRECTED ON THE SECOND INDEPENDENT VERIFICATION -- see ERRATA V3. This
read "28,539 ... 3.6% apart", which was the count BEFORE ERRATA C2 removed
monthly payers from the 'between' leg, and which the run report's own
position-gate table already contradicted at 28,402.)
It was NOT re-run with a corrected universe: changing a frozen gate after
seeing the result is precisely the move the pre-registration exists to
prevent, and the verdict does not turn on it. It is the first thing a
successor should fix, and any successor must carry these 12 trials into its
own DSR denominator.

OVERLAP WITH THE SIBLING earnings_announcement_premium FAMILY -- MEASURED,
NOT ARGUED, because the build brief flagged it and because it turned out to
matter. Both families are "long a predictable corporate event, short the
rest of the index", both infer the event from the firm's own past calendar,
and both run on this universe and window. Using both cached calendars:

 * AS EVENTS THEY ARE DISTINCT. Of 18,014 ex-dates matched to their nearest
   real announcement, only 0.8% fall on the same day, 4.0% within 3 calendar
   days and 16.9% within 10; the median absolute gap is 24 calendar days and
   the median SIGNED gap is -13 days (announcement first, which is what
   declaring a dividend alongside earnings looks like). At the portfolio
   level 28.2% of ex-date firm-months are also announcement firm-months.
   So the two families do not hold the same names for the same reason, and
   this is NOT a re-run of the earnings family.
 * AS EVENT WINDOWS THEY ARE BADLY ENTANGLED, which is the finding above:
   92.0% of the -20..+40 trading-day ex-day windows contain an announcement.
   The families' PORTFOLIOS are separable; their MECHANISM EVIDENCE is not.
 * THE DEEPEST OVERLAP IS THE SEARCH, and n_trials cannot see it. Both
   families were nominated by one literature scan, test one idea
   ("predictable corporate events earn a premium"), and share a universe,
   window and cost model. This family's n_trials=12 does not cover the fact
   that it is this project's SECOND attempt at that idea, after the earnings
   family already returned an honest negative. Both DSRs are upper bounds.
 * THEY DID FAIL DIFFERENTLY, which is worth recording. The earnings family
   was negative GROSS on 4 of 8 specs and its best net was -0.231 on a book
   turning over 0.39-0.96 a day. This family is positive gross on 12 of 12
   at a third of the turnover, and dies on cost rather than on signal.

VERDICT -- HONEST NEGATIVE, MECHANISM NOT ESTABLISHED. The dividend month
premium is not tradeable by this project on the point-in-time S&P 500 over
2016-2026 at realistic cost, in any of three short-leg definitions, two
weightings or two holding windows. The precise claim is "nothing that clears
the bar", not "an effect of exactly zero": every spec is positive before
cost, the placebo loses to the live book on all twelve, and the ex-day
run-up and reversal appear in the right directions and relative sizes --
but that last piece cannot be separated from earnings on this data and does
not survive the subset where it can be. What this does NOT claim is that it
refutes [HS13]: their sort is a broad-universe, multi-decade,
factor-adjusted sort over thousands of names, and the paper's own liquidity
evidence says a large-cap-only sample is where the effect should be
smallest.

WHAT A SUCCESSOR NEEDS, in priority order: (1) a dividend DECLARATION-date
feed, without which the earnings confound above cannot be separated and no
mechanism claim is available here at all; (2) the never-payer fix, so
'between' is really [HS12]'s between-companies portfolio; (3) a wider or
less liquid cross-section, where the paper's own evidence says the effect
should be larger. Anything that re-tests this must carry these 12 trials
into its own denominator.

=======================================================================
6. ERRATA -- EVERY CORRECTION MADE AFTER THE FIRST WRITE-UP
=======================================================================
An adversarial independent verification pass on 2026-09-02 re-derived the
forecast table, the event study and five of the twelve backtests from raw
data with its own code. IT FOUND NO LOOK-AHEAD AND EVERY NUMBER REPRODUCED;
the defects were all in the prose and in one arithmetic seam. They are
listed here rather than silently repaired, because a family whose whole
claim is "we did not overstate" has to show its corrections.

TWO CODE FIXES, both re-run (the verdict did not move):
 C1 THE EVENT-STUDY TABLE MIXED TWO POPULATIONS. run_up_bps and
    reversal_bps came from the per-offset curve (15,255 events) while the
    t-statistics and the round trip came from the complete-window subset
    (14,924). Published as +12.02 / -18.35 against a round trip of -5.24 --
    which is -6.33, so the table did not add up, and both errors flattered
    the reversal/run-up ratio (1.53x printed against 1.41x measured). All
    three headline numbers now come from the complete-window population;
    a regression test asserts run-up + reversal == round trip.
 C2 MONTHLY PAYERS WERE NOT EXCLUDED FROM THE 'between' SHORT LEG, though
    the pre-registration freezes that exclusion as a family-wide constant.
    'within' dropped them via its frequency check and 'one_after'
    structurally; 'between' filtered nothing, admitting monthly-classified
    firm-months into ~0.7% of its short slots. Fixed and re-run; no verdict
    changed. ITS EXACT EFFECT CANNOT BE ISOLATED, for the reason in D5: the
    before/after runs differ by vendor float noise as well as by the fix, and
    an earlier draft of this entry attributed the whole ≤0.003 movement to
    the fix, which it could not have known.

SIX WRITE-UP CORRECTIONS, made in place above:
 E1 "the mechanism, in the paper's own words ... inelastic short-run
    supply" -- THAT PHRASE IS NOT IN THE PAPER ("inelastic" 0 hits,
    "supply" 0 hits). Attribution withdrawn; see section 1.
 E2 THE CLAIMED SHARPE SELF-CONTRADICTION IN [HS12] DOES NOT EXIST. The
    intro's 0.194 is annual-frequency and the paper says so; Table II's
    note says its own figures are monthly. Retracted in full, and the
    comparator it had been suppressing is now stated.
 E3 "+54.2bp of run-up BEFORE the ex-day" -- it is "from announcement to
    ex-day" and 49.1% of it IS the ex-day. Strictly before is 27.5bp.
 E4 "THE PLACEBO IS NEGATIVE" -- negative on 9 of 12, positive on the three
    equal-weighted 'toex' specs. The pre-registered test (the live-minus-
    placebo difference) still passes 12/12.
 E5 "Four of six alternatives beat it on precision" -- FIVE of six. A
    miscount of this family's own table, in both documents.
 E6 THE FORMATION WINDOW. The pre-registration twice names 2015-01 and
    quotes a 0.62 benchmark against "~170 long / ~260 short". The run starts
    2016-01-04, so the right benchmark is the 0.54 row -- which is
    INSIGNIFICANT -- and realized legs are 144 / 218-226. The correction
    makes the prior LESS favourable, not more.

THE PRE-REGISTRATION IS LEFT AS COMMITTED. E5 and E6 are errors in that
frozen document, and the honest handling is to record them here rather than
edit the file the whole discipline depends on being unedited.

FOUR DISCLOSURES THAT ARE NOT ERRORS BUT SHOULD BE READ AS LIMITS:
 D1 THE 12 PERSISTED ROWS LIVE IN THIS WORKTREE'S OWN gitignored sqlite,
    not in the main checkout's database where every sibling family's rows
    are. Whoever integrates this must re-run the driver from main, or the
    "carry these 12 trials into your denominator" instruction above will
    point at rows a successor cannot see. The git-durable record is the
    report in data/research_runs/.
 D2 'one_after' IS NOT EXACTLY [HS12]'s THIRD COMPARISON. The paper's is
    "all other companies with a Dividend in Lag1, Lag4, Lag7 and/or Lag10
    Months" -- ACTUAL dividends at FOUR lags; this is a PREDICTED dividend
    at ONE lag. Overlapping sets, not identical.
 D3 22 OF THE 2,662 REPORTED TRADING DAYS CARRY NO BOOK. The last position
    exits 2026-07-31 and the replay runs to the panel end, appending exact
    0.0 for 2026-08-03..2026-09-01. So every 'month' spec's one-sided-day
    count is that dead tail rather than mid-month exhaustion, and
    n_observations overstates traded days by 22. Effect on Sharpe ~0.4%.
 D4 THE PLACEBO SHIFTS THE PROJECTED EX-DAY BY 30 CALENDAR DAYS, which
    breaks the day-of-week preservation that is the whole stated rationale
    for the frozen 91-day constant. "Identical machinery" is therefore
    slightly overstated for the 'toex' half of the placebo.
 D5 THIS RUN IS NOT BIT-REPRODUCIBLE, AND THE THIRD DECIMAL OF EVERY SHARPE
    IN THE REPORT IS NOISE. The dividend calendar is cached, but PRICES are
    re-fetched live on every run, and yfinance returns float32-rounded
    values: two consecutive fetches of the identical 3,437 x 496 panel,
    seconds apart, were measured to differ by up to 0.00048828125 (= 2^-11,
    a float32 rounding artifact) with identical index, columns and NaN
    count. Compounded across 2,662 daily returns that moves annualized
    Sharpes by up to ~0.008 and the best DSR between 0.076 and 0.078 across
    re-runs. IT DOES NOT COME CLOSE TO MATTERING: the bar is 0.95. But a
    reader diffing two runs of this driver will see the last digit move, and
    should know it is vendor float precision rather than a real change. A
    successor wanting reproducibility should cache the price panel the way
    the dividend calendar is already cached.

=======================================================================
7. ERRATA, SECOND PASS -- A SEPARATE INDEPENDENT VERIFICATION, 2026-09-02
=======================================================================
APPENDED, NOT MERGED INTO SECTION 6. Section 6 is the FIRST verification
pass's record; this is a SECOND, separate adversarial pass, by a verifier
that did not write this family. Keeping the two apart is the point: a
reader can see what each pass caught, and that the second found things the
first did not.

WHAT THE SECOND PASS REPRODUCED FROM SCRATCH, so the scope of what follows
is clear. Working from a re-downloaded copy of [HS12] and its own
re-implementation of the book (importing nothing from this module):
 * the EFA 2012 draft was re-fetched from the Internet Archive (55pp,
   SHA-256 c03403cb..9e4e34) and every quotation and figure in sections 1-4
   was re-grepped out of it. All confirmed verbatim: the forecast rule, the
   ex-date convention, the monthly-payer exclusion and its "0.7% of dividend
   observations", the $5 screen, the yield definition, "any fixed loadings
   on risk factors...", "dividend-paying stocks have larger market
   capitalization...", the 26.2/4.5bp yield sensitivities, the 7.0/4.8/11.7bp
   liquidity sensitivities, Table II Panel B's five Sharpes and Table IV
   Panel A in full. E1 AND E2 BOTH RE-VERIFIED: "inelastic" and "supply"
   really do appear ZERO times, and the intro's 0.194 really is followed
   immediately by annual-frequency language ("71 out of 81 years").
 * [HS12]'s three short portfolios re-read from its own Table III note.
   'between' ("All Other Companies") and 'within' ("All Other Companies with
   a Dividend in the Last 12 Months") are the paper's own, as claimed -- and
   D2's admission about 'one_after' is confirmed too: the paper's third
   portfolio is an ACTUAL dividend at Lag1/4/7/10, not a PREDICTED one at
   Lag1.
 * all twelve specs, both weightings, both windows, the placebo, the whole
   cost ladder and every position count, re-derived from the raw calendar
   and a re-fetched price panel. Position counts matched EXACTLY (18,164
   long; 28,402 / 27,505 / 14,956 short; 2,662 days; 80.2% / 54.1% caught)
   and every Sharpe matched to <=0.006, inside the D5 noise band. The cost
   ladder's 12/12, 12/12, 7/12, 1/12, 0/12 reproduced exactly, as did E4's
   correction: the placebo's gross is negative on 9 of 12 and positive on
   exactly the three equal-weighted 'toex' specs.
 * the ex-day event study and the earnings confound, re-implemented
   independently: 15,255 events, 14,924 complete, +12.84 / -18.08 / -5.24bp
   at clustered t +2.12 / -3.27 / -1.20, 92.00% contamination, and the clean
   subset's n=1,194 with run-up -42.51bp at clustered t -0.06. C1's
   arithmetic seam reproduced too: the per-offset curve really does give
   +12.02 / -18.35, which really does sum to -6.33 rather than -5.24.
 * the portfolio-level overlap with earnings_announcement_premium,
   recomputed from both cached calendars: 0.81% same day, 3.98% within 3
   calendar days, 16.89% within 10, median absolute gap 24 days, median
   signed gap -13. Confirmed.
 * D5's float32 claim, re-measured on two fresh consecutive fetches: maximum
   absolute difference exactly 0.00048828125 = 2^-11, identical index,
   columns and NaN count (87,329 both). Confirmed -- and note the
   SPLIT-ADJUSTED panel does not move at all (maximum difference 0.0); only
   the dividend-adjusted total-return frame does.
 * the suite, re-run independently: 3,049 passed, 1 skipped.
NO LOOK-AHEAD WAS FOUND and the honest-negative verdict stands unchanged.
The five entries below are what that pass did find.

 V1 THE YIELD LEG IS NOT PURELY PROPORTIONAL TO YIELD, AND BOTH DOCUMENTS
    SAY IT IS. The pre-registration froze "weight PROPORTIONAL to the paper's
    own dividend-yield measure" and section 3 above repeats it. The weights
    actually ride cross_sectional._resolve_leg_weights, which normalizes the
    basis and then applies MAX_WEIGHT_MULTIPLE -- a 3x-equal-share
    concentration cap, redistributed to convergence. MEASURED, NOT ARGUED:
    the cap BINDS on 91.2% of trading days under the 'month' window and on
    62.8% under 'toex', clamping ~5,200 name-days. It is not a corner case.
    Its effect, measured by re-running the yield specs with the cap removed:
    gross Sharpe moves by up to +0.030 and net-of-5bp by up to +0.049, in the
    direction FAVOURABLE to this family -- and the verdict is unmoved, because
    the best uncapped net-of-5bp spec is still negative (-0.079) and still
    nowhere near the 0.95 DSR bar.
    NOT RE-RUN, deliberately. The cap is a project-wide risk control every
    basis-weighted family here inherits, and removing it AFTER seeing results,
    to numbers that flatter this family, is exactly the move the
    pre-registration exists to prevent. What was wrong was the DESCRIPTION, so
    the description is what is corrected. A test now pins that the cap is in
    the path, so it cannot silently drift in either direction.
 V2 A t-STATISTIC WAS ATTRIBUTED TO THE WRONG TABLE. Section 1's precision
    note gave Table IV Panel A's "declaration to ex-day" cell as 0.534
    (t = 12.31). The alpha is right; the t is Table III Panel A's, for the
    equal-weighted between-companies difference portfolio, which happens to
    share the value 0.534. Table IV's own t is 37.28. Corrected in place in
    section 1, where the full Panel A row is now quoted so the two cannot be
    confused again. Nothing downstream read the number -- the entry exists
    because a paragraph whose subject is citation precision is the last place
    an unchecked figure belongs.
 V3 A COUNT WENT STALE WHEN ERRATA C2 WAS APPLIED. Section 5's design-defect
    paragraph, and the run report's, both still said 'between' and 'within'
    differ by "28,539 against 27,505 short slots -- 3.6% apart". 28,539 is the
    PRE-C2 count; removing monthly payers from the 'between' leg made it
    28,402, i.e. 3.3% apart -- and the same run report's own position-gate
    table already printed 28,402, so the document contradicted itself.
    Corrected in section 5; the report generator now DERIVES both counts from
    the run instead of carrying them as typed literals, so it cannot go stale
    again.
 V4 A CODE COMMENT KEPT THE PRE-CORRECTION NUMBERS. The header comment over
    measure_earnings_confound still read "74.3% of the ex-day event windows
    contain a real 8-K Item 2.02 earnings announcement, 42.5% of them inside
    the run-up half" and quoted "+12.0bp run-up and -18.4bp reversal". The
    contamination figure is 92.0% -- 74.3% was never re-measured after the
    diagnostic was finished and no run of this code produces it -- and
    +12.0/-18.4 are the pre-C1 curve figures. The docstring and the report
    were both right; only the comment was left behind. Corrected in place.
 V5 THREE BEHAVIOURS WERE UNPINNED, ONE OF THEM A POINT-IN-TIME GUARANTEE.
    Mutation testing (24 mutations against this family's own suite) found 21
    caught and 3 survivors, each now pinned by a test shown to fail before the
    behaviour was restored:
      * build_dmp_positions' min-history gate reads history.before(month).
        Changing it to before(month + 1) -- which counts an ex-date inside the
        very month being traded, unknowable at a formation on the last day of
        month t-1 -- passed the ENTIRE suite. This family's central claim is
        its point-in-time discipline, and this specific gate was asserting
        nothing about it.
      * net_daily_returns' bps conversion. Halving it (dividing by 20_000)
        passed: the suite pinned that zero cost is a no-op and that more cost
        is never better, and a halved rate satisfies both. This family's
        verdict is "positive gross, killed by cost", which makes the absolute
        rate the load-bearing number in the whole result.
      * DMP_MIN_PRICE's VALUE. The existing screen test places its fixture at
        DMP_MIN_PRICE - 0.01, so it tracks the constant and passes at any
        level, including 0.0. The $5 screen is [HS12]'s own and the
        pre-registration freezes it, so its value is part of the frozen spec.
    All 24 mutations are now caught.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from app.services.research_lab.cross_sectional import (
    DEFAULT_IMPUTED_DELISTING_RETURN,
    DEFAULT_XS_COST_BPS,
    FINANCING_DAYS_PER_YEAR,
    MIN_REPLAY_TRADING_DAYS,
    _compute_delisting_positions,
    _leg_weighted_return,
    _resolve_leg_weights,
)
from app.services.research_lab.cross_sectional_earnings_premium import (
    build_membership_frame,
)
from app.services.research_lab.deflated_sharpe import (
    DeflatedSharpeResult,
    compute_deflated_sharpe,
)
from app.services.research_lab.global_effective_n import dsr_n_trials
from app.services.research_lab.metrics import sharpe_ratio
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    get_universe_over,
    membership_coverage_end,
)

logger = logging.getLogger(__name__)

DMP_FAMILY_NAME = "dividend_month_premium"

# Default on-disk cache for the fetched dividend calendar, following the
# data/ convention the EAP announcement calendar and the futures/insider
# caches use. Gitignored as a refetchable VENDOR INPUT, not a result --
# the results live in cross_sectional_trial_results and data/research_runs/.
# Rebuilt from scratch by data/research_runs/fetch_dividend_calendar.py.
DIVIDEND_CACHE_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "dividend_month_ex_date_calendar.json"
)

DMP_CITATION = (
    "Hartzmark & Solomon, 'The dividend month premium' (Journal of Financial Economics 109(3), "
    "2013, pp. 640-660, doi:10.1016/j.jfineco.2013.02.015); methodology and every quotation "
    "taken from the EFA 2012 conference draft of the same paper, whose full text was retrieved "
    "and re-grepped locally -- the published JFE body is paywalled and was NOT retrieved. "
    "Corroborating sources read in full: Hartzmark & Solomon 'The Dividend Disconnect' (2017 "
    "draft of JF 74(5), 2019), 'Predictable Price Pressure' (2021), their own Annual Review of "
    "Financial Economics 10 (2018) update, Ainsworth & Nicholson's 11-country test (1993-2013), "
    "and Chen & Zimmermann's open-source 'DivSeason' return series"
)


# ===========================================================================
# THE DIVIDEND CALENDAR
# ===========================================================================


@dataclass(frozen=True)
class DividendEvent:
    """One cash distribution, dated by its EX-DIVIDEND date.

    `amount` is SPLIT-ADJUSTED, on the same basis as Yahoo's
    split-adjusted-but-not-dividend-adjusted Close -- see
    YFinanceProvider.get_dividend_history. It is only ever divided by that
    same Close (see trailing_dividend_yield), never by the total-return
    close every realized return in this module is computed from."""

    ticker: str
    ex_date: date
    amount: float


@dataclass
class DividendCalendarReport:
    """What the yfinance corporate-actions pass actually covered. Every
    field is a sample-construction fact that belongs in the run report: a
    ticker with no dividend history contributes no prediction, and silence
    is exactly what has to be counted."""

    n_tickers_requested: int = 0
    n_tickers_priced: int = 0
    n_tickers_with_dividends: int = 0
    n_ex_dates: int = 0
    fetch_start: date | None = None
    fetch_end: date | None = None
    missing_price_data: list[str] = field(default_factory=list)


def load_dividend_cache(
    path: Path = DIVIDEND_CACHE_PATH,
) -> tuple[list[DividendEvent], DividendCalendarReport] | None:
    """The cached ex-dividend calendar, or None if it has never been built.

    Deliberately a plain load with no fallback to a live fetch: a screening
    run must replay a FIXED input, and silently re-fetching from an
    unofficial scraping API mid-run would mean two runs of the same script
    could disagree with no record of why."""
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    events: list[DividendEvent] = []
    for ticker, rows in payload["dividends"].items():
        for iso, amount in rows:
            events.append(
                DividendEvent(ticker=ticker, ex_date=date.fromisoformat(iso), amount=float(amount))
            )
    events.sort(key=lambda e: (e.ticker, e.ex_date))
    report = DividendCalendarReport(
        n_tickers_requested=int(payload.get("n_tickers_requested", 0)),
        n_tickers_priced=int(payload.get("n_tickers_priced", 0)),
        n_tickers_with_dividends=int(payload.get("n_tickers_with_dividends", 0)),
        n_ex_dates=len(events),
        fetch_start=date.fromisoformat(payload["fetch_start"]),
        fetch_end=date.fromisoformat(payload["fetch_end"]),
        missing_price_data=list(payload.get("missing_price_data", [])),
    )
    return events, report


def month_index(day: date) -> int:
    """Months since year 0, so that month arithmetic ("three months before
    t") is plain integer arithmetic and cannot go wrong at a year boundary
    -- which is exactly where a hand-rolled (year, month) decrement does go
    wrong. [HS12]'s rule is stated entirely in month offsets, so this is the
    natural unit for the whole forecast."""
    return day.year * 12 + (day.month - 1)


def month_start(index: int) -> date:
    return date(index // 12, index % 12 + 1, 1)


def build_ex_date_calendar(
    events: list[DividendEvent],
) -> dict[str, dict[int, list[DividendEvent]]]:
    """{ticker: {month_index: [ex-dividend events that month, ascending]}}.

    A month with two ex-dates for one ticker is kept as two entries rather
    than collapsed: it is a real thing (a special alongside a regular, or a
    genuine schedule change), the frequency classifier counts MONTHS not
    events so it is unaffected, and the ex-day projection takes the LAST one
    in the source month, which is the conservative (never-early) direction."""
    calendar: dict[str, dict[int, list[DividendEvent]]] = {}
    for event in events:
        calendar.setdefault(event.ticker, {}).setdefault(month_index(event.ex_date), []).append(
            event
        )
    for months in calendar.values():
        for rows in months.values():
            rows.sort(key=lambda e: e.ex_date)
    return calendar


# --- [HS12]'s forecast rule --------------------------------------------------

# A firm with at least this many ex-date MONTHS in the trailing twelve is a
# monthly payer and is EXCLUDED outright. [HS12]'s own exclusion: "we exclude
# companies that paid a monthly dividend in the previous 12 months unless
# otherwise noted (0.7% of dividend observations)". 10 rather than 12 because
# a genuine monthly payer can miss a month at the edges of the window without
# ceasing to be one, and because the classifier reads MONTHS not payments.
DMP_MONTHLY_MONTHS_THRESHOLD = 10

# The month offsets [HS12] forecasts from, per declared frequency. Quoted
# rule: quarterly at t-3/t-6/t-9/t-12, semi-annual at t-6/t-12, annual at
# t-12. "Unknown frequency" is treated as quarterly, exactly as the paper
# does ("third digits 0 and 1 ... as being equivalent to a quarterly
# dividend") -- here that case is subsumed by the inferred classifier, which
# has no unknown category.
DMP_FORECAST_LAGS: dict[str, tuple[int, ...]] = {
    "quarterly": (3, 6, 9, 12),
    "semiannual": (6, 12),
    "annual": (12,),
}

# A firm needs at least this many of its OWN past ex-dates before any
# prediction about it is traded, and before it can enter any short-leg pool.
# One year of a quarterly calendar. Applied UNIFORMLY to all twelve specs --
# including the equal-weighted ones, which do not need a yield basis -- so
# every spec trades the IDENTICAL population and differs only in short leg,
# weighting and window. Without that uniformity the sigma_SR feeding the DSR
# would measure universe differences rather than spec differences. Asserted
# by a test.
DMP_MIN_PRIOR_EX_DATES = 4

# [HS12]'s own price screen, quoted: "we also exclude shares with prices less
# than $5 in the previous month". Applied at the formation close. On an S&P
# 500 universe it should almost never bind; how often it actually binds is
# MEASURED and reported rather than assumed.
DMP_MIN_PRICE = 5.0

# Calendar days per 3 months of forecast lag when projecting the predicted
# EX-DAY. 91 = 13 weeks exactly, so 91/182/273/364 are all multiples of 7 and
# all PRESERVE DAY OF WEEK. Measured on dates alone before the grid was
# frozen: the 91-day projection lands on the exact ex-day 46.3% of the time
# against 7.1% for calendar-month arithmetic, median absolute error 1 day.
# Same day-of-week effect this project already measured for scheduled
# earnings filings.
DMP_EX_DAY_QUARTER_DAYS = 91


def classify_dividend_frequency(
    calendar: dict[int, list[DividendEvent]], month: int
) -> str:
    """[HS12]'s declared-frequency field, INFERRED. Returns one of
    "monthly" | "quarterly" | "semiannual" | "annual" | "none", from the
    count of ex-date MONTHS in months month-12 .. month-1.

    THIS IS DEVIATION 2 OF THE MODULE DOCSTRING and the approximation is
    real: [HS12] reads CRSP's distribution code, which states the frequency
    the company itself declared. This project has no CRSP, so frequency is
    inferred from observed spacing, and a firm that changed cadence inside
    the trailing year is classified by what it did rather than by what it
    said it would do.

    Strictly point-in-time: the window is closed at month-1, so a
    classification for month t never reads an ex-date in month t or later.

    The 3..6 band maps to quarterly rather than 4 exactly, because a real
    quarterly payer's ex-dates drift across month boundaries (KO's fourth
    quarter has landed in both November and December inside this sample), so
    a trailing twelve months genuinely contains three or five ex-months for
    a quarterly payer more often than one would like."""
    n_months = sum(1 for k in range(month - 12, month) if k in calendar)
    if n_months >= DMP_MONTHLY_MONTHS_THRESHOLD:
        return "monthly"
    if n_months >= 3:
        return "quarterly"
    if n_months == 2:
        return "semiannual"
    if n_months == 1:
        return "annual"
    return "none"


def qualifying_source_lags(
    calendar: dict[int, list[DividendEvent]], month: int
) -> tuple[str, tuple[int, ...]]:
    """(frequency, the month offsets at which this firm actually has a past
    ex-date) under [HS12]'s rule. An empty tuple means "not predicted".

    Monthly payers return no lags because they are excluded outright, and
    non-payers return none because the rule has no branch for them."""
    frequency = classify_dividend_frequency(calendar, month)
    lags = DMP_FORECAST_LAGS.get(frequency, ())
    return frequency, tuple(lag for lag in lags if (month - lag) in calendar)


@dataclass(frozen=True)
class PredictedDividendMonth:
    """One EX-ANTE prediction: `ticker` is expected to go ex-dividend
    somewhere in calendar month `month`, on the strength of its own ex-date
    `source_lag` months earlier.

    `predicted_ex_date` is that source ex-date projected forward by whole
    weeks (DMP_EX_DAY_QUARTER_DAYS per quarter of lag). It is used ONLY by
    the 'toex' window; the 'month' window needs nothing but `month` itself.
    `outside_month` records that the projection landed outside `month`, in
    which case the 'toex' window degrades to the 'month' window for this
    name -- counted, never silently dropped."""

    ticker: str
    month: int
    frequency: str
    source_lag: int
    source_ex_date: date
    predicted_ex_date: date
    outside_month: bool
    # Mean amount per paying month over the trailing 12 months -- the
    # numerator of [HS12]'s own yield measure. The denominator is a price at
    # formation, which this object cannot know, so the division happens in
    # build_dmp_positions.
    trailing_mean_amount: float
    n_prior_ex_dates: int


def _trailing_mean_amount(
    calendar: dict[int, list[DividendEvent]], month: int
) -> float:
    """[HS12]'s yield numerator, quoted: "the average from the previous 12
    months of dividends payment (in months that included a dividend)". The
    average is over PAYING MONTHS, not over all twelve -- a quarterly payer
    and a monthly payer of the same annual total do not get the same
    numerator, which is the paper's own convention and is why this is not
    simply the trailing sum over 12."""
    totals = [
        sum(e.amount for e in calendar[k])
        for k in range(month - 12, month)
        if k in calendar
    ]
    return float(np.mean(totals)) if totals else float("nan")


def predict_dividend_months(
    calendar: dict[str, dict[int, list[DividendEvent]]],
    first_month: int,
    last_month: int,
) -> dict[str, dict[int, PredictedDividendMonth]]:
    """{ticker: {month: prediction}} over [first_month, last_month] under
    [HS12]'s rule.

    Point-in-time by construction: the shortest forecast lag is three
    months, so every input is an ex-date at least three months old at the
    formation it justifies. Nothing here can read a distribution that had
    not yet happened, and build_dmp_positions asserts it anyway.

    When several lags qualify (the common case for a quarterly payer), the
    MOST RECENT is used as the projection source -- it is the closest in
    time and therefore the least likely to have been overtaken by a
    schedule change."""
    prior_counts = build_prior_ex_date_counts(calendar)
    out: dict[str, dict[int, PredictedDividendMonth]] = {}
    for ticker, months in calendar.items():
        rows: dict[int, PredictedDividendMonth] = {}
        history = prior_counts[ticker]
        for month in range(first_month, last_month + 1):
            frequency, lags = qualifying_source_lags(months, month)
            if not lags:
                continue
            lag = min(lags)
            source = months[month - lag][-1]
            projected = source.ex_date + timedelta(
                days=DMP_EX_DAY_QUARTER_DAYS * lag // 3
            )
            n_prior = history.before(month)
            rows[month] = PredictedDividendMonth(
                ticker=ticker,
                month=month,
                frequency=frequency,
                source_lag=lag,
                source_ex_date=source.ex_date,
                predicted_ex_date=projected,
                outside_month=month_index(projected) != month,
                trailing_mean_amount=_trailing_mean_amount(months, month),
                n_prior_ex_dates=n_prior,
            )
        if rows:
            out[ticker] = rows
    return out


# --- forecast accuracy, measured on DATES ONLY -------------------------------


@dataclass
class ForecastAccuracy:
    """How well a candidate rule locates real ex-date MONTHS. A DATA-QUALITY
    measurement containing no return of any kind -- see the pre-registration
    for why running it before the grid was frozen is not a p-hacking
    route."""

    rule: str
    n_predicted: int
    n_true_positive: int
    n_false_positive: int
    n_false_negative: int
    precision: float
    recall: float


# The alternatives measured against [HS12]'s rule, reported so the choice is
# checkable. NONE of these is ever traded: the adopted rule is the paper's,
# and it is NOT the best scorer here (see the module docstring section 3).
DMP_ALTERNATIVE_RULES: tuple[str, ...] = (
    "hs13",
    "t12",
    "t12_and_t24",
    "t12_or_t24",
    "t3",
    "t3_and_t12",
    "t12_plus_minus_1",
)


def _rule_predicts(
    rule: str, months: dict[int, list[DividendEvent]], month: int
) -> bool:
    if rule == "hs13":
        return bool(qualifying_source_lags(months, month)[1])
    if rule == "t12":
        return (month - 12) in months
    if rule == "t12_and_t24":
        return (month - 12) in months and (month - 24) in months
    if rule == "t12_or_t24":
        return (month - 12) in months or (month - 24) in months
    if rule == "t3":
        return (month - 3) in months
    if rule == "t3_and_t12":
        return (month - 3) in months and (month - 12) in months
    if rule == "t12_plus_minus_1":
        return any((month - 12 + k) in months for k in (-1, 0, 1))
    raise ValueError(f"unknown forecast rule {rule!r}")


def measure_forecast_accuracy(
    calendar: dict[str, dict[int, list[DividendEvent]]],
    first_month: int,
    last_month: int,
    rule: str,
) -> ForecastAccuracy:
    """Precision and recall of `rule` against "the firm really had an
    ex-date that month", over every ticker-month in the window. Dates only:
    no price, no position, no return is read anywhere in this function."""
    tp = fp = fn = 0
    for months in calendar.values():
        for month in range(first_month, last_month + 1):
            actual = month in months
            predicted = _rule_predicts(rule, months, month)
            if predicted and actual:
                tp += 1
            elif predicted:
                fp += 1
            elif actual:
                fn += 1
    return ForecastAccuracy(
        rule=rule,
        n_predicted=tp + fp,
        n_true_positive=tp,
        n_false_positive=fp,
        n_false_negative=fn,
        precision=tp / (tp + fp) if tp + fp else float("nan"),
        recall=tp / (tp + fn) if tp + fn else float("nan"),
    )


# ===========================================================================
# THE TRADED BOOK
# ===========================================================================


@dataclass(frozen=True)
class DmpSpec:
    """One pre-declared definition. Deliberately NOT a
    cross_sectional.CrossSectionalSpec, for the same reason
    cross_sectional_earnings_premium.EapSpec is not: that type's required
    fields (signal_fn, lookback_days, rank_fraction) describe a periodic
    universe scan ranked on a signal, and this family ranks nothing -- it
    selects on a CALENDAR."""

    pattern_id: str
    family: str
    citation: str
    short_leg: str  # "between" | "within" | "one_after"
    leg_weighting: str  # "equal" | "yield"
    window: str  # "month" | "toex"


@dataclass
class DmpConfig:
    """Market conventions, split from the specs exactly as
    CrossSectionalConfig / EapConfig split them."""

    # One-way cost in bps charged on L1 turnover of the NET book. 5.0 =
    # cross_sectional.DEFAULT_XS_COST_BPS, this project's conservative
    # equity control rate; the pre-declared sensitivity ladder carries the
    # sourced realistic levels.
    cost_bps: float = DEFAULT_XS_COST_BPS
    # 0.0 = the equity families' shared, DISCLOSED optimism (no observable
    # borrow feed; a known OPEN paid-data item for this project).
    financing_bps_per_year: float = 0.0
    impute_delisting_returns: bool = True
    imputed_delisting_return: float = DEFAULT_IMPUTED_DELISTING_RETURN
    min_price: float = DMP_MIN_PRICE


@dataclass(frozen=True)
class DmpPosition:
    """One firm-month turned into a position: on at the close of
    entry_position, off at the close of exit_position. Both rows are fixed
    the moment the month's book is formed, and NEITHER depends on the
    dividend actually being declared, or on anything about it -- that is the
    whole point of this family.

    `weight_basis` is the formation-date dividend yield for a long position
    and NaN for a short one (the short leg is always equal-weighted).
    `caught_actual` is a hindsight DIAGNOSTIC, never a filter."""

    ticker: str
    month: int
    side: str  # "long" | "short"
    entry_position: int
    exit_position: int
    weight_basis: float
    caught_actual: bool


@dataclass
class PositionCounts:
    n_predictions: int = 0
    n_outside_formation: int = 0
    n_not_member: int = 0
    n_no_price: int = 0
    n_below_price_screen: int = 0
    n_thin_history: int = 0
    n_no_yield_basis: int = 0
    n_ex_day_outside_month: int = 0
    n_long: int = 0
    n_short: int = 0
    n_long_caught_actual: int = 0


def month_end_rows(index: pd.DatetimeIndex) -> list[tuple[int, int]]:
    """[(month_index, position of the LAST trading row in that month)],
    ascending. These are the formation rows: the book for month t is decided
    at the close of the last trading day of month t-1, so consecutive
    entries of this list are a formation and its own exit.

    The final month is included even though it is usually incomplete -- it
    is a real formation row for the month before it, and build_dmp_positions
    refuses any position whose exit would run past the end of the index
    anyway."""
    months = pd.Series(
        [month_index(ts.date()) for ts in index], index=range(len(index))
    )
    out: list[tuple[int, int]] = []
    for month, group in months.groupby(months):
        out.append((int(month), int(group.index[-1])))
    out.sort()
    return out


@dataclass(frozen=True)
class PriorExDateCounts:
    """Prefix sums of one firm's ex-date count by month, so that "how many
    ex-dates did this firm have STRICTLY BEFORE month m" is an O(1) lookup.

    Built once per screening pass rather than inside the formation loop:
    without it build_dmp_positions is O(tickers x formations x months) and
    it is called 24 times per pass (12 specs, then 12 placebos), which is
    the difference between seconds and many minutes. The behaviour is
    identical to the naive sum -- a test pins the two against each other."""

    first_month: int
    last_month: int
    total: int
    # counts[m - first_month] = number of ex-dates strictly before month m,
    # defined over first_month .. last_month + 1 inclusive.
    counts: tuple[int, ...]

    def before(self, month: int) -> int:
        if month <= self.first_month:
            return 0
        if month > self.last_month:
            return self.total
        return self.counts[month - self.first_month]


def build_prior_ex_date_counts(
    calendar: dict[str, dict[int, list[DividendEvent]]],
) -> dict[str, PriorExDateCounts]:
    """{ticker: PriorExDateCounts}. Pure precomputation; reads no price and
    no return."""
    out: dict[str, PriorExDateCounts] = {}
    for ticker, months_map in calendar.items():
        if not months_map:
            continue
        first, last = min(months_map), max(months_map)
        running = 0
        counts: list[int] = []
        for month in range(first, last + 2):
            counts.append(running)
            running += len(months_map.get(month, ()))
        out[ticker] = PriorExDateCounts(
            first_month=first, last_month=last, total=running, counts=tuple(counts)
        )
    return out


def _first_row_at_or_after(index: pd.DatetimeIndex, target: date) -> int | None:
    position = int(
        np.searchsorted(index.values, pd.Timestamp(target).to_datetime64(), side="left")
    )
    return None if position >= len(index) else position


def build_dmp_positions(
    close: pd.DataFrame,
    price_only_close: pd.DataFrame,
    calendar: dict[str, dict[int, list[DividendEvent]]],
    predicted: dict[str, dict[int, PredictedDividendMonth]],
    membership: pd.DataFrame,
    formation_start: date,
    formation_end: date,
    spec: DmpSpec,
    config: DmpConfig,
) -> tuple[list[DmpPosition], PositionCounts]:
    """Every firm-month that clears the ex-ante gates, as a dated position.

    THE GATES, in order, each counted and none of them a performance filter:
      * the formation close must sit inside the formation window;
      * the firm must be a point-in-time index member at the formation
        close;
      * it must have a usable total-return price AND a usable split-adjusted
        price at that close;
      * that split-adjusted price must clear [HS12]'s own $5 screen;
      * it must have at least DMP_MIN_PRIOR_EX_DATES of its own past
        ex-dates -- applied to BOTH legs and to every spec, so all twelve
        trade the identical population;
      * a LONG position additionally needs a finite, positive yield basis
        (applied under equal weighting too, for that same uniformity).

    LONG positions run from the formation close to the spec's window end.
    SHORT positions always run the full month, whatever the window axis
    says: the short leg is a comparison pool, not a ranked leg."""
    counts = PositionCounts()
    index = close.index
    n = len(index)
    rows = month_end_rows(index)
    positions: list[DmpPosition] = []

    tr_array = close.to_numpy(dtype=float)
    px_array = price_only_close.reindex(
        index=close.index, columns=close.columns
    ).to_numpy(dtype=float)
    columns = list(close.columns)
    column_of = {t: i for i, t in enumerate(columns)}
    membership_array = membership.reindex(
        index=close.index, columns=columns
    ).fillna(False).to_numpy(dtype=bool)

    # PRECOMPUTED ONCE, not per formation. The min-prior-ex-dates gate needs
    # "how many ex-dates did this firm have strictly before month m", which
    # is a prefix sum over its own calendar. Recomputing it inside the
    # ticker loop makes this function O(tickers x formations x months) and
    # it is called 24 times per screening pass (12 specs, then 12 placebos),
    # which is the difference between seconds and many minutes.
    prior_counts = build_prior_ex_date_counts(calendar)

    for (_, formation_row), (month, month_end_row) in zip(rows, rows[1:]):
        formation_day = index[formation_row].date()
        if formation_day < formation_start or formation_day > formation_end:
            counts.n_outside_formation += 1
            continue
        if month_end_row >= n:
            continue

        long_tickers: set[str] = set()
        eligible: list[str] = []
        for ticker in columns:
            col = column_of[ticker]
            if not membership_array[formation_row, col]:
                counts.n_not_member += 1
                continue
            price = tr_array[formation_row, col]
            raw_price = px_array[formation_row, col]
            if not (np.isfinite(price) and np.isfinite(raw_price)):
                counts.n_no_price += 1
                continue
            if raw_price < config.min_price:
                counts.n_below_price_screen += 1
                continue
            history = prior_counts.get(ticker)
            if history is None:
                continue
            if history.before(month) < DMP_MIN_PRIOR_EX_DATES:
                counts.n_thin_history += 1
                continue
            eligible.append(ticker)

        for ticker in eligible:
            prediction = predicted.get(ticker, {}).get(month)
            if prediction is None:
                continue
            counts.n_predictions += 1
            raw_price = px_array[formation_row, column_of[ticker]]
            yield_basis = prediction.trailing_mean_amount / raw_price
            if not np.isfinite(yield_basis) or yield_basis <= 0.0:
                counts.n_no_yield_basis += 1
                continue

            assert prediction.source_ex_date <= formation_day, (
                f"{ticker} {month}: the prediction's source ex-date "
                f"{prediction.source_ex_date} is AFTER its own formation date "
                f"{formation_day}. This family's point-in-time guarantee is that the shortest "
                "forecast lag is three months, so this is impossible unless the forecast rule "
                "was changed."
            )

            exit_row = month_end_row
            if spec.window == "toex":
                if prediction.outside_month:
                    counts.n_ex_day_outside_month += 1
                else:
                    projected = _first_row_at_or_after(index, prediction.predicted_ex_date)
                    if projected is not None:
                        exit_row = min(max(projected, formation_row + 1), month_end_row)

            actual = calendar.get(ticker, {}).get(month, [])
            caught = any(
                formation_row < (_first_row_at_or_after(index, e.ex_date) or n) <= exit_row
                for e in actual
            )
            long_tickers.add(ticker)
            counts.n_long += 1
            counts.n_long_caught_actual += int(caught)
            positions.append(
                DmpPosition(
                    ticker=ticker,
                    month=month,
                    side="long",
                    entry_position=formation_row,
                    exit_position=exit_row,
                    weight_basis=float(yield_basis),
                    caught_actual=caught,
                )
            )

        for ticker in eligible:
            if ticker in long_tickers:
                continue
            months = calendar.get(ticker, {})
            # MONTHLY PAYERS ARE EXCLUDED FROM EVERY SHORT LEG, not just the
            # two that happened to drop them structurally. The
            # pre-registration freezes "monthly payers EXCLUDED -- [HS12]'s
            # own exclusion" as a family-wide constant; an earlier revision
            # applied it to 'within' (via the frequency check below) and to
            # 'one_after' (which needs a prediction, and monthly payers never
            # get one) but NOT to 'between', which filtered nothing. That was
            # a divergence from a frozen constant rather than a design
            # choice, and it is fixed here rather than disclosed and left.
            if classify_dividend_frequency(months, month) == "monthly":
                continue
            if spec.short_leg == "within":
                if classify_dividend_frequency(months, month) not in DMP_FORECAST_LAGS:
                    continue
            elif spec.short_leg == "one_after":
                if month - 1 not in predicted.get(ticker, {}):
                    continue
            counts.n_short += 1
            positions.append(
                DmpPosition(
                    ticker=ticker,
                    month=month,
                    side="short",
                    entry_position=formation_row,
                    exit_position=month_end_row,
                    weight_basis=float("nan"),
                    caught_actual=False,
                )
            )

    positions.sort(key=lambda p: (p.entry_position, p.side, p.ticker))
    return positions, counts


@dataclass
class DmpBacktestResult:
    """One spec's replay. GROSS returns and TURNOVER are stored separately
    from any net series so that the whole pre-declared cost ladder is
    derived from ONE position path rather than from re-running the book at
    each cost level -- the positions are identical by construction, and
    re-running them would invite a silent divergence between the sensitivity
    table and the headline."""

    status: str  # "ok" | "no_positions" | "insufficient_history"
    gross_daily_returns: pd.Series
    daily_turnover: pd.Series
    daily_gross_notional: pd.Series
    n_long_positions: int = 0
    n_short_positions: int = 0
    n_delisted_mid_hold: int = 0
    n_invested_days: int = 0
    n_one_sided_days: int = 0
    n_weight_fallback_days: int = 0
    mean_long_leg_size: float = 0.0
    min_long_leg_size: int = 0
    max_long_leg_size: int = 0
    mean_short_leg_size: float = 0.0


def _turnover_l1(old: dict[str, float], new: dict[str, float]) -> float:
    """L1 distance between two net-weight books -- cross_sectional._turnover's
    own definition, restated here because that function is keyed to the
    harness's formation loop rather than to a daily one. Same restatement,
    for the same reason, as the earnings-premium family makes."""
    tickers = set(old) | set(new)
    return float(sum(abs(new.get(t, 0.0) - old.get(t, 0.0)) for t in tickers))


def net_daily_returns(
    replay: DmpBacktestResult, cost_bps: float, financing_bps_per_year: float
) -> pd.Series:
    """gross - turnover*cost - financing, on the stored position path. The
    single place cost is applied, so the headline and every sensitivity
    column are guaranteed to describe the same book."""
    gross = replay.gross_daily_returns
    if gross.empty:
        return gross
    cost = replay.daily_turnover * (cost_bps / 10_000.0)
    financing = pd.Series(0.0, index=gross.index)
    if financing_bps_per_year:
        per_day = (financing_bps_per_year / 10_000.0) / FINANCING_DAYS_PER_YEAR
        calendar_days = pd.Series(
            gross.index.to_series().diff().dt.days.fillna(1.0).to_numpy(),
            index=gross.index,
        )
        financing = replay.daily_gross_notional * per_day * calendar_days
    return gross - cost - financing


def run_dmp_backtest(
    close: pd.DataFrame,
    positions: list[DmpPosition],
    spec: DmpSpec,
    config: DmpConfig,
) -> DmpBacktestResult:
    """The daily replay. Each position is on from the close of its
    entry_position through the close of its exit_position; the long leg is
    1.0 of notional and the short leg is 1.0 of notional, so the book is
    dollar-neutral by construction.

    A day on which either leg is empty is 0.0 BY DESIGN and counted
    (n_one_sided_days), never traded as a naked single leg -- the same
    convention cross_sectional_pead and the earnings-premium family state.
    That case is not hypothetical here: under the 'toex' window every long
    position closes on or before its predicted ex-day, so the tail of a
    month can genuinely have no long leg left."""
    if not positions:
        empty = pd.Series(dtype=float)
        return DmpBacktestResult(
            status="no_positions",
            gross_daily_returns=empty,
            daily_turnover=empty,
            daily_gross_notional=empty,
        )

    index = close.index
    n = len(index)
    first_entry = min(p.entry_position for p in positions)
    if first_entry >= n - 1:
        empty = pd.Series(dtype=float)
        return DmpBacktestResult(
            status="insufficient_history",
            gross_daily_returns=empty,
            daily_turnover=empty,
            daily_gross_notional=empty,
        )

    returns = close.pct_change(fill_method=None)
    columns = list(close.columns)
    column_of = {t: i for i, t in enumerate(columns)}
    returns_array = returns.to_numpy(dtype=float)

    delisting_by_position: dict[int, list[str]] = {}
    if config.impute_delisting_returns:
        for ticker, position in _compute_delisting_positions(close).items():
            delisting_by_position.setdefault(position, []).append(ticker)

    open_at: dict[int, list[DmpPosition]] = {}
    for position in positions:
        open_at.setdefault(position.entry_position, []).append(position)

    active_long: dict[str, DmpPosition] = {}
    active_short: dict[str, DmpPosition] = {}
    previous_weights: dict[str, float] = {}

    dates: list[pd.Timestamp] = []
    gross_values: list[float] = []
    turnovers: list[float] = []
    notionals: list[float] = []
    n_invested = 0
    n_one_sided = 0
    n_fallback = 0
    n_delisted = 0
    long_sizes: list[int] = []
    short_sizes: list[int] = []

    for j in range(first_entry + 1, n):
        for position in open_at.get(j - 1, ()):
            if position.side == "long":
                active_long[position.ticker] = position
            else:
                active_short[position.ticker] = position

        day_returns = returns_array[j].copy()
        delisting_today = delisting_by_position.get(j)
        if delisting_today:
            for ticker in delisting_today:
                day_returns[column_of[ticker]] = config.imputed_delisting_return
                if ticker in active_long or ticker in active_short:
                    n_delisted += 1

        finite = np.isfinite(day_returns)
        long_tickers = sorted(t for t in active_long if finite[column_of[t]])
        long_set = set(long_tickers)
        short_tickers = sorted(
            t for t in active_short if finite[column_of[t]] and t not in long_set
        )
        day_series = pd.Series(day_returns, index=columns)

        if not long_tickers or not short_tickers:
            n_one_sided += 1
            dates.append(index[j])
            gross_values.append(0.0)
            # A flat book trades nothing, so it also pays nothing; the
            # turnover of unwinding into flat is charged here, on the day it
            # happens, via the weight diff against an empty book.
            turnovers.append(_turnover_l1(previous_weights, {}))
            notionals.append(0.0)
            previous_weights = {}
        else:
            long_signal = pd.Series(0.0, index=long_tickers, dtype=float)
            basis = None
            if spec.leg_weighting == "yield":
                basis = pd.Series(
                    {t: active_long[t].weight_basis for t in long_tickers}, dtype=float
                )
            long_weights, long_fallback = _resolve_leg_weights(
                long_tickers,
                long_signal,
                higher_is_stronger=True,
                leg_weighting="equal" if spec.leg_weighting == "equal" else "inverse_vol",
                market_cap=None,
                weight_basis=basis,
            )
            short_weights, _ = _resolve_leg_weights(
                short_tickers,
                pd.Series(0.0, index=short_tickers, dtype=float),
                higher_is_stronger=True,
                leg_weighting="equal",
                market_cap=None,
                weight_basis=None,
            )
            if long_fallback:
                n_fallback += 1

            gross = _leg_weighted_return(day_series, long_weights) - _leg_weighted_return(
                day_series, short_weights
            )
            net_weights: dict[str, float] = dict(long_weights)
            for ticker, weight in short_weights.items():
                net_weights[ticker] = net_weights.get(ticker, 0.0) - weight

            n_invested += 1
            long_sizes.append(len(long_tickers))
            short_sizes.append(len(short_tickers))
            dates.append(index[j])
            gross_values.append(gross)
            turnovers.append(_turnover_l1(previous_weights, net_weights))
            notionals.append(2.0)
            previous_weights = net_weights

        for ticker in list(active_long):
            if j >= active_long[ticker].exit_position or (
                delisting_today and ticker in delisting_today
            ):
                del active_long[ticker]
        for ticker in list(active_short):
            if j >= active_short[ticker].exit_position or (
                delisting_today and ticker in delisting_today
            ):
                del active_short[ticker]

    date_index = pd.DatetimeIndex(dates)
    return DmpBacktestResult(
        status="ok",
        gross_daily_returns=pd.Series(gross_values, index=date_index, dtype=float),
        daily_turnover=pd.Series(turnovers, index=date_index, dtype=float),
        daily_gross_notional=pd.Series(notionals, index=date_index, dtype=float),
        n_long_positions=sum(1 for p in positions if p.side == "long"),
        n_short_positions=sum(1 for p in positions if p.side == "short"),
        n_delisted_mid_hold=n_delisted,
        n_invested_days=n_invested,
        n_one_sided_days=n_one_sided,
        n_weight_fallback_days=n_fallback,
        mean_long_leg_size=float(np.mean(long_sizes)) if long_sizes else 0.0,
        min_long_leg_size=int(np.min(long_sizes)) if long_sizes else 0,
        max_long_leg_size=int(np.max(long_sizes)) if long_sizes else 0,
        mean_short_leg_size=float(np.mean(short_sizes)) if short_sizes else 0.0,
    )


# ===========================================================================
# THE PRE-DECLARED FAMILY
# ===========================================================================
#
# Levels are fixed in data/research_runs/dividend_month_premium_
# PREREGISTRATION.txt and asserted against the built list below, so a size
# drift is a loud import-time failure rather than a silent change to every
# future run's DSR denominator.

# [HS12]'s OWN three short portfolios (its Table III), not three variants
# invented here. "between" = every other point-in-time member not predicted
# to go ex this month, including firms that never pay. "within" = only firms
# that had an ex-date in the last 12 months but are not predicted to have one
# this month -- the paper's identification workhorse, long each quarterly
# payer 4 months a year and short the same names the other 8, so fixed factor
# loadings cancel. "one_after" = only firms exactly one month AFTER a
# predicted dividend, which under the price-pressure mechanism puts the short
# leg squarely in the reversal window.
DMP_SHORT_LEGS: tuple[str, ...] = ("between", "within", "one_after")

# "equal" = the harness's own equal mode, and [HS12]'s EW book. "yield" =
# weight PROPORTIONAL to the paper's own dividend-yield measure, which it
# reports drives the size of the price pressure. NOT the paper's VW book --
# see the module docstring, deviation 3. Rides the harness's generic
# weight_basis path, whose mode is named "inverse_vol" for historical reasons
# but performs no inversion of its own.
DMP_LEG_WEIGHTINGS: tuple[str, ...] = ("equal", "yield")

# "month" = [HS12]'s own unit, the full calendar month. "toex" = out at the
# predicted ex-day, capturing the run-up and exiting before the reversal.
DMP_WINDOWS: tuple[str, ...] = ("month", "toex")

DMP_N_TRIALS = len(DMP_SHORT_LEGS) * len(DMP_LEG_WEIGHTINGS) * len(DMP_WINDOWS)

# The project's OWN sourced cost ladder for an equal-weighted S&P 500 book,
# adopted verbatim from data/research_runs/edge_cost_reaudit_corrected_
# PREREGISTRATION.txt section 2 rather than re-derived here.
DMP_COST_SENSITIVITY_BPS: tuple[float, ...] = (0.0, 1.0, 2.0, 3.5, 5.0)

# The placebo shifts every predicted month forward by this many months. +1 is
# the right shift for THIS family and 6 would be wrong: a quarterly payer's
# ex-months are t, t+3, t+6, t+9, so a six-month shift lands on another real
# payment month and the "placebo" would be a live book. One month lands
# squarely between payments. Pre-declared as a FALSIFICATION CONTROL, not a
# spec: if the placebo earns what the real book earns, whatever is being
# measured is not about dividend months.
DMP_PLACEBO_SHIFT_MONTHS = 1


def build_dmp_family() -> list[DmpSpec]:
    specs: list[DmpSpec] = []
    for short_leg in DMP_SHORT_LEGS:
        for weighting in DMP_LEG_WEIGHTINGS:
            for window in DMP_WINDOWS:
                specs.append(
                    DmpSpec(
                        pattern_id=f"dmp_{short_leg}_{weighting}_{window}",
                        family=DMP_FAMILY_NAME,
                        citation=DMP_CITATION,
                        short_leg=short_leg,
                        leg_weighting=weighting,
                        window=window,
                    )
                )
    assert len(specs) == DMP_N_TRIALS == 12, (
        f"the dividend-month family built {len(specs)} definitions; the declared grid implies "
        f"{DMP_N_TRIALS} and the pre-registration froze exactly 12. All three must agree -- a "
        "drift silently changes this family's DSR denominator."
    )
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    assert {s.short_leg for s in specs} == set(DMP_SHORT_LEGS)
    assert {s.leg_weighting for s in specs} == set(DMP_LEG_WEIGHTINGS)
    assert {s.window for s in specs} == set(DMP_WINDOWS)
    assert all(s.family == DMP_FAMILY_NAME for s in specs)
    return specs


DMP_FAMILY: list[DmpSpec] = build_dmp_family()


# ===========================================================================
# THE EX-DAY EVENT STUDY -- THE MECHANISM DIAGNOSTIC
# ===========================================================================

# Event-time bounds, in trading days either side of the ACTUAL ex-day. -20
# spans the interim period ([HS12]'s median announcement-to-ex-day gap is ten
# days) and +40 is exactly the horizon over which the paper measures its
# -73.2bp reversal.
DMP_EVENT_WINDOW: tuple[int, int] = (-20, 40)


@dataclass
class ExDayEventStudy:
    """Mean UNIVERSE-HEDGED daily return in event time around real ex-dates,
    and its cumulation. THE mechanism test for this family.

    NOT DGTW characteristic-adjusted as [HS12]'s is -- this project has no
    size/book-to-market/momentum matched portfolios -- so the LEVELS are not
    directly comparable to the paper's +54.2bp run-up and -73.2bp reversal.
    The SHAPE is what this measures: does the excess return rise into day 0
    and fall back afterwards?

    Computed with hindsight on actual ex-dates and used for REPORTING ONLY.
    Nothing in position formation consults it."""

    n_events: int
    offsets: list[int]
    mean_excess_bps: list[float]
    cumulative_bps: list[float]
    run_up_bps: float  # cumulative over [start, 0]
    reversal_bps: float  # cumulative over (0, end]
    # PRECISION, on events with a complete window. Reporting a run-up and a
    # reversal without saying whether either is distinguishable from zero
    # would be over-claiming, which is the failure mode this project's rules
    # exist to prevent -- so the t-statistics are part of the diagnostic
    # rather than an optional extra.
    #
    # THE CLUSTERED t IS THE ONE TO READ. Ex-dates cluster hard into the
    # Feb/Mar, May/Jun, Aug/Sep and Nov/Dec pairs, so events in the same
    # calendar month share most of their market exposure and a naive
    # cross-event t treats correlated observations as independent. The
    # clustered figure averages within each ex-date month first and takes
    # the t across months. Both are reported so the gap is visible.
    n_complete_events: int = 0
    run_up_t: float = float("nan")
    reversal_t: float = float("nan")
    run_up_t_clustered: float = float("nan")
    reversal_t_clustered: float = float("nan")
    # run-up + reversal. Under [HS12]'s price-pressure mechanism the round
    # trip should be indistinguishable from zero -- the paper's own -73.2bp
    # is "large enough to offset the gains during the dividend month".
    net_bps: float = float("nan")
    net_t_clustered: float = float("nan")


def run_ex_day_event_study(
    close: pd.DataFrame,
    calendar: dict[str, dict[int, list[DividendEvent]]],
    membership: pd.DataFrame,
    formation_start: date,
    formation_end: date,
    window: tuple[int, int] = DMP_EVENT_WINDOW,
) -> ExDayEventStudy:
    """Every real ex-date in the formation window, for point-in-time members
    with usable prices, aligned in event time and averaged.

    The hedge is the equal-weighted mean return of that day's eligible
    point-in-time members -- the same "rest of the universe" comparison the
    portfolio uses, so the event study and the book are measuring excess
    return against the same thing rather than against two different
    benchmarks."""
    index = close.index
    n = len(index)
    start_offset, end_offset = window
    returns = close.pct_change(fill_method=None)
    returns_array = returns.to_numpy(dtype=float)
    columns = list(close.columns)
    column_of = {t: i for i, t in enumerate(columns)}
    membership_array = membership.reindex(
        index=close.index, columns=columns
    ).fillna(False).to_numpy(dtype=bool)

    # The daily equal-weighted universe return, computed once.
    eligible_mask = membership_array & np.isfinite(returns_array)
    counts = eligible_mask.sum(axis=1)
    sums = np.where(eligible_mask, returns_array, 0.0).sum(axis=1)
    universe = np.divide(sums, counts, out=np.full(n, np.nan), where=counts > 0)

    offsets = list(range(start_offset, end_offset + 1))
    totals = np.zeros(len(offsets))
    observations = np.zeros(len(offsets))
    n_events = 0
    # Per-event cumulative excess over the run-up and reversal halves, for
    # the t-statistics. Only events with a COMPLETE window contribute, so
    # the two halves are measured on the same population.
    event_run_ups: list[float] = []
    event_reversals: list[float] = []
    event_months: list[int] = []
    for ticker, months in calendar.items():
        if ticker not in column_of:
            continue
        col = column_of[ticker]
        for rows in months.values():
            for event in rows:
                if not (formation_start <= event.ex_date <= formation_end):
                    continue
                day0 = _first_row_at_or_after(index, event.ex_date)
                if day0 is None:
                    continue
                if day0 + start_offset < 0 or day0 + end_offset >= n:
                    continue
                if not membership_array[day0, col]:
                    continue
                n_events += 1
                for k, offset in enumerate(offsets):
                    row = day0 + offset
                    excess = returns_array[row, col] - universe[row]
                    if np.isfinite(excess):
                        totals[k] += excess
                        observations[k] += 1
                pre = returns_array[day0 + start_offset : day0 + 1, col] - universe[
                    day0 + start_offset : day0 + 1
                ]
                post = returns_array[day0 + 1 : day0 + end_offset + 1, col] - universe[
                    day0 + 1 : day0 + end_offset + 1
                ]
                if np.isfinite(pre).all() and np.isfinite(post).all():
                    event_run_ups.append(float(pre.sum()))
                    event_reversals.append(float(post.sum()))
                    event_months.append(month_index(event.ex_date))

    mean = np.divide(
        totals, observations, out=np.zeros(len(offsets)), where=observations > 0
    )
    cumulative = np.cumsum(mean)
    zero_index = offsets.index(0)
    run_ups = np.asarray(event_run_ups)
    reversals = np.asarray(event_reversals)
    months_array = np.asarray(event_months)
    # THE HEADLINE RUN-UP AND REVERSAL COME FROM THE COMPLETE-EVENT
    # POPULATION, not from the per-offset curve. The curve above averages
    # each offset over whatever events have data there (n_events, 15,255),
    # while the t-statistics can only be computed on events with a COMPLETE
    # window (n_complete_events, 14,924). Deriving the two halves from the
    # curve and the t-statistics from the complete subset -- which an earlier
    # revision did -- puts three numbers from two different populations in
    # one table, and they then do not add up: the curve gave +12.02 and
    # -18.35 against a round trip of -5.24, which is -6.33. Everything
    # reported as a headline now comes from one population, so run-up +
    # reversal == round trip by construction (asserted by a test).
    def _mean_bps(values: np.ndarray) -> float:
        return float(values.mean() * 10_000.0) if len(values) else float("nan")

    return ExDayEventStudy(
        n_events=n_events,
        offsets=offsets,
        mean_excess_bps=[float(v * 10_000.0) for v in mean],
        cumulative_bps=[float(v * 10_000.0) for v in cumulative],
        run_up_bps=_mean_bps(run_ups),
        reversal_bps=_mean_bps(reversals),
        n_complete_events=len(run_ups),
        run_up_t=_t_statistic(run_ups),
        reversal_t=_t_statistic(reversals),
        run_up_t_clustered=_clustered_t_statistic(run_ups, months_array),
        reversal_t_clustered=_clustered_t_statistic(reversals, months_array),
        net_bps=float(np.mean(run_ups + reversals) * 10_000.0) if len(run_ups) else float("nan"),
        net_t_clustered=_clustered_t_statistic(run_ups + reversals, months_array),
    )


def _t_statistic(values: np.ndarray) -> float:
    """Plain cross-event t. Reported alongside the clustered figure rather
    than instead of it, so the gap between "treating every event as
    independent" and "not doing that" is visible rather than hidden."""
    if len(values) < 2:
        return float("nan")
    std = float(np.std(values, ddof=1))
    if std <= 0.0 or not np.isfinite(std):
        return float("nan")
    return float(np.mean(values) / std * np.sqrt(len(values)))


def _clustered_t_statistic(values: np.ndarray, clusters: np.ndarray) -> float:
    """t across CLUSTER MEANS -- here, across ex-date calendar months.

    Ex-dates cluster hard into four seasonal pairs, so events sharing a
    month share most of their market exposure and a naive t treats
    correlated observations as independent. Averaging within cluster first
    is the conservative direction and it is the figure the run report leads
    with."""
    if len(values) < 2:
        return float("nan")
    frame = pd.DataFrame({"value": values, "cluster": clusters})
    means = frame.groupby("cluster")["value"].mean()
    if len(means) < 2:
        return float("nan")
    std = float(means.std(ddof=1))
    if std <= 0.0 or not np.isfinite(std):
        return float("nan")
    return float(means.mean() / std * np.sqrt(len(means)))


# ===========================================================================
# THE EARNINGS CONFOUND -- A POST-HOC DIAGNOSTIC, LABELLED AS SUCH
# ===========================================================================
#
# THIS WAS NOT PRE-REGISTERED. It was added after the run, because measuring
# this family's overlap with the sibling earnings_announcement_premium family
# turned up something that directly undermines the pre-registered event
# study's interpretation: 92.0% of the ex-day event windows contain a real
# 8-K Item 2.02 earnings announcement (median distance from the ex-date to
# the nearest announcement: 17 trading days).
#
#   CORRECTED ON THE SECOND INDEPENDENT VERIFICATION, 2026-09-02 -- see
#   ERRATA V4. This block said "74.3% ... 42.5% of them inside the run-up
#   half" and quoted "+12.0bp run-up and -18.4bp reversal". All three were
#   stale: 74.3% was never re-measured after the diagnostic was finished and
#   no run of this code produces it, and +12.0/-18.4 are the PRE-C1 figures
#   read off the per-offset curve. The module docstring and the run report
#   both carry the right numbers; only this comment was left behind, which is
#   exactly how a reader of the CODE rather than the write-up ends up with a
#   number the write-up already retracted.
#
# The pre-registered study therefore CANNOT, on its own, attribute its
# +12.84bp run-up and -18.08bp reversal to dividend price pressure rather
# than to earnings. [HS12] does not have this problem: its Table IV separates the
# declaration day, the interim period and the ex-day, so it can locate the
# return between the announcement and the ex-day. This family's
# universe-hedged study does not decompose that way.
#
# What this measures is the obvious clean test: re-run the identical event
# study on only those ex-dates with NO earnings announcement anywhere in the
# window. It computes no portfolio, no Sharpe and no DSR, is NOT in
# n_trials, and is reported with its own severe caveat -- dropping ~92% of
# events leaves a SELECTED subsample (firms whose dividend calendar is far
# from their earnings calendar are unusual) with much less power, so a null
# on it is "not supported", never "refuted".


@dataclass
class EarningsConfoundDiagnostic:
    """The post-hoc earnings-contamination test. `available` is False when
    no announcement calendar was supplied, in which case every figure is NaN
    and the report says so rather than printing zeros."""

    available: bool
    n_all_events: int = 0
    n_clean_events: int = 0
    fraction_window_contains_announcement: float = float("nan")
    # Distance from an ex-date to that firm's NEAREST announcement, in
    # TRADING ROWS (not calendar days -- both are row indices into the price
    # panel). The share_within_* fields answer the separate question of
    # whether the two families trade the SAME EVENT, as opposed to whether
    # their event WINDOWS overlap.
    median_abs_gap_trading_days: float = float("nan")
    share_same_day: float = float("nan")
    share_within_3_days: float = float("nan")
    share_within_10_days: float = float("nan")
    all_run_up_bps: float = float("nan")
    all_reversal_bps: float = float("nan")
    all_round_trip_bps: float = float("nan")
    all_run_up_t: float = float("nan")
    all_reversal_t: float = float("nan")
    all_round_trip_t: float = float("nan")
    clean_run_up_bps: float = float("nan")
    clean_reversal_bps: float = float("nan")
    clean_round_trip_bps: float = float("nan")
    clean_run_up_t: float = float("nan")
    clean_reversal_t: float = float("nan")
    clean_round_trip_t: float = float("nan")


def _share_within(gaps: list[int], k: int) -> float:
    """Share of ex-dates whose nearest earnings announcement is within k
    trading rows. Answers "are these the same event?", which is a different
    question from "do their windows overlap?" -- the two families can be
    (and are) distinct as events while badly entangled as windows."""
    if not gaps:
        return float("nan")
    array = np.asarray(gaps)
    return float((array <= k).mean())


def measure_earnings_confound(
    close: pd.DataFrame,
    calendar: dict[str, dict[int, list[DividendEvent]]],
    membership: pd.DataFrame,
    announcement_dates: dict[str, list[date]] | None,
    formation_start: date,
    formation_end: date,
    window: tuple[int, int] = DMP_EVENT_WINDOW,
) -> EarningsConfoundDiagnostic:
    """The pre-registered event study, split by whether an earnings
    announcement falls inside the event window.

    `announcement_dates` is {ticker: [8-K Item 2.02 filing dates]}, supplied
    by the caller from the earnings-premium family's own cached calendar --
    passed in rather than loaded here, so this module does not depend on
    that family's cache existing."""
    if not announcement_dates:
        return EarningsConfoundDiagnostic(available=False)

    index = close.index
    n = len(index)
    start_offset, end_offset = window
    returns_array = close.pct_change(fill_method=None).to_numpy(dtype=float)
    columns = list(close.columns)
    column_of = {t: i for i, t in enumerate(columns)}
    membership_array = membership.reindex(
        index=close.index, columns=columns
    ).fillna(False).to_numpy(dtype=bool)

    eligible = membership_array & np.isfinite(returns_array)
    counts = eligible.sum(axis=1)
    sums = np.where(eligible, returns_array, 0.0).sum(axis=1)
    universe = np.divide(sums, counts, out=np.full(n, np.nan), where=counts > 0)

    announcement_rows: dict[str, np.ndarray] = {}
    for ticker, dates in announcement_dates.items():
        if ticker not in column_of or not dates:
            continue
        rows = np.searchsorted(
            index.values,
            np.array([pd.Timestamp(d).to_datetime64() for d in sorted(dates)]),
        )
        announcement_rows[ticker] = np.unique(rows[rows < n])

    buckets: dict[bool, dict[str, list]] = {
        True: {"run_up": [], "reversal": [], "month": []},
        False: {"run_up": [], "reversal": [], "month": []},
    }
    gaps: list[int] = []
    for ticker, by_month in calendar.items():
        if ticker not in column_of:
            continue
        col = column_of[ticker]
        rows = announcement_rows.get(ticker, np.array([], dtype=int))
        for events in by_month.values():
            for event in events:
                if not (formation_start <= event.ex_date <= formation_end):
                    continue
                day0 = _first_row_at_or_after(index, event.ex_date)
                if day0 is None or day0 + start_offset < 0 or day0 + end_offset >= n:
                    continue
                if not membership_array[day0, col]:
                    continue
                pre = returns_array[day0 + start_offset : day0 + 1, col] - universe[
                    day0 + start_offset : day0 + 1
                ]
                post = returns_array[day0 + 1 : day0 + end_offset + 1, col] - universe[
                    day0 + 1 : day0 + end_offset + 1
                ]
                if not (np.isfinite(pre).all() and np.isfinite(post).all()):
                    continue
                contaminated = bool(
                    len(rows)
                    and ((rows >= day0 + start_offset) & (rows <= day0 + end_offset)).any()
                )
                if len(rows):
                    gaps.append(int(np.min(np.abs(rows - day0))))
                for key, value in (("run_up", pre.sum()), ("reversal", post.sum())):
                    buckets[contaminated][key].append(float(value))
                buckets[contaminated]["month"].append(month_index(event.ex_date))

    def summarize(contaminated_only: bool | None):
        if contaminated_only is None:
            run_up = np.array(buckets[True]["run_up"] + buckets[False]["run_up"])
            reversal = np.array(buckets[True]["reversal"] + buckets[False]["reversal"])
            months = np.array(buckets[True]["month"] + buckets[False]["month"])
        else:
            run_up = np.array(buckets[contaminated_only]["run_up"])
            reversal = np.array(buckets[contaminated_only]["reversal"])
            months = np.array(buckets[contaminated_only]["month"])
        if not len(run_up):
            return (float("nan"),) * 6 + (0,)
        return (
            float(run_up.mean() * 10_000.0),
            float(reversal.mean() * 10_000.0),
            float((run_up + reversal).mean() * 10_000.0),
            _clustered_t_statistic(run_up, months),
            _clustered_t_statistic(reversal, months),
            _clustered_t_statistic(run_up + reversal, months),
            len(run_up),
        )

    a_run, a_rev, a_net, a_rt, a_rvt, a_nt, n_all = summarize(None)
    c_run, c_rev, c_net, c_rt, c_rvt, c_nt, n_clean = summarize(False)
    n_contaminated = len(buckets[True]["run_up"])
    return EarningsConfoundDiagnostic(
        available=True,
        n_all_events=n_all,
        n_clean_events=n_clean,
        fraction_window_contains_announcement=(
            n_contaminated / n_all if n_all else float("nan")
        ),
        median_abs_gap_trading_days=float(np.median(gaps)) if gaps else float("nan"),
        share_same_day=_share_within(gaps, 0),
        share_within_3_days=_share_within(gaps, 3),
        share_within_10_days=_share_within(gaps, 10),
        all_run_up_bps=a_run,
        all_reversal_bps=a_rev,
        all_round_trip_bps=a_net,
        all_run_up_t=a_rt,
        all_reversal_t=a_rvt,
        all_round_trip_t=a_nt,
        clean_run_up_bps=c_run,
        clean_reversal_bps=c_rev,
        clean_round_trip_bps=c_net,
        clean_run_up_t=c_rt,
        clean_reversal_t=c_rvt,
        clean_round_trip_t=c_nt,
    )


# ===========================================================================
# SCREENING
# ===========================================================================


@dataclass
class DmpScreeningResult:
    pattern_id: str
    family: str
    citation: str
    short_leg: str
    leg_weighting: str
    window: str
    n_long_positions: int
    n_short_positions: int
    n_long_caught_actual: int
    caught_actual_fraction: float
    n_delisted_mid_hold: int
    n_trading_days: int
    n_invested_days: int
    n_one_sided_days: int
    invested_fraction: float
    mean_long_leg_size: float
    min_long_leg_size: int
    max_long_leg_size: int
    mean_short_leg_size: float
    mean_daily_turnover: float
    sharpe_annualized: float
    gross_sharpe_annualized: float
    total_cost_drag: float
    net_cumulative_return: float
    cost_sensitivity_sharpe: dict[float, float]
    subperiod_sharpes: list[float]
    deflated_sharpe: DeflatedSharpeResult
    n_weight_fallback_days: int = 0
    position_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class DmpPlaceboResult:
    status: str
    sharpe_annualized: float
    gross_sharpe_annualized: float
    n_trading_days: int
    n_long_positions: int
    caught_actual_fraction: float


def _subperiod_sharpes(returns: pd.Series, n_parts: int = 3) -> list[float]:
    """Sharpe of each of `n_parts` equal contiguous slices -- the same
    stability diagnostic the eigenportfolio and earnings-premium families
    report. A slice too short to annualize honestly returns NaN rather than
    a number."""
    if len(returns) < n_parts * MIN_REPLAY_TRADING_DAYS:
        return [float("nan")] * n_parts
    edges = np.linspace(0, len(returns), n_parts + 1).astype(int)
    return [
        float(sharpe_ratio(returns.iloc[edges[i] : edges[i + 1]])) for i in range(n_parts)
    ]


def shift_predictions(
    predicted: dict[str, dict[int, PredictedDividendMonth]], months: int
) -> dict[str, dict[int, PredictedDividendMonth]]:
    """The placebo calendar: every prediction moved `months` months later,
    carrying its projected ex-day with it so the 'toex' window is shifted
    identically rather than silently degrading.

    `outside_month` is recomputed against the NEW month, because a
    projection that sat inside its original month does not sit inside the
    shifted one -- getting that wrong would make the placebo trade a
    systematically different window shape from the live book and the
    comparison would be worthless."""
    out: dict[str, dict[int, PredictedDividendMonth]] = {}
    delta = timedelta(days=30 * months)
    for ticker, rows in predicted.items():
        shifted: dict[int, PredictedDividendMonth] = {}
        for month, prediction in rows.items():
            new_month = month + months
            new_ex = prediction.predicted_ex_date + delta
            shifted[new_month] = PredictedDividendMonth(
                ticker=prediction.ticker,
                month=new_month,
                frequency=prediction.frequency,
                source_lag=prediction.source_lag,
                source_ex_date=prediction.source_ex_date,
                predicted_ex_date=new_ex,
                outside_month=month_index(new_ex) != new_month,
                trailing_mean_amount=prediction.trailing_mean_amount,
                n_prior_ex_dates=prediction.n_prior_ex_dates,
            )
        out[ticker] = shifted
    return out


def screen_dmp_family(
    close: pd.DataFrame,
    price_only_close: pd.DataFrame,
    calendar: dict[str, dict[int, list[DividendEvent]]],
    predicted: dict[str, dict[int, PredictedDividendMonth]],
    membership: pd.DataFrame,
    formation_start: date,
    formation_end: date,
    config: DmpConfig,
    specs: list[DmpSpec] | None = None,
) -> tuple[list[DmpScreeningResult], dict[str, DmpPlaceboResult]]:
    """One Sharpe per spec, DSR-corrected for the family's PRE-DECLARED
    size. n_trials is len(specs) -- the family's literal declared size,
    never shrunk to however many specs happened to clear the data floors.
    sigma_sr is the ddof=1 std of every sibling spec's own Sharpe from this
    same pass."""
    specs = specs if specs is not None else DMP_FAMILY
    # POOLED DENOMINATOR (2026-09-04). len(specs) is this FAMILY's search;
    # it was never the whole search. dsr_n_trials raises it to the
    # project-wide effectively-independent trial count (ONC E[K] over every
    # persisted trial's realized returns) whenever that is larger, and only
    # ever larger -- see global_effective_n.py's "THE ONE GUARD".
    # `if specs else 0` because dsr_n_trials REFUSES a grid size of 0 (a
    # caller with no pre-declared family at all), and an empty spec list is
    # a legitimate no-op every one of these screens already returns [] for.
    n_trials = dsr_n_trials(len(specs)) if specs else 0

    replays: dict[str, tuple[DmpBacktestResult, PositionCounts]] = {}
    for spec in specs:
        positions, counts = build_dmp_positions(
            close,
            price_only_close,
            calendar,
            predicted,
            membership,
            formation_start,
            formation_end,
            spec,
            config,
        )
        replay = run_dmp_backtest(close, positions, spec, config)
        if replay.status != "ok" or len(replay.gross_daily_returns) < MIN_REPLAY_TRADING_DAYS:
            logger.warning(
                "%s produced no replayable series (status=%s, days=%d)",
                spec.pattern_id,
                replay.status,
                len(replay.gross_daily_returns),
            )
            continue
        replays[spec.pattern_id] = (replay, counts)

    net_by_id = {
        pattern_id: net_daily_returns(replay, config.cost_bps, config.financing_bps_per_year)
        for pattern_id, (replay, _counts) in replays.items()
    }
    sharpes = {pid: sharpe_ratio(series) for pid, series in net_by_id.items()}
    sigma_sr = float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None

    spec_by_id = {spec.pattern_id: spec for spec in specs}
    results: list[DmpScreeningResult] = []
    for pattern_id, (replay, counts) in replays.items():
        spec = spec_by_id[pattern_id]
        net = net_by_id[pattern_id]
        n_days = len(net)
        cost_rate = config.cost_bps / 10_000.0
        results.append(
            DmpScreeningResult(
                pattern_id=pattern_id,
                family=spec.family,
                citation=spec.citation,
                short_leg=spec.short_leg,
                leg_weighting=spec.leg_weighting,
                window=spec.window,
                n_long_positions=counts.n_long,
                n_short_positions=counts.n_short,
                n_long_caught_actual=counts.n_long_caught_actual,
                caught_actual_fraction=(
                    counts.n_long_caught_actual / counts.n_long if counts.n_long else 0.0
                ),
                n_delisted_mid_hold=replay.n_delisted_mid_hold,
                n_trading_days=n_days,
                n_invested_days=replay.n_invested_days,
                n_one_sided_days=replay.n_one_sided_days,
                invested_fraction=(replay.n_invested_days / n_days) if n_days else 0.0,
                mean_long_leg_size=replay.mean_long_leg_size,
                min_long_leg_size=replay.min_long_leg_size,
                max_long_leg_size=replay.max_long_leg_size,
                mean_short_leg_size=replay.mean_short_leg_size,
                mean_daily_turnover=float(replay.daily_turnover.mean()),
                sharpe_annualized=sharpes[pattern_id],
                gross_sharpe_annualized=float(sharpe_ratio(replay.gross_daily_returns)),
                total_cost_drag=float(replay.daily_turnover.sum() * cost_rate),
                net_cumulative_return=float((1.0 + net).prod() - 1.0),
                cost_sensitivity_sharpe={
                    level: float(
                        sharpe_ratio(
                            net_daily_returns(replay, level, config.financing_bps_per_year)
                        )
                    )
                    for level in DMP_COST_SENSITIVITY_BPS
                },
                subperiod_sharpes=_subperiod_sharpes(net),
                deflated_sharpe=compute_deflated_sharpe(
                    sharpes[pattern_id], net, n_trials, sigma_sr
                ),
                n_weight_fallback_days=replay.n_weight_fallback_days,
                position_counts={
                    "n_predictions": counts.n_predictions,
                    "n_outside_formation": counts.n_outside_formation,
                    "n_not_member": counts.n_not_member,
                    "n_no_price": counts.n_no_price,
                    "n_below_price_screen": counts.n_below_price_screen,
                    "n_thin_history": counts.n_thin_history,
                    "n_no_yield_basis": counts.n_no_yield_basis,
                    "n_ex_day_outside_month": counts.n_ex_day_outside_month,
                    "n_long": counts.n_long,
                    "n_short": counts.n_short,
                },
            )
        )

    placebo = _run_placebo(
        close,
        price_only_close,
        calendar,
        predicted,
        membership,
        formation_start,
        formation_end,
        config,
        specs,
    )
    results.sort(key=lambda r: r.sharpe_annualized, reverse=True)
    return results, placebo


def _run_placebo(
    close: pd.DataFrame,
    price_only_close: pd.DataFrame,
    calendar: dict[str, dict[int, list[DividendEvent]]],
    predicted: dict[str, dict[int, PredictedDividendMonth]],
    membership: pd.DataFrame,
    formation_start: date,
    formation_end: date,
    config: DmpConfig,
    specs: list[DmpSpec],
) -> dict[str, DmpPlaceboResult]:
    """The pre-declared FALSIFICATION CONTROL: the identical machinery on a
    calendar shifted DMP_PLACEBO_SHIFT_MONTHS months, so every long position
    lands in a month the firm is NOT due to go ex. Not a spec, not in
    n_trials -- it is the thing this family must be shown not to be."""
    shifted = shift_predictions(predicted, DMP_PLACEBO_SHIFT_MONTHS)
    out: dict[str, DmpPlaceboResult] = {}
    for spec in specs:
        positions, counts = build_dmp_positions(
            close,
            price_only_close,
            calendar,
            shifted,
            membership,
            formation_start,
            formation_end,
            spec,
            config,
        )
        replay = run_dmp_backtest(close, positions, spec, config)
        caught = counts.n_long_caught_actual / counts.n_long if counts.n_long else 0.0
        if replay.status != "ok" or len(replay.gross_daily_returns) < MIN_REPLAY_TRADING_DAYS:
            out[spec.pattern_id] = DmpPlaceboResult(
                status=replay.status,
                sharpe_annualized=float("nan"),
                gross_sharpe_annualized=float("nan"),
                n_trading_days=len(replay.gross_daily_returns),
                n_long_positions=counts.n_long,
                caught_actual_fraction=caught,
            )
            continue
        net = net_daily_returns(replay, config.cost_bps, config.financing_bps_per_year)
        out[spec.pattern_id] = DmpPlaceboResult(
            status="ok",
            sharpe_annualized=float(sharpe_ratio(net)),
            gross_sharpe_annualized=float(sharpe_ratio(replay.gross_daily_returns)),
            n_trading_days=len(net),
            n_long_positions=counts.n_long,
            caught_actual_fraction=caught,
        )
    return out


@dataclass
class DmpScreeningSummary:
    results: list[DmpScreeningResult]
    placebo: dict[str, DmpPlaceboResult]
    event_study: ExDayEventStudy
    earnings_confound: EarningsConfoundDiagnostic
    forecast_accuracy: dict[str, ForecastAccuracy]
    calendar_report: DividendCalendarReport
    n_tickers_priced: int
    n_tickers_with_dividends: int
    panel_start: date | None
    panel_end: date | None
    formation_start: date
    formation_end: date
    cost_disclosure: str
    warnings: list[str] = field(default_factory=list)


def build_cost_disclosure(config: DmpConfig) -> str:
    return (
        f"COST DISCLOSURE. {config.cost_bps:.1f}bp ONE-WAY charged on the L1 turnover of the NET "
        f"book every day (cross_sectional.DEFAULT_XS_COST_BPS, this project's conservative equity "
        f"control rate, used as the HEADLINE). The pre-declared sensitivity ladder "
        f"{DMP_COST_SENSITIVITY_BPS} is adopted verbatim from this project's own sourced "
        f"calibration in data/research_runs/edge_cost_reaudit_corrected_PREREGISTRATION.txt "
        f"section 2 (1.0bp tight bound, 2.0bp BEST ESTIMATE for an equal-weighted S&P 500 book, "
        f"3.5bp conservative bound); it was NOT re-derived here. UNLIKE the sibling "
        f"earnings-announcement family, this book rebalances MONTHLY, so cost should not be the "
        f"assumption that decides the verdict -- if it turns out to be, that is a finding about "
        f"the 'toex' window rather than about the premium, and the ladder below is what shows it. "
        f"Financing: {config.financing_bps_per_year}bp/yr -- the equity families' shared "
        f"convention and the SAME DISCLOSED OPTIMISM documented in cross_sectional.py: the short "
        f"leg's real borrow cost is unobservable with this project's free data, and a real "
        f"securities-borrow feed is a known OPEN paid-data item. Market impact, commissions and "
        f"borrow are NOT modelled, so true costs are HIGHER than every column of the ladder."
    )


def run_dmp_screening(
    start: date,
    end: date,
    provider=None,
    config: DmpConfig | None = None,
    events: list[DividendEvent] | None = None,
    calendar_report: DividendCalendarReport | None = None,
    tickers: list[str] | None = None,
    fetch_start: date | None = None,
    announcement_dates: dict[str, list[date]] | None = None,
) -> DmpScreeningSummary:
    """THE production entry point.

    `start` must be >= MEMBERSHIP_DATA_START: every position is gated by
    point-in-time membership, which answers a silent False before coverage
    begins. Formations are additionally capped at membership_coverage_end()
    -- past it, get_universe_as_of cannot answer and build_membership_frame
    masks the dates ALL-FALSE rather than substituting today's roster.

    Pass `events` (+ `calendar_report`) to reuse the cached dividend
    calendar; omitting them loads the on-disk cache, which
    data/research_runs/fetch_dividend_calendar.py must have written first.
    There is deliberately no live-fetch fallback -- see
    load_dividend_cache."""
    from app.services.market_data.yfinance_provider import YFinanceProvider

    if start < MEMBERSHIP_DATA_START:
        raise ValueError(
            f"Dividend-month screening start {start.isoformat()} predates point-in-time "
            f"membership coverage ({MEMBERSHIP_DATA_START.isoformat()}) -- the membership gate "
            "would silently answer False for every formation before it."
        )
    provider = provider if provider is not None else YFinanceProvider()
    config = config if config is not None else DmpConfig()
    warnings: list[str] = []

    coverage_end = membership_coverage_end()
    formation_end = min(end, coverage_end)
    universe = (
        tickers
        if tickers is not None
        else get_universe_over(MEMBERSHIP_DATA_START, coverage_end)
    )

    if events is None:
        cached = load_dividend_cache()
        if cached is None:
            raise ValueError(
                "No dividend calendar cache found. Run "
                "data/research_runs/fetch_dividend_calendar.py first -- this module "
                "deliberately does not fall back to a live fetch, so that a screening run "
                "replays a fixed input."
            )
        events, calendar_report = cached
    if calendar_report is None:
        calendar_report = DividendCalendarReport(n_ex_dates=len(events))

    price_start = fetch_start if fetch_start is not None else start
    event_tickers = sorted({e.ticker for e in events} & set(universe))
    total_return, price_only, missing = provider.get_total_and_price_return_closes(
        event_tickers, price_start, end
    )
    if total_return.empty:
        raise ValueError("No price data resolved for any dividend-paying ticker.")
    if missing:
        warnings.append(
            f"{len(missing)} of {len(event_tickers)} dividend-paying tickers resolved no price "
            "data (the standing departed-member yfinance gap -- see cross_sectional.py)."
        )

    close = total_return
    membership = build_membership_frame(close.index, list(close.columns))
    calendar = build_ex_date_calendar([e for e in events if e.ticker in close.columns])

    first_month = month_index(close.index[0].date())
    last_month = month_index(close.index[-1].date())
    predicted = predict_dividend_months(calendar, first_month, last_month)

    results, placebo = screen_dmp_family(
        close,
        price_only,
        calendar,
        predicted,
        membership,
        start,
        formation_end,
        config,
    )
    event_study = run_ex_day_event_study(
        close, calendar, membership, start, formation_end
    )
    earnings_confound = measure_earnings_confound(
        close, calendar, membership, announcement_dates, start, formation_end
    )
    accuracy = {
        rule: measure_forecast_accuracy(
            calendar, month_index(start), month_index(formation_end), rule
        )
        for rule in DMP_ALTERNATIVE_RULES
    }
    return DmpScreeningSummary(
        results=results,
        placebo=placebo,
        event_study=event_study,
        earnings_confound=earnings_confound,
        forecast_accuracy=accuracy,
        calendar_report=calendar_report,
        n_tickers_priced=len(close.columns),
        n_tickers_with_dividends=len(calendar),
        panel_start=close.index[0].date(),
        panel_end=close.index[-1].date(),
        formation_start=start,
        formation_end=formation_end,
        cost_disclosure=build_cost_disclosure(config),
        warnings=warnings,
    )
