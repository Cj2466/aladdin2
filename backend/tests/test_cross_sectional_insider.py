"""Unit tests for the routine-vs-opportunistic insider family, mirroring
test_cross_sectional_pead.py's structure: synthetic fixtures for the pure
logic, no live network calls. The SEC Insider Transactions Data Sets shape
(quarterly ZIPs of tab-delimited SUBMISSION / NONDERIV_TRANS /
REPORTINGOWNER tables, DD-MON-YYYY dates, the AFF10B5ONE column present in
new files and absent in 2006-era files) was verified LIVE during the build
session on 2026-08-28 against the real 2006q1, 2016q1 and 2024q1 files and
is exercised here only through recorded-shape fixtures -- CI never hits
sec.gov. The classification tests include a verbatim replay of the paper's
own Exhibit A1 worked example (insider Bob)."""

import io
import zipfile
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

import app.services.research_lab.cross_sectional_insider as insider
from app.services.research_lab.cross_sectional import DEFAULT_IMPUTED_DELISTING_RETURN
from app.services.research_lab.cross_sectional_insider import (
    INSIDER_FAMILY,
    INSIDER_HOLDING_DAYS,
    INSIDER_LEG_WEIGHTINGS,
    INSIDER_MIN_CLUSTER_BUYS,
    INSIDER_N_TRIALS,
    INSIDER_ROUND_TRIP_BPS,
    OPPORTUNISTIC,
    ROUTINE,
    UNCLASSIFIED,
    BuyEvent,
    InsiderConfig,
    InsiderFetchReport,
    InsiderSpec,
    InsiderTrade,
    SignalCounts,
    build_buy_events,
    build_insider_sample_disclosure,
    build_inverse_vol_basis,
    build_owner_labels,
    classify_owner_year,
    load_trades_cache,
    parse_quarter_zip,
    quarter_labels,
    run_insider_backtest,
    run_insider_screening,
    save_trades_cache,
    screen_insider_family,
)

# --- shared synthetic fixtures --------------------------------------------


def _frame(
    values_by_ticker: dict[str, list[float]], start: str = "2020-01-01"
) -> pd.DataFrame:
    n = len(next(iter(values_by_ticker.values())))
    return pd.DataFrame(values_by_ticker, index=pd.bdate_range(start, periods=n))


def _flat(n: int, value: float = 100.0) -> list[float]:
    return [value] * n


def _trade(
    trans: date,
    code: str = "P",
    owner: int = 1,
    issuer: int = 9,
    ticker: str = "AAPL",
    filing: date | None = None,
    accession: str | None = None,
) -> InsiderTrade:
    filing = filing if filing is not None else trans + timedelta(days=2)
    return InsiderTrade(
        ticker=ticker,
        issuer_cik=issuer,
        owner_cik=owner,
        accession=accession or f"acc-{ticker}-{owner}-{trans.isoformat()}",
        trans_date=trans,
        filing_date=filing,
        trans_code=code,
        acquired_disposed="A" if code == "P" else "D",
        shares=100.0,
        price_per_share=50.0,
    )


def _buy_event(
    ticker: str, index: pd.DatetimeIndex, entry_position: int, cluster: int = 1
) -> BuyEvent:
    return BuyEvent(
        ticker=ticker,
        filing_date=index[entry_position - 1].date(),
        entry_position=entry_position,
        entry_date=index[entry_position].date(),
        cluster_filings=cluster,
    )


def _spec(
    hold: int = 5, weighting: str = "equal", min_buys: int = 1
) -> InsiderSpec:
    return InsiderSpec(
        pattern_id=f"t_h{hold}_c{min_buys}_{weighting}",
        family="insider_opportunistic",
        citation="test",
        holding_days=hold,
        min_cluster_buys=min_buys,
        leg_weighting=weighting,
    )


def _free_config() -> InsiderConfig:
    return InsiderConfig(round_trip_bps=0.0, financing_bps_per_year=0.0)


# --- family shape: exactly these 8, no more, no fewer ---------------------

EXPECTED_PATTERN_IDS = {
    "insider_opp_buy_h21_c1_equal",
    "insider_opp_buy_h21_c1_inverse_vol",
    "insider_opp_buy_h21_c2_equal",
    "insider_opp_buy_h21_c2_inverse_vol",
    "insider_opp_buy_h63_c1_equal",
    "insider_opp_buy_h63_c1_inverse_vol",
    "insider_opp_buy_h63_c2_equal",
    "insider_opp_buy_h63_c2_inverse_vol",
}


def test_family_is_exactly_8_definitions():
    assert len(INSIDER_FAMILY) == 8
    assert INSIDER_N_TRIALS == 8


def test_family_pattern_ids_are_exactly_the_expected_8_and_no_others():
    assert {s.pattern_id for s in INSIDER_FAMILY} == EXPECTED_PATTERN_IDS


def test_family_covers_all_three_axes_exactly_once():
    combos = {
        (s.holding_days, s.min_cluster_buys, s.leg_weighting) for s in INSIDER_FAMILY
    }
    assert combos == {
        (h, c, lw)
        for h in INSIDER_HOLDING_DAYS
        for c in INSIDER_MIN_CLUSTER_BUYS
        for lw in INSIDER_LEG_WEIGHTINGS
    }
    assert len(combos) == 8


def test_family_every_spec_is_cited_and_shares_the_family_name():
    for spec in INSIDER_FAMILY:
        assert spec.family == "insider_opportunistic"
        assert "Cohen, Malloy & Pomorski" in spec.citation
        assert "Decoding Inside Information" in spec.citation
        assert "SEC Insider Transactions Data Sets" in spec.citation


def test_family_size_assertion_is_hard_not_documented():
    """The pre-declared size is asserted against the built list, so a
    drift is an import-time failure rather than a silent n_trials change."""
    original = insider.INSIDER_HOLDING_DAYS
    try:
        insider.INSIDER_HOLDING_DAYS = (21, 63, 126)
        with pytest.raises(AssertionError, match="not the pre-declared"):
            insider._build_insider_family()
    finally:
        insider.INSIDER_HOLDING_DAYS = original


def test_family_meets_the_dsr_floor():
    from app.services.research_lab.deflated_sharpe import MIN_TRIALS_FOR_DSR

    assert INSIDER_N_TRIALS >= MIN_TRIALS_FOR_DSR


def test_holding_days_match_the_paper_convention():
    # 21 = the paper's hold-over-the-following-month; 63 sits inside its
    # six-months-then-plateau horizon (module docstring quotes).
    assert min(INSIDER_HOLDING_DAYS) == 21
    assert max(INSIDER_HOLDING_DAYS) == 63


# --- the paper's classification rule ---------------------------------------


def test_obviously_routine_pattern_is_routine():
    """Same calendar month, three consecutive years -- the paper's own
    definition of a routine trader, hand-built."""
    trades = [
        _trade(date(2016, 3, 10)),
        _trade(date(2017, 3, 12), code="S"),
        _trade(date(2018, 3, 8)),
    ]
    assert classify_owner_year(trades, 2019) == ROUTINE


def test_obviously_opportunistic_pattern_is_opportunistic():
    """Active in each of the three preceding years but in scattered
    months: classifiable, no discernible timing pattern."""
    trades = [
        _trade(date(2016, 2, 3)),
        _trade(date(2017, 9, 20), code="S"),
        _trade(date(2018, 5, 14)),
    ]
    assert classify_owner_year(trades, 2019) == OPPORTUNISTIC


def test_under_three_years_of_history_is_unclassified():
    trades = [
        _trade(date(2017, 3, 12)),
        _trade(date(2018, 3, 8)),
    ]
    assert classify_owner_year(trades, 2019) == UNCLASSIFIED


def test_a_gap_year_in_the_three_preceding_years_is_unclassified():
    """'At least one trade in each of the three preceding years' -- a
    2017 gap breaks classifiability even with a long history."""
    trades = [
        _trade(date(2014, 3, 1)),
        _trade(date(2015, 3, 1)),
        _trade(date(2016, 3, 1)),
        _trade(date(2018, 3, 1)),
    ]
    assert classify_owner_year(trades, 2019) == UNCLASSIFIED


def test_same_month_but_non_consecutive_years_is_not_routine():
    """March in 2014/2016/2018 is not three CONSECUTIVE years; with
    activity in each preceding year the insider is opportunistic."""
    trades = [
        _trade(date(2014, 3, 1)),
        _trade(date(2016, 3, 1)),
        _trade(date(2016, 6, 1), code="S"),
        _trade(date(2017, 6, 1)),
        _trade(date(2018, 3, 1)),
    ]
    assert classify_owner_year(trades, 2019) == OPPORTUNISTIC


def test_the_papers_own_exhibit_a1_bob_example_replays_verbatim():
    """The paper's Exhibit A1: Bob trades March 1987, 1988, 1989 (no
    other trades those years), then January 1990, March 1990, December
    1990, January 1991. The paper classifies Bob ROUTINE, and all his
    1990/1991 trades as routine trades."""
    bob = [
        _trade(date(1987, 3, 10)),
        _trade(date(1988, 3, 15)),
        _trade(date(1989, 3, 20)),
        _trade(date(1990, 1, 5)),
        _trade(date(1990, 3, 11)),
        _trade(date(1990, 12, 3)),
        _trade(date(1991, 1, 8)),
    ]
    assert classify_owner_year(bob, 1990) == ROUTINE
    assert classify_owner_year(bob, 1991) == ROUTINE


def test_routine_is_sticky_once_the_run_exists_anywhere_in_the_past():
    """The Exhibit A1 'in the past' reading: a May 2015-2017 run keeps
    the insider routine in 2021 even though recent months are scattered."""
    trades = [
        _trade(date(2015, 5, 1)),
        _trade(date(2016, 5, 1)),
        _trade(date(2017, 5, 1)),
        _trade(date(2018, 2, 1)),
        _trade(date(2019, 9, 1), code="S"),
        _trade(date(2020, 11, 1)),
    ]
    assert classify_owner_year(trades, 2021) == ROUTINE


def test_an_opportunistic_insider_can_become_routine_later():
    trades = [
        _trade(date(2015, 1, 10)),
        _trade(date(2016, 2, 10)),
        _trade(date(2017, 5, 10)),
        _trade(date(2018, 5, 10)),
        _trade(date(2019, 5, 10)),
    ]
    assert classify_owner_year(trades, 2018) == OPPORTUNISTIC
    assert classify_owner_year(trades, 2020) == ROUTINE


def test_classification_is_point_in_time_unfiled_trades_are_invisible():
    """LOOK-AHEAD CHECK: a March 2018 trade FILED 2019-01-05 must not
    inform the start-of-2019 label. With it invisible the insider has no
    2018 trade and is unclassifiable; the contrast case (same trade filed
    promptly) is routine. Using trans_date alone here would silently
    classify on information the market did not yet have."""
    late = [
        _trade(date(2016, 3, 10)),
        _trade(date(2017, 3, 12)),
        _trade(date(2018, 3, 8), filing=date(2019, 1, 5)),
    ]
    prompt = [
        _trade(date(2016, 3, 10)),
        _trade(date(2017, 3, 12)),
        _trade(date(2018, 3, 8)),
    ]
    assert classify_owner_year(late, 2019) == UNCLASSIFIED
    assert classify_owner_year(prompt, 2019) == ROUTINE


def test_build_owner_labels_keeps_pairs_separate():
    """Classification is per (owner, issuer) pair: owner 1's routine
    pattern at issuer 9 must not leak onto owner 2 or onto issuer 8."""
    trades = [
        _trade(date(2016, 3, 1), owner=1, issuer=9),
        _trade(date(2017, 3, 1), owner=1, issuer=9),
        _trade(date(2018, 3, 1), owner=1, issuer=9),
        _trade(date(2016, 1, 1), owner=2, issuer=9),
        _trade(date(2017, 6, 1), owner=2, issuer=9),
        _trade(date(2018, 11, 1), owner=2, issuer=9),
    ]
    labels = build_owner_labels(trades, [2019])
    assert labels[(1, 9, 2019)] == ROUTINE
    assert labels[(2, 9, 2019)] == OPPORTUNISTIC
    assert (1, 8, 2019) not in labels


# --- signal construction ----------------------------------------------------


def _labels_for(
    owner: int, issuer: int, years: list[int], label: str
) -> dict[tuple[int, int, int], str]:
    return {(owner, issuer, y): label for y in years}


def test_entry_is_strictly_after_the_filing_date():
    """The structured data has no intraday acceptance timestamp, so EVERY
    filing takes the conservative after-close rule: filed Monday
    2020-06-01 -> entry at Tuesday's close, never Monday's."""
    index = pd.bdate_range("2020-05-01", periods=60)
    trades = [
        _trade(date(2020, 5, 28), filing=date(2020, 6, 1), ticker="AAPL", issuer=9)
    ]
    labels = _labels_for(1, 9, [2020], OPPORTUNISTIC)
    events, counts = build_buy_events(
        trades, labels, index, date(2020, 1, 1), date(2020, 12, 31), {"AAPL"}
    )
    assert counts.n_events == 1
    assert events[0].entry_date == date(2020, 6, 2)
    assert index[events[0].entry_position].date() == date(2020, 6, 2)


def test_a_weekend_filing_enters_at_the_next_trading_close():
    index = pd.bdate_range("2020-05-01", periods=60)
    trades = [
        _trade(date(2020, 6, 4), filing=date(2020, 6, 6), ticker="AAPL", issuer=9)
    ]
    labels = _labels_for(1, 9, [2020], OPPORTUNISTIC)
    events, _ = build_buy_events(
        trades, labels, index, date(2020, 1, 1), date(2020, 12, 31), {"AAPL"}
    )
    assert events[0].entry_date == date(2020, 6, 8)  # Monday


def test_routine_and_unclassified_buys_never_become_events():
    """The family's entire point: only OPPORTUNISTIC buys carry the
    signal. Routine and unclassifiable buys are counted, never traded."""
    index = pd.bdate_range("2020-05-01", periods=60)
    trades = [
        _trade(date(2020, 5, 28), owner=1, ticker="AAPL", issuer=9),
        _trade(date(2020, 5, 28), owner=2, ticker="AAPL", issuer=9),
        _trade(date(2020, 5, 28), owner=3, ticker="AAPL", issuer=9),
    ]
    labels = {
        (1, 9, 2020): ROUTINE,
        (2, 9, 2020): UNCLASSIFIED,
        (3, 9, 2020): OPPORTUNISTIC,
    }
    _events, counts = build_buy_events(
        trades, labels, index, date(2020, 1, 1), date(2020, 12, 31), {"AAPL"}
    )
    assert counts.n_buy_rows == 3
    assert counts.n_buys_by_routine == 1
    assert counts.n_buys_by_unclassified == 1
    assert counts.n_buys_by_opportunistic == 1
    assert counts.n_events == 1


def test_sells_never_become_events():
    index = pd.bdate_range("2020-05-01", periods=60)
    trades = [_trade(date(2020, 5, 28), code="S", ticker="AAPL", issuer=9)]
    labels = _labels_for(1, 9, [2020], OPPORTUNISTIC)
    events, counts = build_buy_events(
        trades, labels, index, date(2020, 1, 1), date(2020, 12, 31), {"AAPL"}
    )
    assert counts.n_buy_rows == 0
    assert events == []


def test_stale_late_filings_are_dropped_and_counted():
    """A buy filed >30 calendar days after its trade is not a fresh
    signal (the paper's median delay is 3 days)."""
    index = pd.bdate_range("2020-05-01", periods=60)
    trades = [
        _trade(date(2020, 4, 1), filing=date(2020, 6, 1), ticker="AAPL", issuer=9)
    ]
    labels = _labels_for(1, 9, [2020], OPPORTUNISTIC)
    events, counts = build_buy_events(
        trades, labels, index, date(2020, 1, 1), date(2020, 12, 31), {"AAPL"}
    )
    assert counts.n_dropped_stale_filing == 1
    assert events == []


def test_membership_gate_drops_non_members_at_the_filing_date():
    """HOOD was not an S&P 500 member in 2020 (it had not even IPOed);
    the vendored point-in-time membership data answers False, so an
    opportunistic buy there must not trade."""
    index = pd.bdate_range("2020-05-01", periods=60)
    trades = [
        _trade(date(2020, 5, 28), ticker="HOOD", issuer=9),
        _trade(date(2020, 5, 28), owner=2, ticker="AAPL", issuer=8),
    ]
    labels = {(1, 9, 2020): OPPORTUNISTIC, (2, 8, 2020): OPPORTUNISTIC}
    events, counts = build_buy_events(
        trades, labels, index, date(2020, 1, 1), date(2020, 12, 31), {"HOOD", "AAPL"}
    )
    assert counts.n_dropped_not_member == 1
    assert [e.ticker for e in events] == ["AAPL"]


def test_cluster_counts_distinct_accessions_within_the_trailing_window():
    """Two separate filings on one ticker inside 21 rows: the FIRST event
    sees only itself (cluster 1 -- its sibling is not yet public), the
    SECOND sees both (cluster 2). Entry on the completing event only,
    never retroactively."""
    index = pd.bdate_range("2020-05-01", periods=60)
    trades = [
        _trade(
            date(2020, 5, 28),
            owner=1,
            ticker="AAPL",
            issuer=9,
            accession="a1",
            filing=date(2020, 6, 1),
        ),
        _trade(
            date(2020, 6, 8),
            owner=2,
            ticker="AAPL",
            issuer=9,
            accession="a2",
            filing=date(2020, 6, 9),
        ),
    ]
    labels = {(1, 9, 2020): OPPORTUNISTIC, (2, 9, 2020): OPPORTUNISTIC}
    events, _ = build_buy_events(
        trades, labels, index, date(2020, 1, 1), date(2020, 12, 31), {"AAPL"}
    )
    by_date = {e.entry_date: e for e in events}
    first = by_date[date(2020, 6, 2)]
    second = by_date[date(2020, 6, 10)]
    assert first.cluster_filings == 1
    assert second.cluster_filings == 2


def test_a_joint_filing_is_one_cluster_member_not_two():
    """One accession listing two reporting owners is ONE economic buy;
    counting each listed owner would manufacture a 'cluster' out of a
    single trade (1,473 multi-owner accessions measured in 2024q1)."""
    index = pd.bdate_range("2020-05-01", periods=60)
    trades = [
        _trade(date(2020, 5, 28), owner=1, ticker="AAPL", issuer=9, accession="joint"),
        _trade(date(2020, 5, 28), owner=2, ticker="AAPL", issuer=9, accession="joint"),
    ]
    labels = {(1, 9, 2020): OPPORTUNISTIC, (2, 9, 2020): OPPORTUNISTIC}
    events, _ = build_buy_events(
        trades, labels, index, date(2020, 1, 1), date(2020, 12, 31), {"AAPL"}
    )
    assert len(events) == 1
    assert events[0].cluster_filings == 1


def test_two_filings_beyond_the_cluster_window_do_not_cluster():
    index = pd.bdate_range("2020-01-01", periods=120)
    trades = [
        _trade(date(2020, 1, 10), owner=1, ticker="AAPL", issuer=9, accession="a1"),
        _trade(date(2020, 4, 20), owner=2, ticker="AAPL", issuer=9, accession="a2"),
    ]
    labels = {(1, 9, 2020): OPPORTUNISTIC, (2, 9, 2020): OPPORTUNISTIC}
    events, _ = build_buy_events(
        trades, labels, index, date(2020, 1, 1), date(2020, 12, 31), {"AAPL"}
    )
    assert all(e.cluster_filings == 1 for e in events)


# --- the replay -------------------------------------------------------------


def test_daily_return_is_long_leg_minus_benchmark():
    """The hedge is the whole design: without it the book is beta."""
    close = _frame({"AAA": [100, 100, 102, 103, 103, 103, 103]})
    bench = pd.Series([100, 100, 101, 101, 101, 101, 101], index=close.index, dtype=float)
    events = [_buy_event("AAA", close.index, 1)]
    result = run_insider_backtest(close, bench, events, _spec(hold=3), _free_config())
    assert result.status == "ok"
    # First realized day j=2: AAA +2%, SPY +1% -> net +1%.
    assert result.daily_returns.iloc[0] == pytest.approx(0.02 - 0.01)
    # j=3: AAA 103/102-1, SPY flat.
    assert result.daily_returns.iloc[1] == pytest.approx(103 / 102 - 1)


def test_hold_length_is_exactly_holding_days_of_realized_returns():
    n = 30
    close = _frame({"AAA": [100.0 + i for i in range(n)]})
    bench = pd.Series(_flat(n), index=close.index, dtype=float)
    events = [_buy_event("AAA", close.index, 5)]
    result = run_insider_backtest(close, bench, events, _spec(hold=7), _free_config())
    assert result.n_invested_days == 7
    # After the exit the book is flat -- uninvested days are real 0.0 rows.
    assert result.n_uninvested_days == len(result.daily_returns) - 7


def test_uninvested_days_are_flat_and_counted_never_dropped():
    n = 40
    close = _frame({"AAA": [100.0 * (1.01**i) for i in range(n)]})
    bench = pd.Series(_flat(n), index=close.index, dtype=float)
    events = [_buy_event("AAA", close.index, 20)]
    result = run_insider_backtest(close, bench, events, _spec(hold=5), _free_config())
    assert result.n_uninvested_days > 0
    flat_days = result.daily_returns[result.daily_returns == 0.0]
    assert len(flat_days) >= result.n_uninvested_days - 1  # exits can also be 0.0


def test_round_trip_cost_is_charged_once_per_event_regardless_of_hold():
    n = 30
    close = _frame({"AAA": _flat(n)})
    bench = pd.Series(_flat(n), index=close.index, dtype=float)
    events = [_buy_event("AAA", close.index, 5)]
    config = InsiderConfig(round_trip_bps=20.0, financing_bps_per_year=0.0)
    result = run_insider_backtest(close, bench, events, _spec(hold=8), config)
    assert result.total_cost == pytest.approx(20.0 / 10_000.0)
    # All of it lands on the first realized day.
    assert result.daily_returns.iloc[0] == pytest.approx(-20.0 / 10_000.0)
    assert result.daily_returns.iloc[1] == pytest.approx(0.0)


def test_a_new_event_on_a_held_ticker_supersedes_and_repays():
    n = 40
    close = _frame({"AAA": _flat(n)})
    bench = pd.Series(_flat(n), index=close.index, dtype=float)
    events = [
        _buy_event("AAA", close.index, 5),
        _buy_event("AAA", close.index, 10),
    ]
    config = InsiderConfig(round_trip_bps=20.0, financing_bps_per_year=0.0)
    result = run_insider_backtest(close, bench, events, _spec(hold=15), config)
    assert result.n_events_superseded == 1
    # Two events, each paying its own round trip.
    assert result.total_cost == pytest.approx(2 * 20.0 / 10_000.0)
    # Hold runs from the SECOND entry: rows 11..25 invested, then flat.
    assert result.n_invested_days == 20  # rows 6..25 inclusive


def test_delisting_mid_hold_is_a_loss_for_the_long():
    """The Shumway imputation applied to a LONG is a -42.5% day -- the
    conservative direction for this family (its book is only ever long
    single names)."""
    n = 20
    values = _flat(n)
    values[12:] = [np.nan] * (n - 12)  # last valid price at row 11
    close = _frame({"AAA": values})
    bench = pd.Series(_flat(n), index=close.index, dtype=float)
    events = [_buy_event("AAA", close.index, 8)]
    result = run_insider_backtest(close, bench, events, _spec(hold=10), _free_config())
    assert result.n_events_delisted_mid_hold == 1
    assert result.daily_returns.loc[close.index[12]] == pytest.approx(
        DEFAULT_IMPUTED_DELISTING_RETURN
    )


def test_delisting_imputation_can_be_turned_off():
    n = 20
    values = _flat(n)
    values[12:] = [np.nan] * (n - 12)
    close = _frame({"AAA": values})
    # A RISING benchmark: if the dead long left its hedge on, this day
    # would print -1% (a naked short SPY). It must print 0.0 -- a book
    # whose every long is missing is FLAT, hedge included.
    bench = pd.Series([100.0 * (1.01**i) for i in range(n)], index=close.index)
    events = [_buy_event("AAA", close.index, 8)]
    config = InsiderConfig(
        round_trip_bps=0.0, financing_bps_per_year=0.0, impute_delisting_returns=False
    )
    result = run_insider_backtest(close, bench, events, _spec(hold=10), config)
    assert result.n_events_delisted_mid_hold == 0
    assert result.daily_returns.loc[close.index[12]] == pytest.approx(0.0)


def test_inverse_vol_without_a_basis_fails_loudly():
    close = _frame({"AAA": _flat(10)})
    bench = pd.Series(_flat(10), index=close.index, dtype=float)
    events = [_buy_event("AAA", close.index, 2)]
    with pytest.raises(ValueError, match="no inverse-vol basis"):
        run_insider_backtest(
            close, bench, events, _spec(weighting="inverse_vol"), _free_config()
        )


def test_inverse_vol_weights_come_from_a_real_basis_not_the_fallback():
    """Two names entered the same day with different trailing vols: the
    lower-vol name gets the larger weight (harness semantics, reused
    verbatim). This test only pins that a REAL basis was used -- the
    entry-row-vs-current-row convention is pinned by the test below."""
    n = 80
    rng = np.random.default_rng(7)
    calm = 100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.005, n))
    wild = 100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.04, n))
    close = _frame({"CALM": list(calm), "WILD": list(wild)})
    bench = pd.Series(_flat(n), index=close.index, dtype=float)
    basis = build_inverse_vol_basis(close)
    entry = 70
    assert basis["CALM"].iloc[entry] > basis["WILD"].iloc[entry]
    events = [
        _buy_event("CALM", close.index, entry),
        _buy_event("WILD", close.index, entry),
    ]
    config = InsiderConfig(round_trip_bps=10_000.0 * 2, financing_bps_per_year=0.0)
    result = run_insider_backtest(
        close, bench, events, _spec(hold=3, weighting="inverse_vol"), config, basis
    )
    # Cost on day one = sum(w_i) * round_trip = 1.0 * 2.0 regardless of
    # split, so instead check the fallback never fired (real basis used).
    assert result.n_weight_fallback_days == 0


def test_inverse_vol_weights_are_frozen_at_the_events_own_entry_row():
    """ADDED BY THE INDEPENDENT VERIFICATION PASS (2026-08-28). The test
    above is named for the entry-row convention but its only assertion is
    `n_weight_fallback_days == 0`, which a mutant reading `basis.iloc[j]`
    (the CURRENT row) instead of the entry row survives -- verified by
    mutating the module and watching all 50 tests still pass. The module
    docstring states the entry-row convention explicitly, so it needs a
    test that can actually fail.

    NOT a look-ahead property either way: a trailing rolling std at row j
    reads only rows <= j, so the current-row reading would also be
    point-in-time. It is a stated convention, and this pins it.

    Construction: the basis ORDER FLIPS one row after entry, and only one
    held name moves, so the realized portfolio return alone identifies
    which row's weights were used."""
    n = 12
    idx = pd.bdate_range("2020-01-01", periods=n)
    entry = 5
    # CALM jumps +10% on the first realized day (row 6); WILD never moves.
    close = pd.DataFrame(
        {"CALM": [100.0] * 6 + [110.0] * 6, "WILD": [100.0] * n}, index=idx
    )
    bench = pd.Series(_flat(n), index=idx, dtype=float)
    basis = pd.DataFrame(
        {"CALM": [3.0] * 6 + [1.0] * 6, "WILD": [1.0] * 6 + [3.0] * 6}, index=idx
    )
    assert basis["CALM"].iloc[entry] > basis["WILD"].iloc[entry]
    assert basis["CALM"].iloc[entry + 1] < basis["WILD"].iloc[entry + 1]
    events = [_buy_event("CALM", idx, entry), _buy_event("WILD", idx, entry)]
    result = run_insider_backtest(
        close, bench, events, _spec(hold=3, weighting="inverse_vol"),
        _free_config(), basis,
    )
    assert result.n_weight_fallback_days == 0
    # Entry-row basis 3:1 -> 0.75 CALM, 0.25 WILD -> 0.75 * 10% = 7.5%.
    # Current-row basis 1:3 would give 0.25 * 10% = 2.5% instead.
    assert result.daily_returns.iloc[0] == pytest.approx(0.075, abs=1e-12)


def test_inverse_vol_basis_is_point_in_time():
    n = 80
    rng = np.random.default_rng(11)
    values = list(100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.02, n)))
    close = _frame({"AAA": values})
    basis_full = build_inverse_vol_basis(close)
    truncated = close.iloc[:70]
    basis_trunc = build_inverse_vol_basis(truncated)
    pd.testing.assert_series_equal(
        basis_full["AAA"].iloc[:70], basis_trunc["AAA"], check_names=False
    )


# --- screening / DSR --------------------------------------------------------


def _synthetic_events_and_frame(
    n_tickers: int = 8, n_days: int = 500, seed: int = 3
) -> tuple[pd.DataFrame, pd.Series, list[BuyEvent]]:
    rng = np.random.default_rng(seed)
    close = _frame(
        {
            f"T{i}": list(100.0 * np.cumprod(1.0 + rng.normal(0.0002, 0.02, n_days)))
            for i in range(n_tickers)
        },
        start="2019-01-01",
    )
    bench = pd.Series(
        100.0 * np.cumprod(1.0 + rng.normal(0.0002, 0.01, n_days)), index=close.index
    )
    events = []
    for i in range(n_tickers):
        for k in range(8):
            row = 70 + i * 3 + k * 50
            if row >= n_days - 2:
                continue
            # cluster_filings=2 so every spec (c1 and c2 alike) enters.
            events.append(_buy_event(f"T{i}", close.index, row, cluster=2))
    events.sort(key=lambda e: (e.entry_position, e.ticker))
    return close, bench, events


def test_screening_uses_the_full_pre_declared_family_as_n_trials():
    close, bench, events = _synthetic_events_and_frame()
    results = screen_insider_family(close, bench, events, _free_config())
    assert {r.pattern_id for r in results} == EXPECTED_PATTERN_IDS
    for r in results:
        assert r.deflated_sharpe.n_trials == INSIDER_N_TRIALS
        assert r.deflated_sharpe.dsr_floor_met  # 8 >= MIN_TRIALS_FOR_DSR
        assert 0.0 <= r.invested_fraction <= 1.0


def test_min_cluster_2_specs_trade_a_subset_of_events():
    close, bench, events = _synthetic_events_and_frame()
    # Demote half the events to cluster 1.
    demoted = [
        BuyEvent(
            ticker=e.ticker,
            filing_date=e.filing_date,
            entry_position=e.entry_position,
            entry_date=e.entry_date,
            cluster_filings=1 if i % 2 == 0 else 2,
        )
        for i, e in enumerate(events)
    ]
    results = screen_insider_family(close, bench, demoted, _free_config())
    by_id = {r.pattern_id: r for r in results}
    c1 = by_id["insider_opp_buy_h21_c1_equal"]
    c2 = by_id["insider_opp_buy_h21_c2_equal"]
    assert c2.n_events_entered < c1.n_events_entered


def test_screening_returns_nothing_when_there_are_no_events():
    close = _frame({"AAA": _flat(300)})
    bench = pd.Series(_flat(300), index=close.index, dtype=float)
    assert screen_insider_family(close, bench, [], _free_config()) == []


def test_positive_control_a_real_edge_produces_a_large_positive_sharpe():
    """POSITIVE CONTROL (the sibling verification passes' discipline): a
    deliberately planted edge -- the held name drifts +30bp/day while the
    benchmark is flat -- must come out as a large positive Sharpe, proving
    the machinery can convert real signal into a positive number and that
    an honest negative from the production run is a finding, not broken
    plumbing."""
    n = 400
    close = _frame({"EDGE": [100.0 * (1.003**i) for i in range(n)]})
    bench = pd.Series(_flat(n), index=close.index, dtype=float)
    events = [
        _buy_event("EDGE", close.index, row, cluster=2) for row in range(5, n - 2, 20)
    ]
    results = screen_insider_family(close, bench, events, _free_config())
    assert results, "the control must produce results"
    for r in results:
        assert r.sharpe_annualized > 3.0


# --- the SEC data-set fixtures (shape verified live 2026-08-28) ------------


def _tsv(rows: list[list[str]]) -> bytes:
    return ("\n".join("\t".join(row) for row in rows) + "\n").encode("utf-8")


def _fixture_zip(modern: bool = True) -> bytes:
    """A quarterly ZIP whose headers mirror the REAL files inspected live
    this session: modern=True mirrors 2024q1 (AFF10B5ONE present),
    modern=False mirrors 2006q1/2016q1 (no AFF10B5ONE). Both spell
    FORM3_HOLDINGS_REPORTED as the real files do (the readme PDF spells it
    without the S -- the parser must select by name, so both variants are
    exercised)."""
    sub_header = [
        "ACCESSION_NUMBER",
        "FILING_DATE",
        "PERIOD_OF_REPORT",
        "DATE_OF_ORIG_SUB",
        "NO_SECURITIES_OWNED",
        "NOT_SUBJECT_SEC16",
        "FORM3_HOLDINGS_REPORTED",
        "FORM4_TRANS_REPORTED",
        "DOCUMENT_TYPE",
        "ISSUERCIK",
        "ISSUERNAME",
        "ISSUERTRADINGSYMBOL",
        "REMARKS",
    ] + (["AFF10B5ONE"] if modern else [])
    pad = ["0"] if modern else []
    sub_rows = [
        sub_header,
        # kept: Form 4, universe issuer
        ["acc-1", "31-JAN-2024", "29-JAN-2024", "", "", "", "", "", "4", "0000000009", "TESTCO", "TST", ""] + pad,
        # excluded: amendment
        ["acc-2", "31-JAN-2024", "29-JAN-2024", "", "", "", "", "", "4/A", "0000000009", "TESTCO", "TST", ""] + pad,
        # excluded: non-universe issuer
        ["acc-3", "31-JAN-2024", "29-JAN-2024", "", "", "", "", "", "4", "0000000777", "OTHERCO", "OTH", ""] + pad,
        # excluded: Form 5
        ["acc-4", "31-JAN-2024", "29-JAN-2024", "", "", "", "", "", "5", "0000000009", "TESTCO", "TST", ""] + pad,
    ]
    nd_header = [
        "ACCESSION_NUMBER",
        "NONDERIV_TRANS_SK",
        "SECURITY_TITLE",
        "TRANS_DATE",
        "TRANS_FORM_TYPE",
        "TRANS_CODE",
        "TRANS_SHARES",
        "TRANS_PRICEPERSHARE",
        "TRANS_ACQUIRED_DISP_CD",
    ]
    nd_rows = [
        nd_header,
        ["acc-1", "1", "Common Stock", "29-JAN-2024", "4", "P", "200.0", "21.97", "A"],
        ["acc-1", "2", "Common Stock", "29-JAN-2024", "4", "S", "100.0", "22.10", "D"],
        ["acc-1", "3", "Common Stock", "29-JAN-2024", "4", "M", "500.0", "10.00", "A"],
        ["acc-2", "4", "Common Stock", "29-JAN-2024", "4", "P", "300.0", "21.00", "A"],
        ["acc-3", "5", "Common Stock", "29-JAN-2024", "4", "P", "400.0", "5.00", "A"],
    ]
    ro_header = ["ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNERNAME", "RPTOWNER_RELATIONSHIP"]
    ro_rows = [
        ro_header,
        ["acc-1", "0000000501", "DOE JANE", "Director"],
        ["acc-2", "0000000501", "DOE JANE", "Director"],
        ["acc-3", "0000000502", "ROE RICHARD", "Officer"],
    ]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("SUBMISSION.tsv", _tsv([[str(c) for c in r] for r in sub_rows]))
        archive.writestr("NONDERIV_TRANS.tsv", _tsv(nd_rows))
        archive.writestr("REPORTINGOWNER.tsv", _tsv(ro_rows))
    return buffer.getvalue()


@pytest.mark.parametrize("modern", [True, False])
def test_parse_quarter_zip_matches_the_verified_file_shape(modern):
    """Only DOCUMENT_TYPE '4' (never 4/A or 5), only universe issuers,
    only P/S codes; DD-MON-YYYY dates parse; owner CIK joins."""
    trades = parse_quarter_zip(_fixture_zip(modern), {9: "TST"})
    assert len(trades) == 2  # acc-1's P and S rows only
    codes = {t.trans_code for t in trades}
    assert codes == {"P", "S"}
    for t in trades:
        assert t.ticker == "TST"
        assert t.issuer_cik == 9
        assert t.owner_cik == 501
        assert t.accession == "acc-1"
        assert t.filing_date == date(2024, 1, 31)
        assert t.trans_date == date(2024, 1, 29)
    buy = next(t for t in trades if t.trans_code == "P")
    assert buy.acquired_disposed == "A"
    assert buy.shares == pytest.approx(200.0)
    assert buy.price_per_share == pytest.approx(21.97)


def test_parse_quarter_zip_returns_nothing_for_a_non_universe_quarter():
    assert parse_quarter_zip(_fixture_zip(), {123: "XYZ"}) == []


# --- cache round-trip -------------------------------------------------------


def test_trades_cache_round_trips(tmp_path):
    trades = [
        _trade(date(2020, 5, 28)),
        _trade(date(2021, 6, 1), code="S", owner=2),
    ]
    report = InsiderFetchReport(
        quarters_requested=["2020q1", "2020q2"],
        quarters_fetched=["2020q1"],
        quarters_failed=["2020q2"],
        n_tickers_requested=500,
        n_tickers_cik_resolved=498,
        unresolved_tickers=["XX"],
        n_raw_ps_rows=2,
    )
    path = tmp_path / "trades.csv.gz"
    save_trades_cache(trades, report, path)
    loaded = load_trades_cache(path)
    assert loaded is not None
    loaded_trades, loaded_report = loaded
    assert loaded_trades == trades
    assert loaded_report.quarters_failed == ["2020q2"]
    assert loaded_report.n_tickers_cik_resolved == 498


def test_missing_cache_returns_none(tmp_path):
    assert load_trades_cache(tmp_path / "absent.csv.gz") is None


# --- quarter labels ---------------------------------------------------------


def test_quarter_labels_span_years_correctly():
    assert quarter_labels("2006q1", "2007q2") == [
        "2006q1",
        "2006q2",
        "2006q3",
        "2006q4",
        "2007q1",
        "2007q2",
    ]
    assert len(quarter_labels("2006q1", "2026q2")) == 82


# --- production entry point guards and disclosure ---------------------------


def test_screening_start_before_membership_coverage_fails_loudly():
    with pytest.raises(ValueError, match="predates point-in-time membership"):
        run_insider_screening(date(2010, 1, 1), date(2020, 1, 1))


def test_screening_fails_loudly_when_the_benchmark_resolves_no_data():
    class _NoBenchmarkProvider:
        def get_daily_ohlcv(self, tickers, start, end):
            if tickers == ["SPY"]:
                return {}, ["SPY"]
            n = 400
            idx = pd.bdate_range("2019-06-01", periods=n)
            frame = pd.DataFrame({t: [100.0] * n for t in tickers}, index=idx)
            return {"close": frame, "open": frame, "volume": frame}, []

    trades = [
        _trade(date(2020, 3, 2), ticker="AAPL", issuer=9),
    ]
    with pytest.raises(ValueError, match="benchmark resolved no price data"):
        run_insider_screening(
            date(2020, 1, 1),
            date(2021, 1, 1),
            provider=_NoBenchmarkProvider(),
            trades=trades,
            fetch_report=InsiderFetchReport(n_tickers_requested=1),
        )


def test_sample_disclosure_states_the_thin_leg_and_the_buy_side_caveat():
    report = InsiderFetchReport(
        quarters_requested=["2020q1"],
        quarters_fetched=["2020q1"],
        n_tickers_requested=500,
        n_tickers_cik_resolved=498,
        n_raw_ps_rows=1000,
    )
    counts = SignalCounts(
        n_buy_rows=100,
        n_buys_by_opportunistic=40,
        n_buys_by_routine=30,
        n_buys_by_unclassified=30,
        n_events=25,
    )
    d = build_insider_sample_disclosure(report, counts, [], 480, date(2026, 6, 30))
    assert d.n_buys_by_opportunistic == 40
    assert "survivorship" in d.text.lower()
    assert "SELL side" in d.text
    assert "OPPORTUNISTIC" in d.text
    assert f"n_trials={INSIDER_N_TRIALS}" in d.text


def test_cost_disclosure_names_its_own_numbers_and_their_source():
    class _Provider:
        def get_daily_ohlcv(self, tickers, start, end):
            if not tickers:
                return {}, []
            n = 400
            idx = pd.bdate_range("2019-06-01", periods=n)
            frame = pd.DataFrame({t: [100.0] * n for t in tickers}, index=idx)
            return {"close": frame, "open": frame, "volume": frame}, []

    summary = run_insider_screening(
        date(2020, 1, 1),
        date(2021, 1, 1),
        provider=_Provider(),
        trades=[],
        fetch_report=InsiderFetchReport(n_tickers_requested=0),
    )
    assert str(INSIDER_ROUND_TRIP_BPS) in summary.cost_disclosure
    assert "ONCE PER EVENT" in summary.cost_disclosure
    assert "SPY hedge" in summary.cost_disclosure
