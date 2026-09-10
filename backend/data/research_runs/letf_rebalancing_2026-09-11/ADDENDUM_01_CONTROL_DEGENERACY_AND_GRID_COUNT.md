# ADDENDUM 01 — control degeneracy, the C1 grid count, and the power block's sigma_SR

Written 2026-09-10 (UTC; 2026-09-11 local) by the builder, BEFORE any strategy
return, any regression coefficient, or any power number for this family existed.
`PREREGISTRATION.md` is not edited. Section 4.4 requires that any deviation be an
addendum committed before the affected result exists; this is that commit.

---

## 1. THE PROBLEM — C1 and C2 are ALGEBRAICALLY IDENTICAL to the specs they control

This is not an empirical finding. It follows from the pre-registration's own
definitions and can be written down without touching a return.

Section 3 defines, per underlying u and session t:

    K_{u,t} = sum_i A_{i,t-1} * (L_i^2 - L_i)      over the four ProShares funds
    D_{u,t} = K_{u,t} * r_open->w
    x_{u,t} = D_{u,t} / ADV20_{u,t-1}

`A_{i,t-1}` is a fund's net assets, so `A > 0`. `L^2 - L` is 2, 6, 6 and 12 for
the four leverage levels in the pre-registered fund list, so it is `> 0` for
every fund. `ADV20` is a trailing dollar volume, so it is `> 0`. Therefore

    K_{u,t} > 0  and  ADV20_{u,t-1} > 0   for every u and t,

and `x_{u,t}` is `r_open->w` multiplied by a STRICTLY POSITIVE scalar. Hence

    sign(x_{u,t}) == sign(r_open->w)   identically, for every u and t.

Every trading spec in section 3 keys off `sign(x)` (spec A and the pooled P) or
off `sign(x)` plus a cut on `|r_open->w|` (spec B) or off `sign(x_t)` (the
reversal R). None uses the MAGNITUDE of `x`. Consequently:

* **C1 (constant-AUM control)** replaces `K_{u,t}` by its sample mean — another
  strictly positive scalar. The sign of `x` is unchanged on every session, so
  C1's position series, return series, Sharpe, DSR and preservation score are
  **exactly equal** to those of the spec it controls. It cannot fail to match.
* **C2 (shuffled-AUM placebo, seed 12345)** permutes `K` across sessions.
  A permutation of positive numbers is still positive on every session, so the
  sign of `x` is again unchanged and C2's series is **exactly equal** to the
  pooled 15:30 spec's. The pre-registration's requirement that C2 "must not
  pass" is therefore vacuous on the trading grid: C2 passes exactly when the
  spec it is supposed to discriminate against passes, by construction.
* **C3 (wrong-window control)** is NOT degenerate. It changes the window, not
  the coefficient, so it is a real control and is unaffected by this addendum.

The pre-registration half-anticipated this — section 3 says "A beats C1 only
through the time-variation of K/ADV, which is what the regression in section 4.1
tests directly", and section 5 warns that "a positive on A that is not
distinguishable from C1 is [intraday_momentum_spy]'s result again, not a new
mechanism". What it did not state is that on a sign-rule grid the two are not
merely hard to distinguish but numerically the same series. The consequence is
worth saying plainly, in advance:

> **The trading grid in section 3 contains no test of the LETF mechanism at
> all.** Every spec in it is a pure intraday-momentum rule on the underlying
> ETF. The entire LETF content of this family lives in the section 4.1
> regression, where `x` enters by MAGNITUDE and `K`'s time variation is the
> regressor. Section 4.1 was already written as the gate that must pass before
> any economic claim is attributed; this addendum records that it is not merely
> the first gate but the ONLY place the mechanism is examined.

## 2. WHAT CHANGES — nothing in the grid; one diagnostic is added

**The grid is implemented verbatim.** No spec is added, dropped, renamed or
re-parameterised, and `n_local` stays 20. C1 and C2 are computed, persisted and
reported like every other spec, and the run report states their exact equality
to their base specs as a measured fact (asserted numerically in the run, and
covered by a test) rather than only as the algebra above.

**One DIAGNOSTIC is added, and it is not a spec.** Because C2's permutation
does bite where `K`'s magnitude matters, the section 4.1 regression is
additionally estimated on the seed-12345 permuted `K`. It is reported next to
the real regression as a regression-level placebo. Following the convention
`intraday_momentum_spy.py` set for its own out-of-sample re-run of the paper's
Eq. (2) — "a DIAGNOSTIC ONLY: it is not a spec, it is not in N_local, and it
never enters the DSR or the verdict" — this permuted regression:

* is NOT counted in `n_local` (which stays 20, the pre-registered number),
* has NO trial row persisted,
* changes NO verdict; the section 4.1 gate is read off the REAL regression's
  `b` and `t` exactly as pre-registered.

It exists because a mechanism gate whose only placebo is degenerate is a gate
with no false-positive check, and adding a reported diagnostic can only make the
reading of the gate stricter, never more permissive.

## 3. DISAMBIGUATION — C1 is ONE spec, the pooled 15:30 one

Section 3 writes C1 as "A_u_15:30 with K_{u,t} replaced by its sample mean for
u", which read per-underlying would be three specs and would make the grid
17 + 3 + 1 + 1 = 22. The same section states `n_local = 20`. Only one reading
satisfies the stated count: C1, like C2 ("for the pooled 15:30 spec") and C3
("pooled A rule"), is a single POOLED 15:30 spec. It is implemented that way —
`P_15:30` with each underlying's `K` replaced by that underlying's own sample
mean — and `n_local` is 20 as declared. Since C1 is degenerate (section 1
above), no reading of this ambiguity could have changed any number.

## 4. THE POWER BLOCK'S sigma_SR, declared before it is computed

Section 4.3 requires the power block to be computed from the sigma of `y` and
the `|r|` distribution ONLY, before any strategy return. `dsr_power.dsr_power_report`
also requires `sigma_sr_annualized`, the dispersion of Sharpe across the family's
specs — which is a REALIZED quantity and does not exist at that point.
`intraday_momentum_spy` used its own realized value, but that family computed
its power block after its run; this one may not.

The value used is therefore declared here, before the number exists:

    sigma_sr_annualized = sqrt(periods_per_year / n_observations)

the sampling standard error of a single annualized Sharpe estimate under the
null of zero true edge — i.e. the cross-spec dispersion that 20 specs would show
if they were independent draws with no edge. It depends only on the panel's
length and the annualization factor, never on a return. This is **this
project's own choice, not a formula from any source paper**, and it is stated as
such. Because the realized dispersion of correlated specs is generally SMALLER
than the independent-draw value, and a larger `sigma_SR` raises the required
observed Sharpe, this choice is the CONSERVATIVE side: it can only lower the
computed power and make an "underpowered" declaration more likely, never less.

The power block reports the same two Tuzun calibrations the pre-registration
fixes (full and 50%) at this value, and additionally at `sigma_sr = 0` and at
`2x` the value, as a sensitivity. The pre-registered decision rule is unchanged
and is read off the declared value: **the family is declared underpowered for
the claim in advance if the 50% arm's power to clear 0.95 at n_local is < 0.80.**

## 5. Scope

Nothing here touches any live registration, promotes or retires anything, or
changes any shared formula module. No strategy return, regression coefficient or
power number for this family existed when this file was committed.
