# SOURCES — candidate sourcing, 2026-09-11

Every file in this directory is text I extracted from a document I fetched and read during this
task (`pdftotext -layout`, an HTML tag-strip, or a raw S3 XML listing). Fetch date for all of them
is **2026-09-11**. SHA-256 is of the file as committed in this directory, not of the original
PDF/HTML.

Three files (#3, #4, #5) are **byte-identical copies** of extracts that the 2026-09-11
hunting-ground review already committed under
`data/research_runs/hunting_ground_review_2026-09-11/sources/`. I did not re-fetch those three;
I read the committed extract myself for this task, and the matching SHA-256 is the evidence that
it is the same text that review's SOURCES.md documents the URL and fetch for. Everything else
here was fetched fresh by me today.

**Evidence tiers** (same scale the hunting-ground review used): **T1** peer-reviewed / regulatory
/ primary-vendor document, read by me · **T2** working paper or preprint, read by me · **T3**
credible secondary source read by me · **T4** recalled, not verified · **H** hypothesis.

---

## 1. `chen_velikov_zeroing_in_2020.txt`
- **Document**: Andrew Y. Chen & Mihail Velikov, "Zeroing in on the Expected Returns of Anomalies",
  Finance and Economics Discussion Series 2020-039, Federal Reserve Board, May 2020.
- **URL fetched**: https://www.federalreserve.gov/econres/feds/files/2020039pap.pdf
- **SHA-256**: `897e477989062ad2b637069125941fb39e77eadd63f268327ce765497d26b304`
- **What I read**: abstract; the introduction's two data-mining adjustments (the out-of-sample
  quartile sort and the empirical-Bayes estimator) including every headline bps figure; Section
  4.2.2's empirical-Bayes result paragraphs; Table 3 (out-of-sample quartile sorts, Panels A and
  B) and Table 4 (empirical-Bayes parameter estimates and adjusted returns, Panels A and B) in
  full.
- **Tier**: **T2** — this is the Fed working-paper version (120 anomalies, "a measly 8 bps per
  month"). A published version exists in JFQA 58(3), 2023; a web-search snippet described it as
  covering 204 anomalies and 4 bps per month. **I did not read the published version**, so the
  204/4-bps figures are NOT used anywhere in my deliverables; every Chen-Velikov number I cite is
  from this FEDS PDF.

## 2. `nagel_evaporating_liquidity_2011.txt`
- **Document**: Stefan Nagel, "Evaporating Liquidity", NBER Working Paper 17653, December 2011
  (published Review of Financial Studies 25(7), 2005-2039, 2012 — I did not read the published
  version).
- **URL fetched**: https://www.nber.org/system/files/working_papers/w17653/w17653.pdf
- **SHA-256**: `1088bd72ddc3d57ebc1adb9407acec12df79a7f8ae03fe0ab0a860f25c8e55b7`
- **What I read**: abstract; the "mapping the model to the data" subsection (individual stocks vs
  industry portfolios, return-measurement horizon, heterogeneity in scale, sample period and the
  1998 start / decimalization discussion); Table 1 in full (raw and market-hedged reversal
  strategy statistics, transaction-price vs quote-midpoint); the paragraphs interpreting Table 1
  including the author's own caveat about fixed costs for high-speed market access; Section 3.4 /
  Figure 4 (reversal returns within size-, illiquidity- and volatility-sorted subgroups) and the
  conclusion's first paragraphs.
- **Tier**: **T2** (NBER working paper, explicitly not peer-reviewed; the RFS article is the
  peer-reviewed object and I did not read it).

## 3. `novy_marx_velikov_taxonomy_2014.txt`
- **Document**: Robert Novy-Marx & Mihail Velikov, "A Taxonomy of Anomalies and their Trading
  Costs", NBER Working Paper 20721, December 2014 (published RFS 29(1), 104-147, 2016).
- **URL** (as recorded by the hunting-ground review, which fetched it):
  https://www.nber.org/system/files/working_papers/w20721/w20721.pdf
- **SHA-256**: `3897a646ffec23670a0bdeeece2bfd3217c39769c9ff26abeba9087cce699982` — identical to the
  hunting-ground review's committed copy.
- **What I read (this task, beyond what that review read)**: the effective-spread measurement
  section around Figure 1 (median effective spreads by market-capitalization rank; the convexity
  of the cost/size relation and the explicit warning in Appendix A.2 against extrapolating
  large-cap cost models to small stocks); the low/mid/high turnover strategy definitions and the
  full-universe turnover/cost/net-return table rows for the reversal strategies; and — the part
  this task actually turns on — **Table 13 in full** ("Value-weighted excess returns on sS
  strategies by size": gross and net returns with t-statistics for micro / small / large size
  bins, Panels A (low turnover), B (mid turnover) and C (high turnover)), plus the Section-7
  paragraphs that interpret it.
- **Tier**: **T2** (NBER working paper version).

## 4. `mclean_pontiff_2016.txt`
- **Document**: R. David McLean & Jeffrey Pontiff, "Does Academic Research Destroy Stock Return
  Predictability?" (Journal of Finance 71(1), 5-32, 2016; author-hosted accepted version).
- **URL** (as recorded by the hunting-ground review, which fetched it):
  https://tevgeniou.github.io/EquityRiskFactors/bibliography/AcademicReviewFactor.pdf
- **SHA-256**: `67272f8d8c35045798c66a202cf879c851784ec804bdbe10855c07de403250d2` — identical to the
  hunting-ground review's committed copy.
- **What I read (this task)**: the abstract and the introduction paragraphs containing the 26%
  out-of-sample / 58% post-publication decline and the 32% publication-informed-trading residual,
  and the sentence stating the out-of-sample decline is an upper-bound estimate of data-mining
  effects. This is the sole basis for the 0.5 offset fraction used in every power check below.
- **Tier**: **T1**.

## 5. `hou_xue_zhang_replicating_anomalies.txt`
- **Document**: Kewei Hou, Chen Xue, Lu Zhang, "Replicating Anomalies", NBER Working Paper 23394,
  May 2017.
- **URL** (as recorded by the hunting-ground review, which fetched it):
  https://www.nber.org/system/files/working_papers/w23394/w23394.pdf
- **SHA-256**: `f094a134e0073feeb295b2edb464dea2b9fbbdc96d01654ba46ef76c8a043160` — identical to the
  hunting-ground review's committed copy.
- **What I read (this task)**: the microcap paragraphs — Fama-French (2008) as HXZ report it
  (microcaps are 3% of total NYSE-Amex-NASDAQ market capitalization but 60% of the number of
  stocks), the 20th-NYSE-percentile microcap definition, and HXZ's own stated reason for their
  replication failures ("because of high costs in trading these stocks, anomalies in microcaps are
  more apparent than real").
- **Tier**: **T2** (NBER working paper).

## 6. `ante_crypto_exchange_listings_2019.txt`
- **Document**: Lennart Ante, "Exploring Market Reactions to Exchange Listings of
  Cryptocurrencies", Blockchain Research Lab Working Paper Series No. 3, 8 September 2019.
- **URL fetched**: https://www.blockchainresearchlab.org/wp-content/uploads/2019/10/Exploring-Market-Reactions-to-Exchange-Listings-of-Cryptocurrencies-BRL-working-paper3.pdf
- **SHA-256**: `f1ba8962a39b8f4e5f16c33ab9872e5a603c3ca8de1aa1034100c3ab064c93d2`
- **What I read**: abstract; the introduction's description of when listing information becomes
  public; the sample description (327 listings of 180 cryptocurrencies across 22 exchanges); the
  event-study method (market model with Bitcoin as the market portfolio); the per-exchange CAAR
  table rows for Binance; and the announcement-vs-actual-listing split discussion.
- **Tier**: **T2** (working paper, not peer-reviewed).

## 7. `kitron_wengrowicz_crypto_short_horizon_reversion_2026.txt`
- **Document**: Nadav A. Kitron & Jonathan M. Wengrowicz, "Short-horizon mean reversion in
  cryptocurrency markets: a matched cross-market measurement", arXiv:2608.21888v1, 22 August 2026.
- **URL fetched**: https://arxiv.org/pdf/2608.21888
- **SHA-256**: `bc60e6c13546918d262120ce90c9834d94c6c391d91974f9d2d8de42aeb149b2`
- **What I read**: abstract; the introduction in full (including the evidential hierarchy
  paragraph and the relation-to-literature paragraph on equity short-horizon reversal).
- **Tier**: **T2** (arXiv preprint by two authors listing themselves as independent researchers;
  no institutional affiliation and no peer review — weighted accordingly).

## 8. `borri_liu_tsyvinski_wu_crypto_asset_class_2025.txt`
- **Document**: Nicola Borri, Yukun Liu, Aleh Tsyvinski, Xi Wu, "Cryptocurrency as an Investable
  Asset Class: Coming of Age", arXiv:2510.14435v2 (v1 submitted 16 October 2025).
- **URL fetched**: https://arxiv.org/html/2510.14435v2 (HTML, tag-stripped). Title, author list and
  submission date confirmed separately against https://arxiv.org/abs/2510.14435.
- **SHA-256**: `ebf82a08123f32e4fc4028e11af5fe40c97cb7c9f6f136cae0725a08f5f6de12`
- **What I read**: the table of contents / list of the ten stylized facts; the Fact 4 section on
  crypto size, momentum and value in an updated sample; the Fact 9 paragraph reporting the
  cryptocurrency-carry Sharpe ratio by subperiod.
- **Tier**: **T2** (preprint; three of the four authors are the authors of the Liu-Tsyvinski-Wu
  crypto-factor papers this project's `cross_sectional_crypto` family already cites).

## 9. `binance_vision_probe_2026-09-11.txt` and `binance_vision_futures_um_daily_listing.xml`
- **Document**: Binance's own public market-data archive (data.binance.vision), queried through
  its S3 bucket listing API and by direct object fetch.
- **URLs fetched**:
  - `https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=data/futures/um/daily/`
  - `.../metrics/BTCUSDT/`, `.../data/spot/monthly/klines/BTCUSDT/1d/`
  - `https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2020-09-01.zip`
  - `https://data.binance.vision/data/futures/um/daily/liquidationSnapshot/BTCUSDT/BTCUSDT-liquidationSnapshot-2024-01-01.zip` (returned **HTTP 404**)
- **SHA-256**: probe log `4b4678ad8d0632ef96e4c0bb7a7521937daf5ce4cb17acfe6313d90c2584818d`;
  raw XML listing `38c28cc17f9a59a41572497486770dddd20bc519393c0a4359be62376ee79efd`.
- **What I read**: the full set of datasets published under `data/futures/um/daily/` (aggTrades,
  bookDepth, bookTicker, indexPriceKlines, klines, markPriceKlines, **metrics**,
  premiumIndexKlines, trades — and no liquidation dataset); the earliest available `metrics` file
  for BTCUSDT (2020-09-01) and its column header; the earliest spot daily kline month for BTCUSDT
  (2017-08).
- **Tier**: **T1** (primary vendor artifact, fetched directly, outputs committed).

---

## Attempted and not used
- `http://rcea.org/wp-content/uploads/2021/05/Borri.pdf` ("The Cross-Section of Cryptocurrency
  Returns", RCEA working paper) — the server returned an HTML page, not a PDF; not read, not cited.
- Web-search result snippets for several 2025-2026 crypto machine-learning portfolio preprints
  (AdaptiveTrend, Talyxion, neural ranking) were seen but **no such paper was fetched or read**, so
  none of their Sharpe figures appears anywhere in my deliverables. See `COULD_NOT_VERIFY.md`.
