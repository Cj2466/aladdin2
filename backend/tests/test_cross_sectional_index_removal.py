from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

import app.services.research_lab.cross_sectional_index_removal as removal
from app.services.research_lab.cross_sectional import DEFAULT_IMPUTED_DELISTING_RETURN
from app.services.research_lab.cross_sectional_index_removal import (
    INDEX_REMOVAL_FAMILY,
    REMOVAL_ENTRY_OFFSET_TRADING_DAYS,
    REMOVAL_EVENT_CLUSTER_MIN_GAP_DAYS,
    REMOVAL_HOLDING_DAYS,
    REMOVAL_LEG_WEIGHTINGS,
    REMOVAL_N_TRIALS,
    REMOVAL_SPY_BORROW_BPS_PER_YEAR,
    REMOVAL_STOCK_ROUND_TRIP_BPS,
    REMOVAL_TOTAL_ROUND_TRIP_BPS,
    EnteredEvent,
    IndexRemovalConfig,
    IndexRemovalSpec,
    RemovalEvent,
    build_index_removal_sample_disclosure,
    build_inverse_vol_basis,
    build_removal_event_book,
    count_independent_event_clusters,
    list_index_removal_events,
    run_index_removal_backtest,
    run_index_removal_screening,
    screen_index_removal_family,
)
from app.services.research_lab.sp500_membership_history import vendored_events


def _frame(
    values_by_ticker: dict[str, list[float]], start: str = "2020-01-01"
) -> pd.DataFrame:
    n = len(next(iter(values_by_ticker.values())))
    return pd.DataFrame(values_by_ticker, index=pd.bdate_range(start, periods=n))


def _flat(n: int, value: float = 100.0) -> list[float]:
    return [value] * n


# --- family shape: exactly these 6, no more, no fewer ---------------------

EXPECTED_PATTERN_IDS = {
    "index_removal_rebound_h63_equal",
    "index_removal_rebound_h63_inverse_vol",
    "index_removal_rebound_h126_equal",
    "index_removal_rebound_h126_inverse_vol",
    "index_removal_rebound_h252_equal",
    "index_removal_rebound_h252_inverse_vol",
}


def test_family_is_exactly_6_definitions():
    assert len(INDEX_REMOVAL_FAMILY) == 6
    assert REMOVAL_N_TRIALS == 6


def test_family_pattern_ids_are_exactly_the_expected_6_and_no_others():
    ids = {s.pattern_id for s in INDEX_REMOVAL_FAMILY}
    assert ids == EXPECTED_PATTERN_IDS
    assert len([s.pattern_id for s in INDEX_REMOVAL_FAMILY]) == 6


def test_family_covers_both_axes_exactly_once():
    combos = {(s.holding_days, s.leg_weighting) for s in INDEX_REMOVAL_FAMILY}
    assert combos == {
        (h, w) for h in REMOVAL_HOLDING_DAYS for w in REMOVAL_LEG_WEIGHTINGS
    }
    assert len(combos) == 6


def test_family_every_spec_is_cited_and_shares_the_family_name():
    for spec in INDEX_REMOVAL_FAMILY:
        assert spec.family == "index_removal_rebound"
        assert "Greenwood & Sammon" in spec.citation
        assert "Chen, Noronha & Singal" in spec.citation


def test_family_size_assertion_is_hard_not_documented():
    """The pre-declared size is asserted against the built list, so a drift
    is an import-time failure rather than a silent n_trials change."""
    original = removal.REMOVAL_HOLDING_DAYS
    try:
        removal.REMOVAL_HOLDING_DAYS = (63, 126, 252, 21)
        with pytest.raises(AssertionError, match="not the pre-declared"):
            removal._build_index_removal_family()
    finally:
        removal.REMOVAL_HOLDING_DAYS = original


def test_no_hold_shorter_than_one_quarter():
    """See the module docstring: the cost argument for this floor is not
    the periodic-rebalance one, but the floor itself is pre-declared."""
    assert min(s.holding_days for s in INDEX_REMOVAL_FAMILY) == 63
    assert REMOVAL_N_TRIALS >= 5  # deflated_sharpe.MIN_TRIALS_FOR_DSR


# --- rename artifacts ------------------------------------------------------


def test_rename_filter_drops_the_documented_renames():
    events, n_dropped = list_index_removal_events()
    traded = {(e.ticker, e.effective_date) for e in events}
    # Every one of these is a pure ticker change: the company stayed in the
    # index under a new symbol, so the old symbol must never be traded.
    for ticker, day in [
        ("FB", date(2022, 6, 9)),  # -> META
        ("ANTM", date(2022, 6, 28)),  # -> ELV
        ("BLL", date(2022, 5, 10)),  # -> BALL
        ("PKI", date(2023, 5, 16)),  # -> RVTY
        ("FISV", date(2023, 6, 7)),  # -> FI, caught only by the round-trip rule
        ("FI", date(2025, 11, 11)),  # -> FISV, the other half of that round trip
        ("PARA", date(2025, 8, 8)),  # -> PSKY
        ("MMC", date(2026, 1, 14)),  # -> MRSH
        ("ARNC", date(2020, 4, 6)),  # -> HWM; ARNC's symbol was then recycled
    ]:
        assert (ticker, day) not in traded, f"{ticker} on {day} is a rename artifact"
    assert n_dropped > 0


def test_rename_filter_keeps_genuine_removals():
    events, _ = list_index_removal_events()
    traded = {(e.ticker, e.effective_date) for e in events}
    for ticker, day in [
        ("TWTR", date(2022, 11, 1)),  # taken private
        ("SIVB", date(2023, 3, 15)),  # bank failure
        ("ATVI", date(2023, 10, 18)),  # acquired
        ("ZION", date(2024, 3, 18)),  # deleted, still listed
        ("WHR", date(2024, 3, 18)),  # deleted, still listed
    ]:
        assert (ticker, day) in traded, f"{ticker} on {day} is a genuine removal"


def test_rename_filter_does_not_flag_genuine_index_reentries():
    """A ticker that genuinely left and later rejoined (EQT, PCG, FSLR)
    must not make its re-entry date look like a rename."""
    events, _ = list_index_removal_events()
    traded = {(e.ticker, e.effective_date) for e in events}
    assert ("CTXS", date(2022, 10, 3)) in traded  # same date EQT/PCG re-entered
    assert ("DRE", date(2022, 10, 3)) in traded
    assert ("FBHS", date(2022, 12, 19)) in traded  # same date FSLR re-entered


def test_every_traded_event_is_a_real_removal_in_the_vendored_data():
    events, n_dropped = list_index_removal_events()
    real = {(t, eff) for eff, _a, removed in vendored_events() for t in removed}
    assert {(e.ticker, e.effective_date) for e in events} <= real
    assert len(events) + n_dropped == len(real)


# --- entry timing: never the effective close ------------------------------


def test_entry_is_strictly_after_the_effective_date():
    close = _frame({"AAA": _flat(60)})
    effective = close.index[30].date()
    entered, rejected = build_removal_event_book(
        close, [RemovalEvent("AAA", effective)]
    )
    assert len(entered) == 1
    assert entered[0].entry_position == 31
    assert entered[0].entry_date > effective
    assert not rejected


def test_entry_is_the_next_trading_day_when_the_effective_date_is_not_one():
    """An effective date landing on a weekend must still enter on the next
    real trading day, never on the last one before it."""
    close = _frame({"AAA": _flat(60)})  # business days only
    friday = close.index[27].date()
    assert friday.weekday() == 4
    saturday = friday + timedelta(days=1)
    entered, _ = build_removal_event_book(close, [RemovalEvent("AAA", saturday)])
    assert len(entered) == 1
    assert entered[0].entry_position == 28
    assert entered[0].entry_date > saturday
    assert entered[0].entry_date.weekday() == 0  # the following Monday


def test_entry_offset_is_one_and_never_zero():
    assert REMOVAL_ENTRY_OFFSET_TRADING_DAYS == 1


def test_the_effective_date_close_is_never_the_entry_price():
    """The whole point of the +1: the effective close is the index's own
    forced-selling print, so the entry row must not be it."""
    close = _frame({"AAA": [100.0 + i for i in range(60)]})
    effective = close.index[30].date()
    entered, _ = build_removal_event_book(close, [RemovalEvent("AAA", effective)])
    assert close["AAA"].iloc[entered[0].entry_position] != close["AAA"].iloc[30]


# --- the recycled-ticker / tradeability filter ----------------------------


def test_recycled_ticker_with_no_pre_removal_prices_is_rejected():
    """The mechanical form of the membership-interval intersection: a
    ticker whose price series starts AFTER its own removal is a different
    company (yfinance's FB restarting 2025-06-26 is the real case)."""
    values = [np.nan] * 25 + [100.0] * 15
    close = _frame({"FB": values})
    effective = close.index[24].date()
    entered, rejected = build_removal_event_book(close, [RemovalEvent("FB", effective)])
    assert entered == []
    assert rejected == {"no pre-removal prices (recycled ticker)": 1}


def test_ticker_with_no_price_data_at_all_is_rejected():
    close = _frame({"AAA": _flat(40)})
    entered, rejected = build_removal_event_book(
        close, [RemovalEvent("GONE", close.index[10].date())]
    )
    assert entered == []
    assert rejected == {"no price data": 1}


def test_prices_resuming_long_after_removal_are_rejected():
    values = _flat(25) + [np.nan] * 200 + _flat(30)
    close = _frame({"AAA": values})
    effective = close.index[24].date()
    entered, rejected = build_removal_event_book(
        close, [RemovalEvent("AAA", effective)]
    )
    assert entered == []
    assert "no price on entry day" in rejected


def test_surviving_a_full_post_window_is_NOT_an_entry_condition():
    """Conditioning entry on later survival would be look-ahead. A name
    that dies two days after entry still enters."""
    values = _flat(28) + [np.nan] * 32
    close = _frame({"AAA": values})
    effective = close.index[25].date()
    entered, rejected = build_removal_event_book(
        close, [RemovalEvent("AAA", effective)]
    )
    assert len(entered) == 1
    assert not rejected


# --- the replay ------------------------------------------------------------


def _spec(hold: int = 5, weighting: str = "equal") -> IndexRemovalSpec:
    return IndexRemovalSpec(
        pattern_id=f"t_h{hold}_{weighting}",
        family="index_removal_rebound",
        citation="test",
        holding_days=hold,
        leg_weighting=weighting,
    )


def _free_config() -> IndexRemovalConfig:
    return IndexRemovalConfig(
        stock_round_trip_bps=0.0, spy_round_trip_bps=0.0, spy_borrow_bps_per_year=0.0
    )


def test_a_name_that_exactly_tracks_the_hedge_returns_zero():
    n = 30
    prices = [100.0 * (1.01**i) for i in range(n)]
    close = _frame({"AAA": prices})
    hedge = pd.Series(prices, index=close.index)
    entered = [EnteredEvent("AAA", close.index[5].date(), 5, close.index[5].date())]
    result = run_index_removal_backtest(close, hedge, entered, _spec(), _free_config())
    assert result.status == "ok"
    realized = result.daily_returns.iloc[:5]
    assert np.allclose(realized.to_numpy(), 0.0, atol=1e-12)


def test_outperformance_against_the_hedge_is_the_return():
    n = 30
    stock = [100.0 * (1.02**i) for i in range(n)]
    bench = [100.0 * (1.01**i) for i in range(n)]
    close = _frame({"AAA": stock})
    hedge = pd.Series(bench, index=close.index)
    entered = [EnteredEvent("AAA", close.index[5].date(), 5, close.index[5].date())]
    result = run_index_removal_backtest(close, hedge, entered, _spec(), _free_config())
    realized = result.daily_returns.iloc[:5]
    assert np.allclose(realized.to_numpy(), 0.02 - 0.01, atol=1e-12)


def test_hold_length_is_exactly_holding_days_of_realized_returns():
    n = 40
    close = _frame({"AAA": [100.0 * (1.02**i) for i in range(n)]})
    hedge = pd.Series(_flat(n), index=close.index)
    entered = [EnteredEvent("AAA", close.index[5].date(), 5, close.index[5].date())]
    result = run_index_removal_backtest(
        close, hedge, entered, _spec(hold=7), _free_config()
    )
    invested = result.daily_returns[result.daily_returns != 0.0]
    assert len(invested) == 7
    assert result.n_invested_days == 7


def test_days_with_no_active_event_are_flat_not_dropped():
    n = 40
    close = _frame({"AAA": [100.0 * (1.02**i) for i in range(n)]})
    hedge = pd.Series(_flat(n), index=close.index)
    entered = [EnteredEvent("AAA", close.index[5].date(), 5, close.index[5].date())]
    result = run_index_removal_backtest(
        close, hedge, entered, _spec(hold=3), _free_config()
    )
    assert len(result.daily_returns) == n - 6
    assert result.n_invested_days == 3
    assert (result.daily_returns.iloc[3:] == 0.0).all()


def test_round_trip_cost_is_charged_once_per_event_regardless_of_hold():
    """The event-driven cost fact the module docstring corrects the scout
    on: a longer hold does NOT pay the round trip more often."""
    n = 300
    close = _frame({"AAA": _flat(n)})
    hedge = pd.Series(_flat(n), index=close.index)
    entered = [EnteredEvent("AAA", close.index[5].date(), 5, close.index[5].date())]
    config = IndexRemovalConfig(spy_borrow_bps_per_year=0.0)
    costs = {}
    for hold in (63, 126, 252):
        result = run_index_removal_backtest(
            close, hedge, entered, _spec(hold=hold), config
        )
        costs[hold] = result.total_cost
    assert costs[63] == pytest.approx(costs[126]) == pytest.approx(costs[252])
    assert costs[63] == pytest.approx(REMOVAL_TOTAL_ROUND_TRIP_BPS / 10_000.0)


def test_borrow_accrues_with_the_hold_and_only_with_it():
    n = 300
    close = _frame({"AAA": _flat(n)})
    hedge = pd.Series(_flat(n), index=close.index)
    entered = [EnteredEvent("AAA", close.index[5].date(), 5, close.index[5].date())]
    config = IndexRemovalConfig(stock_round_trip_bps=0.0, spy_round_trip_bps=0.0)
    drags = {}
    for hold in (63, 126, 252):
        result = run_index_removal_backtest(
            close, hedge, entered, _spec(hold=hold), config
        )
        drags[hold] = result.total_financing_cost
    assert drags[63] < drags[126] < drags[252]
    # 63 trading days is ~one calendar quarter of borrow.
    assert drags[63] == pytest.approx(
        REMOVAL_SPY_BORROW_BPS_PER_YEAR / 10_000.0 * 0.25, rel=0.05
    )


def test_borrow_is_zero_when_the_rate_is_zero():
    n = 100
    close = _frame({"AAA": _flat(n)})
    hedge = pd.Series(_flat(n), index=close.index)
    entered = [EnteredEvent("AAA", close.index[5].date(), 5, close.index[5].date())]
    result = run_index_removal_backtest(
        close, hedge, entered, _spec(hold=20), _free_config()
    )
    assert result.total_financing_cost == 0.0


def test_delisting_mid_hold_is_charged_the_shumway_return_not_silently_dropped():
    n = 40
    values = _flat(20) + [np.nan] * 20
    close = _frame({"AAA": values})
    hedge = pd.Series(_flat(n), index=close.index)
    entered = [EnteredEvent("AAA", close.index[5].date(), 5, close.index[5].date())]
    result = run_index_removal_backtest(
        close, hedge, entered, _spec(hold=30), _free_config()
    )
    assert result.n_events_delisted_mid_hold == 1
    assert result.daily_returns.min() == pytest.approx(DEFAULT_IMPUTED_DELISTING_RETURN)


def test_delisting_imputation_can_be_turned_off():
    n = 40
    values = _flat(20) + [np.nan] * 20
    close = _frame({"AAA": values})
    hedge = pd.Series(_flat(n), index=close.index)
    entered = [EnteredEvent("AAA", close.index[5].date(), 5, close.index[5].date())]
    config = IndexRemovalConfig(
        stock_round_trip_bps=0.0,
        spy_round_trip_bps=0.0,
        spy_borrow_bps_per_year=0.0,
        impute_delisting_returns=False,
    )
    result = run_index_removal_backtest(close, hedge, entered, _spec(hold=30), config)
    assert result.n_events_delisted_mid_hold == 0
    assert result.daily_returns.min() > DEFAULT_IMPUTED_DELISTING_RETURN


def test_a_transient_gap_is_not_treated_as_a_delisting():
    n = 40
    values = _flat(15) + [np.nan] * 3 + _flat(22)
    close = _frame({"AAA": values})
    hedge = pd.Series(_flat(n), index=close.index)
    entered = [EnteredEvent("AAA", close.index[5].date(), 5, close.index[5].date())]
    result = run_index_removal_backtest(
        close, hedge, entered, _spec(hold=30), _free_config()
    )
    assert result.n_events_delisted_mid_hold == 0


def test_all_names_missing_means_flat_not_a_naked_hedge_short():
    """On a day the only open name has no return, the book must be FLAT.
    Leaving the hedge on alone would turn a market-neutral position into a
    naked short of a +5%/day benchmark."""
    n = 40
    close = _frame({"AAA": _flat(15) + [np.nan] * 3 + _flat(22)})
    hedge = pd.Series([100.0 * (1.05**i) for i in range(n)], index=close.index)
    entered = [EnteredEvent("AAA", close.index[5].date(), 5, close.index[5].date())]
    result = run_index_removal_backtest(
        close, hedge, entered, _spec(hold=30), _free_config()
    )
    # daily_returns index 0 is close-frame position 6, so the four rows with
    # no usable stock return (positions 15-18) are indices 9-12.
    assert (result.daily_returns.iloc[9:13] == 0.0).all()
    # Every other held day is a genuinely hedged loss: flat stock, +5% hedge.
    assert result.daily_returns.iloc[:9].to_numpy() == pytest.approx(-0.05)
    assert result.daily_returns.iloc[13:30].to_numpy() == pytest.approx(-0.05)


# --- leg weighting: the harness's own modes, not a new scheme -------------


def test_equal_weighting_gives_every_concurrent_event_the_same_share():
    n = 30
    close = _frame({"AAA": [100.0 * (1.04**i) for i in range(n)], "BBB": _flat(n)})
    hedge = pd.Series(_flat(n), index=close.index)
    entered = [
        EnteredEvent("AAA", close.index[5].date(), 5, close.index[5].date()),
        EnteredEvent("BBB", close.index[5].date(), 5, close.index[5].date()),
    ]
    result = run_index_removal_backtest(
        close, hedge, entered, _spec(hold=10, weighting="equal"), _free_config()
    )
    # Half of +4%, half of 0%.
    assert result.daily_returns.iloc[0] == pytest.approx(0.02, rel=1e-9)
    assert result.n_weight_fallback_days == 0


def test_inverse_vol_weighting_favours_the_quieter_name():
    rng = np.random.default_rng(0)
    n = 200
    calm = 100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.002, n))
    wild = 100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.020, n))
    close = _frame({"CALM": list(calm), "WILD": list(wild)})
    hedge = pd.Series(_flat(n), index=close.index)
    basis = build_inverse_vol_basis(close)
    assert basis["CALM"].iloc[150] > basis["WILD"].iloc[150]
    entered = [
        EnteredEvent("CALM", close.index[150].date(), 150, close.index[150].date()),
        EnteredEvent("WILD", close.index[150].date(), 150, close.index[150].date()),
    ]
    result = run_index_removal_backtest(
        close,
        hedge,
        entered,
        _spec(hold=10, weighting="inverse_vol"),
        _free_config(),
        basis,
    )
    assert result.status == "ok"
    assert result.n_weight_fallback_days == 0


def test_inverse_vol_falls_back_to_equal_when_the_basis_is_unusable():
    """The harness's whole-leg fallback, reached through the constant
    signal, which makes _leg_weights degrade to equal weight."""
    n = 30
    close = _frame({"AAA": [100.0 * (1.04**i) for i in range(n)], "BBB": _flat(n)})
    hedge = pd.Series(_flat(n), index=close.index)
    basis = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    entered = [
        EnteredEvent("AAA", close.index[5].date(), 5, close.index[5].date()),
        EnteredEvent("BBB", close.index[5].date(), 5, close.index[5].date()),
    ]
    result = run_index_removal_backtest(
        close,
        hedge,
        entered,
        _spec(hold=10, weighting="inverse_vol"),
        _free_config(),
        basis,
    )
    assert result.n_weight_fallback_days == result.n_weighted_days > 0
    # Fallback is EQUAL weight, so this matches the equal-weighted answer.
    assert result.daily_returns.iloc[0] == pytest.approx(0.02, rel=1e-9)


def test_inverse_vol_without_a_basis_fails_loudly():
    close = _frame({"AAA": _flat(30)})
    hedge = pd.Series(_flat(30), index=close.index)
    entered = [EnteredEvent("AAA", close.index[5].date(), 5, close.index[5].date())]
    with pytest.raises(ValueError, match="inverse-vol basis"):
        run_index_removal_backtest(
            close, hedge, entered, _spec(weighting="inverse_vol"), _free_config(), None
        )


def test_inverse_vol_basis_is_point_in_time():
    """A rolling std at row i reads only rows <= i, so appending future
    rows cannot change an earlier basis value."""
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


def test_screening_uses_the_full_pre_declared_family_as_n_trials():
    rng = np.random.default_rng(2)
    n = 900
    close = _frame(
        {
            f"T{i}": list(100.0 * np.cumprod(1.0 + rng.normal(0.0003, 0.02, n)))
            for i in range(6)
        }
    )
    hedge = pd.Series(
        100.0 * np.cumprod(1.0 + rng.normal(0.0002, 0.01, n)), index=close.index
    )
    entered = [
        EnteredEvent(
            f"T{i}",
            close.index[100 + 60 * i].date(),
            100 + 60 * i,
            close.index[100 + 60 * i].date(),
        )
        for i in range(6)
    ]
    results = screen_index_removal_family(close, hedge, entered, _free_config())
    assert len(results) == REMOVAL_N_TRIALS
    for r in results:
        assert r.deflated_sharpe.n_trials == REMOVAL_N_TRIALS
        assert r.deflated_sharpe.dsr_floor_met  # 6 >= MIN_TRIALS_FOR_DSR
        assert 0.0 <= r.invested_fraction <= 1.0


def test_screening_reports_every_spec_not_just_the_winner():
    rng = np.random.default_rng(3)
    n = 900
    close = _frame(
        {
            f"T{i}": list(100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.02, n)))
            for i in range(4)
        }
    )
    hedge = pd.Series(_flat(n), index=close.index)
    entered = [
        EnteredEvent(
            f"T{i}",
            close.index[100 + 80 * i].date(),
            100 + 80 * i,
            close.index[100 + 80 * i].date(),
        )
        for i in range(4)
    ]
    results = screen_index_removal_family(close, hedge, entered, _free_config())
    assert {r.pattern_id for r in results} == EXPECTED_PATTERN_IDS


def test_screening_returns_nothing_when_there_are_no_events():
    close = _frame({"AAA": _flat(300)})
    hedge = pd.Series(_flat(300), index=close.index)
    assert screen_index_removal_family(close, hedge, [], _free_config()) == []


# --- sample disclosure -----------------------------------------------------


def test_clusters_collapse_a_single_rebalance_date():
    day = date(2024, 3, 18)
    assert count_independent_event_clusters([day, day, day]) == 1
    assert count_independent_event_clusters([]) == 0


def test_clusters_split_dates_far_enough_apart():
    a = date(2024, 3, 18)
    b = a + pd.Timedelta(days=REMOVAL_EVENT_CLUSTER_MIN_GAP_DAYS).to_pytimedelta()
    c = a + pd.Timedelta(days=REMOVAL_EVENT_CLUSTER_MIN_GAP_DAYS - 1).to_pytimedelta()
    assert count_independent_event_clusters([a, b]) == 2
    assert count_independent_event_clusters([a, c]) == 1


def test_sample_disclosure_states_the_low_prior_and_the_cluster_count():
    entered = [
        EnteredEvent("AAA", date(2024, 3, 18), 10, date(2024, 3, 19)),
        EnteredEvent("BBB", date(2024, 3, 18), 10, date(2024, 3, 19)),
        EnteredEvent("CCC", date(2024, 9, 20), 10, date(2024, 9, 23)),
    ]
    d = build_index_removal_sample_disclosure(274, 31, entered, {"no price data": 127})
    assert d.n_entered == 3
    assert d.n_independent_clusters == 2
    assert d.n_candidate_removals == 243
    assert "Greenwood & Sammon" in d.text
    assert "disbelieved" in d.text
    assert "INDEPENDENT CLUSTERS" in d.text


# --- the production entry point -------------------------------------------


def test_screening_start_before_membership_coverage_fails_loudly():
    with pytest.raises(ValueError, match="predates point-in-time membership coverage"):
        run_index_removal_screening(date(2010, 1, 1), date(2020, 1, 1))


def test_screening_fails_loudly_when_the_hedge_resolves_no_data():
    """Silently screening an unhedged long book would be a different and
    far more market-exposed strategy than this family declares."""

    class _NoHedgeProvider:
        def get_daily_ohlcv(self, tickers, start, end):
            if tickers == ["SPY"]:
                return {}, ["SPY"]
            n = 400
            idx = pd.bdate_range("2015-01-01", periods=n)
            frame = pd.DataFrame({t: [100.0] * n for t in tickers}, index=idx)
            return {"close": frame, "open": frame, "volume": frame}, []

    with pytest.raises(ValueError, match="hedge leg resolved no price data"):
        run_index_removal_screening(
            date(2015, 1, 7), date(2016, 1, 1), provider=_NoHedgeProvider()
        )


def test_cost_disclosure_names_its_own_numbers_and_their_source():
    class _Provider:
        def get_daily_ohlcv(self, tickers, start, end):
            n = 400
            idx = pd.bdate_range("2015-01-01", periods=n)
            frame = pd.DataFrame({t: [100.0] * n for t in tickers}, index=idx)
            return {"close": frame, "open": frame, "volume": frame}, []

    summary = run_index_removal_screening(
        date(2015, 1, 7), date(2016, 6, 1), provider=_Provider()
    )
    assert str(REMOVAL_STOCK_ROUND_TRIP_BPS) in summary.cost_disclosure
    assert "Amihud" in summary.cost_disclosure
    assert "ASSUMED" in summary.cost_disclosure
    assert "ONCE PER EVENT" in summary.cost_disclosure
