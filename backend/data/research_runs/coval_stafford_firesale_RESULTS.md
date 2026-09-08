# Coval & Stafford (2007) mutual-fund fire sales — candidate #14, closing note

**Verdict: DEFINITE_NEGATIVE by the letter of the pre-registered DSR rule, but
the honest reading is NOT_TESTABLE / POWER FAILURE.** Both are stated here
because reporting only the first would overstate what was learned, and
reporting only the second would look like an excuse for a null.

Branch `coval-stafford-firesales`. Not merged, not pushed, nothing registered,
no live status changed.

---

## 1. What the paper actually says (two corrections to the build brief)

Source read directly: the authors' own **September 2005 working paper**, the
pre-publication version of *"Asset fire sales (and purchases) in equity
markets"*, JFE 86(2), 2007, 479-512. Fetched from the Federal Reserve Bank of
New York's media library, sha256 `6840a832…`, 41 pages, read in full. The
published JFE version is paywalled (ScienceDirect); the one open mirror
returned nothing. **Disclosed gap: section/equation numbers are the 2005
working paper's and may be renumbered in the published article.**

**Correction 1 — the title.** The brief called it "Fire Sales in Equity
Markets". It is "Asset fire sales **(and purchases)** in equity markets". The
inflow-driven purchase leg is half the paper's own strategy, not a footnote.

**Correction 2 — the measure, and this one is substantive.** The brief
specified a measure weighting each stock by the sum of (fund outflow severity ×
fund ownership share). **That is not the paper's measure, and the paper
explicitly considered and rejected it.** Eq.(4), page 10, verbatim:

```
PRESSURE_i,t = [ Σ_j Buy_{j,i,t}(flow_{j,t} > 5%) − Σ_j Sell_{j,i,t}(flow_{j,t} < −5%) ]
               / [ Σ_j Own_{j,i,t−1} ]
```

An **unweighted net count** of constrained buyers minus constrained sellers,
over the number of owners. Unweighted by ownership share, unweighted by flow
severity. The paragraph immediately after Eq.(4) says of the share-weighted
alternative: *"Initial tests that rely such measures deliver results that are
economically large, but of mixed statistical reliability."* Two stated reasons:
price pressure needs **commonality** among owners, which a count captures and a
share-sum does not; and share-based measures are *"highly sensitive to
reporting errors in fund holdings."*

Eq.(4) is implemented as written. The brief's version was declined on the
paper's own authority, and the refusal is recorded in the module docstring
rather than silently absorbed.

This also makes the candidate genuinely distinct from this queue's
already-closed Lou (2012) FIT family: Lou's Eq.(3) is a share-weighted,
severity-weighted *average* of fund flows; Coval-Stafford's Eq.(4) is an
unweighted *count*. Different estimand, different functional form.

**The paper's own prior on itself**, which shaped the grid: at |flow| > 5% its
long-short strategy is *"economically large, but of mixed statistical
significance"* (annualized alpha 4.8%, t = 0.80 to 10.9%, t = 1.79). Only at
|flow| > 10% (Table 5.b) does it get strong (1.68%/mo, t = 2.22 to 2.64%/mo,
t = 3.50). So the 10% arm was pre-declared primary.

---

## 2. The 13F-vs-N-PORT substitution, stated plainly

The brief framed the original as 13F-based. **It is not** — Coval-Stafford use
CDA/Spectrum *mutual fund* holdings, which is much closer to N-PORT than 13F
is, so the scope mismatch is *smaller* than the brief assumed. It is not zero:

- N-PORT covers registered investment companies only (~83% of the $39.2tn
  registered-fund industry), excluding hedge funds and separate accounts. Owner
  counts here are N-PORT fund **series** counts, not Spectrum fund counts, so
  the −15%/+25% cutoffs are applied to a differently-populated denominator.
- History is Oct 2019→now (~6 years) against the paper's 25. Binding, unfixable.
- Mergers corrupt the flow identity on ~33.7% of fund-quarters (median error
  13.4bp) — inherited, irreducible; biases toward *less* measured signal.
- Flow definition is Item B.6.a − B.6.c (external flow), already resolved for
  this project on 49,705 fund-quarters (`a1d64b3`) and adopted unchanged.

An infrastructure blocker was found and solved rather than worked around: the
existing `data/nport_bulk` cache was filtered at fetch time to **S&P 500 CUSIPs
only** (599 distinct `ISSUER_CUSIP` in 2024q1, verified). Reading it would have
returned a **silently empty S&P 600 arm while logging "already cached"** for
every quarter. A separate union cache was fetched instead: 1828 CUSIPs across
1695 tickers, 27 quarters, 423MB (2024q1 now carries 1516 distinct CUSIPs).

---

## 3. The pre-registered result

Pre-registration committed `3a81d63` at 13:29:41 +07, **before any strategy
return was computed**. 24 specs = 2 flow thresholds × 3 legs × 2 weightings ×
2 universes — deliberately the paper's own Table 5.a/5.b structure, so it
cannot be mistaken for a search. Bar 0.95 across the ladder {24, 37, 362, 1031}.

| | |
|---|---|
| Best spec (baseline) | `sp600/cs_flow0.05_long_value_baseline` |
| Sharpe | **−0.3771** |
| DSR @ N=24 / 37 / 362 / 1031 | **0.00424 / 0.00315 / 0.00076 / 0.00042** |
| preservation_score | **−0.0** |
| Zero-cost arm, best | DSR@24 **0.00509** — same verdict |

Fails the 0.95 bar at the most lenient rung by three orders of magnitude, at
zero cost as well as at baseline cost. `preservation_score` computed for all 24
specs, no exceptions. 24 rows persisted to main's `aladdin2.db`
(`firesale_pressure` 12 + `small_cap_firesale_pressure` 12; 2945 → 2969).

---

## 4. Why that verdict is NOT evidence about the mechanism

**Pre-registered check C2 fired on every single spec.** C2, frozen before any
result existed: *"If the long leg is formable in under 1/3 of months, the arm
is reported as POWER-LIMITED and its DSR is not treated as informative in
either direction."*

| universe | months | long leg formable | short leg formable |
|---|---|---|---|
| sp500 | 65 | **0** | **0** |
| sp600 | 67 | **2** (3.0%) | **0** |

22 of 24 specs have Sharpe exactly 0.0000 because the portfolio never held
anything. A DSR computed on a strategy that essentially never trades says
nothing about forced selling. **The correct verdict is that this candidate was
not testable at the paper's own cutoffs on this data.**

### The root cause, measured rather than asserted

Coval-Stafford's footnote 7 defines its cutoffs *distributionally*: *"The
cutoffs of −15% and 25% approximately correspond to the 5th and 95th
percentiles of the PRESSURE variable."* On this project's panels those
percentiles are somewhere else entirely:

| | paper | S&P 500 | S&P 600 |
|---|---|---|---|
| 5th percentile of PRESSURE | −15% | **−2.88%** | **−6.34%** |
| 95th percentile | +25% | **+13.68%** | **+13.82%** |
| median fund owners per stock | **47** (worked example) | **643** | **246** |
| cells ≤ −15% (of 39,070 / 64,347) | 5% by construction | **50** (0.13%) | **232** (0.36%) |

The mechanism is ownership density. Reaching a *net* −15% of owners when the
median stock has 643 fund owners requires ~100 simultaneous net forced sellers;
in the paper's 47-owner example it requires 7. The paper's numeric cutoffs do
not transfer to a modern N-PORT panel, and the emptiness is a property of
**the cutoff**, not (on this evidence) of the mechanism.

### The exploratory arm — labelled, and excluded from the grid

Per pre-registered check C3, cutoffs were **not** re-tuned inside the family. A
separate `explore_firesale_cutoffs.py` re-runs at percentile-matched cutoffs,
writes no DB rows, and is excluded from the 24-spec denominator. It is
look-ahead-tainted (percentiles measured on the full sample) and un-costed, so
it could never have produced a registrable result. It answers one question:

| arm | long formable | long net-of-market | long-short |
|---|---|---|---|
| sp500 percentile 5/95 | 20/65 months (155 names) | **+0.055%/mo** | **−0.028%/mo** |
| sp600 percentile 5/95 | 30/66 months (99 names) | **+0.114%/mo** | **−0.026%/mo** |

So: making the test *possible* does not make it *positive*. Even gross of
costs, with look-ahead in the cutoff choice, the long-short spread is slightly
**negative** in both universes and the long leg's market-adjusted return is
economically trivial. That materially strengthens the negative reading —
while remaining, honestly, not a clean test.

### The paper's own falsification control (C1)

The unconstrained-pressure control (flow condition removed, Table 4 Panel B)
was computed and is reported, but with every constrained arm empty there is no
constrained-vs-unconstrained comparison to make. **C1 is unevaluable here**, not
passed and not failed.

---

## 5. Independent verification

`verify_firesale_pressure.py` is a separate code path that never imports the
family. **It needed five corrections before it agreed — and in every case the
family was right and the re-derivation wrong:**

1. quarterly flow is the **sum of three monthly fields**, not month 3 alone;
2. skew/kurtosis standardize on the **population** second moment (scipy
   `bias=True`), not the ddof=1 sample std used for the Sharpe;
3. filings need the `filing_date < report_date` and positive-net-assets refusals;
4. accessions must be deduplicated globally;
5. holdings count only **long common equity measured in shares**
   (`UNIT == NS`, `ASSET_CAT == EC`, positive balance, no `999999999`).

Final state: filing selection reproduces the family's **10,671 snapshots and
every refusal category exactly**; five real PRESSURE cells re-derive to the last
digit (ESE, RITM, FLO, VECO, SSP); DSR matches to **2.6e-18**; all seven reused
shared modules diff clean against `main`. **Stated plainly: a check that had to
be corrected five times to agree is weaker evidence than one that agreed
immediately** — though each correction was a demonstrable bug in the checker,
diagnosed against the family's own source, not a tuning of the check.

Full backend suite: **1 failed, 4382 passed, 3 skipped**. The one failure is the
pre-existing `test_registration_scorecards.py::test_every_family_has_a_scorecard`,
documented in its own source as *"EXPECTED TO FAIL until scorecards are
written"* (50 of 51 families lack one). This family adds 2 keys to that list.

---

## 6. Recommendation

**Close as an honest negative on testability grounds; do not register
anything.** Specifically:

- Do **not** record this as "the Coval-Stafford mechanism does not work." It
  was not tested at the paper's cutoffs — the sample was empty.
- **Do** record the transferable finding, which is reusable well beyond this
  candidate: **fixed percentile-derived thresholds from pre-2005 institutional
  holdings papers do not transfer to N-PORT-era ownership breadth.** Any future
  family porting a cutoff from that literature should re-derive it as a
  percentile of its own panel and say so, or it will silently test nothing.
  This applies directly to any remaining Group C candidate in the flow queue.
- A future round wanting a real test of this mechanism needs either
  percentile-relative cutoffs pre-registered *before* seeing returns (the
  exploratory arm suggests the answer would still be negative), or a universe
  with genuinely sparse fund ownership — which free data does not obviously
  supply.
