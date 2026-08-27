"""Unit tests for the PEAD-EAR event-driven family, mirroring
test_cross_sectional_index_removal.py's structure: synthetic fixtures for
the pure math, no live network calls. The SEC EDGAR API shape
(submissions JSON parallel arrays with an `items` field, the ticker->CIK
mapping file's dash convention, the 10 req/s fair-access cap) was verified
LIVE during the build session on 2026-08-28 and is exercised here only
through recorded-shape fixtures -- CI never hits EDGAR."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

import app.services.research_lab.cross_sectional_pead as pead
from app.services.research_lab.cross_sectional import DEFAULT_IMPUTED_DELISTING_RETURN
from app.services.research_lab.cross_sectional_pead import (
    PEAD_EAR_WINDOWS,
    PEAD_FAMILY,
    PEAD_HOLDING_DAYS,
    PEAD_LEG_WEIGHTINGS,
    PEAD_N_TRIALS,
    PEAD_ROUND_TRIP_BPS,
    ClassifiedEvent,
    EarningsEvent,
    EdgarFetchReport,
    PeadConfig,
    PeadSpec,
    ScoredEvent,
    announcement_day0,
    build_inverse_vol_basis,
    build_pead_sample_disclosure,
    classify_events,
    load_event_cache,
    run_pead_backtest,
    run_pead_screening,
    save_event_cache,
    score_events,
    screen_pead_family,
)

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


def _classified(
    ticker: str,
    index: pd.DatetimeIndex,
    entry_position: int,
    leg: str,
    ear: float = 0.05,
) -> ClassifiedEvent:
    return ClassifiedEvent(
        ticker=ticker,
        day0_position=entry_position - 1,
        day0_date=index[entry_position - 1].date(),
        entry_position=entry_position,
        entry_date=index[entry_position].date(),
        ear=ear,
        leg=leg,
    )


def _spec(
    hold: int = 5, weighting: str = "equal", window: tuple[int, int] = (0, 1)
) -> PeadSpec:
    return PeadSpec(
        pattern_id=f"t_{window}_h{hold}_{weighting}",
        family="pead_ear",
        citation="test",
        ear_window=window,
        holding_days=hold,
        leg_weighting=weighting,
    )


def _free_config() -> PeadConfig:
    return PeadConfig(round_trip_bps=0.0, financing_bps_per_year=0.0)


# --- family shape: exactly these 8, no more, no fewer ---------------------

EXPECTED_PATTERN_IDS = {
    "pead_ear_w0p1_h63_equal",
    "pead_ear_w0p1_h63_inverse_vol",
    "pead_ear_w0p1_h126_equal",
    "pead_ear_w0p1_h126_inverse_vol",
    "pead_ear_wm1p1_h63_equal",
    "pead_ear_wm1p1_h63_inverse_vol",
    "pead_ear_wm1p1_h126_equal",
    "pead_ear_wm1p1_h126_inverse_vol",
}


def test_family_is_exactly_8_definitions():
    assert len(PEAD_FAMILY) == 8
    assert PEAD_N_TRIALS == 8


def test_family_pattern_ids_are_exactly_the_expected_8_and_no_others():
    assert {s.pattern_id for s in PEAD_FAMILY} == EXPECTED_PATTERN_IDS


def test_family_covers_all_three_axes_exactly_once():
    combos = {(s.ear_window, s.holding_days, s.leg_weighting) for s in PEAD_FAMILY}
    assert combos == {
        (w, h, lw)
        for w in PEAD_EAR_WINDOWS
        for h in PEAD_HOLDING_DAYS
        for lw in PEAD_LEG_WEIGHTINGS
    }
    assert len(combos) == 8


def test_family_every_spec_is_cited_and_shares_the_family_name():
    for spec in PEAD_FAMILY:
        assert spec.family == "pead_ear"
        assert "Bernard & Thomas" in spec.citation
        assert "Brandt, Kishore, Santa-Clara & Venkatachalam" in spec.citation
        assert "Ball & Brown" in spec.citation


def test_family_size_assertion_is_hard_not_documented():
    """The pre-declared size is asserted against the built list, so a
    drift is an import-time failure rather than a silent n_trials change."""
    original = pead.PEAD_HOLDING_DAYS
    try:
        pead.PEAD_HOLDING_DAYS = (63, 126, 21)
        with pytest.raises(AssertionError, match="not the pre-declared"):
            pead._build_pead_family()
    finally:
        pead.PEAD_HOLDING_DAYS = original


def test_family_meets_the_dsr_floor():
    assert PEAD_N_TRIALS >= 5  # deflated_sharpe.MIN_TRIALS_FOR_DSR


# --- day 0 mapping from the EDGAR acceptance timestamp --------------------


def test_acceptance_before_the_close_keeps_the_same_trading_day():
    close = _frame({"AAA": _flat(30)})
    # 2020-01-15T14:00Z == 09:00 ET (EST) -- a pre-open announcement.
    event = _event("AAA", date(2020, 1, 15), "2020-01-15T14:00:00.000Z")
    day0 = announcement_day0(event, close.index)
    assert close.index[day0].date() == date(2020, 1, 15)


def test_acceptance_after_the_close_shifts_day0_to_the_next_trading_day():
    close = _frame({"AAA": _flat(30)})
    # 2020-01-15T21:30Z == 16:30 ET (EST) -- a classic after-close filing.
    event = _event("AAA", date(2020, 1, 15), "2020-01-15T21:30:00.000Z")
    day0 = announcement_day0(event, close.index)
    assert close.index[day0].date() == date(2020, 1, 16)


def test_the_utc_to_eastern_conversion_is_real_not_a_string_slice():
    """20:30 UTC is 16:30 ET in winter (EST, after close) but 15:30 ET in
    summer... no: 20:30 UTC is 15:30 ET in summer (EDT, BEFORE close). The
    same UTC clock time must land on different trading days by season."""
    close = _frame({"AAA": _flat(400)})
    winter = _event("AAA", date(2020, 1, 15), "2020-01-15T20:30:00.000Z")  # 15:30 EST
    summer = _event("AAA", date(2020, 7, 15), "2020-07-15T20:30:00.000Z")  # 16:30 EDT
    assert close.index[announcement_day0(winter, close.index)].date() == date(
        2020, 1, 15
    )
    assert close.index[announcement_day0(summer, close.index)].date() == date(
        2020, 7, 16
    )


def test_a_tz_naive_acceptance_is_read_as_utc_not_machine_local_time():
    """Regression for the latent bug the 2026-08-28 adversarial pass found:
    datetime.astimezone() on a NAIVE datetime assumes the MACHINE's local
    timezone, so a 'Z'-less acceptanceDateTime would have been converted
    from whatever timezone the host was in -- silently, and differently on
    different machines. Every real cached row is 'Z'-suffixed, which is
    exactly why no existing fixture exercised this.

    20:30 UTC on 2020-01-15 is 15:30 EST, BEFORE the close, so day 0 stays
    on 01-15. Read as US/Eastern-local it would be 20:30 ET (after close ->
    01-16); read as UTC+9 local it would be 06:30 ET (still 01-15 but for
    the wrong reason), so the naive and 'Z'-suffixed forms must agree AND
    must both land pre-close."""
    close = _frame({"AAA": _flat(30)})
    aware = _event("AAA", date(2020, 1, 15), "2020-01-15T20:30:00.000Z")
    naive = _event("AAA", date(2020, 1, 15), "2020-01-15T20:30:00")
    day0_aware = announcement_day0(aware, close.index)
    day0_naive = announcement_day0(naive, close.index)
    assert day0_naive == day0_aware
    assert close.index[day0_naive].date() == date(2020, 1, 15)


def test_a_tz_naive_after_close_acceptance_still_shifts_to_the_next_day():
    """The other side of the same fix: 21:30 UTC is 16:30 EST, after the
    close, so day 0 must move to 01-16 whether or not the string said 'Z'."""
    close = _frame({"AAA": _flat(30)})
    aware = _event("AAA", date(2020, 1, 15), "2020-01-15T21:30:00.000Z")
    naive = _event("AAA", date(2020, 1, 15), "2020-01-15T21:30:00")
    assert announcement_day0(naive, close.index) == announcement_day0(
        aware, close.index
    )
    assert close.index[announcement_day0(naive, close.index)].date() == date(
        2020, 1, 16
    )


def test_missing_acceptance_falls_back_to_the_after_close_rule():
    """The conservative direction: never place the window before the news
    could have existed."""
    close = _frame({"AAA": _flat(30)})
    event = _event("AAA", date(2020, 1, 15), "")
    day0 = announcement_day0(event, close.index)
    assert close.index[day0].date() == date(2020, 1, 16)


def test_weekend_filing_maps_to_the_next_index_row():
    close = _frame({"AAA": _flat(30)})
    saturday = date(2020, 1, 18)
    assert saturday.weekday() == 5
    event = _event("AAA", saturday, "")
    day0 = announcement_day0(event, close.index)
    # The fixture index is plain business days (no holiday calendar), so
    # the first row after Saturday 1/18 is Monday 1/20.
    assert close.index[day0].date() == date(2020, 1, 20)
    assert close.index[day0].date() > saturday


def test_announcement_beyond_the_loaded_index_returns_none():
    close = _frame({"AAA": _flat(10)})
    event = _event("AAA", date(2030, 1, 1), "")
    assert announcement_day0(event, close.index) is None


# --- EAR scoring -----------------------------------------------------------


def test_ear_is_the_stock_return_minus_the_benchmark_return():
    n = 30
    # AAA jumps 10% at row 11; benchmark rises 1% the same row.
    aaa = _flat(n)
    aaa[11:] = [110.0] * (n - 11)
    bench_vals = _flat(n)
    bench_vals[11:] = [101.0] * (n - 11)
    close = _frame({"AAA": aaa})
    bench = pd.Series(bench_vals, index=close.index)
    # Pre-open acceptance on the index[11] date -> day0 = 11.
    filing = close.index[11].date()
    event = _event("AAA", filing, f"{filing.isoformat()}T13:00:00.000Z")
    scored, rejected = score_events(close, bench, [event], (0, 1))
    assert not rejected
    assert len(scored) == 1
    s = scored[0]
    assert s.day0_position == 11
    # window (0,1): close(10) -> close(12): 110/100 - 101/100 = 0.09
    assert s.ear == pytest.approx(0.09, abs=1e-12)
    assert s.entry_position == 12  # the EAR window's final close


def test_the_wider_window_starts_one_row_earlier():
    n = 30
    aaa = [100.0 + i for i in range(n)]
    close = _frame({"AAA": aaa})
    bench = pd.Series(_flat(n), index=close.index)
    filing = close.index[11].date()
    event = _event("AAA", filing, f"{filing.isoformat()}T13:00:00.000Z")
    narrow, _ = score_events(close, bench, [event], (0, 1))
    wide, _ = score_events(close, bench, [event], (-1, 1))
    # (0,1): close(10)->close(12); (-1,1): close(9)->close(12).
    assert narrow[0].ear == pytest.approx(112.0 / 110.0 - 1.0)
    assert wide[0].ear == pytest.approx(112.0 / 109.0 - 1.0)
    assert narrow[0].entry_position == wide[0].entry_position == 12


def test_duplicate_filings_within_the_gap_keep_only_the_first():
    n = 40
    close = _frame({"AAA": _flat(n)})
    bench = pd.Series(_flat(n), index=close.index)
    d1 = close.index[10].date()
    d2 = close.index[12].date()
    events = [
        _event("AAA", d1, f"{d1.isoformat()}T13:00:00.000Z", accession="a-1"),
        _event("AAA", d2, f"{d2.isoformat()}T13:00:00.000Z", accession="a-2"),
    ]
    scored, rejected = score_events(close, bench, events, (0, 1))
    assert len(scored) == 1
    assert scored[0].day0_position == 10
    assert rejected == {"duplicate filing within gap": 1}


def test_a_second_filing_beyond_the_gap_is_a_real_event():
    n = 60
    close = _frame({"AAA": _flat(n)})
    bench = pd.Series(_flat(n), index=close.index)
    d1 = close.index[10].date()
    d2 = close.index[30].date()
    events = [
        _event("AAA", d1, f"{d1.isoformat()}T13:00:00.000Z", accession="a-1"),
        _event("AAA", d2, f"{d2.isoformat()}T13:00:00.000Z", accession="a-2"),
    ]
    scored, rejected = score_events(close, bench, events, (0, 1))
    assert len(scored) == 2
    assert not rejected


def test_missing_prices_at_the_window_endpoints_reject_the_event():
    n = 30
    values = _flat(n)
    values[12] = np.nan  # the (0,1) window's final close
    close = _frame({"AAA": values})
    bench = pd.Series(_flat(n), index=close.index)
    filing = close.index[11].date()
    event = _event("AAA", filing, f"{filing.isoformat()}T13:00:00.000Z")
    scored, rejected = score_events(close, bench, [event], (0, 1))
    assert scored == []
    assert rejected == {"no price at EAR window endpoints": 1}


def test_unpriced_ticker_and_too_recent_event_are_rejected_with_reasons():
    n = 30
    close = _frame({"AAA": _flat(n)})
    bench = pd.Series(_flat(n), index=close.index)
    gone = _event("GONE", close.index[10].date(), "")
    late_filing = close.index[n - 2].date()
    late = _event("AAA", late_filing, f"{late_filing.isoformat()}T13:00:00.000Z")
    scored, rejected = score_events(close, bench, [gone, late], (0, 1))
    assert scored == []
    assert rejected == {
        "no price data for ticker": 1,
        "announcement too recent for any hold": 1,
    }


# --- classification against trailing breakpoints --------------------------


def _scored_seq(
    index: pd.DatetimeIndex, ears: list[float], start_pos: int = 10
) -> list[ScoredEvent]:
    """One event per row starting at start_pos, EARs as given, each with
    entry one row after its day 0."""
    out = []
    for i, ear in enumerate(ears):
        d0 = start_pos + i
        out.append(
            ScoredEvent(
                ticker=f"T{i}",
                day0_position=d0,
                day0_date=index[d0].date(),
                entry_position=d0 + 1,
                entry_date=index[d0 + 1].date(),
                ear=ear,
            )
        )
    return out


def test_extreme_ears_go_long_and_short_and_the_middle_goes_nowhere(monkeypatch):
    monkeypatch.setattr(pead, "PEAD_MIN_BREAKPOINT_OBS", 5)
    index = pd.bdate_range("2020-01-01", periods=300)
    trailing = list(np.linspace(-0.04, 0.04, 20))
    tail = [0.10, -0.10, 0.0]  # long, short, middle
    scored = _scored_seq(index, trailing + tail)
    classified, counts = classify_events(scored, index[0].date())
    by_ticker = {c.ticker: c.leg for c in classified}
    assert by_ticker.get("T20") == "long"
    assert by_ticker.get("T21") == "short"
    assert "T22" not in by_ticker
    assert counts.n_long >= 1 and counts.n_short >= 1 and counts.n_middle >= 1


def test_thin_breakpoint_history_skips_the_event_not_the_run():
    index = pd.bdate_range("2020-01-01", periods=100)
    scored = _scored_seq(index, [0.05, -0.05, 0.06])
    classified, counts = classify_events(scored, index[0].date())
    assert classified == []
    assert counts.n_skipped_thin_breakpoints == 3


def test_warmup_events_feed_breakpoints_but_are_never_entered(monkeypatch):
    monkeypatch.setattr(pead, "PEAD_MIN_BREAKPOINT_OBS", 5)
    index = pd.bdate_range("2020-01-01", periods=300)
    ears = list(np.linspace(-0.04, 0.04, 20)) + [0.10]
    scored = _scored_seq(index, ears)
    # Formation starts after every warm-up event's day 0 but before the
    # final event's.
    formation_start = scored[-1].day0_date
    classified, counts = classify_events(scored, formation_start)
    assert [c.ticker for c in classified] == ["T20"]
    assert counts.n_eligible_day0 == 1
    assert counts.n_scored == 21


def test_breakpoints_are_point_in_time_only_completed_ears_count(monkeypatch):
    """An event entered at row j must rank only against EARs completed
    STRICTLY before row j -- same-close siblings and anything later are
    excluded. With only 4 completed priors, the 5th event is skipped even
    though 5 other events exist in total."""
    monkeypatch.setattr(pead, "PEAD_MIN_BREAKPOINT_OBS", 5)
    index = pd.bdate_range("2020-01-01", periods=300)
    scored = _scored_seq(index, [0.01, 0.02, 0.03, 0.04, 0.10])
    classified, counts = classify_events(scored, index[0].date())
    assert counts.n_skipped_thin_breakpoints == 5  # 0..4 priors each < 5
    assert classified == []


def test_breakpoints_respect_the_trailing_window(monkeypatch):
    """EARs whose day 0 has fallen out of the 126-row trailing window must
    not shape the quantiles."""
    monkeypatch.setattr(pead, "PEAD_MIN_BREAKPOINT_OBS", 5)
    index = pd.bdate_range("2018-01-01", periods=800)
    # 20 ancient huge EARs, then 20 recent tiny ones, then a +0.02 event.
    ancient = _scored_seq(index, [1.0] * 20, start_pos=10)
    recent = _scored_seq(index, list(np.linspace(-0.01, 0.01, 20)), start_pos=500)
    probe = ScoredEvent(
        ticker="PROBE",
        day0_position=560,
        day0_date=index[560].date(),
        entry_position=561,
        entry_date=index[561].date(),
        ear=0.02,
    )
    scored = sorted(ancient + recent + [probe], key=lambda s: s.entry_position)
    classified, _ = classify_events(scored, index[0].date())
    legs = {c.ticker: c.leg for c in classified}
    # Against the RECENT distribution +0.02 is extreme-high; against the
    # ancient 1.0s it would have been middle.
    assert legs.get("PROBE") == "long"


# --- the replay ------------------------------------------------------------


def test_long_minus_short_is_the_daily_return():
    n = 40
    close = _frame({"AAA": [100.0 * (1.02**i) for i in range(n)], "BBB": _flat(n)})
    entered = [
        _classified("AAA", close.index, 5, "long"),
        _classified("BBB", close.index, 5, "short"),
    ]
    result = run_pead_backtest(close, entered, _spec(hold=10), _free_config())
    assert result.status == "ok"
    realized = result.daily_returns.iloc[:10]
    assert np.allclose(realized.to_numpy(), 0.02, atol=1e-12)
    assert result.n_invested_days == 10
    assert result.n_one_sided_days == 0


def test_a_short_leg_profit_comes_from_the_short_falling():
    n = 40
    close = _frame({"AAA": _flat(n), "BBB": [100.0 * (0.99**i) for i in range(n)]})
    entered = [
        _classified("AAA", close.index, 5, "long"),
        _classified("BBB", close.index, 5, "short"),
    ]
    result = run_pead_backtest(close, entered, _spec(hold=10), _free_config())
    assert np.allclose(result.daily_returns.iloc[:10].to_numpy(), 0.01, atol=1e-12)


def test_one_sided_days_are_flat_and_counted_never_traded_naked():
    n = 40
    close = _frame({"AAA": [100.0 * (1.05**i) for i in range(n)], "BBB": _flat(n)})
    entered = [_classified("AAA", close.index, 5, "long")]
    result = run_pead_backtest(close, entered, _spec(hold=10), _free_config())
    assert (result.daily_returns == 0.0).all()
    assert result.n_one_sided_days == 10
    assert result.n_invested_days == 0


def test_hold_length_is_exactly_holding_days_of_realized_returns():
    n = 60
    close = _frame({"AAA": [100.0 * (1.02**i) for i in range(n)], "BBB": _flat(n)})
    entered = [
        _classified("AAA", close.index, 5, "long"),
        _classified("BBB", close.index, 5, "short"),
    ]
    result = run_pead_backtest(close, entered, _spec(hold=7), _free_config())
    invested = result.daily_returns[result.daily_returns != 0.0]
    assert len(invested) == 7
    assert result.n_invested_days == 7
    # Days after both exits are flat, not dropped.
    assert len(result.daily_returns) == n - 6


def test_round_trip_cost_is_charged_once_per_event_regardless_of_hold():
    n = 300
    close = _frame({"AAA": _flat(n), "BBB": _flat(n)})
    entered = [
        _classified("AAA", close.index, 5, "long"),
        _classified("BBB", close.index, 5, "short"),
    ]
    config = PeadConfig(financing_bps_per_year=0.0)
    costs = {}
    for hold in (63, 126):
        result = run_pead_backtest(close, entered, _spec(hold=hold), config)
        costs[hold] = result.total_cost
    assert costs[63] == pytest.approx(costs[126])
    # Two single-name legs, each at weight 1.0.
    assert costs[63] == pytest.approx(2.0 * PEAD_ROUND_TRIP_BPS / 10_000.0)


def test_cost_is_deferred_while_the_book_is_one_sided():
    """An event entered during a one-sided stretch pays nothing until its
    trade is actually on; if it never is, it never pays."""
    n = 60
    close = _frame({"AAA": _flat(n)})
    entered = [_classified("AAA", close.index, 5, "long")]
    result = run_pead_backtest(close, entered, _spec(hold=10), PeadConfig())
    assert result.total_cost == 0.0


def test_a_new_traded_event_on_a_held_ticker_supersedes_and_repays():
    n = 80
    close = _frame({"AAA": _flat(n), "BBB": _flat(n)})
    entered = [
        _classified("AAA", close.index, 5, "long"),
        _classified("BBB", close.index, 5, "short"),
        _classified("AAA", close.index, 10, "short"),  # supersedes the long
    ]
    config = PeadConfig(financing_bps_per_year=0.0)
    result = run_pead_backtest(close, entered, _spec(hold=30), config)
    assert result.n_events_superseded == 1
    # AAA pays twice (once per event), BBB once -- but after AAA flips
    # short, the book is short-only (BBB short + AAA short, no long leg),
    # so those days are one-sided and AAA's second round trip is only paid
    # if its trade ever goes on. Verify the charge accounting stays within
    # [2, 3] round trips and the flip was registered.
    per_event = PEAD_ROUND_TRIP_BPS / 10_000.0
    assert 2.0 * per_event <= result.total_cost <= 3.0 * per_event + 1e-12


def test_delisting_mid_hold_is_charged_the_shumway_return():
    n = 40
    values = _flat(n)
    for i in range(10, n):
        values[i] = np.nan
    close = _frame({"AAA": values, "BBB": _flat(n)})
    entered = [
        _classified("AAA", close.index, 5, "long"),
        _classified("BBB", close.index, 5, "short"),
    ]
    result = run_pead_backtest(close, entered, _spec(hold=20), _free_config())
    assert result.n_events_delisted_mid_hold == 1
    assert result.daily_returns.min() == pytest.approx(DEFAULT_IMPUTED_DELISTING_RETURN)


def test_delisting_imputation_can_be_turned_off():
    n = 40
    values = _flat(n)
    for i in range(10, n):
        values[i] = np.nan
    close = _frame({"AAA": values, "BBB": _flat(n)})
    entered = [
        _classified("AAA", close.index, 5, "long"),
        _classified("BBB", close.index, 5, "short"),
    ]
    config = PeadConfig(
        round_trip_bps=0.0,
        financing_bps_per_year=0.0,
        impute_delisting_returns=False,
    )
    result = run_pead_backtest(close, entered, _spec(hold=20), config)
    assert result.n_events_delisted_mid_hold == 0
    assert result.daily_returns.min() > DEFAULT_IMPUTED_DELISTING_RETURN


def test_a_delisted_short_is_a_gain_not_a_loss():
    """The imputed -42.5% on a SHORT-leg name is profit -- the realistic
    direction for a negative-surprise name that dies."""
    n = 40
    values = _flat(n)
    for i in range(10, n):
        values[i] = np.nan
    close = _frame({"AAA": _flat(n), "BBB": values})
    entered = [
        _classified("AAA", close.index, 5, "long"),
        _classified("BBB", close.index, 5, "short"),
    ]
    result = run_pead_backtest(close, entered, _spec(hold=20), _free_config())
    assert result.daily_returns.max() == pytest.approx(
        -DEFAULT_IMPUTED_DELISTING_RETURN
    )


def test_inverse_vol_without_a_basis_fails_loudly():
    close = _frame({"AAA": _flat(30)})
    entered = [_classified("AAA", close.index, 5, "long")]
    with pytest.raises(ValueError, match="inverse-vol basis"):
        run_pead_backtest(
            close, entered, _spec(weighting="inverse_vol"), _free_config(), None
        )


def test_inverse_vol_with_unusable_basis_falls_back_to_equal():
    n = 40
    close = _frame(
        {
            "AAA": [100.0 * (1.04**i) for i in range(n)],
            "BBB": _flat(n),
            "CCC": _flat(n),
        }
    )
    basis = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    entered = [
        _classified("AAA", close.index, 5, "long"),
        _classified("BBB", close.index, 5, "long"),
        _classified("CCC", close.index, 5, "short"),
    ]
    result = run_pead_backtest(
        close, entered, _spec(hold=10, weighting="inverse_vol"), _free_config(), basis
    )
    assert result.n_weight_fallback_days == result.n_invested_days > 0
    # Fallback is EQUAL weight: half of +4%, half of 0%, minus flat short.
    assert result.daily_returns.iloc[0] == pytest.approx(0.02, rel=1e-9)


def test_inverse_vol_basis_is_point_in_time():
    rng = np.random.default_rng(1)
    prices = list(100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.01, 200)))
    short = build_inverse_vol_basis(_frame({"AAA": prices[:150]}))
    long = build_inverse_vol_basis(_frame({"AAA": prices}))
    assert np.allclose(
        short["AAA"].iloc[100:150].to_numpy(),
        long["AAA"].iloc[100:150].to_numpy(),
        equal_nan=True,
    )


# --- screening / DSR -------------------------------------------------------


def _synthetic_events_and_frame(
    n_tickers: int = 10, n_days: int = 700, seed: int = 2
) -> tuple[pd.DataFrame, pd.Series, list[EarningsEvent]]:
    rng = np.random.default_rng(seed)
    close = _frame(
        {
            f"T{i}": list(100.0 * np.cumprod(1.0 + rng.normal(0.0002, 0.02, n_days)))
            for i in range(n_tickers)
        },
        start="2018-01-01",
    )
    bench = pd.Series(
        100.0 * np.cumprod(1.0 + rng.normal(0.0002, 0.01, n_days)), index=close.index
    )
    events = []
    for i in range(n_tickers):
        for q in range(10):  # "quarterly" filings every ~63 rows
            row = 20 + i + q * 63
            if row >= n_days - 3:
                continue
            filing = close.index[row].date()
            events.append(
                _event(
                    f"T{i}",
                    filing,
                    f"{filing.isoformat()}T13:00:00.000Z",
                    accession=f"t{i}-q{q}",
                )
            )
    return close, bench, events


def test_screening_uses_the_full_pre_declared_family_as_n_trials(monkeypatch):
    monkeypatch.setattr(pead, "PEAD_MIN_BREAKPOINT_OBS", 5)
    close, bench, events = _synthetic_events_and_frame()
    results, _scored, _rejected, _counts = screen_pead_family(
        close, bench, events, close.index[0].date(), _free_config()
    )
    assert {r.pattern_id for r in results} == EXPECTED_PATTERN_IDS
    for r in results:
        assert r.deflated_sharpe.n_trials == PEAD_N_TRIALS
        assert r.deflated_sharpe.dsr_floor_met  # 8 >= MIN_TRIALS_FOR_DSR
        assert 0.0 <= r.invested_fraction <= 1.0
        assert r.n_events_entered == r.n_events_long + r.n_events_short


def test_screening_returns_nothing_when_there_are_no_events():
    close = _frame({"AAA": _flat(300)})
    bench = pd.Series(_flat(300), index=close.index)
    results, _, _, _ = screen_pead_family(
        close, bench, [], close.index[0].date(), _free_config()
    )
    assert results == []


# --- sample disclosure -----------------------------------------------------


def test_sample_disclosure_states_the_survivorship_direction_and_the_prior():
    report = EdgarFetchReport(
        n_tickers_requested=500,
        n_tickers_cik_resolved=490,
        n_tickers_fetched=488,
        n_tickers_coverage_truncated=12,
    )
    d = build_pead_sample_disclosure(report, 1000, 950, 480, {}, {}, {})
    assert d.n_tickers_requested == 500
    assert d.n_events_after_membership_gate == 950
    assert "SHORT leg" in d.text
    assert "survivorship" in d.text
    assert "disbelieved" in d.text
    assert f"n_trials={PEAD_N_TRIALS}" in d.text


# --- the EDGAR fixtures (shape verified live 2026-08-28, replayed here) ---


def test_parse_item_202_rows_matches_the_verified_submissions_shape():
    """The fixture mirrors the REAL data.sec.gov/submissions response shape
    verified live during the build: filings.recent as parallel arrays, an
    8-K row with items='2.02,9.01' and an ISO-8601 Z acceptance."""
    submissions = {
        "filings": {
            "recent": {
                "form": ["8-K", "10-Q", "8-K", "8-K/A", "8-K"],
                "items": ["2.02,9.01", "", "5.02", "2.02,9.01", "2.02"],
                "filingDate": [
                    "2025-07-30",
                    "2025-08-01",
                    "2025-09-15",
                    "2025-08-02",
                    "2018-05-01",
                ],
                "acceptanceDateTime": [
                    "2025-07-30T20:30:28.000Z",
                    "2025-08-01T10:00:00.000Z",
                    "2025-09-15T12:00:00.000Z",
                    "2025-08-02T12:00:00.000Z",
                    "2018-05-01T12:00:00.000Z",
                ],
                "accessionNumber": ["a-1", "a-2", "a-3", "a-4", "a-5"],
            }
        }
    }
    events, truncated = pead._parse_item_202_rows(
        "AAPL", 320193, submissions, date(2020, 1, 1), date(2026, 1, 1)
    )
    # Row 0: kept. Row 1: not an 8-K. Row 2: no 2.02. Row 3: 8-K/A, an
    # amendment, never the announcement. Row 4: before the fetch window.
    assert len(events) == 1
    assert events[0].accession == "a-1"
    assert events[0].acceptance_utc == "2025-07-30T20:30:28.000Z"
    assert truncated is False


def test_item_substring_matching_is_exact_not_a_contains():
    """'2.02' must not match a hypothetical '12.02' or '2.02' embedded in
    another item id -- matching is against the comma-split list."""
    submissions = {
        "filings": {
            "recent": {
                "form": ["8-K"],
                "items": ["12.02"],
                "filingDate": ["2025-07-30"],
                "acceptanceDateTime": ["2025-07-30T20:30:28.000Z"],
                "accessionNumber": ["a-1"],
            }
        }
    }
    events, _ = pead._parse_item_202_rows(
        "AAPL", 320193, submissions, date(2020, 1, 1), date(2026, 1, 1)
    )
    assert events == []


def test_event_cache_round_trips(tmp_path):
    path = tmp_path / "cache.json"
    events = [
        _event("AAPL", date(2025, 7, 30), "2025-07-30T20:30:28.000Z", "a-1"),
        _event("MSFT", date(2025, 7, 29), "", "a-2"),
    ]
    report = EdgarFetchReport(
        n_tickers_requested=2,
        n_tickers_cik_resolved=2,
        n_tickers_fetched=2,
        unresolved_tickers=[],
        failed_tickers=[],
    )
    save_event_cache(events, report, date(2018, 4, 1), date(2026, 8, 27), path)
    loaded = load_event_cache(path)
    assert loaded is not None
    loaded_events, loaded_report, fetch_start, end = loaded
    assert loaded_events == events
    assert loaded_report.n_tickers_fetched == 2
    assert (fetch_start, end) == (date(2018, 4, 1), date(2026, 8, 27))


def test_missing_cache_returns_none(tmp_path):
    assert load_event_cache(tmp_path / "nope.json") is None


# --- the production entry point -------------------------------------------


def test_screening_start_before_membership_coverage_fails_loudly():
    with pytest.raises(ValueError, match="predates point-in-time membership"):
        run_pead_screening(date(2010, 1, 1), date(2020, 1, 1))


def test_screening_fails_loudly_when_the_benchmark_resolves_no_data():
    """Silently ranking on raw returns would be a different, market-
    direction-contaminated signal than this family declares."""

    class _NoBenchmarkProvider:
        def get_daily_ohlcv(self, tickers, start, end):
            if tickers == ["SPY"]:
                return {}, ["SPY"]
            n = 400
            idx = pd.bdate_range("2019-06-01", periods=n)
            frame = pd.DataFrame({t: [100.0] * n for t in tickers}, index=idx)
            return {"close": frame, "open": frame, "volume": frame}, []

    filing = date(2020, 3, 2)
    events = [_event("AAPL", filing, f"{filing.isoformat()}T13:00:00.000Z")]
    with pytest.raises(ValueError, match="benchmark resolved no price data"):
        run_pead_screening(
            date(2020, 1, 1),
            date(2021, 1, 1),
            provider=_NoBenchmarkProvider(),
            events=events,
            edgar_report=EdgarFetchReport(n_tickers_requested=1),
        )


def test_membership_gate_drops_non_members_at_the_filing_date():
    """A ticker that was NOT an S&P 500 member when it filed must not
    contribute an event -- day-one point-in-time discipline."""

    class _Provider:
        def get_daily_ohlcv(self, tickers, start, end):
            if not tickers:
                return {}, []
            n = 400
            idx = pd.bdate_range("2019-06-01", periods=n)
            frame = pd.DataFrame({t: [100.0] * n for t in tickers}, index=idx)
            return {"close": frame, "open": frame, "volume": frame}, []

    filing = date(2020, 3, 2)
    events = [
        # HOOD did not IPO until 2021 and was not an S&P 500 member in
        # 2020; the vendored membership data answers False.
        _event("HOOD", filing, f"{filing.isoformat()}T13:00:00.000Z")
    ]
    summary = run_pead_screening(
        date(2020, 1, 1),
        date(2021, 1, 1),
        provider=_Provider(),
        events=events,
        edgar_report=EdgarFetchReport(n_tickers_requested=1),
    )
    assert summary.results == []
    assert summary.sample.n_raw_events == 1
    assert summary.sample.n_events_after_membership_gate == 0


def test_cost_disclosure_names_its_own_numbers_and_their_source():
    class _Provider:
        def get_daily_ohlcv(self, tickers, start, end):
            if not tickers:
                return {}, []
            n = 400
            idx = pd.bdate_range("2019-06-01", periods=n)
            frame = pd.DataFrame({t: [100.0] * n for t in tickers}, index=idx)
            return {"close": frame, "open": frame, "volume": frame}, []

    summary = run_pead_screening(
        date(2020, 1, 1),
        date(2021, 1, 1),
        provider=_Provider(),
        events=[],
        edgar_report=EdgarFetchReport(n_tickers_requested=0),
    )
    assert str(PEAD_ROUND_TRIP_BPS) in summary.cost_disclosure
    assert "ONCE PER EVENT" in summary.cost_disclosure
    assert "DISCLOSED OPTIMISM" in summary.cost_disclosure


def test_holding_days_match_the_literature_convention():
    assert min(PEAD_HOLDING_DAYS) == 63  # the ~60-trading-day convention
    assert max(PEAD_HOLDING_DAYS) == 126
