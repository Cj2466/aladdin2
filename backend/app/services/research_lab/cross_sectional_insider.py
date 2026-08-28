"""Routine-vs-opportunistic insider trading (Cohen, Malloy & Pomorski
2012): a deliberately small (8-definition) EVENT-DRIVEN, LONG-ONLY-plus-
index-hedge family -- long fresh open-market insider BUYS by insiders
classified OPPORTUNISTIC under the paper's own rule, hedged 1:1 with SPY,
each event held for a fixed pre-declared horizon. Insider trades come from
SEC's own structured Insider Transactions Data Sets (quarterly Form 3/4/5
TSV files), NOT from Thomson Reuters (the paper's source, which this
project does not have) and NOT from the free-text/XBRL company-facts
pipeline the PEAD/NOA families built -- this is a genuinely different,
structured tabular SEC product, verified live below.

Like cross_sectional_pead.py and cross_sectional_index_removal.py (both
read in full before this was built; PEAD is the direct structural
template) this module owns its family object, its n_trials denominator,
and its never-pooled DSR correction, and it does NOT run on
cross_sectional.screen_cross_sectional_universe -- insider Form 4 filings
are individual dated events like 8-Ks, not a synchronized universe
snapshot, so there is no shared formation calendar to rank on. What it
reuses, unmodified, is everything downstream and sideways of the event
loop: metrics.sharpe_ratio, deflated_sharpe.compute_deflated_sharpe, and
-- from cross_sectional.py itself -- _resolve_leg_weights (so "equal" and
"inverse_vol" here are LITERALLY the harness's own leg-weighting modes),
_leg_weighted_return, _compute_delisting_positions plus
DEFAULT_IMPUTED_DELISTING_RETURN, DEFAULT_XS_COST_BPS,
FINANCING_DAYS_PER_YEAR and MIN_REPLAY_TRADING_DAYS. It also reuses
cross_sectional_pead.load_cik_map verbatim (SEC's own ticker->CIK file,
whose shape that module verified live and this session re-verified by
executing it: 500 of 503 SCREENING_UNIVERSE tickers resolved).

============================================================================
THE ACADEMIC BASIS -- VERIFIED LIVE THIS SESSION (2026-08-28), NOT MEMORY
============================================================================
 * Cohen, L., Malloy, C. & Pomorski, L., "Decoding Inside Information"
   (The Journal of Finance, 67(3), 2012, pp. 1009-1043, DOI
   10.1111/j.1540-6261.2012.01740.x). PRIMARY: the full open-access text
   was retrieved from Harvard DASH (dash.harvard.edu, handle 1/33785679,
   82-page PDF whose own citation page carries the volume/issue/pages/DOI
   above) and read; every quote below is from that retrieved text.

   THE CLASSIFICATION RULE, quoted from the retrieved text: "We require an
   insider to make at least one trade in each of the three preceding years
   in order to define her as either an opportunistic or a routine trader.
   Specifically, we then define a routine trader as an insider who placed
   a trade in the same calendar month for at least three consecutive
   years." and "We define opportunistic traders as everyone else, i.e.
   those insiders for whom we cannot detect an obvious discernible pattern
   in the past timing of their trades. We thus designate all insiders as
   either routine traders or opportunistic traders at the beginning of
   each calendar year, based on their past history of trades, and then
   look to see how they trade from that point onwards."

   The paper's own Exhibit A1 resolves the "which three consecutive years"
   ambiguity: "the 'routine' trades are trades made by an insider who has
   had three consecutive calendar years with trades in the same month IN
   THE PAST" -- its worked example (insider Bob trades March 1987, 1988,
   1989, then January/March/December 1990 and January 1991) classifies Bob
   routine in 1990 AND 1991, i.e. the same-month run may lie anywhere in
   the visible past, not only in the three immediately preceding years,
   and the label is sticky once the run exists. classify_owner_year below
   implements exactly this reading, and the test suite replays the Bob
   example verbatim.

   DATA, quoted: "Our data are drawn from these Form 4 filings for the
   period January, 1986 to December, 2007. Our analysis focuses on
   open-market purchases and sales by insiders, and hence we exclude
   options exercises and private transactions." Reporting: "This 10-day
   deadline was later changed to a 2-day deadline in 2002. The median
   delay between trade date and report date over our entire 22 year
   sample is 3 days."

   PORTFOLIOS, quoted: "we identify opportunistic and routine trades each
   month, and then form opportunistic buy, opportunistic sell, routine
   buy, and routine sell portfolios containing these stocks. We then hold
   these stocks over the month following these insider trades; at the end
   of the month, we rebalance the portfolios based on new insider trades."

   HEADLINE RESULT, quoted: "a long-short portfolio that exploits solely
   the trades of opportunistic traders (opportunistic buys minus
   opportunistic sells) earns value-weighted abnormal returns of 82 basis
   points per month (9.8 percent annualized, t=2.15), and equal-weighted
   abnormal returns of 180 basis points per month (21.6 percent
   annualized, t=6.07)" while "a portfolio that mimics the behavior of
   routine traders (routine buys minus routine sells) earns value-weighted
   returns of -20 basis points per month (t=-0.57)". Event-time returns
   "continue to rise for the first six months, and then level off,
   exhibiting no future reversal" (Figure 1: ~4% VW / ~8% EW over twelve
   months on the four-leg spread).

   AN HONESTY NOTE THIS FAMILY MUST CARRY: the paper states "over half of
   the improvement in predictive power gained by focusing on opportunistic
   trades comes from the superior performance of opportunistic SELLS
   relative to routine sells". This family trades the BUY side only (the
   project has no real securities-borrow data for single-name shorts, a
   known open gap), so it deliberately forgoes the side the paper says
   carries over half the improvement. The buy side is still real in the
   paper: opportunistic buys alone predict future returns (their modified-
   approach figure: "opportunistic buys predict future returns of 98 basis
   points per month (t=12.25)"), but a weaker result here than the
   headline long-short is EXPECTED BY DESIGN, not evidence of a bug.

============================================================================
SEC INSIDER TRANSACTIONS DATA SETS -- VERIFIED LIVE 2026-08-28, NOT ASSUMED
============================================================================
 * PAGE: https://www.sec.gov/data-research/sec-markets-data/
   insider-transactions-data-sets (fetched this session with a declared
   User-Agent; returns 403 without one). It lists exactly 82 quarterly ZIP
   links covering 2006q1 through 2026q2 at build time, named
   {yyyy}q{n}_form345.zip. All quarters up to 2026q1 live under
   /files/structureddata/data/insider-transactions-data-sets/ ; the newest
   (2026q2) lives under /files/datastandardsinnovation/data/
   insider-transactions-data-sets/ -- fetch_quarter_zip tries both
   prefixes rather than assuming either. NOTE the coverage END is a
   liveness observation (SEC appends a quarter each publication cycle);
   the START (2006q1) and the naming scheme are what this module depends
   on. The data sets are published QUARTERLY, so the last ~1-3 months of
   filings are structurally absent from any run -- disclosed per run, not
   silently ignored.
 * README: https://www.sec.gov/files/insider_transactions_readme.pdf
   (fetched and read this session, 7 pages): each ZIP holds 8 TSV tables
   ("text format, tab delimited, UTF-8"): SUBMISSION (ACCESSION_NUMBER,
   FILING_DATE in DD-MON-YYYY, DOCUMENT_TYPE in {3,4,5,3/A,4/A,5/A},
   ISSUERCIK, ISSUERTRADINGSYMBOL, ...), REPORTINGOWNER (ACCESSION_NUMBER,
   RPTOWNERCIK, RPTOWNER_RELATIONSHIP in
   OFFICER/DIRECTOR/TENPERCENTOWNER/OTHER, ...), NONDERIV_TRANS
   (TRANS_DATE, TRANS_CODE, TRANS_SHARES, TRANS_PRICEPERSHARE,
   TRANS_ACQUIRED_DISP_CD, ...), NONDERIV_HOLDING, DERIV_TRANS,
   DERIV_HOLDING, FOOTNOTES, OWNER_SIGNATURE. The readme's own Trans Code
   List: P = "Open market or private purchase of non-derivative or
   derivative security", S = "Open market or private sale of
   non-derivative or derivative security" -- note SEC's single code P
   CANNOT separate open-market from private purchases, a real deviation
   from the paper (which excluded private transactions via Thomson's
   richer coding), disclosed here because it is unfixable with this data.
 * REAL FILES INSPECTED (2006q1, 2016q1, 2024q1 downloaded and parsed
   this session): headers match the readme with two deltas the parser
   handles by selecting columns BY NAME: (a) the real header spells
   FORM3_HOLDINGS_REPORTED (readme: FORM3_HOLDING_REPORTED); (b) newer
   SUBMISSION files carry an extra AFF10B5ONE column (the ZIP's own
   metadata: "The transaction was made pursuant to a contract, instruction
   or written plan ... intended to satisfy the affirmative defense
   conditions of Rule 10b5-1(c)") absent in 2006q1/2016q1. Measured on
   2024q1: 67,671 submissions, of which 61,366 are DOCUMENT_TYPE '4';
   13,257 Form 4s for this project's 500 CIK-resolved universe tickers;
   111,404 NONDERIV_TRANS rows; 10,833 owner-joined P/S rows for the
   universe (893 P vs 9,940 S -- large-cap insiders overwhelmingly SELL,
   the single biggest sample-thinness fact about this family's long-buys
   design, disclosed in the run disclosure).
 * FAIR ACCESS: https://www.sec.gov/os/accessing-edgar-data re-fetched
   this session (it redirects; the served page states verbatim "Current
   max request rate: 10 requests/second" and "Please declare your user
   agent in request headers", sample "User-Agent: Sample Company Name
   AdminContact@<sample company domain>.com"). This module sends
   INSIDER_SEC_USER_AGENT on every request and sleeps
   INSIDER_SEC_MIN_REQUEST_INTERVAL_SECONDS between quarterly downloads
   (~2 req/s worst case, far under the cap; each request is one large
   file, which is also what SEC's "use efficient scripting. Download only
   what you need" guidance favors over per-filing crawling). The UA
   contact token is the same explicitly non-routable placeholder as the
   PEAD module's, for the same documented reason (this project's rules
   forbid embedding the operator's personal email in request headers).

============================================================================
SIGNAL DEFINITION AND TIMING -- POINT-IN-TIME BY CONSTRUCTION
============================================================================
CLASSIFICATION (classify_owner_year): at the start of each calendar year
Y, each (owner CIK, issuer CIK) pair is labelled from the P/S
non-derivative Form 4 trades FILED strictly before Jan 1 of Y (a trade
the market could not yet see cannot inform a label -- the paper's
Thomson data has the same property implicitly since it classifies from
reported trades):
  - CLASSIFIABLE requires >=1 visible trade with TRANS_DATE in each of
    calendar years Y-3, Y-2, Y-1 (the paper's "at least one trade in each
    of the three preceding years").
  - ROUTINE if any calendar month m has visible trades in >=3 consecutive
    years anywhere in the past (the Exhibit A1 reading, sticky).
  - OPPORTUNISTIC = classifiable and not routine. Everyone else is
    UNCLASSIFIED and their trades are ignored, exactly as the paper's
    main design ignores non-classified trades.
The pair level (owner x issuer) is a deliberate, disclosed reading: the
paper says "for each insider, we analyze her past trading history"
without specifying whether a person's trades at a second firm feed the
first firm's pattern; per-pair is the conservative choice available in
this data (most insiders file at one issuer).

EVENTS (build_buy_events): one candidate event per (ticker, entry row) --
two after-close/weekend filing dates mapping to the same next trading row
merge into one event -- holding >=1 open-market-coded BUY row (TRANS_CODE 'P' and
TRANS_ACQUIRED_DISP_CD 'A') by an owner labelled OPPORTUNISTIC for the
FILING year (the label in force when the information became public).
Gates, all tradeability/data facts, all counted: point-in-time S&P 500
membership at the filing date (was_member -- same gate and same
survivorship caveat as the PEAD family); filing delay
(filing_date - trans_date) <= 30 calendar days (a stale late-filed trade
is not a "fresh buy"; the paper's median delay is 3 days); filing within
the formation window.

ENTRY is at the close of the FIRST TRADING ROW STRICTLY AFTER the filing
date. The structured data carries no intraday acceptance timestamp (the
PEAD family's EDGAR submissions API does; this data set does not), so the
conservative after-close rule is applied to EVERY event: a filing dated D
is assumed visible only after D's close, never before. The error
direction is a strictly LATER entry, never an entry before the
information was public. First realized return is the following row.

CLUSTERING: an event's cluster count is the number of DISTINCT Form 4
accessions containing a qualifying opportunistic buy of the same ticker
whose entry rows fall within the trailing
INSIDER_CLUSTER_WINDOW_TRADING_DAYS (21) rows ending at the event's own
entry row (all of them public by then). Distinct ACCESSIONS, not distinct
owner CIKs, deliberately: a single joint Form 4 lists several related
reporting owners (1,473 multi-owner accessions in 2024q1 alone, measured)
and counting each as an independent buyer would manufacture "clusters"
out of one economic trade. min_cluster_buys=1 admits every opportunistic
buy (the paper's own design); min_cluster_buys=2 is the pre-declared
signal-strength variant (entry triggers on the event that completes the
cluster, never retroactively).

THE BOOK: every entered event opens 1.0 of leg notional long at its entry
close, held spec.holding_days trading rows (truncated at the data's end,
closed early on delisting with the Shumway imputation -- which for a LONG
is a LOSS, the conservative direction -- or superseded by a newer entered
event on the same ticker, exactly the PEAD convention). The long leg is
hedged 1:1 with SPY: daily net = weighted long-leg return minus SPY
return. WITHOUT the hedge a long-only book's Sharpe would be mostly the
equity market's own, and the family would be testing beta, not the
anomaly; the paper's headline numbers are likewise abnormal
(risk-adjusted) returns, not raw longs. SPY (not single-name shorts) is
what makes a long-informed-buys strategy implementable without the
borrow-rate data this project does not have. Days with no open event are
0.0 -- flat, counted, never dropped.

============================================================================
FAMILY SIZE -- 8, FIXED AND ASSERTED BEFORE ANY RUN
============================================================================
2 holding periods {21, 63 trading days} x 2 cluster minima {1, 2} x 2 leg
weightings {equal, inverse_vol} = 8. INSIDER_N_TRIALS is asserted against
the built list in _build_insider_family, so a size drift is a loud
import-time failure, not a silent DSR-denominator change. 8 >=
deflated_sharpe.MIN_TRIALS_FOR_DSR (5). 21 days is the paper's own
hold-over-the-following-month convention; 63 days sits inside the
six-months-then-plateau horizon its Figure 1 documents (quoted above).
The weightings are the harness's own two non-signal modes (the paper
reports equal- and value-weighted; this project's point-in-time
market-cap machinery lives in the periodic harness, not here, so
inverse_vol stands in as the second weighting exactly as it does in the
PEAD family). Cluster window (21 rows), filing-delay gate (30 days),
benchmark (SPY), entry timing and the classification thresholds (3
preceding years / 3 consecutive same-month years -- the paper's own
numbers, not free parameters) are fixed constants, not axes.

============================================================================
COSTS
============================================================================
 * ROUND TRIP: 4 x cross_sectional.DEFAULT_XS_COST_BPS = 20bp per unit of
   event notional, charged in full on the event's first realized day:
   entry+exit of the stock (2 x 5bp) PLUS entry+exit of a matched SPY
   hedge increment (2 x 5bp) -- deliberately charging the hedge at the
   full single-name equity constant although SPY's true cost is far
   lower, and as if each event's hedge were traded separately although a
   real book would net hedge flows. Both simplifications overstate cost.
 * FINANCING: 0.0bp/yr by default, the equity families' shared
   convention. The usual short-borrow-optimism disclosure is genuinely
   WEAKER here than in the sibling families: the only short is SPY,
   which really does trade near zero specialness, unlike their
   adversely-selected single-name short legs.
 * Daily renormalization as events enter/leave is NOT charged -- the
   harness's stated zero-cost-rebalancing convention, kept and disclosed.

============================================================================
THE HONEST PRIOR IS MODEST, FOR STATED REASONS
============================================================================
 1. WRONG SIDE, BY NECESSITY: the paper attributes over half the
    improvement to opportunistic SELLS (quoted above); this family can
    only trade buys.
 2. LARGE CAPS: the whole universe is S&P 500 members, where insider
    BUYS are rare (893 P rows vs 9,940 S rows in the measured quarter)
    and prices are the most arbitraged on earth; the paper's own sample
    is all of CRSP, 1986-2007.
 3. POST-PUBLICATION: the paper was published in 2012; this sample is
    2015-2026. Post-publication attenuation of published anomalies is a
    widely documented pattern (not independently re-verified this
    session, flagged as such).
 4. THIN LONG LEG: with a handful of qualifying buys per month across
    500 large caps, the book is often 1-3 names against SPY --
    idiosyncratic variance will dominate many holds.
An honest negative is the expected outcome and is fine; this project has
shipped many already.

============================================================================
KNOWN LIMITS
============================================================================
 * SURVIVORSHIP UNIVERSE: events are sourced for TODAY's S&P 500
   snapshot then gated by point-in-time membership -- names that LEFT the
   index before the snapshot are absent entirely (same closure-needs-paid-
   data situation as every equity family here). For a LONG-buys family
   the missing departed names are ones insiders may have bought on the
   way down; the direction of the bias is not signed a priori and is
   disclosed rather than guessed at.
 * CODE P INCLUDES PRIVATE PURCHASES (readme wording quoted above);
   the paper excluded private transactions. Not separable in this data.
 * OWNER-LEVEL AGGREGATION: joint filings list several owner CIKs for
   one economic trade; classification treats each listed owner's history
   independently (their filed history IS their history), while
   clustering counts accessions to avoid manufacturing clusters.
 * QUARTERLY PUBLICATION LAG: filings after the last published quarter's
   end simply do not exist in this data yet; every run reports its real
   last-covered date.
 * NO DOLLAR-SIZE FLOOR: the paper's main tests impose none, so none is
   imposed here; TRANS_SHARES x TRANS_PRICEPERSHARE is carried in the
   cache for later analysis but never filters an event.
 * AMENDMENTS EXCLUDED: only DOCUMENT_TYPE '4' rows are used (never
   4/A), matching the PEAD family's amendments-are-not-the-announcement
   convention; Form 5s (annual, late/exempt reporting) are excluded
   because the paper's data "are drawn from these Form 4 filings".
 * OVERLAPPING HOLDS: consecutive daily returns share constituents at 63-
   day holds; the daily observation count overstates independent
   information, exactly as the sibling disclosures state.
 * DUAL-CLASS TICKERS COLLAPSE TO ONE (found by the independent
   verification pass, 2026-08-28): fetch_insider_trades keys its universe
   map by ISSUER CIK, and FOX/FOXA, GOOG/GOOGL and NWS/NWSA are three
   issuers filing one Form 4 each, not six. All 503 SCREENING_UNIVERSE
   tickers do resolve to a CIK (unresolved_tickers is empty); 500 is the
   distinct-ISSUER count, and the disclosure now says so rather than
   implying three lookups failed. Every trade at such an issuer is priced
   with whichever class the map kept, so the two share classes' returns
   are treated as one -- economically negligible for these three pairs,
   disclosed rather than silently absorbed.
 * THE ROUTINE SHARE HERE IS MUCH HIGHER THAN THE PAPER'S (measured by
   the independent verification pass, 2026-08-28, on the real cached
   data): of the P/S trades filed 2015-2026 that this rule CAN classify,
   78.2% are by routine traders and 21.8% by opportunistic ones. The
   paper's own sample splits 55%/45% BY TRADE -- quoted: "Overall, trades
   made by routine traders comprise 55% of the total sample, while trades
   made by opportunistic traders represent 45% of the total sample" (its
   Table I gives 54.81%/45.19% of all trades and 64.44%/35.56% of
   purchases). Counted per insider-YEAR decision rather than per trade
   this implementation is 50.4%/49.6% (9,264/9,133) -- an even split, but
   NOT on the paper's unit. The published text never characterises its
   split as "roughly 50/50" at all (that phrasing appears only in the
   2010 NBER working-paper version, w16454), so an even insider-year
   split here must not be reported as reproducing the paper. Two things
   drive the gap and neither is a defect: (a) the universe is S&P 500
   large caps in the 10b5-1 era,
   where programmatic executive selling dominates far more than in the
   paper's 1986-2007 whole-CRSP sample; (b) the Exhibit A1 "run anywhere
   in the past", sticky reading labels routine more readily than a strict
   most-recent-three-years reading would (re-measured under that stricter
   reading: 64.7%/35.3% by trade). The direction is CONSERVATIVE for this
   family -- a larger routine bucket means a smaller, stricter
   opportunistic bucket, which is the only one it trades.
 * ROUTINE IS STICKY ONLY WHILE THE INSIDER STAYS CLASSIFIABLE: the paper
   says a routine label survives "regardless of what trading behavior (or
   lack of trading behavior) takes place after", but classify_owner_year
   applies the three-preceding-years classifiability gate FIRST, so an
   insider who went routine and then stopped trading for three years
   returns UNCLASSIFIED rather than ROUTINE. Both labels are excluded
   from this family's events, so the deviation cannot move a trade into
   the traded bucket -- it only affects the routine/opportunistic
   bookkeeping above.
 * FILER TYPOS IN THE RAW SEC DATA (counted 2026-08-28 on the cached
   653,424 rows): 31 rows carry a TRANS_DATE before 2000 (one reads year
   0015) and 82 carry a TRANS_DATE AFTER their own FILING_DATE, 7 of them
   P/A buys. The data is published "as-filed" and these are registrant
   errors, not parse failures. Neither can create look-ahead: entry is
   keyed off FILING_DATE alone, and classify_owner_year's visible-history
   filter already requires trans_date < the classification cutoff.

============================================================================
WHAT THE 2026-08-28 PRODUCTION RUN FOUND -- see the persisted rows
============================================================================
Run: formation 2015-01-07..2026-06-30 (the last date the published
quarterly data covers), classification history 2006q1 onward, persisted
to cross_sectional_trial_results (family_key='insider_opportunistic'),
which is the authoritative record of the numbers. The result prose
deliberately lives in the persisted rows and the session report, not
here, so this docstring cannot silently drift from the record. The rows
committed to the main database carry
run_tag='insider_form4_verified_2026-08-28' -- they are the INDEPENDENT
VERIFICATION pass's own re-run from the cached SEC data, which reproduced
the build run's eight Sharpes to four decimal places.

============================================================================
WHAT THE INDEPENDENT VERIFICATION PASS CHECKED (2026-08-28)
============================================================================
Re-derived from primary sources, not from the build session's report:
 * THE PAPER, re-fetched independently -- the same DASH copy cited above
   (item 73120379-15cc-6bd4-e053-0100007fdf3b at handle 1/33785679, file
   "cohen,malloy,pomorski_decoding-inside-information.pdf", 82 pages),
   cross-read against NBER w16454 and the AFA-hosted Internet Appendix.
   EVERY quotation in this docstring appears verbatim in that DASH copy:
   the classification rule, Exhibit A1's Bob example, the 82bp/t=2.15 and
   180bp/t=6.07 headlines, the routine -20bp/t=-0.57, the "over half ...
   comes from the superior performance of opportunistic sells"
   attribution, the "we exclude options exercises and private
   transactions" data note, the monthly formation convention, the
   six-months-then-level-off event-time shape, the 98bp/t=12.25
   modified-approach buy figure, and the "appear to more closely resemble
   opportunistic trades" note. Two of those (98bp/t=12.25 and the
   "resemble" note) are in the PUBLISHED text only and are absent from
   the 2010 working paper -- worth knowing before checking quotes against
   the freely-downloadable NBER PDF and concluding anything.
 * THE SEC PAGE, re-fetched: exactly 82 quarterly ZIPs, 2006q1-2026q2,
   81 under structureddata/ and 2026q2 under datastandardsinnovation/ --
   as documented. The readme's "P Open market or private purchase..."
   wording is verbatim, and NONDERIV_TRANS carries no field that could
   separate the two, so that limitation is real and unavoidable here.
 * CLASSIFICATION: twelve hand-worked cases, including Exhibit A1 and
   traps the rule must not fall into (repeat trades in one month must not
   fake a three-year run; same-month-but-non-consecutive years must not
   be routine; a trade filed after the cutoff must be invisible). All
   correct.
 * LOOK-AHEAD, audited against the raw cache rather than the module's own
   bookkeeping: all 321 entered events have an entry date strictly after
   a REAL SEC filing date, on a real trading row, and on exactly the
   FIRST such row -- 0 violations on all four criteria, entry-minus-filing
   gap 1 to 4 calendar days. Four filing dates were then confirmed
   against live EDGAR filing indexes (CINF/CCL/SPG/INTC), matching both
   FILING_DATE and period-of-report.
 * THE TEST SUITE is not vacuous: sixteen deliberate mutations (entry on
   the filing day, entry a row early, classify from trans_date instead of
   filing_date, 2-year thresholds, non-consecutive runs, inverted labels,
   sells leaking in, unbounded/forward-looking cluster windows, hedge
   removed, gates disabled, n_trials shrunk) are all caught.

FIXES MADE BY THAT PASS, all documented above at their sites:
 1. test_inverse_vol_weights_use_the_entry_row_basis asserted only that
    the weight fallback never fired, so a mutant reading the CURRENT
    row's basis instead of the entry row's survived the whole suite --
    the test's name promised more than it checked. Split in two, with a
    new test that pins the entry-row convention by construction.
 2. The sample disclosure said "503 tickers, 500 CIK-resolved", which
    reads as three failed lookups. All 503 resolve; 500 is the distinct-
    ISSUER count, because three dual-class pairs share an issuer CIK.
    Reworded, and the collapse is now a KNOWN LIMIT.
 3. The build session's fidelity check ("~50/50 routine/opportunistic,
    matching the paper") was measured per insider-YEAR; the paper's
    split is stated per TRADE (55%/45%), and per trade this rule gives
    78.2%/21.8%. The published text never says "roughly 50/50" at all.
    Both numbers, the reasons for the gap, and the fact that the
    deviation is conservative are now a KNOWN LIMIT.
No result changed: the family was an honest negative before these fixes
and is an honest negative after them.
"""

import gzip
import io
import itertools
import logging
import time
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    DEFAULT_IMPUTED_DELISTING_RETURN,
    DEFAULT_XS_COST_BPS,
    FINANCING_DAYS_PER_YEAR,
    MIN_REPLAY_TRADING_DAYS,
    _compute_delisting_positions,
    _leg_weighted_return,
    _resolve_leg_weights,
)
from app.services.research_lab.cross_sectional_pead import load_cik_map
from app.services.research_lab.deflated_sharpe import (
    DeflatedSharpeResult,
    compute_deflated_sharpe,
)
from app.services.research_lab.metrics import sharpe_ratio
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    was_member,
)
from app.services.research_lab.ticker_universe import SCREENING_UNIVERSE

logger = logging.getLogger(__name__)

# --- the family's fixed axes ----------------------------------------------

# 21 = the paper's own hold-over-the-following-month convention; 63 sits
# inside the ~6-months-then-plateau horizon of its Figure 1 (docstring).
INSIDER_HOLDING_DAYS: tuple[int, ...] = (21, 63)

# 1 = every opportunistic buy (the paper's design); 2 = the pre-declared
# clustering variant (>=2 distinct buy accessions in the trailing window).
INSIDER_MIN_CLUSTER_BUYS: tuple[int, ...] = (1, 2)

# The harness's OWN leg-weighting modes (cross_sectional.
# _resolve_leg_weights) -- identical reuse to the PEAD family.
INSIDER_LEG_WEIGHTINGS: tuple[str, ...] = ("equal", "inverse_vol")

# 2 x 2 x 2, asserted against the built list in _build_insider_family.
INSIDER_N_TRIALS = (
    len(INSIDER_HOLDING_DAYS)
    * len(INSIDER_MIN_CLUSTER_BUYS)
    * len(INSIDER_LEG_WEIGHTINGS)
)

INSIDER_CITATION = (
    "Cohen, Malloy & Pomorski, 'Decoding Inside Information' (The Journal of Finance, 67(3), "
    "2012, pp. 1009-1043, DOI 10.1111/j.1540-6261.2012.01740.x; full text retrieved from Harvard "
    "DASH and read 2026-08-28). Data: SEC Insider Transactions Data Sets (structured quarterly "
    "Form 3/4/5 TSV files, sec.gov, coverage 2006q1+, page and readme verified live 2026-08-28)"
)

INSIDER_FAMILY_NAME = "insider_opportunistic"

# --- fixed design constants (NOT family axes -- see module docstring) -----

# The paper's own classification thresholds ("at least one trade in each
# of the three preceding years"; "the same calendar month for at least
# three consecutive years") -- verified quotes in the module docstring.
# These are the paper's numbers, not free parameters of this family.
CLASSIFY_MIN_HISTORY_YEARS = 3
ROUTINE_CONSECUTIVE_YEARS = 3

# Trailing window (trading rows, ending at the event's own entry row) in
# which distinct buy accessions are counted for the cluster axis. ~1
# calendar month -- the granularity of the paper's own monthly formation.
INSIDER_CLUSTER_WINDOW_TRADING_DAYS = 21

# A buy filed more than this many calendar days after its transaction date
# is not a "fresh buy" and never enters (still feeds classification
# history). The paper's median trade-to-report delay is 3 days (quoted).
INSIDER_MAX_FILING_DELAY_CALENDAR_DAYS = 30

# Trailing inverse-vol basis: same 63-row/40-obs convention as the PEAD
# and index-removal families (restated, not imported, for the same
# documented coupling reason both siblings give).
INSIDER_VOL_WINDOW_DAYS = 63
INSIDER_VOL_MIN_PERIODS = 40

# Calendar days of prices fetched before the formation start, purely to
# warm the inverse-vol basis (63 rows + margin). No event enters early.
INSIDER_WARMUP_PADDING_CALENDAR_DAYS = 270

INSIDER_BENCHMARK_TICKER = "SPY"

# --- costs ----------------------------------------------------------------

# Stock entry+exit PLUS a matched SPY hedge entry+exit, all four one-way
# trades at the harness's own equity constant (see docstring COSTS -- the
# hedge legs are deliberately overcharged).
INSIDER_ROUND_TRIP_BPS = 4.0 * DEFAULT_XS_COST_BPS

# --- SEC data set access (all verified live 2026-08-28; see docstring) ----

# 2026q1 and earlier live under structureddata/; the newest quarter under
# datastandardsinnovation/ -- both observed on the live page this session.
SEC_INSIDER_ZIP_URL_TEMPLATES = (
    "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{quarter}_form345.zip",
    "https://www.sec.gov/files/datastandardsinnovation/data/insider-transactions-data-sets/{quarter}_form345.zip",
)

# Earliest quarter published (verified: the live page's oldest link).
INSIDER_DATA_FIRST_QUARTER = "2006q1"

# Same declared-UA convention and non-routable placeholder contact as the
# PEAD module, for the same documented reasons.
INSIDER_SEC_USER_AGENT = "Aladdin2ResearchLab/0.1 research-contact@aladdin2-project.local"

# One quarterly ZIP (5-18MB measured) per request: 0.5s between requests
# is ~2 req/s worst case, far under SEC's published 10 req/s cap.
INSIDER_SEC_MIN_REQUEST_INTERVAL_SECONDS = 0.5

# On-disk cache of the PARSED, universe-filtered trade rows (not the raw
# ZIPs), following the PEAD event-cache convention: a committed cache
# makes the production run reproducible without re-hitting SEC.
INSIDER_TRADES_CACHE_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "insider_form4_trades.csv.gz"
)


@dataclass(frozen=True)
class InsiderSpec:
    """One pre-declared definition. Deliberately NOT a
    cross_sectional.CrossSectionalSpec, for the identical reason the PEAD
    and index-removal families give: that type's required fields describe
    a periodic universe-scan and placeholders would misdescribe an
    event-driven trade."""

    pattern_id: str
    family: str
    citation: str
    holding_days: int
    min_cluster_buys: int
    leg_weighting: str  # "equal" | "inverse_vol"


def _build_insider_family() -> list[InsiderSpec]:
    specs: list[InsiderSpec] = []
    for hold in INSIDER_HOLDING_DAYS:
        for min_buys in INSIDER_MIN_CLUSTER_BUYS:
            for weighting in INSIDER_LEG_WEIGHTINGS:
                specs.append(
                    InsiderSpec(
                        pattern_id=(
                            f"insider_opp_buy_h{hold}_c{min_buys}_{weighting}"
                        ),
                        family=INSIDER_FAMILY_NAME,
                        citation=INSIDER_CITATION,
                        holding_days=hold,
                        min_cluster_buys=min_buys,
                        leg_weighting=weighting,
                    )
                )
    assert len(specs) == INSIDER_N_TRIALS, (
        f"Insider family has {len(specs)} definitions, not the pre-declared "
        f"{INSIDER_N_TRIALS} -- this family's entire point is being an exact, fixed enumeration "
        "of holding_days x min_cluster_buys x leg_weighting (see module docstring); a size drift "
        "here silently changes n_trials for every future run."
    )
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    assert all(s.family == INSIDER_FAMILY_NAME for s in specs)
    assert {s.holding_days for s in specs} == set(INSIDER_HOLDING_DAYS)
    assert {s.min_cluster_buys for s in specs} == set(INSIDER_MIN_CLUSTER_BUYS)
    assert {s.leg_weighting for s in specs} == set(INSIDER_LEG_WEIGHTINGS)
    return specs


INSIDER_FAMILY: list[InsiderSpec] = _build_insider_family()


@dataclass
class InsiderConfig:
    """Market conventions, split from the specs exactly as the sibling
    families split them."""

    round_trip_bps: float = INSIDER_ROUND_TRIP_BPS
    financing_bps_per_year: float = 0.0
    # ON by default: a held long that dies mid-hold takes the Shumway
    # imputation as a LOSS -- the conservative direction for this family.
    impute_delisting_returns: bool = True
    imputed_delisting_return: float = DEFAULT_IMPUTED_DELISTING_RETURN


# --- SEC quarterly data acquisition ---------------------------------------


@dataclass(frozen=True)
class InsiderTrade:
    """One non-derivative P/S transaction row from one Form 4 (DOCUMENT_
    TYPE '4' only), joined to its filing and one reporting owner. shares /
    price_per_share may be NaN (nullable in the real data)."""

    ticker: str
    issuer_cik: int
    owner_cik: int
    accession: str
    trans_date: date
    filing_date: date
    trans_code: str  # "P" | "S"
    acquired_disposed: str  # "A" | "D"
    shares: float
    price_per_share: float


@dataclass
class InsiderFetchReport:
    """What the SEC pass actually covered -- required output, because
    every gap here is a sample-construction fact."""

    quarters_requested: list[str] = field(default_factory=list)
    quarters_fetched: list[str] = field(default_factory=list)
    quarters_failed: list[str] = field(default_factory=list)
    n_tickers_requested: int = 0
    n_tickers_cik_resolved: int = 0
    unresolved_tickers: list[str] = field(default_factory=list)
    n_raw_ps_rows: int = 0


def quarter_labels(first: str, last: str) -> list[str]:
    """['2006q1', ..., last] inclusive. Labels are the SEC page's own
    naming scheme (verified live)."""
    fy, fq = int(first[:4]), int(first[5])
    ly, lq = int(last[:4]), int(last[5])
    labels: list[str] = []
    y, q = fy, fq
    while (y, q) <= (ly, lq):
        labels.append(f"{y}q{q}")
        q += 1
        if q == 5:
            y, q = y + 1, 1
    return labels


def fetch_quarter_zip(
    quarter: str, user_agent: str = INSIDER_SEC_USER_AGENT
) -> bytes:
    """One quarter's ZIP, trying both live URL prefixes (see docstring).
    Raises on failure at BOTH -- the caller records and continues."""
    last_error: Exception | None = None
    for template in SEC_INSIDER_ZIP_URL_TEMPLATES:
        url = template.format(quarter=quarter)
        request = urllib.request.Request(url, headers={"User-Agent": user_agent})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except Exception as exc:  # noqa: BLE001 -- try the other prefix
            last_error = exc
    raise RuntimeError(f"both URL prefixes failed for {quarter}: {last_error}")


def parse_quarter_zip(
    zip_bytes: bytes, universe_ciks: dict[int, str]
) -> list[InsiderTrade]:
    """Universe-filtered P/S non-derivative Form 4 rows from one quarterly
    ZIP. Columns are selected BY NAME (usecols), which is what makes the
    2006-vs-2024 header drift (AFF10B5ONE added, FORM3_HOLDINGS spelling)
    a non-event -- both real variants were inspected this session.
    DOCUMENT_TYPE '4' only: never amendments (4/A), never Forms 3/5."""
    archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    submissions = pd.read_csv(
        archive.open("SUBMISSION.tsv"),
        sep="\t",
        dtype=str,
        usecols=["ACCESSION_NUMBER", "FILING_DATE", "DOCUMENT_TYPE", "ISSUERCIK"],
    )
    submissions["issuer_cik"] = pd.to_numeric(
        submissions["ISSUERCIK"], errors="coerce"
    ).astype("Int64")
    form4 = submissions[
        (submissions["DOCUMENT_TYPE"] == "4")
        & submissions["issuer_cik"].isin(universe_ciks.keys())
    ]
    if form4.empty:
        return []

    transactions = pd.read_csv(
        archive.open("NONDERIV_TRANS.tsv"),
        sep="\t",
        dtype=str,
        usecols=[
            "ACCESSION_NUMBER",
            "TRANS_DATE",
            "TRANS_CODE",
            "TRANS_SHARES",
            "TRANS_PRICEPERSHARE",
            "TRANS_ACQUIRED_DISP_CD",
        ],
    )
    ps = transactions[transactions["TRANS_CODE"].isin(["P", "S"])]
    merged = ps.merge(
        form4[["ACCESSION_NUMBER", "FILING_DATE", "issuer_cik"]],
        on="ACCESSION_NUMBER",
    )
    if merged.empty:
        return []

    owners = pd.read_csv(
        archive.open("REPORTINGOWNER.tsv"),
        sep="\t",
        dtype=str,
        usecols=["ACCESSION_NUMBER", "RPTOWNERCIK"],
    )
    owners["owner_cik"] = pd.to_numeric(
        owners["RPTOWNERCIK"], errors="coerce"
    ).astype("Int64")
    merged = merged.merge(
        owners[["ACCESSION_NUMBER", "owner_cik"]], on="ACCESSION_NUMBER"
    )
    merged = merged.dropna(subset=["owner_cik", "TRANS_DATE", "FILING_DATE"])

    # DD-MON-YYYY, the readme's stated format, verified on real rows.
    trans_dates = pd.to_datetime(merged["TRANS_DATE"], format="%d-%b-%Y", errors="coerce")
    filing_dates = pd.to_datetime(merged["FILING_DATE"], format="%d-%b-%Y", errors="coerce")
    shares = pd.to_numeric(merged["TRANS_SHARES"], errors="coerce")
    prices = pd.to_numeric(merged["TRANS_PRICEPERSHARE"], errors="coerce")

    trades: list[InsiderTrade] = []
    for i in range(len(merged)):
        td = trans_dates.iloc[i]
        fd = filing_dates.iloc[i]
        if pd.isna(td) or pd.isna(fd):
            continue
        issuer = int(merged["issuer_cik"].iloc[i])
        trades.append(
            InsiderTrade(
                ticker=universe_ciks[issuer],
                issuer_cik=issuer,
                owner_cik=int(merged["owner_cik"].iloc[i]),
                accession=str(merged["ACCESSION_NUMBER"].iloc[i]),
                trans_date=td.date(),
                filing_date=fd.date(),
                trans_code=str(merged["TRANS_CODE"].iloc[i]),
                acquired_disposed=str(merged["TRANS_ACQUIRED_DISP_CD"].iloc[i]),
                shares=float(shares.iloc[i]) if pd.notna(shares.iloc[i]) else float("nan"),
                price_per_share=float(prices.iloc[i]) if pd.notna(prices.iloc[i]) else float("nan"),
            )
        )
    return trades


def fetch_insider_trades(
    tickers: list[str],
    quarters: list[str],
    user_agent: str = INSIDER_SEC_USER_AGENT,
    min_request_interval: float = INSIDER_SEC_MIN_REQUEST_INTERVAL_SECONDS,
) -> tuple[list[InsiderTrade], InsiderFetchReport]:
    """One rate-limited download per quarter, parsed and filtered to the
    universe's issuer CIKs. A failed quarter is recorded and skipped --
    a REAL sample gap the disclosure reports, never silently retried."""
    report = InsiderFetchReport(
        quarters_requested=list(quarters), n_tickers_requested=len(tickers)
    )
    cik_map = load_cik_map(user_agent)
    # Keyed by CIK, so DUAL-CLASS PAIRS COLLAPSE: FOX/FOXA, GOOG/GOOGL and
    # NWS/NWSA each share one issuer CIK, and Form 4 reports the issuer,
    # not the share class. All 503 SCREENING_UNIVERSE tickers really do
    # resolve (verified 2026-08-28: unresolved_tickers is empty); the count
    # falls to 500 because 3 pairs are 3 issuers. n_tickers_cik_resolved is
    # therefore a DISTINCT-ISSUER count, which is what the disclosure calls
    # it -- see KNOWN LIMITS.
    universe_ciks: dict[int, str] = {}
    for ticker in tickers:
        cik = cik_map.get(ticker)
        if cik is None:
            report.unresolved_tickers.append(ticker)
        else:
            universe_ciks[cik] = ticker
    report.n_tickers_cik_resolved = len(universe_ciks)

    trades: list[InsiderTrade] = []
    last_request = 0.0
    for quarter in quarters:
        elapsed = time.monotonic() - last_request
        if elapsed < min_request_interval:
            time.sleep(min_request_interval - elapsed)
        last_request = time.monotonic()
        try:
            payload = fetch_quarter_zip(quarter, user_agent)
            quarter_trades = parse_quarter_zip(payload, universe_ciks)
        except Exception as exc:  # noqa: BLE001 -- record and continue
            logger.warning("insider data fetch failed for %s: %s", quarter, exc)
            report.quarters_failed.append(quarter)
            continue
        report.quarters_fetched.append(quarter)
        trades.extend(quarter_trades)
    report.n_raw_ps_rows = len(trades)
    return trades, report


_CACHE_COLUMNS = [
    "ticker",
    "issuer_cik",
    "owner_cik",
    "accession",
    "trans_date",
    "filing_date",
    "trans_code",
    "acquired_disposed",
    "shares",
    "price_per_share",
]


def save_trades_cache(
    trades: list[InsiderTrade],
    report: InsiderFetchReport,
    path: Path = INSIDER_TRADES_CACHE_PATH,
) -> None:
    """CSV.gz (not JSON like the PEAD cache: ~40x the row count). The
    fetch report rides along as a JSON sidecar comment line convention
    would be fragile, so it gets its own small .report.json file."""
    frame = pd.DataFrame(
        [
            {
                "ticker": t.ticker,
                "issuer_cik": t.issuer_cik,
                "owner_cik": t.owner_cik,
                "accession": t.accession,
                "trans_date": t.trans_date.isoformat(),
                "filing_date": t.filing_date.isoformat(),
                "trans_code": t.trans_code,
                "acquired_disposed": t.acquired_disposed,
                "shares": t.shares,
                "price_per_share": t.price_per_share,
            }
            for t in trades
        ],
        columns=_CACHE_COLUMNS,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        frame.to_csv(handle, index=False)
    sidecar = path.with_suffix(".report.json")
    sidecar.write_text(
        pd.Series(
            {
                "quarters_requested": report.quarters_requested,
                "quarters_fetched": report.quarters_fetched,
                "quarters_failed": report.quarters_failed,
                "n_tickers_requested": report.n_tickers_requested,
                "n_tickers_cik_resolved": report.n_tickers_cik_resolved,
                "unresolved_tickers": report.unresolved_tickers,
                "n_raw_ps_rows": report.n_raw_ps_rows,
            }
        ).to_json()
    )


def load_trades_cache(
    path: Path = INSIDER_TRADES_CACHE_PATH,
) -> tuple[list[InsiderTrade], InsiderFetchReport] | None:
    if not path.exists():
        return None
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        frame = pd.read_csv(handle, dtype={"trans_code": str, "acquired_disposed": str})
    trades = [
        InsiderTrade(
            ticker=str(row.ticker),
            issuer_cik=int(row.issuer_cik),
            owner_cik=int(row.owner_cik),
            accession=str(row.accession),
            trans_date=date.fromisoformat(row.trans_date),
            filing_date=date.fromisoformat(row.filing_date),
            trans_code=str(row.trans_code),
            acquired_disposed=str(row.acquired_disposed),
            shares=float(row.shares),
            price_per_share=float(row.price_per_share),
        )
        for row in frame.itertuples()
    ]
    report = InsiderFetchReport()
    sidecar = path.with_suffix(".report.json")
    if sidecar.exists():
        loaded = pd.read_json(sidecar, typ="series")
        report = InsiderFetchReport(
            quarters_requested=list(loaded["quarters_requested"]),
            quarters_fetched=list(loaded["quarters_fetched"]),
            quarters_failed=list(loaded["quarters_failed"]),
            n_tickers_requested=int(loaded["n_tickers_requested"]),
            n_tickers_cik_resolved=int(loaded["n_tickers_cik_resolved"]),
            unresolved_tickers=list(loaded["unresolved_tickers"]),
            n_raw_ps_rows=int(loaded["n_raw_ps_rows"]),
        )
    return trades, report


# --- the paper's classification rule --------------------------------------

ROUTINE = "routine"
OPPORTUNISTIC = "opportunistic"
UNCLASSIFIED = "unclassified"


def classify_owner_year(
    trades: list[InsiderTrade], year: int
) -> str:
    """One (owner, issuer) pair's label at the start of `year`, from the
    paper's own rule (docstring quotes):
      - visible history = trades FILED strictly before Jan 1 of `year`
        (point-in-time: an unfiled trade cannot inform a label);
      - CLASSIFIABLE requires >=1 visible trade with trans_date in each
        of years year-3, year-2, year-1;
      - ROUTINE if any calendar month has visible trades in >=
        ROUTINE_CONSECUTIVE_YEARS consecutive years ANYWHERE in the past
        (the Exhibit A1 'in the past' reading -- see docstring; the test
        suite replays the paper's own Bob example);
      - OPPORTUNISTIC = classifiable, not routine; else UNCLASSIFIED.
    The caller groups trades per (owner, issuer); this function does not
    re-check that."""
    cutoff = date(year, 1, 1)
    visible = [t for t in trades if t.filing_date < cutoff and t.trans_date < cutoff]
    if not visible:
        return UNCLASSIFIED
    years_traded = {t.trans_date.year for t in visible}
    required = {year - offset for offset in range(1, CLASSIFY_MIN_HISTORY_YEARS + 1)}
    if not required.issubset(years_traded):
        return UNCLASSIFIED

    years_by_month: dict[int, set[int]] = {}
    for t in visible:
        years_by_month.setdefault(t.trans_date.month, set()).add(t.trans_date.year)
    for month_years in years_by_month.values():
        run = 1
        for previous, current in itertools.pairwise(sorted(month_years)):
            run = run + 1 if current == previous + 1 else 1
            if run >= ROUTINE_CONSECUTIVE_YEARS:
                return ROUTINE
    return OPPORTUNISTIC


def build_owner_labels(
    trades: list[InsiderTrade], years: list[int]
) -> dict[tuple[int, int, int], str]:
    """{(owner_cik, issuer_cik, year): label} for every pair with any
    trade, for every requested year. Pairs whose label is UNCLASSIFIED
    are stored too -- the signal builder needs to COUNT ignored buys, not
    just skip them silently."""
    by_pair: dict[tuple[int, int], list[InsiderTrade]] = {}
    for t in trades:
        by_pair.setdefault((t.owner_cik, t.issuer_cik), []).append(t)
    labels: dict[tuple[int, int, int], str] = {}
    for (owner, issuer), pair_trades in by_pair.items():
        for year in years:
            labels[(owner, issuer, year)] = classify_owner_year(pair_trades, year)
    return labels


# --- signal construction ---------------------------------------------------


@dataclass(frozen=True)
class BuyEvent:
    """One (ticker, filing date) with >=1 qualifying opportunistic buy.
    entry_position is the first trading row STRICTLY AFTER the filing
    date -- the close at which the position is established (docstring:
    the conservative after-close rule, applied to every event because the
    structured data has no intraday acceptance timestamp).
    cluster_filings counts DISTINCT qualifying buy accessions for this
    ticker with entry rows in the trailing cluster window (self
    included)."""

    ticker: str
    filing_date: date
    entry_position: int
    entry_date: date
    cluster_filings: int


@dataclass
class SignalCounts:
    n_buy_rows: int = 0
    n_buys_by_routine: int = 0
    n_buys_by_unclassified: int = 0
    n_buys_by_opportunistic: int = 0
    n_dropped_not_member: int = 0
    n_dropped_stale_filing: int = 0
    n_dropped_outside_window: int = 0
    n_dropped_no_price_row: int = 0
    n_events: int = 0


def build_buy_events(
    trades: list[InsiderTrade],
    labels: dict[tuple[int, int, int], str],
    index: pd.DatetimeIndex,
    formation_start: date,
    formation_end: date,
    priced_tickers: set[str],
) -> tuple[list[BuyEvent], SignalCounts]:
    """Entry-ordered opportunistic-buy events from the raw trade rows.
    Every gate is a tradeability/data fact, counted, never a performance
    filter. The membership gate is point-in-time (was_member at the
    filing date, same as the PEAD family)."""
    counts = SignalCounts()
    # (ticker, entry_row) -> distinct qualifying buy accessions at that row.
    qualifying: dict[tuple[str, int], set[str]] = {}
    # (ticker, entry_row) -> latest real filing date mapping to that row
    # (two after-close/weekend filing dates can share one entry row).
    filing_by_key: dict[tuple[str, int], date] = {}
    for t in trades:
        if t.trans_code != "P" or t.acquired_disposed != "A":
            continue
        # Window first, so the label counts below describe IN-WINDOW buys
        # (the disclosure quotes them as the classification breakdown;
        # letting the pre-formation history years pollute "unclassified"
        # would misstate it).
        if not (formation_start <= t.filing_date <= formation_end):
            counts.n_dropped_outside_window += 1
            continue
        counts.n_buy_rows += 1
        label = labels.get((t.owner_cik, t.issuer_cik, t.filing_date.year), UNCLASSIFIED)
        if label == ROUTINE:
            counts.n_buys_by_routine += 1
            continue
        if label == UNCLASSIFIED:
            counts.n_buys_by_unclassified += 1
            continue
        counts.n_buys_by_opportunistic += 1
        if not was_member(t.ticker, t.filing_date):
            counts.n_dropped_not_member += 1
            continue
        if (t.filing_date - t.trans_date).days > INSIDER_MAX_FILING_DELAY_CALENDAR_DAYS:
            counts.n_dropped_stale_filing += 1
            continue
        if t.ticker not in priced_tickers:
            counts.n_dropped_no_price_row += 1
            continue
        ts = pd.Timestamp(t.filing_date)
        position = int(np.searchsorted(index.values, ts.to_datetime64(), side="right"))
        # Need at least one realized day after the entry close.
        if position >= len(index) - 1:
            counts.n_dropped_no_price_row += 1
            continue
        key = (t.ticker, position)
        qualifying.setdefault(key, set()).add(t.accession)
        prior = filing_by_key.get(key)
        if prior is None or t.filing_date > prior:
            filing_by_key[key] = t.filing_date

    # Cluster counting over entry rows, trailing window inclusive of the
    # event's own row -- all counted filings are public by the entry close.
    rows_by_ticker: dict[str, list[int]] = {}
    for ticker, position in qualifying:
        rows_by_ticker.setdefault(ticker, []).append(position)

    events: list[BuyEvent] = []
    for (ticker, position) in qualifying:
        floor = position - INSIDER_CLUSTER_WINDOW_TRADING_DAYS + 1
        cluster = 0
        for other in rows_by_ticker[ticker]:
            if floor <= other <= position:
                cluster += len(qualifying[(ticker, other)])
        events.append(
            BuyEvent(
                ticker=ticker,
                filing_date=filing_by_key[(ticker, position)],
                entry_position=position,
                entry_date=index[position].date(),
                cluster_filings=cluster,
            )
        )
    events.sort(key=lambda e: (e.entry_position, e.ticker))
    counts.n_events = len(events)
    return events, counts


def build_inverse_vol_basis(close: pd.DataFrame) -> pd.DataFrame:
    """1 / trailing realized volatility, aligned to `close` -- identical
    formula to the PEAD sibling (rolling ddof=1 std of daily returns,
    reciprocated, non-finite NaNed), restated with this family's own
    window constants. Point-in-time: a rolling std at row i reads only
    rows <= i, and the replay reads each event's basis at its OWN entry
    row."""
    returns = close.pct_change(fill_method=None)
    vol = returns.rolling(
        INSIDER_VOL_WINDOW_DAYS, min_periods=INSIDER_VOL_MIN_PERIODS
    ).std(ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        basis = 1.0 / vol
    return basis.replace([np.inf, -np.inf], np.nan)


# --- the replay ------------------------------------------------------------


@dataclass
class InsiderBacktestResult:
    status: str  # "ok" | "no_events" | "insufficient_history"
    daily_returns: pd.Series
    n_events_entered: int = 0
    n_events_superseded: int = 0
    n_events_delisted_mid_hold: int = 0
    total_cost: float = 0.0
    total_financing_cost: float = 0.0
    n_invested_days: int = 0
    n_uninvested_days: int = 0
    n_weight_fallback_days: int = 0
    mean_leg_size: float = 0.0


def run_insider_backtest(
    close: pd.DataFrame,
    benchmark: pd.Series,
    entered: list[BuyEvent],
    spec: InsiderSpec,
    config: InsiderConfig,
    basis: pd.DataFrame | None = None,
) -> InsiderBacktestResult:
    """One spec's event-driven replay: every entered event opens 1.0 of
    long-leg notional at its entry close, hedged 1:1 with the benchmark;
    daily net = leg-weighted long return minus benchmark return, minus
    costs. Exit after spec.holding_days trading rows, at the data's end,
    on delisting (Shumway imputation -- a LOSS for these longs), or by
    supersession from a newer entered event on the same ticker. Days with
    no open event are 0.0 (flat, counted). The caller has already
    filtered `entered` by the spec's min_cluster_buys."""
    if spec.leg_weighting == "inverse_vol" and basis is None:
        raise ValueError(
            f"{spec.pattern_id} has leg_weighting='inverse_vol' but no inverse-vol basis was "
            "supplied. Without it every day would silently take the fallback and the run would "
            "report itself as inverse-vol weighted while being equal weighted throughout."
        )
    if not entered:
        return InsiderBacktestResult(status="no_events", daily_returns=pd.Series(dtype=float))

    index = close.index
    n = len(index)
    first_entry = min(e.entry_position for e in entered)
    if first_entry >= n - 1:
        return InsiderBacktestResult(
            status="insufficient_history", daily_returns=pd.Series(dtype=float)
        )

    stock_returns = close.pct_change(fill_method=None)
    bench_returns = benchmark.reindex(index).pct_change(fill_method=None)
    round_trip = config.round_trip_bps / 10_000.0
    financing_per_day = (
        config.financing_bps_per_year / 10_000.0
    ) / FINANCING_DAYS_PER_YEAR

    delisting_by_position: dict[int, list[str]] = {}
    if config.impute_delisting_returns:
        for ticker, position in _compute_delisting_positions(close).items():
            delisting_by_position.setdefault(position, []).append(ticker)

    open_at: dict[int, list[BuyEvent]] = {}
    entry_basis: dict[tuple[str, int], float] = {}
    for event in entered:
        open_at.setdefault(event.entry_position, []).append(event)
        if basis is not None and event.ticker in basis.columns:
            entry_basis[(event.ticker, event.entry_position)] = float(
                basis[event.ticker].iloc[event.entry_position]
            )

    active: dict[str, BuyEvent] = {}
    exit_position: dict[str, int] = {}
    charged: set[str] = set()

    dates: list[pd.Timestamp] = []
    nets: list[float] = []
    total_cost = 0.0
    total_financing = 0.0
    n_invested = 0
    n_uninvested = 0
    n_fallback = 0
    n_superseded = 0
    n_delisted = 0
    leg_sizes: list[int] = []

    for j in range(first_entry + 1, n):
        for event in open_at.get(j - 1, ()):
            if event.ticker in active:
                n_superseded += 1
            active[event.ticker] = event
            exit_position[event.ticker] = min(
                event.entry_position + spec.holding_days, n - 1
            )
            charged.discard(event.ticker)

        if not active:
            n_uninvested += 1
            dates.append(index[j])
            nets.append(0.0)
            continue

        day = stock_returns.iloc[j]
        delisting_today = delisting_by_position.get(j)
        if delisting_today:
            hit = [t for t in delisting_today if t in active]
            if hit:
                day = day.copy()
                for ticker in hit:
                    day[ticker] = config.imputed_delisting_return
                n_delisted += len(hit)

        longs = sorted(active)
        # A day on which EVERY held name is missing a return (transient
        # data gap, or an unimputed delisting) is FLAT, not a naked short
        # SPY hedge: the long leg cannot be on, so neither is its hedge.
        # (_leg_weighted_return alone cannot distinguish "all missing"
        # from a genuine 0.0 leg return, hence the explicit check.)
        if day.reindex(longs).dropna().empty:
            n_uninvested += 1
            dates.append(index[j])
            nets.append(0.0)
            for ticker in list(active):
                if j >= exit_position[ticker] or (
                    delisting_today and ticker in delisting_today
                ):
                    del active[ticker]
                    del exit_position[ticker]
                    charged.discard(ticker)
            continue

        signal = pd.Series(0.0, index=longs, dtype=float)
        basis_row: pd.Series | None = None
        if spec.leg_weighting == "inverse_vol":
            basis_row = pd.Series(
                {
                    t: entry_basis.get((t, active[t].entry_position), np.nan)
                    for t in longs
                },
                dtype=float,
            )
        weights, used_fallback = _resolve_leg_weights(
            longs,
            signal,
            higher_is_stronger=True,
            leg_weighting=spec.leg_weighting,  # type: ignore[arg-type]
            market_cap=None,
            weight_basis=basis_row,
        )
        if used_fallback:
            n_fallback += 1

        bench_today = bench_returns.iloc[j]
        long_return = _leg_weighted_return(day, weights)
        hedge_return = float(bench_today) if np.isfinite(bench_today) else 0.0
        gross = long_return - hedge_return

        cost_today = 0.0
        for name, w in weights.items():
            if name not in charged:
                cost_today += w * round_trip
                charged.add(name)
        financing_today = 0.0
        if financing_per_day:
            calendar_days = float((index[j] - index[j - 1]).days)
            financing_today = financing_per_day * 2.0 * calendar_days

        net = gross - cost_today - financing_today
        total_cost += cost_today
        total_financing += financing_today
        n_invested += 1
        leg_sizes.append(len(longs))
        dates.append(index[j])
        nets.append(net)

        for ticker in list(active):
            if j >= exit_position[ticker] or (
                delisting_today and ticker in delisting_today
            ):
                del active[ticker]
                del exit_position[ticker]
                charged.discard(ticker)

    daily = pd.Series(nets, index=pd.DatetimeIndex(dates), dtype=float)
    return InsiderBacktestResult(
        status="ok",
        daily_returns=daily,
        n_events_entered=len(entered),
        n_events_superseded=n_superseded,
        n_events_delisted_mid_hold=n_delisted,
        total_cost=total_cost,
        total_financing_cost=total_financing,
        n_invested_days=n_invested,
        n_uninvested_days=n_uninvested,
        n_weight_fallback_days=n_fallback,
        mean_leg_size=float(np.mean(leg_sizes)) if leg_sizes else 0.0,
    )


# --- screening / DSR -------------------------------------------------------


@dataclass
class InsiderScreeningResult:
    pattern_id: str
    family: str
    citation: str
    holding_days: int
    min_cluster_buys: int
    leg_weighting: str
    n_events_entered: int
    n_events_superseded: int
    n_events_delisted_mid_hold: int
    n_trading_days: int
    n_invested_days: int
    n_uninvested_days: int
    invested_fraction: float
    mean_leg_size: float
    sharpe_annualized: float
    total_cost_drag: float
    total_financing_drag: float
    deflated_sharpe: DeflatedSharpeResult
    n_weight_fallback_days: int = 0


@dataclass(frozen=True)
class InsiderSampleDisclosure:
    """Sample-construction facts as typed data, recomputed from the real
    inputs on every run -- the sibling families' discipline."""

    quarters_fetched: int
    quarters_failed: int
    n_tickers_requested: int
    n_tickers_cik_resolved: int
    n_raw_ps_rows: int
    n_buy_rows: int
    n_buys_by_opportunistic: int
    n_buys_by_routine: int
    n_buys_by_unclassified: int
    n_dropped_not_member: int
    n_dropped_stale_filing: int
    n_events: int
    n_tickers_priced: int
    first_event_date: date | None
    last_event_date: date | None
    last_data_coverage_date: date | None
    text: str


def build_insider_sample_disclosure(
    report: InsiderFetchReport,
    counts: SignalCounts,
    events: list[BuyEvent],
    n_tickers_priced: int,
    last_data_coverage_date: date | None,
) -> InsiderSampleDisclosure:
    entry_dates = sorted(e.entry_date for e in events)
    text = (
        f"INSIDER-OPPORTUNISTIC SAMPLE DISCLOSURE -- read before trusting any Sharpe or DSR "
        f"below. Universe: {report.n_tickers_requested} tickers from TODAY's S&P 500 snapshot "
        f"(ticker_universe.SCREENING_UNIVERSE) mapping to {report.n_tickers_cik_resolved} "
        f"DISTINCT ISSUER CIKs ({len(report.unresolved_tickers)} tickers resolved to no CIK at "
        f"all; the rest of any shortfall is dual-class pairs sharing one issuer -- see KNOWN "
        f"LIMITS); "
        f"{len(report.quarters_fetched)} SEC quarterly data-set files fetched "
        f"({len(report.quarters_failed)} failed), yielding {report.n_raw_ps_rows} P/S "
        f"non-derivative Form 4 rows for those issuers across the full classification history, "
        f"of which {counts.n_buy_rows} are open-market-coded buy rows (code P/A) with filing "
        f"dates inside the formation window. Under the paper's own classification rule "
        f"{counts.n_buys_by_opportunistic} buys were made by insiders labelled OPPORTUNISTIC in "
        f"the filing year, {counts.n_buys_by_routine} by ROUTINE insiders (excluded -- the "
        f"paper's finding is precisely that these carry no information), and "
        f"{counts.n_buys_by_unclassified} by insiders with under three years of visible history "
        f"(ignored, as in the paper's main design -- its own robustness note says such trades "
        f"'appear to more closely resemble opportunistic trades', so ignoring them THINS the "
        f"signal rather than flattering it). Gates: {counts.n_dropped_not_member} buys dropped "
        f"by the point-in-time membership gate, {counts.n_dropped_stale_filing} as stale "
        f"late filings (> {INSIDER_MAX_FILING_DELAY_CALENDAR_DAYS} calendar days), "
        f"{counts.n_dropped_outside_window} outside the formation window, "
        f"{counts.n_dropped_no_price_row} with no usable price row -> {counts.n_events} entered "
        f"events on {n_tickers_priced} priced tickers. THE UNIVERSE IS SURVIVORSHIP-THINNED: "
        f"names that left the index before the snapshot are absent entirely; for a long-buys "
        f"family the sign of that bias is not knowable a priori and is disclosed, not guessed. "
        f"The long leg is THIN (large-cap insiders overwhelmingly sell): many invested days "
        f"hold 1-3 names against SPY, so idiosyncratic variance dominates and the daily "
        f"observation count overstates independent information. The published data sets end at "
        f"{last_data_coverage_date} -- filings after that date do not exist in this data yet. "
        f"This is a SEPARATE caution from the DSR's n_trials={INSIDER_N_TRIALS} correction; "
        f"neither substitutes for the other. Finally, this family trades ONLY the buy side, and "
        f"the paper itself attributes over half its improvement to the SELL side (docstring "
        f"quote), so a weak result here is expected by design."
    )
    return InsiderSampleDisclosure(
        quarters_fetched=len(report.quarters_fetched),
        quarters_failed=len(report.quarters_failed),
        n_tickers_requested=report.n_tickers_requested,
        n_tickers_cik_resolved=report.n_tickers_cik_resolved,
        n_raw_ps_rows=report.n_raw_ps_rows,
        n_buy_rows=counts.n_buy_rows,
        n_buys_by_opportunistic=counts.n_buys_by_opportunistic,
        n_buys_by_routine=counts.n_buys_by_routine,
        n_buys_by_unclassified=counts.n_buys_by_unclassified,
        n_dropped_not_member=counts.n_dropped_not_member,
        n_dropped_stale_filing=counts.n_dropped_stale_filing,
        n_events=counts.n_events,
        n_tickers_priced=n_tickers_priced,
        first_event_date=entry_dates[0] if entry_dates else None,
        last_event_date=entry_dates[-1] if entry_dates else None,
        last_data_coverage_date=last_data_coverage_date,
        text=text,
    )


@dataclass
class InsiderScreeningSummary:
    results: list[InsiderScreeningResult]
    missing_price_data: list[str]
    sample: InsiderSampleDisclosure
    cost_disclosure: str


def _build_cost_disclosure(config: InsiderConfig) -> str:
    return (
        f"COST DISCLOSURE. {config.round_trip_bps}bp round trip per event (4 x the harness's own "
        f"DEFAULT_XS_COST_BPS one-way equity constant: stock entry+exit PLUS a matched SPY hedge "
        f"entry+exit, the hedge deliberately overcharged at the single-name constant and treated "
        f"as traded per event rather than netted), charged ONCE PER EVENT on its first realized "
        f"day. Financing: {config.financing_bps_per_year}bp/yr -- the equity families' shared "
        f"convention; unlike the sibling families' single-name short legs, the only short here "
        f"is SPY, which genuinely does trade near zero borrow specialness, so the usual "
        f"borrow-optimism caveat is weaker for this family. Daily renormalization as events "
        f"enter/leave is not charged (the harness's stated zero-cost-rebalancing convention), "
        f"so true costs are somewhat higher than the reported drag."
    )


def screen_insider_family(
    close: pd.DataFrame,
    benchmark: pd.Series,
    events: list[BuyEvent],
    config: InsiderConfig,
    specs: list[InsiderSpec] | None = None,
) -> list[InsiderScreeningResult]:
    """One Sharpe per spec, DSR-corrected for the family's pre-declared
    size. n_trials is len(specs) -- never shrunk to however many specs
    cleared the data floors. sigma_sr is the ddof=1 std of every sibling
    spec's own Sharpe from this same pass."""
    specs = specs if specs is not None else INSIDER_FAMILY
    n_trials = len(specs)
    basis = (
        build_inverse_vol_basis(close)
        if any(s.leg_weighting == "inverse_vol" for s in specs)
        else None
    )

    replays: dict[str, InsiderBacktestResult] = {}
    for spec in specs:
        entered = [e for e in events if e.cluster_filings >= spec.min_cluster_buys]
        result = run_insider_backtest(close, benchmark, entered, spec, config, basis)
        if result.status != "ok" or len(result.daily_returns) < MIN_REPLAY_TRADING_DAYS:
            continue
        replays[spec.pattern_id] = result

    sharpes = {pid: sharpe_ratio(res.daily_returns) for pid, res in replays.items()}
    sigma_sr = (
        float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None
    )

    spec_by_id = {spec.pattern_id: spec for spec in specs}
    results: list[InsiderScreeningResult] = []
    for pattern_id, replay in replays.items():
        spec = spec_by_id[pattern_id]
        n_days = len(replay.daily_returns)
        results.append(
            InsiderScreeningResult(
                pattern_id=pattern_id,
                family=spec.family,
                citation=spec.citation,
                holding_days=spec.holding_days,
                min_cluster_buys=spec.min_cluster_buys,
                leg_weighting=spec.leg_weighting,
                n_events_entered=replay.n_events_entered,
                n_events_superseded=replay.n_events_superseded,
                n_events_delisted_mid_hold=replay.n_events_delisted_mid_hold,
                n_trading_days=n_days,
                n_invested_days=replay.n_invested_days,
                n_uninvested_days=replay.n_uninvested_days,
                invested_fraction=(replay.n_invested_days / n_days) if n_days else 0.0,
                mean_leg_size=replay.mean_leg_size,
                sharpe_annualized=sharpes[pattern_id],
                total_cost_drag=replay.total_cost,
                total_financing_drag=replay.total_financing_cost,
                deflated_sharpe=compute_deflated_sharpe(
                    sharpes[pattern_id], replay.daily_returns, n_trials, sigma_sr
                ),
                n_weight_fallback_days=replay.n_weight_fallback_days,
            )
        )
    results.sort(key=lambda r: r.sharpe_annualized, reverse=True)
    return results


def run_insider_screening(
    start: date,
    end: date,
    provider: YFinanceProvider | None = None,
    config: InsiderConfig | None = None,
    trades: list[InsiderTrade] | None = None,
    fetch_report: InsiderFetchReport | None = None,
    tickers: list[str] | None = None,
) -> InsiderScreeningSummary:
    """THE production entry point -- mirrors run_pead_screening's shape
    (same provider contract, same start-date guard, same
    disclosure-is-part-of-the-result convention).

    `start` must be >= MEMBERSHIP_DATA_START (the was_member gate answers
    a silent False before coverage). Pass `trades` (+ `fetch_report`) to
    reuse a cached SEC pass (save_trades_cache / load_trades_cache);
    omitting them fetches every published quarter from
    INSIDER_DATA_FIRST_QUARTER through `end`'s quarter live, rate-limited
    under SEC's published fair-access cap. Classification always uses the
    FULL trade history handed in (more visible past years = more routine
    patterns detectable, exactly as in the paper)."""
    if start < MEMBERSHIP_DATA_START:
        raise ValueError(
            f"Insider screening start {start.isoformat()} predates point-in-time membership "
            f"coverage ({MEMBERSHIP_DATA_START.isoformat()}) -- the was_member gate would "
            "silently answer False for every event before it."
        )
    provider = provider if provider is not None else YFinanceProvider()
    config = config if config is not None else InsiderConfig()
    universe = tickers if tickers is not None else list(SCREENING_UNIVERSE)

    if trades is None:
        quarters = quarter_labels(
            INSIDER_DATA_FIRST_QUARTER, f"{end.year}q{(end.month - 1) // 3 + 1}"
        )
        trades, fetch_report = fetch_insider_trades(universe, quarters)
    if fetch_report is None:
        fetch_report = InsiderFetchReport(n_tickers_requested=len(universe))

    last_coverage = max((t.filing_date for t in trades), default=None)
    formation_end = min(end, last_coverage) if last_coverage else end

    years = list(range(start.year, formation_end.year + 1))
    labels = build_owner_labels(trades, years)

    event_tickers = sorted(
        {t.ticker for t in trades if t.trans_code == "P" and t.acquired_disposed == "A"}
    )
    fetch_start = start - timedelta(days=INSIDER_WARMUP_PADDING_CALENDAR_DAYS)
    frames, missing = provider.get_daily_ohlcv(event_tickers, fetch_start, end)
    if not frames:
        empty_counts = SignalCounts()
        sample = build_insider_sample_disclosure(
            fetch_report, empty_counts, [], 0, last_coverage
        )
        return InsiderScreeningSummary(
            results=[],
            missing_price_data=missing,
            sample=sample,
            cost_disclosure=_build_cost_disclosure(config),
        )
    close = frames["close"]

    bench_frames, bench_missing = provider.get_daily_ohlcv(
        [INSIDER_BENCHMARK_TICKER], fetch_start, end
    )
    if (
        bench_missing
        or not bench_frames
        or INSIDER_BENCHMARK_TICKER not in bench_frames["close"].columns
    ):
        raise ValueError(
            f"The {INSIDER_BENCHMARK_TICKER} benchmark resolved no price data. The long leg is "
            "hedged 1:1 with it, so without it the book is a naked long -- a different "
            "(beta-contaminated) strategy than this family declares. Failing loudly."
        )
    benchmark = bench_frames["close"][INSIDER_BENCHMARK_TICKER]

    events, counts = build_buy_events(
        trades, labels, close.index, start, formation_end, set(close.columns)
    )
    results = screen_insider_family(close, benchmark, events, config)
    sample = build_insider_sample_disclosure(
        fetch_report, counts, events, len(close.columns), last_coverage
    )
    return InsiderScreeningSummary(
        results=results,
        missing_price_data=missing,
        sample=sample,
        cost_disclosure=_build_cost_disclosure(config),
    )
