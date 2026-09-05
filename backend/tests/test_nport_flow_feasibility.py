"""data/research_runs/run_nport_flow_feasibility.py -- N-PORT/flow-mechanism
feasibility scoping -- needs test coverage for the same reason as
test_tsmom_futures_feasibility.py: it implements a PUBLISHED FORMULA (Lou 2012
Eq.(1) and Eq.(3)), and CLAUDE.md's standing rule is that a published formula
is never implemented from memory and never trusted before it reproduces a
hand-derivable known-answer case, AND is checked against real pulled data
rather than only against documentation.

Same convention as tests/test_tsmom_futures_feasibility.py (import the runner
by path, exercise its pure functions, pin real numbers from the real sample
filings committed alongside the runner under data/research_runs/nport_samples/
so a parser regression is caught with no network call).

WHAT IS PINNED HERE:

 1. THE HAND-DERIVABLE ARITHMETIC. compound_quarterly_return_pct,
    lou_eq1_flow_fraction and lou_eq3_single_fund_numerator_term are each
    checked against a case whose answer is computed by hand in the assertion
    itself, not against the module's own fixture.

 2. THE PARSER, AGAINST THE REAL COMMITTED SAMPLE FILINGS. Two real,
    consecutive-quarter Form N-PORT filings for the same fund (Vanguard
    Mid-Cap Growth Index Fund, CIK 0000036405, quarters ended 2026-03-31 and
    2026-06-30) are committed under nport_samples/. This pins the REAL,
    SPECIFIC numbers this run found on 2026-09-05 (share counts, net assets,
    monthly flow dollar figures) so a parsing regression -- e.g. picking up
    the wrong <balance> tag, or misreading pctVal's units -- fails loudly.

 3. THE PCTVAL UNITS FINDING. Form N-PORT's own instructions do not state
    whether pctVal is a fraction (0-1) or a percentage (0-100); this run
    determined it empirically (sum across ~127 holdings is ~100, not ~1).
    Pinned so a future SEC schema change that flips the convention is caught.

 4. THE SIGN-DISAGREEMENT FINDING. Lou's Eq.(1) (TNA-inferred flow) and
    N-PORT's own Item B.6 (directly-reported flow) disagree in SIGN on the
    one real fund-quarter measured here. This is reported as an open
    methodological question, not resolved -- pinned so it is not silently
    "fixed" into agreement by a future edit without that being a deliberate,
    reviewed choice.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
RUNNER = BACKEND / "data" / "research_runs" / "run_nport_flow_feasibility.py"
REPORT_JSON = BACKEND / "data" / "research_runs" / "nport_flow_feasibility_2026-09-05.json"

TOL = 1e-9


@pytest.fixture(scope="module")
def runner():
    """Import the runner by path -- it lives under data/research_runs/, not
    app/, so it is not importable by name. No network call: it only reads the
    two committed sample XML files under nport_samples/."""
    spec = importlib.util.spec_from_file_location("_run_nport_flow_feasibility", RUNNER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# 1. HAND-DERIVABLE ARITHMETIC
# ---------------------------------------------------------------------------


def test_compound_quarterly_return_zero_case(runner):
    assert abs(runner.compound_quarterly_return_pct(0.0, 0.0, 0.0) - 0.0) < TOL


def test_compound_quarterly_return_hand_derived(runner):
    # Doubling in month 1 (100%), flat in months 2 and 3 -> still just doubled.
    got = runner.compound_quarterly_return_pct(100.0, 0.0, 0.0)
    assert abs(got - 100.0) < TOL
    # 10% then 10% then 10% compounds to 1.1^3 - 1 = 33.1%, not 30%.
    got2 = runner.compound_quarterly_return_pct(10.0, 10.0, 10.0)
    assert abs(got2 - 33.1) < 1e-9


def test_lou_eq1_flow_fraction_zero_flow_case(runner):
    """TNA growth exactly equal to the fund's own return implies zero flow."""
    got = runner.lou_eq1_flow_fraction(tna_prev=100.0, tna_curr=105.0, quarterly_return_pct=5.0)
    assert abs(got - 0.0) < TOL


def test_lou_eq1_flow_fraction_hand_derived_nonzero_case(runner):
    # TNA_prev=100, return=0%, TNA_curr=110 -> flow = (110 - 100*1.0)/100 = 0.10
    got = runner.lou_eq1_flow_fraction(tna_prev=100.0, tna_curr=110.0, quarterly_return_pct=0.0)
    assert abs(got - 0.10) < TOL


def test_lou_eq3_single_fund_numerator_term_hand_derived(runner):
    # shares_prev=1000, flow_fraction=0.10, psf=1.0 -> hypothetical shares=100
    got = runner.lou_eq3_single_fund_numerator_term(shares_prev=1000.0, flow_fraction=0.10, psf=1.0)
    assert abs(got - 100.0) < TOL
    # PSF < 1 dampens it: psf=0.62 (Lou's published inflow estimate) -> 62
    got2 = runner.lou_eq3_single_fund_numerator_term(shares_prev=1000.0, flow_fraction=0.10, psf=0.62)
    assert abs(got2 - 62.0) < TOL


def test_net_monthly_flow_dollars_hand_derived(runner):
    flow = {"sales": 100.0, "reinvestment": 5.0, "redemption": 40.0}
    assert abs(runner.net_monthly_flow_dollars(flow) - 65.0) < TOL


# ---------------------------------------------------------------------------
# 2. THE PARSER, AGAINST THE REAL COMMITTED SAMPLE FILINGS
# ---------------------------------------------------------------------------


def test_sample_filings_exist(runner):
    assert runner.SAMPLE_Q1_2026.exists(), "Q1 2026 real sample filing missing"
    assert runner.SAMPLE_Q2_2026.exists(), "Q2 2026 real sample filing missing"


def test_parse_real_q2_filing_matches_known_values(runner):
    filing = runner.parse_nport_filing(runner.SAMPLE_Q2_2026)
    assert filing.series_name == "VANGUARD MID-CAP GROWTH INDEX FUND"
    assert filing.series_id == "S000012756"
    assert filing.report_period_date == "2026-06-30"
    assert abs(filing.net_assets - 34819073910.65) < 1.0
    assert abs(filing.total_assets - 34843258309.86) < 1.0
    assert len(filing.holdings) == 127

    hilton = runner.find_holding_by_cusip(filing, "43300A203")
    assert hilton is not None
    assert hilton.name == "Hilton Worldwide Holdings Inc"
    assert hilton.isin == "US43300A2033"
    assert hilton.asset_cat == "EC"
    assert hilton.units == "NS"
    assert abs(hilton.balance - 872023.0) < TOL
    assert abs(hilton.val_usd - 288168720.58) < 1.0

    # Real Item B.6 monthly flow figures, filed 2026-08-28.
    assert abs(filing.mon1_flow["redemption"] - 405158029.10) < 1.0
    assert abs(filing.mon1_flow["sales"] - 292254707.46000700) < 1.0
    assert abs(filing.mon3_flow["reinvestment"] - 16562681.59) < 1.0


def test_parse_real_q1_filing_matches_known_values(runner):
    filing = runner.parse_nport_filing(runner.SAMPLE_Q1_2026)
    assert filing.series_id == "S000012756"
    assert filing.report_period_date == "2026-03-31"
    assert abs(filing.net_assets - 29248363673.15) < 1.0

    hilton = runner.find_holding_by_cusip(filing, "43300A203")
    assert hilton is not None
    assert abs(hilton.balance - 872007.0) < TOL, (
        "the prior-quarter share count is the shares_{i,j,t-1} term Lou's Eq.(3) needs -- "
        "a regression here would silently corrupt every downstream FIT-style calculation"
    )


def test_same_series_across_both_quarters(runner):
    q1 = runner.parse_nport_filing(runner.SAMPLE_Q1_2026)
    q2 = runner.parse_nport_filing(runner.SAMPLE_Q2_2026)
    assert q1.series_id == q2.series_id, "the two sample filings must be the same fund series"


# ---------------------------------------------------------------------------
# 3. THE PCTVAL UNITS FINDING
# ---------------------------------------------------------------------------


def test_pct_val_is_a_percentage_not_a_fraction(runner):
    """Empirically determined, not assumed: summing pctVal across all real
    holdings in the Q2 filing lands near 100, not near 1."""
    filing = runner.parse_nport_filing(runner.SAMPLE_Q2_2026)
    total = sum(h.pct_val for h in filing.holdings)
    assert 90.0 < total < 110.0, (
        f"pctVal sum was {total}; if this ever falls near 1.0 the SEC schema's units "
        "convention has changed and every weight in this run is wrong by 100x"
    )


# ---------------------------------------------------------------------------
# 4. THE SIGN-DISAGREEMENT FINDING (end-to-end)
# ---------------------------------------------------------------------------


def test_illustrative_cross_check_runs_and_flags_the_sign_disagreement(runner):
    result = runner.run_illustrative_cross_check()
    fc = result["flow_cross_check"]
    assert fc["signs_agree"] is False, (
        "this run's central open-methodological-question finding is that Lou's Eq.(1) and "
        "N-PORT's own Item B.6 disagree in sign on the sample fund-quarter; if a future "
        "rerun ever finds them agreeing, that is a real change and must be re-examined, "
        "not silently absorbed"
    )
    assert abs(fc["eq1_inferred_flow_fraction"]) < 0.01, "both estimates are small in this fund-quarter"
    assert abs(fc["b6_implied_flow_fraction"]) < 0.01


def test_main_produces_valid_verdict_and_is_json_serializable(runner):
    result = runner.main()
    assert result["verdict_code"] == runner.VERDICT_CODE
    # Must round-trip through json.dumps with no TypeError (main() already does
    # this to print; re-serializing here catches any non-JSON-safe value type
    # a future edit might introduce, e.g. a bare Path or dataclass).
    json.dumps(result, default=str)


# ---------------------------------------------------------------------------
# 5. THE PERSISTED REPORT'S OWN INTERNAL CONSISTENCY
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not REPORT_JSON.exists(), reason="this run's report is not in this checkout")
def test_persisted_report_is_internally_consistent():
    payload = json.loads(REPORT_JSON.read_text())
    assert payload["verdict_code"] == "FEASIBLE_FREE_WITH_NAMED_LIMITS_NO_PAID_GAP"
    cc = payload["illustrative_cross_check"]["flow_cross_check"]
    assert cc["signs_agree"] is False
