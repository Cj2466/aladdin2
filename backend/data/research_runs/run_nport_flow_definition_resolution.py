"""METHODOLOGICAL RESOLUTION ONLY -- which fund-flow definition a Lou (2012)-style
flow-induced-trading (FIT) build should use, and why.

This run builds NO SIGNAL, constructs NO FIT measure, and BACKTESTS NOTHING. It
resolves the single open question left by
`nport_flow_feasibility_2026-09-05.txt` PROOF_4: Lou (2012) Eq.(1)'s
TNA-inferred flow and Form N-PORT Item B.6's directly-reported flow disagreed in
SIGN on the one real fund-quarter that run measured, and it deliberately did not
decide which to use.

============================================================================
THE ANSWER, IN ONE LINE
============================================================================
They were never measuring the same thing. Lou's Eq.(1), by his own stated
assumption, estimates EXTERNAL net flow -- subscriptions minus redemptions,
with distributions assumed fully reinvested and therefore cancelling. Form
N-PORT reports that exact quantity DIRECTLY and separately as Item B.6.a minus
Item B.6.c. The prior run compared Eq.(1) against Item B.6.a + B.6.b - B.6.c,
which ADDS reinvested distributions back in -- a quantity Lou's construction
deliberately excludes. On the prior run's own fund-quarter, using B.6.a - B.6.c
instead of B.6.a + B.6.b - B.6.c makes the sign disagreement DISAPPEAR.

============================================================================
THE THREE CANDIDATE DEFINITIONS
============================================================================
Writing a = Item B.6.a (shares sold, EXCLUDING reinvestment), b = Item B.6.b
(shares sold in connection with reinvestment of dividends and distributions),
c = Item B.6.c (shares redeemed/repurchased), D = total distributions declared
by the fund (NOT reported on Form N-PORT), and R = the fund's total return:

  (1) LOU EQ.(1), TNA-inferred:  TNA_t - TNA_{t-1}*(1+R) - MGN_t, over TNA_{t-1}
  (2) B.6 NET:                   a + b - c      <- what the prior run compared against
  (3) B.6 EXTERNAL:              a - c          <- what this run recommends

============================================================================
THE STRUCTURAL IDENTITY THIS RUN DERIVES, TESTS, AND CONFIRMS
============================================================================
Both primary sources are quoted verbatim in the persisted report. In brief:

  * Lou (2012), Section 2.2, VERBATIM: "I further assume that inflows and
    outflows occur at the end of each quarter, and that investors reinvest
    their dividends and capital appreciation distributions in the same fund."

  * Form N-PORT Item B.5.a requires returns "calculated in accordance with the
    methodologies outlined in Item 26(b)(1) of Form N-1A"; Form N-1A Item
    26(b)(1), Instruction 2, VERBATIM: "Assume all distributions by the Fund
    are reinvested at the price stated in the prospectus (including any sales
    load imposed upon reinvestment of dividends) on the reinvestment dates
    during the period."

So the return R fed into Eq.(1) is, by construction, a full-reinvestment
total return. Decomposing the change in net assets over the quarter:

    TNA_t = TNA_{t-1} + (P&L net of expenses) - D + a + b - c

and since a full-reinvestment total return satisfies
(P&L net of expenses) ~= TNA_{t-1} * R (exactly, under Lou's own stated
end-of-quarter flow-timing assumption), substituting gives

    EQ1_dollars  ==  (a + b - c) - D  ==  (a - c) - (D - b)                (I)

i.e. Eq.(1) equals B.6-EXTERNAL flow MINUS the portion of distributions that
was NOT reinvested (paid out in cash). Two consequences, both tested here on
real data rather than asserted:

    EQ1 <= (a - c) <= (a + b - c)                                         (II)

and, if a fund's distributions really are fully reinvested (D == b, Lou's
literal assumption), Eq.(1) collapses EXACTLY onto B.6 EXTERNAL:

    D == b   ==>   EQ1_dollars == a - c                                  (III)

Identity (I) and corollary (III) are validated in this module against SYNTHETIC
funds with a KNOWN true answer (see `simulate_fund_quarter`), per CLAUDE.md's
standing rule that a published formula is never trusted before it reproduces a
hand-derivable known-answer case.

============================================================================
WHAT WAS MEASURED, ON REAL DATA
============================================================================
49,705 real fund-quarter observations, built from the SEC DERA Form N-PORT
quarterly bulk data sets 2025q2..2026q2 (five ZIPs; tables SUBMISSION,
REGISTRANT, FUND_REPORTED_INFO, MONTHLY_TOTAL_RETURN), paired into consecutive
fiscal quarters by SERIES_ID and report date, amendments deduped to the latest
filing. The derived panel is committed alongside this file at
nport_samples/nport_flow_panel_from_2025q2_2026q2_bulk.csv.gz so every number
below is reproducible with no network call.

Headline measurements (all reproduced by `main()`):

  * Eq.(1) tracks B.6 EXTERNAL far better than B.6 NET, on every metric:
      Spearman        0.9726  (external)  vs  0.9069  (net)
      sign agreement  94.0%   (external)  vs  87.1%   (net)
      |Eq1|/|B6| median ratio 1.015 with IQR [0.968, 1.063] (external)
                          vs  1.013 with IQR [0.911, 1.110] (net)
  * Decile assignment -- what a FIT sort actually consumes:
      exact decile match  83.8% (external) vs 59.7% (net)
      top flow decile: 95.3% stay in the same decile, 99.6% same sign
      bottom flow decile: 92.8% same decile, 99.2% same sign
      a fund in the true top decile landing in the Eq.(1) BOTTOM decile:
      5 out of 4,971 (0.1%)
  * Sign disagreement is concentrated in the economic noise floor: for
    |a-c| < 0.1% of TNA (2,473 obs carrying 0.03% of all flow dollars) sign
    agreement is 25.7%; for |a-c| >= 2% of TNA (35,594 obs carrying 87.7% of
    all flow dollars) it is 98.7-99.3%.
  * The residual gap behaves exactly as identity (I) predicts:
      - regressing (B6net - Eq1) on the reinvestment amount gives a coefficient
        of +1.02 at a $10mm size floor and +1.04 at $100mm (identity predicts
        >= +1.00); the unfiltered fit is destroyed by 33 micro-fund outliers
        and is reported in the output rather than hidden;
      - it spikes in the fiscal quarters containing December, when US funds
        make annual capital-gains distributions: median gap 135.0bp of TNA vs
        22.4bp in non-December quarters, and sign agreement against B.6 NET
        falls to 75.4% vs 91.0% -- while sign agreement against B.6 EXTERNAL
        is FLAT at 93.8% vs 94.1%, which is the discriminating test;
      - it is ~8.6x larger for bond/income-named funds (104.6bp) than for
        equity-named funds (12.2bp), matching their distribution intensity.
  * The share-class explanation the prior run floated is REFUTED: only 4.1% of
    sign disagreements can be fixed by ANY share-class return in the fund's own
    observed range, and 3,329 of the 6,420 disagreements are SINGLE-share-class
    funds where the explanation cannot apply at all.

============================================================================
WHAT THIS RUN DOES NOT ESTABLISH
============================================================================
Identity (I) is confirmed in direction, seasonality, cross-section and
regression loading, but is NOT satisfied row-by-row: inequality (II) is
violated in 33.7% of fund-quarters (median violation 13.4bp of TNA; 80.7% of
all rows are within 10bp of satisfying it). The residual is consistent with the
two approximations Lou himself names -- within-quarter flow timing (restricting
to quiet quarters moves compliance monotonically from 67.0% to 75.4%) -- plus
fund mergers, which Form N-PORT folds INTO Item B.6.a ("For mergers and other
acquisitions, include in the value of shares sold...") and which Lou removes
via his MGN term, and which N-PORT provides no way to separate. This run does
not decompose the remaining residual further, does not construct a FIT measure,
does not backtest anything, and takes no paid-data decision.
"""

from __future__ import annotations

import csv
import gzip
import json
import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

THIS_FILE = Path(__file__).resolve()
SAMPLES_DIR = THIS_FILE.parent / "nport_samples"
PANEL_CSV_GZ = SAMPLES_DIR / "nport_flow_panel_from_2025q2_2026q2_bulk.csv.gz"

# The two real, consecutive filings the PRIOR run's PROOF_4 sign disagreement
# came from; re-used here to show the disagreement dissolving under B.6 EXTERNAL.
SAMPLE_Q1_2026 = SAMPLES_DIR / "vanguard_midcap_growth_2026Q1_0000036405-26-000321.xml"
SAMPLE_Q2_2026 = SAMPLES_DIR / "vanguard_midcap_growth_2026Q2_0000036405-26-000481.xml"

# SEC DERA Form N-PORT quarterly bulk data sets used to build the panel.
# https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets
SOURCE_BULK_QUARTERS = ("2025q2", "2025q3", "2025q4", "2026q1", "2026q2")
SOURCE_BULK_TABLES = ("SUBMISSION.tsv", "REGISTRANT.tsv", "FUND_REPORTED_INFO.tsv", "MONTHLY_TOTAL_RETURN.tsv")

VERDICT_CODE = "RESOLVED_USE_B6_EXTERNAL_A_MINUS_C"


# ---------------------------------------------------------------------------
# 1. THE THREE FLOW DEFINITIONS -- each a pure function with a hand-checkable
#    known answer, each citing its own source.
# ---------------------------------------------------------------------------


def compound_quarterly_return_pct(rtn1: float, rtn2: float, rtn3: float) -> float:
    """Three Item B.5.a monthly total returns (reported as percentages, e.g.
    10.5476 meaning 10.5476%) compounded into one quarterly return, still a
    percentage.

    Hand check: (0,0,0) -> 0.0; (100,0,0) -> 100.0; (10,10,10) -> 33.1.
    """
    growth = (1.0 + rtn1 / 100.0) * (1.0 + rtn2 / 100.0) * (1.0 + rtn3 / 100.0)
    return (growth - 1.0) * 100.0


def lou_eq1_flow_dollars(
    tna_prev: float, tna_curr: float, quarterly_return_pct: float, mgn: float = 0.0
) -> float:
    """Lou (2012), "A Flow-Based Explanation for Return Predictability", RFS
    25(12):3457-3489, Section 2.2, Eq.(1), quoted verbatim from the author's own
    working paper (https://personal.lse.ac.uk/loud/flows.pdf):

        flow_{i,t} = (TNA_{i,t} - TNA_{i,t-1}*(1 + RET_{i,t}) - MGN_{i,t})
                     / TNA_{i,t-1}

    This returns the DOLLAR numerator (divide by tna_prev for Lou's fraction).

    MGN (the increase in TNA due to fund mergers) defaults to 0.0: Form N-PORT
    provides no way to identify or separate merger-driven share issuance --
    Item B.6's own instruction says "For mergers and other acquisitions,
    include in the value of shares sold any transaction in which the Fund
    acquired the assets of another investment company" -- so an N-PORT-only
    build cannot reproduce Lou's MGN adjustment. Stated, not silently omitted.

    Hand check: tna_prev=100, tna_curr=105, return=5% -> 0.0 (TNA grew exactly
    by the fund's own return, so no flow).
    """
    return tna_curr - tna_prev * (1.0 + quarterly_return_pct / 100.0) - mgn


def b6_net_flow_dollars(sales: float, reinvestment: float, redemption: float) -> float:
    """Form N-PORT Item B.6, a + b - c. INCLUDES reinvested distributions.

    Item B.6.a verbatim: "Total net asset value of shares sold (including
    exchanges but excluding reinvestment of dividends and distributions)."
    Item B.6.b verbatim: "Total net asset value of shares sold in connection
    with reinvestments of dividends and distributions."
    Item B.6.c verbatim: "Total net asset value of shares redeemed or
    repurchased, including exchanges."

    This is the definition the PRIOR feasibility run compared Eq.(1) against.
    Hand check: 100 + 5 - 40 = 65.
    """
    return sales + reinvestment - redemption


def b6_external_flow_dollars(sales: float, redemption: float) -> float:
    """Form N-PORT Item B.6.a - Item B.6.c: EXTERNAL net flow, excluding
    reinvested distributions (because B.6.a already excludes them, per the
    verbatim instruction quoted above).

    THIS IS THE QUANTITY LOU'S EQ.(1) IS DEFINED TO ESTIMATE, given his own
    stated assumption (Section 2.2) that "investors reinvest their dividends
    and capital appreciation distributions in the same fund" -- under which
    reinvestment cancels out of the TNA identity entirely.

    Hand check: 100 - 40 = 60.
    """
    return sales - redemption


# ---------------------------------------------------------------------------
# 2. SYNTHETIC KNOWN-ANSWER VALIDATION OF IDENTITY (I)
#      EQ1_dollars == (a - c) - (D - b)
#    CLAUDE.md: a published formula is validated against synthetic data with a
#    known true answer before it is trusted on real data.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SyntheticFundQuarter:
    """A fund-quarter simulated from primitives, so every flow definition has a
    KNOWN true value rather than an estimated one."""

    tna_prev: float
    tna_curr: float
    quarterly_return_pct: float
    sales: float          # a -- external subscriptions, excludes reinvestment
    reinvestment: float   # b -- reinvested portion of distributions
    redemption: float     # c
    distributions: float  # D -- total declared, NOT reported on Form N-PORT
    true_external_flow: float  # a - c, known by construction


def simulate_fund_quarter(
    *,
    tna_prev: float,
    gross_return_pct: float,
    subscriptions: float,
    redemptions: float,
    distributions: float,
    reinvestment_rate: float,
) -> SyntheticFundQuarter:
    """Build a fund-quarter from primitives under Lou's OWN two stated
    assumptions (Section 2.2): flows occur at the end of the quarter, and the
    reported total return is a full-reinvestment total return.

    Accounting, exactly as a real fund's net assets move:

        TNA_t = TNA_{t-1} + (P&L net of expenses) - D + a + b - c

    where the reported total return R is defined so that
    TNA_{t-1} * R == (P&L net of expenses) -- which is what Form N-1A Item
    26(b)(1) Instruction 2's full-reinvestment convention means, and what
    Lou assumes.

    `reinvestment_rate` is the fraction of D reinvested (Lou assumes 1.0).
    """
    if not 0.0 <= reinvestment_rate <= 1.0:
        raise ValueError("reinvestment_rate must be in [0, 1]")
    if distributions < 0:
        raise ValueError("distributions must be non-negative")
    pnl = tna_prev * gross_return_pct / 100.0
    reinvestment = distributions * reinvestment_rate
    tna_curr = tna_prev + pnl - distributions + subscriptions + reinvestment - redemptions
    return SyntheticFundQuarter(
        tna_prev=tna_prev,
        tna_curr=tna_curr,
        quarterly_return_pct=gross_return_pct,
        sales=subscriptions,
        reinvestment=reinvestment,
        redemption=redemptions,
        distributions=distributions,
        true_external_flow=subscriptions - redemptions,
    )


def identity_residual(fq: SyntheticFundQuarter) -> float:
    """Residual of identity (I): EQ1 - [(a - c) - (D - b)]. Zero by construction
    when the simulation's assumptions hold; used as the known-answer check."""
    eq1 = lou_eq1_flow_dollars(fq.tna_prev, fq.tna_curr, fq.quarterly_return_pct)
    predicted = b6_external_flow_dollars(fq.sales, fq.redemption) - (fq.distributions - fq.reinvestment)
    return eq1 - predicted


# ---------------------------------------------------------------------------
# 3. THE REAL PANEL
# ---------------------------------------------------------------------------


@dataclass
class PanelRow:
    series_id: str
    series_name: str
    report_date: str
    prev_report_date: str
    n_classes: int
    tna_prev: float
    tna_curr: float
    qret_mean_pct: float
    qret_min_pct: float
    qret_max_pct: float
    max_abs_monthly_class_return_pct: float
    sales: float
    reinvestment: float
    redemption: float
    realized_gain: float
    unrealized_ap: float

    # -- derived, all as FRACTIONS of tna_prev unless named _dollars --
    @property
    def eq1_dollars(self) -> float:
        return lou_eq1_flow_dollars(self.tna_prev, self.tna_curr, self.qret_mean_pct)

    @property
    def eq1_dollars_min_return(self) -> float:
        """Eq.(1) using the LOWEST share-class return -> the HIGHEST inferred flow."""
        return lou_eq1_flow_dollars(self.tna_prev, self.tna_curr, self.qret_min_pct)

    @property
    def eq1_dollars_max_return(self) -> float:
        """Eq.(1) using the HIGHEST share-class return -> the LOWEST inferred flow."""
        return lou_eq1_flow_dollars(self.tna_prev, self.tna_curr, self.qret_max_pct)

    @property
    def b6_net_dollars(self) -> float:
        return b6_net_flow_dollars(self.sales, self.reinvestment, self.redemption)

    @property
    def b6_external_dollars(self) -> float:
        return b6_external_flow_dollars(self.sales, self.redemption)

    @property
    def eq1(self) -> float:
        return self.eq1_dollars / self.tna_prev

    @property
    def b6_net(self) -> float:
        return self.b6_net_dollars / self.tna_prev

    @property
    def b6_external(self) -> float:
        return self.b6_external_dollars / self.tna_prev

    @property
    def reinvestment_frac(self) -> float:
        return self.reinvestment / self.tna_prev

    @property
    def gap_vs_net(self) -> float:
        """(a+b-c) - EQ1. Identity (I) predicts this equals D, so >= 0."""
        return self.b6_net - self.eq1

    @property
    def gap_vs_external(self) -> float:
        """(a-c) - EQ1. Identity (I) predicts this equals D - b (cash
        distributions), so >= 0."""
        return self.b6_external - self.eq1

    @property
    def quarter_contains_december(self) -> bool:
        """A fiscal quarter ending in Dec, Jan or Feb spans December -- the month
        US mutual funds make annual capital-gains distributions."""
        return int(self.report_date[5:7]) in (12, 1, 2)


def load_panel(path: Path | None = None) -> list[PanelRow]:
    """Load the committed derived panel. No network call."""
    path = path or PANEL_CSV_GZ
    rows: list[PanelRow] = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            tna_prev = float(r["tna_prev"])
            if tna_prev <= 0:
                continue
            rows.append(
                PanelRow(
                    series_id=r["series_id"],
                    series_name=r["series_name"],
                    report_date=r["report_date"],
                    prev_report_date=r["prev_report_date"],
                    n_classes=int(r["n_classes"]),
                    tna_prev=tna_prev,
                    tna_curr=float(r["tna_curr"]),
                    qret_mean_pct=float(r["qret_mean_pct"]),
                    qret_min_pct=float(r["qret_min_pct"]),
                    qret_max_pct=float(r["qret_max_pct"]),
                    max_abs_monthly_class_return_pct=float(r["max_abs_monthly_class_return_pct"]),
                    sales=float(r["sales"]),
                    reinvestment=float(r["reinvestment"]),
                    redemption=float(r["redemption"]),
                    realized_gain=float(r["realized_gain"]),
                    unrealized_ap=float(r["unrealized_ap"]),
                )
            )
    return rows


# ---------------------------------------------------------------------------
# 4. COMPARISON STATISTICS -- dependency-free so the tests never need scipy.
# ---------------------------------------------------------------------------


def _rank(xs: Sequence[float]) -> list[float]:
    """Average ranks, ties shared (the Spearman convention)."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    sxx = sum((a - mx) ** 2 for a in xs)
    syy = sum((b - my) ** 2 for b in ys)
    if sxx <= 0 or syy <= 0:
        return float("nan")
    return sxy / math.sqrt(sxx * syy)


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float:
    return pearson(_rank(xs), _rank(ys))


def same_sign(a: float, b: float) -> bool:
    """Strict: exact zero agrees only with exact zero. Used everywhere in this
    module so every sign statistic counts the same events."""
    return (a > 0) == (b > 0) and (a < 0) == (b < 0)


def sign_agreement(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Fraction of observations where the two series have the same sign.
    NOTE: this metric mechanically decays toward chance as the true magnitude
    approaches zero, which is exactly what section `by_flow_magnitude` shows --
    do not read a low value at tiny flows as a measurement problem."""
    return sum(1 for a, b in zip(xs, ys) if same_sign(a, b)) / len(xs)


def _quantiles(xs: Sequence[float], n: int) -> list[float]:
    s = sorted(xs)
    return [s[min(len(s) - 1, round(q * len(s) / n))] for q in range(1, n)]


def decile_of(value: float, cutoffs: Sequence[float]) -> int:
    lo = 0
    for cut in cutoffs:
        if value >= cut:
            lo += 1
        else:
            break
    return lo


def decile_agreement(reference: Sequence[float], candidate: Sequence[float]) -> dict[str, Any]:
    """How a decile sort -- the thing a cross-sectional FIT signal actually
    consumes -- is affected by swapping the flow definition."""
    ref_cuts, cand_cuts = _quantiles(reference, 10), _quantiles(candidate, 10)
    dr = [decile_of(v, ref_cuts) for v in reference]
    dc = [decile_of(v, cand_cuts) for v in candidate]
    n = len(dr)
    exact = sum(1 for a, b in zip(dr, dc) if a == b) / n
    within1 = sum(1 for a, b in zip(dr, dc) if abs(a - b) <= 1) / n
    top_idx = [i for i, d in enumerate(dr) if d == 9]
    bot_idx = [i for i, d in enumerate(dr) if d == 0]
    return {
        "n": n,
        "exact_decile_match": exact,
        "within_one_decile": within1,
        "top_decile_retained": sum(1 for i in top_idx if dc[i] == 9) / max(len(top_idx), 1),
        "bottom_decile_retained": sum(1 for i in bot_idx if dc[i] == 0) / max(len(bot_idx), 1),
        "top_decile_sign_agreement": sum(
            1 for i in top_idx if same_sign(reference[i], candidate[i])
        ) / max(len(top_idx), 1),
        "bottom_decile_sign_agreement": sum(
            1 for i in bot_idx if same_sign(reference[i], candidate[i])
        ) / max(len(bot_idx), 1),
        # the failure a FIT long/short portfolio would actually care about
        "top_decile_flipped_to_bottom": sum(1 for i in top_idx if dc[i] == 0),
        "bottom_decile_flipped_to_top": sum(1 for i in bot_idx if dc[i] == 9),
    }


def compare_definitions(rows: Sequence[PanelRow]) -> dict[str, Any]:
    """Eq.(1) against each of the two directly-reported N-PORT definitions."""
    eq1 = [r.eq1 for r in rows]
    net = [r.b6_net for r in rows]
    ext = [r.b6_external for r in rows]

    def magnitude_ratio(ref: Sequence[float]) -> dict[str, float]:
        rr = sorted(abs(e) / abs(v) for e, v in zip(eq1, ref) if abs(v) > 1e-4)
        if not rr:
            return {}
        return {
            "n": len(rr),
            "median": statistics.median(rr),
            "p25": rr[int(0.25 * len(rr))],
            "p75": rr[int(0.75 * len(rr))],
        }

    return {
        "n": len(rows),
        "vs_b6_net": {
            "pearson": pearson(eq1, net),
            "spearman": spearman(eq1, net),
            "sign_agreement": sign_agreement(eq1, net),
            "magnitude_ratio_eq1_over_ref": magnitude_ratio(net),
            "decile": decile_agreement(net, eq1),
        },
        "vs_b6_external": {
            "pearson": pearson(eq1, ext),
            "spearman": spearman(eq1, ext),
            "sign_agreement": sign_agreement(eq1, ext),
            "magnitude_ratio_eq1_over_ref": magnitude_ratio(ext),
            "decile": decile_agreement(ext, eq1),
        },
    }


def by_flow_magnitude(rows: Sequence[PanelRow]) -> list[dict[str, Any]]:
    """Where sign disagreement actually lives, and how much economic flow mass
    sits there. The prior run's PROOF_4 fund-quarter sat in the FIRST bucket."""
    buckets = [(0.0, 0.001), (0.001, 0.005), (0.005, 0.02), (0.02, 0.05), (0.05, 0.10), (0.10, float("inf"))]
    total_mass = sum(abs(r.b6_external_dollars) for r in rows)
    out = []
    for lo, hi in buckets:
        sel = [r for r in rows if lo <= abs(r.b6_external) < hi]
        if not sel:
            continue
        out.append(
            {
                "abs_external_flow_lo": lo,
                "abs_external_flow_hi": hi,
                "n": len(sel),
                "sign_agreement_vs_external": sign_agreement([r.eq1 for r in sel], [r.b6_external for r in sel]),
                "sign_agreement_vs_net": sign_agreement([r.eq1 for r in sel], [r.b6_net for r in sel]),
                "share_of_total_flow_dollars": sum(abs(r.b6_external_dollars) for r in sel) / total_mass,
            }
        )
    return out


def share_class_explanation_test(rows: Sequence[PanelRow]) -> dict[str, Any]:
    """Can the prior run's reason (a) -- 'one share class's return was used
    instead of a NAV-weighted blend' -- account for the disagreements?

    Form N-PORT reports Item B.5.a per class but reports NO class-level assets,
    so a true NAV-weighted blend is not computable from N-PORT alone. Instead
    this BRACKETS: if neither the lowest nor the highest share-class return the
    fund itself reported can flip Eq.(1) to agree, then no weighting of those
    classes could, and the explanation is ruled out for that observation."""

    def analyse(ref_attr: str) -> dict[str, Any]:
        dis = [r for r in rows if not same_sign(getattr(r, ref_attr), r.eq1)]
        fixable = [
            r
            for r in dis
            if same_sign(r.eq1_dollars_min_return, getattr(r, ref_attr))
            or same_sign(r.eq1_dollars_max_return, getattr(r, ref_attr))
        ]
        return {
            "n_disagreements": len(dis),
            "n_fixable_by_any_share_class_return": len(fixable),
            "fraction_fixable": len(fixable) / max(len(dis), 1),
            "n_disagreements_single_share_class": sum(1 for r in dis if r.n_classes == 1),
        }

    single = [r for r in rows if r.n_classes == 1]
    multi = [r for r in rows if r.n_classes > 1]
    return {
        "vs_b6_net": analyse("b6_net"),
        "vs_b6_external": analyse("b6_external"),
        "single_share_class": {
            "n": len(single),
            "sign_agreement_vs_net": sign_agreement([r.eq1 for r in single], [r.b6_net for r in single]),
            "sign_agreement_vs_external": sign_agreement([r.eq1 for r in single], [r.b6_external for r in single]),
        },
        "multi_share_class": {
            "n": len(multi),
            "sign_agreement_vs_net": sign_agreement([r.eq1 for r in multi], [r.b6_net for r in multi]),
            "sign_agreement_vs_external": sign_agreement([r.eq1 for r in multi], [r.b6_external for r in multi]),
        },
    }


def distribution_explanation_test(rows: Sequence[PanelRow]) -> dict[str, Any]:
    """Test identity (I)'s prediction that the gap IS distributions, using three
    independent fingerprints that distributions would leave and nothing else
    obviously would: the December capital-gains season, bond-vs-equity
    distribution intensity, and a unit regression loading on the reinvestment
    amount the fund itself reports."""
    dec = [r for r in rows if r.quarter_contains_december]
    non = [r for r in rows if not r.quarter_contains_december]

    bond_kw = ("BOND", "INCOME", "TREASURY", "MUNI", "CREDIT", "FIXED", "YIELD", "DURATION", "MORTGAGE", "GNMA")
    eq_kw = ("EQUITY", "STOCK", "GROWTH", "VALUE", "CAP", "INDEX", "APPRECIATION", "500")
    bond = [r for r in rows if any(k in (r.series_name or "").upper() for k in bond_kw)]
    eqty = [
        r
        for r in rows
        if any(k in (r.series_name or "").upper() for k in eq_kw)
        and not any(k in (r.series_name or "").upper() for k in bond_kw)
    ]

    # OLS of gap_vs_net on (flow-timing proxy, reinvestment). Identity (I)
    # predicts the reinvestment coefficient is >= +1 (reinvestment is a
    # component of D dollar for dollar) and the flow-timing coefficient is
    # negative (return earned on within-quarter flows inflates Eq.(1)).
    #
    # SIZE FLOOR, DISCLOSED RATHER THAN QUIETLY APPLIED: the unfiltered
    # regression is destroyed by ~33 micro-fund observations whose gap exceeds
    # 500% of their own net assets (the worst is a $584k closed-end fund at
    # -911x TNA; several are sub-$1mm leveraged single-stock ETFs posting
    # +166% quarterly returns). Those are ratios of small numbers, not
    # economically meaningful flow. The unfiltered fit is reported below
    # alongside the filtered ones so the effect of the floor is visible and
    # nothing is hidden; the $10mm floor retains 92% of the panel.
    def fit(sel: Sequence[PanelRow]) -> dict[str, Any]:
        y = [r.gap_vs_net for r in sel]
        x1 = [r.b6_net * (r.qret_mean_pct / 100.0) for r in sel]
        x2 = [r.reinvestment_frac for r in sel]
        b = _ols3(y, x1, x2)
        pred = [b[0] + b[1] * a + b[2] * c for a, c in zip(x1, x2)]
        resid_var = statistics.pvariance([a - p for a, p in zip(y, pred)])
        return {
            "n": len(sel),
            "intercept": b[0],
            "coef_flow_times_return": b[1],
            "coef_reinvestment": b[2],
            "r_squared": 1.0 - resid_var / statistics.pvariance(y),
        }

    ols = {
        "primary_tna_at_least_10mm": fit([r for r in rows if r.tna_prev >= 1e7]),
        "robustness_tna_at_least_100mm": fit([r for r in rows if r.tna_prev >= 1e8]),
        "unfiltered_outlier_destroyed": fit(rows),
        "n_gap_exceeding_500pct_of_tna": sum(1 for r in rows if abs(r.gap_vs_net) > 5.0),
        "note": (
            "identity (I) predicts coef_reinvestment >= +1.0 and "
            "coef_flow_times_return < 0; the unfiltered fit is reported only to "
            "show what the micro-fund outliers do to it, not as evidence"
        ),
    }

    def blk(sel: Sequence[PanelRow]) -> dict[str, Any]:
        if not sel:
            return {}
        return {
            "n": len(sel),
            "median_gap_vs_net": statistics.median([r.gap_vs_net for r in sel]),
            "median_gap_vs_external": statistics.median([r.gap_vs_external for r in sel]),
            "sign_agreement_vs_net": sign_agreement([r.eq1 for r in sel], [r.b6_net for r in sel]),
            "sign_agreement_vs_external": sign_agreement([r.eq1 for r in sel], [r.b6_external for r in sel]),
        }

    # FLOW-TIMING CONTROL. Lou (2012) Section 2.2 assumes verbatim that
    # "inflows and outflows occur at the end of each quarter". Where that is
    # least wrong -- quarters in which the fund's own monthly returns were all
    # small, so any within-quarter flow earned little return -- inequality (II)
    # should hold more often. It does, monotonically, which is what makes
    # flow timing a credible part of the residual rather than a guess.
    timing = []
    for thr in (10.0, 5.0, 2.0, 1.0):
        sel = [r for r in rows if r.max_abs_monthly_class_return_pct <= thr]
        if len(sel) < 100:
            continue
        timing.append(
            {
                "max_abs_monthly_return_pct_at_most": thr,
                "n": len(sel),
                "fraction_satisfying_eq1_le_external": sum(1 for r in sel if r.gap_vs_external >= 0) / len(sel),
                "median_gap_vs_external": statistics.median([r.gap_vs_external for r in sel]),
            }
        )

    gaps_ext = [r.gap_vs_external for r in rows]
    return {
        "flow_timing_control": timing,
        "december_quarters": blk(dec),
        "non_december_quarters": blk(non),
        "bond_income_named": blk(bond),
        "equity_named": blk(eqty),
        "ols_gap_vs_net": ols,
        "inequality_eq1_le_external": {
            "fraction_satisfied": sum(1 for g in gaps_ext if g >= 0) / len(gaps_ext),
            "fraction_within_10bp": sum(1 for g in gaps_ext if g >= -0.0010) / len(gaps_ext),
            "fraction_within_50bp": sum(1 for g in gaps_ext if g >= -0.0050) / len(gaps_ext),
            "median_violation_bp": statistics.median([-g for g in gaps_ext if g < 0]) * 1e4
            if any(g < 0 for g in gaps_ext)
            else 0.0,
        },
    }


def _ols3(y: Sequence[float], x1: Sequence[float], x2: Sequence[float]) -> tuple[float, float, float]:
    """Three-parameter OLS (intercept, x1, x2) via normal equations. Kept
    dependency-free; validated against a known-answer case in the tests."""
    n = len(y)
    cols = [[1.0] * n, list(x1), list(x2)]
    xtx = [[sum(cols[i][k] * cols[j][k] for k in range(n)) for j in range(3)] for i in range(3)]
    xty = [sum(cols[i][k] * y[k] for k in range(n)) for i in range(3)]
    # Gauss-Jordan
    m = [row[:] + [xty[i]] for i, row in enumerate(xtx)]
    for i in range(3):
        p = max(range(i, 3), key=lambda r: abs(m[r][i]))
        if abs(m[p][i]) < 1e-14:
            raise ValueError("singular design matrix")
        m[i], m[p] = m[p], m[i]
        piv = m[i][i]
        m[i] = [v / piv for v in m[i]]
        for r in range(3):
            if r != i and m[r][i] != 0.0:
                f = m[r][i]
                m[r] = [a - f * b for a, b in zip(m[r], m[i])]
    return (m[0][3], m[1][3], m[2][3])


# ---------------------------------------------------------------------------
# 5. THE PRIOR RUN'S OWN FUND-QUARTER, RE-EXAMINED
# ---------------------------------------------------------------------------


def reexamine_proof4_fund_quarter() -> dict[str, Any]:
    """Recompute the prior feasibility run's PROOF_4 case (Vanguard Mid-Cap
    Growth Index Fund, quarters ended 2026-03-31 -> 2026-06-30) under all three
    definitions and across ALL of the fund's share classes, from the same two
    real filings that run committed."""
    import importlib.util
    import sys

    prior = THIS_FILE.parent / "run_nport_flow_feasibility.py"
    spec = importlib.util.spec_from_file_location("_prior_nport_feasibility", prior)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    q1 = mod.parse_nport_filing(SAMPLE_Q1_2026)
    q2 = mod.parse_nport_filing(SAMPLE_Q2_2026)
    tna_prev, tna_curr = q1.net_assets, q2.net_assets

    per_class = {}
    for class_id, (r1, r2, r3) in q2.monthly_returns_by_class.items():
        qret = compound_quarterly_return_pct(r1, r2, r3)
        d = lou_eq1_flow_dollars(tna_prev, tna_curr, qret)
        per_class[class_id] = {
            "quarterly_return_pct": qret,
            "eq1_flow_dollars": d,
            "eq1_flow_fraction": d / tna_prev,
        }

    sales = sum(f["sales"] for f in (q2.mon1_flow, q2.mon2_flow, q2.mon3_flow))
    reinv = sum(f["reinvestment"] for f in (q2.mon1_flow, q2.mon2_flow, q2.mon3_flow))
    redem = sum(f["redemption"] for f in (q2.mon1_flow, q2.mon2_flow, q2.mon3_flow))
    net_d = b6_net_flow_dollars(sales, reinv, redem)
    ext_d = b6_external_flow_dollars(sales, redem)

    eq1_values = [v["eq1_flow_dollars"] for v in per_class.values()]
    implied_total_distributions = net_d - statistics.median(eq1_values)

    return {
        "fund": q2.series_name,
        "series_id": q2.series_id,
        "tna_prev_2026_03_31": tna_prev,
        "tna_curr_2026_06_30": tna_curr,
        "eq1_by_share_class": per_class,
        "eq1_all_share_classes_negative": all(v < 0 for v in eq1_values),
        "b6_a_sales": sales,
        "b6_b_reinvestment": reinv,
        "b6_b_reinvestment_by_month": [
            q2.mon1_flow["reinvestment"], q2.mon2_flow["reinvestment"], q2.mon3_flow["reinvestment"]
        ],
        "b6_c_redemption": redem,
        "b6_net_dollars": net_d,
        "b6_net_fraction": net_d / tna_prev,
        "b6_external_dollars": ext_d,
        "b6_external_fraction": ext_d / tna_prev,
        "prior_run_disagreement_vs_b6_net": all(v < 0 for v in eq1_values) and net_d > 0,
        "disagreement_resolved_vs_b6_external": all(v < 0 for v in eq1_values) and ext_d < 0,
        "implied_total_distributions_dollars": implied_total_distributions,
        "implied_reinvestment_rate": reinv / implied_total_distributions
        if implied_total_distributions
        else float("nan"),
        "note": (
            "Eq.(1) is NEGATIVE for every one of the fund's three share classes, so the "
            "prior run's reason (a) -- 'a single share class's return was used' -- cannot "
            "explain the disagreement here. The whole disagreement is Item B.6.b: "
            "$16,562,681.94 of reinvested distributions, essentially all of it in month 3, "
            "which B.6 NET adds and which Lou's Eq.(1), by his own stated full-reinvestment "
            "assumption, cancels out. Under B.6 EXTERNAL (a - c) both definitions agree: "
            "this fund-quarter was a small net OUTFLOW."
        ),
    }


# ---------------------------------------------------------------------------
# 6. main()
# ---------------------------------------------------------------------------


def main() -> dict[str, Any]:
    rows = load_panel()
    result = {
        "verdict_code": VERDICT_CODE,
        "recommendation": "B.6 EXTERNAL (Item B.6.a - Item B.6.c), with Lou Eq.(1) reported as a robustness dimension",
        "panel": {
            "n_fund_quarters": len(rows),
            "n_distinct_series": len({r.series_id for r in rows}),
            "report_date_min": min(r.report_date for r in rows),
            "report_date_max": max(r.report_date for r in rows),
            "source_bulk_quarters": list(SOURCE_BULK_QUARTERS),
            "source_bulk_tables": list(SOURCE_BULK_TABLES),
        },
        "definition_comparison": compare_definitions(rows),
        "by_flow_magnitude": by_flow_magnitude(rows),
        "share_class_explanation": share_class_explanation_test(rows),
        "distribution_explanation": distribution_explanation_test(rows),
        "proof4_reexamined": reexamine_proof4_fund_quarter(),
    }
    print(json.dumps(result, indent=2, default=str))
    return result


if __name__ == "__main__":
    main()
