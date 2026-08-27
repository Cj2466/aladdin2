"""Buyback / dilution (NET SHARE ISSUANCE) cross-sectional family: rank the
S&P 500 point-in-time cross-section by the trailing change in split-adjusted
shares outstanding, long the shrinkers (buybacks), short the growers
(dilution), expressed against cross_sectional.py's harness.

Structurally this module is cross_sectional_ivol.py's closest sibling — same
equity universe, same point-in-time membership gate, and the same
get_shares_full plumbing — with one decisive difference. Build D1 used share
counts as a WEIGHT (market cap, a level, whose errors mostly move a leg's
weights around). This family uses share counts as the SIGNAL ITSELF (a
trailing ratio, whose errors decide which decile a name lands in). Every
data defect that was a second-order weighting nuisance for D1 is a
first-order correctness problem here, which is why the two defects below are
handled structurally rather than disclosed.

CITATIONS:
 * Ikenberry, D., Lakonishok, J. & Vermaelen, T., "Market Underreaction to
   Open Market Share Repurchases" (Journal of Financial Economics, 1995):
   firms announcing open-market repurchases earn significant positive
   abnormal returns over the FOLLOWING FOUR YEARS, i.e. the market
   under-reacts to the repurchase signal. This is the long-horizon,
   slow-decay character of the effect and the reason this family's holding
   periods are quarters and years rather than weeks.
 * Pontiff, J. & Woodgate, A., "Share Issuance and Cross-Sectional Returns"
   (Journal of Finance, 2008): THE canonical cross-sectional construction
   and this family's primary reference. Sorting on the trailing (typically
   one-year) log growth in SPLIT-ADJUSTED shares outstanding produces a
   monotone cross-section of subsequent returns — issuers underperform,
   repurchasers outperform — and the effect subsumes much of the size and
   book-to-market predictability in post-1970 US data. The paper is explicit
   that the share count must be SPLIT-ADJUSTED before differencing, which is
   exactly defect (1) below.
 * Daniel, K. & Titman, S., "Market Reactions to Tangible and Intangible
   Information" (Journal of Finance, 2006): the "composite issuance" measure
   — the part of a firm's market-cap growth not explained by its stock
   return, which is share issuance by construction — predicts returns
   negatively over multi-year horizons. The reason a lookback LONGER than
   one year is a pre-declared family member here rather than an arbitrary
   extra.
 * Fama, E. F. & French, K. R., "Dissecting Anomalies" (Journal of Finance,
   2008): net share issuance survives their own sorting-and-regression
   gauntlet as one of the few anomalies that is reliably present in
   micro-caps, small caps AND big caps — i.e. not a small-stock artifact.
   That robustness is why a large-cap-only universe (the S&P 500 is all this
   project has point-in-time membership for) is a legitimate place to look
   for it, rather than a universe the effect was never claimed to live in.

DIRECTION: shrinking share count -> long. select_leg_tickers's convention
(top-of-signal == long) is honored by NEGATING the log issuance, exactly as
cross_sectional_ivol.signal_idiosyncratic_volatility negates volatility and
cross_sectional_fx.signal_fx_long_run_reversal negates momentum. No
reverse=True variants are declared, for the reason every prior round gives:
a long-short decile portfolio is antisymmetric under direction reversal up
to (identical) costs, so a reversed variant would double n_trials while
adding zero information.

============================================================================
THE DATA HAS TWO REAL DEFECTS. BOTH ARE HANDLED. NEITHER IS OPTIONAL.
============================================================================
Both were re-verified live against yfinance on 2026-08-27 by this module's
author, not inherited from a scouting note.

(1) SPLITS CONTAMINATE THE RAW SHARE COUNTS, and for a signal that IS the
    trailing share-count ratio this is not a distortion — it is a sign
    error large enough to invert a name's decile.

    Confirmed on real tickers. GE did a 1-for-8 REVERSE split on 2021-08-02
    (yfinance ratio 0.125); its raw get_shares_full series reads 8.7813e9 on
    2021-07-28 and 1.09766e9 on 2021-08-02 — an 8.00x drop. Uncorrected, a
    trailing one-year share-count change measured in early 2022 reads
    -87.5% for GE: the largest apparent buyback in the entire S&P 500, top
    decile, maximum long weight. GE bought back nothing of the kind; the
    company's share count barely moved.

    ANET is the mirror image. Its 4-for-1 split had ex-date 2021-11-18 and
    the share series switched five days later, on 2021-11-23, from 7.8174e7
    to 3.0730e8 — a 3.93x jump. Uncorrected, ANET's trailing one-year change
    reads about +300%: the largest apparent dilution in the universe, bottom
    decile, maximum short weight. Again, entirely fictional.

    So an uncorrected run does not merely add noise. It reliably routes
    reverse-splitters to the LONG leg and forward-splitters to the SHORT
    leg — a systematic, non-random misassignment of exactly the mega-cap
    names (AAPL, NVDA, AMZN, GOOGL, TSLA all split inside this window) that
    a decile portfolio leans hardest on.

    THE FIX IS NOT REINVENTED HERE. This is the same class of bug found and
    fixed in Build D1 on 2026-08-27 (commit aad5bf8, "Fix Build D1's
    market-cap calculation mixing adjusted price with raw shares"), and this
    module reuses that fix's actual implementation —
    cross_sectional_ivol.split_adjust_share_counts, imported below, not
    copied and not re-derived. It restates a raw as-filed count series into
    one continuous basis by locating each split's boundary from the SERIES'
    OWN jump rather than from the ex-date (yfinance's switch can lead the
    ex-date by weeks or lag it by a full filing cycle, both measured), and
    applies no adjustment at all when the series shows no jump (yfinance
    sometimes serves a series already restated onto today's basis, where
    adjusting would CREATE the discontinuity). See that function's docstring
    for the measured residual: over the 224 split events in this project's
    2015-2026 S&P 500 universe, 7 remain discontinuous by more than 1.5x,
    mostly genuine simultaneous corporate actions (HLT/AIV/MTCH spin-offs)
    rather than adjustment failures.

    WHY THE SAME FUNCTION IS THE RIGHT ONE DESPITE THE DIFFERENT JOB. D1
    needed the counts on the PRICE's basis (to multiply). This family needs
    the counts on ONE INTERNALLY CONSISTENT basis (to difference). Restating
    everything into today's units satisfies both: today's units are the
    basis Yahoo's back-adjusted price series is already on, and any single
    consistent basis makes a ratio meaningful. There is no second, different
    correction to invent.

    ONE HONEST WRINKLE, disclosed rather than hidden: split_adjust_share_
    counts locates a boundary by scanning a window around the ex-date that
    extends up to 120 days BEFORE it, so for a split whose count was
    restated early, dates shortly before the ex-date are expressed in
    post-split units. That is not this module adding future information —
    the vendor's own dated series had already switched on those dates, so a
    real-time reader of it would have seen the same numbers — and the
    signal here is a RATIO, which is invariant to a basis change that
    covers both of its endpoints. It bites only in the narrow case where a
    detected boundary falls inside a formation's lookback window while the
    ex-date falls outside it. The alternative, leaving an 8x fake jump in
    the ranking variable, is worse by orders of magnitude.

    Spin-offs recorded by Yahoo as "splits" (GE carries three: 1.040 in
    2019 for Wabtec, 1.281 in 2023 for GE HealthCare, 1.253 in 2024 for GE
    Vernova) are handled correctly by the same mechanism and for free: those
    are PRICE adjustments, the share count does not jump by those ratios, no
    matching jump is found, and no adjustment is applied. That is the
    "NO JUMP FOUND -> NO ADJUSTMENT" rule doing exactly the job it was
    written for, on a case D1 never had to think about.

(2) THE SERIES IS GENUINELY STEPWISE AND ITS DENSITY IS WILDLY UNEVEN — so
    it must be forward-filled as a STEP FUNCTION and never interpolated, a
    stale step must eventually be refused rather than carried forever, AND
    a window containing no new filing must be refused rather than reported
    as a confident zero.

    Measured live 2026-08-27, over this project's own real 607-ticker
    priced point-in-time S&P 500 universe, not on a couple of hand-picked
    names.

    THE FLOOR. get_shares_full effectively begins in late 2015 whatever
    start is requested: asked for 2015-01-01, 587 of the 607 tickers have
    their first observation on or after 2015-10-01 (median first observation
    2015-11-05; 5th percentile 2015-10-09), and the 20 that start earlier
    carry EXACTLY ONE stray row each before joining the same late-2015
    cluster (LLY 2015-04-23, GEN 2015-05-08, MRVL 2015-06-04, ..., PAYX
    2015-09-30). Asked for 2010-01-01 the answer is the same: MSFT
    2015-10-23, AAPL 2015-10-28, ANET 2015-11-06, GE 2015-11-20. The scout's
    "hard floor at ~2015-09/10" is therefore very nearly right and slightly
    overstated — it is a hard floor for 97% of the universe and a
    one-row-earlier soft edge for the rest, and nothing in this module may
    lean on that stray row.

    THE DENSITY. Median observations per ticker per year: 1 (2015), 5
    (2016), 4 (2017), 22 (2018), 107 (2019), 26 (2020), 19 (2021), 24
    (2022), 58 (2023), 146 (2024), 132 (2025). Pooled gaps between
    consecutive observations: median 2 days, p90 11, p99 91, MAX 3,220.
    ANET has ZERO rows in all of 2022; AAPL has 3 in all of 2016.

    THREE consequences, all load-bearing:
      * NO INTERPOLATION, EVER. A linear or spline fill between two filings
        eleven months apart would manufacture a smooth, gently-trending
        share count that was never filed and could not have been known on
        any day between them — turning a signal about corporate actions
        into a signal about a smoothing kernel, and giving every such
        ticker a small non-zero issuance reading on days when the true
        point-in-time answer is "unchanged since the last filing".
        build_point_in_time_share_counts forward-fills and nothing else.
      * A STEP CANNOT BE CARRIED FOREVER. Forward-filling with no bound
        means a ticker whose series stops in 2022 keeps reporting its 2022
        count in 2026 (12 tickers here have a last observation more than
        two years before the panel ends). SHARES_MAX_STALENESS_DAYS caps
        how far a filing may be carried; past it the value goes NaN and the
        ticker is simply not ranked.
      * A WINDOW WITH NO NEW FILING IN IT IS NOT A ZERO. This is the defect
        that turned out to matter most, and it was not visible until it was
        measured. If a ticker's last filing predates the whole lookback
        window, forward-fill puts the IDENTICAL count at both endpoints and
        the log ratio is exactly 0.000000 — read by a ranking as a
        confident "this company issued and repurchased nothing", when the
        truth is "nothing has been filed since before this window began".
        On the real panel, at the 126-day lookback, an average of 8.2% of
        otherwise-usable names carry such a fabricated zero on any given
        day — and on 2018-06-07 it was 530 of 542 names, i.e. essentially
        the ENTIRE cross-section, so that day's "542-name decile sort"
        would in truth have been decided by the dozen names that happened
        to have filed. (252-day lookback: 2.0% mean, worst 408 of 522 on
        2018-10-05. 504-day: 0.2% mean.) signal_net_share_issuance refuses
        these outright — see its docstring, and REFUSE_IDENTICAL_ENDPOINTS
        for the one thing that refusal costs.

    A MEASURED COVERAGE HOLE, disclosed because it is large and because it
    is partly self-inflicted: populated tickers per day in the built panel
    run ~545 through 2018-09, collapse to 398 in 2018-10, 114 in 2018-11 and
    108 in 2018-12, then snap back to 545 in 2019-01. The cause is the
    2017 filing drought (median 4 rows per ticker that year) meeting
    SHARES_MAX_STALENESS_DAYS, followed by a January-2019 filing wave
    (59,030 pooled observations in 2019 against 2,734 in 2017). The hole is
    the staleness bound working correctly — those names genuinely had
    nothing filed for over 400 days — but any formation landing inside it
    ranks a much smaller cross-section, or is skipped by the harness's
    min_names_per_leg floor. Formations are NOT repositioned to dodge it:
    moving the schedule to avoid a data-quality hole would be choosing the
    sample for a reason correlated with data quality. n_skipped_formations
    and the per-formation records report what actually happened.

    The uneven density also means an early-sample signal is coarser than a
    late-sample one: a 2018 formation may be differencing two filings a
    year apart, while a 2025 formation differences two that are weeks
    apart. That is a real, unfixable property of the free data. It is
    reported per run (BuybackScreeningSummary.median_signal_endpoint_age_
    days) rather than argued away.

(3) THE TWO ENDPOINTS ARE JOINED BY TICKER SYMBOL, AND A TICKER SYMBOL IS
    NOT A COMPANY. Found by a dedicated audit on 2026-08-27, AFTER the
    production run below; that run was contaminated by it.

    Prices come from the batched chart endpoint (yf.download) and share
    counts from the per-ticker fundamentals endpoint (get_shares_full).
    Symbols are retired and REASSIGNED, and the two endpoints do not agree
    about when — so one column can carry two unrelated issuers with no
    error, no warning and no NaN. Confirmed live: STI returns 1,083 price
    rows from 2022-05-02 (Solidion Technology) beside 447 share-count rows
    from 2015-11-16 (SunTrust Banks, merged away in 2019).

    FOR BUILD D1 THIS WAS A WEIGHTING NUISANCE. HERE IT IS THE RANKING
    VARIABLE, and — exactly as with defect (1) — a corporate-entity change
    produces the LARGEST apparent share-count change in the universe, which
    is precisely what a decile sort selects on. Three cases were live in the
    production run below, all at maximum weight:
      * FOXA/FOX: 21st Century Fox's ~1.85e9 counts (from 2015-11) in front
        of Fox Corporation's prices (from 2019-03-12). Reads as a ~67% share
        reduction — signal +1.09, 99.8th percentile, the largest apparent
        buyback in the S&P 500, maximum LONG, on formations through
        2019-2021. Fox Corporation bought back nothing of the kind.
      * BNY: Bank of New York Mellon's real prices against a 12.9M-24.6M
        share count belonging to some other issuer (BNY Mellon's true count
        is ~686M, which the series only reaches on 2026-05-22 in a 28.5x
        step with no split). That other issuer's count doubles on
        2021-06-10 (12,976,100 -> 24,608,900), reading as +89.6% dilution —
        signal -0.640, the 0.0-0.7th percentile, maximum SHORT, on every
        formation whose window spans it across 2022-2023. The 2026 step
        reads as -3.349, the most extreme value anywhere in the replay.
        NOTE that BNY's price and share series overlap in time perfectly
        well — its first filing is 2014-06-16 against a first price bar of
        2013-12-03 — so the lifecycle check structurally cannot see this one.
        It is the case the magnitude check exists for.
      * IR: Ingersoll-Rand plc's ~2.6e8 counts (8 filings, from 2015-10) in
        front of Gardner Denver's prices (from its 2017-05-12 IPO) — signal
        -0.55, the 0.0-1.4th percentile, maximum SHORT.
      Also present: PARA (a 3.16e6-share issuer's 2017 filings, then a
      206.8x step to Paramount Global's counts) and COL (Rockwell Collins'
      counts against a price series carrying a 1-for-10 reverse split
      Rockwell Collins never had — the successor holder of the symbol did).

    THE FIX IS TWO CHECKS, BOTH IN cross_sectional_ivol.py and imported here
    rather than reimplemented, applied in run_buyback_screening before the
    join: restrict_share_counts_to_price_lifecycle (the TIME axis — a share
    count dated on a day this symbol had no price is not this company's) and
    implausible_market_cap_mask (the MAGNITUDE axis — BNY's and COL's series
    overlap in time perfectly well and still describe different companies;
    only price x shares gives it away). Both counts are reported:
    BuybackScreeningSummary.n_share_observations_outside_price_lifecycle and
    .n_implausible_market_cap_cells.

    WHAT THE FIX DID TO THE NUMBERS is reported in its own section below, and
    it did NOT make this family look worse — read that section before
    quoting it.

(4) NOT A DEFECT BUT A HARD LIMIT: the late-2015 floor in (2) caps this
    family's usable sample at roughly nine years, and the warmup for the
    longest lookback plus the reporting lag eats the first part of it. The
    replay is short by the standards of the cited literature (Pontiff &
    Woodgate run 1970-2003). No amount of care here manufactures statistical
    power the sample does not contain, which is exactly what the DSR
    correction over the pre-declared family size exists to keep honest.

============================================================================
POINT-IN-TIME: THE REPORTING LAG
============================================================================
A share count is not public on the date it describes. get_shares_full's
index is filing-driven but this module does not rely on that: every
observation is shifted forward by SHARES_REPORTING_LAG_DAYS before it is
made visible to any formation, so a count dated D can first influence a
formation on D + lag. See that constant for the choice and what it costs.

This is the same discipline cross_sectional_fx.py applies to FRED's
publication lag, and the same reason: a signal may only read what was
genuinely available, whatever the vendor's index convention happens to be.
Note the asymmetry with FX is deliberate and in the opposite direction —
there, realized ACCRUAL legitimately uses contemporaneous rates because a
position earns a rate whether or not the statistic is published. Nothing
here is accrued; a share count is information only, so it gets the lag with
no exception.

============================================================================
FAMILY SIZE — 14, computed and fixed BEFORE any run
============================================================================
3 lookbacks x 2 holding periods x 2 portfolio modes = 12 core definitions,
plus 2 winsorized robustness variants at the LONGEST lookback (long_short
only, one per holding period) = 14. BUYBACK_N_TRIALS is asserted against the
built list in _build_buyback_family, so a size drift is a loud import-time
failure rather than a silent change to every future run's DSR denominator.
14 is above deflated_sharpe.MIN_TRIALS_FOR_DSR, so the correction proper
computes.

The 2 robustness variants and what they DO and DO NOT test, stated plainly
because it is easy to overclaim: winsorizing at a cross-sectional quantile
is a monotone transform, so it does NOT change any name's rank and
therefore does NOT change which names are in which leg. That invariance is
not free — it holds because BUYBACK_WINSORIZE_QUANTILE (0.01) is strictly
INSIDE BUYBACK_RANK_FRACTION (0.1). Clipping ties the clipped names to one
another, and select_leg_tickers breaks ties alphabetically; because the
whole clipped tail already sits inside the selected decile, those ties can
only permute a leg's internal ORDER (which nothing downstream reads —
_leg_weights reindexes by ticker), never its membership. A winsorize
quantile LARGER than the rank fraction would tie names ACROSS the decile
boundary and quietly turn these into selection variants as well. Asserted
in the tests, not merely reasoned here. What winsorization changes is
the MAGNITUDE weighting — this family's legs are weighted by each member's
distance from its leg's boundary (cross_sectional._leg_weights), so a
handful of extreme readings can carry outsized weight. Given that the
extremes in THIS signal are disproportionately corporate-action residue
(the 7 splits split_adjust_share_counts cannot rescue, merger-scale share
issuance, spin-off restatements), "does the result survive de-emphasizing
the extreme tail" is the single most relevant robustness question this
family can ask of itself. It is asked at the longest lookback because that
is where the most corporate actions fall inside one window.

NO 21-DAY OR 63-DAY HOLD, deliberately. The economics: this signal REFRESHES
ABOUT FOUR TIMES A YEAR — it can only move when a new share count is filed,
and defect (2) shows filings arrive quarterly at best. A 21-day hold
reformates roughly twelve times a year and a 63-day hold four times, against
a ranking variable that is unchanged between filings; most of those
reformations pay real turnover cost to re-express a ranking that has not
moved. With BUYBACK_COST_BPS one-way on gross notional traded, a full
long_short book (gross 2.0) costs ~10bps to establish from flat and 10bps x
the fraction of book replaced at each reformation. Measured on this
family's own real production replay (see BuybackScreeningSummary.
turnover_per_formation, reported per spec), so the annualized cost is
directly comparable across holds rather than assumed. Shortening the hold
multiplies that charge without buying any additional signal, and it is
exactly the cost-dominated-noise signature three prior honest rounds in this
project (270 single-ticker definitions, all negative) diagnosed. The two
holds declared here (126 and 252 trading days, i.e. two quarters and one
year) each span at least two fresh filings and amortize the charge over a
return window long enough to matter — and they sit inside the multi-year
horizon Ikenberry/Lakonishok/Vermaelen and Daniel/Titman actually document.

THE COST NUMBER IS STATED, NOT HIDDEN: BUYBACK_COST_BPS = 5.0bps one-way per
unit of gross notional traded, inherited unchanged from
cross_sectional.DEFAULT_XS_COST_BPS (itself momentum.py's single-leg
convention) so this family's numbers stay comparable with every other equity
family in the project. BUYBACK_FINANCING_BPS_PER_YEAR is 0.0 and that is a
DISCLOSURE, not a claim: see the constant.

============================================================================
UNIVERSE, AND THE BIASES THIS FAMILY DOES NOT ESCAPE
============================================================================
Point-in-time S&P 500 membership via the harness's default gate
(sp500_membership_history.was_member) over get_universe_over(start, end) —
identical to Build D1 and Round C, and the correct gate here because these
ARE equities with a real, moving, survivorship-relevant membership boundary
(cross_sectional.fixed_universe_membership would be flatly wrong; see its
docstring).

Everything cross_sectional.py's module docstring says about the residual
biases applies here unchanged and is not restated. Two are worth pointing at
specifically because this signal interacts with them:
 * The ~48% of index leavers with no yfinance price history are eligible but
   unrankable. Firms in distress often issue equity to survive — a dilution
   signal would route them to the SHORT leg — so their absence plausibly
   denies the short leg opportunities rather than flattering it, the same
   direction cross_sectional.py reasons through for its own signals. Not
   confidently signed without the delisted-securities vendor already on this
   project's pending-paid-decisions list.
 * SHORT BORROW IS NOT MODELED, at any price. The short leg here is heavy
   issuers: secondary offerings, heavy stock-comp issuers, merger acquirers
   paying in stock. That is a different population from the distressed
   hard-to-borrow names cross_sectional.py worries about and is on average
   easier to borrow, but "on average easier" is not "free", and this family
   sets financing_bps_per_year to 0.0 like every equity family before it.
   Any positive short-leg contribution reported here is therefore optimistic
   by an unmeasured amount.

A THIRD, SPECIFIC TO THIS SIGNAL: share count changes for reasons that are
not buybacks or offerings. A stock-financed acquisition raises the acquirer's
count; a spin-off can restate it; a large convertible conversion moves it.
This family's signal cannot tell those apart from a repurchase programme,
because the free data carries no corporate-action taxonomy. The winsorized
variants are the only instrument it has for asking how much of any result
rides on those cases, and they are a blunt one.

============================================================================
PRODUCTION RESULT (2026-08-27): NOT A CLEAN NEGATIVE — AND NOT AN EDGE
EITHER. READ ALL OF THIS BEFORE QUOTING ANY NUMBER FROM IT.
============================================================================
Run over formations 2018-01-02 .. 2026-08-26 (2,173 replayed trading days;
691 point-in-time S&P 500 members requested, 94 unpriceable, 0 without
usable share history; 132 priced tickers carried splits and 25,858 share
observations were restated by the defect-(1) correction; median share count
7 calendar days old after the reporting lag). All 14 specs replayed, none
fell below the data floors, n_trials = 14 throughout, dsr_floor_met True for
every one. Decile legs averaged 41-44 names.

Headline: 11 of 14 positive raw Sharpe, 3 of 14 with DSR above 0.5. Best is
nsi_l504_ls_h126 at raw Sharpe +0.412, DSR 0.598. That is materially
different from this project's four previous honest rounds (270 intraday
definitions, Round C, D1, D2, bonds, FX — all cleanly negative), and it
must not be rounded up into a claim.

WHAT LOOKS LIKE STRUCTURE. The ranking is monotone in lookback across every
single (portfolio, hold) pair: 504 beats 252 beats 126, without exception.

  lookback   ls_h126   ls_h252   hedged_h126   hedged_h252
     504      +0.412    +0.306      +0.327        +0.231
     252      +0.162    -0.041      +0.309        +0.076
     126      +0.047    -0.163      +0.086        -0.093

That is the direction Daniel & Titman and Ikenberry/Lakonishok/Vermaelen
predict (the effect is a multi-year underreaction, not a quarterly one),
and a coherent monotone surface is harder to get from noise than a single
lucky cell. The two winsorized robustness variants also track their plain
siblings closely (+0.400 vs +0.412 at h126, +0.340 vs +0.306 at h252), so
the result is NOT being carried by a handful of extreme corporate-action
readings — which was the specific failure mode those variants were declared
to probe, and they came back clean.

WHAT THE COST ASSUMPTIONS ARE NOT DOING. Measured breakevens for the best
spec: it survives a one-way trading cost up to 151.7bp (assumed: 5.0bp) and
a short-leg borrow up to 427bp/yr (assumed: 0, and typical US large-cap
borrow is tens of bps). So unlike this project's earlier cost-dominated
negatives, the cost assumptions are not what is producing this result, and
plugging in a realistic borrow rate would not erase it.

WHY IT IS STILL NOT AN EDGE.
 * DSR 0.598 means the model's point estimate is a ~60% probability that the
   true Sharpe beats what the BEST of 14 zero-edge trials would show by
   chance. That is barely better than a coin flip on the one question that
   matters, and 11 of the 14 specs sit below it.
 * The independent-observation count is tiny. Each spec has 9 (h252) or 18
   (h126) NON-OVERLAPPING formations. A daily series of 2,173 observations
   does not change that — the bets are quarterly-to-annual, and 9-18 of them
   is not a sample from which a Sharpe of 0.4 can be distinguished from 0.
 * 8.6 years is ONE macro regime for a value-flavoured signal.
 * The 504-day specs sit at the top and also have by far the cleanest data
   (0.2% uninformative windows against 8.1% at 126 days). Signal horizon and
   data quality are confounded here, and this run cannot separate them.
 * The survivorship hole is unchanged: 94 of 691 members never rank.

The honest summary was originally "worth a forward-validation slot, not
worth capital" — SUPERSEDED, see below.

============================================================================
2026-08-27 ADVERSARIAL RECHECK VERDICT — REJECTED, do not register
============================================================================
A dedicated adversarial recheck computed a whole-night meta multiple-
comparisons correction (a Monte Carlo calibration across all ~7 families
tested this session, not just this family's own 14-trial correction) and
found the best spec's DSR 0.598 sits BELOW the median best-of-7-families
DSR (0.64) an all-noise night would be expected to produce by chance —
study-wise p≈0.69. This family's result is statistically indistinguishable
from, and if anything slightly worse than, pure noise once corrected for
the fact that 7 independent families were searched this session and this
was the one being looked at. Combined with the already-disclosed,
never-resolved lookback/data-cleanliness confound above, there is no basis
to register this for forward validation. The code, tests, and production
numbers above are left unchanged and remain independently verified as
CORRECTLY COMPUTED — only the interpretation is overturned. The correct
next step, if this family is revisited, is a larger multi-family batch
where every family's meta-corrected significance is computed together
before any is proposed for forward validation, not a sweep around this
particular result.

============================================================================
2026-08-27 CROSS-ENDPOINT CONTAMINATION AUDIT — the defect-(3) fix, and what
it did to the numbers above. THE VERDICT IS UNCHANGED: still REJECTED.
============================================================================
The production run above was contaminated by defect (3) — FOXA/FOX at
maximum LONG on 21st Century Fox's share counts, BNY and IR at maximum SHORT
on another issuer's. The two checks described in defect (3) are now applied,
and the family was replayed against the SAME saved production fetch so the
before/after is a controlled comparison rather than two different runs. (The
replay reproduces the published table above to within 0.01 Sharpe on 13 of
14 specs before the fix, which is what makes it a valid control; the small
residual is a one-day difference in the price fetch's end date.)

WHAT THE CHECKS REFUSED: 3,216 share-count observations across 22 tickers
dated outside their own price history, and 13,314 panel cells across 34
tickers implying an impossible market cap.

  spec                      before    after     d
  nsi_l504_ls_h126          +0.420   +0.466  +0.046
  nsi_l504_ls_h126_winsor   +0.405   +0.424  +0.019
  nsi_l504_ls_h252          +0.304   +0.336  +0.032
  nsi_l504_ls_h252_winsor   +0.337   +0.354  +0.017
  nsi_l504_hedged_h126      +0.336   +0.421  +0.085
  nsi_l504_hedged_h252      +0.228   +0.307  +0.079
  nsi_l252_hedged_h252      +0.076   +0.187  +0.112
  nsi_l252_hedged_h126      +0.316   +0.393  +0.077
  nsi_l126_ls_h252          -0.165   -0.216  -0.051
  (the remaining five move by less than 0.04)

THE RESULT GOT MORE POSITIVE, AND THAT IS THE THING TO BE SUSPICIOUS OF.
This project's standing rule is that a correctness fix which improves a
result must be re-verified harder than one that worsens it. Three
independent reasons it survives that scrutiny:
 * NEITHER CHECK CAN SEE A RETURN. One compares two date ranges, the other
   compares a product against a fixed dollar band. No realized return, no
   Sharpe, no P&L enters either decision, so neither can be selecting
   against losing positions.
 * THE REMOVED DATA IS INDEPENDENTLY CONFIRMED WRONG, not merely suspicious:
   yfinance's own current metadata for PARA reads "Banzai International,
   Inc." (3.5M shares), for STI "Solidion Technology, Inc.", for BNY 678.5M
   shares against the 12.9M-24.6M its history serves. Fox Corporation's 2019
   share count is not 21st Century Fox's. These are facts about the data,
   established before any Sharpe was recomputed.
 * IT IS NOT LOOK-AHEAD. The lifecycle check's trailing bound does read a
   ticker's last price bar, which is future information — but it can only
   remove observations dated after that bar, on rows where the ticker has no
   price and is therefore already ineligible at every formation. Pinned by
   test, not argued.

AND IT CHANGES NOTHING THAT MATTERS. The best spec's DSR moves 0.604 ->
0.606 — essentially not at all — because the DSR's sigma_sr is derived from
the SPREAD of sibling Sharpes, and the fix raised the siblings along with
the leader, so the expected-max-of-noise benchmark rose with it. Still 11 of
14 positive raw, still 4 of 14 with DSR above 0.5, still monotone in
lookback. Against the whole-night meta-correction above (median best-of-7-
families DSR 0.64 under pure noise), 0.606 remains AT OR BELOW the noise
median. The rejection stands, on the corrected numbers as on the originals.
The one thing that did change is that the family's legs are now made of this
family's own companies.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import partial

import numpy as np
import pandas as pd

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
from app.services.research_lab.cross_sectional_ivol import (
    implausible_market_cap_mask,
    restrict_share_counts_to_price_lifecycle,
    split_adjust_share_counts,
)
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    get_universe_over,
)

logger = logging.getLogger(__name__)

# --- the point-in-time share-count panel -----------------------------------

# Calendar days an as-filed share count is held back before any formation may
# read it. See the module docstring's REPORTING LAG section.
#
# 45 days is the SEC's own 10-Q deadline for a large accelerated filer (40
# days after quarter end) plus a margin, and every S&P 500 constituent is a
# large accelerated filer by definition of the index's size criteria. It is
# applied unconditionally rather than only when needed, because
# get_shares_full's index convention is not documented by the vendor and this
# module refuses to depend on an undocumented convention for a
# look-ahead-critical question: if the dates are already filing dates the lag
# is pure conservatism costing a little signal freshness, and if they are
# as-of dates it is the difference between a valid backtest and an invalid
# one.
#
# The cost is small BECAUSE OF what makes the signal usable in the first
# place: the ranking variable is a trailing multi-quarter change that moves
# about four times a year, so delaying every input by six weeks shifts a
# cross-sectional ranking that was mostly already fixed. It is not free, and
# it is not claimed to be.
SHARES_REPORTING_LAG_DAYS = 45

# How long a filed count may be carried forward before it is refused (NaN)
# rather than reported as current. See the module docstring's defect (2).
#
# 400 calendar days = one full annual reporting cycle plus a ~5-week margin.
# Chosen against the MEASURED density rather than the regulatory ideal, and
# the measurement is what settles it. Panel cells populated, over the real
# 607-ticker universe (2026-08-27): 77.2% at a 130-day cap, 79.0% at 200,
# 83.6% at 400, 85.3% at 730, 86.7% unbounded. The differences look small
# pooled and are NOT small where they land — mean tickers rankable per day
# during 2018 is 64 at a 130-day cap, 167 at 200, 460 at 400 and 550 at 730,
# because yfinance's 2017 coverage is a drought (median 4 observations per
# ticker for the whole year) and a tight cap turns that drought into a
# year-long blackout for most of the universe. A strict quarterly bound
# (~130 days) is what the SEC's filing schedule implies and would delete the
# early sample outright — not because companies stopped filing, but because
# the vendor did not surface it.
#
# 730 was rejected in the other direction: a count carried two years is
# older than this family's longest lookback, so BOTH endpoints of any window
# would come from the same filing and every such name would read an exact,
# fabricated 0.00% (see REFUSE_IDENTICAL_ENDPOINTS). 400 is the value at
# which a stale count can still, at worst, be the older endpoint of the
# 504-day window rather than both of them.
#
# This is a bound on VENDOR staleness, and the honest reading of a signal
# computed off a 300-day-old count is "coarse", not "wrong": the count was
# genuinely the last one known. BuybackScreeningSummary reports the realized
# endpoint ages so a reader can see how coarse a given run actually was.
SHARES_MAX_STALENESS_DAYS = 400


def build_point_in_time_share_counts(
    close: pd.DataFrame,
    shares_outstanding: dict[str, pd.Series],
    splits: dict[str, pd.Series],
    *,
    reporting_lag_days: int = SHARES_REPORTING_LAG_DAYS,
    max_staleness_days: int = SHARES_MAX_STALENESS_DAYS,
) -> tuple[pd.DataFrame, list[str]]:
    """The split-adjusted, reporting-lagged, staleness-bounded share-count
    STEP panel this family's signal ranks on: one column per ticker, aligned
    to `close`'s exact trading-day index and column order, ready to hand to
    CrossSectionalData.shares_outstanding.

    Returns (frame, tickers_with_no_usable_share_history).

    FOUR STEPS, IN THIS ORDER, EACH LOAD-BEARING:

    1. SPLIT-ADJUST, on the sparse filing-dated series, via
       cross_sectional_ivol.split_adjust_share_counts — Build D1's own fix
       (commit aad5bf8), imported rather than reimplemented. This must
       happen FIRST, on the raw observation dates, because that function
       locates each split's basis boundary by scanning a window around the
       split's ex-date: shifting the dates first (step 3) would move every
       observation 45 days away from the ex-date it is being matched
       against. See the module docstring's defect (1) for the real GE/ANET
       numbers this prevents.

    2. DROP NON-POSITIVE COUNTS. A zero or negative share count is a data
       error, and this signal DIVIDES by the window's first value; a zero
       there would produce an infinity that would rank first in the cross-
       section. Dropped, never clipped to a floor, which would fabricate a
       count.

    3. APPLY THE REPORTING LAG by shifting every observation's date forward
       by `reporting_lag_days` — an as-filed count dated D becomes visible
       to formations from D + lag onward. A constant shift preserves order
       and distinctness, so this cannot reorder or collide observations.

    4. FORWARD-FILL ONTO `close`'s TRADING DAYS, AND ONLY FORWARD-FILL, then
       NaN out any value carried further than `max_staleness_days`. The fill
       runs on the union of the (shifted) filing dates and close's index so
       a filing landing on a non-trading day still propagates from its own
       date; the result is read back on close's dates alone. No
       interpolation, no backward fill, no extrapolation: a date before a
       ticker's first visible filing is NaN, and so is a date more than
       max_staleness_days after its last. See the module docstring's defect
       (2) for why interpolating here would manufacture information.

    A ticker absent from `shares_outstanding`, present with an empty series,
    or left with nothing usable after steps 1-2 gets an all-NaN column and
    is named in the returned list — never zero, never a guess. Its signal
    will be NaN at every formation and it simply never ranks, which is the
    correct point-in-time answer for a company whose share count this
    project cannot observe.

    Accepts plain ticker -> Series mappings (not specifically
    get_shares_outstanding's / get_market_cap_basis's return shapes) so it is
    directly unit-testable against hand-built dicts with no network — the
    same contract build_point_in_time_market_cap keeps, for the same
    reason."""
    aligned: dict[str, pd.Series] = {}
    unusable: list[str] = []
    empty_column = pd.Series(np.nan, index=close.index, dtype=float)

    for ticker in close.columns:
        raw = shares_outstanding.get(ticker)
        if raw is None or raw.empty:
            unusable.append(ticker)
            aligned[ticker] = empty_column.copy()
            continue

        adjusted = split_adjust_share_counts(raw.sort_index(), splits.get(ticker))
        adjusted = adjusted[np.isfinite(adjusted) & (adjusted > 0.0)]
        if adjusted.empty:
            unusable.append(ticker)
            aligned[ticker] = empty_column.copy()
            continue

        lagged = pd.Series(
            adjusted.to_numpy(dtype=float),
            index=pd.DatetimeIndex(adjusted.index) + pd.Timedelta(days=reporting_lag_days),
        )
        lagged = lagged[~lagged.index.duplicated(keep="last")].sort_index()

        union = lagged.index.union(close.index).sort_values()
        on_union = lagged.reindex(union)
        filled = on_union.ffill()

        # Age of the value each row carries, in calendar days since the
        # filing it was carried forward FROM. Rows before the first visible
        # filing carry NaT here and are therefore refused too (they are
        # already NaN in `filled`; the mask keeps that true rather than
        # relying on it).
        observed_at = pd.Series(union, index=union).where(on_union.notna()).ffill()
        age_days = (pd.Series(union, index=union) - observed_at).dt.days
        filled = filled.where(age_days.notna() & (age_days <= max_staleness_days))

        aligned[ticker] = filled.reindex(close.index)

    frame = pd.DataFrame(aligned, index=close.index)[list(close.columns)]
    return frame, unusable


# --- the signal ------------------------------------------------------------

# A signal window with fewer than this fraction of its rows populated is
# refused (NaN signal) rather than computed on whatever survives. Same 0.8
# register, and deliberately the same value, as every other coverage floor in
# this project (cross_sectional_patterns.MIN_SIGNAL_OBS_FRACTION,
# cross_sectional_ivol's and cross_sectional_fx's own copies) — each family
# module owning its own copy rather than importing one is this project's
# established convention, not an oversight.
#
# On THIS panel the guard does real work rather than being a formality: the
# staleness bound above punches genuine holes in a sparse ticker's column, and
# a name whose window is mostly holes should not be ranked on the two rows
# that happen to survive at the ends.
MIN_SIGNAL_OBS_FRACTION = 0.8

# Refuse (NaN) any ticker whose two window endpoints are the BIT-IDENTICAL
# share count. See the module docstring's defect (2), third bullet: on a step
# panel forward-filled from filings, identical endpoints mean no new distinct
# count was filed anywhere in the window, so the exactly-0.000000 log ratio
# that would result is a statement the data cannot support — "nothing was
# issued" asserted from "nothing has been reported".
#
# WHAT THIS CONFLATES, stated because it is the honest objection: a company
# whose share count genuinely did not change would also be refused. That is
# accepted, because exact equality TO THE SHARE across at least 126 trading
# days is a fingerprint of vendor staleness rather than a corporate fact —
# real counts drift continuously with option exercises, RSU vesting and
# buyback tranches, and are refiled with a different number every quarter.
#
# WHAT IT COSTS, measured on the real panel rather than assumed (2026-08-27,
# 252-day lookback, formations from 2018-01-02): mean names ranked falls from
# 538 to 527, and the decile leg from 53 names to 52. Trading days left below
# the 50 ranked names a 5-name decile leg needs go from 3 to 30 (of 2,174),
# and every one of the 27 it adds falls between 2018-11-13 and 2018-12-21 —
# i.e. entirely inside the 2018-10..2018-12 coverage hole documented above,
# where the cross-section was already not worth ranking. Outside that hole
# the refusal costs no formation at all.
REFUSE_IDENTICAL_ENDPOINTS = True

# A cross-section smaller than this is not winsorized at all (the signal is
# returned unclipped). At q = 0.01 the 1st and 99th percentiles of a
# 20-name sample are its near-extremes, so clipping there is already close to
# a no-op; below that it is pure noise dressed as a robustness control, and a
# silent no-op is more honest than a fake one. Never reached in production
# (this family's cross-sections run to several hundred names) — it exists so
# the function is total, and so tests can exercise the boundary.
MIN_WINSORIZE_NAMES = 20


def signal_net_share_issuance(
    history: CrossSectionalData,
    *,
    lookback_days: int,
    winsorize_quantile: float | None = None,
) -> pd.Series:
    """Pontiff & Woodgate (2008) net share issuance: per ticker, the NEGATED
    log growth in split-adjusted shares outstanding over the trailing
    `lookback_days` trading days.

        signal = -log( S_t / S_{t-lookback_days} ) = log( S_{t-L} / S_t )

    so a company whose share count SHRANK (buybacks) scores highest and
    ranks into the long leg, and a company that ISSUED scores lowest and
    ranks into the short leg — the cited literature's own direction,
    expressed through this harness's top-is-long convention rather than
    through a direction flag the harness does not have (the same choice
    cross_sectional_ivol and cross_sectional_patterns_d2 both make).

    LOG, not the raw percentage change, following Pontiff & Woodgate
    directly. It matters here for a concrete reason and not just for
    fidelity: a doubling of share count and a halving are equal and opposite
    in logs (+0.693 / -0.693) but wildly asymmetric as percentages (+100% /
    -50%), and this family's legs are MAGNITUDE-weighted by distance from
    the leg boundary. On percentages, a single large issuer would
    systematically outweigh any repurchaser, tilting the book by an artifact
    of the units.

    `history.shares_outstanding` is the panel built by
    build_point_in_time_share_counts: split-adjusted, reporting-lagged,
    staleness-bounded, forward-filled as a step function. It arrives already
    truncated to rows <= the formation date by the harness's history view,
    so this function cannot read a future filing however wrong its
    arithmetic is (cross_sectional.SignalFn's structural guarantee).

    Refused (NaN) for a ticker when ANY of:
      * either endpoint is missing or non-positive;
      * fewer than MIN_SIGNAL_OBS_FRACTION of the window's rows are
        populated (the staleness bound in
        build_point_in_time_share_counts punches real holes in a sparse
        ticker's column, and a name whose window is mostly holes must not
        be ranked on the two rows that happen to survive at its ends);
      * the two endpoints are the BIT-IDENTICAL count, meaning no new
        distinct share count was filed anywhere in the window — see
        REFUSE_IDENTICAL_ENDPOINTS for why that is a refusal rather than a
        zero, what it conflates with, and what it measurably costs.
    A NaN excludes the ticker from the ranking entirely, which is the
    correct answer for "this project cannot observe this company's share
    count over this window" — never a zero, which would read as a confident
    "no issuance" and place it mid-cross-section as though it were an
    observation.

    `winsorize_quantile` (the family's 2 robustness variants) clips the
    cross-sectional signal at its own q and 1-q quantiles. Read the module
    docstring's FAMILY SIZE section before interpreting one: clipping is
    monotone, so it changes NO name's rank and therefore NO leg's
    membership; what it changes is the magnitude WEIGHTS within each leg,
    which is precisely the channel through which corporate-action residue
    (the splits split_adjust_share_counts cannot rescue, stock-financed
    mergers, spin-off restatements) would drive a result."""
    shares = history.shares_outstanding
    if shares is None:
        raise ValueError(
            "signal_net_share_issuance requires CrossSectionalData.shares_outstanding; the spec "
            "must set requires_shares_outstanding=True and the caller must supply the frame."
        )

    window = shares.iloc[-(lookback_days + 1) :]
    columns = list(shares.columns)
    if len(window) < lookback_days + 1:
        # The harness only forms once lookback_days of history exist, so this
        # is unreachable in a normal replay; a hand-built short frame in a
        # test gets a clean all-NaN answer rather than a partial window
        # silently measured over fewer days than the definition claims.
        return pd.Series(np.nan, index=columns, dtype=float)

    first = window.iloc[0]
    last = window.iloc[-1]
    n_obs = window.notna().sum()

    usable = (
        np.isfinite(first)
        & np.isfinite(last)
        & (first > 0.0)
        & (last > 0.0)
        & (n_obs >= int((lookback_days + 1) * MIN_SIGNAL_OBS_FRACTION))
    )
    if REFUSE_IDENTICAL_ENDPOINTS:
        usable = usable & (first != last)

    with np.errstate(divide="ignore", invalid="ignore"):
        signal = -np.log(last / first)
    signal = pd.Series(signal, index=columns, dtype=float)
    signal = signal.where(usable & np.isfinite(signal))

    if winsorize_quantile is not None:
        signal = winsorize_cross_section(signal, winsorize_quantile)
    return signal


def winsorize_cross_section(signal: pd.Series, quantile: float) -> pd.Series:
    """Clips a cross-sectional signal at its own `quantile` and
    `1 - quantile` values, leaving NaNs NaN.

    Split out as its own function (rather than inlined) so the family's
    robustness claim is directly testable in isolation, including the two
    properties it is easy to assume without checking: that it preserves
    ranks exactly (hence leg membership), and that it is a no-op below
    MIN_WINSORIZE_NAMES rather than clipping against meaningless quantiles
    of a tiny sample."""
    finite = signal[np.isfinite(signal)]
    if len(finite) < MIN_WINSORIZE_NAMES:
        return signal
    lo = float(finite.quantile(quantile))
    hi = float(finite.quantile(1.0 - quantile))
    if not (np.isfinite(lo) and np.isfinite(hi)) or hi < lo:
        return signal
    return signal.clip(lower=lo, upper=hi)


# --- the family, pre-declared ----------------------------------------------

BUYBACK_CITATION = (
    "Pontiff & Woodgate, 'Share Issuance and Cross-Sectional Returns' (Journal of Finance, "
    "2008); Ikenberry, Lakonishok & Vermaelen, 'Market Underreaction to Open Market Share "
    "Repurchases' (Journal of Financial Economics, 1995); Daniel & Titman, 'Market Reactions "
    "to Tangible and Intangible Information' (Journal of Finance, 2006); Fama & French, "
    "'Dissecting Anomalies' (Journal of Finance, 2008)"
)

# The three measurement horizons, in TRADING days. 252 (one year) is Pontiff
# & Woodgate's own headline construction and the centre of the family; 126
# (two quarters) is the shortest horizon that still spans at least two
# quarterly filings, which is the floor set by defect (2)'s refresh rate
# rather than by taste; 504 (two years) reaches toward the multi-year
# horizon Daniel & Titman and Ikenberry/Lakonishok/Vermaelen document,
# capped there rather than at their full 4-5 years because the ~2015-10 data
# floor would otherwise leave almost no replay at all.
BUYBACK_LOOKBACK_DAYS: tuple[int, ...] = (126, 252, 504)

# Two holding periods. See the module docstring's NO 21-DAY OR 63-DAY HOLD
# section for the cost-vs-refresh-rate argument that excludes the shorter
# siblings this project's earlier rounds kept losing to.
BUYBACK_HOLDING_DAYS: tuple[int, ...] = (126, 252)

# Both harness portfolio constructions. long_universe_hedged is long the top
# decile minus the equal-weighted eligible universe — see cross_sectional.py's
# CONVENTIONS for why that, rather than a raw unhedged long, is what "long
# only" has to mean for the Sharpes in this family to be comparable with each
# other inside one DSR correction.
BUYBACK_PORTFOLIOS: tuple[str, ...] = ("long_short", "long_universe_hedged")

# Deciles, the standard construction of the cited literature (Pontiff &
# Woodgate sort into deciles; Fama & French use decile and quintile breaks).
BUYBACK_RANK_FRACTION = 0.1

# The robustness axis: winsorize at the 1st/99th percentiles of the
# cross-section. 1% is the conventional figure in this literature, not tuned
# — and deliberately not something larger, which would stop being a tail
# control and start being a different signal.
BUYBACK_WINSORIZE_QUANTILE = 0.01

# The robustness variants are declared at the LONGEST lookback only, and
# long_short only. Longest because that window contains the most corporate
# actions and therefore the most of the extreme readings the variants exist
# to probe; long_short only because the hedge leg of long_universe_hedged is
# equal-weighted by construction (cross_sectional._target_weights) and so has
# no magnitude weighting for winsorization to affect on that side — testing
# it there would be half a test. Exactly D1's own robustness-slice shape
# (one lookback, long_short only, across the family's holds).
BUYBACK_ROBUSTNESS_LOOKBACK_DAYS = max(BUYBACK_LOOKBACK_DAYS)

# THE PRE-DECLARED FAMILY SIZE and the honest n_trials denominator for this
# family's own, never-pooled DSR correction. Computed from the axes above
# rather than typed as a bare literal so the arithmetic and the number can
# never disagree, then cross-checked against the literal 14 the build was
# specified with, and asserted against the built list in
# _build_buyback_family.
BUYBACK_N_CORE_TRIALS = (
    len(BUYBACK_LOOKBACK_DAYS) * len(BUYBACK_HOLDING_DAYS) * len(BUYBACK_PORTFOLIOS)
)
BUYBACK_N_ROBUSTNESS_TRIALS = len(BUYBACK_HOLDING_DAYS)
BUYBACK_N_TRIALS = BUYBACK_N_CORE_TRIALS + BUYBACK_N_ROBUSTNESS_TRIALS

# One-way cost per unit of gross notional traded at a formation. Inherited
# UNCHANGED from cross_sectional.DEFAULT_XS_COST_BPS rather than
# re-estimated, deliberately: every other equity family in this project
# (Round C, Round D, D1, D2) is priced at exactly this, and re-tuning it here
# would make this family's Sharpes incomparable with theirs for no better
# reason than that a different number was available. Aliased under this
# family's own name so the module reads self-contained and a future change
# has to be an explicit decision.
BUYBACK_COST_BPS = DEFAULT_XS_COST_BPS

# 0.0, and this is a DISCLOSURE rather than an estimate. See the module
# docstring's SHORT BORROW paragraph: the short leg here is heavy issuers,
# which are on average more borrowable than the distressed names
# cross_sectional.py's own disclosure worries about, but this project has no
# sourced borrow-rate data for any US equity and inventing one would be
# fabrication. Kept at the harness default so this family's cost treatment is
# identical to every equity family before it, and so the optimism it implies
# is the SAME known, disclosed optimism rather than a new and different one.
BUYBACK_FINANCING_BPS_PER_YEAR = 0.0


def _build_buyback_family() -> list[CrossSectionalSpec]:
    """Assembles the full, fixed 14-definition family: the exact product
    BUYBACK_LOOKBACK_DAYS x BUYBACK_HOLDING_DAYS x BUYBACK_PORTFOLIOS (12),
    plus the 2 winsorized robustness variants at the longest lookback,
    long_short only, one per holding period.

    The literal length of this list is the n_trials denominator
    screen_cross_sectional_universe uses — every definition counts, whether
    or not it survives the data floors, which is what makes it ungameable by
    declaring specs expected to fail."""
    specs: list[CrossSectionalSpec] = []

    for lookback in BUYBACK_LOOKBACK_DAYS:
        for portfolio in BUYBACK_PORTFOLIOS:
            portfolio_tag = "ls" if portfolio == "long_short" else "hedged"
            for holding in BUYBACK_HOLDING_DAYS:
                specs.append(
                    CrossSectionalSpec(
                        pattern_id=f"nsi_l{lookback}_{portfolio_tag}_h{holding}",
                        family="net_share_issuance",
                        citation=BUYBACK_CITATION,
                        signal_fn=partial(signal_net_share_issuance, lookback_days=lookback),
                        # +1 row: the signal differences the window's first
                        # and last rows, so it needs lookback + 1 rows to
                        # measure a change over `lookback` trading days —
                        # the same convention (and the same reason)
                        # cross_sectional_ivol's specs use for pct_change.
                        lookback_days=lookback + 1,
                        holding_days=holding,
                        portfolio=portfolio,  # type: ignore[arg-type]
                        rank_fraction=BUYBACK_RANK_FRACTION,
                        requires_shares_outstanding=True,
                    )
                )

    for holding in BUYBACK_HOLDING_DAYS:
        specs.append(
            CrossSectionalSpec(
                pattern_id=f"nsi_l{BUYBACK_ROBUSTNESS_LOOKBACK_DAYS}_ls_h{holding}_winsor",
                family="net_share_issuance",
                citation=BUYBACK_CITATION,
                signal_fn=partial(
                    signal_net_share_issuance,
                    lookback_days=BUYBACK_ROBUSTNESS_LOOKBACK_DAYS,
                    winsorize_quantile=BUYBACK_WINSORIZE_QUANTILE,
                ),
                lookback_days=BUYBACK_ROBUSTNESS_LOOKBACK_DAYS + 1,
                holding_days=holding,
                portfolio="long_short",
                rank_fraction=BUYBACK_RANK_FRACTION,
                requires_shares_outstanding=True,
            )
        )

    assert len(specs) == BUYBACK_N_TRIALS == 14, (
        f"Buyback family built {len(specs)} definitions; the declared grid "
        f"({len(BUYBACK_LOOKBACK_DAYS)} lookbacks x {len(BUYBACK_HOLDING_DAYS)} holds x "
        f"{len(BUYBACK_PORTFOLIOS)} portfolio modes = {BUYBACK_N_CORE_TRIALS}, plus "
        f"{BUYBACK_N_ROBUSTNESS_TRIALS} winsorized robustness variants) implies "
        f"{BUYBACK_N_TRIALS}, and the build pre-declared exactly 14. All three must agree — a "
        "drift here silently changes the DSR's multiple-comparisons denominator for every "
        "future run of this family."
    )
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    assert all(s.requires_shares_outstanding for s in specs), (
        "every definition in this family ranks on the share-count panel; a spec that does not "
        "declare it would silently be handed no frame and produce an all-NaN signal."
    )
    assert all(s.rank_fraction == BUYBACK_RANK_FRACTION for s in specs)
    assert all(s.leg_weighting == "magnitude" for s in specs), (
        "this family is magnitude-weighted (the harness default); the winsorized robustness "
        "variants are meaningless under any weighting that ignores signal magnitude."
    )
    assert all(s.cohort_formation_days is None for s in specs), (
        "this family forms non-overlapping holds; it does not use the harness's "
        "overlapping-cohort option."
    )
    assert all(s.holding_days in BUYBACK_HOLDING_DAYS for s in specs)
    assert 21 not in BUYBACK_HOLDING_DAYS and 63 not in BUYBACK_HOLDING_DAYS, (
        "holds shorter than a quarter are deliberately excluded: this signal only refreshes when "
        "a new share count is filed (~4x/year), so a shorter hold pays more turnover cost to "
        "re-express a ranking that has not moved — see the module docstring."
    )
    assert min(BUYBACK_HOLDING_DAYS) >= min(BUYBACK_LOOKBACK_DAYS) / 2, (
        "a hold much shorter than the signal's own measurement window reforms far more often "
        "than the window can meaningfully change."
    )
    return specs


BUYBACK_FAMILY: list[CrossSectionalSpec] = _build_buyback_family()

# The longest signal window any spec in this family declares, in TRADING
# rows — 504 + 1. Everything below that needs a calendar figure derives from
# this rather than repeating the number.
BUYBACK_MAX_LOOKBACK_ROWS = max(s.lookback_days for s in BUYBACK_FAMILY)

# Calendar padding fetched BEFORE the requested screening start, purely to
# warm up that longest lookback: 505 trading rows ~= 505 * 365 / 252 ~= 732
# calendar days, rounded up to 800 for holiday clustering and for the
# reporting lag (a 45-day-lagged filing has to exist 45 days before the row
# that reads it). Formations themselves never occur in the padding —
# CrossSectionalConfig.formation_start pins them to the requested start — so
# no formation can predate the point-in-time membership data either.
BUYBACK_PRICE_HISTORY_PADDING_CALENDAR_DAYS = 800

# The earliest date this family will let a formation happen, and the default
# `start` of the production entry point.
#
# DERIVED FROM THE MEASURED DATA FLOOR, not chosen for a result. Per defect
# (2), the share series effectively begins in late 2015 (median first
# observation 2015-11-05 across the real 607-ticker universe). The longest
# lookback is 504 trading days (~730 calendar days) and the reporting lag
# adds 45 more, so the first formation at which the longest-lookback spec can
# see a real filing at BOTH ends of its window is roughly 2015-11 + 45d +
# 730d ~= 2018-01.
#
# CONFIRMED, not just derived: on 2018-01-02 the real panel has 433 tickers
# with a usable 504-day signal (530 at 252 days, 538 at 126) — comfortably
# above the ~50 a 5-name decile leg needs. The first date on which 300+ names
# carry a usable 504-day signal is 2017-12-20, so this start is two weeks
# past the earliest defensible one rather than tuned against it.
#
# ALL FOURTEEN SPECS ARE PINNED TO THIS SAME DATE, including the 126-day
# ones that could technically start a year earlier. That costs the short-
# lookback specs some replay and buys something worth more, for exactly the
# reason cross_sectional_fx.py gives for its own common lookback: screen_
# cross_sectional_universe derives the DSR's sigma_sr from the SPREAD of
# sibling Sharpes, and siblings measured over different windows would make
# that spread partly an artifact of differing samples rather than of
# differing definitions — letting a spec look good merely by having skipped
# a bad regime.
BUYBACK_FORMATION_START = date(2018, 1, 2)


def default_buyback_config() -> CrossSectionalConfig:
    """This family's cost/leg configuration, as a FUNCTION rather than a
    module-level singleton so callers cannot mutate a shared object (the
    harness writes formation_start onto whatever config it is given) — the
    same contract default_bonds_config keeps, for the same reason.

    Every value here is the harness default, and that is the point rather
    than an omission: this family is priced exactly like every other equity
    family in the project so their Sharpes stay comparable (see
    BUYBACK_COST_BPS and BUYBACK_FINANCING_BPS_PER_YEAR for why each is what
    it is, including why the financing zero is a disclosure and not an
    estimate)."""
    return CrossSectionalConfig(
        cost_bps=BUYBACK_COST_BPS,
        financing_bps_per_year=BUYBACK_FINANCING_BPS_PER_YEAR,
    )


# --- production entry point -------------------------------------------------


@dataclass
class BuybackScreeningSummary:
    """run_buyback_screening's full result. Every caution this family carries
    is a TYPED FIELD here rather than a docstring paragraph a caller could
    skip — the same discipline FXScreeningSummary and BondsScreeningSummary
    keep."""

    results: list[CrossSectionalScreeningResult]
    n_trials: int
    # Universe accounting. `universe_size` is the point-in-time candidate
    # pool (every ticker that was an S&P 500 member on any day of the
    # window); the two lists below are how much of it this project could
    # actually observe. A result read without these is not interpretable.
    universe_size: int
    missing_price_data: list[str]
    tickers_without_share_history: list[str]
    # Panel shape actually replayed.
    panel_start: date | None
    panel_end: date | None
    formation_start: date
    # Defect (1): how much work the split correction actually did this run —
    # how many priced tickers had at least one split inside the window, and
    # how many share-count observations the adjustment moved. A first-class
    # count so "the correction did nothing this run" (which would mean it
    # silently stopped working) cannot go unnoticed.
    n_tickers_with_splits: int
    n_split_adjusted_observations: int
    # Defect (2): how coarse the signal really was. The median calendar age,
    # across every ticker and every trading day of the replayed panel, of the
    # filing whose count that cell carries — after the reporting lag. A
    # number in the tens of days means the panel is genuinely quarterly; a
    # number in the hundreds means large stretches are being carried a long
    # way, and every Sharpe here should be read accordingly.
    median_signal_endpoint_age_days: float
    # Defect (2), third bullet: per lookback, the fraction of otherwise-usable
    # (ticker, day) cells whose two window endpoints were the bit-identical
    # count and were therefore REFUSED rather than reported as an exact 0.00%
    # issuance. A first-class number because it is the direct measure of how
    # much of this run's cross-section the vendor's filing gaps had hollowed
    # out — a value in the tens of percent means most names had nothing new
    # filed inside their window.
    uninformative_window_rate: dict[int, float] = field(default_factory=dict)
    # Defect (3), the ticker-reassignment splice: how much data the two
    # cross-endpoint consistency checks actually refused this run. First-class
    # counts for the same reason n_split_adjusted_observations is one — a
    # correction that silently stops firing looks exactly like a correction
    # that had nothing to do, and the consequence of the former is
    # 21st-Century-Fox's share count deciding Fox Corporation's decile.
    n_share_observations_outside_price_lifecycle: int = 0
    n_implausible_market_cap_cells: int = 0
    # Realized, not assumed: mean gross notional traded per formation, per
    # spec, from the run's own FormationRecords. This is what turns the
    # module docstring's holding-period cost argument from an assertion into
    # a measurement (see build_buyback_disclosure).
    turnover_per_formation: dict[str, float] = field(default_factory=dict)
    # Per spec: the one-way cost_bps at which that spec's REALIZED edge would
    # be exactly consumed. The bonds family reports the same number for the
    # same reason (see build_bonds_disclosure) — a positive Sharpe computed
    # at an assumed 5bps means nothing until you know whether the assumption
    # is carrying it. Absent for a spec with no realized cost charge or a
    # non-positive gross return, where the quantity is meaningless.
    breakeven_cost_bps: dict[str, float] = field(default_factory=dict)
    # Per spec: the SHORT-LEG borrow rate, in bps per year, that would
    # exactly consume the realized net return. THE most important number in
    # this summary whenever a spec looks good, because financing is modeled
    # at 0.0 here (see BUYBACK_FINANCING_BPS_PER_YEAR) and a real short book
    # is not free. Both portfolio modes carry gross 1.0 of short notional (a
    # ranked short leg, or the universe hedge), so the arithmetic is direct:
    # a spec earning R per year of equity survives a borrow rate below
    # R * 10,000 bps/yr and not above it. Negative for a losing spec, which
    # is reported rather than suppressed.
    breakeven_short_borrow_bps_per_year: dict[str, float] = field(default_factory=dict)
    cost_bps: float = BUYBACK_COST_BPS
    financing_bps_per_year: float = BUYBACK_FINANCING_BPS_PER_YEAR
    disclosure: str = ""
    warnings: list[str] = field(default_factory=list)


def count_split_adjustments(
    shares_outstanding: dict[str, pd.Series], splits: dict[str, pd.Series]
) -> tuple[int, int]:
    """(tickers with at least one split in the window, share-count
    observations whose value the split correction actually changed).

    Computed by running cross_sectional_ivol.split_adjust_share_counts and
    comparing — i.e. it measures what the correction DID, not what it was
    asked to do. That distinction is the whole reason this is reported: a
    ticker can carry a split whose boundary is not detectable in its share
    series, in which case the correct behaviour is to leave the series alone
    (see split_adjust_share_counts' NO JUMP FOUND -> NO ADJUSTMENT rule), and
    such a ticker contributes to the first count but not the second."""
    n_tickers = 0
    n_observations = 0
    for ticker, raw in shares_outstanding.items():
        ticker_splits = splits.get(ticker)
        if ticker_splits is None or ticker_splits.empty or raw is None or raw.empty:
            continue
        n_tickers += 1
        adjusted = split_adjust_share_counts(raw.sort_index(), ticker_splits)
        changed = ~np.isclose(
            adjusted.to_numpy(dtype=float), raw.sort_index().to_numpy(dtype=float), equal_nan=True
        )
        n_observations += int(changed.sum())
    return n_tickers, n_observations


def median_share_count_age_days(
    shares_frame: pd.DataFrame,
    shares_outstanding: dict[str, pd.Series],
    *,
    since: date | None = None,
) -> float:
    """Median calendar age, over every populated cell of the built panel, of
    the (reporting-lagged) filing that cell's value was carried forward from.

    `since` restricts the measurement to the sample actually REPLAYED — pass
    the run's formation_start. Without it the figure is dominated by the
    warmup padding, whose 2016-2017 rows are the sparsest in the whole data
    set, and would describe a period no formation ever ranked.

    Recomputed from the sparse inputs rather than threaded out of
    build_point_in_time_share_counts, so this diagnostic cannot drift out of
    step with the panel it describes: it reads the SAME frame the harness
    was handed and asks, for each of its populated cells, how old the most
    recent visible observation was. Non-positive observations are dropped
    first, matching that function's step 2 — counting a dropped row as a
    filing would understate the real age. Returns NaN for an empty panel."""
    frame = shares_frame if since is None else shares_frame.loc[shares_frame.index.date >= since]
    if frame.empty:
        return float("nan")
    ages: list[np.ndarray] = []
    index_values = frame.index.to_numpy()
    for ticker in frame.columns:
        raw = shares_outstanding.get(ticker)
        column = frame[ticker]
        if raw is None or raw.empty or column.isna().all():
            continue
        usable_raw = raw[np.isfinite(raw) & (raw > 0.0)]
        if usable_raw.empty:
            continue
        visible = (
            pd.DatetimeIndex(
                pd.DatetimeIndex(usable_raw.index) + pd.Timedelta(days=SHARES_REPORTING_LAG_DAYS)
            )
            .unique()
            .sort_values()
        )
        if visible.empty:
            continue
        # For each panel row, the most recent visible filing date at or
        # before it. searchsorted on a sorted index is the vectorized form of
        # the ffill build_point_in_time_share_counts performs.
        positions = np.searchsorted(visible.to_numpy(), index_values, side="right") - 1
        valid = (positions >= 0) & column.notna().to_numpy()
        if not valid.any():
            continue
        age = (
            index_values[valid] - visible.to_numpy()[positions[valid]]
        ) / np.timedelta64(1, "D")
        ages.append(age.astype(float))
    if not ages:
        return float("nan")
    return float(np.median(np.concatenate(ages)))


def uninformative_window_rate(
    shares_frame: pd.DataFrame, lookback_days: int, *, since: date | None = None
) -> float:
    """Fraction of (ticker, day) cells that would have BOTH window endpoints
    usable but bit-identical at `lookback_days` — i.e. the share of the
    cross-section for which the vendor filed nothing new inside the window,
    and which signal_net_share_issuance therefore refuses rather than
    reporting as an exact 0.00% (see REFUSE_IDENTICAL_ENDPOINTS).

    Computed over the whole panel, or from `since` onward — pass the run's
    formation_start to describe the sample that was actually replayed rather
    than the warmup padding, which is dominated by the sparse early years and
    would overstate the rate. Returns NaN when no cell has usable endpoints
    at all.

    The shift is taken on the FULL frame and only then restricted to
    `since`, not the other way round: shifting a truncated frame would leave
    its first `lookback_days` rows with no earlier endpoint at all and
    silently drop the start of the replay from the measurement — which is
    precisely the stretch (the 2018 filing drought) where this rate is
    highest."""
    if shares_frame.empty or len(shares_frame) <= lookback_days:
        return float("nan")
    earlier = shares_frame.shift(lookback_days)
    usable = (
        shares_frame.notna() & earlier.notna() & (shares_frame > 0.0) & (earlier > 0.0)
    )
    identical = usable & (shares_frame == earlier)
    if since is not None:
        rows = shares_frame.index.date >= since
        usable, identical = usable.loc[rows], identical.loc[rows]
    n_usable = int(usable.to_numpy().sum())
    if n_usable == 0:
        return float("nan")
    return float(identical.to_numpy().sum()) / n_usable


def build_buyback_disclosure(
    summary: BuybackScreeningSummary, config: CrossSectionalConfig
) -> str:
    """The run's own cost and data-quality disclosure, built from its
    MEASURED numbers rather than from the module docstring's arguments.

    In particular it turns the holding-period argument into arithmetic: for
    every replayed spec it reports the realized mean turnover per formation
    and the implied annualized turnover cost (turnover x cost_bps x
    formations per year), so a reader can check for themselves that the
    longer hold pays less — and how much less — instead of taking the
    docstring's reasoning on trust."""
    lines = [
        "BUYBACK / NET-SHARE-ISSUANCE FAMILY — READ BEFORE TRUSTING ANY NUMBER.",
        (
            f"Pre-declared family size {summary.n_trials} definitions "
            f"({len(BUYBACK_LOOKBACK_DAYS)} lookbacks x {len(BUYBACK_HOLDING_DAYS)} holds x "
            f"{len(BUYBACK_PORTFOLIOS)} portfolio modes = {BUYBACK_N_CORE_TRIALS}, plus "
            f"{BUYBACK_N_ROBUSTNESS_TRIALS} winsorized robustness variants at the "
            f"{BUYBACK_ROBUSTNESS_LOOKBACK_DAYS}-day lookback), fixed before the run and used "
            "as the DSR's n_trials denominator in this family's own, never-pooled screening "
            "call."
        ),
        (
            f"Universe: {summary.universe_size} point-in-time S&P 500 members over the window, "
            f"of which {len(summary.missing_price_data)} resolved no price data and "
            f"{len(summary.tickers_without_share_history)} no usable share-count history. "
            "Eligibility is decided per formation date by sp500_membership_history.was_member, "
            "never by today's constituent list."
        ),
        (
            f"DATA CORRECTION APPLIED (defect 1, splits): {summary.n_tickers_with_splits} priced "
            f"ticker(s) had at least one split inside the window and "
            f"{summary.n_split_adjusted_observations} share-count observation(s) were restated "
            "onto a single basis by cross_sectional_ivol.split_adjust_share_counts. WITHOUT "
            "this, a reverse-splitter (GE, 1-for-8 on 2021-08-02) reads as an ~87% buyback and "
            "lands in the top long decile, and a forward-splitter (ANET, 4-for-1 on 2021-11-18) "
            "reads as ~300% dilution and lands in the bottom short decile — both entirely "
            "fictional."
        ),
        (
            f"DATA COARSENESS (defect 2, stepwise filings): the median share count in the "
            f"replayed panel was {summary.median_signal_endpoint_age_days:.0f} calendar days old "
            f"(after the {SHARES_REPORTING_LAG_DAYS}-day reporting lag). The panel is "
            "forward-filled as a STEP function and never interpolated; a count is refused "
            f"outright once carried more than {SHARES_MAX_STALENESS_DAYS} days, so a dead series "
            "cannot masquerade as a confident 0.00% issuance reading."
        ),
        (
            f"CROSS-ENDPOINT CONSISTENCY (defect 3, ticker reassignment): "
            f"{summary.n_share_observations_outside_price_lifecycle} share-count observation(s) "
            "were dated outside their ticker's own price history and refused, and "
            f"{summary.n_implausible_market_cap_cells} panel cell(s) implied a market cap "
            "impossible for an S&P 500 member and were refused. Prices and share counts come "
            "from two different yfinance endpoints joined by ticker symbol alone, and symbols "
            "get reassigned: without this, 21st Century Fox's share counts sit in front of Fox "
            "Corporation's prices and read as the largest buyback in the index (signal +1.09, "
            "99.8th percentile, maximum long), and Bank of New York Mellon carries a 12.9M-share "
            "count belonging to another issuer that doubles in 2021 and reads as the largest "
            "dilution in the index (maximum short). Both were live in this family's first "
            "production run."
        ),
        (
            "UNINFORMATIVE WINDOWS REFUSED (defect 2): share of otherwise-usable names whose two "
            "window endpoints were the identical filed count — no new share count filed anywhere "
            "inside the window, so an exact 0.00% would have been fabricated rather than "
            "observed — "
            + ", ".join(
                f"{lb}d lookback {100 * rate:.1f}%"
                for lb, rate in sorted(summary.uninformative_window_rate.items())
            )
            + ". These are refused (NaN, unranked), never ranked as zeros."
        ),
        (
            f"COSTS: {config.cost_bps}bp one-way per unit of gross notional TRADED (a full "
            "long_short book is gross 2.0, so ~10bp to establish from flat and 10bp x the "
            f"fraction of book replaced per reformation), and {config.financing_bps_per_year}"
            "bps/yr per unit of gross notional HELD. That financing zero is a DISCLOSURE, not "
            "an estimate: this project has no sourced US equity borrow rate, so any positive "
            "short-leg contribution below is optimistic by an unmeasured amount — the same "
            "known gap every equity family in this project carries."
        ),
    ]

    if summary.turnover_per_formation:
        lines.append(
            "REALIZED TURNOVER AND THE HOLDING-PERIOD ARGUMENT (measured, not assumed) — "
            "annualized cost = mean turnover per formation x cost_bps x (252 / holding_days):"
        )
        spec_by_id = {s.pattern_id: s for s in BUYBACK_FAMILY}
        for pattern_id, turnover in sorted(summary.turnover_per_formation.items()):
            holding = spec_by_id[pattern_id].holding_days
            formations_per_year = 252.0 / holding
            annual_bps = turnover * config.cost_bps * formations_per_year
            lines.append(
                f"  {pattern_id}: mean turnover {turnover:.3f} gross/formation, "
                f"{formations_per_year:.1f} reformations/yr -> {annual_bps:.1f}bp/yr"
            )

    if summary.breakeven_short_borrow_bps_per_year:
        lines.append(
            "BREAKEVEN COSTS — how much of any positive result above is the COST ASSUMPTIONS "
            "rather than the signal. 'borrow' is the short-leg borrow rate in bps/yr that would "
            "exactly consume the realized net return, and it is the number to read first, "
            "because financing here is modeled at ZERO and a real short book is not free. "
            "'trade' is the one-way cost_bps that would consume the same edge; blank where the "
            "spec's gross edge is non-positive and the quantity is meaningless."
        )
        for pattern_id in sorted(summary.breakeven_short_borrow_bps_per_year):
            borrow = summary.breakeven_short_borrow_bps_per_year[pattern_id]
            trade = summary.breakeven_cost_bps.get(pattern_id)
            trade_text = "n/a" if trade is None else f"{trade:.1f}bp one-way"
            lines.append(f"  {pattern_id}: borrow {borrow:.0f}bp/yr, trade {trade_text}")

    if summary.warnings:
        lines.append("WARNINGS: " + " | ".join(summary.warnings))
    return "\n".join(lines)


def run_buyback_screening(
    start: date = BUYBACK_FORMATION_START,
    end: date | None = None,
    provider: YFinanceProvider | None = None,
    config: CrossSectionalConfig | None = None,
) -> BuybackScreeningSummary:
    """THE production entry point for the buyback / net-share-issuance
    family, scoped to exactly BUYBACK_FAMILY's 14 definitions and their own
    n_trials.

    Universe: get_universe_over(start, end) — every ticker that was an S&P
    500 member on ANY day of the screening window, NOT today's snapshot —
    gated per formation date by the harness's default point-in-time
    membership function. Same primitive and same reasoning as
    run_round_d1_screening and run_round_c_screening. `start` must be >=
    MEMBERSHIP_DATA_START, checked here so the error names the actual fix,
    and is separately floored by the share-data reality documented at
    BUYBACK_FORMATION_START.

    THE DATA FETCH IS THREE STEPS, deliberately sequenced, and the middle one
    is not what it looks like:
     (1) Close-only daily prices for the whole point-in-time universe via
         get_price_history — the dividend-ADJUSTED total-return basis, which
         is what every realized return in the harness comes off. This
         family's signal never reads a price at all.
     (2) get_market_cap_basis, used ONLY for its per-ticker split ratios.
         Its close frame is deliberately DISCARDED: this family never
         multiplies a share count by a price, so it has no market cap to get
         onto a consistent basis and no use for a dividend-unadjusted price.
         The call is made anyway because it is the one BATCHED source of
         dated split ratios in this project — yf.Ticker(t).splits is a
         network call per ticker, the same cost problem
         get_shares_outstanding already has, and there is no reason to pay it
         twice.
     (3) Real point-in-time shares-outstanding history via
         get_shares_outstanding, fetched only for tickers that actually
         resolved a price (a ticker with no price can never be eligible at a
         formation regardless of its share count, and this is a per-ticker
         network call).
    Steps (2) and (3) are what build_point_in_time_share_counts combines into
    the step panel the signal ranks on.

    Returns a BuybackScreeningSummary: the results, the universe accounting,
    the measured effect of the split correction, the measured coarseness of
    the share panel, the realized per-spec turnover, and the disclosure built
    from all of it. Every one of those is a required part of the result
    rather than a logging detail — the same discipline run_round_c_screening
    and run_bonds_screening state for their own."""
    if start < MEMBERSHIP_DATA_START:
        raise ValueError(
            f"Buyback screening start {start.isoformat()} predates point-in-time membership "
            f"coverage ({MEMBERSHIP_DATA_START.isoformat()}) — a formation before that date "
            "would silently see an empty universe."
        )
    # date.today() is the LOCAL date, which is immaterial here: this is only
    # the exclusive end bound of a price fetch, where a day either side just
    # includes or omits the most recent bar.
    end = end if end is not None else date.today()  # noqa: DTZ011
    provider = provider if provider is not None else YFinanceProvider()
    config = config if config is not None else default_buyback_config()
    config.formation_start = start

    warnings: list[str] = []
    universe = get_universe_over(start, end)
    padded_start = start - timedelta(days=BUYBACK_PRICE_HISTORY_PADDING_CALENDAR_DAYS)

    close, missing_price = provider.get_price_history(universe, padded_start, end)
    if close.empty:
        summary = BuybackScreeningSummary(
            results=[],
            n_trials=BUYBACK_N_TRIALS,
            universe_size=len(universe),
            missing_price_data=missing_price,
            tickers_without_share_history=[],
            panel_start=None,
            panel_end=None,
            formation_start=start,
            n_tickers_with_splits=0,
            n_split_adjusted_observations=0,
            median_signal_endpoint_age_days=float("nan"),
            uninformative_window_rate={},
            warnings=["No price data resolved for any universe member — nothing was screened."],
        )
        summary.disclosure = build_buyback_disclosure(summary, config)
        return summary

    priced = list(close.columns)
    if missing_price:
        warnings.append(
            f"{len(missing_price)} of {len(universe)} point-in-time universe members resolved no "
            "price data and can never be ranked (see cross_sectional.py's survivorship "
            "disclosure — index leavers are the bulk of these)."
        )

    # Splits only. See the docstring above on why the close from this call is
    # discarded rather than used.
    _mcap_close, splits, _missing_basis = provider.get_market_cap_basis(priced, padded_start, end)
    shares, missing_shares_fetch = provider.get_shares_outstanding(priced, padded_start, end)

    # DEFECT (3), THE TICKER-REASSIGNMENT SPLICE — see the module docstring.
    # Applied BEFORE build_point_in_time_share_counts, on the raw filing-dated
    # series, for the same reason the split adjustment is: this is a judgement
    # about each observation's OWN date against the price series' own dates,
    # and step 3 of that builder shifts every date by the reporting lag.
    shares, out_of_lifecycle = restrict_share_counts_to_price_lifecycle(shares, close)
    n_out_of_lifecycle = sum(out_of_lifecycle.values())
    if out_of_lifecycle:
        warnings.append(
            f"{n_out_of_lifecycle} share-count observation(s) across {len(out_of_lifecycle)} "
            "ticker(s) were dated outside the ticker's own price history and refused — the "
            "yfinance price and fundamentals endpoints disagreed about which company holds the "
            "symbol (see the module docstring's defect 3)."
        )

    shares_frame, unusable_shares = build_point_in_time_share_counts(close, shares, splits)
    # The magnitude half of the same check. This family never needs a market
    # cap for any other purpose — `close` here is the dividend-ADJUSTED total
    # -return price, which is deliberately not a market-cap basis (see
    # cross_sectional_ivol.build_point_in_time_market_cap's "TWO INPUTS, ONE
    # BASIS") — but it is within a factor of a ticker's own accumulated
    # dividend yield of one, which is nowhere near the orders of magnitude
    # that separate a real S&P 500 member from a spliced one (BNY reads
    # $0.4-1.0B against a true $40-110B; COL reads $6-53M against $18B). A
    # refused cell simply leaves that ticker unranked at any formation whose
    # window needs it, which is this family's existing answer to "the share
    # count here cannot be observed".
    implausible = implausible_market_cap_mask(shares_frame * close)
    n_implausible = int(implausible.to_numpy().sum())
    shares_frame = shares_frame.mask(implausible)
    if n_implausible:
        warnings.append(
            f"{n_implausible} panel cell(s) across "
            f"{int((implausible.to_numpy().sum(axis=0) > 0).sum())} ticker(s) implied a market "
            "cap impossible for an S&P 500 member and were refused — the price and share-count "
            "endpoints are not describing the same company there (see defect 3)."
        )

    tickers_without_share_history = sorted(set(missing_shares_fetch) | set(unusable_shares))
    if tickers_without_share_history:
        warnings.append(
            f"{len(tickers_without_share_history)} of {len(priced)} priced tickers have no usable "
            "point-in-time share-count history and are never ranked (get_shares_full's ~2015-10 "
            "floor and per-ticker gaps — see the module docstring's defect 2)."
        )

    n_tickers_with_splits, n_split_adjusted = count_split_adjustments(shares, splits)
    if n_tickers_with_splits and not n_split_adjusted:
        # Every ticker that had a split came back unadjusted. That is
        # POSSIBLE (a whole universe of already-restated series) but it is
        # also what a silently broken correction looks like, and the
        # consequence of the latter is GE-in-the-long-decile. Loud.
        warnings.append(
            f"{n_tickers_with_splits} ticker(s) carried splits in the window but the split "
            "correction changed ZERO observations — verify split_adjust_share_counts is still "
            "detecting boundaries before trusting any ranking below."
        )

    data = CrossSectionalData(close=close, shares_outstanding=shares_frame)
    results = screen_cross_sectional_universe(data, BUYBACK_FAMILY, config)
    turnover, breakeven_cost, breakeven_borrow = _replay_diagnostics(data, config, results)

    summary = BuybackScreeningSummary(
        results=results,
        n_trials=BUYBACK_N_TRIALS,
        universe_size=len(universe),
        missing_price_data=missing_price,
        tickers_without_share_history=tickers_without_share_history,
        panel_start=close.index[0].date(),
        panel_end=close.index[-1].date(),
        formation_start=start,
        n_tickers_with_splits=n_tickers_with_splits,
        n_split_adjusted_observations=n_split_adjusted,
        median_signal_endpoint_age_days=median_share_count_age_days(
            shares_frame, shares, since=start
        ),
        uninformative_window_rate={
            lookback: uninformative_window_rate(shares_frame, lookback, since=start)
            for lookback in BUYBACK_LOOKBACK_DAYS
        },
        n_share_observations_outside_price_lifecycle=n_out_of_lifecycle,
        n_implausible_market_cap_cells=n_implausible,
        turnover_per_formation=turnover,
        breakeven_cost_bps=breakeven_cost,
        breakeven_short_borrow_bps_per_year=breakeven_borrow,
        cost_bps=config.cost_bps,
        financing_bps_per_year=config.financing_bps_per_year,
        warnings=warnings,
    )
    summary.disclosure = build_buyback_disclosure(summary, config)
    return summary


# Trading days per year, for turning a mean daily return into the annual
# rate the breakeven borrow arithmetic is quoted in. Matches the convention
# metrics.sharpe_ratio already annualizes with.
TRADING_DAYS_PER_YEAR = 252.0


def _replay_diagnostics(
    data: CrossSectionalData,
    config: CrossSectionalConfig,
    results: list[CrossSectionalScreeningResult],
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """Per replayed spec: (mean turnover per formed formation, breakeven
    one-way cost_bps, breakeven short-leg borrow in bps/yr).

    A second, clearly-labelled replay pass purely for these diagnostics:
    screen_cross_sectional_universe returns aggregate results, not each
    spec's FormationRecords or daily series, and both the holding-period
    cost argument and the short-borrow disclosure in this module's docstring
    are only worth stating if they are measured. Doing it here, rather than
    widening the shared harness's return type, keeps that type unchanged for
    every other family — the same choice run_bonds_screening makes for its
    own diagnostic replay.

    TURNOVER excludes skipped formations: their turnover is the cost of
    going FLAT, which is real but is not the reformation cost that number is
    about.

    BREAKEVEN COST_BPS, following build_bonds_disclosure's arithmetic
    exactly, since the harness charges turnover cost linearly in cost_bps:
    with `charged` the cost actually deducted over the replay and `net` the
    realized cumulative net return, gross = net + charged, and the cost that
    would exactly consume the edge is cost_bps * gross / charged. Omitted
    when nothing was charged or the gross edge is non-positive, where the
    quantity has no meaning.

    BREAKEVEN SHORT BORROW: the annualized net return, expressed in bps.
    Both portfolio modes hold gross 1.0 of short notional — a ranked short
    leg for long_short, the equal-weighted universe hedge for
    long_universe_hedged — so a borrow rate of B bps/yr costs exactly B bps
    of equity per year, and the spec survives B below this figure and not
    above it. Reported for losing specs too (as a negative), because
    suppressing it there would make the field look like a property only
    winners have."""
    spec_by_id = {s.pattern_id: s for s in BUYBACK_FAMILY}
    turnover: dict[str, float] = {}
    breakeven_cost: dict[str, float] = {}
    breakeven_borrow: dict[str, float] = {}
    for result in results:
        spec = spec_by_id.get(result.pattern_id)
        if spec is None:
            continue
        replay = run_cross_sectional_backtest(data, spec, config)
        formed = [f for f in replay.formations if f.skipped_reason is None]
        if formed:
            turnover[result.pattern_id] = float(np.mean([f.turnover for f in formed]))

        daily = replay.daily_returns
        if daily.empty:
            continue
        net_cumulative = float(daily.sum())
        breakeven_borrow[result.pattern_id] = (
            float(daily.mean()) * TRADING_DAYS_PER_YEAR * 10_000.0
        )
        charged = replay.total_cost
        gross_cumulative = net_cumulative + charged
        if charged > 0.0 and gross_cumulative > 0.0:
            breakeven_cost[result.pattern_id] = config.cost_bps * gross_cumulative / charged
    return turnover, breakeven_cost, breakeven_borrow


__all__ = [
    "BUYBACK_CITATION",
    "BUYBACK_COST_BPS",
    "BUYBACK_FAMILY",
    "BUYBACK_FINANCING_BPS_PER_YEAR",
    "BUYBACK_FORMATION_START",
    "BUYBACK_HOLDING_DAYS",
    "BUYBACK_LOOKBACK_DAYS",
    "BUYBACK_MAX_LOOKBACK_ROWS",
    "BUYBACK_N_CORE_TRIALS",
    "BUYBACK_N_ROBUSTNESS_TRIALS",
    "BUYBACK_N_TRIALS",
    "BUYBACK_PORTFOLIOS",
    "BUYBACK_PRICE_HISTORY_PADDING_CALENDAR_DAYS",
    "BUYBACK_RANK_FRACTION",
    "BUYBACK_ROBUSTNESS_LOOKBACK_DAYS",
    "BUYBACK_WINSORIZE_QUANTILE",
    "MIN_SIGNAL_OBS_FRACTION",
    "MIN_WINSORIZE_NAMES",
    "REFUSE_IDENTICAL_ENDPOINTS",
    "SHARES_MAX_STALENESS_DAYS",
    "SHARES_REPORTING_LAG_DAYS",
    "BuybackScreeningSummary",
    "build_buyback_disclosure",
    "build_point_in_time_share_counts",
    "count_split_adjustments",
    "default_buyback_config",
    "median_share_count_age_days",
    "run_buyback_screening",
    "signal_net_share_issuance",
    "uninformative_window_rate",
    "winsorize_cross_section",
]
