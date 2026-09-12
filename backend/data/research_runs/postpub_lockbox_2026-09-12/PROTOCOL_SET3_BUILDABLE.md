# Set 3 protocol — which of the 195 can we build, and what would a buildable book look like (declared 2026-09-12 13:50 Bangkok, before any Set 3 number)

Uses ONLY the sealed-window rules already declared in `LOCKBOX_PROTOCOL_OSAP.md` (post-publication
months, standard 20/P bps haircut, ≥36 sealed months, P-clean membership). No new window, no new
cost, no re-selection on results.

1. **Buildability class (from OSAP `Cat.Data`, declared now, before looking at any per-predictor
   number):** BUILDABLE = Accounting (EDGAR companyfacts), Price, Trading (volume), 13F, Event
   (8-K/EDGAR dates); NOT BUILDABLE on free data = Analyst (IBES), Options, Other (case by case,
   default not). Counts reported.
2. **Per-predictor sealed statistics** for all 195 (same computation as the look; the run did not
   persist them): sealed Sharpe after haircut, NW t, n months, sign of in-sample check.
3. **Buildable book:** equal-weight pool of the BUILDABLE ∩ P-clean predictors, sealed months,
   standard haircut — same statistics as Set 2. Reported next to Set 2's primary; no pass line is
   attached (Set 2 already decided the question "is there something"; Set 3 answers "how much of it
   is within our reach").
4. **Correlation:** pairwise ρ of sealed-window monthly returns within the buildable set (≥ 120
   overlapping months), mean and the share of pairs with |ρ| ≥ 0.30; and the buildable pool's ρ
   with the non-buildable pool.
5. **Ranking for the owner:** buildable predictors ordered by sealed Sharpe after haircut, with n,
   t, Cat.Data, Cat.Economic, and whether an aladdin2 family already implements it (matched by hand
   from the module docstrings, cited). The ranking is descriptive; admission to the BOOK remains a
   separate, pre-registered step per family on OUR data.
6. Overlap correction: predictors already implemented here are flagged so their OSAP sealed number
   is not double-counted as new evidence for our own version.

---
## Declared extension, 2026-09-12 (owner asked "is our set of mechanisms actually comprehensive?")

Same sealed data, same window, same haircut, NO new selection and NO verdict attached. Adds only
a descriptive breakdown of the correlation work §4 already authorises:
1. Coverage by `Cat.Economic`: how many of the 195 (and of the 163 buildable) sit in each economic
   category, and which categories have zero buildable members.
2. Category pools: equal-weight pool of the buildable predictors within each category that has ≥ 3
   of them, on the sealed window after the standard haircut; report each pool's Sharpe, n months,
   and the pairwise correlation MATRIX between category pools.
3. The question it answers: are the categories genuinely different bets (low pairwise ρ between
   pools) or one bet wearing different names (high ρ)? An effective-number-of-bets figure
   M_eff = (Σw)²/(w'Σw) with equal weights is reported as a single summary.
Nothing here can change the Set 2 PASS/FAIL or promote any predictor. It is a map, not a decision.
