# Dormant pool — gate results and what is adopted (2026-09-09)

Pre-registration: `DORMANT_POOL_PREREGISTRATION.md` (committed `26c336f`,
before any run). Amendment 1: `DORMANT_POOL_AMENDMENT_1.md` (committed
`d3bf9ec`, after runs 1–2, before run 3). Script: `dormant_pool_gates.py`.
Outputs: `..._run1_FAILED_G2b.txt`, `..._run2_worst_case.txt`,
`dormant_pool_gates_output.txt` (run 3, adopted).

## The three runs

| run | boundary | G1 normal | G2a t(4) | G2b AR(1) | power @ true Sharpe 0.5 / 1.0 within 10 y | status |
|---|---|---|---|---|---|---|
| 1 | 0.98865 (normal only) | 0.051 | 0.056 | **0.166 @ φ=0.3 — FAIL** | 0.35 / 0.86 | rejected |
| 2 | 0.99902 (worst model, φ=0.3) | 0.006 | 0.008 | 0.050 @ φ=0.3 | 0.10 / 0.59 | passed, but paid for a return process no spec has |
| 3 LOW (φ̂ ≤ 0.10) | **0.99397** | 0.029 | 0.034 | 0.050 @ φ=0.1 (0.120 @ φ=0.3, disclosed, outside contract) | **0.26 / 0.80** | **adopted** |
| 3 HIGH (φ̂ > 0.10) | **0.99894** | — | — | 0.053 @ φ=0.3 | 0.11 / 0.59 | **adopted** |

Measured on the 481 persisted spec series: lag-1 φ median −0.001, 95th pct
0.070, max 0.247, none ≥ 0.3 → 98% of families fall in LOW.

For contrast, the thing the look schedule replaces — "look at the 0.95 bar
every year and promote the first time it clears" — has a 17% family-wise
false-promotion rate under a pure null. The boundary is what makes repeated
looks honest.

## What the numbers say, plainly

* A family with a **real** net Sharpe of 0.5 that sits in Dormant for ten
  years is promoted with probability 0.26. Not 0.8. This is not the
  boundary's fault: it is the sample-length problem stated in
  `criteria_fix_2026-09-09` (0/50 families had 80% power at 0.5) seen from
  the other side. Dormant converts time into evidence at zero cost; it does
  not manufacture evidence.
* A real Sharpe-1.0 family is promoted with probability 0.80, median year 5.
* Pool cost: with 50 null families, ~1.1 false promotions over ten years
  (LOW). A promotion is a forward-tracking slot, not capital; the capital bar
  (DSR ≥ 0.95 at the top ladder rung, all layers) is untouched.

## A correction to the rule as I first stated it

"Statistics cannot close a candidate; only mechanism evidence can" was too
strong. The precise rule, consistent with the `underpowered` tier:

> **An underpowered statistical failure cannot close a candidate.** A failure
> from a test that had ≥ 80% power at the claimed effect size (a
> `definite_negative` with a passing `power` block) is legitimate evidence of
> absence at that size and may close. Mechanism evidence may close regardless
> of power.

So Frazzini-Lamont (sign reversed in 7/8 specs, recorded as well-powered)
stays Closed on statistics; an underpowered `definite_negative` does not.

## Proposed triage of the closed candidates (owner sign-off required — a proposal, not an action)

Statuses below are from the project's own records; "→ Dormant?" means the
close was statistical and the power block was never computed, so under the
new rule the candidate is a Dormant *candidate* pending (a) a power number
from `dsr_power` at the source's claimed Sharpe, (b) `pit_ok`, (c) a runner.

| candidate | why it was closed | proposed |
|---|---|---|
| quarter-end marking-the-close | markup leg absent from the data (mechanism gone) | Closed (mechanism) |
| TSMOM (all variants) | universe breadth 10 vs floor 15; loading drift irresolvable | Closed (structural) |
| Gabaix-Koijen inelastic | source itself predicts no forecastability; fidelity gate failed | Closed (mechanism) |
| Coval-Stafford fire sales | long leg formable 0/65 months — cannot be constructed from N-PORT breadth | Closed (structural) unless a holdings source with paper-like breadth appears |
| Frazzini-Lamont dumb money | sign reversed 7/8, recorded well-powered | Closed (statistics, powered) — verify the power number, then keep |
| asset_growth, residual_momentum, best_ideas_13f, ivol, buyback, bonds, fx, commodities, vol_regime, dividend_month, dividend_payment_pressure, earnings_announcement, pead, insider, index_removal, liquidity_shock, correlation_risk_premium, country_valmom, tax_loss (both), small_cap_* (statistical) | DSR below bar, power never computed; `family_min_detectable.csv` shows every one had < 80% power at a true 0.5 | → Dormant candidates, each needing (a)(b)(c) |
| ipo_lockup, jump_drift, eigenportfolio, low_frequency_patterns, phase_a_intraday | statistical, some with the 3× "sign reversed" pattern | → review individually: a reversed sign with adequate power closes; without it, Dormant |
| lazy_prices (all variants), short_interest, quality_cbop, crypto BAB | Active (forward-tracked) | unchanged |

Nothing above changes any row or file until the owner signs the list.

## What is built next (this branch)

`app/services/research_lab/dormant_pool.py`: the pinned boundaries, look
size and K_MAX (read back from run 3's committed output by a test so they
cannot drift), the entry dataclass and manifest loader (refuses incomplete
entries, forbids promotion when `pit_ok` is false or `rescorable` is false),
`assign_bucket(phi_hat)`, and `evaluate_look(extension_net_returns, entry)`
which computes PSR_ext with `deflated_sharpe.probabilistic_sharpe_ratio` and
returns the look index and promotion decision. Per-family re-scoring runners
are **not** built here; entries without one are recorded `rescorable=false`.
The manifest ships with zero entries: every entry is an owner decision.
