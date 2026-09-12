# Lockbox protocol — Set 2: the Open Source Asset Pricing predictors (declared 2026-09-12 13:55 Bangkok, BEFORE any post-sample number was computed)

Orchestrator: Fable 5.1. Owner's decisions (2026-09-12): one look only; the pass line is written
before the look; costs shown three ways; more papers rather than fewer, so the look is done once.
Owner's caveat accepted: the set of papers is itself selected by publication (survivorship of
ideas), which no window can remove — the result is a statement about PUBLISHED anomalies, read
by us for the first time here, not about our own system.

## 1. Data (committed, hashed — `osap/SOURCES.md`)
- `osap_ls_returns_wide.csv`: 212 predictor long-short monthly returns "following the original
  papers" (OSAP's construction on CRSP/Compustat), 1926-01 → 2024-12. Units: percent per month
  (to be confirmed from the in-sample rows against the doc's `Return` column before use — an
  in-sample check, not a look).
- `osap_signal_doc.csv`: per predictor `Year` (publication), `SampleEndYear`, `Sign`, `Portfolio
  Period` (months), `Return`, `T-Stat`, `Predictability in OP`, `Signal Rep Quality`.
- Nothing else. No family of ours enters this set.

## 2. The sealed window, per predictor
- **Primary (post-publication):** months from January of (`Year` + 1) through 2024-12. Referees
  and authors saw data through publication; nobody in the paper saw later data.
- **Secondary (post-sample):** months from January of (`SampleEndYear` + 1). Reported alongside;
  the primary decides.
- A predictor with fewer than 36 sealed months is excluded from the pooled series (there are
  6 predictors published ≥ 2015; the count excluded is reported).
- The in-sample window (through `SampleEndYear`) is used ONLY to (a) confirm return units and
  sign orientation per predictor (mean in-sample return should carry the paper's sign — any
  predictor failing this is reported and kept as-is, not flipped), and (b) compute the decay
  ratio in §5.

## 3. The pooled series ("the published book")
Equal-weight average, each month, of the sealed-window returns of every predictor sealed in that
month (the membership grows over time as papers are published). Two pools:
- **P-all:** all 212 predictors.
- **P-clean:** `Predictability in OP` ∈ {1_clear, 2_likely} AND `Signal Rep Quality` ∈ {1_good,
  2_fair} (declared now; the count is reported).
Also reported, not deciding: the cross-sectional distribution of per-predictor sealed-window
Sharpes (median, share > 0), because the owner's question is "is there something in the many".

## 4. Costs, three ways (OSAP returns are GROSS)
- **Gross** (as delivered).
- **Standard haircut:** the project's flat one-way cost 5 bps per unit traded
  (`cross_sectional.DEFAULT_XS_COST_BPS`). For a long-short book rebalanced every P months with
  full replacement, the upper-bound monthly drag is 4 legs-traded × 5 bps / P = **20 / P bps per
  month** (P from `Portfolio Period`; P missing → 1). This overstates cost for low-turnover
  signals and understates it for micro-cap-heavy ones — it is a haircut, labelled as such.
- **Doubled haircut:** 40 / P bps per month (the project's x2 cost arm convention).
No borrow cost is applied (the project's own equity default is 0; disclosed as lenient).

## 5. Statistics, and the single pass line
On each pooled series (monthly, annualized by √12; the monthly frequency is OSAP's, not a choice):
- annualized Sharpe; Newey-West t (6 lags); n months;
- **PSR** via the project's `deflated_sharpe.probabilistic_sharpe_ratio` at benchmark 0 with
  N = 1 (one pre-declared object, one look — no multiple-testing correction is due, and none is
  applied; the OSAP authors' own selection is the survivorship caveat in the header, not a
  correctable N);
- decay ratio = sealed-window Sharpe / in-sample Sharpe of the same predictors (McLean-Pontiff's
  quantity; their published post-publication decay is ~58%, not re-derived here).
**PASS (declared now):** P-clean, primary window, standard haircut: annualized Sharpe ≥ 0.50
AND PSR ≥ 0.95. (0.50 is the project's screening floor; it is what a BOOK member must show before
being watched. The 0.95 certification bar is NOT applied per predictor — that is the rule the
owner and I agreed to drop for portfolio-level judgement.) Everything else is reported, not judged.

## 6. What a PASS and a FAIL each mean, written before the look
- PASS: a book of published, unmodified anomalies, built by third parties on institutional data,
  still carried a screening-level edge after publication and a retail cost haircut. Next step is
  Set 3 (which of them are buildable on our free data) — NOT capital.
- FAIL: even the best-documented published anomalies pooled together do not clear screening after
  publication and costs at retail haircut. That closes "many small published edges" as a path
  for this project and strengthens Path B.
- Either way the look is not repeated with different settings. Variants in §2–4 are all reported
  in the same single run; none may be promoted to "primary" afterwards.

## 7. Execution
One script, `osap_lockbox.py`, run ONCE; outputs JSON + one page; the orchestrator re-derives the
primary pooled Sharpe with separate code before the number is reported to the owner. Full backend
suite before merge. No DB row (this is not a family).

---
CORRECTION (appended 2026-09-12, clock 13:44): the header time "13:55" was written before reading the clock; the protocol was committed at 13:43 (commit cd8d029). Content unchanged.
