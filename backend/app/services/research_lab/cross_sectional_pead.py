"""Post-earnings-announcement drift (PEAD) via the Earnings Announcement
Return (EAR) proxy: a deliberately small (8-definition) EVENT-DRIVEN family
-- long the top quintile of fresh earnings announcements ranked by their own
announcement-window market-adjusted return, short the bottom quintile, each
event held for a fixed pre-declared horizon. Announcement dates come from
real SEC EDGAR 8-K filings carrying Item 2.02 ("Results of Operations and
Financial Condition"), NOT from analyst-estimate data this project does not
have.

Like cross_sectional_index_removal.py (read in full before this was built,
and the direct structural template) this module owns its family object, its
n_trials denominator, and its never-pooled DSR correction, and it does NOT
run on cross_sectional.screen_cross_sectional_universe -- each ticker has
its own announcement dates, so there is no shared formation calendar to
rank on (the same four structural mismatches that module's WHY THIS FAMILY
NEEDS ITS OWN REPLAY LOOP section lays out apply here almost unchanged,
with one difference: this family DOES have a cross-sectional ranking, but
it happens per-event against a trailing distribution, not per-date against
a synchronized universe snapshot). What it reuses, unmodified, is
everything downstream and sideways of the formation loop:
metrics.sharpe_ratio, deflated_sharpe.compute_deflated_sharpe, and -- from
cross_sectional.py itself -- _resolve_leg_weights (so "equal" and
"inverse_vol" here are LITERALLY the harness's own leg-weighting modes),
_leg_weighted_return (the drop-a-missing-name-and-renormalize convention),
_compute_delisting_positions plus DEFAULT_IMPUTED_DELISTING_RETURN (the
Shumway imputation, opted into exactly as cross_sectional_patterns_d2.py
and the index-removal family do), DEFAULT_XS_COST_BPS (the equity cost
convention), FINANCING_DAYS_PER_YEAR and MIN_REPLAY_TRADING_DAYS.

============================================================================
THE ACADEMIC BASIS -- EVERY CITATION BELOW WAS VERIFIED LIVE, TWICE
============================================================================
Verified once at build time (2026-08-28) and then RE-verified independently
the same day by an adversarial pass that re-fetched every source itself
rather than trusting this list. None is quoted from training memory. The
two tiers are labelled per entry and must not be blurred:
  PRIMARY  = the paper's own retrievable text was read and quoted.
  RECORD   = bibliographic record (journal/volume/pages) confirmed at
             Crossref, but the paywalled full text was NOT retrieved, so
             the one-line substantive summary rests on secondary sources
             and is marked as such.

 * Ball, R. & Brown, P., "An Empirical Evaluation of Accounting Income
   Numbers" (Journal of Accounting Research, 6(2), 1968, pp. 159-178).
   RECORD verified at Crossref (DOI 10.2307/2490232: title, JAR, vol 6,
   issue 2, first page 159; RePEc gives the 159-178 range). Note the print
   original was JAR's annual supplement "Empirical Research in Accounting:
   Selected Studies 1968", so "6(2)" and "6, Supplement" both circulate;
   6(2) is the publisher-of-record form used here. The original
   observation that returns continue to drift in the direction of the
   earnings news after the announcement -- SUBSTANCE NOT PRIMARY-VERIFIED
   (the paper is paywalled); confirmed only via secondary academic
   sources restating the finding.
 * Bernard, V. L. & Thomas, J. K., "Post-Earnings-Announcement Drift:
   Delayed Price Response or Risk Premium?" (Journal of Accounting
   Research, 27 (Supplement), 1989, pp. 1-36). RECORD verified at Crossref
   (DOI 10.2307/2491062: title, JAR, vol 27, NO issue number -- consistent
   with the supplement -- first page 1). Establishes the drift is a delayed
   price response, not a risk premium (confirmed via a retrieved source
   quoting the paper directly, not from the paywalled original). The
   ~60-trading-day top-minus-bottom-decile convention this family's 63-day
   hold mirrors comes from Foster, Olsen & Shevlin (1984), which estimated
   ~25% annualized abnormal return over the 60 trading days after the
   announcement. THE 25% IS FOSTER/OLSEN/SHEVLIN'S, NOT BERNARD & THOMAS'S
   -- B&T 1989's own comparable estimate is ~18-19%/yr, and conflating the
   two is a live risk this file names so it cannot happen by accident. The
   ~25%-via-FOS figure is corroborated by two independent secondary
   sources; that B&T 1989 is specifically the conduit for it was NOT
   primary-verified (paywalled).
 * Bernard, V. L. & Thomas, J. K., "Evidence that stock prices do not fully
   reflect the implications of current earnings for future earnings"
   (Journal of Accounting and Economics, 13(4), 1990, pp. 305-340). RECORD
   verified at Crossref (DOI 10.1016/0165-4101(90)90008-R: title, JAE, vol
   13, issue 4, pp. 305-340, 1990-12). Three-day reactions at announcements
   t+1..t+4 are predictable from quarter t's earnings -- the reason
   positions here are NOT closed early when a subsequent non-extreme
   announcement arrives mid-hold (the drift concentrates AT later
   announcements; closing before them would cut off exactly the documented
   effect). SUBSTANCE NOT PRIMARY-VERIFIED: on 2026-08-28 every full-text
   and abstract route was blocked (Deep Blue behind Cloudflare on the
   bitstream, the DSpace REST API and OAI-PMH alike; ScienceDirect 403;
   no Wayback snapshot; no abstract at Crossref or OpenAlex), and
   search-engine summaries were deliberately not accepted as evidence. It
   is corroborated indirectly: the Brandt et al. paper below cites B&T 1990
   for exactly this point and replicates the design. Treat the hold rule it
   justifies as resting on an unconfirmed reading until someone with
   journal access checks it.
 * Chan, L. K. C., Jegadeesh, N. & Lakonishok, J., "Momentum Strategies"
   (Journal of Finance, 51(5), 1996, pp. 1681-1713). PRIMARY: the published
   PDF was retrieved and read (its own header reads "THE JOURNAL OF FINANCE
   VOL. LI, NO 5 . DECEMBER 1996"). Measures earnings surprise three ways
   -- SUE, ABR, and REV6 (analyst revisions) -- and the abstract states
   "Past return and past earnings surprise each predict large drifts in
   future returns after controlling for the other". This is the canonical
   support for announcement-window return as a surprise proxy that is
   RELATED TO but DISTINCT FROM SUE.
   FLAG CLOSED 2026-08-28 by the verification pass: the build session could
   not retrieve the ABR day-window and honestly declined to quote it. It is
   now retrieved and quoted. Table I's own note: "ABR is the abnormal
   return relative to the equally-weighted market index cumulated from TWO
   DAYS BEFORE to ONE DAY AFTER the most recent past announcement date of
   quarterly earnings." So CJL's ABR is a FOUR-day (-2,+1) window against
   the equally-weighted market -- which is NEITHER of this family's two
   windows ((0,+1) and (-1,+1)) and uses a different benchmark. CJL is
   therefore support for the CONCEPT of a return-based surprise proxy, not
   for this family's specific window choice; the window choice traces to
   Brandt et al. below, whose three-day (-1,+1) window this family's wider
   axis matches exactly. (The mirror that serves it does so only over plain
   HTTP -- the HTTPS port refuses the connection, which is very likely why
   the build session concluded both mirrors had refused it.)
 * Brandt, M. W., Kishore, R., Santa-Clara, P. & Venkatachalam, M.,
   "Earnings Announcements are Full of Surprises" (SSRN working paper
   909563; the June-2007 version's full text was retrieved and read, and
   every quote below re-retrieved and re-checked by the verification pass).
   AUTHOR ORDER CORRECTED 2026-08-28: this was originally cited
   Kishore-first, which is SSRN's listing order; the paper's own title page
   reads "Michael W. Brandt(a), Runeet Kishore(b), Pedro Santa-Clara(c),
   Mohan Venkatachalam(d)", so Brandt-first is the correct form and is what
   the literature uses. The eight already-persisted
   cross_sectional_trial_results rows carry the OLD Kishore-first citation
   string; they were not rewritten, since the numbers are the record and
   silently editing archived rows is worse than a stale citation string in
   them.
   THE direct precedent for this family: they define EAR as the
   abnormal return "recorded over a three-day window centered on the
   announcement date" in excess of the matched size/book-to-market
   Fama-French portfolio, sort into QUINTILES using breakpoints from the
   PRIOR quarter's distribution ("This mitigates potential look-ahead bias
   associated with ranking observations based on quarter q realizations"),
   form portfolios "the day after the earnings announcement date", cumulate
   drift returns from t+2 "in 60 day increments", and report (June-2007
   text) an EAR-sorted hedge strategy earning ~6.3%/yr abnormal, ~0.7%/yr
   MORE than the SUE sort. Their Table 7 repeats the test on the top 1,000
   CRSP names and finds the EAR effect "considerably reduced, yet far from
   eliminated" in large caps -- directly load-bearing for the honest prior
   below, since this family's whole universe is S&P 500 constituents.

============================================================================
THE HONEST PRIOR IS MODEST, FOR PUBLISHED REASONS
============================================================================
Three compounding reasons to expect little here, stated before any result:
 1. LARGE CAPS. Brandt et al.'s own large-cap table (verified from the
    retrieved text, quoted above) shows the EAR effect is much weaker in
    the top-1000 universe; PEAD generally is concentrated in small,
    illiquid, high-arbitrage-cost names. This family's universe is the
    S&P 500 -- the single most arbitraged corner of global equities.
 2. RECENCY. The verified literature samples end in 2004 (Brandt et al.)
    or earlier; this family's sample is 2019-2026. A widely-documented
    pattern (not independently re-verified this session, flagged as such)
    is that published anomalies attenuate after publication; PEAD is among
    the most published anomalies in existence.
 3. PROXY NOISE. EAR-via-8-K is a proxy for a proxy: the 8-K Item 2.02
    filing time can lag the true press-release time, and no press-release
    text is parsed to confirm any given 2.02 filing is a genuine quarterly
    earnings release rather than a preliminary-results or guidance 8-K.
An honest negative is the expected outcome and is fine; this project has
shipped several already.

============================================================================
SEC EDGAR -- EVERYTHING BELOW WAS VERIFIED LIVE 2026-08-28, NOT ASSUMED
============================================================================
 * TICKER -> CIK: https://www.sec.gov/files/company_tickers.json returns a
   dict of {index: {cik_str, ticker, title}} (verified: 10,388 entries at
   build time and 10,391 on the verification pass hours later -- SEC
   regenerates this file continuously, so treat the COUNT as a liveness
   observation, not a constant; the SHAPE is what this module depends on.
   AAPL -> 320193; dual-class tickers use the DASH convention, "BRK-B",
   which matches ticker_universe.SCREENING_UNIVERSE's own convention
   exactly, so no symbol translation layer is needed).
 * FILING HISTORY: https://data.sec.gov/submissions/CIK##########.json
   (10-digit zero-padded) returns filings.recent as PARALLEL ARRAYS keyed
   accessionNumber / filingDate / acceptanceDateTime / form / items / ...
   (verified against CIK 0000320193: an 8-K row carries form='8-K',
   items='2.02,9.01', acceptanceDateTime='2026-07-30T20:30:28.000Z'). Item
   numbers ARE present directly in the submissions API, so the earnings
   8-Ks can be identified without full-text search. filings.recent holds
   up to ~1,000 filings (Apple's is 1,001 rows spanning
   2015-06-04..2026-08-20); older history lives in paginated filings.files
   entries THIS MODULE DOES NOT FETCH -- a heavy filer's recent window may
   start after the requested sample start, which is measured and disclosed
   per run (n_tickers_coverage_truncated), not silently ignored.
   REFINED by the verification pass 2026-08-28: "~1,000" is the usual case
   but NOT the rule -- EDGAR also guarantees at least the last year, and a
   very heavy filer blows past 1,000 while still covering only that year.
   Measured: JPM's filings.recent is 25,901 rows covering only
   2025-08-27..2026-08-27 (4 Item 2.02 8-Ks, against ~30 for a comparable
   full-history filer). _SEC_RECENT_TRUNCATION_ROWS still catches this
   correctly -- the test is len(recent) >= 1000 AND earliest > fetch_start,
   and JPM satisfies both -- so the 181 truncated tickers the production
   run reports are genuinely detected, not missed. The count is a real
   sample limit, disclosed, not a bug.
 * FULL-TEXT SEARCH: https://efts.sec.gov/LATEST/search-index?q=...&forms=
   8-K&startdt=...&enddt=... is real and returns Elasticsearch-style JSON
   (verified live with a real query), but is NOT used here -- the
   submissions API's items field already answers the only question this
   family asks of EDGAR.
 * FAIR ACCESS: https://www.sec.gov/os/accessing-edgar-data (retrieved
   2026-08-28; it 301-redirects to /search-filings/edgar-search-assistance/
   accessing-edgar-data, so follow redirects when re-checking) states
   verbatim "Current max request rate: 10 requests/second" and
   "Please declare your user agent in request headers" (its sample header
   is "User-Agent: Sample Company Name AdminContact@<sample company
   domain>.com"). Both strings re-retrieved and re-quoted by the
   independent verification pass the same day. This module
   enforces PEAD_SEC_MIN_REQUEST_INTERVAL_SECONDS (0.15s => ~6.7 req/s,
   under the published cap) and sends PEAD_SEC_USER_AGENT on every
   request. Measured empirically 2026-08-28, not assumed: www.sec.gov
   (which serves the ticker->CIK file) returns HTTP 403 to any User-Agent
   WITHOUT an email-shaped contact token and 200 to the same UA with one,
   while data.sec.gov accepts an email-free UA -- so the default UA
   carries an explicitly non-routable placeholder contact
   (research-contact@aladdin2-project.local). A real personal email is
   deliberately NOT embedded (this project's rules forbid sending the
   operator's email to third-party services without explicit
   instruction); SEC's own sample UA includes a real admin contact, so an
   operator running this at scale should override user_agent with one.

============================================================================
SIGNAL DEFINITION AND TIMING
============================================================================
DAY 0 is the first trading session that could have reacted to the
announcement, derived from acceptanceDateTime (converted UTC -> US/Eastern
via zoneinfo): accepted BEFORE 16:00 ET on day D -> day 0 is the first
trading row at-or-after D; accepted at-or-after 16:00 ET (or on a
non-trading day) -> day 0 is the first trading row strictly after D. A
missing acceptanceDateTime falls back to the AFTER-close rule -- the
conservative direction, since it can only delay the window, never place it
before the news existed. (Caveat, disclosed not solved: the EDGAR
acceptance time is when the FILING hit EDGAR, which can lag the press
release by minutes to hours; a release at 15:55 followed by a 16:20
acceptance is mapped to the next day and the [0,+1] window then misses the
final pre-close minutes of reaction. The error direction is a slightly
LATER, never earlier, window.)

EAR = buy-and-hold return of the stock MINUS buy-and-hold return of SPY
over the window, computed on adjusted closes:
    window (0,+1):  close(day0-1) -> close(day0+1)
    window (-1,+1): close(day0-2) -> close(day0+1)
Brandt et al. adjust with the matched size/book-to-market Fama-French
portfolio; this project has no book-to-market data, so the benchmark is
SPY -- defensible because every name here is an S&P 500 member at its
announcement (the was_member gate below), i.e. SPY IS the matched
large-cap benchmark, but a real deviation from the paper and disclosed as
such.

RANKING is against the TRAILING distribution: an event is LONG if its EAR
is at or above the 80th percentile, SHORT if at or below the 20th
percentile, of the EARs of all events whose own EAR windows completed
STRICTLY BEFORE this event's entry close and whose day 0 lies within the
trailing PEAD_BREAKPOINT_WINDOW_TRADING_DAYS (126) rows -- the
point-in-time analogue of Brandt et al.'s prior-quarter breakpoints
(quintiles, matching their verified design; the cutoff is NOT a family
axis). An event with fewer than PEAD_MIN_BREAKPOINT_OBS (30) trailing
observations is not entered (counted, disclosed). Events fetched in the
warm-up padding before the requested start feed the breakpoint
distribution but are never themselves entered.

ENTRY is at the close of the LAST DAY OF THE EAR WINDOW -- the close at
which the signal is fully determined. This matches
cross_sectional.py's own form-at-the-close-with-signal-through-that-close
convention, and deliberately DIFFERS from the index-removal family's +1
offset: that family delays entry to avoid transacting into the index's own
forced-flow auction, a mechanism that has no analogue here. The first
realized return is the following trading day. Exit is holding_days trading
days after entry (truncated at the data's end), or the day the name
delists (Shumway imputation, ON by default -- the short leg here is
adversely selected negative-surprise names, exactly the population the
imputation exists for; note that for a SHORT position the imputed -42.5%
is a gain, which is the realistic direction: bad-news names that die hurt
their shorts' lenders, not the shorts).

A NEW TRADED EVENT ON AN ALREADY-HELD TICKER SUPERSEDES the old position
(counted): with quarterly announcements ~63 trading days apart and holds
of 63-126 days, overlap is structural, and the newest extreme announcement
is the freshest information. A subsequent NON-extreme announcement does
NOT close an open position -- Bernard & Thomas (1990) locate the drift
precisely at subsequent announcements, so closing ahead of them would
amputate the hypothesis being tested.

============================================================================
FAMILY SIZE -- 8, FIXED AND ASSERTED BEFORE ANY RUN
============================================================================
2 EAR windows {(0,+1), (-1,+1)} x 2 holding periods {63, 126 trading days}
x 2 leg weightings {equal, inverse_vol} = 8. PEAD_N_TRIALS is asserted
against the built list in _build_pead_family, so a size drift is a loud
import-time failure rather than a silent change to every future run's DSR
denominator. 8 >= deflated_sharpe.MIN_TRIALS_FOR_DSR (5). The two windows
are the two standard short EAR windows ((0,+1) is the minimal
announcement-reaction window; (-1,+1) is Brandt et al.'s three-day window
including the leakage day); 63 days is the literature's ~60-day
convention, 126 extends to two quarters, inside the four-quarter horizon
Brandt et al. cumulate over; the weightings are the harness's own two
non-signal modes. Quintile cutoff, breakpoint window, benchmark, and entry
timing are fixed constants, not axes -- widening any of them into an axis
after seeing results would be exactly the search this project's DSR
machinery exists to punish.

============================================================================
COSTS
============================================================================
 * ROUND TRIP: 2 x cross_sectional.DEFAULT_XS_COST_BPS = 10bp per unit of
   event notional, entry and exit together, charged in full on the event's
   FIRST realized day (the sibling families' convention; conservative for
   an event that delists mid-hold, which has then paid an exit it never
   executed). Reusing the harness's own equity constant rather than
   estimating a new one: every name traded here is a current S&P 500
   member, the exact population DEFAULT_XS_COST_BPS was declared for.
 * FINANCING: 0.0bp/yr by default, matching every equity family in
   cross_sectional.py (DEFAULT_FINANCING_BPS_PER_YEAR = 0.0) and carrying
   the SAME disclosed optimism documented there: the short leg's real
   borrow cost is unobservable with this project's free data, and the
   short leg here is negative-surprise names, some of which will be
   hard-to-borrow precisely when shorted. A real borrow feed is already on
   the project's pending-paid list. config.financing_bps_per_year exists
   for sensitivity runs; when non-zero it accrues on gross notional held
   (2.0 when both legs are on) over CALENDAR days via
   FINANCING_DAYS_PER_YEAR.
 * Daily renormalization as events enter/leave is NOT charged -- the
   harness's own stated zero-cost-rebalancing convention, kept for
   consistency and disclosed: true costs are higher than reported.

============================================================================
KNOWN LIMITS
============================================================================
 * SURVIVORSHIP UNIVERSE. Events are sourced for ticker_universe.
   SCREENING_UNIVERSE -- TODAY's S&P 500 snapshot -- then gated by
   point-in-time membership (was_member at the filing date), so no event
   is used from before a name joined the index. What the gate CANNOT
   restore is names that LEFT the index before the snapshot: their events
   are absent entirely. Departed members skew toward deteriorating
   companies whose negative-surprise events would populate the SHORT leg,
   so their absence plausibly WEAKENS the measured short-side drift; the
   direction is disclosed, the size is unknowable with free data (same
   closure-needs-CRSP/Norgate situation as every equity family here).
 * ONE 8-K != ONE EARNINGS RELEASE, EXACTLY. Item 2.02 is overwhelmingly
   quarterly earnings but also covers preliminary-results and
   results-related guidance 8-Ks; no press-release text is parsed to
   distinguish them. Amended filings (8-K/A) are excluded; two 2.02
   filings by one ticker within PEAD_DUPLICATE_FILING_GAP_TRADING_DAYS (5)
   rows keep only the first (counted).
 * COVERAGE TRUNCATION. filings.recent holds ~1,000 filings; for heavy
   filers that window can start after the sample start. Measured and
   reported per run, and such tickers simply contribute fewer events.
 * OVERLAPPING HOLDS / CLUSTERED EVENTS. Earnings cluster in quarterly
   reporting seasons and holds overlap heavily at 126 days, so consecutive
   daily returns share most of their constituents; the daily observation
   count feeding the Sharpe/DSR overstates the independent information.
   The disclosure reports events, distinct day-0 dates, and announcement-
   season clustering; none of the numbers below should be read as if each
   day were independent.
 * FLAT DAYS ARE REAL RETURNS. A day on which either leg is empty is 0.0
   by design (a long-short book with one side missing cannot put on its
   trade; going naked one-sided would be a different strategy). Counted
   and reported (n_one_sided_days), never dropped.

============================================================================
WHAT THE 2026-08-28 PRODUCTION RUN FOUND -- AN HONEST NEGATIVE
============================================================================
Run: announcements 2019-01-02..2026-08-27 (EDGAR fetched down to
2018-04-07 for breakpoint warm-up), run_tag='pead_build_2026-08-28',
persisted to cross_sectional_trial_results (family_key='pead_ear'), which
is the authoritative record of these numbers.

The sample, as actually measured: all 503 SCREENING_UNIVERSE tickers
resolved a CIK and returned a submissions JSON (0 failures); 181 of them
have truncated 'recent' coverage starting after 2018-04-07 (heavy filers
-- their early events are missing, disclosed above). 15,552 Item 2.02
8-Ks in-window; 13,942 survive the point-in-time membership gate; 499
tickers priced on yfinance; ~13,750 events scored per window (~170
dropped as duplicate filings within the 5-row gap); 13,012 with day 0 in
the formation window, ZERO skipped for thin breakpoints; ~5,290 entered
per window (~2,620 long + ~2,670 short), on 1,920 realized trading days,
invested 99.7-99.8% of them.

All eight specs, not the best of them:

    window   hold  weighting     Sharpe    PSR     DSR
    (-1,+1)   63   equal        -0.077   0.416   0.145
    (-1,+1)   63   inverse_vol  -0.082   0.410   0.141
    (-1,+1)  126   equal        -0.166   0.324   0.096
    (-1,+1)  126   inverse_vol  -0.188   0.302   0.086
    (0,+1)    63   equal        -0.411   0.127   0.023
    (0,+1)    63   inverse_vol  -0.414   0.125   0.023
    (0,+1)   126   inverse_vol  -0.578   0.053   0.007
    (0,+1)   126   equal        -0.584   0.052   0.006

Every Sharpe is NEGATIVE. The best DSR is 0.145 against the pre-declared
n_trials=8. Nothing here goes anywhere near validation.

Cross-checked the same day by a separate route sharing no code with the
replay: a pooled-quintile event study (full-sample breakpoints --
deliberately MORE favorable to finding drift than the point-in-time
rule; no costs, no weighting, no book) over the 12,649 events with a
full 63-trading-day post-window. Mean 63-day excess-vs-SPY by EAR
quintile (window -1..+1): Q1 -0.36%, Q2 -0.61%, Q3 -0.66%, Q4 -0.89%,
Q5 -0.20%. Q5-minus-Q1 spread: +0.16pp, naive t = +0.36 (and that t
treats 5,060 events as independent, which quarterly clustering says they
are not). No monotonic pattern across quintiles; fewer than half the
events in BOTH extreme quintiles are positive. So the gross drift is
statistically indistinguishable from zero.

============================================================================
CORRECTION FROM THE INDEPENDENT VERIFICATION PASS, 2026-08-28
============================================================================
An adversarial re-verification pass re-derived every number above from the
cached EDGAR event list and a fresh price pull, with a from-scratch replay
sharing no code with this module. The eight persisted Sharpes reproduced to
<= 1.2e-6 and every event count (13,942 gated / 13,751 and 13,752 scored /
13,012 eligible / 0 thin / 2,629+2,677 and 2,612+2,661 entered / 1,920
days) reproduced exactly. Two things did NOT survive that pass:

 1. THE MECHANISM SENTENCE WAS WRONG AND HAS BEEN REMOVED. This section
    originally closed by asserting that "the traded replay's negative
    Sharpes are that zero minus ~10bp of round-trip cost per event". That
    is true for the (-1,+1) specs and FALSE for the (0,+1) specs. Measured
    directly by re-running each spec at round_trip_bps=0.0:

        spec                       gross SR   net SR   cost gap
        (-1,+1) h63  equal          +0.049    -0.077     -0.126
        (-1,+1) h63  inverse_vol    +0.052    -0.082     -0.134
        (-1,+1) h126 equal          -0.055    -0.166     -0.110
        (-1,+1) h126 inverse_vol    -0.071    -0.188     -0.117
        (0,+1)  h63  equal          -0.272    -0.411     -0.139
        (0,+1)  h63  inverse_vol    -0.266    -0.414     -0.148
        (0,+1)  h126 equal          -0.464    -0.584     -0.120
        (0,+1)  h126 inverse_vol    -0.450    -0.578     -0.127

    Costs are worth a uniform ~0.11-0.15 of Sharpe (cumulative drag
    4.85-7.14pp, not the "~5-7pp" originally written). The (-1,+1) specs
    genuinely are ~zero gross minus that. The (0,+1) specs are NOT: their
    gross Sharpes are -0.27 to -0.46 before a cent of cost, i.e. most of
    their negativity is a real in-sample negative gross drift, not cost.
    The original sentence generalized a (-1,+1) finding to all eight specs.
 2. THE CROSS-CHECK WAS RUN ON ONE WINDOW ONLY. The quintile study quoted
    above is the (-1,+1) window. Re-run on (0,+1) with the same method it
    gives Q1 -0.08%, Q2 -0.58%, Q3 -1.10%, Q4 -0.66%, Q5 -0.23%, a
    Q5-minus-Q1 spread of -0.14pp, naive t = -0.32 -- also indistinguishable
    from zero, also non-monotonic, but NEGATIVE, which is what the (0,+1)
    replay's negative gross Sharpe is made of.

 The re-derivation put the (-1,+1) study at 12,501 events (vs 12,649 here)
 with Q3 at -0.60% (vs -0.66%); spread (+0.16pp) and t (+0.35 vs +0.36)
 matched. The gap is a different-day yfinance pull and was not traced
 further -- it changes no conclusion, and the persisted
 cross_sectional_trial_results rows, not this prose, remain the
 authoritative record.

 Two controls the same pass ran, both passed: (a) POSITIVE CONTROL --
 feeding this exact replay a deliberately look-ahead signal (each event's
 own FUTURE 63-day excess return) produces Sharpe +8.58 (h63) and +6.71
 (h126), so the machinery demonstrably converts a real edge into a large
 positive number and the negative result is a finding, not broken
 plumbing; (b) POINT-IN-TIME TRUNCATION -- recomputing EARs and leg
 assignments on the price panel truncated at 2021-06-30, 2023-06-30 and
 2025-06-30 reproduced every comparable event's leg and EAR exactly
 (0 mismatches out of 1,357 / 2,736 / 4,256), i.e. no classification
 depends on a future price row. Worth recording what that control ALMOST
 caught: anchoring the forward return at day 0 instead of at the entry
 close (day 0 + 1) turns the same pooled study into a +2.46pp spread at
 t = +5.61 -- a textbook "too good to be true" positive manufactured by
 one day of overlap between the ranking window and the measured return.
 This family does not do that; the distance between the honest negative
 and that artifact is exactly one trading day of timing discipline.

The honest read: on S&P 500 large caps, 2019-2026, with a free-data EAR
proxy, there is NO post-earnings-announcement drift to trade -- exactly
what the stated prior expected (Brandt et al.'s own large-cap table,
post-publication attenuation, proxy noise). The one internal regularity
-- the (-1,+1) window dominating (0,+1) at every hold, i.e. the ranking
that includes the pre-announcement leakage day is less bad -- is a
DIAGNOSTIC of where the signal's information lives, not an edge, and no
spec is forwarded on the strength of being least negative. It survives
the correction above: it is now known to be a GROSS difference (+0.05 vs
-0.27 at h63), not a cost artifact, and it is still not tradeable.
"""

import json
import logging
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    DEFAULT_IMPUTED_DELISTING_RETURN,
    DEFAULT_XS_COST_BPS,
    FINANCING_DAYS_PER_YEAR,
    MIN_REPLAY_TRADING_DAYS,
    _compute_delisting_positions,
    _leg_weighted_return,
    _resolve_leg_weights,
)
from app.services.research_lab.deflated_sharpe import (
    DeflatedSharpeResult,
    compute_deflated_sharpe,
)
from app.services.research_lab.global_effective_n import dsr_n_trials
from app.services.research_lab.metrics import sharpe_ratio
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    was_member,
)
from app.services.research_lab.ticker_universe import SCREENING_UNIVERSE

logger = logging.getLogger(__name__)

# --- the family's fixed axes ----------------------------------------------

# (first, last) trading-day offsets of the EAR window relative to day 0.
# (0, 1): close(day0-1) -> close(day0+1). (-1, 1): close(day0-2) ->
# close(day0+1), Brandt et al.'s verified "three-day window centered on
# the announcement date".
PEAD_EAR_WINDOWS: tuple[tuple[int, int], ...] = ((0, 1), (-1, 1))

# 63 = the literature's ~60-trading-day convention (Foster/Olsen/Shevlin
# via Bernard & Thomas 1989); 126 = two quarters, inside the four-quarter
# horizon Brandt et al. cumulate drift over.
PEAD_HOLDING_DAYS: tuple[int, ...] = (63, 126)

# The harness's OWN leg-weighting modes (cross_sectional._resolve_leg_
# weights) -- "equal" can never fall back; "inverse_vol" reads the
# entry-date basis built by build_inverse_vol_basis below and falls back
# for the whole leg when any active member's basis is unusable (degrading
# to equal weight via the constant-signal tie behavior, exactly as the
# index-removal family documents).
PEAD_LEG_WEIGHTINGS: tuple[str, ...] = ("equal", "inverse_vol")

# 2 x 2 x 2, asserted against the built list in _build_pead_family so a
# size drift is an import-time failure, not a silent DSR-denominator change.
PEAD_N_TRIALS = (
    len(PEAD_EAR_WINDOWS) * len(PEAD_HOLDING_DAYS) * len(PEAD_LEG_WEIGHTINGS)
)

PEAD_CITATION = (
    "Ball & Brown, 'An Empirical Evaluation of Accounting Income Numbers' (Journal of Accounting "
    "Research, 1968); Bernard & Thomas, 'Post-Earnings-Announcement Drift: Delayed Price Response "
    "or Risk Premium?' (Journal of Accounting Research, 1989); Bernard & Thomas, 'Evidence that "
    "stock prices do not fully reflect the implications of current earnings for future earnings' "
    "(Journal of Accounting and Economics, 1990); Chan, Jegadeesh & Lakonishok, 'Momentum "
    "Strategies' (Journal of Finance, 1996); Brandt, Kishore, Santa-Clara & Venkatachalam, "
    "'Earnings Announcements are Full of Surprises' (SSRN 909563, 2007 version)"
)

PEAD_FAMILY_NAME = "pead_ear"

# --- fixed design constants (NOT family axes -- see module docstring) -----

# Quintiles, matching Brandt et al.'s verified design.
PEAD_QUANTILE = 0.20

# Trailing window (trading rows of day-0 dates) whose completed EARs form
# the ranking distribution -- the point-in-time analogue of Brandt et
# al.'s prior-quarter breakpoints. 126 rows (~2 quarters) rather than one
# quarter so the window always spans at least one full earnings season
# regardless of where in the reporting cycle an event lands.
PEAD_BREAKPOINT_WINDOW_TRADING_DAYS = 126

# Below this many trailing completed EARs the quintile boundaries are too
# unstable to rank against; the event is skipped (counted, disclosed).
# Same "smallest sample not dominated by a few draws" register as
# deflated_sharpe.MIN_TRIALS_FOR_DSR and DEFAULT_MIN_NAMES_PER_LEG.
PEAD_MIN_BREAKPOINT_OBS = 30

# Two Item 2.02 filings by the same ticker within this many trading rows
# are one announcement (re-files, same-quarter follow-ups); the first wins.
PEAD_DUPLICATE_FILING_GAP_TRADING_DAYS = 5

# 8-K acceptance at/after this hour US/Eastern shifts day 0 to the next
# trading day -- the market could not react until the next session.
PEAD_ANNOUNCEMENT_CUTOFF_HOUR_ET = 16
_EASTERN = ZoneInfo("America/New_York")

# Trailing window for the inverse-vol basis: same 63-trading-day /
# 40-observation convention as the index-removal family and the project's
# other "one quarter" constants. Restated rather than imported for the
# same reason cross_sectional_index_removal gives: the sibling's function
# bakes in its own window constant.
PEAD_VOL_WINDOW_DAYS = 63
PEAD_VOL_MIN_PERIODS = 40

# Calendar days of EDGAR events and prices fetched BEFORE the requested
# start, purely to (a) warm the trailing breakpoint distribution with
# completed EARs and (b) warm the inverse-vol basis. 270 covers the
# 126-row breakpoint window (~6 months) plus the EAR window itself. No
# event with day 0 in the padding is ever ENTERED.
PEAD_WARMUP_PADDING_CALENDAR_DAYS = 270

# --- costs ----------------------------------------------------------------

# Entry + exit on one event's notional: two one-way trades at the
# harness's own equity constant. See the module docstring's COSTS section.
PEAD_ROUND_TRIP_BPS = 2.0 * DEFAULT_XS_COST_BPS

# --- SEC EDGAR access (all verified live 2026-08-28; see docstring) -------

SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

# Identifies the project per SEC fair-access guidance ("Please declare
# your user agent"). The contact token is an explicitly NON-ROUTABLE
# placeholder, not a real mailbox: www.sec.gov's edge 403s any UA without
# an email-shaped token (measured 2026-08-28, see docstring), and this
# project's rules forbid embedding the operator's personal email in
# request headers. Operators running at scale should pass a real contact
# via fetch_item_202_events(user_agent=...).
PEAD_SEC_USER_AGENT = "Aladdin2ResearchLab/0.1 research-contact@aladdin2-project.local"

# SEC's published cap is 10 req/s (verified live 2026-08-28 at
# sec.gov/os/accessing-edgar-data). 0.15s between requests ~= 6.7 req/s.
PEAD_SEC_MIN_REQUEST_INTERVAL_SECONDS = 0.15

# filings.recent is truncated at ~1,000 rows; at or above this count the
# ticker's coverage window is treated as truncated (its earliest recent
# filingDate is a coverage floor, not the start of its history).
_SEC_RECENT_TRUNCATION_ROWS = 1000

# Default on-disk cache for the fetched event list, following
# futures_curve_collector.py's backend/data convention. A committed cache
# makes the production run reproducible without re-hitting EDGAR.
PEAD_EVENT_CACHE_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "pead_edgar_item202_events.json"
)


@dataclass(frozen=True)
class PeadSpec:
    """One pre-declared definition. Deliberately NOT a
    cross_sectional.CrossSectionalSpec, for the identical reason the
    index-removal family gives: that type's required fields (signal_fn,
    lookback_days, rank_fraction, portfolio) describe a periodic
    universe-scan and filling them with placeholders would misdescribe an
    event-driven trade."""

    pattern_id: str
    family: str
    citation: str
    ear_window: tuple[int, int]
    holding_days: int
    leg_weighting: str  # "equal" | "inverse_vol"


def _offset_id(x: int) -> str:
    return f"m{-x}" if x < 0 else str(x)


def _window_id(window: tuple[int, int]) -> str:
    return f"w{_offset_id(window[0])}p{_offset_id(window[1])}"


def _build_pead_family() -> list[PeadSpec]:
    """The full, fixed family: every (ear_window, holding_days,
    leg_weighting) triple. pattern_ids encode all three axes."""
    specs: list[PeadSpec] = []
    for window in PEAD_EAR_WINDOWS:
        for hold in PEAD_HOLDING_DAYS:
            for weighting in PEAD_LEG_WEIGHTINGS:
                specs.append(
                    PeadSpec(
                        pattern_id=(
                            f"pead_ear_{_window_id(window)}_h{hold}_{weighting}"
                        ),
                        family=PEAD_FAMILY_NAME,
                        citation=PEAD_CITATION,
                        ear_window=window,
                        holding_days=hold,
                        leg_weighting=weighting,
                    )
                )
    assert len(specs) == PEAD_N_TRIALS, (
        f"PEAD family has {len(specs)} definitions, not the pre-declared {PEAD_N_TRIALS} -- this "
        "family's entire point is being an exact, fixed enumeration of ear_window x holding_days x "
        "leg_weighting (see module docstring); a size drift here silently changes n_trials for "
        "every future run."
    )
    assert len({s.pattern_id for s in specs}) == len(specs), (
        "pattern_ids must be unique"
    )
    assert all(s.family == PEAD_FAMILY_NAME for s in specs)
    assert {s.ear_window for s in specs} == set(PEAD_EAR_WINDOWS)
    assert {s.holding_days for s in specs} == set(PEAD_HOLDING_DAYS)
    assert {s.leg_weighting for s in specs} == set(PEAD_LEG_WEIGHTINGS)
    return specs


PEAD_FAMILY: list[PeadSpec] = _build_pead_family()


@dataclass
class PeadConfig:
    """Market conventions, split from the specs exactly as
    CrossSectionalConfig / IndexRemovalConfig split them: a spec says what
    to rank and how long to hold, a config says what that costs."""

    round_trip_bps: float = PEAD_ROUND_TRIP_BPS
    # 0.0 = the equity families' shared, disclosed optimism (no observable
    # borrow data); non-zero accrues on gross notional held over calendar
    # days. See the module docstring's COSTS section.
    financing_bps_per_year: float = 0.0
    # ON by default: the short leg is adversely-selected negative-surprise
    # names, the exact population the Shumway imputation exists for (same
    # opt-in reasoning as cross_sectional_patterns_d2.py and the
    # index-removal family).
    impute_delisting_returns: bool = True
    imputed_delisting_return: float = DEFAULT_IMPUTED_DELISTING_RETURN


# --- SEC EDGAR event acquisition ------------------------------------------


@dataclass(frozen=True)
class EarningsEvent:
    """One 8-K filing carrying Item 2.02, as fetched from the submissions
    API. acceptance_utc is the raw acceptanceDateTime string ('' when the
    API row had none)."""

    ticker: str
    cik: int
    accession: str
    filing_date: date
    acceptance_utc: str


@dataclass
class EdgarFetchReport:
    """What the EDGAR pass actually covered -- required output, not a log
    detail, because every gap here is a sample-construction fact."""

    n_tickers_requested: int = 0
    n_tickers_cik_resolved: int = 0
    n_tickers_fetched: int = 0
    n_tickers_fetch_failed: int = 0
    # Tickers whose filings.recent window is truncated (>= ~1,000 rows)
    # AND starts after the requested fetch start -- their early events are
    # missing from the sample, not absent from history.
    n_tickers_coverage_truncated: int = 0
    unresolved_tickers: list[str] = field(default_factory=list)
    failed_tickers: list[str] = field(default_factory=list)


def _sec_get_json(url: str, user_agent: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def load_cik_map(user_agent: str = PEAD_SEC_USER_AGENT) -> dict[str, int]:
    """{ticker: CIK} from SEC's own mapping file. The file's tickers use
    the dash convention for dual-class shares (verified live: 'BRK-B' is
    present as-is), which is also SCREENING_UNIVERSE's convention, so
    lookup is exact-match."""
    raw = _sec_get_json(SEC_COMPANY_TICKERS_URL, user_agent)
    return {row["ticker"]: int(row["cik_str"]) for row in raw.values()}


def _parse_item_202_rows(
    ticker: str, cik: int, submissions: dict, fetch_start: date, end: date
) -> tuple[list[EarningsEvent], bool]:
    """(events, coverage_truncated) from one submissions JSON. Only
    form == '8-K' (never '8-K/A' -- an amendment is not the announcement)
    with '2.02' among its item numbers, filed within [fetch_start, end]."""
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    items = recent.get("items", [])
    filing_dates = recent.get("filingDate", [])
    acceptances = recent.get("acceptanceDateTime", [])
    accessions = recent.get("accessionNumber", [])

    events: list[EarningsEvent] = []
    for i, form in enumerate(forms):
        if form != "8-K":
            continue
        item_field = items[i] if i < len(items) else ""
        if "2.02" not in (item_field or "").split(","):
            continue
        filed = date.fromisoformat(filing_dates[i])
        if not (fetch_start <= filed <= end):
            continue
        events.append(
            EarningsEvent(
                ticker=ticker,
                cik=cik,
                accession=accessions[i] if i < len(accessions) else "",
                filing_date=filed,
                acceptance_utc=(acceptances[i] or "") if i < len(acceptances) else "",
            )
        )

    truncated = False
    if len(forms) >= _SEC_RECENT_TRUNCATION_ROWS and filing_dates:
        earliest_covered = date.fromisoformat(min(filing_dates))
        truncated = earliest_covered > fetch_start
    return events, truncated


def fetch_item_202_events(
    tickers: list[str],
    fetch_start: date,
    end: date,
    user_agent: str = PEAD_SEC_USER_AGENT,
    min_request_interval: float = PEAD_SEC_MIN_REQUEST_INTERVAL_SECONDS,
) -> tuple[list[EarningsEvent], EdgarFetchReport]:
    """One submissions request per CIK-resolved ticker, rate-limited under
    SEC's published 10 req/s fair-access cap. A ticker that fails is
    recorded and skipped, never retried in a tight loop."""
    report = EdgarFetchReport(n_tickers_requested=len(tickers))
    cik_map = load_cik_map(user_agent)
    events: list[EarningsEvent] = []
    last_request = 0.0
    for ticker in tickers:
        cik = cik_map.get(ticker)
        if cik is None:
            report.unresolved_tickers.append(ticker)
            continue
        report.n_tickers_cik_resolved += 1

        elapsed = time.monotonic() - last_request
        if elapsed < min_request_interval:
            time.sleep(min_request_interval - elapsed)
        last_request = time.monotonic()
        try:
            submissions = _sec_get_json(
                SEC_SUBMISSIONS_URL_TEMPLATE.format(cik=cik), user_agent
            )
        except Exception as exc:  # noqa: BLE001 -- record and continue
            logger.warning("EDGAR submissions fetch failed for %s: %s", ticker, exc)
            report.n_tickers_fetch_failed += 1
            report.failed_tickers.append(ticker)
            continue
        report.n_tickers_fetched += 1
        ticker_events, truncated = _parse_item_202_rows(
            ticker, cik, submissions, fetch_start, end
        )
        if truncated:
            report.n_tickers_coverage_truncated += 1
        events.extend(ticker_events)
    return events, report


def save_event_cache(
    events: list[EarningsEvent],
    report: EdgarFetchReport,
    fetch_start: date,
    end: date,
    path: Path = PEAD_EVENT_CACHE_PATH,
) -> None:
    payload = {
        "fetched_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "fetch_start": fetch_start.isoformat(),
        "end": end.isoformat(),
        "report": {
            "n_tickers_requested": report.n_tickers_requested,
            "n_tickers_cik_resolved": report.n_tickers_cik_resolved,
            "n_tickers_fetched": report.n_tickers_fetched,
            "n_tickers_fetch_failed": report.n_tickers_fetch_failed,
            "n_tickers_coverage_truncated": report.n_tickers_coverage_truncated,
            "unresolved_tickers": report.unresolved_tickers,
            "failed_tickers": report.failed_tickers,
        },
        "events": [
            {
                "ticker": e.ticker,
                "cik": e.cik,
                "accession": e.accession,
                "filing_date": e.filing_date.isoformat(),
                "acceptance_utc": e.acceptance_utc,
            }
            for e in events
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def load_event_cache(
    path: Path = PEAD_EVENT_CACHE_PATH,
) -> tuple[list[EarningsEvent], EdgarFetchReport, date, date] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    events = [
        EarningsEvent(
            ticker=row["ticker"],
            cik=int(row["cik"]),
            accession=row["accession"],
            filing_date=date.fromisoformat(row["filing_date"]),
            acceptance_utc=row["acceptance_utc"],
        )
        for row in payload["events"]
    ]
    r = payload["report"]
    report = EdgarFetchReport(
        n_tickers_requested=r["n_tickers_requested"],
        n_tickers_cik_resolved=r["n_tickers_cik_resolved"],
        n_tickers_fetched=r["n_tickers_fetched"],
        n_tickers_fetch_failed=r["n_tickers_fetch_failed"],
        n_tickers_coverage_truncated=r["n_tickers_coverage_truncated"],
        unresolved_tickers=list(r["unresolved_tickers"]),
        failed_tickers=list(r["failed_tickers"]),
    )
    return (
        events,
        report,
        date.fromisoformat(payload["fetch_start"]),
        date.fromisoformat(payload["end"]),
    )


# --- signal construction ---------------------------------------------------


def announcement_day0(event: EarningsEvent, index: pd.DatetimeIndex) -> int | None:
    """Integer row of the first trading session that could have reacted to
    the filing, or None when it falls off the loaded index. Acceptance
    before 16:00 ET on day D -> first row >= D; at/after 16:00 ET, on a
    non-trading day, or with no acceptance timestamp -> first row > D
    (the conservative, never-early direction)."""
    after_close = True
    if event.acceptance_utc:
        try:
            accepted = datetime.fromisoformat(event.acceptance_utc)
            # BUG FIX (found by adversarial verification 2026-08-28, LATENT
            # -- provably a no-op on the cached production sample, where all
            # 15,552 acceptanceDateTime values carry the 'Z' suffix and so
            # parse tz-AWARE): datetime.astimezone() on a tz-NAIVE datetime
            # silently assumes the datetime is in the MACHINE's local
            # timezone, not UTC. This field is named acceptance_utc and the
            # module docstring promises a "UTC -> US/Eastern" conversion, so
            # a naive value reaching astimezone() would have converted from
            # whatever timezone the host happened to be in -- shifting day 0
            # by a session for every affected event, differently on
            # different machines, with no error. Not caught by the build's
            # own tests: every acceptance fixture there is 'Z'-suffixed,
            # exactly like the real data. Stamping UTC on a naive parse
            # makes the code do what the field name and the docstring both
            # already claim it does.
            if accepted.tzinfo is None:
                accepted = accepted.replace(tzinfo=UTC)
            accepted_et = accepted.astimezone(_EASTERN)
            after_close = accepted_et.hour >= PEAD_ANNOUNCEMENT_CUTOFF_HOUR_ET
            base_date = accepted_et.date()
        except ValueError:
            base_date = event.filing_date
    else:
        base_date = event.filing_date
    ts = pd.Timestamp(base_date)
    side = "right" if after_close else "left"
    position = int(np.searchsorted(index.values, ts.to_datetime64(), side=side))
    if position >= len(index):
        return None
    return position


@dataclass(frozen=True)
class ScoredEvent:
    """One announcement with its EAR computed for ONE window. entry_position
    is the row of the EAR window's final close -- the close at which the
    signal is fully determined and the position is established."""

    ticker: str
    day0_position: int
    day0_date: date
    entry_position: int
    entry_date: date
    ear: float


def score_events(
    close: pd.DataFrame,
    benchmark: pd.Series,
    events: list[EarningsEvent],
    window: tuple[int, int],
) -> tuple[list[ScoredEvent], dict[str, int]]:
    """EARs for every event under one window, in entry order, plus
    {rejection reason: count}. Rejections are tradeability/data facts,
    never performance filters. Duplicate 2.02 filings by one ticker within
    PEAD_DUPLICATE_FILING_GAP_TRADING_DAYS rows keep the first only."""
    index = close.index
    n = len(index)
    start_offset, end_offset = window
    bench = benchmark.reindex(index)
    rejected: dict[str, int] = {}

    def _reject(reason: str) -> None:
        rejected[reason] = rejected.get(reason, 0) + 1

    scored: list[ScoredEvent] = []
    last_kept_day0: dict[str, int] = {}
    for event in sorted(events, key=lambda e: (e.ticker, e.filing_date, e.accession)):
        if event.ticker not in close.columns:
            _reject("no price data for ticker")
            continue
        day0 = announcement_day0(event, index)
        if day0 is None:
            _reject("announcement beyond loaded price history")
            continue
        prior = last_kept_day0.get(event.ticker)
        if prior is not None and day0 - prior <= PEAD_DUPLICATE_FILING_GAP_TRADING_DAYS:
            _reject("duplicate filing within gap")
            continue
        window_start = day0 + start_offset - 1
        window_end = day0 + end_offset
        if window_start < 0:
            _reject("EAR window before price history")
            continue
        # Need at least one realized day after the entry close.
        if window_end >= n - 1:
            _reject("announcement too recent for any hold")
            continue
        p0 = close[event.ticker].iloc[window_start]
        p1 = close[event.ticker].iloc[window_end]
        b0 = bench.iloc[window_start]
        b1 = bench.iloc[window_end]
        if not (
            np.isfinite(p0) and np.isfinite(p1) and np.isfinite(b0) and np.isfinite(b1)
        ):
            _reject("no price at EAR window endpoints")
            continue
        if p0 <= 0.0 or b0 <= 0.0:
            _reject("non-positive price at EAR window start")
            continue
        last_kept_day0[event.ticker] = day0
        scored.append(
            ScoredEvent(
                ticker=event.ticker,
                day0_position=day0,
                day0_date=index[day0].date(),
                entry_position=window_end,
                entry_date=index[window_end].date(),
                ear=float(p1 / p0 - b1 / b0),
            )
        )
    scored.sort(key=lambda s: (s.entry_position, s.ticker))
    return scored, rejected


@dataclass(frozen=True)
class ClassifiedEvent:
    """A ScoredEvent assigned to a leg against its own trailing quintile
    breakpoints. leg is 'long' or 'short' -- mid-distribution events are
    never materialized as ClassifiedEvents."""

    ticker: str
    day0_position: int
    day0_date: date
    entry_position: int
    entry_date: date
    ear: float
    leg: str


@dataclass
class ClassificationCounts:
    n_scored: int = 0
    n_eligible_day0: int = 0  # day 0 at/after formation start
    n_skipped_thin_breakpoints: int = 0
    n_long: int = 0
    n_short: int = 0
    n_middle: int = 0


def classify_events(
    scored: list[ScoredEvent],
    formation_start: date,
) -> tuple[list[ClassifiedEvent], ClassificationCounts]:
    """Long / short / nothing per event, against the trailing distribution
    of already-completed sibling EARs -- see the module docstring's RANKING
    section. Point-in-time by construction: an event's breakpoint set is
    exactly the events whose EAR windows completed STRICTLY BEFORE its own
    entry close (scored is entry-ordered, so a single forward walk gives
    that set -- same-close siblings are deliberately excluded, which also
    excludes the event itself without a special case), restricted to day 0
    within the trailing PEAD_BREAKPOINT_WINDOW_TRADING_DAYS rows. Warm-up
    events (day 0 before formation_start) feed the distribution but are
    never entered."""
    counts = ClassificationCounts(n_scored=len(scored))
    classified: list[ClassifiedEvent] = []
    completed_day0: list[int] = []
    completed_ear: list[float] = []
    cursor = 0  # first scored index NOT yet folded into the completed set

    for event in scored:
        while (
            cursor < len(scored)
            and scored[cursor].entry_position < event.entry_position
        ):
            completed_day0.append(scored[cursor].day0_position)
            completed_ear.append(scored[cursor].ear)
            cursor += 1
        if event.day0_date < formation_start:
            continue
        counts.n_eligible_day0 += 1

        floor = event.day0_position - PEAD_BREAKPOINT_WINDOW_TRADING_DAYS
        trailing = [
            ear for d0, ear in zip(completed_day0, completed_ear) if d0 >= floor
        ]
        if len(trailing) < PEAD_MIN_BREAKPOINT_OBS:
            counts.n_skipped_thin_breakpoints += 1
            continue
        low, high = np.quantile(trailing, [PEAD_QUANTILE, 1.0 - PEAD_QUANTILE])
        if event.ear >= high:
            leg = "long"
            counts.n_long += 1
        elif event.ear <= low:
            leg = "short"
            counts.n_short += 1
        else:
            counts.n_middle += 1
            continue
        classified.append(
            ClassifiedEvent(
                ticker=event.ticker,
                day0_position=event.day0_position,
                day0_date=event.day0_date,
                entry_position=event.entry_position,
                entry_date=event.entry_date,
                ear=event.ear,
                leg=leg,
            )
        )
    return classified, counts


def build_inverse_vol_basis(close: pd.DataFrame) -> pd.DataFrame:
    """1 / trailing realized volatility per ticker, aligned to `close` --
    the entry-date basis the "inverse_vol" specs weight each leg by through
    cross_sectional._resolve_leg_weights. Same formula as the sibling
    event-driven family (rolling ddof=1 std of daily returns, reciprocated,
    non-finite NaNed), restated with this family's own window constants for
    the coupling reason both siblings document. Point-in-time by
    construction: a rolling std at row i reads only rows <= i, and the
    replay reads each event's basis at ITS OWN entry row."""
    returns = close.pct_change(fill_method=None)
    vol = returns.rolling(PEAD_VOL_WINDOW_DAYS, min_periods=PEAD_VOL_MIN_PERIODS).std(
        ddof=1
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        basis = 1.0 / vol
    return basis.replace([np.inf, -np.inf], np.nan)


# --- the replay ------------------------------------------------------------


@dataclass
class PeadBacktestResult:
    status: str  # "ok" | "no_events" | "insufficient_history"
    daily_returns: pd.Series
    n_events_entered: int = 0
    n_events_superseded: int = 0
    n_events_delisted_mid_hold: int = 0
    total_cost: float = 0.0
    total_financing_cost: float = 0.0
    # Days with BOTH legs populated (the book's trade actually on) /
    # days with exactly one leg populated (flat by design, counted) over
    # the realized series length.
    n_invested_days: int = 0
    n_one_sided_days: int = 0
    n_weight_fallback_days: int = 0
    mean_long_leg_size: float = 0.0
    mean_short_leg_size: float = 0.0


def run_pead_backtest(
    close: pd.DataFrame,
    entered: list[ClassifiedEvent],
    spec: PeadSpec,
    config: PeadConfig,
    basis: pd.DataFrame | None = None,
) -> PeadBacktestResult:
    """One spec's event-driven replay. Every entered event opens 1.0 of
    leg notional in its leg at its entry close and closes spec.holding_days
    trading days later (or at the data's end, or on delisting, or when a
    newer traded event on the same ticker supersedes it). Each day both
    legs' weights are resolved by cross_sectional._resolve_leg_weights
    (constant signal -- every event in a leg carries the same hypothesis,
    so the documented tie behavior makes the inverse-vol fallback degrade
    to equal weight); the day's gross return is long-leg weighted mean
    minus short-leg weighted mean via _leg_weighted_return, or 0.0 when
    either leg is empty (one-sided days are counted, never traded naked).
    An event's whole round trip lands on its FIRST realized day; financing
    (default 0.0) accrues on gross notional held over calendar days."""
    if spec.leg_weighting == "inverse_vol" and basis is None:
        raise ValueError(
            f"{spec.pattern_id} has leg_weighting='inverse_vol' but no inverse-vol basis was "
            "supplied. Without it every day would silently take the fallback and the run would "
            "report itself as inverse-vol weighted while being equal weighted throughout."
        )
    if not entered:
        return PeadBacktestResult(
            status="no_events", daily_returns=pd.Series(dtype=float)
        )

    index = close.index
    n = len(index)
    first_entry = min(e.entry_position for e in entered)
    if first_entry >= n - 1:
        return PeadBacktestResult(
            status="insufficient_history", daily_returns=pd.Series(dtype=float)
        )

    stock_returns = close.pct_change(fill_method=None)
    round_trip = config.round_trip_bps / 10_000.0
    financing_per_day = (
        config.financing_bps_per_year / 10_000.0
    ) / FINANCING_DAYS_PER_YEAR

    delisting_by_position: dict[int, list[str]] = {}
    if config.impute_delisting_returns:
        for ticker, position in _compute_delisting_positions(close).items():
            delisting_by_position.setdefault(position, []).append(ticker)

    open_at: dict[int, list[ClassifiedEvent]] = {}
    entry_basis: dict[tuple[str, int], float] = {}
    for event in entered:
        open_at.setdefault(event.entry_position, []).append(event)
        if basis is not None and event.ticker in basis.columns:
            entry_basis[(event.ticker, event.entry_position)] = float(
                basis[event.ticker].iloc[event.entry_position]
            )

    active: dict[str, ClassifiedEvent] = {}
    exit_position: dict[str, int] = {}
    # Tickers whose CURRENT event has already paid its round trip. An
    # event pays exactly once, on the first day its trade is actually ON
    # (both legs populated) -- an event whose whole hold falls inside a
    # one-sided (flat-by-design) stretch never trades and never pays. A
    # superseding event is a new trade and pays its own round trip
    # (conservative for a same-leg supersession, which in practice would
    # only re-weight).
    charged: set[str] = set()

    dates: list[pd.Timestamp] = []
    nets: list[float] = []
    total_cost = 0.0
    total_financing = 0.0
    n_invested = 0
    n_one_sided = 0
    n_fallback = 0
    n_superseded = 0
    n_delisted = 0
    long_sizes: list[int] = []
    short_sizes: list[int] = []

    def _leg(
        tickers: list[str], day: pd.Series, weighting: str
    ) -> tuple[float, dict[str, float], bool]:
        signal = pd.Series(0.0, index=tickers, dtype=float)
        basis_row: pd.Series | None = None
        if weighting == "inverse_vol":
            basis_row = pd.Series(
                {
                    t: entry_basis.get((t, active[t].entry_position), np.nan)
                    for t in tickers
                },
                dtype=float,
            )
        weights, used_fallback = _resolve_leg_weights(
            tickers,
            signal,
            higher_is_stronger=True,
            leg_weighting=weighting,  # type: ignore[arg-type]
            market_cap=None,
            weight_basis=basis_row,
        )
        return _leg_weighted_return(day, weights), weights, used_fallback

    for j in range(first_entry + 1, n):
        for event in open_at.get(j - 1, ()):
            if event.ticker in active:
                n_superseded += 1
            active[event.ticker] = event
            exit_position[event.ticker] = min(
                event.entry_position + spec.holding_days, n - 1
            )
            charged.discard(event.ticker)

        if not active:
            dates.append(index[j])
            nets.append(0.0)
            continue

        day = stock_returns.iloc[j]
        delisting_today = delisting_by_position.get(j)
        if delisting_today:
            hit = [t for t in delisting_today if t in active]
            if hit:
                day = day.copy()
                for ticker in hit:
                    day[ticker] = config.imputed_delisting_return
                n_delisted += len(hit)

        longs = sorted(t for t, e in active.items() if e.leg == "long")
        shorts = sorted(t for t, e in active.items() if e.leg == "short")

        if not longs or not shorts:
            # One-sided book: flat by design, not a naked single leg.
            # Costs are not charged on a flat day either -- an uncharged
            # event pays on the first day its trade is actually on.
            n_one_sided += 1
            dates.append(index[j])
            nets.append(0.0)
            for ticker in list(active):
                if j >= exit_position[ticker] or (
                    delisting_today and ticker in delisting_today
                ):
                    del active[ticker]
                    del exit_position[ticker]
                    charged.discard(ticker)
            continue

        long_return, long_weights, long_fb = _leg(longs, day, spec.leg_weighting)
        short_return, short_weights, short_fb = _leg(shorts, day, spec.leg_weighting)
        if long_fb or short_fb:
            n_fallback += 1
        gross = long_return - short_return

        cost_today = 0.0
        for weights in (long_weights, short_weights):
            for name, w in weights.items():
                if name not in charged:
                    cost_today += w * round_trip
                    charged.add(name)
        financing_today = 0.0
        if financing_per_day:
            calendar_days = float((index[j] - index[j - 1]).days)
            financing_today = financing_per_day * 2.0 * calendar_days

        net = gross - cost_today - financing_today
        total_cost += cost_today
        total_financing += financing_today
        n_invested += 1
        long_sizes.append(len(longs))
        short_sizes.append(len(shorts))
        dates.append(index[j])
        nets.append(net)

        for ticker in list(active):
            if j >= exit_position[ticker] or (
                delisting_today and ticker in delisting_today
            ):
                del active[ticker]
                del exit_position[ticker]
                charged.discard(ticker)

    daily = pd.Series(nets, index=pd.DatetimeIndex(dates), dtype=float)
    return PeadBacktestResult(
        status="ok",
        daily_returns=daily,
        n_events_entered=len(entered),
        n_events_superseded=n_superseded,
        n_events_delisted_mid_hold=n_delisted,
        total_cost=total_cost,
        total_financing_cost=total_financing,
        n_invested_days=n_invested,
        n_one_sided_days=n_one_sided,
        n_weight_fallback_days=n_fallback,
        mean_long_leg_size=float(np.mean(long_sizes)) if long_sizes else 0.0,
        mean_short_leg_size=float(np.mean(short_sizes)) if short_sizes else 0.0,
    )


# --- screening / DSR -------------------------------------------------------


@dataclass
class PeadScreeningResult:
    pattern_id: str
    family: str
    citation: str
    ear_window: tuple[int, int]
    holding_days: int
    leg_weighting: str
    n_events_scored: int
    n_events_entered: int
    n_events_long: int
    n_events_short: int
    n_events_superseded: int
    n_events_skipped_thin_breakpoints: int
    n_events_delisted_mid_hold: int
    n_trading_days: int
    n_invested_days: int
    n_one_sided_days: int
    invested_fraction: float
    mean_long_leg_size: float
    mean_short_leg_size: float
    sharpe_annualized: float
    total_cost_drag: float
    total_financing_drag: float
    deflated_sharpe: DeflatedSharpeResult
    n_weight_fallback_days: int = 0


@dataclass(frozen=True)
class PeadSampleDisclosure:
    """The sample-construction and independence caution as typed data,
    recomputed from the real inputs on every run -- the discipline every
    event-driven sibling here applies to its own small-sample problem."""

    n_tickers_requested: int
    n_tickers_cik_resolved: int
    n_tickers_fetched: int
    n_tickers_coverage_truncated: int
    n_raw_events: int
    n_events_after_membership_gate: int
    n_tickers_priced: int
    scored_by_window: dict[str, int]
    rejected_by_window: dict[str, dict[str, int]]
    classification_by_window: dict[str, dict[str, int]]
    first_event_date: date | None
    last_event_date: date | None
    n_distinct_day0_dates: int
    text: str


def build_pead_sample_disclosure(
    edgar: EdgarFetchReport,
    n_raw_events: int,
    n_after_membership: int,
    n_tickers_priced: int,
    scored_by_window: dict[str, list[ScoredEvent]],
    rejected_by_window: dict[str, dict[str, int]],
    counts_by_window: dict[str, ClassificationCounts],
) -> PeadSampleDisclosure:
    all_scored = [s for scored in scored_by_window.values() for s in scored]
    day0_dates = sorted({s.day0_date for s in all_scored})
    scored_counts = {w: len(v) for w, v in scored_by_window.items()}
    classification = {
        w: {
            "n_scored": c.n_scored,
            "n_eligible_day0": c.n_eligible_day0,
            "n_skipped_thin_breakpoints": c.n_skipped_thin_breakpoints,
            "n_long": c.n_long,
            "n_short": c.n_short,
            "n_middle": c.n_middle,
        }
        for w, c in counts_by_window.items()
    }
    text = (
        f"PEAD-EAR SAMPLE DISCLOSURE -- read before trusting any Sharpe or DSR below. Universe: "
        f"{edgar.n_tickers_requested} tickers from TODAY's S&P 500 snapshot "
        f"(ticker_universe.SCREENING_UNIVERSE), of which {edgar.n_tickers_cik_resolved} resolved a "
        f"CIK in SEC's own mapping file and {edgar.n_tickers_fetched} returned a submissions JSON; "
        f"{edgar.n_tickers_coverage_truncated} tickers' EDGAR 'recent' windows are truncated and "
        f"start after the requested fetch start, so their early events are missing from the sample "
        f"(not from history). {n_raw_events} 8-K Item 2.02 filings were found in-window, "
        f"{n_after_membership} survive the point-in-time membership gate (was_member at the filing "
        f"date), and {n_tickers_priced} tickers resolved yfinance prices. THE GATE CANNOT RESTORE "
        f"DEPARTED MEMBERS: names that left the index before the snapshot are absent entirely, and "
        f"since departures skew toward deteriorating companies whose negative surprises would "
        f"populate the SHORT leg, the short side of every number below is measured on a "
        f"survivorship-thinned population. Scored events per window: {scored_counts}. Events "
        f"cluster in quarterly reporting seasons and holds of 63-126 trading days overlap heavily, "
        f"so consecutive daily returns share most of their constituents -- the honest unit of "
        f"independent information is closer to the number of distinct announcement dates "
        f"({len(day0_dates)}) spread over ~4 reporting seasons/year than to the daily observation "
        f"count that feeds the Sharpe and the DSR. This is a SEPARATE caution from the DSR's own "
        f"n_trials={PEAD_N_TRIALS} multiple-comparisons correction; neither substitutes for the "
        f"other. Finally, the whole sample is S&P 500 large caps in 2019-2026: Brandt et al.'s own "
        f"top-1000 table shows the EAR effect 'considerably reduced' in large caps, so the prior "
        f"going in is modest and a strong positive here should be disbelieved before it is "
        f"believed."
    )
    return PeadSampleDisclosure(
        n_tickers_requested=edgar.n_tickers_requested,
        n_tickers_cik_resolved=edgar.n_tickers_cik_resolved,
        n_tickers_fetched=edgar.n_tickers_fetched,
        n_tickers_coverage_truncated=edgar.n_tickers_coverage_truncated,
        n_raw_events=n_raw_events,
        n_events_after_membership_gate=n_after_membership,
        n_tickers_priced=n_tickers_priced,
        scored_by_window=scored_counts,
        rejected_by_window=rejected_by_window,
        classification_by_window=classification,
        first_event_date=day0_dates[0] if day0_dates else None,
        last_event_date=day0_dates[-1] if day0_dates else None,
        n_distinct_day0_dates=len(day0_dates),
        text=text,
    )


@dataclass
class PeadScreeningSummary:
    results: list[PeadScreeningResult]
    missing_price_data: list[str]
    sample: PeadSampleDisclosure
    cost_disclosure: str


def _build_cost_disclosure(config: PeadConfig) -> str:
    return (
        f"COST DISCLOSURE. {config.round_trip_bps}bp round trip per event (2 x the harness's own "
        f"DEFAULT_XS_COST_BPS one-way equity constant -- every name traded is a current S&P 500 "
        f"member, the population that constant was declared for), charged ONCE PER EVENT on its "
        f"first realized day, entry and exit together. Financing: "
        f"{config.financing_bps_per_year}bp/yr -- the equity families' shared convention, and the "
        f"same DISCLOSED OPTIMISM documented in cross_sectional.py: the short leg's real borrow "
        f"cost is unobservable with free data, and this family's short leg is negative-surprise "
        f"names, some of which will be hard-to-borrow exactly when shorted. Daily renormalization "
        f"as events enter/leave is not charged (the harness's stated zero-cost-rebalancing "
        f"convention), so true costs are HIGHER than the reported drag."
    )


def screen_pead_family(
    close: pd.DataFrame,
    benchmark: pd.Series,
    events: list[EarningsEvent],
    formation_start: date,
    config: PeadConfig,
    specs: list[PeadSpec] | None = None,
) -> tuple[
    list[PeadScreeningResult],
    dict[str, list[ScoredEvent]],
    dict[str, dict[str, int]],
    dict[str, ClassificationCounts],
]:
    """One Sharpe per spec, DSR-corrected for the family's pre-declared
    size. n_trials is len(specs) -- the family's literal pre-declared size,
    never shrunk to however many specs cleared the data floors. sigma_sr is
    the ddof=1 std of every sibling spec's own Sharpe from this same pass.
    Scoring and classification are computed once per WINDOW (they do not
    depend on holding_days or weighting) and shared across the specs."""
    specs = specs if specs is not None else PEAD_FAMILY
    # POOLED DENOMINATOR (2026-09-04). len(specs) is this FAMILY's search;
    # it was never the whole search. dsr_n_trials raises it to the
    # project-wide effectively-independent trial count (ONC E[K] over every
    # persisted trial's realized returns) whenever that is larger, and only
    # ever larger -- see global_effective_n.py's "THE ONE GUARD".
    # `if specs else 0` because dsr_n_trials REFUSES a grid size of 0 (a
    # caller with no pre-declared family at all), and an empty spec list is
    # a legitimate no-op every one of these screens already returns [] for.
    n_trials = dsr_n_trials(len(specs)) if specs else 0
    basis = (
        build_inverse_vol_basis(close)
        if any(s.leg_weighting == "inverse_vol" for s in specs)
        else None
    )

    scored_by_window: dict[str, list[ScoredEvent]] = {}
    rejected_by_window: dict[str, dict[str, int]] = {}
    entered_by_window: dict[str, list[ClassifiedEvent]] = {}
    counts_by_window: dict[str, ClassificationCounts] = {}
    for window in {s.ear_window for s in specs}:
        wid = _window_id(window)
        scored, rejected = score_events(close, benchmark, events, window)
        classified, counts = classify_events(scored, formation_start)
        scored_by_window[wid] = scored
        rejected_by_window[wid] = rejected
        entered_by_window[wid] = classified
        counts_by_window[wid] = counts

    replays: dict[str, PeadBacktestResult] = {}
    for spec in specs:
        result = run_pead_backtest(
            close, entered_by_window[_window_id(spec.ear_window)], spec, config, basis
        )
        if result.status != "ok" or len(result.daily_returns) < MIN_REPLAY_TRADING_DAYS:
            continue
        replays[spec.pattern_id] = result

    sharpes = {pid: sharpe_ratio(res.daily_returns) for pid, res in replays.items()}
    sigma_sr = (
        float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None
    )

    spec_by_id = {spec.pattern_id: spec for spec in specs}
    results: list[PeadScreeningResult] = []
    for pattern_id, replay in replays.items():
        spec = spec_by_id[pattern_id]
        wid = _window_id(spec.ear_window)
        counts = counts_by_window[wid]
        n_days = len(replay.daily_returns)
        results.append(
            PeadScreeningResult(
                pattern_id=pattern_id,
                family=spec.family,
                citation=spec.citation,
                ear_window=spec.ear_window,
                holding_days=spec.holding_days,
                leg_weighting=spec.leg_weighting,
                n_events_scored=counts.n_scored,
                n_events_entered=replay.n_events_entered,
                n_events_long=counts.n_long,
                n_events_short=counts.n_short,
                n_events_superseded=replay.n_events_superseded,
                n_events_skipped_thin_breakpoints=counts.n_skipped_thin_breakpoints,
                n_events_delisted_mid_hold=replay.n_events_delisted_mid_hold,
                n_trading_days=n_days,
                n_invested_days=replay.n_invested_days,
                n_one_sided_days=replay.n_one_sided_days,
                invested_fraction=(replay.n_invested_days / n_days) if n_days else 0.0,
                mean_long_leg_size=replay.mean_long_leg_size,
                mean_short_leg_size=replay.mean_short_leg_size,
                sharpe_annualized=sharpes[pattern_id],
                total_cost_drag=replay.total_cost,
                total_financing_drag=replay.total_financing_cost,
                deflated_sharpe=compute_deflated_sharpe(
                    sharpes[pattern_id], replay.daily_returns, n_trials, sigma_sr
                ),
                n_weight_fallback_days=replay.n_weight_fallback_days,
            )
        )

    results.sort(key=lambda r: r.sharpe_annualized, reverse=True)
    return results, scored_by_window, rejected_by_window, counts_by_window


PEAD_BENCHMARK_TICKER = "SPY"


def run_pead_screening(
    start: date,
    end: date,
    provider: YFinanceProvider | None = None,
    config: PeadConfig | None = None,
    events: list[EarningsEvent] | None = None,
    edgar_report: EdgarFetchReport | None = None,
    tickers: list[str] | None = None,
) -> PeadScreeningSummary:
    """THE production entry point -- mirrors
    run_index_removal_screening's shape (same provider contract, same
    start-date guard, same disclosure-is-part-of-the-result convention).

    `start` must be >= MEMBERSHIP_DATA_START, because every event is gated
    by point-in-time membership and was_member answers a silent False
    before coverage. Events and prices are fetched with
    PEAD_WARMUP_PADDING_CALENDAR_DAYS of lead-in purely to warm the
    trailing breakpoint distribution and the inverse-vol basis; no event
    with day 0 before `start` is ever entered.

    Pass `events` (+ `edgar_report`) to reuse a cached EDGAR pass (see
    save_event_cache / load_event_cache); omitting them fetches live,
    rate-limited under SEC's published fair-access cap."""
    if start < MEMBERSHIP_DATA_START:
        raise ValueError(
            f"PEAD screening start {start.isoformat()} predates point-in-time membership coverage "
            f"({MEMBERSHIP_DATA_START.isoformat()}) -- the was_member gate would silently answer "
            "False for every event before it."
        )
    provider = provider if provider is not None else YFinanceProvider()
    config = config if config is not None else PeadConfig()
    universe = tickers if tickers is not None else list(SCREENING_UNIVERSE)

    fetch_start = start - timedelta(days=PEAD_WARMUP_PADDING_CALENDAR_DAYS)
    if events is None:
        events, edgar_report = fetch_item_202_events(universe, fetch_start, end)
    if edgar_report is None:
        edgar_report = EdgarFetchReport(n_tickers_requested=len(universe))
    n_raw = len(events)

    # Point-in-time membership gate, applied at the FILING date (day 0 is
    # within a row or two of it and membership intervals are month-scale,
    # so filing-date membership is the right granularity and needs no
    # price index to evaluate).
    events = [e for e in events if was_member(e.ticker, e.filing_date)]
    n_after_membership = len(events)

    event_tickers = sorted({e.ticker for e in events})
    frames, missing = provider.get_daily_ohlcv(event_tickers, fetch_start, end)
    if not frames:
        sample = build_pead_sample_disclosure(
            edgar_report, n_raw, n_after_membership, 0, {}, {}, {}
        )
        return PeadScreeningSummary(
            results=[],
            missing_price_data=missing,
            sample=sample,
            cost_disclosure=_build_cost_disclosure(config),
        )
    close = frames["close"]

    bench_frames, bench_missing = provider.get_daily_ohlcv(
        [PEAD_BENCHMARK_TICKER], fetch_start, end
    )
    if (
        bench_missing
        or not bench_frames
        or PEAD_BENCHMARK_TICKER not in bench_frames["close"].columns
    ):
        raise ValueError(
            f"The {PEAD_BENCHMARK_TICKER} benchmark resolved no price data. EAR is defined as the "
            "stock's announcement-window return MINUS the benchmark's, so without it the signal "
            "does not exist -- failing loudly rather than silently ranking on raw returns, which "
            "would be a different (market-direction-contaminated) signal than this family declares."
        )
    benchmark = bench_frames["close"][PEAD_BENCHMARK_TICKER]

    results, scored_by_window, rejected_by_window, counts_by_window = (
        screen_pead_family(close, benchmark, events, start, config)
    )
    sample = build_pead_sample_disclosure(
        edgar_report,
        n_raw,
        n_after_membership,
        len(close.columns),
        scored_by_window,
        rejected_by_window,
        counts_by_window,
    )
    return PeadScreeningSummary(
        results=results,
        missing_price_data=missing,
        sample=sample,
        cost_disclosure=_build_cost_disclosure(config),
    )
