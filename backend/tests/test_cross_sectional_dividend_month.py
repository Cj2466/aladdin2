"""Tests for the dividend-month-premium family.

House convention, same as the sibling earnings-announcement and asset-growth
suites: SYNTHETIC fixtures are fine HERE (a test that needed the network
would not be a test), and are forbidden in the real screening run. Every
fixture below is hand-constructed so the expected answer is computable by
hand, and the assertions pin BEHAVIOUR the pre-registration commits to --
the grid's size, the forecast rule's exact month offsets, the point-in-time
guarantee, the price basis, and the diagnostics' status as diagnostics.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.cross_sectional_dividend_month import (
    DMP_ALTERNATIVE_RULES,
    DMP_COST_SENSITIVITY_BPS,
    DMP_EX_DAY_QUARTER_DAYS,
    DMP_FAMILY,
    DMP_FORECAST_LAGS,
    DMP_LEG_WEIGHTINGS,
    DMP_MIN_PRICE,
    DMP_MIN_PRIOR_EX_DATES,
    DMP_MONTHLY_MONTHS_THRESHOLD,
    DMP_N_TRIALS,
    DMP_PLACEBO_SHIFT_MONTHS,
    DMP_SHORT_LEGS,
    DMP_WINDOWS,
    DividendEvent,
    DmpConfig,
    DmpSpec,
    build_dmp_family,
    build_dmp_positions,
    build_ex_date_calendar,
    build_prior_ex_date_counts,
    classify_dividend_frequency,
    load_dividend_cache,
    measure_forecast_accuracy,
    month_end_rows,
    month_index,
    net_daily_returns,
    predict_dividend_months,
    qualifying_source_lags,
    run_dmp_backtest,
    run_ex_day_event_study,
    screen_dmp_family,
    shift_predictions,
)
from app.services.research_lab.global_effective_n import dsr_n_trials

# --- shared synthetic fixtures ---------------------------------------------


def trading_index(start: date, n_days: int) -> pd.DatetimeIndex:
    """Business days only -- the real panel has no weekends, and month_end_rows
    must pick the last BUSINESS day of a month, not the 31st."""
    return pd.DatetimeIndex(pd.bdate_range(start=start, periods=n_days))


def flat_prices(index: pd.DatetimeIndex, tickers: list[str], level: float = 100.0):
    return pd.DataFrame(level, index=index, columns=tickers, dtype=float)


def quarterly_events(ticker: str, first: date, n: int, amount: float = 1.0):
    """`n` ex-dates 91 calendar days apart -- a perfectly regular quarterly
    payer, so the 91-day projection is exact by construction and any error
    the tests see is the code's, not the fixture's."""
    return [
        DividendEvent(ticker=ticker, ex_date=first + timedelta(days=91 * k), amount=amount)
        for k in range(n)
    ]


def all_true_membership(index: pd.DatetimeIndex, tickers: list[str]) -> pd.DataFrame:
    return pd.DataFrame(True, index=index, columns=tickers)


# --- family shape: exactly these 12, no more, no fewer ---------------------


def test_family_is_exactly_12_definitions():
    assert len(DMP_FAMILY) == DMP_N_TRIALS == 12


def test_family_pattern_ids_are_exactly_the_expected_12_and_no_others():
    expected = {
        f"dmp_{short}_{weight}_{window}"
        for short in ("between", "within", "one_after")
        for weight in ("equal", "yield")
        for window in ("month", "toex")
    }
    assert {s.pattern_id for s in DMP_FAMILY} == expected


def test_family_covers_all_three_axes_exactly_once():
    seen = {(s.short_leg, s.leg_weighting, s.window) for s in DMP_FAMILY}
    assert len(seen) == len(DMP_FAMILY)
    assert {s.short_leg for s in DMP_FAMILY} == set(DMP_SHORT_LEGS)
    assert {s.leg_weighting for s in DMP_FAMILY} == set(DMP_LEG_WEIGHTINGS)
    assert {s.window for s in DMP_FAMILY} == set(DMP_WINDOWS)


def test_family_size_assertion_is_hard_not_documented(monkeypatch):
    """A drift in any axis must be a LOUD import-time failure, because it
    silently changes the DSR denominator for every future run."""
    monkeypatch.setattr(
        "app.services.research_lab.cross_sectional_dividend_month.DMP_WINDOWS",
        ("month", "toex", "sneaky_third"),
    )
    with pytest.raises(AssertionError, match="denominator"):
        build_dmp_family()


def test_family_meets_the_dsr_floor():
    from app.services.research_lab.deflated_sharpe import MIN_TRIALS_FOR_DSR

    assert DMP_N_TRIALS >= MIN_TRIALS_FOR_DSR


def test_every_spec_carries_the_verified_citation():
    for spec in DMP_FAMILY:
        assert "Hartzmark" in spec.citation
        assert "10.1016/j.jfineco.2013.02.015" in spec.citation


def test_the_citation_says_the_published_body_was_not_retrieved():
    """The whole tier discipline collapses if a later reader assumes the
    published JFE text was read. It was not; the citation must say so."""
    citation = DMP_FAMILY[0].citation
    assert "NOT retrieved" in citation
    assert "EFA 2012" in citation


def _normalized_module_doc() -> str:
    """The module docstring with runs of whitespace collapsed, so an
    assertion about a quoted sentence does not depend on where the line
    wrapping happens to fall."""
    from app.services.research_lab import cross_sectional_dividend_month as module

    return " ".join(module.__doc__.split())


def test_the_sharpe_contradiction_claim_stays_retracted():
    """An earlier revision asserted that [HS12] contradicts itself on Sharpe
    and used that to suppress every paper comparator. THE ASSERTION WAS
    WRONG -- the intro's 0.194 is annual-frequency and Table II's note says
    its own figures are monthly. This pins the retraction, because the
    tempting "cleanup" is to delete the whole embarrassing paragraph, which
    would also delete the comparator it was wrongly withholding."""
    doc = _normalized_module_doc()
    assert "RETRACTION" in doc
    assert "THE ASSERTION IS WRONG AND IS WITHDRAWN" in doc
    # The comparators it had been suppressing must actually be stated.
    for figure in ("0.194", "0.413", "0.097"):
        assert figure in doc, figure
    # The old claim may appear ONLY inside the retraction, where it is
    # quoted so a reader can see what was withdrawn -- never as a live
    # assertion elsewhere in the module.
    start = doc.index("*** RETRACTION")
    end = doc.index("THE COMPARATORS, now stated", start)
    retraction = doc[start:end]
    for stale in ("Those do not reconcile", "the word 'annual' appears to be wrong"):
        assert doc.count(stale) == retraction.count(stale) == 1, stale


def test_the_module_records_its_errata_rather_than_silently_repairing_them():
    """A family whose whole claim is 'we did not overstate' has to show its
    corrections. Pins that the errata section survives future edits."""
    doc = _normalized_module_doc()
    assert "ERRATA" in doc
    for marker in ("C1", "C2", "E1", "E2", "E3", "E4", "E5", "E6"):
        assert marker in doc, marker
    # The pre-registration must be left as committed, not retro-edited.
    assert "THE PRE-REGISTRATION IS LEFT AS COMMITTED" in doc


def test_the_module_records_both_build_brief_corrections():
    doc = _normalized_module_doc()
    # The title correction.
    assert "Slow Moving Capital" in doc
    assert "THE TITLE IS WRONG" in doc
    # The ex-date-vs-payment-date correction, which is the load-bearing one:
    # it is the difference between a quantity this project's data can
    # represent and one it cannot.
    assert "Dividend months refer to months with an ex-date unless otherwise noted." in doc
    assert "keyed on the EX-DIVIDEND DATE" in doc


# --- [HS12]'s forecast rule, quoted offsets ---------------------------------


def test_forecast_lags_are_exactly_the_papers_offsets():
    """Quoted rule: quarterly at t-3/t-6/t-9/t-12, semi-annual at t-6/t-12,
    annual at t-12. Pinned literally, because these four numbers ARE the
    method."""
    assert DMP_FORECAST_LAGS == {
        "quarterly": (3, 6, 9, 12),
        "semiannual": (6, 12),
        "annual": (12,),
    }


def test_monthly_payers_are_excluded_outright():
    """[HS12]: 'we exclude companies that paid a monthly dividend in the
    previous 12 months'. A monthly payer must get NO forecast lags at all,
    not merely a different set."""
    events = [
        DividendEvent("MO", date(2020, m, 10), 1.0) for m in range(1, 13)
    ]
    calendar = build_ex_date_calendar(events)["MO"]
    month = month_index(date(2021, 1, 1))
    assert classify_dividend_frequency(calendar, month) == "monthly"
    assert qualifying_source_lags(calendar, month) == ("monthly", ())


def test_frequency_classification_bands():
    month = month_index(date(2021, 1, 1))

    def freq(paying_months):
        events = [
            DividendEvent("X", date(2020, m, 10), 1.0) for m in paying_months
        ]
        # A ticker with no events at all is absent from the calendar
        # entirely, which is the same "not a payer" state an empty month map
        # represents -- classify it from an empty map rather than from a
        # KeyError.
        return classify_dividend_frequency(build_ex_date_calendar(events).get("X", {}), month)

    assert freq([]) == "none"
    assert freq([6]) == "annual"
    assert freq([3, 9]) == "semiannual"
    assert freq([3, 6, 9]) == "quarterly"
    assert freq([1, 4, 7, 10]) == "quarterly"
    assert freq(list(range(1, 13))) == "monthly"
    assert DMP_MONTHLY_MONTHS_THRESHOLD == 10


def test_a_quarterly_payer_qualifies_on_any_single_lag():
    """The rule is an OR across t-3/t-6/t-9/t-12, not an AND. One correctly
    lagged ex-date in the trailing year is enough -- this is what makes the
    adopted rule higher-recall and lower-precision than the naive t-12 rule,
    and the pre-registration turns on that trade-off."""
    month = month_index(date(2021, 4, 1))
    # Three ex-dates give a 'quarterly' classification; the one at t-12 is
    # what the rule then fires on.
    events = [
        DividendEvent("X", date(2020, 4, 10), 1.0),
        DividendEvent("X", date(2020, 7, 10), 1.0),
        DividendEvent("X", date(2020, 10, 10), 1.0),
    ]
    calendar = build_ex_date_calendar(events)["X"]
    frequency, lags = qualifying_source_lags(calendar, month)
    assert frequency == "quarterly"
    assert lags == (6, 9, 12)  # Oct, Jul, Apr 2020 -- but NOT t-3 (Jan 2021)


def test_frequency_window_is_closed_before_the_forecast_month():
    """Strictly point-in-time: a classification for month t must never read
    an ex-date in month t itself."""
    month = month_index(date(2021, 1, 1))
    with_current = [
        DividendEvent("X", date(2020, 6, 10), 1.0),
        DividendEvent("X", date(2021, 1, 10), 1.0),  # the forecast month itself
    ]
    calendar = build_ex_date_calendar(with_current)["X"]
    # Only the 2020-06 ex-date is inside t-12..t-1, so this is 'annual'. If
    # the window leaked forward it would count two and read 'semiannual'.
    assert classify_dividend_frequency(calendar, month) == "annual"


def test_every_prediction_sources_an_ex_date_at_least_three_months_old():
    """THE point-in-time guarantee. The shortest forecast lag is three
    months, so no prediction can read a distribution that had not yet
    happened."""
    events = quarterly_events("X", date(2015, 1, 15), 40)
    calendar = build_ex_date_calendar(events)
    predicted = predict_dividend_months(
        calendar, month_index(date(2016, 1, 1)), month_index(date(2024, 1, 1))
    )
    assert predicted["X"]
    for month, prediction in predicted["X"].items():
        assert prediction.source_lag >= 3
        assert month_index(prediction.source_ex_date) <= month - 3


def test_the_ex_day_projection_is_a_whole_number_of_weeks():
    """91/182/273/364 are all multiples of 7, which is what preserves day of
    week -- measured at 46.3% exact-day hits against 7.1% for calendar-month
    arithmetic, before the grid was frozen."""
    assert DMP_EX_DAY_QUARTER_DAYS == 91
    for lag in (3, 6, 9, 12):
        assert (DMP_EX_DAY_QUARTER_DAYS * lag // 3) % 7 == 0


def test_a_perfectly_regular_payer_is_projected_with_zero_error():
    events = quarterly_events("X", date(2015, 1, 15), 30)
    calendar = build_ex_date_calendar(events)
    actual = {month_index(e.ex_date): e.ex_date for e in events}
    predicted = predict_dividend_months(
        calendar, month_index(date(2016, 1, 1)), month_index(date(2020, 1, 1))
    )
    checked = 0
    for month, prediction in predicted["X"].items():
        if month in actual:
            assert prediction.predicted_ex_date == actual[month]
            assert not prediction.outside_month
            checked += 1
    assert checked > 10


def test_the_most_recent_qualifying_lag_is_used_as_the_projection_source():
    """When several lags qualify, the closest in time wins -- it is the least
    likely to have been overtaken by a schedule change."""
    events = quarterly_events("X", date(2019, 1, 15), 8)
    calendar = build_ex_date_calendar(events)
    predicted = predict_dividend_months(
        calendar, month_index(date(2020, 1, 1)), month_index(date(2020, 12, 1))
    )
    for prediction in predicted["X"].values():
        assert prediction.source_lag == 3


def test_prior_ex_date_counts_match_the_naive_sum_everywhere():
    """The prefix-sum optimisation must be behaviour-identical to the O(n)
    sum it replaced; it exists only because build_dmp_positions is called 24
    times per screening pass."""
    events = quarterly_events("X", date(2015, 2, 10), 20)
    calendar = build_ex_date_calendar(events)
    counts = build_prior_ex_date_counts(calendar)["X"]
    months = calendar["X"]
    for month in range(month_index(date(2013, 1, 1)), month_index(date(2023, 1, 1))):
        naive = sum(len(v) for k, v in months.items() if k < month)
        assert counts.before(month) == naive, month


# --- forecast accuracy is a DATES-ONLY measurement --------------------------


def test_forecast_accuracy_is_perfect_on_a_perfectly_regular_payer():
    events = quarterly_events("X", date(2015, 1, 15), 40)
    calendar = build_ex_date_calendar(events)
    accuracy = measure_forecast_accuracy(
        calendar, month_index(date(2017, 1, 1)), month_index(date(2023, 1, 1)), "hs13"
    )
    assert accuracy.precision == pytest.approx(1.0)
    assert accuracy.recall == pytest.approx(1.0)
    assert accuracy.n_false_positive == 0
    assert accuracy.n_false_negative == 0


def test_all_seven_alternative_rules_are_computable():
    events = quarterly_events("X", date(2015, 1, 15), 40)
    calendar = build_ex_date_calendar(events)
    for rule in DMP_ALTERNATIVE_RULES:
        accuracy = measure_forecast_accuracy(
            calendar, month_index(date(2018, 1, 1)), month_index(date(2022, 1, 1)), rule
        )
        assert accuracy.n_predicted >= 0
    assert "hs13" in DMP_ALTERNATIVE_RULES


def test_an_unknown_rule_raises_rather_than_silently_predicting_false():
    events = quarterly_events("X", date(2015, 1, 15), 8)
    calendar = build_ex_date_calendar(events)
    with pytest.raises(ValueError, match="unknown forecast rule"):
        measure_forecast_accuracy(
            calendar, month_index(date(2016, 1, 1)), month_index(date(2017, 1, 1)), "made_up"
        )


# --- month-end formation rows -----------------------------------------------


def test_month_end_rows_pick_the_last_business_day_of_each_month():
    index = trading_index(date(2020, 1, 1), 90)
    rows = month_end_rows(index)
    for month, position in rows:
        assert month_index(index[position].date()) == month
        if position + 1 < len(index):
            assert month_index(index[position + 1].date()) > month


# --- position construction and its gates ------------------------------------


def _one_ticker_setup(window: str = "month", short_leg: str = "between"):
    """One predicted payer (PAY) and one never-payer (NOPAY) over three
    years of business days."""
    index = trading_index(date(2015, 1, 1), 800)
    tickers = ["PAY", "NOPAY"]
    close = flat_prices(index, tickers)
    events = quarterly_events("PAY", date(2015, 1, 15), 12)
    calendar = build_ex_date_calendar(events)
    predicted = predict_dividend_months(
        calendar, month_index(index[0].date()), month_index(index[-1].date())
    )
    spec = DmpSpec(
        pattern_id="t",
        family="dividend_month_premium",
        citation="c",
        short_leg=short_leg,
        leg_weighting="equal",
        window=window,
    )
    return index, tickers, close, calendar, predicted, spec


def test_a_long_position_runs_from_formation_to_the_month_end_under_month():
    index, tickers, close, calendar, predicted, spec = _one_ticker_setup("month")
    positions, counts = build_dmp_positions(
        close,
        close,
        calendar,
        predicted,
        all_true_membership(index, tickers),
        date(2016, 1, 1),
        date(2017, 12, 31),
        spec,
        DmpConfig(),
    )
    longs = [p for p in positions if p.side == "long"]
    assert longs
    rows = dict(month_end_rows(index))
    for position in longs:
        assert position.exit_position == rows[position.month]


def test_the_toex_window_exits_no_later_than_the_month_window():
    index, tickers, close, calendar, predicted, _ = _one_ticker_setup()
    membership = all_true_membership(index, tickers)
    config = DmpConfig()
    by_window = {}
    for window in ("month", "toex"):
        spec = DmpSpec("t", "f", "c", "between", "equal", window)
        positions, _ = build_dmp_positions(
            close, close, calendar, predicted, membership,
            date(2016, 1, 1), date(2017, 12, 31), spec, config,
        )
        by_window[window] = {
            (p.ticker, p.month): p.exit_position for p in positions if p.side == "long"
        }
    assert by_window["toex"]
    assert set(by_window["toex"]) == set(by_window["month"])
    for key, toex_exit in by_window["toex"].items():
        assert toex_exit <= by_window["month"][key]
    # And at least one is STRICTLY earlier, or the axis is doing nothing.
    assert any(
        by_window["toex"][k] < by_window["month"][k] for k in by_window["toex"]
    )


def test_the_short_leg_always_runs_the_full_month_whatever_the_window():
    index, tickers, close, calendar, predicted, _ = _one_ticker_setup()
    membership = all_true_membership(index, tickers)
    rows = dict(month_end_rows(index))
    for window in ("month", "toex"):
        spec = DmpSpec("t", "f", "c", "between", "equal", window)
        positions, _ = build_dmp_positions(
            close, close, calendar, predicted, membership,
            date(2016, 1, 1), date(2017, 12, 31), spec, DmpConfig(),
        )
        shorts = [p for p in positions if p.side == "short"]
        assert shorts
        for position in shorts:
            assert position.exit_position == rows[position.month]


def test_a_name_is_never_long_and_short_in_the_same_month():
    index, tickers, close, calendar, predicted, spec = _one_ticker_setup()
    positions, _ = build_dmp_positions(
        close, close, calendar, predicted, all_true_membership(index, tickers),
        date(2016, 1, 1), date(2017, 12, 31), spec, DmpConfig(),
    )
    seen: dict[tuple[str, int], str] = {}
    for position in positions:
        key = (position.ticker, position.month)
        assert key not in seen, f"{key} appears twice: {seen.get(key)} and {position.side}"
        seen[key] = position.side


def test_the_between_short_leg_does_NOT_include_never_payers_the_known_defect():
    index, tickers, close, calendar, predicted, spec = _one_ticker_setup(
        short_leg="between"
    )
    positions, _ = build_dmp_positions(
        close, close, calendar, predicted, all_true_membership(index, tickers),
        date(2016, 1, 1), date(2017, 12, 31), spec, DmpConfig(),
    )
    # NOPAY has no dividend history at all, so it fails the min-prior-ex-dates
    # gate and is not in ANY leg -- that gate is applied to both legs on
    # purpose, so all twelve specs trade the identical population.
    assert not any(p.ticker == "NOPAY" for p in positions)


def test_the_within_short_leg_excludes_firms_with_no_recent_dividend():
    """'within companies' = paid in the last 12 months but not predicted this
    month. A firm whose dividend history stopped a year ago must drop out of
    the short pool, which is what makes this leg the paper's risk test."""
    index = trading_index(date(2015, 1, 1), 1000)
    tickers = ["A", "B"]
    close = flat_prices(index, tickers)
    # A pays throughout; B stops paying after early 2016.
    events = quarterly_events("A", date(2015, 1, 15), 16) + quarterly_events(
        "B", date(2015, 1, 20), 5
    )
    calendar = build_ex_date_calendar(events)
    predicted = predict_dividend_months(
        calendar, month_index(index[0].date()), month_index(index[-1].date())
    )
    membership = all_true_membership(index, tickers)
    shorts = {}
    for short_leg in ("between", "within"):
        spec = DmpSpec("t", "f", "c", short_leg, "equal", "month")
        positions, _ = build_dmp_positions(
            close, close, calendar, predicted, membership,
            date(2017, 6, 1), date(2018, 6, 30), spec, DmpConfig(),
        )
        shorts[short_leg] = {p.ticker for p in positions if p.side == "short"}
    # By mid-2017 B has not paid for over a year: it can still be shorted
    # under 'between' but must be gone from 'within'.
    assert "B" in shorts["between"]
    assert "B" not in shorts["within"]


def test_the_one_after_short_leg_is_only_the_month_after_a_prediction():
    index, tickers, close, calendar, predicted, _ = _one_ticker_setup()
    membership = all_true_membership(index, tickers)
    spec = DmpSpec("t", "f", "c", "one_after", "equal", "month")
    positions, _ = build_dmp_positions(
        close, close, calendar, predicted, membership,
        date(2016, 1, 1), date(2017, 12, 31), spec, DmpConfig(),
    )
    shorts = [p for p in positions if p.side == "short"]
    assert shorts
    for position in shorts:
        assert position.month - 1 in predicted[position.ticker]


def test_a_non_member_is_gated_out_and_counted():
    index, tickers, close, calendar, predicted, spec = _one_ticker_setup()
    membership = all_true_membership(index, tickers)
    membership["PAY"] = False
    positions, counts = build_dmp_positions(
        close, close, calendar, predicted, membership,
        date(2016, 1, 1), date(2017, 12, 31), spec, DmpConfig(),
    )
    assert not any(p.ticker == "PAY" for p in positions)
    assert counts.n_not_member > 0


def test_the_five_dollar_price_screen_binds_and_is_counted():
    """[HS12]'s own screen. It reads the SPLIT-ADJUSTED price, not the
    total-return one."""
    index, tickers, close, calendar, predicted, spec = _one_ticker_setup()
    price_only = close.copy()
    price_only["PAY"] = DMP_MIN_PRICE - 0.01
    positions, counts = build_dmp_positions(
        close, price_only, calendar, predicted, all_true_membership(index, tickers),
        date(2016, 1, 1), date(2017, 12, 31), spec, DmpConfig(),
    )
    assert not any(p.ticker == "PAY" for p in positions)
    assert counts.n_below_price_screen > 0


def test_a_firm_with_too_little_history_is_never_traded():
    index = trading_index(date(2015, 1, 1), 800)
    tickers = ["THIN"]
    close = flat_prices(index, tickers)
    # Exactly one fewer ex-date than the gate requires, all before 2016.
    events = quarterly_events("THIN", date(2015, 1, 15), DMP_MIN_PRIOR_EX_DATES - 1)
    calendar = build_ex_date_calendar(events)
    predicted = predict_dividend_months(
        calendar, month_index(index[0].date()), month_index(index[-1].date())
    )
    spec = DmpSpec("t", "f", "c", "between", "equal", "month")
    positions, counts = build_dmp_positions(
        close, close, calendar, predicted, all_true_membership(index, tickers),
        date(2016, 1, 1), date(2016, 6, 30), spec, DmpConfig(),
    )
    assert positions == []
    assert counts.n_thin_history > 0


def test_the_min_history_gate_is_identical_across_every_spec():
    """Applied UNIFORMLY so all twelve specs trade the IDENTICAL population
    and differ only in short leg, weighting and window. Without that, the
    sigma_SR feeding the DSR would measure universe differences rather than
    spec differences."""
    index, tickers, close, calendar, predicted, _ = _one_ticker_setup()
    membership = all_true_membership(index, tickers)
    long_sets = []
    for spec in DMP_FAMILY:
        positions, _ = build_dmp_positions(
            close, close, calendar, predicted, membership,
            date(2016, 1, 1), date(2017, 12, 31), spec, DmpConfig(),
        )
        long_sets.append({(p.ticker, p.month) for p in positions if p.side == "long"})
    assert all(s == long_sets[0] for s in long_sets)


def test_caught_actual_is_a_diagnostic_and_never_a_filter():
    """A prediction that lands in a month with no real ex-date must still be
    TRADED -- an ex-ante family cannot know it missed."""
    index = trading_index(date(2015, 1, 1), 900)
    tickers = ["X"]
    close = flat_prices(index, tickers)
    # Regular through early 2016, then the payments stop -- so 2016-2017
    # predictions keep firing against months with no real ex-date.
    events = quarterly_events("X", date(2015, 1, 15), 6)
    calendar = build_ex_date_calendar(events)
    predicted = predict_dividend_months(
        calendar, month_index(index[0].date()), month_index(index[-1].date())
    )
    spec = DmpSpec("t", "f", "c", "between", "equal", "month")
    positions, counts = build_dmp_positions(
        close, close, calendar, predicted, all_true_membership(index, tickers),
        date(2016, 6, 1), date(2017, 6, 30), spec, DmpConfig(),
    )
    longs = [p for p in positions if p.side == "long"]
    assert longs, "predictions must still be traded after the real payments stop"
    assert any(not p.caught_actual for p in longs)
    assert counts.n_long_caught_actual < counts.n_long


# --- the replay --------------------------------------------------------------


def _two_name_replay(long_return: float, short_return: float, weighting="equal"):
    """A book with one long and one short name, each moving a fixed amount
    every day, so the expected gross daily return is exactly
    long_return - short_return."""
    index = trading_index(date(2020, 1, 1), 120)
    tickers = ["L", "S"]
    close = pd.DataFrame(
        {
            "L": 100.0 * (1.0 + long_return) ** np.arange(len(index)),
            "S": 100.0 * (1.0 + short_return) ** np.arange(len(index)),
        },
        index=index,
    )
    from app.services.research_lab.cross_sectional_dividend_month import DmpPosition

    positions = [
        DmpPosition("L", 0, "long", 0, len(index) - 1, 0.02, True),
        DmpPosition("S", 0, "short", 0, len(index) - 1, float("nan"), False),
    ]
    spec = DmpSpec("t", "f", "c", "between", weighting, "month")
    return close, positions, spec


def test_long_minus_short_is_the_daily_return():
    close, positions, spec = _two_name_replay(0.002, 0.001)
    replay = run_dmp_backtest(close, positions, spec, DmpConfig(impute_delisting_returns=False))
    assert replay.status == "ok"
    assert replay.gross_daily_returns.iloc[5] == pytest.approx(0.002 - 0.001)


def test_the_position_spans_entry_plus_one_through_exit():
    """A position formed at the close of row e first earns a return on row
    e+1 -- the same convention the sibling earnings-premium family states."""
    close, positions, spec = _two_name_replay(0.002, 0.001)
    replay = run_dmp_backtest(close, positions, spec, DmpConfig(impute_delisting_returns=False))
    assert replay.gross_daily_returns.index[0] == close.index[1]
    assert replay.gross_daily_returns.index[-1] == close.index[len(close) - 1]


def test_a_day_with_no_long_leg_is_flat_by_design_and_counted():
    """Not hypothetical under 'toex': every long position closes on or
    before its predicted ex-day, so a month's tail can genuinely have no
    long leg left. It must be 0.0 and counted, never a naked short."""
    index = trading_index(date(2020, 1, 1), 120)
    close = pd.DataFrame(
        {"L": np.linspace(100, 130, len(index)), "S": np.linspace(100, 80, len(index))},
        index=index,
    )
    from app.services.research_lab.cross_sectional_dividend_month import DmpPosition

    positions = [
        DmpPosition("L", 0, "long", 0, 20, 0.02, True),
        DmpPosition("S", 0, "short", 0, len(index) - 1, float("nan"), False),
    ]
    spec = DmpSpec("t", "f", "c", "between", "equal", "toex")
    replay = run_dmp_backtest(close, positions, spec, DmpConfig(impute_delisting_returns=False))
    assert replay.n_one_sided_days > 0
    # Every day after the long leg closes contributes exactly 0.0, despite
    # the short name falling steadily -- which it would have profited from.
    assert replay.gross_daily_returns.iloc[25:].abs().sum() == pytest.approx(0.0)


def test_yield_weighting_is_proportional_to_yield_not_inverse_to_it():
    """[HS12] reports higher dividend yield driving LARGER interim and ex-day
    returns, so the theory-implied weighting is proportional. The harness's
    generic basis path is named 'inverse_vol' for historical reasons and
    performs no inversion -- this test is what stops that name from being
    read as an instruction."""
    index = trading_index(date(2020, 1, 1), 120)
    close = pd.DataFrame(
        {
            "HIGH": 100.0 * (1.0 + 0.01) ** np.arange(len(index)),
            "LOW": 100.0 * np.ones(len(index)),
            "S": 100.0 * np.ones(len(index)),
        },
        index=index,
    )
    from app.services.research_lab.cross_sectional_dividend_month import DmpPosition

    positions = [
        DmpPosition("HIGH", 0, "long", 0, len(index) - 1, 0.05, True),
        DmpPosition("LOW", 0, "long", 0, len(index) - 1, 0.01, True),
        DmpPosition("S", 0, "short", 0, len(index) - 1, float("nan"), False),
    ]
    config = DmpConfig(impute_delisting_returns=False)
    equal = run_dmp_backtest(
        close, positions, DmpSpec("t", "f", "c", "between", "equal", "month"), config
    )
    weighted = run_dmp_backtest(
        close, positions, DmpSpec("t", "f", "c", "between", "yield", "month"), config
    )
    # HIGH is the only name that moves, and it has the higher yield, so
    # proportional weighting must earn MORE than equal weighting.
    assert weighted.gross_daily_returns.mean() > equal.gross_daily_returns.mean()


def test_zero_cost_net_equals_gross():
    close, positions, spec = _two_name_replay(0.002, 0.001)
    replay = run_dmp_backtest(close, positions, spec, DmpConfig(impute_delisting_returns=False))
    net = net_daily_returns(replay, 0.0, 0.0)
    pd.testing.assert_series_equal(net, replay.gross_daily_returns)


def test_higher_cost_never_produces_a_higher_net_return():
    close, positions, spec = _two_name_replay(0.002, 0.001)
    replay = run_dmp_backtest(close, positions, spec, DmpConfig(impute_delisting_returns=False))
    totals = [net_daily_returns(replay, bps, 0.0).sum() for bps in DMP_COST_SENSITIVITY_BPS]
    assert totals == sorted(totals, reverse=True)


def test_turnover_is_recorded_so_the_cost_ladder_shares_one_position_path():
    close, positions, spec = _two_name_replay(0.002, 0.001)
    replay = run_dmp_backtest(close, positions, spec, DmpConfig(impute_delisting_returns=False))
    assert len(replay.daily_turnover) == len(replay.gross_daily_returns)
    # Entry day charges the full two units of notional; steady state charges
    # nothing, because neither leg's membership changes.
    assert replay.daily_turnover.iloc[0] == pytest.approx(2.0)
    assert replay.daily_turnover.iloc[5] == pytest.approx(0.0)


def test_no_positions_is_a_status_not_a_crash():
    index = trading_index(date(2020, 1, 1), 60)
    close = flat_prices(index, ["A"])
    spec = DmpSpec("t", "f", "c", "between", "equal", "month")
    replay = run_dmp_backtest(close, [], spec, DmpConfig())
    assert replay.status == "no_positions"
    assert replay.gross_daily_returns.empty


def test_delisting_mid_hold_is_charged_the_shumway_return():
    from app.services.research_lab.cross_sectional import DEFAULT_IMPUTED_DELISTING_RETURN
    from app.services.research_lab.cross_sectional_dividend_month import DmpPosition

    index = trading_index(date(2020, 1, 1), 120)
    close = pd.DataFrame(
        {"L": np.full(len(index), 100.0), "S": np.full(len(index), 100.0)}, index=index
    )
    close.iloc[60:, close.columns.get_loc("L")] = np.nan
    positions = [
        DmpPosition("L", 0, "long", 0, len(index) - 1, 0.02, True),
        DmpPosition("S", 0, "short", 0, len(index) - 1, float("nan"), False),
    ]
    spec = DmpSpec("t", "f", "c", "between", "equal", "month")
    replay = run_dmp_backtest(close, positions, spec, DmpConfig(impute_delisting_returns=True))
    assert replay.n_delisted_mid_hold == 1
    assert replay.gross_daily_returns.iloc[59] == pytest.approx(
        DEFAULT_IMPUTED_DELISTING_RETURN
    )


def test_delisting_imputation_can_be_turned_off():
    from app.services.research_lab.cross_sectional_dividend_month import DmpPosition

    index = trading_index(date(2020, 1, 1), 120)
    close = pd.DataFrame(
        {"L": np.full(len(index), 100.0), "S": np.full(len(index), 100.0)}, index=index
    )
    close.iloc[60:, close.columns.get_loc("L")] = np.nan
    positions = [
        DmpPosition("L", 0, "long", 0, len(index) - 1, 0.02, True),
        DmpPosition("S", 0, "short", 0, len(index) - 1, float("nan"), False),
    ]
    spec = DmpSpec("t", "f", "c", "between", "equal", "month")
    replay = run_dmp_backtest(close, positions, spec, DmpConfig(impute_delisting_returns=False))
    assert replay.n_delisted_mid_hold == 0


# --- the placebo -------------------------------------------------------------


def test_the_placebo_shift_is_one_month_not_six():
    """A quarterly payer's ex-months are t, t+3, t+6, t+9 -- so a six-month
    shift would land on ANOTHER real payment month and the 'placebo' would
    be a live book. One month lands between payments."""
    assert DMP_PLACEBO_SHIFT_MONTHS == 1


def test_shifted_predictions_land_where_the_firm_is_not_due():
    events = quarterly_events("X", date(2015, 1, 15), 30)
    calendar = build_ex_date_calendar(events)
    predicted = predict_dividend_months(
        calendar, month_index(date(2016, 1, 1)), month_index(date(2020, 1, 1))
    )
    shifted = shift_predictions(predicted, DMP_PLACEBO_SHIFT_MONTHS)
    real_months = {month_index(e.ex_date) for e in events}
    assert shifted["X"]
    # Not one shifted prediction may sit on a month the firm really went ex.
    assert not (set(shifted["X"]) & real_months)


def test_shifted_predictions_recompute_outside_month():
    """A projection that sat inside its original month does not sit inside
    the shifted one; getting that wrong would make the placebo trade a
    systematically different window shape from the live book."""
    events = quarterly_events("X", date(2015, 1, 15), 30)
    calendar = build_ex_date_calendar(events)
    predicted = predict_dividend_months(
        calendar, month_index(date(2016, 1, 1)), month_index(date(2020, 1, 1))
    )
    shifted = shift_predictions(predicted, DMP_PLACEBO_SHIFT_MONTHS)
    for month, prediction in shifted["X"].items():
        assert prediction.month == month
        assert prediction.outside_month == (month_index(prediction.predicted_ex_date) != month)


# --- the ex-day event study --------------------------------------------------


def test_the_event_study_recovers_a_planted_run_up_and_reversal():
    """A synthetic firm that outperforms the universe by a fixed amount on
    each of the five days before its ex-day and underperforms by the same
    amount on each of the five days after must show a positive run-up and a
    negative reversal of matching size."""
    index = trading_index(date(2020, 1, 1), 400)
    tickers = ["X", "A", "B"]
    rng = np.random.default_rng(0)
    base = pd.DataFrame(
        100.0 * np.cumprod(1.0 + rng.normal(0, 0.001, size=(len(index), 3)), axis=0),
        index=index,
        columns=tickers,
    )
    ex_dates = [index[100].date(), index[190].date(), index[280].date()]
    bump = 0.001
    x = base["X"].to_numpy().copy()
    for ex_date in ex_dates:
        day0 = int(np.searchsorted(index.values, pd.Timestamp(ex_date).to_datetime64()))
        for offset in range(-4, 1):
            x[day0 + offset :] *= 1.0 + bump
        for offset in range(1, 6):
            x[day0 + offset :] *= 1.0 - bump
    base["X"] = x
    calendar = build_ex_date_calendar(
        [DividendEvent("X", d, 1.0) for d in ex_dates]
    )
    study = run_ex_day_event_study(
        base,
        calendar,
        all_true_membership(index, tickers),
        index[0].date(),
        index[-1].date(),
        window=(-10, 10),
    )
    assert study.n_events == 3
    assert study.run_up_bps > 30.0
    assert study.reversal_bps < -30.0


def test_the_event_study_is_hedged_so_a_pure_market_move_nets_to_zero():
    """If every name moves together, the excess return is zero at every
    offset -- otherwise the study would report market drift as a dividend
    effect."""
    index = trading_index(date(2020, 1, 1), 300)
    tickers = ["X", "A", "B"]
    path = 100.0 * (1.0 + 0.002) ** np.arange(len(index))
    close = pd.DataFrame({t: path for t in tickers}, index=index)
    calendar = build_ex_date_calendar([DividendEvent("X", index[150].date(), 1.0)])
    study = run_ex_day_event_study(
        close, calendar, all_true_membership(index, tickers),
        index[0].date(), index[-1].date(), window=(-5, 5),
    )
    assert study.n_events == 1
    assert study.run_up_bps == pytest.approx(0.0, abs=1e-6)
    assert study.reversal_bps == pytest.approx(0.0, abs=1e-6)


def test_the_clustered_t_is_the_conservative_one_when_events_cluster():
    """Ex-dates cluster into four seasonal pairs, so events sharing a month
    share most of their market exposure. The clustered t must not simply
    equal the naive one on clustered data -- otherwise reporting it would be
    security theatre."""
    from app.services.research_lab.cross_sectional_dividend_month import (
        _clustered_t_statistic,
        _t_statistic,
    )

    rng = np.random.default_rng(3)
    # 40 clusters of 50 observations; the signal is a per-CLUSTER shock, so
    # the 2,000 observations carry only 40 clusters' worth of information.
    cluster_effect = rng.normal(0.5, 1.0, size=40)
    values = np.concatenate([np.full(50, effect) for effect in cluster_effect])
    clusters = np.concatenate([np.full(50, i) for i in range(40)])
    naive = _t_statistic(values)
    clustered = _clustered_t_statistic(values, clusters)
    assert abs(clustered) < abs(naive)
    # The clustered figure is exactly the t across the 40 cluster means.
    expected = cluster_effect.mean() / cluster_effect.std(ddof=1) * np.sqrt(40)
    assert clustered == pytest.approx(expected)


def test_t_statistics_degrade_to_nan_rather_than_dividing_by_zero():
    from app.services.research_lab.cross_sectional_dividend_month import (
        _clustered_t_statistic,
        _t_statistic,
    )

    assert np.isnan(_t_statistic(np.array([1.0])))
    assert np.isnan(_t_statistic(np.array([2.0, 2.0, 2.0])))  # zero variance
    assert np.isnan(_clustered_t_statistic(np.array([1.0, 2.0]), np.array([0, 0])))


def test_the_event_study_reports_the_round_trip_not_just_its_two_halves():
    """[HS12]'s claim is that the reversal is 'large enough to offset the
    gains during the dividend month'. That is a claim about the SUM, so the
    sum has to be reported -- a run-up and a reversal quoted separately can
    be read as two findings when they are one."""
    index = trading_index(date(2020, 1, 1), 300)
    tickers = ["X", "A"]
    close = flat_prices(index, tickers)
    calendar = build_ex_date_calendar([DividendEvent("X", index[150].date(), 1.0)])
    study = run_ex_day_event_study(
        close, calendar, all_true_membership(index, tickers),
        index[0].date(), index[-1].date(), window=(-5, 5),
    )
    assert study.n_complete_events == 1
    assert study.net_bps == pytest.approx(study.run_up_bps + study.reversal_bps, abs=1e-6)


def test_the_earnings_confound_is_unavailable_rather_than_zero_without_a_calendar():
    """A missing announcement calendar must produce available=False and NaNs,
    so the report says NOT COMPUTED. Printing zeros would read as 'no
    contamination', which is the opposite of the truth."""
    from app.services.research_lab.cross_sectional_dividend_month import (
        measure_earnings_confound,
    )

    index = trading_index(date(2020, 1, 1), 200)
    tickers = ["X", "A"]
    close = flat_prices(index, tickers)
    calendar = build_ex_date_calendar([DividendEvent("X", index[100].date(), 1.0)])
    for empty in (None, {}):
        diagnostic = measure_earnings_confound(
            close, calendar, all_true_membership(index, tickers), empty,
            index[0].date(), index[-1].date(),
        )
        assert diagnostic.available is False
        assert np.isnan(diagnostic.fraction_window_contains_announcement)


def test_the_earnings_confound_splits_events_on_window_containment():
    """One ex-date with an announcement inside its window and one without
    must land in different buckets, and the 'all' row must cover both."""
    from app.services.research_lab.cross_sectional_dividend_month import (
        measure_earnings_confound,
    )

    index = trading_index(date(2020, 1, 1), 400)
    tickers = ["X", "A"]
    rng = np.random.default_rng(11)
    close = pd.DataFrame(
        100.0 * np.cumprod(1.0 + rng.normal(0, 0.005, size=(len(index), 2)), axis=0),
        index=index,
        columns=tickers,
    )
    dirty_ex, clean_ex = index[100].date(), index[250].date()
    calendar = build_ex_date_calendar(
        [DividendEvent("X", dirty_ex, 1.0), DividendEvent("X", clean_ex, 1.0)]
    )
    # One announcement 5 rows before the first ex-date (inside -20..+40) and
    # none anywhere near the second.
    announcements = {"X": [index[95].date()]}
    diagnostic = measure_earnings_confound(
        close, calendar, all_true_membership(index, tickers), announcements,
        index[0].date(), index[-1].date(),
    )
    assert diagnostic.available is True
    assert diagnostic.n_all_events == 2
    assert diagnostic.n_clean_events == 1
    assert diagnostic.fraction_window_contains_announcement == pytest.approx(0.5)


def test_the_earnings_confound_computes_no_portfolio_and_is_not_a_spec():
    """It is a diagnostic: it must not appear in the family, must not change
    n_trials, and must not be reachable from position formation."""
    import inspect

    from app.services.research_lab.cross_sectional_dividend_month import (
        measure_earnings_confound,
    )

    source = inspect.getsource(measure_earnings_confound)
    for forbidden in ("sharpe", "Sharpe", "DmpPosition", "run_dmp_backtest", "deflated"):
        assert forbidden not in source, forbidden
    assert "earnings" not in " ".join(s.pattern_id for s in DMP_FAMILY)
    assert DMP_N_TRIALS == 12


def test_the_event_study_headline_halves_sum_to_its_round_trip():
    """M1 REGRESSION. An earlier revision derived the run-up and reversal
    from the per-offset curve (averaged over every event with data at that
    offset) while computing the t-statistics and the round trip on the
    COMPLETE-window subset. Three numbers, two populations, and they did not
    add up: +12.02 and -18.35 against a round trip of -5.24, which is -6.33.
    Everything reported as a headline now comes from one population."""
    index = trading_index(date(2020, 1, 1), 500)
    tickers = ["X", "Y", "A"]
    rng = np.random.default_rng(21)
    close = pd.DataFrame(
        100.0 * np.cumprod(1.0 + rng.normal(0, 0.008, size=(len(index), 3)), axis=0),
        index=index,
        columns=tickers,
    )
    # Y has a price gap inside one of its windows, so that event contributes
    # to the per-offset curve at the offsets it does have but NOT to the
    # complete-window population -- which is exactly the split that produced
    # the original mismatch.
    close.iloc[145:150, close.columns.get_loc("Y")] = np.nan
    calendar = build_ex_date_calendar(
        [
            DividendEvent("X", index[120].date(), 1.0),
            DividendEvent("X", index[300].date(), 1.0),
            DividendEvent("Y", index[140].date(), 1.0),
            DividendEvent("Y", index[360].date(), 1.0),
        ]
    )
    study = run_ex_day_event_study(
        close, calendar, all_true_membership(index, tickers),
        index[0].date(), index[-1].date(),
    )
    assert study.n_complete_events < study.n_events, "fixture must exercise the gap"
    assert study.run_up_bps + study.reversal_bps == pytest.approx(study.net_bps, abs=1e-9)


def test_no_short_leg_ever_holds_a_monthly_payer():
    """The pre-registration freezes monthly-payer exclusion as a family-wide
    constant. An earlier revision applied it to 'within' and 'one_after' but
    not to 'between'."""
    index = trading_index(date(2015, 1, 1), 1100)
    tickers = ["MO", "Q"]
    close = flat_prices(index, tickers)
    events = [
        DividendEvent("MO", date(2015 + (m - 1) // 12, (m - 1) % 12 + 1, 12), 0.1)
        for m in range(1, 37)
    ] + quarterly_events("Q", date(2015, 1, 20), 16)
    calendar = build_ex_date_calendar(events)
    predicted = predict_dividend_months(
        calendar, month_index(index[0].date()), month_index(index[-1].date())
    )
    membership = all_true_membership(index, tickers)
    for spec in DMP_FAMILY:
        positions, _ = build_dmp_positions(
            close, close, calendar, predicted, membership,
            date(2016, 6, 1), date(2017, 6, 30), spec, DmpConfig(),
        )
        assert not any(p.ticker == "MO" for p in positions), spec.pattern_id


def test_the_event_study_never_reaches_into_position_formation():
    """It is computed with hindsight on ACTUAL ex-dates, so it must not be
    an input to anything the book does. Pinned structurally: the position
    builder's signature does not accept an event study, and its output
    depends only on predictions."""
    import inspect

    signature = inspect.signature(build_dmp_positions)
    assert "event_study" not in signature.parameters
    assert "ExDayEventStudy" not in str(signature)


# --- screening / DSR ---------------------------------------------------------


def _screening_fixture(n_tickers: int = 8, n_days: int = 1500):
    index = trading_index(date(2015, 1, 1), n_days)
    tickers = [f"T{i}" for i in range(n_tickers)]
    rng = np.random.default_rng(7)
    close = pd.DataFrame(
        100.0 * np.cumprod(1.0 + rng.normal(0, 0.01, size=(len(index), n_tickers)), axis=0),
        index=index,
        columns=tickers,
    )
    events: list[DividendEvent] = []
    for i, ticker in enumerate(tickers):
        # Stagger the quarterly cycles so some names are predicted in any
        # given month and others are not.
        events.extend(
            quarterly_events(ticker, date(2015, 1, 10) + timedelta(days=30 * (i % 3)), 24)
        )
    calendar = build_ex_date_calendar(events)
    predicted = predict_dividend_months(
        calendar, month_index(index[0].date()), month_index(index[-1].date())
    )
    return index, tickers, close, calendar, predicted


def test_screening_returns_one_result_per_spec_with_the_declared_denominator():
    index, tickers, close, calendar, predicted = _screening_fixture()
    results, placebo = screen_dmp_family(
        close, close, calendar, predicted, all_true_membership(index, tickers),
        date(2016, 1, 1), date(2020, 12, 31), DmpConfig(),
    )
    assert len(results) == DMP_N_TRIALS
    assert {r.pattern_id for r in results} == {s.pattern_id for s in DMP_FAMILY}
    for result in results:
        assert result.deflated_sharpe.n_trials == DMP_N_TRIALS


def test_n_trials_is_the_declared_size_not_the_surviving_count():
    """The DSR denominator is the family's LITERAL declared size. Shrinking
    it to however many specs happened to clear a data floor would understate
    the search and inflate every DSR."""
    index, tickers, close, calendar, predicted = _screening_fixture()
    subset = DMP_FAMILY[:6]
    results, _ = screen_dmp_family(
        close, close, calendar, predicted, all_true_membership(index, tickers),
        date(2016, 1, 1), date(2020, 12, 31), DmpConfig(), specs=subset,
    )
    for result in results:
        # POOLED DENOMINATOR (2026-09-04): the family's own declared size is
        # now the FLOOR, not the answer -- global_effective_n.dsr_n_trials
        # raises it to the project-wide effectively-independent trial count
        # when that is larger. Both halves are pinned: the exact pooled value,
        # AND the >= that this test was originally written to protect (a
        # denominator below the declared size is trial-count laundering).
        assert result.deflated_sharpe.n_trials == dsr_n_trials(len(subset))
        assert result.deflated_sharpe.n_trials >= len(subset)


def test_results_are_sorted_by_sharpe_descending():
    index, tickers, close, calendar, predicted = _screening_fixture()
    results, _ = screen_dmp_family(
        close, close, calendar, predicted, all_true_membership(index, tickers),
        date(2016, 1, 1), date(2020, 12, 31), DmpConfig(),
    )
    sharpes = [r.sharpe_annualized for r in results]
    assert sharpes == sorted(sharpes, reverse=True)


def test_the_placebo_is_run_for_every_spec_and_is_not_in_n_trials():
    index, tickers, close, calendar, predicted = _screening_fixture()
    results, placebo = screen_dmp_family(
        close, close, calendar, predicted, all_true_membership(index, tickers),
        date(2016, 1, 1), date(2020, 12, 31), DmpConfig(),
    )
    assert set(placebo) == {s.pattern_id for s in DMP_FAMILY}
    # The placebo must NOT inflate the multiple-comparisons denominator: it
    # is a falsification control, not a searched-over variant.
    for result in results:
        assert result.deflated_sharpe.n_trials == DMP_N_TRIALS


def test_the_placebo_catches_far_fewer_real_ex_dates_than_the_live_book():
    """The check that the shift actually worked."""
    index, tickers, close, calendar, predicted = _screening_fixture()
    results, placebo = screen_dmp_family(
        close, close, calendar, predicted, all_true_membership(index, tickers),
        date(2016, 1, 1), date(2020, 12, 31), DmpConfig(),
    )
    by_id = {r.pattern_id: r for r in results}
    for pattern_id, placebo_result in placebo.items():
        assert placebo_result.caught_actual_fraction < by_id[pattern_id].caught_actual_fraction


def test_cost_sensitivity_covers_the_declared_ladder():
    index, tickers, close, calendar, predicted = _screening_fixture()
    results, _ = screen_dmp_family(
        close, close, calendar, predicted, all_true_membership(index, tickers),
        date(2016, 1, 1), date(2020, 12, 31), DmpConfig(),
    )
    for result in results:
        assert set(result.cost_sensitivity_sharpe) == set(DMP_COST_SENSITIVITY_BPS)
        assert result.cost_sensitivity_sharpe[5.0] == pytest.approx(
            result.sharpe_annualized
        )
        assert result.cost_sensitivity_sharpe[0.0] == pytest.approx(
            result.gross_sharpe_annualized
        )


def test_results_carry_the_fields_the_shared_persistence_writer_requires():
    """persist_cross_sectional_trial_results raises rather than silently
    skipping a result missing a required field, so the shape is pinned
    here instead of being discovered in a production run."""
    index, tickers, close, calendar, predicted = _screening_fixture()
    results, _ = screen_dmp_family(
        close, close, calendar, predicted, all_true_membership(index, tickers),
        date(2016, 1, 1), date(2020, 12, 31), DmpConfig(),
    )
    for result in results:
        assert isinstance(result.pattern_id, str)
        assert isinstance(result.n_trading_days, int)
        assert result.deflated_sharpe is not None
        assert isinstance(result.sharpe_annualized, float)


# --- the price-basis contract, which is load-bearing ------------------------


def test_the_yield_basis_uses_the_split_adjusted_price_not_the_total_return_one():
    """Dividend amounts are split-adjusted; the total-return close is
    additionally dividend-back-adjusted. Dividing one by the other would
    overstate historical yields by a per-ticker factor. The two frames are
    passed separately for exactly this reason, and this test is what stops
    them being collapsed into one."""
    index, tickers, close, calendar, predicted, spec = _one_ticker_setup()
    price_only = close * 0.5  # as if the total-return series had drifted away
    spec = DmpSpec("t", "f", "c", "between", "yield", "month")
    membership = all_true_membership(index, tickers)
    same, _ = build_dmp_positions(
        close, close, calendar, predicted, membership,
        date(2016, 1, 1), date(2017, 12, 31), spec, DmpConfig(),
    )
    halved, _ = build_dmp_positions(
        close, price_only, calendar, predicted, membership,
        date(2016, 1, 1), date(2017, 12, 31), spec, DmpConfig(),
    )
    same_long = {(p.ticker, p.month): p.weight_basis for p in same if p.side == "long"}
    halved_long = {(p.ticker, p.month): p.weight_basis for p in halved if p.side == "long"}
    assert same_long and set(same_long) == set(halved_long)
    for key, basis in same_long.items():
        assert halved_long[key] == pytest.approx(basis * 2.0)


def test_the_cache_loader_returns_none_rather_than_fetching(tmp_path):
    """No live-fetch fallback: a screening run must replay a FIXED input, so
    a missing cache is an explicit None the caller has to handle, never a
    silent network call."""
    assert load_dividend_cache(tmp_path / "does_not_exist.json") is None


# --- pinned by the INDEPENDENT VERIFICATION pass, 2026-09-02 ----------------
#
# Each of the three below kills a mutation that the suite as committed did
# NOT catch. They are regression pins, not new behaviour: the code already
# does the right thing, and nothing was asserting that it kept doing it.


def test_the_min_history_gate_cannot_see_the_traded_months_own_ex_date():
    """POINT-IN-TIME. The gate counts ex-dates STRICTLY BEFORE month t,
    because the book for month t is formed at the close of the last trading
    day of month t-1 -- an ex-date inside month t has not happened yet and
    cannot be one of the four the gate requires.

    MUTATION THIS KILLS (survived the suite as committed): changing
    `history.before(month)` to `history.before(month + 1)` in
    build_dmp_positions, which admits a firm on the strength of a
    distribution nobody could know about at formation.

    The fixture is the exact boundary: three ex-dates before month t and the
    fourth INSIDE it. The firm IS predicted for month t (its t-3/t-6/t-9 all
    qualify), so the only thing standing between it and a position is the
    gate reading the right side of the formation date."""
    index = trading_index(date(2015, 1, 1), 800)
    tickers = ["EDGE"]
    close = flat_prices(index, tickers)
    # Ex-dates at t-9, t-6, t-3 and t itself, where t = 2016-04.
    events = [
        DividendEvent("EDGE", date(2015, 7, 15), 1.0),
        DividendEvent("EDGE", date(2015, 10, 15), 1.0),
        DividendEvent("EDGE", date(2016, 1, 15), 1.0),
        DividendEvent("EDGE", date(2016, 4, 15), 1.0),
    ]
    calendar = build_ex_date_calendar(events)
    predicted = predict_dividend_months(
        calendar, month_index(index[0].date()), month_index(index[-1].date())
    )
    target = month_index(date(2016, 4, 1))
    # The forecast rule really does fire for the target month, so a position
    # is only avoided by the history gate -- not by there being no prediction.
    assert target in predicted["EDGE"]
    assert build_prior_ex_date_counts(calendar)["EDGE"].before(target) == 3
    assert build_prior_ex_date_counts(calendar)["EDGE"].before(target + 1) == 4

    # The book for April is formed at the close of the last trading day of
    # MARCH, so March is the formation window that decides the target month.
    spec = DmpSpec("t", "f", "c", "between", "equal", "month")
    positions, counts = build_dmp_positions(
        close, close, calendar, predicted, all_true_membership(index, tickers),
        date(2016, 3, 1), date(2016, 3, 31), spec, DmpConfig(),
    )
    assert not any(p.month == target and p.side == "long" for p in positions)
    assert counts.n_thin_history > 0


def test_one_way_cost_is_charged_at_exactly_bps_over_ten_thousand():
    """The ABSOLUTE cost level, not just its monotonicity. This family's
    entire verdict is "positive gross, killed by cost", so the arithmetic
    turning 5.0bp into a per-day fraction is load-bearing -- and the suite as
    committed pinned only that zero cost is a no-op and that more cost is
    never better, both of which a halved (or doubled) rate satisfies.

    MUTATION THIS KILLS (survived the suite as committed): dividing by
    20_000 instead of 10_000 in net_daily_returns."""
    close, positions, spec = _two_name_replay(0.002, 0.001)
    replay = run_dmp_backtest(close, positions, spec, DmpConfig(impute_delisting_returns=False))
    # Entry day trades the full two units of notional (long 1.0 + short 1.0).
    assert replay.daily_turnover.iloc[0] == pytest.approx(2.0)
    for bps in DMP_COST_SENSITIVITY_BPS:
        net = net_daily_returns(replay, bps, 0.0)
        expected = replay.gross_daily_returns - replay.daily_turnover * (bps / 10_000.0)
        pd.testing.assert_series_equal(net, expected)
        # Stated in money on the one day whose turnover is known by hand:
        # 2.0 of L1 turnover at 5bp one-way is exactly 10bp of the book.
        assert net.iloc[0] == pytest.approx(
            replay.gross_daily_returns.iloc[0] - 2.0 * bps / 10_000.0
        )


def test_the_yield_leg_is_capped_proportional_not_purely_proportional():
    """ERRATA V1. The pre-registration froze "weight PROPORTIONAL to the
    paper's own dividend-yield measure", and the realized weighting is
    proportional-THEN-CAPPED: the harness applies MAX_WEIGHT_MULTIPLE, a
    3x-equal-share concentration limit, on the way through. Measured on the
    real run, that cap binds on 91.2% of 'month'-window days -- it is not a
    corner case, and the documents did not mention it.

    Pinned in BOTH directions on purpose. The cap must stay (removing it
    after seeing results moves this family's numbers in its own favour, which
    is exactly what the pre-registration exists to prevent), and it must stay
    VISIBLE (this test is the thing that made it visible). A future change to
    either the cap or the weighting mode has to come here and say so."""
    from app.services.research_lab.cross_sectional import MAX_WEIGHT_MULTIPLE

    assert MAX_WEIGHT_MULTIPLE == 3.0

    index = trading_index(date(2020, 1, 1), 40)
    tickers = ["HIGH", "A", "B", "C", "D", "S"]
    close = flat_prices(index, tickers)
    close.iloc[1, close.columns.get_loc("HIGH")] = 110.0
    from app.services.research_lab.cross_sectional_dividend_month import DmpPosition

    # HIGH's yield basis is 20x every other long name's. Pure proportional
    # weighting would hand it 20/24 = 83.3% of the leg; the cap holds it to
    # 3 x (1/5) = 60%.
    positions = [DmpPosition("HIGH", 0, "long", 0, 30, 0.20, True)]
    positions += [DmpPosition(t, 0, "long", 0, 30, 0.01, True) for t in ("A", "B", "C", "D")]
    positions.append(DmpPosition("S", 0, "short", 0, 30, float("nan"), False))
    spec = DmpSpec("t", "f", "c", "between", "yield", "month")
    replay = run_dmp_backtest(
        close, positions, spec, DmpConfig(impute_delisting_returns=False)
    )
    # Day 1 is HIGH's +10%; every other name is flat, so the book's gross
    # return that day IS HIGH's realized weight times 10%.
    realized_weight = replay.gross_daily_returns.iloc[0] / 0.10
    assert realized_weight == pytest.approx(0.60), (
        "the yield leg must be CAPPED-proportional at 3x an equal share, not "
        "purely proportional -- see ERRATA V1"
    )
    assert realized_weight < 20.0 / 24.0


def test_the_price_screen_is_frozen_at_the_papers_own_five_dollars():
    """[HS12]'s own screen, quoted: "we also exclude shares with prices less
    than $5 in the previous month". The pre-registration freezes it at one
    value, so its VALUE is part of the frozen spec, not a tunable.

    MUTATION THIS KILLS (survived the suite as committed): DMP_MIN_PRICE set
    to 0.0. The existing screen test places its fixture price at
    DMP_MIN_PRICE - 0.01, so it moves with the constant and passes at any
    level; this pins the level itself, and that the boundary is strict
    ("less than $5" excludes, exactly $5 does not)."""
    assert DMP_MIN_PRICE == 5.0
    assert DmpConfig().min_price == 5.0

    index, tickers, close, calendar, predicted, spec = _one_ticker_setup()
    membership = all_true_membership(index, tickers)
    at_the_line = close.copy()
    at_the_line["PAY"] = 5.0
    positions, counts = build_dmp_positions(
        close, at_the_line, calendar, predicted, membership,
        date(2016, 1, 1), date(2017, 12, 31), spec, DmpConfig(),
    )
    assert any(p.ticker == "PAY" and p.side == "long" for p in positions)
    assert counts.n_below_price_screen == 0
