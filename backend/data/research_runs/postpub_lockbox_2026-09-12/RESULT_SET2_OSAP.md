# Set 2 result — the published book, one look (2026-09-12, look taken 13:45 Bangkok; protocol `LOCKBOX_PROTOCOL_OSAP.md` @ cd8d029 written first)

## Verdict by the pre-declared line: **PASS**

Primary pool = P-clean (195 of 212 predictors after the ≥36-sealed-month rule), post-PUBLICATION
months only (January after each paper's publication year → 2024-12), standard cost haircut
(20/P bps per month): **annualized Sharpe 0.599, Newey-West t 4.27, PSR vs 0 ≈ 1.00, 612 months
(1974-01 → 2024-12), decay ratio 0.39 vs the same predictors' in-sample pool.** Pass line was
Sharpe ≥ 0.50 AND PSR ≥ 0.95.

Independently re-derived by the orchestrator with plain-Python csv code (no pandas, no shared
helper): members 195, n 612, mean 0.4202 %/month, Sharpe 0.5991 — equal to four decimals.

## The whole table (one run; nothing was re-run)

| pool | window | cost | n | Sharpe | NW t | PSR | members | median per-predictor SR | share > 0 | decay |
|---|---|---|---|---|---|---|---|---|---|---|
| P-clean | post-publication | gross | 612 | 0.785 | 5.55 | 1.000 | 195 | 0.259 | 0.85 | 0.51 |
| **P-clean** | **post-publication** | **standard** | **612** | **0.599** | **4.27** | **1.000** | **195** | **0.147** | **0.72** | **0.39** |
| P-clean | post-publication | doubled | 612 | 0.412 | 2.96 | 0.9999 | 195 | 0.042 | 0.55 | 0.27 |
| P-clean | post-sample | gross | 672 | 0.414 | 3.04 | 0.9995 | 197 | 0.298 | 0.87 | 0.27 |
| P-clean | post-sample | standard | 672 | 0.243 | 1.77 | 0.971 | 197 | 0.169 | 0.74 | 0.16 |
| P-clean | post-sample | doubled | 672 | 0.072 | 0.52 | 0.707 | 197 | 0.079 | 0.58 | 0.05 |
| P-all | post-publication | standard | 612 | 0.573 | 4.09 | 1.000 | 210 | 0.131 | 0.70 | 0.36 |
| P-all | post-sample | standard | 672 | 0.217 | 1.58 | 0.955 | 212 | 0.170 | 0.73 | 0.14 |

(full JSON: `osap_lockbox_output.json`; in-sample checks: 210/212 predictors carry the paper's
sign in-sample; OSAP's in-sample means are 0.85× the papers' own numbers, units percent/month.)

## What it says, in plain terms
1. A book of ~200 published, unmodified anomalies — built by third parties, read by us for the
   first time — still shows a screening-level edge after publication and after a retail cost
   haircut: about 0.6 Sharpe, t ≈ 4, over 51 years. Each anomaly alone is small (median
   post-publication Sharpe 0.15 after costs; 72% positive); pooled, the law of large numbers does
   the work. **This is the first positive result in this project, and it is exactly the
   portfolio-level claim, not a single-edge claim.**
2. The edge shrinks to ~40% of in-sample (decay 0.39) — consistent with McLean-Pontiff's published
   post-publication decay, which is reassuring about the computation and sobering about the size.
3. The stricter-looking "post-sample" window scores LOWER (0.24 with haircut) although it contains
   more months. Not investigated here (it would be a second computation on the sealed data);
   candidate explanations to test in a separately declared look: the early pooled years (1969–80)
   hold only a handful of predictors, and the sample-end→publication gap years may differ. Flagged,
   not explained.
4. Costs decide the size: gross 0.79 → standard 0.60 → doubled 0.41. The haircut is a crude
   turnover upper bound; a real cost model per predictor would move this either way.

## Caveats that stand (written in the protocol before the look)
- Survivorship of IDEAS: these 212 are the anomalies that got published and replicated. No window
  removes that; it biases the result up by an unknown amount.
- OSAP builds on CRSP/Compustat with 210 of 242 weightings equal-weight → micro-caps carry weight
  (Hou-Xue-Zhang's objection). Set 3 must check which survive on a tradable universe with our data.
- Not our data, not our code, not our costs. This is evidence about the published literature
  pooled, and it answers the owner's question ("is there something real in the many small
  patterns?") with a measured yes — small, pooled, after decay.

## What follows (owner decides; nothing built)
- Set 1: the same lockbox on our own 20 members with paper-faithful specs (protocol next).
- Set 3: rank the 195 by (a) buildable on free data (EDGAR fundamentals, prices, 13F, FINRA),
  (b) post-publication Sharpe after haircut, (c) correlation with the pool; propose BOOK members
  from the top of that list. This is the concrete "many small edges" path the project was built for.
