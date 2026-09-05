"""FEASIBILITY SCOPING ONLY -- Vayanos & Woolley (2013) / Lou (2012)-style flow
mechanism, using SEC Form N-PORT as the candidate free data source.

This run builds NO SIGNAL and constructs NO flow-induced-trading (FIT) measure.
It answers four questions with real, live-fetched evidence (SEC rule text, real
EDGAR filings, the SEC's own bulk N-PORT dataset) and stops. Per CLAUDE.md, a
published formula is never implemented from memory: Lou (2012) Equations (1)
and (3) below are quoted from the actual working-paper PDF
(https://personal.lse.ac.uk/loud/flows.pdf, fetched live 2026-09-05), not
recalled, and every number this run reports from them is checked against real
N-PORT data pulled from EDGAR on the same day, not asserted from documentation.

WHY THIS RUN EXISTS
====================
This project's fundamentals-based factor line (asset_growth, quality/NOA,
residual_momentum, best_ideas_13f) has produced a run of honest negatives,
with the working hypothesis that short/medium-horizon US equity returns are
driven more by mechanical flow than by fundamentals. Vayanos & Woolley (2013,
RFS 26(5):1087-1145) model fund-flow-induced trading pressure as generating
BOTH momentum (short-run) and reversal (long-run) from one mechanism, building
on Lou (2012, RFS 25(12):3457-3489), who built a flow-induced-trading (FIT)
measure from mutual-fund holdings + flows and showed it forecasts returns.

An earlier, UNVERIFIED project note claimed "SEC EDGAR hosts Form N-PORT
(monthly fund holdings + capital-flow data) free since Oct 2019." This run
exists to check that claim against the real rule text and real filings before
anyone spends effort building on it.

============================================================================
THE FOUR QUESTIONS, AND THE SHORT ANSWERS THIS RUN MEASURED
============================================================================

Q1. WHAT IS ACTUALLY PUBLIC, SINCE WHEN, AT WHAT GRANULARITY?
    Answer: the prior claim's START DATE is right and its GRANULARITY claim is
    HALF right. Public N-PORT data exists since October 2019 (SEC's own bulk
    dataset states this verbatim; three independently-checked fund families'
    first real NPORT-P filings cluster Nov 18-27, 2019 for the quarter ended
    2019-09-30). But holdings are quarterly, not monthly, in the CURRENTLY
    OPERATIVE regime: only the THIRD month of each fiscal quarter's per-security
    holdings snapshot is ever made public, 60 days after quarter-end (SEC
    Release 33-10231/IC-32314, Oct 13 2016, quoted verbatim below). A 2024
    amendment (Release adopted Aug 28 2024) that would have moved to true
    monthly public holdings has NEVER taken effect: its effective date was
    delayed (April 2025) to Nov 17 2027 / May 18 2028, and the SEC has since
    PROPOSED (Feb 18 2026) abandoning it and reverting permanently to quarterly.
    So the operative reality today (2026-09-05) is unchanged from 2016.
    FLOW data, by contrast, genuinely IS monthly even in the current regime:
    Item B.6 requires the public (third-month) filing to report sales,
    reinvestment and redemption dollar amounts for EACH of the preceding three
    months -- verified in real filings below (mon1Flow/mon2Flow/mon3Flow, three
    distinct real dollar figures per filing).

Q2. WHAT FORMAT, AND HOW PRACTICAL IS BULK COLLECTION?
    Answer: far more practical than per-filing scraping. SEC DERA publishes an
    official structured bulk dataset -- "Form N-PORT Data Sets"
    (https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets),
    directly analogous to the Financial Statement Data Sets for 10-K/10-Q XBRL.
    One ZIP per quarter, tab-delimited UTF-8 text, ~30 tables, covering "October
    2019 through current period" (SEC's own words). This run verified the LIVE
    2026-Q2 file is real (not a stub or 404): confirmed its declared size over
    HTTP (440,699,889 bytes), parsed its ZIP central directory via an HTTP range
    request (no full download), and confirmed the real internal file list
    matches the README's documented tables exactly, including
    FUND_REPORTED_INFO.tsv (fund-level flow, Items B.1-B.6) and
    FUND_REPORTED_HOLDING.tsv (per-security holdings, Items C.1-C.8). This run
    then downloaded and decompressed FUND_REPORTED_INFO.tsv in full (2,030,541
    compressed bytes -> 4,614,304 bytes, again via range request, no full-file
    download) and confirmed 14,417 real fund-quarter rows with genuine
    SALES_FLOW_MON1..3 / REINVESTMENT_FLOW_MON1..3 / REDEMPTION_FLOW_MON1..3
    columns and real dollar values (three real funds' rows are quoted in the
    report). No scraping of thousands of individual XML filings is required.

Q3. CAN A LOU (2012)-STYLE FIT MEASURE ACTUALLY BE CONSTRUCTED FROM THIS?
    Answer: the two raw ingredients Lou's construction needs -- per-fund,
    per-security prior-quarter holdings (shares_{i,j,t-1}) and per-fund
    period flow (flow_{i,t}) -- are BOTH genuinely present and were BOTH
    extracted from two real, consecutive, same-series N-PORT filings below
    (Vanguard Mid-Cap Growth Index Fund, quarters ended 2026-03-31 and
    2026-06-30). CUSIP/ISIN/LEI identifiers allow matching a security across
    funds and time. Coverage: N-PORT filers include open-end mutual funds,
    closed-end funds, AND UIT-organized ETFs (verified directly: SPY and PCM
    Fund Inc. both file real NPORT-P), excluding only money market funds (17%
    of the $39.2 trillion US-registered-fund industry at YE2024 per ICI's 2025
    Fact Book Figure 2.2) and SBICs (negligible). That ~83%-of-industry
    population is exactly the population Lou (2012) himself used -- so N-PORT
    is not a degraded substitute for Lou's original data, it is (arguably) a
    better one, because Item B.6 flow is DIRECTLY REPORTED rather than backed
    out of TNA and returns the way Lou had to.
    A REAL, UNRESOLVED METHODOLOGICAL QUESTION SURFACED HERE, NOT RESOLVED:
    cross-checking Lou's Eq.(1)-inferred flow against N-PORT's own directly-
    reported Item B.6 flow, on the one real fund-quarter measured below, the
    two estimates are both small (each under 0.2% of TNA) but they DISAGREE IN
    SIGN (Eq.(1): -0.143%, an outflow; Item B.6: +0.015%, an inflow). This is
    exactly the kind of construction choice CLAUDE.md says should not be
    resolved unilaterally in a scoping run -- it is logged here as an open
    question for whoever designs the real measure, not answered.

Q4. HONEST FEASIBILITY VERDICT.
    FEASIBLE, FREE, WITH NAMED LIMITS -- NO PAID-DATA GAP LOGGED. See
    VERDICT_CODE and the report's own verdict section. This is the first
    scoping run in this project's futures/N-PORT/flow line that does NOT end
    in a paid-data recommendation.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# WORKTREE BINDING GUARD (project convention: this file only runs inside the
# isolated worktree it was authored in, never accidentally against a stale
# checkout of a different branch).
# ---------------------------------------------------------------------------
THIS_FILE = Path(__file__).resolve()
EXPECTED_WORKTREE_MARKER = "nport-flow-feasibility"
if EXPECTED_WORKTREE_MARKER not in str(THIS_FILE) and "PYTEST_CURRENT_TEST" not in __import__("os").environ:
    print(
        f"WARNING: running outside the {EXPECTED_WORKTREE_MARKER} worktree -- path is {THIS_FILE}",
        file=sys.stderr,
    )

SAMPLES_DIR = THIS_FILE.parent / "nport_samples"
SAMPLE_Q1_2026 = SAMPLES_DIR / "vanguard_midcap_growth_2026Q1_0000036405-26-000321.xml"
SAMPLE_Q2_2026 = SAMPLES_DIR / "vanguard_midcap_growth_2026Q2_0000036405-26-000481.xml"

REAL_SAMPLE_FILINGS_METADATA = {
    "Q1_2026": {
        "fund": "Vanguard Mid-Cap Growth Index Fund",
        "series_id": "S000012756",
        "cik": "0000036405",
        "accession_number": "0000036405-26-000321",
        "filed": "2026-05-28",
        "report_period_end": "2026-03-31",
        "url": "https://www.sec.gov/Archives/edgar/data/36405/000003640526000321/primary_doc.xml",
    },
    "Q2_2026": {
        "fund": "Vanguard Mid-Cap Growth Index Fund",
        "series_id": "S000012756",
        "cik": "0000036405",
        "accession_number": "0000036405-26-000481",
        "filed": "2026-08-28",
        "report_period_end": "2026-06-30",
        "url": "https://www.sec.gov/Archives/edgar/data/36405/000003640526000481/primary_doc.xml",
    },
}

# ---------------------------------------------------------------------------
# Lou (2012), "A Flow-Based Explanation for Return Predictability", Review of
# Financial Studies 25(12):3457-3489. Equations and point estimates quoted
# from the freely-available working paper (https://personal.lse.ac.uk/loud/
# flows.pdf, fetched live 2026-09-05), Section 2.2 "Fund Flows" and Section
# 3.1-3.2 "Trading in Response to Capital Flows" / "The Return Pattern".
#
# Eq.(1), Section 2.2:
#   flow_{i,t} = (TNA_{i,t} - TNA_{i,t-1}*(1 + RET_{i,t}) - MGN_{i,t}) / TNA_{i,t-1}
#
# Eq.(3), Section 3.2:
#   FIT_{j,t} = [ sum_i shares_{i,j,t-1} * flow_{i,t} * PSF_{i,t-1} ]
#               / [ sum_i shares_{i,j,t-1} ]
#   where PSF is the "partial scaling factor" from the Eq.(2) panel regression
#   (Table II): the paper reports managers liquidate ~0.97 (t=16.82) of a
#   dollar of OUTFLOW dollar-for-dollar, but invest only ~0.62 (t=15.78) of a
#   dollar of INFLOW in existing holdings.
#
# THIS RUN DOES NOT COMPUTE FIT. Eq.(3)'s sum is over ALL mutual funds holding
# a stock; this run has real data for exactly ONE fund, which is illustrative
# of the per-fund NUMERATOR TERM only, never a FIT value. Building the actual
# measure is explicitly out of scope (see module docstring, CLAUDE.md).
PSF_OUTFLOW = 0.97
PSF_INFLOW = 0.62

# ---------------------------------------------------------------------------
# XML parsing -- Form N-PORT namespace is
# http://www.sec.gov/edgar/nport; parsed with plain regex rather than an XML
# library's namespace machinery, matching the flattened-TSV shape the SEC's
# own bulk dataset uses for the same tags.
# ---------------------------------------------------------------------------


@dataclass
class NportHolding:
    name: str
    cusip: str
    isin: str | None
    balance: float
    units: str
    val_usd: float
    pct_val: float
    asset_cat: str


@dataclass
class NportFundFiling:
    series_name: str
    series_id: str
    report_period_date: str
    net_assets: float
    total_assets: float
    monthly_returns_by_class: dict[str, tuple[float, float, float]]
    mon1_flow: dict[str, float]
    mon2_flow: dict[str, float]
    mon3_flow: dict[str, float]
    holdings: list[NportHolding] = field(default_factory=list)


def _flow_block(xml_text: str, tag: str) -> dict[str, float]:
    m = re.search(rf"<{tag} ([^/]*)/>", xml_text)
    if not m:
        raise ValueError(f"{tag} not found in filing")
    attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
    return {k: float(v) for k, v in attrs.items()}


def parse_nport_filing(xml_path: Path) -> NportFundFiling:
    """Parse ONE real Form N-PORT XML submission (edgarSubmission /
    formData). Extracts exactly the fields Lou (2012) Eq.(1)/Eq.(3) need
    (TNA, monthly returns, monthly flow, per-security shares/identifiers) plus
    enough context (pctVal, totAssets) to sanity-check the parse against the
    filing's own internal arithmetic, per CLAUDE.md's rule that a parser is
    validated against real data, not trusted from documentation alone.
    """
    xml_text = xml_path.read_text()

    series_name = re.search(r"<seriesName>([^<]*)", xml_text).group(1).strip()
    series_id = re.search(r"<seriesId>([^<]*)", xml_text).group(1).strip()
    report_period_date = re.search(r"<repPdDate>([^<]*)", xml_text).group(1).strip()
    net_assets = float(re.search(r"<netAssets>([^<]*)", xml_text).group(1))
    total_assets = float(re.search(r"<totAssets>([^<]*)", xml_text).group(1))

    monthly_returns_by_class: dict[str, tuple[float, float, float]] = {}
    for m in re.finditer(
        r'<monthlyTotReturn classId="([^"]+)" rtn1="([^"]+)" rtn2="([^"]+)" rtn3="([^"]+)"/>',
        xml_text,
    ):
        class_id, r1, r2, r3 = m.groups()
        monthly_returns_by_class[class_id] = (float(r1), float(r2), float(r3))

    holdings: list[NportHolding] = []
    for block in re.findall(r"<invstOrSec>.*?</invstOrSec>", xml_text, re.S):
        name_m = re.search(r"<name>([^<]*)", block)
        cusip_m = re.search(r"<cusip>([^<]*)", block)
        isin_m = re.search(r'<isin value="([^"]*)"', block)
        balance_m = re.search(r"<balance>([^<]*)", block)
        units_m = re.search(r"<units>([^<]*)", block)
        valusd_m = re.search(r"<valUSD>([^<]*)", block)
        pctval_m = re.search(r"<pctVal>([^<]*)", block)
        assetcat_m = re.search(r"<assetCat>([^<]*)", block)
        if not (name_m and cusip_m and balance_m and valusd_m and pctval_m):
            continue
        holdings.append(
            NportHolding(
                name=name_m.group(1).strip(),
                cusip=cusip_m.group(1).strip(),
                isin=isin_m.group(1).strip() if isin_m else None,
                balance=float(balance_m.group(1)),
                units=units_m.group(1).strip() if units_m else "",
                val_usd=float(valusd_m.group(1)),
                pct_val=float(pctval_m.group(1)),
                asset_cat=assetcat_m.group(1).strip() if assetcat_m else "",
            )
        )

    return NportFundFiling(
        series_name=series_name,
        series_id=series_id,
        report_period_date=report_period_date,
        net_assets=net_assets,
        total_assets=total_assets,
        monthly_returns_by_class=monthly_returns_by_class,
        mon1_flow=_flow_block(xml_text, "mon1Flow"),
        mon2_flow=_flow_block(xml_text, "mon2Flow"),
        mon3_flow=_flow_block(xml_text, "mon3Flow"),
        holdings=holdings,
    )


def find_holding_by_cusip(filing: NportFundFiling, cusip: str) -> NportHolding | None:
    for h in filing.holdings:
        if h.cusip == cusip:
            return h
    return None


# ---------------------------------------------------------------------------
# Lou (2012) Eq.(1) / Eq.(3) primitives -- ILLUSTRATIVE ONLY (see docstring).
# ---------------------------------------------------------------------------


def net_monthly_flow_dollars(flow_block: dict[str, float]) -> float:
    """Item B.6's own definition: sales (incl. reinvestment) minus redemptions.
    Form N-PORT text (Item B.6.a-c): 'a. Total net asset value of shares sold
    ... b. ... sold in connection with reinvestments ... c. ... redeemed or
    repurchased.' Net flow = a + b - c."""
    return flow_block["sales"] + flow_block["reinvestment"] - flow_block["redemption"]


def compound_quarterly_return_pct(rtn1: float, rtn2: float, rtn3: float) -> float:
    """Three monthly total returns (Item B.5.a, reported as percentages, e.g.
    10.548... meaning 10.548%) compounded to one quarterly return, still as a
    percentage. Hand check: rtn1=rtn2=rtn3=0.0 -> 0.0 (a fund with zero return
    every month has zero quarterly return); rtn1=100.0 (doubles), rtn2=0,
    rtn3=0 -> 100.0 (still just doubled). Both asserted in the test file."""
    growth = (1.0 + rtn1 / 100.0) * (1.0 + rtn2 / 100.0) * (1.0 + rtn3 / 100.0)
    return (growth - 1.0) * 100.0


def lou_eq1_flow_fraction(tna_prev: float, tna_curr: float, quarterly_return_pct: float, mgn: float = 0.0) -> float:
    """Lou (2012) Eq.(1), Section 2.2, quoted verbatim above. MGN (merger-
    driven TNA change) defaults to 0.0 -- this run has no merger information
    for the sample fund and states that assumption rather than silently
    omitting the term. Hand check: TNA flat, return zero -> flow_fraction=0
    (asserted in the test file: tna_prev=tna_curr=100, ret=0 -> 0.0)."""
    ret = quarterly_return_pct / 100.0
    return (tna_curr - tna_prev * (1.0 + ret) - mgn) / tna_prev


def lou_eq3_single_fund_numerator_term(shares_prev: float, flow_fraction: float, psf: float) -> float:
    """ONE TERM of Eq.(3)'s numerator sum (shares_{i,j,t-1} * flow_{i,t} *
    PSF_{i,t-1}) for a single fund i and single stock j -- NOT a FIT value,
    which requires summing this term (and the shares_prev denominator) across
    every mutual fund holding the stock. Hand check: shares_prev=1000,
    flow_fraction=0.10, psf=1.0 -> hypothetical shares = 100 (asserted in the
    test file)."""
    return shares_prev * flow_fraction * psf


# ---------------------------------------------------------------------------
# main(): run the illustrative extraction + cross-check on the two real,
# committed sample filings, and assemble the JSON-serializable findings.
# ---------------------------------------------------------------------------


def run_illustrative_cross_check() -> dict[str, Any]:
    q1 = parse_nport_filing(SAMPLE_Q1_2026)
    q2 = parse_nport_filing(SAMPLE_Q2_2026)

    HILTON_CUSIP = "43300A203"
    h_prev = find_holding_by_cusip(q1, HILTON_CUSIP)
    h_curr = find_holding_by_cusip(q2, HILTON_CUSIP)
    if h_prev is None or h_curr is None:
        raise AssertionError("Hilton Worldwide Holdings (CUSIP 43300A203) not found in both quarters")

    # Sanity check 1: pctVal units. Sum across all holdings should land near
    # 100 IF pctVal is a percentage (0-100), or near 1.0 if it is a fraction.
    # Validated against the real filing rather than assumed from the form
    # instructions, which do not state the convention explicitly.
    pct_val_sum_q2 = sum(h.pct_val for h in q2.holdings)

    # Sanity check 2: reported holdings should roughly reconcile to netAssets.
    val_usd_sum_q2 = sum(h.val_usd for h in q2.holdings)

    # Lou Eq.(1): TNA-inferred flow for the fund over the current quarter (Q2
    # 2026), using one representative share class's compounded quarterly
    # return (the fund has three classes; a fully faithful build would
    # NAV-weight across classes -- this run uses one class and states that
    # simplification rather than silently generalizing it).
    one_class_id = next(iter(q2.monthly_returns_by_class))
    r1, r2, r3 = q2.monthly_returns_by_class[one_class_id]
    quarterly_return_pct = compound_quarterly_return_pct(r1, r2, r3)
    eq1_flow_fraction = lou_eq1_flow_fraction(q1.net_assets, q2.net_assets, quarterly_return_pct)
    eq1_flow_dollars = eq1_flow_fraction * q1.net_assets

    # Item B.6 directly-reported net flow, summed over the same quarter's
    # three months.
    b6_net_flow_dollars = (
        net_monthly_flow_dollars(q2.mon1_flow)
        + net_monthly_flow_dollars(q2.mon2_flow)
        + net_monthly_flow_dollars(q2.mon3_flow)
    )
    b6_flow_fraction = b6_net_flow_dollars / q1.net_assets

    # Illustrative Eq.(3) numerator term for Hilton, using EACH flow estimate
    # and the OUTFLOW/INFLOW PSF implied by that estimate's own sign -- shown
    # side by side precisely because the two disagree in sign here (see
    # docstring "REAL, UNRESOLVED METHODOLOGICAL QUESTION").
    eq1_psf = PSF_OUTFLOW if eq1_flow_fraction < 0 else PSF_INFLOW
    b6_psf = PSF_OUTFLOW if b6_flow_fraction < 0 else PSF_INFLOW
    eq3_term_using_eq1_flow = lou_eq3_single_fund_numerator_term(h_prev.balance, eq1_flow_fraction, eq1_psf)
    eq3_term_using_b6_flow = lou_eq3_single_fund_numerator_term(h_prev.balance, b6_flow_fraction, b6_psf)

    return {
        "sample_filings": REAL_SAMPLE_FILINGS_METADATA,
        "fund_identity_check": {
            "q1_series_id": q1.series_id,
            "q2_series_id": q2.series_id,
            "same_series": q1.series_id == q2.series_id,
        },
        "holding_checked": {
            "name": h_curr.name,
            "cusip": HILTON_CUSIP,
            "isin": h_curr.isin,
            "asset_cat": h_curr.asset_cat,
            "units": h_curr.units,
        },
        "shares_prev_2026Q1": h_prev.balance,
        "shares_curr_2026Q2": h_curr.balance,
        "shares_actual_change": h_curr.balance - h_prev.balance,
        "pct_val_q2": {"weight_q1": h_prev.pct_val, "weight_q2": h_curr.pct_val},
        "parser_sanity_checks": {
            "n_holdings_q2": len(q2.holdings),
            "pct_val_sum_q2": pct_val_sum_q2,
            "pct_val_units_verdict": (
                "PERCENTAGE (0-100), not a fraction -- sum is ~100, not ~1"
                if 90.0 < pct_val_sum_q2 < 110.0
                else "AMBIGUOUS -- re-examine"
            ),
            "net_assets_q2": q2.net_assets,
            "val_usd_sum_q2": val_usd_sum_q2,
            "val_usd_vs_net_assets_ratio": val_usd_sum_q2 / q2.net_assets,
        },
        "flow_cross_check": {
            "tna_prev_2026Q1": q1.net_assets,
            "tna_curr_2026Q2": q2.net_assets,
            "class_id_used_for_return": one_class_id,
            "compounded_quarterly_return_pct": quarterly_return_pct,
            "eq1_inferred_flow_fraction": eq1_flow_fraction,
            "eq1_inferred_flow_dollars": eq1_flow_dollars,
            "b6_reported_net_flow_dollars": b6_net_flow_dollars,
            "b6_implied_flow_fraction": b6_flow_fraction,
            "signs_agree": (eq1_flow_fraction < 0) == (b6_flow_fraction < 0),
            "note": (
                "Eq.(1) and Item B.6 DISAGREE IN SIGN on this real fund-quarter -- "
                "logged as an open methodological question, not resolved here."
            ),
        },
        "illustrative_eq3_numerator_term_for_hilton": {
            "using_eq1_flow": {
                "flow_fraction": eq1_flow_fraction,
                "psf_used": eq1_psf,
                "hypothetical_shares_traded": eq3_term_using_eq1_flow,
            },
            "using_b6_flow": {
                "flow_fraction": b6_flow_fraction,
                "psf_used": b6_psf,
                "hypothetical_shares_traded": eq3_term_using_b6_flow,
            },
            "caveat": (
                "This is ONE TERM of Eq.(3)'s numerator for ONE fund, NOT a FIT value. "
                "A real FIT needs this term summed (with the shares-outstanding or "
                "total-mutual-fund-shares-held denominator) across every mutual fund "
                "holding the stock. Not attempted here -- out of scope per the task brief."
            ),
        },
    }


VERDICT_CODE = "FEASIBLE_FREE_WITH_NAMED_LIMITS_NO_PAID_GAP"


def main() -> dict[str, Any]:
    findings = run_illustrative_cross_check()
    result = {
        "verdict_code": VERDICT_CODE,
        "lou_2012_citations": {
            "eq1": "flow_{i,t} = (TNA_{i,t} - TNA_{i,t-1}*(1+RET_{i,t}) - MGN_{i,t}) / TNA_{i,t-1}",
            "eq3": "FIT_{j,t} = sum_i(shares_{i,j,t-1}*flow_{i,t}*PSF_{i,t-1}) / sum_i(shares_{i,j,t-1})",
            "psf_outflow": PSF_OUTFLOW,
            "psf_inflow": PSF_INFLOW,
            "source": "https://personal.lse.ac.uk/loud/flows.pdf, Section 2.2 and 3.1-3.2, fetched live 2026-09-05",
        },
        "illustrative_cross_check": findings,
    }
    print(json.dumps(result, indent=2, default=str))
    return result


if __name__ == "__main__":
    main()
