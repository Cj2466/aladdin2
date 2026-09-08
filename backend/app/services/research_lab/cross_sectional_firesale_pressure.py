"""MUTUAL-FUND FIRE-SALE PRESSURE (Coval & Stafford): one pre-declared,
24-spec calendar-time family testing whether stocks under widespread FORCED
selling by outflow-constrained mutual funds subsequently rebound, built from
real SEC Form N-PORT bulk data.

=======================================================================
1. THE SOURCE, AND WHAT IT ACTUALLY SAYS
=======================================================================

PRIMARY (published): Coval, Joshua D. and Erik Stafford, "Asset fire sales
(and purchases) in equity markets", Journal of Financial Economics 86(2),
November 2007, pp. 479-512.

SOURCE ACTUALLY READ: the authors' own September 2005 working paper — the
pre-publication version of that JFE article — fetched live on 2026-09-08 from
the Federal Reserve Bank of New York's media library,
  https://www.newyorkfed.org/medialibrary/media/research/conference/2005/liquidity/Coval_Stafford.pdf
  sha256 6840a8329de3fa22f0f0cd22e3278f689de89e16fde561fd2ccfead92e836bc2
41 pages, extracted with pypdf and read in full. Every equation, threshold and
coefficient below was read off that file. None of it is from memory, per
CLAUDE.md's standing rule.

DISCLOSED GAP, NOT GLOSSED. The published JFE version is paywalled
(ScienceDirect) and the one open mirror found returned nothing on fetch — the
same wall this queue hit for margin_credit, ipo_lockup and quarter_end_marking.
Section and equation numbers here are the 2005 working paper's and may have
been renumbered in the 2007 published article. Where the published version's
numbers matter, that is flagged rather than assumed identical.

THE MEASURE — Eq.(4), page 10, quoted verbatim from the fetched PDF:

    PRESSURE_i,t =
       [ sum_j Buy_{j,i,t}(flow_{j,t} > 5%) - sum_j Sell_{j,i,t}(flow_{j,t} < -5%) ]
       / [ sum_j Own_{j,i,t-1} ]

    "where Buy_j,i,t equals one if fund j increased its holding in stock i
     during quarter t, and zero otherwise, Sell_j,i,t is defined similarly
     based on decreases, and Own_j,i,t-1 equals one if fund j owns stock i at
     the beginning of quarter t."

It is an UNWEIGHTED NET COUNT of constrained buyers minus constrained sellers,
divided by the number of owners. It is NOT weighted by ownership share and NOT
weighted by flow severity. The paper's own worked example (page 11), which
`test_paper_worked_example` in the test module pins exactly: 47 owners, 13 with
outflows >= 5% of which 11 reduce, 1 with a 5% inflow which increases
=> (1 - 11)/47 = -21.3%.

WHY NOT A SHARE-WEIGHTED MEASURE. Because the paper considered exactly that
and set it aside, in the paragraph immediately after Eq.(4):

    "An alternative determinant of asset fire sales might be to tabulate the
     number of shares sold due to capital outflows and scale by the number of
     shares outstanding or trading volume. Initial tests that rely such
     measures deliver results that are economically large, but of mixed
     statistical reliability."

with two stated reasons: price pressure requires COMMONALITY among owners,
which a count captures and a share-sum does not; and share-based measures are
"highly sensitive to reporting errors in fund holdings". This module implements
Eq.(4) as written. The build brief for this family asked for the share-weighted
form; that request was declined on the paper's own authority and the refusal is
recorded here rather than silently absorbed.

HOW THIS DIFFERS FROM THIS PROJECT'S ALREADY-CLOSED Lou (2012) FIT FAMILY
(cross_sectional_nport_flow.py, DEFINITE_NEGATIVE, merged 30851a5). Lou's
Eq.(3) is a share-weighted AVERAGE of fund flows over the funds holding a
stock — continuous and severity-weighted. Coval-Stafford's Eq.(4) is an
unweighted NET COUNT over owners. Different estimand, different functional
form, different thresholds. Both were checked against their own PDFs before
this claim was made; this is a separate test, not a re-run.

THRESHOLDS, all the paper's own, none tuned here:
  * fire sale stock:            PRESSURE <= -15%   (page 11)
  * inflow-driven purchase:     PRESSURE >= +25%   (page 11)
    footnote 7: these "approximately correspond to the 5th and 95th
    percentiles of the PRESSURE variable".
  * constrained-fund flow gate: |flow| > 5% (Eq.(4)) and, in the paper's
    Table 5.b variant, |flow| > 10%.
  * minimum owners:             10  (footnote 6, verbatim: "We require at
    least 10 mutual funds owners before we calculate the PRESSURE variable.")

THE RESULT THIS FAMILY IS MEASURED AGAINST — Table 4 Panel A, page 14: over
the fire-sale quarter (months -2,-1,0) the average abnormal return is -10.1%
(t = -6.94) with average pressure about -27%; over months +1 to +12 the stocks
rebound +6.15% (t = 2.01) as net forced selling "retreats to under 2%".

THE PAPER'S OWN FALSIFICATION CONTROL — Table 4 Panel B: the identical
construction with the FLOW CONDITION REMOVED (widespread selling by
unconstrained funds) shows a significant price drop and NO reversal,
"consistent with voluntary mutual fund trading bringing information into
prices". That control is implemented here as `unconstrained` pressure and is a
BINDING check (C1 in the pre-registration), not a nicety: if the unconstrained
arm reverses as strongly as the constrained one, the forced-selling mechanism
is not what is being measured.

THE STRATEGY — Section III.A, page 17. Not an event study: a calendar-time
portfolio that "buys all stocks identified as fire sale stocks within the past
year, but not within the most recent quarter", and symmetrically sells stocks
involved in an inflow-driven purchase over the same window. Footnote 10,
verbatim: "We skip a quarter to ensure that the strategy is feasible and to
avoid any potential spillover of forced selling from the event window to
subsequent months." That skip is the reason this candidate is testable at all
under N-PORT's 60-day publication wall (section 3 below).

THE PRIOR THE PAPER SETS ON ITSELF, and it is decisive for reading this
family's grid. At |flow| > 5% the long-short strategy's annualized abnormal
returns run 4.8% (t = 0.80) to 10.9% (t = 1.79) — the paper's own words:
"economically large, but of mixed statistical significance", "weak statistical
reliability", "The incentive to provide liquidity appears to be fairly mild."
Only at |flow| > 10% (Table 5.b) does it become strong: monthly abnormal
returns 1.68% (t = 2.22) to 2.64% (t = 3.50). So the 10% arm is the PRIMARY
one and a null at 5% is not evidence against the mechanism — the source is
itself null-ish there.

THE PAPER'S OWN CAVEAT, carried forward rather than dropped (footnote 12): the
long-short strategy was feasible in only 155 of 180 months, so "the abnormal
return estimates overstate the true investment returns by ignoring the capital
costs of standing idle" — Scholes's "fire-station" problem. This module
therefore pays 0 on an unformable leg rather than dropping the month; see
`calendar_time_returns`.

=======================================================================
2. WHAT IS SUBSTITUTED FOR THE PAPER'S DATA, STATED PLAINLY
=======================================================================

Coval-Stafford used CDA/Spectrum quarterly MUTUAL FUND holdings 1980-2004 plus
CRSP mutual-fund flows. This project has neither. The free substitute is SEC
Form N-PORT, already ingested and independently verified for the Lou/FIT family
(backend/data/nport_bulk, 2019q4 onward).

Worth stating because the build brief had it the other way round: the original
is NOT 13F-based. 13F is a broader all-institutions filing; Spectrum here is
mutual-fund holdings, which is much CLOSER to N-PORT than 13F is. The scope
mismatch is therefore smaller than the brief assumed. It is not zero:

  (a) N-PORT covers registered investment companies only (~83% of the $39.2tn
      registered-fund industry by AUM) and excludes hedge funds and separate
      accounts. Owner counts here are N-PORT fund SERIES counts, not Spectrum
      fund counts, so the -15%/+25% cutoffs are applied to a
      differently-populated denominator than the paper's. Reported, not
      assumed away.
  (b) History runs Oct 2019 to now — about six years against the paper's
      twenty-five. This is the single largest power constraint on this family
      and no amount of further work fixes it.
  (c) Mergers. N-PORT Item B.6 folds merger-driven share issuance into "shares
      sold" with no separating field, corrupting the flow identity on ~33.7%
      of fund-quarters (median error 13.4bp). Inherited, verified disclosure
      from nport_flow_definition_resolution_2026-09-05; irreducible. It
      misclassifies some funds' constraint status, which adds noise to the
      count in Eq.(4) and therefore biases toward LESS measured signal, not
      more.
  (d) Flow definition — settled elsewhere, not re-litigated here. External
      flow = Item B.6.a minus Item B.6.c, which is algebraically Lou's own
      Eq.(1) estimand under full reinvestment; resolved on 49,705 real
      fund-quarters and merged as a1d64b3. Coval-Stafford say only "capital
      flows" scaled by TNA and specify no reinvestment convention, so this
      project's already-resolved definition is adopted unchanged.

=======================================================================
3. POINT-IN-TIME CONSTRUCTION, AND THE 60-DAY WALL
=======================================================================

SEC Release 33-10231: N-PORT information "will not be made public until 60 days
after the end of the third month of the fund's fiscal quarter." Every fund
snapshot used here therefore comes from
cross_sectional_nport_flow.fund_snapshots_as_of, which selects each series'
current and previous filings by real FILING_DATE <= the snapshot date and was
built and independently verified for exactly this purpose. Nothing in this
module reads a filing before it was public.

The paper's own skip-a-quarter rule then sits ON TOP of that wall rather than
fighting it: a stock is eligible at snapshot D if it was flagged at some
snapshot in [D - 365d, D - 91d]. Both constraints point the same way and
neither is assumed.

DEVIATION FROM THE PAPER, LOGGED. The paper computes PRESSURE on a single
CALENDAR quarter for all funds at once. N-PORT funds have STAGGERED FISCAL
quarters, so a calendar-quarter grid would silently mix funds that have
reported with funds that have not. This module instead recomputes PRESSURE at
each MONTH END from whatever each fund's latest public quarter pair is — the
same resolution the FIT family adopted and verified for the same reason. The
cost is that a given fund-quarter contributes to roughly three consecutive
monthly snapshots; since eligibility is a set-membership test over a
twelve-month window, that repetition changes which month a stock is first
flagged, not whether it is flagged.

SPLITS. Share counts are restated onto one split basis (build_split_adjustment
/ split_factor_on, reused unchanged) BEFORE they are differenced. Without this
a 2-for-1 split reads as a "Buy" for every holder at once, injecting fake
positive PRESSURE into precisely the widely-held stocks. This is a correctness
requirement, not a refinement.

=======================================================================
4. THE GRID, FROZEN BEFORE ANY RETURN WAS COMPUTED
=======================================================================

See data/research_runs/coval_stafford_firesale_PREREGISTRATION.txt, committed
as 3a81d63 before this module computed anything. The grid is deliberately the
paper's own Table 5.a / 5.b structure so it cannot be mistaken for a search:

    flow threshold {5%, 10%} x leg {long, short, long_short}
        x weighting {equal, value} x universe {sp500, sp600}  = 24 specs

n_local = 24. DSR bar 0.95 across the {24, 37, 362, 1031} ladder. Verdict rule
and the four binding interpretive checks are in the pre-registration.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal, Mapping, Sequence

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


FIRESALE_FAMILY_KEY = "firesale_pressure"
FIRESALE_SMALL_CAP_FAMILY_KEY = "small_cap_firesale_pressure"

FIRESALE_CITATION = (
    "Coval, Joshua D. and Erik Stafford, 'Asset fire sales (and purchases) in equity "
    "markets', Journal of Financial Economics 86(2), 2007, pp. 479-512. Built from the "
    "authors' September 2005 working paper (NY Fed media library, sha256 6840a832...), "
    "Eq.(4) page 10; thresholds page 11 and footnotes 6-7; strategy Section III.A page 17 "
    "and footnote 10."
)

# --- the paper's own constants, none of them tuned here ------------------------

# Eq.(4)'s own gate, and the Table 5.b variant. Page 10 and page 15.
FLOW_THRESHOLDS: tuple[float, ...] = (0.05, 0.10)

# Page 11. "stocks with PRESSURE <= -15% are considered fire sale stocks. We
# also pay particular attention to stocks with PRESSURE >= 25%".
FIRESALE_CUTOFF = -0.15
INFLOW_CUTOFF = 0.25

# Footnote 6, verbatim: "We require at least 10 mutual funds owners before we
# calculate the PRESSURE variable."
MIN_OWNERS = 10

# Section III.A / footnote 10: "within the past year, but not within the most
# recent quarter". 365 and 91 calendar days.
FORMATION_LOOKBACK_DAYS = 365
FORMATION_SKIP_DAYS = 91

# Section III.A: "requiring at least 10 firms in each of the long and short
# portfolios". A leg below this is UNFORMABLE and earns 0 for the month rather
# than being dropped — footnote 12's fire-station problem.
MIN_FIRMS_PER_LEG = 10

# The family's own grid size: 2 flow thresholds x 3 legs x 2 weightings, per
# universe-family. Both universes share one 24-spec denominator because they
# were declared together in one pre-registration.
FIRESALE_N_TRIALS = 24

# Formations cannot start before N-PORT can supply a fund's CURRENT and
# PREVIOUS public quarter plus the paper's one-year lookback.
FIRESALE_FORMATION_START = date(2021, 1, 1)

MONTHS_PER_YEAR = 12.0

Leg = Literal["long", "short", "long_short"]
Weighting = Literal["equal", "value"]
LEGS: tuple[Leg, ...] = ("long", "short", "long_short")
WEIGHTINGS: tuple[Weighting, ...] = ("equal", "value")


# =============================================================================
# Eq.(4) itself — a pure function, so it can be pinned against the paper's own
# worked example without any data, filing or price machinery in the way.
# =============================================================================


@dataclass(frozen=True)
class OwnerObservation:
    """One fund's state in one stock over one quarter, as Eq.(4) needs it.

    `shares_before` and `shares_after` must already be on the SAME split basis;
    differencing raw reported counts across a split is the bug section 3 of the
    module docstring describes.
    """

    series_id: str
    shares_before: float
    shares_after: float
    flow: float

    @property
    def owned_before(self) -> bool:
        """Own_{j,i,t-1}: did this fund hold the stock at the START of t?"""
        return self.shares_before > 0.0

    @property
    def increased(self) -> bool:
        return self.shares_after > self.shares_before

    @property
    def decreased(self) -> bool:
        """Includes eliminating the position entirely (shares_after == 0).

        The paper's Table 2 discussion speaks throughout of holdings being
        "reduced or eliminated", so a full exit is a Sell, not a non-event.
        """
        return self.shares_after < self.shares_before


def pressure(
    owners: Sequence[OwnerObservation],
    *,
    flow_threshold: float,
    constrained: bool = True,
    min_owners: int = MIN_OWNERS,
) -> float | None:
    """Coval-Stafford Eq.(4), page 10.

    Returns None when the stock has fewer than `min_owners` owners at the start
    of the quarter — footnote 6's requirement, expressed as a refusal rather
    than as a small-denominator number that would look like a real reading.

    `constrained=False` implements the paper's OWN Table 4 Panel B control:
    "a 'pressure' variable, but one altered by removing the condition on flow
    from the calculation" (page 14-15). Every net buyer and net seller counts,
    distressed or not. The paper predicts a price drop with NO reversal there.
    """
    held = [o for o in owners if o.owned_before]
    n_owners = len(held)
    if n_owners < min_owners:
        return None

    if constrained:
        buys = sum(1 for o in held if o.increased and o.flow > flow_threshold)
        sells = sum(1 for o in held if o.decreased and o.flow < -flow_threshold)
    else:
        buys = sum(1 for o in held if o.increased)
        sells = sum(1 for o in held if o.decreased)

    return (buys - sells) / n_owners


# =============================================================================
# Panel construction
# =============================================================================


@dataclass
class PressureDiagnostics:
    """Every refusal counted, never silent."""

    n_snapshots: int = 0
    n_stock_snapshots_attempted: int = 0
    n_below_min_owners: int = 0
    n_measured: int = 0
    n_firesale_flags: dict[float, int] = field(default_factory=lambda: defaultdict(int))
    n_inflow_flags: dict[float, int] = field(default_factory=lambda: defaultdict(int))
    owners_per_stock: list[int] = field(default_factory=list)

    def owner_count_summary(self) -> dict[str, float]:
        if not self.owners_per_stock:
            return {}
        arr = np.asarray(self.owners_per_stock, dtype=float)
        return {
            "mean": float(arr.mean()),
            "p10": float(np.percentile(arr, 10)),
            "median": float(np.median(arr)),
            "p90": float(np.percentile(arr, 90)),
            "max": float(arr.max()),
        }


def month_end_snapshots(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """The last trading day of each month present in `index`."""
    if len(index) == 0:
        return []
    frame = pd.Series(index, index=index)
    return [pd.Timestamp(v) for v in frame.groupby([index.year, index.month]).max().tolist()]


def build_pressure_panels(
    close: pd.DataFrame,
    filings: Sequence[object],
    holdings_by_accession: Mapping[str, Mapping[str, float]],
    cusip_to_ticker: Mapping[str, str],
    split_adjustments: Mapping[str, pd.Series],
    *,
    formation_start: date,
    flow_thresholds: Sequence[float] = FLOW_THRESHOLDS,
    include_unconstrained: bool = True,
) -> tuple[dict[str, pd.DataFrame], PressureDiagnostics]:
    """PRESSURE at each month end, per flow threshold, plus the paper's own
    unconstrained control panel.

    Returns {panel_name: DataFrame(index=snapshot dates, columns=tickers)}
    where panel_name is e.g. "constrained_0.05" or "unconstrained".

    Reuses cross_sectional_nport_flow's point-in-time filing selection wholesale
    rather than reimplementing it: that code carries the 60-day publication
    wall, the amendment-supersedes rule, the one-quarter-apart gate, the fund
    size floor and the absolute-flow cap, and all of it was independently
    verified when the FIT family was built.
    """
    from app.services.research_lab.cross_sectional_nport_flow import (
        FlowPanelDiagnostics,
        _series_index,
        fund_snapshots_as_of,
        split_factor_on,
    )

    diagnostics = PressureDiagnostics()
    by_series = _series_index(list(filings))  # type: ignore[arg-type]

    snapshots = [d for d in month_end_snapshots(close.index) if d.date() >= formation_start]
    diagnostics.n_snapshots = len(snapshots)

    panel_names = [f"constrained_{t:g}" for t in flow_thresholds]
    if include_unconstrained:
        panel_names.append("unconstrained")
    panels: dict[str, dict[pd.Timestamp, dict[str, float]]] = {n: {} for n in panel_names}

    flow_diag = FlowPanelDiagnostics()

    for snapshot in snapshots:
        as_of = snapshot.date()
        fund_snapshots = fund_snapshots_as_of(by_series, as_of, flow_diag)
        if not fund_snapshots:
            continue

        # Gather, per ticker, one OwnerObservation per fund series.
        owners_by_ticker: dict[str, list[OwnerObservation]] = defaultdict(list)
        # (ticker, report_date) -> split factor. Memoised because the same pair
        # recurs once per fund holding that stock — thousands of times per
        # snapshot — and split_factor_on does a binary search each call.
        factor_cache: dict[tuple[str, date], float] = {}

        def _factor(ticker: str, when: date) -> float:
            key = (ticker, when)
            hit = factor_cache.get(key)
            if hit is None:
                hit = split_factor_on(split_adjustments, ticker, when)
                factor_cache[key] = hit
            return hit

        for series_id, snap in fund_snapshots.items():
            before_book = holdings_by_accession.get(snap.previous_accession, {})
            after_book = holdings_by_accession.get(snap.current_accession, {})
            if not before_book and not after_book:
                continue
            # Union: a stock bought from zero has no `before` row, and a stock
            # fully exited has no `after` row. Both matter to Eq.(4) — the
            # second is a Sell, the first is a Buy from a non-owner and is
            # excluded by Own_{j,i,t-1} inside pressure().
            for cusip in set(before_book) | set(after_book):
                ticker = cusip_to_ticker.get(cusip)
                if ticker is None:
                    continue
                before_factor = _factor(ticker, snap.previous_report_date)
                after_factor = _factor(ticker, snap.report_date)
                owners_by_ticker[ticker].append(
                    OwnerObservation(
                        series_id=series_id,
                        shares_before=float(before_book.get(cusip, 0.0)) * before_factor,
                        shares_after=float(after_book.get(cusip, 0.0)) * after_factor,
                        flow=snap.flow,
                    )
                )

        for ticker, owners in owners_by_ticker.items():
            diagnostics.n_stock_snapshots_attempted += 1
            n_held = sum(1 for o in owners if o.owned_before)
            if n_held < MIN_OWNERS:
                diagnostics.n_below_min_owners += 1
                continue
            diagnostics.n_measured += 1
            diagnostics.owners_per_stock.append(n_held)
            for threshold in flow_thresholds:
                value = pressure(owners, flow_threshold=threshold, constrained=True)
                if value is None:
                    continue
                panels[f"constrained_{threshold:g}"].setdefault(snapshot, {})[ticker] = value
                if value <= FIRESALE_CUTOFF:
                    diagnostics.n_firesale_flags[threshold] += 1
                if value >= INFLOW_CUTOFF:
                    diagnostics.n_inflow_flags[threshold] += 1
            if include_unconstrained:
                value = pressure(owners, flow_threshold=0.0, constrained=False)
                if value is not None:
                    panels["unconstrained"].setdefault(snapshot, {})[ticker] = value

    out: dict[str, pd.DataFrame] = {}
    for name, rows in panels.items():
        if not rows:
            out[name] = pd.DataFrame(index=pd.DatetimeIndex([], name="snapshot"))
            continue
        frame = pd.DataFrame.from_dict(rows, orient="index").sort_index()
        frame.index.name = "snapshot"
        out[name] = frame.reindex(columns=sorted(frame.columns))
    return out, diagnostics


def eligible_sets(
    panel: pd.DataFrame,
    snapshot: pd.Timestamp,
    *,
    cutoff: float,
    direction: Literal["below", "above"],
    lookback_days: int = FORMATION_LOOKBACK_DAYS,
    skip_days: int = FORMATION_SKIP_DAYS,
) -> set[str]:
    """Stocks flagged at some snapshot in [D - lookback, D - skip].

    Section III.A / footnote 10: "within the past year, but not within the most
    recent quarter". The window is CLOSED at both ends; a flag exactly
    `skip_days` old is the oldest thing the paper would already have excluded
    as "most recent quarter", so the boundary is inclusive on the far side and
    inclusive on the near side by <=, which is the conservative reading (it can
    only make the strategy stale, never fresher than the paper's).
    """
    if panel.empty:
        return set()
    lo = snapshot - pd.Timedelta(days=lookback_days)
    hi = snapshot - pd.Timedelta(days=skip_days)
    window = panel.loc[(panel.index >= lo) & (panel.index <= hi)]
    if window.empty:
        return set()
    if direction == "below":
        hit = (window <= cutoff).any(axis=0)
    else:
        hit = (window >= cutoff).any(axis=0)
    return set(hit.index[hit.to_numpy()])


# =============================================================================
# The calendar-time portfolio (Section III.A)
# =============================================================================


@dataclass
class LegDiagnostics:
    """How often each leg could actually be formed — footnote 12's
    fire-station problem, measured rather than assumed away."""

    n_months: int = 0
    n_long_formable: int = 0
    n_short_formable: int = 0
    long_sizes: list[int] = field(default_factory=list)
    short_sizes: list[int] = field(default_factory=list)

    def formable_fraction(self, leg: str) -> float:
        if self.n_months == 0:
            return 0.0
        if leg == "long":
            return self.n_long_formable / self.n_months
        if leg == "short":
            return self.n_short_formable / self.n_months
        return min(self.n_long_formable, self.n_short_formable) / self.n_months


def _weights(
    names: Sequence[str],
    weighting: Weighting,
    caps: pd.Series | None,
) -> dict[str, float]:
    """Equal or value weights over `names`, summing to 1.

    A value-weighted request degrades to EQUAL weights only if no name has a
    usable cap, and that degradation is visible to the caller through the
    returned dict being uniform — it is never silently applied per-name, which
    would mix two weighting schemes inside one portfolio.
    """
    if not names:
        return {}
    if weighting == "equal" or caps is None:
        w = 1.0 / len(names)
        return {n: w for n in names}
    values = {n: float(caps.get(n, np.nan)) for n in names}
    usable = {n: v for n, v in values.items() if np.isfinite(v) and v > 0}
    if not usable:
        w = 1.0 / len(names)
        return {n: w for n in names}
    total = sum(usable.values())
    return {n: v / total for n, v in usable.items()}


def calendar_time_returns(
    panel: pd.DataFrame,
    close: pd.DataFrame,
    *,
    members_on: "callable",
    market_cap: pd.DataFrame | None,
    half_spread: pd.DataFrame | None,
    formation_start: date,
    borrow_bps_per_year: float,
    weighting: Weighting,
    diagnostics: LegDiagnostics | None = None,
) -> tuple[pd.Series, pd.Series, pd.Series, LegDiagnostics]:
    """Monthly returns of the long, short and long-short portfolios.

    The long leg buys stocks flagged as fire sales in the past year but not the
    past quarter; the short leg sells stocks flagged as inflow-driven purchases
    over the same window (Section III.A).

    RETURNS ARE MARKET-HEDGED, and this is an implementation decision worth
    naming rather than burying. The paper reports raw portfolio returns and
    extracts abnormal performance with CAPM/FF3/Carhart regressions, and it
    explicitly notes "the large estimated coefficient on the market excess
    return" (page 17) — the raw legs are dominated by beta. A Sharpe ratio
    computed on a raw long-only leg would therefore mostly measure the equity
    risk premium over 2021-2026, not the fire-sale effect, and its DSR would be
    a statement about the stock market rather than about Coval-Stafford. Each
    single-sided leg is therefore reported net of the SAME-WEIGHTED return of
    the eligible universe on the same date. The long_short leg needs no such
    adjustment and is simply long minus short. This makes the long and short
    legs alpha-like, which is what the paper's own intercepts measure, and it
    can only REMOVE return, never add it.

    An unformable leg (fewer than MIN_FIRMS_PER_LEG names) earns 0.0 for that
    month rather than being dropped from the series. Dropping it is exactly the
    overstatement footnote 12 warns about.
    """
    diagnostics = diagnostics or LegDiagnostics()
    snapshots = [d for d in month_end_snapshots(close.index) if d.date() >= formation_start]

    long_rows: list[float] = []
    short_rows: list[float] = []
    ls_rows: list[float] = []
    dates: list[pd.Timestamp] = []

    prev_long: dict[str, float] = {}
    prev_short: dict[str, float] = {}
    monthly_borrow = borrow_bps_per_year / 1e4 / MONTHS_PER_YEAR

    for i in range(len(snapshots) - 1):
        formation = snapshots[i]
        following = snapshots[i + 1]
        members = set(members_on(formation.date()))
        if not members:
            continue

        priced = close.loc[formation].notna() & close.loc[following].notna()
        tradable = members & set(close.columns[priced.to_numpy()])
        if not tradable:
            continue

        rets = (close.loc[following] / close.loc[formation]) - 1.0
        caps = market_cap.loc[formation] if market_cap is not None else None

        long_names = sorted(eligible_sets(panel, formation, cutoff=FIRESALE_CUTOFF, direction="below") & tradable)
        short_names = sorted(eligible_sets(panel, formation, cutoff=INFLOW_CUTOFF, direction="above") & tradable)

        long_ok = len(long_names) >= MIN_FIRMS_PER_LEG
        short_ok = len(short_names) >= MIN_FIRMS_PER_LEG

        diagnostics.n_months += 1
        if long_ok:
            diagnostics.n_long_formable += 1
            diagnostics.long_sizes.append(len(long_names))
        if short_ok:
            diagnostics.n_short_formable += 1
            diagnostics.short_sizes.append(len(short_names))

        universe_names = sorted(tradable)
        market_w = _weights(universe_names, weighting, caps)
        market_ret = sum(w * float(rets[n]) for n, w in market_w.items())

        long_w = _weights(long_names, weighting, caps) if long_ok else {}
        short_w = _weights(short_names, weighting, caps) if short_ok else {}

        long_gross = sum(w * float(rets[n]) for n, w in long_w.items()) if long_ok else 0.0
        short_gross = sum(w * float(rets[n]) for n, w in short_w.items()) if short_ok else 0.0

        # Transaction cost: one half-spread per unit of weight traded, on each
        # side, charged at formation. This is the same "pay the spread to get
        # in and to get out" convention the sibling families use; a name held
        # through to the next month pays only on the weight CHANGE.
        def _cost(new: dict[str, float], old: dict[str, float]) -> float:
            if half_spread is None:
                return 0.0
            if formation not in half_spread.index:
                return 0.0
            row = half_spread.loc[formation]
            names = set(new) | set(old)
            total = 0.0
            for n in names:
                delta = abs(new.get(n, 0.0) - old.get(n, 0.0))
                if delta == 0.0:
                    continue
                hs = float(row.get(n, np.nan))
                if not np.isfinite(hs):
                    continue
                total += delta * hs
            return total

        long_cost = _cost(long_w, prev_long)
        short_cost = _cost(short_w, prev_short)
        borrow = monthly_borrow if short_ok else 0.0

        long_net = (long_gross - market_ret - long_cost) if long_ok else 0.0
        short_net = (market_ret - short_gross - short_cost - borrow) if short_ok else 0.0
        if long_ok and short_ok:
            ls_net = long_gross - short_gross - long_cost - short_cost - borrow
        else:
            ls_net = 0.0

        long_rows.append(long_net)
        short_rows.append(short_net)
        ls_rows.append(ls_net)
        dates.append(following)

        prev_long = long_w
        prev_short = short_w

    index = pd.DatetimeIndex(dates, name="month_end")
    return (
        pd.Series(long_rows, index=index, name="long"),
        pd.Series(short_rows, index=index, name="short"),
        pd.Series(ls_rows, index=index, name="long_short"),
        diagnostics,
    )


# =============================================================================
# Evaluation: DSR across the policy ladder + preservation_score, for all 24
# =============================================================================


@dataclass
class FiresaleSpecResult:
    """One spec's full record. Field names `spec_id`, `sharpe_annualized`,
    `deflated_sharpe` and `n_trading_days` are the ones
    cross_sectional_persistence.persist_cross_sectional_trial_results requires;
    they are not free-form."""

    spec_id: str
    universe: str
    flow_threshold: float
    leg: str
    weighting: str
    cost_arm: str
    sharpe_annualized: float
    n_trading_days: int
    mean_monthly_return: float
    dsr_by_n: dict[int, float | None]
    preservation_score: float | None
    formable_fraction: float
    deflated_sharpe: object = None


def spec_id_for(universe: str, flow_threshold: float, leg: str, weighting: str, cost_arm: str) -> str:
    return f"{universe}/cs_flow{flow_threshold:g}_{leg}_{weighting}_{cost_arm}"


def evaluate_specs(
    returns_by_spec: Mapping[str, pd.Series],
    *,
    n_local: int = FIRESALE_N_TRIALS,
) -> tuple[dict[str, dict[int, float | None]], dict[str, float], dict[str, float | None], list[int]]:
    """DSR at every ladder rung and a preservation score for every spec.

    sigma_sr is the DISPERSION OF SHARPES ACROSS THE SIBLING SPECS, matching
    the FIT family's convention exactly (cross_sectional_nport_flow.py:2162) so
    the two families' DSRs are computed the same way and stay comparable.

    preservation_score is computed for every spec with no exceptions. CLAUDE.md
    calls this out specifically because it was silently skipped once for a real
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
            sharpes[spec_id],
            clean,
            sigma_sr,
            denominators,
            periods_per_year=MONTHS_PER_YEAR,
        )
        dsr_by_spec[spec_id] = dsr_map
        # Preservation is scored against the MOST LENIENT rung's DSR, which is
        # the friendliest reading available; a spec that scores badly here
        # cannot be rescued by a different rung, since DSR falls with N.
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

    Frozen in coval_stafford_firesale_PREREGISTRATION.txt section 5 before any
    return existed. A None DSR counts as NOT clearing the bar — an unmeasurable
    deflation is not a passing one.
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
    return (
        "PASS",
        f"best DSR clears {bar} even at the most conservative rung N={denominators[-1]}.",
    )
