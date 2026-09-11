# COULD_NOT_VERIFY — candidate sourcing, 2026-09-11

Everything on this page is something I tried to establish and could **not**, or deliberately did
not attempt. Nothing here supports any claim in `CANDIDATE_SOURCING_2026-09-11.md`; where a
deliverable depends on one of these, it says so and declines rather than assumes.

---

## A. Sources the brief named that I did NOT fetch or read

- **A.1 Frazzini, Israel & Moskowitz, "Trading Costs"** — named in the brief as a cost source to
  verify. **Not fetched, not read.** No number attributed to it appears anywhere in my
  deliverables. I stopped searching for it once Novy-Marx & Velikov's Table 13 supplied
  microcap-specific *net* returns by size bin, which is the quantity the pre-check actually needs
  (FIM's contribution is live institutional execution data, which speaks to a book size far above
  this project's and would not have changed a verdict). This is a scope decision, not a finding
  about the paper.
- **A.2 Corwin-Schultz spread estimator papers** — **not fetched, not read.** The project already
  has `spread_estimator.py` and the `bidask` package; no claim here rests on a spread-estimator
  paper.
- **A.3 Chen & Velikov, published JFQA 58(3) 2023 version** — I read the **Fed FEDS 2020-039
  working paper** (120 anomalies, "a measly 8 bps per month"). A web-search snippet described the
  published version as covering 204 anomalies with an average of 4 bps per month. **I did not read
  the published version and those two figures are T3-secondary-snippet only**; they appear nowhere
  in the report's reasoning.
- **A.4 Liu, Tsyvinski & Wu, "Common Risk Factors in Cryptocurrency" (JF 2022)** — not re-fetched
  this session. It did not need verifying for a novelty call, because `cross_sectional_crypto.py`
  already cites it as one of its five mechanisms, which settles the novelty question on its own.
  I did read a 2025 preprint by three of the same authors (source #8) for the post-publication
  update.

## B. Things I looked for and could not find

- **B.1 A primary source for a tradable open-interest or positioning signal in crypto.** Searches
  returned exchange blogs (Amberdata, Bookmap, XT, Presto, Mudrex), vendor guides (CryptoQuant),
  and one SSRN case study of the single October-2025 liquidation cascade. None reports a strategy
  effect size with a sample period, and none is peer-reviewed or a working paper from an
  identifiable research group. **Candidate B3 is declined for want of a source, not on evidence
  against it.**
- **B.2 A primary source for a tradable liquidation-cascade signal.** Same outcome as B.1, plus
  the free data does not exist (see C.2).
- **B.3 An academic source for a funding-rate signal that predicts *directional* spot returns**
  (as distinct from the delta-neutral carry `funding_carry` already tests). Searches returned
  exchange education pages and a Substack. Nothing sourceable. Not proposed as a candidate.
- **B.4 Borri, "The Cross-Section of Cryptocurrency Returns" (RCEA working paper)** —
  `http://rcea.org/wp-content/uploads/2021/05/Borri.pdf` served an **HTML page, not a PDF**. Not
  read; nothing cited from it.
- **B.5 Any measurement of microcap trading costs at a $100k-$1M book, or for a patient
  limit-order (maker) participant.** This is hunting-ground hypothesis **H3** and it remains
  completely unmeasured. Both cost sources I read (NMV; Chen & Velikov) model a **taker**
  spread-crossing cost that does not vary with book size. This is the single largest open question
  in Ground A, and it cannot be settled from the literature — it needs the project's own fills or
  its own microcap spread study.

## C. Facts I did not measure, and which should not be quoted as if I had

- **C.1 The size of the investable US microcap universe under Alpaca's 2016+ coverage.** The
  bets-per-year arithmetic in the report uses an order-of-magnitude figure of 1,000-2,500 names,
  which I did **not** measure. The portfolio-level bet count (12/yr for a monthly rebalance) does
  not depend on it, and no verdict does.
- **C.2 Whether any free source publishes historical crypto liquidation data.** I verified only
  that **Binance's own public archive does not**: the `data/futures/um/daily/` prefix listing
  contains no liquidation dataset, and a direct `liquidationSnapshot` object fetch returns HTTP
  404 (probe committed in `sources/`). I did **not** survey other exchanges or aggregators, so
  "not available free" is established for Binance only. The paid gap is logged provisionally
  (**P8**) and not acted on, per CLAUDE.md section 4.
- **C.3 Whether the EDGAR facts store could be extended to a microcap CIK roster, and at what
  cost in time or SEC rate limits.** The store currently holds 163 CIKs, an S&P-500-scale roster.
  A microcap build would need roughly an order of magnitude more. Not attempted, not estimated.
- **C.4 Whether `cross_sectional_pead`'s known successor-shell CIK-resolution defect would bite
  harder on a microcap roster.** Plausibly yes (microcaps reorganise and shell more often), but I
  measured nothing. Recorded as a prerequisite, not a finding.
- **C.5 The exact NMV sample length.** The paper says "1963 through 2013" in its data section and
  "07/1963 - 12/2012" in a table note. I used 49.5 years and showed the ~1% sensitivity at 50.5
  years in the report. No verdict turns on it.

## D. Machine-learning crypto preprints seen in search results and deliberately not used

Search results surfaced several 2025-2026 arXiv preprints reporting high crypto Sharpe ratios
(an "AdaptiveTrend" trend-following paper at 2.41, a "Talyxion" allocation paper at 3.02, a neural
ranking paper at 1.01). **I fetched and read none of them**, and no number from them appears in
any deliverable. Two reasons, stated so the omission is a decision rather than an oversight:
their headline figures come from search-result summaries (T3 at best), and a black-box selected
model cannot satisfy this project's mechanism-fidelity requirement (every construction choice
citing a source paper's section and equation) even if its Sharpe cleared the power gate.
