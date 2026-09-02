"""13F INSTITUTIONAL "BEST IDEAS": one pre-declared cross-sectional equity
family testing whether the stocks representing many institutional
managers' single largest ACTIVE BET outperform, using only holdings
information that was PUBLIC at each formation date.

Pre-registration: data/research_runs/best_ideas_13f_PREREGISTRATION.txt,
committed in ac9bc8b BEFORE this module computed a single number.
Ingestion lives in market_data/form13f_provider.py.

=======================================================================
1. THE SOURCE, AND AN UNUSUALLY WEAK EVIDENTIARY BASE
=======================================================================

PRIMARY. Antón, Miguel, Randolph B. Cohen & Christopher Polk, "Best
Ideas". The full PDF was fetched from the corresponding author's own LSE
page (personal.lse.ac.uk/polk/research/bestideas.pdf) during this build
(2026-09-02) and read; every quote below is from that retrieved text. Its
title page reads "This Draft: April 2021".

READ THIS BEFORE CITING IT ANYWHERE. This is an UNPUBLISHED WORKING
PAPER, and the verification went further than "not yet published":
Polk's own CV (personal.lse.ac.uk/polk/research/polkcv.pdf, fetched and
parsed this build, current through June 2026) lists "Best Ideas (with
Miguel Antón and Randy Cohen), April 2021." under the heading WORKING
PAPERS, with NO journal and NO revise-and-resubmit annotation -- while
OTHER entries in that same list explicitly carry them ("Revise-and-
resubmit, Journal of Finance"). So it has sat at one draft for five years
on an actively-maintained CV without being marked as under review
anywhere, and the idea has circulated publicly since a 2008 NBER
conference draft (Cohen-Polk-Silli). Seventeen years, no peer review.

That is the WEAKEST evidentiary base of any family in this codebase --
every other one rests on a published JF/JFE/RFS paper -- and it is a
reason for a LOWER prior, not a higher one. This module must never
describe the paper as more validated than that.

THE HEADLINE CLAIM, verbatim from the retrieved abstract: managers'
best ideas "outperform the market, as well as the other stocks in those
managers' portfolios, by approximately 2.8 to 4.5 percent per year,
depending on the benchmark employed. The vast majority of the other
stocks managers hold do not exhibit significant outperformance."

THE MECHANISM IS AGENCY, NOT MISPRICING. The claim is not that markets
are broadly inefficient; it is that asset-gathering incentives and
tracking-error constraints push informed managers to overdiversify, so
real skill concentrates in a few large active tilts and is diluted to
nothing across the long tail of portfolio-rounding positions.

=======================================================================
2. THE THREE MEASURES -- QUOTED, NOT INVENTED
=======================================================================

The paper's Figure 4 caption states the ranking statistic in closed form.
Verbatim (PDF extraction loses subscripts; restored in brackets):

    "Best ideas are determined within each fund as the stock with the
     maximum value of the following information ratio measure, IR[ift] =
     sigma[it] (lambda[ift] - lambda[iMt]) where lambda[ift] is manager
     f's portfolio weight in stock i, lambda[iMt] is the weight of stock
     i in the market portfolio, and sigma[it] is the most-recent estimate
     of a stock's CAPM-idiosyncratic volatility."

matching its section III algebra (alpha = k Sigma_t tilt, IR = alpha /
sigma, hence IR proportional to sigma_it x tilt_ift). Section III gives
the market and portfolio tilts, section V.E the conviction measure:

  market_tilt     lambda[ft] - lambda[Mt]
  portfolio_tilt  lambda[ft] - lambda[fVt], where lambda[fVt] is "the
                  value-weight portfolio consisting only of stocks the
                  manager actually holds" (verbatim)
  conviction      alpha[ft] = lambda[ft], best = arg max lambda[ift]

CONVICTION IS THE PAPER'S OWN 13F MEASURE. It is introduced specifically
for the paper's 13F hedge-fund sample because "hedge funds arguably care
less about benchmarks and tracking error than mutual funds" (verbatim).
Since 13F is the only holdings data this project has, the paper's own
choice for this data is the measure this family leans on hardest -- and
it is EXACT here, not a proxy: it needs no benchmark and no volatility
estimate.

WHY SIGMA IS ABSENT FROM ALL THREE, and why that is the paper's decision
rather than this project's shortcut. Section III, verbatim: "we confirm
that robustness checks based on the assumption that all stocks have equal
idiosyncratic risk provide qualitatively similar results." Under equal
idiosyncratic risk the IR ordering collapses to the TILT ordering, so
sigma drops out of every arg max. This matters enormously for what is
constructible: a manager's best idea is an arg max over their ENTIRE
book, which runs to thousands of securities outside this project's price
universe, and no per-stock volatility estimate exists for those. Under
the paper's own stated robustness assumption, none is needed.

THE MARKET-WEIGHT VECTOR IS A DISCLOSED PROXY. lambda[Mt] here is the
AGGREGATE 13F PORTFOLIO -- total reported value in a security across all
filers, over total reported value across all securities and filers. It is
NOT the CRSP value-weighted market. It was chosen because it is the only
market-weight vector available that is simultaneously (a) real, (b)
point-in-time, and (c) defined over the SAME universe as lambda[ift]. A
market weight computed over only this project's ~768-name price universe
would carry a different denominator from the manager weight, and their
difference would be arithmetically meaningless.
  ITS BIAS, STATED IN ADVANCE: securities with low institutional
  ownership (founder- or insider-controlled firms) carry understated
  weights in it, which mechanically inflates every manager's apparent
  tilt toward them. portfolio_tilt inherits the same proxy as its
  capitalisation basis.

=======================================================================
3. POINT-IN-TIME -- THE SINGLE MOST IMPORTANT PROPERTY HERE
=======================================================================

THE RULE, admitting no exception: a 13F filing contributes to the signal
on and after its own FILING_DATE, and never one day earlier. Not its
PERIODOFREPORT, not the statutory 45-day deadline, not a quarter end.

FILING_DATE is the date the document became public on EDGAR, so it is the
date an outsider could have acted on it. It is also robust to every
anomaly the real data contains -- late filers reporting two-year-old
quarters (the measured 2016q1 lag distribution runs min 4 / median 42 /
p95 68 / max 1509 days) and same-day filings. Under a period-keyed rule
those rows would be look-ahead or need special-casing; under a
FILING_DATE-keyed rule they are simply correct, because a document IS
knowable the day it is filed.

TWO DERIVED QUANTITIES ARE LAGGED A FULL PERIOD FOR THE SAME REASON.
Both the aggregate market-weight vector (section 2) and the top-25%
activeness cutoff (section 4) are cross-sectional statistics over MANY
managers, so computing either from the current period's filings would let
a manager who filed early be judged against filings that did not yet
exist. Both are therefore computed from the PREVIOUS period's filings,
restricted to those filed strictly before the current period's end date.
That bound is what makes it provable rather than merely likely: every
period-p filing has FILING_DATE >= period-p end (enforced at parse time),
and every input to its benchmark has FILING_DATE < period-p end, so no
period-p filing can ever see a contemporaneous or future filing.

AMENDMENTS. A 13F-HR/A restates an earlier report. Point-in-time honesty
means the ORIGINAL is what was visible between its filing date and the
amendment's filing date, and the amendment takes over only from ITS OWN
filing date. Filings are replayed in FILING_DATE order and the
latest-filed record for a given (manager, period) wins as of the date it
was filed -- never retroactively. Restatements never rewrite history.

STRUCTURAL BACKSTOP. The panel is handed to the harness as
CrossSectionalData.fundamental_signal, which the harness slices to rows
<= the formation date, so formation-time look-ahead is structurally
impossible on top of the filing-date construction.

STALENESS. A manager's view expires MANAGER_VIEW_MAX_STALENESS_DAYS (200)
after it was filed, so a filer who stops filing does not haunt the panel
forever. 200 covers a normal quarterly cadence (~91 days) plus a very
late filing, without spanning three quarters.

=======================================================================
4. MANAGER UNIVERSE -- AND THE ONE THING THIS FAMILY CANNOT DO
=======================================================================

APPLIED, following the paper's own rules wherever the data permits:
  * 13F-HR / 13F-HR/A only; 13F-NT notice filings carry no holdings.
  * Long equity only: PUTCALL blank, SSHPRNAMTTYPE 'SH' (provider).
  * >= 5 recorded holdings        [paper: "at least 5 recorded holdings"]
  * > $5m total equity            [paper: "exceeding $5 million"]
  * Index/passive FILER-NAME screen -- the closest available analogue of
    the paper's fund-name screen, and STRICTLY COARSER, because 13F is
    filed by an institution rather than a fund.
  * Top-25% activeness cut, per measure [paper: "the top 25% most active
    ... whose maximum position-level information ratio ... is in the top
    25% of all corresponding information ratios at that point in time"],
    computed on the previous period's distribution for the PIT reason in
    section 3.

THE THING THIS FAMILY CANNOT DO, and it is its biggest weakness. The
paper's 13F results rest on Agrawal-Jiang-Tang-Yang's MANUAL
classification of every 13F institution, yielding 1,662 hand-identified
pure-play hedge funds, explicitly excluding "banks and mutual fund
companies" (verbatim). That is a hand-built academic dataset this project
does not have, and no free official registry of "which 13F filers are
pure-play hedge funds" exists -- 13F filings carry no such field.

  WHAT IS SUBSTITUTED: the mechanical screens above. A name screen
  catches obvious index and ETF sponsors but CANNOT tell a discretionary
  long-only boutique from a bank trust department from a quant shop.

  WHY THE SUBSTITUTE IS PARTIALLY DEFENSIBLE, without overclaiming: the
  activeness cut is BEHAVIOURAL, not nominal, and it mechanically demotes
  exactly the filers the paper excludes -- a hugely diversified
  index-tracking or bank-trust filer has tiny maximum position weights
  and therefore tiny maximum tilts, so it fails the cut on its own
  portfolio's arithmetic. That is a real mitigation, NOT a replacement
  for hand classification, and this family does not claim otherwise.

  DISCLOSED CONSEQUENCE: this manager universe is dirtier than the
  paper's, so a negative here is confounded with universe quality and
  cannot be read as a clean refutation of the paper's hedge-fund finding.

TWO FURTHER HAZARDS INHERENT TO 13F, neither fixable here:
  * It is filed by the INSTITUTION, not the fund, so a multi-strategy
    complex reports one blended book and genuine per-fund conviction is
    smeared. The paper concedes the same point.
  * It shows LONGS ONLY. A manager's largest active bet may be a short
    that is never reported. Every "best idea" here is a best LONG idea.

=======================================================================
5. AGGREGATION, AND THE ONE DELIBERATE DEPARTURE FROM THE PAPER
=======================================================================

  count  the number of eligible managers whose most recent VISIBLE filing
         names stock i as their best idea. This IS the paper's own
         aggregation, verbatim: "Each best idea in the portfolio is
         equal-weighted (if more than one manager considers a stock a
         best idea, we overweight accordingly)".

  share  count_i / (number of eligible managers holding i). THIS IS THIS
         PROJECT'S OWN VARIANT AND IS LABELLED AS SUCH -- it is NOT in
         the paper. A widely-held mega-cap is mechanically somebody's top
         position more often than a thinly-held name, so `count` is
         partly a popularity/size proxy. `share` asks the
         popularity-controlled question: of the managers who hold this
         name, what fraction have it as their single highest-conviction
         bet. Both are in ONE grid under ONE denominator so that the
         size-artifact reading is a pre-declared test rather than a
         post-hoc excuse -- the lesson this project took from the sibling
         NOA family, whose confound check had to be designed after the
         confounded result.

=======================================================================
6. THE PRE-DECLARED GRID
=======================================================================

    measure     {conviction, market_tilt, portfolio_tilt}   3
  x aggregation {count, share}                              2
  x holding     {63, 126, 252} trading days                 3
  x fraction    {decile 0.1, quintile 0.2}                  2
  = 36 definitions, long_short throughout, n_trials = 36.

36 is a large DSR denominator and it raises this family's bar. That is
the correct consequence of searching 36 definitions and it is accepted
deliberately rather than trimmed -- the denominator is the honest count
of what is searched.

63 trading days is the paper's own cadence ("The portfolio is rebalanced
on the first day of every quarter") and the natural one since 13F
refreshes quarterly; 126 and 252 are robustness variants supported by its
Figure 4 finding that the outperformance "does not revert in the months
or even years". A 21-day hold is EXCLUDED up front: the signal cannot
change more often than quarterly, so a monthly hold re-pays turnover on
an unchanged ranking.

UNIVERSE: the FULL point-in-time S&P 500 union universe (768 names over
2015-2026), gated per formation by was_member -- not the 200-name seeded
sample the sibling EDGAR families use. That is affordable here for a
structural reason: those families pay one HTTP fetch PER TICKER to
EDGAR, whereas 13F archives are whole-market files parsed once
regardless of universe size, so restricting the universe would buy
nothing. It matters, because the paper's own section V.A reports that
72% of best ideas belong to exactly one manager -- best ideas are spread
thinly, and a wider cross-section is the main lever this family has
against that.

PASS/FAIL, fixed before results: a validated edge ONLY if (i) the best
spec's DSR at n_trials=36 exceeds 0.95, AND (ii) its `share` counterpart
at the same measure, hold and fraction is also materially positive rather
than collapsing. Anything else is an honest negative or an honest
artifact and is written up as such.

=======================================================================
7. PRODUCTION RUN 2026-09-02 — MEASURED COVERAGE AND RESULTS
=======================================================================

Sections 1-6 and the pre-registration were committed in ac9bc8b BEFORE
this run existed. Everything below is what came out; the grid and the
pass/fail rule applied are that commit's, unchanged. Full detail in
data/research_runs/best_ideas_13f_2026-09-02.txt.

Run tag "best_ideas_13f_build_2026-09-02", persisted to
cross_sectional_trial_results under family_key "best_ideas_13f" (36 rows,
n_trials=36 on every row). 2,890 realized trading days per spec, price
panel 2014-11-28..2026-08-28, wall clock 207 minutes.

DATA PROVENANCE — REAL. 53 real SEC Form 13F quarterly archives
(2013q2..2026q2), 120,182,194 INFOTABLE rows, 307,994 holdings filings.
CUSIP->ticker from real SEC fails-to-deliver files. Prices from real
yfinance history. No synthetic input touched any persisted number.

COVERAGE. 80,317 eligible manager-filing views from 6,763 distinct
filers. The CUSIP map resolved 765 of 768 universe tickers (99.6%); the
three that never resolved are BF-B, BRK-B and DAY. 143 universe tickers
resolved no price history (the standing departed-member gap), leaving a
cross-section whose decile legs run ~45 names and quintile legs ~90 —
roughly four times the sibling EDGAR families' ~12, which is the payoff
of ranking the full universe rather than a 200-name sample.
Best ideas landing inside the S&P 500: 17.3% (conviction), 16.0%
(market_tilt), 11.8% (portfolio_tilt) — the rest name securities outside
the index, which is the CORRECT answer and matches the paper's own
finding that best ideas are spread thinly across the whole market.

POINT-IN-TIME, MEASURED: realized report-period -> filing-date lag of
min 1 day, median 43 days, never negative by construction.

RESULTS — HONEST NEGATIVE. sigma_sr 0.161. Best spec
bi_portfolio_tilt_share_h252_quintile at Sharpe +0.573, DSR 0.778.
ZERO of the 36 specs clear the pre-registered 0.95 bar, so condition (i)
fails and condition (ii) is never reached.

FOUR THINGS THE GRID'S STRUCTURE SAYS:

 * THE SIGN IS RIGHT, THE SIZE IS NOT. 35 of 36 specs are positive in the
   paper's direction, but they are correlated variants of ONE idea, so
   that sign count carries roughly the information of a single draw —
   which sigma_sr already prices in.

 * COUNT BEATS SHARE ALMOST EVERYWHERE, the uncomfortable number: mean
   +0.398 vs +0.184, with count winning 17 of 18 matched pairs. `share`
   was pre-declared precisely to detect "many managers call this their
   best idea" really meaning "many managers hold this because it is big",
   and this is direct evidence a meaningful part of the raw signal is
   that popularity effect.

 * BUT NOT PURELY A SIZE ARTIFACT. The single best spec in the grid IS a
   `share` spec, beating both the best `count` spec and its own matched
   count counterpart. Popularity explains much of the average, not the
   maximum. Neither reading matters at DSR 0.778 against a 0.95 bar.

 * THE LONGEST HOLD IS THE BEST (h252 mean +0.388 vs h63 +0.262, h126
   +0.222), which is the one result sitting comfortably with the source —
   the paper's Figure 4 claims the outperformance does not revert over
   months or years. Contrast the sibling asset-growth family, where the
   literature's own rebalance frequency was the WORST hold.

   Read portfolio_tilt's rank as best measure (mean +0.364) CAUTIOUSLY:
   it leans hardest on the disclosed aggregate-13F capitalisation proxy
   (section 2), so its edge over conviction — the one exact, proxy-free
   measure — is as easily a property of the proxy as of the economics.

WHAT THIS DOES NOT CLAIM, as the pre-registration committed in advance to
saying: it does NOT refute Anton/Cohen/Polk. They identify best ideas at
TRUE holding dates while this tests public filing dates ~45 days later;
they use a hand-classified pure-play hedge-fund universe while this uses
mechanical screens that admit banks and fund complexes; they rank the
whole CRSP cross-section while this ranks large caps, where the paper's
own 72%-single-manager statistic says best ideas are least distinctive;
and they measure factor-model alpha on a long-only portfolio while this
measures a long-short Sharpe on a cross-sectional rank. Those are
different statistics and a null in one does not imply a null in the
other. What this DOES establish is the only question that matters here:
not tradeable by us, on our universe, at public filing dates, now.

ONE PARAMETER WAS ADDED AFTER PRE-REGISTRATION and is disclosed rather
than buried: MAX_REPORTING_LAG_DAYS = 365, chosen from ingestion
diagnostics only, before any backtest number existed, after the realized
lag distribution showed delinquent filers reporting books up to 3,027
days old. It refused 7,733 filings. No result influenced it.

AN INCIDENTAL FINDING THAT OUTLIVES THE BACKTEST — THE 2023 UNITS BREAK.
The per-filing unit classifier detected, from the data alone with no
hardcoded date, that whole-dollar VALUE reporting jumps from ~1.3% of
filings in 2022q4 to 79.9% in 2023q1 and on to 96.0% by 2026q2. The
CURRENT Form 13F instructions were fetched and say verbatim "Enter values
rounded to the nearest dollar" (instruction 8). The causal attribution to
a units-convention change is LABELLED AN INFERENCE — no explicit
effective date was located — but the measurement is counted from the real
archives. It matters beyond this family: any 13F pipeline hardcoding the
thousands convention every pre-2023 description of this dataset states is
wrong by 1,000x for most filings after 2023q1. Portfolio WEIGHTS survive
it; anything comparing value ACROSS filers does not.
"""

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import partial

import numpy as np
import pandas as pd

from app.services.market_data.form13f_provider import (
    CusipTickerMap,
    Form13FFiling,
    Form13FParseDiagnostics,
    Form13FProvider,
    build_cusip_ticker_map,
    is_passive_filer_name,
    parse_ftd_archive,
    parse_quarter_archive,
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

BEST_IDEAS_CITATION = (
    "Anton, Cohen & Polk, 'Best Ideas' (April 2021 draft; first circulated as Cohen-Polk-Silli "
    "2009) — an UNPUBLISHED WORKING PAPER, listed as such on Polk's own CV with no journal and "
    "no revise-and-resubmit annotation while sibling entries on that list carry them. Its "
    "abstract claims managers' highest-conviction holdings 'outperform the market, as well as "
    "the other stocks in those managers' portfolios, by approximately 2.8 to 4.5 percent per "
    "year'. This family tests the OUTSIDER version (public filing dates), which the paper "
    "supports only by footnote assertion, not its headline true-holding-date result"
)

# --- pre-declared constants (all fixed in the pre-registration) --------------

# The paper's own portfolio-eligibility screens, section IV.
MIN_HOLDINGS_PER_FILING = 5
MIN_PORTFOLIO_VALUE_USD = 5_000_000.0
# The paper's "top 25% most active" cut.
ACTIVENESS_QUANTILE = 0.75
# A manager's filed view expires after this many calendar days (section 3).
MANAGER_VIEW_MAX_STALENESS_DAYS = 200
# A filing whose REPORT PERIOD is older than this at the moment it is
# filed describes holdings too stale to represent current conviction.
#
# THIS IS A BUILD-TIME DATA-HYGIENE DECISION, NOT A SEARCHED PARAMETER,
# and it is recorded rather than quietly applied. It was added after the
# ingestion diagnostics (never any backtest result) showed a realized
# filing-lag distribution of min 1 / median 44 / MAX 3027 days across
# 2015-2016 — i.e. genuine delinquent filers reporting eight-year-old
# books. Keying visibility on FILING_DATE makes those rows harmless as
# look-ahead (they are public when filed), but it would let a 2016
# filing of 2008 holdings enter the panel as fresh conviction, which is
# an economics error rather than a timing one. 365 days admits any
# ordinary late filing while refusing a book that predates the current
# fiscal year entirely. No result influenced this number.
MAX_REPORTING_LAG_DAYS = 365

BEST_IDEA_MEASURES: tuple[str, ...] = ("conviction", "market_tilt", "portfolio_tilt")
BEST_IDEAS_AGGREGATIONS: tuple[str, ...] = ("count", "share")
BEST_IDEAS_HOLDING_DAYS: tuple[int, ...] = (63, 126, 252)
BEST_IDEAS_RANK_FRACTIONS: tuple[tuple[str, float], ...] = (("", 0.1), ("_quintile", 0.2))

BEST_IDEAS_N_TRIALS = (
    len(BEST_IDEA_MEASURES)
    * len(BEST_IDEAS_AGGREGATIONS)
    * len(BEST_IDEAS_HOLDING_DAYS)
    * len(BEST_IDEAS_RANK_FRACTIONS)
)

BEST_IDEAS_FAMILY = "best_ideas_13f"
BEST_IDEAS_FAMILY_KEY = "best_ideas_13f"

BEST_IDEAS_COST_BPS = DEFAULT_XS_COST_BPS
BEST_IDEAS_FINANCING_BPS_PER_YEAR = 0.0
# Trading rows of history each signal needs before its first formation.
# The signal reads a single row, but the harness requires a lookback; one
# quarter of rows keeps the contract identical to the sibling families.
BEST_IDEAS_SIGNAL_LOOKBACK_ROWS = 63
BEST_IDEAS_PRICE_HISTORY_PADDING_CALENDAR_DAYS = 40


@dataclass
class ManagerView:
    """One eligible manager-filing reduced to exactly what the panel needs:
    when it became public, which universe ticker (if any) it names as the
    best idea under each measure, and which universe tickers it holds.

    The full book is deliberately NOT retained. Best ideas are computed as
    an arg max over the manager's ENTIRE portfolio (section 2) at
    construction time; what survives into the panel is only the universe
    projection of that answer, which is all the cross-section can use."""

    cik: int
    filing_date: date
    period: date
    # measure -> universe ticker index, or None when that manager's best
    # idea is a security outside this family's universe. None is the
    # CORRECT answer, not a failure: the manager genuinely does not name
    # any ranked name as their top bet.
    best_idea: dict[str, int | None]
    # measure -> did this filing clear that measure's activeness cut.
    # SEPARATE from best_idea being None, and the separation is
    # load-bearing: "ineligible under this measure" and "eligible but the
    # best idea is outside the ranked universe" are different facts, and
    # only the second one may still count toward the `share`
    # denominator. Conflating them would silently shrink that
    # denominator and inflate every share.
    eligible: dict[str, bool]
    # measure -> that filing's own maximum statistic, used for the
    # activeness cut.
    max_stat: dict[str, float]
    held_universe: np.ndarray  # int32 indices into the universe ticker list


@dataclass
class BestIdeasBuildDiagnostics:
    """Every refusal and every measured coverage number. Nothing silent."""

    n_filings_seen: int = 0
    n_filings_eligible: int = 0
    n_refused: Counter = field(default_factory=Counter)
    n_periods: int = 0
    # measure -> count of eligible filings whose best idea landed inside
    # the ranked universe.
    n_best_idea_in_universe: Counter = field(default_factory=Counter)
    cusips_resolved: int = 0
    cusips_unresolved_in_universe_filings: int = 0
    parse: Form13FParseDiagnostics = field(default_factory=Form13FParseDiagnostics)
    # The realized gap between PERIODOFREPORT and FILING_DATE across every
    # eligible filing -- the family's headline point-in-time honesty number.
    filing_lag_days: list[int] = field(default_factory=list)


def _period_key(d: date) -> tuple[int, int]:
    return (d.year, (d.month - 1) // 3)


def _previous_period(period: date, known: list[date]) -> date | None:
    """The calendar quarter-end immediately preceding `period` among the
    periods actually present in the data."""
    earlier = [p for p in known if p < period]
    return max(earlier) if earlier else None


def compute_best_ideas_for_filing(
    filing: Form13FFiling,
    market_weights: dict[str, float] | None,
    cap_basis: dict[str, float] | None,
) -> tuple[dict[str, str | None], dict[str, float]]:
    """The three arg maxes for one filing, over that filing's FULL book.

    Returns (measure -> best-idea CUSIP or None, measure -> max statistic).

    `market_weights` is the previous period's aggregate 13F weight vector
    (section 2), and `cap_basis` the previous period's aggregate 13F VALUE
    per security used as the capitalisation proxy for the portfolio
    measure. Both are None for the very first period in the data, where
    the two benchmark-relative measures are simply unavailable -- reported
    as such, never silently replaced by a zero benchmark, which would
    turn market_tilt into conviction and quietly duplicate a spec."""
    total = filing.total_value_usd
    best: dict[str, str | None] = {}
    stat: dict[str, float] = {}
    if total <= 0.0:
        return {m: None for m in BEST_IDEA_MEASURES}, dict.fromkeys(BEST_IDEA_MEASURES, float("nan"))

    weights = {c: v / total for c, v in filing.holdings.items()}

    # conviction: alpha = lambda, exact, no benchmark needed.
    top = max(weights.items(), key=lambda kv: kv[1])
    best["conviction"], stat["conviction"] = top[0], top[1]

    # market_tilt: lambda_f - lambda_M.
    if market_weights is None:
        best["market_tilt"], stat["market_tilt"] = None, float("nan")
    else:
        tilts = {c: w - market_weights.get(c, 0.0) for c, w in weights.items()}
        top = max(tilts.items(), key=lambda kv: kv[1])
        best["market_tilt"], stat["market_tilt"] = top[0], top[1]

    # portfolio_tilt: lambda_f - lambda_fV, the value weight of each held
    # name WITHIN the manager's own held set.
    if cap_basis is None:
        best["portfolio_tilt"], stat["portfolio_tilt"] = None, float("nan")
    else:
        held_cap = {c: cap_basis.get(c, 0.0) for c in weights}
        cap_total = sum(held_cap.values())
        if cap_total <= 0.0:
            best["portfolio_tilt"], stat["portfolio_tilt"] = None, float("nan")
        else:
            tilts = {c: weights[c] - held_cap[c] / cap_total for c in weights}
            top = max(tilts.items(), key=lambda kv: kv[1])
            best["portfolio_tilt"], stat["portfolio_tilt"] = top[0], top[1]

    return best, stat


def build_manager_views(
    filings_by_quarter: list[list[Form13FFiling]],
    cusip_map: CusipTickerMap,
    universe: list[str],
) -> tuple[list[ManagerView], BestIdeasBuildDiagnostics]:
    """Replay every quarterly archive in chronological order into the
    eligible manager views the panel is built from.

    THE PERIOD-LAG DISCIPLINE IS THE POINT OF THIS FUNCTION (section 3).
    Both cross-manager statistics -- the aggregate market-weight vector
    and the activeness cutoff -- are computed from the PREVIOUS period's
    filings, restricted to those FILED STRICTLY BEFORE the current
    period's end date. Combined with the parser's guarantee that every
    filing has FILING_DATE >= its own period end, that makes it
    impossible for any filing to be judged against a contemporaneous or
    later filing."""
    ticker_index = {t: i for i, t in enumerate(universe)}
    diagnostics = BestIdeasBuildDiagnostics()

    all_filings: list[Form13FFiling] = [f for quarter in filings_by_quarter for f in quarter]
    all_filings.sort(key=lambda f: (f.filing_date, f.accession))
    diagnostics.n_filings_seen = len(all_filings)

    by_period: dict[date, list[Form13FFiling]] = defaultdict(list)
    for filing in all_filings:
        by_period[filing.period].append(filing)
    periods = sorted(by_period)
    diagnostics.n_periods = len(periods)

    views: list[ManagerView] = []
    staged: dict[date, list[tuple[Form13FFiling, dict[str, str | None], dict[str, float]]]] = (
        defaultdict(list)
    )

    for period in periods:
        prior = _previous_period(period, periods)
        cap_basis: dict[str, float] | None = None
        market_weights: dict[str, float] | None = None
        if prior is not None:
            # The bound that makes the lag provable: the prior aggregate is
            # re-derived from prior-period filings public STRICTLY BEFORE
            # this period's end, rather than trusting the whole prior
            # period (a delinquent prior-period filer could otherwise land
            # after this period had already started).
            strict: dict[str, float] = defaultdict(float)
            for filing in by_period[prior]:
                if filing.filing_date < period:
                    for cusip, value in filing.holdings.items():
                        strict[cusip] += value
            usable = {c: v for c, v in strict.items() if v > 0.0}
            grand = sum(usable.values())
            if grand > 0.0:
                cap_basis = usable
                market_weights = {c: v / grand for c, v in usable.items()}

        for filing in by_period[period]:
            if (filing.filing_date - filing.period).days > MAX_REPORTING_LAG_DAYS:
                diagnostics.n_refused["report_period_too_stale_at_filing"] += 1
                continue
            if filing.n_holdings < MIN_HOLDINGS_PER_FILING:
                diagnostics.n_refused["fewer_than_5_holdings"] += 1
                continue
            if filing.total_value_usd <= MIN_PORTFOLIO_VALUE_USD:
                diagnostics.n_refused["portfolio_under_5m"] += 1
                continue
            if is_passive_filer_name(filing.manager_name):
                diagnostics.n_refused["passive_or_index_filer_name"] += 1
                continue
            best, stat = compute_best_ideas_for_filing(filing, market_weights, cap_basis)
            staged[period].append((filing, best, stat))

    # Activeness cutoffs, per measure, from the PREVIOUS period's realized
    # distribution of maximum statistics (section 3's PIT reasoning) --
    # and, like the market-weight vector above, restricted to prior-period
    # filings PUBLIC STRICTLY BEFORE the current period ended.
    #
    # THE RESTRICTION IS NOT COSMETIC. Without it the cutoff is a quantile
    # over every prior-period filing including delinquent ones submitted
    # after the current period had already begun, so a manager's
    # eligibility could depend on a document filed after their own. The
    # measured tail is small (58 of ~6,000 submissions in the real 2016q1
    # archive report an older quarter) but it is a genuine leak, and this
    # module's own point-in-time contract claims both cross-manager
    # statistics are bounded the same way.
    def _cutoffs_for(period: date, prior: date | None) -> dict[str, float]:
        if prior is None:
            return {}
        cutoffs: dict[str, float] = {}
        for measure in BEST_IDEA_MEASURES:
            values = [
                s[measure]
                for f, _, s in staged.get(prior, [])
                if f.filing_date < period and np.isfinite(s.get(measure, float("nan")))
            ]
            cutoffs[measure] = (
                float(np.quantile(values, ACTIVENESS_QUANTILE)) if values else float("nan")
            )
        return cutoffs

    for period in periods:
        prior = _previous_period(period, periods)
        cutoffs = _cutoffs_for(period, prior)
        for filing, best, stat in staged.get(period, []):
            best_index: dict[str, int | None] = {}
            eligible: dict[str, bool] = {}
            for measure in BEST_IDEA_MEASURES:
                bar = cutoffs.get(measure, float("nan"))
                value = stat.get(measure, float("nan"))
                if not np.isfinite(value) or not np.isfinite(bar) or value < bar:
                    eligible[measure] = False
                    best_index[measure] = None
                    continue
                eligible[measure] = True
                cusip = best[measure]
                ticker = cusip_map.resolve(cusip, filing.filing_date) if cusip else None
                idx = ticker_index.get(ticker) if ticker else None
                best_index[measure] = idx
                if idx is not None:
                    diagnostics.n_best_idea_in_universe[measure] += 1
            if not any(eligible.values()):
                diagnostics.n_refused["below_activeness_cutoff"] += 1
                continue

            held: list[int] = []
            for cusip in filing.holdings:
                ticker = cusip_map.resolve(cusip, filing.filing_date)
                if ticker is None:
                    continue
                idx = ticker_index.get(ticker)
                if idx is not None:
                    held.append(idx)
            diagnostics.n_filings_eligible += 1
            diagnostics.filing_lag_days.append((filing.filing_date - filing.period).days)
            views.append(
                ManagerView(
                    cik=filing.cik,
                    filing_date=filing.filing_date,
                    period=filing.period,
                    best_idea=best_index,
                    eligible=eligible,
                    max_stat=stat,
                    held_universe=np.asarray(sorted(set(held)), dtype=np.int32),
                )
            )

    views.sort(key=lambda v: (v.filing_date, v.cik))
    return views, diagnostics


def build_best_idea_panels(
    close: pd.DataFrame,
    views: list[ManagerView],
    universe: list[str],
    *,
    max_staleness_days: int = MANAGER_VIEW_MAX_STALENESS_DAYS,
) -> dict[tuple[str, str], pd.DataFrame]:
    """The point-in-time daily step panels the family ranks on: one frame
    per (measure, aggregation), aligned to close's exact index and columns.

    THE LOOK-AHEAD GUARANTEE IS THE WHOLE POINT. A view contributes to row
    t if and only if `view.filing_date <= t` and t is within
    max_staleness_days of it. The replay walks trading days forward and
    activates a view only once the calendar has reached its filing date,
    so there is no code path by which a filing can influence an earlier
    row. This is tested directly, on real cached SEC filings, in
    test_cross_sectional_best_ideas.py.

    A manager's CURRENT view is their latest filing with filing_date <= t
    (amendments therefore take over only from their own filing date). When
    a newer filing supersedes an older one, the older one's contribution
    is removed on that same day, so a manager is never double-counted."""
    if list(close.columns) != list(universe):
        raise ValueError(
            "build_best_idea_panels requires `universe` to be EXACTLY close.columns, in order. "
            "ManagerView stores best ideas and holdings as integer indices into the ticker list "
            "build_manager_views was given, and this function resolves those indices against "
            "`universe`; if the two lists differ, every index silently points at a different "
            "company. Build the views against the same priced ticker list used here."
        )
    n_tickers = len(universe)
    index = close.index
    dates = np.array([ts.date() for ts in index])

    by_activation: dict[date, list[ManagerView]] = defaultdict(list)
    for view in views:
        by_activation[view.filing_date].append(view)
    activation_days = sorted(by_activation)

    counts = {m: np.zeros(n_tickers, dtype=np.int32) for m in BEST_IDEA_MEASURES}
    holders = {m: np.zeros(n_tickers, dtype=np.int32) for m in BEST_IDEA_MEASURES}
    current: dict[int, ManagerView] = {}

    count_rows = {m: np.zeros((len(index), n_tickers), dtype=np.float32) for m in BEST_IDEA_MEASURES}
    holder_rows = {
        m: np.zeros((len(index), n_tickers), dtype=np.float32) for m in BEST_IDEA_MEASURES
    }

    def _apply(view: ManagerView, sign: int) -> None:
        """Add (+1) or remove (-1) one manager's contribution to every
        measure's count and holder tallies.

        A manager contributes to a measure ONLY if it cleared that
        measure's activeness cut. Within an eligible measure, it always
        contributes to the HOLDER denominator for every ranked name it
        holds, but to the COUNT numerator only when its best idea is one
        of the ranked names -- an eligible manager whose top bet is a
        small cap outside the universe correctly enlarges the denominator
        without adding to any numerator."""
        for measure in BEST_IDEA_MEASURES:
            if not view.eligible.get(measure, False):
                continue
            idx = view.best_idea.get(measure)
            if idx is not None:
                counts[measure][idx] += sign
            holders[measure][view.held_universe] += sign

    pointer = 0
    for row, day in enumerate(dates):
        while pointer < len(activation_days) and activation_days[pointer] <= day:
            for view in by_activation[activation_days[pointer]]:
                previous = current.get(view.cik)
                if previous is not None:
                    _apply(previous, -1)
                current[view.cik] = view
                _apply(view, +1)
            pointer += 1
        # Expire stale views.
        expired = [
            cik
            for cik, view in current.items()
            if (day - view.filing_date).days > max_staleness_days
        ]
        for cik in expired:
            _apply(current[cik], -1)
            del current[cik]
        for measure in BEST_IDEA_MEASURES:
            count_rows[measure][row] = counts[measure]
            holder_rows[measure][row] = holders[measure]

    panels: dict[tuple[str, str], pd.DataFrame] = {}
    for measure in BEST_IDEA_MEASURES:
        count_frame = pd.DataFrame(count_rows[measure], index=index, columns=universe)
        holder_frame = pd.DataFrame(holder_rows[measure], index=index, columns=universe)
        panels[(measure, "count")] = count_frame
        with np.errstate(invalid="ignore", divide="ignore"):
            share = count_frame / holder_frame.where(holder_frame > 0)
        panels[(measure, "share")] = share
    return panels


# --- the signal --------------------------------------------------------------


def signal_best_ideas(history: CrossSectionalData, *, panel: pd.DataFrame) -> pd.Series:
    """The formation-date row of ONE point-in-time best-idea step panel.

    All the real work -- the arg max over each manager's book, the
    filing-date visibility, the staleness bound -- already happened in the
    builders above. This function only reads a single row.

    WHY THE PANEL ARRIVES BY CLOSURE RATHER THAN AS fundamental_signal,
    and why that is still safe. The DSR denominator must be this family's
    whole pre-declared grid (36), and sigma_sr must be the dispersion of
    all 36 sibling Sharpes -- but the harness carries exactly ONE
    fundamental_signal frame per screening call, and this family has SIX
    distinct panels. Screening them in six separate calls would silently
    set n_trials to 6 and compute sigma_sr from 6 siblings, which would
    UNDERSTATE the multiple-comparisons correction on every row. So all
    36 specs run in one call and each carries its own panel by closure --
    exactly the relationship cross_sectional_asset_growth's
    industry-neutral signal has to its bucket_frame.

    The row is read at `frame.index[-1]`, the formation timestamp of the
    history view the harness has ALREADY truncated to rows <= the
    formation date. So the only row this function can reach is the
    formation date's own, and a value dated after it is unreachable by
    construction -- which is asserted directly by a tamper test in
    test_cross_sectional_best_ideas.py rather than assumed.

    NaN cells refuse the ticker from ranking, the correct answer for "no
    eligible manager's visible filing bears on this name here"."""
    frame = history.fundamental_signal
    if frame is None:
        raise ValueError(
            "signal_best_ideas requires CrossSectionalData.fundamental_signal; the spec must "
            "set requires_fundamental_signal=True and the caller must supply the frame."
        )
    formation_ts = frame.index[-1]
    row = panel.loc[formation_ts].reindex(frame.columns).astype(float)
    return row.where(np.isfinite(row))


def build_best_ideas_family(
    measure: str, aggregation: str, panel: pd.DataFrame
) -> list[CrossSectionalSpec]:
    """The 6 specs for one (measure, aggregation) panel, bound to that
    panel. The full 36-spec grid is the six of these."""
    if measure not in BEST_IDEA_MEASURES:
        raise ValueError(f"unknown best-idea measure {measure!r}")
    if aggregation not in BEST_IDEAS_AGGREGATIONS:
        raise ValueError(f"unknown aggregation {aggregation!r}")
    specs: list[CrossSectionalSpec] = []
    for holding in BEST_IDEAS_HOLDING_DAYS:
        for suffix, rank_fraction in BEST_IDEAS_RANK_FRACTIONS:
            specs.append(
                CrossSectionalSpec(
                    pattern_id=f"bi_{measure}_{aggregation}_h{holding}{suffix}",
                    family=BEST_IDEAS_FAMILY,
                    citation=BEST_IDEAS_CITATION,
                    signal_fn=partial(signal_best_ideas, panel=panel),
                    lookback_days=BEST_IDEAS_SIGNAL_LOOKBACK_ROWS,
                    holding_days=holding,
                    portfolio="long_short",
                    rank_fraction=rank_fraction,
                    requires_fundamental_signal=True,
                )
            )
    assert len(specs) == len(BEST_IDEAS_HOLDING_DAYS) * len(BEST_IDEAS_RANK_FRACTIONS) == 6
    return specs


def all_best_ideas_specs(
    panels: dict[tuple[str, str], pd.DataFrame],
) -> list[CrossSectionalSpec]:
    """Every spec in the pre-declared grid, in ONE list, so the whole grid
    is screened in a single call under a single 36-trial denominator."""
    specs = [
        spec
        for measure in BEST_IDEA_MEASURES
        for aggregation in BEST_IDEAS_AGGREGATIONS
        for spec in build_best_ideas_family(measure, aggregation, panels[(measure, aggregation)])
    ]
    assert len(specs) == BEST_IDEAS_N_TRIALS == 36, (
        f"best ideas built {len(specs)} definitions; the declared grid implies "
        f"{BEST_IDEAS_N_TRIALS} and the pre-registration fixed exactly 36. All three must "
        "agree — a drift silently changes this family's DSR denominator."
    )
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    assert all(s.requires_fundamental_signal for s in specs)
    assert all(s.portfolio == "long_short" for s in specs)
    assert 21 not in BEST_IDEAS_HOLDING_DAYS, (
        "monthly holds are excluded up front: 13F refreshes quarterly, so a 21-day hold "
        "re-pays turnover on an unchanged ranking."
    )
    return specs


def default_best_ideas_config() -> CrossSectionalConfig:
    """A fresh config per call (the harness writes formation_start onto
    whatever it is given)."""
    return CrossSectionalConfig(
        cost_bps=BEST_IDEAS_COST_BPS,
        financing_bps_per_year=BEST_IDEAS_FINANCING_BPS_PER_YEAR,
    )


# --- production entry point --------------------------------------------------


@dataclass
class BestIdeasScreeningSummary:
    """run_best_ideas_screening's full result: the screening output plus
    every measured coverage number a reader needs to interpret it."""

    results: list[CrossSectionalScreeningResult]
    n_trials: int
    universe_size: int
    missing_price_data: list[str]
    panel_start: date | None
    panel_end: date | None
    formation_start: date
    quarters_parsed: list[str] = field(default_factory=list)
    n_manager_views: int = 0
    n_distinct_managers: int = 0
    cusip_map_size: int = 0
    universe_tickers_with_cusip: int = 0
    universe_tickers_without_cusip: list[str] = field(default_factory=list)
    diagnostics: BestIdeasBuildDiagnostics = field(default_factory=BestIdeasBuildDiagnostics)
    # measure -> median number of managers naming a ranked name, measured
    # on the realized panel; the honest power number for this family.
    panel_nonzero_rate: dict[str, float] = field(default_factory=dict)
    min_filing_lag_days: int = 0
    median_filing_lag_days: float = float("nan")
    cost_bps: float = BEST_IDEAS_COST_BPS
    financing_bps_per_year: float = BEST_IDEAS_FINANCING_BPS_PER_YEAR
    warnings: list[str] = field(default_factory=list)


def load_cusip_map_for_universe(
    provider: Form13FProvider, universe: list[str]
) -> tuple[CusipTickerMap, list[str], list[str]]:
    """Build the dated CUSIP<->ticker map from every cached SEC
    fails-to-deliver file, restricted to this family's universe.

    Returns (map, universe tickers that never resolved, FTD stamps that
    yielded no rows at all). Both lists are REPORTED, never silently
    dropped.

    THE THIRD RETURN VALUE EXISTS BECAUSE ITS ABSENCE HID A REAL BUG. An
    archive that parses to zero rows raises nothing and looks exactly like
    an archive of securities that all fell outside the universe, so a
    member-naming change at SEC removed 31 of 107 archives -- every file
    from 202207a to 202604a -- from the map with no symptom anywhere. A
    zero-row archive is now surfaced as a warning on the run, because the
    only honest way to report identifier coverage is to know which of the
    inputs actually contributed."""
    triples: list[tuple[date, str, str]] = []
    wanted = set(universe)
    empty_stamps: list[str] = []
    for stamp in provider.available_ftd_stamps():
        try:
            parsed = parse_ftd_archive(provider.get_ftd_archive(stamp))
        except (RuntimeError, ValueError, KeyError):
            logger.warning("fails-to-deliver archive %s could not be parsed", stamp)
            empty_stamps.append(stamp)
            continue
        if not parsed:
            logger.warning("fails-to-deliver archive %s parsed to ZERO rows", stamp)
            empty_stamps.append(stamp)
        triples.extend(parsed)
    cusip_map = build_cusip_ticker_map(triples, restrict_to=wanted)
    resolved = cusip_map.tickers()
    return cusip_map, sorted(wanted - resolved), empty_stamps


def run_best_ideas_screening(
    start: date = MEMBERSHIP_DATA_START,
    end: date | None = None,
    provider: YFinanceProvider | None = None,
    form13f: Form13FProvider | None = None,
    config: CrossSectionalConfig | None = None,
) -> BestIdeasScreeningSummary:
    """THE production entry point: parse every cached 13F quarter, build
    the CUSIP map, replay filings into point-in-time manager views, build
    the six panels, and screen the 36 pre-declared specs under one
    36-trial DSR denominator."""
    if start < MEMBERSHIP_DATA_START:
        raise ValueError(
            f"Best-ideas screening start {start.isoformat()} predates point-in-time membership "
            f"coverage ({MEMBERSHIP_DATA_START.isoformat()})."
        )
    end = end if end is not None else date.today()  # noqa: DTZ011 — price-fetch end bound only
    provider = provider if provider is not None else YFinanceProvider()
    form13f = form13f if form13f is not None else Form13FProvider()
    config = config if config is not None else default_best_ideas_config()
    config.formation_start = start

    warnings: list[str] = []
    universe = sorted(get_universe_over(start, end))

    cusip_map, without_cusip, empty_ftd = load_cusip_map_for_universe(form13f, universe)
    if without_cusip:
        warnings.append(
            f"{len(without_cusip)} of {len(universe)} universe tickers never appear in any SEC "
            "fails-to-deliver file and can therefore never be matched to a 13F CUSIP."
        )
    if empty_ftd:
        warnings.append(
            f"{len(empty_ftd)} cached fails-to-deliver archives contributed ZERO rows to the "
            f"CUSIP map ({empty_ftd[:5]}{' ...' if len(empty_ftd) > 5 else ''}) — the dated map "
            "has a hole over those dates and identifier resolution there falls back on the "
            "nearest observation from outside it."
        )

    # PRICES FIRST, AND THE ORDER IS LOAD-BEARING. ManagerView stores best
    # ideas and holdings as INTEGER INDICES into a ticker list, and the
    # panel builder resolves those indices against the list it is given.
    # If views were built against the full universe but panels against the
    # PRICED subset (which is smaller, and in the price provider's own
    # column order), every index would silently point at a different
    # company. Fetching prices first means one list, `priced`, is used for
    # both, and the assertion below makes the coupling impossible to break
    # by a later edit.
    padded_start = start - timedelta(days=BEST_IDEAS_PRICE_HISTORY_PADDING_CALENDAR_DAYS)
    close, missing_price = provider.get_price_history(universe, padded_start, end)
    if close.empty:
        return BestIdeasScreeningSummary(
            results=[],
            n_trials=BEST_IDEAS_N_TRIALS,
            universe_size=len(universe),
            missing_price_data=missing_price,
            panel_start=None,
            panel_end=None,
            formation_start=start,
            quarters_parsed=form13f.available_quarters(),
            warnings=[*warnings, "No price data resolved for any universe ticker."],
        )
    if missing_price:
        warnings.append(
            f"{len(missing_price)} of {len(universe)} universe tickers resolved no price data "
            "(the standing departed-member yfinance gap — see cross_sectional.py)."
        )

    # THE one ticker list, used to index views AND to label panels.
    priced = list(close.columns)

    quarters = form13f.available_quarters()
    filings_by_quarter: list[list[Form13FFiling]] = []
    parse_diag = Form13FParseDiagnostics()
    for quarter in quarters:
        filings, diag = parse_quarter_archive(form13f.get_quarter_archive(quarter))
        filings_by_quarter.append(filings)
        parse_diag.merge(diag)

    views, build_diag = build_manager_views(filings_by_quarter, cusip_map, priced)
    build_diag.parse = parse_diag
    del filings_by_quarter  # ~5GB of holdings dicts; nothing below reads them

    panels = build_best_idea_panels(close, views, priced)

    nonzero: dict[str, float] = {
        measure: float((panels[(measure, "count")].to_numpy() > 0).mean())
        for measure in BEST_IDEA_MEASURES
    }

    # ONE screening call for the WHOLE 36-spec grid. The frame handed to
    # the harness is the canonical conviction/count panel — it establishes
    # the formation calendar and the row slicing; each spec reads its OWN
    # panel by closure at that same formation timestamp (see
    # signal_best_ideas). Screening the six panels separately would set
    # n_trials to 6 and compute sigma_sr from 6 siblings, understating the
    # multiple-comparisons correction the pre-registration fixed at 36.
    results: list[CrossSectionalScreeningResult] = screen_cross_sectional_universe(
        CrossSectionalData(close=close, fundamental_signal=panels[("conviction", "count")]),
        all_best_ideas_specs(panels),
        config,
    )

    lags = build_diag.filing_lag_days
    return BestIdeasScreeningSummary(
        results=results,
        n_trials=BEST_IDEAS_N_TRIALS,
        universe_size=len(universe),
        missing_price_data=missing_price,
        panel_start=close.index[0].date(),
        panel_end=close.index[-1].date(),
        formation_start=start,
        quarters_parsed=quarters,
        n_manager_views=len(views),
        n_distinct_managers=len({v.cik for v in views}),
        cusip_map_size=len(cusip_map.observations),
        universe_tickers_with_cusip=len(cusip_map.tickers()),
        universe_tickers_without_cusip=without_cusip,
        diagnostics=build_diag,
        panel_nonzero_rate=nonzero,
        min_filing_lag_days=min(lags) if lags else 0,
        median_filing_lag_days=float(np.median(lags)) if lags else float("nan"),
        cost_bps=config.cost_bps,
        financing_bps_per_year=config.financing_bps_per_year,
        warnings=warnings,
    )
