"""Tests for the SEC XBRL frames share-count provider.

No network anywhere: a fake session serves hand-built frame payloads shaped
exactly like the real endpoint's (verified field set: accn, cik, entityName,
loc, end, val — and notably NO `filed`, which is the whole reason
VISIBILITY_LAG_DAYS exists).
"""

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
import requests

from app.services.market_data.sec_shares_outstanding_provider import (
    EARLIEST_FRAME,
    VISIBILITY_LAG_DAYS,
    SecSharesFetchError,
    SecSharesOutstandingProvider,
    ShareCountObservation,
    build_point_in_time_share_count_frame,
    quarterly_frames,
)


def frame_payload(*records: dict) -> dict:
    return {
        "taxonomy": "dei",
        "tag": "EntityCommonStockSharesOutstanding",
        "uom": "shares",
        "data": list(records),
    }


def record(cik: int, end: str, val: float) -> dict:
    return {
        "accn": "0001104659-20-037857",
        "cik": cik,
        "entityName": f"CIK {cik}",
        "loc": "US-IL",
        "end": end,
        "val": val,
    }


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, responses: dict[str, FakeResponse] | None = None) -> None:
        self.responses = responses or {}
        self.headers: dict[str, str] = {}
        self.get_urls: list[str] = []

    def get(self, url: str, timeout: float | None = None) -> FakeResponse:
        self.get_urls.append(url)
        return self.responses.get(url, FakeResponse(404))


def url_for(year: int, quarter: int) -> str:
    return (
        "https://data.sec.gov/api/xbrl/frames/dei/"
        f"EntityCommonStockSharesOutstanding/shares/CY{year}Q{quarter}I.json"
    )


def provider(session: FakeSession, tmp_path=None) -> SecSharesOutstandingProvider:
    return SecSharesOutstandingProvider(
        cache_dir=tmp_path, session=session, sleep=lambda _seconds: None
    )


def bdays(start: str, periods: int) -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=periods)


# --- frame enumeration -------------------------------------------------------


def test_quarterly_frames_spans_the_requested_window():
    assert quarterly_frames(date(2024, 2, 1), date(2024, 8, 1)) == [
        (2024, 1),
        (2024, 2),
        (2024, 3),
    ]


def test_quarterly_frames_never_precedes_the_earliest_useful_frame():
    frames = quarterly_frames(date(2010, 1, 1), date(2018, 3, 1))
    assert frames[0] == EARLIEST_FRAME


def test_quarterly_frames_crosses_a_year_boundary():
    assert quarterly_frames(date(2023, 11, 1), date(2024, 2, 1)) == [
        (2023, 4),
        (2024, 1),
    ]


# --- fetching and caching ----------------------------------------------------


def test_a_frame_is_cached_and_a_second_call_makes_no_request(tmp_path):
    session = FakeSession({url_for(2024, 1): FakeResponse(200, frame_payload(record(1, "2024-02-29", 100.0)))})
    p = provider(session, tmp_path)
    first = p.fetch_frame(2024, 1)
    assert first["data"][0]["val"] == 100.0
    assert (tmp_path / "CY2024Q1I.json").exists()
    assert p.fetch_frame(2024, 1) == first
    assert len(session.get_urls) == 1


def test_a_payload_without_a_data_key_is_refused_after_every_retry(tmp_path):
    session = FakeSession({url_for(2024, 1): FakeResponse(200, {"taxonomy": "dei"})})
    with pytest.raises(SecSharesFetchError):
        provider(session, tmp_path).fetch_frame(2024, 1)
    assert len(session.get_urls) == 3
    assert not (tmp_path / "CY2024Q1I.json").exists()


def test_a_persistent_http_error_raises_rather_than_returning_an_empty_frame(tmp_path):
    """An empty frame would look exactly like "no company filed that
    quarter", which is indistinguishable from real data at read time."""
    session = FakeSession({url_for(2024, 1): FakeResponse(500)})
    with pytest.raises(SecSharesFetchError):
        provider(session, tmp_path).fetch_frame(2024, 1)


def test_no_temp_file_survives_a_successful_write(tmp_path):
    session = FakeSession({url_for(2024, 1): FakeResponse(200, frame_payload(record(1, "2024-02-29", 5.0)))})
    provider(session, tmp_path).fetch_frame(2024, 1)
    assert [path.name for path in tmp_path.glob("*.tmp")] == []


def test_a_cached_frame_is_valid_json_on_disk(tmp_path):
    session = FakeSession({url_for(2024, 1): FakeResponse(200, frame_payload(record(7, "2024-02-29", 9.0)))})
    provider(session, tmp_path).fetch_frame(2024, 1)
    on_disk = json.loads((tmp_path / "CY2024Q1I.json").read_text())
    assert on_disk["data"][0]["cik"] == 7


# --- reshaping into per-ticker observations ----------------------------------


def test_share_counts_are_keyed_by_ticker_and_carry_the_visibility_lag(tmp_path):
    session = FakeSession(
        {url_for(2024, 1): FakeResponse(200, frame_payload(record(320193, "2024-02-16", 15_000_000.0)))}
    )
    counts, diagnostics = provider(session, tmp_path).fetch_share_counts(
        {"AAPL": 320193}, date(2024, 1, 1), date(2024, 3, 31)
    )
    assert len(counts["AAPL"]) == 1
    observation = counts["AAPL"][0]
    assert observation.as_of == date(2024, 2, 16)
    assert observation.available == date(2024, 2, 16) + timedelta(days=VISIBILITY_LAG_DAYS)
    assert observation.shares == 15_000_000.0
    assert diagnostics.n_observations == 1
    assert diagnostics.n_frames_resolved == 1


def test_a_cik_outside_the_requested_map_is_ignored(tmp_path):
    session = FakeSession(
        {
            url_for(2024, 1): FakeResponse(
                200, frame_payload(record(1, "2024-02-16", 100_000_000.0), record(2, "2024-02-16", 200_000_000.0))
            )
        }
    )
    counts, _diagnostics = provider(session, tmp_path).fetch_share_counts(
        {"AAA": 1}, date(2024, 1, 1), date(2024, 3, 31)
    )
    assert set(counts) == {"AAA"}
    assert counts["AAA"][0].shares == 100_000_000.0


@pytest.mark.parametrize("bad_value", [0.0, -5.0, float("nan")])
def test_a_non_positive_share_count_is_refused_and_counted(tmp_path, bad_value):
    """This is the DENOMINATOR of a short-interest ratio; a zero there would
    produce an infinity that ranks first in the cross-section."""
    session = FakeSession(
        {url_for(2024, 1): FakeResponse(200, frame_payload(record(1, "2024-02-16", bad_value)))}
    )
    counts, diagnostics = provider(session, tmp_path).fetch_share_counts(
        {"AAA": 1}, date(2024, 1, 1), date(2024, 3, 31)
    )
    assert counts["AAA"] == []
    assert diagnostics.n_refused.get("non_positive_shares") == 1


def test_a_malformed_record_is_refused_and_counted(tmp_path):
    session = FakeSession(
        {url_for(2024, 1): FakeResponse(200, frame_payload({"cik": 1, "end": "nope", "val": 1.0}))}
    )
    counts, diagnostics = provider(session, tmp_path).fetch_share_counts(
        {"AAA": 1}, date(2024, 1, 1), date(2024, 3, 31)
    )
    assert counts["AAA"] == []
    assert diagnostics.n_refused.get("unparseable_record") == 1


def test_a_duplicate_end_date_keeps_the_last_value_read(tmp_path):
    """Matches YFinanceProvider.get_shares_outstanding's documented keep-last
    de-duplication for the same situation (a preliminary vs. corrected
    filing for one date)."""
    session = FakeSession(
        {
            url_for(2024, 1): FakeResponse(
                200, frame_payload(record(1, "2024-02-16", 100_000_000.0), record(1, "2024-02-16", 200_000_000.0))
            )
        }
    )
    counts, _diagnostics = provider(session, tmp_path).fetch_share_counts(
        {"AAA": 1}, date(2024, 1, 1), date(2024, 3, 31)
    )
    assert [o.shares for o in counts["AAA"]] == [200_000_000.0]


# --- the two plausibility guards ---------------------------------------------
#
# These exist because the family's FIRST production run emitted a realized
# short-interest RATIO range of 0 .. 32,050,932, a quantity confined to ~[0, 1].
# Each test below carries the real ticker and value that motivated it.


def test_a_shell_registration_share_count_is_refused_by_the_absolute_floor(tmp_path):
    """FOXA 2019-03-18 really reports 1 share outstanding — a cover page filed
    before the Fox spin-off distribution. It is the case the scale-break guard
    CANNOT see, because it is FOXA's only record, so the ticker's own median is
    also 1 and nothing looks anomalous relative to it."""
    session = FakeSession(
        {url_for(2019, 1): FakeResponse(200, frame_payload(record(1754301, "2019-03-18", 1.0)))}
    )
    counts, diagnostics = provider(session, tmp_path).fetch_share_counts(
        {"FOXA": 1754301}, date(2019, 1, 1), date(2019, 3, 31)
    )
    assert counts["FOXA"] == []
    assert diagnostics.n_refused.get("below_plausible_share_floor") == 1
    assert diagnostics.refused_records == [("FOXA", date(2019, 3, 18), 1.0)]
    assert diagnostics.tickers_without_share_count == ["FOXA"]


def test_a_units_error_is_refused_by_the_scale_break_against_the_tickers_own_median(tmp_path):
    """AJG 2020-06-30 really reports 191,469,000,000,000 shares against its own
    median of ~210,588,000 — off by ~10^6. It is the case the absolute floor
    CANNOT see, because it is far ABOVE any floor. Its real neighbouring
    records must survive."""
    session = FakeSession(
        {
            url_for(2020, 1): FakeResponse(
                200,
                frame_payload(
                    record(354190, "2020-03-31", 189_621_000_000_000.0),
                    record(354190, "2020-01-31", 210_000_000.0),
                ),
            ),
            url_for(2020, 2): FakeResponse(
                200, frame_payload(record(354190, "2020-05-31", 211_000_000.0))
            ),
        }
    )
    counts, diagnostics = provider(session, tmp_path).fetch_share_counts(
        {"AJG": 354190}, date(2020, 1, 1), date(2020, 6, 30)
    )
    assert diagnostics.n_refused.get("share_count_scale_break") == 1
    assert [o.shares for o in counts["AJG"]] == [210_000_000.0, 211_000_000.0]


def test_the_guards_keep_the_lowest_real_share_count_in_the_index(tmp_path):
    """NVR trades around 2.7-3.7M shares outstanding — the lowest of any S&P
    500 constituent, and the binding constraint on how high the absolute floor
    may be set. It must survive."""
    session = FakeSession(
        {url_for(2024, 1): FakeResponse(200, frame_payload(record(906163, "2024-02-16", 2_664_860.0)))}
    )
    counts, diagnostics = provider(session, tmp_path).fetch_share_counts(
        {"NVR": 906163}, date(2024, 1, 1), date(2024, 3, 31)
    )
    assert [o.shares for o in counts["NVR"]] == [2_664_860.0]
    assert diagnostics.n_refused == {}


def test_the_scale_break_guard_does_not_fire_on_a_real_twenty_for_one_split(tmp_path):
    """AMZN's 2022 20-for-1 split is a real 20x change in the raw share count.
    It is what sets the LOWER edge of the threshold's plateau, and it must not
    be refused — which is exactly why the threshold is 100x and not 20x."""
    session = FakeSession(
        {
            url_for(2022, 1): FakeResponse(
                200, frame_payload(record(1018724, "2022-01-31", 509_000_000.0))
            ),
            url_for(2022, 2): FakeResponse(200, frame_payload()),
            url_for(2022, 3): FakeResponse(
                200, frame_payload(record(1018724, "2022-07-31", 10_180_000_000.0))
            ),
        }
    )
    counts, diagnostics = provider(session, tmp_path).fetch_share_counts(
        {"AMZN": 1018724}, date(2022, 1, 1), date(2022, 9, 30)
    )
    assert len(counts["AMZN"]) == 2
    assert diagnostics.n_refused == {}


def test_tickers_with_no_observation_and_no_cik_are_both_reported(tmp_path):
    session = FakeSession({url_for(2024, 1): FakeResponse(200, frame_payload())})
    counts, diagnostics = provider(session, tmp_path).fetch_share_counts(
        {"AAA": 1}, date(2024, 1, 1), date(2024, 3, 31), missing_from_map=["GONE"]
    )
    assert counts["AAA"] == []
    assert diagnostics.tickers_without_share_count == ["AAA"]
    assert diagnostics.tickers_without_cik == ["GONE"]


# --- the point-in-time step panel --------------------------------------------


def test_a_count_is_invisible_until_its_availability_date():
    index = bdays("2024-01-01", 200)
    close = pd.DataFrame(1.0, index=index, columns=["AAA"])
    observation = ShareCountObservation(
        as_of=date(2024, 2, 16),
        available=date(2024, 2, 16) + timedelta(days=VISIBILITY_LAG_DAYS),
        shares=100.0,
    )
    frame, unusable = build_point_in_time_share_count_frame(
        close, {"AAA": [observation]}, max_staleness_days=400
    )
    assert unusable == []
    available = pd.Timestamp(observation.available)
    assert frame.loc[frame.index < available, "AAA"].isna().all()
    assert frame.loc[frame.index >= available, "AAA"].notna().any()


def test_the_panel_is_a_step_function_not_an_interpolation():
    index = bdays("2024-01-01", 400)
    close = pd.DataFrame(1.0, index=index, columns=["AAA"])
    observations = [
        ShareCountObservation(date(2024, 1, 15), date(2024, 1, 15) + timedelta(days=VISIBILITY_LAG_DAYS), 100.0),
        ShareCountObservation(date(2024, 4, 15), date(2024, 4, 15) + timedelta(days=VISIBILITY_LAG_DAYS), 200.0),
    ]
    frame, _unusable = build_point_in_time_share_count_frame(
        close, {"AAA": observations}, max_staleness_days=400
    )
    assert sorted(set(frame["AAA"].dropna())) == [100.0, 200.0]


def test_a_count_carried_past_the_staleness_bound_is_refused():
    index = bdays("2024-01-01", 500)
    close = pd.DataFrame(1.0, index=index, columns=["AAA"])
    observation = ShareCountObservation(date(2024, 1, 15), date(2024, 1, 15), 100.0)
    frame, _unusable = build_point_in_time_share_count_frame(
        close, {"AAA": [observation]}, max_staleness_days=100
    )
    cutoff = pd.Timestamp("2024-01-15") + pd.Timedelta(days=100)
    assert frame.loc[frame.index <= cutoff, "AAA"].notna().any()
    assert frame.loc[frame.index > cutoff, "AAA"].isna().all()


def test_a_ticker_with_no_observations_gets_an_all_nan_column_and_is_named():
    index = bdays("2024-01-01", 30)
    close = pd.DataFrame(1.0, index=index, columns=["AAA", "BBB"])
    frame, unusable = build_point_in_time_share_count_frame(
        close, {"AAA": []}, max_staleness_days=400
    )
    assert unusable == ["AAA", "BBB"]
    assert frame.isna().all().all()


def test_the_panel_is_aligned_to_close_exactly():
    index = bdays("2024-01-01", 30)
    close = pd.DataFrame(1.0, index=index, columns=["BBB", "AAA"])
    frame, _unusable = build_point_in_time_share_count_frame(close, {}, max_staleness_days=400)
    assert frame.index.equals(close.index)
    assert frame.columns.equals(close.columns)
    assert np.isnan(frame.to_numpy()).all()
