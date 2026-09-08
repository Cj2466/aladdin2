# Frazzini & Lamont (2008) "Dumb Money" — RESULTS

Candidate #15 in the flow-mechanism queue. Fourteen closed before it, zero
false positives.

Pre-registration: `frazzini_lamont_dumb_money_PREREGISTRATION.txt`, committed
`b30090a` **before** any strategy return existed (independently re-checked by
the verifier's V7: pre-registration commit 1788856400, first family code
1788856843).

---

## 1. Verdict, stated in two layers

**DEFINITE_NEGATIVE by the letter of the pre-registered rule — and, unlike
candidate #14, the honest reading agrees.** This is a well-powered,
construction-validated negative, not a test that could not run.

Best spec `sp500/dm_3year_long_low_flow_baseline`: Sharpe 0.482, mean
+1.287%/mo, **DSR 0.2274 / 0.1753 / 0.0391 / 0.0186** at N = 24/37/362/1031
against a 0.95 bar, `preservation_score` 0.0. It fails at the most lenient
rung, so no more conservative denominator can rescue it.

**Not a cost artifact.** The zero-cost arm gives DSR 0.2259 at N=24 — a
difference of 0.0015. Charging nothing at all leaves the candidate short of the
bar by a factor of four.

**Not a power failure.** Every leg was formable in **100% of months** in every
one of the 24 specs, with 44–77 monthly returns per arm and median quintile
sizes of 94–104 names. The pre-registered C2 floor (36 months) is cleared
everywhere. This is the specific thing that went wrong with Coval-Stafford,
where the long leg was formable in 0 of 65 months; it did not go wrong here.

**And the sign is backwards.** See §3.

---

## 2. The construction is validated even though the trade is not

This is the part worth more than the verdict, and it is the reason the negative
can be read as being about the mechanism rather than about the pipeline.

**C5(a) — monotonicity and widening: PASSES, and closely.** The pre-registered
test was that mean FLOW must rise monotonically across quintiles at every
horizon *and* that the Q5−Q1 spread must widen with horizon, the latter being
the signature of the paper's own Fig. 1 finding that flows cumulate over two to
three years. Monotonicity holds in **8 of 8** universe × horizon cells. The
widening:

| horizon | paper (Table 2A) | S&P 500 | S&P 600 |
|---|---|---|---|
| 3-month | 1.459 | 1.246 | 2.010 |
| 6-month | 2.646 | 1.929 | 3.416 |
| 1-year  | 4.624 | 3.063 | 5.016 |
| 3-year  | 10.135 | 5.796 | **10.500** |

The S&P 600 three-year spread lands within 4% of the paper's own published
value. The measure is doing what the paper says it does.

**C5(b) — scale: reported, with a real structural difference.** Pooled FLOW
dispersion rises with horizon exactly as it should (sd 1.53 → 2.41 → 3.45 →
4.76, against the paper's 5.61 at its three-year baseline). But the pooled
**mean is negative** here (−0.24 to −0.71) where the paper's is +0.54. That is
not a bug and it is not noise: FLOW is a relative measure, so an equal-weighted
average across stocks is negative precisely when fund inflows are concentrated
in a *few* very large funds rather than spread across the sector — the typical
stock's holders then received less than pro rata. That is a fair description of
2019–2026, and a poor description of the 1983–2003 sector-wide expansion the
paper sampled. Stated as an observation about the period, not as validation.

**C6 — the paper's own worked examples reproduce exactly.** Both of them, and
neither was derived from this code:

* **Appendix Table A1** (p.321): all **21 published counterfactual cells**,
  checked from both sides — the TNA path, and the counterfactual flows
  recovered by inverting Eq. (12). Includes the newborn rule (Fund 3), the
  death rule (Fund 2's outflow is its *counterfactual* 141, not its actual
  144), and the fact that Eq. (11)'s denominator and F^Agg have different
  membership.
* **The Cisco example** (pp.301–302): counterfactual TNAs of exactly $31bn and
  $89bn, and a FLOW of 5.625% against the paper's printed 5.6%.

Plus a null the paper does not print but Eq. (8) forces: when every fund's flow
is exactly pro rata, FLOW is identically zero.

---

## 3. C4 — the direction check FAILS, and that is the substantive finding

The paper's claim is directional: high FLOW predicts **low** future returns
(Table 2B, Q5−Q1 = −0.846%/mo, t = −3.30 at the three-year baseline). The
tradeable portfolio is therefore long Q1 and short Q5, and the pre-registration
fixed in advance that a positive Q5−Q1 "is a NEGATIVE for this mechanism, not a
signal to be traded with the sign flipped."

Mean monthly return of the Q1−Q5 leg (positive = the paper's direction):

| horizon | S&P 500 | S&P 600 |
|---|---|---|
| 3-month | −0.202 | **+0.056** |
| 6-month | −0.324 | −0.052 |
| 1-year  | −0.826 | −0.505 |
| 3-year  | −0.410 | −0.064 |

**Seven of eight are the wrong sign.** The single right-signed cell is the
3-month S&P 600 arm — which is the horizon the paper itself reports as null
(+0.033%/mo, t = 0.13), and which the pre-registration therefore declared
null-expected in advance. At the paper's own three-year baseline the S&P 500
spread is +0.410%/mo in the *opposite* direction to the published −0.846%/mo.

Over 2020–2026 in these universes, stocks owned by inflow-receiving funds
**outperformed**. The dumb money looks smart, or more precisely: whatever FLOW
is measuring has not been a sentiment-overpricing signal in this sample.

**C1 — the paper's own factor control (Table 3): also fails to reproduce.**
Frazzini-Lamont find the effect survives Fama-French adjustment at −0.74%/mo
with a large *negative* HML loading on Q5−Q1, i.e. a *positive* HML loading on
the Q1−Q5 portfolio traded here. Measured: alphas of −0.559 to +0.070 %/mo,
**none significant** (|t| ≤ 1.16), and HML loadings between −0.32 and +0.16,
**none significant** (|t| ≤ 1.32) and mixed in sign. So there is no alpha to
subsume, and the growth/value tilt the paper identifies as the economic content
of the effect is absent. Honest caveat: the factor file ends 2026-06, so the
overlap is 46–52 months at the short horizons and only **29 months** at the
three-year horizon — thin enough that the three-year row should not be leaned
on by itself.

**Robustness — the Appendix Table A1 counterfactual reading** (declared in
advance, outside the DSR grid): best DSR@24 = 0.2717 versus 0.2274 for the
primary main-text reading. Verdict unchanged.

---

## 4. Three corrections to the commissioning brief, from the published paper

The published JFE article itself was obtained (author's own NYU Stern page,
sha256 `3c39e8ff…`) — the **first candidate in this queue that did not need a
working-paper substitute**, so no "may be renumbered" caveat applies anywhere.

1. **The measure, fundamentally.** The brief described "a value-weighted
   average, across the funds holding a stock, of each fund's own recent flow."
   Eq. (8) is nothing of the kind: it is a **counterfactual ownership
   decomposition** — actual mutual-fund ownership minus the ownership that
   would have obtained under proportional inflows — denominated in percent of
   market cap. This is what makes it genuinely distinct from Lou (2012) Eq. (3)
   (share-weighted flow average, units: fraction of shares) and Coval-Stafford
   Eq. (4) (unweighted net owner count, units: fraction of owners), rather than
   a third pass at one idea.
2. **The mechanism.** The brief attributed price pressure from uninformed
   forced buying. The paper explicitly declines that reading (p.302: it does
   not attempt to analyse the propagation mechanism, and it names
   Coval-Stafford as the hypothesis it is *not* testing). Registered and
   reported as a **sentiment / demand-revelation** test.
3. **"Smart money".** The paper finds *no* solid smart-money effect, so the
   3-month arm was pre-declared null-expected rather than treated as a
   prediction.

Also resolved in advance: the main text's rolling-window counterfactual and
Appendix Table A1's arithmetic **are not the same recursion**. All 21 published
cells reproduce only under a recursion that re-anchors the pro-rata share each
period; the main-text reading (Eq. 11's own subscripts) was fixed as primary
and Table A1's as a declared robustness arm. Three anomalies in that table — a
missing 1984 column, an aggregate printed 494 where its own rows sum to 495,
and prose reading "1993" for 1983 — are present **identically in the 2005 NBER
draft**, so they predate JFE review. The 494/495 one is pinned by a test:
only 495 reproduces the published final cell.

---

## 5. Defects found and fixed mid-build

**One real family bug, found by the independent checker.** The amendment
tie-break — which of several filings for one (series, quarter) to use — ran at
build time and picked the latest-filed over the *whole history*. The
snapshot-time FILING_DATE gate then discarded that pick as not-yet-public and
took **the entire fund-quarter with it**, even though an earlier filing was
public and observable at the time. Future information was deciding which past
observations existed, and its effect was to delete real ones. Measured on the
real cache: **5,175 of 315,930** (series, quarter) keys carry more than one
filing, median filing-date spread 90 days, maximum 1,628; 312 of them report a
different NET_ASSETS on the later filing. Fixed by deferring the tie-break to
the point-in-time selection and keying holdings by accession. Three regression
tests pin it. **Effect on the verdict: none** — best DSR moved 0.1756 → 0.2274,
still four times short of the bar.

**An infrastructure trap avoided.** `data/nport_bulk` is filtered to S&P 500
CUSIPs and would have returned a silently empty small-cap arm; the S&P 500 +
S&P 600 union cache was used instead. Separately, that 423MB union cache was
found living inside the merged `coval-stafford` *worktree*, where routine
worktree cleanup would have deleted it — relocated to main's `data/`, the
canonical home every other shared cache already uses, and symlinked. The coval
worktree was left exactly as clean as it was found.

**A new fetch was genuinely required.** The paper restricts to *domestic equity
funds* (p.302), and that restriction is load-bearing in a way that is easy to
miss: a bond fund contributes a zero term to Eq. (8)'s per-stock sum and is
therefore invisible in the inputs, but it still enters TNA^Agg and F^Agg and so
shifts **every** equity fund's counterfactual. N-PORT publishes no fund-type
field (verified by enumerating all 32 members of a bulk ZIP), and both existing
caches were CUSIP-filtered, so an equity share computed from them would have
silently meant "fraction of net assets in this index". A new unfiltered
streaming pass over all 27 quarters produced per-fund asset-category totals.
The resulting split is cleanly bimodal (median equity share 0.95), so the 80%
threshold is not knife-edge.

---

## 6. Verification — and an honest caveat about it

`verify_dumb_money.py` imports nothing from the family. **8 of 9 checks pass.**

| | check | outcome |
|---|---|---|
| V1 | Table A1's 21 cells, from a retyped recursion | PASS |
| V2 | Cisco worked example → 5.625% vs printed 5.6% | PASS |
| V3a | real FLOW cells re-derived from raw N-PORT CSVs | **FAIL**, residual 3.7e-05 |
| V3b | that residual moves no stock across a quintile breakpoint | PASS |
| V4a | DSR at every rung, Bailey–López de Prado retyped | PASS, max diff 3.4e-16 |
| V4b | verdict rule re-applied | PASS |
| V5 | 9 reused shared modules byte-identical to main | PASS |
| V6 | 24 persisted DB rows match the report | PASS |
| V7 | pre-registration precedes all family code | PASS |

**V3a is left red deliberately.** Chasing the disagreement from 3.3e-03 down to
3.7e-05 found four real bugs — **one in the family** (§5) and **three in the
checker** (a wrong column name; reading a missing Item B.6 month as 0.0 rather
than refusing the filing; pooling share-class returns across filings instead of
within one filing). What remains is a tie-break *ordering* difference:
`fund_monthly_returns` walks filings quarter-file by quarter-file while the
checker walks them sorted by (series, report_date, filing_date), so a fund-month
covered by filings in two different quarterly ZIPs can resolve differently.
Loosening V3a's tolerance to turn it green would be exactly the quietly-weakened
test this project forbids, so it stays red and V3b measures whether the residual
*can* matter: across all **1,291 overlapping tickers**, max |diff| 2.16e-04,
median 3.27e-05, and **zero quintile assignments differ**. FLOW enters the
strategy only as a cross-sectional sort key, so a residual that reorders nothing
cannot reach the verdict.

**Stated plainly, as candidate #14's report did:** a checker that needed three
corrections before it nearly agreed is weaker evidence than one that agreed
immediately. What partly offsets that here is that the two *published* worked
examples (V1, V2) agreed on the very first run, and they test the formula
itself rather than the data plumbing.

**Test suite:** see §9.

---

## 7. Limitations, stated rather than glossed

* **History.** 27 published N-PORT quarters (2019 Q4 – 2026 Q2) against the
  paper's 24 years, and the measure *consumes* k quarters before its first
  observation — which is why the three-year arm has 44–45 months and the
  five-year row of Table 2 was excluded as infeasible **in advance**.
* **Universe.** S&P 500 / S&P 600 constituents, versus a CRSP-wide sample
  covering 69% of names. F-L's effect lives partly in smaller and growthier
  names than the S&P 600 floor.
* **Survivorship.** 295 of 1,695 union tickers (17.4%) resolved no price data —
  the standing delisted-securities gap (P2). Direction of the resulting bias is
  **not** assumed to be conservative.
* **Ticker identity.** 37 of 1,828 CUSIPs resolve to a different ticker at a
  sample endpoint than at the midpoint; the midpoint answer is used, which is a
  mild use of full-sample information (same convention as candidate #14).
* **A residual look-ahead, disclosed.** The equity-fund classification keeps a
  series if it clears the 80% bar in *any* quarter, including quarters after
  the snapshot. This was a declared choice in the pre-registration (fund
  mandates are stable), but it is still future information. It was **not**
  measured — stating that as a limitation, not claiming it is negligible. The
  reasoning, offered as reasoning rather than measurement: it can only change
  which funds enter sector aggregates, the equity-share distribution is
  strongly bimodal, and the verdict misses its bar by 4x at zero cost.
* **Mergers.** N-PORT folds merger-driven share issuance into "shares sold"
  with no separating field, so neither of the paper's two merger adjustments
  (Eq. 1's MGN term, Appendix A.1's lagged-TNA merge) can be reconstructed.
  Irreducible; it adds noise, biasing toward *less* measured signal.
* **Fiscal-quarter misalignment.** N-PORT publishes the third month of each
  fund's own fiscal quarter, so the flow windows aggregated into F^Agg are
  staggered by up to two months. No analogue in the paper; no correction
  available.
* **"Domestic" is not testable.** ASSET_CAT does not encode issuer country, so
  this selects equity funds, not *domestic* equity funds.
* **Independence.** Although Eq. (8) is a genuinely different functional form
  from Lou's Eq. (3) and Coval-Stafford's Eq. (4), all three are computed from
  the **same N-PORT flows and holdings over the same ~7 years**. Three
  negatives from this data are **not** three independent pieces of evidence
  about flow-driven mispricing.

---

## 8. Recommendation

**Do not register. Nothing was registered and no live or forward-validation
status was touched** (CLAUDE.md rule 6). This is a research recommendation
only.

The candidate fails its own pre-registered bar at every rung, at zero cost, and
in the wrong direction, on a test that had adequate power and a construction
validated against the paper's own published statistics. Of the fifteen
candidates in this queue this is one of the cleaner negatives: the machinery
demonstrably works and the effect is simply not there in this sample, in this
universe, in this period.

The transferable observation, for whatever picks up this thread: the paper's
*measurement* claim replicates well (Table 2 Panel A's quintile structure and
its widening with horizon come back almost exactly), while its *return* claim
inverts. That pattern — construction reproduces, trade does not — now matches
`ipo_lockup` (unlock volume reproduced at 1.6–3.3× the published magnitude, CAR
gone) and `quarter_end_marking` (fund-return signature partly reproduced, markup
leg gone). Three separate published effects where the observable phenomenon
survives and the exploitable mispricing does not.

---

## 9. Reproduction

```
cd backend
./venv/bin/python data/research_runs/fetch_nport_fund_asset_categories.py   # ~17 min, ~7GB
./venv/bin/python data/research_runs/run_dumb_money.py                      # ~9 min
./venv/bin/python data/research_runs/verify_dumb_money.py                   # independent
./venv/bin/python -m pytest tests/test_cross_sectional_dumb_money.py        # 17 tests
```

Persisted: **24 rows** under `run_tag='dumb_money_2026-09-08'`
(`dumb_money` 12, `small_cap_dumb_money` 12) in main's shared `aladdin2.db`.
Derived panels are committed under `dumb_money_panels/` so every number is
re-derivable without the 423MB N-PORT cache. Report:
`dumb_money_2026-09-08.json`.

Full backend suite: **4,399 passed, 3 skipped, 1 failed** in 11m38s — the
single failure is the documented pre-existing
`tests/test_registration_scorecards.py::test_every_family_has_a_scorecard`,
expected until scorecards are written. Note there is **no second failure**:
`test_family_inventory_is_not_stale_against_the_live_database`, which
candidate #14 tripped by persisting rows for new family keys, passes here
because `FAMILY_INVENTORY.json` was refreshed for `dumb_money` and
`small_cap_dumb_money` first. Main's copy was verified byte-identical before
and after (`1ad4f47b…`) and main's git status unchanged, per the binding guard
added after the earlier incident where that script silently rewrote main's
inventory from inside a worktree.
