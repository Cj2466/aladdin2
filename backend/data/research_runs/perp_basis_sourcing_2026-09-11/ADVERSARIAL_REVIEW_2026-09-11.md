# Adversarial review of the perp-basis DECLINE_AT_SOURCING decision (Fable 5.1, 2026-09-11)

Stand-alone review. Scope: try to break the decision in
`FEASIBILITY_AND_SOURCING_2026-09-11.md`; no code written into `app/`, no DB touched, nothing merged.
Inputs read directly (not via the memo's quotations): the paper extract
`../hunting_ground_review_2026-09-11/sources/perpetual_futures_fundamentals.txt` (Tables 2, 3, 5, 6,
7, 8, 9; §4.3; Appendix C), `app/services/research_lab/dsr_power.py`, `deflated_sharpe.py`
(`expected_max_sharpe_under_noise`, `MIN_TRIALS_FOR_DSR = 5`),
`criteria_audit_2026-09-09/CRITERIA_AUDIT_2026-09-09.md`, `cross_sectional_funding_carry.py`
docstring, `funding_carry_build_2026-08-29.txt`, `letf_rebalancing_2026-09-11/POWER_BLOCK.md`,
`hunting_ground_review_2026-09-11/{HUNTING_GROUND_REVIEW,HYPOTHESES,ORCHESTRATOR_NOTE}.md`.

Every number below is produced by `adversarial_review_calc.py` (beside this file; run from
`backend/` with `./venv/bin/python data/research_runs/perp_basis_sourcing_2026-09-11/adversarial_review_calc.py`)
or by a formula stated inline. The memo's own script was re-run first and reproduces its JSON
exactly (the only diff is the `written_utc` stamp; the committed copy was restored).

**The decision under review**: "DECLINED AT SOURCING: at the paper's own post-2022 Sharpe ratios the
DSR gate has power 0.05–0.20 over 7 years and 0.01–0.03 on the 2.5-year OOS window."

---

## 0. The one finding that matters most (found under attack 2, stated first)

**The memo's "Table 7" numbers are Table 8's.** `sourcing_power_perp_basis.py` declares
`TABLE_7_POST_BREAK_SR = {BTC:(0.51,0.87), ETH:(0.81,1.16), BNB:(0.76,0.73), DOGE:(1.03,0.49), ADA:(None,0.88)}`
with the comment "Table 7, High tier, unrestricted strategy". Read against the extract:

| coin | memo constants | Table 7 (UNRESTRICTED) 2022, 2023 | Table 8 (LONG-SPOT-ONLY) 2022, 2023 |
|---|---|---|---|
| BTC | 0.51, 0.87 | 0.70, 1.32 | 0.51, 0.87 |
| ETH | 0.81, 1.16 | 1.29, 1.64 | 0.81, 1.16 |
| BNB | 0.76, 0.73 | 2.83, 2.96 | 0.76, 0.73 |
| DOGE | 1.03, 0.49 | 1.49, 0.85 | 1.03, 0.49 |
| ADA | –, 0.88 | 2.33, 1.12 | –, 0.88 |

Likewise `TABLE_7_ALL_SR = {1.62, 2.23, 3.29, 2.52, 2.11}` is Table 8's "All" column (Table 7's is
1.80, 2.55, 4.84, 3.58, 2.68), and the memo's "active 0.02–3.8% of hours in 2022–23" is Table 8's
range (Table 7's is 7.7–28.5%). Every number in the memo's power table row "Table 7 post-break
2022–23 mean" therefore describes the **long-spot-only** variant, mislabeled as the unrestricted one.

Corrected power at the memo's own settings (n_local = 16, bar 0.95, σ_SR = √(365/n), normal moments),
claim = Table 7 unrestricted 2022–23 mean:

| | BTC 1.01 | ETH 1.46 | BNB 2.90 | DOGE 1.17 | ADA 1.73 |
|---|---|---|---|---|---|
| 7.0 y | 0.219 | 0.666 | **1.000** | 0.363 | **0.867** |
| 2.5 y OOS | 0.032 | 0.128 | **0.868** | 0.055 | 0.235 |

So the memo's headline "0.05–0.20 over 7 years, 0.01–0.03 OOS" becomes "0.22–1.00 over 7 years,
0.03–0.87 OOS" for the variant the memo names. Under the script's own decision rule (every coin,
both windows, ≥ 0.80) the verdict is unchanged — BTC/ETH/DOGE fail both windows — but the
quantitative claim as written is wrong by a factor of ~4 for the unrestricted variant, and BNB
clears the floor on both windows once the right table is used.

The memo also proposed building BOTH variants ("5 coins × {unrestricted, long-spot-only}"), so the
Table 8 numbers are not irrelevant — they are the right claim for half the grid. But the decision
text attributes them to the wrong strategy.

---

## 1. The Sharpe convention

**Derivation.** Let the hourly strategy return be X = R while active (probability a), 0 while flat.
Then E[X] = aμ, Var[X] = a(σ² + μ²) − a²μ² = aσ² + a(1−a)μ². The hourly Sharpe of the calendar series
is aμ / √(aσ² + a(1−a)μ²) = √a · (μ/σ) / √(1 + (1−a)(μ/σ)²), and annualizing by √8760 gives
(μ/σ)·√(a·8760) / √(1 + (1−a)(μ/σ)²) = (μ/σ)·√N_active / √(1 + (1−a)(μ/σ)²). The Lucca–Moench
number is the numerator. The memo's "variance ≈ a·σ²" drops the (1−a)μ² term.

**When it fails, quantified from Table 6 High tier** (μ/σ per hour = SR/√N_active):

| coin | active | N_active | hourly μ/σ | LM SR | exact calendar SR | ratio |
|---|---|---|---|---|---|---|
| BTC | 0.201 | 1757 | 0.0429 | 1.80 | 1.7987 | 0.99926 |
| ETH | 0.227 | 1987 | 0.0572 | 2.55 | 2.5468 | 0.99874 |
| BNB | 0.350 | 3068 | 0.0874 | 4.84 | 4.8280 | 0.99753 |
| DOGE | 0.288 | 2522 | 0.0713 | 3.58 | 3.5735 | 0.99820 |
| ADA | 0.346 | 3031 | 0.0487 | 2.68 | 2.6779 | 0.99923 |

The μ² term is worth < 0.25% at the paper's hourly Sharpe ratios. It matters only where the
per-hour μ/σ is large — e.g. Table 8 BTC 2022 (active 0.02% of 8,760 h = 1.75 hours, one 1-hour
trade, implied hourly μ/σ = 0.385), and that cell is not an effect-size estimate at all (see §2).

**Other failure conditions, stated, none quantifiable from the paper:**
- *Non-zero return while flat.* The paper reports excess returns, so flat = 0 excess; holds.
- *Hourly → daily aggregation.* The DSR runs on daily returns. Daily Sharpe = hourly × √24 only if
  hourly returns are serially uncorrelated within a trade. A convergence trade on a mean-reverting
  basis has P&L ≈ −Δ(f−s) + funding; if (f−s) is mean-reverting, its changes are negatively
  autocorrelated, in which case the daily-aggregated Sharpe is HIGHER than the hourly-implied one
  (variance of a sum < sum of variances). Direction: the memo's use of the paper's number would be
  conservative. The paper reports no return autocorrelation, so this cannot be quantified; it is
  in the could-not-verify list. Funding is paid in 8-hour lumps, which does not change the daily
  aggregate.
- *The memo's "mean open-to-close ~135 h".* That is BTC only (Table 6: 134.94 h); ETH 83.7, BNB
  27.3, DOGE 13.8, ADA 40.6. Cosmetic.

**SURVIVES.** The convention claim is correct to < 0.25% at the relevant Sharpe ratios; the one
unquantifiable term (daily aggregation) most plausibly cuts in the memo's favour.

---

## 2. The conservative claim

**Is Table 7's 2022–23 the right conservative claim?** Not as used — see §0, the memo used Table 8.
Beyond the label, the deeper problem is that the per-year post-break cells are not Sharpe
estimates in any usable sense, because they rest on a handful of trades. From Table 7,
trades per year = active hours / mean open-to-close:

| coin | 2022 | 2023 | 2024 (70 d) | All (2020–24-03) |
|---|---|---|---|---|
| BTC | 807 h / 402.5 = **2.0** | 673 / 223.3 = **3.0** | 373 / 185.5 = **2.0** | 54 |
| ETH | 7.1 | 5.0 | 2.0 | 99 |
| BNB | 26.5 | 39.8 | 14.7 | 459 |
| DOGE | 45.4 | 3.0 | 3.0 | 670 |
| ADA | 78.0 | 9.3 | 2.0 | 307 |

The "BTC 2024 SR 11.52 on 1,682 hours" the brief flags is two trades. The 2022 BTC SR 0.70 is two
trades. Neither is a claim a pre-registration should declare; both are noise around a ~2-bet
sample. The honest description of the paper's post-break evidence for BTC/ETH is "5 trades a year
or fewer, sign positive in every year, Sharpe unestimable per year".

**What a fair-minded pre-registration would declare.** Three defensible choices, with the
decision under each (n_local = 16; all-coins-both-windows rule as in the memo's script):

| claim | source | 7 y power range | 2.5 y power range | decision |
|---|---|---|---|---|
| paper's headline: Table 6 High tier | what the paper actually claims (1.80–4.84) | 0.905–1.000 | 0.273–1.000 (BTC 0.27, ETH 0.72, ADA 0.78) | DECLINE (OOS window) |
| Table 7 unrestricted 2022–23 mean | the memo's intent, correctly sourced (1.01–2.90) | 0.219–1.000 | 0.032–0.868 | DECLINE |
| Table 7 pooled 2022 → 2024-03 (Lucca–Moench pooling of the three post-break rows)* | 1.41–3.03 | 0.611–1.000 | 0.111–0.908 | DECLINE |
| memo as written (Table 8 2022–23 mean) | long-spot-only (0.69–0.98) | 0.052–0.200 | 0.009–0.029 | DECLINE |

\* Pooling: per year μ = Return/N_a,yr and σ = Vol/√N_a,yr (the paper's own annualization
inverted), pooled μ and σ weighted by active hours, re-annualized by √(active hours per calendar
year). Self-check: pooling 2020–2024 this way reproduces the paper's "All" column exactly for all
five coins (1.80, 2.55, 4.84, 3.58, 2.68), so the reconstruction is sound. The pooled post-break
figure is, however, dominated by the 2024 two-trade cells (BTC 2.39 pooled vs 1.06 for 2022–23
alone) and should not be treated as stable.

**Does the decision flip?** Under the script's AND rule, no claim in the table flips it, because
the 2.5-year OOS window fails for BTC under every claim (best case 0.63 at the fragile pooled
number). Under the 7-year window alone, the paper's headline claim PASSES for all five coins
(0.905–1.000) and the corrected Table 7 claim passes for BNB and ADA. So the decision rests on
requiring 0.80 power on the out-of-sample window, which the memo justifies ("a build could only
replicate the paper's in-sample years"). That justification is stronger than the memo's numbers:
with 2–5 trades a year for BTC/ETH post-break, the 2.5-year OOS window holds roughly 5–13 bets,
and no Sharpe test at any bar resolves that. The bets-per-year hypothesis H1 in
`HYPOTHESES.md` ("under ~1,000 independent bets/year ... declining it at the sourcing stage")
declines this candidate on its own, two orders of magnitude clear of the line, without any power
arithmetic.

**n_local sensitivity** (required observed annualized Sharpe to clear 0.95 / power at three
claims):

| years | n_trials | required SR | power @ 0.69 | @ 1.01 | @ 1.80 |
|---|---|---|---|---|---|
| 7.0 | 5 | 1.073 | 0.156 | 0.434 | 0.972 |
| 7.0 | 16 | 1.303 | 0.052 | 0.219 | 0.905 |
| 7.0 | 37 | 1.439 | 0.024 | 0.129 | 0.830 |
| 7.0 | 362 | 1.740 | 0.003 | 0.027 | 0.563 |
| 7.0 | 1031 | 1.857 | 0.001 | 0.013 | 0.440 |
| 2.5 | 5 | 1.798 | 0.040 | 0.107 | 0.501 |
| 2.5 | 16 | 2.184 | 0.009 | 0.032 | 0.273 |
| 2.5 | 37 | 2.411 | 0.003 | 0.013 | 0.168 |
| 2.5 | 1031 | 3.113 | 0.000 | 0.000 | 0.019 |

A 5-spec grid (the smallest `MIN_TRIALS_FOR_DSR` allows) raises BTC's 7-year power at the corrected
claim from 0.22 to 0.43 and at the headline claim from 0.905 to 0.972; it does not lift any
sub-floor cell above 0.80. The pooled ladder rungs only lower power. Grid size does not change the
verdict.

**WEAKENED (how):** the memo's numbers are the long-spot-only variant's, mislabeled as the
unrestricted one; the unrestricted variant's power is ~4× higher and BNB clears the floor on both
windows. The decision survives because the OOS window still fails for BTC/ETH/DOGE under every
defensible claim, and — more robustly — because the paper's own Table 7 puts BTC/ETH at 2–7
trades a year post-break, which H1 declines directly. The memo should be corrected to say so
and to cite the trade count rather than the mislabeled Sharpe cells.

---

## 3. Pooling across coins

**What the paper reports.** Table 5, rows ρ_BTC..ρ_ADA (correlations of the hourly DEVIATION
LEVELS, not of strategy returns): BTC–ETH 0.89, BTC–BNB 0.58, BTC–DOGE 0.76, BTC–ADA 0.82,
ETH–BNB 0.61, ETH–DOGE 0.76, ETH–ADA 0.84, BNB–DOGE 0.58, BNB–ADA 0.56, DOGE–ADA 0.78; mean
pairwise 0.718. Text (§4.2): "arbitrageurs are willing to absorb the idiosyncratic demand first
because combining the arbitrage trades across different idiosyncratic deviations would generate a
high Sharpe ratio strategy as in Kozak et al. (2018). Therefore, in equilibrium, after
arbitrageurs have absorbed the idiosyncratic demand, we anticipate the emergence of a common
factor in deviations". The paper reports no portfolio Sharpe and no return correlations.

**Bound.** For an equal-weight, equal-vol portfolio of n trades with mean Sharpe S̄ and common
pairwise return correlation ρ, SR_p = S̄ / √((1+(n−1)ρ)/n). Using the deviation-level correlation
as the proxy for return correlation (the paper offers nothing closer; ρ = 0 is the upper bound on
diversification):

| claim (mean of 5 coins) | ρ = 0.718 (Table 5) | ρ = 0.5 | ρ = 0 (upper bound) |
|---|---|---|---|
| memo / Table 8 2022–23, S̄ 0.81 | SR_p 0.92 → 7 y 0.157, 2.5 y 0.023 | 1.05 → 0.250 / 0.037 | 1.82 → 0.912 / 0.281 |
| Table 7 2022–23, S̄ 1.65 | 1.88 → 0.936 / 0.315 | 2.13 → 0.986 / 0.469 | 3.70 → 1.000 / 0.991 |
| Table 7 pooled 22–24-03, S̄ 2.17 | 2.47 → 0.999 / 0.674 | 2.81 → 1.000 / 0.836 | 4.86 → 1.000 / 1.000 |
| Table 6 full, S̄ 3.09 | 3.51 → 1.000 / 0.981 | | |

20 coins at ρ = 0.718: factor 1.169 (vs 1.136 for 5) — breadth beyond 5 is worth ~3% Sharpe at the
paper's correlation. The equal-vol assumption is wrong in detail (2022 vols: BTC 0.40% vs BNB
1.77%), so an equal-notional book is tilted to the higher-vol coins; this is an approximation and
is stated as such.

**Does breadth rescue the claim?** At the Table 5 correlation, no: the 2.5-year OOS power at the
corrected post-break claim is 0.32 pooled. At the 7-year window and the corrected claim, yes
(0.94) — but that window is the paper's in-sample plus the OOS tail, which is the memo's point.
Only the ρ = 0 bound rescues the OOS window, and the paper's own text argues against ρ = 0 (a
common factor is the equilibrium prediction). A pooled 5-coin trade also cannot escape the trade
count: the 2022 sum across five coins is ~159 trades, 2023 ~60, 2024-partial ~24 — still far below
H1's line.

**SURVIVES.** Pooling is worth ~14% Sharpe at the paper's reported correlation; it does not lift
the OOS window above the floor at any post-break claim.

---

## 4. The DSR bar itself

**Moments.** Zero-when-flat returns are a mixture; if active-hour returns were normal the mixture
kurtosis is 3/a (15 at a = 0.20, ~100 at a = 0.03). Power with those moments, and with negative
skew (the loss tail of an unstopped convergence trade — the position is closed only at ρ = 0, never
on a loss):

| claim | (0, 3) | (0, 15) | (0, 100) | (−1, 15) | (−2, 30) |
|---|---|---|---|---|---|
| 0.69, 7 y | 0.052 | 0.052 | 0.046 | 0.049 | 0.045 |
| 1.01, 7 y | 0.219 | 0.217 | 0.200 | 0.207 | 0.195 |
| 1.80, 7 y | 0.905 | 0.900 | 0.865 | 0.880 | 0.853 |

The moment terms enter the Sharpe standard error only through s and s² at per-period scale
(s ≈ 0.05/day), so even kurtosis 100 moves power by < 0.05. `dsr_power`'s docstring says the
normal-case number is an upper bound for fat tails; that is confirmed in direction and shown to be
immaterial in size here.

**Non-i.i.d. hours.** The PSR standard error assumes i.i.d. periods. Daily returns from a
strategy holding one position for 135 h (BTC) are serially dependent across ~5.6 days per trade.
The effective sample is the trade count (§2), not the day count; the daily-Sharpe PSR does not
know this and will be over-confident in both directions. The project examined exactly this on
2026-09-09 (`project_bet_level_test_rejected` in session memory: a bet-level PSR failed its own
false-positive gate) and kept the daily PSR deliberately. So the gate is the project's standard,
and applying it here is consistent; but a reviewer should know that for THIS candidate the
"n = 2,555 daily observations" the power computation sees is really ~30–60 bets over 7 years for
BTC. That makes the true power LOWER than computed, not higher.

**"Bounded-loss arbitrage".** It is not bounded-loss: the paper's own MaxDD for BTC High tier is
−4.43% against 6.38%/yr return (Table 6), the position has no stop, and the funding_carry
docstring's cited BIS finding (carry predicts liquidations of the short-futures leg) applies to
the perp leg of this trade. The DSR bar is not the wrong instrument for it; a trade-count
criterion would simply be a sharper one.

**Does `criteria_audit` undercut the application?** Its F5 ("short-sample families are
structurally untestable at 0.95 ... a negative there is 'sample too short', never 'mechanism
refuted'") supports declining BEFORE building, which is what the memo did. Its executive summary
point 1 (the 0.95 bar cannot see Sharpe 0.3–0.5 edges; the error is the DEFINITE_NEGATIVE label,
not the bar) is consistent with a DECLINE_AT_SOURCING that makes no claim about the mechanism.
Nothing in either document undercuts the application; the audit's "count bets" reasoning
strengthens it.

**SURVIVES**, with the note that the computed power is an upper bound on two independent counts
(moments, and daily-vs-bet effective sample).

---

## 5. Novelty vs `cross_sectional_funding_carry`

The earlier family's docstring, verbatim: "WHAT THIS FAMILY ACTUALLY TESTS. The papers above study
single-name, delta-neutral carry (short perp vs long spot). This family tests the CROSS-SECTIONAL
version, in this project's established harness shape: rank the perp universe by trailing realized
funding, go SHORT the highest-funding names (collecting their funding) and LONG the lowest-funding
names ... equal-weighted legs, dollar-neutral in perp notional. That is a genuinely different (and
riskier) construction than the papers' hedged trade — it is exposed to the funding SPREAD's price
risk rather than hedged to spot". And: "(He, Manela, Ross & von Wachter 2022, 'Fundamentals of
Perpetual Futures', is cited by both papers for the same mechanism; that one is cited here VIA the
BIS paper — it was not itself read this session.)"

The memo's novelty claim is correct: different state variable (basis level vs funding rank),
different hedge (spot leg vs none), different holding logic (threshold-to-zero vs 7/30-day
rebalance), and Table 9 attributes the paper's return mostly to price convergence, not funding.
The earlier negative is not a prior on this one.

Two things the memo does not say that a reviewer should: (i) the He et al. long-spot-only leg IS
the Christin et al. "short perp + long spot, delta-neutral, single-name" trade the funding_carry
docstring already cites (Sharpe 8.76 full sample, "much smaller in the later part"), with a
threshold entry rule instead of always-on — so the delta-neutral basis trade is a documented
mechanism the project has read about twice, and both sources report the same post-2022 decay;
(ii) the funding_carry build note's independent verification found Binance VIP0 futures fees "2bp
maker / 5bp taker (2026 schedule, verified)" — a verified fee input the memo's §3 lists as
unverified. It does not cover the spot side.

**SURVIVES.**

---

## 6. Anything else

**6a. The decision rule is stricter than the project applied to its equity families.** Every
literature-grounded equity family was backtested over a window overlapping the source paper's
sample, and none was declined for it; the remedy was forward validation. The memo requires 0.80
power on the post-publication window alone. That is a defensible reading of the sourcing rule
(the LETF pre-registration likewise noted "Entire sample is post-publication" as a virtue), but it
is a new standard being applied for the first time and should be written down as such, or the
next candidate will be judged inconsistently. It does not reverse the decision: the trade count
(§2) declines this candidate under the older standard too, once H1 is adopted.

**6b. The script mutates a committed artifact.** `sourcing_power_perp_basis.py` rewrites
`sourcing_power_perp_basis.json` (with a fresh `written_utc`) on every run, so any verification
run dirties the tree. Cosmetic; note for the pattern.

**6c. Sample-window arithmetic.** The memo's "7.0 y" runs from the 2019-09 perp listing; the
paper's own analysis starts 2020-01-08 (Aave rate availability, Table 2) and DOGE's perp from
2020-07. A build that follows the paper's r definition has 6.7 y for BTC/ETH and 6.2 y for DOGE.
Immaterial to the verdict.

**6d. Retail fee tier.** The paper's High tier is MAKER 6.75/1.44 bp. Table 3's own formula
ρ_u = κ·ln(1+C) with C the round-trip cost gives 179.2%/yr at the paper's tier (reproduced). At a
plausible retail TAKER schedule of 10 bp spot / 5 bp futures (the futures side is the verified
2026 VIP0 taker fee from the funding_carry verification; the spot side is UNVERIFIED) the bound is
328%/yr; at 10 bp spot maker / 2 bp futures maker, 262%/yr. The opportunity set beyond 328% is a
strict subset of the set beyond 179%, and the paper does not report it. Any descriptive
measurement must tabulate at the retail-taker bound, not only at the paper's.

**6e. Is Block C′ (descriptive measurement of ρ) the right next step?** Yes, cheap and decisive —
but the memo's proposed table (share of hours beyond the bound, mean excursion, mean time-to-zero)
omits the one number that decides sourcing: **excursions (trades) per year**, by coin, by year,
at BOTH bounds (179% and ~328%). That is H1's bets-per-year figure and it is what §2 shows the
paper's post-break cells are hiding. If the 2024–2026 count is in the tens per coin-year the entry
can be reopened on a pooled book; if it is single digits the ground is closed at the sourcing
stage on evidence rather than on a mislabeled Sharpe. Two cautions for the builder: the Aave r
series is small against the bound but its sign matters near ρ = 0 (the close rule), so a constant
r must be disclosed; and hourly klines give ρ at bar close only, so excursions shorter than an
hour are invisible (the paper has the same limitation, so the comparison is fair).

**6f. Nothing here reverses the decision.** The strongest reversal candidate — "use the paper's
headline Table 6 claim, as every other family did" — passes the 7-year window for all five coins
but fails the OOS window for BTC/ETH/ADA, and is then refuted by the post-break trade count
independently of any Sharpe.

---

## Verdict

**SURVIVES, WEAKENED.** The decision stands; the memo's headline power numbers do not. They are the
long-spot-only variant's (Table 8), mislabeled as the unrestricted strategy's (Table 7). The
unrestricted variant's corrected power is 0.22–1.00 over 7 years and 0.03–0.87 on the 2.5-year OOS
window (BNB clears the floor on both). The decline survives on the OOS window for BTC/ETH/DOGE
under every defensible claim, and more robustly on the paper's own trade counts: BTC 2/3/2 and
ETH 7/5/2 trades in 2022/2023/2024-partial, two orders of magnitude under H1's ~1,000 bets/year
line. Required corrections before the memo is treated as final: relabel the constants and the
"active %" range as Table 8; add the corrected Table 7 row; cite the trade count as the primary
ground; add excursions-per-year at both fee bounds to Block C′.

## Could not verify

- Return autocorrelation of the paper's hourly strategy series (needed to sign the hourly→daily
  aggregation effect); the paper reports none.
- Correlation of the five coins' STRATEGY RETURNS (Table 5 gives deviation-level correlations
  only); the pooling bound uses those as a proxy.
- Skewness/kurtosis of the paper's returns; not reported, so the moment sensitivity uses the
  mixture-kurtosis argument and assumed skews.
- Binance spot fee schedule today (the memo's gap stands; only the futures VIP0 2/5 bp figure is
  verified, via `funding_carry_build_2026-08-29.txt`).
- Whether the paper's Table 7 "N" and "Active %" are on the same hour basis as its OtC (the trade
  count = N·active/OtC arithmetic assumes so; the self-check that pooling the yearly rows
  reproduces the "All" column supports it but does not prove it).
- Whether the project's sourcing rule requires power on the post-publication window alone; no
  written rule says so (H1 is a hypothesis "recommended for adoption", ORCHESTRATOR_NOTE line 26).
- Aave USDT/USDC/DAI rate history availability (the memo's gap; not attempted here).
