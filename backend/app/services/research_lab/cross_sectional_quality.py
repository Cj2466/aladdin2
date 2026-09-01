"""Two quality/profitability cross-sectional equity families computed from
SEC EDGAR XBRL annual fundamentals: CASH-BASED OPERATING PROFITABILITY and
NET OPERATING ASSETS. Two separate pre-declared families — never pooled,
never conflated into one signal — sharing one data pipeline
(edgar_xbrl_provider.py), the same way cross_sectional_small_mid_cap.py
hosts two families over one fetch.

=======================================================================
1. THE TWO SIGNALS AND THEIR VERIFIED SOURCES
=======================================================================

Both formulas below were read out of the actual papers THIS SESSION
(2026-08-28), fetched live — not recalled from memory:

(a) CASH-BASED OPERATING PROFITABILITY (CbOP). Ball, Gerakos, Linnainmaa
    & Nikolaev, "Accruals, cash flows, and operating profitability in the
    cross section of stock returns", Journal of Financial Economics 121(1),
    2016, pp. 28-45. Verified against the April 2015 working-paper PDF
    (fetched from ivey.uwo.ca/media/3775325/gerakos.pdf; the published JFE
    version is paywalled — the appendix formulas quoted below are from that
    working paper, whose tables match the published abstract's claims).
    Its Appendix, verbatim in substance:

      Operating profitability = Revenue (REVT) - Cost of goods sold (COGS)
        - Reported sales, general, and administrative expenses (XSGA - XRD)

      "in which 'Reported sales, general, and administrative expenses'
      subtracts off expenditures on research and development to undo the
      adjustment that Standard & Poor's makes to firms' accounting
      statements."

      Cash-based operating profitability = Operating profitability
        - d(Accounts receivable (RECT)) - d(Inventory (INVT))
        - d(Pre-paid expenses (XPP)) + d(Deferred revenue (DRC + DRLT))
        + d(Trade accounts payable (AP)) + d(Accrued expenses (XACC))

      "All changes are computed on year-to-year basis. Instances where
      balance sheet accounts have missing values are replaced with zero
      values for the computation."  All measures are deflated by the book
      value of total assets in year t-1 (the paper's Section 4.1: "all of
      which are deflated by the year t-1 value of total assets").

    Lineage (also verified live the same day): Novy-Marx, "The Other Side
    of Value: The Gross Profitability Premium", Journal of Financial
    Economics 108(1), 2013 — gross profitability (REVT - COGS, scaled by
    assets) as the parent profitability predictor. Ball et al.'s own Table
    2 (working paper) shows why the CASH-based refinement is the family
    run here: in Fama-MacBeth regressions cash-based operating
    profitability carries t = 9.84 against operating profitability's 8.97,
    and when both enter together (their column 7) cash-based survives
    (t = 5.83) while plain operating profitability collapses (t = 1.19) —
    the accrual component is the noise, the cash component the signal.

    DIRECTION: high CbOP predicts HIGH returns -> long the top decile,
    short the bottom (the harness's native top-is-long convention; no
    inversion needed).

(b) NET OPERATING ASSETS (NOA). Hirshleifer, Hou, Teoh & Zhang, "Do
    investors overvalue firms with bloated balance sheets?", Journal of
    Accounting and Economics 38 (2004), pp. 297-331. Verified against the
    published-version PDF (fetched from anderson.ucla.edu). Section 3.1,
    equations (4)-(6), verbatim in substance:

      NOA_t = (Operating Assets_t - Operating Liabilities_t) / Total Assets_{t-1}
      Operating Assets_t = Total Assets_t - Cash and Short-Term Investment_t
      Operating Liabilities_t = Total Assets_t - Short-Term Debt_t
        - Long-Term Debt_t - Minority Interest_t - Preferred Stock_t
        - Common Equity_t

      "if short-term debt, taxes payable, long-term debt, minority
      interest, or preferred stock has missing values, we treat these
      values as zeroes to avoid unnecessary loss of observations."

    DIRECTION: HIGH NOA (balance-sheet bloat) predicts LOW returns — the
    paper's own abstract calls scaled NOA "a strong negative predictor of
    long-run stock returns". The GOOD side is LOW NOA, so this family's
    signal is the NEGATED NOA value: the harness's top decile (long leg)
    is then the low-NOA firms and the bottom decile (short leg) the
    bloated ones, matching the paper's documented direction.

=======================================================================
2. COMPUSTAT -> XBRL MAPPING DECISIONS (each one stated, none silent)
=======================================================================

The papers define their variables in Compustat items; this project has no
Compustat. The XBRL equivalents and every judgment in them live in
edgar_xbrl_provider.py's measured fallback lists; the three decisions that
change arithmetic (not just tag names) are:

 * (XSGA - XRD) is implemented as us-gaap SellingGeneralAndAdministrative-
   Expense taken DIRECTLY, with NO research-and-development subtraction.
   Compustat's XSGA is S&P's own construction that ADDS R&D into reported
   SG&A; the paper subtracts XRD "to undo the adjustment that Standard &
   Poor's makes", i.e. to recover the REPORTED figure. The XBRL tag IS the
   reported figure (R&D is a separate income-statement line under its own
   tag), so subtracting R&D from it would remove R&D twice.
 * The paper's missing->0 convention is applied to the CHANGE terms, not
   to levels, and only when the account is missing at BOTH ends of the
   year-over-year window. A one-sided missing (present one year, absent
   the next — overwhelmingly XBRL tag-era flicker, e.g. XOM's inventory
   moving between tags) is treated as zero change AND COUNTED
   (FactorBuildDiagnostics.n_one_sided_changes), because zeroing it hides
   a real change the filer did report somewhere this pipeline could not
   see. Treating a one-sided missing LEVEL as zero — the naive reading of
   the paper's rule — would fabricate an enormous spurious "change" equal
   to the whole account balance, in whichever direction the flicker runs.
 * Common equity (CEQ) is parent stockholders' equity minus preferred
   stock at carrying value; where only the including-noncontrolling-
   interests equity total is tagged, minority interest is subtracted back
   out. See _resolve_common_equity for the residual imprecision this
   leaves and the tier tally that measures how often it is taken.

POINT-IN-TIME CONSTRUCTION. Every factor value becomes visible at the
LATEST "filed" date among every XBRL observation used to compute it — for
a year-over-year measure that is in practice the current year's 10-K
submission date. Values are originally-filed (earliest filing per period
wins in the provider), so restatements never rewrite history. The step
frame forward-fills from those filing dates only, never interpolates,
never backfills, and refuses a value carried beyond
FUNDAMENTAL_MAX_STALENESS_DAYS. Formation-time look-ahead is then
structural: the frame rides CrossSectionalData.fundamental_signal, which
the harness slices to rows <= the formation date like every other frame.

=======================================================================
3. UNIVERSE, SAMPLE, AND WHAT THAT COSTS
=======================================================================

The candidate pool is the point-in-time S&P 500 union universe
(get_universe_over), gated per formation by the harness's default
was_member — the same survivorship treatment as every equity family here.
From that pool a SEEDED random sample of QUALITY_SAMPLE_SIZE tickers is
drawn (seed QUALITY_SAMPLE_SEED, fixed in code before any result was
computed). The cap exists because the EDGAR pipeline is a per-CIK fetch
under SEC's published 10 req/s fair-access ceiling and the full union
would roughly quadruple the download for a first screening pass; the
honest cost is a smaller cross-section (measured on the real run: ~115-137
names ranked per NOA formation, ~68 for CbOP, so decile legs of ~10 and ~7
against the papers' hundreds) and correspondingly noisier leg returns. The
sample is random rather than alphabetical or size-ranked so it cannot tilt
the cross-section along any economically meaningful axis.

TWO SAMPLE-SPECIFIC COVERAGE HOLES, both measured and reported per run
rather than assumed away:
 * SEC's company_tickers.json maps CURRENT tickers only, so departed
   members whose symbols died with them resolve no CIK
   (QualityScreeningSummary.missing_cik). Those names' filings exist on
   EDGAR but are unreachable without a historical ticker-CIK map this
   project does not have. This stacks with the known yfinance price gap
   for departed members (see cross_sectional.py's survivorship section):
   both holes remove mostly index leavers, i.e. disproportionately the
   short leg's natural candidates.
 * Financial firms lack COGS-shaped tags entirely (JPM in the design
   probe), so CbOP refuses them and they never rank in family (a) — an
   incidental echo of the literature's standard financials exclusion. NOA
   computes for them (the paper's residual definition makes deposits
   operating liabilities), and Hirshleifer et al.'s own sample selection
   ("all NYSE/AMEX and NASDAQ firms in the intersection of the 2002
   COMPUSTAT and CRSP tapes") states no financials exclusion, so none is
   imposed here either.

=======================================================================
4. THE PRE-DECLARED FAMILIES
=======================================================================

Each family is the SAME fixed grid, declared before any backtest ran:
3 holding periods {63, 126, 252} x 2 portfolio modes {long_short,
long_universe_hedged} at deciles (6 core), plus a quintile long_short
robustness variant per holding period (3) = 9 definitions. n_trials = 9
PER FAMILY, each family's own size, never pooled across the two — the
same convention every sibling family keeps (buyback's 14, bonds', FX's own
counts). That the two families were built and run in one session is a
cross-family search the within-family DSR does not correct; it is
disclosed here exactly as it is for every other pair of families this
project has ever run in one session.

Holding periods: the ranking variable refreshes ANNUALLY per firm (one
10-K a year) but the CROSS-SECTION refreshes continuously as different
fiscal calendars file through the year, so quarterly reformation (63) is
the shortest hold that can catch staggered filings without re-paying
turnover on a mostly-unchanged ranking; 252 is the annual rebalance the
source papers themselves use (both rebalance yearly); 126 sits between.
Shorter holds were excluded up front by the same cost-vs-refresh argument
cross_sectional_buyback.py's NO-21/63-DAY section makes for its own
annual-ish signal — with the 63-day hold RETAINED here (unlike buyback)
precisely because the staggered-fiscal-year channel gives the cross-
section genuine intra-year news that a share-count panel lacks.

Costs: DEFAULT_XS_COST_BPS (5 bps one-way), identical to every S&P 500
equity family so Sharpes stay comparable. financing_bps_per_year stays
0.0 — the standing disclosed optimism about short borrow, not an estimate
(see cross_sectional.py's short-borrow section).

=======================================================================
5. PRODUCTION RUN 2026-08-28 — MEASURED COVERAGE AND RESULTS
=======================================================================

Run tag "quality_build_2026-08-28": formations 2015-01-07..2026-08-27
(2,926 realized trading days per spec), seeded 200-ticker sample from the
768-ticker union pool, persisted to cross_sectional_trial_results under
family_keys "quality_cbop" and "quality_noa" (9 + 9 rows). The persisted
rows are the POST-VERIFICATION numbers: the independent verification pass
(section 6) found and fixed two entity-discontinuity data bugs, re-ran
this entry point end to end, and REPLACED the original rows under the
same run tag so the database always matches the shipped code. Every
number below is from that canonical post-fix run's own
QualityScreeningSummary, and the full grid was independently re-replayed
from the cached filings twice during verification, reproducing every
Sharpe.

UNIVERSE ACCOUNTING (measured): 38 of 200 sampled tickers (19%) resolve
no CIK in SEC's current-day ticker map — all departed members whose
symbols died with them (FB, TWX, TWTR, EMC, ATVI, XLNX...) — and 0 EDGAR
fetches failed. 32 of 200 resolved no yfinance price history (the
standing departed-member gap; heavy overlap with the no-CIK list). Of
the 168 priced tickers, 53 produced no CbOP observation — dominated by
financials, which have no COGS-shaped tags (JPM, GS, MS, WFC, PNC, STT,
ZION, AIG...) — and 16 no NOA observation.

TAG-FALLBACK COVERAGE (measured, resolved fiscal-year observations across
162 extracted companyfacts): revenue 2,578 obs — 45.7% Revenues, 33.8%
RevenueFromContractWithCustomerExcludingAssessedTax, 15.4%
SalesRevenueNet, 5.1% last-resort tiers. COGS 1,681 — 52.4%
CostOfGoodsAndServicesSold, 28.6% CostOfRevenue, 14.9% CostOfGoodsSold
alone, 3.3% goods+services summed, 0.8% ex-D&A variant. SG&A 2,103 —
69.4% the combined tag, 30.6% component sums. Assets 2,629 — 100%
Assets. Cash+STI 2,702 — only 3.8% the exact combined tag, 96.2%
assembled cash(+STI/marketable securities). Short-term debt 1,954 —
31.1% DebtCurrent, 68.9% component composites. Long-term debt 2,158 —
62.8% LongTermDebtNoncurrent, 21.4% LongTermDebtAndCapitalLease-
Obligations, 15.8% recovered from the LongTermDebt total. Common equity
2,917 — 88.0% parent StockholdersEquity (34.3% with a preferred-stock
subtraction), 12.0% the including-NCI fallback. Receivables 84.2%/15.8%
across its two tags; inventory 98.2% InventoryNet; prepaid 63.7% the
bundled tag; deferred revenue split roughly evenly across the ASC-606 /
pre-606 eras. EVERY fallback tier fired somewhere real. The AP/accrued
double-count guard fired twice; the provider's cross-filing entity guard
refused 1,270 (tag, period) values across 139 firms (44 on tags this
pipeline reads — see section 6); CbOP counted 177 one-sided changes
treated as zero-change and 98 change terms diffed across a tag switch;
NOA zeroed missing short-term debt 530, long-term debt 357, minority
interest 1,058, preferred stock 1,295 times (the paper's own
convention). Factor panels: CbOP 1,476 observations (801 firm-years
refused for missing COGS, 120 for missing revenue), NOA 2,196 (201
refused for missing cash); median panel-cell age 183/181 calendar days —
genuinely annual, ~6 months carried on the median day.

RESULTS. All 18 definitions replayed at 2,926 days each.

CASH-BASED OPERATING PROFITABILITY — no validated edge. Long-short
deciles +0.27..+0.46 annualized Sharpe (best cbop_ls_h63 +0.46, DSR
0.82), universe-hedged variants +0.13..+0.17 (DSR 0.42..0.48). No spec
clears an 82% probability of beating its own family's 9-trial noise
benchmark, well short of this project's bar. NOTE: the first (pre-fix)
run reported this family MORE negatively (best +0.33/DSR 0.56, hedged
variants -0.11..-0.01): the two shell-entity names of section 6(b),
held at the long extreme on absurd shell-denominator CbOP values (FTI
through its 2018 collapse), had suppressed the best-spec Sharpe by 0.13
— a reminder that data bugs are not directionally conservative. On a
~68-name financials-free cross-section
this remains a null result, consistent with Ball et al.'s own reported
post-publication attenuation.

NET OPERATING ASSETS — positive on its face (+0.46..+0.66 Sharpe, DSR
0.88..0.97, all 9 specs) and NOT VALIDATED as the paper's anomaly: the
independent verification pass (section 6) CONFIRMED the builder's
sector-composition diagnosis quantitatively. The paper's own robustness
section reports its finding survives industry demeaning IN ITS OWN
1964-2002 broad-universe sample ("our main findings remain strong with
industry-demeaned NOA", p.315, a robustness check — its headline tests
use RAW NOA and include financials); THIS ~130-name 2015-2026 S&P 500
replication does NOT survive the same adjustment, which is exactly the
difference between the documented anomaly and a sector bet that happens
to share its ranking. VERDICT — DO NOT TREAT AS VALIDATED EDGE: likely
sector-tilt artifact; an industry-neutral NOA variant would be a NEW
family (new specs, its own pre-declared trial count, this run's 9 trials
carried into its denominator), deliberately NOT built post-hoc in this
module after seeing these results.

CORRECTION ADDENDUM 2026-09-02 — XOM WAS MISSING FROM THE RUN ABOVE.
Section 5's numbers stand as what run tag "quality_build_2026-08-28"
actually produced, and the persisted rows still match them; what
follows is what changes once one silently-excluded company is put
back. SEC's company_tickers.json had already moved ticker XOM onto CIK
2115436 ("ExxonMobil Holdings Corp", the successor of Exxon's
2026-07-01 holding-company reorganization — 29 filings, ZERO 10-Ks)
rather than CIK 34088, so a top-10 constituent produced no line item in
any year and did not even reach the missing-CIK list. Fixed in
edgar_xbrl_provider.py (see its SUCCESSOR-SHELL RESOLUTION block).
RE-RUN 2026-09-02 with one price fetch replayed to both arms and the
same cached fundamentals: the pre-fix arm reproduced every number in
section 5 exactly, and with XOM restored —
 * CbOP: MAX |dSharpe| = 0.0000 on all nine specs, formation counts and
   leg sizes identical. Exxon carries NO COGS-shaped us-gaap tag at all
   (none of CostOfGoodsAndServicesSold / CostOfRevenue /
   CostOfGoodsSold / CostOfServices / the ex-D&A variant appears in CIK
   34088's companyfacts), so CbOP refuses all 17 of its firm-years for
   missing_cogs — the same tag-shaped exclusion that already removes
   financials. XOM was never CbOP-eligible; tickers_without_cbop stays
   53.
 * NOA: XOM adds 17 observations (fiscal 2009..2025, +0.500..+0.769,
   inside the panel's existing |NOA| <= 8.7 bound and right where the
   sector diagnostic puts energy at +0.68). tickers_without_noa 16 ->
   15; Sharpes +0.461..+0.659 -> +0.461..+0.672, MAX |dSharpe| 0.031,
   DSR 0.880..0.968 -> 0.871..0.970.
Neither family's standing moves: CbOP remains no validated edge, and
NOA remains DO NOT TREAT AS VALIDATED EDGE for the reason section 6
establishes (the collapse test, not the Sharpe level). Full detail in
data/research_runs/xom_cik_fix_2026-09-02.txt and its pre-registration.

=======================================================================
6. INDEPENDENT VERIFICATION PASS (2026-08-28) — what it found
=======================================================================

Run independently of the builder, against the actual papers, the raw
filings, live SEC sector data, and the persisted rows. Everything below
was measured, not inferred.

(a) FORMULAS VERIFIED against both primary sources re-fetched during the
pass: Ball et al.'s working-paper Appendix (pp. 24-25) and Table 2
(t = 8.97 OP alone, 9.84 CbOP alone, and in the joint column 7 OP
collapses to 1.19 while CbOP survives at 5.83) match section 1's
transcription exactly; the published JFE version remains paywalled
(ScienceDirect 403), so the working-paper citation stands. Hirshleifer
et al.'s published JAE version (Eqs. 4-6 and its Table 1 Compustat map:
#6, #1, #34, #9, #38, #130, #60; the missing->0 convention; the negative
predicted sign; "we include the financial industry", fn. 16) matches
section 1 exactly.

(b) TWO REAL DATA BUGS, found, fixed, and unit-tested — both faces of
one root cause: XBRL has no Compustat-style entity linking, so a newly-
formed holding company's first 10-K (the pre-merger SHELL's balance
sheet) can sit in the same companyfacts history as the real operating
company. TechnipFMC's shell filed 2015/2016 total assets of $74,100
against $28.3B in FY2017 (NOA_2017 = +142,065); Linde's shell filed
$9.2M against $93.4B (NOA_2018 = +7,370); and for FTI's 2016 period the
per-item earliest-filed resolution MIXED the two entities within one
year (shell assets/cash/equity vs the real company's debt, NOA_2016 =
+34,294). Fixes: the cross-year assets ratio guard
(ASSETS_SCALE_BREAK_RATIO below) and the provider's cross-filing
same-period disagreement guard (CROSS_FILING_SCALE_CONFLICT_RATIO in
edgar_xbrl_provider.py). Cost: 3 CbOP + 3 NOA observations refused, all
garbage; every remaining panel value is |CbOP| <= 2.3, |NOA| <= 8.7
(the extremes are CBOE's genuine 11x Bats-merger year and INCY —
real data, kept). Impact: CbOP's published numbers changed materially
(see section 5), NOA's barely moved — the NOA positive was never the
bug.

(c) SECTOR TILT QUANTIFIED with live-fetched SEC SIC codes (data.sec.gov
/submissions, one per CIK) for every ranked name. The decile long leg is
36.8% tech + 25.5% financial by ticker-formation slots (h126; h63/h252
within 1%), with ZERO REIT/energy/telecom slots; the short leg's largest
bucket is REITs at 22.5% (DOC and ARE each 18/24 formations, VICI 9/24;
plus INVH, SIC 6510, 8/24). VRSN and PFG sit long 24/24. The ranking
variable itself is close to a sector label: median per-ticker mean NOA
climbs monotonically financial +0.25, tech +0.46, consumer +0.49,
industrial +0.59, healthcare +0.61, utility/energy +0.68, REIT +0.83 —
a low-NOA sort IS a long-financials/tech short-REIT sort on this
universe.

(d) THE COLLAPSE TEST — the decisive number. Re-running the identical 9
specs on NOA demeaned cross-sectionally within SIC sector bucket at
every date (a diagnostic, not a new family): Sharpes fall from
+0.46..+0.66 to -0.01..+0.22 and DSR from 0.88..0.97 to 0.36..0.66;
median-demeaned, +0.07..+0.34 (DSR 0.41..0.75). A crude STATIC long
eq-wt financials+tech / short eq-wt REITs portfolio over the same
formation dates earns Sharpe +0.67 by itself — more than any NOA spec —
correlates 0.39 daily with the real NOA stream (beta 0.62), and
regressing it out leaves residual Sharpe +0.34. Between-sector
composition, not within-sector NOA rotation, carries the result. The
9-trial DSR cannot see this because all nine siblings share the same
tilt — 0.97 measures "not the noise of nine correlated variants", never
"the documented anomaly at work".
"""

import itertools
import logging
import random
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import partial

import numpy as np
import pandas as pd

from app.services.market_data.edgar_xbrl_provider import (
    EdgarXbrlProvider,
    LineItemExtraction,
)
from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    DEFAULT_XS_COST_BPS,
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalScreeningResult,
    CrossSectionalSpec,
    screen_cross_sectional_universe,
)
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    get_universe_over,
)

logger = logging.getLogger(__name__)

# --- citations (verified live 2026-08-28 — see module docstring section 1) --

CBOP_CITATION = (
    "Ball, Gerakos, Linnainmaa & Nikolaev, 'Accruals, cash flows, and operating "
    "profitability in the cross section of stock returns' (Journal of Financial Economics, "
    "2016); Novy-Marx, 'The Other Side of Value: The Gross Profitability Premium' (Journal "
    "of Financial Economics, 2013)"
)

NOA_CITATION = (
    "Hirshleifer, Hou, Teoh & Zhang, 'Do investors overvalue firms with bloated balance "
    "sheets?' (Journal of Accounting and Economics, 2004)"
)

# --- factor construction constants ------------------------------------------

# A year-over-year pair of consecutive fiscal-year ends must be 250-480
# calendar days apart: wide enough for 52/53-week calendars and modest
# fiscal-year-end shifts, narrow enough that a multi-year gap (missing 10-K)
# can never masquerade as "the change over one year".
ANNUAL_PAIR_MIN_GAP_DAYS = 250
ANNUAL_PAIR_MAX_GAP_DAYS = 480

# ENTITY SCALE-BREAK GUARD (bug found & fixed 2026-08-28, independent
# verification pass). Both factors deflate by year t-1 total assets, which
# silently assumes the two fiscal years describe the SAME ECONOMIC ENTITY.
# XBRL breaks that assumption in a way Compustat (the papers' source, which
# links predecessor entities) never does: a newly-formed holding company's
# FIRST 10-K can be a pre-merger shell's balance sheet. Two real cases in
# this very sample: TechnipFMC (FTI) filed 2015/2016 total assets of
# $74,100 — seventy-four thousand dollars, the pre-merger shell — against
# $28.3B in FY2017, making NOA_2017 = +142,065; Linde (LIN) filed 2017
# assets of $9.2M (shell) against $93.4B in FY2018, NOA_2018 = +7,370.
# Both garbage values sat at the extreme short end of the ranking for ~a
# year each. The guard: refuse any year-over-year pair whose total-assets
# ratio exceeds this bound, in either direction. 100x is not a tuned
# number — the measured sample distribution (2,400 annual pairs) has NO
# ratio between 11.0x (CBOE's genuine Bats acquisition, kept) and 10,135x
# (LIN's shell, refused): real corporate events live at <11x, entity
# discontinuities at >10,000x, so anywhere in the four-orders-of-magnitude
# gap refuses exactly the same observations. Refusals are counted
# (n_refused["assets_entity_scale_break"]), never silent.
ASSETS_SCALE_BREAK_RATIO = 100.0

# How long a factor value may be carried forward from its filing date before
# the step frame refuses (NaN) it: one annual refresh cycle (365d) plus the
# SEC's own 10-K filing window (60-90 days after fiscal year end, depending
# on filer size). A firm whose next 10-K is later than that has genuinely
# stopped filing on schedule, and carrying its year-old fundamentals as
# "current" would be the dead-series masquerade shares_outstanding's rule
# exists to prevent.
FUNDAMENTAL_MAX_STALENESS_DAYS = 455

# The six accrual-adjustment accounts of Ball et al.'s balance-sheet CbOP,
# with the paper's own signs: subtract growth in receivables/inventory/
# prepaid (profit booked, cash not yet received / cash sunk into stock),
# add growth in deferred revenue/payables/accrued (cash received or
# retained, profit not yet booked).
CBOP_ACCRUAL_ITEMS: tuple[tuple[str, float], ...] = (
    ("receivables", -1.0),
    ("inventory", -1.0),
    ("prepaid", -1.0),
    ("deferred_revenue", +1.0),
    ("accounts_payable", +1.0),
    ("accrued_expenses", +1.0),
)


@dataclass(frozen=True)
class FactorObservation:
    """One fiscal year's factor value for one company.

    `available` is the first date the value could have been publicly known:
    the LATEST 'filed' date across every XBRL observation used to compute
    it (in practice the current year's 10-K submission date). The step
    frame builder forward-fills from THIS date — never from the fiscal
    period end, which precedes public availability by the whole filing
    lag."""

    end: date
    value: float
    available: date


@dataclass
class FactorBuildDiagnostics:
    """What the factor computation refused, zeroed, or bridged — measured
    per run and reported first-class, per this project's standing
    discipline that a correction (or a coverage hole) that silently stops
    firing must not look like one that had nothing to do."""

    n_observations: int = 0
    # reason -> count of (ticker, fiscal-year) pairs refused outright.
    n_refused: Counter = field(default_factory=Counter)
    # CbOP: accrual accounts missing at BOTH window ends, treated as zero
    # change per the paper's own missing->0 convention (item -> count).
    n_both_missing_zero: Counter = field(default_factory=Counter)
    # CbOP: accounts present at exactly ONE window end — zero change plus a
    # count, per the module docstring's one-sided rule.
    n_one_sided_changes: int = 0
    # CbOP: change terms whose two endpoints resolved from DIFFERENT tags
    # (an era switch inside the window) — the delta is still computed, but
    # cross-tag scope drift is a real hazard worth counting.
    n_tag_switch_pairs: int = 0
    # NOA: items the paper's convention zeroes when missing (item -> count).
    n_missing_treated_as_zero: Counter = field(default_factory=Counter)

    def merge(self, other: "FactorBuildDiagnostics") -> None:
        self.n_observations += other.n_observations
        self.n_refused.update(other.n_refused)
        self.n_both_missing_zero.update(other.n_both_missing_zero)
        self.n_one_sided_changes += other.n_one_sided_changes
        self.n_tag_switch_pairs += other.n_tag_switch_pairs
        self.n_missing_treated_as_zero.update(other.n_missing_treated_as_zero)


def _annual_pairs(ends: list[date]) -> list[tuple[date, date]]:
    pairs = []
    for prev, cur in itertools.pairwise(sorted(ends)):
        gap = (cur - prev).days
        if ANNUAL_PAIR_MIN_GAP_DAYS <= gap <= ANNUAL_PAIR_MAX_GAP_DAYS:
            pairs.append((prev, cur))
    return pairs


def _is_entity_scale_break(prev_assets: float, cur_assets: float) -> bool:
    """True when a year-over-year total-assets pair cannot be the same
    economic entity (see ASSETS_SCALE_BREAK_RATIO): both ends positive and
    finite, but different by more than the bound in either direction. A
    non-positive or non-finite CURRENT value is not judged here — the
    lagged-assets check and each factor's own finiteness refusal already
    own those cases."""
    if not (np.isfinite(prev_assets) and np.isfinite(cur_assets)):
        return False
    if prev_assets <= 0.0 or cur_assets <= 0.0:
        return False
    ratio = max(cur_assets / prev_assets, prev_assets / cur_assets)
    return ratio > ASSETS_SCALE_BREAK_RATIO


def compute_cbop_observations(
    extraction: LineItemExtraction,
) -> tuple[list[FactorObservation], FactorBuildDiagnostics]:
    """Ball et al. (2016) cash-based operating profitability, one value per
    usable consecutive fiscal-year pair:

        CbOP_t = [ (REV_t - COGS_t - SGA_t)
                   - dReceivables - dInventory - dPrepaid
                   + dDeferredRevenue + dAccountsPayable + dAccrued ]
                 / Assets_{t-1}

    Refusals (all counted): missing revenue or COGS at the current year end
    (the measure is undefined without an income statement — this is what
    keeps banks out, see module docstring), missing SG&A is NOT a refusal
    (a filer with no SG&A line genuinely has none — treated as zero and
    counted), and non-positive or missing lagged assets (an unusable
    deflator)."""
    items = extraction.items
    diagnostics = FactorBuildDiagnostics()
    out: list[FactorObservation] = []
    assets = items["assets"]

    for e_prev, e in _annual_pairs(list(assets.keys())):
        lagged_assets = assets[e_prev]
        if not np.isfinite(lagged_assets.value) or lagged_assets.value <= 0.0:
            diagnostics.n_refused["non_positive_lagged_assets"] += 1
            continue
        if _is_entity_scale_break(lagged_assets.value, assets[e].value):
            diagnostics.n_refused["assets_entity_scale_break"] += 1
            continue
        revenue = items["revenue"].get(e)
        cogs = items["cogs"].get(e)
        if revenue is None:
            diagnostics.n_refused["missing_revenue"] += 1
            continue
        if cogs is None:
            diagnostics.n_refused["missing_cogs"] += 1
            continue

        used_filed = [lagged_assets.filed, revenue.filed, cogs.filed]

        sga = items["sga"].get(e)
        if sga is None:
            diagnostics.n_both_missing_zero["sga"] += 1
            sga_value = 0.0
        else:
            sga_value = sga.value
            used_filed.append(sga.filed)

        operating_profitability = revenue.value - cogs.value - sga_value

        accrual_adjustment = 0.0
        for item_name, sign in CBOP_ACCRUAL_ITEMS:
            cur = items[item_name].get(e)
            prev = items[item_name].get(e_prev)
            if cur is not None and prev is not None:
                accrual_adjustment += sign * (cur.value - prev.value)
                used_filed.extend((cur.filed, prev.filed))
                if cur.tag != prev.tag:
                    diagnostics.n_tag_switch_pairs += 1
            elif cur is None and prev is None:
                diagnostics.n_both_missing_zero[item_name] += 1
            else:
                diagnostics.n_one_sided_changes += 1

        value = (operating_profitability + accrual_adjustment) / lagged_assets.value
        if not np.isfinite(value):
            diagnostics.n_refused["non_finite_value"] += 1
            continue
        diagnostics.n_observations += 1
        out.append(FactorObservation(end=e, value=float(value), available=max(used_filed)))

    return out, diagnostics


def compute_noa_observations(
    extraction: LineItemExtraction,
) -> tuple[list[FactorObservation], FactorBuildDiagnostics]:
    """Hirshleifer et al. (2004) scaled net operating assets:

        NOA_t = (OA_t - OL_t) / Assets_{t-1}
        OA_t  = Assets_t - CashAndShortTermInvestments_t
        OL_t  = Assets_t - ShortTermDebt_t - LongTermDebt_t
                - MinorityInterest_t - PreferredStock_t - CommonEquity_t

    Missing short-term debt, long-term debt, minority interest, or
    preferred stock -> zero, per the paper's own stated convention (each
    zeroing counted). Missing cash or common equity is a REFUSAL: zeroing
    cash would call the whole balance sheet operating, and there is no
    sensible zero for common equity — both would fabricate an extreme NOA
    rather than approximate a real one."""
    items = extraction.items
    diagnostics = FactorBuildDiagnostics()
    out: list[FactorObservation] = []
    assets = items["assets"]

    for e_prev, e in _annual_pairs(list(assets.keys())):
        lagged_assets = assets[e_prev]
        if not np.isfinite(lagged_assets.value) or lagged_assets.value <= 0.0:
            diagnostics.n_refused["non_positive_lagged_assets"] += 1
            continue
        total_assets = assets[e]
        if _is_entity_scale_break(lagged_assets.value, total_assets.value):
            diagnostics.n_refused["assets_entity_scale_break"] += 1
            continue
        cash = items["cash_and_short_term_investments"].get(e)
        common_equity = items["common_equity"].get(e)
        if cash is None:
            diagnostics.n_refused["missing_cash_and_short_term_investments"] += 1
            continue
        if common_equity is None:
            diagnostics.n_refused["missing_common_equity"] += 1
            continue

        used_filed = [lagged_assets.filed, total_assets.filed, cash.filed, common_equity.filed]

        zeroable = 0.0
        for item_name in (
            "short_term_debt",
            "long_term_debt",
            "minority_interest",
            "preferred_stock",
        ):
            resolved = items[item_name].get(e)
            if resolved is None:
                diagnostics.n_missing_treated_as_zero[item_name] += 1
            else:
                zeroable += resolved.value
                used_filed.append(resolved.filed)

        operating_assets = total_assets.value - cash.value
        operating_liabilities = total_assets.value - zeroable - common_equity.value
        value = (operating_assets - operating_liabilities) / lagged_assets.value
        if not np.isfinite(value):
            diagnostics.n_refused["non_finite_value"] += 1
            continue
        diagnostics.n_observations += 1
        out.append(FactorObservation(end=e, value=float(value), available=max(used_filed)))

    return out, diagnostics


def build_point_in_time_factor_frame(
    close: pd.DataFrame,
    observations: dict[str, list[FactorObservation]],
    *,
    max_staleness_days: int = FUNDAMENTAL_MAX_STALENESS_DAYS,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """The point-in-time STEP panel a quality family ranks on: one column
    per ticker aligned to close's exact index and columns, each value
    visible from its own FILING-derived availability date, forward-filled
    only, staleness-bounded, never interpolated, never backfilled.

    Returns (factor frame, value-age frame in calendar days, tickers with
    no usable observations). The age frame exists so a run can report the
    measured median staleness of what it actually ranked on — the same
    honesty number BuybackScreeningSummary carries for its share panel.

    A late-arriving STALE observation (an older fiscal year whose
    availability postdates a newer year's — amended filings can do this)
    is dropped rather than allowed to overwrite fresher information: the
    step must be monotone in BOTH availability and period end."""
    empty = pd.Series(np.nan, index=close.index, dtype=float)
    factor_columns: dict[str, pd.Series] = {}
    age_columns: dict[str, pd.Series] = {}
    unusable: list[str] = []

    for ticker in close.columns:
        events = sorted(observations.get(ticker, []), key=lambda o: (o.available, o.end))
        kept: list[FactorObservation] = []
        for event in events:
            if kept and event.end <= kept[-1].end:
                continue  # stale fiscal year arriving after a fresher one
            kept.append(event)
        if not kept:
            unusable.append(ticker)
            factor_columns[ticker] = empty.copy()
            age_columns[ticker] = empty.copy()
            continue

        avail_index = pd.DatetimeIndex([pd.Timestamp(e.available) for e in kept])
        values = pd.Series([e.value for e in kept], index=avail_index, dtype=float)
        values = values[~values.index.duplicated(keep="last")].sort_index()

        union = values.index.union(close.index).sort_values()
        on_union = values.reindex(union)
        filled = on_union.ffill()
        observed_at = pd.Series(union, index=union).where(on_union.notna()).ffill()
        age_days = (pd.Series(union, index=union) - observed_at).dt.days
        filled = filled.where(age_days.notna() & (age_days <= max_staleness_days))

        factor_columns[ticker] = filled.reindex(close.index)
        age_columns[ticker] = age_days.where(filled.notna()).reindex(close.index).astype(float)

    frame = pd.DataFrame(factor_columns, index=close.index)[list(close.columns)]
    ages = pd.DataFrame(age_columns, index=close.index)[list(close.columns)]
    return frame, ages, sorted(unusable)


# --- the signal --------------------------------------------------------------


def signal_fundamental_factor(history: CrossSectionalData, *, direction: float) -> pd.Series:
    """The formation-date row of the point-in-time factor step panel, times
    `direction` (+1.0 for CbOP where high is good; -1.0 for NOA where LOW
    is good, so the harness's top-is-long convention lands the long leg on
    the paper's documented good side).

    All the real work — formula, filing-date visibility, staleness — happened
    in the builders above; this function only reads the last row of the
    history view, which the harness has already truncated to rows <= the
    formation date (the structural look-ahead guarantee). NaN cells refuse
    the ticker from ranking, which is the correct answer for "this
    company's fundamentals are unobservable or stale here"."""
    frame = history.fundamental_signal
    if frame is None:
        raise ValueError(
            "signal_fundamental_factor requires CrossSectionalData.fundamental_signal; the "
            "spec must set requires_fundamental_signal=True and the caller must supply the "
            "frame."
        )
    row = frame.iloc[-1].astype(float)
    signal = direction * row
    return signal.where(np.isfinite(signal))


# --- the two pre-declared families ------------------------------------------

QUALITY_HOLDING_DAYS: tuple[int, ...] = (63, 126, 252)
QUALITY_PORTFOLIOS: tuple[str, ...] = ("long_short", "long_universe_hedged")
QUALITY_RANK_FRACTION = 0.1  # deciles — both papers' own headline sorts
QUALITY_ROBUSTNESS_RANK_FRACTION = 0.2  # quintile robustness variant

# Per family: 3 holds x 2 portfolios at deciles, plus 3 quintile long_short
# robustness variants. Each family's OWN DSR denominator — see module
# docstring section 4 for why the two are never pooled.
QUALITY_N_CORE_TRIALS = len(QUALITY_HOLDING_DAYS) * len(QUALITY_PORTFOLIOS)
QUALITY_N_ROBUSTNESS_TRIALS = len(QUALITY_HOLDING_DAYS)
QUALITY_N_TRIALS_PER_FAMILY = QUALITY_N_CORE_TRIALS + QUALITY_N_ROBUSTNESS_TRIALS

QUALITY_COST_BPS = DEFAULT_XS_COST_BPS  # same 5 bps as every S&P 500 equity family
QUALITY_FINANCING_BPS_PER_YEAR = 0.0  # the standing short-borrow disclosure, not an estimate

# The signal reads exactly one row (the formation date's step value); 1 row
# of declared lookback keeps the per-formation view minimal. History depth
# lives in the FILING data, not the price frame.
QUALITY_SIGNAL_LOOKBACK_ROWS = 1


def _build_quality_family(
    family: str, id_prefix: str, citation: str, direction: float
) -> list[CrossSectionalSpec]:
    specs: list[CrossSectionalSpec] = []
    for portfolio in QUALITY_PORTFOLIOS:
        portfolio_tag = "ls" if portfolio == "long_short" else "hedged"
        for holding in QUALITY_HOLDING_DAYS:
            specs.append(
                CrossSectionalSpec(
                    pattern_id=f"{id_prefix}_{portfolio_tag}_h{holding}",
                    family=family,
                    citation=citation,
                    signal_fn=partial(signal_fundamental_factor, direction=direction),
                    lookback_days=QUALITY_SIGNAL_LOOKBACK_ROWS,
                    holding_days=holding,
                    portfolio=portfolio,  # type: ignore[arg-type]
                    rank_fraction=QUALITY_RANK_FRACTION,
                    requires_fundamental_signal=True,
                )
            )
    for holding in QUALITY_HOLDING_DAYS:
        specs.append(
            CrossSectionalSpec(
                pattern_id=f"{id_prefix}_ls_h{holding}_quintile",
                family=family,
                citation=citation,
                signal_fn=partial(signal_fundamental_factor, direction=direction),
                lookback_days=QUALITY_SIGNAL_LOOKBACK_ROWS,
                holding_days=holding,
                portfolio="long_short",
                rank_fraction=QUALITY_ROBUSTNESS_RANK_FRACTION,
                requires_fundamental_signal=True,
            )
        )

    assert len(specs) == QUALITY_N_TRIALS_PER_FAMILY == 9, (
        f"{family} built {len(specs)} definitions; the declared grid implies "
        f"{QUALITY_N_TRIALS_PER_FAMILY} and the build pre-declared exactly 9. All three must "
        "agree — a drift silently changes this family's DSR denominator."
    )
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    assert all(s.requires_fundamental_signal for s in specs)
    assert all(s.leg_weighting == "magnitude" for s in specs)
    assert all(s.cohort_formation_days is None for s in specs)
    assert all(s.holding_days in QUALITY_HOLDING_DAYS for s in specs)
    assert 21 not in QUALITY_HOLDING_DAYS, (
        "monthly holds are excluded up front: the per-firm ranking variable refreshes once a "
        "year, so a 21-day hold re-pays turnover on an almost entirely unchanged ranking."
    )
    return specs


# CbOP: high value is the good side — direction +1.0 (no inversion).
CBOP_FAMILY: list[CrossSectionalSpec] = _build_quality_family(
    "cash_operating_profitability", "cbop", CBOP_CITATION, direction=+1.0
)
# NOA: LOW value is the good side (high NOA predicts LOW returns) —
# direction -1.0, so the harness's long top decile is the low-NOA firms.
# The id prefix says so, to keep every printed leaderboard self-describing.
NOA_FAMILY: list[CrossSectionalSpec] = _build_quality_family(
    "net_operating_assets", "noa_low", NOA_CITATION, direction=-1.0
)

CBOP_N_TRIALS = len(CBOP_FAMILY)
NOA_N_TRIALS = len(NOA_FAMILY)

# --- universe sample ---------------------------------------------------------

# The pre-registered sample cap and seed — both fixed in code BEFORE any
# result was computed (see module docstring section 3 for why a cap exists
# at all and what it costs).
QUALITY_SAMPLE_SIZE = 200
QUALITY_SAMPLE_SEED = 20260828

# Price history padding before the requested start: the signal needs only
# one prior row (QUALITY_SIGNAL_LOOKBACK_ROWS), so this is a small calendar
# margin for the row-indexed formation floor, not a lookback warmup.
QUALITY_PRICE_HISTORY_PADDING_CALENDAR_DAYS = 30


def build_quality_sample(start: date, end: date) -> tuple[list[str], int]:
    """(sorted seeded sample, full union universe size). Deterministic:
    same window -> same sample, so a re-run screens the identical
    cross-section."""
    full = get_universe_over(start, end)
    if len(full) <= QUALITY_SAMPLE_SIZE:
        return sorted(full), len(full)
    rng = random.Random(QUALITY_SAMPLE_SEED)
    return sorted(rng.sample(full, QUALITY_SAMPLE_SIZE)), len(full)


def default_quality_config() -> CrossSectionalConfig:
    """A fresh config per call (the harness writes formation_start onto
    whatever it is given) — the same no-shared-singleton contract
    default_buyback_config keeps."""
    return CrossSectionalConfig(
        cost_bps=QUALITY_COST_BPS,
        financing_bps_per_year=QUALITY_FINANCING_BPS_PER_YEAR,
    )


# --- production entry point --------------------------------------------------


@dataclass
class QualityScreeningSummary:
    """run_quality_screening's full result: both families' screening
    output plus every measured coverage number a reader needs to interpret
    them. Typed fields, not docstring paragraphs — the discipline
    BuybackScreeningSummary states."""

    cbop_results: list[CrossSectionalScreeningResult]
    noa_results: list[CrossSectionalScreeningResult]
    cbop_n_trials: int
    noa_n_trials: int
    # Universe accounting: the full point-in-time union pool, the seeded
    # sample actually fetched, and every hole between the sample and what
    # finally ranked. A result read without these is not interpretable.
    universe_size: int
    sample_size: int
    sample_seed: int
    missing_cik: list[str]
    failed_edgar_fetch: list[str]
    missing_price_data: list[str]
    tickers_without_cbop: list[str]
    tickers_without_noa: list[str]
    panel_start: date | None
    panel_end: date | None
    formation_start: date
    # Measured tag-fallback coverage, aggregated across the sample:
    # line item -> {"t{tier}:{tag}": count of resolved fiscal-year
    # observations}. THE number that makes the provider's fallback design
    # honest — realized usage, not assumed availability.
    tag_tier_usage: dict[str, dict[str, int]] = field(default_factory=dict)
    cbop_diagnostics: FactorBuildDiagnostics = field(default_factory=FactorBuildDiagnostics)
    noa_diagnostics: FactorBuildDiagnostics = field(default_factory=FactorBuildDiagnostics)
    n_ap_accrued_double_count_guard: int = 0
    # Median calendar age, across every populated panel cell on formation-
    # eligible dates, of the filing each cell's value came from. Annual
    # panels should read ~180-230 days; a number far above that means
    # values are being carried too long.
    median_cbop_value_age_days: float = float("nan")
    median_noa_value_age_days: float = float("nan")
    cost_bps: float = QUALITY_COST_BPS
    financing_bps_per_year: float = QUALITY_FINANCING_BPS_PER_YEAR
    warnings: list[str] = field(default_factory=list)


def _median_age(ages: pd.DataFrame, since: date) -> float:
    window = ages.loc[ages.index.date >= since]  # type: ignore[attr-defined]
    values = window.to_numpy().ravel()
    values = values[np.isfinite(values)]
    return float(np.median(values)) if values.size else float("nan")


def run_quality_screening(
    start: date = MEMBERSHIP_DATA_START,
    end: date | None = None,
    provider: YFinanceProvider | None = None,
    edgar: EdgarXbrlProvider | None = None,
    config: CrossSectionalConfig | None = None,
) -> QualityScreeningSummary:
    """THE production entry point for both quality families: one EDGAR
    fetch, one price fetch, two separately-screened pre-declared families.

    The two screening calls share the identical price panel and point-in-
    time membership gate; only the fundamental_signal frame differs. Each
    family's DSR uses its OWN n_trials (len of its own spec list, the
    harness default) — see module docstring section 4."""
    if start < MEMBERSHIP_DATA_START:
        raise ValueError(
            f"Quality screening start {start.isoformat()} predates point-in-time membership "
            f"coverage ({MEMBERSHIP_DATA_START.isoformat()}) — a formation before that date "
            "would silently see an empty universe."
        )
    end = end if end is not None else date.today()  # noqa: DTZ011 — price-fetch end bound only
    provider = provider if provider is not None else YFinanceProvider()
    edgar = edgar if edgar is not None else EdgarXbrlProvider()
    config = config if config is not None else default_quality_config()
    config.formation_start = start

    warnings: list[str] = []
    sample, universe_size = build_quality_sample(start, end)

    extractions, missing_cik, failed_fetch = edgar.fetch_line_items_for_tickers(sample)
    if missing_cik:
        warnings.append(
            f"{len(missing_cik)} of {len(sample)} sampled tickers resolve no CIK in SEC's "
            "current-day ticker map (departed members whose symbols died — see module "
            "docstring section 3) and can never be ranked."
        )
    if failed_fetch:
        warnings.append(
            f"{len(failed_fetch)} EDGAR companyfacts fetches failed outright after retries."
        )
    if edgar.cik_resolution.describe():
        warnings.append(
            "SEC ticker-map CIK resolution: " + edgar.cik_resolution.describe() + "."
        )

    padded_start = start - timedelta(days=QUALITY_PRICE_HISTORY_PADDING_CALENDAR_DAYS)
    close, missing_price = provider.get_price_history(sample, padded_start, end)
    if close.empty:
        return QualityScreeningSummary(
            cbop_results=[],
            noa_results=[],
            cbop_n_trials=CBOP_N_TRIALS,
            noa_n_trials=NOA_N_TRIALS,
            universe_size=universe_size,
            sample_size=len(sample),
            sample_seed=QUALITY_SAMPLE_SEED,
            missing_cik=missing_cik,
            failed_edgar_fetch=failed_fetch,
            missing_price_data=missing_price,
            tickers_without_cbop=[],
            tickers_without_noa=[],
            panel_start=None,
            panel_end=None,
            formation_start=start,
            warnings=[*warnings, "No price data resolved for any sampled ticker."],
        )
    if missing_price:
        warnings.append(
            f"{len(missing_price)} of {len(sample)} sampled tickers resolved no price data "
            "(the standing departed-member yfinance gap — see cross_sectional.py)."
        )

    # Factor observations per ticker, from the shared extraction.
    cbop_obs: dict[str, list[FactorObservation]] = {}
    noa_obs: dict[str, list[FactorObservation]] = {}
    cbop_diag = FactorBuildDiagnostics()
    noa_diag = FactorBuildDiagnostics()
    tier_usage: dict[str, Counter] = {}
    n_guard = 0
    for ticker, extraction in extractions.items():
        obs, diag = compute_cbop_observations(extraction)
        cbop_obs[ticker] = obs
        cbop_diag.merge(diag)
        obs, diag = compute_noa_observations(extraction)
        noa_obs[ticker] = obs
        noa_diag.merge(diag)
        for item, counter in extraction.tier_usage.items():
            tier_usage.setdefault(item, Counter()).update(counter)
        n_guard += extraction.n_ap_accrued_double_count_guard

    cbop_frame, cbop_ages, no_cbop = build_point_in_time_factor_frame(close, cbop_obs)
    noa_frame, noa_ages, no_noa = build_point_in_time_factor_frame(close, noa_obs)
    for label, missing in (("CbOP", no_cbop), ("NOA", no_noa)):
        if missing:
            warnings.append(
                f"{len(missing)} of {len(close.columns)} priced tickers produced no usable "
                f"{label} observation (no CIK, failed fetch, or refused by the formula's own "
                "requirements — see diagnostics) and are never ranked in that family."
            )

    cbop_results = screen_cross_sectional_universe(
        CrossSectionalData(close=close, fundamental_signal=cbop_frame), CBOP_FAMILY, config
    )
    noa_results = screen_cross_sectional_universe(
        CrossSectionalData(close=close, fundamental_signal=noa_frame), NOA_FAMILY, config
    )

    return QualityScreeningSummary(
        cbop_results=cbop_results,
        noa_results=noa_results,
        cbop_n_trials=CBOP_N_TRIALS,
        noa_n_trials=NOA_N_TRIALS,
        universe_size=universe_size,
        sample_size=len(sample),
        sample_seed=QUALITY_SAMPLE_SEED,
        missing_cik=missing_cik,
        failed_edgar_fetch=failed_fetch,
        missing_price_data=missing_price,
        tickers_without_cbop=no_cbop,
        tickers_without_noa=no_noa,
        panel_start=close.index[0].date(),
        panel_end=close.index[-1].date(),
        formation_start=start,
        tag_tier_usage={item: dict(counter) for item, counter in tier_usage.items()},
        cbop_diagnostics=cbop_diag,
        noa_diagnostics=noa_diag,
        n_ap_accrued_double_count_guard=n_guard,
        median_cbop_value_age_days=_median_age(cbop_ages, start),
        median_noa_value_age_days=_median_age(noa_ages, start),
        cost_bps=config.cost_bps,
        financing_bps_per_year=config.financing_bps_per_year,
        warnings=warnings,
    )
