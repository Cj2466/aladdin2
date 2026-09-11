# SOURCES — micro-cap forced-flow sourcing, 2026-09-12

Every file below was fetched by me in this session with `fetch.sh` (curl, browser UA), saved
verbatim, SHA-256'd, and (for PDFs) converted to text with `pdftotext -layout`. The `.txt` beside
each `.pdf` is that conversion, not a summary. Nothing here was typed from memory.

| # | file | SHA-256 (of the fetched file) | source URL | what it is |
|---|---|---|---|---|
| 1 | `chang_hong_liskovich_2015_nber_w19290.pdf` | `3b531ddb0558153b977bf18803481c8c5b5b7e6b6559a4c94ade54fcbbe42321` | https://www.nber.org/system/files/working_papers/w19290/revisions/w19290.rev0.pdf | Chang, Hong & Liskovich, "Regression Discontinuity and the Price Effects of Stock Market Indexing", NBER WP 19290, Aug 2013 (published RFS 28(1) 212-246, 2015). Read: abstract, §4.3 (Russell 1000 cut-off), §4.4 (Russell 3000 cut-off), Tables 4, 5, 8. |
| 2 | `wardlaw_2020_repec_abstract.html` | `eeba51c97dea3e66af981c3e042f4f2e2c1ca86ef24ed1094207e8d0ed410c2f` | https://ideas.repec.org/a/bla/jfinan/v75y2020i6p3221-3243.html | Wardlaw, "Measuring Mutual Fund Flow Pressure as Shock to Stock Returns", JF 75(6) 3221-3243, Dec 2020 — **abstract only** (SSRN and Wiley both refused the fetch: SSRN HTTP 403). |
| 3 | `macey_ohara_pompilio_2004_wp.pdf` | `a760e3bd592d3b829a45bf58ce3de5b8cb40ceb9db78cf22ee0d0f892cfc2073` | https://users.nber.org/~confer/2004/mmf04/macey.pdf | Macey, O'Hara & Pompilio, "Down and Out in the Stock Market: The Law and Finance of the Delisting Process", July 2004 working paper (published as "...Law and Economics of the Delisting Process", JLE 51(4) 683-713, 2008). **Disclosed gap: this is the 2004 WP, not the 2008 JLE article; section/table numbers may be renumbered and the published title differs.** Read: abstract, §III, Table 6/7 discussion, footnote 45. |
| 4 | `edmans_goldstein_jiang_2012_jf.pdf` | `654c1e07dd7294462980ae6190893459977c9df46f3418b8d9fd0d82473939a3` | https://finance.wharton.upenn.edu/~itayg/Files/takeoverfeedback-published.pdf | Edmans, Goldstein & Jiang, "The Real Effects of Financial Markets: The Impact of Prices on Takeovers", JF 67(3) 933-971, 2012 — the origin of the MFFlow/FIT price-pressure measure Wardlaw critiques. |
| 5 | `residual_supply_arxiv_2605.30672.pdf` | `095fc836480c59cf5d809c26a2b6507fede282dd825925a18d4149777ff1ef95` | https://arxiv.org/pdf/2605.30672 | Ziyao Wang, "Residual Supply and the Price of Risk Absorption", arXiv:2605.30672v1 [q-fin.GN], 29 May 2026. **Unrefereed preprint, single author, Department of Mathematics and Statistics, Texas Tech.** Read: abstract, §3.2 (Eq. 34-36), §4.3-4.4, Tables 8 and 9. |
| 6 | `appel_gormley_keim_russell_rd_wharton.pdf` | `108042f2c0e82c0e40675449bfb717f3ec2b8efdebe7aa7c427043ba5286e9ce` | https://rodneywhitecenter.wharton.upenn.edu/wp-content/uploads/2018/11/04-18.Keim_.pdf | Appel, Gormley & Keim, "Identification using Russell 1000/2000 index assignments: A discussion of methodologies", 17 Oct 2018. Read: abstract, §2.1, §3.1-3.2. |
| 7 | `han_institutional_constraints_jfqa.pdf` | `65c6dfffcd36f9c618f370f088903275e312c110661df6b387e3272de4ea3bab` | https://www-2.rotman.utoronto.ca/facbios/file/JFQA_Han.pdf | Cao, Han & Wang, "Institutional Investment Constraints and Stock Prices" (JFQA). Read: abstract only — see COULD_NOT_VERIFY. |

## Sources re-used from earlier runs in this repo (fetched and hashed on 2026-09-11, not re-fetched today)

| file | what it supplies here |
|---|---|
| `../../candidate_sourcing_2026-09-11/sources/hou_xue_zhang_replicating_anomalies.txt` | HXZ's microcap cost verdict, quoted in the report |
| `../../candidate_sourcing_2026-09-11/sources/novy_marx_velikov_taxonomy_2014.txt` | NMV Table 13 net-of-spread returns by size bin |
| `../../candidate_sourcing_2026-09-11/sources/mclean_pontiff_2016.txt` | post-publication decay multiplier |
| `../../hunting_ground_review_2026-09-11/sources/gahng_ritter_zhang_spacs.txt` | SPAC redemption-floor mechanism |

## Helper
`fetch.sh <name> <url>` — curl with a browser UA, saves `<name>.pdf|.html`, prints size/MIME, prints
SHA-256, and runs `pdftotext -layout` for PDFs.
