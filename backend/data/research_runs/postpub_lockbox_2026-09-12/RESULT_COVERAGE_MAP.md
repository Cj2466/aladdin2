# Coverage map — is our mechanism set actually "many different bets"? (2026-09-12, declared extension @4c17e89, run once)

## Short answer
**Broad in topic, much narrower in independence.** 163 buildable predictors sit in 30 different
economic categories, but measured on their own sealed returns they behave like about
**10 to 15 independent bets**, not 163 and not 30.

## 1. Topic coverage (the easy half)
The 195 sealed predictors span 33 economic categories. 30 of them contain at least one buildable
predictor. **Three contain none, and all three are blocked by paid data:**

| category with zero buildable | why | best sealed Sharpe there |
|---|---|---|
| optionrisk | needs options data (paid, gap P6) | **1.19 — the highest in the whole table** |
| informed trading | needs trade/participant classification (paid) | 0.85 |
| earnings forecast | needs analyst estimates, IBES (paid) | 0.66 |

So the paid gaps do not just cost us a few names, they cost us the three highest single sealed
Sharpes in the set. Everything else — valuation, financing, profitability, momentum, accruals,
liquidity, volume, leverage, R&D, short-sale constraints, ownership, payout, size, reversal,
investment, sales growth, risk, volatility, lead-lag, earnings events — has buildable members.

## 2. Independence (the half that matters)
Equal-weight pool per category, for the 23 categories with ≥3 buildable members, sealed months,
standard haircut. Pairwise correlations between the 23 category pools, over their 228 common months:

| | value |
|---|---|
| mean ρ | 0.058 |
| mean \|ρ\| | 0.243 |
| pairs at \|ρ\| ≥ 0.30 | 31% of 253 |
| most correlated pair | asset composition × leverage +0.76 |
| most anti-correlated pair | profitability × risk −0.69 |
| **effective number of independent bets** | **14.6** (variance-based) / **10.1** (simple K/(1+(K−1)ρ̄)) |

The two effective-bet figures differ because the category pools have unequal variances; both are
reported rather than picking the flattering one. Either way the honest range is **~10–15**.

## 3. The categories are not equally alive
Sealed Sharpe after the haircut, by category pool:

| carrying the result (≥0.35) | flat or negative (≤0.15) |
|---|---|
| short-sale constraints 0.71, valuation 0.65, earnings growth 0.63, external financing 0.59, profitability 0.54, investment growth 0.47, volume 0.41, R&D 0.40, accruals 0.37, momentum 0.36 | lead lag 0.13, composite accounting 0.10, volatility 0.06, liquidity 0.02, risk −0.01, asset composition −0.24, sales growth −0.27 |

About half the topics carry the whole book; the rest are noise or worse after costs. A plan that
counts "163 mechanisms" as 163 bets is wrong by an order of magnitude.

## 4. What is missing entirely, not just unbuilt
Verified by keyword search over all 331 signal-doc rows: **zero** predictors for mergers,
acquisitions, takeovers, bankruptcy, distress or default. Altman Z-Score and Failure Probability
exist in the dataset but are classified PLACEBO, not predictors. Also absent by construction:
macro/market timing, intraday microstructure, non-US equities, and every non-equity asset class.
This project's own 20 members DO cover some of that (crypto, FX, commodities, bonds, vol-regime
timing, forced-flow families) — so our set and this one are complementary, not nested.

## 5. What this means for the plan
- The BOOK needs ~30 low-ρ members to reach useful power. This map says the published-anomaly
  route supplies roughly 10–15 independent ones, not 30. **The gap must come from elsewhere**:
  our own non-equity families, the forced-flow families, or paid data (the three blocked
  categories are the highest-Sharpe ones in the set).
- Member selection must be BY CATEGORY, one or two from each live category, never "the top 15 by
  Sharpe" — the top of the list clusters in valuation and external financing.
- Nothing here changes the Set 2 verdict or promotes any predictor; it is a map for choosing what
  to build first.
