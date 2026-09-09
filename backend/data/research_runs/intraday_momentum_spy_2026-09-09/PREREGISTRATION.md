# Pre-registration — Market intraday momentum on SPY (`intraday_momentum_spy`)

**Written and committed 2026-09-09, BEFORE any backtest of this family was run.**
Nothing below may be revised after a strategy return exists. Any deviation
forced by the data is appended as a dated addendum with its reason, never a
silent edit.

Worktree `.claude/worktrees/intraday-momentum`, branch
`intraday-momentum-2026-09-09`, off `main` at `35943a1`.

---

## 0. The one-line claim being tested, and the headline caveat

**Claim.** The first half-hour return of the trading day, measured from the
PREVIOUS day's close, predicts the sign of the last half-hour return on the
same day, on the S&P 500 ETF.

**THE ENTIRE SAMPLE HERE IS OUT-OF-SAMPLE RELATIVE TO THE PAPER.** The source
paper's sample is 1 February 1993 – 31 December 2013. This project's free
Alpaca minute-bar history starts 2016-01-04. There is **zero overlap**. This is
not a replication and cannot be one: it is a pure out-of-sample test of a claim
published (JFE) in 2018 on data ending in 2013, run on the 2016–2026 period,
after 8 years of publicity. A negative here is fully consistent with the paper
having been right about 1993–2013.

---

## 1. Primary source — OBTAINED and read

**Obtained.** The scoping memo
(`../intraday_data_scoping_2026-09-09/INTRADAY_DATA_SCOPING.md` §M3, §6 item 1)
recorded that SSRN 2440866 returned HTTP 403 and that the paper's own Sharpe /
success rate / break-even cost were therefore UNVERIFIED. **That gap is now
closed.** On 2026-09-09 the working-paper PDF was fetched from

    https://www.smallake.kr/wp-content/uploads/2015/01/SSRN-id2440866.pdf

(a third-party mirror of SSRN id 2440866), and its text extracted with
`pdftotext -layout`. Header page, verbatim:

> Intraday Momentum: The First Half-Hour Return Predicts the Last Half-Hour Return
> Lei Gao (Iowa State University), Yufeng Han (University of Colorado Denver),
> Sophia Zhengzi Li (Michigan State University), Guofu Zhou (Washington
> University in St. Louis). First Draft: March, 2014. Current Version:
> October, 2014.

**IMPORTANT PROVENANCE LIMIT, stated rather than glossed.** This is the
**October 2014 working-paper version**, not the published *Journal of Financial
Economics* 129(2) (2018), 394–414 article. Author affiliations differ from the
published version (Han is at Colorado Denver here, UNC Charlotte in the
published version; Li at Michigan State here, Rutgers in the published version),
which confirms it is an earlier draft. **Every number quoted below is from the
October 2014 draft.** Whether the published 2018 version reports the same
figures is **UNVERIFIED** — the JFE/ScienceDirect page is paywalled and SSRN
still 403s. The draft's sample (Feb 1993 – Dec 2013) matches the published
abstract's, and its OOS R² for r₁ (1.69%) matches the Monash replication's
independently-verified corroboration of a ~1.7% figure, so the draft is not
obviously superseded — but it is a draft, and is labelled as one everywhere.

### 1a. The exact return definition (draft §2, Eq. 1) — verbatim

> Specifically, to examine the intraday return predictability, we calculate
> half-hour (30 minutes) returns on any trading day t from 9:30 am to 4:00 pm
> Eastern time, a total of 13 observations per day, from
>
>     r_{j,t} = p_{j,t} / p_{j-1,t} − 1,   j = 1, ..., 13,            (1)
>
> where p_{j,t} is the price at the j-th half-hour and p_{j−1,t} is the price at
> the previous half-hour, for j = 1, . . . , 13. Note that p_{0,t} is the
> previous trading day's price at the 13th half-hour (4:00 pm). That is, we use
> the previous trading day's closing price as the starting price when
> calculating the first half-hour return on day t, i.e., p_{0,t} = p_{13,t−1},
> so that the first half-hour return captures the impact of information since
> the previous trading day's closing time.

So, unambiguously:

| symbol | window | price ratio |
|---|---|---|
| r₁ | previous 16:00 → today 10:00 | p(10:00) / p_prev(16:00) − 1 |
| r₂ | 10:00 → 10:30 | p(10:30) / p(10:00) − 1 |
| r₁₂ | 15:00 → 15:30 | p(15:30) / p(15:00) − 1 |
| r₁₃ | 15:30 → 16:00 | p(16:00) / p(15:30) − 1 |

(The published version labels the last half-hour rₙ and the penultimate one
rₙ₋₁; n = 13 for US regular hours. Same objects.)

### 1b. The exact strategy rule (draft §4.1, Eqs. 4 and 5) — verbatim

> we will take a long position of the market at the beginning of the last
> half-hour if the timing signal is positive, and take a short position
> otherwise. It is worth noting that the position (long or short) is closed at
> the market close each trading day.
>
>     η(r₁) = { r₁₃  if r₁ > 0 ;  −r₁₃  if r₁ ≤ 0 }                    (4)
>
> When using both r₁ and r₁₂ as the trading signal, we buy only if both returns
> are positive, and sell when both are negative. Otherwise, we stay out of the
> market.
>
>     η(r₁, r₁₂) = { r₁₃ if r₁>0 & r₁₂>0 ; −r₁₃ if r₁≤0 & r₁₂≤0 ; 0 otherwise } (5)

Note the tie convention: `r₁ ≤ 0` is **short**, not flat. Reproduced exactly.

### 1c. The paper's own reported performance — VERIFIED from the draft

Draft Table 5 ("Market Timing"), Panel A and B, sample Feb 1993 – Dec 2013,
SPY, transcribed verbatim:

| Timing Signal | Avg Ret(%) | Std Dev(%) | SRatio | Skew | Kurt | Annual Cum Ret(%) | Cum Ret(%) | Success(%) |
|---|---|---|---|---|---|---|---|---|
| r₁ | 6.67*** (t=4.36) | 6.19 | **1.08** | 0.90 | 15.65 | 6.08 | 109.39 | **54.37** |
| r₁₂ | 1.77 (t=1.16) | 6.20 | 0.29 | 0.38 | 15.73 | 1.62 | 29.08 | 50.93 |
| r₁ and r₁₂ | 4.39*** (t=3.96) | 4.49 | 0.98 | 1.87 | 34.10 | 4.00 | 71.98 | **77.05** |
| *Always Long* | −1.11 (t=−0.73) | 6.21 | −0.18 | −0.46 | 15.73 | −1.02 | −18.27 | 50.42 |
| *Buy-and-Hold* | 6.04 (t=1.19) | 20.57 | 0.29 | −0.16 | 6.61 | 5.50 | 98.99 | — |

Draft footnote 4, verbatim: "Even though we are only in the market for the last
half hour, we still annualize the returns by multiplying a factor of 252 because
we only trade once per day."

Draft Table 3 (out-of-sample R²): **r₁ alone 1.69%**, r₁₂ alone 0.92%, both
2.53%; β_r1 = 0.05*** (t = 31.8), β_r12 = 0.07*** (t = 21.9). In-sample R²
(draft §1): 1.6% for r₁, 2.6% for both.

**These Table 5 numbers are gross of transaction costs.** The draft's cost
discussion is separate (§1d).

### 1d. The paper's own transaction-cost treatment — VERIFIED, and it is
generous

Draft §4.2, verbatim:

> Consider day trading 1000 shares of SPY. ... At an online broker, such as
> Tradestation, an active individual investor can pay only $4.99 commission ...
> Then, the percentage cost of a daily round trip per year is bounded by
> 252 × 10/(1000 × 100) = 2.52% as the price of the SPY is $100 and above (up to
> about $200) a majority of the time over the sample period. Because of the
> decimalization, the bid/ask spread is just 0.01/100 per trade. **Since the
> closing of the SPY is uniquely traded at the market clearing price for all the
> buys and sells, there will be no bid/ask spread effect here.** Therefore, the
> trading cost due to the bid/ask spread is only 0.5 × 0.01/100 = 0.005/100 per
> day, and 252 × 0.005/100 = 1.26% per year. Thus, the total trading cost is
> under 3.78% per year. Since the average return is 6.85% per year when r₁ is
> used as the predictor, the economic gain is about 3.07% per year.

**No break-even cost is reported anywhere in the draft.** The closest thing is
the 3.78%/yr total-cost bound above; it is not framed as a break-even. This
project therefore computes its own break-even and labels it as its own.

Two things about that passage are worth flagging *before* results exist, because
they cut in opposite directions and both are relevant to 2016–2026:

1. The **commission** half (2.52%/yr) is obsolete in the good direction — US
   retail equity commissions went to zero in 2019. Modelling it today would
   manufacture a false negative.
2. The **spread** half is optimistic. The paper charges only **one** half-spread
   (0.5 bp/day) for the entire round trip, on the argument that the closing
   print is a single clearing auction and therefore free. The 15:30 entry is
   still a spread-crossing liquidity-taking trade, and the closing auction is
   not free either — it has its own imbalance-driven price impact, measured at
   ~8.1 bp mean absolute deviation by Bogousslavsky & Muravyev (2023) as quoted
   in this project's own scoping memo §M1. This test does **not** adopt the
   paper's zero-cost-at-the-close assumption.

---

## 2. Data

**Instrument.** SPY only. **Source.** `AlpacaProvider.get_stock_bars(["SPY"],
timeframe="1Min", ...)`, `regular_session_only=True`, `feed="sip"` (the
provider's explicit default), `adjustment="all"`.

**Window.** `2016-01-04` → `2026-09-08` (the latest complete session before this
run). 2016-01-04 is the first trading day of 2016; the addendum
`ADDENDUM_ALPACA_PROBE.md` verified 390 rows for 2016-01-05 on this account.

**Cache path (declared, so a worktree removal cannot destroy it).**

    <MAIN checkout>/backend/data/spy_1min_bars/SPY_1Min.pkl

resolved via `app.config._main_checkout_backend_dir`, exactly as
`data/research_runs/fetch_intraday_bars_15min.py` does, and gitignored with an
explanatory block in `backend/.gitignore` following the
`data/intraday_bars_15min/` precedent. Refetchable vendor input, not a result;
the results live in `cross_sectional_trial_results` and in this directory.

### 2a. Bar aggregation — which minute bars form which half-hour

Alpaca bar timestamps are **bar-START** times, tz-aware `America/New_York`
(`alpaca_provider.py`: "Bar timestamps are bar-START times: a regular-session
bar starts at or after 09:30 and strictly before 16:00 ET").

Half-hour block *j* (j = 1..13) is the set of 1-minute bars whose **start** time
lies in

    [ 09:30 + 30·(j−1) minutes ,  09:30 + 30·j minutes )

So block 1 = starts 09:30..09:59, block 12 = 15:00..15:29, block 13 =
15:30..15:59. **p_j = the `close` of the LAST bar in block j** (i.e. the print at
the block's closing instant, up to the last available minute). p₁₃ is therefore
the close of the 15:59 bar = the session's regular-hours closing price.

r_j = p_j / p_{j−1} − 1 for j = 2..13, and r₁ = p₁ / p₁₃(previous usable
session) − 1.

### 2b. Missing bars and early closes — DECLARED NOW, not after seeing results

A calendar date's session is **usable** iff all three hold:

* **(U1)** at least one 1-minute bar in **every** one of the 13 blocks;
* **(U2)** the session's last bar starts at or after **15:55** (this is what
  actually excludes early-close half-days — a 13:00 close has no 15:30–16:00
  half-hour at all, so r₁₃ does not exist and the trade is untradeable, not
  merely awkward);
* **(U3)** at least **380** 1-minute bars in total (390 is a full session; the
  10-bar slack absorbs isolated no-trade minutes without admitting a truncated
  session).

Within a usable session, a missing minute inside a block is **not** an error:
p_j takes the last bar actually present in that block. This is last-price
sampling, the same convention the paper's TAQ construction implies.

A **trading day enters the sample** iff its session is usable AND the previous
usable session in the sequence is within **5 calendar days** (so a long gap
never turns r₁ into a multi-day return, which is not the paper's construction).
The first usable session of the sample has no predecessor and is dropped.

Every drop is **counted and reported by reason** in the run report. No
session is dropped for any reason not listed here.

### 2c. Feed check (one cheap test, per the task brief)

The scoping addendum flagged that the free Alpaca tier is advertised IEX-only
while `alpaca_provider.py`'s header records a 2026-08-26 measurement showing
this account returns full SIP data by default. **Test:** for a handful of
sample dates, sum the `volume` column of the 1-minute bars and compare against
the same day's `1Day` bar volume from the same endpoint. Consolidated SPY volume
runs ~50–100M shares; IEX-only would be a few percent of that. Result reported
in the run report either way.

**Why it does or does not matter is stated in advance:** this is a **price-return**
test — every quantity in §1a is a ratio of two *prints*. IEX prints are inside
the consolidated NBBO essentially always, so a thin-feed last-print at 15:59
differs from the consolidated last-print by at most a fraction of a
sub-penny-wide spread on a $400–700 instrument. A materially thin feed would,
however, raise the chance that a given minute has **no** bar at all, which feeds
directly into the §2b usability rules — so the check is run, and the drop counts
are reported alongside it.

---

## 3. Spec grid — 8 specs, N_local = 8

Deliberately tight. The scoping memo §3c measured that grid width dominates
every other lever: at a true Sharpe of 1.0 the years-to-detect goes from 13.92
(N=12, σ_SR=0.2) to 220.53 (N=12, σ_SR=0.5). Eight specs is the smallest grid
that covers the paper's own three signals plus one pre-declared control.

| # | spec_id | predictor | rule | control? |
|---|---|---|---|---|
| 1 | `r1__sign` | r₁ | sign | no |
| 2 | `r1__deadband10bp` | r₁ | dead-band | no |
| 3 | `r12__sign` | r₁₂ | sign | no |
| 4 | `r12__deadband10bp` | r₁₂ | dead-band | no |
| 5 | `r1_and_r12__sign` | r₁ & r₁₂ | sign | no |
| 6 | `r1_and_r12__deadband10bp` | r₁ & r₁₂ | dead-band | no |
| 7 | `placebo_r2__sign` | r₂ | sign | **YES** |
| 8 | `placebo_r2__deadband10bp` | r₂ | dead-band | **YES** |

Sizing is **unit** (|w| = 1) for every spec — the paper's Eq. 4/5 rule exactly.
No leverage, no volatility scaling, no forecast-proportional sizing. (The
scoping memo's derived Sharpe of 2.09 assumes *optimal linear scaling*; that is
a different, richer strategy and is deliberately NOT in this grid, because it
would need a fitted coefficient and would widen the grid.)

**Justification of each cell, from the source:**

* **predictor r₁** — the paper's headline signal; Eq. (4); Table 5 Panel A row 1
  (SRatio 1.08).
* **predictor r₁₂** — the paper's second signal; same Eq. (4) form; Table 5
  Panel A row 2 (SRatio 0.29). Included because the paper reports it as a
  co-equal timing signal, not because it looked promising.
* **predictor r₁ & r₁₂** — the paper's Eq. (5) combination; Table 5 Panel A row 3
  (SRatio 0.98, success 77.05%).
* **rule `sign`** — Eq. (4)/(5) verbatim, including the `≤ 0 ⇒ short` tie.
* **rule `deadband10bp`** — identical to `sign` except the position is **flat**
  when |predictor| ≤ **0.0010** (10 bps). Licensed by the paper's own footnote 9,
  verbatim: "In practice, one may trade only on high volume or more profitable
  days to reduce total transaction costs", and by its Table 6, which reports the
  timing performance rising monotonically across first-half-hour volatility
  terciles. **This is a DEVIATION from the paper's construction and is logged as
  one** — the paper never specifies a threshold. **The 10 bp value is a single
  a-priori number fixed here and is NOT gridded, tuned, or revisited.** For the
  combination predictor the dead-band applies to both legs (both must exceed it,
  in the same direction).
* **placebo r₂** — the 10:00–10:30 return, the half-hour immediately after the
  paper's predictor window. It has the same scale, the same instrument, the same
  intraday-noise structure and the same number of observations as r₁, but no
  overnight-information content and no role in the paper's mechanism (which is
  overnight news → informed/day-trader positioning → unwind into the close).
  Pre-declared use of the result is in §6.

**N_local = 8, the literal grid size, controls included** (including them raises
the denominator, i.e. is the conservative choice). Raised by
`global_effective_n.dsr_n_trials` if that is larger; measured today
`dsr_n_trials(8) = 8`. **No spec may be dropped from the count after the fact
for any reason.** The full ladder is `dsr_policy_denominators(8)` =
**{8, 37, 362, 1031}**.

---

## 4. Cost arms — the verdict arm is fixed here, before any result

The position is opened at 15:30 and closed at 16:00 **every** traded day, so a
traded day pays **two** one-way crossings. A flat day (dead-band, or Eq. 5
disagreement) pays **zero**. There is never any netting across days, because the
paper closes the position at every close.

| arm | one-way bps | role |
|---|---|---|
| `cost_free` | 0.0 | **attribution only, never a verdict input** |
| `baseline` | see below | **THE VERDICT ARM** |
| `conservative` | 5.0 | project-wide default `intraday_patterns.INTRADAY_COST_BPS` |

**The `baseline` one-way cost is set by a PROCEDURE declared now and frozen in a
committed addendum before any strategy return is computed:**

> baseline_one_way_bps = max( 0.5 , round_up_to_0.1bp( EDGE-estimated median
> effective HALF-spread of SPY over the full sample ) )

where the EDGE estimate comes from this project's own
`app/services/research_lab/spread_estimator.py` (the `bidask` package's
implementation of Ardia, Guidotti & Kroencke's EDGE estimator), run on SPY daily
OHLC over the sample window. The 0.5 bp floor is the paper's own per-day spread
charge (§1d), so the verdict arm can never be cheaper than the source's own
assumption.

**Why not just use the project's 5 bps default as the verdict arm.** The scoping
memo §4 (M3) already flagged this in advance: "the project's 5 bps one-way cost
model is calibrated for a broad cross-section and would be punitive and
unrealistic here — **using it unchanged would manufacture a false negative**, and
changing it for one family needs an explicit, logged, reviewed justification".
SPY is the single most liquid equity instrument in the world; its quoted spread
is one cent on a several-hundred-dollar price. A 5 bp/side charge is ~30–60×
SPY's own half-spread and would decide the result by assumption. It is retained
as the **`conservative` arm** and reported at every ladder rung alongside the
verdict arm, so nothing is hidden — but it is not the verdict.

**Cost realism feeds the DSR directly** (CLAUDE.md §4): DSR, preservation and
the verdict are all computed on the **net** `baseline` daily return series. The
`cost_free` arm exists solely to attribute how much of the result the costs ate.

**Break-even cost is reported** (the paper reports none): the one-way bps at
which the best non-control spec's net annualized Sharpe reaches zero.

**Borrow.** The short leg is a short of SPY held for 30 minutes intraday. No
overnight borrow is charged, because no position is held overnight; this is
stated rather than silently omitted.

---

## 5. Power block — the claimed Sharpe, and the fact that this test is on the
boundary

**Claimed annualized Sharpe = 1.08.** Source: the draft's own Table 5 Panel A,
row r₁, `SRatio` column — the Sharpe of the *exact* rule spec #1 implements.

**It is a zero-cost / gross upper bound**, for three stated reasons: (a) Table 5
carries no transaction costs (the cost discussion is a separate section, §1d);
(b) it is an in-sample-period figure for 1993–2013; (c) it is the best of the
three signals the paper reports.

**Relation to the scoping memo's 2.09.** The memo (§3d) derived an annualized
Sharpe of 2.088 from R²_OS = 0.017 via SR_per_period = R/√(1−R²). That
derivation is for a strategy that **scales its position with a linear forecast**
— it is the maximal Sharpe of an optimally-sized bet, not of a ±1 sign bet. The
sign rule throws away magnitude information, so it must and does score lower.
The paper's own 1.08 for the sign rule is therefore the correct claimed effect
for **this** grid, and 1.08 is what the scorecard's power block uses. 2.09 is
reported alongside as the memo's optimally-scaled upper bound, never as the
power input for this grid.

**Pre-run power, computed today with the real modules** (`dsr_power_report`,
threshold 0.95, n_observations ≈ 2690 ≈ 10.7 yr × 252, n_trials = 8):

| σ_SR | claimed | required observed Sharpe | power | min detectable Sharpe | years to detect |
|---|---|---|---|---|---|
| 0.2 | **1.08** | 0.80 | **0.82** (adequate) | 1.05 | 10 |
| 0.2 | 2.088 | 0.80 | 1.00 | 1.05 | 2 |
| 0.5 | **1.08** | 1.23 | **0.31 (UNDERPOWERED)** | 1.49 | 50 |
| 0.5 | 2.088 | 1.23 | 1.00 | 1.49 | 3 |

**Read this before the result exists:** at the paper's own claimed Sharpe this
test clears the 0.80 power floor *only* if the realized σ_SR across the 8 specs
comes in near 0.2, and fails it badly at σ_SR ≈ 0.5. The scorecard's power block
will use the **realized** σ_SR from the run. **A failing DSR at n_local with
power < 0.80 is reported as `underpowered`, NOT as `definite_negative`** —
`registration_scorecard.policy_d_verdict` enforces this automatically from the
power block. This is not a lowered bar: nothing that fails passes, and an
`underpowered` family earns no forward-validation slot.

---

## 6. Verdict rule — declared before any result

Computed on the **`baseline`** arm's net daily return series, for the best
**non-control** spec (highest net annualized Sharpe among specs 1–6).

1. **DSR at every rung of {8, 37, 362, 1031}**, reported at BOTH the 0.95
   validated bar and the 0.50 screening bar.
2. Tiering (CLAUDE.md §4, via `registration_scorecard.policy_d_verdict`):
   * fails at n_local = 8 **and** power ≥ 0.80 → **DEFINITE_NEGATIVE**;
   * fails at n_local = 8 **and** power < 0.80 → **UNDERPOWERED**;
   * passes at 8 but fails at a more conservative rung → **UNRESOLVED**;
   * passes at all four rungs → **real pass**.
3. **`preservation_score` is computed for every spec, no exceptions**
   (`preservation_score.py`, `periods_per_year = 252`, `dsr` input = the DSR at
   n_local).
4. **Placebo override, declared now.** If the best placebo spec's net
   annualized Sharpe is **≥** the best non-control spec's, the family is
   declared a negative **on attribution grounds regardless of DSR** — a signal
   that a mechanism-free intraday half-hour reproduces cannot be evidence for
   the paper's overnight-information mechanism. The placebo's DSR is reported
   but never used to pass anything.
5. **Nothing is registered for forward validation and no live registration is
   touched** (CLAUDE.md rule 6). The output of this family is a recommendation
   and a scorecard, full stop.

## 7. Regime conditioning — scope, declared

The paper's **headline** claim ("the first half-hour return predicts the last
half-hour return") is **unconditional**, so under CLAUDE.md §4's conditional
rule no regime-conditional DSR split is required and none is pre-declared. The
paper does make *secondary* conditional claims (stronger on high-volatility
days, high-volume days, recession days, macro-announcement days; Tables 2, 4, 6,
9, 10). Testing those would multiply the grid several-fold and is deliberately
**out of scope for this family**, recorded here as a declared scope limit rather
than a skipped requirement. The `deadband10bp` rule is the single, minimal nod
to that literature and is logged as a deviation in §3.

## 8. What would make this a false positive, and what protects against it

* *Look-ahead through the previous close.* r₁ uses the PREVIOUS session's 15:59
  close, known 17.5 hours before the trade. The position is formed at 15:30 from
  r₁ (known at 10:00) and r₁₂ (known at 15:30) and earns r₁₃ (15:30→16:00). No
  quantity entering the weight is measurable after 15:30. Enforced by a unit
  test on synthetic bars.
* *Cost assumption doing the work.* Three arms, verdict arm fixed by a
  data-driven procedure before results, break-even reported.
* *Grid mining.* 8 specs, all declared here, controls counted in N, no
  post-hoc exclusions.
* *Mechanism-free reproduction.* The r₂ placebo, with an override rule that
  can veto a DSR pass.
* *Survivorship.* Not applicable — one instrument, continuously listed.
* *Replay correctness.* Validated on synthetic bars with a known constructed
  answer before it is ever pointed at real data.
