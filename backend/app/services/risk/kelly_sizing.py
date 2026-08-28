"""Continuous-time Kelly (growth-optimal) position SIZING, from the
Merton/HJB solution to the lifetime portfolio problem.

WHAT IS ACTUALLY NEW HERE, STATED FIRST BECAUSE IT IS EASY TO OVERSELL.
The unconstrained direction this module computes,

    Sigma^-1 (mu - r 1),

is the SAME LINE through weight space as the (unconstrained) tangency /
max-Sharpe portfolio that optimizer.py's SLSQP already searches for.
optimizer.py maximizes (w'mu - r)/sqrt(w'Sigma w) subject to sum(w) = 1,
and under that constraint w'mu - r == w'(mu - r 1), so absent its long-only
bounds and its 40% per-name cap its answer is
Sigma^-1(mu - r 1) / [1' Sigma^-1(mu - r 1)]. This module does NOT
contribute a new notion of which assets to hold or in what relative
proportion.

  ONE PRECISION, because "same direction" is not quite "same portfolio"
  and the difference is not academic. The normalization divides by
  1' Sigma^-1(mu - r 1), which CAN BE NEGATIVE — and on the real 12-ETF
  universe measured below it is: the full-Kelly weights sum to -4.796.
  Normalizing there does not rescale the Kelly portfolio, it REVERSES it.
  Measured: the sum-to-1 portfolio on that data has Sharpe -1.5214, the
  exact negative of the Kelly direction's +1.5214. So "the tangency
  portfolio" and "the growth-optimal direction" coincide only up to a sign
  that the sum-to-1 contract silently throws away, and the degenerate case
  is not rare. Kelly, which never normalizes, does not have this failure
  mode.

What it contributes is the SCALE: how much total capital to deploy against
a direction, derived from maximizing the long-run growth rate of wealth
rather than from an ad hoc weight cap. optimizer.py answers "what mix?"
and forces sum(w) = 1 by constraint; HRP answers "what mix?" and gets
sum(w) = 1 by construction. NEITHER ANSWERS "how much?" — both are
definitionally fully invested. Kelly answers exactly that, and its answer
is frequently nowhere near 1.0 — in both directions. On the real 12-ETF
universe measured below it says 43x gross for the unconstrained direction
(an estimation-error artifact, and the module says so) and 0.35x for HRP's
direction (which is the tool doing its job: that portfolio's Sharpe was
0.03). That is the whole of the new content, and the API is shaped around
it (see API DESIGN below).

SHIPPED OPT-IN, NEVER A DEFAULT. Same convention as hrp_optimizer.py,
rmt_denoising.py and effective_n_clustering.py: nothing in this codebase
calls this module. optimizer.py and hrp_optimizer.py are untouched; no
setting selects it; no endpoint exposes it. It is infrastructure for an
explicit caller.

=============================================================================
PRIMARY SOURCES — fetched and read line-by-line during this implementation
session, never quoted from memory. Page/equation numbers below are the
sources' own.

ONE CONVENTION THAT APPLIES TO EVERY QUOTE BELOW: this file is ASCII, the
sources are not. Greek letters, subscripts, superscripts and fraction bars
are TRANSLITERATED (alpha, sigma^2, f_i*, m_i, Omega^-1, ...). "Verbatim"
therefore means the WORDS are the source's exactly; the SYMBOLS are
rendered. Where a symbol could not be read at all rather than merely
re-rendered, that is called out as a reconstruction, individually.
=============================================================================

  [M69] Merton, R. C., "Lifetime Portfolio Selection under Uncertainty: The
        Continuous-Time Case", The Review of Economics and Statistics, Vol.
        51, No. 3 (Aug. 1969), pp. 247-257 (MIT Press; JSTOR 1926560). The
        full 11-page scan was downloaded and its text extracted and read
        this session. THE SOURCE OF THE CLOSED FORM this module implements.
        SOURCING LIMIT — READ THIS BEFORE TRUSTING ANY EQUATION QUOTED FROM
        [M69] BELOW. What was read is a 1969 JSTOR SCAN, and its text layer
        mangles mathematical symbols: Greek letters come through as digits
        or Latin letters (gamma variously as "y" or "8"), superscripts and
        subscripts are dropped, and fraction bars vanish. PROSE from [M69]
        is quoted verbatim and is reliable. EQUATIONS are NOT transcribed
        blind: each one below was reconstructed from the surviving
        structure and then CROSS-CHECKED against a source whose text layer
        is clean — [M71] for the first-order condition, [T06] eq. (8.2) for
        the m-asset closed form — and, for eq. (60) specifically, verified
        numerically against Merton's own HJB objective in
        tests/test_kelly_sizing.py. Every place where the reconstruction is
        a reading rather than a reading-off is flagged inline.
        Two concrete examples of the mangling, so the reader can calibrate:
        the scan renders eq. (25) as "w*(t) = (a-r)" with the whole
        denominator lost, and renders "1 - gamma is Pratt's [7] measure of
        relative risk aversion" as "1 - 8 is Pratt's [7] measure ...".

  [M71] Merton, R. C., "Optimum Consumption and Portfolio Rules in a
        Continuous-Time Model", Journal of Economic Theory 3, 373-413
        (1971). Full 41-page PDF downloaded, text extracted and read this
        session. Used as the general-utility corroboration of [M69]'s
        first-order condition. Its text layer is better than [M69]'s but
        not clean either (it drops eq. (27) entirely); the two statements
        used from it, eq. (25)'s footnote 16 and the p. 387 corollary,
        both survived legibly.

  [T06] Thorp, E. O., "The Kelly Criterion in Blackjack Sports Betting, and
        the Stock Market", Chapter 9 of Handbook of Asset and Liability
        Management, Volume 1, eds. S. A. Zenios and W. T. Ziemba, Elsevier
        (2006), DOI 10.1016/S1872-0978(06)01009-X, pp. 385-428. (The
        chapter's own footnote: paper presented at the 10th International
        Conference on Gambling and Risk Taking, Montreal, June 1997,
        published in "Finding the Edge: Mathematical Analysis of Casino
        Games", 2000; corrections added April 20, 2005.) Full 44-page PDF
        downloaded and read this session. THE SOURCE OF THE MULTI-ASSET
        KELLY STATEMENT IN INVESTMENT NOTATION and of the fractional-Kelly
        practitioner guidance.

  [Z11] Ziemba, W. T. and L. C. MacLean, "Using the Kelly Criterion for
        Investing", Chapter 1 of Stochastic Optimization Methods in Finance
        and Energy, eds. M. Bertocchi, G. Consigli, M. A. H. Dempster,
        International Series in Operations Research & Management Science
        163, Springer (2011), DOI 10.1007/978-1-4419-9586-5_1, pp. 3-20.
        Full 18-page PDF downloaded and read this session. THE SOURCE OF
        THE EXPLICIT "fractional Kelly fraction == 1 / relative risk
        aversion" IDENTITY that welds [M69] to [T06].

  [P10] Photiou, G., "Extend the ideas of Kan and Zhou paper on Optimal
        Portfolio Construction under parameter uncertainty", MSc
        dissertation in Mathematical and Computational Finance, Lincoln
        College, University of Oxford, 25 June 2010 (ora.ox.ac.uk). Full
        45-page PDF downloaded and read this session.
        SOURCING LIMIT, STATED PLAINLY: this is a SECONDARY source. The
        primary — Kan, R. and G. Zhou, "Optimal Portfolio Choice with
        Parameter Uncertainty", Journal of Financial and Quantitative
        Analysis 42(3) (Sept. 2007), 621-656 — WAS NOT READ. Both of the
        author's own posted PDFs (rotman.utoronto.ca/~kan/papers/erisk8.pdf
        and .../optport.pdf) returned a 404 handler page to this session.
        [P10] transcribes their results as its own eqs. (2.7)-(2.20) and
        attributes them to "section II.B of Kan Zhou paper". Everything
        below marked [P10] is quoted from the dissertation, NOT from JFQA,
        and the JFQA equation numbers are deliberately not cited because
        they were not seen. The one [P10] result this module implements is
        INDEPENDENTLY VERIFIED NUMERICALLY against this module's own Monte
        Carlo (see ESTIMATION RISK below) rather than taken on trust.
        INDEPENDENT-VERIFICATION UPDATE (2026-08-29, verification pass):
        the primary WAS subsequently obtained — a Wayback Machine snapshot
        (timestamp 20101029023816) of the same
        rotman.utoronto.ca/~kan/papers/erisk8.pdf that 404s today, i.e. the
        authors' own posted December 2005 working-paper version of the JFQA
        article, read in full. Its section II.B / "Optimal Two-Fund Rule"
        eqs. (41)-(42) state EXACTLY the expected-utility expression and c*
        that [P10] transcribes as (2.16)-(2.17), including
        mu_hat ~ N(mu, Sigma/T) and Sigma_hat ~ W_N(T-1, Sigma)/T with the
        1/T divisor flagged below (its eqs. 10-11, 13-14), and its footnote
        4 independently states the theta^2 < N/T "better off not investing"
        reading used in THE TRAP below. Equation numbers here are the
        working paper's own; the published JFQA typesetting was still not
        seen, so JFQA equation numbers remain uncited.

  NOT READ, THEREFORE NOT CITED AS READ, though it is the origin of the
  name: Kelly, J. L., "A New Interpretation of Information Rate", Bell
  System Technical Journal 35 (1956), 917-926. That citation appears in
  [Z11]'s abstract and [T06]'s references; the 1956 paper itself was not
  fetched this session. Nothing in this module rests on it.
  Also not read: MacLean, Ziemba and Li (2005), cited by [Z11] as the proof
  of the fraction-vs-risk-aversion identity; Chopra and Ziemba (1993), JPM
  19, 6-11, cited by [Z11] for the 100:3:1 error-sensitivity ratio quoted
  below. Both are quoted THROUGH [Z11] and labelled as such.

=============================================================================
THE DERIVATION, as it actually appears in [M69]
=============================================================================

WEALTH DYNAMICS. [M69] section II builds the budget equation as a limit of
its discrete-time form. Its eq. (12), the two-asset continuous-time budget
equation (w = fraction in the risky asset, alpha its drift, r the sure
rate, sigma its volatility, C consumption):

    dW = [(w(t)(alpha - r) + r)W(t) - C(t)] dt + w(t) sigma Z(t) W(t) sqrt(dt)

(quoted from the scan; [M69] writes the Wiener increment as
"Z(t) sqrt(dt)" with Z standard normal, i.e. what modern notation writes
dZ). Its m-asset counterparts are eqs. (6') and (7') on p. 255, in which
w is an n-vector, alpha - r the excess-return vector, and Omega = [sigma_ij]
"the n x n variance-covariance matrix of the risky assets" which "is
symmetric and positive definite" ([M69] p. 255, verbatim).

  DEVIATION FROM THE TASK SKETCH, flagged because it is real: this module
  drops consumption (C == 0) and the bequest function. [M69]'s problem is a
  JOINT consumption-and-portfolio problem, and its eq. (12) carries the
  -C(t) dt term. What makes the reduction legitimate is [M69]'s own
  separation result, section VII, p. 253, verbatim: "for iso-elastic
  marginal utility, the portfolio-selection decision is independent of the
  consumption decision." So the portfolio rule this module implements is
  the same rule whether or not consumption is modelled. Stated rather than
  assumed, because a reader comparing to [M69] will see a term missing.

THE HJB EQUATION. [M69] eq. (17'), p. 249 — "a continuous-time version of
the Bellman-Dreyfus fundamental equation of optimality" ([M69]'s own words)
for the value function I[W(t), t]:

    0 = Max_{C,w} [ e^{-rho t} U[C(t)] + dI/dt
                    + (dI/dW)[(w(t)(alpha - r) + r)W(t) - C(t)]
                    + (1/2)(d2I/dW2) sigma^2 w^2(t) W^2(t) ]

The m-asset version is [M69] eq. (58), p. 255, in the infinite-horizon form
where J(W) = e^{rho t} I (eq. 34):

    0 = Max_{C,w} [ U(C) - rho J(W)
                    + J'(W){[w'(alpha - r) + r]W - C}
                    + (1/2) J''(W) w' Omega w W^2 ]

FIRST-ORDER CONDITION IN w. [M69] eq. (19), p. 249:

    0 = (alpha - r) W dI/dW + sigma^2 w W^2 d2I/dW2

solved in [M69]'s system (*'), p. 250, for

    w*(t) = -[(alpha - r) / (sigma^2 W)] * (dI/dW) / (d2I/dW2)

(The first display is [M69] eq. (19) as printed, with I's partials written
out; the second is its solution as [M69] system (*') states it. Both come
through the scan with their structure intact, and the leading minus sign
on the second is required for w* to be positive when alpha > r and I is
concave — which one of [M69]'s own footnotes on p. 250 states as a
condition: "we have the condition w*(t)(alpha - r) > 0 if and only if
d2I/dW2 < 0". The footnote's NUMBER is deliberately not cited: the scan's
markers on that page are ambiguous between two adjacent notes, and
guessing one would be a fabricated precision.)

[M71] states the same thing for n risky assets and GENERAL utility, which
is the useful corroboration: its eq. (25) writes
w_k* = h_k(P,t) + m(P,W,t) g_k(P,t) + f_k(P,W,t), and its footnote 16
defines the middle coefficient as
    m(P, W, t) = -J_W / (W J_WW)
(rendered in [M71]'s text layer as "m(P, w, t) = --Jw/WJwv", i.e. legible
apart from the second subscript). Its p. 387 corollary, for the case where
one asset is risk-free, gives
    w_k* = m(W, t) sum_j v_kj (alpha_j - r),  k = 1..m
where [M71] eq. (24) defines [v_ij] == Omega^-1. (That display's summation
is partly garbled in the text layer; its SHAPE — a scalar m times a row of
Omega^-1 against the excess-return vector — is what is read from it, and it
is corroborated by [M69] eq. (60) and [T06] eq. (8.2), both independent.)

So the optimal risky-asset vector is ALWAYS proportional to
Omega^-1(alpha - r 1); preferences enter only through the scalar
-J_W/(W J_WW). That scalar is the whole content of "how much".

THE CRRA CLOSED FORM. [M69] section IV sets U(C) = C^gamma/gamma with
gamma < 1, gamma != 0, or U(C) = log C as "the limiting form for gamma = 0",
and states that "-U''(C) C / U'(C) = 1 - gamma is Pratt's [7] measure of
relative risk aversion" (the "[7]" is [M69]'s own reference marker to
Pratt; the scan renders the gamma there as an "8", see the [M69] sourcing
limit, and the identity delta = 1 - gamma is pinned independently by
eqs. (25) and (29') below). WATCH THE NOTATION: [M69]'s gamma is NOT the
risk-aversion coefficient; 1 - gamma is. With the trial solution
I[W,t] = (b(t)/gamma) e^{-rho t} W^gamma ([M69] eq. 22), J_W/(W J_WW)
= 1/(gamma - 1), and [M69]'s m-asset result, eq. (60), p. 256, is:

    w*(t) = [1/(1 - gamma)] Omega^-1 (alpha - r)                    [M69] (60)

with the two-asset case eq. (29')/(25):  w* = (alpha - r)/(delta sigma^2),
where [M69] p. 253 writes it "in terms of Pratt's relative risk-aversion
measure, delta".
  RECONSTRUCTION NOTE, per the [M69] sourcing limit, because the two
  equations are NOT in the same state and it matters which is which.
    - EQ. (60) IS LEGIBLE. The scan renders it across three lines as
      "1" / "wX,*(t) = Q- (a-r)   (60)" / "(l1-y)" — i.e. numerator 1,
      body Omega^-1(alpha - r), denominator (1 - gamma). It is READ, not
      reconstructed. This is the equation the module implements.
    - EQ. (25) AND EQ. (29') ARE NOT. They come through as bare
      "w*(t) = (a-r)" with their denominators lost, and are reconstructed
      from two places on the SAME pages where the scan held together:
      p. 250's transformed discount rate, "rho_mu = rho - gamma[(alpha -
      r)^2/2 sigma^2 (1 - gamma) + r]", and p. 252's convergence condition
      (40), which carries "(alpha - r)^2 / 2 sigma^2 (1 - gamma)^2" and
      "1/(1 - gamma)". (A third, p. 251's eq. (13') for alpha*, survives
      only as the fragment "sigma^2(1 -" and is not relied on.) Only
      w* = (alpha - r)/(sigma^2 (1 - gamma)) makes those consistent, and
      it is the two-asset case of the legible eq. (60), which is the real
      check.
    - EQ. (58) is legible except that its 1/2 renders as "2"
      ("+ 2 J"(W) we Q wW2]"); the corresponding 1/2 in eq. (17') DOES
      come through, so the reading is not in doubt.
  [T06] eq. (8.2) then confirms the gamma = 0 case from an independent
  source with a clean text layer, and tests/test_kelly_sizing.py confirms
  the general case numerically against [M69]'s own HJB maximand.

Rewritten in the risk-aversion parameter this module actually exposes,
gamma_RRA == 1 - gamma_Merton == delta:

    pi* = (1 / gamma_RRA) Sigma^-1 (mu - r 1)

and at gamma_RRA = 1 (log utility, [M69]'s gamma = 0):

    pi* = Sigma^-1 (mu - r 1)                                    FULL KELLY

  IS THE LOG CASE REALLY COVERED? [M69]'s own footnote 6, p. 250, verbatim:
  "Although not derived explicitly here, the special case (gamma = 0) of
  Bernoulli logarithmic utility has (29) with gamma = 0 as a solution".
  Section VII, p. 254, treats gamma = 0 / delta = 1 as an ordinary member
  of the family ("In the borderline case of Bernoulli logarithmic utility
  (delta = 1) ..."). So log utility is inside [M69]'s solution, by [M69]'s
  own statement — not by this module's extrapolation.

  ON LEVERAGE, [M69] IS EXPLICIT. Footnote 10, p. 253, verbatim: "no
  restriction on borrowing or going short was imposed on the problem, and
  therefore, w* can be greater than one or less than zero. Thus, if
  alpha < r, the risk-averter will short some of the risky asset, and if
  alpha > r + [sigma^2 delta] he will borrow funds to invest in the risky
  asset." The bracketed term is the one place the scan's OCR is
  unrecoverable; it is reconstructed from eq. (29') (w* > 1 iff
  alpha - r > delta sigma^2), NOT read, and is flagged as such.

=============================================================================
IS THAT REALLY "THE KELLY CRITERION"? — YES, AND HERE IS THE CHAIN
=============================================================================

[M69] never uses the word "Kelly". The identification is made by the Kelly
literature itself, and it is made twice over, in two independent places
both read this session:

  (a) [Z11] section 1.4, footnote 2, verbatim: "The formula relating lambda
      and f for this example is as follows. For the problem
      Max_x {E(ln(1 + r + x(R - r))}, where R is assumed to be Gaussian
      with mean mu_R and standard deviation sigma_R, and r = the risk-free
      rate. The solution is given by Merton (1990) as x = (mu_R - r)/sigma_R
      [sic]. Since mu_R = 0.102, sigma_R = 0.203, r = 0.039, the Kelly
      strategy is x = 1.5288."
      The printed formula lost its exponent in the PDF text layer; the
      chapter's OWN ARITHMETIC settles which it is, and this module checked
      it rather than guessing: (0.102 - 0.039)/0.203^2 = 1.52879, matching
      the printed 1.5288 to five figures, while (0.102 - 0.039)/0.203 =
      0.3103 does not. So the intended formula is x = (mu_R - r)/sigma_R^2,
      i.e. [M69] eq. (29') at delta = 1. Asserted in the tests.
      Note this is a MERTON citation used to answer a KELLY question, by
      Kelly's own principal expositors. That is the weld.

  (b) [T06] section 8.4, p. 418, "The theory for a portfolio of securities",
      derives the multi-asset case from scratch in investment notation. Its
      eq. (8.1): with riskless fraction f_0 and f_0 + ... + f_n = 1,
          m = r + F^T (M - R),   s^2 = F^T C F
      where C = (s_ij) is the covariance matrix, M the vector of drift
      rates, R the constant vector (r, ..., r)^T. Then, verbatim: "Then our
      previous formulas and results for one security plus a riskless
      security apply to g_inf(f_1, ..., f_n) = m - s^2/2. This is a
      standard quadratic maximization problem. Using (8.1) and solving the
      simultaneous equations dg_inf/df_i = 0, i = 1, ..., n, we get"

          F* = C^-1 [M - R]                                       [T06] (8.2)
          g_inf(f_1*, ..., f_n*) = r + (F*)^T C F* / 2            [T06] (8.2)

      which is [M69] eq. (60) at 1 - gamma = 1, in a paper whose title
      contains "Kelly Criterion". [T06] adds, verbatim: "When all the
      securities are uncorrelated, C is diagonal and we have
      f_i* = (m_i - r)/s_ii".

  This module re-derived [T06] (8.2) independently rather than copying it,
  and the two agree: g(F) = r + F'(M - R) - (1/2) F'CF is concave in F, so
  grad g = (M - R) - CF = 0 gives F* = C^-1(M - R), and substituting back
  gives g(F*) = r + F*'(M - R) - (1/2)F*'CF* = r + (1/2)F*'CF* because
  F*'(M - R) = F*'CF*. Both the gradient identity and the growth-rate
  identity are asserted in the tests against numerical differentiation.

  A USEFUL IDENTITY THAT FALLS OUT, and the cleanest link back to
  optimizer.py: F*'CF* = (M - R)'C^-1(M - R) = theta^2, the SQUARED MAXIMUM
  SHARPE RATIO of the unconstrained tangency portfolio. So
  g_inf(F*) = r + theta^2/2. [T06] p. 407 states the one-asset form of
  exactly this and draws the same connection, verbatim: "The slope of this
  line is the Sharpe ratio S = (m_0 - r_0)/s_0 and from (7.3)
  g_inf(f*) = S^2/2 + r so the maximum growth rate g_inf(f*) depends, for
  fixed r, only on the Sharpe ratio."

  And the flip side, [T06] p. 408, which is why this module is not an
  alternative to mean-variance but a scaling of it, verbatim: "In the
  continuous approximation, the Kelly investor appears to have the utility
  function U(s, m) = m - s^2/2." That is mean-variance utility with risk
  aversion exactly 1 — the same objective optimizer.py maximizes a
  normalized version of.

=============================================================================
FRACTIONAL KELLY — WHAT IT MEANS HERE, EXACTLY
=============================================================================

In THIS framework fractional Kelly and CRRA risk aversion are the same
knob, and [Z11] p. 9 says so in one line, verbatim: "These values come from
the handy formula for the fractional Kelly

    f = 1/(1 - alpha) = 1/R_R,

which is exactly correct for lognormal assets and approximately correct
otherwise; see MacLean, Ziemba, and Li (2005) for proof. Thorp (2008) shows
that this approximation can be very poor."

([Z11]'s alpha is the exponent of the negative-power utility alpha w^alpha;
R_R is relative risk aversion. Its Table 1.1 tabulates the same thing:
log w has relative RA 1 and is the "geometric mean optimizer"; -1/w has
relative RA 2 and is labelled "half Kelly".)

Set against [M69] eq. (60), that identity is not an approximation at all
here, it is an algebraic restatement:

    pi*(gamma_RRA) = (1/gamma_RRA) Sigma^-1(mu - r 1) = (1/gamma_RRA) pi*_full

so a Kelly fraction c and a risk aversion gamma_RRA = 1/c are the SAME
VECTOR. Half Kelly (c = 0.5) is EXACTLY gamma_RRA = 2, and half-Kelly
weights are EXACTLY half the full-Kelly weights, component by component,
to floating point. The task asked whether that is really true or "more
subtle"; in this UNCONSTRAINED, CONSTANT-OPPORTUNITY-SET, lognormal setting
it is exactly true and the tests assert bit-level proportionality.

WHERE IT STOPS BEING TRUE, three ways, all real and all flagged:
  1. [Z11]'s own caveat above: exact for lognormal assets only, and
     "Thorp (2008) shows that this approximation can be very poor"
     otherwise. This module's model IS lognormal, so it is exact HERE and
     nowhere claimed beyond.
  2. Add ANY constraint that binds — long-only, a weight cap, a margin
     limit ([T06] eq. (8.3): "|f_1| + ... + |f_n| <= 1/q") — and exact
     proportionality dies, because the constraint set does not scale with
     c. This is precisely why this module does not try to reuse
     optimizer.py's constrained SLSQP: that path's answer is NOT
     c-proportional.
  3. [M69]'s solution assumes a CONSTANT opportunity set (mu, Sigma
     constant; [M69] eq. (29), p. 251, states the consequence verbatim —
     w*(t) is "a constant independent of W or t"). Under a stochastic
     opportunity set an intertemporal hedging demand appears and the
     1/gamma scaling no longer describes the whole answer. That case is
     [M71]'s section 7 onwards and is NOT implemented here.

WHY THE DEFAULT IS 0.5. It is a cited practitioner convention, not a
derived optimum, and the module says so at the parameter. [T06] section
7.3, p. 415, verbatim: "The chance of ever losing half the starting capital
is 1/2 for f = f* but only 1/8 for f = f*/2. My gambling and investment
experience, as well as reports from numerous blackjack players and teams,
suggests that most people strongly prefer the increased safety and
psychological comfort of 'half Kelly' (or some nearby value), in exchange
for giving up 1/4 of their growth rate." [Z11] p. 8, verbatim: "half Kelly
is a toned down version of full Kelly that provides a lot more security to
compensate for its loss in long-term growth."

The "1/4 of their growth rate" and "1/8" are not rhetoric; they are two
closed forms in [T06] that this module reproduces and tests:

    g_inf(c f*) / g_inf(f*) = c(2 - c)          [T06] (7.6), r = 0
    Prob(V(t, c f*)/V_0 <= x for some t) = x^(2/c - 1)      [T06] (7.13)

At c = 1/2: growth ratio 0.5 * 1.5 = 0.75 (the "3/4 the growth rate",
[T06] p. 415) and ruin exponent 3, so the chance of ever halving is
(1/2)^3 = 1/8 against (1/2)^1 = 1/2 at full Kelly. Both asserted in the
tests, and (7.13) is additionally used as an ANALYTIC CHECK ON THIS
MODULE'S OWN SIMULATOR (below).

At c = 2 the growth ratio is 0, which [Z11] p. 8 states in words, verbatim:
"the investor who wagers exactly twice this amount has a growth rate of
zero plus the risk-free rate of interest". KellyLeverageResult surfaces
that crossover as `zero_growth_leverage`, because "how far am I from the
leverage at which all my edge is eaten by variance drag" is the single most
useful number a sizing tool can report.

And on never exceeding full Kelly, [Z11] p. 8, verbatim: "Since the growth
rate and the security are both decreasing for f > f*, it follows that it is
never advisable to wager more than f*." This module nonetheless ALLOWS
kelly_fraction > 1 (with the growth rate reported, which goes negative past
c = 2) rather than refusing it, because refusing would make the module
unable to demonstrate the very failure it exists to warn about. It is
never the default.

=============================================================================
ESTIMATION RISK — THE PART THAT ACTUALLY MATTERS
=============================================================================

Full Kelly uses mu and Sigma as if known. They are not. That this is the
dominant practical problem is not this module's opinion:

  [T06] section 7.3, p. 411, verbatim: "To the extent m_e is an uncertain
  estimate of m_t, it is wise to assume m_t < m_e and to choose f < f_e* by
  enough to prevent g <= 0. Estimates of m_e in the stock market have many
  uncertainties and, in cases of forecast excess return, are more likely to
  be too high than too low. ... Systems that worked may be partly or
  entirely based on data mining so m_t may be substantially less than m_e."
  And p. 417, verbatim: "because 'overbetting' is much more harmful than
  underbetting, 'fractional Kelly' is prudent to the extent the results of
  the Kelly calculations reflect uncertainties."

  [T06] p. 411 also gives the concrete disaster case, verbatim: "A disaster
  occurs when m_t = .5 m_e but we choose f = 1.5 f_e*. This combines
  overbetting f_e* by 50% with the overestimate of m_e = 2 m_t. Then
  g = -.75 and we will be ruined."

  [Z11] abstract, verbatim: "Great sensitivity to parameter estimates,
  especially the means, makes the strategy dangerous to those whose
  estimates are in error and leads them to poor betting and possible
  bankruptcy."

  [Z11] p. 17, quoting Chopra and Ziemba (1993) — SECOND-HAND, that paper
  was not read: "errors in the means average about 20 times in importance
  in objective value than errors in co-variances with errors in variances
  about double the co-variance errors. This is dangerous enough but they
  also show that the relative importance of the errors is risk aversion
  dependent with the errors compounding more and more for lower risk
  aversion investors and for the extreme log investors with essentially
  zero risk aversion the errors are worth about 100:3:1. So log investors
  must estimate means well if they are to survive."
  That last clause is the sharpest single statement of why FULL Kelly
  specifically — not mean-variance generally — is the dangerous case: the
  penalty for mis-estimating mu is WORST at exactly the risk aversion Kelly
  picks.

HOW MUCH TO SHRINK, ANALYTICALLY. Two results, one derived here and one
transcribed:

  (i) THIS MODULE'S OWN DERIVATION (not from any source; verified against
      simulation in the tests). Hold Sigma fixed at truth and let only mu
      be estimated from T years of data, so mu_hat ~ N(mu, Sigma/T). Plug
      in pi = c Sigma^-1(mu_hat - r 1). Then, using
      E[(mu_hat - r)'Sigma^-1(mu - r)] = theta^2 and
      E[(mu_hat - r)'Sigma^-1(mu_hat - r)] = theta^2 + N/T
      (the second because E[e'Sigma^-1 e] = tr(Sigma^-1 Sigma/T) = N/T):

          E[g(c)] - r = theta^2 (c - c^2/2) - c^2 N / (2T)

      which is maximized at

          c*_mu-only = theta^2 / (theta^2 + N/T)

      i.e. shrink by exactly the fraction of the plug-in squared Sharpe
      that is real rather than noise. This is implemented as
      growth_optimal_kelly_fraction(..., include_covariance_penalty=False).

 (ii) [P10] eqs. (2.16)-(2.17), attributed there to Kan and Zhou (2007)
      section II.B — SECONDARY SOURCE, see the sourcing limit above. With
      BOTH mu_hat and Sigma_hat estimated (mu_hat ~ N(mu, Sigma/T),
      Sigma_hat ~ W_N(T-1, Sigma)/T, i.e. the divide-by-T maximum-
      likelihood covariance, [P10] eqs. 2.9-2.10), the expected
      out-of-sample utility of the scaled plug-in rule
      w_hat = (c/gamma) Sigma_hat^-1 mu_hat is, verbatim from [P10] (2.16):

        E[U(w_hat)] = (c theta^2/gamma)(T/(T-N-2))
                      - (c^2/(2 gamma))(theta^2 + N/T)
                        [T^2(T-2) / ((T-N-1)(T-N-2)(T-N-4))]

      maximized, [P10] (2.17), at

        c* = [(T-N-1)(T-N-4) / (T(T-2))] (theta^2 / (theta^2 + N/T))

      valid for T > N + 4. Note the structure: it is EXACTLY this module's
      (i) multiplied by an extra factor < 1 that accounts for the bias of
      Sigma_hat^-1. So estimating the covariance too makes the optimal bet
      SMALLER STILL. gamma = 1 is the Kelly case ([T06]'s U = m - s^2/2),
      and the formula is gamma-free anyway, so c* transfers unchanged.

      TWO CHECKS ON THAT TRANSCRIPTION, because it comes from a secondary
      source. (a) ALGEBRAIC, done here: (2.17) really is the argmax of
      (2.16). Differentiating (2.16) in c and solving gives
          c* = [theta^2 T/(T-N-2)] / [(theta^2 + N/T) K],
          K = T^2(T-2)/((T-N-1)(T-N-2)(T-N-4)),
      in which the (T-N-2) cancels and T/T^2 collapses to 1/T, leaving
      exactly (2.17). A garbled transcription would not have been
      self-consistent under differentiation. (b) NUMERICAL: the Monte Carlo
      below reproduces c* to within one grid step in both of its
      configurations.

  ONE NOTATIONAL DETAIL, since the two formulas count different things:
  N/T in the mu-noise term is N over the span in YEARS (mu and Sigma are
  per-year quantities, so mu_hat's covariance is Sigma/T_years), while
  [P10]'s covariance factor counts OBSERVATIONS. For daily data those
  differ by 252. growth_optimal_kelly_fraction() takes both.
  A SECOND, SMALLER ONE, recorded because it is a real discrepancy and not
  a rounding: [P10] eq. (2.8) defines Sigma_hat with a 1/T divisor, while
  this module (and optimizer.py, and pandas .cov()) uses 1/(T-1). That
  rescales the plug-in weights by (T-1)/T, i.e. shifts the effective c by
  0.08% at T = 1260. Below the resolution of anything measured here, but
  stated rather than glossed.

  NUMBERS, so the shrinkage is concrete rather than abstract. At the real
  12-ETF, 5-years-of-daily configuration measured below, where
  theta_hat = 1.5213:

      theta_hat^2 = 2.3142,  N/T_years = 12/4.976 = 2.4115
      c*_mu-only  = 2.3142 / (2.3142 + 2.4115)       = 0.4897
      c*_KanZhou  = 0.4897 * 0.97857                 = 0.4792  (T = 1254)

  and at a more ordinary theta = 0.6 on the same N and T:
      c*_mu-only = 0.36 / (0.36 + 2.4115) = 0.1300.

  So the growth-optimal fraction on a realistically-sized universe with an
  ordinary Sharpe is WELL BELOW the 0.5 this module ships as its default.
  0.5 is shipped anyway, because it is what [T06] and [Z11] actually
  recommend and because c* depends on the TRUE theta, which is exactly the
  thing nobody knows; growth_optimal_kelly_fraction() is exported so a
  caller can compute the smaller number for their own N, T and theta and
  decide for themselves.

  A TRAP WORTH NAMING, and it is not hypothetical — it bites hard on the
  real data below. Feeding the SAMPLE theta into c* is optimistic in
  exactly the dangerous direction, because E[theta_hat^2] = theta^2 + N/T:
  the same N/T that the formula is trying to penalize has already been
  added to its input. Deflating instead (theta^2 ~ max(theta_hat^2 - N/T,
  0)) gives 2.3142 - 2.4115 < 0, i.e. c* = 0 — "this universe shows no
  tangency edge that survives its own estimation error, hold cash". Both
  readings are reported below; neither is suppressed.
  `growth_optimal_kelly_fraction` therefore takes theta_squared as an
  explicit argument with this warning attached, rather than silently
  computing it from the sample.

MEASURED — MONTE CARLO DEMONSTRATION. Reproducible via
estimation_risk_monte_carlo; every number below is that function's actual
output at seed 12345, and the load-bearing ones are re-asserted, at a
reduced trial count, in tests/test_kelly_sizing.py.
(Independent re-run, 2026-08-29 verification pass, same seed and configs:
every cell reproduced digit-for-digit EXCEPT two probability cells that
moved by one trial in 4,000 — config A's P(end<50%) at c = 0.5 read 49.9%
against the 49.8% below, and config B's at c = 0.25 read 0.2% against
0.3%. Both sit at the 0.5x-wealth counting threshold, so a one-trial
floating-point-environment difference flips the rounded digit; every
median, mean, and both predicted c* columns matched exactly.)

  Design, per trial (4,000 trials per configuration):
    1. draw T i.i.d. normal per-period return vectors from a KNOWN true
       (mu/252, Sigma/252);
    2. estimate mu_hat and Sigma_hat from that sample ALONE;
    3. form pi_hat = Sigma_hat^-1(mu_hat - r 1) — the plug-in full-Kelly
       portfolio, i.e. exactly what an unwary user of kelly_weights gets;
    4. for each fraction c, compute the TRUE growth rate
       g(c pi_hat) = r + c pi_hat'(mu - r) - (c^2/2) pi_hat' Sigma pi_hat
       in closed form, using the truth the estimator never saw;
    5. simulate a 5-year forward wealth path at that c, driving EVERY c in
       the trial with the same pi_hat AND the same standard-normal shock
       sequence, so rows differ only in bet size.

  CONFIGURATION A — 10 assets, 5 years of daily data. True annual mu
  linear on [7%, 13%], true vols linear on [16%, 30%], equicorrelation
  0.35, r = 4%. True theta = 0.4183, so the ORACLE growth rate (full Kelly
  on the TRUE parameters) is r + theta^2/2 = 0.1275.

     c     median g   mean g   P(g<r)  median W_5y  P(end<50%)  P(maxDD>50%)
    0.10    0.0466    0.0461    34.4%     1.251        0.5%         3.1%
    0.25    0.0193    0.0136    68.2%     1.070       17.6%        67.1%
    0.50   -0.1330   -0.1515    97.7%     0.505       49.8%        98.2%
    1.00   -0.8318   -0.8983   100.0%     0.016       84.6%       100.0%
    1.50   -2.0516   -2.2004   100.0%     0.000       95.7%       100.0%
    2.00   -3.8014   -4.0578   100.0%     0.000       99.0%       100.0%

  THIS IS THE HEADLINE AND IT IS BRUTAL. Plug-in FULL KELLY on a perfectly
  well-specified, stationary, i.i.d.-normal 10-asset universe, estimated
  from five clean years of daily data, DESTROYS 98.4% OF CAPITAL IN THE
  MEDIAN over the following five years, while the same universe run at the
  true parameters would have compounded at 12.75%/yr. Even HALF Kelly
  halves capital in the median. The growth-optimal fraction here is 0.08 —
  one twelfth of Kelly — and at that fraction the median result is a
  respectable 4.66%/yr.
  The mechanism is not subtle: mu_hat's annual standard error is
  vol/sqrt(5) ~ 9%, against true excess returns of 3%-9%. mu_hat is mostly
  noise, so Sigma_hat^-1(mu_hat - r) is mostly a large random vector.

  CONFIGURATION B — the friendlier case, so the table above is not
  mistaken for an artifact of a hopeless universe. 5 assets, 10 years of
  daily data, true mu linear on [12%, 20%], vols on [15%, 25%],
  equicorrelation 0.15, r = 4%. True theta = 1.0530 (a genuinely strong
  edge), oracle growth rate 0.5944.

     c     median g   mean g   P(g<r)  median W_5y  P(end<50%)  P(maxDD>50%)
    0.25    0.2677    0.2659     0.1%     3.589        0.3%        15.3%
    0.50    0.4021    0.3916     0.3%     6.540        3.1%        79.2%
    1.00    0.3779    0.3423     4.9%     5.422       18.7%        99.5%
    1.50   -0.0222   -0.1081    56.2%     0.817       45.9%        99.9%
    2.00   -0.7773   -0.9594    89.5%     0.019       70.5%       100.0%

  Here the classic textbook comparison appears cleanly, and it is the exact
  demonstration the task asked for:
    - HALF KELLY BEATS FULL KELLY ON GROWTH ITSELF, 0.4021 vs 0.3779 in
      the median (0.3916 vs 0.3423 in the mean). Not on risk-adjusted
      growth, not under some other utility — on the very quantity full
      Kelly is defined to maximize. Same estimation noise in both rows,
      same market paths; the only difference is bet size. The plug-in bet
      is systematically too big, so cutting it improves the outcome.
    - AND IT IS FAR SAFER AT THE SAME TIME. P(ending below half of
      starting capital) 3.1% vs 18.7%; median terminal wealth 6.54x vs
      5.42x. There is no trade-off being made here at all — full Kelly is
      dominated, because it is not actually full Kelly, it is full Kelly's
      formula fed a noisy input.
    - THE ORACLE CEILING, 0.5944, is still well above the best achievable
      0.4021. That gap — 32% of the theoretical growth rate — is the cost
      of estimation that NO choice of c can recover, and it is reported
      because quoting only the half-vs-full comparison would flatter the
      method.
    - AT c = 2 THE MEDIAN INVESTOR LOSES ALMOST EVERYTHING (median
      terminal wealth 0.019x, 89.5% of trials below cash). That is [Z11]'s
      "twice this amount has a growth rate of zero" plus estimation error
      pushing it well below zero.

  THE PREDICTED OPTIMUM CHECKS OUT, IN BOTH CONFIGURATIONS. Fine sweeps of
  the same Monte Carlo (4,000 trials, seed 12345) against the two analytic
  formulas above:

      config   c* mu-only   c* Kan-Zhou/[P10]   empirical argmax of mean g
      A          0.0804         0.0790          0.0800  (grid step 0.01)
      B          0.6892         0.6857          0.7000  (grid step 0.025)

  Config A pins the prediction to within one grid step of 0.01 on a
  formula transcribed from a SECONDARY source. That is why [P10] is used
  at all: it is checked, not trusted. (The two formulas are within 2% of
  each other at these T, so this run confirms the shared theta^2/(theta^2 +
  N/T) core sharply and the [P10] covariance factor only weakly.)
  ONE TENSION, NOT HIDDEN: in config B the MEDIAN growth rate peaks at
  c = 0.725 rather than 0.700. The analytic c* maximizes the MEAN, and the
  mean and median of a skewed growth distribution do not have to agree.
  Quoting c* as "the optimum" without that qualifier would be sloppy.

  HONEST LIMITS OF THIS DEMONSTRATION, stated because they all cut the same
  way — the real world is worse, not better:
    - Returns are drawn i.i.d. normal, which is the model's own assumption.
      No fat tails, no jumps, no vol clustering, no regime change.
    - mu and Sigma are CONSTANT and the estimator is unbiased for them.
      [T06] p. 411's central practical point — that real mu estimates are
      "more likely to be too high than too low", from data mining and from
      capital chasing returns — is NOT modelled here at all. Adding a
      downward bias to the truth would move every row down and push c*
      lower still.
    - Rebalancing is continuous and frictionless; no costs, no slippage,
      no borrow cost on the levered part. This project has a cost model
      (risk/edge_cost_model wiring, commit 214a58c) that is deliberately
      NOT wired in here — see KNOWN LIMITS.
    - Wealth follows a geometric Brownian motion, so it CANNOT reach zero
      at any finite leverage. "Ruin" in the table means a drawdown
      threshold, never literal bankruptcy. [T06] p. 413's own framing of
      the discrete-jump danger ("In the crash of October, 1987, the S&P 500
      index dropped 23% in a single day. If this happened at leverage of
      2.0, the new leverage would suddenly be 77/27 = 2.85 before
      readjustment") is exactly the mechanism this simulation excludes.

  SIMULATOR VALIDATION AGAINST A PUBLISHED CLOSED FORM. simulate_wealth_paths
  is not merely self-consistent with the rest of this module: driven with
  the TRUE parameters (no estimation error), one risky asset, r = 0, it
  must reproduce [T06] eq. (7.13),
      Prob(V(t, c f*)/V_0 <= x for some t) = x^(2/c - 1).
  Measured at m = 0.10, s = 0.20 (so f* = m/s^2 = 2.5), x = 0.5:

      horizon   dt        paths     c=0.5           c=1.0           c=1.5
      40 yr    1/252     40,000   0.1220/0.1250   0.4819/0.5000   0.7545/0.7937
     200 yr    1/252     20,000   0.1222/0.1250   0.4851/0.5000   0.7865/0.7937
      40 yr    1/2520    20,000   0.1213/0.1250   0.4822/0.5000   0.7561/0.7937
                                  (simulated / [T06] (7.13) predicted)

  Every cell is slightly LOW, always in the same direction, and the third
  row identifies which of the two candidate causes it is: refining the time
  step tenfold changes essentially nothing (0.7545 -> 0.7561), while
  extending the horizon fivefold closes most of the c = 1.5 gap
  (0.7545 -> 0.7865). So the residual is FINITE-HORIZON TRUNCATION of an
  "ever" probability, not discrete monitoring of a continuous path. The
  c = 1.0 row stays ~3% low even at 200 years because at c = 1 the ratio
  2 g_inf / Var(G_inf) is exactly 1 and the hitting time is heavy-tailed.
  Recorded as measured rather than tuned away; this check is in the tests
  at a reduced path count.

=============================================================================
RMT-DENOISED COVARIANCE — WHY IT IS OFFERED HERE
=============================================================================

Kelly needs Sigma^-1, so it is exposed to covariance estimation error
through a matrix inverse — the most error-amplifying operation available.
This module therefore accepts `denoise=True` on the from-returns entry
points, which routes the sample covariance through
rmt_denoising.denoise_covariance_matrix (REUSED, not reimplemented) before
inverting it. Default is False, so every call that does not opt in is
bit-identical to a build without the option.

NO SOURCE COMBINES RMT DENOISING WITH KELLY SIZING. Same disclosure
hrp_optimizer.py makes about denoising + HRP: Lopez de Prado's denoising
work sits ahead of a quadratic optimizer, and neither [M69], [T06] nor
[Z11] mentions random matrix theory. The composition is this project's own
option to be measured, not an authority-backed recommendation.

AND ON THE REAL UNIVERSE BELOW IT IS AN HONEST NEGATIVE, reported as
found rather than quietly dropped. Denoising did exactly what it says on
the tin to the SPECTRUM — the condition number of Sigma fell from 479.7 to
125.9 (q = T/N = 104.5, fitted sigma^2 saturated at its upper bound, 3
signal eigenvalues, 9 collapsed) — and it did essentially NOTHING to the
problem this module cares about:

    gross leverage  43.17x  ->  42.87x   (-0.7%)
    net exposure    -4.80x  ->  -7.29x   (further out, not nearer home)
    growth rate      1.197  ->   1.340   (the estimate got MORE absurd)

The individual weights moved a great deal (SPY +11.80 -> +5.46, GLD +6.62
-> +8.54), so denoising is not inert; it REDISTRIBUTES the leverage
without reducing it. The reason is visible in the numbers: at N = 12 and
T = 1254, the covariance matrix is not the binding source of error at all
— mu is (N/T_years = 2.41 against theta_hat^2 = 2.31). Denoising cannot
fix a mean-estimation problem, and [Z11]'s quotation of Chopra and Ziemba
above says as much in advance: for a log investor the error weights are
about 100:3:1, means:variances:covariances. NO CLAIM IS MADE THAT
DENOISING HELPS KELLY SIZING. On this evidence it does not.

=============================================================================
MEASURED ON THIS PROJECT'S REAL DATA — reported as found, not curated
=============================================================================

Universe: 12 liquid cross-asset ETFs (SPY, QQQ, IWM, EFA, EEM, TLT, IEF,
LQD, HYG, GLD, DBC, VNQ), 5 years of daily adjusted closes pulled through
this codebase's own path (YFinanceProvider.get_price_history ->
risk/returns.compute_daily_returns), annualized with
volatility.TRADING_DAYS_PER_YEAR exactly the way optimizer.py does. T =
1,254 overlapping days, N = 12, window 2021-08-31 to 2026-08-28. r = 4%,
a round number chosen here rather than a fetched rate — flagged, and note
that r moves every number below.

  Estimated max Sharpe of the unconstrained tangency portfolio:
      theta_hat = 1.5213   (theta_hat^2 = 2.3142)
  Implied full-Kelly growth rate r + theta^2/2 = 119.7%/yr. That number is
  the tell, and it should be read as a diagnostic rather than a forecast:
  nothing in this universe compounds at 120% a year. It comes out that way
  because theta_hat^2 is inflated by N/T_years = 2.4115, which is 104% of
  the whole estimate. Deflating (see THE TRAP above) leaves
  theta^2 <= 0 — the honest reading is that FIVE YEARS OF DAILY DATA ON
  TWELVE ETFS ESTABLISHES NO TANGENCY EDGE THAT SURVIVES ITS OWN
  ESTIMATION ERROR.

  Full Kelly (c = 1) from the raw sample covariance:
      gross leverage sum|w|         43.17x
      net exposure  sum w           -4.80x  (so 580% notionally in cash)
      largest long                 +11.80   (SPY)
      largest short                -11.48   (IEF)
      portfolio vol                152.1%/yr   ( == theta_hat, exactly)
      condition number of Sigma      479.7

  Half Kelly (c = 0.5), the shipped default: every weight is exactly
  halved — 21.58x gross, -2.40x net, 76.1% vol. Still uninvestable.
  (That "exactly halved" is the fractional-Kelly proportionality above,
  visible on real data.)

  [P10]/Kan-Zhou c* at this N, T and theta_hat: 0.4792, giving 20.69x
  gross. Using the DEFLATED theta^2 instead gives c* = 0.0000, i.e. hold
  cash. Both are computed and both are reported; the first is what the
  formula says fed the naive input, the second is what it says fed the
  honest one, and the gap between them is the entire lesson.

  IS THIS ECONOMICALLY SANE? NO — AND THAT IS THE FINDING, NOT A BUG. A
  43x-gross book out of twelve ETFs, long 1,180% of SPY against short
  1,148% of a 7-10y Treasury fund, is a pure estimation-error artifact:
  Sigma^-1 hands the tiny, unreliable differences between highly
  correlated sample means enormous weight. This is the textbook Markowitz
  corner solution that optimizer.py's DEFAULT_MAX_WEIGHT = 0.4 comment
  already names ("Unconstrained mean-variance optimization is well known
  to produce degenerate corner solutions ... under estimation error"),
  arriving unconstrained because Kelly has no cap and no sum-to-one.
  It also independently reproduces [T06]'s own real-data experience.
  [T06] Table 8 (printed p. 417), unrestricted-borrowing column: Berkshire
  6.26, BioTime 1.18, S&P 500 12.61, T-bills -19.04 — on THREE securities —
  and [T06]'s verdict on it, verbatim from the paragraph that introduces
  that table (p. 416): "If unrestricted borrowing were allowed it would be
  foolish to choose the corresponding portfolio in Table 8."
  When Thorp calls the unconstrained full-Kelly portfolio foolish on his
  own data, a module that produced a comfortable number on this data would
  be the one that was wrong.

  APPLIED TO A NORMALIZED DIRECTION INSTEAD — the intended use, see API
  DESIGN. kelly_leverage_for_weights on the same returns, for three
  directions this codebase can already produce:

    direction                      m - r      s      Sharpe   lambda*  half
    HRP (compute_hrp_weights..)   +0.0025  0.0833   0.0295    0.354   0.177
    equal weight                  +0.0354  0.1100   0.3218    2.926   1.463
    optimizer.py max-Sharpe       +0.1203  0.1268   0.9482    7.476   3.738
    SPY alone                     +0.0951  0.1720   0.5530    3.216   1.608

  Read these, because they are the argument for the whole API shape:
    - HRP's 0.354 is the module WORKING. HRP allocated 63% of the book to
      IEF/LQD/HYG, all of which had negative or ~zero excess returns over
      this window, so the portfolio's Sharpe is 0.03 and Kelly's answer is
      "hold 35% of it and 65% cash". A sizing tool that cannot say
      "less than fully invested" is not a sizing tool.
    - optimizer.py's 7.48x is the module reporting an IN-SAMPLE Sharpe of
      0.95 faithfully, and should be read with the same suspicion as the
      43x: those weights were fitted to this same window.
    - SPY alone gives 3.22x, against [T06]'s own 2.22x for the S&P 500 at
      m = .11, s = .15, r = .06 ([T06] Example 7.2, p. 409) and [Z11]'s
      1.5288x for 1926-2001 US equities. Same order of magnitude, higher
      here because 2021-2026 SPY realized a 0.55 Sharpe. That agreement
      with two published worked examples is the closest thing to an
      external check on the real-data path.
    - EVERY leverage above 2 breaches [T06] eq. (8.3)'s margin constraint
      |f_1| + ... + |f_n| <= 1/q at the q = 50% initial margin [T06]
      p. 413 calls "the maximum initial leverage allowed 'customers' under
      current regulations". This module does not impose that constraint;
      it reports numbers a caller must check against it.

  HOW REPRODUCIBLE ARE THOSE NUMBERS? Independently recomputed the same
  session through a DIFFERENT code path — raw pandas pct_change instead of
  risk/returns.compute_daily_returns, np.cov instead of DataFrame.cov,
  an explicit np.linalg.inv instead of the module's np.linalg.solve, and a
  fresh price fetch:
      theta 1.5213 -> 1.5214,  gross 43.17 -> 43.21,  net -4.80 -> -4.80,
      vol 1.5213 -> 1.5214,  cond 479.7 -> 479.7 (exact),
      SPY +11.805 -> +11.806,  IEF -11.477 -> -11.453,
      SPY-alone lambda* 3.2165 -> 3.2162.
  Same T = 1254, so the ~0.1% drift is the provider restating recent
  adjusted closes between two fetches minutes apart, not a code
  discrepancy. Read every real-data figure here as "about this", to two
  or three significant figures, never as a per-run prediction — the same
  caveat rmt_denoising.py records for its own real-universe numbers.

=============================================================================
API DESIGN — why sizing is NOT bolted onto the existing weight functions
=============================================================================

compute_portfolio_optimization_from_returns and
compute_hrp_weights_from_returns both promise weights that sum to 1. Kelly
weights do not, cannot and must not: their whole content is that the sum is
a decision. Three consequences shaped this API.

  1. TWO ENTRY POINTS, NOT ONE, because there are genuinely two questions.
     - kelly_weights(mu, cov, r, c) answers "direction AND scale from
       scratch", returning the raw c * Sigma^-1(mu - r 1). This is the
       faithful [M69] eq. (60) / [T06] eq. (8.2) object. It is the one that
       produced the 43.17x above, and it is exported mainly so the closed
       form is available and testable — not because it is the recommended
       way to run money.
     - kelly_leverage_for_weights(w, mu, cov, r, c) answers "I already have
       a direction from HRP or mean-variance; how much of it?" It takes
       weights that sum to 1, treats the portfolio as [T06] section 7's
       single composite risky asset, and returns the scalar
           lambda* = w'(mu - r 1) / (w' Sigma w)
       which is [T06] eq. (7.3)'s f* = (m - r)/s^2 with m - r = w'(mu - r)
       and s^2 = w'Sigma w. NO NEW MATHEMATICS — it is the one-asset Kelly
       formula applied to the composite, which is exactly what [T06]
       section 8.4 says the multi-asset case reduces to. THIS is the
       function that composes cleanly with everything already in the
       codebase, and it is the one the module docstring recommends.
     Keeping them separate rather than overloading one function means a
     caller can never accidentally read a leverage as a weight.

  2. THE RESULT TYPES DO NOT PRETEND TO BE OptimizationResult.
     hrp_optimizer.py deliberately mirrors optimizer.py's OptimizationResult
     so the two are comparable like with like. This module deliberately
     does NOT, because pouring a 43x-gross vector into a container whose
     consumers assume sum(w) = 1 is how a leverage decision silently
     becomes a weight. KellySizingResult and KellyLeverageResult are
     separate dataclasses that report gross_leverage, net_exposure and
     risk_free_weight as first-class fields precisely so the scale cannot
     be overlooked.

  3. NOTHING IS CLAMPED. Negative expected excess return gives a negative
     lambda*; a fraction above 1 gives a growth rate below the full-Kelly
     one and, past 2, below the risk-free rate. All reported, none
     silently fixed, same posture as the rest of risk/: degenerate inputs
     are refused with an explanatory ValueError, but VALID inputs with
     alarming answers are reported as they are.

KNOWN LIMITS, each real and none patched over:
  - r is a caller-supplied constant, and [M69]'s model has ONE riskless
    rate for both lending and borrowing. Real borrow costs more; [T06]
    p. 410 measures exactly this and finds it decisive, verbatim: "We
    replace r by r_b in Equations (7.7) and, if f* > 1, f* = 1.33 ... Note
    how greatly f* is reduced." (from 2.22 to 1.33 on his S&P example, a
    40% cut, purely from a 2% borrow spread). NOT MODELLED HERE. Any
    leverage above 1 that this module reports is therefore an OVERSTATEMENT
    of what is actually optimal, by a margin [T06] shows can be large.
    This is also why the outstanding "real securities-borrow rate feed"
    item in this project's paid-decisions list matters for this module
    specifically.
  - No transaction costs, no market impact, no taxes, no discrete
    rebalancing. [T06] p. 413 on the last of these: "Leverage to the level
    6.22 would be inadvisable here in the real world because securities
    prices may change suddenly and discontinuously."
  - Constant opportunity set only ([M69] section VII). No intertemporal
    hedging demand, which is [M71]'s subject.
  - Sigma^-1 is computed by np.linalg.solve, not by forming an explicit
    inverse, and the condition number is REPORTED rather than acted on.
    A caller staring at cond = 479.7 is being told something.

PURE FUNCTIONS. Nothing here reads a database or mutates an input.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.services.risk.engine import MIN_OBS_FOR_ANY_ESTIMATE
from app.services.risk.errors import InsufficientHistoryError
from app.services.risk.rmt_denoising import (
    DEFAULT_KDE_BANDWIDTH,
    RMTDenoiseResult,
    denoise_covariance_matrix,
)
from app.services.risk.volatility import TRADING_DAYS_PER_YEAR

# [T06] section 7.3 / [Z11] p. 8: half Kelly is the practitioner
# convention, NOT a derived optimum. See "WHY THE DEFAULT IS 0.5" in the
# module docstring — and note that growth_optimal_kelly_fraction() will
# usually return something SMALLER for a realistic N, T and Sharpe.
DEFAULT_KELLY_FRACTION = 0.5

# [Z11] p. 8, verbatim: "the investor who wagers exactly twice this amount
# has a growth rate of zero plus the risk-free rate of interest".
# Equivalently [T06] (7.6): g(c f*)/g(f*) = c(2 - c), which is 0 at c = 2.
ZERO_GROWTH_KELLY_MULTIPLE = 2.0


@dataclass
class KellySizingResult:
    """One full/fractional Kelly allocation from a (mu, Sigma, r) triple.

    `weights` DO NOT SUM TO 1 and must never be treated as if they do —
    that is the entire content of the method. gross_leverage, net_exposure
    and risk_free_weight are first-class fields for exactly that reason
    (see API DESIGN in the module docstring)."""

    weights: dict[str, float]  # kelly_fraction * full_kelly_weights
    full_kelly_weights: dict[str, float]  # [M69] (60) at gamma_RRA = 1
    kelly_fraction: float
    risk_aversion: float  # 1 / kelly_fraction; [M69]'s delta, [Z11]'s R_R
    gross_leverage: float  # sum |w_i|  ([T06] (8.3)'s constrained quantity)
    net_exposure: float  # sum w_i
    risk_free_weight: float  # 1 - sum w_i  ([T06] (8.1)'s f_0)
    expected_excess_return: float  # w'(mu - r 1)
    volatility: float  # sqrt(w' Sigma w)
    growth_rate: float  # r + w'(mu - r) - w'Sigma w / 2   ([T06] 8.1/8.2)
    full_kelly_growth_rate: float  # r + theta^2 / 2
    max_sharpe: float  # theta = sqrt((mu-r)'Sigma^-1(mu-r))
    condition_number: float  # of Sigma; reported, never acted on
    # None unless denoising was explicitly requested. Present for the same
    # reason HRPResult.denoise is: a weight vector carries no evidence of
    # which matrix produced it.
    denoise: RMTDenoiseResult | None = None


@dataclass
class KellyLeverageResult:
    """The SCALE decision alone, for a direction someone else chose.

    This is the composition-friendly half of the API (see API DESIGN). The
    caller brings relative weights — HRP's, mean-variance's, equal-weight,
    anything — and gets back how much of that portfolio to hold."""

    kelly_fraction: float
    full_kelly_leverage: float  # lambda* = w'(mu - r) / w'Sigma w
    leverage: float  # kelly_fraction * full_kelly_leverage
    scaled_weights: dict[str, float]  # leverage * w
    # The composite risky asset's own statistics, in [T06] section 7's
    # notation: m - r, s, and their ratio.
    portfolio_excess_return: float
    portfolio_volatility: float
    portfolio_sharpe: float
    growth_rate: float  # at `leverage`
    full_kelly_growth_rate: float  # at `full_kelly_leverage`
    # 2 * lambda*: the leverage at which variance drag has eaten the whole
    # edge and the growth rate is back to r ([Z11] p. 8).
    zero_growth_leverage: float
    denoise: RMTDenoiseResult | None = None


@dataclass
class KellyMonteCarloRow:
    """One Kelly fraction's outcomes across all Monte Carlo trials."""

    kelly_fraction: float
    median_growth_rate: float
    mean_growth_rate: float
    prob_growth_below_risk_free: float
    median_terminal_wealth: float
    p05_terminal_wealth: float
    prob_terminal_below_half: float
    prob_max_drawdown_over_half: float
    mean_max_drawdown: float


@dataclass
class KellyMonteCarloResult:
    """Output of estimation_risk_monte_carlo.

    `oracle_growth_rate` is r + theta^2/2 computed on the TRUE parameters —
    the ceiling no estimator can reach. Reported alongside the rows so the
    fractional-vs-full comparison is never quoted without the much larger
    number that estimation error costs regardless of c."""

    rows: list[KellyMonteCarloRow]
    true_max_sharpe: float
    oracle_growth_rate: float
    n_trials: int
    n_assets: int
    estimation_obs: int
    horizon_obs: int
    periods_per_year: float
    risk_free_rate: float
    # The analytic predictions from the module docstring's ESTIMATION RISK
    # section, computed for this design so the table can be read against
    # them without a second call.
    predicted_optimal_fraction_mu_only: float
    predicted_optimal_fraction_kan_zhou: float


def _validate_inputs(mu: pd.Series, cov: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Input guards — module additions, not steps in any source. [M69]
    p. 255 simply declares Omega "symmetric and positive definite" and
    [T06] (8.2) requires only "det C != 0"; neither specifies handling for
    degenerate input, so degenerate input is REFUSED, never patched.
    Deliberately mirrors hrp_optimizer._validate_cov's posture."""
    if cov.shape[0] != cov.shape[1]:
        raise ValueError(f"covariance matrix must be square, got {cov.shape}")
    if list(cov.index) != list(cov.columns):
        raise ValueError("covariance matrix index and columns must match (same assets, same order)")
    if list(mu.index) != list(cov.columns):
        raise ValueError(
            "mu's index must match the covariance matrix's assets, in the same order; "
            f"got {list(mu.index)} vs {list(cov.columns)}"
        )
    if len(set(cov.columns)) != len(cov.columns):
        raise ValueError("covariance matrix has duplicate asset labels")

    cov_values = cov.to_numpy(dtype=float)
    mu_values = mu.to_numpy(dtype=float)
    if not np.isfinite(cov_values).all():
        raise ValueError(
            "covariance matrix contains NaN/inf — refused rather than silently filled "
            "(no source for this method specifies a fill convention)"
        )
    if not np.isfinite(mu_values).all():
        raise ValueError("expected-return vector contains NaN/inf")
    diag = np.diag(cov_values)
    if (diag <= 0).any():
        bad = [str(c) for c, v in zip(cov.columns, diag) if v <= 0]
        raise ValueError(
            f"non-positive variance for {', '.join(bad)} — Sigma cannot be positive "
            "definite, so Sigma^-1(mu - r 1) is undefined"
        )
    scale = max(1.0, float(np.abs(diag).max()))
    if not np.allclose(cov_values, cov_values.T, rtol=0.0, atol=1e-8 * scale):
        raise ValueError("covariance matrix is not symmetric")
    return mu_values, cov_values


def _solve_sigma_inverse_times(cov_values: np.ndarray, vector: np.ndarray) -> np.ndarray:
    """Sigma^-1 v via a linear solve rather than an explicit inverse.

    Mathematically identical to [M69] (60) / [T06] (8.2); numerically
    better conditioned, and the standard way to evaluate A^-1 b. The
    tests assert agreement with np.linalg.inv(Sigma) @ v on
    well-conditioned inputs."""
    try:
        return np.linalg.solve(cov_values, vector)
    except np.linalg.LinAlgError as exc:  # pragma: no cover - needs an exactly singular matrix
        raise ValueError(
            "covariance matrix is singular — Sigma^-1(mu - r 1) does not exist. "
            "[T06] section 8.4 names the usual cause: two assets that are exact "
            "linear combinations of each other (his example: BRK.A and BRK.B at a "
            "fixed 30:1 ratio) give det C = 0."
        ) from exc


def full_kelly_weights(
    mu: pd.Series, cov: pd.DataFrame, risk_free_rate: float
) -> pd.Series:
    """pi* = Sigma^-1 (mu - r 1) — [M69] eq. (60) at relative risk aversion
    1, identically [T06] eq. (8.2)'s F* = C^-1[M - R].

    mu and cov must be in the SAME time units as risk_free_rate (this
    codebase annualizes both with volatility.TRADING_DAYS_PER_YEAR). The
    result is invariant to that choice: scaling mu, r and Sigma all by the
    same k leaves Sigma^-1(mu - r) unchanged, because the k in the
    numerator cancels the k in Sigma^-1. Asserted in the tests.

    The returned weights DO NOT SUM TO 1. See the module docstring."""
    mu_values, cov_values = _validate_inputs(mu, cov)
    excess = mu_values - risk_free_rate
    weights = _solve_sigma_inverse_times(cov_values, excess)
    return pd.Series(weights, index=cov.columns)


def growth_rate(
    weights: pd.Series | np.ndarray,
    mu: pd.Series,
    cov: pd.DataFrame,
    risk_free_rate: float,
) -> float:
    """g(w) = r + w'(mu - r 1) - (1/2) w' Sigma w.

    [T06] eq. (8.1) defines m = r + F'(M - R) and s^2 = F'CF, and section
    8.4 states verbatim that "our previous formulas and results ... apply
    to g_inf(f_1, ..., f_n) = m - s^2/2". This is that expression written
    out. It is the drift of d(log W) under [M69] eq. (12)'s dynamics with
    C = 0, which is why it is also exactly what the Monte Carlo simulates."""
    _validate_inputs(mu, cov)
    w = np.asarray(
        weights.to_numpy(dtype=float) if isinstance(weights, pd.Series) else weights, dtype=float
    )
    excess = mu.to_numpy(dtype=float) - risk_free_rate
    variance = float(w @ cov.to_numpy(dtype=float) @ w)
    return float(risk_free_rate + w @ excess - 0.5 * variance)


def max_sharpe_ratio(mu: pd.Series, cov: pd.DataFrame, risk_free_rate: float) -> float:
    """theta = sqrt((mu - r 1)' Sigma^-1 (mu - r 1)).

    The Sharpe ratio of the UNCONSTRAINED tangency portfolio, and the only
    quantity the full-Kelly growth rate depends on: g(pi*) = r + theta^2/2
    ([T06] p. 407 for the one-asset form: "the maximum growth rate
    g_inf(f*) depends, for fixed r, only on the Sharpe ratio").

    ESTIMATION WARNING, this module's own and load-bearing downstream: the
    sample theta^2 is biased UP by N/T (E[theta_hat^2] = theta^2 + N/T for
    N assets and T years of data). On the real 12-ETF universe in the
    module docstring that inflation accounts for the entire estimate."""
    mu_values, cov_values = _validate_inputs(mu, cov)
    excess = mu_values - risk_free_rate
    quad = float(excess @ _solve_sigma_inverse_times(cov_values, excess))
    # Numerically, a positive-definite Sigma makes this non-negative; clip
    # only float noise at exactly-zero excess returns.
    return float(np.sqrt(max(quad, 0.0)))


def kelly_weights(
    mu: pd.Series,
    cov: pd.DataFrame,
    risk_free_rate: float,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
) -> KellySizingResult:
    """Fractional-Kelly weights c * Sigma^-1(mu - r 1) plus the diagnostics
    that say how levered they are.

    kelly_fraction c is EXACTLY 1/gamma_RRA ([Z11] p. 9's f = 1/R_R, and
    [M69] eq. (60)'s 1/(1 - gamma)); c = 1 is full Kelly / log utility,
    c = 0.5 is half Kelly / relative risk aversion 2. In this unconstrained
    lognormal setting the scaling is exact, so half-Kelly weights are
    exactly half of full-Kelly weights.

    c > 1 is ALLOWED and never silently clamped — the growth_rate field
    will show it degrading, and past c = 2 it drops below the risk-free
    rate ([Z11] p. 8) — but it is never the default. c <= 0 is refused:
    a non-positive fraction is not a smaller bet, it is a sign flip on the
    whole portfolio, which no source treats as a "fraction"."""
    if not np.isfinite(kelly_fraction) or kelly_fraction <= 0.0:
        raise ValueError(
            f"kelly_fraction must be finite and > 0; got {kelly_fraction}. A fraction of 0 "
            "means 'hold only the risk-free asset' (just do that) and a negative fraction "
            "inverts the portfolio rather than shrinking it."
        )
    full = full_kelly_weights(mu, cov, risk_free_rate)
    scaled = full * kelly_fraction

    theta = max_sharpe_ratio(mu, cov, risk_free_rate)
    cov_values = cov.to_numpy(dtype=float)
    w = scaled.to_numpy(dtype=float)
    excess = mu.to_numpy(dtype=float) - risk_free_rate

    return KellySizingResult(
        weights={str(k): float(v) for k, v in scaled.items()},
        full_kelly_weights={str(k): float(v) for k, v in full.items()},
        kelly_fraction=float(kelly_fraction),
        risk_aversion=float(1.0 / kelly_fraction),
        gross_leverage=float(np.abs(w).sum()),
        net_exposure=float(w.sum()),
        risk_free_weight=float(1.0 - w.sum()),
        expected_excess_return=float(w @ excess),
        volatility=float(np.sqrt(max(float(w @ cov_values @ w), 0.0))),
        growth_rate=float(risk_free_rate + w @ excess - 0.5 * float(w @ cov_values @ w)),
        full_kelly_growth_rate=float(risk_free_rate + 0.5 * theta**2),
        max_sharpe=theta,
        condition_number=float(np.linalg.cond(cov_values)),
    )


def kelly_leverage_for_weights(
    weights: dict[str, float] | pd.Series,
    mu: pd.Series,
    cov: pd.DataFrame,
    risk_free_rate: float,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
) -> KellyLeverageResult:
    """THE RECOMMENDED ENTRY POINT. Given RELATIVE weights someone else
    chose (HRP, mean-variance, equal-weight — anything summing to 1),
    return how much of that portfolio to hold.

    Treat the whole portfolio as [T06] section 7's single composite risky
    asset with m - r = w'(mu - r 1) and s^2 = w' Sigma w. Then
    g(lambda) = r + lambda(m - r) - (1/2) lambda^2 s^2 is a scalar
    quadratic, maximized at

        lambda* = (m - r) / s^2 = w'(mu - r 1) / (w' Sigma w)

    which IS [T06] eq. (7.3)'s f* = (m - r)/s^2. No new mathematics: the
    multi-asset formula reduces to this the moment the direction is fixed.

    NOT CLAMPED. If the portfolio's expected excess return is negative,
    lambda* is negative and the honest answer is "short it, or hold cash";
    the result reports it rather than flooring at zero. `weights` is not
    required to sum to 1 either — lambda* is invariant to rescaling w
    (numerator scales by k, denominator by k^2, product lambda*w
    unchanged), which the tests assert — but a caller passing an already-
    levered vector will get a lambda* that looks small, so passing
    normalized weights is the intended use."""
    if not np.isfinite(kelly_fraction) or kelly_fraction <= 0.0:
        raise ValueError(f"kelly_fraction must be finite and > 0; got {kelly_fraction}")
    _validate_inputs(mu, cov)

    w_series = pd.Series(weights) if not isinstance(weights, pd.Series) else weights
    if list(w_series.index) != list(cov.columns):
        # Reindex rather than refuse: a caller composing with
        # hrp_optimizer.compute_hrp_weights_from_returns gets a dict, whose
        # ordering is the caller's, not the covariance matrix's. Missing
        # names are an error, not a zero.
        missing = set(map(str, cov.columns)) - set(map(str, w_series.index))
        if missing:
            raise ValueError(f"weights are missing assets present in the covariance: {sorted(missing)}")
        extra = set(map(str, w_series.index)) - set(map(str, cov.columns))
        if extra:
            raise ValueError(f"weights contain assets absent from the covariance: {sorted(extra)}")
        w_series = w_series.reindex(cov.columns)

    w = w_series.to_numpy(dtype=float)
    if not np.isfinite(w).all():
        raise ValueError("weights contain NaN/inf")
    excess = mu.to_numpy(dtype=float) - risk_free_rate
    portfolio_excess = float(w @ excess)
    portfolio_variance = float(w @ cov.to_numpy(dtype=float) @ w)
    if portfolio_variance <= 0.0:
        raise ValueError(
            "the supplied weights have zero portfolio variance — lambda* = (m - r)/s^2 "
            "is undefined (an all-zero weight vector, or an exact hedge)"
        )
    portfolio_vol = float(np.sqrt(portfolio_variance))

    full_leverage = portfolio_excess / portfolio_variance
    leverage = kelly_fraction * full_leverage

    def _g(lev: float) -> float:
        return float(risk_free_rate + lev * portfolio_excess - 0.5 * lev**2 * portfolio_variance)

    return KellyLeverageResult(
        kelly_fraction=float(kelly_fraction),
        full_kelly_leverage=float(full_leverage),
        leverage=float(leverage),
        scaled_weights={str(k): float(v) for k, v in (w_series * leverage).items()},
        portfolio_excess_return=portfolio_excess,
        portfolio_volatility=portfolio_vol,
        portfolio_sharpe=float(portfolio_excess / portfolio_vol),
        growth_rate=_g(leverage),
        full_kelly_growth_rate=_g(full_leverage),
        zero_growth_leverage=float(ZERO_GROWTH_KELLY_MULTIPLE * full_leverage),
    )


def growth_optimal_kelly_fraction(
    theta_squared: float,
    n_assets: int,
    n_years: float,
    n_obs: int | None = None,
    include_covariance_penalty: bool = True,
) -> float:
    """The Kelly fraction that maximizes EXPECTED out-of-sample growth once
    mu (and optionally Sigma) are estimated rather than known.

    Two formulas, selected by include_covariance_penalty:

      False -> c* = theta^2 / (theta^2 + N/T_years)
        THIS MODULE'S OWN DERIVATION (see ESTIMATION RISK in the module
        docstring), assuming Sigma known and mu_hat ~ N(mu, Sigma/T_years).
        Verified against this module's Monte Carlo in the tests. Not from
        any source.

      True (default) -> that, times (T-N-1)(T-N-4) / (T(T-2)) with T =
        n_obs, the additional shrinkage for an estimated Sigma.
        [P10] eq. (2.17), attributed there to Kan and Zhou (2007) section
        II.B. SECONDARY SOURCE — the JFQA paper itself was not read this
        session (see the module docstring's sourcing limit). Requires
        n_obs > n_assets + 4, [P10]'s own stated condition.

    theta_squared IS THE *TRUE* SQUARED MAXIMUM SHARPE, and this argument
    is deliberately not defaulted to a sample estimate: E[theta_hat^2] =
    theta^2 + N/T_years, so feeding the sample value in makes c* too LARGE
    — biased in exactly the dangerous direction. A caller with only a
    sample estimate should consider max(theta_hat^2 - N/T_years, 0).

    n_years and n_obs are both taken because they measure different things:
    theta and Sigma are per-year quantities so the mu-noise term is N over
    the span in YEARS, while [P10]'s covariance factor counts OBSERVATIONS.
    For daily data they differ by a factor of 252. n_obs defaults to
    round(n_years * TRADING_DAYS_PER_YEAR)."""
    if not np.isfinite(theta_squared) or theta_squared < 0:
        raise ValueError(f"theta_squared must be finite and >= 0; got {theta_squared}")
    if n_assets < 1:
        raise ValueError(f"n_assets must be >= 1; got {n_assets}")
    if not np.isfinite(n_years) or n_years <= 0:
        raise ValueError(f"n_years must be finite and > 0; got {n_years}")

    base = theta_squared / (theta_squared + n_assets / n_years) if theta_squared > 0 else 0.0
    if not include_covariance_penalty:
        return float(base)

    t = round(n_years * TRADING_DAYS_PER_YEAR) if n_obs is None else int(n_obs)
    if t <= n_assets + 4:
        raise ValueError(
            f"[P10] eq. (2.17) requires T > N + 4; got T = {t}, N = {n_assets}. "
            "Pass include_covariance_penalty=False for the mu-only formula, which "
            "has no such requirement."
        )
    factor = ((t - n_assets - 1) * (t - n_assets - 4)) / (t * (t - 2))
    return float(base * factor)


# ---------------------------------------------------------------------------
# From-returns entry points. Same estimation convention as optimizer.py:
# sample mean and sample covariance of daily returns, annualized by
# TRADING_DAYS_PER_YEAR. Deliberately the same so a Kelly leverage can be
# read against an optimizer.py Sharpe without a units mismatch.
# ---------------------------------------------------------------------------


def _annualized_moments(
    asset_returns: pd.DataFrame,
    denoise: bool,
    denoise_bandwidth: float,
    insufficient_history_label: str,
) -> tuple[pd.Series, pd.DataFrame, RMTDenoiseResult | None]:
    """Sample mean and covariance of per-period SIMPLE returns, annualized
    by TRADING_DAYS_PER_YEAR — byte-for-byte optimizer.py's convention.

    WHY SIMPLE AND NOT LOG RETURNS, since it matters here more than it does
    in optimizer.py. [M69] eq. (12) and [T06] eq. (8.1) both define alpha /
    M as the DRIFT of dP/P, i.e. the arithmetic expected rate of return;
    the -s^2/2 that turns it into a log growth rate is applied ONCE,
    explicitly, by growth_rate(). Feeding this module a mean of LOG returns
    would subtract that variance drag twice and understate every Kelly
    weight. risk/returns.compute_daily_returns returns simple returns
    ("Simple (non-log) daily returns", its own docstring), which is the
    correct input; this note exists so a caller assembling a frame by hand
    does not helpfully "improve" it into log space."""
    n_obs, n_assets = asset_returns.shape
    if n_obs < MIN_OBS_FOR_ANY_ESTIMATE:
        raise InsufficientHistoryError(n_obs, label=insufficient_history_label)

    mu = asset_returns.mean() * TRADING_DAYS_PER_YEAR
    cov = asset_returns.cov() * TRADING_DAYS_PER_YEAR

    denoise_result: RMTDenoiseResult | None = None
    if denoise:
        # q = T/N, which a returns frame knows about itself — same reason
        # compute_hrp_weights_from_returns takes a bool rather than a q.
        denoise_result = denoise_covariance_matrix(
            cov, n_obs / n_assets, bandwidth=denoise_bandwidth
        )
        assert denoise_result.covariance is not None  # always set by that function
        cov = denoise_result.covariance
    return mu, cov, denoise_result


def compute_kelly_sizing_from_returns(
    asset_returns: pd.DataFrame,
    risk_free_rate: float,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
    *,
    denoise: bool = False,
    denoise_bandwidth: float = DEFAULT_KDE_BANDWIDTH,
    insufficient_history_label: str = "holdings",
) -> KellySizingResult:
    """Kelly weights straight from a T x N frame of per-period returns.

    Estimates mu and Sigma exactly as optimizer.py does (sample mean and
    sample covariance, both annualized by TRADING_DAYS_PER_YEAR), then
    applies [M69] eq. (60).

    READ THE MODULE DOCSTRING'S REAL-DATA SECTION BEFORE USING THIS ON REAL
    RETURNS: on a 12-ETF universe with 5 years of daily data it produced
    43.17x gross leverage, which is an estimation-error artifact, not an
    opportunity. kelly_leverage_for_weights on a direction chosen by
    something more robust is the recommended path.

    `denoise` DEFAULTS TO FALSE and, left alone, this function is
    bit-identical to a build without the option (asserted in the tests).
    Set True to route the sample covariance through
    rmt_denoising.denoise_covariance_matrix before inverting it — motivated
    because Kelly inverts Sigma, but NOT endorsed by any source (see the
    module docstring)."""
    mu, cov, denoise_result = _annualized_moments(
        asset_returns, denoise, denoise_bandwidth, insufficient_history_label
    )
    result = kelly_weights(mu, cov, risk_free_rate, kelly_fraction)
    result.denoise = denoise_result
    return result


def compute_kelly_leverage_from_returns(
    asset_returns: pd.DataFrame,
    weights: dict[str, float] | pd.Series,
    risk_free_rate: float,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
    *,
    denoise: bool = False,
    denoise_bandwidth: float = DEFAULT_KDE_BANDWIDTH,
    insufficient_history_label: str = "holdings",
) -> KellyLeverageResult:
    """The recommended composition point: take a set of relative weights
    (from compute_hrp_weights_from_returns, from
    compute_portfolio_optimization_from_returns, from anywhere) plus the
    returns that produced them, and get back the leverage.

    Neither optimizer.py nor hrp_optimizer.py is touched or wrapped — this
    reads the same returns frame independently and answers the separate
    question they do not."""
    mu, cov, denoise_result = _annualized_moments(
        asset_returns, denoise, denoise_bandwidth, insufficient_history_label
    )
    result = kelly_leverage_for_weights(weights, mu, cov, risk_free_rate, kelly_fraction)
    result.denoise = denoise_result
    return result


# ---------------------------------------------------------------------------
# The estimation-risk demonstration.
# ---------------------------------------------------------------------------


def simulate_wealth_paths(
    growth: float,
    volatility: float,
    horizon_obs: int,
    periods_per_year: float,
    shocks: np.ndarray,
) -> np.ndarray:
    """Log-wealth paths for a portfolio with true growth rate `growth` and
    true volatility `volatility`, driven by a caller-supplied array of
    standard normal shocks (n_paths x horizon_obs).

    This is [M69] eq. (12) with C = 0, after Ito, i.e.

        d(log W) = [r + pi'(mu - r 1) - (1/2) pi' Sigma pi] dt
                   + sqrt(pi' Sigma pi) dZ

    so the drift is exactly `growth` (which is what growth_rate() returns)
    and the diffusion coefficient is exactly `volatility`. Discretized
    exactly, not by Euler: over dt the increment is Normal(growth*dt,
    volatility^2 * dt), which is the exact law of the continuous process.

    SHOCKS ARE PASSED IN, NOT DRAWN HERE, so that a caller comparing
    several Kelly fractions can drive them all with the SAME market path.
    Without that, a difference between fractions could be path noise.

    Returns cumulative log wealth, shape (n_paths, horizon_obs), starting
    from log W_0 = 0."""
    dt = 1.0 / periods_per_year
    increments = growth * dt + volatility * np.sqrt(dt) * shocks[:, :horizon_obs]
    return np.cumsum(increments, axis=1)


def _max_drawdown_from_log_paths(log_paths: np.ndarray) -> np.ndarray:
    """Max drawdown of each path, as a fraction of the running peak.

    Computed in log space (running max of the log path, then exponentiated)
    because that is where the paths live; 1 - exp(log_W - running_max_log_W)
    is the ordinary drawdown definition. The initial value (log W = 0) is
    included as a peak, so a path that only ever falls still reports a
    drawdown against its starting wealth."""
    padded = np.concatenate([np.zeros((len(log_paths), 1)), log_paths], axis=1)
    running_max = np.maximum.accumulate(padded, axis=1)
    return 1.0 - np.exp(padded - running_max).min(axis=1)


def estimation_risk_monte_carlo(
    true_mu: pd.Series,
    true_cov: pd.DataFrame,
    risk_free_rate: float,
    estimation_obs: int,
    horizon_obs: int,
    kelly_fractions: tuple[float, ...] = (0.25, 0.5, 1.0, 1.5, 2.0),
    n_trials: int = 4000,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
    seed: int = 12345,
) -> KellyMonteCarloResult:
    """Quantify what estimation error in mu and Sigma does to a Kelly bet.

    The experiment, per trial:
      1. draw `estimation_obs` i.i.d. normal per-period return vectors from
         the TRUE (mu, Sigma), scaled to per-period units;
      2. estimate mu_hat, Sigma_hat from that sample and nothing else;
      3. form the plug-in full-Kelly portfolio pi_hat =
         Sigma_hat^-1(mu_hat - r 1);
      4. for each fraction c, compute the TRUE growth rate of c*pi_hat
         using parameters the estimator never saw, and simulate a
         `horizon_obs`-step wealth path.

    EVERY FRACTION IN A TRIAL SHARES pi_hat AND SHARES THE PATH SHOCKS, so
    the rows differ only in bet size — the "same estimation noise in both
    cases" comparison, with market-path noise controlled too.

    Trials whose Sigma_hat is singular are impossible for
    estimation_obs > n_assets and are not special-cased; smaller samples
    will raise from np.linalg.solve, which is the honest failure.

    See the module docstring's MEASURED section for a full run's numbers
    and for the limits of what this demonstrates (i.i.d. normal, constant
    parameters, frictionless, no jumps — every one of which flatters the
    result relative to reality)."""
    mu_values, cov_values = _validate_inputs(true_mu, true_cov)
    n_assets = len(mu_values)
    if estimation_obs <= n_assets:
        raise ValueError(
            f"estimation_obs ({estimation_obs}) must exceed the number of assets "
            f"({n_assets}) or the sample covariance is singular by construction"
        )
    if horizon_obs < 1:
        raise ValueError(f"horizon_obs must be >= 1; got {horizon_obs}")
    if n_trials < 1:
        raise ValueError(f"n_trials must be >= 1; got {n_trials}")

    rng = np.random.default_rng(seed)
    dt = 1.0 / periods_per_year
    period_mu = mu_values * dt
    period_cov = cov_values * dt
    chol = np.linalg.cholesky(period_cov)

    theta = max_sharpe_ratio(true_mu, true_cov, risk_free_rate)
    excess = mu_values - risk_free_rate

    n_fracs = len(kelly_fractions)
    growth_rates = np.empty((n_trials, n_fracs))
    terminal = np.empty((n_trials, n_fracs))
    max_dd = np.empty((n_trials, n_fracs))

    for trial in range(n_trials):
        sample = period_mu + rng.standard_normal((estimation_obs, n_assets)) @ chol.T
        mu_hat = sample.mean(axis=0) / dt
        cov_hat = np.cov(sample, rowvar=False, ddof=1) / dt
        pi_hat = np.linalg.solve(cov_hat, mu_hat - risk_free_rate)

        pi_excess = float(pi_hat @ excess)
        pi_variance = float(pi_hat @ cov_values @ pi_hat)
        shocks = rng.standard_normal((1, horizon_obs))

        for j, c in enumerate(kelly_fractions):
            g = risk_free_rate + c * pi_excess - 0.5 * c**2 * pi_variance
            vol = c * np.sqrt(pi_variance)
            log_path = simulate_wealth_paths(g, vol, horizon_obs, periods_per_year, shocks)
            growth_rates[trial, j] = g
            terminal[trial, j] = float(np.exp(log_path[0, -1]))
            max_dd[trial, j] = float(_max_drawdown_from_log_paths(log_path)[0])

    rows = [
        KellyMonteCarloRow(
            kelly_fraction=float(c),
            median_growth_rate=float(np.median(growth_rates[:, j])),
            mean_growth_rate=float(growth_rates[:, j].mean()),
            prob_growth_below_risk_free=float((growth_rates[:, j] < risk_free_rate).mean()),
            median_terminal_wealth=float(np.median(terminal[:, j])),
            p05_terminal_wealth=float(np.percentile(terminal[:, j], 5)),
            prob_terminal_below_half=float((terminal[:, j] < 0.5).mean()),
            prob_max_drawdown_over_half=float((max_dd[:, j] > 0.5).mean()),
            mean_max_drawdown=float(max_dd[:, j].mean()),
        )
        for j, c in enumerate(kelly_fractions)
    ]

    n_years = estimation_obs / periods_per_year
    return KellyMonteCarloResult(
        rows=rows,
        true_max_sharpe=theta,
        oracle_growth_rate=float(risk_free_rate + 0.5 * theta**2),
        n_trials=n_trials,
        n_assets=n_assets,
        estimation_obs=estimation_obs,
        horizon_obs=horizon_obs,
        periods_per_year=float(periods_per_year),
        risk_free_rate=float(risk_free_rate),
        predicted_optimal_fraction_mu_only=growth_optimal_kelly_fraction(
            theta**2, n_assets, n_years, include_covariance_penalty=False
        ),
        predicted_optimal_fraction_kan_zhou=growth_optimal_kelly_fraction(
            theta**2, n_assets, n_years, n_obs=estimation_obs
        ),
    )
