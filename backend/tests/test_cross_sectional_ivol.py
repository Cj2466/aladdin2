from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
)
from app.services.research_lab.cross_sectional_ivol import (
    IVOL_HOLDING_HORIZONS_DAYS,
    IVOL_LOOKBACK_DAYS,
    IVOL_RANK_FRACTION,
    ROUND_D1_FAMILY,
    ROUND_D1_PATTERN_CEILING,
    SP500_MAX_PLAUSIBLE_MARKET_CAP_USD,
    SP500_MIN_PLAUSIBLE_MARKET_CAP_USD,
    build_point_in_time_market_cap,
    implausible_market_cap_mask,
    restrict_share_counts_to_price_lifecycle,
    run_round_d1_screening,
    signal_idiosyncratic_volatility,
    split_adjust_share_counts,
)


def _frame(values_by_ticker: dict[str, list[float]], start: str = "2023-01-02") -> pd.DataFrame:
    n = len(next(iter(values_by_ticker.values())))
    return pd.DataFrame(values_by_ticker, index=pd.bdate_range(start, periods=n))


# --- family shape guards (same convention as test_cross_sectional_patterns's
# guards on ROUND_C_FAMILY) --------------------------------------------------


def test_family_is_21_definitions_inside_the_hard_ceiling():
    assert len(ROUND_D1_FAMILY) == 21
    assert len(ROUND_D1_FAMILY) <= ROUND_D1_PATTERN_CEILING


def test_family_pattern_ids_are_unique_and_every_spec_is_cited():
    ids = [s.pattern_id for s in ROUND_D1_FAMILY]
    assert len(set(ids)) == len(ids)
    for spec in ROUND_D1_FAMILY:
        assert spec.citation
        assert "Ang" in spec.citation and "Hodrick" in spec.citation
        assert "Bali" in spec.citation and "Cakici" in spec.citation
        assert "Blitz" in spec.citation and "van Vliet" in spec.citation
        assert spec.holding_days > 0
        assert spec.lookback_days > 0
        assert spec.rank_fraction == pytest.approx(IVOL_RANK_FRACTION)


def test_family_is_entirely_value_weighted_and_declares_market_cap():
    # Build D1's whole point: every definition, including the raw-vol
    # robustness split, value-weights its legs — never the old
    # magnitude-weighted default.
    for spec in ROUND_D1_FAMILY:
        assert spec.leg_weighting == "value"
        assert spec.requires_market_cap is True
        assert spec.requires_open is False
        assert spec.requires_volume is False


def test_family_covers_the_18_main_definitions_grid():
    main = [s for s in ROUND_D1_FAMILY if s.pattern_id.startswith("ivol_resid_")]
    assert len(main) == 18
    lookbacks = {s.lookback_days - 1 for s in main}
    holds = {s.holding_days for s in main}
    portfolios = {s.portfolio for s in main}
    assert lookbacks == set(IVOL_LOOKBACK_DAYS)
    assert holds == set(IVOL_HOLDING_HORIZONS_DAYS)
    assert portfolios == {"long_short", "long_universe_hedged"}
    # Full 3 x 3 x 2 grid, no gaps, no duplicates.
    grid = {(s.lookback_days - 1, s.holding_days, s.portfolio) for s in main}
    assert len(grid) == 18


def test_family_covers_the_3_robustness_definitions():
    robust = [s for s in ROUND_D1_FAMILY if s.pattern_id.startswith("ivol_rawvol_")]
    assert len(robust) == 3
    for spec in robust:
        assert spec.lookback_days - 1 == 63  # w=63 only, per the build
        assert spec.portfolio == "long_short"  # long_short only, per the build
    assert {s.holding_days for s in robust} == set(IVOL_HOLDING_HORIZONS_DAYS)


# --- signal_idiosyncratic_volatility: residual IVOL hand-check -------------

# Ground truth computed independently via numpy.polyfit (a different code
# path from this module's own closed-form covariance/variance regression),
# not by running the implementation forward — see the task's own build log
# for the derivation. market_t = mean(X_t, Y_t, Z_t) each day; each series's
# OLS residual (intercept + slope on market) has std(ddof=1) as below.
_X = [0.02, -0.01, 0.015, -0.005]
_Y = [0.01, 0.02, -0.01, 0.03]
_Z = [-0.01, 0.005, 0.02, -0.015]
_IVOL_X = 0.009036961141150643
_IVOL_Y = 0.0031622776601683738
_IVOL_Z = 0.010723805294763607


def _prices_from_returns(returns: list[float], start_price: float = 100.0) -> list[float]:
    prices = [start_price]
    for r in returns:
        prices.append(prices[-1] * (1.0 + r))
    return prices


def test_residual_ivol_hand_check_matches_independent_ols_ground_truth():
    close = _frame(
        {
            "X": _prices_from_returns(_X),
            "Y": _prices_from_returns(_Y),
            "Z": _prices_from_returns(_Z),
        }
    )
    data = CrossSectionalData(close=close)
    signal = signal_idiosyncratic_volatility(data, lookback_days=4, raw_vol=False)

    # Signal is NEGATIVE ivol (top-of-signal == long == lowest vol, matching
    # every other family's "higher signal is more long" convention).
    assert signal["X"] == pytest.approx(-_IVOL_X, abs=1e-9)
    assert signal["Y"] == pytest.approx(-_IVOL_Y, abs=1e-9)
    assert signal["Z"] == pytest.approx(-_IVOL_Z, abs=1e-9)

    # Ranking sanity: Y has the lowest IVOL of the three (0.00316 < 0.00904
    # < 0.01072), so it must rank FIRST (largest, i.e. least negative,
    # signal value) — the AHXZ long candidate.
    ranked = signal.sort_values(ascending=False)
    assert list(ranked.index) == ["Y", "X", "Z"]


def test_raw_vol_robustness_hand_check_matches_plain_std():
    close = _frame({"X": _prices_from_returns(_X), "Y": _prices_from_returns(_Y)})
    data = CrossSectionalData(close=close)
    signal = signal_idiosyncratic_volatility(data, lookback_days=4, raw_vol=True)

    expected_x = float(np.std(_X, ddof=1))
    expected_y = float(np.std(_Y, ddof=1))
    assert signal["X"] == pytest.approx(-expected_x)
    assert signal["Y"] == pytest.approx(-expected_y)
    # raw_vol skips the market regression entirely -- these must NOT equal
    # the residual IVOL values from the test above (different quantities).
    assert signal["X"] != pytest.approx(-_IVOL_X, abs=1e-6)


def test_ivol_refuses_short_history_ipo_artifact():
    n = 60
    full = np.linspace(50, 100, n + 1).tolist()
    sparse = [np.nan] * (n - 5) + list(np.linspace(90, 100, 6))
    close = _frame({"FULL": full, "SPARSE": sparse})
    data = CrossSectionalData(close=close)
    signal = signal_idiosyncratic_volatility(data, lookback_days=n, raw_vol=False)
    assert np.isfinite(signal["FULL"])
    assert np.isnan(signal["SPARSE"])


def test_ivol_raw_vol_also_refuses_short_history():
    n = 60
    full = np.linspace(50, 100, n + 1).tolist()
    sparse = [np.nan] * (n - 5) + list(np.linspace(90, 100, 6))
    close = _frame({"FULL": full, "SPARSE": sparse})
    data = CrossSectionalData(close=close)
    signal = signal_idiosyncratic_volatility(data, lookback_days=n, raw_vol=True)
    assert np.isfinite(signal["FULL"])
    assert np.isnan(signal["SPARSE"])


def test_ivol_zero_for_a_ticker_that_exactly_equals_the_market():
    # A ticker equal to the (equal-weighted) market itself has a perfect,
    # zero-residual fit: IVOL == 0 exactly, the AHXZ-minimum case. Three
    # tickers so TRACK isn't just a literal duplicate of some other single
    # column: TRACK is constructed as (O1 + O2) / 2, which makes
    # mean(TRACK, O1, O2) == TRACK exactly (3T = T+O1+O2 => T=(O1+O2)/2,
    # independently verified: max abs diff market-vs-TRACK is ~3.5e-18,
    # i.e. exact up to floating point).
    rng = np.random.default_rng(3)
    n = 40
    o1 = rng.normal(0.0, 0.01, n)
    o2 = rng.normal(0.0, 0.01, n)
    track = (o1 + o2) / 2.0
    close = _frame(
        {
            "TRACK": _prices_from_returns(track.tolist()),
            "O1": _prices_from_returns(o1.tolist()),
            "O2": _prices_from_returns(o2.tolist()),
        }
    )
    data = CrossSectionalData(close=close)
    signal = signal_idiosyncratic_volatility(data, lookback_days=n, raw_vol=False)
    assert signal["TRACK"] == pytest.approx(0.0, abs=1e-9)


# --- cross-endpoint consistency: prices and share counts come from two
# DIFFERENT yfinance endpoints joined by ticker symbol alone, and a ticker
# symbol is not a company. Confirmed live 2026-08-27: STI serves 1,083 price
# rows from 2022-05-02 (Solidion Technology) beside 447 share-count rows from
# 2015-11-16 (SunTrust Banks). -----------------------------------------------


def _quarterly(values_by_ticker: dict[str, list[float]]) -> pd.DataFrame:
    """A price frame whose rows are a QUARTER apart, so a lifecycle boundary
    sits far outside CROSS_ENDPOINT_PRICE_GRACE_DAYS — the register the real
    mismatches live in (smallest measured: 119 days)."""
    n = len(next(iter(values_by_ticker.values())))
    return pd.DataFrame(
        values_by_ticker, index=pd.date_range("2018-01-01", periods=n, freq="QE")
    )


def test_lifecycle_check_drops_share_counts_predating_the_first_price_bar():
    # The FOXA case in miniature: a share-count history that begins years
    # before this symbol had any price at all belongs to whoever held the
    # symbol then, not to the company whose prices this column carries.
    close = _quarterly({"A": [np.nan, np.nan, 10.0, 10.0, 10.0]})
    idx = close.index
    shares = pd.Series([1.85e9, 1.85e9, 6.2e8], index=[idx[0], idx[1], idx[3]])

    restricted, dropped = restrict_share_counts_to_price_lifecycle({"A": shares}, close)

    assert dropped == {"A": 2}
    assert list(restricted["A"]) == [6.2e8]


def test_lifecycle_check_drops_share_counts_after_the_last_price_bar():
    close = _quarterly({"A": [10.0, 10.0, np.nan, np.nan, np.nan]})
    idx = close.index
    shares = pd.Series([100.0, 200.0], index=[idx[1], idx[4]])

    restricted, dropped = restrict_share_counts_to_price_lifecycle({"A": shares}, close)

    assert dropped == {"A": 1}
    assert list(restricted["A"]) == [100.0]


def test_lifecycle_check_keeps_an_ordinary_ticker_completely_untouched():
    # The overwhelmingly common case must be a no-op, or the check would be
    # silently deleting good data across the whole universe.
    close = _frame({"A": [10.0] * 6})
    shares = pd.Series([100.0, 110.0], index=[close.index[0], close.index[4]])

    restricted, dropped = restrict_share_counts_to_price_lifecycle({"A": shares}, close)

    assert dropped == {}
    pd.testing.assert_series_equal(restricted["A"], shares)


def test_lifecycle_check_grace_window_absorbs_an_ipo_edge_filing():
    # A count filed a few days before the first trade is legitimate; the real
    # mismatches this check exists for are years wide (smallest measured on
    # the production universe: 119 days), so the grace cannot decide one.
    close = _frame({"A": [10.0] * 5})
    just_before = close.index[0] - pd.Timedelta(days=3)
    long_before = close.index[0] - pd.Timedelta(days=400)
    shares = pd.Series([90.0, 100.0], index=[long_before, just_before])

    restricted, dropped = restrict_share_counts_to_price_lifecycle({"A": shares}, close)

    assert dropped == {"A": 1}
    assert list(restricted["A"]) == [100.0]


def test_lifecycle_check_leaves_a_ticker_with_no_price_at_all_alone():
    # There is no lifecycle to check against; deleting its history would
    # punish a fetch that simply did not resolve.
    close = _frame({"A": [10.0, 10.0], "B": [np.nan, np.nan]})
    shares = pd.Series([100.0], index=[close.index[0] - pd.Timedelta(days=900)])

    restricted, dropped = restrict_share_counts_to_price_lifecycle({"B": shares}, close)

    assert dropped == {}
    pd.testing.assert_series_equal(restricted["B"], shares)


def test_lifecycle_check_cannot_use_the_future_to_change_an_eligible_row():
    """The trailing bound reads the ticker's LAST price bar, which is future
    information at an earlier formation. It is safe only because it can
    remove nothing dated on or before that bar — so extending the price
    series later (i.e. revealing the future) must leave every share count
    that any priced row could read bit-identical."""
    early_close = _quarterly({"A": [10.0, 10.0, 10.0, np.nan, np.nan]})
    late_close = _quarterly({"A": [10.0, 10.0, 10.0, 10.0, 10.0]})
    idx = early_close.index
    shares = pd.Series([100.0, 200.0, 300.0], index=[idx[0], idx[2], idx[4]])

    restricted_early, _ = restrict_share_counts_to_price_lifecycle({"A": shares}, early_close)
    restricted_late, _ = restrict_share_counts_to_price_lifecycle({"A": shares}, late_close)

    # Everything dated within the SHORTER (known-so-far) lifecycle survives
    # both, unchanged: knowing the delisting date early changed nothing that
    # a formation inside the priced window could ever read.
    within = restricted_late["A"].loc[: idx[2]]
    pd.testing.assert_series_equal(restricted_early["A"], within)


def test_implausible_market_cap_mask_flags_both_tails_and_never_nan():
    frame = pd.DataFrame(
        {
            "TINY": [SP500_MIN_PLAUSIBLE_MARKET_CAP_USD / 2.0],  # BNY/COL-style splice
            "HUGE": [SP500_MAX_PLAUSIBLE_MARKET_CAP_USD * 2.0],  # PARA-style splice
            "REAL": [3.0e10],
            "GONE": [np.nan],
        }
    )
    mask = implausible_market_cap_mask(frame)
    assert bool(mask["TINY"].iloc[0]) and bool(mask["HUGE"].iloc[0])
    assert not bool(mask["REAL"].iloc[0])
    # NaN is already "absent"; flagging it would double-count it as a defect.
    assert not bool(mask["GONE"].iloc[0])


def test_implausible_market_cap_mask_admits_the_whole_real_sp500_range():
    # Measured on Build D1's real production run: the 0.1st percentile of
    # eligible-cell market caps is $0.52B and the 99.9th is $3,889B. The band
    # must not touch anything inside the genuine range.
    frame = pd.DataFrame({"A": [2.0e9, 2.8e10, 3.9e12, 4.9e12]})
    assert not implausible_market_cap_mask(frame)["A"].any()


# --- build_point_in_time_market_cap -----------------------------------------


def test_market_cap_forward_fills_from_sparse_share_events_only():
    close = _frame({"A": [10.0, 10.0, 10.0, 10.0, 10.0]})
    idx = close.index
    # Share count known as of day 0 (100) and day 3 (200) only.
    shares = pd.Series([100.0, 200.0], index=[idx[0], idx[3]])
    market_cap, missing = build_point_in_time_market_cap(close, {"A": shares}, {})
    assert missing == []
    expected = pd.Series([1_000.0, 1_000.0, 1_000.0, 2_000.0, 2_000.0], index=idx, name="A")
    pd.testing.assert_series_equal(market_cap["A"], expected, check_names=False)


def test_market_cap_is_nan_before_the_first_known_share_count():
    close = _frame({"A": [10.0, 10.0, 10.0]})
    idx = close.index
    shares = pd.Series([50.0], index=[idx[2]])  # only known as of the LAST day
    market_cap, missing = build_point_in_time_market_cap(close, {"A": shares}, {})
    assert missing == []
    assert market_cap["A"].iloc[0:2].isna().all()
    assert market_cap["A"].iloc[2] == pytest.approx(500.0)


def test_market_cap_reports_tickers_with_no_shares_data_and_leaves_them_nan():
    close = _frame({"A": [10.0, 11.0], "B": [20.0, 21.0]})
    shares = {"A": pd.Series([100.0], index=[close.index[0]])}  # B absent entirely
    market_cap, missing = build_point_in_time_market_cap(close, shares, {})
    assert missing == ["B"]
    assert market_cap["B"].isna().all()
    assert market_cap["A"].notna().all()


def test_market_cap_future_share_counts_cannot_affect_past_days():
    # Look-ahead-impossibility check, mirroring test_cross_sectional's own
    # "future prices cannot affect past formations" test: perturbing a
    # LATER share-count observation must leave every EARLIER day's market
    # cap bit-identical.
    close = _frame({"A": [10.0] * 10})
    idx = close.index
    shares = pd.Series([100.0, 150.0, 300.0], index=[idx[0], idx[4], idx[8]])
    baseline, _ = build_point_in_time_market_cap(close, {"A": shares}, {})

    perturbed_shares = shares.copy()
    perturbed_shares.iloc[-1] = 999_999.0  # change only the LAST (future-most) observation
    perturbed, _ = build_point_in_time_market_cap(close, {"A": perturbed_shares}, {})

    pd.testing.assert_series_equal(
        baseline["A"].iloc[:8], perturbed["A"].iloc[:8], check_names=False
    )
    assert baseline["A"].iloc[8] != perturbed["A"].iloc[8]  # the changed day itself does differ


def test_market_cap_is_close_times_shares():
    close = _frame({"A": [10.0, 20.0, 30.0]})
    shares = pd.Series([2.0], index=[close.index[0]])
    market_cap, _ = build_point_in_time_market_cap(close, {"A": shares}, {})
    assert list(market_cap["A"]) == pytest.approx([20.0, 40.0, 60.0])


# --- split adjustment: the bug that made market cap jump at a split ---------
#
# THE BUG (shipped in Build D1, confirmed live 2026-08-26 before this fix):
# get_price_history returns SPLIT-ADJUSTED prices (every price before a split
# is back-adjusted into today's share units) while get_shares_outstanding
# returns the share counts AS FILED at the time. Multiplying the two
# understates market cap by the cumulative split factor on every date before
# a later split. Real measured example: AAPL's computed market cap was $517B
# on 2020-08-28 and $1,918B on 2020-10-22 -- a 3.96x jump on a day the price
# moved -0.95% -- purely because the share count crossed the 4-for-1 split's
# filing boundary. The real figure was ~$2.1T on both days.


def _split_scenario(
    *,
    share_events: list[tuple[int, float]],
    ex_date_offset: int,
    ratio: float,
    n_days: int = 14,
    price: float = 100.0,
) -> tuple[pd.DataFrame, dict[str, pd.Series], dict[str, pd.Series]]:
    """A company whose TRUE market cap never changes, seen through the same
    two data conventions yfinance really uses: a split-adjusted price (flat
    at `price`, since a pure split moves no value) and raw as-filed share
    counts that step up by `ratio` at whatever date the filing lands on.
    `share_events` are (day offset, raw count) pairs."""
    index = pd.bdate_range("2020-08-03", periods=n_days)
    close = pd.DataFrame({"A": [price] * n_days}, index=index)
    shares = pd.Series(
        [count for _, count in share_events],
        index=[index[offset] for offset, _ in share_events],
    )
    splits = {"A": pd.Series([ratio], index=[index[ex_date_offset]])}
    return close, {"A": shares}, splits


def test_market_cap_is_continuous_across_a_split_when_the_filing_lags():
    # The AAPL shape: 4-for-1 split on day 5, but the share count does not
    # show the post-split number until the next filing on day 9.
    close, shares, splits = _split_scenario(
        share_events=[(0, 100.0), (9, 400.0)], ex_date_offset=5, ratio=4.0
    )
    fixed, _ = build_point_in_time_market_cap(close, shares, splits)

    # A pure stock split creates no value: market cap must be flat.
    assert fixed["A"].nunique() == 1
    assert fixed["A"].iloc[0] == pytest.approx(40_000.0)

    # And the same inputs WITHOUT the split adjustment reproduce the shipped
    # bug exactly -- the regression this test exists to prevent.
    buggy, _ = build_point_in_time_market_cap(close, shares, {})
    assert buggy["A"].iloc[8] == pytest.approx(10_000.0)  # 4x understated
    assert buggy["A"].iloc[9] == pytest.approx(40_000.0)
    assert buggy["A"].iloc[9] / buggy["A"].iloc[8] == pytest.approx(4.0)


def test_split_adjustment_follows_the_share_series_own_jump_not_the_ex_date():
    # The NVDA-2024 shape: the share count switches to post-split units two
    # days BEFORE the ex-date. Keying off the ex-date would multiply an
    # already-post-split count by the ratio again and OVERSTATE market cap
    # 4x for those two days; keying off the series' own jump does not.
    close, shares, splits = _split_scenario(
        share_events=[(0, 100.0), (3, 400.0), (9, 400.0)], ex_date_offset=5, ratio=4.0
    )
    fixed, _ = build_point_in_time_market_cap(close, shares, splits)
    assert fixed["A"].nunique() == 1
    assert fixed["A"].iloc[0] == pytest.approx(40_000.0)
    # Days 3 and 4 (after the early filing, before the ex-date) are the ones
    # an ex-date-keyed adjustment would have blown up.
    assert fixed["A"].iloc[3] == pytest.approx(40_000.0)
    assert fixed["A"].iloc[4] == pytest.approx(40_000.0)


def test_split_adjustment_tolerates_a_share_count_that_also_moved():
    # NVDA's real 10-for-1 showed an observed jump of 9.63x, not 10.0,
    # because ordinary issuance moved the count in the same gap. The
    # detection has to recognise that as the split anyway.
    close, shares, splits = _split_scenario(
        share_events=[(0, 100.0), (6, 963.0)], ex_date_offset=5, ratio=10.0
    )
    fixed, _ = build_point_in_time_market_cap(close, shares, splits)
    assert fixed["A"].iloc[0] == pytest.approx(100_000.0)  # 100 * 10 * 100
    assert fixed["A"].iloc[6] == pytest.approx(96_300.0)  # the genuine -3.7% issuance move
    # No 10x artifact anywhere: the biggest one-day step is the real one.
    steps = (fixed["A"] / fixed["A"].shift()).dropna()
    assert steps.max() < 1.1


def test_a_series_already_restated_onto_todays_basis_is_left_alone():
    # THE OTHER HALF of the source's behaviour, and the reason the fallback
    # is "no adjustment" rather than "split at the ex-date": yfinance does
    # not always serve as-filed counts. For many older splits it serves a
    # series already restated onto today's share basis, flat across the
    # split, with no jump anywhere -- measured on NKE's real 2-for-1 of
    # 2015-12-24, whose series reads 1.704e9 ten weeks BEFORE the split and
    # 1.703e9 a year after. Adjusting that at the ex-date would split one
    # consistent basis into two and manufacture the very discontinuity this
    # code exists to remove (measured: it did exactly that to 20 of 164 real
    # split tickers before this rule was corrected).
    close, shares, splits = _split_scenario(
        share_events=[(0, 400.0), (9, 402.0)], ex_date_offset=5, ratio=4.0
    )
    fixed, _ = build_point_in_time_market_cap(close, shares, splits)
    # Untouched: 400 shares throughout, never 1600 before the ex-date.
    assert fixed["A"].iloc[0] == pytest.approx(40_000.0)
    assert fixed["A"].iloc[4] == pytest.approx(40_000.0)
    assert fixed["A"].iloc[9] == pytest.approx(40_200.0)
    steps = (fixed["A"] / fixed["A"].shift()).dropna()
    assert steps.max() < 1.01


def test_split_adjustment_detects_a_jump_filed_weeks_before_the_ex_date():
    # ICE's real 5-for-1 (ex-date 2016-11-04) switched on 2016-08-29, 67
    # days EARLY; MNST's 3-for-1 switched 69 days early. The search window
    # has to reach back far enough to see those, or they fall through to
    # "no adjustment" and stay 5x wrong.
    ex_date = pd.Timestamp("2016-11-04")
    jump_date = pd.Timestamp("2016-08-29")  # 67 calendar days before the ex-date
    raw = pd.Series(
        [119_046_000.0, 595_770_000.0, 595_341_000.0],
        index=[pd.Timestamp("2016-05-03"), jump_date, pd.Timestamp("2017-02-07")],
    )
    adjusted = split_adjust_share_counts(raw, pd.Series([5.0], index=[ex_date]))
    # The pre-jump count is restated into today's units; the two post-jump
    # counts already are, and must not be touched.
    assert list(adjusted) == pytest.approx([595_230_000.0, 595_770_000.0, 595_341_000.0])


def test_split_adjustment_ignores_a_jump_far_outside_the_ex_date_window():
    # A 4x share-count change years before the split is a financing event,
    # not the split, and must not be mistaken for its boundary. Here the
    # real split is at day 700 and a spurious 4x issuance lands at day 100,
    # far outside the search window around it.
    index = pd.bdate_range("2020-01-01", periods=800)
    raw = pd.Series([100.0, 400.0, 410.0], index=[index[0], index[100], index[750]])
    splits = pd.Series([4.0], index=[index[700]])
    adjusted = split_adjust_share_counts(raw, splits)
    # No jump matching the split inside its own window, so no adjustment —
    # and specifically NOT the [400, 400, 410] that taking the day-100
    # issuance for the boundary would have produced.
    assert list(adjusted) == pytest.approx([100.0, 400.0, 410.0])


def test_split_adjust_share_counts_is_a_no_op_without_splits():
    index = pd.bdate_range("2020-01-01", periods=5)
    raw = pd.Series([100.0, 110.0], index=[index[0], index[3]])
    pd.testing.assert_series_equal(split_adjust_share_counts(raw, None), raw)
    pd.testing.assert_series_equal(split_adjust_share_counts(raw, pd.Series(dtype=float)), raw)


# --- real-data regressions (recorded, not fetched) --------------------------
#
# Real values read off live yfinance on 2026-08-26 and frozen here, so these
# assert against genuine market data with no network dependence in the test
# suite. Sources: YFinanceProvider.get_market_cap_basis (close + split
# ratios) and .get_shares_outstanding (raw counts).


def test_real_aapl_2020_split_market_cap_is_continuous_and_the_right_size():
    dates = pd.to_datetime(["2020-08-04", "2020-08-28", "2020-08-31", "2020-10-22", "2020-10-23"])
    close = pd.DataFrame(
        {"AAPL": [109.66500091552734, 124.80750274658203, 129.0399932861328, 115.75, 115.04000091552734]},
        index=dates,
    )
    shares = {
        "AAPL": pd.Series(
            [4_275_630_080.0, 17_102_499_840.0],
            index=pd.to_datetime(["2020-08-04", "2020-10-22"]),
        )
    }
    splits = {"AAPL": pd.Series([4.0], index=pd.to_datetime(["2020-08-31"]))}

    fixed, _ = build_point_in_time_market_cap(close, shares, splits)
    buggy, _ = build_point_in_time_market_cap(close, shares, {})

    # AAPL was a ~$2.1 TRILLION company in August 2020. The shipped code
    # said $534bn -- roughly Salesforce-sized, and exactly 4x too small.
    assert 2.0e12 < fixed.loc["2020-08-28", "AAPL"] < 2.3e12
    assert buggy.loc["2020-08-28", "AAPL"] == pytest.approx(5.336e11, rel=1e-3)
    assert fixed.loc["2020-08-28", "AAPL"] / buggy.loc["2020-08-28", "AAPL"] == pytest.approx(4.0)

    # Across the split's filing boundary the fixed market cap moves ONLY as
    # much as the price did (the share count is unchanged to 6 dp), which is
    # what "a stock split creates no value" means operationally.
    cap_ratio = fixed.loc["2020-10-22", "AAPL"] / fixed.loc["2020-08-28", "AAPL"]
    price_ratio = close.loc["2020-10-22", "AAPL"] / close.loc["2020-08-28", "AAPL"]
    assert cap_ratio == pytest.approx(price_ratio, rel=1e-5)
    # The shipped code instead jumped ~4x on that same boundary.
    buggy_ratio = buggy.loc["2020-10-22", "AAPL"] / buggy.loc["2020-08-28", "AAPL"]
    assert buggy_ratio == pytest.approx(3.71, rel=0.02)


def test_real_nvda_2024_split_survives_a_share_count_filed_before_the_ex_date():
    # NVDA's 10-for-1 had ex-date 2024-06-10, but yfinance already carried
    # the post-split count on Saturday 2024-06-08 -- a non-trading day, so
    # this also exercises the union-then-ffill path.
    dates = pd.to_datetime(["2024-05-31", "2024-06-07", "2024-06-10", "2024-06-12", "2024-06-13"])
    close = pd.DataFrame(
        {"NVDA": [109.63300323486328, 120.88800048828125, 121.79000091552734,
                  125.19999694824219, 129.61000061035156]},
        index=dates,
    )
    shares = {
        "NVDA": pd.Series(
            [2_554_579_968.0, 24_598_300_672.0],
            index=pd.to_datetime(["2024-05-31", "2024-06-08"]),
        )
    }
    splits = {"NVDA": pd.Series([10.0], index=pd.to_datetime(["2024-06-10"]))}

    fixed, _ = build_point_in_time_market_cap(close, shares, splits)
    buggy, _ = build_point_in_time_market_cap(close, shares, {})

    # NVDA was a ~$3 TRILLION company in June 2024 -- the third largest in
    # the world. The shipped code priced it at ~$309bn on 2024-06-07.
    assert 2.9e12 < fixed.loc["2024-06-07", "NVDA"] < 3.2e12
    assert buggy.loc["2024-06-07", "NVDA"] < 4.0e11
    # Across the split boundary (2024-06-07 -> 2024-06-10) the fixed market
    # cap tracks the price, give or take the genuine -3.7% share-count
    # revision yfinance reports in the same gap. No 10x artifact.
    cap_step = fixed.loc["2024-06-10", "NVDA"] / fixed.loc["2024-06-07", "NVDA"]
    price_step = close.loc["2024-06-10", "NVDA"] / close.loc["2024-06-07", "NVDA"]
    assert cap_step == pytest.approx(price_step, rel=0.05)
    # The shipped code jumped ~10x on that same boundary instead.
    buggy_step = buggy.loc["2024-06-10", "NVDA"] / buggy.loc["2024-06-07", "NVDA"]
    assert buggy_step > 9.0


# --- run_round_d1_screening (production entry point, offline) --------------


def test_round_d1_screening_rejects_start_before_membership_coverage():
    with pytest.raises(ValueError, match="predates point-in-time membership"):
        run_round_d1_screening(date(2014, 1, 1), date(2020, 1, 1))


class _FakePriceProvider:
    """Synthetic-data stand-in for YFinanceProvider.get_price_history +
    get_market_cap_basis + get_shares_outstanding — no network. Every served
    ticker gets a real, resolvable share-count history except one
    deliberately excluded name (to exercise the tickers_without_shares path
    end to end).

    The market-cap-basis close is deliberately served at a DIFFERENT level
    from the signal close (see _MCAP_BASIS_MULTIPLE) so a test can prove
    which of the two the market-cap frame was actually built from — the
    distinction the dividend-adjustment half of this build's market-cap fix
    turns on."""

    def __init__(self, tickers_expected_member: list[str], seed: int = 5):
        self.tickers = tickers_expected_member
        self.seed = seed
        self.requested_prices: list[str] | None = None
        self.requested_shares: list[str] | None = None
        self.requested_mcap_basis: list[str] | None = None
        self.served_signal_close: pd.DataFrame | None = None

    def _close_frame(self, tickers, start, end):
        rng = np.random.default_rng(self.seed)
        index = pd.bdate_range(start, end)
        served = [t for t in tickers if t in self.tickers]
        return pd.DataFrame(
            {t: 100.0 * np.cumprod(1.0 + rng.normal(0.0003, 0.015, len(index))) for t in served},
            index=index,
        ), [t for t in tickers if t not in served]

    def get_price_history(self, tickers, start, end):
        self.requested_prices = list(tickers)
        close, missing = self._close_frame(tickers, start, end)
        self.served_signal_close = close
        return close, missing

    def get_market_cap_basis(self, tickers, start, end):
        self.requested_mcap_basis = list(tickers)
        close, missing = self._close_frame(tickers, start, end)
        splits = {t: pd.Series([2.0], index=[close.index[10]]) for t in close.columns}
        return close * _MCAP_BASIS_MULTIPLE, splits, missing

    def get_shares_outstanding(self, tickers, start, end):
        self.requested_shares = list(tickers)
        index = pd.bdate_range(start, end)
        shares: dict[str, pd.Series] = {}
        missing: list[str] = []
        for t in tickers:
            if t == self.tickers[0]:
                # Deliberately unresolvable, exercising the fallback path.
                missing.append(t)
                continue
            shares[t] = pd.Series([1.0e9], index=[index[0]])
        return shares, missing


_MCAP_BASIS_MULTIPLE = 1.25


_STALWART_MEMBERS = [
    "AAPL", "MSFT", "JPM", "JNJ", "KO", "PG", "XOM", "WMT", "MCD", "HD", "CAT", "MMM",
]


def test_round_d1_screening_runs_end_to_end_against_a_fake_provider():
    provider = _FakePriceProvider(_STALWART_MEMBERS)
    config = CrossSectionalConfig(min_names_per_leg=1)
    results, missing_price, tickers_without_shares = run_round_d1_screening(
        date(2020, 1, 6), date(2024, 12, 31), provider=provider, config=config
    )

    assert provider.requested_prices is not None
    assert len(provider.requested_prices) > 550
    assert set(_STALWART_MEMBERS) <= set(provider.requested_prices)
    assert set(missing_price) == set(provider.requested_prices) - set(_STALWART_MEMBERS)

    # Shares AND the market-cap basis are only fetched for tickers that
    # actually resolved a price.
    assert provider.requested_shares is not None
    assert set(provider.requested_shares) == set(_STALWART_MEMBERS)
    assert provider.requested_mcap_basis is not None
    assert set(provider.requested_mcap_basis) == set(_STALWART_MEMBERS)
    assert tickers_without_shares == [_STALWART_MEMBERS[0]]

    assert results
    for r in results:
        assert r.deflated_sharpe.n_trials == 21  # every definition counted, survivors or not
        assert np.isfinite(r.sharpe_annualized)
        assert r.n_trading_days >= 60
        assert r.n_formations > 0
    sharpes = [r.sharpe_annualized for r in results]
    assert sharpes == sorted(sharpes, reverse=True)


def test_round_d1_screening_builds_market_cap_from_the_basis_price_and_splits(monkeypatch):
    """The wiring half of the market-cap fix: the market_cap frame must be
    built from get_market_cap_basis's close (split-adjusted, dividend-
    UNadjusted) and its split ratios — never from get_price_history's
    dividend-adjusted signal close, which is what shipped."""
    from app.services.research_lab import cross_sectional_ivol

    captured: dict[str, object] = {}
    real_builder = cross_sectional_ivol.build_point_in_time_market_cap

    def spy(close, shares, splits):
        captured["close"] = close
        captured["splits"] = splits
        return real_builder(close, shares, splits)

    monkeypatch.setattr(cross_sectional_ivol, "build_point_in_time_market_cap", spy)

    provider = _FakePriceProvider(_STALWART_MEMBERS)
    run_round_d1_screening(
        date(2020, 1, 6),
        date(2024, 12, 31),
        provider=provider,
        config=CrossSectionalConfig(min_names_per_leg=1),
    )

    signal_close = provider.served_signal_close
    mcap_close = captured["close"]
    assert isinstance(mcap_close, pd.DataFrame)
    # The basis price actually used is the fake's mcap basis, not the signal
    # close: the ratio between them is _MCAP_BASIS_MULTIPLE everywhere.
    ratio = (mcap_close["MSFT"] / signal_close["MSFT"]).dropna()
    assert not ratio.empty
    assert ratio.round(10).nunique() == 1
    assert float(ratio.iloc[0]) == pytest.approx(_MCAP_BASIS_MULTIPLE)
    # And the split ratios reached the builder rather than being dropped.
    assert captured["splits"]
    assert set(captured["splits"]) == set(_STALWART_MEMBERS)
