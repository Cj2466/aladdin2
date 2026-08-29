"""Rough volatility, used narrowly as a REALIZED-VARIANCE FORECASTING tool.

SCOPE, STATED FIRST BECAUSE THE LITERATURE IS MOSTLY ABOUT SOMETHING ELSE.
The rough-volatility literature exists largely to price options: its
headline result is that a fractional driver with small H reproduces the
observed power-law term structure of at-the-money implied volatility skew
([GJR] Sec. 1.3). THIS PROJECT HAS NO OPTIONS DATA AND NO OPTIONS
INFRASTRUCTURE, so none of that is implemented here and none of it is
claimed. What IS implemented is the one piece that needs nothing but a
price history: [GJR] Sec. 2 (how rough is log-volatility?) and [GJR] Sec. 5
(does that roughness forecast future realized variance better than HAR?).

THE ANSWER THIS MODULE MEASURED, UP FRONT: on this project's real data,
NO. See "REAL-DATA RESULT" below. The rough-volatility forecast does not
beat the HAR baseline here, and the module ships saying so.

SHIPPED OPT-IN, NEVER A DEFAULT. Same convention as hrp_optimizer.py,
rmt_denoising.py, kelly_sizing.py and effective_n_clustering.py: nothing in
this codebase calls this module. No setting selects it; no endpoint exposes
it; no existing code path changes behaviour because it exists. It is
infrastructure for an explicit caller.

=============================================================================
PRIMARY SOURCES — every one of these was fetched and read line-by-line
during this implementation session. Nothing below is quoted from memory.
Equation numbers are the sources' own.

ONE CONVENTION FOR EVERY QUOTE: this file is ASCII, the sources are not.
Greek letters, integrals, subscripts and superscripts are TRANSLITERATED
(sigma, Delta, H, m(q, Delta), Int_0^inf, W^H_t). "Verbatim" means the
WORDS are the source's exactly; the SYMBOLS are rendered.
=============================================================================

  [GJR]  Gatheral, J., T. Jaisson and M. Rosenbaum, "Volatility is rough".
         WHICH VERSION WAS ACTUALLY READ, STATED PRECISELY: the arXiv
         working paper, arXiv:1410.3394v1 [q-fin.ST], dated 13 Oct 2014 on
         the arXiv stamp and "October 14, 2014" on its own title page. The
         full 41-page PDF was downloaded and its text extracted and read
         this session. Every "[GJR] eq. (n)" and every quoted sentence
         below is from THAT version.
         SOURCING LIMIT, STATED PLAINLY: the JOURNAL version — Quantitative
         Finance, Vol. 18, No. 6 (2018), pp. 933-949, DOI
         10.1080/14697688.2017.1393551 — was NOT read. tandfonline.com
         returned HTTP 403 to this session. The 2018 volume/page/DOI above
         come from search-result metadata, not from a fetched paper, and
         are recorded here only so a reader can find the published version;
         no CLAIM in this file rests on them. Between the 2014 preprint and
         the 2017-accepted journal version there were three years of
         revision, so section numbers, table numbers and the exact H
         figures may differ in print. Anywhere this file says "GJR report
         X", it means the 2014 preprint reports X.

  [C09]  Corsi, F., "A Simple Approximate Long-Memory Model of Realized
         Volatility", Journal of Financial Econometrics, 2009, Vol. 7,
         No. 2, pp. 174-196. THE PUBLISHED VERSION was downloaded and read
         this session (the PDF carries the journal's own running header
         "Journal of Financial Econometrics, 2009, Vol. 7, No. 2, 174-196"
         and its per-page Oxford Journals download stamp). This is the
         source of the HAR-RV baseline. [GJR] cite exactly this paper, as
         their ref. [18], where they specify their own HAR comparison.

  [P11]  Patton, A. J., "Volatility forecast comparison using imperfect
         volatility proxies", Journal of Econometrics 160 (2011) 246-256.
         The full 11-page PDF was downloaded from the author's own Duke
         page and read this session. Source of the QLIKE loss function and
         of the reason to prefer it here.

  [D04]  Dieker, T., "Simulation of fractional Brownian motion", CWI /
         University of Twente, revised September 2004 (the author's own
         updated version of his 2002 master's thesis, downloaded from
         columbia.edu/~ad3217/fbm/thesis.pdf). The full 77-page PDF was
         downloaded and read this session. Source of the exact fractional
         Gaussian noise autocovariance and of the Davies-Harte circulant
         embedding algorithm implemented here, step by step.
         [D04] attributes the algorithm to its ref. [19], "R.B. Davies and
         D.S. Harte, Tests for Hurst effect, Biometrika, 74 (1987),
         pp. 95-102", "later simultaneously generalized by" ref. [23],
         "C.R. Dietrich and G.N. Newsam, Fast and exact simulation of
         stationary Gaussian processes through circulant embedding of the
         covariance matrix, SIAM Journal Sci. Comput., 18 (1997),
         pp. 1088-1107", AND ref. [59], Wood and Chan — named here because
         [D04] credits the two jointly and an earlier revision of this file
         dropped the second.
         SOURCING LIMIT: Davies & Harte (1987) and Dietrich & Newsam (1997)
         THEMSELVES WERE NOT READ. Their bibliographic details above are
         transcribed from [D04]'s bibliography, which WAS read. The
         algorithm implemented here is [D04]'s exposition of it.

  [CD23] Cont, R. and P. Das, "Rough volatility: fact or artefact?",
         arXiv:2203.13820v3 [q-fin.ST], 10 Jul 2023 (title page dated
         July 11, 2023). The full 30-page PDF was downloaded and read this
         session. This is the DISSENT, and it is cited here because it
         bears directly on how the H number this module produces should be
         read. It is not a footnote; see "HOW TO READ THE H NUMBER".

  NOT VERIFIED, AND THEREFORE NOT CITED AS READ:

  * Nuzman, C. J. and V. H. Poor, "Linear estimation of self-similar
    processes via Lamperti's transformation", Journal of Applied
    Probability, 37(2):429-452, 2000. This is [GJR]'s ref. [41], and it is
    where [GJR] say the prediction formula eq. (5.1) and the conditional
    variance constant come from ("see Theorem 4.2 of [41]"). Cambridge
    Core returned HTML rather than the PDF to this session, so THEOREM 4.2
    WAS NOT READ. Everything this module implements from eq. (5.1) is
    transcribed from [GJR]'s own printed statement of it, which WAS read.
    Three independent numerical checks were run in place of reading [41],
    and all three are asserted in tests/test_rough_volatility.py:
      - THE STRONGEST ONE: eq. (5.1)'s weights are compared against the
        EXACT best linear predictor of fBm on the discrete daily grid,
        solved from scratch out of fBm's own covariance function
        Cov(W_s, W_t) = 0.5(s^{2H} + t^{2H} - |t-s|^{2H}) — which follows
        from [GJR] eq. (1.1) alone and needs nothing from [41]. At H = 0.14
        the two weight vectors correlate 0.9885-0.9912 and their
        out-of-sample MSE agrees to within 1-2%. A garbled transcription
        would not land there.
      - the kernel of eq. (5.1) integrates to exactly 1 over u in (0, inf),
        i.e. the predictor is a weighted average of the past and reproduces
        a constant series exactly (proved below, and checked numerically);
      - the conditional variance constant c is bracketed against the SAME
        from-scratch covariance. Conditioning on the discrete daily past is
        conditioning on strictly less than [GJR]'s F_t, so the from-scratch
        number must sit just ABOVE c Delta^{2H} and tighten toward it as the
        grid reaches further back. It does, at every H and Delta tested
        (H = 0.1, Delta = 1: c Delta^{2H} = 0.6397 against 0.6960 -> 0.6956;
        H = 0.45, Delta = 1: 0.99208 against 0.99381).
    None of the three proves Theorem 4.2. They do rule out a garbled
    transcription, which is the claim this module actually needs.

    STRENGTHENED BY THE INDEPENDENT VERIFICATION PASS, which pushed the
    third check past a bracket and into a positive confirmation. The
    discrete-past conditional variance converges DOWNWARD onto c Delta^{2H}
    as the grid reaches further back and as Delta grows, so the limit
    identifies c rather than merely bounding it. Solved from the same
    from-scratch covariance with 4000 daily lags:

        H      Delta   (from-scratch) / (c Delta^{2H})
        0.35   20      1.00140
        0.35   60      1.00075
        0.35   120     1.00085
        0.40   60      1.00033
        0.45   20      1.00015
        0.45   60      1.00008

    i.e. [GJR]'s printed c = Gamma(3/2-H)/[Gamma(H+1/2) Gamma(2-2H)] is
    reproduced to within 1e-4 at H = 0.45 by a calculation that uses nothing
    but Cov(W_s, W_t). Both mutants tried fail this: c' above sits at 1.80 /
    0.64 rather than 1.00, and Gamma(3/2-H) -> Gamma(3/2+H) sits at 0.9936
    and does NOT converge to 1 as the grid grows. Theorem 4.2 still was not
    read; its constant has now been checked numerically rather than only
    sanity-bounded.

    ONE EARLIER CLAIM HERE WAS TOO STRONG AND IS CORRECTED. Until an
    adversarial review of this file, the third check was "c collapses to
    c = 1 at H = 1/2", and that was presented as showing the transcription
    is not garbled. It does not: swapping the numerator with one denominator
    factor, c' = Gamma(H+1/2)/[Gamma(3/2-H) Gamma(2-2H)], is ALSO exactly 1
    at H = 1/2, is positive everywhere, and passed the entire test suite.
    The bracket above is what actually excludes it (c' = 1.802 at H = 0.1,
    Delta = 1, which is impossible because it exceeds the discrete-past
    conditional variance 0.6956). c(1/2) = 1 is retained as a necessary
    condition and is labelled as only that.

  * Comte, F. and E. Renault (1998), Fukasawa (2011), Rogers (2019),
    Fukasawa, Takabatake and Westphal (2022), Bennedsen, Lunde and
    Pakkanen (2022), Duchon, Robert and Vargas (2012). None was fetched.
    Every one of them, INCLUDING THE YEARS, is transcribed from a
    bibliography or citation that WAS read this session: Comte & Renault,
    Rogers, Fukasawa et al. and Bennedsen et al. from [CD23]; Fukasawa
    (2011) from [GJR]'s ref. [25]; Duchon, Robert and Vargas (2012) from
    [GJR]'s ref. [21]. They are named nowhere in this module except here.

=============================================================================
1. WHAT "ROUGH" MEANS, AND [GJR]'s ESTIMATOR
=============================================================================

[GJR] Sec. 1.2, on the fractional Brownian motion (W^H_t), verbatim: it "is
a centered self-similar Gaussian process with stationary increments
satisfying for any t in R, Delta >= 0, q > 0:

    E[|W^H_{t+Delta} - W^H_t|^q] = K_q Delta^{qH},          ([GJR] eq. 1.1)

with K_q the moment of order q of the absolute value of a standard Gaussian
variable. For H = 1/2, we retrieve the classical Brownian motion."

That scaling law IS the estimator. [GJR] Sec. 2.1 defines, on a grid of
mesh Delta with N = floor(T/Delta),

    m(q, Delta) = (1/N) sum_{k=1}^{N} |log(sigma_{k Delta})
                                       - log(sigma_{(k-1) Delta})|^q

NOTE THE SCALE: [GJR] write log(sigma), i.e. LOG VOLATILITY, not
log-variance. H is unaffected by the factor of two (scaling the series by a
constant shifts log m by q log 2 and leaves the slope alone) but nu is not,
so estimate_hurst() below documents and enforces the log-volatility
convention.

Their assumption, [GJR] eq. (2.1), is that N^{q s_q} m(q, Delta) -> b_q as
Delta tends to zero. (TRANSCRIPTION NOTE: the PDF's text layer renders this
as the flat string "Nqsqm(q, Delta) -> bq", with the superscript lost. It is
read here as N^{q s_q}, which is the only grouping consistent with the rest
of the section — m(q, Delta) ~ Delta^{q s_q} and Delta = T/N. Flagged
because it is a reading of a mangled superscript, not a clean quote.) They
then note, and this part IS clean in the text layer, "if log(sigma_t) is a
fBM with Hurst parameter H, then for any q >= 0, Equation (2.1) holds in
probability with s_q = H".

The procedure, verbatim from [GJR] Sec. 2.1: "We now proceed to estimate
the smoothness parameter s_q for each q by computing the m(q, Delta) for
different values of Delta and regressing log m(q, Delta) against log Delta.
Note that for a given Delta, several m(q, Delta) can be computed depending
on the starting point. Our final measure of m(q, Delta) is the average of
these values."

And the grid, verbatim from [GJR] Sec. 2.4: "for each index and for
q = 0.5, 1, 1.5, 2, 3, by doing a linear regression of log(m(q, Delta)) on
log(Delta) for Delta = 1, ..., 30, we obtain estimates of zeta_q".

Then, [GJR] Sec. 2.2: "plotting zeta_q against q, we obtain that
zeta_q ~ H q with H equal to 0.125 for the DAX and to 0.082 for the Bund".

ONE RECONSTRUCTION, FLAGGED AS SUCH. [GJR] do not print the arithmetic by
which the single number H is extracted from the five zeta_q. Their Fig. 2.3
and Fig. 2.6 plot zeta_q against the LINE "0.125 x q" / "0.142 x q", which
is a line through the origin, so estimate_hurst() reports the
through-origin least-squares fit H = sum(zeta_q q) / sum(q^2) as its
headline. THIS IS AN INFERENCE FROM THEIR FIGURES, NOT A QUOTE. The
ordinary with-intercept slope is computed too and returned as
`hurst_with_intercept`. On synthetic fBm (30 seeds, 4096 points) the two
readings differ by a mean of 0.0012 at H = 0.1, 0.0025 at 0.3 and 0.0041 at
0.5, never by more than 0.011 — so on data that really is fBm the choice
does not drive any conclusion. ON THE REAL DATA IT DIFFERS BY FAR MORE
(0.2343 vs 0.1896 for SPY), and that gap is itself a diagnostic: see
section 7's "SECOND WARNING SIGN".

[GJR]'s own reported numbers, from the version read: H = 0.125 (DAX),
0.082 (Bund) from one-hour uncertainty-zone integrated variance; H = 0.142
(S&P), 0.139 (NASDAQ) from Oxford-Man 5-minute whole-day realized variance.
Abstract: "log-volatility behaves essentially as a fractional Brownian
motion with Hurst exponent H of order 0.1, at any reasonable time scale."

=============================================================================
2. HOW TO READ THE H NUMBER — TWO BIASES, POINTING OPPOSITE WAYS
=============================================================================

This matters more here than in [GJR], because this project's volatility
proxy is much worse than theirs. Both biases are documented from sources
read this session, and the module refuses to report H without both.

UPWARD BIAS FROM AVERAGING. [GJR] Sec. 2.1, on their own S&P proxy: "Since
these estimates of integrated variance are for the whole trading day, we
expect estimates of the smoothness of the volatility process to be biased
upwards, integration being a regularizing operation." They then measure it,
[GJR] Sec. 3.4: simulating with a true H = 0.14, "When the uncertainty
zones estimator is applied on a one-hour window ... we estimate H = 0.16,
which is close to the true value H = 0.14 ... However, the estimated H is
biased slightly higher at around 0.18" for whole-day realized variance.

DOWNWARD BIAS FROM PROXY NOISE. [CD23] abstract: "even when the
instantaneous volatility has diffusive dynamics with the same roughness as
Brownian motion, the realized volatility exhibits rough behaviour
corresponding to a Hurst exponent significantly smaller than 0.5 ...
irrespective of the roughness of the spot volatility process, realized
volatility always exhibits 'rough' behaviour with an apparent Hurst index
H < 0.5. These results suggest that the origin of the roughness observed in
realized volatility time-series lies in the estimation error rather than
the volatility process itself." Their Sec. 6, on Brownian-driven stochastic
volatility: "the realized volatility has a roughness index ~ 0.3 so
exhibits an 'apparent roughness' which instantaneous volatility does not
have, both in terms of normalized p-th variation statistics and also in
terms of the log-regression method used by Gatheral et al. (2018). Clearly
in these simulation examples this is entirely due to the discretization
error or 'estimation error'."

SO: A SMALL H MEASURED HERE IS NOT EVIDENCE THAT VOLATILITY IS ROUGH. It is
consistent with rough volatility and equally consistent with a Brownian
volatility observed through a noisy proxy. This module estimates H; it does
not adjudicate that question, and the docstring does not pretend to.

=============================================================================
3. THE FORECAST — [GJR] eq. (5.1)
=============================================================================

[GJR] Sec. 5.1, verbatim: "The key formula on which our prediction method
is based is the following one:

    E[W^H_{t+Delta} | F_t] = (cos(H pi)/pi) Delta^{H + 1/2}
                             Int_{-inf}^{t} W^H_s
                             / [(t - s + Delta)(t - s)^{H + 1/2}] ds,

where W^H is a fBM with H < 1/2 and F_t the filtration it generates, see
Theorem 4.2 of [41]." (That is [GJR]'s ref. [41] = Nuzman & Poor, NOT read
this session — see the sourcing block above.)

"By construction, over any reasonable time scale of interest, as formalized
in Corollary 3.1, we may approximate the fOU volatility process in the RFSV
model as log sigma^2_t ~ 2 nu W^H_t + C for some constants nu and C. Our
prediction formula for log-variance then follows:

    E[log sigma^2_{t+Delta} | F_t] = (cos(H pi)/pi) Delta^{H + 1/2}
        Int_{-inf}^{t} log sigma^2_s
        / [(t - s + Delta)(t - s)^{H + 1/2}] ds"       ([GJR] eq. 5.1)

with their footnote 11: "The constants 2 nu and C cancel when deriving the
expression."

[GJR] then give the change of variable this module actually implements,
verbatim: "Note also that our prediction formula may be rewritten as

    E[log(sigma^2_{t+Delta}) | F_t] = (cos(H pi)/pi)
        Int_0^{+inf} log(sigma^2_{t - Delta u}) / [(u + 1) u^{H + 1/2}] du."

THE KERNEL HAS MASS EXACTLY ONE. This is not stated in [GJR]; it is derived
here and it is what makes the discretisation below well posed. With
a = H + 1/2 in (0, 1),

    Int_0^inf u^{-a} / (1 + u) du = pi / sin(pi a) = pi / cos(pi H),

so the prefactor cos(H pi)/pi normalises it to 1 exactly. Consequence: the
predictor is a WEIGHTED AVERAGE of past log-variance, it reproduces a
constant series exactly, and truncating the tail at a finite number of lags
is a mass deficit that can be corrected by renormalising. Checked
numerically (scipy.integrate.quad, H in {0.02, 0.1, 0.3, 0.49}: total mass
1.0000000000 in every case) and asserted in the tests.

DISCRETISATION, DECLARED AS THIS MODULE'S CHOICE AND NOT [GJR]'s. [GJR] say
only "its approximation through a Riemann sum". With daily observations,
observation i days back sits at u = i/Delta, so this module gives it the
EXACT kernel mass of the cell u in [(i - 0.5)/Delta, (i + 0.5)/Delta], with
cell 0 being [0, 0.5/Delta] to absorb the integrable singularity at u = 0.
That is a piecewise-constant (nearest-neighbour) approximation of
log sigma^2_{t - Delta u}, and it is exact for a constant series. The cell
masses are computed in closed form, not quadrature:

    Int_0^x u^{-a}/(1 + u) du = x^{1-a}/(1-a) * 2F1(1, 1-a; 2-a; -x)

which was verified against scipy.integrate.quad to 1e-10 or better at
H in {0.02, 0.1, 0.3, 0.49} and x in {0.001, 0.5, 1, 10, 100, 499.5, 5000}
(asserted in the tests).

VARIANCE, NOT LOG-VARIANCE. [GJR] Sec. 5.2, verbatim: "In [41], it is shown
that W^H_{t+Delta} is conditionally Gaussian with conditional variance

    Var[W^H_{t+Delta} | F_t] = c Delta^{2H}   with
    c = Gamma(3/2 - H) / [Gamma(H + 1/2) Gamma(2 - 2H)],

Thus, we obtain the following natural form for the RFSV predictor of the
variance:

    sigmahat^2_{t+Delta} = exp{ loghat sigma^2_{t+Delta} + 2 c nu^2 Delta^{2H} }

where loghat(sigma^2_{t+Delta}) is the estimator from Section 5.1 and nu^2
is estimated as the exponential of the intercept in the linear regression
of log(m(2, Delta)) on log(Delta)."

FOUR SELF-CHECKS ON THAT TRANSCRIPTION, all asserted in the tests, all
derived here rather than quoted:
  * THE ONE WITH REAL POWER: c is bracketed against fBm's own covariance,
    solved from scratch. Var[W^H_{t+Delta} | discrete daily past] is an
    upper bound on Var[.. | F_t] = c Delta^{2H}, because the daily grid is
    coarser than the continuous filtration, and it tightens as the grid
    reaches further back. Measured, 200 -> 600 lags: at H = 0.1, Delta = 1,
    c Delta^{2H} = 0.63970 against 0.69600 -> 0.69559; at H = 0.45,
    Delta = 1, 0.99208 against 0.99381 -> 0.99380. Both ends have to hold at
    once, so no wrong constant survives.
  * At H = 1/2, c = Gamma(1)/[Gamma(1) Gamma(1)] = 1, so Var = Delta. That
    is the right conditional variance for ordinary Brownian motion. THIS IS
    A NECESSARY CONDITION AND NOTHING MORE — the swapped form
    Gamma(H+1/2)/[Gamma(3/2-H) Gamma(2-2H)] satisfies it too. See the
    sourcing block; this file used to over-read it.
  * The exp{...} form is exactly the lognormal mean correction: with
    log sigma^2 ~ 2 nu W^H + C, Var[log sigma^2_{t+Delta}|F_t] =
    4 nu^2 c Delta^{2H}, and E[exp(X)] = exp(mean + var/2) contributes
    2 c nu^2 Delta^{2H}. [GJR]'s printed constant is internally consistent.
  * nu^2 = exp(intercept) is consistent ONLY on the log-VOLATILITY scale:
    with log sigma_t ~ nu W^H_t + const, m(2, Delta) = nu^2 Delta^{2H}, so
    the intercept is log nu^2. This is why estimate_hurst() insists on
    log-volatility input. On log-variance the same line would return
    4 nu^2.

=============================================================================
4. THE BASELINE — HAR
=============================================================================

[C09] is the source and it is unambiguous. [C09] eq. (3) defines daily
realized volatility as the square root of the sum of intraday squared
returns; [C09] eq. (4) defines the multi-period aggregates as SIMPLE
AVERAGES of the daily ones, verbatim: "these multiperiod volatilities are
normalized sums of the one-period realized volatilities (i.e., a simple
average of the daily quantities). For example, in our notation, a weekly
realized volatility at time t is given by the average

    RV^(w)_t = (1/5) ( RV^(d)_t + RV^(d)_{t-1d} + ... + RV^(d)_{t-4d} )."

and [C09] eq. (8), the model itself:

    RV^(d)_{t+1d} = c + beta^(d) RV^(d)_t + beta^(w) RV^(w)_t
                      + beta^(m) RV^(m)_t + omega_{t+1d}

"it could then be labeled as HAR(3)-RV". [C09]'s monthly aggregate is 22
days: "employs monthly realized volatility (which corresponds to 22 working
days)". Estimation is OLS.

[GJR] Sec. 5.1 restate HAR on the LOG-VARIANCE scale, which is the scale
their eq. (5.1) predictor lives on, with 5 and 20 rather than 5 and 22:

    loghat(sigma^2_{t+Delta}) = K^Delta_0 + C^Delta_0 log(sigma^2_t)
        + C^Delta_5  (1/5)  sum_{i=0}^{5}  log(sigma^2_{t-i})
        + C^Delta_20 (1/20) sum_{i=0}^{20} log(sigma^2_{t-i})

AN ERRATUM IN [GJR], FLAGGED RATHER THAN SILENTLY FIXED. As printed, those
sums run i = 0..5 (six terms) over 5, and i = 0..20 (twenty-one terms) over
20. That is inconsistent with the "simple average" definition it inherits
from [C09] eq. (4), which is unambiguous. This module follows [C09]:
`har_features` averages exactly `lag` terms. Both the 1/5/20 lags of [GJR]
and the 1/5/22 lags of [C09] are runnable; the real-data run below reports
1/5/20 as headline and 1/5/22 as a declared variant, and they differ by
less than 0.001 in the loss ratio.

WHY HAR IS THE FAIR BASELINE AND NOT A STRAW MAN: [GJR] themselves chose
it, and they concede it is the one to beat — [GJR] Sec. 5.2, verbatim: "it
is worth noting that the HAR forecast is already visibly superior to the AR
forecast."

=============================================================================
5. THE LOSS FUNCTIONS
=============================================================================

PRIMARY, on the log-variance scale, is [GJR]'s own ratio P, so the numbers
below land on the same scale as their Table 5.1. [GJR] Sec. 5.1, verbatim:
"We then assess the quality of the various forecasts by computing the ratio
P between the mean squared error of our predictor and the (approximate)
variance of the log-variance:

    P = sum_{k=500}^{N-Delta} (log(sigma^2_{k+Delta}) - loghat(sigma^2_{k+Delta}))^2
        / sum_{k=500}^{N-Delta} (log(sigma^2_{k+Delta}) - E[log(sigma^2_{t+Delta})])^2

where E[log(sigma^2_{t+Delta})] denotes the empirical mean of the
log-variance over the whole time period." P = 1 is "no better than the
unconditional mean"; lower is better.

SECONDARY, on the variance scale, is QLIKE. [P11] eq. (6), verbatim:

    QLIKE: L(sigmahat^2, h) = log h + sigmahat^2 / h

where, in [P11]'s notation, h is the FORECAST and sigmahat^2 is the
volatility PROXY (his robustness condition is stated "for any sigmahat^2_t
s.t. E[sigmahat^2_t | F_{t-1}] = sigma^2_t").

QLIKE rather than MSE is [P11]'s own recommendation, and the reason is
exactly this module's situation — a noisy proxy. [P11] Prop. 2(ii): "The
'QLIKE' loss function is the only robust loss function satisfying
assumptions A1-A5 that depends solely on the standardised forecast error."
And: "Patton and Sheppard (2009) find that the power of DMW tests using
QLIKE loss are higher than those using MSE loss, providing further
motivation for using QLIKE rather than MSE in volatility forecasting
applications." Variance-scale RMSE is reported alongside as the familiar
number, explicitly labelled non-robust.

=============================================================================
6. SYNTHETIC GROUND TRUTH — RUN THIS SESSION
=============================================================================

The estimator was validated against a generator with a KNOWN H before it
was pointed at any market data.

EVERY NUMBER IN THIS SECTION IS REPRODUCIBLE FROM THE SEEDS NAMED, and all
but one column comes from the SHIPPED MODULE CODE rather than a prototype.
The exception, flagged so the claim is exact: the "exact-optimal" yardstick
is NOT module code — it is _exact_fbm_predictor_weights and
_exact_fbm_conditional_variance in tests/test_rough_volatility.py, which
need a known H and a full covariance solve and so deliberately do not ship.
Wherever a figure below involves that yardstick, the construction it was
computed with is named, because the numbers move in the third decimal with
the lag count.

GENERATOR. Davies-Harte circulant embedding, [D04] Sec. 2.1.3, implemented
from its eq. (2.9)-(2.13) step by step (see simulate_fgn). Its correctness
was checked against [D04] eq. (1.7), the exact fGn autocovariance
gamma(k) = 0.5(|k-1|^2H - 2|k|^2H + |k+1|^2H): over 600 paths of length
1024 (seed 20260829), the largest gap between empirical and theoretical
autocovariance across lags 0..5 was 0.0033 (H = 0.1), 0.0025 (0.3),
0.0023 (0.5), 0.0022 (0.7) — i.e. Monte Carlo error, not a structural
mismatch. Asserted in the tests.

H-RECOVERY, 30 seeds per H (seeds 1000..1029), paths of 4096 points, the
estimator run on the cumulated fBm exactly as it is run on real
log-volatility:

    true H     mean H_hat     sd      bias
    0.1        0.1005       0.0088   +0.0005
    0.2        0.2003       0.0130   +0.0003
    0.3        0.2999       0.0155   -0.0001
    0.5        0.4989       0.0168   -0.0011
    0.7        0.6965       0.0188   -0.0035

The estimator is unbiased to within a fifth of its own sampling standard
deviation across the whole range, including at the H ~ 0.1 that the whole
question turns on. IT IS NOT THE H ESTIMATOR THAT IS PRODUCING SMALL
NUMBERS ON REAL DATA. (Independently re-run on 30 fresh seeds, 90000..90029:
mean H_hat 0.1007 / 0.2007 / 0.3005 / 0.4993 / 0.6965 at true H = 0.1 / 0.2 /
0.3 / 0.5 / 0.7 — the same picture on seeds this module never saw.)

ON A 500-POINT WINDOW, which is what the rolling study uses, the sd widens
to 0.022 at H = 0.1, 0.041 at H = 0.3 and 0.049 at H = 0.5, and a small
NEGATIVE bias appears. CORRECTED BY THE INDEPENDENT VERIFICATION PASS: an
earlier version of this paragraph put that bias at -0.005 (H = 0.1) to
-0.011 (H = 0.5). Those were honest readings of a 60-seed sample, but 60
seeds cannot resolve a bias this small — the standard error of the mean is
0.003 to 0.007, so each figure was a 1-2 s.e. draw. Re-measured over
2000-3000 fresh seeds per H:

    true H     bias      s.e.      sd of H_hat
    0.1        -0.0013   0.0004    0.0224
    0.15       -0.0023   0.0005    0.0287
    0.2        -0.0031   0.0006    0.0334
    0.3        -0.0058   0.0007    0.0407
    0.5        -0.0085   0.0009    0.0493

The qualitative claim survives and the overstated magnitudes do not: the
bias IS negative and DOES grow with H, but at the H ~ 0.17-0.24 the real
data actually lands on, it is about -0.003, not -0.005 to -0.011. This
still matters for reading section 7 in ONE direction only — it makes the
real-data H a touch too SMALL, so correcting for it moves the estimate
further from [GJR]'s 0.1, not closer — but the correction is ~0.003 on a
reported 0.2025, i.e. immaterial either way.

A CONTROL THE FIRST PASS DID NOT RUN, added by the independent verification
because it quantifies section 7's central caveat rather than just asserting
it. Feed IID GAUSSIAN RETURNS — constant spot volatility, no volatility
dynamics of any kind, nothing rough anywhere — through this module's own
w-day realized-variance proxy at the real data's length (n = 4863, 20 seeds)
and estimate H off the result:

    proxy window   H on IID returns   H on the real ETFs
    1 day          0.0003             0.0100
    2 days         0.0305             0.0558
    3 days         0.0661             0.1088
    5 days         0.1366             0.2025
    10 days        0.2769             0.3749
    21 days        0.4424             0.5534
    42 days        0.4842             0.6336

At the headline 5-day window, TWO THIRDS of the measured H (0.1366 of
0.2025) is produced by the proxy alone on data with no volatility process
at all. The real series does sit above the IID control at every window, so
there is signal there — genuine volatility clustering pushes H up — but the
level of H is mostly an artefact of the smoothing, exactly as [CD23]
predict. This is the quantitative version of section 7's "H measures the
proxy at least as much as it measures the volatility".

PREDICTOR, CHECKED AGAINST TWO INDEPENDENT YARDSTICKS, because its own
source could not be fetched.

First, against a ground truth computable from scratch: the EXACT best
linear predictor of fBm on the discrete daily grid, solved directly from
Cov(W_s, W_t) = 0.5(s^{2H} + t^{2H} - |t-s|^{2H}), which follows from
[GJR] eq. (1.1) and needs nothing from Nuzman & Poor. At H = 0.14 with 200
lags, 6 seeds:

    D     weight correlation    MSE(eq 5.1) / MSE(exact optimum)
    1     0.9885                1.0219
    5     0.9909                1.0096
    20    0.9912                1.0109

Within 1-2% of the optimum. The residual is discretisation, largest at
D = 1 where the daily grid spreads the u^{-(H+1/2)} singularity over the
widest range of u.

Second, against the actual HAR baseline on data that really is rough.
12 seeds (9000..9011), series of 2,000 and 6,000 points, rolling window
500, true H = 0.14 handed to the predictor, mean of [GJR]'s P ratio:

    D    RFSV/HAR          RFSV wins    HAR / exact-optimal
    1    1.0035 / 0.9994   3 and 7 of 12    1.0198 / 1.0204
    5    0.9712 / 0.9706   12 and 12 of 12  1.0354 / 1.0347
    20   0.9193 / 0.9184   12 and 12 of 12  1.0902 / 1.0861
    (the two figures are the n = 2,000 and n = 6,000 runs; the third column
     uses _exact_fbm_predictor_weights at 200 lags with its default remote
     origin, which is the same construction the tests assert against — at
     500 lags the same column reads 1.0199/1.0210, 1.0359/1.0369,
     1.0923/1.0940, and that spread is why the construction is named.
     INDEPENDENTLY REPRODUCED: 1.0198/1.0203, 1.0351/1.0344, 1.0893/1.0850,
     which matches only if the yardstick's weights are RENORMALISED to sum
     to 1 — see the note under the next paragraph, which is where the
     unnormalised version had done real damage. All three columns are means
     of per-seed ratios, not ratios of means; that convention reproduces the
     RFSV/HAR column to the last digit.)

So when the data IS a rough fBm, eq. (5.1) beats a rolling HAR by ~2.9% at
five days and ~8.1% at twenty — [GJR] Sec. 5.1's own "especially at longer
horizons" pattern — and it lands essentially ON the exact optimum: at
D = 20, n = 2,000, mean P is 0.64387 for eq. (5.1) against 0.64392 for the
200-lag exact predictor, a gap of 0.008%. At one day it merely ties, because
the ~2% discretisation penalty is the same size as its advantage over a
four-parameter fitted regression.

    THE OPTIMUM FIGURE IN THIS PARAGRAPH HAS NOW BEEN WRONG TWICE, AND THE
    SECOND VERIFICATION PASS FOUND THE REASON. It first read 0.64384, which
    review could not reproduce; that was replaced with 0.64335, which does
    not reproduce either. The independent pass measured, at D = 20, n =
    2,000, 12 seeds, using _exact_fbm_predictor_weights exactly as the tests
    call it:

        lags   sum(w)     P (weights as-is)   P (weights renormalised)
        100    0.993901   0.65285             0.64806
        200    0.995178   0.64780             0.64392
        500    0.996483   0.64384             0.64095

    THE CAUSE: the exact best-linear-predictor weights DO NOT SUM TO 1 on a
    truncated grid, while eq. (5.1)'s normalised weights do, and this
    synthetic series has mean -9. Applying unnormalised weights to it
    injects a constant bias of C * (sum(w) - 1) — about 0.04 at 200 lags —
    which is what made the "optimum" look like it improved with lag count.
    Most of that apparent improvement is sum(w) creeping toward 1, not
    better prediction. (0.64384 was in fact reproducible, at 500 lags rather
    than the 200 the text claimed; 0.64335 matches no lag count.)

    THE APPLES-TO-APPLES COMPARISON is therefore the renormalised column,
    since it is the only one that holds the predictors to the same
    constraint eq. (5.1) satisfies by construction. On it eq. (5.1) scores
    0.64387 against the 200-lag optimum's 0.64392 — a dead heat, and if
    anything eq. (5.1) is a hair ahead, which is a truncation artefact of
    the yardstick rather than a real edge. The qualitative claim was always
    right and is unchanged: eq. (5.1) is at the optimum to within noise.

THIS MATTERS FOR READING SECTION 7. The machinery is not broken and it is
not underpowered: on rough data it finds the edge the paper says is there.
When it fails below, that is information about the data.

=============================================================================
7. REAL-DATA RESULT — THE HONEST NEGATIVE
=============================================================================

WHAT WAS PRE-DECLARED, BEFORE ANY FORECAST WAS COMPUTED. Universe: the same
12 cross-asset ETFs kelly_sizing.py uses for its real-data check (SPY QQQ
IWM EFA EEM TLT IEF LQD HYG GLD DBC VNQ). Sample: daily adjusted closes via
YFinanceProvider.get_price_history, 2007-05-01 to 2026-08-28, 4864 rows x
12 columns, zero unresolved tickers. Proxy: 5-day rolling realized variance
from daily log returns. Horizons 1, 5, 20 days. Rolling window 500
([GJR]'s own). Baseline HAR(1,5,20) log-variance, refit by OLS every
origin. Primary metric [GJR]'s P; secondary QLIKE. Decision rule fixed in
advance: "rough volatility beats HAR" only if RFSV wins on >= 8 of 12
assets AND the cross-asset mean loss ratio is < 1. See section 8 for the
one thing that could not be pre-declared.

REAL H, ESTIMATED HERE. On log-volatility from the headline 5-day proxy,
cross-asset mean H = 0.2025, ranging from 0.1685 (GLD) to 0.2353 (HYG).
SPY = 0.2343, QQQ = 0.2229, TLT = 0.1718, IEF = 0.1796, LQD = 0.2064,
DBC = 0.1776. Every one of the twelve is far below 1/2 and none is close
to it: in 52,296 rolling 500-day windows across the twelve assets, ZERO
produced H >= 0.5 (rolling mean H = 0.1972, within-asset sd 0.0439).

COMPARISON WITH [GJR]'s ~0.1: DIRECTIONALLY YES, NUMERICALLY ABOUT DOUBLE,
AND THE GAP IS EXPLAINED BY THE PROXY RATHER THAN BY THE MARKET. 0.20 is
unambiguously in "rough" territory (H << 1/2) and in the same league as
their 0.082-0.142. It is not the same number. The reason is section 2's
upward bias, and it is enormous here — H is almost entirely a function of
how much the proxy is smoothed:

    proxy window     cross-asset mean H
    1 day            0.0101   (see the caveat below — not a clean number)
    5 days (headline) 0.2025
    21 days          0.5534

ONE DATA-HANDLING CHOICE INSIDE THAT TABLE, DECLARED BECAUSE IT IS INVISIBLE
OTHERWISE. At w = 1, RV_t = r_t^2, which is exactly zero on any day the
close is unchanged; log(RV) is then undefined. The run DROPS those days
(9 on IWM up to 82 on DBC, out of 4,863), which splices non-adjacent days
together and is not a neutral operation on a scaling estimator. Replacing
them instead with the smallest positive RV, keeping the series at full
length, gives a cross-asset mean of 0.0080 rather than 0.0101. Both are
"indistinguishable from zero" for the purposes of the argument here, so the
choice does not change what this table is used for — but the 1-day row is
the only one affected, and it should not be quoted as a precise figure.
w = 5 and w = 21 drop nothing at all, so the headline 0.2025 and the 0.5534
are clean.

That table is the single most important thing in this file. Sliding the
averaging window from 1 to 21 days moves the estimate from "rougher than
anything in the literature" to "indistinguishable from ordinary Brownian
motion", on the same prices. [CD23]'s thesis is not a caveat here, it is
the dominant effect: on daily closes, H measures the proxy at least as
much as it measures the volatility. This module reports 0.2025 as ITS
number for ITS proxy and makes no claim about the true roughness of
volatility.

A SECOND WARNING SIGN, REPORTED BECAUSE IT CUTS AGAINST THE MODEL. [GJR]
Sec. 2.2 record that on their data "the points essentially lie on a
straight line" and "the smoothness parameter s_q does not seem to depend
on q". NEITHER HOLDS HERE. The worst per-q R^2 of log m(q, Delta) against
log Delta runs 0.68 (TLT) to 0.85 (SPY), not the ~1 their figures show.
And zeta_q / q, which should be the constant H, falls monotonically for
every asset — SPY: 0.323, 0.290, 0.264, 0.244, 0.214 at q = 0.5, 1, 1.5,
2, 3. So the single-H fBm scaling that licenses reading zeta_q as "H q"
does not describe this series. That is also why the through-origin H
(0.2343 for SPY) and the with-intercept slope (0.1896) disagree by more
here than they ever do on synthetic fBm.

FORECAST COMPARISON, strictly out of sample, 12 assets x ~4,350 origins
per horizon, cross-asset mean of [GJR]'s P ratio (LOWER IS BETTER; 1.0 is
the unconditional mean):

    D    RFSV     HAR      last     RFSV/HAR   RFSV wins   [GJR] Table 5.1
                                                            (SPX, for scale)
    1    0.2347   0.2073   0.2250   1.132      0 of 12      HAR .314 RFSV .313
    5    0.7599   0.7105   1.0143   1.069      0 of 12      HAR .437 RFSV .426
    20   0.8847   0.8725   1.2726   1.014      3 of 12      HAR .656 RFSV .606

READ THE D = 1 ROW WITH THIS IN MIND — THE TARGET IS 80% ALREADY OBSERVED.
The proxy is a 5-day rolling variance, so RV_{t+1} shares FOUR of its five
squared returns with RV_t. Measured on SPY: corr(x_t, x_{t+1}) = 0.915,
against 0.613 at Delta = 5 and 0.434 at Delta = 20. [GJR]'s whole-day
realized variance has no such overlap, so the [GJR] column above is NOT a
like-for-like comparison at Delta = 1 and is labelled "for scale" for that
reason; most of the drop from P = 0.71 at Delta = 5 to P = 0.21 at
Delta = 1 is the overlap, not skill. The overlap also makes the last-value
forecast nearly unbeatable at Delta = 1, which is the right way to read
point 2 below. At Delta = 5 and Delta = 20 the target and the last observed
value share no returns at all, so those rows are clean.

QLIKE ([P11] eq. 6), variance scale, cross-asset mean (LOWER IS BETTER):

    D    RFSV      HAR       last      RFSV wins
    1    -8.8176   -8.8260   -8.8033   1 of 12
    5    -8.4029   -8.4308   -8.0990   1 of 12
    20   -8.0175   -8.0446   -7.4545   2 of 12

THE ONE METRIC ON WHICH ROUGH VOLATILITY LOOKS GOOD, REPORTED IN FULL
BECAUSE IT IS THE RESULT THAT WOULD BE MOST TEMPTING TO OMIT. Variance-scale
RMSE (x 1e6, LOWER IS BETTER) was pre-declared as the third, non-robust
metric, and it disagrees with the other two:

    D    RFSV      HAR       last      RFSV beats HAR on
    1    112.51    113.00     92.26    7 of 12
    5    215.45    228.24    241.96    12 of 12
    20   246.85    246.41    315.89    5 of 12

Read literally, RFSV wins outright at D = 5 and edges ahead at D = 1. THIS
IS REPORTED, NOT ACTED ON, AND THE REASON WAS FIXED IN ADVANCE RATHER THAN
AFTER SEEING IT. The pre-declared hierarchy is P first, QLIKE second, RMSE
"alongside, labelled non-robust" — and non-robust is exactly what [P11] is
about: with a noisy proxy, variance-scale MSE can rank forecasts wrongly,
which is why he derives QLIKE and why he quotes the finding that "the power
of DMW tests using QLIKE loss are higher than those using MSE loss". The
tell that his warning is live here rather than theoretical: at D = 1 the
LAST-VALUE forecast has the best RMSE of the three (92.26) while having the
worst QLIKE, which is the signature of a handful of extreme-variance days
dominating a squared-error average. Anyone who wants to argue rough
volatility won on this data has to argue it on the non-robust metric, and
has to explain why last-value also beats both models on it.

VERDICT AGAINST THE PRE-DECLARED RULE: FAILS AT EVERY HORIZON. The rule
required >= 8 of 12 wins AND a mean ratio below 1. RFSV got 0, 0 and 3
wins and ratios of 1.132, 1.069 and 1.014. The two metrics the rule rests
on — P and QLIKE — agree (the third, non-robust one does not; see the
paragraph above, which is why the hierarchy was fixed in advance). So does
the [C09] 1/5/22 lag variant (HAR mean P 0.2073 / 0.7106 / 0.8723, i.e.
indistinguishable from 1/5/20). Running it [GJR]'s own way, with H fitted
once on the whole sample — which peeks — does not rescue it either:
0.2334 / 0.7607 / 0.8826, ratios 1.125 / 1.070 / 1.011. THE ROUGH-VOLATILITY
FORECAST DOES NOT BEAT HAR ON THIS PROJECT'S DATA. That is the result.

THREE THINGS WORTH KEEPING FROM A NEGATIVE:

  1. The gap CLOSES with horizon — 13.2%, 6.9%, 1.4% — which is the same
     direction [GJR] report ("especially at longer horizons"). It simply
     never crosses over within 20 days on daily data. Their crossover was
     already visible at D = 1 on 5-minute data.
  2. At D = 1, RFSV loses even to the LAST-VALUE forecast — 0.2347 against
     0.2250 on the mean, and on 12 assets out of 12 individually. (It does
     win there at D = 5 and D = 20, by 25% and 30%.) THE OBVIOUS READING OF
     THIS IS THE WRONG ONE, so it is spelled out: this is NOT mainly
     evidence that the kernel's long tail hurts. With a 5-day proxy the
     D = 1 target is four-fifths observed at the origin (see the note under
     the table), so last-value is close to the best any forecast can do
     there, and a smooth long-memory kernel that spreads weight over the
     past is structurally disadvantaged by the proxy's construction rather
     than by anything about volatility. Section 6 shows the same D = 1 tie
     against a fitted HAR on synthetic data that has NO overlap, where the
     cause is the ~2% discretisation penalty instead. Two mechanisms, both
     unfavourable at D = 1, and this data cannot separate them.
  3. HAR is not a straw man here. It beat the unconditional mean by a wide
     margin at every horizon (P of 0.21 / 0.71 / 0.87) and beat last-value
     everywhere. The negative is "rough volatility did not add anything",
     not "nothing worked".

WHY, MOST LIKELY, AND STATED AS A HYPOTHESIS RATHER THAN A FINDING: the
synthetic tests in section 6 show the predictor DOES beat HAR by 3-8% when
the data is genuinely a rough fBm with the H it is given. Here it does not,
and the diagnostics above say the series is not a single-H fBm (R^2 0.68-
0.85, zeta_q/q falling with q). Section 6 also shows the D = 1 tie is
structural. Neither of those is tested against an alternative model, so
this paragraph is a conjecture and is labelled one.

=============================================================================
8. WHAT THIS MODULE DOES NOT ESTABLISH
=============================================================================

* It does not show volatility is rough. See section 2: with this proxy, a
  small H is exactly what [CD23] predict you would measure even if it were
  not.
* It does not refute [GJR]. Their result is on 5-minute realized variance;
  this is daily closes. A negative here is evidence about DAILY-DATA
  forecasting, not about their claim.
* It does not price anything. No options, no implied volatility, no skew.
* One thing could not be pre-declared honestly: the price data was
  downloaded before the pre-registration text was written. Nothing was
  computed on it first — at freeze time the only facts known about it were
  its shape (4864, 12) and its date span. The pre-declared design is
  reproduced at the top of tests/test_rough_volatility.py as a CONDENSATION,
  not a verbatim copy: every choice the decision rule depends on is there,
  but the frozen text is about twice that length and that header names the
  clauses it drops. It also records the one measured deviation from the
  frozen design — m(q, Delta) was pooled across offsets rather than averaged
  per offset, worth less than 1e-4 in H on every one of the twelve series.
  (Earlier revisions of this file and of that header claimed "preserved
  verbatim" and "no clause dropped or added". Both were false and both are
  corrected; the frozen original is unedited in the run's scratch directory.)

PURE FUNCTIONS. Nothing here reads a database, touches the network, or
mutates an input.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.special import gamma as gamma_fn
from scipy.special import hyp2f1

# --------------------------------------------------------------------------
# Defaults, all traceable to a source quoted in the docstring.
# --------------------------------------------------------------------------

#: [GJR] Sec. 2.4: "for q = 0.5, 1, 1.5, 2, 3".
DEFAULT_Q_VALUES: tuple[float, ...] = (0.5, 1.0, 1.5, 2.0, 3.0)

#: [GJR] Sec. 2.4: "for Delta = 1, ..., 30".
DEFAULT_MAX_LAG: int = 30

#: [GJR] Sec. 5.1: "a rolling time window of 500 days". PRECISE PROVENANCE:
#: that clause is in their AR sentence ("We estimate AR coefficients using
#: the R stats library on a rolling time window of 500 days"); for HAR they
#: say only "we use standard linear regression to estimate the coefficients
#: as explained in [18]". The reading that 500 is the study-wide window is
#: corroborated by their P formula, whose sums run from k = 500.
DEFAULT_ROLLING_WINDOW: int = 500

#: Truncation of the eq. (5.1) kernel. This module's choice, not [GJR]'s;
#: the tail mass beyond it is redistributed by renormalisation.
DEFAULT_N_LAGS: int = 500

#: [GJR] Sec. 5.1's HAR lags. [C09]'s own monthly aggregate is 22.
GJR_HAR_LAGS: tuple[int, ...] = (1, 5, 20)
CORSI_HAR_LAGS: tuple[int, ...] = (1, 5, 22)

#: [GJR] Sec. 5.1: "1, 5 and 20 days ahead (Delta = 1, 5, 20)".
DEFAULT_HORIZONS: tuple[int, ...] = (1, 5, 20)

#: Below this the Davies-Harte circulant is degenerate; above 1 fBm is not
#: defined. [GJR] Sec. 1.2: "The fBM (W^H_t) with Hurst parameter H in (0, 1)".
_MIN_HURST = 1e-6
_MAX_HURST = 1.0 - 1e-6


# ==========================================================================
# 1. Fractional Brownian motion — synthetic ground truth
# ==========================================================================


def fgn_autocovariance(n: int, hurst: float) -> np.ndarray:
    """Exact autocovariance of unit-variance fractional Gaussian noise.

    [D04] eq. (1.7):
        gamma(k) = 0.5 * (|k-1|^{2H} - 2|k|^{2H} + |k+1|^{2H}), k in Z.

    Returns gamma(0), ..., gamma(n-1). gamma(0) == 1 for every H, and every
    gamma(k) for k >= 1 is zero at H = 1/2 ([D04]: "If H = 1/2, all the
    covariances are 0 ... this implies independence").
    """
    _validate_hurst(hurst)
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    k = np.arange(n, dtype=float)
    two_h = 2.0 * hurst
    return 0.5 * (
        np.abs(k - 1.0) ** two_h - 2.0 * np.abs(k) ** two_h + np.abs(k + 1.0) ** two_h
    )


def simulate_fgn(n: int, hurst: float, rng: np.random.Generator) -> np.ndarray:
    """Exact fractional Gaussian noise via Davies-Harte circulant embedding.

    [D04] Sec. 2.1.3, implemented from its own equations:

      * eq. (2.9): embed the n x n covariance Toeplitz matrix in a circulant
        C of size 2n whose first row is
            gamma(0), ..., gamma(n-1), [slot], gamma(n-1), ..., gamma(1).
        [D04] fills [slot] with 0 in the displayed matrix but then says
        "When gamma(.) is the covariance function of fractional Gaussian
        noise and the zeros in the matrix are replaced by gamma(N), the
        matrix is positive definite". This uses gamma(n), the version [D04]
        states is positive definite.
      * eq. (2.10): the eigenvalues are the DFT of that first row. Real and
        positive because C is symmetric positive definite.
      * eq. (2.13): the sample is the FFT of
            w_k = sqrt(lambda_k / 2n) V1_k                       k = 0
                  sqrt(lambda_k / 4n) (V1_k + i V2_k)            k = 1..n-1
                  sqrt(lambda_k / 2n) V1_k                       k = n
                  sqrt(lambda_k / 4n) (V1_{2n-k} - i V2_{2n-k})  k = n+1..2n-1
        with V1, V2 i.i.d. standard normal.
      * "A sample of fractional Gaussian noise is obtained by taking the
        first N elements of Z."

    EXACT, not approximate: the output's covariance is fgn_autocovariance
    to machine precision, not asymptotically. Cost is O(n log n).

    Returns a length-n array with unit variance and autocovariance
    fgn_autocovariance(., hurst).
    """
    _validate_hurst(hurst)
    if n < 2:
        raise ValueError(f"n must be >= 2, got {n}")

    g = fgn_autocovariance(n + 1, hurst)
    first_row = np.concatenate([g[:n], [g[n]], g[1:n][::-1]])
    eigenvalues = np.fft.fft(first_row).real
    if eigenvalues.min() < 0.0:
        # [D04]: "the circulant matrix is not necessarily positive definite
        # for general autocovariance functions". For fGn it is, so this is a
        # guard against numerical failure rather than an expected branch.
        raise ValueError(
            f"circulant embedding is not positive definite at H={hurst}, "
            f"n={n} (min eigenvalue {eigenvalues.min():.3e}); "
            "Davies-Harte cannot be used here"
        )

    two_n = 2 * n
    v1 = rng.standard_normal(two_n)
    v2 = rng.standard_normal(two_n)
    w = np.zeros(two_n, dtype=complex)
    w[0] = np.sqrt(eigenvalues[0] / two_n) * v1[0]
    w[n] = np.sqrt(eigenvalues[n] / two_n) * v1[n]
    lo = np.arange(1, n)
    w[lo] = np.sqrt(eigenvalues[lo] / (2 * two_n)) * (v1[lo] + 1j * v2[lo])
    hi = np.arange(n + 1, two_n)
    w[hi] = np.sqrt(eigenvalues[hi] / (2 * two_n)) * (
        v1[two_n - hi] - 1j * v2[two_n - hi]
    )
    return np.fft.fft(w).real[:n]


def simulate_fbm(n: int, hurst: float, rng: np.random.Generator) -> np.ndarray:
    """Fractional Brownian motion on the integer grid, W^H_0 = 0 excluded.

    The cumulative sum of simulate_fgn, so
    E[|W^H_{t+Delta} - W^H_t|^2] = Delta^{2H} exactly ([GJR] eq. 1.1 at
    q = 2, where K_2 = 1).
    """
    return np.cumsum(simulate_fgn(n, hurst, rng))


# ==========================================================================
# 2. Hurst estimation — [GJR] Sec. 2.1
# ==========================================================================


def scaling_moment(
    series: np.ndarray, q: float, lag: int, *, overlapping: bool = True
) -> float:
    """m(q, Delta) of [GJR] Sec. 2.1 for one (q, Delta).

    `series` must be LOG VOLATILITY (see the module docstring, section 1);
    H is invariant to the log-vol / log-variance choice but nu is not.

    Two ways to average, and they agree to about 1e-3 on real series:

    overlapping=False is [GJR] literally: form the sub-series
    series[s::Delta] for each starting offset s = 0..Delta-1, take
    mean(|diff|^q) within each, then average across offsets ("Note that for
    a given Delta, several m(q, Delta) can be computed depending on the
    starting point. Our final measure of m(q, Delta) is the average of these
    values").

    overlapping=True pools every lag-Delta increment
    series[i+Delta] - series[i] into one mean. This is the same set of
    increments; only the weighting of unequal-length offset groups differs.
    It is the default because it is one vectorised operation instead of
    Delta of them, which is what makes a rolling out-of-sample study
    affordable. The tests assert the two agree.
    """
    x = np.asarray(series, dtype=float)
    if q <= 0:
        raise ValueError(f"q must be > 0, got {q}")
    if lag < 1:
        raise ValueError(f"lag must be >= 1, got {lag}")
    if x.ndim != 1:
        raise ValueError(f"series must be 1-D, got shape {x.shape}")
    if x.size <= lag:
        raise ValueError(f"series of length {x.size} is too short for lag {lag}")

    if overlapping:
        return float(np.mean(np.abs(x[lag:] - x[:-lag]) ** q))

    per_offset = []
    for start in range(lag):
        sub = x[start::lag]
        if sub.size < 2:
            continue
        per_offset.append(np.mean(np.abs(np.diff(sub)) ** q))
    if not per_offset:
        raise ValueError(f"series of length {x.size} is too short for lag {lag}")
    return float(np.mean(per_offset))


@dataclass(frozen=True)
class HurstEstimate:
    """Result of estimate_hurst.

    hurst
        The headline number: through-origin least squares of zeta_q on q,
        H = sum(zeta_q q) / sum(q^2). See the module docstring's flagged
        reconstruction — [GJR] plot zeta_q against the line H*q but do not
        print the arithmetic.
    hurst_with_intercept
        Ordinary with-intercept OLS slope of zeta_q on q. Robustness check.
        A large gap between the two means zeta_q is not proportional to q,
        i.e. the process is not behaving like a single-H fBm.
    zeta_by_q
        The per-q regression slopes zeta_q, in q_values order.
    r2_by_q
        R^2 of each log m(q, Delta) vs log Delta regression. [GJR] Sec. 2.2:
        "the points essentially lie on a straight line". Values well below
        ~0.99 mean that sentence does not hold for this series and H should
        not be read as a Hurst exponent at all.
    log_nu
        Intercept of the q = 2 regression; nu^2 = exp(log_nu) per [GJR]
        Sec. 5.2, valid only because the input is log VOLATILITY. NaN if
        q = 2 is not in q_values.
    n_obs, q_values, lags
        What was actually used.
    """

    hurst: float
    hurst_with_intercept: float
    zeta_by_q: np.ndarray = field(repr=False)
    r2_by_q: np.ndarray = field(repr=False)
    log_nu: float
    n_obs: int
    q_values: tuple[float, ...]
    lags: tuple[int, ...]

    @property
    def nu(self) -> float:
        """nu of [GJR] Sec. 5.2, the 'volatility of volatility'."""
        return float(np.exp(0.5 * self.log_nu))


def estimate_hurst(
    log_volatility: np.ndarray | pd.Series,
    *,
    q_values: tuple[float, ...] = DEFAULT_Q_VALUES,
    max_lag: int = DEFAULT_MAX_LAG,
    overlapping: bool = True,
) -> HurstEstimate:
    """Estimate the Hurst exponent of a log-volatility series, [GJR] Sec. 2.1.

    THE INPUT MUST BE LOG VOLATILITY, i.e. log(sigma), which is HALF the
    log-variance. [GJR] define m(q, Delta) on log(sigma_{k Delta}). H comes
    out identical either way (a constant factor shifts the intercept, not
    the slope) but nu does not, so the convention is enforced by
    documentation here and relied on by HurstEstimate.nu.

    The procedure, verbatim from [GJR] Sec. 2.1: "computing the m(q, Delta)
    for different values of Delta and regressing log m(q, Delta) against
    log Delta", then reading H off zeta_q ~ H q.

    Raises ValueError if the series is shorter than 2 * max_lag; below that
    the longest-lag moments rest on too few increments for the regression to
    mean anything.
    """
    x = np.asarray(
        log_volatility.to_numpy() if isinstance(log_volatility, pd.Series)
        else log_volatility,
        dtype=float,
    )
    if x.ndim != 1:
        raise ValueError(f"log_volatility must be 1-D, got shape {x.shape}")
    if not np.all(np.isfinite(x)):
        raise ValueError("log_volatility contains non-finite values")
    if max_lag < 2:
        raise ValueError(f"max_lag must be >= 2, got {max_lag}")
    if x.size < 2 * max_lag:
        raise ValueError(
            f"need at least 2 * max_lag = {2 * max_lag} observations to "
            f"estimate H with lags up to {max_lag}, got {x.size}"
        )
    if not q_values:
        raise ValueError("q_values must be non-empty")

    lags = np.arange(1, max_lag + 1, dtype=int)
    log_lags = np.log(lags.astype(float))
    design = np.column_stack([np.ones_like(log_lags), log_lags])

    zetas = np.empty(len(q_values))
    r2s = np.empty(len(q_values))
    log_nu = float("nan")

    for i, q in enumerate(q_values):
        moments = np.array(
            [scaling_moment(x, q, int(d), overlapping=overlapping) for d in lags]
        )
        if np.any(moments <= 0.0):
            raise ValueError(
                f"m({q}, Delta) is zero at some lag; the series is constant "
                "over part of its range and log m is undefined"
            )
        log_m = np.log(moments)
        coef, *_ = np.linalg.lstsq(design, log_m, rcond=None)
        intercept, slope = float(coef[0]), float(coef[1])
        zetas[i] = slope
        resid = log_m - design @ coef
        total = log_m - log_m.mean()
        denom = float(total @ total)
        r2s[i] = 1.0 - float(resid @ resid) / denom if denom > 0 else float("nan")
        if q == 2.0:
            log_nu = intercept

    q_arr = np.asarray(q_values, dtype=float)
    hurst = float(np.dot(zetas, q_arr) / np.dot(q_arr, q_arr))
    if len(q_values) >= 2:
        slope_int = float(
            np.linalg.lstsq(
                np.column_stack([np.ones_like(q_arr), q_arr]), zetas, rcond=None
            )[0][1]
        )
    else:
        slope_int = float("nan")

    return HurstEstimate(
        hurst=hurst,
        hurst_with_intercept=slope_int,
        zeta_by_q=zetas,
        r2_by_q=r2s,
        log_nu=log_nu,
        n_obs=int(x.size),
        q_values=tuple(float(q) for q in q_values),
        lags=tuple(int(d) for d in lags),
    )


# ==========================================================================
# 3. The volatility proxy
# ==========================================================================


def realized_variance(
    returns: np.ndarray | pd.Series, window: int
) -> np.ndarray | pd.Series:
    """Rolling realized variance from returns: mean of the last `window` r^2.

    [C09] eq. (3) builds realized volatility as the square root of a sum of
    squared INTRADAY returns over one day. THIS PROJECT HAS NO INTRADAY
    DATA, so `window` daily squared returns stand in for the intraday sum,
    normalised to a per-day variance.

    The substitution is the weakest link in the whole module and the
    docstring's section 2 spells out both bias directions it introduces.
    window=1 is allowed but is usually a mistake: RV_t is then r_t^2 and
    log(RV_t) explodes on any day the return is near zero.

    Leading positions with fewer than `window` observations are NaN.
    """
    if window < 1:
        raise ValueError(f"window must be >= 1, got {window}")
    if isinstance(returns, pd.Series):
        return returns.pow(2).rolling(window).mean()
    r = np.asarray(returns, dtype=float)
    if r.ndim != 1:
        raise ValueError(f"returns must be 1-D, got shape {r.shape}")
    if r.size < window:
        raise ValueError(f"need at least {window} returns, got {r.size}")
    sq = r**2
    csum = np.concatenate([[0.0], np.cumsum(sq)])
    out = np.full(r.size, np.nan)
    out[window - 1 :] = (csum[window:] - csum[:-window]) / window
    return out


# ==========================================================================
# 4. The RFSV predictor — [GJR] eq. (5.1)
# ==========================================================================


def _kernel_cdf(x: np.ndarray | float, a: float) -> np.ndarray:
    """Int_0^x u^{-a} / (1 + u) du in closed form, for 0 < a < 1.

        = x^{1-a}/(1-a) * 2F1(1, 1-a; 2-a; -x)

    Verified against scipy.integrate.quad to <= 1e-10 absolute at
    a = H + 1/2 for H in {0.02, 0.1, 0.3, 0.49} and
    x in {0.001, 0.5, 1, 10, 100, 499.5, 5000}. Asserted in the tests.
    """
    xa = np.asarray(x, dtype=float)
    out = np.zeros_like(xa)
    pos = xa > 0.0
    xp = xa[pos] if xa.ndim else xa
    val = xp ** (1.0 - a) / (1.0 - a) * hyp2f1(1.0, 1.0 - a, 2.0 - a, -xp)
    if xa.ndim:
        out[pos] = val
        return out
    return np.asarray(val if xa > 0 else 0.0)


def rfsv_kernel_mass(hurst: float) -> float:
    """Total mass of the eq. (5.1) kernel over u in (0, inf). Exactly 1.

        (cos(H pi)/pi) Int_0^inf u^{-(H+1/2)}/(1+u) du
      = (cos(H pi)/pi) * pi / sin(pi (H + 1/2))
      = (cos(H pi)/pi) * pi / cos(pi H) = 1.

    Derived here, not in [GJR]. Computed rather than hard-coded so the
    identity is exercised; returns 1.0 to machine precision for any H in
    (0, 1/2).
    """
    _validate_hurst(hurst)
    return float(np.cos(np.pi * hurst) / np.pi * (np.pi / np.cos(np.pi * hurst)))


def rfsv_weights(
    hurst: float,
    horizon: int,
    n_lags: int = DEFAULT_N_LAGS,
    *,
    normalize: bool = True,
) -> np.ndarray:
    """Discrete weights for [GJR] eq. (5.1), newest observation first.

    Implements the change-of-variable form [GJR] print in Sec. 5.1,

        E[log sigma^2_{t+Delta} | F_t]
            = (cos(H pi)/pi) Int_0^inf log sigma^2_{t - Delta u}
              / [(u + 1) u^{H + 1/2}] du,

    by giving the observation i days back the EXACT kernel mass of the cell
    u in [(i-0.5)/Delta, (i+0.5)/Delta], cell 0 being [0, 0.5/Delta]. That
    discretisation is this module's choice, not [GJR]'s — see the module
    docstring. The cell masses come from _kernel_cdf, in closed form.

    normalize=True rescales the truncated weights to sum to 1, which is
    exact in the untruncated limit (rfsv_kernel_mass) and makes the
    predictor reproduce a constant series exactly. With normalize=False the
    weights sum to less than 1 and the forecast is shrunk toward zero, which
    is meaningless on a log scale — so normalize=False exists only to let
    the tests measure the truncation deficit.

    Returns weights[i] = weight on the value i days before the forecast
    origin, i = 0 .. n_lags-1.
    """
    _validate_hurst(hurst)
    if hurst >= 0.5:
        # cos(H pi) <= 0 at H >= 1/2: the weights change sign and the
        # formula is stated for H < 1/2 ("where W^H is a fBM with H < 1/2").
        raise ValueError(
            f"[GJR] eq. (5.1) is stated for H < 1/2; got H={hurst}. "
            "At H >= 1/2 the kernel prefactor cos(H pi) is non-positive and "
            "the weights are not a probability distribution."
        )
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")
    if n_lags < 1:
        raise ValueError(f"n_lags must be >= 1, got {n_lags}")

    a = hurst + 0.5
    c = np.cos(np.pi * hurst) / np.pi
    i = np.arange(n_lags, dtype=float)
    upper = (i + 0.5) / horizon
    lower = np.maximum((i - 0.5) / horizon, 0.0)
    weights = c * (_kernel_cdf(upper, a) - _kernel_cdf(lower, a))
    if normalize:
        total = weights.sum()
        if total <= 0:
            raise ValueError(f"degenerate kernel weights at H={hurst}")
        weights = weights / total
    return weights


def rfsv_forecast(
    history: np.ndarray | pd.Series,
    hurst: float,
    horizon: int,
    *,
    n_lags: int = DEFAULT_N_LAGS,
    weights: np.ndarray | None = None,
) -> float:
    """One RFSV forecast of log-variance `horizon` steps ahead, [GJR] eq. (5.1).

    `history` is the log-variance series up to and including the forecast
    origin, OLDEST FIRST (the usual pandas order). Only its last n_lags
    entries are used. Pass `weights` to reuse a precomputed
    rfsv_weights(hurst, horizon, n_lags) across many origins.
    """
    x = np.asarray(
        history.to_numpy() if isinstance(history, pd.Series) else history, dtype=float
    )
    if x.ndim != 1:
        raise ValueError(f"history must be 1-D, got shape {x.shape}")
    if x.size == 0:
        raise ValueError("history is empty")
    if weights is None:
        weights = rfsv_weights(hurst, horizon, n_lags)
    k = min(int(weights.size), x.size)
    w = weights[:k]
    total = w.sum()
    if total <= 0:
        raise ValueError("degenerate weights")
    return float(np.dot(w, x[::-1][:k]) / total)


def fbm_conditional_variance_constant(hurst: float) -> float:
    """c of [GJR] Sec. 5.2: Var[W^H_{t+Delta} | F_t] = c Delta^{2H}.

        c = Gamma(3/2 - H) / [Gamma(H + 1/2) Gamma(2 - 2H)]

    Transcribed from [GJR]; their source (Nuzman & Poor) was NOT read this
    session. Two checks are run in its place, in the tests:

      * c(1/2) == 1, so Var = Delta, the right answer for ordinary Brownian
        motion. NECESSARY BUT NOT SUFFICIENT: the swapped form
        Gamma(H+1/2)/[Gamma(3/2-H) Gamma(2-2H)] also equals 1 there.
      * c Delta^{2H} is bracketed against the conditional variance of fBm on
        the discrete daily grid, computed from Cov(W_s, W_t) alone. That
        number is an upper bound which tightens with more lags, so it pins c
        from both sides and does exclude the swapped form.
    """
    _validate_hurst(hurst)
    return float(
        gamma_fn(1.5 - hurst) / (gamma_fn(hurst + 0.5) * gamma_fn(2.0 - 2.0 * hurst))
    )


def rfsv_variance_forecast(
    log_variance_forecast: float | np.ndarray,
    hurst: float,
    horizon: int,
    nu: float,
) -> float | np.ndarray:
    """Convert a log-variance forecast to a variance forecast, [GJR] Sec. 5.2.

        sigmahat^2_{t+Delta} = exp{ loghat sigma^2_{t+Delta}
                                    + 2 c nu^2 Delta^{2H} }

    The added term is the lognormal mean correction, half the conditional
    variance of log sigma^2 (which is 4 nu^2 c Delta^{2H} because
    log sigma^2 ~ 2 nu W^H + C). `nu` is HurstEstimate.nu.
    """
    _validate_hurst(hurst)
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")
    c = fbm_conditional_variance_constant(hurst)
    correction = 2.0 * c * nu**2 * float(horizon) ** (2.0 * hurst)
    return np.exp(np.asarray(log_variance_forecast, dtype=float) + correction)


# ==========================================================================
# 5. The HAR baseline — [C09] eq. (8)
# ==========================================================================


def har_features(series: np.ndarray, lags: tuple[int, ...] = GJR_HAR_LAGS) -> np.ndarray:
    """HAR regressors: trailing means over each lag, [C09] eq. (4).

    Column j at row t is mean(series[t-lags[j]+1 : t+1]), i.e. EXACTLY
    lags[j] terms, per [C09]: "a simple average of the daily quantities".
    See the module docstring for the off-by-one in [GJR]'s restatement.

    Rows before max(lags)-1 are NaN. No intercept column; fit_har adds one.
    """
    x = np.asarray(series, dtype=float)
    if x.ndim != 1:
        raise ValueError(f"series must be 1-D, got shape {x.shape}")
    if not lags or any(lag < 1 for lag in lags):
        raise ValueError(f"lags must be non-empty positive integers, got {lags}")
    if x.size < max(lags):
        raise ValueError(f"series of length {x.size} is shorter than max lag {max(lags)}")

    csum = np.concatenate([[0.0], np.cumsum(x)])
    out = np.full((x.size, len(lags)), np.nan)
    for j, lag in enumerate(lags):
        out[lag - 1 :, j] = (csum[lag:] - csum[:-lag]) / lag
    return out


@dataclass(frozen=True)
class HARModel:
    """OLS-fitted HAR(3), [C09] eq. (8). coefficients[0] is the intercept."""

    coefficients: np.ndarray
    lags: tuple[int, ...]
    n_obs: int

    def predict(self, features_row: np.ndarray) -> float:
        row = np.asarray(features_row, dtype=float)
        if row.size != len(self.lags):
            raise ValueError(
                f"expected {len(self.lags)} features, got {row.size}"
            )
        return float(self.coefficients[0] + np.dot(self.coefficients[1:], row))


def fit_har(
    series: np.ndarray,
    horizon: int,
    *,
    lags: tuple[int, ...] = GJR_HAR_LAGS,
) -> HARModel:
    """Fit HAR(3) by OLS to forecast `series` `horizon` steps ahead.

    [C09] eq. (8) with [C09]'s own estimator. [C09] Sec. 3.2, verbatim:
    "we can consider all the terms in Equation (8) as observed and then
    easily estimate its parameters beta(.) by applying simple linear
    regression. Standard OLS regression estimators are consistent and
    normally distributed."

    Generalised from one step to `horizon` steps exactly as [GJR] Sec. 5.1
    do ("the AR(p) and HAR predictors take the following form ...
    loghat(sigma^2_{t+Delta}) = ...").

    ONE THING [C09] DO THAT THIS DOES NOT, DECLARED SO NOBODY ASSUMES
    OTHERWISE. The same [C09] Sec. 3.2 continues: "In order to account for
    the possible presence of serial correlation in the data, the
    Newey-West covariance correction for serial correlation is employed."
    This module fits POINT ESTIMATES only and reports no
    standard errors at all, so the correction changes nothing here — but a
    caller who wants inference on the HAR coefficients must add it
    themselves rather than assume `HARModel.coefficients` arrives with
    valid uncertainty attached.
    """
    x = np.asarray(series, dtype=float)
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")
    feats = har_features(x, lags)
    max_lag = max(lags)
    origins = np.arange(max_lag - 1, x.size - horizon)
    if origins.size <= len(lags) + 1:
        raise ValueError(
            f"series of length {x.size} gives only {max(origins.size, 0)} usable "
            f"training rows for lags {lags} at horizon {horizon}; need more than "
            f"{len(lags) + 1}"
        )
    design = np.column_stack([np.ones(origins.size), feats[origins]])
    target = x[origins + horizon]
    coef, *_ = np.linalg.lstsq(design, target, rcond=None)
    return HARModel(coefficients=coef, lags=tuple(lags), n_obs=int(origins.size))


# ==========================================================================
# 6. Losses
# ==========================================================================


def gjr_p_ratio(actual: np.ndarray, forecast: np.ndarray, reference_mean: float) -> float:
    """[GJR] Sec. 5.1's ratio P. Lower is better; 1.0 == the sample mean.

    P = sum (actual - forecast)^2 / sum (actual - reference_mean)^2,
    with reference_mean "the empirical mean of the log-variance over the
    whole time period".
    """
    a = np.asarray(actual, dtype=float)
    f = np.asarray(forecast, dtype=float)
    if a.shape != f.shape:
        raise ValueError(f"shape mismatch: actual {a.shape}, forecast {f.shape}")
    denom = float(np.sum((a - reference_mean) ** 2))
    if denom <= 0:
        raise ValueError("reference variance is zero; P is undefined")
    return float(np.sum((a - f) ** 2) / denom)


def qlike_loss(proxy_variance: np.ndarray, forecast_variance: np.ndarray) -> float:
    """Mean QLIKE, [P11] eq. (6): L(sigmahat^2, h) = log h + sigmahat^2 / h.

    `proxy_variance` is [P11]'s sigmahat^2 (the realized proxy),
    `forecast_variance` is his h (the forecast). Both must be strictly
    positive. Lower is better. Not scale-free: only differences between
    models on the SAME data are meaningful.
    """
    p = np.asarray(proxy_variance, dtype=float)
    h = np.asarray(forecast_variance, dtype=float)
    if p.shape != h.shape:
        raise ValueError(f"shape mismatch: proxy {p.shape}, forecast {h.shape}")
    if np.any(h <= 0) or np.any(p <= 0):
        raise ValueError("QLIKE requires strictly positive variances")
    return float(np.mean(np.log(h) + p / h))


def variance_rmse(proxy_variance: np.ndarray, forecast_variance: np.ndarray) -> float:
    """RMSE on the variance scale. NOT robust to proxy noise — see [P11]."""
    p = np.asarray(proxy_variance, dtype=float)
    h = np.asarray(forecast_variance, dtype=float)
    if p.shape != h.shape:
        raise ValueError(f"shape mismatch: proxy {p.shape}, forecast {h.shape}")
    return float(np.sqrt(np.mean((p - h) ** 2)))


# ==========================================================================
# 7. The rolling out-of-sample comparison
# ==========================================================================


@dataclass(frozen=True)
class ForecastComparison:
    """Out-of-sample forecasts from rolling_forecast_comparison.

    All arrays are aligned and have one entry per forecast origin.
    `origins` holds the index into the input series of each origin t;
    `actual` holds the realised log-variance at t + horizon.
    """

    horizon: int
    origins: np.ndarray = field(repr=False)
    actual: np.ndarray = field(repr=False)
    rfsv: np.ndarray = field(repr=False)
    har: np.ndarray = field(repr=False)
    last_value: np.ndarray = field(repr=False)
    hurst_by_origin: np.ndarray = field(repr=False)
    n_forecasts: int

    def p_ratios(self) -> dict[str, float]:
        """[GJR]'s P for each model, against the full-sample mean."""
        ref = float(np.mean(self.actual))
        return {
            "rfsv": gjr_p_ratio(self.actual, self.rfsv, ref),
            "har": gjr_p_ratio(self.actual, self.har, ref),
            "last_value": gjr_p_ratio(self.actual, self.last_value, ref),
        }

    def qlike(self) -> dict[str, float]:
        """QLIKE on the variance scale, exponentiating the log forecasts.

        NOTE: this exponentiates the log-variance forecast WITHOUT [GJR]
        Sec. 5.2's lognormal correction, so that all three models are
        treated identically. Applying the correction to RFSV only would
        hand it an advantage no baseline gets. rfsv_variance_forecast
        exposes the corrected version for callers who want it.
        """
        proxy = np.exp(self.actual)
        return {
            "rfsv": qlike_loss(proxy, np.exp(self.rfsv)),
            "har": qlike_loss(proxy, np.exp(self.har)),
            "last_value": qlike_loss(proxy, np.exp(self.last_value)),
        }

    def variance_rmse(self) -> dict[str, float]:
        """RMSE on the variance scale. NOT robust to proxy noise ([P11]);
        reported only because it is the familiar number. Same
        no-lognormal-correction convention as qlike()."""
        proxy = np.exp(self.actual)
        return {
            "rfsv": variance_rmse(proxy, np.exp(self.rfsv)),
            "har": variance_rmse(proxy, np.exp(self.har)),
            "last_value": variance_rmse(proxy, np.exp(self.last_value)),
        }


def rolling_forecast_comparison(
    log_variance: np.ndarray | pd.Series,
    horizon: int,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    har_lags: tuple[int, ...] = GJR_HAR_LAGS,
    n_lags: int = DEFAULT_N_LAGS,
    fixed_hurst: float | None = None,
    max_lag: int = DEFAULT_MAX_LAG,
    hurst_round: int = 3,
) -> ForecastComparison:
    """Rolling out-of-sample RFSV vs HAR vs last-value, on log-variance.

    Protocol, following [GJR] Sec. 5.1: at every origin t from `window` to
    len - horizon - 1, refit HAR by OLS on the trailing `window`
    observations and form all three forecasts of log_variance[t + horizon].

    fixed_hurst=None (the default and the honest one) re-estimates H on
    each trailing window, so nothing from the future enters the forecast.
    Passing a float instead reproduces [GJR]'s own protocol — their
    footnote 14: "the parameter H used in our predictor is computed only
    once for each asset, using the whole time period" — which peeks at the
    full sample. Callers who do that must label the result as such.

    `hurst_round` rounds the per-window H before looking up kernel weights,
    so weights are computed once per distinct H rather than once per origin.
    At the default of 3 decimals the rounding error is at most 5e-4 (mean
    2.5e-4), against a sampling standard deviation for H on a 500-point
    window of 0.022 at H = 0.1 rising to 0.056 at H = 0.5 (measured; see
    test_estimator_degrades_predictably_on_a_500_point_window). So the
    rounding is roughly two orders of magnitude below the noise it sits
    inside. Set to None to disable.

    The RFSV kernel needs H < 1/2 ([GJR] state eq. (5.1) for H < 1/2). Any
    window whose estimated H lands at or above 1/2 is CLIPPED to just below,
    and the unclipped value is still recorded in `hurst_by_origin` so the
    caller can see how often it happened.
    """
    x = np.asarray(
        log_variance.to_numpy() if isinstance(log_variance, pd.Series)
        else log_variance,
        dtype=float,
    )
    if x.ndim != 1:
        raise ValueError(f"log_variance must be 1-D, got shape {x.shape}")
    if not np.all(np.isfinite(x)):
        raise ValueError("log_variance contains non-finite values")
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")
    if window < 2 * max_lag:
        raise ValueError(
            f"window {window} is too short to estimate H with lags up to "
            f"{max_lag}; need at least {2 * max_lag}"
        )
    if x.size <= window + horizon:
        raise ValueError(
            f"need more than window + horizon = {window + horizon} observations, "
            f"got {x.size}"
        )
    if fixed_hurst is not None and not 0.0 < fixed_hurst < 0.5:
        raise ValueError(f"fixed_hurst must be in (0, 0.5), got {fixed_hurst}")

    origins = np.arange(window, x.size - horizon)
    n = origins.size
    rfsv = np.empty(n)
    har = np.empty(n)
    last = np.empty(n)
    hursts = np.empty(n)

    weight_cache: dict[float, np.ndarray] = {}
    clip_hi = 0.5 - 1e-4

    for k, t in enumerate(origins):
        train = x[t - window + 1 : t + 1]

        if fixed_hurst is None:
            h_raw = estimate_hurst(train, max_lag=max_lag).hurst
        else:
            h_raw = float(fixed_hurst)
        hursts[k] = h_raw

        h_use = min(max(h_raw, _MIN_HURST), clip_hi)
        key = round(h_use, hurst_round) if hurst_round is not None else h_use
        key = min(max(float(key), _MIN_HURST), clip_hi)
        w = weight_cache.get(key)
        if w is None:
            w = rfsv_weights(key, horizon, n_lags)
            weight_cache[key] = w

        hist = x[max(0, t - n_lags + 1) : t + 1]
        rfsv[k] = rfsv_forecast(hist, key, horizon, n_lags=n_lags, weights=w)

        model = fit_har(train, horizon, lags=har_lags)
        feats = har_features(train, har_lags)[-1]
        har[k] = model.predict(feats)

        last[k] = x[t]

    return ForecastComparison(
        horizon=int(horizon),
        origins=origins,
        actual=x[origins + horizon],
        rfsv=rfsv,
        har=har,
        last_value=last,
        hurst_by_origin=hursts,
        n_forecasts=int(n),
    )


# ==========================================================================
# helpers
# ==========================================================================


def _validate_hurst(hurst: float) -> None:
    if not np.isfinite(hurst):
        raise ValueError(f"hurst must be finite, got {hurst}")
    if not _MIN_HURST <= hurst <= _MAX_HURST:
        raise ValueError(
            f"hurst must lie in ({_MIN_HURST}, {_MAX_HURST}) — [GJR] Sec. 1.2 "
            f"defines fBm for H in (0, 1) — got {hurst}"
        )
