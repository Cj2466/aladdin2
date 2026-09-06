"""Tests for the aggregate-dividend-payment price-pressure family.

FIDELITY CHECK F13 OF THE PRE-REGISTRATION lives here: every published
construction is validated against a HAND-BUILT SYNTHETIC PANEL WITH A KNOWN
CORRECT ANSWER before it is trusted on real data, per CLAUDE.md's rule against
implementing a published formula from memory. Each such test names the [HS22]
section it pins.

The rest are the structural guards: the grid size that is the DSR denominator,
the point-in-time contract, the tie rule, and the split-basis join that is the
one place this construction could silently scale its whole numerator.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.dividend_payment_pressure_timing import (
    ABNORMAL_LOOKBACK_DAYS,
    ABNORMAL_SKIP_DAYS,
    CUMULATION_DAYS,
    DATINGS,
    DIVIDEND_PAYMENT_N_TRIALS,
    DIVIDEND_PRESSURE_COST_BPS,
    DIVIDEND_PRESSURE_DIRECTION,
    DIVIDEND_PRESSURE_FAMILY,
    GROSS_NOTIONAL_PER_UNIT_POSITION,
    MAX_PLAUSIBLE_LAG_DAYS,
    RANK_WINDOW_DAYS,
    TOM_WINDOW_FIRST_DAYS,
    TOM_WINDOW_LAST_DAYS,
    TOP_N_THRESHOLDS,
    DividendPaymentEvent,
    DividendPressureConfig,
    DividendPressureData,
    PaymentCalendarReport,
    RawPaymentCache,
    abnormal_denominator,
    assert_no_lookahead,
    build_aggregate_market_cap,
    build_daily_dividend_dollars,
    build_payment_events,
    build_share_count_frame,
    build_signal_series,
    demeaned_position,
    future_cumulative,
    resolve_payment_lags,
    run_dividend_pressure_backtest,
    top_n_indicator,
    turn_of_month_indicator,
    two_day_cumulative,
)

# ---------------------------------------------------------------------------
# THE GRID -- the DSR denominator, asserted three ways
# ---------------------------------------------------------------------------


def test_family_size_matches_the_preregistered_denominator():
    """34 = 4 signals x 2 datings x 4 thresholds + 2 calendar controls.

    This is the n_trials the screen deflates at. A silent drift here silently
    changes the multiple-comparisons denominator for every future run, which is
    why the module asserts it at import and this test asserts it again from the
    outside."""
    assert len(DIVIDEND_PRESSURE_FAMILY) == DIVIDEND_PAYMENT_N_TRIALS == 34
    assert len({s.spec_id for s in DIVIDEND_PRESSURE_FAMILY}) == 34
    assert sum(1 for s in DIVIDEND_PRESSURE_FAMILY if s.is_control) == 2
    assert sum(1 for s in DIVIDEND_PRESSURE_FAMILY if s.is_placebo) == len(DATINGS) * len(
        TOP_N_THRESHOLDS
    )


def test_thresholds_are_the_papers_own_four():
    """[HS22] Table II Panel B, verbatim: "the top 2 weeks (10 days), quarter
    (63 days), third (84 days) or half (126 days) of days in the past year".

    These are INHERITED, not searched. Pinning the literal values means a later
    edit that quietly adds or tunes a threshold has to change this test, which
    makes it a visible decision rather than a silent one."""
    assert TOP_N_THRESHOLDS == (10, 63, 84, 126)
    assert RANK_WINDOW_DAYS == 252
    assert CUMULATION_DAYS == 2


def test_controls_are_not_duplicated_across_the_dating_axis():
    """The calendar controls use NO dividend data, so the two datings would
    produce byte-identical position series. Counting them twice would inflate
    the denominator with a distinction that does not exist."""
    controls = [s for s in DIVIDEND_PRESSURE_FAMILY if s.is_control]
    assert len(controls) == 2
    assert all(s.dating == "none" for s in controls)


def test_direction_is_positive_and_fixed():
    """[HS25] abstract: dividend buying pressure "predicts HIGHER
    value-weighted market returns". Direction is not a free parameter; a
    flipped family would be a second 34-trial search."""
    assert DIVIDEND_PRESSURE_DIRECTION == 1.0


def test_single_instrument_book_trades_one_unit_of_gross_notional():
    """The deliberate difference from rebalancing_pressure_timing.py, which
    trades a two-legged spread at 2.0 gross per unit. Pinning it stops the
    constant being "corrected" to 2.0 by someone copying that module."""
    assert GROSS_NOTIONAL_PER_UNIT_POSITION == 1.0
    assert DIVIDEND_PRESSURE_COST_BPS == 1.0


# ---------------------------------------------------------------------------
# F13 -- KNOWN-ANSWER VALIDATION OF EVERY PUBLISHED CONSTRUCTION
# ---------------------------------------------------------------------------


def _index(n: int) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.bdate_range("2015-01-01", periods=n))


def test_two_day_cumulative_is_exactly_the_paper_stated_sum():
    """[HS22] Table I columns 3-4: "the cumulative dividend payment yield on
    the payment date and the day before". KNOWN ANSWER, computed by hand."""
    dollars = pd.Series([1.0, 2.0, 4.0, 8.0], index=_index(4))
    out = two_day_cumulative(dollars)
    assert np.isnan(out.iloc[0])  # no "day before" exists for the first row
    assert out.iloc[1] == 3.0
    assert out.iloc[2] == 6.0
    assert out.iloc[3] == 12.0


def test_abnormal_denominator_uses_exactly_the_papers_t20_to_t272_window():
    """[HS22] footnote 12, verbatim: "We calculate this average using the
    trading days from t-20 to t-272."

    KNOWN-ANSWER CONSTRUCTION: a series that is 0 everywhere except a single
    1.0 spike. The denominator at day t is then 1/253 exactly on the days whose
    t-272..t-20 window contains the spike, and 0 elsewhere. That pins BOTH
    window edges to the day, which an averaged-value test could not do.

    THE SPIKE IS PLACED AT INDEX 300, PAST THE BURN-IN, DELIBERATELY. The first
    non-NaN output is at index 272 (a 253-day window shifted forward by 20), so
    a spike placed earlier would have its lower coverage edge hidden inside the
    burn-in and the test would silently check only one of the two edges."""
    n = 700
    dollars = pd.Series(0.0, index=_index(n))
    spike_at = 300
    dollars.iloc[spike_at] = 1.0

    out = abnormal_denominator(dollars)
    width = ABNORMAL_LOOKBACK_DAYS - ABNORMAL_SKIP_DAYS + 1
    assert width == 253
    # Burn-in: 252 rolling rows plus the 20-day shift.
    first_valid = int(np.flatnonzero(np.isfinite(out.to_numpy()))[0])
    assert first_valid == width - 1 + ABNORMAL_SKIP_DAYS == 272

    covering = [i for i in range(n) if np.isfinite(out.iloc[i]) and out.iloc[i] > 0]
    # The window at t is [t-272, t-20] inclusive, so the spike at index s is
    # inside it for t from s+20 to s+272.
    assert min(covering) == spike_at + ABNORMAL_SKIP_DAYS
    assert max(covering) == spike_at + ABNORMAL_LOOKBACK_DAYS
    assert out.iloc[covering[0]] == pytest.approx(1.0 / width)

    # THE SKIP IS THE WHOLE POINT: the 20 days immediately before t must NOT
    # see the spike, so the day the spike lands on has a zero denominator.
    assert out.iloc[spike_at] == 0.0
    assert out.iloc[spike_at + ABNORMAL_SKIP_DAYS - 1] == 0.0


def test_top_n_indicator_known_answer_and_window_boundary():
    """[HS22] Table II Panel B: 1 if today is in the top n of the trailing 252
    days INCLUDING today.

    KNOWN ANSWER: a strictly increasing series makes every day the largest in
    its own window, so every fully-warmed day is high. A strictly DECREASING
    series makes every day the smallest, so none is."""
    n_days = RANK_WINDOW_DAYS + 20
    rising = pd.Series(np.arange(n_days, dtype=float), index=_index(n_days))
    out = top_n_indicator(rising, 10)
    # Burn-in: no full window before row 251.
    assert out.iloc[: RANK_WINDOW_DAYS - 1].isna().all()
    assert not np.isnan(out.iloc[RANK_WINDOW_DAYS - 1])
    assert (out.iloc[RANK_WINDOW_DAYS - 1 :] == 1.0).all()

    falling = pd.Series(np.arange(n_days, 0, -1, dtype=float), index=_index(n_days))
    assert (top_n_indicator(falling, 10).iloc[RANK_WINDOW_DAYS - 1 :] == 0.0).all()


def test_top_n_indicator_tie_rule_is_the_declared_one():
    """The declared rule: a day is high when STRICTLY FEWER THAN n values in
    its own window exceed it.

    KNOWN ANSWER: a window that is all zeros except one 1.0. At n=1, the single
    1.0 is high (nothing exceeds it) and every tied zero is NOT (one value
    exceeds it). At n=2 the zeros tie into the top and ALL become high, which
    is the declared consequence -- the realized frequency can exceed n/252 where
    ties cluster, and the module reports the realized frequency beside the
    pre-declared one so the inflation is visible."""
    n_days = RANK_WINDOW_DAYS
    values = np.zeros(n_days)
    values[-1] = 1.0
    series = pd.Series(values, index=_index(n_days))

    assert top_n_indicator(series, 1).iloc[-1] == 1.0
    # At n=2 the last row's window has ONE strictly greater value... none, it
    # IS the max, so it is high; the point of the check is the zeros case.
    zeros_only = pd.Series(np.zeros(n_days), index=_index(n_days))
    assert top_n_indicator(zeros_only, 1).iloc[-1] == 1.0, (
        "with every value tied, nothing is strictly greater, so the day is high"
    )


def test_top_n_indicator_refuses_an_incoherent_threshold():
    series = pd.Series(np.arange(300, dtype=float), index=_index(300))
    with pytest.raises(ValueError):
        top_n_indicator(series, 0)
    with pytest.raises(ValueError):
        top_n_indicator(series, RANK_WINDOW_DAYS + 1)


def test_future_cumulative_reads_days_t_plus_1_and_t_plus_2():
    """[HS22] Table I columns 5-6's placebo: "future dividends (on day t+1 and
    t+2)". IT READS THE FUTURE ON PURPOSE. KNOWN ANSWER by hand."""
    dollars = pd.Series([1.0, 2.0, 4.0, 8.0, 16.0], index=_index(5))
    out = future_cumulative(dollars)
    assert out.iloc[0] == 6.0  # 2 + 4
    assert out.iloc[1] == 12.0  # 4 + 8
    assert out.iloc[2] == 24.0  # 8 + 16
    assert np.isnan(out.iloc[3]) and np.isnan(out.iloc[4])


def test_demeaned_position_is_market_neutral_at_the_declared_frequency():
    """position = indicator - n/252. If the realized frequency equals the
    declared one, the mean position is exactly zero -- which is the whole
    reason this sizing exists rather than a long-only book."""
    index = _index(252)
    indicator = pd.Series(0.0, index=index)
    indicator.iloc[:10] = 1.0
    position = demeaned_position(indicator, 10 / 252)
    assert position.mean() == pytest.approx(0.0, abs=1e-12)
    assert position.max() == pytest.approx(1.0 - 10 / 252)
    assert position.min() == pytest.approx(-10 / 252)


def test_turn_of_month_indicator_marks_the_lakonishok_smidt_window():
    """The last TOM_WINDOW_LAST_DAYS trading days of a month plus the first
    TOM_WINDOW_FIRST_DAYS of the next, derived from the TRADED calendar."""
    index = pd.DatetimeIndex(pd.bdate_range("2020-01-01", "2020-03-31"))
    out = turn_of_month_indicator(index)
    january = index[index.month == 1]
    february = index[index.month == 2]
    # First three trading days of February are in the window.
    for ts in february[:TOM_WINDOW_FIRST_DAYS]:
        assert out[ts] == 1.0
    assert out[february[TOM_WINDOW_FIRST_DAYS]] == 0.0
    # Last trading day of January is in the window.
    assert out[january[-1]] == 1.0
    assert out[january[-1 - TOM_WINDOW_LAST_DAYS]] == 0.0


# ---------------------------------------------------------------------------
# THE PAYMENT-DATE IMPUTATION
# ---------------------------------------------------------------------------


def test_resolve_payment_lags_refuses_a_negative_or_absurd_lag():
    """A payment cannot precede its own ex-date, and Yahoo's `.calendar` can
    return a STALE pair that presents as a negative lag. A lag beyond a full
    quarter would put the imputed payment after the NEXT ex-date."""
    lags, median = resolve_payment_lags(
        {
            "GOOD": {"lag_days": 21},
            "ALSO_GOOD": {"lag_days": 7},
            "STALE": {"lag_days": -60},
            "ABSURD": {"lag_days": MAX_PLAUSIBLE_LAG_DAYS + 1},
            "NO_PAY": {"ex": "2026-01-01", "pay": None},
        }
    )
    assert set(lags) == {"GOOD", "ALSO_GOOD"}
    assert median == pytest.approx(14.0)


def _cache(dividends, lags, share_counts=None, nasdaq=None) -> RawPaymentCache:
    return RawPaymentCache(
        dividends=dividends,
        yf_payment_lag=lags,
        nasdaq_history=nasdaq or {},
        share_counts=share_counts or {},
        report=PaymentCalendarReport(),
    )


def test_payment_date_is_rolled_forward_to_a_trading_day_never_backward():
    """A payment landing on a weekend cannot be a trading day in a daily panel.
    Rolling BACKWARD would move cash earlier than it could have arrived.

    KNOWN ANSWER: 2020-01-02 (Thursday) + 2 days = 2020-01-04, a SATURDAY. The
    next trading day in a business-day calendar is Monday 2020-01-06."""
    index = pd.DatetimeIndex(pd.bdate_range("2020-01-01", "2020-03-31"))
    cache = _cache({"AAA": [(date(2020, 1, 2), 1.0)]}, {"AAA": {"lag_days": 2}})
    events, _ = build_payment_events(cache, index)
    assert len(events) == 1
    assert events[0].payment_date == date(2020, 1, 6)
    assert events[0].ex_date == date(2020, 1, 2)
    assert events[0].lag_source == "ticker"


def test_ticker_without_a_lag_falls_back_to_the_universe_median():
    index = pd.DatetimeIndex(pd.bdate_range("2020-01-01", "2020-06-30"))
    cache = _cache(
        {"AAA": [(date(2020, 1, 2), 1.0)], "BBB": [(date(2020, 1, 2), 1.0)]},
        {"AAA": {"lag_days": 20}},
    )
    events, report = build_payment_events(cache, index)
    by_ticker = {e.ticker: e for e in events}
    assert by_ticker["AAA"].lag_source == "ticker"
    assert by_ticker["BBB"].lag_source == "universe_median"
    assert by_ticker["BBB"].lag_days == 20
    assert report.n_events_on_universe_median_lag == 1


def test_event_whose_payment_falls_off_the_panel_is_dropped_not_clamped():
    """Clamping to the last day would pile a tail of unrelated payments onto
    one date and MANUFACTURE the largest dividend day in the sample -- which,
    on a top-N-of-252 rank, is exactly the day this family trades."""
    index = pd.DatetimeIndex(pd.bdate_range("2020-01-01", "2020-01-31"))
    cache = _cache({"AAA": [(date(2020, 1, 28), 1.0)]}, {"AAA": {"lag_days": 90}})
    events, _ = build_payment_events(cache, index)
    assert events == []


def test_event_whose_payment_falls_BEFORE_the_panel_is_dropped_not_clamped():
    """THE REGRESSION TEST FOR THE START-OF-PANEL GUARD THAT WAS MISSING IN THE
    FIRST BUILD. np.searchsorted returns 0 for a target before the panel, so
    every pre-panel payment was being assigned to the panel's FIRST trading day
    -- measured on the real calendar, 6,843 of 24,712 events (27.7%) landing on
    one date. On a top-N-of-252 rank that single date is exactly the kind of
    manufactured maximum this family trades on.

    KNOWN ANSWER: an ex-date two years before the panel starts must contribute
    NOTHING, while one inside the panel must still be kept."""
    index = pd.DatetimeIndex(pd.bdate_range("2020-01-01", "2020-12-31"))
    cache = _cache(
        {"AAA": [(date(2018, 3, 1), 1.0), (date(2020, 3, 2), 1.0)]},
        {"AAA": {"lag_days": 21}},
    )
    events, _ = build_payment_events(cache, index)
    assert len(events) == 1, "the 2018 payment predates the panel and must be dropped"
    assert events[0].ex_date == date(2020, 3, 2)
    assert events[0].payment_date >= index[0].date()


def test_no_lookahead_under_payment_dating():
    """THE POINT-IN-TIME CONTRACT. For the `payment` dating every dividend
    contributing to D_t must already have gone ex, so assert_no_lookahead must
    return exactly zero. Under `ex_date` dating it returns every event by
    construction -- which is the disclosed weakness of that arm, not a bug."""
    index = pd.DatetimeIndex(pd.bdate_range("2020-01-01", "2020-12-31"))
    cache = _cache(
        {"AAA": [(date(2020, 1, 2), 1.0), (date(2020, 4, 2), 1.0)]},
        {"AAA": {"lag_days": 21}},
    )
    events, _ = build_payment_events(cache, index)
    assert assert_no_lookahead(events, use_ex_date=False) == 0
    assert assert_no_lookahead(events, use_ex_date=True) == len(events)


# ---------------------------------------------------------------------------
# THE DOLLAR AGGREGATE AND THE SPLIT-BASIS JOIN
# ---------------------------------------------------------------------------


def _panel(n=10, tickers=("AAA", "BBB")):
    index = pd.DatetimeIndex(pd.bdate_range("2020-01-01", periods=n))
    close = pd.DataFrame(100.0, index=index, columns=list(tickers))
    shares = pd.DataFrame(1_000.0, index=index, columns=list(tickers))
    members = pd.DataFrame(True, index=index, columns=list(tickers))
    return index, close, shares, members


def test_dollar_aggregate_is_amount_times_shares_for_members_only():
    """KNOWN ANSWER: one $2.00/share payment by a firm with 1,000 shares is
    exactly $2,000 of dollar dividend on that day, and zero on every other."""
    index, _close, shares, members = _panel()
    events = [
        DividendPaymentEvent("AAA", date(2020, 1, 1), index[3].date(), 2.0, 21, "ticker"),
    ]
    dollars, skipped = build_daily_dividend_dollars(
        events, shares, members, index, use_ex_date=False
    )
    assert dollars.iloc[3] == pytest.approx(2_000.0)
    assert dollars.drop(dollars.index[3]).sum() == 0.0
    assert skipped["counted"] == 1


def test_non_member_and_missing_share_count_contribute_nothing_and_are_counted():
    """A per-share amount without a share count is not a dollar figure. It is
    dropped and COUNTED, never silently absorbed -- the count is a real
    downward bias on the aggregate's level and belongs in the run report."""
    index, _close, shares, members = _panel()
    members.loc[:, "BBB"] = False
    shares.loc[:, "AAA"] = np.nan
    events = [
        DividendPaymentEvent("AAA", date(2020, 1, 1), index[2].date(), 1.0, 21, "ticker"),
        DividendPaymentEvent("BBB", date(2020, 1, 1), index[2].date(), 1.0, 21, "ticker"),
        DividendPaymentEvent("CCC", date(2020, 1, 1), index[2].date(), 1.0, 21, "ticker"),
    ]
    dollars, skipped = build_daily_dividend_dollars(
        events, shares, members, index, use_ex_date=False
    )
    assert dollars.sum() == 0.0
    # FOUR DISTINCT BUCKETS, and the distinction matters: BBB was a real ticker
    # masked out by the point-in-time universe (the universe doing its job),
    # while CCC never resolved a price at all (a COVERAGE failure). Collapsing
    # them into one count would hide which of the two is doing the work.
    assert skipped["no_share_count"] == 1  # AAA: a member, but no share count
    assert skipped["not_a_member"] == 1  # BBB: priced, masked out that day
    assert skipped["absent_from_price_panel"] == 1  # CCC: never priced at all
    assert skipped["counted"] == 0


def test_aggregate_market_cap_is_price_times_shares_over_members():
    """KNOWN ANSWER: two members at $100 with 1,000 shares each is $200,000."""
    index, close, shares, members = _panel()
    cap = build_aggregate_market_cap(close, shares, members)
    assert cap.tolist() == pytest.approx([200_000.0] * len(cap))
    members.loc[:, "BBB"] = False
    halved = build_aggregate_market_cap(close, shares, members)
    assert halved.tolist() == pytest.approx([100_000.0] * len(halved))


def test_share_counts_are_split_adjusted_and_visibility_lagged():
    """THE SPLIT-BASIS HAZARD, pinned. SEC files the RAW count; Yahoo's Close
    and Yahoo's dividend amounts are in TODAY's share units. A 2:1 split must
    put the PRE-split count onto the post-split basis (double it), or every
    pre-split dividend dollar is understated by the split factor.

    Also pinned: a count is unreadable before its own AVAILABILITY date (as_of
    plus the provider's 90-day visibility lag), so the frame is NaN there."""
    index = pd.DatetimeIndex(pd.bdate_range("2020-01-01", "2021-12-31"))
    close = pd.DataFrame(100.0, index=index, columns=["AAA"])
    split_date = pd.Timestamp("2020-07-01")
    cache = _cache(
        {},
        {},
        share_counts={
            "AAA": [
                (date(2020, 1, 31), date(2020, 4, 30), 1_000.0),  # pre-split raw count
                (date(2020, 10, 31), date(2021, 1, 29), 2_000.0),  # post-split raw count
            ]
        },
    )
    splits = {"AAA": pd.Series([2.0], index=pd.DatetimeIndex([split_date]))}
    frame, no_counts = build_share_count_frame(cache, close, splits)
    assert no_counts == []

    # Before the first count is VISIBLE (2020-04-30) the frame must be NaN.
    assert np.isnan(frame.loc[pd.Timestamp("2020-03-02"), "AAA"])
    # After it, the PRE-split 1,000 must have been doubled onto the post-split
    # basis so it is comparable with the later 2,000.
    early = frame.loc[pd.Timestamp("2020-05-01"), "AAA"]
    late = frame.loc[pd.Timestamp("2021-06-01"), "AAA"]
    assert early == pytest.approx(2_000.0), (
        "a pre-split raw count must be split-adjusted onto today's share basis"
    )
    assert late == pytest.approx(2_000.0)


def test_ticker_with_no_share_counts_is_reported_not_silently_dropped():
    index = pd.DatetimeIndex(pd.bdate_range("2020-01-01", periods=30))
    close = pd.DataFrame(100.0, index=index, columns=["AAA", "BBB"])
    cache = _cache(
        {}, {}, share_counts={"AAA": [(date(2019, 1, 31), date(2019, 4, 30), 1_000.0)]}
    )
    frame, no_counts = build_share_count_frame(cache, close, {})
    assert no_counts == ["BBB"]
    assert "BBB" not in frame.columns


# ---------------------------------------------------------------------------
# THE SIGNALS AND THE REPLAY
# ---------------------------------------------------------------------------


def test_mktcap_signal_uses_the_PREVIOUS_days_market_cap():
    """[HS22] Table I, verbatim: "divided by the PREVIOUS DAY'S total market
    capitalization". The shift(1) is the paper's own timing.

    KNOWN ANSWER: with dollars [_, 10, 20] and caps [100, 1000, 1000], the
    signal at index 2 is (10+20)/cap[1] = 30/1000 = 0.03, NOT 30/1000 read off
    the same day by coincidence -- so the cap series is built to differ."""
    index = _index(3)
    dollars = pd.Series([0.0, 10.0, 20.0], index=index)
    caps = pd.Series([100.0, 1_000.0, 999_999.0], index=index)
    out = build_signal_series(dollars, caps, "mktcap")
    assert out.iloc[2] == pytest.approx(30.0 / 1_000.0)


def test_raw_signal_ignores_market_cap_entirely():
    """The `raw` definition is [HS22] Table II Panel B literally: no scaling."""
    index = _index(3)
    dollars = pd.Series([0.0, 10.0, 20.0], index=index)
    absurd_caps = pd.Series([1.0, 1e18, 1e-9], index=index)
    out = build_signal_series(dollars, absurd_caps, "raw")
    assert out.iloc[2] == pytest.approx(30.0)


def _synthetic_data(n=400, seed=7) -> DividendPressureData:
    index = pd.DatetimeIndex(pd.bdate_range("2018-01-01", periods=n))
    rng = np.random.default_rng(seed)
    close = pd.Series(100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n))), index=index)
    dollars = pd.Series(rng.gamma(2.0, 1e8, n), index=index)
    caps = pd.Series(4e13, index=index)
    signals = {}
    for key in ("raw", "mktcap", "abnormal", "future_ph"):
        for dating in DATINGS:
            signals[(key, dating)] = build_signal_series(dollars, caps, key)
    return DividendPressureData(
        market_close=close,
        market_returns=close.pct_change(fill_method=None),
        dollars_by_dating={d: dollars for d in DATINGS},
        aggregate_market_cap=caps,
        signals=signals,
        events=[],
        report=PaymentCalendarReport(),
        skip_counts={},
    )


def test_backtest_has_no_lookahead_a_future_only_shift_kills_the_return():
    """THE TIMING CONTRACT, tested rather than asserted: the position at index
    t earns the return at t+1. Shifting the MARKET RETURNS backward by one day
    must change the result -- if it did not, the replay would be reading the
    same day's return it formed on."""
    data = _synthetic_data()
    spec = next(s for s in DIVIDEND_PRESSURE_FAMILY if s.spec_id == "divpay_raw_payment_top63")
    config = DividendPressureConfig(cost_bps=0.0, short_borrow_bps_per_year=0.0,
                                    formation_start=date(2018, 1, 1))
    base = run_dividend_pressure_backtest(data, spec, config)
    assert base.status == "ok"

    shifted = DividendPressureData(
        **{**data.__dict__, "market_returns": data.market_returns.shift(-1)}
    )
    other = run_dividend_pressure_backtest(data=shifted, spec=spec, config=config)
    assert other.status == "ok"
    # Compared on the COMMON index: shifting the return series also changes how
    # many days are replayable, so a raw array comparison would fail on length
    # alone and would prove nothing about the pairing.
    common = base.daily_returns.index.intersection(other.daily_returns.index)
    assert len(common) > 50
    assert not np.allclose(
        base.daily_returns.reindex(common).to_numpy(),
        other.daily_returns.reindex(common).to_numpy(),
        equal_nan=True,
    ), "the replay must depend on WHICH day's return it pairs with a formation"


def test_costs_are_never_free_and_more_cost_is_never_better():
    data = _synthetic_data()
    spec = next(s for s in DIVIDEND_PRESSURE_FAMILY if s.spec_id == "divpay_raw_payment_top10")
    free = run_dividend_pressure_backtest(
        data, spec, DividendPressureConfig(0.0, 0.0, date(2018, 1, 1))
    )
    priced = run_dividend_pressure_backtest(
        data, spec, DividendPressureConfig(1.0, 34.0, date(2018, 1, 1))
    )
    expensive = run_dividend_pressure_backtest(
        data, spec, DividendPressureConfig(50.0, 34.0, date(2018, 1, 1))
    )
    assert free.total_cost == 0.0 and free.total_financing_cost == 0.0
    assert priced.total_cost > 0.0
    assert priced.daily_returns.sum() < free.daily_returns.sum()
    assert expensive.daily_returns.sum() < priced.daily_returns.sum()


def test_borrow_is_charged_on_the_short_notional_only():
    """The demeaned book is SHORT most days at N=10 (-10/252 on ~96% of them),
    which is why the borrow charge is the one that matters here. A book with no
    short exposure at all must accrue exactly zero financing."""
    data = _synthetic_data()
    spec = next(s for s in DIVIDEND_PRESSURE_FAMILY if s.spec_id == "divpay_raw_payment_top10")
    priced = run_dividend_pressure_backtest(
        data, spec, DividendPressureConfig(0.0, 34.0, date(2018, 1, 1))
    )
    assert priced.total_financing_cost > 0.0
    assert (priced.positions < 0).mean() > 0.5, "the N=10 demeaned book is short most days"


# ---------------------------------------------------------------------------
# THE POST-HOC BURN-IN DIAGNOSTIC
# ---------------------------------------------------------------------------


def test_abnormal_burn_in_diagnostic_separates_contaminated_from_clean_days():
    """The post-hoc corrective diagnostic that established F6's apparent
    scaling DISAGREEMENT to be this build's own burn-in artifact rather than a
    finding about the paper.

    KNOWN ANSWER on the day counts: a formation day's abnormal denominator
    averages trading days t-20..t-272, so a day is CONTAMINATED exactly when
    fewer than 272 formation days precede it. With a panel whose formation
    window starts at row `pad`, the contaminated count must be exactly
    ABNORMAL_LOOKBACK_DAYS, and the clean count the rest."""
    from app.services.research_lab.dividend_payment_pressure_timing import (
        post_hoc_abnormal_burn_in_diagnostic,
    )

    n = 1200
    pad = 400
    index = pd.DatetimeIndex(pd.bdate_range("2016-01-01", periods=n))
    formation_start = index[pad].date()

    rng = np.random.default_rng(11)
    close = pd.Series(100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n))), index=index)
    # THE DEFECT, REPRODUCED ON PURPOSE: the padding carries essentially no
    # dividend dollars (the real cause is SEC share counts only becoming
    # visible partway through), while the formation window carries real ones.
    dollars = pd.Series(rng.gamma(2.0, 1e8, n), index=index)
    dollars.iloc[:pad] = 0.0
    caps = pd.Series(4e13, index=index)

    signals = {}
    for key in ("raw", "mktcap", "abnormal", "future_ph"):
        for dating in DATINGS:
            signals[(key, dating)] = build_signal_series(dollars, caps, key)
    data = DividendPressureData(
        market_close=close,
        market_returns=close.pct_change(fill_method=None),
        dollars_by_dating={d: dollars for d in DATINGS},
        aggregate_market_cap=caps,
        signals=signals,
        events=[],
        report=PaymentCalendarReport(),
        skip_counts={},
    )

    out = post_hoc_abnormal_burn_in_diagnostic(
        data, dating="payment", formation_start=formation_start
    )
    assert out.n_formation_days == n - pad
    assert out.n_contaminated_days == ABNORMAL_LOOKBACK_DAYS
    assert out.n_clean_days == out.n_formation_days - ABNORMAL_LOOKBACK_DAYS
    assert out.padding_trading_days == pad
    assert out.padding_nonzero_dividend_days == 0
    assert out.padding_total_dollars == 0.0
    # The whole point: the artificial zero padding inflates the abnormal
    # signal's tail, and removing the contaminated days must shrink it.
    assert out.abnormal_max_as_run > out.abnormal_max_clean


def test_the_two_controls_use_genuinely_different_windows():
    """REGRESSION TEST FOR THE CONTROL-SPECIFICATION ERRATUM.

    The first build called turn_of_month_indicator() with its module defaults
    for BOTH controls, so tom_ctrl_1d and tom_ctrl_4d shared one indicator
    (measured on the real run: identical n_high = 419 and identical long-only
    Sharpe) and differed only in the demeaning constant. That did not implement
    the pre-registration, which specifies a genuine ONE-DAY window for
    tom_ctrl_1d, and it MATTERED: demeaning a 4-day indicator by 1/21 leaves a
    permanent +0.14 net-long tilt, so the spec's Sharpe was substantially the
    EQUITY PREMIUM -- precisely what the demeaned sizing exists to remove. It
    inflated that control from +0.19 to +0.44 and tripped a pre-declared veto
    that the correctly-specified control does not trip.

    KNOWN ANSWER: over a full year of business days the 1-day control fires
    exactly once per month and the 4-day control four times."""
    from app.services.research_lab.dividend_payment_pressure_timing import (
        turn_of_month_indicator as tom,
    )

    controls = {s.spec_id: s for s in DIVIDEND_PRESSURE_FAMILY if s.is_control}
    assert set(controls) == {"tom_ctrl_1d", "tom_ctrl_4d"}

    one, four = controls["tom_ctrl_1d"], controls["tom_ctrl_4d"]
    assert (one.tom_first_days, one.tom_last_days) == (1, 0)
    assert (four.tom_first_days, four.tom_last_days) == (
        TOM_WINDOW_FIRST_DAYS,
        TOM_WINDOW_LAST_DAYS,
    )

    index = pd.DatetimeIndex(pd.bdate_range("2020-01-01", "2020-12-31"))
    ind_one = tom(index, first_days=one.tom_first_days, last_days=one.tom_last_days)
    ind_four = tom(index, first_days=four.tom_first_days, last_days=four.tom_last_days)

    assert int(ind_one.sum()) == 12, "one high day per calendar month"
    assert int(ind_four.sum()) == 12 * (TOM_WINDOW_FIRST_DAYS + TOM_WINDOW_LAST_DAYS)
    assert not ind_one.equals(ind_four), "the two controls must not share an indicator"

    # THE DEMEANING CONSTANT MUST MATCH ITS OWN WINDOW. If it does not, the
    # spec carries a permanent directional tilt and its Sharpe is partly the
    # equity premium -- the exact defect this test exists to prevent.
    for spec, indicator in ((one, ind_one), (four, ind_four)):
        assert abs(indicator.mean() - spec.frequency) < 0.02, (
            f"{spec.spec_id}: realized frequency {indicator.mean():.4f} must match the "
            f"declared demeaning constant {spec.frequency:.4f}"
        )
        assert abs(demeaned_position(indicator, spec.frequency).mean()) < 0.02
