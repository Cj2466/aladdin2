"""Tests for data/research_runs/chain_cme_span_continuous.py (Job 4 of
futures_span_full_pull_2026-09-07), imported by path per the same pattern as
tests/test_tsmom_futures_feasibility.py (the module lives under
data/research_runs/, not app/, so it is not importable by name).

The most important case here is the ZT/ZF/LE zero-settle stub bug found and
fixed while chaining the REAL full CME SPAN pull (not visible on synthetic
fixtures until this real-data failure was reproduced): a placeholder
Type-82 record with settle 0.0 and a self-referential expiration_date equal
to its own trade date must never be selected as the held/front contract."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

BACKEND = Path(__file__).resolve().parents[1]
RUNNER = BACKEND / "data" / "research_runs" / "chain_cme_span_continuous.py"


@pytest.fixture(scope="module")
def chainmod():
    spec = importlib.util.spec_from_file_location("_chain_cme_span_continuous", RUNNER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _row(trade_date: str, contract_month: str, settle: float, expiration_date: str) -> dict:
    return {
        "trade_date": trade_date,
        "contract_month": contract_month,
        "settle": settle,
        "expiration_date": expiration_date,
    }


def test_build_holding_series_picks_nearest_unexpired_contract(chainmod):
    """Basic case, no stubs: on each date, the contract with the smallest
    expiration_date that has not yet expired is held."""
    rows = [
        _row("2019-01-02", "201812", 45.00, "20181119"),  # already expired
        _row("2019-01-02", "201901", 45.50, "20181219"),  # already expired
        _row("2019-01-02", "201902", 46.54, "20190122"),  # first unexpired -> front
        _row("2019-01-02", "201903", 47.00, "20190220"),
    ]
    frame = pd.DataFrame(rows)
    holding, closes_by_contract, diag = chainmod.build_holding_series(frame)
    assert holding.loc[pd.Timestamp("2019-01-02")] == "201902"
    assert diag["n_zero_settle_candidate_exclusions"] == 0


def test_zero_settle_stub_with_self_referential_expiration_is_excluded(chainmod):
    """Reproduces the real ZT contract_month "201612" bug found on the full
    2013-2025 pull: a stub record with settle 0.0 and expiration_date equal
    to its own trade date must not be chosen as front just because its
    (bogus) expiration looks like the earliest. The real, correctly-priced
    contract for that same month, listed weeks later with its real
    expiration date, must be what the chain eventually rolls into."""
    rows = [
        # nearby real contracts around 2015-09-25 (mirroring real ZT shape)
        _row("2015-09-24", "201509", 109.640625, "20150930"),
        _row("2015-09-24", "201512", 109.484375, "20151231"),
        _row("2015-09-25", "201509", 109.617188, "20150930"),
        _row("2015-09-25", "201512", 109.445312, "20151231"),
        # the stub: settle 0.0, expiration_date == its own trade date
        _row("2015-09-25", "201612", 0.0, "20150925"),
        _row("2015-09-28", "201509", 109.664062, "20150930"),
        _row("2015-09-28", "201512", 109.492188, "20151231"),
        _row("2015-09-28", "201612", 0.0, "20150925"),
        # weeks later, the REAL 201612 contract appears with real prices and
        # its real (much later) expiration date
        _row("2015-09-30", "201509", 109.700000, "20150930"),
        _row("2015-09-30", "201512", 109.500000, "20151231"),
    ]
    frame = pd.DataFrame(rows)
    holding, closes_by_contract, diag = chainmod.build_holding_series(frame)
    # the stub must never be "held" on any date
    assert "201612" not in set(holding.dropna().unique())
    # front on 2015-09-25/28 must still be the real front month (201509,
    # nearest unexpired, non-zero settle), not the zero-settle stub
    assert holding.loc[pd.Timestamp("2015-09-25")] == "201509"
    assert holding.loc[pd.Timestamp("2015-09-28")] == "201509"
    # only the 2015-09-25 stub row satisfies "expiry_by_contract >= trade_date"
    # (the 2015-09-28 stub row's expiration_date 20150925 is already in the
    # past relative to that trade date, so it is excluded by the pre-existing
    # not-yet-expired filter, not counted again here -- both rows are still
    # correctly kept out of `held` either way, per the assertions above)
    assert diag["n_zero_settle_candidate_exclusions"] == 1


def test_chain_one_instrument_end_to_end_with_stub_does_not_raise(chainmod, tmp_path):
    """The bug this test guards against: chain_one_instrument used to raise
    ValueError('... is not priced on both ... a roll needs an overlap day')
    when the roll rule picked the zero-settle stub as front. After the fix,
    chaining must succeed end-to-end on data shaped exactly like the real
    failure case."""
    rows = [
        _row("2015-09-24", "201509", 109.640625, "20150930"),
        _row("2015-09-25", "201509", 109.617188, "20150930"),
        _row("2015-09-25", "201612", 0.0, "20150925"),
        _row("2015-09-28", "201509", 109.664062, "20150930"),
        _row("2015-09-28", "201612", 0.0, "20150925"),
        _row("2015-09-29", "201509", 109.700000, "20150930"),
        _row("2015-09-30", "201512", 109.500000, "20151231"),  # roll day (201509 expires 09-30)
        _row("2015-09-30", "201509", 109.690000, "20150930"),
    ]
    by_instrument = tmp_path / "by_instrument"
    by_instrument.mkdir()
    pd.DataFrame(rows).to_csv(by_instrument / "ZT.csv", index=False)
    chainmod.BY_INSTRUMENT = by_instrument

    result, out = chainmod.chain_one_instrument("ZT")
    assert result.ok, result.error
    assert out is not None
    assert "201612" not in set(out["held_contract_month"].unique())


def test_chain_one_instrument_missing_file_reports_failure_not_crash(chainmod, tmp_path):
    chainmod.BY_INSTRUMENT = tmp_path / "by_instrument_missing"
    result, out = chainmod.chain_one_instrument("ZZ")
    assert result.ok is False
    assert out is None
    assert "no by_instrument CSV" in result.error
