"""FRAZZINI & LAMONT (2008) "DUMB MONEY" — the counterfactual-ownership FLOW
measure, and the calendar-time quintile portfolios sorted on it.

THE SOURCE
==========
Frazzini, Andrea and Owen A. Lamont, "Dumb money: Mutual fund flows and the
cross-section of stock returns", Journal of Financial Economics 88(2), May
2008, pp. 299-322. DOI 10.1016/j.jfineco.2007.07.001.

THE PUBLISHED ARTICLE ITSELF was read (sha256 3c39e8ff..., 24pp, from the
corresponding author's own NYU Stern page), not a working-paper substitute --
unlike this queue's margin_credit / ipo_lockup / quarter_end_marking /
coval_stafford builds, none of which could get past a paywall. So every
equation, table and page number in this module is the PUBLISHED one and needs
no "may be renumbered" caveat. Provenance:
data/research_runs/frazzini_lamont_dumb_money_SOURCES.md.

WHAT THE MEASURE ACTUALLY IS (and what it is NOT)
=================================================
FLOW is NOT an average of the flows of the funds holding a stock. That was the
build brief's description and it is wrong; the correction is recorded in
section 2 of the pre-registration. FLOW is a DIFFERENCE OF TWO OWNERSHIP
LEVELS -- actual mutual-fund ownership of the stock, minus the ownership that
would have obtained if every fund had received proportional inflows -- and it
is denominated in PERCENT OF THE STOCK'S MARKET CAPITALISATION. Section 2,
p.301, verbatim:

    "Our central variable is FLOW, the percent of the shares of a given stock
     owned by mutual funds that is attributable to fund flows. This variable is
     defined as the actual ownership by mutual funds minus the ownership that
     would have occurred if every fund had received identical proportional
     inflows, every fund manager chose the same portfolio weights in different
     stocks as he actually did, and stock prices were the same as they actually
     were."

Eqs. (6), (7), (8), p.303:

    z_jt    = ( SUM_i  x_it   w_ijt TNA^Agg_t ) / MKTCAP_jt              (6)
    zhat_jt = ( SUM_i  xhat_it w_ijt TNA^Agg_t ) / MKTCAP_jt             (7)
    FLOW_jt = z_jt - zhat_jt                                             (8)

with x_it = TNA^i_t / TNA^Agg_t (Eq. 4) the fund's actual share of the sector
and xhat_it = dTNA^i_t / dTNA^Agg_t (Eq. 5) its counterfactual share.

THE FORM ACTUALLY COMPUTED HERE, and why it is the same thing. Substituting
w_ijt = V_ijt / TNA^i_t, where V_ijt is the DOLLAR VALUE of fund i's position
in stock j, and x_it TNA^Agg_t = TNA^i_t, Eqs. (6)-(8) collapse to

    z_jt    = SUM_i V_ijt / MKTCAP_jt
    zhat_jt = (TNA^Agg_t / dTNA^Agg_t) * SUM_i V_ijt (dTNA^i_t / TNA^i_t)
              / MKTCAP_jt

i.e. each fund's dollar position rescaled by its own counterfactual-to-actual
TNA ratio, times one global normaliser. That is an algebraic rearrangement of
the paper's own equations, not a simplification of them: no term is dropped.
It is written this way because N-PORT reports position VALUE directly, so
forming w_ijt only to multiply it back out would introduce a division and a
multiplication by TNA^i_t for no gain. `stock_flow` documents the step again
at the point of use.

Note what this means for the sum over i: a fund holding none of stock j
contributes a ZERO term. Bond funds are therefore invisible in the per-stock
inputs -- but they are NOT harmless, because they enter TNA^Agg and F^Agg and
so move every equity fund's counterfactual. That is why `equity_fund_series`
exists and why the paper's own "domestic equity funds" restriction (p.302) is
enforced rather than skipped.

THE COUNTERFACTUAL, AND AN AMBIGUITY IN THE PAPER'S OWN EXPOSITION
==================================================================
Counterfactual TNA is built by redistributing the sector's AGGREGATE flow pro
rata (Eqs. 2/11 and 3/12, pp.302 and 320):

    Fhat^i_s = ( TNA^i_{t-k} / TNA^Agg_{t-k} ) * F^Agg_s        (2) = (11)
    dTNA^i_s = ( 1 + R^i_s ) dTNA^i_{s-1} + Fhat^i_s            (3) = (12)

The MAIN TEXT (p.302) describes a ROLLING WINDOW: "In order to compute the
FLOW at date t, we start by looking at the total net asset value of the fund at
date t-k. Then, for every date s we track the evolution of the fund's
counterfactual TNA using [(2) and (3)], t-k <= s <= t", repeating "every
quarter t, and storing the resulting dTNA^i_t at the end of each rolling
window". So: initialise dTNA at t-k to the ACTUAL TNA, hold the pro-rata share
fixed at t-k weights, recurse forward.

APPENDIX TABLE A1 (p.321) DOES SOMETHING ELSE. Every one of its 21 published
counterfactual cells was re-derived by hand during pre-registration and they
reproduce EXACTLY -- but only under a recursion that never restarts and that
re-anchors the pro-rata share every period. For Fund 1 in 1982 the table prints
292, which is 1.05*210 + (160/315)*140 = 291.6 (carrying the prior
COUNTERFACTUAL 210 forward); the main-text reading with a restart at t-k would
give 1.05*160 + 71.1 = 239.1.

Resolution, fixed in the pre-registration BEFORE any result existed:
`CounterfactualVariant.ROLLING` (main text) is PRIMARY, because it is what the
equations' own subscripts say and the only reading under which "the end of each
rolling window" means anything. `CounterfactualVariant.CONTINUOUS` (Table A1)
is computed as a declared ROBUSTNESS ARM, outside the DSR grid. Table A1 is
still used as the C6 unit test of the building blocks both readings share.

THE PAPER'S OWN NUMBERS, for orientation (Table 2 Panel B, p.307,
value-weighted quintiles, monthly excess returns, L/S = Q5 high MINUS Q1 low):
3-month +0.033 (t 0.13) / 6-month -0.363 (-2.08) / 1-year -0.501 (-2.61) /
3-year -0.846 (-3.30) / 5-year -0.394 (-1.35). NOTE THE SIGN: the paper's
headline spread is NEGATIVE, so a tradeable portfolio is LONG Q1 and SHORT Q5,
the negative of the paper's reported column. `Leg.LONG_SHORT` is Q1 - Q5 for
exactly that reason, and check C4 exists so the sign cannot be quietly flipped.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
=========================================
It does not fetch, it does not decide a flow definition (Item B.6.a - B.6.c,
settled in a1d64b3 and reused), and it registers nothing. Spec grid, verdict
rule and the C1-C6 checks live in
data/research_runs/frazzini_lamont_dumb_money_PREREGISTRATION.txt, committed
before any strategy return was computed.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# Constants — every one of them the paper's own, or named as a judgement call
# =============================================================================

DUMB_MONEY_FAMILY_KEY = "dumb_money"
DUMB_MONEY_SMALL_CAP_FAMILY_KEY = "small_cap_dumb_money"

DUMB_MONEY_CITATION = (
    "Frazzini, A. and O. A. Lamont (2008), 'Dumb money: Mutual fund flows and "
    "the cross-section of stock returns', Journal of Financial Economics "
    "88(2), 299-322, doi:10.1016/j.jfineco.2007.07.001. Eqs. (2),(3),(6),(7),"
    "(8) pp.302-303; Eqs. (11),(12) and Table A1 p.320-321; Table 2 p.307."
)

# Table 2's own rows (p.307), minus the 5-year row. The 5-year horizon needs 20
# of the 27 published N-PORT quarters as lookback and is EXCLUDED FOR
# INFEASIBILITY, declared in pre-registration section 4(a) before any result --
# not dropped after seeing one. It is also the paper's weakest published
# horizon (t = -1.35).
HORIZON_QUARTERS: dict[str, int] = {
    "3month": 1,
    "6month": 2,
    "1year": 4,
    "3year": 12,
}

# Section 3, p.306: "we rank stocks in ascending order based on the latest
# available FLOW and assign them to one of five quintile portfolios."
N_QUINTILES = 5

# NOT the paper's number, and flagged as such wherever it appears. F-L restrict
# to "domestic equity funds" (p.302) using CRSP's fund-type codes; N-PORT
# publishes no fund-type field at all (verified by enumerating all 32 members
# of a bulk ZIP), so equity-ness is inferred from portfolio composition. 0.80
# is a judgement call frozen in the pre-registration; 0.50/0.90 sensitivity is
# an EXPLORATORY diagnostic outside the DSR grid (check C3).
EQUITY_ASSET_SHARE_MIN = 0.80
ASSET_CAT_EQUITY_COMMON = "EC"

# SEC Release 33-10231: N-PORT data is public only 60 days after the third
# month of the fund's fiscal quarter. Used to pick which calendar quarter is
# knowable at a formation date, alongside a belt-and-braces FILING_DATE gate.
PUBLICATION_LAG_DAYS = 60

# A leg with fewer than this many names is not formed; that month earns 0.0 for
# the leg rather than being dropped (dropping idle months overstates, the same
# reasoning coval_stafford took from Coval-Stafford's own footnote 12).
MIN_FIRMS_PER_LEG = 10

# Below this the fund's TNA ratio is numerically meaningless and the fund is
# refused rather than allowed to produce a wild counterfactual ratio.
MIN_FUND_NET_ASSETS = 1_000_000.0

# 4 horizons x 3 legs x 2 universes, frozen in pre-registration section 6.
DUMB_MONEY_N_TRIALS = 24

MONTHS_PER_YEAR = 12.0


class CounterfactualVariant(str, Enum):
    """Which of the paper's two mutually inconsistent descriptions to follow.

    ROLLING is PRIMARY (main text, p.302, and Eq. (11)'s own t-k subscripts).
    CONTINUOUS reproduces Appendix Table A1's arithmetic and is a declared
    robustness arm only. See the module docstring.
    """

    ROLLING = "rolling"
    CONTINUOUS = "continuous"


class Leg(str, Enum):
    """Table 2's columns. LONG_SHORT is Q1 - Q5, the NEGATIVE of the paper's
    own reported L/S column, because the paper's spread is negative and a
    tradeable portfolio must be long the low-flow quintile."""

    LONG_LOW_FLOW = "long_low_flow"
    SHORT_HIGH_FLOW = "short_high_flow"
    LONG_SHORT = "long_short"


# =============================================================================
# Fund-quarter inputs
# =============================================================================


@dataclass(frozen=True)
class FundQuarterState:
    """One equity fund series' state for one CALENDAR quarter.

    `quarter` is the calendar quarter containing the filing's REPORT_DATE.
    N-PORT publishes only the third month of each fund's own FISCAL quarter and
    fiscal year-ends differ, so these windows are staggered by up to two months
    across funds -- a limitation with no analogue in the paper, disclosed in
    pre-registration section 4(e) rather than corrected, because no correction
    is available from the published data.
    """

    series_id: str
    quarter: pd.Period
    accession: str
    filing_date: date
    report_date: date
    net_assets: float
    external_flow: float
    quarterly_return: float


@dataclass
class DumbMoneyDiagnostics:
    """Every refusal counted. Nothing here is ever silent."""

    n_filings_seen: int = 0
    n_states_built: int = 0
    n_equity_series: int = 0
    n_non_equity_series: int = 0
    n_snapshot_dates: int = 0
    n_flow_cells: int = 0
    n_refused: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    n_survivors: list[int] = field(default_factory=list)
    n_newborns: list[int] = field(default_factory=list)
    n_negative_tna_overrides: int = 0

    def refuse(self, reason: str, count: int = 1) -> None:
        self.n_refused[reason] += count

    def summary(self) -> dict[str, object]:
        return {
            "n_filings_seen": self.n_filings_seen,
            "n_states_built": self.n_states_built,
            "n_equity_series": self.n_equity_series,
            "n_non_equity_series": self.n_non_equity_series,
            "n_snapshot_dates": self.n_snapshot_dates,
            "n_flow_cells": self.n_flow_cells,
            "n_negative_tna_overrides": self.n_negative_tna_overrides,
            "median_survivors": (
                float(np.median(self.n_survivors)) if self.n_survivors else None
            ),
            "median_newborns": (
                float(np.median(self.n_newborns)) if self.n_newborns else None
            ),
            "refused": dict(sorted(self.n_refused.items())),
        }


def equity_fund_series(
    category_rows: Sequence[Mapping[str, str]],
    accession_to_series: Mapping[str, str],
    *,
    minimum_equity_share: float = EQUITY_ASSET_SHARE_MIN,
    diagnostics: DumbMoneyDiagnostics | None = None,
) -> set[str]:
    """Series ids whose portfolios are at least `minimum_equity_share` common
    equity, from the per-accession/per-ASSET_CAT totals produced by
    data/research_runs/fetch_nport_fund_asset_categories.py.

    Implements the paper's "domestic equity funds" universe restriction
    (p.302). TWO HONEST GAPS, neither fixable from N-PORT:

      * DOMESTIC is not testable. ASSET_CAT does not encode issuer country, so
        this selects EQUITY funds, not DOMESTIC equity funds. An international
        equity fund is kept where F-L would have dropped it.
      * The threshold is not the paper's. F-L used CRSP fund-type codes. 0.80
        is a judgement call frozen in the pre-registration and is not tuned.

    A series is kept if ANY of its accessions clears the bar in the quarters
    seen; equity-ness is a property of the fund's mandate, not of one filing,
    and a fund does not stop being an equity fund in a quarter it happened to
    hold extra cash.
    """
    by_accession: dict[str, dict[str, float]] = defaultdict(dict)
    for row in category_rows:
        accession = row["ACCESSION_NUMBER"]
        try:
            value = float(row["VALUE_SUM"])
        except (TypeError, ValueError):
            if diagnostics is not None:
                diagnostics.refuse("category_value_unparseable")
            continue
        # A BLANK asset category is real as-filed data, not a parse failure:
        # some filers leave Item C.7 empty. It is kept as its own bucket so it
        # still counts toward the denominator -- a fund whose portfolio is half
        # uncategorised is not thereby 100% equity -- but it can never be
        # mistaken for common equity.
        raw_category = row.get("ASSET_CAT")
        category = raw_category.strip() if isinstance(raw_category, str) else ""
        by_accession[accession][category or "__uncategorised__"] = value

    equity: set[str] = set()
    non_equity: set[str] = set()
    for accession, categories in by_accession.items():
        series = accession_to_series.get(accession)
        if series is None:
            continue
        # Negative category totals (short positions) would make a share
        # meaningless, so the denominator is the sum of ABSOLUTE category
        # values -- gross portfolio size, which is what "how much of this fund
        # is equity" means.
        total = sum(abs(v) for v in categories.values())
        if total <= 0.0:
            if diagnostics is not None:
                diagnostics.refuse("fund_reports_no_positions")
            continue
        share = categories.get(ASSET_CAT_EQUITY_COMMON, 0.0) / total
        if share >= minimum_equity_share:
            equity.add(series)
        else:
            non_equity.add(series)

    if diagnostics is not None:
        diagnostics.n_equity_series = len(equity)
        diagnostics.n_non_equity_series = len(non_equity - equity)
    return equity


def build_fund_quarter_states(
    filings: Sequence["object"],
    returns_by_series: Mapping[str, Mapping[pd.Timestamp, float]],
    *,
    keep_series: set[str] | None = None,
    diagnostics: DumbMoneyDiagnostics | None = None,
) -> dict[str, dict[pd.Period, list[FundQuarterState]]]:
    """{series_id: {calendar quarter: [every candidate filing]}} from N-PORT rows.

    EVERY filing for a (series, quarter) is kept, not just the latest, and the
    amendment tie-break is deferred to `_public_states` where it can be made
    POINT-IN-TIME. This is a corrected defect, not a design flourish: choosing
    the latest-filed amendment here used FUTURE information, and then the
    snapshot-time FILING_DATE gate discarded that choice as not-yet-public,
    silently dropping a fund-quarter that genuinely WAS observable at the time
    via its earlier filing. Measured on the real cache: 5,175 (series, quarter)
    keys carry more than one filing, median filing-date spread 90 days and up
    to 1,628, so the affected window is wide. Found by the independent checker
    (V3), which gated before choosing and therefore disagreed; the checker was
    right and this function was wrong.

    The quarterly return compounds the filing's own three reported monthly
    returns (Item B.5.a), which are the report month and the two before it --
    exactly the window the filing's Item B.6 flow fields also cover, so return
    and flow describe the same three months.

    Amendments: where two filings cover the same series and quarter, the one
    filed LAST wins.
    """
    diagnostics = diagnostics or DumbMoneyDiagnostics()
    out: dict[str, dict[pd.Period, list[FundQuarterState]]] = defaultdict(dict)

    for filing in filings:
        diagnostics.n_filings_seen += 1
        series = filing.series_id
        if keep_series is not None and series not in keep_series:
            diagnostics.refuse("series_not_equity_fund")
            continue
        if filing.filing_date < filing.report_date:
            # A filing dated before the period it reports on cannot be real;
            # the same refusal the fire-sale checker had to add.
            diagnostics.refuse("filing_date_before_report_date")
            continue
        if not np.isfinite(filing.net_assets) or filing.net_assets < MIN_FUND_NET_ASSETS:
            diagnostics.refuse("fund_below_size_floor")
            continue
        months = returns_by_series.get(series)
        if not months:
            diagnostics.refuse("no_monthly_returns_for_series")
            continue
        report_month = pd.Timestamp(filing.report_date) + pd.offsets.MonthEnd(0)
        window = [
            report_month - pd.offsets.MonthEnd(2),
            report_month - pd.offsets.MonthEnd(1),
            report_month,
        ]
        values = [months.get(m) for m in window]
        if any(v is None or not np.isfinite(v) for v in values):
            diagnostics.refuse("incomplete_quarterly_return")
            continue
        quarterly_return = float(np.prod([1.0 + v for v in values]) - 1.0)

        quarter = pd.Period(filing.report_date, freq="Q")
        out[series].setdefault(quarter, []).append(FundQuarterState(
            series_id=series,
            quarter=quarter,
            accession=filing.accession,
            filing_date=filing.filing_date,
            report_date=filing.report_date,
            net_assets=float(filing.net_assets),
            external_flow=float(filing.external_flow_dollars),
            quarterly_return=quarterly_return,
        ))
        diagnostics.n_states_built += 1

    return {
        series: {q: sorted(v, key=lambda s: s.filing_date) for q, v in sorted(quarters.items())}
        for series, quarters in out.items()
    }


# =============================================================================
# The counterfactual — Eqs. (2)/(11) and (3)/(12), Appendix A.1
# =============================================================================


@dataclass
class CounterfactualResult:
    """dTNA^i_t for every fund with one, plus the aggregates Eq. (5) needs."""

    counterfactual_tna: dict[str, float]
    actual_tna: dict[str, float]
    survivors: set[str]
    newborns: set[str]
    aggregate_actual: float
    aggregate_counterfactual: float


def _step_membership(
    states: Mapping[str, Mapping[pd.Period, FundQuarterState]],
    members: Sequence[str],
    previous: pd.Period,
    current: pd.Period,
) -> tuple[dict[str, float], float, float, set[str]]:
    """Appendix A.1's two aggregate rows for one step, plus the dying set.

    Returns
      lagged      -- per-fund TNA at `previous`, for funds ALIVE at both ends
      lagged_total-- their sum, Eq. (11)'s denominator TNA^Agg_{t-k}
      flow_total  -- F^Agg_s: the actual flow at `current` of every fund alive
                     at `current` and not dying, INCLUDING newborns
      dying       -- funds alive at `previous` but not at `current`

    Table A1 (p.321) prints both aggregate rows explicitly and they are the
    check on this function:
      1981: "NAV, last year, of funds existing this year" = 150 = Fund 1's 100
            + Fund 2's 50, EXCLUDING newborn Fund 3 which has no 1980 NAV;
            "FLOW of non-dying funds" = 150 = 50 + 50 + 50, INCLUDING newborn
            Fund 3's 50. The two rows have different membership, which is
            exactly what Appendix A.1's prose says: F^Agg covers "all funds
            alive in quarter t (including funds that were recently born, but
            excluding funds that die in month t)".
      1983: denominator 313 = 268 + 45, Fund 2 having died; flow 150 = 100 +
            50, excluding dying Fund 2's -144.

    DEATH is taken to be either absence at `current` or a reported TNA of zero
    there. Table A1 represents Fund 2's 1983 death the second way (it still
    prints a flow of -144 against a NAV of 0); real N-PORT data represents it
    the first way, because a dead fund simply stops filing. Both are handled so
    that the same code path serves the unit test and the panel.
    """
    lagged: dict[str, float] = {}
    dying: set[str] = set()
    flow_total = 0.0
    for series in members:
        by_quarter = states.get(series)
        if not by_quarter:
            continue
        before = by_quarter.get(previous)
        now = by_quarter.get(current)
        alive_now = now is not None and now.net_assets > 0.0
        if before is not None and not alive_now:
            dying.add(series)
            continue
        if not alive_now:
            continue
        flow_total += now.external_flow
        if before is not None:
            lagged[series] = before.net_assets
    return lagged, sum(lagged.values()), flow_total, dying


def counterfactual_tna(
    states: Mapping[str, Mapping[pd.Period, FundQuarterState]],
    window: Sequence[pd.Period],
    *,
    variant: CounterfactualVariant = CounterfactualVariant.ROLLING,
    diagnostics: DumbMoneyDiagnostics | None = None,
) -> CounterfactualResult:
    """Counterfactual TNA at `window[-1]`, per Eqs. (2)/(11) and (3)/(12).

    `window` is t-k ... t inclusive, ascending, contiguous calendar quarters.

    THE RULES, all from Appendix A.1 p.320, quoted where they bite:

    NEWBORNS. "We assign a counterfactual total net asset value of zero to
    funds that were newly created in the past k quarters. New funds represent
    new flows, but in the counterfactual exercise they do not receive assets
    for the first k quarters." So a fund appearing mid-window starts at
    dTNA = 0 and only begins receiving redistributed flow at the NEXT step,
    once it has a lagged TNA to be weighted by. Its entire ownership therefore
    counts as flow-driven, which is the economically intended reading. Table A1
    is the check: Fund 3, born 1981, has counterfactual TNA blank (zero) in
    1981 and 22 in 1982.

    DEATHS. "For funds that die in quarter s+1 (so that their last TNA is
    quarter s), we set Fhat^i_{s+1} = -dTNA^i_s and dTNA^i_{s+h} = 0 for all
    h > 0." Note the outflow is the COUNTERFACTUAL TNA, not the actual one:
    Table A1 assigns Fund 2 a 1983 counterfactual flow of -141, its
    counterfactual 1982 TNA, where its ACTUAL 1982 TNA was 144.

    NEGATIVE-TNA OVERRIDE. "Note that Eq. (12) does not guarantee that
    counterfactual total net asset values are always non-negative in quarters
    where we have aggregate outflows. In this case we override Eq. (12), set
    dTNA^i_t = 0 and redistribute the corresponding counterfactual flows to the
    remaining funds, to keep the total aggregate dollar outflow the same in
    both the counterfactual and actual case." Implemented with the
    redistribution, iterated because pinning one fund can push another below
    zero. The paper measures this at 0.08% of its sample over 12 quarters.

    THE TWO VARIANTS (module docstring). Within a single window the ONLY
    difference is the pro-rata share's anchor:
      ROLLING    -- share fixed at the window's own t-k weights (Eq. 11's
                    subscripts). The main text. PRIMARY.
      CONTINUOUS -- share re-anchored to the previous quarter at every step.
                    Reproduces Appendix Table A1. Robustness arm only.
    Both initialise dTNA at the window start to the ACTUAL TNA there, so
    Table A1 is simply one long CONTINUOUS window.
    """
    diagnostics = diagnostics or DumbMoneyDiagnostics()
    if len(window) < 2:
        raise ValueError("counterfactual_tna needs at least two quarters")
    start, end = window[0], window[-1]

    # Everyone who appears anywhere in the window takes part in the recursion:
    # newborns join partway, the dying leave partway, and both are needed to
    # keep F^Agg and the redistribution honest.
    members = sorted({s for s, q in states.items() if any(w in q for w in window)})
    if not members:
        diagnostics.refuse("no_funds_in_window")
        return CounterfactualResult({}, {}, set(), set(), 0.0, 0.0)

    counterfactual: dict[str, float] = {
        s: (states[s][start].net_assets if start in states[s] else 0.0) for s in members
    }
    dead: set[str] = set()

    # ROLLING's fixed anchor: the window's own t-k weights.
    fixed_lagged = {s: states[s][start].net_assets for s in members if start in states[s]}

    for position in range(1, len(window)):
        previous, step = window[position - 1], window[position]
        lagged, lagged_total, flow_total, dying = _step_membership(
            states, members, previous, step
        )

        # The death rule, applied before the redistribution so that the
        # departing counterfactual assets are not also handed out.
        for series in dying:
            if series in dead:
                continue
            dead.add(series)
            counterfactual[series] = 0.0

        if variant is CounterfactualVariant.ROLLING:
            weights = {s: w for s, w in fixed_lagged.items() if s in lagged}
        else:
            weights = dict(lagged)
        weights = {s: w for s, w in weights.items() if s not in dead}
        if sum(weights.values()) <= 0.0:
            diagnostics.refuse("non_positive_aggregate_tna")
            return CounterfactualResult({}, {}, set(), set(), 0.0, 0.0)

        pinned: set[str] = set()
        while True:
            denominator = sum(w for s, w in weights.items() if s not in pinned)
            proposed = dict(counterfactual)
            if denominator <= 0.0:
                diagnostics.refuse("redistribution_exhausted")
                for series in weights:
                    proposed[series] = 0.0
                break
            for series in members:
                if series in dead:
                    proposed[series] = 0.0
                    continue
                state = states[series].get(step)
                if state is None:
                    proposed[series] = counterfactual[series]
                    continue
                grown = (1.0 + state.quarterly_return) * counterfactual[series]
                if series in pinned or series not in weights:
                    # A newborn (no lagged TNA yet) grows but receives no
                    # redistributed flow this step; a pinned fund is held at 0.
                    proposed[series] = 0.0 if series in pinned else grown
                    continue
                proposed[series] = grown + (weights[series] / denominator) * flow_total
            breached = {
                s for s in weights if s not in pinned and proposed[s] < 0.0
            }
            if not breached:
                break
            pinned |= breached
            diagnostics.n_negative_tna_overrides += len(breached)
        counterfactual = {s: max(v, 0.0) for s, v in proposed.items()}

    present_at_end = {s for s in members if end in states[s] and states[s][end].net_assets > 0.0}
    survivors = {s for s in present_at_end if start in states[s]}
    newborns = present_at_end - survivors

    actual_tna = {s: states[s][end].net_assets for s in present_at_end}
    counterfactual_out = {s: counterfactual.get(s, 0.0) for s in present_at_end}

    diagnostics.n_survivors.append(len(survivors))
    diagnostics.n_newborns.append(len(newborns))
    return CounterfactualResult(
        counterfactual_tna=counterfactual_out,
        actual_tna=actual_tna,
        survivors=survivors,
        newborns=newborns,
        aggregate_actual=sum(actual_tna.values()),
        aggregate_counterfactual=sum(counterfactual_out.values()),
    )


def stock_flow(
    holdings_value: Mapping[str, Mapping[str, float]],
    counterfactual: CounterfactualResult,
    market_cap: Mapping[str, float],
) -> dict[str, float]:
    """FLOW_jt for every stock, Eq. (8) p.303.

    `holdings_value[series][ticker]` is the DOLLAR value of that fund's
    position (N-PORT CURRENCY_VALUE), which is w_ijt * TNA^i_t.

    Using the rearrangement derived in the module docstring:

        z_jt    = SUM_i V_ijt / MKTCAP_jt
        zhat_jt = (TNA^Agg_t / dTNA^Agg_t) * SUM_i V_ijt * (dTNA^i_t/TNA^i_t)
                  / MKTCAP_jt
        FLOW_jt = z_jt - zhat_jt

    The normaliser TNA^Agg_t / dTNA^Agg_t is a single scalar per date, so it
    cannot reorder stocks by itself; the cross-sectional content is entirely in
    each holder's own dTNA^i_t / TNA^i_t ratio, weighted by how much of the
    stock that holder owns. Returned in PERCENT, matching Table 1 Panel C and
    Table 2 Panel A, whose values (mean 0.54, sd 5.61) are percentages.
    """
    if counterfactual.aggregate_counterfactual <= 0.0:
        return {}
    normaliser = counterfactual.aggregate_actual / counterfactual.aggregate_counterfactual

    actual: dict[str, float] = defaultdict(float)
    counter: dict[str, float] = defaultdict(float)
    for series, positions in holdings_value.items():
        own_actual = counterfactual.actual_tna.get(series)
        if own_actual is None or own_actual <= 0.0:
            continue
        ratio = counterfactual.counterfactual_tna.get(series, 0.0) / own_actual
        for ticker, value in positions.items():
            if not np.isfinite(value):
                continue
            actual[ticker] += value
            counter[ticker] += value * ratio

    out: dict[str, float] = {}
    for ticker, actual_value in actual.items():
        cap = market_cap.get(ticker)
        if cap is None or not np.isfinite(cap) or cap <= 0.0:
            continue
        z = actual_value / cap
        z_hat = normaliser * counter[ticker] / cap
        out[ticker] = 100.0 * (z - z_hat)
    return out


# =============================================================================
# The panel: FLOW for every stock at every month-end, point-in-time
# =============================================================================


def month_end_snapshots(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """Last trading day of each month present in `index`."""
    frame = pd.Series(index, index=index)
    return sorted(frame.groupby([index.year, index.month]).max().tolist())


def latest_public_quarter(as_of: date) -> pd.Period:
    """The most recent calendar quarter whose N-PORT data can be public at
    `as_of`, per SEC Release 33-10231's 60-day rule.

    This bounds WHICH quarter may be looked at; a second, per-filing
    FILING_DATE gate in `build_flow_panels` then bounds WHICH FUNDS within it
    have actually filed. Both are needed: the rule gives the earliest possible
    publication date, while a late filer is genuinely unavailable past it.
    """
    return pd.Period(as_of - timedelta(days=PUBLICATION_LAG_DAYS), freq="Q") - 1


def build_flow_panels(
    states: Mapping[str, Mapping[pd.Period, Sequence[FundQuarterState]]],
    holdings: Mapping[str, Mapping[str, float]],
    market_cap: pd.DataFrame,
    snapshots: Sequence[pd.Timestamp],
    *,
    horizons: Mapping[str, int] = HORIZON_QUARTERS,
    variant: CounterfactualVariant = CounterfactualVariant.ROLLING,
    diagnostics: DumbMoneyDiagnostics | None = None,
) -> dict[str, pd.DataFrame]:
    """{horizon name: DataFrame of FLOW, month-end x ticker}, in percent.

    POINT-IN-TIME, twice over. At each snapshot date only filings with
    FILING_DATE <= that date are visible (`_public_states`), and only quarters
    already past the 60-day publication wall are eligible
    (`latest_public_quarter`). A fund that files late simply drops out of that
    snapshot rather than being back-filled.

    MARKET CAP is taken as of the HOLDINGS quarter-end, not the snapshot date,
    because Eq. (6)'s MKTCAP_jt is contemporaneous with the holdings it scales
    -- z_jt is "the percent of the stock held by mutual funds" on the reporting
    date. Using the snapshot date's cap would mix a stale numerator with a
    fresh denominator and make FLOW move with price between reports.
    """
    diagnostics = diagnostics or DumbMoneyDiagnostics()
    panels: dict[str, dict[pd.Timestamp, dict[str, float]]] = {
        name: {} for name in horizons
    }

    for snapshot in snapshots:
        as_of = snapshot.date()
        diagnostics.n_snapshot_dates += 1
        quarter = latest_public_quarter(as_of)
        public = _public_states(states, as_of)
        if not public:
            diagnostics.refuse("no_public_filings_at_snapshot")
            continue

        cap_row = _market_cap_at(market_cap, quarter)
        if cap_row is None:
            diagnostics.refuse("no_market_cap_for_quarter")
            continue

        for name, k in horizons.items():
            window = [quarter - offset for offset in range(k, -1, -1)]
            result = counterfactual_tna(
                public, window, variant=variant, diagnostics=diagnostics
            )
            if not result.actual_tna:
                diagnostics.refuse(f"empty_counterfactual_{name}")
                continue
            # Holdings are keyed by ACCESSION, so the positions used are the
            # ones on the very filing `_public_states` selected for this
            # snapshot -- not those of an amendment that was not public yet.
            holdings_value = {}
            for series in result.actual_tna:
                state = public.get(series, {}).get(quarter)
                if state is not None:
                    holdings_value[series] = holdings.get(state.accession, {})
            flow = stock_flow(holdings_value, result, cap_row)
            if not flow:
                diagnostics.refuse(f"empty_flow_{name}")
                continue
            panels[name][snapshot] = flow
            diagnostics.n_flow_cells += len(flow)

    return {
        name: pd.DataFrame.from_dict(rows, orient="index").sort_index()
        for name, rows in panels.items()
    }


def _public_states(
    states: Mapping[str, Mapping[pd.Period, Sequence[FundQuarterState]]], as_of: date
) -> dict[str, dict[pd.Period, FundQuarterState]]:
    """Collapse each quarter's candidate filings to the one a reader had on
    `as_of`: the LATEST-FILED among those already public.

    Doing the amendment tie-break HERE rather than at build time is what makes
    it point-in-time. An amendment filed after `as_of` must not displace the
    original that was genuinely available then -- and must not, by displacing
    it, delete the quarter altogether.
    """
    out: dict[str, dict[pd.Period, FundQuarterState]] = {}
    for series, by_quarter in states.items():
        visible: dict[pd.Period, FundQuarterState] = {}
        for quarter, candidates in by_quarter.items():
            public = [c for c in candidates if c.filing_date <= as_of]
            if public:
                visible[quarter] = max(public, key=lambda c: (c.filing_date, c.accession))
        if visible:
            out[series] = visible
    return out


def _market_cap_at(market_cap: pd.DataFrame, quarter: pd.Period) -> dict[str, float] | None:
    """Market caps on the last available date at or before the quarter end."""
    end = pd.Timestamp(quarter.end_time.date())
    position = market_cap.index.searchsorted(end, side="right") - 1
    if position < 0:
        return None
    row = market_cap.iloc[position]
    return {t: float(v) for t, v in row.items() if np.isfinite(v) and v > 0.0}


# =============================================================================
# Table 2's calendar-time quintile portfolios
# =============================================================================


@dataclass
class LegDiagnostics:
    n_months: int = 0
    n_formable: int = 0
    quintile_sizes: list[int] = field(default_factory=list)
    mean_flow_by_quintile: list[list[float]] = field(default_factory=list)

    def summary(self) -> dict[str, object]:
        by_quintile = (
            np.array(self.mean_flow_by_quintile, dtype=float)
            if self.mean_flow_by_quintile
            else None
        )
        return {
            "n_months": self.n_months,
            "n_formable": self.n_formable,
            "formable_fraction": (
                self.n_formable / self.n_months if self.n_months else 0.0
            ),
            "median_quintile_size": (
                float(np.median(self.quintile_sizes)) if self.quintile_sizes else None
            ),
            # Table 2 Panel A's own row: the time-series mean FLOW per quintile.
            "mean_flow_by_quintile": (
                [float(v) for v in by_quintile.mean(axis=0)] if by_quintile is not None else None
            ),
        }


def _value_weights(
    names: Sequence[str], caps: Mapping[str, float] | None
) -> dict[str, float]:
    """Value weights, the paper's own choice ("Portfolios are rebalanced
    monthly to maintain value weights", Table 2 caption). Falls back to equal
    weights only if no cap is available for any name, which is reported rather
    than silently absorbed."""
    if not names:
        return {}
    if caps is not None:
        weights = {n: float(caps.get(n, np.nan)) for n in names}
        usable = {n: w for n, w in weights.items() if np.isfinite(w) and w > 0.0}
        total = sum(usable.values())
        if usable and total > 0.0:
            return {n: w / total for n, w in usable.items()}
    return {n: 1.0 / len(names) for n in names}


def quintile_portfolio_returns(
    flow_panel: pd.DataFrame,
    close: pd.DataFrame,
    *,
    members_on,
    market_cap: pd.DataFrame,
    half_spread: pd.DataFrame | None,
    borrow_bps_per_year: float,
    diagnostics: LegDiagnostics | None = None,
) -> tuple[dict[Leg, pd.Series], LegDiagnostics]:
    """Monthly returns of Table 2's three tradeable legs.

    Section 3, p.306: "At the beginning of every calendar month, we rank stocks
    in ascending order based on the latest available FLOW and assign them to
    one of five quintile portfolios. ... We rebalance the portfolios every
    calendar month using value weights."

    SIGN. Q1 is the LOWEST-FLOW quintile and Q5 the highest. The paper's own
    L/S column is Q5 - Q1 and is NEGATIVE at every horizon past three months,
    so the TRADEABLE portfolio is its negative: LONG_SHORT here is Q1 - Q5.
    Check C4 exists so this cannot be quietly reinterpreted after the fact.

    MARKET HEDGING of the single-sided legs, declared in pre-registration
    section 6: LONG_LOW_FLOW is Q1 net of the value-weighted return of the same
    eligible universe, and SHORT_HIGH_FLOW is that universe return minus Q5.
    Over a 2021-2026 sample a raw long-only leg's Sharpe would mostly measure
    the equity risk premium rather than the dumb-money effect, and the paper's
    own inference comes from regression intercepts (Table 3) which is the same
    intent. It can only REMOVE return, never add it. LONG_SHORT needs no such
    adjustment.

    An unformable month earns 0.0 for every leg rather than being dropped.
    """
    diagnostics = diagnostics or LegDiagnostics()
    snapshots = [d for d in month_end_snapshots(close.index) if d in flow_panel.index]

    rows: dict[Leg, list[float]] = {leg: [] for leg in Leg}
    dates: list[pd.Timestamp] = []
    previous: dict[Leg, dict[str, float]] = {leg: {} for leg in Leg}
    monthly_borrow = borrow_bps_per_year / 1e4 / MONTHS_PER_YEAR

    all_months = month_end_snapshots(close.index)
    following_of = {d: all_months[i + 1] for i, d in enumerate(all_months[:-1])}

    for formation in snapshots:
        following = following_of.get(formation)
        if following is None:
            continue
        members = set(members_on(formation.date()))
        if not members:
            continue
        priced = close.loc[formation].notna() & close.loc[following].notna()
        tradable = members & set(close.columns[priced.to_numpy()])
        flows = flow_panel.loc[formation].dropna()
        eligible = sorted(tradable & set(flows.index))

        diagnostics.n_months += 1
        dates.append(following)
        if len(eligible) < N_QUINTILES * MIN_FIRMS_PER_LEG:
            for leg in Leg:
                rows[leg].append(0.0)
            continue
        diagnostics.n_formable += 1

        rets = (close.loc[following] / close.loc[formation]) - 1.0
        caps = {
            t: float(v)
            for t, v in market_cap.loc[formation].items()
            if np.isfinite(v) and v > 0.0
        }

        ranked = flows[eligible].sort_values()
        buckets = np.array_split(np.array(ranked.index), N_QUINTILES)
        low, high = list(buckets[0]), list(buckets[-1])
        diagnostics.quintile_sizes.append(len(low))
        diagnostics.mean_flow_by_quintile.append(
            [float(flows[list(b)].mean()) for b in buckets]
        )

        weights = {
            Leg.LONG_LOW_FLOW: _value_weights(low, caps),
            Leg.SHORT_HIGH_FLOW: _value_weights(high, caps),
        }
        universe_weights = _value_weights(eligible, caps)
        universe_return = sum(w * float(rets[n]) for n, w in universe_weights.items())
        low_return = sum(w * float(rets[n]) for n, w in weights[Leg.LONG_LOW_FLOW].items())
        high_return = sum(w * float(rets[n]) for n, w in weights[Leg.SHORT_HIGH_FLOW].items())

        def cost(new: Mapping[str, float], old: Mapping[str, float]) -> float:
            if half_spread is None or formation not in half_spread.index:
                return 0.0
            row = half_spread.loc[formation]
            total = 0.0
            for name in set(new) | set(old):
                delta = abs(new.get(name, 0.0) - old.get(name, 0.0))
                if delta == 0.0:
                    continue
                value = float(row.get(name, np.nan))
                if np.isfinite(value):
                    total += delta * value
            return total

        low_cost = cost(weights[Leg.LONG_LOW_FLOW], previous[Leg.LONG_LOW_FLOW])
        high_cost = cost(weights[Leg.SHORT_HIGH_FLOW], previous[Leg.SHORT_HIGH_FLOW])

        rows[Leg.LONG_LOW_FLOW].append(low_return - universe_return - low_cost)
        rows[Leg.SHORT_HIGH_FLOW].append(
            universe_return - high_return - high_cost - monthly_borrow
        )
        rows[Leg.LONG_SHORT].append(
            low_return - high_return - low_cost - high_cost - monthly_borrow
        )
        previous[Leg.LONG_LOW_FLOW] = weights[Leg.LONG_LOW_FLOW]
        previous[Leg.SHORT_HIGH_FLOW] = weights[Leg.SHORT_HIGH_FLOW]

    index = pd.DatetimeIndex(dates, name="month_end")
    return ({leg: pd.Series(values, index=index, name=leg.value) for leg, values in rows.items()}, diagnostics)


# =============================================================================
# Evaluation: DSR across the policy ladder + preservation_score
# =============================================================================


def spec_id_for(universe: str, horizon: str, leg: str, cost_arm: str) -> str:
    return f"{universe}/dm_{horizon}_{leg}_{cost_arm}"


def evaluate_specs(
    returns_by_spec: Mapping[str, pd.Series],
    *,
    n_local: int = DUMB_MONEY_N_TRIALS,
) -> tuple[dict[str, dict[int, float | None]], dict[str, float], dict[str, float | None], list[int]]:
    """DSR at every ladder rung and a preservation score for every spec.

    sigma_sr is the DISPERSION OF SHARPES ACROSS SIBLING SPECS, the same
    convention the FIT and fire-sale families use, so the three N-PORT families'
    DSRs stay directly comparable.

    preservation_score is computed for EVERY spec with no exceptions --
    CLAUDE.md calls this out because it was silently skipped once for a real
    decision before anyone noticed.
    """
    from app.services.research_lab.cross_sectional_nport_flow import (
        dsr_across_denominators,
        policy_d_denominators,
    )
    from app.services.research_lab.metrics import sharpe_ratio
    from app.services.research_lab.preservation_score import compute_preservation_metrics

    denominators = policy_d_denominators(n_local)

    sharpes: dict[str, float] = {}
    for spec_id, series in returns_by_spec.items():
        clean = series.dropna()
        sharpes[spec_id] = (
            float(sharpe_ratio(clean, periods_per_year=MONTHS_PER_YEAR)) if len(clean) >= 2 else 0.0
        )
    sigma_sr = float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None

    dsr_by_spec: dict[str, dict[int, float | None]] = {}
    preservation_by_spec: dict[str, float | None] = {}
    for spec_id, series in returns_by_spec.items():
        clean = series.dropna()
        if len(clean) < 2:
            dsr_by_spec[spec_id] = {n: None for n in denominators}
            preservation_by_spec[spec_id] = None
            continue
        dsr_map = dsr_across_denominators(
            sharpes[spec_id], clean, sigma_sr, denominators, periods_per_year=MONTHS_PER_YEAR
        )
        dsr_by_spec[spec_id] = dsr_map
        metrics = compute_preservation_metrics(
            clean, dsr=dsr_map[denominators[0]], periods_per_year=MONTHS_PER_YEAR
        )
        preservation_by_spec[spec_id] = float(metrics.preservation_score)

    return dsr_by_spec, sharpes, preservation_by_spec, denominators


def verdict_for(
    best_dsr_by_n: Mapping[int, float | None],
    denominators: Sequence[int],
    *,
    bar: float = 0.95,
) -> tuple[str, str]:
    """The pre-registered two-tier rule, applied mechanically.

    Frozen in frazzini_lamont_dumb_money_PREREGISTRATION.txt section 7 before
    any return existed. A None DSR counts as NOT clearing the bar.
    """
    lenient = best_dsr_by_n.get(denominators[0])
    strict = best_dsr_by_n.get(denominators[-1])
    if lenient is None or lenient < bar:
        return (
            "DEFINITE_NEGATIVE",
            f"best DSR {lenient!r} at the most lenient rung N={denominators[0]} is below the "
            f"{bar} bar, so no more conservative denominator can rescue it.",
        )
    if strict is None or strict < bar:
        return (
            "UNRESOLVED",
            f"best DSR clears {bar} at N={denominators[0]} but not at N={denominators[-1]} "
            f"({strict!r}) — needs forward-validation evidence, NOT a pass.",
        )
    return ("PASS", f"best DSR clears {bar} even at the most conservative rung N={denominators[-1]}.")
