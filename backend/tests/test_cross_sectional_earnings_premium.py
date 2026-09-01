"""Unit tests for the scheduled earnings-announcement-premium family,
mirroring test_cross_sectional_pead.py's structure: synthetic fixtures for
all the pure math, no live network calls in CI.

The SEC EDGAR API shapes exercised here through recorded-shape fixtures
were verified LIVE on 2026-09-01 during the build:
  * submissions.filings.recent is parallel arrays keyed accessionNumber /
    filingDate / acceptanceDateTime / form / items.
  * submissions.filings.files is a list of
    {"name", "filingCount", "filingFrom", "filingTo"}, and each named chunk
    at https://data.sec.gov/submissions/<name> holds the SAME parallel-array
    shape. Measured on CIK 0000019617 (JPM): filings.recent was 26,083 rows
    covering only 2025-08-29..2026-08-31, with 69 older chunks -- which is
    the concrete reason this family paginates and cross_sectional_pead.py's
    recent-only fetch would have deleted the mega-cap banks from the early
    sample.

REAL-DATA EMPIRICAL CHECKS from the production run are documented in
comments at the bottom of this file; CI never hits EDGAR or yfinance.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

import app.services.research_lab.cross_sectional_earnings_premium as eap
from app.services.research_lab.cross_sectional import (
    DEFAULT_IMPUTED_DELISTING_RETURN,
)
from app.services.research_lab.cross_sectional_earnings_premium import (
    EAP_COST_SENSITIVITY_BPS,
    EAP_DAYS_AFTER,
    EAP_DAYS_BEFORE,
    EAP_FAMILY,
    EAP_LEG_WEIGHTINGS,
    EAP_N_TRIALS,
    EAP_PREDICTOR_LAG_DAYS,
    AnnouncementDay,
    CalendarFetchReport,
    EapConfig,
    EapSpec,
    TradedWindow,
    build_announcement_calendar,
    build_announcement_vol_basis,
    build_traded_windows,
    load_calendar_cache,
    measure_predictor_accuracy,
    net_daily_returns,
    predict_announcements,
    run_eap_backtest,
    run_eap_screening,
    save_calendar_cache,
    screen_eap_family,
    suppressed_by_actual_announcement,
)
from app.services.research_lab.cross_sectional_pead import EarningsEvent

# --- shared synthetic fixtures --------------------------------------------


def _frame(
    values_by_ticker: dict[str, list[float]], start: str = "2020-01-01"
) -> pd.DataFrame:
    n = len(next(iter(values_by_ticker.values())))
    return pd.DataFrame(values_by_ticker, index=pd.bdate_range(start, periods=n))


def _flat(n: int, value: float = 100.0) -> list[float]:
    return [value] * n


def _event(
    ticker: str,
    filing: date,
    acceptance_utc: str = "",
    accession: str = "0000000000-00-000000",
) -> EarningsEvent:
    return EarningsEvent(
        ticker=ticker,
        cik=123456,
        accession=accession,
        filing_date=filing,
        acceptance_utc=acceptance_utc,
    )


def _pre_open(ticker: str, day: date, accession: str = "a") -> EarningsEvent:
    """An announcement accepted at 13:00Z (08:00/09:00 ET), i.e. before the
    close, so day 0 is that same session."""
    return _event(ticker, day, f"{day.isoformat()}T13:00:00.000Z", accession)


def _all_members(index: pd.DatetimeIndex, tickers: list[str]) -> pd.DataFrame:
    return pd.DataFrame(True, index=index, columns=tickers)


def _spec(
    before: int = 1, after: int = 1, weighting: str = "equal"
) -> EapSpec:
    return EapSpec(
        pattern_id=f"t_b{before}_a{after}_{weighting}",
        family=eap.EAP_FAMILY_NAME,
        citation="test",
        days_before=before,
        days_after=after,
        leg_weighting=weighting,
    )


def _free_config() -> EapConfig:
    return EapConfig(cost_bps=0.0, financing_bps_per_year=0.0)


def _window(
    ticker: str, entry: int, exit_position: int, vol_basis: float = 0.02
) -> TradedWindow:
    return TradedWindow(
        ticker=ticker,
        predicted_position=entry + 1,
        predicted_date=date(2020, 1, 1),
        entry_position=entry,
        exit_position=exit_position,
        vol_basis=vol_basis,
    )


# --- family shape: exactly these 8, no more, no fewer ---------------------

EXPECTED_PATTERN_IDS = {
    "eap_b1_a1_equal",
    "eap_b1_a1_ann_vol",
    "eap_b1_a5_equal",
    "eap_b1_a5_ann_vol",
    "eap_b5_a1_equal",
    "eap_b5_a1_ann_vol",
    "eap_b5_a5_equal",
    "eap_b5_a5_ann_vol",
}


def test_family_is_exactly_8_definitions():
    assert len(EAP_FAMILY) == 8
    assert EAP_N_TRIALS == 8


def test_family_pattern_ids_are_exactly_the_expected_8_and_no_others():
    assert {s.pattern_id for s in EAP_FAMILY} == EXPECTED_PATTERN_IDS


def test_family_covers_all_three_axes_exactly_once():
    combos = {(s.days_before, s.days_after, s.leg_weighting) for s in EAP_FAMILY}
    assert combos == {
        (b, a, w)
        for b in EAP_DAYS_BEFORE
        for a in EAP_DAYS_AFTER
        for w in EAP_LEG_WEIGHTINGS
    }
    assert len(combos) == 8


def test_family_size_assertion_is_hard_not_documented():
    """The pre-declared size is asserted against the built list, so a drift
    is an import-time failure rather than a silent n_trials change."""
    original = eap.EAP_DAYS_BEFORE
    try:
        eap.EAP_DAYS_BEFORE = (1, 5, 10)
        with pytest.raises(AssertionError, match="not the pre-declared"):
            eap._build_eap_family()
    finally:
        eap.EAP_DAYS_BEFORE = original


def test_family_meets_the_dsr_floor():
    assert EAP_N_TRIALS >= 5  # deflated_sharpe.MIN_TRIALS_FOR_DSR


def test_every_spec_carries_the_verified_citations():
    for spec in EAP_FAMILY:
        assert spec.family == eap.EAP_FAMILY_NAME
        assert "Savor & Wilson" in spec.citation
        assert "10.1111/jofi.12361" in spec.citation
        assert "Lamont & Frazzini" in spec.citation
        assert "Barber, De George, Lehavy & Trueman" in spec.citation


def test_the_superseded_20_percent_draft_figure_is_never_quoted_as_the_result():
    """Guards the correction the 2026-09-01 verification pass forced: the
    published Savor & Wilson abstract says 9.9%, the December 2011 draft
    says 20% on an equal-weighted book, and the module must not present the
    draft number as the paper's finding."""
    doc = eap.__doc__ or ""
    assert "9.9%" in doc
    assert "superseded draft figure" in doc
    # Every mention of the draft's 20% is introduced BY the correction that
    # labels it superseded -- none of them precedes it.
    assert doc.index("CORRECTION TO THE BUILD BRIEF, #1") < doc.index("20%")
    # And it never reaches the machine-readable citation string, which is
    # what gets copied into every persisted cross_sectional_trial_results row.
    assert "20%" not in eap.EAP_CITATION
    assert "9.9" not in eap.EAP_CITATION  # no headline number in the citation


def test_the_module_records_that_the_risk_story_is_contested():
    """The build brief asserted the premium 'should not decay once known'
    because it is risk-based. Two of the three live explanations in the
    literature are inefficiency stories, so that premise is recorded as
    CONTESTED rather than relied on."""
    doc = eap.__doc__ or ""
    assert "CONTESTED" in doc
    assert "Ball & Kothari" in doc
    assert "limits to arbitrage" in doc.lower()


def test_cohen_et_al_is_not_miscounted_as_an_inefficiency_story():
    """Guards the correction the 2026-09-01 adversarial re-verification
    forced. Cohen, Dey, Lys & Sunder invoke limits to arbitrage to explain
    the premium's SURVIVAL while concluding the returns are "likely to
    represent compensation for announcement risk" -- so it is NOT an
    inefficiency-of-existence story, and the docstring must not tally it as
    one. Reinstating the old "two of those three" count would flip a claim
    the paper's own abstract contradicts."""
    doc = eap.__doc__ or ""
    # The old miscount survives ONLY inside the correction that disowns it --
    # never as a live claim. Same ordering guard the #1 correction uses for
    # the superseded 20% draft figure.
    label = "THIS PARAGRAPH WAS ITSELF CORRECTED ON RE-VERIFICATION"
    assert label in doc  # the correction is labelled, not silently applied
    assert doc.index(label) < doc.index("Two of those three")
    assert doc.count("Two of those three") == 1
    # The verbatim conclusion that makes it a risk-side paper is quoted.
    assert "compensation for announcement risk" in doc
    # And it is never listed among the inefficiency explanations.
    assert "Cohen et al. sit closer to Savor & Wilson" in doc


# --- EDGAR parsing (shapes verified live 2026-09-01, replayed here) -------


def test_parse_filing_rows_matches_the_verified_submissions_shape():
    rows = {
        "form": ["8-K", "10-Q", "8-K", "8-K/A", "8-K"],
        "items": ["2.02,9.01", "", "5.02", "2.02,9.01", "2.02"],
        "filingDate": [
            "2025-07-30",
            "2025-08-01",
            "2025-09-15",
            "2025-08-02",
            "2013-05-01",
        ],
        "acceptanceDateTime": [
            "2025-07-30T20:30:28.000Z",
            "2025-08-01T10:00:00.000Z",
            "2025-09-15T12:00:00.000Z",
            "2025-08-02T12:00:00.000Z",
            "2013-05-01T12:00:00.000Z",
        ],
        "accessionNumber": ["a-1", "a-2", "a-3", "a-4", "a-5"],
    }
    events, earliest = eap._parse_filing_rows(
        "AAPL", 320193, rows, date(2014, 6, 1), date(2026, 9, 1)
    )
    # Row 0 kept. Row 1 not an 8-K. Row 2 no 2.02. Row 3 is an 8-K/A, an
    # amendment, never the announcement. Row 4 predates the fetch window.
    assert [e.accession for e in events] == ["a-1"]
    # earliest reads EVERY form, including the out-of-window one -- that is
    # what proves EDGAR coverage rather than filing activity.
    assert earliest == date(2013, 5, 1)


def test_item_matching_is_against_the_comma_split_list_not_a_substring():
    rows = {
        "form": ["8-K"],
        "items": ["12.02"],
        "filingDate": ["2025-07-30"],
        "acceptanceDateTime": ["2025-07-30T20:30:28.000Z"],
        "accessionNumber": ["a-1"],
    }
    events, _ = eap._parse_filing_rows(
        "AAPL", 320193, rows, date(2014, 6, 1), date(2026, 9, 1)
    )
    assert events == []


def test_chunk_overlap_selects_only_the_ranges_that_matter():
    start, end = date(2016, 1, 1), date(2020, 1, 1)
    assert eap._chunk_overlaps(
        {"filingFrom": "2015-01-01", "filingTo": "2016-06-01"}, start, end
    )
    assert not eap._chunk_overlaps(
        {"filingFrom": "2010-01-01", "filingTo": "2011-01-01"}, start, end
    )
    assert not eap._chunk_overlaps(
        {"filingFrom": "2021-01-01", "filingTo": "2022-01-01"}, start, end
    )


def test_an_unparseable_chunk_range_is_fetched_not_skipped():
    """The conservative direction: skipping would silently drop real
    filings, while an unnecessary fetch only costs one request."""
    assert eap._chunk_overlaps({}, date(2016, 1, 1), date(2020, 1, 1))
    assert eap._chunk_overlaps(
        {"filingFrom": "not-a-date", "filingTo": "also-not"},
        date(2016, 1, 1),
        date(2020, 1, 1),
    )


def test_calendar_cache_round_trips(tmp_path):
    path = tmp_path / "cache.json"
    events = [
        _event("AAPL", date(2025, 7, 30), "2025-07-30T20:30:28.000Z", "a-1"),
        _event("MSFT", date(2025, 7, 29), "", "a-2"),
    ]
    report = CalendarFetchReport(
        n_tickers_requested=2,
        n_tickers_cik_resolved=2,
        n_tickers_fetched=2,
        n_chunks_fetched=7,
        n_tickers_coverage_starts_late=1,
        late_coverage_tickers=["MSFT"],
    )
    save_calendar_cache(events, report, date(2014, 6, 1), date(2026, 9, 1), path)
    loaded = load_calendar_cache(path)
    assert loaded is not None
    loaded_events, loaded_report, fetch_start, end = loaded
    assert loaded_events == events
    assert loaded_report.n_chunks_fetched == 7
    assert loaded_report.late_coverage_tickers == ["MSFT"]
    assert (fetch_start, end) == (date(2014, 6, 1), date(2026, 9, 1))


def test_missing_cache_returns_none(tmp_path):
    assert load_calendar_cache(tmp_path / "nope.json") is None


# --- the announcement calendar --------------------------------------------


def test_calendar_maps_events_to_day0_and_sorts_them():
    close = _frame({"AAA": _flat(60)})
    events = [
        _pre_open("AAA", close.index[30].date(), "a-2"),
        _pre_open("AAA", close.index[10].date(), "a-1"),
    ]
    calendar, rejected = build_announcement_calendar(close.index, events)
    assert [d.day0_position for d in calendar["AAA"]] == [10, 30]
    assert not rejected


def test_duplicate_filings_within_the_gap_are_one_announcement():
    """A re-filed or follow-up 2.02 must not put a phantom extra date on the
    calendar -- one year later that becomes a phantom extra PREDICTION."""
    close = _frame({"AAA": _flat(60)})
    events = [
        _pre_open("AAA", close.index[10].date(), "a-1"),
        _pre_open("AAA", close.index[12].date(), "a-2"),
    ]
    calendar, rejected = build_announcement_calendar(close.index, events)
    assert [d.day0_position for d in calendar["AAA"]] == [10]
    assert rejected == {"duplicate filing within gap": 1}


# --- the ex-ante predictor -------------------------------------------------


def test_each_announcement_generates_exactly_one_prediction_a_year_later():
    index = pd.bdate_range("2020-01-01", periods=900)
    day0 = 10
    calendar = {
        "AAA": [
            AnnouncementDay("AAA", day0, index[day0].date()),
        ]
    }
    predicted = predict_announcements(calendar, index)
    assert len(predicted["AAA"]) == 1
    row = predicted["AAA"][0]
    assert row.predicted_date >= index[day0].date() + timedelta(
        days=EAP_PREDICTOR_LAG_DAYS
    )
    assert row.source_position == day0


def test_the_364_day_lag_preserves_day_of_week():
    """52 weeks exactly. This is the entire reason 364 was chosen over 365,
    and earnings releases are scheduled on weekdays."""
    for start in (date(2020, 1, 6), date(2021, 3, 17), date(2022, 11, 3)):
        assert (start + timedelta(days=EAP_PREDICTOR_LAG_DAYS)).weekday() == (
            start.weekday()
        )


def test_a_prediction_is_always_known_before_the_position_it_justifies():
    """THE point-in-time guarantee: a prediction is generated by an
    announcement roughly a year earlier, so it can never read a filing that
    had not yet been made."""
    index = pd.bdate_range("2018-01-01", periods=1500)
    calendar = {
        "AAA": [AnnouncementDay("AAA", p, index[p].date()) for p in (10, 73, 136, 199)]
    }
    for row in predict_announcements(calendar, index)["AAA"]:
        assert row.known_from_position == row.source_position
        assert row.known_from_position < row.predicted_position


def test_predictions_landing_within_the_gap_collapse_to_one():
    index = pd.bdate_range("2018-01-01", periods=1500)
    # Two announcements two rows apart survive de-dup only if the calendar
    # is built by hand; their predictions land ~2 rows apart and must merge.
    calendar = {
        "AAA": [
            AnnouncementDay("AAA", 10, index[10].date()),
            AnnouncementDay("AAA", 12, index[12].date()),
        ]
    }
    assert len(predict_announcements(calendar, index)["AAA"]) == 1


def test_predictions_beyond_the_index_are_dropped_not_clamped():
    index = pd.bdate_range("2020-01-01", periods=60)
    calendar = {"AAA": [AnnouncementDay("AAA", 10, index[10].date())]}
    assert predict_announcements(calendar, index) == {}


# --- the slot-already-filled suppression ----------------------------------


def _prediction(index, predicted_position, source_position=0):
    return eap.PredictedAnnouncement(
        ticker="AAA",
        predicted_position=predicted_position,
        predicted_date=index[predicted_position].date(),
        source_position=source_position,
        source_date=index[source_position].date(),
        known_from_position=source_position,
    )


def test_a_firm_that_already_announced_this_quarter_is_suppressed():
    """Reporting a week EARLY than last year must not produce a second
    position days after the announcement it was aiming at."""
    index = pd.bdate_range("2020-01-01", periods=900)
    prediction = _prediction(index, 300)
    actual = [AnnouncementDay("AAA", 295, index[295].date())]
    assert suppressed_by_actual_announcement(prediction, actual, decision_position=298)


def test_a_prior_quarters_announcement_does_not_suppress():
    index = pd.bdate_range("2020-01-01", periods=900)
    prediction = _prediction(index, 300)
    # ~63 trading days earlier is the PREVIOUS quarter, far outside the
    # 30-calendar-day slot window.
    actual = [AnnouncementDay("AAA", 237, index[237].date())]
    assert not suppressed_by_actual_announcement(
        prediction, actual, decision_position=298
    )


def test_suppression_is_point_in_time_future_announcements_are_invisible():
    """An announcement that has not happened yet by the decision date must
    not suppress anything -- otherwise the gate would be reading the
    future."""
    index = pd.bdate_range("2020-01-01", periods=900)
    prediction = _prediction(index, 300)
    actual = [AnnouncementDay("AAA", 299, index[299].date())]
    assert not suppressed_by_actual_announcement(
        prediction, actual, decision_position=290
    )
    assert suppressed_by_actual_announcement(prediction, actual, decision_position=299)


# --- the announcement-volatility basis ------------------------------------


def test_the_vol_basis_is_the_mean_absolute_excess_announcement_move():
    n = 200
    prices = _flat(n)
    # The (-1,+1) window spans the SESSIONS 49, 50 and 51, so its cumulative
    # return is anchored at close(48) -> close(51). Prices 48..50 are given
    # DISTINCT values on purpose: with a flat run-up every candidate anchor
    # returns the same number and the test cannot tell a correct
    # three-session window from a two-session close(49) -> close(51) one.
    prices[49] = 101.0
    prices[50] = 102.0
    for i in range(51, n):
        prices[i] = 110.0
    close = _frame({"AAA": prices})
    bench = pd.Series(_flat(n), index=close.index)
    calendar = {"AAA": [AnnouncementDay("AAA", 50, close.index[50].date())]}
    basis = build_announcement_vol_basis(close, bench, calendar)
    stamp, value = basis["AAA"][0]
    assert stamp == 51  # stamped at the window CLOSE, not at day 0
    # close(48)=100 -> close(51)=110.
    assert value == pytest.approx(0.10)
    # And explicitly NOT the two-session close(49)=101 -> close(51)=110 read,
    # which is the off-by-one this window is easiest to get wrong.
    assert value != pytest.approx(110.0 / 101.0 - 1.0)


def test_the_vol_basis_is_in_excess_of_the_benchmark():
    """A stock that moved exactly with the market at its announcement has
    no firm-specific announcement risk to be paid for."""
    n = 200
    prices = _flat(n)
    bench_values = _flat(n)
    for i in range(51, n):
        prices[i] = 110.0
        bench_values[i] = 110.0
    close = _frame({"AAA": prices})
    bench = pd.Series(bench_values, index=close.index)
    calendar = {"AAA": [AnnouncementDay("AAA", 50, close.index[50].date())]}
    basis = build_announcement_vol_basis(close, bench, calendar)
    assert basis["AAA"][0][1] == pytest.approx(0.0, abs=1e-12)


def test_the_vol_basis_is_a_magnitude_so_a_crash_and_a_rally_weigh_the_same():
    """It is a RISK measure, not a directional signal -- the sign of a past
    announcement must never reach the weights."""
    n = 200
    up, down = _flat(n), _flat(n)
    for i in range(51, n):
        up[i], down[i] = 110.0, 90.0
    bench = pd.Series(_flat(n), index=_frame({"X": up}).index)
    calendar = {
        "UP": [AnnouncementDay("UP", 50, bench.index[50].date())],
        "DN": [AnnouncementDay("DN", 50, bench.index[50].date())],
    }
    basis = build_announcement_vol_basis(_frame({"UP": up, "DN": down}), bench, calendar)
    assert basis["UP"][0][1] == pytest.approx(basis["DN"][0][1])


def test_basis_as_of_is_point_in_time_and_respects_the_minimum_sample():
    rows = [(10, 0.01), (20, 0.02), (30, 0.03), (40, 0.04)]
    # Fewer than min_obs completed windows -> no usable basis.
    assert np.isnan(eap._basis_as_of(rows, 25, min_obs=4))
    # At row 40 the fourth window has closed; the newest value wins.
    assert eap._basis_as_of(rows, 40, min_obs=4) == pytest.approx(0.04)
    # A future window is invisible.
    assert eap._basis_as_of(rows, 39, min_obs=3) == pytest.approx(0.03)


# --- traded-window construction and its gates -----------------------------


def _calendar_and_predictions(index, positions, ticker="AAA"):
    calendar = {ticker: [AnnouncementDay(ticker, p, index[p].date()) for p in positions]}
    return calendar, predict_announcements(calendar, index)


def test_entry_and_exit_rows_come_only_from_the_prediction():
    index = pd.bdate_range("2018-01-01", periods=1500)
    close = pd.DataFrame(100.0, index=index, columns=["AAA"])
    calendar, predicted = _calendar_and_predictions(index, [10, 73, 136, 199, 262])
    basis = {"AAA": [(p, 0.02) for p in (10, 73, 136, 199, 262)]}
    windows, counts = build_traded_windows(
        close,
        calendar,
        predicted,
        basis,
        index[0].date(),
        index[-1].date(),
        days_before=5,
        days_after=3,
        membership=_all_members(index, ["AAA"]),
    )
    assert windows
    for window in windows:
        assert window.entry_position == window.predicted_position - 5 - 1
        assert window.exit_position == window.predicted_position + 3
    assert counts.n_traded == len(windows)


def test_a_firm_with_too_little_history_is_never_traded():
    """EAP_MIN_PRIOR_ANNOUNCEMENTS: a predictor built from one or two
    observed announcements is not a calendar."""
    index = pd.bdate_range("2018-01-01", periods=1500)
    close = pd.DataFrame(100.0, index=index, columns=["AAA"])
    calendar, predicted = _calendar_and_predictions(index, [10, 73])
    basis = {"AAA": [(p, 0.02) for p in (10, 73)]}
    windows, counts = build_traded_windows(
        close,
        calendar,
        predicted,
        basis,
        index[0].date(),
        index[-1].date(),
        days_before=1,
        days_after=1,
        membership=_all_members(index, ["AAA"]),
    )
    assert windows == []
    assert counts.n_thin_history > 0


def test_a_non_member_at_entry_is_gated_out_and_counted():
    index = pd.bdate_range("2018-01-01", periods=1500)
    close = pd.DataFrame(100.0, index=index, columns=["AAA"])
    positions = [10, 73, 136, 199, 262]
    calendar, predicted = _calendar_and_predictions(index, positions)
    basis = {"AAA": [(p, 0.02) for p in positions]}
    membership = pd.DataFrame(False, index=index, columns=["AAA"])
    windows, counts = build_traded_windows(
        close,
        calendar,
        predicted,
        basis,
        index[0].date(),
        index[-1].date(),
        days_before=1,
        days_after=1,
        membership=membership,
    )
    assert windows == []
    assert counts.n_not_member > 0


def test_a_missing_vol_basis_gates_every_spec_uniformly():
    """The gate is applied to equal-weighted specs too, so all eight specs
    trade the IDENTICAL population and differ only in window and weights."""
    index = pd.bdate_range("2018-01-01", periods=1500)
    close = pd.DataFrame(100.0, index=index, columns=["AAA"])
    positions = [10, 73, 136, 199, 262]
    calendar, predicted = _calendar_and_predictions(index, positions)
    windows, counts = build_traded_windows(
        close,
        calendar,
        predicted,
        {},  # no basis for anyone
        index[0].date(),
        index[-1].date(),
        days_before=1,
        days_after=1,
        membership=_all_members(index, ["AAA"]),
    )
    assert windows == []
    assert counts.n_no_vol_basis > 0


def test_caught_actual_is_a_diagnostic_and_never_a_filter():
    """A window that misses the real announcement is still traded -- the
    family is ex ante, so it cannot know it missed. The miss is COUNTED."""
    index = pd.bdate_range("2018-01-01", periods=1500)
    close = pd.DataFrame(100.0, index=index, columns=["AAA"])
    positions = [10, 73, 136, 199, 262]
    calendar, predicted = _calendar_and_predictions(index, positions)
    basis = {"AAA": [(p, 0.02) for p in positions]}
    windows, counts = build_traded_windows(
        close,
        calendar,
        predicted,
        basis,
        index[0].date(),
        index[-1].date(),
        days_before=1,
        days_after=1,
        membership=_all_members(index, ["AAA"]),
    )
    # Nothing was filtered on whether the announcement actually arrived.
    assert counts.n_traded == len(windows)
    assert counts.n_caught_actual <= counts.n_traded
    # The two assertions above are NOT sufficient on their own: if
    # caught_actual ever became a filter, n_traded and len(windows) would
    # fall to zero TOGETHER and both would still pass. The guard that
    # actually bites is that this fixture trades windows which caught
    # NOTHING -- its predictions land a year after the last real
    # announcement, so every one of them misses, and every one is traded.
    assert counts.n_caught_actual == 0
    assert counts.n_traded == 4


# --- the replay ------------------------------------------------------------


def test_long_minus_short_is_the_daily_return():
    n = 40
    close = _frame(
        {"AAA": [100.0 * (1.02**i) for i in range(n)], "BBB": _flat(n)}
    )
    windows = [_window("AAA", 5, 15)]
    result = run_eap_backtest(
        close, windows, _all_members(close.index, ["AAA", "BBB"]), _spec(), _free_config()
    )
    assert result.status == "ok"
    realized = result.gross_daily_returns.iloc[:10]
    assert np.allclose(realized.to_numpy(), 0.02, atol=1e-12)


def test_the_short_leg_is_the_rest_of_the_universe():
    """Not a ranked leg: every eligible member that is not currently an
    announcer, equal-weighted."""
    n = 40
    close = _frame(
        {
            "AAA": _flat(n),
            "BBB": [100.0 * (1.10**i) for i in range(n)],
            "CCC": [100.0 * (0.90**i) for i in range(n)],
        }
    )
    windows = [_window("AAA", 5, 15)]
    result = run_eap_backtest(
        close,
        windows,
        _all_members(close.index, ["AAA", "BBB", "CCC"]),
        _spec(),
        _free_config(),
    )
    # Long AAA (0%), short the equal-weighted mean of BBB (+10%) and CCC
    # (-10%), which is 0% -- so the book is flat, not +10% or -10%.
    assert result.gross_daily_returns.iloc[0] == pytest.approx(0.0, abs=1e-12)
    assert result.mean_short_leg_size == pytest.approx(2.0)


def test_a_day_with_no_announcer_is_flat_by_design_and_counted():
    n = 40
    close = _frame({"AAA": _flat(n), "BBB": [100.0 * (1.05**i) for i in range(n)]})
    windows = [_window("AAA", 5, 8)]
    result = run_eap_backtest(
        close, windows, _all_members(close.index, ["AAA", "BBB"]), _spec(), _free_config()
    )
    # After AAA's window closes the long leg is empty: flat, never a naked
    # short of the universe.
    assert result.n_one_sided_days > 0
    tail = result.gross_daily_returns.iloc[result.n_invested_days :]
    assert (tail == 0.0).all()


def test_the_position_spans_exactly_entry_plus_one_through_exit():
    n = 60
    close = _frame({"AAA": [100.0 * (1.02**i) for i in range(n)], "BBB": _flat(n)})
    windows = [_window("AAA", 5, 12)]
    result = run_eap_backtest(
        close, windows, _all_members(close.index, ["AAA", "BBB"]), _spec(), _free_config()
    )
    assert result.n_invested_days == 12 - 5


def test_turnover_is_recorded_so_the_cost_ladder_shares_one_position_path():
    n = 60
    close = _frame({"AAA": _flat(n), "BBB": _flat(n)})
    windows = [_window("AAA", 5, 12)]
    result = run_eap_backtest(
        close, windows, _all_members(close.index, ["AAA", "BBB"]), _spec(), EapConfig()
    )
    assert result.daily_turnover.sum() > 0.0
    # Every cost level is derived from the SAME stored gross series.
    for level in EAP_COST_SENSITIVITY_BPS:
        net = net_daily_returns(result, level, 0.0)
        assert len(net) == len(result.gross_daily_returns)


def test_the_turnover_decomposition_reconciles_to_the_turnover_it_explains():
    """A decomposition that does not sum back to the number it explains is
    worse than none -- this one decides whether the cost that kills the
    family is real trading or an accounting artifact, so it has to add up."""
    n = 120
    rng = np.random.default_rng(7)
    close = _frame(
        {
            f"T{i}": list(100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.01, n)))
            for i in range(8)
        }
    )
    windows = [
        _window("T0", 5, 12),
        _window("T1", 8, 16),
        _window("T2", 20, 28),
        _window("T0", 40, 48),
    ]
    result = run_eap_backtest(
        close, windows, _all_members(close.index, list(close.columns)), _spec(), EapConfig()
    )
    assert set(result.turnover_decomposition) == {
        "long_inout",
        "long_drift",
        "short_inout",
        "short_drift",
        "flat_unwind",
    }
    # Buckets are means over EVERY day of the series and must sum exactly to
    # the mean turnover they explain -- including the flat-unwind turnover on
    # one-sided days, which is charged and so must not be an unexplained
    # residual.
    assert sum(result.turnover_decomposition.values()) == pytest.approx(
        result.daily_turnover.mean(), rel=1e-9
    )
    assert result.turnover_decomposition["flat_unwind"] > 0.0


def test_higher_cost_never_produces_a_higher_net_return():
    n = 60
    close = _frame({"AAA": _flat(n), "BBB": _flat(n)})
    windows = [_window("AAA", 5, 12)]
    result = run_eap_backtest(
        close, windows, _all_members(close.index, ["AAA", "BBB"]), _spec(), EapConfig()
    )
    totals = [net_daily_returns(result, lvl, 0.0).sum() for lvl in (0.0, 2.0, 5.0, 10.0)]
    assert totals == sorted(totals, reverse=True)


def test_zero_cost_net_equals_gross():
    n = 60
    close = _frame({"AAA": _flat(n), "BBB": _flat(n)})
    windows = [_window("AAA", 5, 12)]
    result = run_eap_backtest(
        close, windows, _all_members(close.index, ["AAA", "BBB"]), _spec(), _free_config()
    )
    assert np.allclose(
        net_daily_returns(result, 0.0, 0.0).to_numpy(),
        result.gross_daily_returns.to_numpy(),
    )


def test_ann_vol_weighting_is_proportional_to_risk_not_inverse_to_it():
    """Savor & Wilson's mechanism is compensation for risk BORNE, so a
    higher announcement-window volatility must earn a LARGER weight. This
    is the opposite of a generic inverse-vol scheme."""
    n = 40
    close = _frame(
        {
            "LOWVOL": [100.0 * (1.10**i) for i in range(n)],
            "HIGHVOL": [100.0 * (1.20**i) for i in range(n)],
            "SHORTY": _flat(n),
        }
    )
    windows = [
        _window("LOWVOL", 5, 15, vol_basis=0.01),
        _window("HIGHVOL", 5, 15, vol_basis=0.03),
    ]
    members = _all_members(close.index, ["LOWVOL", "HIGHVOL", "SHORTY"])
    equal = run_eap_backtest(close, windows, members, _spec(), _free_config())
    weighted = run_eap_backtest(
        close, windows, members, _spec(weighting="ann_vol"), _free_config()
    )
    # Equal weighting gives (10+20)/2 = 15%; risk-proportional weighting
    # tilts toward the 20% name, so it must be strictly higher.
    assert equal.gross_daily_returns.iloc[0] == pytest.approx(0.15)
    assert weighted.gross_daily_returns.iloc[0] > equal.gross_daily_returns.iloc[0]


def test_delisting_mid_hold_is_charged_the_shumway_return():
    n = 40
    values = _flat(n)
    for i in range(10, n):
        values[i] = np.nan
    close = _frame({"AAA": values, "BBB": _flat(n)})
    windows = [_window("AAA", 5, 20)]
    result = run_eap_backtest(
        close,
        windows,
        _all_members(close.index, ["AAA", "BBB"]),
        _spec(),
        EapConfig(cost_bps=0.0),
    )
    assert result.n_windows_delisted_mid_hold == 1
    assert result.gross_daily_returns.min() == pytest.approx(
        DEFAULT_IMPUTED_DELISTING_RETURN
    )


def test_delisting_imputation_can_be_turned_off():
    n = 40
    values = _flat(n)
    for i in range(10, n):
        values[i] = np.nan
    close = _frame({"AAA": values, "BBB": _flat(n)})
    windows = [_window("AAA", 5, 20)]
    result = run_eap_backtest(
        close,
        windows,
        _all_members(close.index, ["AAA", "BBB"]),
        _spec(),
        EapConfig(cost_bps=0.0, impute_delisting_returns=False),
    )
    assert result.n_windows_delisted_mid_hold == 0
    assert result.gross_daily_returns.min() > DEFAULT_IMPUTED_DELISTING_RETURN


def test_no_windows_is_a_status_not_a_crash():
    close = _frame({"AAA": _flat(30)})
    result = run_eap_backtest(
        close, [], _all_members(close.index, ["AAA"]), _spec(), _free_config()
    )
    assert result.status == "no_windows"
    assert result.gross_daily_returns.empty


def test_non_members_are_excluded_from_the_short_leg():
    n = 40
    close = _frame({"AAA": _flat(n), "BBB": [100.0 * (1.10**i) for i in range(n)]})
    members = _all_members(close.index, ["AAA", "BBB"])
    members["BBB"] = False
    windows = [_window("AAA", 5, 15)]
    result = run_eap_backtest(close, windows, members, _spec(), _free_config())
    # BBB is not a member, so there is no short leg at all -> one-sided.
    assert result.n_invested_days == 0
    assert result.n_one_sided_days > 0


# --- predictor accuracy ----------------------------------------------------


def test_a_perfectly_periodic_filer_is_predicted_with_zero_error():
    """Ground truth: a firm that announces exactly 364 days apart every
    time must be predicted exactly, which is what makes a non-zero error on
    real data a statement about real filing behaviour rather than a bug."""
    index = pd.bdate_range("2018-01-03", periods=2200)
    first = index[10].date()
    positions = []
    for k in range(8):
        target = first + timedelta(days=91 * k)
        pos = eap._first_row_at_or_after(index, target)
        if pos is not None:
            positions.append(pos)
    # Build a calendar whose year-apart pairs are exactly 364 days apart.
    dates = [first + timedelta(days=364 * y + 91 * q) for y in range(3) for q in range(4)]
    calendar = {
        "AAA": [
            AnnouncementDay("AAA", p, index[p].date())
            for p in sorted(
                {
                    eap._first_row_at_or_after(index, d)
                    for d in dates
                    if eap._first_row_at_or_after(index, d) is not None
                }
            )
        ]
    }
    accuracy = measure_predictor_accuracy(calendar, index, EAP_PREDICTOR_LAG_DAYS)
    assert accuracy.n_matched > 0
    assert accuracy.median_abs_error_days == pytest.approx(0.0)
    assert accuracy.hit_rate_within[1] == pytest.approx(1.0)


def test_predictor_accuracy_reports_unmatched_predictions_rather_than_hiding_them():
    """A firm that stops announcing still generates a prediction; that
    prediction matched nothing and must be counted, not dropped."""
    index = pd.bdate_range("2018-01-01", periods=2200)
    calendar = {
        "AAA": [AnnouncementDay("AAA", p, index[p].date()) for p in (10, 73, 136, 199)]
    }
    accuracy = measure_predictor_accuracy(calendar, index, EAP_PREDICTOR_LAG_DAYS)
    assert accuracy.n_predictions == 4
    # Every prediction lands ~a year later, where this firm never announced.
    assert accuracy.unmatched_fraction == pytest.approx(1.0)


# --- screening / DSR -------------------------------------------------------


def _synthetic_panel(n_tickers: int = 12, n_days: int = 1600, seed: int = 3):
    rng = np.random.default_rng(seed)
    close = _frame(
        {
            f"T{i}": list(100.0 * np.cumprod(1.0 + rng.normal(0.0002, 0.015, n_days)))
            for i in range(n_tickers)
        },
        start="2018-01-01",
    )
    bench = pd.Series(
        100.0 * np.cumprod(1.0 + rng.normal(0.0002, 0.008, n_days)), index=close.index
    )
    events = []
    for i in range(n_tickers):
        # ~quarterly filings, staggered per ticker.
        for q in range(24):
            row = 15 + i + q * 63
            if row >= n_days - 10:
                continue
            filing = close.index[row].date()
            events.append(_pre_open(f"T{i}", filing, accession=f"t{i}-q{q}"))
    return close, bench, events


def test_screening_uses_the_full_pre_declared_family_as_n_trials():
    close, bench, events = _synthetic_panel()
    membership = _all_members(close.index, list(close.columns))
    results, calendar, _rejected, placebo = screen_eap_family(
        close,
        bench,
        events,
        membership,
        close.index[400].date(),
        close.index[-1].date(),
        _free_config(),
    )
    assert {r.pattern_id for r in results} == EXPECTED_PATTERN_IDS
    for r in results:
        assert r.deflated_sharpe.n_trials == EAP_N_TRIALS
        assert r.deflated_sharpe.dsr_floor_met  # 8 >= MIN_TRIALS_FOR_DSR
        assert 0.0 <= r.invested_fraction <= 1.0
        assert 0.0 <= r.caught_actual_fraction <= 1.0
        assert set(r.cost_sensitivity_sharpe) == set(EAP_COST_SENSITIVITY_BPS)
    # The placebo control runs for every spec, always.
    assert set(placebo) == EXPECTED_PATTERN_IDS
    assert calendar


def test_all_eight_specs_trade_the_same_population_size_per_window_pair():
    """The uniform gating means two specs sharing (days_before, days_after)
    differ ONLY in weights, so their traded-window counts must match
    exactly -- otherwise the sigma_SR feeding the DSR would be measuring
    universe differences rather than spec differences."""
    close, bench, events = _synthetic_panel()
    membership = _all_members(close.index, list(close.columns))
    results, _c, _r, _p = screen_eap_family(
        close,
        bench,
        events,
        membership,
        close.index[400].date(),
        close.index[-1].date(),
        _free_config(),
    )
    by_window: dict[tuple[int, int], set[int]] = {}
    for r in results:
        by_window.setdefault((r.days_before, r.days_after), set()).add(
            r.n_windows_traded
        )
    for counts in by_window.values():
        assert len(counts) == 1


def test_screening_returns_nothing_when_there_are_no_events():
    close = _frame({"AAA": _flat(400)})
    bench = pd.Series(_flat(400), index=close.index)
    results, _c, _r, _p = screen_eap_family(
        close,
        bench,
        [],
        _all_members(close.index, ["AAA"]),
        close.index[0].date(),
        close.index[-1].date(),
        _free_config(),
    )
    assert results == []


# --- the production entry point -------------------------------------------


def test_screening_start_before_membership_coverage_fails_loudly():
    with pytest.raises(ValueError, match="predates point-in-time membership"):
        run_eap_screening(date(2010, 1, 1), date(2020, 1, 1))


def test_screening_fails_loudly_when_the_benchmark_resolves_no_data():
    class _NoBenchmarkProvider:
        def get_daily_ohlcv(self, tickers, start, end):
            if tickers == ["SPY"]:
                return {}, ["SPY"]
            n = 400
            idx = pd.bdate_range("2019-06-01", periods=n)
            frame = pd.DataFrame({t: [100.0] * n for t in tickers}, index=idx)
            return {"close": frame, "open": frame, "volume": frame}, []

    events = [_pre_open("AAPL", date(2020, 3, 2))]
    with pytest.raises(ValueError, match="benchmark resolved no price data"):
        run_eap_screening(
            date(2020, 1, 1),
            date(2021, 1, 1),
            provider=_NoBenchmarkProvider(),
            events=events,
            fetch_report=CalendarFetchReport(n_tickers_requested=1),
        )


def test_cost_disclosure_names_its_own_numbers_and_their_source():
    class _Provider:
        def get_daily_ohlcv(self, tickers, start, end):
            if not tickers:
                return {}, []
            n = 400
            idx = pd.bdate_range("2019-06-01", periods=n)
            frame = pd.DataFrame({t: [100.0] * n for t in tickers}, index=idx)
            return {"close": frame, "open": frame, "volume": frame}, []

    summary = run_eap_screening(
        date(2020, 1, 1),
        date(2021, 1, 1),
        provider=_Provider(),
        events=[],
        fetch_report=CalendarFetchReport(n_tickers_requested=0),
    )
    assert "edge_cost_reaudit_corrected_PREREGISTRATION" in summary.cost_disclosure
    assert "DISCLOSED OPTIMISM" in summary.cost_disclosure
    assert "TURNOVER-HEAVY BY CONSTRUCTION" in summary.cost_disclosure


def test_the_cost_ladder_is_the_projects_own_sourced_calibration():
    """Adopted verbatim from edge_cost_reaudit_corrected_PREREGISTRATION.txt
    section 2 rather than re-derived: 1.0 tight bound, 2.0 best estimate for
    an equal-weighted S&P 500 book, 3.5 conservative bound, 5.0 the existing
    control rate and this family's headline."""
    assert EAP_COST_SENSITIVITY_BPS == (0.0, 1.0, 2.0, 3.5, 5.0)
    assert EapConfig().cost_bps == 5.0


# ===========================================================================
# REAL-DATA EMPIRICAL CHECKS -- run live during the build, recorded here
# ===========================================================================
# These are NOT executed in CI (they need SEC EDGAR and yfinance). They are
# the live measurements the 2026-09-01 production run made, kept next to the
# code so a later reader can re-run them and diff.
#
# 1. THE EDGAR FETCH (live, 12.8 min, 0 failures). 768 point-in-time tickers
#    requested; 606 resolved a CIK; 631 filings.files chunks paginated;
#    29,199 Item 2.02 filings returned, de-duplicated to 28,696 announcements
#    across 603 tickers (503 dropped as re-files within 5 trading rows),
#    median 49 announcements per ticker.
#    THE 162 UNRESOLVED TICKERS ARE THE HEADLINE DATA LIMITATION, not a bug:
#    SEC's company_tickers.json lists only CURRENT registrants, so the
#    acquired and renamed names (AABA, ABC, ABMD, AET, AGN, ALXN, ANTM, ATVI,
#    ...) resolve to nothing. Coverage is therefore time-trended: ~390 of
#    ~504 real index members represented in early 2016 against ~501 of 503 in
#    mid-2026.
#
# 2. PREDICTOR ACCURACY (26,199 ex-ante predictions over the formation
#    window). The 364-day lag hits the EXACT trading day 46.8% of the time
#    against 9.4% for a 365-day lag -- the day-of-week rationale for 364 is
#    confirmed empirically, not assumed. Median absolute error 1.0 trading
#    day; 92.2% land within +/-5; 0.5% match no real announcement at all.
#    Mean SIGNED error +1.16 days: firms drift later year over year.
#    Spot check, AAPL's last six quarters: predicted 2025-05-02, 2025-08-01,
#    2025-10-31, 2026-01-30, 2026-05-01, 2026-07-31 -- all six EXACTLY equal
#    to its six actual day-0 dates, each from a source announcement 364 days
#    earlier.
#
# 3. THE PRICE PANEL IS REAL (yfinance, auto_adjust=True), 3,081 trading rows
#    x 603 tickers, 2014-06-02..2026-08-31, 0 tickers missing. Spot values on
#    2020-01-02: AAPL 72.27, MSFT 151.54, JPM 117.90, SPY 296.13 -- all
#    split/dividend-adjusted, which is why they sit below the raw closes of
#    that date.
#
# 4. THE RESULT IS AN HONEST NEGATIVE. All eight specs have NEGATIVE net
#    Sharpe at the declared 5.0bp headline; best is eap_b5_a1_ann_vol at
#    -0.231, whose DSR of 0.044 against n_trials=8 is far below this
#    project's 0.50 floor. Four of eight are POSITIVE gross (+0.116..+0.202),
#    all of them the 5-day-before specs, and they clear their own placebo on
#    a gross-vs-gross comparison by +0.11..+0.24 -- but mean daily L1
#    turnover of 0.39-0.96 (98-242 annualized) means cost erases the entire
#    edge by 2.0bp, this project's own sourced best estimate for the
#    universe. The four 1-day-before specs are negative gross AND lose to
#    their placebo, so the grid contradicts itself.
#
# 5. THE COST IS NOT AN ACCOUNTING ARTIFACT -- checked because it decides the
#    verdict. Turnover decomposes (eap_b5_a1_ann_vol, mean daily L1 0.5177)
#    into long_inout 0.1672 + long_drift 0.1595 + short_inout 0.1653 +
#    short_drift 0.0219 + flat_unwind 0.0037. Only short_drift (4.2%) is pure
#    renormalization of the universe short. Even zeroing BOTH design-
#    dependent buckets (long_drift + short_drift, ~35%) leaves ~0.34 daily
#    turnover, and the conclusion is unchanged.
#
# See data/research_runs/earnings_announcement_premium_2026-09-01.txt for the
# full run report and cross_sectional_trial_results (family_key=
# 'earnings_announcement_premium', run_tag=
# 'earnings_announcement_premium_2026-09-01') for the authoritative per-spec
# numbers.
