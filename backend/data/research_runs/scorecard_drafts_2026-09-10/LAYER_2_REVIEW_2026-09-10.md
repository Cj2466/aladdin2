# Layer 2 / Layer 3 review of the four live registrations (2026-09-10)

Reviewer: the Fable 5.1 main session, independent of every build and of each build's
same-day verification pass. Applied to the drafts by `apply_layer_2_3_review.py`, whose
docstring identifies (by SHA-256) the exact documents read. Companion to
`LAYER_2_SOURCE_DOSSIER.md`, which gathered the raw material and deliberately proposed no
pairing.

## 1. What was done, and the one rule it was done under

`tests/test_registration_scorecards.py` forbids reconstructing a `source_locus` from code:
an honest locus "needs the construction context the original author had". So the method
was the only honest one available to a reviewer who did not build these families:

1. take every construction choice **and its locus as the builder recorded it** at build
   time (module docstring, pre-registration, registration file);
2. fetch the paper and re-read that locus — confirm verbatim, correct, or mark unverifiable;
3. record every deviation the builder logged, plus every one the reading found;
4. sign as reviewer, with findings — including "nothing", when that was the finding.

Where the builder recorded no source for a choice, the locus names the builder's own
document and says so. No locus was invented.

## 2. Documents obtained

| paper | version in hand | published version |
|---|---|---|
| Ball, Gerakos, Linnainmaa & Nikolaev (JFE 2016) | working paper, 17 Apr 2015, 47 pp. | not obtained (paywalled) |
| Cohen, Malloy & Nguyen (JF 2020) | NBER w25084, rev. Mar 2019, 90 pp. | not obtained (Wiley 403) |
| Frazzini & Pedersen (JFE 2014) | author draft, 10 May 2013, 80 pp. | not obtained |
| Liu, Tsyvinski & Wu (JF 2022) | NBER w25882, May 2019, 48 pp. | not obtained |
| **Boehmer, Huszar & Jordan (JFE 2010)** | **none** | **not obtained** |

The fetch tool's reader could not parse any of the PDFs; each was pulled as a binary and
text-extracted locally with pypdf 6.16.2. None is committed — retaining paper texts is the
owner's open decision (copyright dimension) — so the hashes in the script docstring are what
identify the versions.

**BHJ retrieval attempts this pass** (all 2026-09-10): SMU `ink.library.smu.edu.sg/lkcsb_
research/4664/` → Incapsula challenge page (212 bytes, then 958 with a browser UA); SMU
`viewcontent.cgi?article=5663` → the same; USU `digitalcommons.usu.edu/…article=1424&context
=gradreports` (a "Revisited" replication, not the paper) → Cloudflare "Just a moment…";
Semantic Scholar graph API title search → empty result. The paper remains unreadable from
this environment, exactly as the builder found on 2026-09-02.

## 3. Findings by family

### quality_cbop — every quote verified; two wordings corrected

* Both Appendix formula blocks, the missing-to-zero sentence, the §4.1 deflation sentence
  and all four Table 2 t-statistics (8.97 / 9.84 / 1.19 / 5.83) are **verbatim**.
* **Imprecision, not flattering:** the module sets 9.84 against 8.97 (columns 1 and 5,
  different samples); the paper's like-for-like is column 2, t = 6.97. CbOP's advantage is
  larger than the module says.
* **Mislabel in the registration file:** "that paper itself reports post-publication
  attenuation". The paper reports all three strategies' t-values attenuating "starting around
  2004" *inside* its 1963–2013 sample (§4.1 pp. 11–12) — in-sample, shared with momentum,
  years before the 2016 publication.
* **Closer to the paper than claimed:** the financials exclusion the family reaches by
  accident (no COGS-shaped tag) is the paper's explicit rule (one-digit SIC 6, §3 p. 7).
* Six real deviations, all disclosed by the builder except the first: filing-date availability
  is *earlier* than the paper's six-month lag; quarterly reformation vs annual June; magnitude
  weighting on ~68 names vs value-weighted NYSE-breakpoint deciles; the both-ends
  missing-to-zero narrowing; the Compustat→XBRL mapping; the 2015–2026 window.
* Layer 3: unconditional (searched the full text for regime language — none).

### short_interest_ratio — UNVERIFIABLE, and honestly so

* `source_text_obtained = false`. Every locus is second-hand; the card certifies nothing
  against the source and says so. The builder's second-hand record is unusually careful
  (source counts per claim; the one dissenting citation kept).
* The registered spec is the most paper-conformant cell of the grid on the three axes that
  could be sourced (ratio measure, long-side reading, monthly cadence). The largest fidelity
  gap — the unreplicated "relatively heavily traded" conditioning — sits on the paper's
  headline conditional and was already the builder's own flagged design call.
* Layer 3: the abstract's conditioning is **cross-sectional** (heavily traded), not a time
  regime; classified unconditional with that stated. The January concentration (2.05×) is a
  pre-declared diagnostic from a secondary source, not a source claim.
* **Owner decision logged:** reading pp. 80–97 needs journal or institutional access. Until
  then this layer cannot be closed for this family.

### lazy_prices_jaccard_full — every quote verified; one base-case mismatch; two economic facts

* All quotes located and matching: 34–58 bp / 7% / t = 3.59 (value-weighted); MD&A 11–22 bp;
  Risk Factors 188 bp (t = 2.76); zero announcement-day return; 18-month accrual, no reversal;
  four measures; quintiles on the prior month's distribution; 1995–2014; 10-K and 10-Q with
  10-K-only in Appendix A-13. The builder's correction of the 22%/yr briefing figure is
  exactly right. Jaccard and cosine definitions match the paper's (raw counts, no TF-IDF).
* **Base-case mismatch the pre-registration does not present as one:** the paper's main results
  *include* stop words; removal is its robustness check (Appendix A-14, "even larger"). The
  family's frozen tokenisation removes them. Recorded as a deviation — it is the paper's
  stronger variant, not its base construction.
* **The return is in the short leg** (Figure 7, p. 18: "any positive alpha on the Q5 long side
  quickly reverts to zero, while the negative alpha persists"). The registered spec is
  long_short at a now-adopted 48.16 bp/yr borrow. Layer 4 must price the expensive leg.
* **The vocabulary-size ceiling** (registration file's 2026-09-03 correction): explains
  R² ≈ 0.49–0.52 of Jaccard's variance, shares 49.0% of the short leg, and orthogonalising it
  costs 22% of the Sharpe (DSR 0.7278 → 0.5703). The paper has no analogue. A real, disclosed
  fragility of *this* construction; now on the card.
* Layer 3: unconditional (searched — none).

### cross_sectional_crypto — one citation error, one negative finding, one unverifiable claim

* **Citation error.** "BTC as the market proxy per Liu, Tsyvinski & Wu (2022)" — in the
  registration rationale, the draft's provenance field and the signal docstring — is wrong.
  LTW's market factor CMKT is "the value-weighted return of all the underlying available
  coins" (w25882 §2 p. 7), contrasted on the same page with Bitcoin's own return (1.3% vs 1.2%
  per week). Bitcoin enters LTW only as an alternative *short* leg in a robustness check. BTC
  is a defensible proxy; it is the builder's choice and must be cited as such.
* **Negative evidence not recorded anywhere in the family.** LTW test beta as one of ten
  volatility-group factors and find that beta quintile sorts do *not* generate significant
  long-short returns (§3.4 pp. 12–13) on 2014–2018 weekly data. The crypto paper the family
  relies on for the asset class finds nothing on this mechanism.
* **Unverifiable claim.** The registration rationale says the result "held up under a regime
  split". No definition and no artifact exists in `cross_sectional_crypto.py`,
  `compute_crypto_factor_exposure`, or any committed `data/research_runs` file. Treat as
  absent until its computation is committed.
* Construction deviations from FP, all real: plain 180-day OLS beta vs ρ·σᵢ/σₘ with 1-year
  vol / 5-year correlation windows and w = 0.6 shrinkage; quintile tails vs median split;
  inverse-vol vs rank weights; **dollar-neutral vs beta-neutral by levering** (ex-post BTC beta
  0.0572 is measured, not enforced); 180-day hold vs monthly rebalance; BTC vs an asset-class
  market portfolio; and FP's text does not cover crypto at all.
* Layer 3: the tested claim (FP prediction 2) is unconditional. FP's prediction 3 — BAB returns
  are low when funding constraints tighten, tested with the TED spread — *is* explicitly
  conditional, but it is not the claim under test, no crypto funding proxy was pre-declared,
  and it cannot be added after the fact.

## 4. What this pass deliberately did not do

* **Did not rewrite any live row's `registration_rationale`** (CLAUDE.md rule 6; the same
  convention the lazy_prices corrections used). The crypto rationale's two defective sentences
  — the LTW attribution and the regime split — are recorded here and on the card. Correcting
  the *module* wording is a code change the owner can ask for; correcting the persisted column
  on a running track record is not done unilaterally.
* **Did not fill layer 4, power, decision or verdict.** Those need cost-scenario sourcing
  (the borrow-cost runs exist), a capacity method, the regime-coverage narrative, and the
  pre-registration's claimed Sharpe — a separate pass. The drafts stay in this directory.
* **Did not move any draft into `data/research_runs/scorecards/`.** The completeness test
  is still red for the reason the README gives; see `SCORECARD_GAP_DECISION_2026-09-10.md`
  for the recommendation on the remaining 55.
* **Did not commit any paper text.** Owner's call.

## 5. Corrections recommended to the owner (none executed)

1. `bab_forward_registration.py` and `cross_sectional_crypto.py`: replace "per Liu, Tsyvinski
   & Wu" with the builder's actual reasoning, and either commit the regime-split computation
   or delete the sentence.
2. `quality_forward_registration.py`: "post-publication attenuation" → "in-sample attenuation
   from ~2004 (BGLN §4.1)".
3. `cross_sectional_quality.py` §1(a): "9.84 against 8.97" → "9.84 against 6.97 on the
   comparable sample (column 2)".
4. `lazy_prices_2026-09-01_preregistration.txt` cannot be edited (it is a pre-registration);
   the stop-word deviation is recorded on the card and should be carried into the module's
   TOKENIZATION section as a disclosed deviation from the paper's base case.
5. Decide on journal access for BHJ, and on retaining extracted paper texts generally.
