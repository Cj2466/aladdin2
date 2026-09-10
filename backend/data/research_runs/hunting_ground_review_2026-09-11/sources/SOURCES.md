# SOURCES — hunting-ground review, 2026-09-11

Every file in this directory is text extracted (via `pdftotext -layout`, or an HTML tag-strip for the
two web documents) from a document I fetched and read during this review. Fetch date for all of them
is **2026-09-11**. SHA-256 is of the `.txt` file as committed, not of the original PDF/HTML.

Nothing in the review file cites a source that is not listed here, except where the claim is
explicitly labelled **T4 (RECALLED-NOT-VERIFIED)**, **COULD-NOT-ACCESS**, or **H (hypothesis)**.

---

## 1. `chague_daytrading_2020.txt`
- **Document**: Fernando Chague, Rodrigo De-Losso, Bruno Giovannetti, "Day trading for a living?",
  dated 13 June 2020. SSRN abstract id 3423101 (working paper; I did not verify journal publication).
- **URL fetched**: https://ebicapital.nl/wp-content/uploads/2022/05/day-trading.pdf
  (a mirror; the paper's own footer prints "Electronic copy available at: https://ssrn.com/abstract=3423101")
- **SHA-256**: `7d03a881eb903e5bdc62c0230ce0b0d4ae861568cf4fb1a95b77871156bddb03`
- **What I read**: the whole 9-page paper — abstract, Introduction, Section 2 (empirical analysis),
  Section 3 (conclusion), footnotes and reference list.
- **Tier**: T2 (working paper, read in full).

## 2. `mclean_pontiff_2016.txt`
- **Document**: R. David McLean & Jeffrey Pontiff, "Does Academic Research Destroy Stock Return
  Predictability?", marked "Journal of Finance, Forthcoming" on the title page (published JF 71(1), 5–32, 2016).
- **URL fetched**: https://tevgeniou.github.io/EquityRiskFactors/bibliography/AcademicReviewFactor.pdf
- **SHA-256**: `67272f8d8c35045798c66a202cf879c851784ec804bdbe10855c07de403250d2`
- **What I read**: abstract; introduction; Section on costly-arbitrage variables (the paragraphs
  around the Table V / Table VI discussion, incl. the β2 and β2+β3 interpretation); the
  idiosyncratic-risk result paragraph; the post-publication trading-activity section headers.
- **Tier**: T1 (peer-reviewed; this is the author-hosted accepted version).

## 3. `baron_et_al_hft_risk_return_2017.txt`
- **Document**: Matthew Baron, Jonathan Brogaard, Björn Hagströmer, Andrei Kirilenko, "Risk and
  Return in High-Frequency Trading", version dated 2017-08-25 (published JFQA 54(3), 993–1024, 2019).
- **URL fetched**: https://www.cb.cityu.edu.hk/ef/doc/GRU/HFT%202017/Brogaard_HFT_risk_return_20170825.pdf
- **SHA-256**: `21c3a5197ff33a3c95f45a1dfd557b2c4a71174c3b9f24f924588ea73008b680`
- **What I read**: abstract; introduction; the cross-sectional performance paragraphs (median vs 90th
  percentile Sharpe/alpha); footnotes 2–4 and 14; Section III's analysis of five HFT firms' regulatory
  filings (trading margins, fixed-cost shares); the persistence-regression paragraphs.
- **Tier**: T1 (the published article is peer-reviewed; this is the working-paper version of it — I
  read the working paper, so numbers are cited as read from this version).

## 4. `virtu_s1_2014.txt`
- **Document**: Virtu Financial, Inc. Form S-1 registration statement, filed with the SEC (2014).
- **URL fetched**: https://www.sec.gov/Archives/edgar/data/1592386/000104746914002070/a2218589zs-1.htm
- **SHA-256**: `90dd1c968dc6bfb90bf6d17caef398c948c6a7c87965be705e8376607a61c80b`
- **What I read**: I searched and read the passages containing "losing trading day" (four occurrences),
  the "Overview" business description, and the definition of "Adjusted Net Trading Income".
- **Tier**: T1 (SEC filing).

## 5. `makarov_schoar_crypto_arbitrage.txt`
- **Document**: Igor Makarov & Antoinette Schoar, "Trading and Arbitrage in Cryptocurrency Markets",
  preprint submitted to Elsevier dated 20 March 2019 (published JFE 135(2), 293–319, 2020;
  DOI 10.1016/j.jfineco.2019.07.001 confirmed via Crossref).
- **URL fetched**: https://personal.lse.ac.uk/makarov1/index_files/CryptocurrencyMarkets.pdf
- **SHA-256**: `c52308d7b4ff4332178dfa0485a0a17b0ba1a91a57912571259a3462e500da97`
- **What I read**: abstract; the full introduction (stylized facts 1–4 and the capital-controls
  explanation); the data section (Kaiko, exchange/region classification); Section 8.2 "Constraints to
  arbitrage" (blockchain fees, exchange fees, withdrawal fees, round-trip cost estimate, governance risk).
- **Tier**: T1 (peer-reviewed; author-hosted version of the accepted paper).
- **Note**: The LSE Research Online copy (eprints.lse.ac.uk / researchonline.lse.ac.uk) returned 403 to
  both curl and WebFetch; the author's own page served it.

## 6. `senate_psi_basket_options_2014_hearing.txt`
- **Document**: U.S. Senate Hearing 113-422, "Abuse of Structured Financial Products: Misusing Basket
  Options to Avoid Taxes and Leverage Limits", Permanent Subcommittee on Investigations, 22 July 2014.
- **URL fetched**: https://www.govinfo.gov/content/pkg/CHRG-113shrg89882/html/CHRG-113shrg89882.htm
- **SHA-256**: `ff6b1f1b81f4911ca560eefaf06258805f99e7226589f769d1175fbad5ef7811`
- **What I read**: Chairman Levin's and Senator McCain's opening statements (leverage ratios, order
  counts, profit and tax figures); Mr Silber's Renaissance testimony (barrier options, average holding
  periods, counterparty risk); the Levin/Malloy/Ramakrishna exchange on order counts and execution latency.
- **Tier**: T1 (Congressional hearing record).
- **Note**: The Subcommittee's separate 93-page staff REPORT PDF on hsgac.senate.gov returned 403 to
  both curl and WebFetch. I read the hearing record instead, which contains the same figures in the
  members' statements. See COULD_NOT_VERIFY.md.

## 7. `boehmer_revisit_barardehi_2024.txt`
- **Document**: David Ardia, Clément Aymard, Tolga Cenesizoglu, "Revisiting Boehmer et al. (2021):
  Recent Period, Alternative Method, Different Conclusions", arXiv:2403.17095v1, 25 March 2024.
- **URL fetched**: https://arxiv.org/pdf/2403.17095
- **SHA-256**: `6a364b5e70a47919d3f5daf5917d5e8df37d615148c3a395e94a3bc0d5d59b3d`
- **What I read**: abstract; introduction; Section 3.6 (long-short strategy returns) including
  footnote 7 which quotes BJZZ's own cost disclaimer verbatim; the Table 6 interpretation note; conclusion.
- **Tier**: T2 (working paper / preprint).
- **Note**: I did NOT read Boehmer, Jones, Zhang & Zhang (2021) itself — see COULD_NOT_VERIFY.md.
  All BJZZ numbers in the review are quoted *as reported by this replication paper*, and labelled so.

## 8. `polymarket_arbitrage_aft2025.txt`
- **Document**: Oriol Saguillo, Vahid Ghafouri, Lucianna Kiffer, Guillermo Suarez-Tangil,
  "Unravelling the Probabilistic Forest: Arbitrage in Prediction Markets", 7th Conference on Advances
  in Financial Technologies (AFT 2025), LIPIcs, DOI 10.4230/LIPIcs.AFT.2025.27.
- **URL fetched**: https://suarez-tangil.networks.imdea.org/papers/2025aft-arbitrage.pdf
- **SHA-256**: `8542c8fb06429e33822caff5e90ce48aa088ebec10b997c3e3d51ff53967a645`
- **What I read**: abstract; introduction; the arbitrage-type definitions (market rebalancing vs
  combinatorial); the methodology paragraph on bid grouping and the explicit statement that Polymarket
  charged no per-trade fee; Table 1 (top-10 accounts by profit and transaction count); Section 7.4;
  the concluding discussion.
- **Tier**: T1 (peer-reviewed conference proceedings; the paper thanks anonymous AFT reviewers).

## 9. `perpetual_futures_fundamentals.txt`
- **Document**: Songrun He, Asaf Manela, Omri Ross, Victor von Wachter, "Fundamentals of Perpetual
  Futures", arXiv:2212.06888v6, this draft July 2024 (posted 21 Aug 2024).
- **URL fetched**: https://arxiv.org/pdf/2212.06888
- **SHA-256**: `8faba72c04a0ec5c2d2b1a8e9d892f607e71891fd9cb43cc9cd18e076c82ce66`
- **What I read**: abstract; the introduction paragraphs describing the random-maturity arbitrage
  strategy and its Sharpe ratios by fee tier; Table 2 (sample descriptions) and Table 3 (fee tiers,
  with the explicit "typically an individual trader" labelling of the high-fee tier); the Table 12/13
  discussion of strategy returns over time including the post-2022 structural break.
- **Tier**: T2 (working paper / preprint; presented at Utah Winter Finance Conference 2024).

## 10. `bhardwaj_gorton_rouwenhorst_cta.txt`
- **Document**: Geetesh Bhardwaj, Gary B. Gorton, K. Geert Rouwenhorst, "Fooling Some of the People
  All of the Time: The Inefficient Performance and Persistence of Commodity Trading Advisors",
  Review of Financial Studies 27(11), 3099–3132 (2014). The PDF is the typeset RFS article.
- **URL fetched**: http://spinup-000d1a-wp-offload-media.s3.amazonaws.com/faculty/wp-content/uploads/sites/20/2020/12/Fooling-Some-of-the-People-All-of-the-Time-The-Inefficient-Performance-and-Persistence-of-Commodity-Trading-Advisors.pdf
- **SHA-256**: `569e721dbf79e14391fdfd7b90c21e736c20a5d6ef4fdde4d1a656f8f208328b`
- **What I read**: abstract; the introduction's statement of the bias corrections and the
  backfill/graveyard observation counts (footnote 4); the "why does the asset class keep growing"
  discussion; the survivorship/backfill figure captions.
- **Tier**: T1 (peer-reviewed).

## 11. `novy_marx_velikov_taxonomy.txt`
- **Document**: Robert Novy-Marx & Mihail Velikov, "A Taxonomy of Anomalies and their Trading Costs",
  NBER Working Paper 20721, December 2014 (published RFS 29(1), 104–147, 2016).
- **URL fetched**: https://www.nber.org/system/files/working_papers/w20721/w20721.pdf
- **SHA-256**: `3897a646ffec23670a0bdeeece2bfd3217c39769c9ff26abeba9087cce699982`
- **What I read**: abstract; the introduction's summary of the buy/hold-spread mitigation; the
  low/mid/high turnover grouping definitions; the high-turnover cost paragraph (">1% per month",
  "effective bid-ask spread alone eradicates the profits from all but two"); the Table 4 MVE discussion.
- **Tier**: T2 (I read the NBER working-paper version, which is explicitly not peer-reviewed; the
  same paper was later published in RFS, which I did not read).

## 12. `aqr_are_spacs_still_alive_2024.txt`
- **Document**: Rocky Bryant & Michael Schwert (AQR Arbitrage), "Are SPACs Still Alive?", October 2024.
- **URL fetched**: https://www.aqr.com/-/media/AQR/Documents/Insights/White-Papers/Are-SPACs-Still-Alive.pdf?sc_lang=en
- **SHA-256**: `1694524c9af85b12b29b37242210b3109b0f4eec51f87a3b30abde8f94350928`
- **What I read**: executive summary; the spread-to-trust definition (footnote 4); the post-crisis
  structural-changes list; the whole "AQR Arbitrage Approach to SPAC Investing" section; concluding thoughts.
- **Tier**: T2/T3 — an institutional white paper by a manager marketing the strategy it describes.
  Treated as a *self-interested* source; used only for the structural mechanics it states about its
  own access (IPO allocations, sponsor relationships), never as evidence of returns.

## 13. `gahng_ritter_zhang_spacs.txt`
- **Document**: Minmo Gahng, Jay R. Ritter, Donghang Zhang, "SPACs", version dated 23 February 2023
  (published Review of Financial Studies 36(9), 3463–3501, 2023; DOI 10.1093/rfs/hhad019 confirmed via OpenAlex).
- **URL fetched**: https://site.warrington.ufl.edu/ritter/files/SPACs.pdf
- **SHA-256**: `f2c0b5f700a0c873d5110aa7cbf647430e5a39280865c837d2376e3f1ecb3d57`
- **What I read**: abstract; the "optimal redemption strategy" definition; the SPAC-period return
  summary paragraphs; the Table 3 discussion (23.9% EW annualized, 23.6% at first-day close, 0.51%
  worst SPAC, liquidated-SPAC 2.0%) and footnote 19 (the 2021 cohort's low-single-digit returns).
- **Tier**: T1 (peer-reviewed; author-hosted version).

## 14. `crypto_maker_adverse_selection_2025.txt`
- **Document**: Jakob Albers, Mihai Cucuringu, Sam Howison, Alexander Y. Shestopaloff, "The Market
  Maker's Dilemma: Navigating the Fill Probability vs. Post-Fill Returns Trade-Off",
  arXiv:2502.18625v2, 23 November 2025.
- **URL fetched**: https://arxiv.org/pdf/2502.18625
- **SHA-256**: `7f96810a4f54eb41931cd18572a970fef5929f97d47c4a35d6bbb164fcc8831f`
- **What I read**: abstract; introduction; the "Unprofitability Principle" passage; the
  queue-position/adverse-selection discussion; the Contributions paragraph; Section 2 "Data
  Acquisition" (experiment dates, 232,897 orders, Binance fee tiers, tick size, "we assume the best
  possible trading fees").
- **Tier**: T2 (preprint; authors at Oxford / Oxford-Man Institute / QMUL).

## 15. `mev_cexdex_searcher_profitability_2025.txt`
- **Document**: Fei Wu, Danning Sui, Thomas Thiery, Mallesh Pai, "Measuring CEX-DEX Extracted Value
  and Searcher Profitability: The Darkest of the MEV Dark Forest", arXiv:2507.13023v3, 3 August 2025.
- **URL fetched**: https://arxiv.org/pdf/2507.13023
- **SHA-256**: `911517ea7d537a000df2b9168d5b4b30501aa172c5b57b2759e5e48c0b37692f`
- **What I read**: abstract; the introduction's statement of entry barriers and builder concentration;
  the contributions list; the searcher–builder integration section headers and the exclusive-searcher
  margin finding.
- **Tier**: T2 (preprint; authors affiliated with King's College London, Flashbots, Ethereum
  Foundation, Rice/Consensys/Paradigm — note the Flashbots and Paradigm affiliations are an interest
  in this market).

## 16. `hou_xue_zhang_replicating_anomalies.txt`
- **Document**: Kewei Hou, Chen Xue, Lu Zhang, "Replicating Anomalies", NBER Working Paper 23394, May 2017.
- **URL fetched**: https://www.nber.org/system/files/working_papers/w23394/w23394.pdf
- **SHA-256**: `f094a134e0073feeb295b2edb464dea2b9fbbdc96d01654ba46ef76c8a043160`
- **What I read**: abstract; the introduction's replication-success definition and headline counts;
  the "Why does our replication differ so much" microcap paragraph (incl. the Fama-French 2008
  3%-of-cap / 60%-of-count figures as HXZ report them).
- **Tier**: T2 (NBER working paper, explicitly not peer-reviewed; a later version was published in
  Review of Financial Studies, which I did not read).

---

## Documents I attempted and could not read
See `../COULD_NOT_VERIFY.md`.
