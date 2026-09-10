"""Layer 2 (mechanism fidelity) and Layer 3 (regime conditionality) for the
four live-registration scorecard drafts, written from the source papers and
applied to the drafts in this directory.

    ./venv/bin/python data/research_runs/scorecard_drafts_2026-09-10/apply_layer_2_3_review.py

WHO AND HOW. Reviewer: the Fable 5.1 main session, 2026-09-10 — independent
of every build (2026-08-27 crypto, 2026-08-28 quality, 2026-09-02 short
interest, 2026-09-01 lazy_prices) and of each build's same-day verification
pass. Method: every construction choice below was taken from the BUILDER'S
OWN contemporaneous record (module docstring, pre-registration, registration
file), then each cited locus was re-read in the paper text and either
confirmed verbatim, corrected, or marked unverifiable. Nothing was
reconstructed from code: where the builder recorded no source for a choice,
the locus says so and names the builder's document instead. This is the
discipline tests/test_registration_scorecards.py's docstring demands.

THE DOCUMENTS ACTUALLY READ, so a later reader can check the same version.
None is committed (the owner has not decided on retaining paper texts, and
that decision has a copyright dimension); each is identified by SHA-256 of
the fetched PDF and of the text extracted from it with pypdf 6.16.2:

  BGLN  Ball, Gerakos, Linnainmaa & Nikolaev, working paper dated April 17, 2015,
        ivey.uwo.ca/media/3775325/gerakos.pdf, fetched 2026-09-10 12:07Z, 47 pp.
        pdf e5fad33f5ed194883e113b13dabd1b7ae7a2d8daa8ffdb5134c6ee9289f26ce0
        txt 5ded9237e4d1ec63f695e432e58dafef95bcde1d71e36c491cbfb53df66163aa
  CMN   Cohen, Malloy & Nguyen, NBER Working Paper 25084 (Sept 2018, rev. March 2019),
        nber.org/system/files/working_papers/w25084/w25084.pdf, 90 pp.
        pdf 75e86de47d2c754c8d8ae30818268f592c791ea048e3030746328239d41e7466
        txt 745994275f040ec69cba91e40a5a579e73417bece54d8e0636e62a7f195542e4
  FP    Frazzini & Pedersen, "Betting Against Beta", draft dated May 10, 2013,
        w4.stern.nyu.edu/facdir/lpederse/papers/BettingAgainstBeta.pdf, 80 pp.
        pdf 1ce429524fe9ee8b1831824a3b5ba1cc7e506ba01e27eec6e44005e68d4c2037
        txt 328a1d4bb9a3d8c237e7dbe534faccd9657854950dad3ca6e101ec9bf75aeea8
  LTW   Liu, Tsyvinski & Wu, NBER Working Paper 25882 (May 2019),
        nber.org/system/files/working_papers/w25882/w25882.pdf, 48 pp.
        pdf 01fa7e448623627078b43cc75ca70471caa1c436e48795f12704106392b486f2
        txt d6e7fe7fc82ac52ebb67e920f441bed6c6b955f48670be8020f2551e1a60cb33
  BHJ   Boehmer, Huszar & Jordan, JFE 96(1) 2010 — NOT OBTAINED. See that card.

Page numbers below are the papers' own printed page numbers where the text
carries them (CMN prints "Lazy Prices — Page N"; FP prints "Page N"; BGLN
prints a bare number at the foot of each page), otherwise the PDF page.

Only `layer_2_mechanism_fidelity`, `layer_3_regime_conditional`, the two
matching `gaps` entries, `draft_status` and `author` are touched. Layer 1,
layer 4, decision, verdict and power are left exactly as the drafts carry
them; the drafts stay in this directory, NOT in data/research_runs/scorecards/,
for the reason the README gives.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REVIEWED_AT = "2026-09-10"
REVIEWER = (
    "Fable 5.1 main session, 2026-09-10 — independent of the build and of its same-day "
    "verification pass; every locus re-read in the paper text rather than taken from the module"
)

# ---------------------------------------------------------------------------
# quality_cbop / cbop_ls_h63
# ---------------------------------------------------------------------------
QUALITY_CBOP_L2 = {
    "source_citation": (
        "Ball, Gerakos, Linnainmaa & Nikolaev, 'Accruals, cash flows, and operating profitability "
        "in the cross section of stock returns', Journal of Financial Economics 121(1), 2016, "
        "pp. 28-45. TEXT IN HAND: the April 17, 2015 working-paper PDF (ivey.uwo.ca, 47 pp., "
        "sha256 e5fad33f…26ce0 — see this script's docstring); the published JFE version was not "
        "obtained (paywalled), exactly as the module records. Lineage cited by the module, not "
        "re-read for this pass: Novy-Marx, JFE 108(1), 2013."
    ),
    "source_text_obtained": True,
    "construction_choices": [
        {
            "choice": (
                "Operating profitability = REVT - COGS - (XSGA - XRD); cash-based operating "
                "profitability = OP - dRECT - dINVT - dXPP + d(DRC+DRLT) + dAP + dXACC; every term "
                "deflated by year t-1 total assets"
            ),
            "source_locus": (
                "BGLN WP Appendix, pp. 24-26 ('All are deflated by the book value of total assets "
                "in year t-1'; both formula blocks verbatim), restated in section 4.1 p. 9. The "
                "module docstring section 1(a) quotes the same Appendix; re-verified word for word "
                "2026-09-10."
            ),
        },
        {
            "choice": (
                "Missing balance-sheet accounts treated as zero — applied by the builder to CHANGE "
                "terms only, and only when the account is missing at both ends of the year-over-year "
                "window; a one-sided missing is counted as zero change and tallied"
            ),
            "source_locus": (
                "BGLN WP Appendix p. 26: 'All changes are computed on year-to-year basis. Instances "
                "where balance sheet accounts have missing values are replaced with zero values for "
                "the computation of Cash-based operating profitability and accruals.' The both-ends "
                "narrowing is the builder's interpretation, module docstring section 2, second "
                "bullet — recorded under deviations."
            ),
        },
        {
            "choice": (
                "XSGA - XRD implemented as the us-gaap SellingGeneralAndAdministrativeExpense tag "
                "taken directly, with no R&D subtraction"
            ),
            "source_locus": (
                "BGLN WP Appendix p. 25: the subtraction exists 'to undo the adjustment that "
                "Standard & Poor's makes to firms' accounting statements', i.e. to recover the "
                "reported figure, which the XBRL tag already is. Builder's reasoning: module "
                "docstring section 2, first bullet."
            ),
        },
        {
            "choice": (
                "Direction high CbOP long / low CbOP short; decile legs (QUALITY_RANK_FRACTION = "
                "0.1); portfolio long_short; magnitude leg weighting (the harness default)"
            ),
            "source_locus": (
                "Deciles and direction: BGLN WP Table 4 note p. 44 ('We sort stocks into deciles "
                "based on NYSE breakpoints at the end of each June and hold the portfolios for the "
                "following year') and section 4.2 p. 14 (high-minus-low quintile (decile) alpha 72 "
                "(90) bp/month, t = 8.21 (8.5)). Magnitude weighting: cross_sectional.py "
                "CrossSectionalSpec.leg_weighting default — NOT from the paper, see deviations."
            ),
        },
        {
            "choice": (
                "Point-in-time availability at each fact's SEC `filed` date, forward-filled, bounded "
                "by FUNDAMENTAL_MAX_STALENESS_DAYS; earliest-filed value wins so restatements never "
                "rewrite history"
            ),
            "source_locus": (
                "Builder's own rule, module docstring section 2 'POINT-IN-TIME CONSTRUCTION'. The "
                "paper's rule differs: BGLN WP section 3 p. 7, 'lag annual accounting information by "
                "the standard six months … public by the end of the following June' — see deviations."
            ),
        },
        {
            "choice": "Holding periods {63, 126, 252}; the registered spec reforms every 63 trading days",
            "source_locus": (
                "252 = the paper's annual end-of-June rebalance (BGLN WP section 3 p. 6, 'we "
                "rebalance the portfolios annually at the end of June'; Table 4 note). 63 and 126 are "
                "the builder's, module docstring section 4 (staggered fiscal calendars) — see "
                "deviations."
            ),
        },
        {
            "choice": (
                "Financial firms absent from the CbOP cross-section because they carry no COGS-shaped "
                "XBRL tag — an incidental exclusion that coincides with the paper's explicit one"
            ),
            "source_locus": (
                "BGLN WP section 3 p. 7: 'We exclude financial firms, which are defined as firms with "
                "one-digit standard industrial classification codes of six.' Module docstring "
                "section 3 records the exclusion as tag-shaped, not imposed."
            ),
        },
        {
            "choice": (
                "Universe: a seeded random 200-ticker sample of the point-in-time S&P 500 union, "
                "~68 CbOP-ranked names per formation, decile legs of ~7"
            ),
            "source_locus": (
                "Builder's constraint (SEC fair-access rate), module docstring section 3. Paper: all "
                "NYSE/Amex/NASDAQ ordinary common shares, BGLN WP section 3 pp. 6-7 — see deviations."
            ),
        },
        {
            "choice": (
                "The Table 2 horse race is the stated reason CbOP rather than plain operating "
                "profitability is the family"
            ),
            "source_locus": (
                "BGLN WP section 4.1 pp. 9-10, Panel A (All-but-microcaps): t = 8.97 (OP, column 1), "
                "9.84 (CbOP, column 5), and in column 7 OP falls to 1.19 while CbOP holds 5.83. All "
                "four numbers verified. The paper's own like-for-like comparison is column 2, "
                "t = 6.97, on the sample with non-missing CbOP — see findings."
            ),
        },
    ],
    "deviations": [
        {
            "deviation": (
                "The paper's six-month accounting lag is replaced by actual filing-date availability"
            ),
            "reason": (
                "Each 10-K's real SEC filed date, typically 2-3 months after fiscal year-end, is a "
                "genuine availability date, so this is not look-ahead — but it uses the signal "
                "EARLIER than the paper does (section 3 p. 7), and is a construction the paper did "
                "not test. A conservative replication would delay to the paper's convention."
            ),
        },
        {
            "deviation": (
                "Quarterly (63-day) reformation for the registered spec versus the paper's annual "
                "end-of-June rebalance"
            ),
            "reason": (
                "Builder's staggered-fiscal-year argument, module docstring section 4. Consequence: "
                "turnover and the mix of information ages differ from anything Table 4 reports."
            ),
        },
        {
            "deviation": (
                "Magnitude-weighted decile legs on a ~68-name sample's own breakpoints versus the "
                "paper's value-weighted deciles on NYSE breakpoints over the whole market"
            ),
            "reason": (
                "Harness default; no share-count pipeline existed at build. The paper's headline "
                "sorts are value-weighted (Table 4 note), so this spec's result is comparable to the "
                "paper in neither weighting nor breadth."
            ),
        },
        {
            "deviation": "The missing-to-zero rule is narrowed to changes missing at both ends",
            "reason": (
                "Builder's argument (module docstring section 2): the naive reading fabricates a "
                "whole-balance 'change' whenever an XBRL tag flickers. A defensible tightening, "
                "disclosed; the paper's rule as written is broader."
            ),
        },
        {
            "deviation": (
                "Compustat items are mapped to XBRL tags through measured fallback tiers "
                "(edgar_xbrl_provider), including taking XSGA - XRD as the reported SG&A tag"
            ),
            "reason": (
                "This project has no Compustat. The mapping is the builder's and cannot be checked "
                "against the paper, which speaks only in Compustat items."
            ),
        },
        {
            "deviation": (
                "Sample 2015-2026 S&P 500 members versus the paper's July 1963 - December 2013 "
                "across all exchanges"
            ),
            "reason": (
                "Post-publication window on the most-followed 500 names; the module's own prior. "
                "The paper's own attenuation finding is in-sample from ~2004, not post-publication "
                "— see findings."
            ),
        },
    ],
    "independent_reviewer": REVIEWER,
    "independent_reviewer_signed_off_at": REVIEWED_AT,
    "independent_reviewer_findings": (
        "(1) Both formula blocks, the missing-to-zero sentence, the deflation sentence and all "
        "four Table 2 t-statistics quoted by the module were located in the working paper and "
        "match verbatim; nothing was found misquoted. "
        "(2) One imprecision: the module sets CbOP's t = 9.84 against OP's 8.97, which are "
        "columns 1 and 5 on different samples; the paper's like-for-like comparison is column 2, "
        "t = 6.97 (section 4.1 p. 9). The imprecision UNDERSTATES CbOP's advantage, so it is not "
        "flattering. "
        "(3) One mislabel in quality_forward_registration.py's case-against: 'that paper itself "
        "reports post-publication attenuation'. What the paper reports (section 4.1 pp. 11-12) is "
        "that 'starting around 2004, the t-values on all three strategies attenuate toward zero' "
        "INSIDE its own 1963-2013 sample — years before its 2016 publication, and shared with "
        "momentum. In-sample attenuation, not post-publication. "
        "(4) The financials exclusion this family reaches by accident of the data (no COGS tag) is "
        "the paper's explicit rule (SIC 6), so on that point the replication is closer to the "
        "source than the module claims. "
        "(5) What the registered spec actually tests — quarterly reformation, filing-date "
        "availability, magnitude-weighted deciles on ~68 names, 2015-2026 — is not a construction "
        "the paper reports. A positive forward result would be evidence about THIS construction, "
        "not a replication of Table 4. "
        "(6) Source text in hand is the 2015 working paper, not the published article; the module "
        "says the same."
    ),
}

QUALITY_CBOP_L3 = {
    "source_claim_type": "unconditional",
    "claim_evidence": (
        "BGLN state a cross-sectional profitability premium with no regime qualifier anywhere in "
        "the working paper: the abstract, the Fama-MacBeth regressions of section 4.1 and the "
        "portfolio sorts of section 4.2 all run over the full July 1963 - December 2013 sample. The "
        "only time variation discussed is the attenuation of all three strategies' t-values from "
        "about 2004 (section 4.1 pp. 11-12), presented as a structural shift, not as a conditioning "
        "claim. The full text was searched for 'regime', 'recession', 'crisis', 'bad times', 'good "
        "times' and 'state of the': no occurrence."
    ),
    "regime_definition_rule": None,
    "regime_rule_pre_declared_at": None,
    "dsr_in_regime": None,
    "dsr_out_of_regime": None,
    "not_applicable_reason": (
        "Unconditional source claim, so no regime rule was pre-declared and none is computed; "
        "computing one now would be the post-hoc conditioning this layer exists to make visible. "
        "The 2015-2026 window's regime coverage is a layer 4 disclosure, still unfilled."
    ),
}

# ---------------------------------------------------------------------------
# short_interest_ratio / si_ratio_hedged_h21
# ---------------------------------------------------------------------------
SHORT_INTEREST_L2 = {
    "source_citation": (
        "Boehmer, Huszar & Jordan, 'The good news in short interest', Journal of Financial "
        "Economics 96(1), 2010, pp. 80-97. FULL TEXT NOT OBTAINED — not at build (2026-09-02: "
        "SSRN, ScienceDirect, ResearchGate, SMU and NUS repositories all refused) and not at this "
        "review (2026-09-10: SMU ink.library and USU digitalcommons return bot-challenge pages to a "
        "plain fetch; Semantic Scholar's open-access lookup returned nothing). Bibliographic record "
        "and abstract verified against RePEc at build; the abstract is quoted verbatim in the "
        "module docstring section 1."
    ),
    "source_text_obtained": False,
    "construction_choices": [
        {
            "choice": "Ranking measure: short interest divided by shares outstanding, a level",
            "source_locus": (
                "SECOND-HAND. Module docstring section 1(a): a later paper by two of the three "
                "authors (Boehmer, Huszar, Wang & Zhang) and a 2022 citing paper; one dissenting "
                "citation implying days-to-cover is kept on the record. Not verified against BHJ's "
                "own text."
            ),
        },
        {
            "choice": (
                "Long the low-short-interest tail at the 5th percentile "
                "(SHORT_INTEREST_RANK_FRACTION = 0.05), fixed in advance and not searched"
            ),
            "source_locus": (
                "SECOND-HAND for the cutoffs: section 1(b), two replications report 1st/5th/10th "
                "percentile low-side portfolios. The choice of the 5th is the builder's, "
                "pre-registration section 4 (the 1st is ~5 names on this universe; the 10th is not "
                "the tail the paper emphasises)."
            ),
        },
        {
            "choice": (
                "Portfolio long_universe_hedged: long the tail, short the equal-weighted eligible "
                "universe, so the long leg's abnormal return is isolated"
            ),
            "source_locus": (
                "Builder's reading of the abstract's long-side claim (abstract verified at RePEc: "
                "'relatively heavily traded stocks with low short interest experience both "
                "statistically and economically significant positive abnormal returns'); "
                "pre-registration section 4 'WHY BOTH PORTFOLIOS'. The paper's own benchmark is "
                "Carhart four-factor alpha (second-hand, three sources) — not a universe hedge."
            ),
        },
        {
            "choice": "Monthly reformation (21 trading days) for the registered spec",
            "source_locus": "SECOND-HAND: module docstring section 1(c), two sources agree on a monthly rebalance.",
        },
        {
            "choice": (
                "Universe: the full point-in-time S&P 500 union, masked to the common cross-section "
                "where both a ratio and a days-to-cover are computable; the paper's 'relatively "
                "heavily traded' conditioning is NOT replicated and the universe restriction stands "
                "in for it"
            ),
            "source_locus": (
                "Pre-registration section 4, 'THE HEAVILY TRADED CONDITIONING IS NOT REPLICATED' — "
                "the builder's disclosed approximation. Module docstring section 1(e): no source "
                "found states how BHJ operationalise trading activity."
            ),
        },
        {
            "choice": (
                "Point-in-time visibility: short interest at settlement + 14 calendar days; share "
                "counts at cover-page end + 90 calendar days; FINRA split-flagged cycles refused"
            ),
            "source_locus": (
                "Builder's own rules, module docstring section 3, from FINRA's published schedule "
                "and a measured distribution of 7,539 (end, filed) pairs. The design precedent "
                "quoted is Bradford Jordan's later work, not BHJ."
            ),
        },
        {
            "choice": (
                "Magnitude leg weighting; 5 bp one-way cost; financing 44.7705 bp/yr on gross, "
                "adopted 2026-09-06 on the owner's sign-off"
            ),
            "source_locus": (
                "Harness default and project cost policy, module docstring section 4. The paper "
                "reports equal- and value-weighted portfolios (second-hand)."
            ),
        },
    ],
    "deviations": [
        {
            "deviation": "The paper's 'relatively heavily traded' conditioning is not replicated",
            "reason": (
                "Its operationalisation could not be found in any source; substituting a universe "
                "restriction is disclosed as weak in the pre-registration. This is the single "
                "largest fidelity gap and it sits on the paper's headline conditional."
            ),
        },
        {
            "deviation": (
                "~400 large caps over 2018-2026 versus NYSE/AMEX/NASDAQ, ~4,400 stocks per month, "
                "1988-2005"
            ),
            "reason": (
                "The sub-$5 population is excluded by construction; one secondary source attributes "
                "the paper's effect to it (module docstring section 2)."
            ),
        },
        {
            "deviation": "Benchmark is an equal-weighted universe hedge, not four-factor alpha",
            "reason": "The harness's live path carries no factor model.",
        },
        {
            "deviation": "Days-to-cover added as a second normaliser axis",
            "reason": (
                "Pre-declared by the builder on a replication's finding that the two normalisers "
                "disagree (ZHAW thesis); not the paper's measure, and the registered spec "
                "deliberately does not use it."
            ),
        },
        {
            "deviation": "Rank tail fixed at the 5th percentile of the paper's three published cutoffs",
            "reason": "Pre-registration section 4; searching all three would be a selection the sample cannot afford.",
        },
    ],
    "independent_reviewer": REVIEWER,
    "independent_reviewer_signed_off_at": REVIEWED_AT,
    "independent_reviewer_findings": (
        "(1) The full text is unavailable, so every locus above is second-hand and this card "
        "cannot certify a single construction choice against the source. The honest status of "
        "layer 2 for this family is UNVERIFIABLE, and it stays so until someone with journal "
        "access reads pp. 80-97 — an institutional-access or purchase decision, logged for the "
        "owner rather than worked around. "
        "(2) What can be said: the builder's second-hand record is unusually careful (a source "
        "count per claim, the one dissent kept), the registered spec is the most paper-conformant "
        "cell of the grid on the three axes that could be sourced, and the one design call the "
        "builder flagged for human review (the missing conditioning) is exactly the one this "
        "reviewer would flag. "
        "(3) Retrieval attempts made in this pass, with their outcomes, are in "
        "LAYER_2_REVIEW_2026-09-10.md beside this script."
    ),
}

SHORT_INTEREST_L3 = {
    "source_claim_type": "unconditional",
    "claim_evidence": (
        "From the abstract only (the full text is unavailable): the claim is conditioned "
        "CROSS-SECTIONALLY — 'relatively heavily traded stocks with low short interest' — but "
        "not on any time regime or market state, which is what this layer asks about. A "
        "secondary source (a 2016 dissertation, module docstring section 2) attributes the long "
        "side to January; that is a calendar effect measured here as a pre-declared diagnostic "
        "(2.05x for the registered spec), not a regime claim made by the source."
    ),
    "regime_definition_rule": None,
    "regime_rule_pre_declared_at": None,
    "dsr_in_regime": None,
    "dsr_out_of_regime": None,
    "not_applicable_reason": (
        "No regime-conditional claim in the source as far as it can be read; no regime rule was "
        "pre-declared and none is computed. The cross-sectional conditioning the source DOES make "
        "is unreplicated and is recorded as a layer 2 deviation, not a layer 3 regime."
    ),
}

# ---------------------------------------------------------------------------
# lazy_prices_jaccard_full / lazy_jaccard_full_h126_ivol
# ---------------------------------------------------------------------------
LAZY_PRICES_L2 = {
    "source_citation": (
        "Cohen, Malloy & Nguyen, 'Lazy Prices', Journal of Finance 75(3), 2020, pp. 1371-1415, "
        "doi:10.1111/jofi.12885. TEXT IN HAND: NBER Working Paper 25084 (Sept 2018, rev. March "
        "2019), 90 pp., sha256 75e86de4…7466 — the same document the builder extracted in full on "
        "2026-09-01; the published JF text was not obtained (Wiley 403 at build)."
    ),
    "source_text_obtained": True,
    "construction_choices": [
        {
            "choice": (
                "Signal = similarity between a firm's 10-K and its own prior-year 10-K; high "
                "similarity (non-changers) long, low similarity (changers) short"
            ),
            "source_locus": (
                "CMN w25084 section III.A p. 16 and footnote 18 ('the most comparable report for a "
                "given 10-K is the prior year 10-K'); Q5 long / Q1 short, p. 17."
            ),
        },
        {
            "choice": (
                "Jaccard similarity on term SETS for the registered spec; cosine on raw term-count "
                "vectors for sibling specs; no TF-IDF"
            ),
            "source_locus": (
                "CMN section II pp. 12-13: cosine on term-frequency vectors of raw counts; Jaccard is "
                "'the size of the intersection divided by the size of the union of the two term "
                "frequency sets … the Jaccard measure is binary'. No TF-IDF anywhere in the paper's "
                "definitions — the builder's refusal of TF-IDF (pre-registration section 4) is "
                "consistent with the source."
            ),
        },
        {
            "choice": "Quintile legs (LAZY_PRICES_RANK_FRACTION = 0.20)",
            "source_locus": (
                "CMN section III.A p. 16: 'we compute quintiles each month based on the prior "
                "month's distribution of similarity scores across all stocks'."
            ),
        },
        {
            "choice": (
                "Whole-document scope for the registered spec; risk_factors and mda as sibling "
                "scopes with a pre-registered ordering risk_factors > full > mda"
            ),
            "source_locus": (
                "Whole document: Table II is computed on the extracted main 10-K/10-Q text (section "
                "II p. 11). Sections: section IV p. 25, MD&A 'ranging between 11-22 basis [points] "
                "per month' and smaller than Legal Proceedings, Item 7a and Risk Factors; "
                "introduction p. 4, Risk Factors 'even more informative', 188 bp/month, t = 2.76."
            ),
        },
        {
            "choice": (
                "Point-in-time availability from EDGAR acceptance datetime, shifted to the next day "
                "at or after 16:00 ET; forward-filled step frame bounded by 455 calendar days"
            ),
            "source_locus": (
                "Builder's rule, pre-registration section 5. Paper: 'Stocks enter the portfolio in "
                "the month after the public release of one of their reports' (section III.A p. 16) "
                "— a coarser, next-calendar-month lag; the family's is finer and never earlier than "
                "real availability."
            ),
        },
        {
            "choice": "10-K only; 10-K/A and 10-Q/A excluded; same-form pairing enforced",
            "source_locus": (
                "Paper uses 10-K AND 10-Q (section III.A p. 16). Footnote 18 and Appendix Table A-13: "
                "restricting to 10-K year-on-year changes gives results 'similar' to Table II — the "
                "family's restriction sits inside the paper's robustness, not its base case."
            ),
        },
        {
            "choice": (
                "Tokenisation: lowercase; tokens are runs of >= 2 ASCII letters; digits dropped; a "
                "fixed English stopword list REMOVED"
            ),
            "source_locus": (
                "Pre-registration section 4, frozen on the section 3.5 measurement. Paper base case "
                "INCLUDES stop words: section V p. 30, 'We confirm that our results are not affected "
                "by including so-called stop words … when we remove stop words … our main portfolio "
                "results are even larger' (Appendix Table A-14). On numbers the paper removes tables "
                "with > 15% numeric content (section II p. 11) but does not say numeric tokens are "
                "dropped. See deviations."
            ),
        },
        {
            "choice": "Holding 126 trading days (~6 months) for the registered spec; siblings 21 and 63",
            "source_locus": (
                "Paper: 'firms are held in the portfolio for 3 months. Portfolios are rebalanced "
                "monthly' (section III.A p. 16); returns 'continue to accrue out to 18 months, and do "
                "not reverse' (introduction p. 3). 126 is inside the accrual horizon but is not the "
                "paper's tested hold."
            ),
        },
        {
            "choice": "Inverse-vol leg weighting for the registered spec, equal for siblings; long_short",
            "source_locus": (
                "Builder's choice, pre-registration section 6 axis D4 (no share-count pipeline). "
                "Paper headline is value-weighted: 34-58 bp/month, up to 7%/yr, t = 3.59 (p. 3); "
                "Table II Panel A equal-weighted 18-45 bp (p. 17)."
            ),
        },
        {
            "choice": "Sim_MinEdit and Sim_Simple not implemented",
            "source_locus": (
                "Paper section II pp. 13-14 and Appendix: MinEdit is minimum edit distance; "
                "Sim_Simple uses 'Track Changes in Microsoft Word or the function diff in Unix/Linux' "
                "normalised by average document size. Declared deviation, pre-registration section 4 "
                "— the module's paraphrase of Sim_Simple is accurate."
            ),
        },
    ],
    "deviations": [
        {
            "deviation": "Stop words are removed; the paper's base case keeps them",
            "reason": (
                "Frozen by the builder on a measurement (whole-document cosine spread widens ~11x "
                "without them). The paper reports removal as a robustness check that makes its "
                "results 'even larger' (Appendix A-14), so the choice is the paper's stronger "
                "variant, not its base construction. Disclosed as such."
            ),
        },
        {
            "deviation": "Numeric tokens dropped",
            "reason": "Builder's reasoning (the hypothesis is about language); the paper does not state this step.",
        },
        {
            "deviation": "10-K only versus 10-K and 10-Q",
            "reason": "Footprint (pre-registration); inside the paper's Appendix A-13 robustness.",
        },
        {
            "deviation": "Six-month hold versus a three-month hold rebalanced monthly",
            "reason": "Pre-declared grid axis D3; the paper's accrual horizon reaches 18 months but its tested hold is 3.",
        },
        {
            "deviation": "Inverse-vol / equal leg weighting versus the value-weighted headline",
            "reason": "No point-in-time market-cap pipeline at build.",
        },
        {
            "deviation": "S&P 500 members 2015-2026 versus the universe of all U.S. filers 1995-2014",
            "reason": "The module's own 'honest prior is weak' section names this as the largest mismatch.",
        },
        {
            "deviation": "Sim_MinEdit and Sim_Simple absent",
            "reason": "Quadratic cost and a non-reproducible primitive respectively; declared in advance.",
        },
        {
            "deviation": "Availability rule finer than the paper's next-month entry",
            "reason": "Uses the real acceptance timestamp; never earlier than availability, but a different lag structure.",
        },
    ],
    "independent_reviewer": REVIEWER,
    "independent_reviewer_signed_off_at": REVIEWED_AT,
    "independent_reviewer_findings": (
        "(1) Every quotation in the module and pre-registration was located in the NBER text and "
        "matches: the 34-58 bp / 7% / t = 3.59 headline; the MD&A 11-22 bp range; the Risk Factors "
        "188 bp (t = 2.76); 'economically and statistically zero announcement day return'; "
        "'continue to accrue out to 18 months, and do not reverse'; the four measures; 1995-2014. "
        "The builder's correction of the 22%/yr briefing figure is exactly right. "
        "(2) One base-case mismatch the pre-registration does not present as one: the paper's main "
        "results include stop words and treat removal as robustness (Appendix A-14); the family's "
        "frozen tokenisation removes them. Recorded as a deviation above. "
        "(3) The paper's Figure 7 (p. 18) puts the return in the SHORT leg: 'any positive alpha on "
        "the Q5 long side quickly reverts to zero, while the negative alpha persists and increases "
        "up to 6 months out'. The registered spec is long_short at a now-adopted 48.16 bp/yr "
        "borrow (2026-09-06); this family's economics rest on the leg that is expensive to hold, "
        "which layer 4 must price explicitly. "
        "(4) The registration file's own 2026-09-03 correction found whole-document Jaccard is "
        "bounded by a vocabulary-size ceiling explaining R^2 ~ 0.49-0.52 of its variance and "
        "sharing 49.0% of the short leg's names; the ceiling alone does not reproduce the Sharpe "
        "(+0.19 vs +0.57), but orthogonalising it costs 22% of the Sharpe and drops DSR to 0.5703. "
        "The paper has no analogue of this diagnostic; it is a real, disclosed fragility of THIS "
        "construction and belongs on the card. "
        "(5) The registered spec's DSR disagrees across run_tags (0.7540 canonical vs 0.8639 on a "
        "later cost-model rerun) — carried from the draft's preservation note, unresolved here."
    ),
}

LAZY_PRICES_L3 = {
    "source_claim_type": "unconditional",
    "claim_evidence": (
        "CMN state the effect across 'the entire cross-section of U.S. publicly traded firms from "
        "1995 to 2014' (introduction p. 3) and section III.C reports it is 'not concentrated in "
        "just a few quarters or years' (p. 17-18). The full text was searched for 'regime', "
        "'recession' and 'market state': no occurrence. The claim is unconditional."
    ),
    "regime_definition_rule": None,
    "regime_rule_pre_declared_at": None,
    "dsr_in_regime": None,
    "dsr_out_of_regime": None,
    "not_applicable_reason": (
        "Unconditional source claim; no regime rule was pre-declared and none is computed. "
        "Regime coverage of the 2015-2026 window is a layer 4 disclosure, still unfilled."
    ),
}

# ---------------------------------------------------------------------------
# cross_sectional_crypto / xc_btcbeta_l180_h180
# ---------------------------------------------------------------------------
CRYPTO_L2 = {
    "source_citation": (
        "Frazzini & Pedersen, 'Betting Against Beta', Journal of Financial Economics, 2014. TEXT "
        "IN HAND: the May 10, 2013 draft PDF (w4.stern.nyu.edu, 80 pp., sha256 1ce42952…2037). "
        "Cited alongside by the module and registration: Liu, Tsyvinski & Wu, 'Common Risk Factors "
        "in Cryptocurrency', Journal of Finance, 2022 — TEXT IN HAND as NBER Working Paper 25882 "
        "(May 2019, 48 pp., sha256 01fa7e44…86f2). Neither published version was obtained. The "
        "module's other citations (Jegadeesh-Titman, Liu-Tsyvinski RFS 2021, De Bondt-Thaler, "
        "AMP 2013, AHXZ 2006, Blitz-van Vliet) belong to the family's other four mechanisms and "
        "were not re-read for this card."
    ),
    "source_text_obtained": True,
    "construction_choices": [
        {
            "choice": (
                "Signal = negated OLS beta of each coin's daily return on BTC-USD's over a trailing "
                "180-day window (registered spec; siblings 90 and 365): pairwise-complete covariance "
                "over BTC variance, a minimum-observations floor, low beta scores high and goes long"
            ),
            "source_locus": (
                "cross_sectional_crypto.py signal function and its docstring; module docstring "
                "'FAMILY SIZE' section. FP section III 'Estimating Ex-ante Betas' pp. 16-17, "
                "eq. (14)-(15), is a DIFFERENT estimator: beta = rho * sigma_i / sigma_m with a "
                "1-year volatility window, a 5-year correlation window on overlapping 3-day log "
                "returns, and shrinkage w = 0.6 toward 1 — see deviations."
            ),
        },
        {
            "choice": "Market = BTC-USD, itself a ranked member of the cross-section",
            "source_locus": (
                "Builder's choice: signal docstring ('BTC is the market proxy throughout the crypto "
                "factor literature') and the registration rationale ('BTC as market proxy per Liu, "
                "Tsyvinski & Wu 2022'). LTW w25882 section 2 p. 7 defines the market return as 'the "
                "value-weighted return of all the underlying available coins' — NOT Bitcoin. FP "
                "section III p. 18: betas are computed 'with respect to asset-class-specific market "
                "portfolios'. See findings."
            ),
        },
        {
            "choice": (
                "Quintile legs (CRYPTO_RANK_FRACTION = 0.2), long_short, inverse-vol leg weighting, "
                "dollar-neutral, no beta-neutral levering"
            ),
            "source_locus": (
                "Module docstring 'FAMILY SIZE' section — builder's choices. FP section III pp. 18-19, "
                "eq. (16)-(17): a MEDIAN split, rank-weighted legs, and both legs 'rescaled to have a "
                "beta of one at portfolio formation' so the factor is zero-beta — see deviations."
            ),
        },
        {
            "choice": "Hold 180 calendar days; reform at hold end",
            "source_locus": (
                "Module docstring 'COSTS' section (the 90-day floor is a cost decision). FP p. 19: "
                "'The portfolios are rebalanced every calendar month' — see deviations."
            ),
        },
        {
            "choice": (
                "Eligibility: trailing 90-day median dollar volume >= $25M and stale-print fraction "
                "<= 0.20, from prior rows only; dead coins retained on the dates they traded"
            ),
            "source_locus": (
                "Module docstring 'POINT-IN-TIME ELIGIBILITY' — builder's rule. LTW section 2 p. 7 "
                "filter is market capitalisation above one million dollars — a different gate."
            ),
        },
        {
            "choice": (
                "365-row year; 30 bp one-way cost; 800 bp/yr short borrow charged as 400 on gross; "
                "no perpetual-funding credit"
            ),
            "source_locus": (
                "Module docstring 'THE 365-DAY YEAR' and 'COSTS' sections — builder's disclosed "
                "assumptions, not sourced from either paper."
            ),
        },
    ],
    "deviations": [
        {
            "deviation": (
                "Beta estimator: plain OLS over 180 daily returns versus FP's rho * sigma ratio with a "
                "1-year volatility window, a 5-year correlation window and w = 0.6 shrinkage"
            ),
            "reason": (
                "Builder's simplicity. FP p. 17 note that common shrinkage 'does not change the "
                "ranks', so that part is rank-neutral; the separate volatility/correlation windows "
                "are not, and no crypto history is long enough for a 5-year correlation window."
            ),
        },
        {
            "deviation": (
                "Quintile tails versus a median split; inverse-vol versus rank weights; "
                "dollar-neutral versus beta-neutral by levering"
            ),
            "reason": (
                "Harness conventions (module docstring). Consequence: FP's BAB is zero-beta BY "
                "CONSTRUCTION; this spec's ex-post BTC beta of 0.0572 "
                "(bab_independent_reverify_2026-09-04) is measured, not enforced."
            ),
        },
        {
            "deviation": "180-day hold versus monthly rebalancing",
            "reason": "The 30 bp one-way cost arithmetic in the module's 'COSTS' section.",
        },
        {
            "deviation": (
                "Market proxy is BTC rather than an asset-class market portfolio (FP) or a "
                "value-weighted coin index (LTW)"
            ),
            "reason": (
                "Builder's stated wish to keep the equal-weighted basket as an INDEPENDENT confound "
                "factor for the audit regression (signal docstring). Defensible — BTC dominates a "
                "value-weighted index — but it is the builder's choice and the attribution to LTW is "
                "wrong; see findings."
            ),
        },
        {
            "deviation": "The mechanism is transplanted to an asset class the source does not cover",
            "reason": (
                "FP's text was searched for 'crypto' and 'Bitcoin': no occurrence. Their evidence is "
                "U.S. and international equities, Treasuries, credit and futures."
            ),
        },
    ],
    "independent_reviewer": REVIEWER,
    "independent_reviewer_signed_off_at": REVIEWED_AT,
    "independent_reviewer_findings": (
        "(1) CITATION ERROR. 'BTC as the market proxy per Liu, Tsyvinski & Wu (2022)' — in the "
        "registration rationale, the draft's provenance field and the signal docstring — is "
        "incorrect. LTW's market factor CMKT is the value-weighted return of all coins (w25882 "
        "section 2 p. 7), and the paper contrasts it with Bitcoin's own return on the same page "
        "(index 1.3%/week versus Bitcoin 1.2%/week). Bitcoin enters LTW only as an alternative "
        "SHORT leg in a robustness check (p. 5). Using BTC is a defensible proxy but it is the "
        "builder's choice and must be cited as such. "
        "(2) LTW's own evidence on this mechanism is NEGATIVE, and it is recorded nowhere in the "
        "module or registration: among their ten volatility-group factors, beta quintile sorts do "
        "not generate significant long-short returns (section 3.4 pp. 12-13, 'the other factors do "
        "not'; only the standard deviation of dollar volume does), on 2014-2018 weekly data. The "
        "crypto paper the family relies on for the asset class finds nothing on beta. "
        "(3) UNVERIFIABLE CLAIM. The registration rationale states the result 'held up under a "
        "regime split'. No definition of that split and no artifact recording it exists in "
        "cross_sectional_crypto.py, compute_crypto_factor_exposure, or any committed "
        "data/research_runs file (searched 2026-09-10). Treat the claim as absent until its "
        "computation is committed. "
        "(4) FP's factor is beta-neutral by levering; this spec is dollar-neutral with a measured "
        "BTC beta of 0.0572. Near-zero ex post is not the same property as zero by construction. "
        "(5) Every other FP element the module invokes — 1-year/5-year windows, w = 0.6, median "
        "split, rank weights, monthly rebalance, the TED-spread tests — was verified in the 2013 "
        "draft, as were LTW's $1M filter, weekly quintiles and Coinmarketcap source."
    ),
}

CRYPTO_L3 = {
    "source_claim_type": "unconditional",
    "claim_evidence": (
        "The claim this family tests is FP's prediction (2): 'A betting-against-beta (BAB) factor, "
        "which is long leveraged low-beta assets and short high-beta assets, produces significant "
        "positive risk-adjusted returns' (abstract) — stated unconditionally. FP ALSO make an "
        "explicitly conditional prediction (3): 'When funding constraints tighten, the return of "
        "the BAB factor is low', tested with the TED spread (section VI, Table IX). That "
        "conditional claim is NOT the one under test here: no crypto funding-liquidity proxy was "
        "pre-declared, and the module's only regime language is a cost decision (refusing to book "
        "the perpetual-funding credit of 'crypto's bull-market funding regime'). The registration "
        "rationale's 'held up under a regime split' has no committed definition or artifact — "
        "layer 2 finding (3)."
    ),
    "regime_definition_rule": None,
    "regime_rule_pre_declared_at": None,
    "dsr_in_regime": None,
    "dsr_out_of_regime": None,
    "not_applicable_reason": (
        "The tested claim is unconditional; the source's separate funding-constraint prediction "
        "was not pre-declared as a regime rule for this family and cannot be added after the "
        "fact. If the owner wants FP's prediction (3) tested in crypto, it needs its own "
        "pre-declared proxy and a fresh family, not a split of this one."
    ),
}

REVIEWS = {
    "quality_cbop": (QUALITY_CBOP_L2, QUALITY_CBOP_L3),
    "short_interest_ratio": (SHORT_INTEREST_L2, SHORT_INTEREST_L3),
    "lazy_prices_jaccard_full": (LAZY_PRICES_L2, LAZY_PRICES_L3),
    "cross_sectional_crypto": (CRYPTO_L2, CRYPTO_L3),
}

FILLED_GAP_FIELDS = (
    "layer_2_mechanism_fidelity (entire block)",
    "layer_3_regime_conditional.source_claim_type / claim_evidence",
)


def main() -> int:
    for family_key, (layer2, layer3) in REVIEWS.items():
        path = HERE / f"{family_key}_SCORECARD_DRAFT.json"
        draft = json.loads(path.read_text())
        assert draft["family_key"] == family_key, path
        draft["layer_2_mechanism_fidelity"] = layer2
        draft["layer_3_regime_conditional"] = layer3
        remaining = [g for g in draft["gaps"] if g["field"] not in FILLED_GAP_FIELDS]
        if not layer2["source_text_obtained"]:
            remaining.append(
                {
                    "field": "layer_2_mechanism_fidelity.source_text_obtained",
                    "reason": (
                        "false: the paper's full text could not be obtained at build or at review, "
                        "so every construction choice is sourced second-hand and the layer is "
                        "UNVERIFIABLE until someone with journal access reads it."
                    ),
                }
            )
        draft["gaps"] = remaining
        draft["draft_status"] = (
            "INCOMPLETE - layers 2 and 3 filled from the source papers by an independent reviewer "
            "2026-09-10 (see apply_layer_2_3_review.py); layer 4, decision, verdict and power still "
            "open"
        )
        draft["author"] = (
            "mechanical fields assembled by a Sonnet sub-agent 2026-09-09; layers 2 and 3 by the "
            "Fable 5.1 main session 2026-09-10 from the source papers"
        )
        draft["layers_2_3_reviewed_at"] = REVIEWED_AT
        path.write_text(json.dumps(draft, indent=2, ensure_ascii=False) + "\n")
        print(f"{family_key}: layer 2 ({len(layer2['construction_choices'])} choices, "
              f"{len(layer2['deviations'])} deviations, text_obtained={layer2['source_text_obtained']}), "
              f"layer 3 ({layer3['source_claim_type']}); {len(remaining)} gaps remain")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
