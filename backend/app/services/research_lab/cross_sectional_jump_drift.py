"""POST-JUMP DRIFT / REVERSAL — a cross-sectional equity family built on a
Barndorff-Nielsen/Shephard-Huang/Tauchen bipower-variation jump test adapted
to DAILY returns, expressed against cross_sectional.py's harness and following
the structural conventions of cross_sectional_illiq.py and
cross_sectional_seasonality.py (every formula individually cited from a source
actually read, the family a bounded literal whose length IS the n_trials
denominator, point-in-time correctness argued structurally).

Needs ONLY daily OHLC — no new data pipeline. OHLC rather than closes alone
because this family opts into the EDGE spread cost model (see COSTS).

THE PRE-REGISTRATION IS THE CONTRACT. data/research_runs/
jump_drift_2026-08-30_preregistration.txt was written before this module
existed and before any number was computed; the spec grid, the thresholds, the
hypothesis directions and the reading rules below are transcribed from it, not
chosen after seeing results.


============================================================================
CITATIONS — every one of these PDFs was downloaded and text-extracted in full
on 2026-08-30. The formulas below are transcribed from that text, not recalled.
============================================================================
 [BNS06] Ole E. Barndorff-Nielsen & Neil Shephard, "Econometrics of Testing
         for Jumps in Financial Economics Using Bipower Variation", JOURNAL OF
         FINANCIAL ECONOMETRICS 4(1), 2006, pp. 1-30, doi:10.1093/jjfinec/
         nbi022. Read from the author-hosted PDF at public.econ.duke.edu/~get/
         browse/courses/883/Spr15/COURSE-MATERIALS/Z_Papers/BNSJFEC2006.pdf.
 [HT05]  Xin Huang & George Tauchen, "The Relative Contribution of Jumps to
         Total Price Variance", JOURNAL OF FINANCIAL ECONOMETRICS 3(4), 2005,
         pp. 456-499. Read from public.econ.duke.edu/~get/wpapers/rcj.pdf.
 [SAV12] Pavel Savor, "Stock Returns after Major Price Shocks: The Impact of
         Information", JOURNAL OF FINANCIAL ECONOMICS 106(3), 2012, pp.
         635-659. Read from the author's Wharton-hosted May 2012 final
         version.
 [JZ17]  George J. Jiang & Kevin X. Zhu, "Information Shocks and Short-Term
         Market Underreaction", JOURNAL OF FINANCIAL ECONOMICS 124(1), 2017,
         pp. 43-64. HONEST FLAG: full text is behind ScienceDirect and was NOT
         fetched. Only the publisher/SSRN abstract was read, so [JZ17] is
         cited for its headline direction and horizon and nothing finer.


============================================================================
THE JUMP TEST — EXACT FORMULAS, QUOTED
============================================================================
[HT05] p.459, verbatim, for M returns r_{t,1..M} inside one period t:

    RV_t = SUM_{j=1..M} r_{t,j}^2
    BV_t = mu_1^{-2} (M/(M-1)) SUM_{j=2..M} |r_{t,j-1}| |r_{t,j}|
         = (pi/2)  (M/(M-1)) SUM_{j=2..M} |r_{t,j-1}| |r_{t,j}|
    mu_a = E(|Z|^a),  Z ~ N(0,1),  a > 0

So mu_1 = sqrt(2/pi) and mu_1^{-2} = pi/2. [BNS06] Eq. (5) states
mu_1 = sqrt(2)/sqrt(pi) independently; the two sources agree and pi/2 IS the
bipower scaling constant.

[HT05] p.460, verbatim, the joint asymptotic variance of (RV, BV) under the
no-jump null: nu_qq = 2, nu_qb = 2, nu_bb = (pi/2)^2 + pi - 3, hence
nu_bb - nu_qq = (pi/2)^2 + pi - 5. [BNS06] Eq. (6) gives the identical
constant, calling it theta ~= 0.6090. Two independent sources, one number.

[HT05] p.461 Eq. (3), verbatim, realized TRI-POWER QUARTICITY — the
jump-robust estimator of the integrated quarticity that scales the test:

    TP_t = M mu_{4/3}^{-3} (M/(M-2))
             SUM_{j=3..M} |r_{t,j-2}|^{4/3} |r_{t,j-1}|^{4/3} |r_{t,j}|^{4/3}

[HT05] p.462 Eq. (2) and Eq. (9), verbatim — the relative jump measure and the
RATIO-plus-MAX-adjusted z-statistic, which is THE statistic implemented here:

    RJ_t      = (RV_t - BV_t) / RV_t
    z_TP,rm,t = RJ_t / sqrt( (nu_bb - nu_qq) (1/M) max(1, TP_t / BV_t^2) )
              -> N(0,1) as M -> infinity, under the null of no jumps.

[BNS06]'s own "adjusted ratio jump test" (its Eq. 14) is this statistic with
the opposite sign convention and quad-power in place of tri-power quarticity.
[HT05] p.460 says so outright: "An equivalent statistic, -RJ_t, called the
ratio statistic, is proposed and studied by Barndorff-Nielsen and Shephard
(2006)." This module uses [HT05]'s orientation (POSITIVE under jumps) with
one-sided upper-tail critical values. A sign convention, not a different test.

WHY z_TP,rm AND NOT THE OTHER FOUR VARIANTS [HT05] defines. This is the single
most important methodological choice in the file and it rests on the source's
own Monte Carlo, quoted verbatim from [HT05] pp.469-470:

    "With the exception of the z_TP,rm,t statistic, the sampling frequency has
     a significant impact on the size. As the sampling frequency decreases,
     that is, the sampling interval increases, the actual sizes of all
     statistics except z_TP,rm,t increase above the Monte Carlo confidence
     band"
    "Note that z_TP,rm,t in the bottom panel appears to have the best size
     property among the five statistics."

z_TP,rm is the ONE variant Huang & Tauchen find size-robust as the sampling
interval lengthens. This module lengthens the sampling interval to its extreme,
so it is the only defensible choice of the five.


============================================================================
THE DAILY ADAPTATION AND ITS HONEST STATISTICAL COST — READ THIS BEFORE
TRUSTING ANY z VALUE THIS MODULE PRINTS
============================================================================
THE DATA CONSTRAINT. yfinance_provider.py serves DAILY OHLCV bars. Its
get_intraday_bars exists but its shortest interval is 60m over a rolling ~60-day
window — unusable for an 11-year replay. There is no tick, trade or 5-minute
data in this project.

WHY LEE & MYKLAND (2008) IS NOT IMPLEMENTED HERE. Their test standardizes each
return by a LOCAL spot volatility from a short trailing bipower window, and its
critical values come from an extreme-value (double-exponential) limit derived
under in-fill asymptotics in which the sampling interval shrinks INSIDE a
locally constant volatility regime.

CORRECTED BY THE VERIFICATION PASS, 2026-08-30, after the paper was re-read:
this file previously said that handing Lee-Mykland daily bars "would produce a
statistic whose TABULATED critical values do not describe it". That was
overstated on three counts and is retracted. (1) Nothing in Lee & Mykland is
tabulated — their C_n and S_n are closed-form expressions, not a table.
(2) The paper does NOT restrict itself to intraday data: it gives an explicit
window recommendation for DAILY data (K = 16, and K = 7 for weekly) and runs
24-hour-frequency simulations, and it states outright that "our asymptotic
result is not affected, although small-sample distributions of our test will be
affected at lower frequencies such that the precision of our test at lower
frequency decreases". (3) So the limit itself survives daily sampling; what
collapses is finite-sample size and power.

WHAT IS ACTUALLY TRUE, AND STILL SUFFICIENT AS A REASON NOT TO IMPLEMENT IT:
daily bars sit at the extreme low-frequency end of Lee & Mykland's own grid,
where the paper's own numbers show spurious detection running roughly 44x to
380x the 15-minute rate, and only ~2% of jumps sized at 10% of volatility being
detected at all. A test with that size and that power would add nothing this
module's own measured size distortion (below) does not already show. It is not
implemented and no claim about its behaviour on this data is made.

WHAT IS DONE INSTEAD, PRECISELY. BNS/HT is a WITHIN-PERIOD test: M returns
sampled inside one period, asking whether that period's quadratic variation
contains a jump. Here the PERIOD is a rolling window of `window` TRADING DAYS
and the M "intra-period" returns are the `window` DAILY log returns in it. The
algebra is unchanged — a semimartingale has no opinion about calendar units —
but the asymptotic regime is NOT the one the sources validated:

 (a) The in-fill CLT wants delta -> 0 at fixed period length. Here delta is
     pinned at ONE TRADING DAY and cannot shrink; the limit is approached only
     by lengthening `window`. The N(0,1) limit is an APPROXIMATION whose
     finite-sample accuracy is not [HT05]'s. Their Monte Carlo samples a
     390-minute trading day at 1, 3, 5 and 30 minutes, i.e. M in
     {390, 130, 78, 13}, so window = 21 / 63 sit inside that RANGE of M — which
     is why the approximation is usable at all — but their returns are minutes
     apart inside one volatility regime, while 63 daily returns span a quarter
     across which volatility genuinely moves.

     CORRECTED BY THE VERIFICATION PASS, 2026-08-30. This file previously said
     [HT05]'s Monte Carlo "spans M = 12 to 288". It does not: 12 and 288 are two
     grid points in [BNS06]'s Table 1 (n = 12, 24, 72, 288, 1152), transposed
     onto the wrong paper. [HT05]'s own range is 13 to 390 (its Tables 5 and 11
     list only the 1/3/5/30-minute sampling intervals). The CONCLUSION is
     unchanged — 21 and 63 fall inside 13..390 exactly as they fell inside the
     range originally written — but a number was attributed to a source that
     does not contain it, which is the error class this project treats as most
     serious, so it is corrected in place and the correction is recorded rather
     than quietly overwritten.
 (b) THEREFORE the nominal significance level is NOT a trustworthy
     false-positive rate. Daily equity returns are fat-tailed and
     volatility-clustered relative to the null's locally-constant-volatility
     Brownian semimartingale; both push toward OVER-rejection. JUMP_Z_CRITICAL
     values below carry nominal Gaussian labels and are treated as DECLARED
     TUNING PARAMETERS, never as calibrated p-values. compute_jump_diagnostics
     MEASURES the realized firing rate against the nominal alpha so a reader
     sees the size distortion instead of having to infer it.
 (c) The statistic is a WINDOW verdict — a jump happened somewhere in these
     `window` days — not a DAY verdict. The attribution rule below is what
     turns one into the other, and it is this module's own construction.


============================================================================
DAY-LEVEL ATTRIBUTION — THIS PART IS NOT FROM A PAPER, AND SAYS SO
============================================================================
No source was found that localizes a single day inside a rejected BNS/HT
window. The rule below is this module's own. It was chosen for being
deterministic, strictly backward-looking, and falsifiable by unit test, and it
is labelled as unsourced rather than dressed up in a citation:

    Day d is a JUMP DAY iff BOTH hold for the window of `window` daily log
    returns ENDING AT AND INCLUDING d:
      (i)  z_TP,rm(that window) > z_crit     [the window contains a jump]
      (ii) |r_d| == max |r_j| over that window
                                             [and d is its dominant move]
    The jump's signed size is r_d itself.

Because the window ENDS at d, both conditions read only returns up to and
including d: a flag is strictly backward-looking and can never be revised by
later data. That is what makes precomputing the whole panel point-in-time
correct, and it is unit-tested by poisoning future rows and asserting
bit-identity.

test_cross_sectional_jump_drift.py is required to prove, on synthetic ground
truth, that this rule fires on a KNOWN injected jump day and stays silent on an
ordinary high-volatility day with no injected discontinuity. The
pre-registration's stopping rule is explicit that if it could not be made to do
both, the honest outcome would be "no daily-data-feasible jump test could be
responsibly implemented" with no substitute shipped.

RETURNS ARE LOG RETURNS, ln(C_t / C_{t-1}), not simple returns. Required, not
stylistic: RV/BV/TP discretize the quadratic variation of the LOG-price
semimartingale in both sources ([HT05] p.459 defines r_{t,j} as a difference of
p, its log price).


============================================================================
THE ECONOMIC HYPOTHESES — AND WHY THE LITERATURE POINTS BOTH WAYS
============================================================================
[SAV12] is the directly relevant prior because its horizons ARE this family's
horizons. Its Table 4 regresses post-event cumulative abnormal return on the
event-day abnormal return AR_0; the AR_0 coefficient is the drift(+) /
reversal(-) coefficient. Transcribed from the PDF:

    Panel A, Full sample (N = 120,221):
        AR_{1,5}  -0.062 [t=-13.2]   AR_{1,10} -0.065 [t=-6.0]
        AR_{1,20} -0.081 [t= -7.1]   AR_{1,40} -0.115 [t=-12.2]
    Panel B, Unreported ("no-information") sample:
        AR_{1,5}  -0.095 [t=-15.2]   ...   AR_{1,40} -0.157 [t=-12.3]
    Panel C, Reported ("information") sample:
        AR_{1,5}  -0.003 [t= -0.4]   ...   AR_{1,40} -0.025 [t= -1.9]

and from its body: "While no-information stocks experience large reversals
(amounting to 9.6% of the initial price shock), information ones do not and
even exhibit drift."

[JZ17]'s abstract, by contrast, uses jumps as the information-shock proxy and
reports that "Strategies long (short) stocks with positive (negative) lagged
jump returns earn significantly positive returns over the next one- to
three-month horizons" — CONTINUATION, but at ONE TO THREE MONTHS.

THE PRE-REGISTERED PRIOR, fixed before the run: the literature points BOTH ways
at DIFFERENT horizons. Unconditional on any information proxy — which is all
this project can do, having no analyst-recommendation data — [SAV12]'s
full-sample coefficients are NEGATIVE and strongly significant at exactly 5, 10
and 20 days, this family's horizons. So THE LITERATURE-IMPLIED PRIOR AT THESE
HORIZONS IS REVERSAL, while [JZ17]'s continuation lives at horizons this family
does not reach. Written down in advance so a reversal result cannot be
presented as a surprise and a continuation result is recognized as
contradicting [SAV12] rather than confirming [JZ17].


============================================================================
THE 24 PRE-DECLARED SPECS
============================================================================
Four dimensions, fully crossed, frozen by the pre-registration:

  z-threshold  2: 3.0902 (nominal one-sided alpha=0.001), 2.3264 (alpha=0.010)
  window       2: 21 trading days (~1 month), 63 (~1 quarter)
  holding h    3: 5, 10, 20 trading days
  direction    2: cont (H_CONT, long up-jumpers), rev (H_REV, long down-jumpers)
  = 24 = JUMP_SPEC_CEILING, asserted in _build_jump_drift_family().

  pattern_id: jump_{cont|rev}_w{21|63}_a{001|010}_h{5|10|20}

ON DECLARING BOTH DIRECTIONS, which cross_sectional_illiq.py explicitly
declines to do. A long-short book is antisymmetric under a sign flip UP TO
COSTS: H_REV's GROSS return is exactly -1 times H_CONT's, while the cost drag is
SUBTRACTED from both, so the two are near-mirrors rather than independent
trials and declaring both roughly doubles n_trials for roughly one family's
worth of real search. That error is CONSERVATIVE — it makes every DSR harder to
pass, never easier — and it is accepted deliberately, because the brief
requires both hypotheses pre-declared and screened rather than one chosen after
the fact. n_trials will NOT be shrunk back to 12 afterwards on the mirror-image
argument; that is precisely the post-hoc trial-count laundering this project
has rejected before (see cross_sectional_patterns_round_d.py).

NOT SEARCHED, fixed at one value each: rank_fraction 0.40, portfolio
long_short, leg_weighting magnitude (the harness default).

THE EVENT LOOKBACK EQUALS h, and that is a real confound, disclosed in advance
rather than discovered later. A formation reads jumps in the trailing h trading
days, so every detected jump is traded exactly once, at the first formation on
or after it, with 0..h-1 days of delay. Consequence: mean signal staleness is
~h/2, so the h dimension confounds HORIZON with STALENESS. The alternative — a
fixed 5-day event window at every h — would instead discard 75% of events at
h=20. Neither is free; this one was chosen, declared, and is not revisited.


============================================================================
COSTS
============================================================================
config.cost_model = "edge_spread": each ticker's own trailing effective
HALF-spread from spread_estimator.build_edge_half_spread_frame (the validated
Ardia, Guidotti & Kroencke, JFE 2024, EDGE estimator over daily OHLC, full
spread / 2) at its COST_MODEL_WINDOW_DAYS = 63 production window, charged on
that ticker's traded notional at each formation. Reused, not reinvented.
cost_bps = 5.0 (DEFAULT_XS_COST_BPS) is the per-ticker fallback where no EDGE
estimate resolves, and the fallback notional is reported per spec.

config.financing_bps_per_year = 0.0 — the harness default and the value every
other equity family here uses, because this project has no sourced
securities-borrow feed (a known OPEN paid-data gap). A dollar-neutral equity
long-short is approximately self-financing, but the short leg's borrow is a
real cost that is NOT charged. Disclosed, not modeled.

NOT MODELED, declared in advance: market impact, commissions, borrow, and — the
one that matters most for THIS family — POST-JUMP SPREAD WIDENING. EDGE
estimates a TRAILING 63-day spread, so it prices the stock's normal-times
spread, not the wider one it actually trades at in the days right after a jump.
This family's true costs are therefore UNDERSTATED by an unmeasured amount and
a marginal positive result must not be read as tradeable.


============================================================================
UNIVERSE AND SURVIVORSHIP
============================================================================
sp500_membership_history.get_universe_over(start, end) supplies the candidate
pool; sp500_membership_history.was_member (the harness default membership_fn)
gates every formation date. ticker_universe.SCREENING_UNIVERSE is NOT used and
is not imported. A start before MEMBERSHIP_DATA_START is rejected loudly, since
was_member answers False for everyone there.

RESIDUAL SURVIVORSHIP, not fixed by the above and specifically dangerous HERE.
That module's own KNOWN LIMITS record that yfinance returns no price history for
~48% of tickers that left the index in the trailing 5 years — precisely the
acquired and failed names — and that a few resolve as RECYCLED tickers now
belonging to a different company. The point-in-time gate removes the LOOK-AHEAD
half of survivorship bias; it cannot manufacture prices no free vendor sells.
The unpriceable-ticker count is returned as a first-class part of the result,
never a log line.

Why it bites this family in particular: a failed company's terminal decline IS a
large down-jump. The missing names are therefore disproportionately down-jump
events with catastrophic forward returns, so their absence should FLATTER a
continuation book's short leg and PENALIZE a reversal book's short leg.


============================================================================
WHAT WOULD MAKE A POSITIVE RESULT HERE FAKE — declared before the run
============================================================================
 1. SHORT-HORIZON REVERSAL IS A KNOWN, SEPARATE ANOMALY. Lehmann (1990) and
    Jegadeesh (1990) document weekly/monthly reversal in ordinary returns with
    no jump test anywhere. A positive H_REV result is interesting only if it is
    about JUMPS rather than about large returns, which is why
    compute_jump_diagnostics reports the realized firing rate and the mean |r|
    on flagged days: a reader must be able to judge whether the jump test does
    anything a plain |return| threshold would not.
 2. THE SIZE DISTORTION of the daily adaptation. A measured firing rate far
    above nominal alpha means the detector is mostly firing on fat tails, and
    the family is a return-magnitude sort wearing a jump test's name.
 3. TRIAL COUNT. n_trials = 24 covers THIS grid only. It does not cover the
    literature scan that nominated this family, nor the many other families
    this project has screened. Every DSR here is an UPPER BOUND.
 4. THIN LEGS. rank_fraction 0.4 of a flagged-only cross-section can be a
    handful of names; avg_names_per_leg and n_skipped_formations are reported
    per spec, and a spec whose legs sit near the floor is single-name noise.


============================================================================
PRODUCTION RESULT — AN HONEST NEGATIVE ON BOTH HYPOTHESES, PLUS ONE MARGINAL
ASYMMETRIC EFFECT THAT THIS GRID CANNOT TRADE
(header amended by the verification pass: "one REAL asymmetric effect" until
the event study's standard errors were re-derived under event clustering —
see the correction at the end of this section)
============================================================================
Run 2026-08-30 over 2015-01-07..2026-08-29 (run_tag "jump_drift_2026-08-30",
family_key "jump_drift", 24 rows in cross_sectional_trial_results). 768
point-in-time candidates, 625 priced, 143 unpriceable; 2927 realized trading
days per spec; n_trials 24, sigma_SR 0.3842. The full report, with every
number and every caveat, is data/research_runs/jump_drift_2026-08-30.txt.

ALL 24 SPECS ARE NET-NEGATIVE (-0.213 to -1.427) and every DSR is 0.000-0.001.
But the net column is not where the answer lives, because this family's cost
model turned out to be the dominant term (see COSTS BELOW). The answer lives
in the zero-cost attribution: gross Sharpes are exactly antisymmetric mirror
pairs, so their mean is +0.0000 by construction and carries no information,
while WHICH direction wins each of the 12 pairs does — and it is 5
continuation to 7 reversal, a coin flip. The best gross Sharpe in the family
is +0.5290, BELOW the +0.7606 expected from the best of 24 equally-skilled
zero-edge trials. Neither H_CONT nor H_REV is supported.

THE EVENT STUDY SAYS THE SAME THING AND EXPLAINS WHY. Applying the
pre-registered reading rule mechanically gives NULL at EVERY horizon and
detector setting — because BOTH up- and down-jumps are followed by negative
abnormal returns, which is neither the continuation pattern nor the reversal
pattern. (This sentence said "essentially every" until the verification pass
fixed the verdict bug documented in PostJumpEventStudy.verdict: one cell,
w=21/alpha=0.001/h=1, was being emitted as CONTINUATION on an up-jump
abnormal return of +0.0001% with p=0.998. With an insignificant side no
longer permitted to vote, the "essentially" is gone and the reading is NULL
across the board.) What is actually present is ONE-SIDED: a stock that
jumps DOWN keeps underperforming its own baseline at every horizon (w=21,
alpha=0.001: -0.26%/-0.41%/-0.71%/-0.62% at h=1/5/10/20, all p <= 0.0015),
while a stock that jumps UP does essentially nothing. A dollar-neutral
long-short book that trades both sides therefore has one live leg and one
dead one, which is exactly the null the traded specs report. The down-side
effect survives a post-hoc market adjustment at w=21 nearly untouched
(-0.6167% vs -0.6170% at h=20), so it is a stock-level effect and not a
market-timing artifact — directionally consistent with Jiang & Zhu's
underreaction reading, and against Savor's full-sample reversal coefficients
at exactly the horizons those coefficients cover.

BUT THOSE p-VALUES ARE TOO SMALL, AND THE EFFECT IS MARGINAL RATHER THAN
STRONG. Found by the verification pass, 2026-08-30, and it is the most
important correction on this page. The bootstrap above resamples non-jump days
INDEPENDENTLY WITHIN EACH TICKER — which is what the pre-registration's section
9 specified and is therefore what this module still computes — but jump events
are heavily CLUSTERED IN CALENDAR TIME, and that clustering is exactly the
dependence an independent resample destroys. The 3,304 down-jump events at
w=21 / alpha=0.001 fall on only 1,424 distinct dates, with 78 of them on
2025-04-03 alone and 7.7% of all events on just eight dates. Events sharing a
date share that date's market shock, so they are nowhere near independent draws
and the pooled mean's true standard error is much larger than the per-ticker
bootstrap's.

Re-running the same statistic under a DATE-CLUSTERED bootstrap (resample whole
event DATES with replacement, carrying every event on a drawn date together,
4000 draws) instead of per-ticker independent draws, all four down cells at
w=21 / alpha=0.001:

    h      abnormal    i.i.d. t    CLUSTERED t   SE inflation   clustered p
    ---   ---------   ---------   ------------   ------------   -----------
     1     -0.2577%      -4.04         -1.44         2.81x         0.11
     5     -0.4110%      -3.75         -1.88         1.99x         0.038
    10     -0.7125%      -4.65         -2.62         1.78x         0.0050
    20     -0.6176%      -3.06         -2.20         1.39x         0.027

The standard error is understated by 1.4x to 2.8x, worst at the SHORT horizons,
which is exactly where same-day cross-sectional correlation dominates. Two
things follow. First, h=1 — reported above at p = 0.0005 — is p = 0.11 once
clustering is priced in, i.e. NOT significant at all; the "at every horizon"
claim above does not survive. Second, the surviving cells sit at p ~ 0.005 to
0.038, and this run reports 32 event-study cells (4 detector settings x 4
horizons x 2 directions), against which even 0.005 fails a crude Bonferroni
threshold of 0.05/32 = 0.0016.

So the correct characterization is: a MARGINAL one-sided down-jump effect
concentrated at h=10-20, not a strong effect at every horizon. Nothing about
the traded conclusion changes — all 24 specs were already net-negative and
gross-noise — but any future attempt to build on the down-jump result must
start from the clustered standard error, not this module's pre-registered one.

THE OBVIOUS NEXT SPEC — a short-only down-jump book — WAS NOT ADDED, NOT
SCREENED, AND ITS SHARPE IS NOT COMPUTED ANYWHERE. It was nominated by these
results, which is precisely what the pre-registration's stopping rule
forbids; a short-only equity book pays the borrow this project charges at
0.0 for want of data; and the 143 unpriceable point-in-time tickers are the
failed names such a book would most want to have held. The temptation is
recorded here and in the run report rather than acted on.

COSTS DOMINATED THE NET NUMBERS, AND THE COST MODEL IS NOT MERELY SUSPECT — IT
CARRIES NO INFORMATION ABOUT THIS UNIVERSE'S SPREADS. The realized EDGE charge
was 38.8-45.7 bp one-way (mean 41.3), ~8x this project's flat 5bp convention
and worth -0.57 to -1.40 Sharpe per spec. Measured separately over 29
large/mega-caps (87,447 ticker-days, EDGE at the 63-day production window):
median half-spread 23.3bp, with per-ticker medians of 11.9bp for PG and 14.1bp
for JNJ — names whose real quoted half-spread is on the order of 1bp, since a
one-cent tick on a $100-$170 mega-cap IS about 0.6-1.0bp of full spread and the
SEC's 2024 Reg NMS tick amendment exists precisely because these names sit
pinned at that floor. On flagged jump days the median EDGE half-spread is only
1.12x the all-day median, so this is the estimator's LEVEL, not post-jump
selection.

THE VERIFICATION PASS (2026-08-30) DIAGNOSED THE MECHANISM, and it is worse
than the "documented upward bias" this section originally called it:

 * `bidask.edge_rolling` returns sqrt(|s2|) — the ABSOLUTE value of a squared-
   spread estimate that is routinely negative — because its `sign` argument
   defaults to False and spread_estimator.py never passes it. On real PG/JNJ
   OHLC, 35%-47% of the underlying s2 estimates ARE negative. A negative
   squared spread is the estimator saying it cannot distinguish the spread from
   zero; folding it to a positive number of the same magnitude converts "no
   information" into a confident-looking cost. The source paper's own
   prescription (its Eq. 14) is sqrt(max(0, s2)), NOT sqrt(|s2|), and the
   package README warns in as many words that the unsigned default "may create
   a small-sample bias if the estimates are used for averaging".
 * A zero-true-spread PLACEBO settles it. Simulating OHLC with stochastic
   volatility and overnight gaps at each name's own realized volatility and a
   true spread of EXACTLY ZERO, edge_rolling at window=63 returns median
   half-spreads of 18.6bp (PG-like), 27.4bp (MSFT-like), 57.3bp (TSLA-like) and
   80.7bp (ENPH-like) — AT OR ABOVE what the real data returns for those names.
   Injecting a true 2bp spread into the same simulation moves the answer by
   0.04bp. At this window the estimator is not biased; it is blind.
 * Across the 20 mega-caps measured, the EDGE output regresses on realized
   daily volatility through the origin with R^2 = 0.96 and correlation 0.98
   (~13bp of "half-spread" per 1%/day of volatility). It is a volatility proxy
   wearing a spread estimator's name — which is exactly what Jahan-Parvar &
   Zikes (RFS 36(10), 2023) report for daily-data cost measures generally:
   "highly upward biased and imprecise", with "the bias ... a function of
   volatility" and the distortion arising "when the true transaction costs are
   small relative to volatility".
 * The source paper says so itself, which retracts spread_estimator.py's
   parenthetical that this is "not documented in the source paper". Ardia,
   Guidotti & Kroencke's Table 4 reports that in their TIGHTEST spread quintile
   (median true spread 0.09%) EDGE retains 23% correlation with the TAQ
   benchmark and is non-positive 41% of the time; their section 4.1 limits the
   claim to "whenever the transaction costs are not tiny ... small-cap stocks
   and ... all stocks before the year 2000"; and their section 3.5 says outright
   that below a 0.50% spread a researcher should use intraday data instead.
   Their smallest daily-frequency simulation is a 0.50% true spread — 250x
   wider than PG's.

WIDENING THE WINDOW DOES NOT FIX THIS, which matters because
COST_MODEL_WINDOW_DAYS = 63 was chosen on the theory that it would: 21 -> 63
moves the zero-spread floor only from ~13bp to ~10bp of full spread in a plain
Brownian simulation. The floor is set by volatility, not by sample length.

CONSEQUENCE FOR THIS FAMILY: none, and that is why this module still stands.
The verdict rests on the GROSS column, which is computed at zero cost and is
untouched by any of the above.

CONSEQUENCE ELSEWHERE: ALREADY ESCALATED AND ALREADY ACTIONED — main carries
commit df8a933, "Correct severity of the EDGE spread estimator's large-cap
limitation (docs only)", a dedicated investigation triggered by this build's
and eigenportfolio-statarb's cost reports on the same night. It reaches the same
conclusion from independent measurements (PG/JNJ/KO/VZ at 11.8/14.1/13.5/15.8bp
median half-spread; SPY's true ~0.26bp full spread estimated at ~24bp; a 10-40x
overstatement, not 2x) and flags multi_signal_combination.py's two
edge_spread-cited hard exclusions for re-audit. spread_estimator.py is
deliberately NOT touched from this worktree: it is shared, main has moved ahead
of this branch, and editing it here would only create a merge conflict with a
fix that already landed.

THREE THINGS THAT INVESTIGATION LEFT OPEN, recorded here so they are not lost:
 1. spread_estimator.py's HEADER still claims, unchanged, that this estimator
    "recovered 10bps as 4.7bps and 50bps as 48.0bps — close to exact at every
    true-spread level tested (10/50/100/300/500bps)". Re-run with the repo's OWN
    generator (tests/test_edge_cost_model.py::_synthetic_spread_ohlc, 15 seeds x
    400 days), a true 10bp full spread recovers as 33.1bp at w=21 and 26.2bp at
    w=63. The 50/100/300/500bp figures do reproduce (52.1/96.8/293.8/495.2 at
    w=21). Only the 10bp claim is wrong, and it is wrong in the one regime that
    matters here.
 2. The COST_MODEL_WINDOW_DAYS = 63 rationale still says the tight-end bias "is
    short-sample GMM noise, which widening the window directly reduces", which
    df8a933's own new note contradicts ("widening the window here trades away
    liquidity-regime responsiveness without closing this gap"). The file now
    disagrees with itself about why its production constant was chosen. The
    measurement says df8a933 is right: 21 -> 63 moves a true 10bp spread's
    recovery only from 33.1bp to 26.2bp.
 3. tests/test_edge_cost_model.py's recovery test covers only 100bp and 300bp
    true full spreads at +-50% tolerance. Nothing tests the 2-20bp regime this
    project's universe actually occupies, which is why both wrong numbers above
    survived. That gap is the reason to prefer a test over a comment here.

ONE POINT OF DISAGREEMENT WITH df8a933, offered as a nuance rather than a
correction: it calls the sign=False abs()-folding "a secondary, smaller
amplifier". Its own number — JNJ 14.1 -> 5.3bp under the paper's truncate-to-
zero convention — has the folding accounting for roughly 62% of the reported
level, which is closer to primary than secondary. It does not change the
conclusion either way, since 5.3bp is still far above a ~0.4bp truth.

BLAST RADIUS, measured from the persisted rows: cross_sectional_patterns.py
(round_c), intraday_patterns.py (phase_a_intraday_expanded), and
multi_signal_combination.py, which pins the "edge_cost_reaudit_2026-08-28_
edge_spread" run_tag as "the realistic per-ticker cost model" for both of those
families. Switching those families flat -> EDGE cost mean Sharpe -0.18
(round_c: positive specs 14/30 -> 4/30) and -12.76 (phase_a: 8/212 -> 0/212).
Any "uneconomic once you pay realistic costs" conclusion resting on those rows
needs re-reading against the flat_control rows, which already exist in
cross_sectional_trial_results under the parallel run_tag.

THE DETECTOR'S MEASURED SIZE, which the pre-registration required be shown
rather than assumed: at the WINDOW level the test rejects the continuous-path
null on 2.761% of ticker-days at nominal 0.1% (w=21) and 8.630% (w=63) —
27.6x and 86.3x nominal. That is the daily-adaptation size distortion,
and it is much larger than a synthetic stochastic-volatility check suggested
(3.7x at w=21 and 7.1x at w=63; this range was quoted as "5-9x" from an
unpersisted ad-hoc run until the verification pass of 2026-08-30 rebuilt it as
test_size_distortion_under_a_stochastic_volatility_null_is_measured_not_
asserted, so the figure is now reproducible rather than remembered).

WHAT THE VERIFICATION PASS COULD AND COULD NOT SETTLE ABOUT THAT NUMBER, since
it first drafted a stronger claim here and then withdrew it. Two synthetic nulls
bracket the real 27.6x / 86.3x from opposite sides:

 * An unambiguously CONTINUOUS null — Brownian innovations under persistent
   stochastic volatility, no jump component of any kind — over-rejects at only
   3.7x / 7.1x. Continuous-path fat-tail-free volatility clustering therefore
   CANNOT account for what the real data does. Something beyond it is present.
 * A Student-t(4) panel, whose realized per-column excess kurtosis (median 6.5)
   is if anything MILDER than these 625 names' own (median 12.2), over-rejects
   at 47.3x / 169.9x — more than the real data, same w=63 >> w=21 ordering.

The tempting conclusion is "fat tails alone explain it, so the nominal alpha is
simply meaningless". THAT CONCLUSION IS NOT AVAILABLE AND IS NOT DRAWN, because
an i.i.d. Student-t sequence is not the discretization of a continuous
semimartingale either — it is closer to a pure-jump process, and the test is
arguably RIGHT to reject continuity for it. The t(4) experiment shows that a
process matching daily equity KURTOSIS produces this rejection rate whatever
mechanism generated that kurtosis; it does not show the real data is jump-free.

So the report's original framing survives, sharpened: the observed rate needs
more than continuous stochastic volatility, and at daily sampling this test
cannot tell "the Gaussian approximation has failed on fat tails" from "the
fat tails ARE jumps" — those are the same observable. Which is exactly why the
z-thresholds are declared TUNING PARAMETERS and why residual limitation 8
(no comparison against a plain large-|return| filter) is the one that matters.
Both nulls are pinned by tests so the next reader inherits the numbers rather
than the argument. The original wording follows: the number has two readings
this data cannot separate — the nominal alpha is meaningless at daily sampling,
or equity prices genuinely jump often (which is
the sources' own headline finding). What is clear is that the DAY-level flags
are real events — mean |return| on flagged days is 6x to 9x the average
absolute daily move — and equally clear, and stated because it is the
uncomfortable half, that a plain large-|return| filter would select a heavily
overlapping set. No such comparison was pre-registered and none was run, so
this family cannot claim the bipower machinery earned its keep over one.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import partial
from math import gamma, pi

import numpy as np
import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalScreeningResult,
    CrossSectionalSpec,
    screen_cross_sectional_universe,
)
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    get_universe_over,
)
from app.services.research_lab.spread_estimator import build_edge_half_spread_frame

logger = logging.getLogger(__name__)

JUMP_DRIFT_FAMILY = "jump_drift"


# --- [HT05] / [BNS06] constants -------------------------------------------
#
# Every constant below is DERIVED from the moment definition the sources give
# ("mu_a = E(|Z|^a), Z ~ N(0,1), a > 0" — [HT05] p.459) rather than typed in as
# a decimal literal, so there is no transcription to get wrong. The decimals in
# the comments are what the derivation evaluates to, checked against the values
# the papers themselves print.


def _abs_normal_moment(a: float) -> float:
    """mu_a = E(|Z|^a) for Z ~ N(0,1) — [HT05] p.459's own definition.

    E|Z|^a = 2^{a/2} Gamma((a+1)/2) / Gamma(1/2). Checks out against both
    sources' printed values: mu_1 = sqrt(2/pi) = 0.79788 ([BNS06] Eq. 5 states
    mu_1 = sqrt(2)/sqrt(pi)), and mu_2 = 1, mu_4 = 3 ([HT05] p.460 lists
    mu_2 = 1 and mu_4 = 3)."""
    return 2.0 ** (a / 2.0) * gamma((a + 1.0) / 2.0) / gamma(0.5)


# mu_1^{-2} = pi/2 = 1.5707963268 — the bipower scaling constant of [HT05]
# p.459's BV_t, which that page writes out both ways ("mu_1^{-2} ... = pi/2").
MU1_INV_SQ = _abs_normal_moment(1.0) ** -2

# mu_{4/3}^{-3} = 1.7434720745 — the tri-power quarticity constant of [HT05]
# p.461 Eq. (3).
MU43_INV_CUBE = _abs_normal_moment(4.0 / 3.0) ** -3

# nu_bb - nu_qq = (pi/2)^2 + pi - 5 = 0.6089937539. [HT05] p.460 gives
# nu_qq = 2 and nu_bb = (pi/2)^2 + pi - 3; [BNS06] Eq. (6) gives the same
# difference directly as theta ~= 0.6090. Two independent sources, one number.
NU_BB_MINUS_NU_QQ = (pi / 2.0) ** 2 + pi - 5.0


# --- the pre-declared grid ------------------------------------------------

# Nominal one-sided Gaussian critical values, keyed by the nominal alpha they
# would correspond to IF the N(0,1) limit held exactly at daily sampling. It
# does not (see the module docstring's daily-adaptation section (b)), so these
# are DECLARED TUNING PARAMETERS carrying a nominal label, never calibrated
# p-values. compute_jump_diagnostics measures the realized firing rate against
# the nominal alpha so the size distortion is visible rather than assumed away.
JUMP_Z_CRITICAL: dict[str, float] = {
    "001": 3.0902323062,  # scipy.stats.norm.ppf(0.999)
    "010": 2.3263478740,  # scipy.stats.norm.ppf(0.990)
}

# The BNS/HT "period", in trading days. 21 ~ one month, 63 ~ one quarter. Both
# sit inside the M = 13..390 range [HT05]'s own Monte Carlo covers (a 390-minute
# day sampled at 1/3/5/30 minutes; the "12..288" this comment used to name is
# [BNS06]'s grid, not [HT05]'s — corrected by the verification pass 2026-08-30,
# see the module docstring's section (a)), which is the
# reason to expect the N(0,1) approximation to be usable at all at this
# sampling interval — see the docstring, which also states why that is an
# argument about sample SIZE and not about the asymptotic regime.
JUMP_WINDOWS_DAYS: tuple[int, ...] = (21, 63)

# [SAV12]'s own post-event horizons are 5, 10, 20 and 40 trading days; the
# first three are screened here (40 is dropped because at ~11.6 years of
# formations it would leave ~70 non-overlapping holds, too few to read).
JUMP_HOLDING_HORIZONS_DAYS: tuple[int, ...] = (5, 10, 20)

# +1 = H_CONT (long recent up-jumpers, short recent down-jumpers).
# -1 = H_REV  (the opposite book). Both pre-declared; neither favoured.
JUMP_DIRECTIONS: dict[str, int] = {"cont": 1, "rev": -1}

# Top 40% / bottom 40% of the FLAGGED-ONLY cross-section by signed jump
# return, dropping the middle 20% as directionally ambiguous. Not searched.
# 0.40 rather than 0.50 on purpose: at 0.50 the harness's disjointness gate
# (2 * n_leg > n_ranked) sits exactly on the boundary for an even
# cross-section, and a family should not depend on which side of an equality
# a floor division lands.
JUMP_RANK_FRACTION = 0.40

# Two disjoint legs of >= min_names_per_leg (harness default 5) at
# rank_fraction 0.40 needs >= 13 flagged names in the cross-section.
JUMP_MIN_FLAGGED_FOR_TWO_LEGS = 13

JUMP_SPEC_CEILING = 24

# Longest history any spec's signal needs is window + holding_days (see
# _signal_rows_needed), and the longest of those is 63 + 20 = 83 trading days.
# The padding is in CALENDAR days and is deliberately generous so the FIRST
# formation has a full window rather than a truncated one.
JUMP_PRICE_PADDING_CALENDAR_DAYS = 400

# Rows of slack added on top of window + holding_days when declaring
# lookback_days. The rolling statistics need `window` RETURNS, which needs
# window + 1 closes; the extra rows here also absorb a missing print or two
# inside the window without silently shortening it.
JUMP_LOOKBACK_SLACK_ROWS = 10

JUMP_DRIFT_CITATION = (
    "Barndorff-Nielsen & Shephard, 'Econometrics of Testing for Jumps in Financial Economics "
    "Using Bipower Variation', Journal of Financial Econometrics 4(1), 2006, pp. 1-30, and "
    "Huang & Tauchen, 'The Relative Contribution of Jumps to Total Price Variance', Journal of "
    "Financial Econometrics 3(4), 2005, pp. 456-499 — both read in full 2026-08-30; the "
    "detector is Huang & Tauchen's ratio-plus-max-adjusted z_TP,rm (their Eq. 9), chosen "
    "because it is the one variant their Monte Carlo finds size-robust as the sampling "
    "interval lengthens, applied to a rolling window of DAILY returns rather than intraday "
    "ones (an adaptation whose statistical cost is stated in the module docstring, NOT a "
    "result the sources validated). Post-jump direction: Savor, 'Stock Returns after Major "
    "Price Shocks: The Impact of Information', Journal of Financial Economics 106(3), 2012, "
    "pp. 635-659, whose full-sample Table 4 coefficients on the event-day return are "
    "-0.062/-0.065/-0.081 at 5/10/20 days (t = -13.2/-6.0/-7.1), i.e. REVERSAL at these "
    "horizons; against Jiang & Zhu, Journal of Financial Economics 124(1), 2017, pp. 43-64, "
    "which reports CONTINUATION but at one- to three-MONTH horizons. Both directions are "
    "pre-declared and screened."
)


# --- the jump statistic ---------------------------------------------------


def log_returns(close: pd.DataFrame) -> pd.DataFrame:
    """ln(C_t / C_{t-1}). LOG returns, not simple ones — RV/BV/TP discretize the
    quadratic variation of the LOG-price semimartingale in both sources
    ([HT05] p.459 defines its r_{t,j} as a difference of the log price p).

    Non-positive prices become NaN before the log rather than -inf: yfinance
    occasionally ships a zero close for a halted or badly-adjusted name, and an
    infinity there would poison every rolling window that touched it."""
    positive = close.where(close > 0.0)
    return np.log(positive).diff()


def jump_z_statistic(returns: pd.DataFrame, window: int) -> pd.DataFrame:
    """[HT05] Eq. (9)'s z_TP,rm, computed on a ROLLING window of `window` DAILY
    log returns ENDING AT AND INCLUDING each row.

    Returns a frame aligned to `returns`, NaN wherever the window is not fully
    populated. POSITIVE under jumps ([HT05]'s orientation); reject the
    continuous-path null in the UPPER tail.

    Every sum below is taken over exactly the window's own returns, which is
    what makes the row-i value a function of rows <= i alone:
      * RV sums `window` squared returns              -> rolling(window)
      * BV sums `window - 1` adjacent-|r| products,
        each indexed by its SECOND element            -> rolling(window - 1)
      * TP sums `window - 2` triple products,
        each indexed by its LAST element              -> rolling(window - 2)

    M in the source formulas is `window` here. The finite-sample corrections
    (M/(M-1)) on BV and (M/(M-2)) on TP are [HT05]'s own and are applied
    exactly as written — they are not negligible at M = 21."""
    if window < 4:
        raise ValueError(
            f"jump_z_statistic needs window >= 4 (tri-power quarticity sums triples, so a window "
            f"of {window} would leave fewer than 2 terms and no usable quarticity), got {window}."
        )
    absolute = returns.abs()
    m = float(window)

    realized_variance = returns.pow(2.0).rolling(window).sum()

    bipower_terms = absolute * absolute.shift(1)
    bipower_variation = MU1_INV_SQ * (m / (m - 1.0)) * bipower_terms.rolling(window - 1).sum()

    tripower_terms = (
        absolute.pow(4.0 / 3.0)
        * absolute.shift(1).pow(4.0 / 3.0)
        * absolute.shift(2).pow(4.0 / 3.0)
    )
    tripower_quarticity = (
        m * MU43_INV_CUBE * (m / (m - 2.0)) * tripower_terms.rolling(window - 2).sum()
    )

    # A window whose RV or BV is zero is a window in which the price never
    # moved. RJ is 0/0 there and the scaling divides by BV^2; both are NaN
    # rather than an infinity or a spurious 0, because "this ticker did not
    # trade" is not evidence for or against a jump.
    usable = (realized_variance > 0.0) & (bipower_variation > 0.0)
    relative_jump = ((realized_variance - bipower_variation) / realized_variance).where(usable)
    quarticity_ratio = (tripower_quarticity / bipower_variation.pow(2.0)).where(usable)

    scale = np.sqrt(NU_BB_MINUS_NU_QQ * (1.0 / m) * quarticity_ratio.clip(lower=1.0))
    return relative_jump / scale


def detect_jump_days(close: pd.DataFrame, window: int, z_crit: float) -> pd.DataFrame:
    """The SIGNED SIZE of each detected jump — r_d on flagged days, NaN
    everywhere else — for the day-level attribution rule stated in the module
    docstring (which is this module's own, not a published one):

        day d is a jump day iff  z_TP,rm(window ending at d) > z_crit
                            and  |r_d| == max |r_j| over that same window.

    Both conditions read only rows <= d, so a flag is strictly backward-looking
    and cannot be revised by later data — which is what makes computing this
    over a whole panel at once point-in-time correct rather than merely
    convenient. Unit-tested by poisoning future rows and asserting bit-identity.

    Condition (ii) uses exact float equality against the rolling max
    DELIBERATELY: rolling().max() returns one of the window's actual values, so
    the comparison is exact by construction and needs no tolerance. A genuine
    tie (two days with bit-identical |r| in one window) flags both, which is the
    honest reading of an ambiguous window and is vanishingly rare in real
    price data."""
    returns = log_returns(close)
    z = jump_z_statistic(returns, window)
    absolute = returns.abs()
    is_window_max = absolute.eq(absolute.rolling(window).max())
    flagged = (z > z_crit) & is_window_max
    return returns.where(flagged)


def _signal_rows_needed(window: int, event_window_days: int) -> int:
    """Closes required for `event_window_days` consecutive usable jump flags.

    A flag at row i needs `window` returns ending at i, so it needs window + 1
    closes. Flags on the last `event_window_days` rows therefore need
    window + event_window_days closes, and JUMP_LOOKBACK_SLACK_ROWS on top
    absorbs a missing print or two inside the window."""
    return window + event_window_days + JUMP_LOOKBACK_SLACK_ROWS


def signal_post_jump(
    data: CrossSectionalData,
    *,
    window: int,
    z_crit: float,
    event_window_days: int,
    direction: int,
) -> pd.Series:
    """The cross-sectional signal at one formation date: `direction` times the
    signed size of the ticker's MOST RECENT detected jump within the trailing
    `event_window_days` trading days (the formation date included), NaN for any
    ticker with no jump in that window.

    NaN is the SignalFn contract's "no valid signal today", so non-jumpers are
    dropped from the ranking entirely rather than crowding into the middle of
    it. That is the whole design: select_leg_tickers then ranks the FLAGGED
    cross-section only, and rank_fraction 0.40 takes the strongest 40% of it on
    each side. A spec's legs are therefore built from jump events, never from
    the 400-odd stocks that did nothing that week.

    direction is +1 for H_CONT — the long leg is the largest UP-jumps, the short
    leg the largest DOWN-jumps — and -1 for H_REV, which swaps them. Both are
    pre-declared specs; neither is a post-hoc flip.

    Only the last _signal_rows_needed rows are used, and the rolling statistics
    are computed on that slice alone. This is not merely an optimization: it
    makes the signal a function of a FIXED window of history regardless of how
    much the harness happened to hand over, so the same formation produces the
    same number in a full replay and in a single live forward tick."""
    close = data.close
    empty = pd.Series(np.nan, index=close.columns, dtype=float)
    needed = _signal_rows_needed(window, event_window_days)
    if len(close) < needed:
        return empty

    recent_close = close.iloc[-needed:]
    jumps = detect_jump_days(recent_close, window, z_crit)

    # ffill INSIDE the trailing event window only — the slice starts fresh, so
    # nothing older than event_window_days can be carried forward. The result
    # is each column's most recent flagged jump in that window, or NaN.
    event_window = jumps.iloc[-event_window_days:]
    most_recent = event_window.ffill().iloc[-1]
    return (float(direction) * most_recent).reindex(close.columns)


# --- the family -----------------------------------------------------------


def _spec(
    *,
    direction_tag: str,
    window: int,
    alpha_tag: str,
    holding_days: int,
) -> CrossSectionalSpec:
    return CrossSectionalSpec(
        pattern_id=f"jump_{direction_tag}_w{window}_a{alpha_tag}_h{holding_days}",
        family=JUMP_DRIFT_FAMILY,
        citation=JUMP_DRIFT_CITATION,
        signal_fn=partial(
            signal_post_jump,
            window=window,
            z_crit=JUMP_Z_CRITICAL[alpha_tag],
            # The event lookback EQUALS the holding horizon, so every detected
            # jump is traded exactly once at the first formation on or after
            # it. See the module docstring: this deliberately confounds horizon
            # with signal staleness, and the alternative discards most events
            # at the long horizons.
            event_window_days=holding_days,
            direction=JUMP_DIRECTIONS[direction_tag],
        ),
        lookback_days=_signal_rows_needed(window, holding_days),
        holding_days=holding_days,
        portfolio="long_short",
        rank_fraction=JUMP_RANK_FRACTION,
    )


def _build_jump_drift_family() -> list[CrossSectionalSpec]:
    """The pre-declared family, built once at import so its length is fixed
    before any data is touched — the literal here IS the n_trials denominator
    screen_cross_sectional_universe deflates against."""
    specs = [
        _spec(
            direction_tag=direction_tag,
            window=window,
            alpha_tag=alpha_tag,
            holding_days=holding_days,
        )
        for direction_tag in JUMP_DIRECTIONS
        for window in JUMP_WINDOWS_DAYS
        for alpha_tag in JUMP_Z_CRITICAL
        for holding_days in JUMP_HOLDING_HORIZONS_DAYS
    ]
    assert len(specs) == JUMP_SPEC_CEILING, (
        f"jump-drift family is {len(specs)} specs, not the pre-declared {JUMP_SPEC_CEILING} — "
        "the ceiling is the honest n_trials denominator and must be updated deliberately, never "
        "drifted past."
    )
    return specs


JUMP_DRIFT_SPECS: list[CrossSectionalSpec] = _build_jump_drift_family()


# --- detector diagnostics -------------------------------------------------


@dataclass
class JumpDiagnostics:
    """How often the detector actually fired, and on what.

    This exists because of the module docstring's "what would make a positive
    result fake" items 1 and 2: at daily sampling the nominal alpha is not a
    calibrated false-positive rate, so the REALIZED firing rate has to be
    measured and shown rather than assumed to equal it. A rate far above
    nominal_alpha means the test is largely firing on fat tails, and the family
    is a return-magnitude sort wearing a jump test's name."""

    window: int
    z_crit: float
    nominal_alpha: float
    n_ticker_days: int  # rows where the statistic was computable at all
    # THE WINDOW-LEVEL TEST — z > z_crit alone, with no day-level attribution.
    # This, and only this, is the quantity nominal_alpha actually labels: the
    # BNS/HT statistic tests a window, and its critical value is a statement
    # about how often that window test rejects a continuous path. Comparing
    # the day-level flag rate below against nominal_alpha instead would
    # flatter the test badly, because attribution condition (ii) throws away
    # most rejections (only ~1 row in `window` can be its own window's max),
    # so a day-level rate can sit BELOW nominal while the window test is
    # over-rejecting several-fold. Both are reported for exactly that reason.
    n_window_rejections: int
    window_rejection_rate: float
    window_rate_vs_nominal: float
    # THE DAY-LEVEL FLAGS — z > z_crit AND |r_d| is the window max. This is
    # what the family actually trades.
    n_jump_days: int
    n_up_jumps: int
    n_down_jumps: int
    realized_rate: float  # n_jump_days / n_ticker_days
    rate_vs_nominal: float  # realized_rate / nominal_alpha
    mean_abs_jump_return: float
    mean_abs_return_all_days: float
    n_tickers_with_any_jump: int
    n_tickers: int


def compute_jump_diagnostics(
    close: pd.DataFrame, window: int, z_crit: float, nominal_alpha: float
) -> JumpDiagnostics:
    """Measure the detector on real data instead of trusting its nominal label."""
    returns = log_returns(close)
    z = jump_z_statistic(returns, window)
    jumps = detect_jump_days(close, window, z_crit)

    computable = int(z.notna().to_numpy().sum())
    n_window_rejections = int((z > z_crit).to_numpy().sum())
    jump_values = jumps.to_numpy()
    finite = jump_values[np.isfinite(jump_values)]
    n_jumps = int(finite.size)
    all_abs = returns.abs().to_numpy()
    all_abs = all_abs[np.isfinite(all_abs)]

    return JumpDiagnostics(
        window=window,
        z_crit=z_crit,
        nominal_alpha=nominal_alpha,
        n_ticker_days=computable,
        n_window_rejections=n_window_rejections,
        window_rejection_rate=(n_window_rejections / computable) if computable else float("nan"),
        window_rate_vs_nominal=(
            (n_window_rejections / computable) / nominal_alpha
            if computable and nominal_alpha
            else float("nan")
        ),
        n_jump_days=n_jumps,
        n_up_jumps=int((finite > 0).sum()),
        n_down_jumps=int((finite < 0).sum()),
        realized_rate=(n_jumps / computable) if computable else float("nan"),
        rate_vs_nominal=(
            (n_jumps / computable) / nominal_alpha if computable and nominal_alpha else float("nan")
        ),
        mean_abs_jump_return=float(np.abs(finite).mean()) if n_jumps else float("nan"),
        mean_abs_return_all_days=float(all_abs.mean()) if all_abs.size else float("nan"),
        n_tickers_with_any_jump=int(jumps.notna().any().sum()),
        n_tickers=int(close.shape[1]),
    )


# --- the post-jump event study -------------------------------------------

# Horizons for the event study, in trading days after the jump. 1 is included
# here although no traded spec holds for one day: the event study is cost-free
# description, and the 1-day point is where a microstructure bounce would show
# up most clearly if one were driving the result.
EVENT_STUDY_HORIZONS_DAYS: tuple[int, ...] = (1, 5, 10, 20)

# Bootstrap replicates and the seed, both fixed here rather than passed by a
# caller, so the reported p-values are reproducible from the module alone.
EVENT_STUDY_BOOTSTRAP_DRAWS = 2000
EVENT_STUDY_SEED = 20260830

# A ticker needs at least this many usable non-jump forward observations to
# supply a baseline. Below it the ticker's own unconditional mean is itself
# noise, and subtracting a noisy baseline manufactures a spurious abnormal
# return rather than removing a real drift.
EVENT_STUDY_MIN_BASELINE_DAYS = 60

# The bootstrap p-value a cell must clear before its SIGN is allowed to vote in
# PostJumpEventStudy.verdict. Named rather than inlined because it is read in
# two places there and is the whole content of "significant" in the
# pre-registered reading rule.
EVENT_STUDY_VERDICT_ALPHA = 0.05


@dataclass
class EventStudyCell:
    """One (horizon, jump direction) cell of the post-jump event study.

    `mean_abnormal` is the pooled mean, over every event of this direction, of
    (that event's forward cumulative log return) minus (the SAME TICKER's mean
    forward cumulative log return over its own non-jump days). Ticker-demeaning
    is what isolates a jump-conditional effect from ordinary drift: a stock
    that drifted up across the sample contributes that drift to its jump days
    and to its baseline days alike, and the subtraction nets it out."""

    horizon_days: int
    direction: str  # "up" | "down"
    n_events: int
    mean_raw: float  # mean forward cumulative log return after the jump
    mean_baseline: float  # event-weighted mean of the per-ticker baselines
    mean_abnormal: float  # mean_raw - mean_baseline, the headline number
    bootstrap_p_value: float
    bootstrap_null_mean: float
    bootstrap_null_std: float


@dataclass
class PostJumpEventStudy:
    window: int
    z_crit: float
    n_tickers_used: int
    n_bootstrap_draws: int
    seed: int
    cells: list[EventStudyCell] = field(default_factory=list)

    def verdict(self) -> str:
        """The pre-registered reading rule, applied mechanically.

        From the pre-registration, section 9, quoted: up-jumps > 0 and
        down-jumps < 0 => CONTINUATION; up-jumps < 0 and down-jumps > 0 =>
        REVERSAL; anything else => NULL. Only cells whose bootstrap p-value
        clears 0.05 are allowed to vote, and a horizon on which EITHER side is
        insignificant abstains rather than being read off its point estimate. No
        fourth reading is invented here.

        SIGNIFICANCE GATES BOTH SIDES, and that is a correctness fix (verification
        pass, 2026-08-30) rather than a re-reading of the rule. The first version
        of this method checked significance only to catch the case where NEITHER
        side cleared 0.05, and then formed CONTINUATION/REVERSAL off the raw point
        estimates — so a single significant side plus an insignificant one whose
        point estimate happened to carry the complementary sign declared a
        pattern. On the production run that fired once, at w=21 / alpha=0.001 /
        h=1, which was reported as CONTINUATION on the strength of an up-jump
        abnormal return of +0.0001% with p=0.998: a coin-flip point estimate
        casting the deciding vote. A sign that is not distinguishable from zero is
        not a sign, and the docstring above always said so; the code now matches
        it. The fix can only ever turn a directional verdict into NULL, never the
        reverse, so it cannot manufacture support for either hypothesis."""
        votes: list[str] = []
        by_horizon: dict[int, dict[str, EventStudyCell]] = {}
        for cell in self.cells:
            by_horizon.setdefault(cell.horizon_days, {})[cell.direction] = cell
        for horizon in sorted(by_horizon):
            up = by_horizon[horizon].get("up")
            down = by_horizon[horizon].get("down")
            if up is None or down is None:
                continue
            up_sig = up.bootstrap_p_value < EVENT_STUDY_VERDICT_ALPHA
            down_sig = down.bootstrap_p_value < EVENT_STUDY_VERDICT_ALPHA
            if not up_sig and not down_sig:
                votes.append(f"h={horizon}: NULL (neither side significant)")
            elif not up_sig or not down_sig:
                side = "up" if not up_sig else "down"
                votes.append(f"h={horizon}: NULL (the {side} side is not significant)")
            elif up.mean_abnormal > 0 and down.mean_abnormal < 0:
                votes.append(f"h={horizon}: CONTINUATION")
            elif up.mean_abnormal < 0 and down.mean_abnormal > 0:
                votes.append(f"h={horizon}: REVERSAL")
            else:
                votes.append(f"h={horizon}: NULL (signs do not form either pattern)")
        return "; ".join(votes) if votes else "no horizon produced a usable cell"


def forward_cumulative_log_return(returns: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """At row d, the cumulative log return over d+1 .. d+horizon — i.e. STARTING
    THE DAY AFTER d, which is what an event study of a day-d event must measure
    (the event day's own return is the event, not the response).

    rolling(horizon).sum() at row i is the sum over i-horizon+1..i; shifting it
    back by `horizon` rows puts that sum at row i-horizon, whose forward window
    it is. The last `horizon` rows become NaN, correctly: their forward window
    runs past the end of the data."""
    return returns.rolling(horizon).sum().shift(-horizon)


def run_post_jump_event_study(
    close: pd.DataFrame,
    *,
    window: int,
    z_crit: float,
    horizons: Sequence[int] = EVENT_STUDY_HORIZONS_DAYS,
    n_bootstrap: int = EVENT_STUDY_BOOTSTRAP_DRAWS,
    seed: int = EVENT_STUDY_SEED,
) -> PostJumpEventStudy:
    """Forward cumulative returns after detected jumps, against each ticker's
    OWN non-jump baseline, with a seeded bootstrap p-value.

    THE BASELINE, and why it is per-ticker rather than pooled. The brief asks
    for a matched non-jump comparison that isolates a jump-conditional effect
    from ordinary drift. Every event's forward return has that ticker's own
    unconditional forward mean subtracted before pooling, so a stock that rose
    steadily across the sample contributes its drift to both sides of the
    subtraction and none of it to the answer.

    THE BOOTSTRAP NULL is built to mirror exactly that statistic: for each
    event, draw a random NON-JUMP day FROM THE SAME TICKER, take the same
    demeaned forward return, pool, average. Repeating that n_bootstrap times
    gives the distribution of the pooled statistic under "these events were
    ordinary days for these same stocks", which is the null the claim needs.
    The p-value is two-sided and uses the (1 + count) / (1 + draws) form, so it
    is never exactly zero — an empirical p-value cannot resolve past 1/draws
    and reporting 0.0 would overstate what the resampling can show.

    A ticker with fewer than EVENT_STUDY_MIN_BASELINE_DAYS usable non-jump
    forward observations is dropped entirely (its events included), because a
    baseline estimated off a handful of days is noise, and subtracting noise
    manufactures abnormal returns rather than removing drift."""
    returns = log_returns(close)
    jumps = detect_jump_days(close, window, z_crit)
    rng = np.random.default_rng(seed)

    study = PostJumpEventStudy(
        window=window,
        z_crit=z_crit,
        n_tickers_used=0,
        n_bootstrap_draws=n_bootstrap,
        seed=seed,
    )

    tickers_used: set[str] = set()
    for horizon in horizons:
        forward = forward_cumulative_log_return(returns, horizon)
        for direction, sign in (("up", 1.0), ("down", -1.0)):
            event_values: list[np.ndarray] = []
            baseline_means: list[np.ndarray] = []
            baseline_pools: list[np.ndarray] = []

            for ticker in close.columns:
                fwd = forward[ticker]
                jump = jumps[ticker]
                is_jump = jump.notna()
                is_event = is_jump & (np.sign(jump.fillna(0.0)) == sign) & fwd.notna()
                # "Non-jump" excludes EVERY flagged day, not just the ones of
                # this direction: an opposite-signed jump is still not an
                # ordinary day and must not sit in the baseline.
                #
                # It does NOT exclude a day whose FORWARD WINDOW happens to
                # contain a later jump, and that is deliberate. The question
                # being asked is "conditional on a jump TODAY, what follows,
                # versus what follows on an ordinary day" — and an ordinary
                # day's forward window containing a future jump is part of the
                # ordinary experience being compared against. Filtering those
                # out would build an artificially quiet baseline and would
                # therefore make any post-jump effect look larger than it is;
                # keeping them is the conservative direction.
                is_baseline = (~is_jump) & fwd.notna()

                pool = fwd[is_baseline].to_numpy(dtype=float)
                if pool.size < EVENT_STUDY_MIN_BASELINE_DAYS:
                    continue
                events = fwd[is_event].to_numpy(dtype=float)
                if events.size == 0:
                    continue

                mean_baseline = float(pool.mean())
                event_values.append(events - mean_baseline)
                baseline_means.append(np.full(events.size, mean_baseline))
                baseline_pools.append(pool - mean_baseline)
                tickers_used.add(ticker)

            if not event_values:
                continue

            demeaned = np.concatenate(event_values)
            n_events = int(demeaned.size)
            observed = float(demeaned.mean())
            mean_baseline_pooled = float(np.concatenate(baseline_means).mean())

            # Per-ticker resampling, accumulated as SUMS so the pooled mean is
            # exactly the observed statistic's own construction.
            null_sums = np.zeros(n_bootstrap, dtype=float)
            for events_arr, pool_arr in zip(event_values, baseline_pools, strict=True):
                draws = rng.integers(0, pool_arr.size, size=(n_bootstrap, events_arr.size))
                null_sums += pool_arr[draws].sum(axis=1)
            null = null_sums / n_events

            exceed = int(np.sum(np.abs(null) >= abs(observed)))
            study.cells.append(
                EventStudyCell(
                    horizon_days=horizon,
                    direction=direction,
                    n_events=n_events,
                    mean_raw=observed + mean_baseline_pooled,
                    mean_baseline=mean_baseline_pooled,
                    mean_abnormal=observed,
                    bootstrap_p_value=(1.0 + exceed) / (1.0 + n_bootstrap),
                    bootstrap_null_mean=float(null.mean()),
                    bootstrap_null_std=float(null.std(ddof=1)),
                )
            )

    study.n_tickers_used = len(tickers_used)
    return study


# --- production entry point ----------------------------------------------


@dataclass
class JumpDriftScreeningSummary:
    """Everything one production run produced.

    `results` is what persist_cross_sectional_trial_results consumes — the
    harness's own CrossSectionalScreeningResult already carries .pattern_id,
    .sharpe_annualized, .n_trading_days and .deflated_sharpe, so the persistence
    contract comes for free and no adapter dataclass is needed.

    `missing_price_tickers` is a first-class field, not a log line: it IS this
    project's known delisted-securities gap made visible, and for this family in
    particular the missing names are disproportionately the down-jump events
    (see the module docstring's survivorship section)."""

    results: list[CrossSectionalScreeningResult]
    missing_price_tickers: list[str]
    diagnostics: list[JumpDiagnostics]
    event_studies: list[PostJumpEventStudy]
    universe_size: int
    n_priced_tickers: int
    first_date: date | None
    last_date: date | None


def run_jump_drift_screening(
    start: date,
    end: date,
    provider: YFinanceProvider | None = None,
    config: CrossSectionalConfig | None = None,
    *,
    run_event_study: bool = True,
) -> JumpDriftScreeningSummary:
    """THE production entry point.

    Universe: get_universe_over(start, end), the point-in-time S&P 500
    candidate pool, gated per formation by the harness's default was_member.
    `start` must be >= MEMBERSHIP_DATA_START.

    Fetches via get_daily_ohlcv rather than get_price_history because the
    default cost model here is "edge_spread", and build_edge_half_spread_frame
    needs full OHLC on exactly the alignment get_daily_ohlcv guarantees. Only
    close and half_spread are passed on to CrossSectionalData; the signal
    itself reads closes alone.

    Persistence stays a separate explicit call
    (persist_cross_sectional_trial_results), per that module's contract — this
    function takes no Session and writes no rows."""
    if start < MEMBERSHIP_DATA_START:
        raise ValueError(
            f"Jump-drift screening start {start.isoformat()} predates point-in-time membership "
            f"coverage ({MEMBERSHIP_DATA_START.isoformat()}) — a formation before that date would "
            "silently see an empty universe."
        )
    provider = provider if provider is not None else YFinanceProvider()
    if config is None:
        config = CrossSectionalConfig(cost_model="edge_spread")
    config.formation_start = start

    universe = get_universe_over(start, end)
    padded_start = start - timedelta(days=JUMP_PRICE_PADDING_CALENDAR_DAYS)
    frames, missing_price = provider.get_daily_ohlcv(universe, padded_start, end)
    if not frames or frames["close"].empty:
        return JumpDriftScreeningSummary(
            results=[],
            missing_price_tickers=missing_price,
            diagnostics=[],
            event_studies=[],
            universe_size=len(universe),
            n_priced_tickers=0,
            first_date=None,
            last_date=None,
        )

    close = frames["close"]
    half_spread = (
        build_edge_half_spread_frame(frames["open"], frames["high"], frames["low"], close)
        if config.cost_model == "edge_spread"
        else None
    )
    data = CrossSectionalData(close=close, half_spread=half_spread)
    results = screen_cross_sectional_universe(data, JUMP_DRIFT_SPECS, config)

    # The detector's own behavior, measured once per (window, threshold) pair
    # actually screened — four pairs, not twenty-four, because direction and
    # holding horizon do not touch detection.
    diagnostics = [
        compute_jump_diagnostics(close, window, JUMP_Z_CRITICAL[tag], nominal_alpha)
        for window in JUMP_WINDOWS_DAYS
        for tag, nominal_alpha in (("001", 0.001), ("010", 0.010))
    ]
    event_studies = (
        [
            run_post_jump_event_study(close, window=window, z_crit=JUMP_Z_CRITICAL[tag])
            for window in JUMP_WINDOWS_DAYS
            for tag in JUMP_Z_CRITICAL
        ]
        if run_event_study
        else []
    )

    return JumpDriftScreeningSummary(
        results=results,
        missing_price_tickers=missing_price,
        diagnostics=diagnostics,
        event_studies=event_studies,
        universe_size=len(universe),
        n_priced_tickers=int(close.shape[1]),
        first_date=close.index[0].date(),
        last_date=close.index[-1].date(),
    )
