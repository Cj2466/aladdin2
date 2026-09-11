# Rule-free pattern scan vs. placebo — SCAN REPORT

**Verdict: on both panels, GATE 1 and GATE 2 both FAIL. The patterns this scanner finds are not
distinguishable from the patterns it finds in data whose time-ordered information has been
destroyed.** Under PREREGISTRATION §1 that is the "No" branch: *the patterns are scanner artifacts
on this data at this resolution* — a statement about this alphabet, these two panels and these
horizons, and about nothing else (§9).

Run 2026-09-11. Contract: `PREREGISTRATION.md` (written and merged before any scan) as amended by
`ADDENDUM_01_PLACEBO_TARGET_AND_UNDERSPECIFIED_POINTS.md` and
`ADDENDUM_02_PANEL_E_UNIVERSE_AND_CALENDAR.md`, both committed before the numbers they govern.
Builder: Claude Fable 5.1. This is **not** a family, carries no scorecard, registers nothing, and
changes no live status.

---

## 1. Gate table

### GATE 1 — existence (discovery window, real vs. the 20 P1 sign-flip draws)
PASS requires **N3_real > max N3_P1 AND Tmax_real > max Tmax_P1** (§6).

| panel | h | measurable | N3 real | N3 P1 max | N4 real | N4 P1 max | Tmax real | Tmax P1 max | verdict |
|---|---|---|---|---|---|---|---|---|---|
| E | 1 (primary) | 117 | 0 | 2 | 0 | 0 | 2.8843 | 3.5799 | **FAIL** (both legs) |
| E | 5 (secondary) | 117 | 3 | 2 | 0 | 0 | 3.2729 | 3.4264 | **FAIL** (Tmax leg) |
| C | 1 (primary) | 9 | 0 | 1 | 0 | 0 | 2.8173 | 3.0294 | **FAIL** (both legs) |
| C | 5 (secondary) | 9 | 0 | 1 | 0 | 0 | 1.6353 | 3.3156 | **FAIL** (both legs) |

The one leg the real arm wins anywhere is N3 at h = 5 on Panel E (3 real vs. 2 placebo). §6 requires
both legs, and the Tmax leg loses there.

### GATE 2 — survival (holdout window, the real top-20 oriented by discovery sign)
PASS requires **t(H_real) ≥ 2.0 AND t(H_real) > max_d t(H_P1,d)** (§6).

| panel | h | holdout bars | t(H_real) | Sharpe | P1 max | verdict |
|---|---|---|---|---|---|---|
| E | 1 (primary) | 922 | 0.7116 | 0.3686 | 2.0969 | **FAIL** (both legs) |
| E | 5 (secondary) | 918 | 2.0693 | 1.4006 | 2.2654 | **FAIL** (envelope leg) |
| C | 1 (primary) | 15,218 | −1.6828 | −1.2733 | 1.9436 | **FAIL** (sign reversed) |
| C | 5 (secondary) | 15,214 | −1.1933 | −0.9598 | 3.3611 | **FAIL** |

**Overall, per panel (the two do not rescue each other, §6): E — not beyond noise. C — not beyond
noise.**

The h = 5 Panel E row is the closest the experiment comes to a positive, and it is instructive
rather than encouraging: t = 2.0693 clears the absolute floor and is then beaten by 2 of the 20
sign-flip draws, whose own top-20s are pure selection on noise. That is precisely the comparison the
placebo exists to force — an absolute t-floor alone would have called this a pass.

---

## 2. Method as implemented, and every deviation

Implemented exactly as §3–§6 specify: r = close/close_prev − 1 on the store's own split- and
dividend-adjusted closes; σ = 20-bar sample std (ddof 1) strictly prior; z = r/σ; bins D/F/U at
∓0.5; patterns = the ordered last k bins for k ∈ {3,5,8}, base-3 encoded into one 0–6,830 id space
(6,831 per panel); outcome = the cross-sectionally demeaned next return (h = 1) or the sum of the
next five (h = 5); pattern portfolio = the equal-weight average of that outcome over the names
carrying the pattern; statistic = mean / Newey-West SE at lag h; measurability ≥ 10 names on ≥ 250
bars (E) and ≥ 5 on ≥ 2,000 (C); placebos P1 and P2 at seeds 1…20; top-20 held out once.

**Deviations and resolutions**, each declared before the number it affects:

1. **Placebo target (ADDENDUM 01 A).** §5 says the placebos are applied to "the demeaned return
   matrix"; §3 builds the alphabet on the raw return. Taken together literally the two arms would
   run different alphabets. Resolved by giving the scanner one input matrix and doing σ, bins and
   demeaning inside it: the real arm is fed raw returns, each placebo a transform of the same raw
   returns. The arms then differ by exactly the placebo.
2. **Panel E's universe and calendar (ADDENDUM 02).** §2's "every ticker in the store" includes 73
   spot-crypto tickers that quote every calendar day; the union index would then be a calendar-day
   index on which §2's own missing-predecessor rule deletes *every* equity return. Continuous-calendar
   instruments are excluded (the store's own `trades_every_calendar_day`) and a bar is a date
   carrying ≥ 10% of the median live-name count. 17 FX quotes and 7 index symbols are **kept**, per
   §2's literal rule — see limits.
3. **Panel C has only 9 measurable patterns**, so §6's "top 20" took all 9. The Panel C holdout leg
   is thinner than the design assumed. Not a choice; a consequence of 25 names against a 10-name
   equivalent floor of 5 and 6,831 codes.
4. **Under-specified points** (HAC across gaps, outcome-window containment at the window boundary,
   burn-in inside the declared sample, the holdout name floor, the cost arm's turnover definition,
   the synthetic split): all declared in ADDENDUM 01 items B–I before any real number existed.
5. **The holdout phase was executed twice.** The first execution computed everything and then died
   at the persistence step (a NOT NULL constraint: the P2 summary row had a NaN Sharpe, because §6
   gives P2 no holdout leg and the row had nothing to put there). It wrote no output file. The fix
   gave P2 the same holdout leg, reported only; it touched nothing on the real or P1 path that
   either gate reads, and the computation is deterministic. The committed numbers are the second
   execution's.
6. **A timing probe produced real Panel E discovery numbers before ADDENDUM 02 was committed**,
   disclosed in that addendum with its numbers. The committed run reproduces them exactly
   (117 measurable, N3 = 0, Tmax 2.8843).

---

## 3. Panels

| | Panel E | Panel C |
|---|---|---|
| content | US equity daily, point-in-time price store `v1` | Binance hourly spot |
| bars × names | 2,685 × 1,437 | 61,405 × 25 |
| window | 2016-01-04 … 2026-09-08 | 2019-09-08 … 2026-09-11 |
| discovery / holdout | …2022-12-31 / 2023-01-03… | …2023-12-31 / 2024-01-01… |
| store state | 1,592 ticker files, 126,371,032 bytes | 25 spot files (+25 perp) |
| dropped | 73 continuous-calendar, 82 under 1,000 rows, 98 US-holiday dates | none |
| fingerprint (sha256) | `712267499d12ab34fa97c7409455c36595feb0c8343f37b5b6271cb104eb77c8` | `b6d4cf58e8a7b541c323a7f5c6d17922147d26828fd2f585cefea16944a5bb7d` |

---

## 4. Top-20 patterns, discovery → holdout

Full tables in `holdout_top20_E.csv` / `_C.csv`; every measurable pattern in
`patterns_discovery_E.csv` / `_C.csv`.

**Panel E, h = 1** (orientation is the discovery sign; holdout t is that pattern's own oriented t):

| rank | pattern | k | orient | discovery t | holdout t |
|---|---|---|---|---|---|
| 1 | DFFDF | 5 | + | 2.8843 | −0.3020 |
| 2 | FUUUF | 5 | − | −2.6337 | 0.2912 |
| 3 | DUD | 3 | + | 2.5013 | 0.4708 |
| 4 | UFU | 3 | − | −2.4931 | 1.2549 |
| 5 | UDFUF | 5 | + | 2.3268 | −0.4856 |
| 6 | FUU | 3 | − | −2.2942 | 0.2537 |
| 7 | FFD | 3 | + | 2.0574 | 1.2350 |
| 8 | UDU | 3 | − | −2.0240 | 0.0275 |
| 9 | UFFFF | 5 | − | −1.8333 | −0.4579 |
| 10 | FFFFFFFF | 8 | − | −1.7599 | 0.3898 |
| 11 | DFF | 3 | + | 1.7589 | 0.2008 |
| 12 | FFUDD | 5 | − | −1.7268 | 0.4001 |
| 13 | FFFUF | 5 | − | −1.7107 | 0.8471 |
| 14 | UUFFF | 5 | + | 1.6807 | 1.3451 |
| 15 | FDFUF | 5 | + | 1.6323 | −0.8175 |
| 16 | FFFUU | 5 | + | 1.6318 | −2.2499 |
| 17 | UUF | 3 | − | −1.5741 | 1.6403 |
| 18 | FUDFU | 5 | − | −1.5622 | 1.5710 |
| 19 | UFFUF | 5 | − | −1.4862 | −1.5603 |
| 20 | DFFFF | 5 | + | 1.4485 | −0.4061 |

13 of 20 keep their sign out of sample and 7 flip; none reaches |t| = 2.3 in the holdout.

**Panel C, h = 1** (all 9 measurable patterns, all k = 3):

| rank | pattern | orient | discovery t | holdout t |
|---|---|---|---|---|
| 1 | DUF | + | 2.8173 | 0.9721 |
| 2 | FUF | − | −1.9792 | −0.7456 |
| 3 | FFD | + | 1.9295 | −0.2802 |
| 4 | FFU | − | −1.9215 | 0.6162 |
| 5 | UFF | + | 1.3544 | −1.9669 |
| 6 | FFF | + | 1.1079 | 0.0051 |
| 7 | DFF | + | 0.6073 | −1.3829 |
| 8 | FDU | + | 0.4830 | −0.7605 |
| 9 | FDF | + | 0.3473 | −1.3648 |

6 of 9 flip sign out of sample.

---

## 5. Placebo envelopes (20 draws each)

Discovery-window Tmax and N3 across the draws:

| panel | arm | h | N3 min/med/max | Tmax min/med/max |
|---|---|---|---|---|
| E | P1 sign-flip | 1 | 0 / 0 / 2 | 1.8931 / 2.7801 / 3.5799 |
| E | P1 sign-flip | 5 | 0 / 0 / 2 | 1.9251 / 2.6042 / 3.4264 |
| E | P2 time-shuffle | 1 | 0 / 0 / 1 | 1.9612 / 2.4963 / 3.1794 |
| E | P2 time-shuffle | 5 | 0 / 0 / 1 | 1.9401 / 2.6558 / 3.3862 |
| C | P1 sign-flip | 1 | 0 / 0 / 1 | 0.3837 / 1.3128 / 3.0294 |
| C | P1 sign-flip | 5 | 0 / 0 / 1 | 0.7381 / 1.2950 / 3.3156 |
| C | P2 time-shuffle | 1 | 0 / 0 / 0 | 0.1222 / 0.9267 / 2.3002 |
| C | P2 time-shuffle | 5 | 0 / 0 / 0 | 0.0339 / 0.7897 / 2.4173 |

The real arm's Tmax sits just **above the median** of the placebo distribution on Panel E (2.8843
against a P1 median of 2.7801) and well above it on Panel C (2.8173 against 1.3128) — but below the maximum in
both, which is what §5's 1/21 envelope rule asks. **P2 agrees with P1 on every leg of every gate**,
so §5's "if P1 and P2 disagree, P1 decides" tie-break is never invoked.

Holdout-leg envelope, h = 1, the 20 P1 draws' own top-20 books:
E — max 2.0969, and 3 of 20 draws exceed the real arm's 0.7116 by more than a full t.
C — max 1.9436; the real arm is −1.6828, below 19 of the 20 draws.

---

## 6. Control non-degeneracy (§5) — Panel C FAILS its own bar

§5 requires the builder to show that the fraction of (pattern, date) cells whose membership is
identical between the real panel and a P1 draw is **below 5%**. Denominator: cells non-empty in at
least one arm (counting the cells empty in both would make any control pass for free).

| panel | identical / union | fraction | §5 bar | result |
|---|---|---|---|---|
| E | 37,804 / 3,272,756 | 0.01155 | 0.05 | pass |
| C | 158,435 / 3,108,056 | **0.05098** | 0.05 | **FAIL** |

Panel C by k: k = 3 → 0.09068, k = 5 → 0.06021, k = 8 → 0.02932. The cause is structural and not a
coding defect: 25 names spread over 27 three-bin codes leaves a large share of single-name cells,
and a name whose three bins are all F keeps all three under a sign flip, so that cell's membership
survives the placebo.

**Direction of the bias, stated rather than assumed.** A partially degenerate control makes the
placebo arm resemble the real arm, which inflates the placebo envelope and therefore makes GATE 1
and GATE 2 **harder** for the real arm, not easier. Panel C's FAIL is conservative on this account.
It is nevertheless a pre-registered check that Panel C does not meet, and it belongs on the record
as a limit of the crypto panel rather than as a result.

---

## 7. Secondary items (§6: reported, never gating)

* **|t| ≥ 4:** zero patterns on either panel, in the real arm and in all 40 placebo draws, at both
  horizons. The N4 leg is uninformative here — nothing in this experiment ever reached 4. The single
  largest |t| produced anywhere in the whole experiment is **3.5799, and it belongs to a sign-flip
  placebo draw of Panel E**, not to the real data.
* **h = 5:** in the table above. Its one near-miss is discussed in §1.
* **Naive cost arm** (5 bp one-way on E, 10 bp on C, on the implied name-weight turnover of the
  top-20 book; ADDENDUM 01 item H):

  | panel | h | turnover/bar | t before cost | t after cost |
  |---|---|---|---|---|
  | E | 1 | 1.733 | 0.7116 | −6.8898 |
  | E | 5 | 1.548 | 2.0693 | −0.4658 |
  | C | 1 | 1.161 | −1.6828 | −84.7944 |
  | C | 5 | 1.373 | −1.1933 | −43.7692 |

  A book that re-forms from scratch every bar turns over more than its gross exposure each bar and
  is cost-dominated by construction, exactly as §6 predicted. Even had a gate passed, nothing here
  would have been tradable in this form.
* **Perp-close robustness for Panel C** (61,424 bars × 25 perp symbols): GATE 1 FAIL (Tmax real
  2.0529 vs. placebo max 2.1461; N3 0 vs. 0), GATE 2 FAIL (t 0.3156 vs. floor 2.0 and placebo max
  2.2356). Same verdict as spot.
* **Patterns scanned, recorded so nothing is hidden (§6):** 6,831 × 2 horizons × 2 panels = 27,324,
  of which 117 (E) and 9 (C) per horizon were measurable.

---

## 8. Validation on a known answer (§7)

From `tests/test_pattern_scan_placebo.py`, 18 tests, all passing. Synthetic panel: 500 names ×
2,000 bars of i.i.d. Student-t(4), planted rule +0.30σ on the return after a (U,U,U) computed on the
*unplanted* series, so the scanner has to re-derive its bins from the planted data.

| §7 requirement | measured |
|---|---|
| planted UUU recovered at t ≥ 3 | **t = 27.156** (mean 2.277e−3, 1,046 bars, 13.7 names/bar) |
| planted UUU in the top-3 by \|t\| | **rank 1** |
| planted UUU holdout t > 2 | **18.850** (the whole top-20 book: 7.170) |
| P1 draw's \|t\| ≥ 3 count vs. ≈ 6,831 × 0.0027 ≈ 18 | **0 observed**, against 0.08 expected on the 28 patterns actually measurable in a 500-name panel; §7's 18 assumes all 6,831 are measurable, which 500 names cannot make true (ADDENDUM 01 item I) |
| §5 non-degeneracy on the synthetic panel | 35,121 / 1,532,254 = **0.02292** |

The Newey-West transcription is pinned against `statsmodels`' own HAC (`cov_type="HAC"`,
`use_correction=False`) to a relative 1e-10 at lags 1 and 5, rather than trusted as a remembered
formula. The base-3 encoding round-trips over all 6,831 ids, and `code_matrix` is checked cell by
cell against `encode_pattern`. A test asserts that blanking every holdout bar leaves the discovery
scan bit-identical, and that `run_holdout` raises without a discovery result, with a mismatched arm,
or with a non-discovery window.

**Independent re-derivation** (CLAUDE.md, and the "must not share helpers" rule): Panel E's top
discovery pattern DFFDF was re-derived from the store in a separate pandas script that imports
nothing from `pattern_scan_placebo` — its own weekend test, its own binning, its own grouping, its
own Bartlett sum. It returns t = 2.8843494441088247 against the module's 2.8843494441088264 (a
float-summation-order difference in the last two digits), mean 0.0012461367252361174 vs.
…82, 299 bars and 21.622073578595316 mean names — the latter two exact.

**GATE 2's headline number was re-derived the same way.** A second independent pandas script (top-20
list and orientations taken as given from `holdout_top20_E.csv`, everything else rebuilt) returns
922 holdout bars, mean 8.114231026341034e−05, **t = 0.7116167074188684** and annualized Sharpe
0.3685874463541557 — the module's 0.7116 and 0.3686 to every printed digit. The primary gate's
number is therefore reproduced by code that shares no helper with the module under test.

---

## 9. Could not verify / limits

1. **One alphabet.** Sign-and-size bins of the last 3–8 bars. A negative here says nothing about
   volume, level, multi-scale, calendar or cross-asset shapes. §9 forbids adding a second alphabet
   to this run; it would need its own pre-registration.
2. **The scan's real resolution is k = 3 and the common k = 5 shapes.** 117 of 6,831 patterns are
   measurable on E and 9 on C. Most k = 8 codes cannot put 10 names on a bar out of 1,437 names
   spread over 6,561 codes. The experiment did not test long patterns; it could not.
3. **Panel C's control fails its own non-degeneracy bar** (§6 above). Conservative in direction,
   still unmet.
4. **Panel E is not purely US equities.** Under §2's literal "every ticker" rule it retains 17 FX
   quotes (`AUDUSD=X` … `USDZAR=X`) and 7 volatility/rate indices (`^GVZ ^MOVE ^OVX ^SKEW ^VIX
   ^VVIX ^VXN`). Two of those are not tradable instruments at all. 24 of 1,437 names.
5. **Survivorship is not removed, only neutralised across arms.** The universe is whatever the store
   holds because earlier families needed it. Both arms share it and the outcome is demeaned, so it
   cannot manufacture a difference between them — but this is not a point-in-time index and no claim
   about absolute levels should be read off these numbers.
6. **The cost arm understates.** It charges the pattern-basket leg only, not the short in the
   equal-weight universe that cross-sectional demeaning implies (ADDENDUM 01 item H). Since the cost
   arm's role here is only to show the book is cost-dominated, understating it is safe in direction.
7. **P1 does not preserve σ bit-exactly.** §5 claims it preserves volatility clustering "exactly";
   that is true of the return magnitudes but not of the 20-bar sample std, which is taken about a
   window mean a sign flip moves. Second-order, and disclosed rather than asserted away.
8. **P1 leaves the placebo arm without a market factor** for the demeaning to remove (ADDENDUM 01
   item A). Unavoidable once the placebo is applied to raw returns, which the alphabet requires.
9. **Not measured: statistical power.** No claim is made that this design would have detected a
   small real edge. The synthetic validation shows it detects a 0.30σ rule at t = 27; it says nothing
   about a 0.02σ one. A negative from this experiment is "not distinguishable from the placebo",
   never "there is nothing there".
10. **Production reproducibility.** The price store, like every file store in this project, is local;
    Render's free tier has no persistent disk (paid-decisions P7). The "same request twice returns
    the same panel" guarantee behind these fingerprints holds on the owner's machine only.

---

## 10. Artifacts

`PREREGISTRATION.md`, `ADDENDUM_01_*.md`, `ADDENDUM_02_*.md`, `RUN_REPORT.txt`, `run_output.json`,
`patterns_discovery_E.csv`, `patterns_discovery_C.csv`, `placebo_envelope.json`,
`holdout_top20_E.csv`, `holdout_top20_C.csv`, this file;
`app/services/research_lab/pattern_scan_placebo.py`, `tests/test_pattern_scan_placebo.py`,
`data/research_runs/run_pattern_scan_placebo.py`; and 6 rows (one per panel per arm) in
`cross_sectional_trial_results` under run tag `pattern_scan_placebo_2026-09-11`, family key
`pattern_scan_placebo`. The DSR field on those rows is informational: §6 handles multiple
comparisons with the placebo envelope, and no gate in this experiment reads a DSR.

Runtime: discovery 44.0 s, holdout 67.4 s (both panels, all 40 draws, both horizons, plus the perp
re-run), on the owner's machine.
