# Dormant pool — pre-registration (written before any gate was run)

Date: 2026-09-09. Author: Claude (Fable 5.1) for the project owner, who
approved the four-step plan (merge criteria-fix → this → intraday-data scoping
→ one combined paid-data discussion).

## 1. The rule this implements

**A statistical failure cannot close a candidate; only mechanism evidence
can.** Measured basis (`criteria_fix_2026-09-09`): at this project's sample
lengths, 0 of 50 families had 80% power to detect a true Sharpe of 0.5 at the
0.95 bar. A "fail" at that bar is therefore "not yet visible", not "absent".
Absence is established by the mechanism-fidelity layer (the mechanism is gone
from the data, structurally untradeable, or the source itself predicts no
forecastability) — never by a Sharpe.

## 2. Three pools

| pool | who | how it leaves |
|---|---|---|
| Active | forward-tracked registrations (today: 4) | existing rules |
| **Dormant** | any family whose verdict is `underpowered`, or a pre-2026-09-09 `definite_negative` whose scorecard/mechanism review did **not** establish mechanism absence | promotion (§4) → Active; mechanism found absent → Closed |
| Closed | mechanism absent / structurally untradeable / source predicts no forecastability | never returns |

Entry into Dormant freezes: `family_key`, the selected `pattern_id`, the spec
and config fingerprints, `window_end_at_entry` (the last date of the data the
original verdict used), the family's `periods_per_year`, and whether the
family's data path is point-in-time (§6).

## 3. What is re-scored, and why that is not a new trial

Every month the data the original backtest used grows by one month. The
**extension segment** — from `window_end_at_entry` forward — is out-of-sample
for the frozen spec: the spec was selected on the original window, so no
selection happened on the extension. The primary Dormant statistic is
therefore

    PSR_ext = probabilistic_sharpe_ratio(SR_ext, 0, n_ext, skew_ext, kurt_ext)

on the frozen spec's realized **net** daily returns over the cumulative
extension only, with **N = 1** (no SR0 deflation — there is nothing to
deflate: one pre-registered spec, one pre-registered test). The full-window
DSR ladder is recomputed and reported alongside as supporting evidence, but
it is not the promotion statistic (it re-selects in-sample).

The statistic is the project's `deflated_sharpe.probabilistic_sharpe_ratio`,
called as-is. Nothing new is derived.

## 4. Look schedule and boundary (the "no peeking" rule)

Looks happen only when the extension reaches `k × 252` realized observations
of the family's own calendar (`k × 365` for a 365-day family), for
k = 1 … K_MAX = 10. Nothing is evaluated between looks; a dashboard may
*display* PSR_ext at any time but nothing acts on it.

Promotion at look k requires PSR_ext ≥ c_K, a **constant per-look boundary
calibrated by simulation** so that, under a true-zero edge, the probability
of promotion at *any* of the K_MAX looks is ≤ ALPHA = 0.05. The boundary is
not taken from a published group-sequential formula (nothing is to be
implemented from memory); it is the empirical 95th percentile of
max_k PSR_ext,k over ≥ 20 000 null paths at the pre-declared look structure,
under the null returns model of §5, seed 20260909. The calibrated value is
committed with this document once computed and never re-tuned per family.

Promotion = the family moves to Active (a forward-tracking slot). It is
**not** a pass to capital: the capital bar is unchanged (DSR ≥ 0.95 at the
highest ladder rung, plus every other layer).

## 5. Gates that must pass before anything is built (pass criteria fixed here)

G1 (size, i.i.d. normal): 50 null families × K_MAX looks with the calibrated
c_K → per-family promotion probability ≤ 0.05 + 2·MC-se, on a **different
seed** from the calibration run.

G2 (size under misspecification): the same with (a) Student-t(4) daily
returns, (b) AR(1) φ = 0.3 daily returns. Pass criterion: per-family
promotion probability ≤ 0.07 (a stated tolerance — the boundary is
calibrated under normality and the project's real return series are neither
fat-tail-free nor autocorrelation-free; if either exceeds 0.07 the boundary
is recalibrated under the worse model and G1 re-run, and that is recorded).

G3 (power, informational — no pass criterion, an honest number): for a
family whose true annual net Sharpe is 0.5 (and 0.8, 1.0), the distribution
of the look at which promotion happens, i.e. years of new data needed. If
the median for 0.5 exceeds K_MAX the document says so.

G4 (pool-level cost): with 50 null Dormant families, expected false
promotions over 10 years = 50 × per-family rate. This is the price of not
closing anything on statistics; it is a forward-tracking slot each, not
capital.

Nothing in G1–G4 is tuned after seeing results. A gate that fails is
reported as failed, as `bet_level_2026-09-09` was.

## 6. Known limits, stated now

* **Point-in-time.** A re-run on newly downloaded data is honest only where
  the family's inputs are frozen-snapshot / PIT. Where they are not (the
  known lazy_prices ticker→CIK issue), the entry carries `pit_ok = false`
  and its PSR_ext is reported but cannot promote until the data path is
  fixed. This is per family and must be filled in by a human at entry.
* **Re-scorability.** Only families with a reproducible runner (a registered
  forward adapter, or a `run_*` entry point that takes a window) can be
  re-scored. Others enter Dormant as `rescorable = false` — recorded, not
  silently skipped — until an adapter exists.
* **What this does not do.** It does not find edges. It converts calendar
  time into evidence for candidates that would otherwise have been thrown
  away, at zero data cost. The only levers that *find* small edges faster
  are more independent bets per year (breadth, more markets, intraday) —
  step 3 of the owner's plan.
