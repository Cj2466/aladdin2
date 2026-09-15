# Audit of every cost constant in the project (2026-09-12, owner's instruction: "check the bp values — are we using the right ones")

Orchestrator (Opus 5), by reading each constant's own justification in the source and, where a
number could be checked, checking it. Every constant in `app/services/research_lab/` matching
COST/BPS/SPREAD/FINANCING/BORROW was enumerated, not sampled.

## 1. Constants that ARE sourced (spot-checked, justification present in the module)

| constant | value | basis found in the code |
|---|---|---|
| `borrow_cost.GENERAL_COLLATERAL_BPS_PER_YEAR` | 34 /yr | D'Avolio (JFE 2002) with table and page quoted; four independent estimates cluster 17–34 |
| `borrow_cost.HARD_TO_BORROW_BPS_PER_YEAR` | 430 /yr | D'Avolio Table 3 value-weighted mean fee for specials, 4.30%/yr |
| `spread_estimator.SP500_TARGET_MEDIAN_HALF_SPREAD` | 2 bp one-way | Hagströmer (JFE 2021) Table 1 + Nasdaq 2024 economist notes, both fetched and read at the time |
| `cross_sectional_fx.FX_SPREAD_BPS_ONE_WAY` | 1.3 | reasoned from G10 pip spreads, declared "deliberately conservative" |
| `cross_sectional_fx.FX_FINANCING_BPS_PER_YEAR` | 25 /yr | tom-next swap markup, with the reason it dominates for this family |
| `cross_sectional_index_removal.REMOVAL_STOCK_ROUND_TRIP_BPS` | 16.4 | derived from the family's OWN panel: Amihud (2002) ILLIQ median 2.52e-10 → 14.7 bp at 5% of ADV, 23.4 bp at 10%; 16.4 sits at ~6% |
| `…REMOVAL_SPY_ROUND_TRIP_BPS` | 2.0 | labelled **ASSUMED, not measured**, and conservative by construction |
| `cross_sectional_crypto.CRYPTO_COST_BPS` | 30 | sized to the ALT coins a quintile leg actually holds, not to BTC |
| `…CRYPTO_SHORT_BORROW_BPS_PER_YEAR` | 800 /yr | documented, with the perp funding credit deliberately NOT taken (conservative) |
| `cross_sectional_small_mid_cap.SMALL_CAP_COST_BPS` | 15 | measured ratios from the family's own panel; the module states plainly that the measured LEVELS are not credible and are not used |
| `cross_sectional_bonds.BONDS_COST_BPS` / borrow | 2.5 / 40 /yr | docstring COSTS section |

These are in good shape: each says where it came from, and several label themselves as assumptions
rather than measurements — which is the behaviour the project's own rules ask for.

## 2. The gap: the default every US equity family uses has NO source

    ou_pairs.DEFAULT_COST_BPS = 10.0          <- no comment, no citation, nothing
      └─ momentum.DEFAULT_COST_BPS = 5.0       "half of pairs' 10bps — one leg instead of two"
           └─ cross_sectional.DEFAULT_XS_COST_BPS = 5.0
              "mirrors momentum.py's … convention, NOT independently recalibrated"

The chain is honest about itself at every step — but it terminates in a bare number in the
project's first strategy module. **Every equity family that did not override the default has been
costed against an unsourced constant.**

## 3. How wrong is it, and in which direction? — measured, not asserted

Against the sourced large-cap level (≈1.5 bp one-way, §1), the 5 bp default overcharges a large-cap
book by roughly 3×. The Sharpe consequence depends on turnover, and is smaller than it looks:

| book turnover | cost drag at 5 bp | at 1.5 bp | Sharpe difference (8% vol) |
|---|---|---|---|
| 1×/yr | 0.10%/yr | 0.03%/yr | 0.009 |
| 2×/yr | 0.20%/yr | 0.06%/yr | 0.018 |
| 4×/yr | 0.40%/yr | 0.12%/yr | 0.035 |
| 12×/yr | 1.20%/yr | 0.36%/yr | 0.105 |

**I expected this to be large enough to overturn verdicts; the arithmetic says it is not** — 0.01 to
0.10 Sharpe, and only at monthly-full-turnover does it approach 0.1. Recording the corrected
expectation rather than the first instinct.

Direction matters as much as size: an overcharge can only push a net Sharpe DOWN. So no "this
family works" conclusion is threatened by it. What it does mean is that every "uneconomic" verdict
on a HIGH-TURNOVER large-cap family was reached with costs about 3× too high, and those are worth
re-reading before being treated as closed. (The two highest-turnover cases, `round_c` intraday and
`phase_a_intraday_expanded`, were already re-audited on 2026-08-30 for exactly this reason.)

## 4. What A2 will do about it
1. Keep every sourced constant in §1 as it is; none of them is the problem.
2. Replace the unsourced 5 bp default, for the whole-market panel only, with the per-ticker
   estimate A2 produces (measured where measurable, sourced fallback elsewhere, labelled per cell).
   The default stays untouched in the harness so persisted runs stay reproducible.
3. Record the break-even cost per strategy, so the question becomes "how cheaply must this trade"
   rather than "does it pass at one assumed number".
4. Report both a conservative and a permissive cost view side by side (owner's instruction), with
   the conservative one deciding and the permissive one kept for analysis, never for promotion.
