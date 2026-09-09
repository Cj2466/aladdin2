# Forward-retirement rule — result and the decision it leaves to the owner (2026-09-09)

Pre-registration: `RETIREMENT_RULE_PREREGISTRATION.md` (7ebd610). Amendment 1
(1296dee) corrected only R5's stated expectation. Gates: `retirement_rule_gates.py`,
run 2 output `retirement_rule_gates_output.txt` (9484ab1). Module:
`app/services/research_lab/retirement_rule.py`, tests `tests/test_retirement_rule.py`.

## 1. Outcome under the pre-declared rule

At the primary protect level **s0 = 0.5**, LOW bucket (φ̂ ≤ 0.10):

| statistic | R1 false-recommend within 5y (normal / t4 / AR1 0.1) | R2 catch true −1.0 within 5y | R3 decay caught within 5y (median delay) |
|---|---|---|---|
| S-A whole-record PSR floor | 0.028 / 0.037 / 0.051 | 0.64 FAIL | 4% (2.33y) |
| **S-B SPRT (adopted)** | 0.031 / 0.026 / 0.051 | **0.82 PASS** | **14.5%** (2.24y) |
| S-C CUSUM | 0.025 / 0.025 / 0.049 | 0.79 FAIL (by 0.006) | 49% (2.06y) |

S-B is the only statistic passing R1 and R2, so it is adopted, boundary
Λ ≥ 3.7087. HIGH bucket (φ̂ > 0.10): **no statistic reaches 80 % at −1.0
within 5 y** (0.36 / 0.65 / 0.57) — there is no calibrated rule for HIGH
registrations and the module says so rather than pretending.

R5: the harness reproduces the criteria audit's measurement of the retired
trailing-window rule (0.662 vs 0.654 at 126 d; 0.922 vs 0.922 at 252 d).

## 2. What the numbers say, plainly

1. **The adopted rule is slow and nearly blind to decay.** It catches a
   strategy that was −1.0 from day one in 82 % of cases within five years
   (median 2.25 y, median drawdown at trigger 3.4 annual-vol units — at 10 %
   vol that is a 34 % drawdown before the recommendation). A strategy that
   was genuinely 1.0 for two years and then turned −1.0 is caught within the
   remaining three years only 14.5 % of the time, because the whole-record
   statistic carries the good history.
2. **That is the price of protecting 0.5, and no rule avoids it**
   (pre-registration §1: about 2 ln(20)/(1.5)² ≈ 2.7 years of evidence at
   α = 0.05). A zero-edge registration is essentially never retired by
   statistics (SPRT: 15 % within 5 y).
3. **CUSUM is the better change detector and missed R2 by 0.006.** Under the
   pre-declared rule it is not adopted; that is recorded, not argued around.
4. **The protect level is the real decision.** At the alternative s0 = 1.0
   (informational, same procedure): CUSUM passes R1 and R2 in both buckets
   (0.95 LOW / 0.83 HIGH at −1.0), catches the decay case 76 % of the time
   with median delay 1.67 y, and recommends retiring a true 0.5 within 5 y
   11 % of the time (true 0.3: 19 %). SPRT at s0 = 1.0: 0.95 / 0.89, decay
   38 %, true 0.5 killed 12 %.

## 3. Decision for the owner (rule 6: recommend, never execute)

Choose one; nothing is wired until this is chosen, because the boundary
depends on it:

- **A. Protect 0.5 (pre-registered primary): adopt S-B SPRT, LOW bucket
  only.** Consistent with what the pipeline actually registers (net
  backtest Sharpes 0.4–0.9). Accept that a decayed edge persists ~2 y+ and
  that HIGH-bucket registrations have no rule.
- **B. Protect 1.0: adopt S-C CUSUM in both buckets.** Faster and
  decay-aware, at the cost of recommending retirement for roughly one in
  nine genuinely-0.5 registrations within five years. Requires a new
  pre-registration naming s0 = 1.0 as primary (this one named 0.5); the
  numbers above would be its gate run, already done.

Either way: capital protection must come from sizing (volatility targeting,
per-sleeve caps), not from this rule's speed; and the recommendation feeds
the dashboard advisory, never a status flip.

## 4. What was NOT done

- No wiring into runners, API or dashboard (decision above comes first).
- No CUSUM/PSR boundary is adopted; their numbers are in the output for
  the record.
- Bucket assignment for the four live registrations (φ̂ on their original
  windows) is not computed here; `dormant_pool.assign_bucket` on the frozen
  spec's persisted series is the declared method.

## 5. Independent checks done by the author

- PSR arithmetic vectorised in the gate script spot-checked against
  `deflated_sharpe.probabilistic_sharpe_ratio` to 1e-9 (script self-check).
- CUSUM / SPRT known-answer checks (constant increments) in the script and
  in the tests; the increment's expected drift matches the KL arithmetic of
  §1 to 2e-4 over 100 000 days (test).
- R5 reproduces an independently-written Monte Carlo from the criteria fix.
- Runs 1 and 2 give identical R1–R4 numbers (same seeds).
