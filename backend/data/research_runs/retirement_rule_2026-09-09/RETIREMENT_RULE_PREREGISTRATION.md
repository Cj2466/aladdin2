# Forward-retirement rule — pre-registration (2026-09-09)

Written and committed BEFORE `retirement_rule_gates.py` is run. The pass
criteria live here. If a gate fails, that is recorded and the rule is not
adopted; the criteria are not edited to fit.

## 0. Why this exists

On 2026-09-09 the trailing-window auto-park rule (retire when the trailing
60-day Sharpe ≤ −0.5) was demoted to an advisory after
`criteria_fix_2026-09-09` measured that it parks a genuinely good (true
Sharpe 1.0) registration about two times in three. Since then there is NO
statistical rule for when a forward registration should be retired — only the
dashboard advisory (whole-record PSR vs 0) and the owner's judgement. Before
any capital that gap has to be closed with a rule whose error rates are
measured, not assumed. This document declares that rule.

The rule is a RECOMMENDATION generator. Changing a registration's status
remains the owner's decision (CLAUDE.md rule 6). Mechanism evidence closes a
registration regardless of this rule, exactly as in the Dormant pool.

## 1. The quantity that governs everything (stated before any simulation)

Let s0 be the true annualized Sharpe we refuse to kill ("protect") and s1 the
true Sharpe we want to catch ("harm"). For i.i.d. normal daily returns the
Kullback-Leibler divergence per day between N(s1·σ/√252, σ²) and
N(s0·σ/√252, σ²) is (s1−s0)²/(2·252) — the elementary Gaussian KL,
½(Δμ/σ)², with Δμ/σ = (s1−s0)/√252. Per year that is (s1−s0)²/2 nats.
Any sequential test with false-alarm probability α needs on the order of
ln(1/α) nats of evidence, so the mean detection time is roughly

    T ≈ 2·ln(1/α) / (s1−s0)²   years.

At α = 0.05 (ln 20 ≈ 3.0):

| protect s0 | harm s1 | gap | T (years, order of magnitude) |
|---|---|---|---|
| 0.5 | −1.0 | 1.5 | ≈ 2.7 |
| 0.5 | −0.5 | 1.0 | ≈ 6 |
| 1.0 | −1.0 | 2.0 | ≈ 1.5 |
| 0.0 | −1.0 | 1.0 | ≈ 6 |
| 0.5 | 0.0 | 0.5 | ≈ 24 |

This is a bound on ANY rule, not a property of a particular statistic; a
rule that appears to beat it is killing good strategies. The consequence,
stated now so the gate outcome cannot soften it: **no statistical retirement
rule can protect a true 0.5 and catch a true −1.0 inside about three
years, and a zero-edge registration will not be retired by statistics at
all on a useful horizon.** Capital protection therefore has to come from
sizing (volatility targeting, per-sleeve caps), not from detection speed;
this rule only bounds how long a harmful sleeve can persist.

This is the same arithmetic as `feedback_sampling_frequency_does_not_shorten
_detection`: only the annualized Sharpe gap and calendar time enter.

## 2. Pre-declared choices

- **Protect level s0 = 0.5** (primary). The pipeline's candidates carry
  net backtest Sharpes of roughly 0.4–0.9; protecting 0.5 is protecting the
  candidates we actually register. s0 = 1.0 is reported as an alternative
  the owner may choose (faster kills, but a true 0.5 is then killed often).
- **Harm level s1 = −1.0** for the design of the statistic; the operating
  characteristic is reported at s ∈ {1.0, 0.5, 0.3, 0, −0.3, −0.5, −1.0}.
- **False-alarm budget α = 0.05 per registration over the horizon** (per
  registration, so with N live registrations the expected number of wrongly
  recommended retirements over the horizon is N·α, which the output states).
- **Horizon H = 5 years** (1260 trading days): the calibration controls
  P(any trigger within H | s0). Beyond H the rule keeps running; its
  false-alarm probability then exceeds α and the output says by how much
  at 10 years (informational).
- **Monitoring is daily** (every runner tick), from day
  MIN_DAYS = 60 (UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS, unchanged) onward;
  daily monitoring is what the calibration simulates.
- **Scale**: daily net returns standardized by the EXPANDING sample standard
  deviation of the realized record up to and including the current day
  (plug-in σ̂_t; the calibration absorbs its noise).
- **Autocorrelation buckets** exactly as the Dormant pool: LOW (φ̂ ≤ 0.10)
  calibrated as the worst of i.i.d. normal, Student-t(4), AR(1) φ = 0.10;
  HIGH (φ̂ > 0.10) calibrated under AR(1) φ = 0.30. φ̂ is the registration's
  lag-1 autocorrelation measured on its ORIGINAL backtest window (the
  frozen spec's persisted series), fixed at registration — never re-chosen
  on the forward record.

## 3. Three candidate statistics, one pre-declared selection rule

All three use the standardized daily return z_t = r_t / σ̂_t and the
per-day log-likelihood ratio of "harm" against "protect" for a Gaussian
with common variance,

    ℓ_t = d · ( z_t − m ),   d = (s1 − s0)/√252,   m = (s1 + s0)/(2·√252),

which is the elementary identity log[φ(z; μ1)/φ(z; μ0)] = (μ1−μ0)(z − (μ1+μ0)/2)
for unit variance; nothing here is a published formula reproduced from
memory, and the boundaries below are NOT Wald's approximations — every
boundary is the simulated (1−α) quantile.

- **S-A, whole-record PSR floor.** PSR_t = probabilistic_sharpe_ratio(
  SR_t, 0, t, skew_t, kurt_t) on the whole realized record (the project's own
  function, the same number the dashboard advisory shows). Trigger when
  PSR_t ≤ L. L = the α-quantile over paths of min_t PSR_t under s0.
- **S-B, SPRT.** Λ_t = Σ_{i≤t} ℓ_i. Trigger when Λ_t ≥ B. B = the (1−α)
  quantile over paths of max_t Λ_t under s0.
- **S-C, CUSUM (Page).** C_t = max(0, C_{t−1} + ℓ_t), C_0 = 0. Trigger when
  C_t ≥ h. h = the (1−α) quantile over paths of max_t C_t under s0.

Selection rule, declared now: the adopted statistic is the one with the
SHORTEST median detection time in the decay scenario (section 4, R3) among
those passing R1 and R2. Ties (within simulation error) go to the simpler
statistic in the order S-A, S-C, S-B. The reason the decay scenario decides:
the failure mode that actually matters for a registration that earned its
slot is an edge that STOPS working, and a whole-record statistic carrying
years of good history is slow to notice that by construction.

## 4. Gates (pass criteria fixed here)

Calibration seed 20260909, 20 000 paths per model; every gate uses a
different seed (777) and 20 000 paths.

- **R1 (protect, gating).** P(trigger within H | true Sharpe s0 = 0.5)
  ≤ α + 2·se under the calibration model, and ≤ 0.07 under each other
  model in the bucket's contract (t4 and AR(1) 0.10 for LOW). Identical
  structure to Dormant G1/G2.
- **R2 (catch, gating).** P(trigger within H | true Sharpe −1.0) ≥ 0.80.
  Section 1 says the mean is ≈ 2.7 y; 80 % inside 5 y is the claim being
  tested. If R2 fails for every statistic the finding is recorded as "no
  rule protecting 0.5 catches −1.0 inside five years at 80 % power" and
  the owner is offered s0 = 1.0 with its own R1/R2 numbers — NOT a lowered
  bar.
- **R3 (decay, informational + selection).** True Sharpe 1.0 for the first
  2 years, then −1.0. Report the median and 80th-percentile detection
  delay after the change point, and P(trigger before the change point)
  (which is a false alarm and must be consistent with R1).
- **R4 (operating characteristic, informational).** P(trigger by 1/2/3/5/10
  years) at each s in section 2, plus the realized drawdown at trigger
  (median) under s = −1.0 and −0.5 — the price of waiting.
- **R5 (the retired rule, for the record).** The same simulation applied to
  the old trailing-60-day-Sharpe ≤ −0.5 rule, to reproduce the
  criteria-audit measurement in this harness (expected: kills true 1.0 in
  roughly two of three paths within 3 y; if this does not reproduce, the
  harness is wrong and nothing above counts).

## 5. What adoption would mean

If a statistic passes: a module `app/services/research_lab/retirement_rule.py`
exposing the statistic and its calibrated boundaries per bucket, unit-tested
on synthetic paths with a known answer, and a dashboard advisory field
"retirement recommended (rule R-2026-09-09) since <date>". Nothing flips a
status. Wiring the recommendation into a capital stop is a later, separate
decision and would need its own pre-registration.

If nothing passes: this document plus the output are the record, the
dashboard keeps the existing advisory, and section 1's bound is the
finding.
