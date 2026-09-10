# PRE-REGISTRATION — LETF end-of-day rebalancing pressure (`letf_rebalancing_eod`)

Written 2026-09-11 by the orchestrator (Fable 5.1) BEFORE any minute-bar panel for this
family was assembled and before any return statistic of any kind was computed. Committed
to branch `letf-feasibility-2026-09-11` and merged to `main` before the build is
dispatched. Amendments after this commit go in dated ADDENDUM files; this file is never
rewritten. Feasibility record: `../letf_rebalancing_feasibility_2026-09-11/` (memo +
`ORCHESTRATOR_REVIEW_2026-09-11.md`, which corrects two memo errors and adds Tuzun 2013).

## 0. Scope limits (CLAUDE.md rules 4 and 6)

Observational research only. No registration, no live-status change, no real capital, no
paid data. The result is a recommendation. Every number in section 4 is declared here so
that nothing about the verdict can be chosen after the data is seen.

## 1. Mechanism and sources (verbatim provenance in the feasibility directory)

An LETF with leverage L and assets A must trade (L² − L)·A·r of its index near the close
on a day the index returns r, to restore target exposure — Cheng & Madhavan (2009) as
quoted in Shum, Hejazi, Haryanto & Rodier, *Review of Finance* 20(6) 2016, Eq. (1)
(post-print read in full); the same expression is Ivanov & Lenkey, FEDS 2014-106, Eq. (6)
(read in full). Bull and bear funds trade the same direction. The execution window is
the last part of the session: Shum et al. §2 ("as early as 15:30"), Tuzun FEDS 2013-48
("the last hour of trading").

**Claimed return effect, the effect the power block is calibrated against** — Tuzun
(2013) Eq. (2), Table IV Panel A, control included: the 15:00–16:00 return of an S&P 500
member, in units of its 20-day daily σ, rises by β = 4.32 (s.e. 0.57, N = 684,869,
2006-06-19..2011-12-31) per 1% of the stock's 20-day ADV of implied LETF flow; Nasdaq-100
members 3.83 (0.83), Russell 2000 members 0.86 (0.08). The paper's own translation: 6.9 bp
in an average large stock on a 1% index day at December-2011 AUM. **Reversal** — Tuzun Eq.
(3), Table VI Panel A: the lagged flow coefficient on the close→next-15:00 return is −3.52
(1.08) large caps, −4.24 (1.65) Nasdaq-100, −0.35 (0.10) Russell 2000.

**Known offsets, declared now**: Ivanov & Lenkey Table III measure that investor flows cut
the realised rebalancing coefficient to 1.5–3.5 (m = +3) and 7.3–8.8 (m = −3) against the
mechanical 6 and 12 in the tail return quintiles; Jain, Mishra, Pagano & Rodriguez (EFMA
2024 WP) find the effect state-dependent on index-return autocorrelation through 2020.
Neither paper reports a decay to zero. The test below is unconditional (Tuzun's claim is
unconditional); no regime split is pre-declared.

**Entire sample is post-publication**: Tuzun's sample ends 2011-12-31; the earliest minute
bar here is 2016-01-04. Zero overlap, as with `intraday_momentum_spy`.

## 2. Data

- Underlyings: **SPY, QQQ, IWM** only (the three whose LETF complex has a free daily AUM
  history — ProShares `historical_nav.csv`, coverage verified to each fund's inception in
  `ORCHESTRATOR_REVIEW_2026-09-11.md` §2). Funds: SSO SDS UPRO SPXU (S&P 500); QLD QID
  TQQQ SQQQ (Nasdaq-100); UWM TWM URTY SRTY (Russell 2000). Direxion's funds (SPXL/SPXS,
  and for Russell 2000 whatever the builder verifies exists) have no free history and are
  EXCLUDED from the coefficient; their current share of each underlying's coefficient is
  disclosed in the run report as a scaling omission. Semiconductors, biotech, gold miners:
  out of scope (feasibility memo Q3).
- AUM: `Assets Under Management` column, one row per fund per day; A_{i,t−1} is the value
  dated the previous trading day (published after that day's close, known before day t's
  open). Sanity check, reported: AUM ≈ NAV × Shares Outstanding (000) × 1000 within 0.1%
  on ≥ 99% of rows, else the discrepancy rows are listed. Rows are the issuer's current
  historical record; restatements are undetectable and this is disclosed on the card.
  The file is fetched by URL into the MAIN checkout's `data/letf_aum/` with the fetch date
  in the filename and the SHA-256 recorded in the run report; it is not committed
  (52 MB).
- Minute bars: Alpaca SIP 1-minute regular-session bars via `AlpacaProvider.get_stock_bars`
  (feed "sip"), 2016-01-04..the last complete UTC session before the run, cached as
  per-ticker pickles under the MAIN checkout's `data/letf_1min_bars/` (same convention as
  `data/spy_1min_bars/`; the existing `SPY_1Min.pkl` may be reused if its date range is
  extended, never spliced from two feeds). Daily bars for the volume feed check as in
  `intraday_momentum_spy` PREREGISTRATION §2c.
- Session usability rules U1–U3 and the no-predecessor rule are copied unchanged from
  `intraday_momentum_spy.py` (≥ 380 bars, last bar start ≥ 15:55, each block complete);
  a session is used only if all three underlyings pass, so the panel is balanced.

## 3. Constructions (fixed here; no parameter is tuned on returns)

Per underlying u and session t, with bar timestamps = bar START times:

- r_open→w: return from the previous session's 15:59 close to the OPEN of the bar
  starting at w (w = 15:30 primary, 15:00 secondary). This is Tuzun's "previous day's
  close to 15:00" predictor with our window.
- Coefficient K_{u,t} = Σ_i A_{i,t−1}·(L_i² − L_i) over the underlying's ProShares funds.
- Implied demand D_{u,t} = K_{u,t} · r_open→w (dollars, signed).
- Scaled signal x_{u,t} = D_{u,t} / ADV20_{u,t−1}, ADV20 = the ETF's own trailing 20-session
  dollar volume (an UPPER bound on flow/liquidity, since real rebalancing hits constituents
  and swaps — feasibility memo Q5; disclosed, not corrected).
- Target return y_{u,t}: open of the bar starting at w → close of the 15:59 bar.
  Reversal target z_{u,t+1}: close of session t → open of the bar starting 15:00 on t+1.

**Trading specs** (each is one trial; positions are ±1 units of the ETF, closed at the
window end, one bet per session per underlying):

| id | rule | window | underlying |
|---|---|---|---|
| A_u_w | long y if x > 0, short if x ≤ 0 (tie = short, as GHLZ Eq. 4) | w ∈ {15:30, 15:00} | u ∈ {SPY, QQQ, IWM} |
| B_u_w | as A but flat when \|r_open→w\| < 0.50% | same | same |
| P_w | equal-weight average of A_u_w across the three underlyings | same | pooled |
| R_u | reversal: short z if x_t > 0, long if x_t ≤ 0 | close→15:00 | u ∈ {SPY, QQQ, IWM} |

12 + 2 + 3 = 17 specs. **Controls, counted in the grid (n_local = 20)**:
- C1 (constant-AUM control): A_u_15:30 with K_{u,t} replaced by its sample mean for u —
  i.e. plain intraday momentum. Under the mechanism, A beats C1 only through the
  time-variation of K/ADV (K rose roughly an order of magnitude over 2016–2026 while ADV
  did not), which is what the regression in §4.1 tests directly.
- C2 (shuffled-AUM placebo): K_{u,t} permuted across sessions with a fixed seed (12345),
  one draw, for the pooled 15:30 spec. Must not pass.
- C3 (wrong-window control): pooled A rule applied to 10:00→10:30 instead of the last
  window. The mechanism predicts nothing here.

The 0.50% cut in B is a fixed number chosen before any data (it is the |r| at which
Tuzun's Dec-2011 large-cap effect is ~3.5 bp, roughly the round-trip cost of the verdict
arm); it will not be moved.

## 4. Verdict rules, declared before any result

### 4.1 Mechanism gate (layer 2, must pass before any economic claim is attributed)
Pooled OLS across u and t: y_{u,t}/σ20_{u,t} = a + b·x_{u,t}·100 + c·r_open→w/σ20 + e,
standard errors clustered by session (Tuzun Eq. 2 in our units; x·100 puts x in percent
of ADV so b is on Tuzun's scale). Pass iff b > 0 with t ≥ 2.0 at w = 15:30. If it fails,
the family's verdict is written as "momentum, not LETF" whatever the trading specs show,
and no spec is recommended for registration. The point estimate of b is reported next to
Tuzun's 4.32 with the honest note that ADV here is the ETF's, so b is not on the same scale.
Reversal check: the same regression with z_{u,t+1} on x_{u,t}; sign reported, not gating.

### 4.2 Economic gate (layers 1 and 4)
- Costs are inside the return series: verdict arm 1.0 bp one-way on every entry and exit
  (the `intraday_momentum_spy` ADDENDUM_01 arm — SPY's one-cent tick permits at most
  ~0.14 bp half-spread at a $360 close; 1.0 bp is deliberately conservative and covers
  QQQ/IWM). Stress arm 2.0 bp one-way. A cost-free arm is reported for attribution only.
- DSR on the NET daily series of each spec at every rung of the ladder from
  `dsr_policy_n` (n_local = 20, then the policy rungs as the module returns them on the
  run date — 43 / 397 / 1131 as measured 2026-09-09; if the file has been re-measured the
  run uses the current values and says so). Bar 0.95 validated-edge, 0.50 screening
  floor, as `registration_scorecard` defines them.
- `preservation_score` on every spec, no exceptions.
- Two-tier reading per CLAUDE.md §4: fails at n_local → definite_negative if the power
  block (4.3) is ≥ 0.80, else underpowered; passes n_local but fails a pooled rung →
  unresolved; passes 1131 → real pass → recommend registration (owner decides).

### 4.3 Power block (computed BEFORE the returns, from the data's own σ)
Using `dsr_power.dsr_power_report` with its default skew 0 / kurt 3 and periods_per_year
= usable sessions per year: the claimed effect is the Tuzun Dec-2011 large-cap number,
6.9 bp of window return per 1% of |r_open→w|, applied linearly to the sample's
|r_open→15:30| distribution, giving an expected gross daily return E[6.9 bp × |r|/1%] and
a Sharpe against the sample's realised σ of y; net of 2 bp round trip. Two calibrations
are reported: full Tuzun, and 50% of Tuzun (the Ivanov-Lenkey m=+3 flow offset). The
family is declared underpowered for the claim in advance if the 50% arm's power to clear
0.95 at n_local is < 0.80. The builder computes these from the σ of y and |r| only — no
strategy return is needed or allowed at this step — and commits them before running §4.2.

### 4.4 What is NOT allowed
No extra windows, cuts, weights, underlyings, or cost arms beyond the table. No dropping a
spec after seeing it. No "the effect is there in a subperiod" claim unless the subperiod
was declared here (none is). Any deviation is an ADDENDUM committed before the affected
result exists, as in `intraday_momentum_spy`.

## 5. Prior evidence this test must be read against
`intraday_momentum_spy` (merged 9077f59) tested GHLZ's r1→r13 and r12→r13 on SPY over the
same minute bars and was DECLINED/underpowered with the r1 predictor's sign reversed out of
sample. C1 here is close to that family's r12-type predictor extended to the full day.
A positive on A that is not distinguishable from C1 is that family's result again, not a
new mechanism, and the §4.1 gate is written to force that distinction.

## 6. Deliverables
`app/services/research_lab/letf_rebalancing_eod.py` (family key `letf_rebalancing_eod`),
`data/research_runs/fetch_letf_aum.py`, `data/research_runs/fetch_letf_1min_bars.py`,
`data/research_runs/run_letf_rebalancing_eod.py`, tests mirroring `test_intraday_momentum
_spy.py` (formula validation on synthetic data with a known answer: a synthetic panel where
y = β·x + noise must recover β and the verdict logic must classify known-Sharpe series
correctly), `POWER_BLOCK.md` committed before results, `RUN_REPORT.txt`, `run_output.json`,
trial rows persisted through the same store the other timing families use, and a draft
registration scorecard with layers 1–4 filled from the paper text in this directory.
