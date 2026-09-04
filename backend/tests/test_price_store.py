"""Tests for the point-in-time price store and its adjustment engine.

The load-bearing ones are, in order of what they protect:

  * test_apple_2020_split_reconstructs_the_real_traded_price — the as-traded
    normalisation, pinned against an INDEPENDENTLY KNOWN historical fact
    ($499.23 on 2020-08-28) rather than against the code's own output.
  * test_refetch_never_changes_a_stored_row / test_a_revised_row_is_reported
    — the immutability policy that makes a rerun reproduce.
  * test_a_late_discovered_dividend_cannot_move_an_earlier_return — the exact
    fabricated-return mechanism this whole module exists to eliminate,
    reproduced end to end and shown to be gone.
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services.market_data.price_store import (
    AdjustmentConvention,
    PriceStore,
    PriceStoreReport,
    adjusted_frames,
    cumulative_split_factor,
    distribution_series,
    split_adjusted_prices,
    total_return_close,
)


def _bundle(closes, *, dividends=None, splits=None, index=None, volume=None):
    index = index if index is not None else pd.bdate_range("2020-01-01", periods=len(closes))
    n = len(closes)
    return (
        {
            "open": pd.Series(closes, index=index, dtype=float),
            "high": pd.Series(closes, index=index, dtype=float),
            "low": pd.Series(closes, index=index, dtype=float),
            "close": pd.Series(closes, index=index, dtype=float),
            "volume": pd.Series(volume if volume is not None else [1000.0] * n, index=index),
            "dividend": pd.Series(dividends if dividends is not None else [0.0] * n, index=index),
        },
        pd.Series(splits if splits is not None else [0.0] * n, index=index, dtype=float),
    )


# --- cumulative split factor ------------------------------------------------


def test_cumulative_split_factor_is_one_when_there_are_no_splits():
    index = pd.bdate_range("2020-01-01", periods=5)
    factor = cumulative_split_factor(pd.Series(0.0, index=index), index)
    assert (factor == 1.0).all()


def test_cumulative_split_factor_applies_strictly_before_the_ex_date():
    """The ex-date's own price is ALREADY quoted in the new units, so it must
    not be scaled — only strictly earlier dates. Off-by-one here is exactly
    the single-day fabricated return the store exists to remove."""
    index = pd.bdate_range("2020-01-01", periods=5)
    splits = pd.Series([0.0, 0.0, 4.0, 0.0, 0.0], index=index)
    factor = cumulative_split_factor(splits, index)
    assert list(factor) == [4.0, 4.0, 1.0, 1.0, 1.0]


def test_cumulative_split_factor_compounds_multiple_splits():
    index = pd.bdate_range("2020-01-01", periods=5)
    splits = pd.Series([0.0, 2.0, 0.0, 3.0, 0.0], index=index)
    assert list(cumulative_split_factor(splits, index)) == [6.0, 3.0, 3.0, 1.0, 1.0]


def test_cumulative_split_factor_ignores_no_op_ratios():
    """yfinance writes 0.0 on an ordinary day; 1.0 is a no-op ratio. Neither
    is an event."""
    index = pd.bdate_range("2020-01-01", periods=3)
    splits = pd.Series([1.0, 0.0, 1.0], index=index)
    assert list(cumulative_split_factor(splits, index)) == [1.0, 1.0, 1.0]


# --- as-traded normalisation ------------------------------------------------


def test_apple_2020_split_reconstructs_the_real_traded_price():
    """THE ANCHOR TEST. Apple closed at 499.23 on 2020-08-28, the last
    session before its 4-for-1 split took effect on 2020-08-31 — an
    independently known public fact, not a value produced by this codebase.

    Yahoo's auto_adjust=False `Close` for that date is 124.8075, because
    Yahoo has already re-expressed the whole history in post-split units.
    to_as_traded must undo exactly that and recover the real number."""
    index = pd.DatetimeIndex(["2020-08-27", "2020-08-28", "2020-08-31"])
    fields, splits = _bundle([125.010002, 124.807503, 129.039993], splits=[0.0, 0.0, 4.0], index=index)
    as_traded = PriceStore.to_as_traded(fields, splits)

    assert as_traded.loc["2020-08-28", "close"] == pytest.approx(499.230012, rel=1e-9)
    # The ex-date itself is already in new units and must be left alone.
    assert as_traded.loc["2020-08-31", "close"] == pytest.approx(129.039993, rel=1e-12)


def test_volume_is_divided_by_the_split_factor_not_multiplied():
    """CRSP p.117 adjusts share/volume data by MULTIPLYING by the cumulative
    factor where prices are DIVIDED by it. Going the other way would put a
    16x discontinuity into every dollar-volume gate at a 4-for-1 split."""
    index = pd.DatetimeIndex(["2020-08-28", "2020-08-31"])
    fields, splits = _bundle(
        [124.807503, 129.039993], splits=[0.0, 4.0], index=index, volume=[187630000.0, 225702700.0]
    )
    as_traded = PriceStore.to_as_traded(fields, splits)
    # Pre-split as-traded volume is a QUARTER of the post-split-basis figure.
    assert as_traded.loc["2020-08-28", "volume"] == pytest.approx(46907500.0)


def test_dividends_are_put_on_the_as_traded_basis_too():
    index = pd.DatetimeIndex(["2020-01-01", "2020-01-02", "2020-01-03"])
    fields, splits = _bundle([10.0, 10.0, 20.0], dividends=[0.0, 0.5, 0.0], splits=[0.0, 0.0, 2.0], index=index)
    as_traded = PriceStore.to_as_traded(fields, splits)
    assert as_traded.loc["2020-01-02", "dividend"] == pytest.approx(1.0)
    assert as_traded.loc["2020-01-02", "close"] == pytest.approx(20.0)


def test_as_traded_is_basis_invariant_across_a_later_split():
    """The whole reason for storing as-traded: a chunk fetched AFTER a new
    split must land on the store at the same scale as one fetched before it,
    or the two splice together with a fabricated return at the join."""
    index = pd.DatetimeIndex(["2020-01-01", "2020-01-02"])
    before, splits_before = _bundle([100.0, 110.0], index=index)
    # Same two days, refetched after a 2-for-1 split that Yahoo has now
    # applied to the whole history.
    after_index = pd.DatetimeIndex(["2020-01-01", "2020-01-02", "2020-06-01"])
    after, splits_after = _bundle([50.0, 55.0, 60.0], splits=[0.0, 0.0, 2.0], index=after_index)

    first = PriceStore.to_as_traded(before, splits_before)
    second = PriceStore.to_as_traded(after, splits_after)
    assert first.loc["2020-01-02", "close"] == pytest.approx(second.loc["2020-01-02", "close"])


# --- adjustment engine ------------------------------------------------------


def test_split_adjusted_price_uses_the_window_end_as_base_date():
    """CRSP's stated convention, and the reproducibility guarantee: a split
    after the window's end cannot reach back into it."""
    index = pd.bdate_range("2020-01-01", periods=3)
    frame = pd.DataFrame(
        {"close": [400.0, 400.0, 100.0], "split": [0.0, 0.0, 4.0], "volume": [1.0, 1.0, 1.0]},
        index=index,
    )
    adjusted = split_adjusted_prices(frame, ["close"])["close"]
    assert list(adjusted) == [100.0, 100.0, 100.0]


def test_crsp_and_yahoo_conventions_agree_when_nothing_is_distributed():
    index = pd.bdate_range("2020-01-01", periods=4)
    frame = pd.DataFrame(
        {"close": [10.0, 11.0, 10.5, 12.0], "dividend": 0.0, "split": 0.0}, index=index
    )
    crsp = total_return_close(frame, convention=AdjustmentConvention.CRSP)
    yahoo = total_return_close(frame, convention=AdjustmentConvention.YAHOO)
    pd.testing.assert_series_equal(crsp, yahoo, check_names=False)


def test_the_two_conventions_diverge_exactly_as_documented_on_a_large_distribution():
    """The KDP 2018-07-10 case from price_store's section 5, reproduced with
    its real numbers: a $103.75 distribution against a 123.66 close.

    True total return   (22.19 + 103.75)/123.66 - 1 = +1.84%
    Yahoo's convention  22.19/(123.66 - 103.75) - 1 = +11.45%"""
    index = pd.DatetimeIndex(["2018-07-09", "2018-07-10"])
    frame = pd.DataFrame(
        {"close": [123.660004, 22.190001], "dividend": [0.0, 103.75], "split": [0.0, 0.0]},
        index=index,
    )
    crsp = total_return_close(frame, convention=AdjustmentConvention.CRSP).pct_change().iloc[-1]
    yahoo = total_return_close(frame, convention=AdjustmentConvention.YAHOO).pct_change().iloc[-1]
    assert crsp == pytest.approx(0.018438, abs=1e-5)
    assert yahoo == pytest.approx(0.114515, abs=1e-5)


def test_crsp_is_the_default_convention():
    """The default flipped from YAHOO to CRSP on 2026-09-04. Pinned so it
    cannot drift back silently: every caller that does not name a convention
    gets CRSP, and that is what YFinanceProvider constructs itself with."""
    from app.services.market_data.yfinance_provider import YFinanceProvider

    index = pd.DatetimeIndex(["2018-07-09", "2018-07-10"])
    frame = pd.DataFrame(
        {"close": [123.660004, 22.190001], "dividend": [0.0, 103.75], "split": [0.0, 0.0]},
        index=index,
    )
    pd.testing.assert_series_equal(
        total_return_close(frame),
        total_return_close(frame, convention=AdjustmentConvention.CRSP),
    )
    assert YFinanceProvider(price_store=PriceStore(None)).adjustment is AdjustmentConvention.CRSP


def test_the_yahoo_convention_is_exactly_the_true_return_amplified():
    """The closed form that decides the whole convention question:

        r_YAHOO = r_CRSP / (1 - D/P_prev)

    so Yahoo's is not a level offset a cross-sectional ranking could absorb —
    it is a leverage applied on ex-dates in proportion to the distribution.
    Checked on four real, independently-sourced special distributions where
    the share was retained 1:1, so the true return is unambiguous arithmetic.
    Sources: data/research_runs/dividend_convention_2026-09-04.txt section 1."""
    cases = [
        (123.660004, 22.190001, 103.75),  # KDP  2018-07-10, $103.75
        (28.42, 17.15, 12.00),            # GEN  2020-02-03, $12.00
        (57.68, 37.25, 17.50),            # BKR  2017-07-05, $17.50
        (50.58, 29.58, 18.75),            # SHEN 2021-08-03, $18.75
    ]
    index = pd.DatetimeIndex(["2020-01-01", "2020-01-02"])
    for previous, close, dividend in cases:
        frame = pd.DataFrame(
            {"close": [previous, close], "dividend": [0.0, dividend], "split": [0.0, 0.0]},
            index=index,
        )
        crsp = total_return_close(frame).pct_change().iloc[-1]
        yahoo = total_return_close(
            frame, convention=AdjustmentConvention.YAHOO
        ).pct_change().iloc[-1]
        # CRSP's is the arithmetic definition of what a holder earned.
        assert crsp == pytest.approx((close + dividend) / previous - 1.0)
        # Yahoo's is that number divided by (1 - D/P_prev), exactly.
        assert yahoo == pytest.approx(crsp / (1.0 - dividend / previous))


def test_a_same_day_stock_dividend_and_cash_dividend_are_both_kept_by_default():
    """TR (Tootsie Roll) declares a regular quarterly CASH dividend AND,
    separately, an annual 3% STOCK dividend, on the same ex-date every March
    (8-K, CIK 0000098677). The 1.03 ratio is the stock dividend; the cash is a
    second, real payment.

    This is why `drop_same_day_split_distributions` is NOT switched on by the
    CRSP convention: TR alone has ten such events in this project's small-cap
    universe, and dropping the cash discards a payment that was made.

    Real numbers, 2015-03-06: 33.24 -> 31.45. A holder of one share ends the
    day with 1.03 shares at 31.45 plus 1.03 * 0.078 of cash."""
    index = pd.DatetimeIndex(["2015-03-05", "2015-03-06"])
    frame = pd.DataFrame(
        {"close": [33.24, 31.45], "dividend": [0.0, 0.078], "split": [0.0, 1.03]},
        index=index,
    )
    truth = (1.03 * 31.45 + 1.03 * 0.078) / 33.24 - 1.0
    default = total_return_close(frame).pct_change().iloc[-1]
    assert default == pytest.approx(truth, abs=1e-9)

    dropped = total_return_close(
        frame, drop_same_day_split_distributions=True
    ).pct_change().iloc[-1]
    assert dropped == pytest.approx(1.03 * 31.45 / 33.24 - 1.0, abs=1e-9)
    # The drop rule is wrong here by exactly the whole cash dividend.
    assert default - dropped == pytest.approx(1.03 * 0.078 / 33.24, abs=1e-9)


def test_a_spin_off_paid_alongside_a_separate_cash_dividend_is_not_dropped():
    """DXC 2015-11-30: CSC stockholders received one CSRA share per CSC share
    AND a genuinely separate $10.50/share special cash distribution ($2.25
    from CSC, $8.25 from CSRA — SEC 8-K, CIK 0000023082, accession
    0000023082-15-000078). Yahoo's split ratio carries the shares; the $10.50
    is the cash. Dropping the cash turns a roughly flat day into -20.5%."""
    index = pd.DatetimeIndex(["2015-11-27", "2015-11-30"])
    frame = pd.DataFrame(
        {"close": [68.62, 31.33], "dividend": [0.0, 10.50], "split": [0.0, 1.7412]},
        index=index,
    )
    default = total_return_close(frame).pct_change().iloc[-1]
    dropped = total_return_close(
        frame, drop_same_day_split_distributions=True
    ).pct_change().iloc[-1]
    assert default > 0.0
    assert dropped == pytest.approx(1.7412 * 31.33 / 68.62 - 1.0, abs=1e-9)
    assert dropped < -0.20


def test_dropping_same_day_distributions_stays_available_as_an_explicit_opt_in():
    """DHR 2016-07-05 (Fortive) IS a genuine double-encoding — Yahoo records
    the same spin-off value as both a 1.319 ratio and a distribution — and
    dropping it there is right: the day's true total return, from Fortive's
    own first regular-way close of 48.60 at one FTV per two DHR shares, is
    +2.33%, against +3.64% dropped and +39.4% kept.

    The rule is kept reachable for exactly this case. It is not a DEFAULT
    because Yahoo's feed cannot say which case a given event is, and 13 of the
    15 such events in this project's universes are the other case."""
    index = pd.DatetimeIndex(["2016-07-01", "2016-07-05"])
    # Stored rows are AS-TRADED: 68.771202 * 1.319 and 71.276596, both then
    # carrying DHR's later 1.128 Veralto factor. Written here on the vendor's
    # own basis so the ratios are the ones the store actually holds.
    frame = pd.DataFrame(
        {"close": [90.709216, 71.276596], "dividend": [0.0, 24.56], "split": [0.0, 1.319]},
        index=index,
    )
    kept = distribution_series(frame, drop_same_day_split_distributions=False)
    dropped_series = distribution_series(frame, drop_same_day_split_distributions=True)
    assert kept.iloc[-1] > 0.0
    assert dropped_series.iloc[-1] == 0.0

    opted_in = total_return_close(
        frame, drop_same_day_split_distributions=True
    ).pct_change().iloc[-1]
    assert opted_in == pytest.approx(0.036432, abs=1e-4)
    # The default keeps the distribution, so the same day reads much higher.
    assert total_return_close(frame).pct_change().iloc[-1] > 0.3
    # ...and Yahoo's own series reported +61%, which never happened.
    yahoo = total_return_close(
        frame, convention=AdjustmentConvention.YAHOO
    ).pct_change().iloc[-1]
    assert yahoo > 0.5


def test_total_return_close_is_normalised_to_the_split_adjusted_close_at_the_base_date():
    index = pd.bdate_range("2020-01-01", periods=3)
    frame = pd.DataFrame({"close": [10.0, 10.0, 10.0], "dividend": [0.0, 1.0, 0.0], "split": 0.0}, index=index)
    series = total_return_close(frame)
    assert series.iloc[-1] == pytest.approx(10.0)
    # An earlier date is worth LESS on a total-return basis, because holding
    # it through the distribution earned the distribution.
    assert series.iloc[0] < 10.0


def test_ohlc_share_one_total_return_factor_so_an_overnight_return_stays_consistent():
    index = pd.bdate_range("2020-01-01", periods=3)
    frame = pd.DataFrame(
        {
            "open": [9.0, 9.5, 10.5],
            "high": [11.0, 11.0, 11.0],
            "low": [8.0, 8.0, 8.0],
            "close": [10.0, 10.0, 11.0],
            "volume": [100.0, 100.0, 100.0],
            "dividend": [0.0, 1.0, 0.0],
            "split": 0.0,
        },
        index=index,
    )
    frames = adjusted_frames(frame)
    ratio = frames["open"] / frames["close"]
    expected = frame["open"] / frame["close"]
    np.testing.assert_allclose(ratio.to_numpy(), expected.to_numpy(), rtol=1e-12)


def test_price_only_close_carries_no_dividend_adjustment():
    index = pd.bdate_range("2020-01-01", periods=3)
    frame = pd.DataFrame(
        {
            "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0, "volume": 1.0,
            "dividend": [0.0, 1.0, 0.0], "split": 0.0,
        },
        index=index,
    )
    frames = adjusted_frames(frame)
    assert list(frames["price_only_close"]) == [10.0, 10.0, 10.0]
    assert frames["close"].iloc[0] < 10.0


# --- store persistence and immutability -------------------------------------


def test_read_ticker_returns_none_before_anything_is_stored(tmp_path):
    assert PriceStore(tmp_path).read_ticker("AAPL") is None


def test_merge_then_read_round_trips_the_stored_values(tmp_path):
    store = PriceStore(tmp_path)
    fields, splits = _bundle([10.0, 11.0, 12.0])
    frame = PriceStore.to_as_traded(fields, splits)
    report = PriceStoreReport()
    store.merge_ticker("AAPL", frame, report)

    read_back = store.read_ticker("AAPL")
    assert report.rows_written == 3
    np.testing.assert_allclose(read_back["close"].to_numpy(), [10.0, 11.0, 12.0])


def test_refetch_never_changes_a_stored_row(tmp_path):
    """First write wins. This is the property that makes a fixed historical
    window reproduce."""
    store = PriceStore(tmp_path)
    index = pd.bdate_range("2020-01-01", periods=3)
    original, splits = _bundle([10.0, 11.0, 12.0], index=index)
    store.merge_ticker("AAPL", PriceStore.to_as_traded(original, splits), PriceStoreReport())

    revised, revised_splits = _bundle([99.0, 99.0, 99.0], index=index)
    report = PriceStoreReport()
    result = store.merge_ticker("AAPL", PriceStore.to_as_traded(revised, revised_splits), report)

    np.testing.assert_allclose(result["close"].to_numpy(), [10.0, 11.0, 12.0])
    np.testing.assert_allclose(store.read_ticker("AAPL")["close"].to_numpy(), [10.0, 11.0, 12.0])
    assert report.rows_written == 0
    assert report.rows_already_present == 3


def test_a_revised_row_is_reported_rather_than_silently_discarded(tmp_path):
    """Holding a revision back is only defensible if the revision is
    OBSERVABLE — otherwise the store would silently serve data the vendor has
    since corrected, with nothing to notice it by."""
    store = PriceStore(tmp_path)
    index = pd.bdate_range("2020-01-01", periods=2)
    original, splits = _bundle([10.0, 11.0], index=index)
    store.merge_ticker("AAPL", PriceStore.to_as_traded(original, splits), PriceStoreReport())

    revised, revised_splits = _bundle([10.0, 11.5], index=index)
    report = PriceStoreReport()
    store.merge_ticker("AAPL", PriceStore.to_as_traded(revised, revised_splits), report)

    assert len(report.revisions) == 1
    ticker, when, stored, fetched = report.revisions[0]
    assert (ticker, when) == ("AAPL", date(2020, 1, 2))
    assert (stored, fetched) == (pytest.approx(11.0), pytest.approx(11.5))
    assert "UPSTREAM REVISIONS" in report.describe()


def test_new_dates_are_appended_while_existing_ones_are_kept(tmp_path):
    store = PriceStore(tmp_path)
    first_index = pd.bdate_range("2020-01-01", periods=2)
    first, first_splits = _bundle([10.0, 11.0], index=first_index)
    store.merge_ticker("AAPL", PriceStore.to_as_traded(first, first_splits), PriceStoreReport())

    second_index = pd.bdate_range("2020-01-01", periods=4)
    second, second_splits = _bundle([99.0, 99.0, 12.0, 13.0], index=second_index)
    report = PriceStoreReport()
    merged = store.merge_ticker("AAPL", PriceStore.to_as_traded(second, second_splits), report)

    np.testing.assert_allclose(merged["close"].to_numpy(), [10.0, 11.0, 12.0, 13.0])
    assert report.rows_written == 2


def test_resync_is_the_only_way_a_stored_row_ever_changes(tmp_path):
    store = PriceStore(tmp_path)
    index = pd.bdate_range("2020-01-01", periods=2)
    original, splits = _bundle([10.0, 11.0], index=index)
    store.merge_ticker("AAPL", PriceStore.to_as_traded(original, splits), PriceStoreReport())
    store.resync_ticker("AAPL")
    assert store.read_ticker("AAPL") is None

    revised, revised_splits = _bundle([10.0, 11.5], index=index)
    store.merge_ticker("AAPL", PriceStore.to_as_traded(revised, revised_splits), PriceStoreReport())
    assert store.read_ticker("AAPL")["close"].iloc[-1] == pytest.approx(11.5)


def test_implausible_rows_are_refused_at_ingest(tmp_path):
    fields, splits = _bundle([10.0, np.nan, -1.0, 12.0])
    report = PriceStoreReport()
    kept = PriceStore.drop_implausible(PriceStore.to_as_traded(fields, splits), report)
    assert len(kept) == 2
    assert report.rejected_rows == 2


def test_disabling_persistence_makes_every_read_a_miss(tmp_path):
    store = PriceStore(None)
    report = PriceStoreReport()
    fields, splits = _bundle([10.0, 11.0])
    store.merge_ticker("AAPL", PriceStore.to_as_traded(fields, splits), report)
    assert store.read_ticker("AAPL") is None


def test_default_store_dir_is_resolved_at_construction_not_import(monkeypatch, tmp_path):
    """The conftest fixture that keeps tests off the real data directory
    depends on this; a bound parameter default would silently defeat it."""
    from app.services.market_data import price_store as module

    monkeypatch.setattr(module, "DEFAULT_STORE_DIR", tmp_path / "elsewhere")
    assert PriceStore().store_dir == tmp_path / "elsewhere"


# --- coverage ledger --------------------------------------------------------


def test_coverage_is_only_honoured_for_a_containing_window(tmp_path):
    store = PriceStore(tmp_path)
    store.record_coverage(["PCP"], date(2015, 1, 1), date(2026, 1, 1))
    coverage = store.read_coverage()

    assert store.is_covered(coverage, "PCP", date(2016, 1, 1), date(2020, 1, 1))
    # A WIDER request reaches dates never asked about and must be re-asked.
    assert not store.is_covered(coverage, "PCP", date(2010, 1, 1), date(2026, 1, 1))
    assert not store.is_covered(coverage, "AAPL", date(2016, 1, 1), date(2020, 1, 1))


def test_overlapping_coverage_windows_merge(tmp_path):
    store = PriceStore(tmp_path)
    store.record_coverage(["AAPL"], date(2015, 1, 1), date(2018, 1, 1))
    store.record_coverage(["AAPL"], date(2017, 1, 1), date(2020, 1, 1))
    assert store.read_coverage()["AAPL"] == [["2015-01-01", "2020-01-01"]]


def test_disjoint_coverage_windows_do_not_bridge_the_gap_between_them(tmp_path):
    """Two windows with an unasked hole between them must not be treated as
    covering the hole — that would serve a gap as if it were an answer."""
    store = PriceStore(tmp_path)
    store.record_coverage(["AAPL"], date(2015, 1, 1), date(2016, 1, 1))
    store.record_coverage(["AAPL"], date(2020, 1, 1), date(2021, 1, 1))
    coverage = store.read_coverage()
    assert len(coverage["AAPL"]) == 2
    assert not store.is_covered(coverage, "AAPL", date(2015, 6, 1), date(2020, 6, 1))


def test_a_delisted_ticker_is_covered_even_though_it_has_no_rows(tmp_path):
    """The case that makes coverage a SEPARATE record rather than something
    inferred from the rows: a dead symbol legitimately has nothing to store,
    and must not be re-requested on every call forever."""
    store = PriceStore(tmp_path)
    store.record_coverage(["PCP"], date(2015, 1, 1), date(2026, 1, 1))
    assert store.read_ticker("PCP") is None
    assert store.is_covered(store.read_coverage(), "PCP", date(2016, 1, 1), date(2020, 1, 1))


def test_resync_clears_coverage_too(tmp_path):
    store = PriceStore(tmp_path)
    store.record_coverage(["PCP"], date(2015, 1, 1), date(2020, 1, 1))
    store.resync_ticker("PCP")
    assert store.read_coverage() == {}


# --- the end-to-end property the module exists for --------------------------


def test_a_late_discovered_dividend_cannot_move_an_earlier_return(tmp_path):
    """THE REGRESSION TEST FOR THE ORIGINAL BUG, reproduced end to end.

    Yahoo learns about a dividend with an ex-date INSIDE an already-run
    backtest window. Under the old code path that retroactively rescaled
    every earlier price on the next fetch, fabricating one day's return at
    the boundary. Under the store, the second fetch cannot alter the first
    fetch's rows, so every return the window already produced is unchanged."""
    store = PriceStore(tmp_path)
    index = pd.bdate_range("2020-01-01", periods=6)

    first, first_splits = _bundle([10.0, 10.2, 10.1, 10.4, 10.3, 10.6], index=index)
    store.merge_ticker("AAPL", PriceStore.to_as_traded(first, first_splits), PriceStoreReport())
    before = total_return_close(store.read_ticker("AAPL")).pct_change().dropna()

    # The same window refetched later, now carrying a distribution Yahoo had
    # not yet processed on day 4 — the exact shape of the measured drift.
    second, second_splits = _bundle(
        [10.0, 10.2, 10.1, 10.4, 10.3, 10.6], dividends=[0.0, 0.0, 0.0, 0.25, 0.0, 0.0], index=index
    )
    report = PriceStoreReport()
    store.merge_ticker("AAPL", PriceStore.to_as_traded(second, second_splits), report)
    after = total_return_close(store.read_ticker("AAPL")).pct_change().dropna()

    pd.testing.assert_series_equal(before, after)
    # And the divergence is not merely absorbed: `close` is unchanged so no
    # revision is reported, while the dividend the vendor added is correctly
    # held back with the rest of the row.
    assert report.rows_written == 0


def test_an_unwritable_store_degrades_instead_of_failing_the_read(tmp_path, monkeypatch, caplog):
    """This store sits in front of EVERY daily price read, including a live
    forward-validation tick, and production runs on an ephemeral free-tier
    filesystem. An unwritable disk must downgrade to the old pass-through
    behaviour, never fail a request the vendor already answered."""
    from app.services.market_data import price_store as module

    store = PriceStore(tmp_path)
    fields, splits = _bundle([10.0, 11.0, 12.0])
    frame = PriceStore.to_as_traded(fields, splits)

    def _refuse(*_args, **_kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(module.os, "fdopen", _refuse)
    with caplog.at_level("WARNING"):
        result = store.merge_ticker("AAPL", frame, PriceStoreReport())

    # The caller still gets its rows; only persistence was lost.
    np.testing.assert_allclose(result["close"].to_numpy(), [10.0, 11.0, 12.0])
    assert "continuing without persistence" in caplog.text


def test_the_first_run_returns_what_every_rerun_will_see(tmp_path):
    """A float that has been through to_csv/read_csv is exact to ~1e-15
    relative, not to the last bit. So merge_ticker must return the RE-READ
    copy, or the very first run of a backtest would differ from its own
    reruns in the last digits — which is the reproducibility claim, missed by
    a hair. Caught by a live 12-name fetch whose run 1 hashed differently from
    runs 2 and 3."""
    store = PriceStore(tmp_path)
    fields, splits = _bundle([123.456789012345, 98.7654321098765, 1000.000000000001])
    frame = PriceStore.to_as_traded(fields, splits)

    first = store.merge_ticker("AAPL", frame, PriceStoreReport())
    second = store.read_ticker("AAPL")
    assert first.to_numpy().tobytes() == second.to_numpy().tobytes()


def test_without_a_store_directory_the_in_memory_frame_is_what_the_caller_gets(tmp_path):
    store = PriceStore(None)
    fields, splits = _bundle([10.0, 11.0])
    frame = PriceStore.to_as_traded(fields, splits)
    returned = store.merge_ticker("AAPL", frame, PriceStoreReport())
    pd.testing.assert_frame_equal(returned, frame)


def test_the_volume_round_trip_is_lossless():
    """The docstring on get_daily_ohlcv claims volume comes back matching
    Yahoo's own exactly; this pins that rather than leaving it as an
    argument. Store on ingest = volume / C(t); return on read = value * C(t)."""
    index = pd.DatetimeIndex(["2020-08-27", "2020-08-28", "2020-08-31"])
    fields, splits = _bundle(
        [125.010002, 124.807503, 129.039993], splits=[0.0, 0.0, 4.0], index=index,
        volume=[155552400.0, 187630000.0, 225702700.0],
    )
    stored = PriceStore.to_as_traded(fields, splits)
    back = split_adjusted_prices(stored, ["volume"])["volume"]
    np.testing.assert_allclose(
        back.to_numpy(), [155552400.0, 187630000.0, 225702700.0], rtol=1e-15
    )
