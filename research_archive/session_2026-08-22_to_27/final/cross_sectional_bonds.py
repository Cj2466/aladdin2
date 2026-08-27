"""The Bonds family: a fixed 8-ETF fixed-income cross-section screened for
three PRE-DECLARED, individually-cited term-structure and credit mechanisms,
expressed against cross_sectional.py's harness.

This module is Round C's and Build D2's sibling, not a subset of either: it
shares the harness (and two options that landed on it this session -- see
FIXED UNIVERSE and COSTS below) but its family object, its n_trials
denominator, and its DSR correction are entirely its own, never pooled with
ROUND_C_FAMILY, D2_FAMILY, or any other family. screen_cross_sectional_
universe fixes n_trials at len(specs) for whatever family object is actually
passed to it, so calling it here with THIS 18-spec family, in its own call,
is what makes n_trials=18 real rather than merely asserted.

WHY FIXED INCOME AT ALL, after four cleanly negative equity rounds. Every
prior round in this project (270 single-ticker intraday definitions, then
Round C/D/D1/D2 cross-sectional equity) searched for a BEHAVIORAL
mispricing -- an anomaly that exists because somebody is making a mistake,
and that therefore has no reason to survive being found. The three
mechanisms below are structurally different: they are compensations for
bearing a defined risk (term premium, curve-shape risk, default risk) that
the fixed-income literature has documented for thirty-plus years and that
does not disappear when it is published, because it was never an error.
That does not make them free money -- it makes them a genuinely different
hypothesis class from everything screened here so far, which is the entire
reason for spending an 18-trial budget on it. Whether any of them survives
this project's own costs, financing, and DSR correction is exactly what the
production run answers, and a negative answer here is as reportable as the
four before it.

============================================================================
THE UNIVERSE, AND WHY "SURVIVORSHIP" MEANS SOMETHING DIFFERENT HERE
============================================================================
Eight liquid US bond ETFs, every one continuously tradeable across the whole
backtest window:

  Treasury maturity ladder   SHY (1-3y), IEI (3-7y), IEF (7-10y),
                             TLH (10-20y), TLT (20y+)
  Inflation-linked           TIP
  Credit                     LQD (investment grade), HYG (high yield)

VERIFIED LIVE (2026-08-26 and re-verified 2026-08-27, not taken on trust
from the feasibility scout): all eight resolve on yfinance, and their COMMON
clean history -- every one of the eight priced on the same day -- runs
2007-04-11 to 2026-08-26, exactly 4,876 rows. The binding constraint is
HYG's own 2007-04-11 inception; SHY/IEF/LQD/TLT go back to 2002-07-30,
TIP to 2003-12-05, IEI/TLH to 2007-01-11.

This basket uses cross_sectional.fixed_universe_membership, NOT the S&P 500
point-in-time gate was_member that every equity family here uses. That is
not a shortcut around survivorship bias, it is the absence of the thing that
bias is about: AGG was never "added to an index of bond ETFs", there is no
membership event whose date could be gotten wrong, and there is no
failure-clustered deletion process silently removing the names a short leg
would have wanted. See fixed_universe_membership's own docstring for the
full argument, INCLUDING the residual bias it explicitly does not remove and
this family therefore still carries: choosing today's liquid ETFs is a
choice made with hindsight, and an ETF that had closed before today would
never have made this hand-written list. That channel is small here (these
eight are among the largest and oldest fixed-income ETFs in existence, and
ETF closures are announced and orderly rather than failure-clustered) but it
is not zero, and it is disclosed rather than claimed away.

Passing membership_fn=None here instead would make ALL eight tickers
ineligible on every formation date, since was_member answers False for every
non-S&P-500 name. That used to fail silently as a long series of exact 0.0
returns; it now raises EmptyEligibleUniverseError. This module's tests
deliberately exercise that trap to prove the right gate is wired in.

============================================================================
auto_adjust=True IS MANDATORY, AND THE INCOME WEDGE IS THE WHOLE SIGNAL
============================================================================
For these instruments the distributions ARE the return. Measured live over
the common window 2007-04-11..2026-08-26:

  ETF   raw-price CAGR    total-return CAGR
  SHY        +0.12%              +1.86%
  IEI        +0.78%              +2.80%
  IEF        +0.64%              +3.21%
  TLH        -0.11%              +2.83%
  TLT        -0.26%              +2.89%
  TIP        +0.36%              +3.42%
  LQD        +0.02%              +4.02%
  HYG        -1.37%              +4.93%

Three of the eight LOSE money on price alone while all eight make money on
total return. A backtest of this family on unadjusted prices would not be
slightly off, it would have the sign wrong on most of the basket.
CrossSectionalData.close is therefore always the dividend-adjusted
total-return basis, exactly as get_daily_ohlcv already guarantees.

But the carry mechanism below needs to see income SEPARATELY from price
change, and neither basis alone can show that. So this family is the first
consumer of CrossSectionalData.price_only_close (the split-adjusted,
dividend-UNADJUSTED basis, added to the harness for it) and of
YFinanceProvider.get_total_and_price_return_closes, which returns both bases
from one download. Over any window, (TR_t/TR_{t-L}) / (PX_t/PX_{t-L}) - 1 is
the income actually distributed -- an observed number, not an assumed yield.

============================================================================
EMPIRICAL DURATION: THE ONE PRIMITIVE ALL THREE MECHANISMS SHARE
============================================================================
Every mechanism below needs each ETF's interest-rate sensitivity, and two of
them need to duration-MATCH one instrument against another. This module
never hardcodes a published fund-fact-sheet duration. It estimates, at each
formation date and from that formation's own trailing window only, each
ETF's empirical duration BETA: the slope of its daily total returns on a
rate factor defined as the equal-weighted mean daily return of the Treasury
maturity ladder (the ladder's own "level" factor, in Litterman-Scheinkman's
sense -- the first principal component of a set of highly correlated series
is very close to their equal-weighted mean, at a fraction of the machinery).

Three reasons this is better here than a published duration, not merely
cheaper:
 * It is point-in-time by construction. A fund's duration drifts as its
   holdings roll and as rates move; a single fact-sheet number applied
   across nineteen years would be a look-ahead-flavoured constant.
 * Duration RATIOS are all any mechanism here actually needs -- a hedge
   ratio, or a carry-per-unit-of-risk denominator -- and beta_i / beta_j is
   exactly that ratio. The reference duration cancels, so no external
   constant enters anywhere.
 * For credit, empirical duration is the RIGHT number and analytical
   duration is the wrong one. HYG's analytical duration is ~3-4 years, but
   its measured rate beta is near zero and frequently NEGATIVE (measured at
   formation dates spanning the sample: -0.64 in 2010, -0.14 in 2015, -0.35
   in 2019, +0.31 in 2022, +0.39 in 2026), because spread widening offsets
   rate rallies. Measured corr(HYG, TLT) on daily returns over the full
   common window is -0.1312 -- re-verified here, and the direct evidence
   that credit is a genuinely separate risk axis from rates rather than a
   levered version of it.

Sanity-checked live: the estimated betas order themselves monotonically by
maturity exactly as a real duration ladder must (2026-08-26, 252-day window:
SHY 0.19, IEI 0.53, IEF 0.90, TLH 1.54, TLT 1.84), and the annualized
realized volatilities do too (SHY 1.52%, IEI 4.11%, IEF 6.95%, TLH 10.54%,
TLT 15.12%).

============================================================================
MECHANISM 1 -- CURVE CARRY / ROLL-DOWN  (Treasury ladder only)
============================================================================
CITATIONS:
 * Campbell, J. Y. & Shiller, R. J., "Yield Spreads and Interest Rate
   Movements: A Bird's Eye View" (Review of Economic Studies, 1991): the
   yield spread predicts excess bond returns in the opposite direction to
   the pure expectations hypothesis -- a steep curve forecasts realized
   excess returns on longer maturities rather than the rate rises that
   would offset them.
 * Fama, E. F. & Bliss, R. R., "The Information in Long-Maturity Forward
   Rates" (American Economic Review, 1987): forward-spot spreads predict
   bond excess returns at one-year horizons, the original evidence that
   term premia are time-varying and observable from the curve's shape.
 * Ilmanen, A., "Time-Varying Expected Returns in International Bond
   Markets" (Journal of Finance, 1995): curve steepness predicts bond
   excess returns across markets.
 * Koijen, R. S. J., Moskowitz, T. J., Pedersen, L. H. & Vrugt, E. B.,
   "Carry" (Journal of Financial Economics, 2018): the modern unifying
   treatment, defining a bond's carry as its yield spread over the
   short rate plus roll-down, and finding carry predicts returns within
   fixed income as well as across asset classes.

MECHANISM: an upward-sloping curve mechanically pays a longer-maturity bond
twice -- it earns a higher yield than the front end (carry), and as it ages
it is repriced at successively lower points on the curve (roll-down). A
constant-maturity ETF captures both: its duration stays inside its band
because it continuously sells bonds that have rolled below the band, and the
roll-down those bonds earned on the way is realized as fund return.

EXACT CONSTRUCTION, stated so it can be checked:

    signal_i  =  (y_i - y_front) / beta_i

  y_i      the ANNUALIZED TRAILING DISTRIBUTION YIELD of ETF i over the
           spec's own lookback window, measured as the wedge between the two
           price bases:
               y_i = [ (TR_last/TR_first) / (PX_last/PX_first) ] ^ (252/L) - 1
           i.e. the income the fund actually paid over the window, annualized.
  y_front  the same quantity for SHY, this basket's own front-end/short-rate
           proxy -- so the numerator is the yield PICKUP for taking duration
           beyond the front end, which is what carry means.
  beta_i   the empirical duration beta above.

DIVIDING BY DURATION IS THE LOAD-BEARING STEP, not a normalization detail.
Raw carry (y_i - y_front) is mechanically increasing in duration whenever
the curve slopes up, so ranking on it would produce a permanent "long TLT,
short SHY" position -- a static duration bet wearing a cross-sectional
costume, not a signal. Carry PER UNIT OF RATE RISK is the slope of the curve
over that segment, a genuinely time-varying cross-sectional quantity that
rotates the book and changes sign when the curve inverts. Verified on real
data across 37 quarterly-spaced formations: the long leg is (IEF, IEI) 15
times, (TLH, TLT) 10, (IEF, TLH) 6, (IEF, TLT) 3, (IEI, TLH) 3 -- it rotates
across the whole ladder rather than parking at the long end. And on
2023-10-31, with the curve deeply inverted, IEI's carry-per-duration was
measured NEGATIVE (-0.0105) while SHY's is identically zero by construction,
so the signal correctly ranked the front end top and went long it.

SHY's own signal is exactly 0.0 always (it is the reference point). That is
meaningful, not degenerate: when every other segment offers positive yield
pickup per unit duration SHY ranks last and is shorted; when the curve
inverts, every pickup goes negative, SHY's zero becomes the maximum, and the
book goes long the front end. That is the economically right response to an
inverted curve, and it falls out of the construction rather than being
special-cased.

WHY THE TREASURY LADDER ONLY (TIP/LQD/HYG get a NaN signal and are simply
not ranked by this mechanism): carry along the yield curve is a Treasury
term-premium concept, whereas LQD's and HYG's yield pickup is compensation
for DEFAULT risk and TIP's is a real-vs-nominal breakeven -- pooling them
would rank a credit premium against a term premium as though they were the
same quantity, and mechanism 3 exists precisely to test the credit axis on
its own terms. There is also a hard numerical reason: the construction
divides by beta, and HYG's beta is near zero and sign-unstable (measured
above), so the ratio would be both enormous and meaningless for exactly the
names that do not belong in a curve trade.

DISCLOSED APPROXIMATION -- read this before trusting mechanism 1's numbers.
A trailing distribution yield is a REALIZED, CASH measure: it is what the
fund paid over the window, driven by the coupons of bonds it already holds.
It is NOT the SEC 30-day yield or the portfolio's yield-to-maturity, and the
two diverge exactly when rates move fast, because a fund's coupon stream
reprices only as its holdings turn over. Measured instance, and it is a big
one: on 2022-06-30, SHY's trailing 252-day distribution yield was 0.37%
while 2-year Treasury market yields were several times that. So this proxy
LAGS the true forward carry, by roughly half the fund's own turnover cycle
(short for SHY, years for TLT, which holds 20-30y bonds for about a decade
before they leave its band). This is a real weakness of the proxy, it is
the honest best available from price data alone without a yield feed, and
the direction of the resulting error is a lag rather than a bias toward
looking good. A real curve (FRED constant-maturity yields) would fix it and
is the obvious next step if this mechanism shows anything.

============================================================================
MECHANISM 2 -- BUTTERFLY RELATIVE VALUE  (Treasury ladder only)
============================================================================
CITATION:
 * Litterman, R. & Scheinkman, J., "Common Factors Affecting Bond Returns"
   (Journal of Fixed Income, 1991): three factors -- level, slope and
   curvature -- explain very nearly all of the variance of Treasury returns
   across the maturity spectrum. A butterfly (long the two wings, short the
   belly, duration-matched so the level exposure nets out) is the standard
   trade that isolates the curvature factor, and deviation of the belly from
   its duration-matched wing combination is the standard local-dislocation
   signal.

EXACT CONSTRUCTION: at each formation date, across the Treasury ladder only,
regress each ETF's trailing cumulative total return c_i on its empirical
duration beta,

    c_i  =  alpha + lambda * beta_i + e_i          (ordinary least squares)

and take signal_i = -e_i.

The fitted part is exactly the level component: a parallel shift of the
yield curve produces a return proportional to duration, so alpha + lambda*b
absorbs it completely. The residual e_i is the part of the trailing return
that a duration-linear move cannot explain, and across a maturity ladder its
dominant cross-sectional shape IS the butterfly -- a slope or curvature move
in yields maps to a return that is CONVEX in duration, whose deviation from
the best-fit line is therefore U-shaped: same sign at both wings, opposite
sign in the belly. Negating gives mean reversion: an ETF that has
outperformed its duration-matched combination is rich and is shorted, one
that has underperformed is cheap and is bought.

Two properties verified rather than assumed. (1) OLS orthogonality holds to
machine precision on real data (sum of residuals 6.9e-17, sum of
beta-weighted residuals 3.5e-17), which is the formal statement that the
residual carries no level exposure -- this is what makes the construction
duration-matched rather than merely duration-aware. (2) The realized trade
really is a butterfly: across 37 quarterly-spaced formations the long leg
was the two WINGS (SHY, TLT) 21 times, far more than any other pair.

WHY A LEAST-SQUARES BUTTERFLY RATHER THAN THE TEXTBOOK 3-POINT ONE. The
classic construction picks one belly and its two neighbouring wings, with
wing weights w_S = (D_L - D_B)/(D_L - D_S) and w_L = (D_B - D_S)/(D_L - D_S)
so the wings' duration matches the belly's. On a 5-point ladder only the
three INTERIOR points (IEI, IEF, TLH) can ever be a belly, so that version
yields three rankable names -- and three names cannot produce two disjoint
legs of the minimum size at ANY rank_fraction (two legs of 2 need 4 names;
legs of 1 fall below min_names_per_leg). It is arithmetically unusable here.
The least-squares version generalizes the same wings-vs-belly economics
across the whole ladder, keeps all five names rankable, and is duration-
matched by the same orthogonality property -- at the cost, stated plainly,
that a single linear regressor cannot fully separate SLOPE from CURVATURE,
so e_i is a slope-and-curvature residual rather than pure curvature.

Also honest: OLS orthogonality holds across the FULL cross-section, but the
legs are its extremes (top 2 and bottom 2 of 5), not the whole of it, so the
realized long-short book is only APPROXIMATELY duration-neutral, not exactly
so. run_bonds_screening measures each mechanism's realized rate beta from
its own return stream and reports it, rather than leaving this as a claim.

============================================================================
MECHANISM 3 -- DURATION-HEDGED CREDIT-SPREAD REVERSION  (all eight names)
============================================================================
CITATIONS:
 * Collin-Dufresne, P., Goldstein, R. S. & Martin, J. S., "The Determinants
   of Credit Spread Changes" (Journal of Finance, 2001): structural-model
   variables explain only a modest share of credit-spread changes, and the
   residuals are driven by a single dominant common factor -- credit is its
   own risk axis, not a restatement of the rate axis. The same paper is the
   standard source for spread changes being negatively related to Treasury
   rates, which is precisely why the rate exposure has to be hedged out
   before a credit signal means anything.
 * Asvanunt, A. & Richardson, S., "The Credit Risk Premium" (Journal of
   Fixed Income, 2017): isolates the credit premium by hedging out the
   duration component of corporate-bond returns, since the unhedged return
   is dominated by its Treasury component.
 * Fama, E. F. & French, K. R., "Common Risk Factors in the Returns on
   Stocks and Bonds" (Journal of Financial Economics, 1993): TERM and DEF
   enter as distinct bond-market factors.

EXACT CONSTRUCTION: over the spec's lookback window, hedge each ETF's daily
total return against the Treasury rate factor at its own empirical duration
beta and cumulate what is left,

    u_{i,t}   =  r_{i,t} - beta_i * f_t
    hedged_i  =  sum over the window of u_{i,t}
    signal_i  =  -hedged_i

beta_i * f_t is the duration-matched Treasury combination the brief calls
for -- expressed as a beta against the ladder factor rather than as an
explicit two-bond basket, which is the same hedge with an estimator that
degrades gracefully instead of breaking when a specific hedge instrument is
unavailable. Negating gives spread reversion: an ETF whose duration-hedged
excess return has been negative has had its spread widen, is cheap, and is
bought. Summing daily residuals rather than compounding them is the standard
convention for a hedged excess return and is a genuine (small) approximation
at these horizons.

WHY ALL EIGHT NAMES ARE RANKED even though the mechanism is about credit:
there are only three non-Treasury instruments here (TIP, LQD, HYG), and
three names cannot form two disjoint legs of 2 -- the identical arithmetic
that ruled out the 3-point butterfly. Ranking the full basket is not a
dilution of the mechanism, because a pure Treasury's duration-hedged excess
is small by construction and it therefore tends to sit mid-pack, leaving the
extremes to the spread-bearing names. Verified on real data across 37
formations: the SHORT leg was (HYG, LQD) 20 times, more than every other
pair combined, i.e. the trade is most often "short credit when it is rich".

Two things this measurement also showed, reported because they are the
uncomfortable half. First, the mechanism is ASYMMETRIC in practice -- the
long leg was (HYG, LQD) only twice, and was most often the long-end
Treasuries (TLH, TLT) 14 times. Second, and following from that, the
resulting BOOK is not automatically duration-neutral even though the SIGNAL
is duration-hedged: the legs are the extremes of the ranking, not an
orthogonality-preserving combination, so a long-TLT/short-HYG book carries
real residual rate exposure. Mechanism 2's OLS orthogonality does not
transfer here. run_bonds_screening measures and reports each mechanism's
realized rate beta for exactly this reason.

OVERLAP WITH MECHANISM 2, stated rather than hidden: for the five Treasury
names, mechanism 3's hedged excess and mechanism 2's regression residual are
related quantities, so these two axes are not fully independent. They differ
in cross-section (8 names vs 5) and in estimator (a time-series rate-beta
residual cumulated over the window, vs a cross-sectional residual from the
duration-return line fitted at the formation date). run_bonds_screening
measures the realized correlation between the mechanisms' actual return
streams and reports it, so the degree of overlap is a number rather than an
argument.

============================================================================
THE FAMILY: 3 x 2 x 3 = 18 SPECS, PRE-DECLARED AND NEVER SHRUNK
============================================================================
mechanism {curve_carry, butterfly, credit_hedged}
  x lookback {63, 252} trading days
  x holding  {63, 126, 252} trading days

3 * 2 * 3 = 18, recomputed from the grid rather than copied, asserted
exactly in _build_bonds_family, and fixed as BONDS_N_TRIALS before any
result was seen. It is never shrunk to however many specs survive the data
floors -- that would be gameable by declaring specs expected to fail.

Unlike D2's n_trials=4, 18 clears deflated_sharpe.MIN_TRIALS_FOR_DSR (5), so
the DSR correction proper DOES compute for this family and is the number to
read, not PSR-vs-zero.

HOLDING PERIODS -- 21-day variants are excluded ON PURPOSE, and the floor is
63. Costs here are a large fraction of the available signal, so the holding
axis is a cost-amortization decision before it is a signal-decay one. At the
costs below, a 21-day hold reforms ~12 times a year and pays roughly 60bps/yr
of trading plus ~40bps/yr of financing; a 126-day hold reforms ~2 times and
pays roughly 10bps + 40bps. Against a book volatility in the single-digit
percents that is a Sharpe drag of order 0.3 at 21 days against order 0.1 at
126 -- so a 21-day variant would spend a third of a Sharpe on turnover
before the signal says anything. 126 is the family default, 63 the floor,
and the real measured drag is reported by run_bonds_screening from the run's
own realized volatility rather than left at this estimate.

============================================================================
COSTS: TWO COMPONENTS, DELIBERATELY NOT COLLAPSED
============================================================================
This family sets both of the harness's cost knobs, and they scale with
opposite things across the holding axis this family searches over.

TRADING, config.cost_bps = 2.5 (one-way, per unit of gross notional traded).
That is LOWER than the harness default DEFAULT_XS_COST_BPS = 5.0, and the
reduction is justified rather than assumed convenient: that default mirrors
momentum.py's single-leg equity convention, sized for S&P 500 single stocks.
These eight are among the most liquid ETFs listed, quoted at or near a penny
on double- and triple-digit prices, i.e. spreads of order 1bp. 2.5bps one-way
(5bps per instrument round-trip) is therefore already several times the
quoted half-spread, leaving room for impact. It is a disclosed assumption,
not a measured execution cost, and run_bonds_screening reports the BREAKEVEN
cost for any spec with a positive Sharpe so a reader can see how much of the
result the assumption is carrying.

FINANCING, config.financing_bps_per_year = 20.0, representing a 40bps/yr
SHORT-LEG borrow assumption. The factor of two is the harness field's own
documented arithmetic and must not be dropped: financing accrues on GROSS
notional held, a fully formed long-short book carries gross 2.0, and half of
that is the short leg -- so 40bps on the 1.0 short leg is 20bps applied to
gross 2.0. The long leg is treated as funded by the short proceeds, the same
self-financing dollar-neutral assumption metrics.sharpe_ratio already makes,
so it is not charged twice. 40bps/yr is a reasonable general-collateral rate
for ETFs of this size and short interest, and it is an ASSUMPTION, not a
sourced quote from a borrow desk; a real borrow feed is a paid data source
and is noted as such rather than silently wished away.

Keeping these separate is the point. Trading cost falls as holds lengthen,
financing rises, and no single blended per-trade number can be right at both
63 and 252 days. They are reported separately too (total_cost_drag vs
total_financing_drag on each result).

============================================================================
LEG SIZE: TWO NAMES, WELL BELOW THE HARNESS'S OWN FLOOR
============================================================================
config.min_names_per_leg = 2, against the harness default of 5. This must be
set explicitly or every formation is skipped, and the harness's stated reason
for that default -- "a leg with fewer names than this is a stock pick, not a
decile portfolio" -- deserves a real answer rather than an override.

The answer is that the unit here is not a stock. Each leg member is itself a
diversified fund holding hundreds to thousands of individual bonds, so a leg
of two ETFs is not two idiosyncratic bets; it is two systematic exposures on
a curve with essentially no single-issuer risk. The concentration the harness
default protects against is single-name blowup risk, which is the one risk a
Treasury ETF structurally does not have.

What a 2-name leg IS still exposed to, and this is the honest residual: with
eight instruments and legs of two, a single ETF entering or leaving a leg
moves half that leg, so formation-date luck matters more than it would in a
500-name cross-section, and the effective breadth of this whole family is
small. Ranking arithmetic, verified: the ladder mechanisms rank 5 names at
rank_fraction 0.4 (int(5*0.4) = 2, two disjoint legs of 2 from 5), and the
full-basket mechanism ranks 8 at rank_fraction 0.25 (int(8*0.25) = 2, two
disjoint legs of 2 from 8).

============================================================================
PRODUCTION RESULT (2026-08-27): A CLEAN NEGATIVE. NOTHING HERE IS AN EDGE.
============================================================================
Run over 2008-04-10..2026-08-26 (4,623 replayed trading days, formations
starting once all eight ETFs have a full 252-day lookback so all 18 specs
are on identical footing). All 18 specs replayed; all 18 returned; n_trials
= 18 throughout; dsr_floor_met True for every one.

Headline: mean Sharpe -0.010, median +0.028, 9 of 18 positive — a coin
flip. Best raw Sharpe was bonds_curve_carry_l63_h126 at +0.354, whose DSR is
0.385: below 0.5, i.e. the multiple-comparisons correction says this is
what the best of 18 zero-edge trials looks like. No spec clears any
reasonable bar on the DSR alone.

But the DSR is not even the strongest evidence here. THE POSITIVE SHARPES
ARE THE TERM PREMIUM, NOT ALPHA, and the numbers say so unambiguously.
Over this window the Treasury ladder factor itself earned a Sharpe of
+0.350 — most of a historic bond bull market. Measured realized rate betas
of the mechanisms' own return streams:

  mechanism       mean Sharpe   rate beta   rate-neutralized Sharpe   t(alpha)
  curve_carry        +0.195       +0.747            -0.172             -0.74
  credit_hedged      -0.047       +1.110            -0.374             -1.60
  butterfly          -0.178       -0.045            -0.249             -1.07

EVERY mechanism is NEGATIVE once its duration exposure is removed. Per
spec, regressing each daily stream on that factor: NOT ONE of the 18 has an
alpha t-statistic above +0.53, none reaches t > 2.0, only 3 of 18 have a
positive alpha at all, and the best raw spec's +0.354 Sharpe collapses to a
rate-neutralized +0.125 (alpha +0.49%/yr, t = +0.53).

The ordering is the whole finding. The two mechanisms that looked best are
exactly the two carrying the most rate exposure (curve_carry +0.75,
credit_hedged +1.11), while the one mechanism whose traded book really is
rate-neutral — butterfly, realized beta -0.045, the OLS orthogonality
genuinely transferring from the cross-section to the traded legs, which is
a real construction success — has the WORST raw Sharpe of the three. What
looks like edge here is duration; what is actually duration-neutral has no
edge.

Two further honest notes from the run, neither of which rescues it:
 * COSTS DID NOT KILL THIS. Realized cost drag was 0.03-0.13 Sharpe (the
   design estimate was ~0.10 at 126 days), and breakeven trading costs run
   4x-89x the assumed 2.5bps. Unlike Rounds A/B, whose negatives had a
   cost-dominated signature, this family's signal is simply absent — a
   different and stronger form of negative result.
 * THE HOLDING-PERIOD REASONING ABOVE USED A BOOK VOLATILITY THAT THE REAL
   DATA CONTRADICTS. It assumed 3-5%; realized was 4.9-5.7% for butterfly,
   6.0-8.0% for curve_carry and 13.8-15.3% for credit_hedged. At those
   higher volatilities the cost drag at a 21-day hold would have been
   nearer 0.1 than 0.3, so the cost argument for excluding 21-day variants
   was weaker than stated (the signal-decay argument is untouched). This is
   recorded rather than acted on: the family was pre-declared at 18 and
   stays 18, and re-opening the grid after seeing results is precisely the
   thing n_trials exists to prevent. It is an input to a FUTURE
   pre-declared round, not a revision of this one.

The obvious next pre-declared round, if this direction is pursued, is one
whose books are rate-neutralized BY CONSTRUCTION rather than only in the
signal — the measured gap between "the signal is duration-hedged" and "the
traded book is duration-neutral" is the single largest design weakness this
run exposed, and mechanism 2 shows it is achievable.

MEASURED, NOT ARGUED: run_bonds_screening returns all of the above as typed
fields (BondsRateExposure per spec, BondsMechanismDiagnostic per mechanism,
mechanism_correlations, and the cost/breakeven disclosure) so that no future
run of this family can report a positive Sharpe without the term-premium
decomposition sitting right next to it.

Cross-mechanism return correlations, for the record: butterfly/credit_hedged
+0.030 and butterfly/curve_carry +0.067 (genuinely independent axes), but
credit_hedged/curve_carry +0.627 — the two rate-loaded books substantially
overlap, which is a direct consequence of the un-neutralized duration
described above rather than of the signals sharing information.

One design fragility the run surfaced: curve_carry skipped 5-11 formations
out of 37-74 (the other mechanisms skipped none), always for the same
reason — "only 4 ranked names -> leg of 1 < min_names_per_leg=2". With a
5-name ladder and rank_fraction 0.4, a SINGLE NaN'd name drops the
cross-section to 4, where int(4*0.4) = 1 and the formation cannot form two
legs of 2. The 5-name ladder has no margin for a single missing signal.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import partial

import numpy as np
import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalScreeningResult,
    CrossSectionalSpec,
    fixed_universe_membership,
    run_cross_sectional_backtest,
    screen_cross_sectional_universe,
)
from app.services.research_lab.metrics import sharpe_ratio

logger = logging.getLogger(__name__)

# The Treasury maturity ladder: the pure interest-rate instruments, ordered
# short to long. Mechanisms 1 and 2 rank ONLY these (see module docstring),
# and all three use them to build the rate factor.
TREASURY_LADDER: tuple[str, ...] = ("SHY", "IEI", "IEF", "TLH", "TLT")

# The spread-bearing instruments: inflation-linked and credit. Ranked only by
# mechanism 3, but part of the rate-factor regression's left-hand side for
# all three.
SPREAD_INSTRUMENTS: tuple[str, ...] = ("TIP", "LQD", "HYG")

BONDS_UNIVERSE: tuple[str, ...] = TREASURY_LADDER + SPREAD_INSTRUMENTS

# The basket's own short-rate / front-end proxy, against which mechanism 1
# measures yield pickup. SHY (1-3y Treasuries) is the shortest-duration
# instrument here by construction and was confirmed to have the smallest
# empirical duration beta at every spot-checked formation date (0.10-0.21
# across 2010-2026).
FRONT_END_TICKER = "SHY"

# VERIFIED LIVE 2026-08-26, re-verified 2026-08-27: the first date on which
# all eight ETFs are simultaneously priced, bounded by HYG's own inception.
# The common window runs from here to today at exactly 4,876 rows.
BONDS_COMMON_HISTORY_START = date(2007, 4, 11)

# Trading days per year, the same 252 convention metrics.sharpe_ratio and
# every other module here already use.
TRADING_DAYS_PER_YEAR = 252

# A signal window with fewer than this fraction of its rows populated is
# refused (NaN signal) rather than computed on whatever little data exists.
# Kept at the same 0.8 register as cross_sectional_patterns.py's and
# cross_sectional_patterns_d2.py's constants of the same name, for
# consistency across families rather than because it was recalibrated here.
# It binds in exactly one real situation for this family: HYG in the first
# months after 2007-04-11, before a full lookback of its history exists.
MIN_SIGNAL_OBS_FRACTION = 0.8

# Mechanism 1 divides carry by empirical duration beta, so a beta near zero
# would produce an enormous, meaningless ratio. Any ladder ETF whose
# estimated beta falls below this is given a NaN signal instead. 0.05 sits
# far below every measured ladder beta (the smallest ever observed is SHY's
# ~0.10) and far above zero, so in practice it is a guard against a
# degenerate estimation window rather than a filter that routinely fires.
MIN_DURATION_BETA = 0.05

# Mechanism 2 fits two parameters (intercept and duration slope) across the
# ladder, so it needs at least this many usable ladder points to leave any
# residual degrees of freedom at all. 4 leaves 2. The full ladder is 5.
BUTTERFLY_MIN_LADDER_POINTS = 4

# --- the family grid, pre-declared -----------------------------------------
# Signal lookbacks in trading days: one quarter and one year. 63 is short
# enough that the duration-beta regression has only ~62 return observations
# -- thin for a beta, though within the 60-120 day range standard practice
# uses for empirical duration -- and 252 is the conventional one-year window
# every other family in this project uses.
BONDS_LOOKBACK_DAYS: tuple[int, ...] = (63, 252)

# Holding periods in trading days. 21-day variants are deliberately excluded
# and 63 is the floor -- see the module docstring's HOLDING PERIODS section
# for the cost arithmetic behind both decisions.
BONDS_HOLDING_DAYS: tuple[int, ...] = (63, 126, 252)
BONDS_DEFAULT_HOLDING_DAYS = 126
BONDS_MIN_HOLDING_DAYS = 63

# rank_fraction per cross-section width -- see the module docstring's LEG
# SIZE section. Both resolve to legs of exactly 2 under the harness's
# max(1, int(n * rank_fraction)) rule, with two disjoint legs available.
BONDS_LADDER_RANK_FRACTION = 0.4  # 5 ranked names -> legs of 2
BONDS_FULL_RANK_FRACTION = 0.25  # 8 ranked names -> legs of 2

# Explicitly configured, far below the harness's DEFAULT_MIN_NAMES_PER_LEG
# of 5, which would skip every formation this family attempts. See the
# module docstring's LEG SIZE section for why 2 is defensible for ETFs and
# what it still costs.
BONDS_MIN_NAMES_PER_LEG = 2

# One-way trading cost per unit of gross notional traded, and the short-leg
# borrow it is deliberately NOT blended with. See the module docstring's
# COSTS section for the justification of each, and for why the financing
# figure passed to the harness is half the borrow rate.
BONDS_COST_BPS = 2.5
BONDS_SHORT_BORROW_BPS_PER_YEAR = 40.0
BONDS_FINANCING_BPS_PER_YEAR = BONDS_SHORT_BORROW_BPS_PER_YEAR / 2.0

# This family's fixed, pre-declared size: the exact product of the grid
# above (3 mechanisms x 2 lookbacks x 3 holding periods), and the honest
# n_trials denominator for its own, never-pooled DSR correction. Asserted
# exactly in _build_bonds_family rather than merely documented.
BONDS_N_TRIALS = 18

CARRY_CITATION = (
    "Campbell & Shiller, 'Yield Spreads and Interest Rate Movements: A Bird's Eye View' "
    "(Review of Economic Studies, 1991); Fama & Bliss, 'The Information in Long-Maturity "
    "Forward Rates' (American Economic Review, 1987); Ilmanen, 'Time-Varying Expected Returns "
    "in International Bond Markets' (Journal of Finance, 1995); Koijen, Moskowitz, Pedersen & "
    "Vrugt, 'Carry' (Journal of Financial Economics, 2018)"
)
BUTTERFLY_CITATION = (
    "Litterman & Scheinkman, 'Common Factors Affecting Bond Returns' "
    "(Journal of Fixed Income, 1991)"
)
CREDIT_CITATION = (
    "Collin-Dufresne, Goldstein & Martin, 'The Determinants of Credit Spread Changes' "
    "(Journal of Finance, 2001); Asvanunt & Richardson, 'The Credit Risk Premium' "
    "(Journal of Fixed Income, 2017); Fama & French, 'Common Risk Factors in the Returns on "
    "Stocks and Bonds' (Journal of Financial Economics, 1993)"
)


# --- shared primitives -----------------------------------------------------


def _daily_returns(window: pd.DataFrame) -> pd.DataFrame:
    """Close-to-close simple returns. fill_method=None for the same reason
    cross_sectional.run_cross_sectional_backtest uses it: a mid-series NaN
    must yield a NaN return, never pandas' legacy forward-fill, which would
    fabricate a 0% return for a day the instrument did not trade."""
    return window.pct_change(fill_method=None)


def rate_factor(returns: pd.DataFrame) -> pd.Series:
    """The Treasury ladder's own 'level' factor: the equal-weighted mean
    daily return of whichever ladder ETFs are present. See the module
    docstring's EMPIRICAL DURATION section for why an equal-weighted mean
    stands in for the first principal component here. Returns an all-NaN
    series when no ladder member is present at all, which propagates to
    NaN betas and hence to a NaN signal -- the correct 'cannot rank this
    formation' answer rather than a fabricated zero."""
    present = [t for t in TREASURY_LADDER if t in returns.columns]
    if not present:
        return pd.Series(np.nan, index=returns.index, dtype=float)
    return returns[present].mean(axis=1, skipna=True)


def empirical_duration_betas(window: pd.DataFrame) -> pd.Series:
    """Each column's empirical duration beta over the window: the slope of
    its daily total returns on the Treasury ladder's level factor,
    cov(r_i, f) / var(f).

    This is the module's single duration primitive -- see the module
    docstring for why an estimated beta is preferred to a published
    fund-fact-sheet duration, and why only RATIOS of these betas are ever
    used (so the reference duration cancels and no external constant is
    needed). NaN for any column with too little overlapping data for a
    covariance, and an all-NaN result when the factor itself is degenerate
    (zero or non-finite variance), which is the honest answer for a window
    in which rates did not move at all."""
    returns = _daily_returns(window)
    factor = rate_factor(returns)
    var_f = factor.var(ddof=1)
    if not np.isfinite(var_f) or var_f <= 0.0:
        return pd.Series(np.nan, index=window.columns, dtype=float)
    return returns.apply(lambda col: col.cov(factor) / var_f)


def annualized_income_yield(
    total_return_window: pd.DataFrame, price_only_window: pd.DataFrame
) -> pd.Series:
    """The trailing DISTRIBUTION yield, annualized: the wedge between the
    dividend-adjusted (total-return) and dividend-unadjusted (price-only)
    bases over the window,

        [ (TR_last/TR_first) / (PX_last/PX_first) ] ^ (252/periods) - 1

    This is income the fund actually paid, observed rather than assumed --
    see the module docstring for the construction, for why these
    instruments make it the whole signal, and for the DISCLOSED
    APPROXIMATION (it is a realized cash yield that LAGS market
    yield-to-maturity, materially so when rates move fast).

    `periods` is len(window) - 1, NOT the spec's lookback_days: a 252-row
    window spans 251 daily growth periods, and annualizing an endpoint-to-
    endpoint ratio by the ROW count over-annualizes it by a factor of
    252/251. That error is tiny (~0.4% of the yield) and, being a common
    factor, cannot change a cross-sectional ranking -- it is fixed anyway
    because the reported yields are read directly by the diagnostics and by
    anyone auditing a formation, where a number that is silently 0.4% wrong
    is worse than one that is right. Deriving it from the window rather
    than from lookback_days also stays correct when the window is short
    (early history) and returns fewer rows than the spec asked for.

    Non-positive or non-finite endpoints yield NaN rather than a complex or
    infinite number."""
    periods = len(total_return_window) - 1
    if periods <= 0:
        return pd.Series(np.nan, index=total_return_window.columns, dtype=float)

    tr_first = total_return_window.iloc[0]
    tr_last = total_return_window.iloc[-1]
    px_first = price_only_window.iloc[0]
    px_last = price_only_window.iloc[-1]

    with np.errstate(invalid="ignore", divide="ignore"):
        tr_growth = tr_last / tr_first
        px_growth = px_last / px_first
        income_growth = tr_growth / px_growth

    usable = (
        np.isfinite(income_growth)
        & (income_growth > 0.0)
        & np.isfinite(tr_first)
        & (tr_first > 0.0)
        & np.isfinite(px_first)
        & (px_first > 0.0)
    )
    periods_per_year = TRADING_DAYS_PER_YEAR / float(periods)
    annualized = pd.Series(np.nan, index=total_return_window.columns, dtype=float)
    annualized[usable] = income_growth[usable] ** periods_per_year - 1.0
    return annualized


def _coverage_ok(window: pd.DataFrame, lookback_days: int) -> pd.Series:
    """Per-column: does this window carry enough real observations to be
    computed on at all (see MIN_SIGNAL_OBS_FRACTION)?"""
    n_obs = window.notna().sum()
    return n_obs >= int(lookback_days * MIN_SIGNAL_OBS_FRACTION)


# --- mechanism 1: curve carry / roll-down ----------------------------------


def signal_curve_carry_rolldown(history: CrossSectionalData, *, lookback_days: int) -> pd.Series:
    """Carry per unit of interest-rate risk along the Treasury curve:
    (y_i - y_front) / beta_i, ranked over the Treasury maturity ladder only.
    Long the top (steepest yield pickup per unit of duration taken). See the
    module docstring's MECHANISM 1 section for the full construction, for
    why dividing by duration is what stops this being a static long-duration
    bet, and for the disclosed lag in the distribution-yield proxy.

    Every non-ladder instrument gets NaN and is simply not ranked by this
    mechanism -- carry along the yield curve is a term-premium concept, and
    LQD/HYG/TIP are compensated for default and inflation risk instead."""
    if history.price_only_close is None:
        raise ValueError(
            "signal_curve_carry_rolldown needs CrossSectionalData.price_only_close (the "
            "dividend-unadjusted basis) to observe income separately from price change; the "
            "spec must declare requires_price_only_close=True."
        )

    tr_window = history.close.iloc[-lookback_days:]
    px_window = history.price_only_close.iloc[-lookback_days:]

    signal = pd.Series(np.nan, index=history.close.columns, dtype=float)
    ladder = [t for t in TREASURY_LADDER if t in history.close.columns]
    if FRONT_END_TICKER not in ladder:
        # No front-end reference means no yield PICKUP can be measured at
        # all. Refusing the whole formation is the honest answer; silently
        # substituting another ticker would change what the signal means.
        return signal

    yields = annualized_income_yield(tr_window, px_window)
    betas = empirical_duration_betas(tr_window)
    enough = _coverage_ok(tr_window, lookback_days) & _coverage_ok(px_window, lookback_days)

    y_front = yields.get(FRONT_END_TICKER, np.nan)
    if not (np.isfinite(y_front) and bool(enough.get(FRONT_END_TICKER, False))):
        return signal

    for ticker in ladder:
        if not bool(enough.get(ticker, False)):
            continue
        beta = betas.get(ticker, np.nan)
        y = yields.get(ticker, np.nan)
        if not (np.isfinite(beta) and np.isfinite(y)):
            continue
        # A Treasury ETF with a near-zero or negative measured rate beta is
        # an estimation artifact, not a curve observation -- dividing by it
        # would produce an enormous, sign-unstable number.
        if beta < MIN_DURATION_BETA:
            continue
        signal[ticker] = (y - y_front) / beta

    return signal


# --- mechanism 2: butterfly relative value ---------------------------------


def signal_curve_butterfly(history: CrossSectionalData, *, lookback_days: int) -> pd.Series:
    """Litterman-Scheinkman butterfly relative value across the Treasury
    ladder: the negated residual of each ETF's trailing cumulative return
    regressed on its empirical duration beta. Long the top (cheapest
    relative to its duration-matched combination). See the module
    docstring's MECHANISM 2 section for the construction, for the OLS
    orthogonality property that makes it duration-matched, and for why the
    least-squares form is used instead of the textbook 3-point butterfly.

    Every non-ladder instrument gets NaN: a credit or inflation-linked ETF's
    deviation from the nominal Treasury duration line is a spread or
    breakeven move, not curvature, and mechanism 3 tests that separately."""
    window = history.close.iloc[-lookback_days:]
    signal = pd.Series(np.nan, index=history.close.columns, dtype=float)

    betas = empirical_duration_betas(window)
    enough = _coverage_ok(window, lookback_days)

    with np.errstate(invalid="ignore", divide="ignore"):
        cumulative = window.iloc[-1] / window.iloc[0] - 1.0

    usable = [
        t
        for t in TREASURY_LADDER
        if t in window.columns
        and bool(enough.get(t, False))
        and np.isfinite(betas.get(t, np.nan))
        and np.isfinite(cumulative.get(t, np.nan))
    ]
    if len(usable) < BUTTERFLY_MIN_LADDER_POINTS:
        # Too few ladder points to leave the fit any residual degrees of
        # freedom -- a residual from a saturated fit is identically zero and
        # would rank on nothing at all.
        return signal

    beta_vec = np.array([float(betas[t]) for t in usable], dtype=float)
    cum_vec = np.array([float(cumulative[t]) for t in usable], dtype=float)
    if not np.isfinite(beta_vec.std()) or beta_vec.std() <= 0.0:
        # Every ladder point at the same estimated duration: the regressor
        # has no variation, so there is no duration line to deviate from.
        return signal

    design = np.column_stack([np.ones(len(usable)), beta_vec])
    coefficients, *_ = np.linalg.lstsq(design, cum_vec, rcond=None)
    residuals = cum_vec - design @ coefficients

    # Negated: a positive residual means the ETF outperformed its
    # duration-matched combination, i.e. it is RICH and belongs in the short
    # leg. Reversion is the hypothesis under test.
    for ticker, resid in zip(usable, residuals, strict=True):
        signal[ticker] = -float(resid)
    return signal


# --- mechanism 3: duration-hedged credit-spread reversion ------------------


def signal_duration_hedged_credit(history: CrossSectionalData, *, lookback_days: int) -> pd.Series:
    """Duration-hedged credit-spread reversion across the whole basket: each
    ETF's daily total return hedged against the Treasury rate factor at its
    own empirical duration beta, cumulated over the window, and negated so a
    widened spread (a negative hedged excess) ranks long. See the module
    docstring's MECHANISM 3 section for the construction, for why all eight
    names are ranked even though the mechanism is about credit, and for the
    two measured caveats (the trade is asymmetric in practice, and the
    resulting book is not automatically duration-neutral)."""
    window = history.close.iloc[-lookback_days:]
    signal = pd.Series(np.nan, index=history.close.columns, dtype=float)

    returns = _daily_returns(window)
    factor = rate_factor(returns)
    var_f = factor.var(ddof=1)
    if not np.isfinite(var_f) or var_f <= 0.0:
        return signal

    betas = empirical_duration_betas(window)
    enough = _coverage_ok(window, lookback_days)

    for ticker in window.columns:
        if not bool(enough.get(ticker, False)):
            continue
        beta = betas.get(ticker, np.nan)
        if not np.isfinite(beta):
            continue
        hedged_daily = returns[ticker] - beta * factor
        hedged_excess = hedged_daily.sum(skipna=True)
        if not np.isfinite(hedged_excess):
            continue
        signal[ticker] = -float(hedged_excess)

    return signal


# --- the family ------------------------------------------------------------

# (mechanism key, signal fn, citation, rank_fraction, needs price_only_close)
_MECHANISMS: tuple[tuple[str, object, str, float, bool], ...] = (
    ("curve_carry", signal_curve_carry_rolldown, CARRY_CITATION, BONDS_LADDER_RANK_FRACTION, True),
    ("butterfly", signal_curve_butterfly, BUTTERFLY_CITATION, BONDS_LADDER_RANK_FRACTION, False),
    ("credit_hedged", signal_duration_hedged_credit, CREDIT_CITATION, BONDS_FULL_RANK_FRACTION, False),
)


def _build_bonds_family() -> list[CrossSectionalSpec]:
    """Assembles the full, fixed Bonds family: the exact product of
    _MECHANISMS x BONDS_LOOKBACK_DAYS x BONDS_HOLDING_DAYS. The literal
    length of this list is the n_trials denominator
    screen_cross_sectional_universe uses -- every definition counts, whether
    or not it survives the data floors."""
    specs: list[CrossSectionalSpec] = []
    for mechanism, signal_fn, citation, rank_fraction, needs_price_only in _MECHANISMS:
        for lookback in BONDS_LOOKBACK_DAYS:
            for holding in BONDS_HOLDING_DAYS:
                specs.append(
                    CrossSectionalSpec(
                        pattern_id=f"bonds_{mechanism}_l{lookback}_h{holding}",
                        family=f"bonds_{mechanism}",
                        citation=citation,
                        signal_fn=partial(signal_fn, lookback_days=lookback),
                        lookback_days=lookback,
                        holding_days=holding,
                        portfolio="long_short",
                        rank_fraction=rank_fraction,
                        requires_price_only_close=needs_price_only,
                    )
                )

    expected = len(_MECHANISMS) * len(BONDS_LOOKBACK_DAYS) * len(BONDS_HOLDING_DAYS)
    assert len(specs) == expected == BONDS_N_TRIALS, (
        f"Bonds family built {len(specs)} definitions; the grid "
        f"({len(_MECHANISMS)} mechanisms x {len(BONDS_LOOKBACK_DAYS)} lookbacks x "
        f"{len(BONDS_HOLDING_DAYS)} holding periods) implies {expected}; the pre-declared "
        f"BONDS_N_TRIALS is {BONDS_N_TRIALS}. All three must agree -- a drift here silently "
        "changes the DSR's multiple-comparisons denominator for every future run."
    )
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    assert all(s.portfolio == "long_short" for s in specs)
    assert all(s.holding_days >= BONDS_MIN_HOLDING_DAYS for s in specs), (
        "21-day (and shorter) holding periods are deliberately excluded from this family -- "
        "see the module docstring's HOLDING PERIODS section."
    )
    assert all(s.leg_weighting == "magnitude" for s in specs)
    assert all(s.cohort_formation_days is None for s in specs), (
        "this family forms non-overlapping holds; it does not use the harness's "
        "overlapping-cohort option."
    )
    return specs


BONDS_FAMILY: list[CrossSectionalSpec] = _build_bonds_family()

# Calendar padding fetched BEFORE the requested screening start, purely to
# warm up the longest signal lookback (252 trading days ~= 252 * 365 / 252 =
# 365 calendar days) plus room for holiday clustering. Formations themselves
# never occur in the padding -- CrossSectionalConfig.formation_start pins
# them to the requested start.
BONDS_PRICE_HISTORY_PADDING_CALENDAR_DAYS = 420


def default_bonds_config() -> CrossSectionalConfig:
    """This family's own cost/leg configuration, as a function rather than a
    module-level singleton so callers cannot mutate a shared object (the
    harness writes formation_start onto whatever config it is given). See
    the module docstring's COSTS and LEG SIZE sections for the justification
    of every value here."""
    return CrossSectionalConfig(
        cost_bps=BONDS_COST_BPS,
        min_names_per_leg=BONDS_MIN_NAMES_PER_LEG,
        financing_bps_per_year=BONDS_FINANCING_BPS_PER_YEAR,
    )


@dataclass(frozen=True)
class BondsRateExposure:
    """How much of one return stream is just the term premium.

    THE SINGLE MOST IMPORTANT NUMBER THIS FAMILY REPORTS, and the reason it
    is computed automatically rather than left to whoever reads a Sharpe.
    Every mechanism here trades instruments whose dominant common factor is
    the level of interest rates, and the replay window (2008 onward) covers
    most of a historic bond bull market: the Treasury ladder factor itself
    earned a Sharpe of about +0.35 over it. So a book that ends up with a
    large positive rate beta will show a positive Sharpe whether or not its
    SIGNAL has any cross-sectional edge at all, purely by inheriting that.

    `sharpe` is the raw, headline number. `rate_beta` is the book's realized
    loading on the ladder factor. `alpha_annualized` and `alpha_t_stat` come
    from regressing the daily stream on that factor, and
    `rate_neutralized_sharpe` is the Sharpe of the residual. When the raw
    Sharpe is positive but the neutralized one is not, the honest reading is
    "this is term premium, not alpha" — which is exactly what this family's
    own production run found for every spec that looked good."""

    pattern_id: str
    sharpe: float
    rate_beta: float
    alpha_annualized: float
    alpha_t_stat: float
    rate_neutralized_sharpe: float


@dataclass(frozen=True)
class BondsMechanismDiagnostic:
    """Per-mechanism measurements taken from the REAL replayed return
    streams, computed so that the claims this module's docstring makes are
    reported as numbers rather than left as arguments: how much rate
    exposure each mechanism's book actually carried (and what is left of it
    once that is removed), how correlated the mechanisms turned out to be,
    and what the realized book volatility was (which is what the cost-drag
    arithmetic divides by)."""

    mechanism: str
    n_specs_replayed: int
    mean_sharpe: float
    realized_book_volatility: float  # annualized, averaged over the mechanism's specs
    realized_rate_beta: float  # of the mechanism's own return stream, vs the ladder factor
    rate_neutralized_sharpe: float  # what survives removing that rate exposure
    alpha_t_stat: float  # t-statistic of the mechanism's alpha vs the rate factor


@dataclass
class BondsScreeningSummary:
    """run_bonds_screening's full result: the screening results, which
    tickers resolved no price data, the per-mechanism diagnostics above, and
    the cost/breakeven disclosure -- none of them hidden behind something a
    caller has to know to go and compute separately."""

    results: list[CrossSectionalScreeningResult]
    missing_price_data: list[str]
    mechanism_diagnostics: list[BondsMechanismDiagnostic] = field(default_factory=list)
    mechanism_correlations: dict[tuple[str, str], float] = field(default_factory=dict)
    # Per-spec term-premium decomposition, keyed by pattern_id -- see
    # BondsRateExposure for why this is the number that decides whether any
    # positive Sharpe here means anything.
    rate_exposure: dict[str, BondsRateExposure] = field(default_factory=dict)
    disclosure: str = ""


def _mechanism_of(pattern_id: str) -> str:
    """'bonds_credit_hedged_l63_h126' -> 'credit_hedged'."""
    body = pattern_id.removeprefix("bonds_")
    for mechanism, *_ in _MECHANISMS:
        if body.startswith(mechanism + "_"):
            return mechanism
    return "unknown"


def build_bonds_disclosure(
    results: list[CrossSectionalScreeningResult],
    config: CrossSectionalConfig,
    daily_by_pattern: dict[str, pd.Series] | None = None,
) -> str:
    """The cost/assumption disclosure, computed from the run's own numbers.
    For every spec that came back with a positive Sharpe it also reports the
    BREAKEVEN one-way trading cost -- the cost_bps at which that spec's
    realized edge would be exactly consumed -- so a reader can see how much
    of a positive result the 2.5bps assumption is carrying rather than
    taking it on trust.

    The arithmetic, since it is easy to get dimensionally wrong: the harness
    charges turnover cost linearly in cost_bps, so with `charged` the total
    cost actually deducted over the replay (as a fraction of equity, which
    is what total_cost_drag is) and `net` the realized cumulative net
    return, gross = net + charged, and the cost that would exactly consume
    the edge is cost_bps * gross / charged. Financing is deliberately NOT
    folded in: it scales with time held rather than with turnover, so it
    does not move when cost_bps does."""
    lines = [
        "BONDS FAMILY COST DISCLOSURE.",
        (
            f"  Trading: {config.cost_bps} bps one-way per unit of gross notional traded "
            "(an assumption, not a measured execution cost; several times these ETFs' ~1bp quoted "
            "spreads, to leave room for impact)."
        ),
        (
            f"  Financing: {config.financing_bps_per_year} bps/yr on gross notional held, "
            f"representing a {BONDS_SHORT_BORROW_BPS_PER_YEAR} bps/yr SHORT-LEG borrow assumption "
            "(halved because financing accrues on gross 2.0 and half the book is short). This is "
            "an assumption, not a sourced borrow quote -- a real borrow feed is a paid data "
            "source."
        ),
        (
            f"  min_names_per_leg={config.min_names_per_leg} (harness default is 5): legs of 2 "
            "ETFs, each itself a fund of hundreds of bonds, so not a 2-name idiosyncratic bet -- "
            "but the effective breadth of this family is genuinely small and formation-date luck "
            "matters."
        ),
    ]
    positive = [r for r in results if r.sharpe_annualized > 0]
    if not positive:
        lines.append(
            "  Breakeven cost: not applicable -- no spec produced a positive Sharpe, so no "
            "positive result depends on the trading-cost assumption."
        )
        return "\n".join(lines)

    lines.append("  Breakeven one-way trading cost for each spec with a positive Sharpe:")
    for r in sorted(positive, key=lambda x: -x.sharpe_annualized):
        charged = r.total_cost_drag
        series = (daily_by_pattern or {}).get(r.pattern_id)
        if charged <= 0 or series is None or series.empty:
            lines.append(
                f"    {r.pattern_id}: Sharpe {r.sharpe_annualized:+.3f}; breakeven not computable "
                "(no turnover cost charged, or no return series available)."
            )
            continue
        net = float(series.sum())
        gross = net + charged
        breakeven_bps = config.cost_bps * gross / charged
        lines.append(
            f"    {r.pattern_id}: Sharpe {r.sharpe_annualized:+.3f}, cumulative net "
            f"{net:+.2%} after {charged:.2%} of trading cost -> breakeven at "
            f"~{breakeven_bps:.1f} bps one-way ({breakeven_bps / config.cost_bps:.1f}x the "
            "assumption)."
        )
    return "\n".join(lines)


def compute_rate_exposure(
    pattern_id: str, daily_returns: pd.Series, factor: pd.Series
) -> BondsRateExposure:
    """Regresses one return stream on the Treasury ladder factor and reports
    what is left. See BondsRateExposure for why this decomposition, and not
    the raw Sharpe, is what decides whether a result here means anything.

    The alpha t-statistic uses the plain iid standard error of the residual
    mean. That OVERSTATES significance for an overlapping or autocorrelated
    stream, so it is a generous bound rather than a strict test: an alpha
    that is insignificant even by this measure is very safely
    insignificant, which is the direction the honest reading needs."""
    joined = pd.concat([daily_returns.rename("r"), factor.rename("f")], axis=1).dropna()
    nan = float("nan")
    if len(joined) < 3:
        return BondsRateExposure(pattern_id, nan, nan, nan, nan, nan)

    var_f = joined["f"].var(ddof=1)
    if not np.isfinite(var_f) or var_f <= 0.0:
        return BondsRateExposure(pattern_id, sharpe_ratio(daily_returns), nan, nan, nan, nan)

    beta = float(joined["r"].cov(joined["f"]) / var_f)
    residual = joined["r"] - beta * joined["f"]
    residual_std = float(residual.std(ddof=1))
    stream_std = float(joined["r"].std(ddof=1))

    # A stream that IS the factor scaled leaves a residual that is zero only
    # to floating-point dust (std ~1e-19, not exactly 0). metrics.sharpe_
    # ratio guards on `std == 0` exactly, so such a residual divides
    # numerical noise by numerical noise and yields a large, entirely
    # meaningless Sharpe (measured: -1.02 for an exactly-hedged stream).
    # Treat a residual that is negligible RELATIVE to the stream's own
    # volatility as what it is -- the factor explained everything, so there
    # is no alpha and no residual Sharpe. Guarding here rather than in
    # metrics.sharpe_ratio keeps every other family's numbers byte-identical.
    if stream_std > 0.0 and residual_std <= 1e-9 * stream_std:
        return BondsRateExposure(
            pattern_id=pattern_id,
            sharpe=sharpe_ratio(daily_returns),
            rate_beta=beta,
            alpha_annualized=0.0,
            alpha_t_stat=0.0,
            rate_neutralized_sharpe=0.0,
        )

    alpha_daily = float(residual.mean())
    standard_error = residual_std / np.sqrt(len(residual))
    t_stat = alpha_daily / standard_error if standard_error > 0 else nan
    return BondsRateExposure(
        pattern_id=pattern_id,
        sharpe=sharpe_ratio(daily_returns),
        rate_beta=beta,
        alpha_annualized=alpha_daily * TRADING_DAYS_PER_YEAR,
        alpha_t_stat=t_stat,
        rate_neutralized_sharpe=sharpe_ratio(residual),
    )


def _compute_mechanism_diagnostics(
    results: list[CrossSectionalScreeningResult],
    daily_by_pattern: dict[str, pd.Series],
    close: pd.DataFrame,
) -> tuple[
    list[BondsMechanismDiagnostic],
    dict[tuple[str, str], float],
    dict[str, BondsRateExposure],
]:
    """Measures, from the REAL replayed return streams, everything the
    module docstring promises to report as numbers rather than argue:
    realized book volatility, realized rate exposure and what survives
    removing it (is a positive Sharpe alpha, or just the term premium?),
    and the cross-mechanism correlation (are these really independent
    axes?)."""
    ladder_returns = _daily_returns(close)
    factor = rate_factor(ladder_returns)

    by_mechanism: dict[str, list[str]] = {}
    for r in results:
        by_mechanism.setdefault(_mechanism_of(r.pattern_id), []).append(r.pattern_id)

    sharpe_by_pattern = {r.pattern_id: r.sharpe_annualized for r in results}
    rate_exposure = {
        pattern_id: compute_rate_exposure(pattern_id, series, factor.reindex(series.index))
        for pattern_id, series in daily_by_pattern.items()
    }

    diagnostics: list[BondsMechanismDiagnostic] = []
    blended: dict[str, pd.Series] = {}
    for mechanism, pattern_ids in sorted(by_mechanism.items()):
        streams = [daily_by_pattern[p] for p in pattern_ids if p in daily_by_pattern]
        if not streams:
            continue
        blend = pd.concat(streams, axis=1).mean(axis=1)
        blended[mechanism] = blend

        exposure = compute_rate_exposure(mechanism, blend, factor.reindex(blend.index))
        vols = [float(s.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)) for s in streams]
        diagnostics.append(
            BondsMechanismDiagnostic(
                mechanism=mechanism,
                n_specs_replayed=len(pattern_ids),
                mean_sharpe=float(np.mean([sharpe_by_pattern[p] for p in pattern_ids])),
                realized_book_volatility=float(np.mean(vols)),
                realized_rate_beta=exposure.rate_beta,
                rate_neutralized_sharpe=exposure.rate_neutralized_sharpe,
                alpha_t_stat=exposure.alpha_t_stat,
            )
        )

    correlations: dict[tuple[str, str], float] = {}
    names = sorted(blended)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            joined = pd.concat([blended[a], blended[b]], axis=1).dropna()
            if len(joined) >= 2:
                correlations[(a, b)] = float(joined.iloc[:, 0].corr(joined.iloc[:, 1]))
    return diagnostics, correlations, rate_exposure


def run_bonds_screening(
    start: date = BONDS_COMMON_HISTORY_START,
    end: date | None = None,
    provider: YFinanceProvider | None = None,
    config: CrossSectionalConfig | None = None,
) -> BondsScreeningSummary:
    """THE production entry point for the Bonds family, scoped to exactly
    BONDS_FAMILY's 18 definitions and their own n_trials.

    Universe: the fixed 8-ETF basket BONDS_UNIVERSE, gated by
    cross_sectional.fixed_universe_membership -- NOT the S&P 500
    point-in-time gate, which would make every one of these tickers
    ineligible on every date (see the module docstring's FIXED UNIVERSE
    section, and EmptyEligibleUniverseError).

    Data: BOTH close bases from one fetch (see
    YFinanceProvider.get_total_and_price_return_closes). The total-return
    basis is what every signal and every realized return uses; the
    price-only basis exists so the carry mechanism can observe income
    separately from price change.

    `start` defaults to BONDS_COMMON_HISTORY_START, the verified first date
    on which all eight ETFs are simultaneously priced. Price history is
    padded before it so the longest lookback is warm; formations never occur
    in the padding. Note that at the default start, HYG has no history
    BEFORE the window at all, so its own 252-day signals stay NaN (and it is
    simply not ranked) for roughly the first year -- correct behaviour, and
    the reason the returned diagnostics report each mechanism's replayed
    spec count rather than assuming full participation throughout.

    Returns a BondsScreeningSummary: the results, missing tickers, the
    per-mechanism diagnostics measured from the real return streams
    (realized book volatility, realized rate beta, cross-mechanism
    correlation), and the cost/breakeven disclosure."""
    # date.today() is the LOCAL date. That ambiguity is immaterial here --
    # this is only the exclusive end bound of a price fetch, where being a
    # day either side just includes or omits the most recent bar. It is NOT
    # immaterial in a once-per-day guard that compares a local date against
    # a UTC-derived timestamp, which is a real bug shape this codebase has
    # elsewhere; do not copy this line into one.
    end = end if end is not None else date.today()  # noqa: DTZ011
    provider = provider if provider is not None else YFinanceProvider()
    config = config if config is not None else default_bonds_config()
    config.formation_start = start

    padded_start = start - timedelta(days=BONDS_PRICE_HISTORY_PADDING_CALENDAR_DAYS)
    total_return, price_only, missing = provider.get_total_and_price_return_closes(
        list(BONDS_UNIVERSE), padded_start, end
    )
    if total_return.empty:
        return BondsScreeningSummary(results=[], missing_price_data=missing)
    if missing:
        # Not fatal (the harness ranks whatever is priced), but a missing
        # member of an 8-name basket is a big deal and must not be silent.
        logger.error(
            "Bonds screening: %d of %d universe tickers resolved NO price data (%s). "
            "Every mechanism's cross-section is correspondingly narrower.",
            len(missing),
            len(BONDS_UNIVERSE),
            ", ".join(missing),
        )

    data = CrossSectionalData(close=total_return, price_only_close=price_only)
    membership_fn = fixed_universe_membership(BONDS_UNIVERSE)
    results = screen_cross_sectional_universe(data, BONDS_FAMILY, config, membership_fn)

    # A second, clearly-labelled replay pass purely for diagnostics:
    # screen_cross_sectional_universe returns aggregate results, not each
    # spec's daily series, and the diagnostics and breakeven arithmetic
    # below need the series. Replaying 18 specs over 8 tickers a second time
    # is cheap, and doing it here keeps the shared harness's return type
    # unchanged for every other family.
    daily_by_pattern: dict[str, pd.Series] = {}
    spec_by_id = {s.pattern_id: s for s in BONDS_FAMILY}
    for r in results:
        replay = run_cross_sectional_backtest(data, spec_by_id[r.pattern_id], config, membership_fn)
        if replay.status == "ok":
            daily_by_pattern[r.pattern_id] = replay.daily_returns

    diagnostics, correlations, rate_exposure = _compute_mechanism_diagnostics(
        results, daily_by_pattern, total_return
    )
    return BondsScreeningSummary(
        results=results,
        missing_price_data=missing,
        mechanism_diagnostics=diagnostics,
        mechanism_correlations=correlations,
        rate_exposure=rate_exposure,
        disclosure=build_bonds_disclosure(results, config, daily_by_pattern),
    )


__all__ = [
    "BONDS_COMMON_HISTORY_START",
    "BONDS_COST_BPS",
    "BONDS_FAMILY",
    "BONDS_FINANCING_BPS_PER_YEAR",
    "BONDS_FULL_RANK_FRACTION",
    "BONDS_HOLDING_DAYS",
    "BONDS_LADDER_RANK_FRACTION",
    "BONDS_LOOKBACK_DAYS",
    "BONDS_MIN_NAMES_PER_LEG",
    "BONDS_N_TRIALS",
    "BONDS_SHORT_BORROW_BPS_PER_YEAR",
    "BONDS_UNIVERSE",
    "SPREAD_INSTRUMENTS",
    "TREASURY_LADDER",
    "BondsMechanismDiagnostic",
    "BondsRateExposure",
    "BondsScreeningSummary",
    "annualized_income_yield",
    "build_bonds_disclosure",
    "compute_rate_exposure",
    "default_bonds_config",
    "empirical_duration_betas",
    "rate_factor",
    "run_bonds_screening",
    "signal_curve_butterfly",
    "signal_curve_carry_rolldown",
    "signal_duration_hedged_credit",
]
