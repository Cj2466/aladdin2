from datetime import date, timedelta

import pytest

from app.services.research_lab.sp500_membership_history import (
    _BASE_UNIVERSE,
    _EARLIEST_MEMBERSHIP_OVERRIDES,
    _EVENTS,
    MEMBERSHIP_DATA_AS_OF,
    MEMBERSHIP_DATA_START,
    MembershipExtension,
    PointInTimeUniverseError,
    _validate_earliest_override,
    apply_membership_extension,
    build_membership_warnings,
    clear_membership_extension,
    earliest_membership_date,
    get_membership_extension,
    get_membership_intervals,
    get_universe_as_of,
    get_universe_over,
    was_member,
)
from app.services.research_lab.ticker_universe import SCREENING_UNIVERSE


@pytest.fixture(autouse=True)
def vendored_only():
    """Same reasoning as test_sp500_membership_refresh.py's fixture of the
    same name: the extension is process-global module state, so a test
    that applies one and walks away would silently change what every
    later test in the session (in this file or any other) sees."""
    clear_membership_extension()
    yield
    clear_membership_extension()

# --- Vendored-data hygiene: catches a bad hand-edit to the literals the
# same way test_ticker_universe.py guards SCREENING_UNIVERSE. ------------


def test_base_universe_has_no_duplicates():
    assert len(_BASE_UNIVERSE) == len(set(_BASE_UNIVERSE))


def test_base_universe_uses_yfinance_dash_convention():
    # BRK.B / BF.B in the upstream CSV; both must arrive here translated,
    # so this module and ticker_universe.py speak one symbology.
    assert "BRK-B" in _BASE_UNIVERSE
    assert "BF-B" in _BASE_UNIVERSE
    assert not any("." in ticker for ticker in _BASE_UNIVERSE)


def test_events_are_chronological_and_never_add_and_remove_the_same_ticker():
    dates = [effective for effective, _added, _removed in _EVENTS]
    assert dates == sorted(dates)
    assert dates[0] > MEMBERSHIP_DATA_START
    assert dates[-1] <= MEMBERSHIP_DATA_AS_OF
    for effective, added, removed in _EVENTS:
        assert not set(added) & set(removed), f"{effective} both adds and removes a ticker"


def test_reconstructed_universe_size_stays_in_a_plausible_band():
    # The real index is not exactly 500 members on any given day (timing of
    # additions vs. removals), but it is never wildly off. Empirically
    # measured 2026-08-25 across all 236 reconstruction points in the
    # vendored window: min 498, max 507. A reconstruction bug (e.g. applying
    # an event twice, or dropping one) shows up here immediately.
    universe = set(_BASE_UNIVERSE)
    sizes = [len(universe)]
    for _effective, added, removed in _EVENTS:
        universe.difference_update(removed)
        universe.update(added)
        sizes.append(len(universe))
    assert min(sizes) >= 490
    assert max(sizes) <= 515


# --- Real-data empirical checks. Every date asserted here is an
# independently well-known index event, not a value copied out of the
# source file to make a test pass. ---------------------------------------


def test_svb_and_signature_bank_leave_the_index_on_their_real_removal_date():
    # Silicon Valley Bank failed 2023-03-10 and Signature Bank 2023-03-12;
    # S&P removed both before the open on 2023-03-15.
    assert was_member("SIVB", date(2023, 3, 14))
    assert was_member("SBNY", date(2023, 3, 14))
    assert not was_member("SIVB", date(2023, 3, 15))
    assert not was_member("SBNY", date(2023, 3, 15))


def test_first_republic_leaves_the_index_after_its_seizure():
    # Seized 2023-05-01; removed from the index 2023-05-04. Deliberately a
    # separate event from the March bank failures above — one shared removal
    # date would not distinguish real data from a coincidence.
    assert was_member("FRC", date(2023, 5, 3))
    assert not was_member("FRC", date(2023, 5, 4))


def test_activision_leaves_the_index_after_the_microsoft_deal_closed():
    # Microsoft closed the acquisition 2023-10-13; index removal 2023-10-18.
    assert was_member("ATVI", date(2023, 10, 17))
    assert not was_member("ATVI", date(2023, 10, 18))


def test_tesla_joins_the_index_on_its_real_addition_date():
    assert not was_member("TSLA", date(2020, 12, 18))
    assert was_member("TSLA", date(2020, 12, 21))


def test_palantir_joins_the_index_on_its_real_addition_date():
    assert not was_member("PLTR", date(2024, 9, 20))
    assert was_member("PLTR", date(2024, 9, 23))


def test_reconstruction_at_data_as_of_matches_the_current_snapshot_within_known_drift():
    # ticker_universe.SCREENING_UNIVERSE is an independently sourced
    # snapshot taken 2026-08-24, eight weeks after this module's data ends.
    # Agreement on 500/503 with exactly the six real index changes in
    # between is the cross-source check that this reconstruction is not
    # quietly wrong; asserting exact equality would instead be asserting
    # that the index never changes.
    reconstructed = set(get_universe_as_of(MEMBERSHIP_DATA_AS_OF))
    current = set(SCREENING_UNIVERSE)
    assert len(reconstructed) == 503
    assert current - reconstructed == {"FERG", "RDDT", "VMRK"}
    assert reconstructed - current == {"AVB", "EA", "EQR"}


def test_five_year_union_is_materially_larger_than_todays_universe():
    # The survivorship gap this module exists to expose, measured rather
    # than assumed: 5 years of real index membership contains ~20% more
    # distinct tickers than a single day's snapshot does.
    end = MEMBERSHIP_DATA_AS_OF
    union = get_universe_over(end - timedelta(days=round(5 * 365.25)), end)
    assert len(union) > len(SCREENING_UNIVERSE) + 50
    for departed in ("SIVB", "FRC", "ATVI", "TWTR", "XLNX"):
        assert departed in union
        assert departed not in SCREENING_UNIVERSE


# --- Ticker-rename correction ------------------------------------------


def test_earliest_membership_date_looks_through_a_ticker_rename():
    # META's ticker only exists from the 2022-06-09 FB -> META change, but
    # the company has been an index member since 2013-12-23. Without
    # _EARLIEST_MEMBERSHIP_OVERRIDES this would report 2022, and every
    # 5-year META backtest would carry a false inclusion-bias warning.
    assert earliest_membership_date("META") == date(2013, 12, 23)
    assert earliest_membership_date("ELV") == date(2002, 7, 25)
    assert earliest_membership_date("RTX") == date(1957, 3, 4)


def test_earliest_membership_date_is_censored_at_the_data_window_for_old_members():
    # AAPL has been in the index since 1982, but this module's data starts
    # in 2015 — a censored lower bound, which is exactly why
    # build_membership_warnings emits a coverage warning instead of
    # claiming AAPL "joined" in 2015.
    assert earliest_membership_date("AAPL") == MEMBERSHIP_DATA_START


def test_earliest_membership_date_is_none_for_a_non_member():
    assert earliest_membership_date("SPY") is None
    assert get_membership_intervals("SPY") == []


# --- earliest_overrides validation ---------------------------------------
#
# The regression this whole block guards: apply_membership_extension used
# to apply ANY (ticker, date) pair in earliest_overrides with no checks at
# all. Proven exploitable with a hand-built extension claiming a real,
# well-documented-late-IPO ticker (GE HealthCare, ticker GEHC, spun off
# from GE and added to the index on its real, dated 2023-01-04 IPO — see
# the vendored event above) had been an S&P 500 member decades earlier.
# That would have silently corrupted every screening/backtest that reads
# earliest_membership_date("GEHC") or a GEHC inclusion-bias warning from
# build_membership_warnings, without so much as a log line.


def test_earliest_membership_date_before_any_override_reflects_gehcs_real_ipo():
    # The real, dated, hand-verified event this whole test class is about:
    # GE HealthCare only became a public company (and an S&P 500 member)
    # on 2023-01-04, per the vendored _MEMBERSHIP_EVENTS above.
    assert earliest_membership_date("GEHC") == date(2023, 1, 4)


def test_fake_gehc_override_predating_the_sp500_itself_is_rejected():
    # Reconstruction of the exploit: a hand-built extension claiming GEHC
    # was already an S&P 500 constituent before the index itself existed
    # (1957-03-04) — i.e. six decades before its real, well-documented
    # 2023-01-04 IPO. No caller of apply_membership_extension re-derives
    # or cross-checks this field, so before this fix it was applied as-is.
    exploit = MembershipExtension(
        coverage_end=MEMBERSHIP_DATA_AS_OF,
        earliest_overrides=(("GEHC", date(1957, 1, 1)),),
    )
    with pytest.raises(PointInTimeUniverseError, match="before the index itself existed"):
        apply_membership_extension(exploit)
    # The universe must be left exactly as it was — no half-applied state.
    assert earliest_membership_date("GEHC") == date(2023, 1, 4)
    assert get_membership_extension() is None


def test_earliest_override_rejects_a_future_dated_claim():
    tomorrow = date.today() + timedelta(days=1)
    exploit = MembershipExtension(
        coverage_end=MEMBERSHIP_DATA_AS_OF,
        earliest_overrides=(("GEHC", tomorrow),),
    )
    with pytest.raises(PointInTimeUniverseError, match="in the future"):
        apply_membership_extension(exploit)


def test_earliest_override_rejects_a_malformed_ticker_or_non_date():
    with pytest.raises(PointInTimeUniverseError, match="not a well-formed equity ticker"):
        apply_membership_extension(
            MembershipExtension(
                coverage_end=MEMBERSHIP_DATA_AS_OF,
                earliest_overrides=(("'; DROP TABLE tickers;--", date(1990, 1, 1)),),
            )
        )
    with pytest.raises(PointInTimeUniverseError, match="not a date"):
        apply_membership_extension(
            MembershipExtension(
                coverage_end=MEMBERSHIP_DATA_AS_OF,
                earliest_overrides=(("GEHC", "1990-01-01"),),  # type: ignore[arg-type]
            )
        )


def test_all_hand_verified_vendored_overrides_pass_the_new_validation():
    # The no-false-positive guarantee for the 28 STATIC overrides that
    # already ship in this module (BALL, RTX, GL, ... — several of which
    # legitimately predate MEMBERSHIP_DATA_START by decades, which is
    # exactly why that was rejected as a validation rule; see the comment
    # above _SP500_INCEPTION). If a future edit to the validation logic
    # ever tightened it enough to reject one of these known-good,
    # hand-checked entries, this is the test that would catch it.
    for ticker, iso_date in _EARLIEST_MEMBERSHIP_OVERRIDES.items():
        _validate_earliest_override(ticker, date.fromisoformat(iso_date))  # must not raise


def test_a_legitimate_earliest_override_still_applies_correctly():
    # No false-positive rejection: a real rename-shaped correction (a new
    # ticker introduced by an extension event, whose predecessor company
    # was actually a member years earlier) must still take effect exactly
    # as it did before this fix.
    rename_event = (date(2026, 9, 1), ("NEWCO",), ("OLDCO",))
    legitimate = MembershipExtension(
        coverage_end=MEMBERSHIP_DATA_AS_OF,
        events=(rename_event,),
        earliest_overrides=(("NEWCO", date(2004, 4, 23)),),
    )
    apply_membership_extension(legitimate)
    assert earliest_membership_date("NEWCO") == date(2004, 4, 23)
    # ...and a long replay carries no false inclusion-bias warning, exactly
    # the behaviour _EARLIEST_MEMBERSHIP_OVERRIDES exists to produce.
    assert build_membership_warnings("NEWCO", [date(2022, 1, 4), date(2026, 9, 5)]) == []


# --- Interval / coverage semantics --------------------------------------


def test_membership_intervals_are_half_open_at_the_removal_date():
    intervals = get_membership_intervals("SIVB")
    assert len(intervals) == 1
    started, ended = intervals[0]
    assert ended == date(2023, 3, 15)
    assert was_member("SIVB", started)
    assert not was_member("SIVB", ended)


def test_a_re_entering_ticker_keeps_separate_intervals():
    # FSLR really did leave the index in 2017 and rejoin in 2022 — a genuine
    # re-entry, not a data artifact, so it must not be flattened into one
    # continuous span.
    intervals = get_membership_intervals("FSLR")
    assert len(intervals) == 2
    assert not was_member("FSLR", date(2019, 1, 2))
    assert was_member("FSLR", date(2023, 1, 3))


def test_get_universe_as_of_rejects_dates_outside_coverage():
    with pytest.raises(PointInTimeUniverseError):
        get_universe_as_of(MEMBERSHIP_DATA_START - timedelta(days=1))
    with pytest.raises(PointInTimeUniverseError):
        get_universe_as_of(MEMBERSHIP_DATA_AS_OF + timedelta(days=1))


def test_get_universe_over_rejects_an_uncovered_start_but_clamps_a_future_end():
    with pytest.raises(PointInTimeUniverseError):
        get_universe_over(MEMBERSHIP_DATA_START - timedelta(days=1), MEMBERSHIP_DATA_AS_OF)
    with pytest.raises(PointInTimeUniverseError):
        get_universe_over(date(2024, 1, 2), date(2023, 1, 2))
    # A far-future end must clamp silently rather than raise — the natural
    # call passes end=today, which is always past MEMBERSHIP_DATA_AS_OF.
    clamped = get_universe_over(date(2024, 1, 2), date(2099, 1, 1))
    assert clamped == get_universe_over(date(2024, 1, 2), MEMBERSHIP_DATA_AS_OF)


def test_get_universe_over_is_a_union_not_an_endpoint_snapshot():
    # The task this primitive exists for: a lookback window that ENDS after
    # a removal must still contain the removed member, because a
    # walk-forward replay over that window really could have held it.
    spanning = get_universe_over(date(2023, 1, 4), date(2023, 6, 30))
    assert "SIVB" in spanning
    assert "SIVB" not in get_universe_as_of(date(2023, 6, 30))
    # ...and a window that starts after the removal must not.
    after = get_universe_over(date(2023, 6, 1), date(2023, 12, 29))
    assert "SIVB" not in after


# --- build_membership_warnings ------------------------------------------


def _trading_days(start: date, end: date) -> list[date]:
    """Weekday-only date list — the shape a replay index has. Holidays are
    irrelevant here: these tests assert on relative counts and on which
    warnings fire, never on an exact trading-day total."""
    days = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def test_no_warnings_for_a_ticker_that_was_never_an_index_member():
    # An ETF is not an S&P 500 membership claim, so there is nothing to
    # disclose — silence, not a spurious "SPY was never in the index".
    assert build_membership_warnings("SPY", _trading_days(date(2021, 1, 4), date(2026, 1, 2))) == []


def test_no_warnings_for_a_continuous_member_over_a_covered_window():
    assert build_membership_warnings("AAPL", _trading_days(date(2021, 1, 4), date(2026, 6, 1))) == []


def test_inclusion_bias_warning_fires_for_a_recently_added_member():
    # PLTR joined 2024-09-23; a 5-year replay is mostly pre-membership.
    warnings = build_membership_warnings("PLTR", _trading_days(date(2021, 8, 25), date(2026, 6, 1)))
    assert len(warnings) == 1
    assert "PLTR joined the S&P 500 on 2024-09-23" in warnings[0]
    assert "inclusion-biased" in warnings[0]


def test_removal_warning_fires_for_a_departed_member():
    warnings = build_membership_warnings("SIVB", _trading_days(date(2021, 8, 25), date(2023, 12, 29)))
    assert len(warnings) == 1
    assert "SIVB left the S&P 500 on 2023-03-15" in warnings[0]


def test_coverage_warning_fires_for_days_before_the_data_window():
    warnings = build_membership_warnings("AAPL", _trading_days(date(2013, 1, 2), date(2016, 1, 4)))
    assert len(warnings) == 1
    assert "membership data starts 2015-01-07" in warnings[0]
    assert "were not checked" in warnings[0]


def test_warning_counts_only_the_days_actually_outside_membership():
    joined = date(2024, 9, 23)
    days = _trading_days(date(2024, 1, 1), date(2025, 1, 1))
    expected_before = sum(1 for d in days if d < joined)
    warnings = build_membership_warnings("PLTR", days)
    assert f"{expected_before} of the {len(days)} replayed trading days" in warnings[0]


def test_empty_replay_produces_no_warnings():
    assert build_membership_warnings("PLTR", []) == []
