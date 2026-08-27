from datetime import date, timedelta

import pytest

from app.services.research_lab import small_cap_membership_history as scm
from app.services.research_lab.small_cap_membership_history import (
    MEMBERSHIP_DATA_AS_OF,
    MEMBERSHIP_DATA_START,
    NOMINAL_INDEX_SIZE,
    SmallCapPointInTimeUniverseError,
    build_membership_warnings,
    get_membership_intervals,
    get_universe_as_of,
    get_universe_over,
    membership_data_quality,
    was_member,
)
from app.services.research_lab.sp500_membership_history import PointInTimeUniverseError

# --- coverage boundaries (mirrors test_sp500_membership_history's own) ------


def test_coverage_window_is_the_documented_one():
    assert MEMBERSHIP_DATA_START == date(2020, 1, 1)
    assert MEMBERSHIP_DATA_AS_OF == date(2026, 8, 4)
    assert MEMBERSHIP_DATA_START < MEMBERSHIP_DATA_AS_OF


def test_dates_outside_coverage_raise_rather_than_silently_clamp():
    # The whole point of SmallCapPointInTimeUniverseError: a backtest quietly
    # told "the 2017 small-cap index looked like the 2020 one" is worse than
    # one that fails loudly.
    with pytest.raises(SmallCapPointInTimeUniverseError):
        get_universe_as_of(MEMBERSHIP_DATA_START - timedelta(days=1))
    with pytest.raises(SmallCapPointInTimeUniverseError):
        get_universe_as_of(MEMBERSHIP_DATA_AS_OF + timedelta(days=1))
    with pytest.raises(SmallCapPointInTimeUniverseError):
        get_universe_over(MEMBERSHIP_DATA_START - timedelta(days=1), MEMBERSHIP_DATA_AS_OF)
    with pytest.raises(SmallCapPointInTimeUniverseError):
        get_universe_over(date(2022, 1, 1), date(2021, 1, 1))


def test_its_error_type_is_not_the_sp500_modules():
    # Deliberately a distinct exception type: a caller catching one must not
    # swallow the other, because the two speak to different universes with
    # different coverage windows.
    assert not issubclass(SmallCapPointInTimeUniverseError, PointInTimeUniverseError)
    assert not issubclass(PointInTimeUniverseError, SmallCapPointInTimeUniverseError)


def test_end_is_clamped_but_start_is_not():
    # end=today must work (it is the only real call); a start before coverage
    # must not.
    far_future = MEMBERSHIP_DATA_AS_OF + timedelta(days=900)
    clamped = get_universe_over(MEMBERSHIP_DATA_START, far_future)
    exact = get_universe_over(MEMBERSHIP_DATA_START, MEMBERSHIP_DATA_AS_OF)
    assert clamped == exact


# --- the falsification test, asserted rather than only documented ----------


def test_membership_data_quality_matches_the_disclosed_numbers():
    q = membership_data_quality()
    assert q["coverage_start"] == MEMBERSHIP_DATA_START
    assert q["coverage_end"] == MEMBERSHIP_DATA_AS_OF
    assert q["n_dated_events"] == 241
    assert q["n_base_universe"] == 612
    assert q["n_undated_removals"] == 12
    assert q["n_undated_readditions"] == 1
    # The band the module's header states: 603 .. 614 tickers for a nominally
    # 600-COMPANY index. Asserted so a future data refresh that degrades the
    # reconstruction cannot leave a stale prose claim behind.
    assert q["min_members"] == 603
    assert q["max_members"] == 614


def test_member_count_never_strays_far_from_the_index_nominal_size():
    # DRIFT IS INCOMPLETENESS for a changes-table-derived dataset (see the
    # module header). This is the falsification test itself: the replayed
    # count must stay within a few percent of 600 at every event date, or
    # the reconstruction is missing events and nothing should be built on it.
    q = membership_data_quality()
    assert q["member_count_drift_fraction"] < 0.03
    for n in (q["min_members"], q["max_members"]):
        assert abs(n - NOMINAL_INDEX_SIZE) / NOMINAL_INDEX_SIZE < 0.03


def test_forward_replay_reproduces_the_current_snapshot_exactly():
    # The round-trip standard sp500_membership_history holds itself to
    # ("reproduce the source file's own final row exactly, 503/503"): the
    # base universe plus every dated event plus the undated reconciliation
    # must land on exactly the vendored current-constituent count.
    assert len(get_universe_as_of(MEMBERSHIP_DATA_AS_OF)) == 603
    assert len(get_universe_as_of(MEMBERSHIP_DATA_START)) == 612


# --- real, independently-known index events -------------------------------


def test_failure_driven_removals_are_dated_correctly():
    # These are the survivorship-relevant events -- names that left the index
    # because the company deteriorated. Each date was verified against
    # independent knowledge of the real corporate event (see the module
    # header's spot-verification list).
    assert was_member("BBBY", date(2021, 6, 1)) is True  # Bed Bath & Beyond, pre-collapse
    assert was_member("BBBY", date(2023, 6, 1)) is False  # removed 2023-03-20
    assert was_member("WW", date(2022, 6, 1)) is True
    assert was_member("WW", date(2024, 1, 1)) is False  # removed 2023-03-20
    assert was_member("RILY", date(2023, 1, 1)) is True
    assert was_member("RILY", date(2025, 1, 1)) is False  # removed 2024-09-23


def test_a_promotion_out_of_the_small_cap_index_is_also_captured():
    # GME left the S&P 600 by being promoted OUT (the 2021 meme-stock run
    # made it too large), the opposite direction from a failure -- both must
    # be dated, or the universe is biased in one direction.
    assert was_member("GME", date(2020, 6, 1)) is True
    assert was_member("GME", date(2022, 1, 1)) is False


def test_large_caps_are_never_small_cap_members():
    # The gate must answer False for S&P 500 names -- passing this module's
    # was_member as membership_fn is what makes the harness screen the small-
    # cap cross-section rather than an accidental mixture.
    for ticker in ("AAPL", "MSFT", "NVDA", "JPM"):
        assert was_member(ticker, date(2022, 6, 1)) is False


def test_membership_intervals_are_ordered_and_bounded():
    for ticker in ("BBBY", "GME", "WW"):
        spans = get_membership_intervals(ticker)
        assert spans
        assert spans == sorted(spans)
        for began, ended in spans:
            assert began >= MEMBERSHIP_DATA_START
            if ended is not None:
                assert ended > began


def test_unknown_ticker_has_no_recorded_membership():
    assert get_membership_intervals("NOT-A-TICKER") == []
    assert was_member("NOT-A-TICKER", date(2022, 1, 1)) is False


def test_get_universe_over_is_a_union_not_a_snapshot():
    # The survivorship-free candidate pool primitive: every ticker that was a
    # member on ANY day of the window, so it must strictly exceed either
    # endpoint's snapshot.
    union = get_universe_over(MEMBERSHIP_DATA_START, MEMBERSHIP_DATA_AS_OF)
    start_snapshot = get_universe_as_of(MEMBERSHIP_DATA_START)
    end_snapshot = get_universe_as_of(MEMBERSHIP_DATA_AS_OF)
    assert len(union) > len(start_snapshot)
    assert len(union) > len(end_snapshot)
    assert set(start_snapshot) <= set(union)
    assert set(end_snapshot) <= set(union)
    # A name that both joined and left inside the window is in the union and
    # in neither snapshot -- exactly the population survivorship bias eats.
    assert "WW" in union
    assert "WW" not in start_snapshot
    assert "WW" not in end_snapshot


def test_get_universe_over_equals_the_brute_force_union_of_daily_snapshots():
    # get_universe_over walks INTERVALS for speed rather than every day in
    # the window, so its overlap arithmetic ([began, ended) intersects
    # [start, end] iff began <= end and ended > start) is worth checking
    # against the definition it is an optimization of. Windowed to keep the
    # brute force cheap; verified over the full coverage window too (1088 ==
    # 1088) when this was written.
    start, end = date(2021, 3, 1), date(2022, 9, 15)
    brute: set[str] = set()
    day = start
    while day <= end:
        brute |= set(get_universe_as_of(day))
        day += timedelta(days=1)
    assert set(get_universe_over(start, end)) == brute


def test_universe_as_of_and_was_member_never_disagree():
    # get_universe_as_of reads the replayed intervals rather than re-walking
    # the raw events precisely so these two can never diverge -- in
    # particular so the undated reconciliation is applied by both.
    for probe in (MEMBERSHIP_DATA_START, date(2022, 7, 1), MEMBERSHIP_DATA_AS_OF):
        snapshot = set(get_universe_as_of(probe))
        for ticker in ("BBBY", "GME", "WW", "AAPL", "RILY"):
            assert (ticker in snapshot) == was_member(ticker, probe)


# --- the undated reconciliation, disclosed rather than smoothed away -------


def test_undated_removals_are_removed_at_coverage_end_and_flagged():
    # Wikipedia dates these tickers' addition but never their removal. They
    # are removed at coverage end -- so each stays eligible for an unknown
    # stretch past its real removal date, which the warning text must say.
    assert len(scm._UNDATED_REMOVALS) == 12
    for ticker in scm._UNDATED_REMOVALS:
        spans = get_membership_intervals(ticker)
        assert spans
        assert spans[-1][1] == MEMBERSHIP_DATA_AS_OF
    warnings = build_membership_warnings(
        scm._UNDATED_REMOVALS[0], [date(2026, 8, 20), date(2026, 8, 21)]
    )
    assert any("UNDATED removal" in w for w in warnings)


def test_undated_readdition_is_restored_at_coverage_end():
    assert scm._UNDATED_READDITIONS == ("BBT",)
    assert was_member("BBT", MEMBERSHIP_DATA_AS_OF) is True


# --- warnings -------------------------------------------------------------


def test_warnings_flag_days_outside_a_tickers_real_membership():
    # BBBY was removed 2023-03-20; replaying it well after that must say so.
    warnings = build_membership_warnings("BBBY", [date(2024, 1, 3), date(2024, 1, 4)])
    assert warnings
    assert any("left the S&P 600" in w for w in warnings)


def test_warnings_are_empty_for_a_ticker_with_no_recorded_membership():
    assert build_membership_warnings("AAPL", [date(2022, 1, 3)]) == []
    assert build_membership_warnings("BBBY", []) == []
