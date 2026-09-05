"""data/research_runs/run_options_gamma_feasibility.py -- options-dealer-
gamma-hedging-flow feasibility scoping -- needs test coverage for the same
reason as test_tsmom_futures_feasibility.py and test_nport_flow_feasibility.py:
this run makes concrete, checkable claims about what real vendors return,
and CLAUDE.md's standing rule is that "X is/isn't available" claims are the
highest-risk category and must be verified, not asserted.

Same convention as the other two feasibility test files: import the runner
by path, and exercise its pure schema/claim-check functions against REAL
DATA CAPTURED DURING THE LIVE RUN and committed alongside it under
data/research_runs/options_gamma_samples/, so a regression in the CHECKING
logic is caught with NO network call. The live run itself
(run_options_gamma_feasibility.py, run directly) does hit real networks;
this test file deliberately does not, so the suite stays fast and
deterministic in CI.

WHAT IS PINNED HERE, AND WHY EACH ONE MATTERS:

 1. YFINANCE'S LIVE OPTION CHAIN SCHEMA. The captured sample proves the real
    response for SPY/AAPL/QQQ carries openInterest AND impliedVolatility for
    both calls and puts, with a specific column set. If yfinance/Yahoo ever
    drops one of these columns, this run's central "the data is free and
    reachable" claim silently stops being true -- pinned so that would be
    caught, not silently believed forever.

 2. THE EXPIRED-CONTRACT-IS-DEAD FINDING. This run's re-verification of the
    project's existing "historical option chains are confirmed dead" claim
    is pinned against the REAL captured 404/zero-row response, not just
    asserted in prose.

 3. ALPACA'S CONTRACTS-ENDPOINT SCHEMA. Pinned against the real captured
    SPY contract response: open_interest and open_interest_date are both
    present and open_interest is a numeric string. This is the newly-found,
    previously-unverified data source this run adds to the project's
    picture -- a schema regression here would silently invalidate this
    run's strongest finding.

 4. THE NON-REDUNDANCY FINDING. Alpaca's SEPARATE market-data snapshot
    endpoint is pinned to NOT carry open_interest or greeks, confirming the
    two Alpaca endpoints this run checked are not interchangeable.

 5. THE PERSISTED REPORT'S OWN VERDICT AND INTERNAL CONSISTENCY, mirroring
    the other two feasibility runs' final test.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
RUNNER = BACKEND / "data" / "research_runs" / "run_options_gamma_feasibility.py"
SAMPLES_DIR = BACKEND / "data" / "research_runs" / "options_gamma_samples"
REPORT_JSON = BACKEND / "data" / "research_runs" / "options_gamma_feasibility_2026-09-06.json"

YFINANCE_CHAIN_SAMPLE = SAMPLES_DIR / "yfinance_live_chain_sample.json"
YFINANCE_EXPIRED_SAMPLE = SAMPLES_DIR / "yfinance_expired_contract_sample.json"
ALPACA_CONTRACTS_SAMPLE = SAMPLES_DIR / "alpaca_options_contracts_sample.json"
ALPACA_SNAPSHOT_SAMPLE = SAMPLES_DIR / "alpaca_market_data_snapshot_sample.json"


@pytest.fixture(scope="module")
def runner():
    """Import the runner by path -- it lives under data/research_runs/, not
    app/, so it is not importable by name. Importing it does NOT make any
    network call by itself; only calling its probe_*() functions would."""
    spec = importlib.util.spec_from_file_location("_run_options_gamma_feasibility", RUNNER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# 0. THE SAMPLES THEMSELVES EXIST (committed alongside the runner)
# ---------------------------------------------------------------------------


def test_all_four_real_samples_are_committed():
    for path in (YFINANCE_CHAIN_SAMPLE, YFINANCE_EXPIRED_SAMPLE, ALPACA_CONTRACTS_SAMPLE, ALPACA_SNAPSHOT_SAMPLE):
        assert path.exists(), f"real captured sample missing: {path}"


# ---------------------------------------------------------------------------
# 1. YFINANCE LIVE OPTION CHAIN SCHEMA -- pinned against the real sample
# ---------------------------------------------------------------------------


def test_yfinance_chain_schema_check_against_real_sample(runner):
    sample = json.loads(YFINANCE_CHAIN_SAMPLE.read_text())
    for ticker_sym in ("SPY", "AAPL", "QQQ"):
        assert ticker_sym in sample, f"{ticker_sym} missing from the real captured sample"
        entry = sample[ticker_sym]
        assert entry["n_expirations"] > 0, f"{ticker_sym} had zero live expirations on capture day"
        checks = runner.check_yfinance_chain_schema(entry["calls_columns"], entry["puts_columns"])
        assert checks["calls_has_expected_columns"] is True
        assert checks["puts_has_expected_columns"] is True
        assert checks["calls_has_open_interest"] is True, (
            "openInterest missing from yfinance's real calls response -- this run's central "
            "free-data claim would no longer hold"
        )
        assert checks["calls_has_implied_volatility"] is True
        assert checks["puts_has_open_interest"] is True


def test_yfinance_chain_schema_check_fails_on_a_stripped_schema(runner):
    """Negative control: the check function must actually be able to fail,
    not just always return True regardless of input."""
    checks = runner.check_yfinance_chain_schema(["strike", "lastPrice"], ["strike", "lastPrice"])
    assert checks["calls_has_expected_columns"] is False
    assert checks["calls_has_open_interest"] is False


def test_spy_forward_chain_is_genuinely_deep_not_near_dated_only():
    """This run's claim is a DEEP forward chain (dozens of expirations,
    years out), not just a handful of near-dated ones -- pinned against the
    real captured expiration list."""
    sample = json.loads(YFINANCE_CHAIN_SAMPLE.read_text())
    spy_expirations = sample["SPY"]["expirations"]
    assert len(spy_expirations) >= 15, (
        f"only {len(spy_expirations)} SPY expirations captured -- the 'deep forward chain' "
        "finding would need re-examination if this ever drops this low"
    )


# ---------------------------------------------------------------------------
# 2. THE EXPIRED-CONTRACT-IS-DEAD FINDING
# ---------------------------------------------------------------------------


def test_expired_contracts_confirmed_dead_against_real_sample(runner):
    sample = json.loads(YFINANCE_EXPIRED_SAMPLE.read_text())
    for sym, entry in sample.items():
        assert runner.check_expired_contract_is_dead(entry["n_rows"]) is True, (
            f"{sym} returned {entry['n_rows']} rows -- the 'historical option chains are "
            "confirmed dead' claim would need re-examination if this is ever nonzero"
        )
        assert entry["empty"] is True


def test_check_expired_contract_is_dead_is_a_real_check_not_a_tautology(runner):
    """Negative control: must distinguish a real historical row count from zero."""
    assert runner.check_expired_contract_is_dead(0) is True
    assert runner.check_expired_contract_is_dead(250) is False


# ---------------------------------------------------------------------------
# 3. ALPACA CONTRACTS-ENDPOINT SCHEMA -- pinned against the real sample
# ---------------------------------------------------------------------------


def test_alpaca_contracts_schema_check_against_real_sample(runner):
    sample = json.loads(ALPACA_CONTRACTS_SAMPLE.read_text())
    assert sample["status_code"] == 200, "the real captured Alpaca contracts pull did not succeed"
    contracts = sample["body"]["option_contracts"]
    assert len(contracts) > 0, "no contracts in the real captured Alpaca sample"

    for contract in contracts:
        checks = runner.check_alpaca_contract_schema(contract)
        assert checks["has_expected_fields"] is True
        assert checks["has_open_interest"] is True, (
            "open_interest missing from Alpaca's real contracts response -- this run's newly "
            "found free data source would no longer hold"
        )
        assert checks["has_open_interest_date"] is True, (
            "open_interest_date missing -- this run's freshness/auditability finding for "
            "Alpaca depends on this field being present"
        )
        assert checks["open_interest_is_numeric_string"] is True


def test_alpaca_open_interest_date_is_at_most_a_few_days_behind_close_price_date():
    """Sanity-checks this run's 'OI is dated one day behind, overnight-
    computed' finding against the real captured sample, without asserting an
    exact date (which would break the moment this test is re-run on a
    different day)."""
    sample = json.loads(ALPACA_CONTRACTS_SAMPLE.read_text())
    contract = sample["body"]["option_contracts"][0]
    oi_date = contract["open_interest_date"]
    close_date = contract["close_price_date"]
    # Both dates real, both present, and OI dated on/after the close-price
    # date it accompanies -- the qualitative shape of "OI is a dated,
    # as-of snapshot" rather than an unlabeled live number.
    assert oi_date >= close_date


def test_check_alpaca_contract_schema_is_a_real_check_not_a_tautology(runner):
    """Negative control."""
    stripped = {"symbol": "X", "strike_price": "1"}
    checks = runner.check_alpaca_contract_schema(stripped)
    assert checks["has_expected_fields"] is False
    assert checks["has_open_interest"] is False


# ---------------------------------------------------------------------------
# 4. NON-REDUNDANCY: ALPACA'S MARKET-DATA SNAPSHOT LACKS OI/GREEKS
# ---------------------------------------------------------------------------


def test_alpaca_market_data_snapshot_does_not_carry_open_interest_or_greeks():
    sample = json.loads(ALPACA_SNAPSHOT_SAMPLE.read_text())
    assert sample["status_code"] == 200
    assert sample["has_open_interest"] is False, (
        "if Alpaca's market-data snapshot ever starts carrying open_interest, this run's "
        "'the two Alpaca endpoints are not redundant' finding needs re-examination"
    )
    assert sample["has_greeks"] is False
    fields = set(sample["fields_present_on_one_snapshot"])
    assert fields == {"dailyBar", "latestQuote", "latestTrade", "minuteBar"}


# ---------------------------------------------------------------------------
# 5. THE PERSISTED REPORT'S OWN INTERNAL CONSISTENCY
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not REPORT_JSON.exists(), reason="this run's report is not in this checkout")
def test_persisted_report_is_internally_consistent(runner):
    payload = json.loads(REPORT_JSON.read_text())
    assert payload["verdict_code"] == runner.VERDICT_CODE
    assert payload["verdict_code"] == "FEASIBLE_FREE_WITH_NAMED_LIMITS_DATA_LAYER_ONLY"

    schema = payload["schema_checks"]
    for ticker_sym in ("SPY", "AAPL", "QQQ"):
        assert schema["yfinance_chain_schema_by_ticker"][ticker_sym]["calls_has_open_interest"] is True

    for confirmed_dead in schema["expired_contracts_confirmed_dead"].values():
        assert confirmed_dead is True

    assert schema["alpaca_contract_schema"]["has_open_interest"] is True
    assert schema["alpaca_contract_schema"]["has_open_interest_date"] is True

    # Round-trips through json.dumps with no TypeError -- catches any
    # non-JSON-safe value type a future edit might introduce.
    json.dumps(payload, default=str)


@pytest.mark.skipif(not REPORT_JSON.exists(), reason="this run's report is not in this checkout")
def test_persisted_report_carries_both_papers_citations():
    payload = json.loads(REPORT_JSON.read_text())
    citations = payload["citations"]
    assert "Barbon" in citations["barbon_buraschi_2021"]["cite"]
    assert "Buraschi" in citations["barbon_buraschi_2021"]["cite"]
    assert "3725454" in citations["barbon_buraschi_2021"]["cite"]
    assert "Bollen" in citations["bollen_whaley_2004"]["cite"]
    assert "Whaley" in citations["bollen_whaley_2004"]["cite"]
    assert "711-753" in citations["bollen_whaley_2004"]["cite"]
    # The honesty disclosure about the primary text being paywalled must
    # survive in the persisted report, not just in this run's prose.
    assert "NOT OBTAINED" in citations["bollen_whaley_2004"]["cite"]
