# POWER BLOCK — `letf_rebalancing_eod` (PREREGISTRATION section 4.3)

Written and committed 2026-09-10 (UTC) **BEFORE any strategy return, position or
Sharpe for this family was computed.** The producing script,
`data/research_runs/letf_power_block.py`, imports the panel builder and the power
functions and nothing else; it cannot reach a replay. Machine-readable twin:
`power_block.json`.

Authority: `PREREGISTRATION.md` section 4.3 for the procedure and the decision
rule; `ADDENDUM_01_CONTROL_DEGENERACY_AND_GRID_COUNT.md` section 4 for the
`sigma_SR` value, which was likewise declared before it was computed.

---

## 1. What the panel turned out to be

| | |
|---|---|
| underlyings | SPY, QQQ, IWM (balanced — a session enters only if all three pass) |
| calendar sessions per ticker | 2,686 |
| usable after U1–U3 | SPY 2,661 · QQQ 2,659 · IWM 2,660 |
| dropped, not usable for all three | 6 |
| dropped, no bar starting at a required window time | SPY 1 · QQQ 0 · IWM 0 |
| panel sessions (after warm-up + 20-session trailing window) | **2,637** |
| panel rows (session × underlying) | 7,911 |
| first / last session | 2016-02-02 / 2026-09-09 |
| measured sessions per year | **248.751** |

The one "missing window bar" drop is an implementation necessity, not a
discretionary filter: `r_open→w` is defined as a return *to the open of the bar
starting at w*, which is undefined if no bar starts at w. It removes one SPY
session out of 2,686 and is counted and reported rather than absorbed.

## 2. The two quantities section 4.3 allows the block to see

| quantity | value |
|---|---|
| σ of y (the 15:30→close return, pooled equal-weight, daily) | **0.00301618** |
| mean \|r_open→15:30\| | 0.00809574 |
| median \|r_open→15:30\| | 0.00560925 |
| 90th percentile \|r_open→15:30\| | 0.01815869 |

Nothing else was read. No position was formed and no spec was replayed.

## 3. Translating Tuzun's claim onto this sample

Tuzun FEDS 2013-48 section C.1, verbatim: "The end-of-day price reaction is 6.9
basis points (4.32 × 0.8% × 2%) in an average large stock" — on a 1% index day,
at December-2011 AUM. Section 4.3 applies that **linearly** to this sample's own
\|r\| distribution:

    E[gross daily]  =  mean( 6.9 bp × |r| / 1% )
                    =  6.9e-4 × 0.00809574 / 0.01
                    =  0.00055861          (5.586 bp)

    half-Tuzun      =  0.00027930          (2.793 bp)   — Ivanov & Lenkey
                                                          Table III's flow offset

The pre-registered round trip is 2 × 1.0 bp = **0.00020000 (2.0 bp)**, charged
inside the series. So:

| arm | gross/day | net/day | net annualized Sharpe |
|---|---|---|---|
| full Tuzun | 5.586 bp | 3.586 bp | **1.8752** |
| 50% of Tuzun | 2.793 bp | 0.793 bp | **0.4147** |

**The single most important line in this file**: at half strength — the strength
Ivanov & Lenkey's own Table III measures once investor flows are counted — the
pre-registered cost arm consumes **72%** of the entire claimed effect, before any
question of statistical detection arises. That was fixed by the pre-registration
and is arithmetic, not a finding about the data.

## 4. σ_SR, declared in advance

    sigma_SR_annualized = sqrt(periods_per_year / n_observations)
                        = sqrt(248.751 / 2637)
                        = 0.307134

the null sampling standard error of one annualized Sharpe estimate (ADDENDUM_01
section 4). **This project's own choice, not a formula from any source paper.**
It is the conservative side: correlated specs disperse *less* than independent
draws, and a larger σ_SR raises the required observed Sharpe, so this can only
*lower* the computed power. Sensitivities at σ_SR = 0 and 2× are reported below.

## 5. Power, at n_local = 20, n = 2,637, 248.751 periods/year

DSR ladder in force on the run date: **[20, 43, 397, 1131]**.

### 5a. Full-Tuzun arm (claimed net Sharpe 1.8752)

| σ_SR | bar | required observed SR | **power** | min detectable SR | years to detect |
|---|---|---|---|---|---|
| 0.307134 (declared) | 0.95 | 1.0897 | **0.9946** | 1.3487 | 3.73 |
| 0.307134 (declared) | 0.50 | 0.5838 | 0.99999 | 0.8425 | 0.43 |
| 0 | 0.95 | 0.5054 | 0.99999 | 0.7641 | 1.77 |
| 0.614267 (2×) | 0.95 | 1.6743 | 0.7427 | 1.9338 | 12.42 |

### 5b. 50%-of-Tuzun arm (claimed net Sharpe 0.4147) — **THE DECIDING ARM**

| σ_SR | bar | required observed SR | **power** | min detectable SR | years to detect |
|---|---|---|---|---|---|
| **0.307134 (declared)** | **0.95** | **1.0897** | **0.0140** | 1.3487 | not reachable |
| 0.307134 (declared) | 0.50 | 0.5838 | 0.2910 | 0.8425 | not reachable |
| 0 | 0.95 | 0.5054 | 0.3839 | 0.7641 | 35.97 |
| 0 | 0.50 | ~0 | 0.9114 | 0.2586 | 4.12 |
| 0.614267 (2×) | 0.95 | 1.6743 | 0.00002 | 1.9338 | not reachable |

## 6. THE PRE-REGISTERED DECISION

> Section 4.3: "The family is declared underpowered for the claim in advance if
> the 50% arm's power to clear 0.95 at n_local is < 0.80."

    power = 0.0140   <   POWER_FLOOR = 0.80

## ⇒ **`letf_rebalancing_eod` IS DECLARED UNDERPOWERED FOR THE CLAIM, IN ADVANCE.**

Recorded here, before any result exists, with its consequences spelled out so
they cannot be renegotiated after the numbers arrive:

1. **A failing DSR at `n_local` will read UNDERPOWERED, not DEFINITE_NEGATIVE.**
   That is `dsr_power`'s whole purpose: "a test that cannot see the effect it was
   built to look for has not refuted it." This family, at the half-strength
   calibration, would clear the 0.95 bar 1.4% of the time even if Ivanov &
   Lenkey's own measured effect were exactly true.
2. **This label earns nothing.** An UNDERPOWERED family gets no forward slot, no
   registration and no benefit of the doubt. It is a statement about the test's
   resolution, not about the mechanism's existence.
3. **The section 4.1 mechanism gate is unaffected and remains the real test.**
   It is a regression on 7,911 observations with clustered standard errors, not
   a Sharpe on 2,637 daily returns, and its power is a different question
   entirely. Section 4.1 already says a failure there writes the verdict as
   "momentum, not LETF" whatever the trading grid shows — and ADDENDUM_01 records
   that on this sign-rule grid section 4.1 is the *only* place the mechanism is
   examined at all. **If the gate fails, this family's answer does not depend on
   the power block.**
4. **The full-Tuzun arm passing at 0.9946 does not rescue it.** The
   pre-registration named the 50% arm as the deciding one precisely because
   Ivanov & Lenkey measured the offset directly, and it was named before any of
   these numbers existed.

## 7. What would change it

Only two things move a power number: a larger true annualized Sharpe, or more
calendar time (measured for this project on 2026-09-09 — sampling *frequency*
does not shorten detection). At the declared σ_SR the 50% arm needs an observed
Sharpe of 1.0897 to clear 0.95, against a claimed 0.4147; `years_to_detect`
returns *not reachable* at the ladder's own n_trials, meaning no realistic amount
of further daily data resolves this claim at this bar. At the σ_SR = 0 bound it
is 35.97 years. That is the honest statement of what this test could ever do.
