from datetime import date, timedelta

import pytest

from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_AS_OF,
    MEMBERSHIP_DATA_START,
    MembershipExtension,
    PointInTimeUniverseError,
    apply_membership_extension,
    build_membership_warnings,
    clear_membership_extension,
    earliest_membership_date,
    get_live_membership,
    get_membership_extension,
    get_universe_as_of,
    membership_coverage_end,
    vendored_events,
    was_member,
)
from app.services.research_lab.sp500_membership_refresh import (
    LIVE_MEMBERSHIP_MAX_AGE_DAYS,
    MAX_TICKER_CHANGES_PER_EFFECTIVE_DATE,
    LiveConstituents,
    MembershipRefreshError,
    UpstreamHistory,
    _normalize_ticker,
    _parse_spy_workbook_rows,
    derive_events,
    fetch_spy_constituents,
    fetch_wikipedia_constituents,
    plan_refresh,
)


@pytest.fixture(autouse=True)
def vendored_only():
    """Every test here starts from — and leaves behind — the vendored-only
    state. The extension is process-global module state (deliberately: it
    is a cache of a network fetch, not per-request data), so a test that
    applied one and walked away would silently change what every later
    test in the session sees."""
    clear_membership_extension()
    yield
    clear_membership_extension()


# --- Fixtures: the smallest inputs that exercise the real decisions ------

TODAY = date(2026, 8, 25)
LIVE_AS_OF = date(2026, 8, 24)


def _universe_at_coverage() -> set[str]:
    return set(get_universe_as_of(MEMBERSHIP_DATA_AS_OF))


def _upstream_from(events: list[tuple[date, list[str], list[str]]]) -> UpstreamHistory:
    """Rebuilds a full snapshot series equivalent to the vendored data plus
    `events`, which is what the real upstream file is."""
    snapshots: list[tuple[date, frozenset[str]]] = []
    universe = set(get_universe_as_of(MEMBERSHIP_DATA_START))
    snapshots.append((MEMBERSHIP_DATA_START, frozenset(universe)))
    for effective, added, removed in [
        (effective, list(added), list(removed)) for effective, added, removed in vendored_events()
    ] + events:
        universe.difference_update(removed)
        universe.update(added)
        snapshots.append((effective, frozenset(universe)))
    return UpstreamHistory(snapshots=tuple(snapshots), source_url="test://upstream")


def _live(members: set[str], added_dates: dict[str, date] | None = None) -> tuple[LiveConstituents, LiveConstituents]:
    spy = LiveConstituents(members=frozenset(members), as_of=LIVE_AS_OF, source="SPY (test)")
    wiki = LiveConstituents(
        members=frozenset(members),
        as_of=LIVE_AS_OF,
        source="Wikipedia (test)",
        added_dates=added_dates or {},
    )
    return spy, wiki


# --- derive_events: the transformation the vendored literals came from ---


def test_derive_events_round_trips_a_snapshot_series():
    upstream = _upstream_from([(date(2026, 7, 15), ["NEWA"], ["AAPL"])])
    base, events = derive_events(upstream.snapshots)
    assert base == frozenset(get_universe_as_of(MEMBERSHIP_DATA_START))
    assert events[: len(vendored_events())] == vendored_events()
    assert events[-1] == (date(2026, 7, 15), ("NEWA",), ("AAPL",))


def test_derive_events_skips_snapshots_that_did_not_change():
    # ~99% of the real upstream file's rows repeat the previous row; a
    # no-change row must produce no event at all, not an empty one.
    members = frozenset({"AAA", "BBB"})
    _base, events = derive_events(
        ((date(2026, 1, 1), members), (date(2026, 1, 2), members), (date(2026, 1, 3), frozenset({"AAA"})))
    )
    assert events == ((date(2026, 1, 3), (), ("BBB",)),)


def test_derive_events_handles_an_empty_series():
    assert derive_events(()) == (frozenset(), ())


# --- Symbology ------------------------------------------------------------


def test_normalize_ticker_translates_dual_class_and_rejects_non_equities():
    assert _normalize_ticker("BRK.B") == "BRK-B"
    assert _normalize_ticker(" aapl ") == "AAPL"
    # The two non-equity lines the real SPY holdings file actually carries.
    assert _normalize_ticker("-") is None
    assert _normalize_ticker("2602335D") is None
    assert _normalize_ticker("") is None


# --- Upstream tier --------------------------------------------------------


def test_upstream_extends_coverage_forward_with_its_real_dates():
    upstream = _upstream_from([(date(2026, 7, 15), ["NEWA"], ["AAPL"])])
    outcome = plan_refresh(upstream=upstream, spy=None, wikipedia=None, today=TODAY)

    assert outcome.applied
    assert outcome.n_dated_events == 1
    assert outcome.coverage_end == date(2026, 7, 15)
    apply_membership_extension(outcome.extension)
    assert membership_coverage_end() == date(2026, 7, 15)
    assert was_member("NEWA", date(2026, 7, 15))
    assert not was_member("AAPL", date(2026, 7, 15))
    assert "NEWA" in get_universe_as_of(date(2026, 7, 15))


def test_upstream_never_touches_the_verified_window():
    upstream = _upstream_from([(date(2026, 7, 15), ["NEWA"], [])])
    outcome = plan_refresh(upstream=upstream, spy=None, wikipedia=None, today=TODAY)
    apply_membership_extension(outcome.extension)

    # Every hand-verified fact the existing suite asserts must survive.
    assert was_member("SIVB", date(2023, 3, 14))
    assert not was_member("SIVB", date(2023, 3, 15))
    assert earliest_membership_date("META") == date(2013, 12, 23)
    assert set(get_universe_as_of(MEMBERSHIP_DATA_AS_OF)) == _universe_at_coverage()


def test_upstream_is_refused_when_it_no_longer_reproduces_the_verified_end_state():
    # Simulates upstream silently changing history: the handoff state no
    # longer matches, so splicing onto it would produce a membership
    # timeline that is neither source's truth.
    upstream = _upstream_from([])
    corrupted = tuple(
        (when, members - {"AAPL"} if when > date(2020, 1, 1) else members) for when, members in upstream.snapshots
    )
    outcome = plan_refresh(
        upstream=UpstreamHistory(snapshots=corrupted, source_url="test://corrupt"),
        spy=None,
        wikipedia=None,
        today=TODAY,
    )
    assert not outcome.applied
    assert any("no longer reproduces this module's verified state" in w for w in outcome.warnings)
    assert membership_coverage_end() == MEMBERSHIP_DATA_AS_OF


def test_upstream_redating_inside_the_window_warns_but_still_extends_forward():
    # Upstream really does merge historical date fixes. The end state still
    # matches, so the forward splice is safe — but the vendored literals
    # must not be quietly rewritten, and the operator must be told.
    upstream = _upstream_from([(date(2026, 7, 15), ["NEWA"], [])])
    revised = list(upstream.snapshots)
    shifted_index = next(i for i, (when, _m) in enumerate(revised) if when == date(2023, 3, 15))
    revised[shifted_index] = (date(2023, 3, 16), revised[shifted_index][1])

    outcome = plan_refresh(
        upstream=UpstreamHistory(snapshots=tuple(revised), source_url="test://revised"),
        spy=None,
        wikipedia=None,
        today=TODAY,
    )
    assert outcome.applied
    assert outcome.n_dated_events == 1
    assert any("review and re-vendor by hand" in w for w in outcome.warnings)
    # The vendored 2023-03-15 removal still stands, unrewritten.
    apply_membership_extension(outcome.extension)
    assert not was_member("SIVB", date(2023, 3, 15))


def test_upstream_events_that_blow_past_the_plausible_churn_limit_are_rejected():
    absurd = [f"Z{n:03d}" for n in range(MAX_TICKER_CHANGES_PER_EFFECTIVE_DATE + 1)]
    upstream = _upstream_from([(date(2026, 7, 15), absurd, [])])
    outcome = plan_refresh(upstream=upstream, spy=None, wikipedia=None, today=TODAY)
    assert not outcome.applied
    assert any("plausible-churn limit" in w for w in outcome.warnings)


def test_upstream_events_that_blow_past_the_plausible_size_band_are_rejected():
    upstream = _upstream_from([(date(2026, 7, 15), [], sorted(_universe_at_coverage())[:100])])
    outcome = plan_refresh(upstream=upstream, spy=None, wikipedia=None, today=TODAY)
    assert not outcome.applied
    assert any("plausible" in w and "band" in w for w in outcome.warnings)


def test_future_dated_upstream_events_are_rejected():
    upstream = _upstream_from([(TODAY + timedelta(days=30), ["NEWA"], [])])
    outcome = plan_refresh(upstream=upstream, spy=None, wikipedia=None, today=TODAY)
    assert not outcome.applied
    assert any("dated in the future" in w for w in outcome.warnings)


# --- Live tier ------------------------------------------------------------


def test_live_additions_are_dated_from_wikipedia_not_from_the_observation_date():
    joined = date(2026, 8, 5)
    spy, wiki = _live(_universe_at_coverage() | {"NEWA"}, {"NEWA": joined})
    outcome = plan_refresh(upstream=None, spy=spy, wikipedia=wiki, today=TODAY)

    assert outcome.applied
    assert outcome.n_live_dated_additions == 1
    apply_membership_extension(outcome.extension)
    assert earliest_membership_date("NEWA") == joined
    # ...and the live tier must NOT claim dated coverage it does not have.
    assert membership_coverage_end() == MEMBERSHIP_DATA_AS_OF
    with pytest.raises(PointInTimeUniverseError):
        get_universe_as_of(joined)


def test_a_live_member_whose_wikipedia_date_predates_coverage_is_treated_as_a_rename():
    # The real 2026 case: VMRK appears in the live index with a "Date
    # added" of 2001 because the company was a member under a previous
    # ticker. Dating that as a 2026 addition would emit a huge false
    # inclusion-bias warning, so it becomes an earliest-membership
    # override instead — silent until upstream supplies the real event.
    spy, wiki = _live(_universe_at_coverage() | {"SUCC"}, {"SUCC": date(2001, 12, 3)})
    outcome = plan_refresh(upstream=None, spy=spy, wikipedia=wiki, today=TODAY)

    assert outcome.n_live_dated_additions == 0
    assert ("SUCC", date(2001, 12, 3)) in outcome.extension.earliest_overrides
    apply_membership_extension(outcome.extension)
    assert earliest_membership_date("SUCC") is None
    assert build_membership_warnings("SUCC", [date(2026, 1, 5)]) == []


def test_an_undatable_live_addition_is_left_undated_rather_than_guessed():
    spy, wiki = _live(_universe_at_coverage() | {"NEWA"}, {})
    outcome = plan_refresh(upstream=None, spy=spy, wikipedia=wiki, today=TODAY)
    assert outcome.n_live_dated_additions == 0
    assert any("no usable addition date" in w for w in outcome.warnings)
    apply_membership_extension(outcome.extension)
    assert earliest_membership_date("NEWA") is None


def test_live_departure_is_disclosed_without_inventing_a_removal_date():
    departed = "AVB"
    spy, wiki = _live(_universe_at_coverage() - {departed})
    outcome = plan_refresh(upstream=None, spy=spy, wikipedia=wiki, today=TODAY)
    apply_membership_extension(outcome.extension)

    warnings = build_membership_warnings(departed, [date(2026, 1, 5), date(2026, 6, 1)])
    assert len(warnings) == 1
    assert f"{departed} is not an S&P 500 constituent as of {LIVE_AS_OF.isoformat()}" in warnings[0]
    assert "removal date is not known yet" in warnings[0]
    # No fabricated interval end anywhere.
    assert was_member(departed, MEMBERSHIP_DATA_AS_OF)


def test_a_single_live_source_is_never_enough_to_assert_membership():
    spy, _wiki = _live(_universe_at_coverage() | {"NEWA"}, {"NEWA": date(2026, 8, 5)})
    outcome = plan_refresh(upstream=None, spy=spy, wikipedia=None, today=TODAY)
    assert not outcome.applied
    assert any("single unconfirmed source" in w for w in outcome.warnings)
    assert get_live_membership() is None


def test_live_sources_that_disagree_a_little_leave_the_disputed_tickers_undecided():
    shared = _universe_at_coverage()
    spy = LiveConstituents(members=frozenset(shared | {"ONLYA"}), as_of=LIVE_AS_OF, source="SPY (test)")
    wiki = LiveConstituents(
        members=frozenset(shared | {"ONLYB"}),
        as_of=LIVE_AS_OF,
        source="Wikipedia (test)",
        added_dates={"ONLYA": date(2026, 8, 5), "ONLYB": date(2026, 8, 5)},
    )
    outcome = plan_refresh(upstream=None, spy=spy, wikipedia=wiki, today=TODAY)

    assert outcome.applied
    assert any("undecided" in w for w in outcome.warnings)
    assert outcome.n_live_dated_additions == 0
    apply_membership_extension(outcome.extension)
    assert earliest_membership_date("ONLYA") is None
    assert earliest_membership_date("ONLYB") is None


def test_live_sources_that_disagree_wildly_are_rejected_outright():
    shared = _universe_at_coverage()
    spy = LiveConstituents(members=frozenset(shared), as_of=LIVE_AS_OF, source="SPY (test)")
    wiki = LiveConstituents(
        members=frozenset(sorted(shared)[:250]),
        as_of=LIVE_AS_OF,
        source="Wikipedia (test)",
        added_dates={},
    )
    outcome = plan_refresh(upstream=None, spy=spy, wikipedia=wiki, today=TODAY)
    assert not outcome.applied
    assert any("outside the plausible" in w or "disagree on" in w for w in outcome.warnings)


def test_live_data_wildly_adrift_from_the_reconstruction_is_rejected():
    # Both sources agree with each other but not with reality — e.g. a
    # holdings file for the wrong fund. Plausible size, implausible drift.
    bogus = {f"Q{n:03d}" for n in range(495)}
    spy, wiki = _live(bogus)
    outcome = plan_refresh(upstream=None, spy=spy, wikipedia=wiki, today=TODAY)
    assert not outcome.applied
    assert any("implausible" in w for w in outcome.warnings)


# --- Failure / carry-forward behaviour ------------------------------------


def test_a_total_fetch_failure_applies_nothing_and_keeps_the_previous_data():
    seeded = MembershipExtension(
        coverage_end=date(2026, 7, 15),
        events=((date(2026, 7, 15), ("NEWA",), ()),),
        live_members=frozenset(_universe_at_coverage() | {"NEWA"}),
        live_as_of=LIVE_AS_OF,
    )
    apply_membership_extension(seeded)

    outcome = plan_refresh(
        upstream=None,
        spy=None,
        wikipedia=None,
        today=TODAY,
        previous=get_membership_extension(),
        fetch_warnings=("point-in-time history unavailable: boom",),
    )
    assert outcome.applied  # the carried-forward live layer is still real data
    assert outcome.n_dated_events == 1  # the previously fetched event, kept
    # Nothing was cleared: the previously applied data is still in force.
    assert membership_coverage_end() == date(2026, 7, 15)
    assert was_member("NEWA", date(2026, 7, 15))


def test_an_upstream_outage_costs_freshness_but_never_already_earned_coverage():
    # The regression this guards: rebuilding the extension around the
    # vendored baseline on a failed fetch would silently un-date every
    # event gained since, turning an outage into data loss.
    previous = MembershipExtension(
        coverage_end=date(2026, 9, 30),
        events=((date(2026, 9, 1), ("NEWA",), ()),),
    )
    spy, wiki = _live(_universe_at_coverage() | {"NEWA"}, {"NEWA": date(2026, 9, 1)})
    outcome = plan_refresh(upstream=None, spy=spy, wikipedia=wiki, today=TODAY, previous=previous)

    assert outcome.coverage_end == date(2026, 9, 30)
    assert (date(2026, 9, 1), ("NEWA",), ()) in outcome.extension.events
    apply_membership_extension(outcome.extension)
    assert membership_coverage_end() == date(2026, 9, 30)
    assert was_member("NEWA", date(2026, 9, 30))


def test_upstream_coverage_going_backwards_is_rejected():
    previous = MembershipExtension(coverage_end=date(2026, 9, 30), events=((date(2026, 9, 1), ("NEWA",), ()),))
    upstream = _upstream_from([(date(2026, 7, 15), ["OTHR"], [])])
    outcome = plan_refresh(upstream=upstream, spy=None, wikipedia=None, today=TODAY, previous=previous)

    assert any("earlier than the coverage already in force" in w for w in outcome.warnings)
    assert outcome.coverage_end == date(2026, 9, 30)
    assert all("OTHR" not in event[1] for event in outcome.extension.events)


def test_a_stale_live_layer_is_dropped_rather_than_quoted_forever():
    stale = MembershipExtension(
        coverage_end=MEMBERSHIP_DATA_AS_OF,
        live_members=frozenset(_universe_at_coverage() - {"AVB"}),
        live_as_of=TODAY - timedelta(days=LIVE_MEMBERSHIP_MAX_AGE_DAYS + 1),
    )
    outcome = plan_refresh(upstream=None, spy=None, wikipedia=None, today=TODAY, previous=stale)
    assert not outcome.applied
    assert outcome.live_as_of is None


def test_a_fresh_live_layer_survives_a_live_source_outage():
    recent = MembershipExtension(
        coverage_end=MEMBERSHIP_DATA_AS_OF,
        live_members=frozenset(_universe_at_coverage() - {"AVB"}),
        live_as_of=TODAY - timedelta(days=3),
    )
    outcome = plan_refresh(upstream=None, spy=None, wikipedia=None, today=TODAY, previous=recent)
    assert outcome.applied
    apply_membership_extension(outcome.extension)
    assert "AVB" not in get_live_membership()[0]


def test_upstream_supersedes_a_carried_live_dated_addition():
    # The live tier dated NEWA from Wikipedia; upstream later publishes the
    # same addition as a real dated event. The carried-forward provisional
    # copy must not survive alongside it.
    previous = MembershipExtension(
        coverage_end=MEMBERSHIP_DATA_AS_OF,
        events=((date(2026, 8, 5), ("NEWA",), ()),),
        live_members=frozenset(_universe_at_coverage() | {"NEWA"}),
        live_as_of=TODAY - timedelta(days=1),
    )
    upstream = _upstream_from([(date(2026, 8, 5), ["NEWA"], [])])
    outcome = plan_refresh(upstream=upstream, spy=None, wikipedia=None, today=TODAY, previous=previous)

    assert outcome.coverage_end == date(2026, 8, 5)
    assert outcome.extension.events == ((date(2026, 8, 5), ("NEWA",), ()),)


# --- Rename look-through for upstream additions ---------------------------


def test_an_upstream_addition_that_is_really_a_rename_gets_an_earliest_override():
    upstream = _upstream_from([(date(2026, 7, 15), ["NEWCO"], ["OLDCO"])])
    spy, wiki = _live(
        (_universe_at_coverage() - {"OLDCO"}) | {"NEWCO"},
        {"NEWCO": date(2004, 4, 23)},
    )
    outcome = plan_refresh(upstream=upstream, spy=spy, wikipedia=wiki, today=TODAY)
    apply_membership_extension(outcome.extension)

    assert earliest_membership_date("NEWCO") == date(2004, 4, 23)
    # ...so a long replay carries no false inclusion-bias warning.
    assert build_membership_warnings("NEWCO", [date(2022, 1, 4), date(2026, 7, 20)]) == []


def test_a_genuine_new_addition_keeps_its_real_date():
    joined = date(2026, 7, 15)
    upstream = _upstream_from([(joined, ["NEWA"], [])])
    spy, wiki = _live(_universe_at_coverage() | {"NEWA"}, {"NEWA": joined})
    outcome = plan_refresh(upstream=upstream, spy=spy, wikipedia=wiki, today=TODAY)
    apply_membership_extension(outcome.extension)

    assert earliest_membership_date("NEWA") == joined
    warnings = build_membership_warnings("NEWA", [date(2022, 1, 4), date(2026, 7, 20)])
    assert len(warnings) == 1
    assert "inclusion-biased" in warnings[0]


# --- The one invariant the whole design rests on --------------------------


def test_an_extension_may_never_reach_into_the_verified_window():
    with pytest.raises(PointInTimeUniverseError):
        apply_membership_extension(
            MembershipExtension(
                coverage_end=MEMBERSHIP_DATA_AS_OF,
                events=((date(2023, 3, 15), (), ("AAPL",)),),
            )
        )


def test_clearing_the_extension_restores_the_vendored_answers():
    apply_membership_extension(
        MembershipExtension(coverage_end=date(2026, 7, 15), events=((date(2026, 7, 15), ("NEWA",), ()),))
    )
    assert membership_coverage_end() == date(2026, 7, 15)
    clear_membership_extension()
    assert membership_coverage_end() == MEMBERSHIP_DATA_AS_OF
    assert get_membership_extension() is None
    assert earliest_membership_date("NEWA") is None


# --- Parsers, against the real files' actual shapes -----------------------

_SPY_ROWS = [
    ["Fund Name:", "State Street® SPDR® S&P 500® ETF Trust"],
    ["Ticker Symbol:", "SPY"],
    ["Holdings:", "As of 24-Aug-2026"],
    ["Name", "Ticker", "Identifier", "SEDOL", "Weight", "Sector", "Shares Held", "Local Currency"],
    ["NVIDIA CORP", "NVDA", "67066G104", "2379504", "7.658346", "-", "2.9E8", "USD"],
    ["BERKSHIRE HATHAWAY INC CL B", "BRK.B", "084670702", "2073390", "1.5", "-", "1.0E7", "USD"],
    ["US DOLLAR", "-", "999USDZ92", "-", "0.104298", "-", "8.39E8", "USD"],
    ["CONTRA HOLOGIC INCORPO", "2602335D", "436CVR021", "-", "3.0E-6", "-", "2578626.0", "USD"],
    ["Past performance is not a reliable indicator of future performance.", None, None],
]


def test_spy_workbook_parsing_keeps_equities_and_drops_cash_and_contra_lines():
    live = _parse_spy_workbook_rows(_SPY_ROWS)
    assert live.as_of == date(2026, 8, 24)
    assert live.members == frozenset({"NVDA", "BRK-B"})


def test_spy_workbook_without_an_as_of_line_is_refused_rather_than_dated_by_guess():
    rows = [row for row in _SPY_ROWS if not (row and row[0] == "Holdings:")]
    with pytest.raises(MembershipRefreshError, match="As of"):
        _parse_spy_workbook_rows(rows)


def test_spy_workbook_without_a_header_row_is_refused():
    rows = [row for row in _SPY_ROWS if not (row and row[0] == "Name")]
    with pytest.raises(MembershipRefreshError, match="header row"):
        _parse_spy_workbook_rows(rows)


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "", content: bytes = b""):
        self.status_code = status_code
        self.text = text
        self.content = content


class _FakeClient:
    def __init__(self, response: _FakeResponse):
        self._response = response

    def get(self, url: str) -> _FakeResponse:
        # The URL is irrelevant here: these tests exercise parsing and
        # status handling, not routing.
        del url
        return self._response


def test_wikipedia_constituents_parsing_reads_symbols_and_addition_dates():
    csv_text = (
        "Symbol,Security,GICS Sector,GICS Sub-Industry,Headquarters Location,Date added,CIK,Founded\n"
        "MMM,3M,Industrials,Industrial Conglomerates,\"Saint Paul, Minnesota\",1957-03-04,66740,1902\n"
        "BRK.B,Berkshire Hathaway,Financials,Multi-Sector Holdings,\"Omaha, Nebraska\",2010-02-16,1067983,1839\n"
        "NODT,No Date Co,Industrials,Widgets,\"Nowhere\",,1,1900\n"
    )
    live = fetch_wikipedia_constituents(_FakeClient(_FakeResponse(200, text=csv_text)), today=TODAY)
    assert live.members == frozenset({"MMM", "BRK-B", "NODT"})
    assert live.added_dates == {"MMM": date(1957, 3, 4), "BRK-B": date(2010, 2, 16)}
    assert live.as_of == TODAY


def test_wikipedia_constituents_rejects_a_response_that_is_not_the_expected_csv():
    with pytest.raises(MembershipRefreshError, match="Symbol"):
        fetch_wikipedia_constituents(_FakeClient(_FakeResponse(200, text="<html>nope</html>")), today=TODAY)


def test_a_non_200_response_is_an_error_not_a_silently_empty_universe():
    with pytest.raises(MembershipRefreshError, match="HTTP 503"):
        fetch_wikipedia_constituents(_FakeClient(_FakeResponse(503)), today=TODAY)
    with pytest.raises(MembershipRefreshError, match="HTTP 503"):
        fetch_spy_constituents(_FakeClient(_FakeResponse(503)))
