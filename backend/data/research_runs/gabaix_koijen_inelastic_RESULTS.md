# Gabaix & Koijen, "The Inelastic Markets Hypothesis" — candidate #16

**Verdict: DEFINITE_NEGATIVE for tradability.** All 24 pre-registered specs fail
at every rung of the DSR ladder, on the baseline cost arm, reading off the
overlay stream. Nothing is registered, promoted, or given any live or
forward-validation status.

**But the headline number is not the interesting part of this one.** The
substantive finding is *why* it fails, and that result is unusually clean —
see §3.

- Pre-registration: `gabaix_koijen_inelastic_PREREGISTRATION.txt`, commit
  `a1b1df9`, written and committed before any strategy return existed.
- Family module: `app/services/research_lab/inelastic_markets_timing.py`
- Runs: `run_inelastic_markets.py`, `run_inelastic_markets_exploratory.py`
- Independent verification: `verify_inelastic_markets.py` (14/14 checks pass)
- Persisted: 24 baseline rows, `family_key='inelastic_markets'`,
  `run_tag='production_2026-09-08'`

---

## 1. What the paper actually claims, and what this family therefore tested

The dispatch brief framed this as a market-timing overlay: "tilt aggregate
equity exposure based on a measured aggregate-flow signal." **That does not
follow from the paper, and the authors say so themselves.** This was written
into the pre-registration *before* any result existed, because it determines
what a null means.

[GK21] is a theory of price **formation** — a causal attribution of aggregate
volatility to flows — not a theory of return **predictability**:

- Its headline regression, eq. (32), is same-quarter: `dp_t = M·Z_t + e_t`.
  Nothing is forecast.
- Its horizon regression, eq. (38), has left-hand side `p_{t+h} − p_{t−1}`, a
  window that already contains the contemporaneous quarter. On the result,
  [GK21] §4.2 verbatim: *"We find that the cumulative impact is fairly stable
  over time. This is intuitive as sharp reversals would imply a strong negative
  autocorrelation in returns, which is not something that we observe."* A flat
  `M_h` **is** the statement that `E[p_{t+h} − p_t | Z_t] ≈ 0` for `h ≥ 1`.
- [GK22] states the trading implication outright, verbatim: *"a one-time, non
  mean-reverting inflow permanently changes prices … even if it contains no
  information whatsoever. … The typical empirical strategy to look for reversals
  as signs of flows (rather than information) moving prices does not work in
  this case. By the same logic, we can see large changes in prices but small
  changes in long-horizon expected returns."*

So the registered hypothesis was an **adjacent** claim that the paper predicts
to be false. A null therefore **confirms** [GK21]; it is not evidence against
the inelastic markets hypothesis, which this project has no way to falsify and
did not try to.

### Corrections to the brief (all with citations)

| Brief said | Actually |
|---|---|
| headline multiplier "roughly $3–8" | Headline is **~$5** (abstract verbatim: "about $5"); Table 2 points are **7.08** (1 PC, s.e. 1.86) and **5.28** (2 PC, s.e. 1.10). "3.5 to 8" is the §4.2 *robustness range*, a different object. |
| IV strategy may need proprietary data | Split: §4.2 (the headline table) uses **only free Flow of Funds** data — feasible. §4.3 uses FactSet 13F + Morningstar — both paid, **not attempted**. |
| test may be underpowered | Checked numerically *before* building, precisely so "underpowered" could not excuse a null. It is adequately powered (§5). |
| reuse the project's N-PORT infrastructure | **Deliberately not used** — see §6. |

No published journal version was located. Gabaix's own publications page
returned HTTP 403 and could not be read, so "none exists" is **not** claimed.

---

## 2. The gates

**G1 — sector partition integrity: PASS.** The pinned 16-series Z.1 holder
partition reconstructs Z.1's own "All sectors; corporate equities" total to a
median absolute error of **0.108%** (max 1.76%) across 116 quarters, against a
2% threshold. The universe is right.

**G2 — mechanism fidelity: FAIL.** Reproducing [GK21] Table 2 on the paper's own
1993Q1–2018Q4 sample, using Appendix B.2's actual algorithm:

| | this project | [GK21] Table 2 |
|---|---|---|
| M (1 PC) | **2.526** (s.e. 0.387) | 7.08 |
| M (2 PC) | **2.754** (s.e. 0.401) | 5.28 |
| n | 104 | 104 |
| R² | 0.552 / 0.568 | 0.436 / 0.515 |
| GDP-growth coef | 4.07 / 3.97 | 5.99 / 5.97 |

The sample size matches Table 2 *exactly* (104), and R² and the GDP coefficient
are in the same ballpark — so the regression is structurally right. But the
multiplier is roughly **half** the paper's and sits outside its own disclosed
[3.5, 8.0] robustness range. **This project cannot reproduce the paper's
headline magnitude with free data**, and accordingly makes no claim about the
inelastic markets hypothesis in either direction.

A post-hoc sensitivity (run *after* seeing G2 fail, and labelled as such)
checked whether the ETF exclusion forced by the 1993Q1 start explained the gap.
It does not — including ETFs makes it slightly *worse* (2.28 / 2.65).

Four documented reasons the replication could differ, none of them chased to
resolution: the CRSP value-weighted index is paid, so ^GSPC (a large-cap subset)
stands in for the left-hand side; [GK21] §2.1's foreign/US holdings adjustment
(Appendix C.1.3) was **not** performed; the vintage is June 2026 vs their June
2019 and Z.1 is revised substantially; and three holder sectors are excluded on
data-availability grounds (§6).

**G3 — no look-ahead: PASS,** and tested *behaviourally* rather than by
inspection. Corrupting all Z.1 data after 2013Q1 by a factor of −3 changes every
prior recursive `Z_t` by **exactly 0.0**. The pseudo-equal weights, the eq. (67)
panel regression and the PCA are all refit on data through each decision date.

---

## 3. The substantive finding

Regressing market excess returns on the GIV flow shock, by horizon:

| horizon | coefficient | t-stat | correlation |
|---|---|---|---|
| **h = 0 (contemporaneous)** | **3.29** | **12.39** | **0.756** |
| h = 1 (next quarter) | 0.26 | 0.64 | 0.060 |
| h = 2 | 0.35 | 0.87 | 0.081 |
| h = 3 | −0.23 | −0.57 | −0.054 |
| h = 4 | −0.54 | −1.32 | −0.124 |

This is the result worth keeping. The signal explains **~57% of the variance of
contemporaneous quarterly market returns** (t = 12.4) — the mechanism is real,
strongly present in free Z.1 data, and correctly constructed — and then carries
**no forecasting content whatsoever** at any future horizon.

That distinction matters for how the null should be read. A trading null from a
broken signal tells you nothing. A trading null from a signal with a t = 12.4
contemporaneous relationship tells you the flow-price link is genuinely there
and genuinely unharvestable. **The price impact is permanent, exactly as [GK21]
says.** This family is a negative for tradability and a *confirmation* of the
paper.

### A trap this family walked into, and the pre-registration caught

The strategy-stream Sharpes look **excellent** — up to **0.91** against a
buy-and-hold **0.53**. A naive reading is a strong market-timing edge.

It is an artifact. The overlay stream — the incremental bet,
`(w_t − 1)·(R−RF) − costs` — is **negative for all 24 specs** (−0.076 to
−0.457). The timer is out of the market part of the time, which cuts volatility
faster than it cuts return, so the *ratio* improves while the active bet
steadily loses money. The pre-registration fixed the verdict to the overlay
stream in advance for exactly this reason, and the trap then materialized.

---

## 4. Registered results

24 specs × 3 cost arms; verdict on the baseline arm (2.0bp one-way), overlay
stream, `periods_per_year = 4`. DSR ladder `{24, 37, 362, 1031}`, bar 0.95.

- **All 24 specs: DEFINITE_NEGATIVE.**
- Best overlay Sharpe: **−0.0759** (`pcs1_rolling40_binary_1q`).
- Its DSR: **0.064** at the most lenient N=24, **0.011** at N=1031.
- Every overlay Sharpe is negative, so the family fails at the *most lenient*
  rung — the strongest tier of negative available.
- `preservation_score` computed for every spec, no exceptions.

**The `n_pcs` grid dimension is degenerate, and this is correct, not a bug.**
Under eq. (68), `Z_t` is built from the eq. (67) residuals and the principal
components never touch it, so `pcs1` and `pcs2` are byte-identical. The grid
therefore has **12 truly-unique specs**, not 24. `n_local = 24` was left as
pre-registered, which *overstates* the search and makes the bar harder — the
conservative direction.

### Exploratory arms (not registered, run after the verdict was known)

- **Reversal sign.** The pre-registered direction was positive/continuation. The
  reversal direction is **worse, not better** — best overlay Sharpe −0.592,
  median −0.840. Even treating the sign as searched (N doubled to 48), it is
  DEFINITE_NEGATIVE at every rung. *The null does not depend on the
  pre-registered direction.*
- **Footnote 70's alternative instrument** (residualising on the PCs, which
  makes `n_pcs` bite): still all negative, best −0.179. The null is not an
  artifact of the eq. (68) construction choice.

---

## 5. Power — and why the verdict does not rest on it

Computed *before* building, using this project's own DSR code. Minimum
annualized net Sharpe needed to reach DSR ≥ 0.95:

| | N=24 | N=37 | N=362 | N=1031 |
|---|---|---|---|---|
| pre-registered estimate (T≈104) | 0.725 | 0.761 | 0.923 | 0.986 |
| realized, 16 specs (T=92) | 0.773 | 0.811 | 0.984 | **1.052** |
| realized, 8 tertile specs (T=73) | 0.872 | 0.916 | 1.113 | **1.190** |

**Disclosed shortfall:** the realized overlay sample is **73–92 quarters**, not
the ~115–118 the pre-registration projected. Sixteen specs run 92 quarters
(2003Q2–2026Q1); the eight `tertile` specs run 73 (2008Q1–2026Q1), because the
expanding trailing-rank bucket needs extra warm-up on top of the 40-quarter
standardization window and the 2-quarter availability lag. The bar is
correspondingly higher than registered.

This does **not** affect the conclusion: every observed overlay Sharpe is
*negative*, and a negative Sharpe fails at any power level. Power would only
matter if a small positive edge were being dismissed.

What the null does **not** establish: that no edge below ~1.0 annualized Sharpe
exists. It establishes that none clears *this project's* evidentiary bar.

---

## 6. Honest limitations

- **Revision look-ahead, unresolved.** A single June-2026 Z.1 vintage is used
  for all history; Z.1 is revised substantially. A true point-in-time test needs
  per-date vintages, which were not assembled. The bias runs **in the
  strategy's favour**, so a negative is safe — the pre-registration fixed this
  asymmetry in advance, requiring that any *positive* be reported as confounded
  rather than as a pass.
- **Three sectors excluded** from the GIV panel because Z.1 reports them as
  exactly zero for long stretches, making `dq` undefined on a zero base: hedge
  funds (0 in 250 of 303 quarters; note [GK21] §2.2 says the FoF household
  sector *includes* hedge funds, so they are not lost), federal government
  (positive only from 2008Q3), and broker-dealers (a *net* series that goes
  negative; [GK21] §2.2 notes dealers "hold only a small fraction"). The
  admitted 12 sectors still cover a **median 95.8%** of the market. The
  admission rule is mechanical and cannot be steered by the answer.
- **N-PORT deliberately not reused,** though the brief suggested it. GIV's
  instrument is a size-weighted-minus-precision-weighted contrast defined only
  over the *full* cross-section of holders; computing it on the two sectors
  N-PORT covers (mutual funds, ETFs) would not approximate it but compute a
  different, meaningless quantity. N-PORT also begins in 2019, cutting ~118
  quarters to ~26. Z.1 is both more faithful (it is the paper's own source) and
  better powered.
- **Estimator scale factor, measured and disclosed.** On synthetic data the
  pipeline recovers a multiplier ~1.25× the true one, *constant* across true
  values. A closed-form oracle instrument built from the true shocks gives the
  **same** 1.25×, so this is a property of the estimator under that synthetic
  size distribution, **not an implementation error**. [GK21] Appendix D.1
  calibrates its simulated size distribution to the real one and reports
  accuracy; that calibration was not reproduced. Direction note: if anything
  this means the true M behind the measured 2.53 is *lower*, making G2's failure
  wider rather than narrower.
- Paid-data gaps found and logged, not acted on: **CRSP value-weighted index**
  (for the exact Table 2 left-hand side), **FactSet 13F + Morningstar** (for
  §4.3's investor-level estimate).

---

## 7. A real construction error, caught and corrected

The first implementation was built from the main text's eqs. (27)/(31)/(34)/(35)
and was **materially wrong**. Those equations are an *exposition*; the recipe
that produces Table 2 is **Appendix B.2**, which differs in four ways that all
matter:

1. the "equal-weight" leg is **inverse-variance** ("pseudo-equal") weights,
   winsorised at 1.5/N — not equal weights;
2. **the corporate sector is excluded** from the instrument (B.2 step 1
   verbatim), being the supply side;
3. `dq̌` is the residual of a **weighted panel regression** (eq. 67) with sector
   FE, *time* FE, sector-specific GDP loadings and sector-specific trends — not
   a simple cross-sectional demeaning;
4. the principal components are **controls** in eq. (69) and never touch `Z`.

The tell was that `n_pcs=1` and `n_pcs=2` produced near-identical multipliers
(1.796 vs 1.846), which is impossible if the PCs genuinely enter `Z`. Chasing
that produced M = 2.53/2.75 instead of 1.80/1.85. This is CLAUDE.md's "never
implement a published formula from memory — cite the equation and validate
against synthetic data with a known answer" rule doing exactly its job, and it
was caught *before* any strategy return existed.

---

## 8. Recommendation

**Close as an honest negative for tradability. Do not register. Do not pursue a
point-in-time Z.1 rebuild** — it would only matter if there were a positive to
defend, and there is not: the mechanism is permanent by the authors' own account
and measures as permanent (t = 12.4 contemporaneous, |t| ≤ 1.32 at every future
horizon) in this project's own data.

The one genuinely reusable asset from this candidate is the **free Z.1
sector-flow infrastructure** (`z1_corporate_equities_holdings.csv.gz`, the
extractor, and a validated Appendix B.2 GIV implementation). If a future
candidate needs aggregate institutional flow data, it exists now, is verified,
and its partition is checked against the Fed's own totals to 0.1%.
