import json
from datetime import date

from app.services.research_lab.futures_curve_collector import (
    COLLECTOR_COMMODITIES,
    MONTH_CODES,
    N_CANDIDATE_MONTHS,
    NOT_USABLE_FOR_BACKTESTING,
    STALE_AFTER_CALENDAR_DAYS,
    candidate_delivery_months,
    collect_futures_curve_once,
    contract_ticker,
    default_output_path,
)

# --- symbology --------------------------------------------------------------


def test_contract_ticker_symbology():
    assert contract_ticker("CL", date(2026, 10, 1)) == "CLV26.NYM"
    assert contract_ticker("GC", date(2026, 12, 1)) == "GCZ26.CMX"
    assert contract_ticker("ZW", date(2027, 3, 1)) == "ZWH27.CBT"
    assert contract_ticker("NG", date(2026, 1, 1)) == "NGF26.NYM"


def test_month_codes_are_the_standard_cme_letters():
    assert MONTH_CODES == {
        1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
        7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z",
    }


def test_candidate_months_follow_each_commoditys_declared_cycle():
    # Gold trades Feb/Apr/Jun/Aug/Oct/Dec: from mid-January the candidates
    # start at February and skip the odd months.
    gold = candidate_delivery_months("GC", date(2026, 1, 15))
    assert gold == [
        date(2026, 2, 1),
        date(2026, 4, 1),
        date(2026, 6, 1),
        date(2026, 8, 1),
        date(2026, 10, 1),
    ]
    # Wheat (Mar/May/Jul/Sep/Dec) from July rolls over the year boundary.
    wheat = candidate_delivery_months("ZW", date(2026, 7, 2))
    assert wheat == [
        date(2026, 7, 1),
        date(2026, 9, 1),
        date(2026, 12, 1),
        date(2027, 3, 1),
        date(2027, 5, 1),
    ]
    # Crude trades every month.
    crude = candidate_delivery_months("CL", date(2026, 11, 20))
    assert crude == [date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1), date(2027, 2, 1), date(2027, 3, 1)]
    assert all(len(candidate_delivery_months(root, date(2026, 6, 1))) == N_CANDIDATE_MONTHS for root in COLLECTOR_COMMODITIES)


# --- front/next selection ---------------------------------------------------


def _fetch_from(table: dict[str, tuple[float, date, float | None, float | None] | None]):
    def fetch(ticker: str):
        return table.get(ticker)

    return fetch


def test_selects_the_two_nearest_fresh_contracts_as_front_and_next(tmp_path):
    today = date(2026, 8, 27)
    # September crude expired (stale close), so October is front and
    # November is next.
    table = {
        "CLU26.NYM": (60.0, date(2026, 8, 15), 10.0, 100.0),  # stale: 12 days old
        "CLV26.NYM": (61.0, date(2026, 8, 26), 20.0, 200.0),
        "CLX26.NYM": (62.0, date(2026, 8, 26), 30.0, None),
    }
    result = collect_futures_curve_once(
        out_path=tmp_path / "curve.jsonl", fetch=_fetch_from(table), today=today
    )
    crude = [r for r in result.records if r.commodity == "CL"]
    assert [(r.contract, r.position) for r in crude] == [
        ("CLV26.NYM", "front"),
        ("CLX26.NYM", "next"),
    ]
    assert crude[0].close == 61.0
    assert crude[0].open_interest == 200.0
    assert crude[1].open_interest is None
    # Everything else had no data and is recorded as a failure, not raised.
    assert set(result.failures) == set(COLLECTOR_COMMODITIES) - {"CL"}
    assert (today - date(2026, 8, 15)).days > STALE_AFTER_CALENDAR_DAYS


def test_a_single_fresh_contract_is_a_failure_not_a_half_pair(tmp_path):
    today = date(2026, 8, 27)
    table = {"NGV26.NYM": (3.0, date(2026, 8, 26), 5.0, None)}
    result = collect_futures_curve_once(
        out_path=tmp_path / "curve.jsonl", fetch=_fetch_from(table), today=today
    )
    assert all(r.commodity != "NG" for r in result.records)
    assert "NG" in result.failures
    assert "two" in result.failures["NG"]


def test_one_commoditys_error_does_not_cost_the_others(tmp_path):
    today = date(2026, 8, 27)

    def fetch(ticker: str):
        if ticker.startswith("NG"):
            raise RuntimeError("exchange feed down")
        if ticker.startswith("CL"):
            return (61.0, date(2026, 8, 26), 1.0, None)
        return None

    result = collect_futures_curve_once(
        out_path=tmp_path / "curve.jsonl", fetch=fetch, today=today
    )
    assert [r.commodity for r in result.records] == ["CL", "CL"]
    assert "NG" in result.failures and "exchange feed down" in result.failures["NG"]


# --- the output file --------------------------------------------------------


def test_appends_jsonl_records_and_never_rewrites(tmp_path):
    today = date(2026, 8, 27)
    table = {
        "CLV26.NYM": (61.0, date(2026, 8, 26), 20.0, 200.0),
        "CLX26.NYM": (62.0, date(2026, 8, 26), 30.0, 300.0),
    }
    out = tmp_path / "curve.jsonl"
    first = collect_futures_curve_once(out_path=out, fetch=_fetch_from(table), today=today)
    second = collect_futures_curve_once(out_path=out, fetch=_fetch_from(table), today=today)
    assert len(first.records) == len(second.records) == 2

    lines = [json.loads(line) for line in out.read_text().splitlines()]
    assert len(lines) == 4  # append-only: the second run adds, never rewrites
    for line in lines:
        assert line["commodity"] == "CL"
        assert line["position"] in ("front", "next")
        assert line["delivery_month"] in ("2026-10", "2026-11")
        assert line["close"] > 0
        assert line["close_date"] == "2026-08-26"
        assert line["observed_at_utc"]
        assert line["source"] == "yfinance"
        # Every single record carries the label — no consumer can claim
        # they were not told.
        assert line["notice"] == "not_usable_for_backtesting"


def test_nothing_is_written_when_nothing_was_observed(tmp_path):
    out = tmp_path / "curve.jsonl"
    result = collect_futures_curve_once(
        out_path=out, fetch=_fetch_from({}), today=date(2026, 8, 27)
    )
    assert result.records == []
    assert set(result.failures) == set(COLLECTOR_COMMODITIES)
    assert not out.exists()


def test_result_carries_the_not_backtestable_notice(tmp_path):
    result = collect_futures_curve_once(
        out_path=tmp_path / "curve.jsonl", fetch=_fetch_from({}), today=date(2026, 8, 27)
    )
    assert result.notice == NOT_USABLE_FOR_BACKTESTING
    assert "NOT usable for backtesting" in result.notice


def test_default_output_path_is_under_backend_data():
    path = default_output_path()
    assert path.name == "futures_curve_observations.jsonl"
    assert path.parent.name == "data"
    assert path.parent.parent.name == "backend"
